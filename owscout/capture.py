"""Screen capture and the capture-session pipeline (SPEC §7, build step 5).

Screen capture is a read only — ``dxcam`` (falling back to ``mss``). Nothing is
injected into the game process (SPEC §11). Those libraries are heavy and
Windows-specific, so they are imported lazily: importing this module (and thus
the whole CLI) must not require them until an actual grab happens.

The pipeline logic — game-time from playback rate, change-detection write
scheduling, temporal-smoothed observations, side assignment and player
resolution — is pure and unit-tested. The live 1-2 fps sampling loop that wires
it to ``dxcam`` + the matcher is the runtime shell (``run_capture``), marked
no-cover.
"""

from __future__ import annotations

import difflib
import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Optional, Sequence

from .comps import comp_id_for
from .errors import CaptureError
from .integrity import (
    BAN_HIT_FAIL_RATE,
    banned_hero_hits,
    map_names_match,
    over_ban_hit_threshold,
)
from .match import DEFAULT_CONFIDENCE_FLOOR, DEFAULT_SMOOTHING_WINDOW, SlotMatch, TemporalSmoother
from .models import SIDE_LEFT, SIDE_RIGHT

# A captured frame is a numpy HxWx3 uint8 array in BGR order. Kept as Any so the
# module imports without numpy present.
Frame = Any

log = logging.getLogger("owscout.capture")

# Write an observation at least this often in GAME time even if the comp has not
# changed, so long unchanging stretches still leave a heartbeat (SPEC §7.3).
DEFAULT_WRITE_INTERVAL_MS = 30_000

# rapidfuzz-style 0..100 acceptance thresholds (SPEC §8.2).
DEFAULT_NAME_MATCH_THRESHOLD = 70.0
# Minimum lead one side-assignment orientation needs over the other to be trusted.
DEFAULT_SIDE_MARGIN = 1.0

# Name-similarity scorer: (a, b) -> 0..100. Default is stdlib difflib so the pure
# logic needs no rapidfuzz; the runtime may inject rapidfuzz for speed/quality.
Scorer = Callable[[str, str], float]

# CaptureError is imported above and re-exported here so existing
# `from .capture import CaptureError` call sites keep working.


def grab_frame(retries: int = 10, retry_delay: float = 0.05) -> tuple[Frame, int, int]:
    """Grab one frame of the primary display at native resolution.

    Returns ``(frame_bgr, width, height)``. Resolution is DERIVED from the
    frame, never assumed (SPEC §5). Tries ``dxcam`` first, then ``mss``.
    """
    frame = _grab_dxcam(retries, retry_delay)
    if frame is None:
        frame = _grab_mss()
    if frame is None:
        raise CaptureError(
            "no capture backend available — install owscout's capture extra "
            "(`pip install -e .[capture]`) to get dxcam/mss"
        )
    height, width = int(frame.shape[0]), int(frame.shape[1])
    return frame, width, height


# dxcam.create() spins up a D3D device (~seconds), and a second create for the
# same output raises — so the camera is created once and reused across grabs.
_DXCAM_CAMERA: Any = None


def _grab_dxcam(retries: int, retry_delay: float) -> Frame | None:
    global _DXCAM_CAMERA
    try:
        import dxcam
    except ImportError:
        log.debug("dxcam not available")
        return None
    if _DXCAM_CAMERA is None:
        _DXCAM_CAMERA = dxcam.create(output_color="BGR")
    camera = _DXCAM_CAMERA
    if camera is None:
        return None
    # grab() returns None when there is no new frame since the last call; retry
    # briefly to get a fresh one.
    for _ in range(max(1, retries)):
        frame = camera.grab()
        if frame is not None:
            return frame
        time.sleep(retry_delay)
    log.debug("dxcam returned no frame after %d tries", retries)
    return None


def _grab_mss() -> Frame | None:
    try:
        import mss
        import numpy as np
    except ImportError:
        log.debug("mss/numpy not available")
        return None
    with mss.mss() as sct:
        monitor = sct.monitors[1]  # primary display
        shot = sct.grab(monitor)
        # mss gives BGRA; drop alpha to BGR.
        return np.array(shot)[:, :, :3]


def save_frame(frame: Frame, out_dir: str | Path, tag: str) -> str:
    """Write ``frame`` (BGR) to ``out_dir`` as a PNG. Returns the path.

    Used by ``calibrate`` to keep the full frame it was calibrated against.
    """
    try:
        import cv2
    except ImportError as exc:  # pragma: no cover - runtime-only path
        raise CaptureError(
            "opencv-python is required to save frames — "
            "`pip install -e .[capture]`"
        ) from exc
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%dT%H%M%S")
    path = out / f"frame_{tag}_{stamp}.png"
    cv2.imwrite(str(path), frame)
    return str(path)


# --- game time (SPEC §7.1/§7.3) ----------------------------------------------


def game_time_ms(wall_elapsed_s: float, speed: float) -> int:
    """Game-time elapsed given wall-clock seconds and the operator's playback
    speed. Under 4x playback, 1 wall-second is 4 game-seconds. Playback rate is
    config, never detected (SPEC §7.3)."""
    if speed <= 0:
        raise ValueError(f"speed must be positive, got {speed}")
    return int(wall_elapsed_s * speed * 1000)


# --- change-detection write scheduling (SPEC §7.3) ---------------------------


def should_write(
    current_key: tuple[Optional[str], ...],
    last_key: Optional[tuple[Optional[str], ...]],
    game_ts_ms: int,
    last_written_ts_ms: Optional[int],
    interval_ms: int,
) -> bool:
    """Write an observation only when the (smoothed) comp differs from the last
    written, or the game-time interval has elapsed — whichever comes first. Do
    not store 1,200 identical rows per map (SPEC §7.3)."""
    if last_key is None or last_written_ts_ms is None:
        return True                          # nothing written yet
    if current_key != last_key:
        return True                          # a swap
    return (game_ts_ms - last_written_ts_ms) >= interval_ms


@dataclass
class SmoothedObservation:
    """A committed sample for one side: the temporally-smoothed comp at a
    game-time. ``comp_id`` is set only when every slot resolved (SPEC §4)."""

    side: str
    sample_ts_ms: int
    slot_guids: list[Optional[str]]
    slot_confidences: list[float]
    resolved: bool
    min_confidence: float
    comp_id: Optional[str]


@dataclass
class _SideState:
    smoother: TemporalSmoother
    last_key: Optional[tuple[Optional[str], ...]] = None
    last_ts_ms: Optional[int] = None


class CaptureSession:
    """Accumulates per-frame matches per side, smooths them, and emits an
    observation only when the change-detection schedule says to (SPEC §7.3, §8.3).

    ``observe`` is called once per side per sampled frame; the live loop and the
    tests drive it the same way.
    """

    def __init__(
        self,
        num_slots: int,
        *,
        window: int = DEFAULT_SMOOTHING_WINDOW,
        write_interval_ms: int = DEFAULT_WRITE_INTERVAL_MS,
    ) -> None:
        self.num_slots = num_slots
        self.write_interval_ms = write_interval_ms
        self._sides: dict[str, _SideState] = {
            side: _SideState(TemporalSmoother(num_slots, window))
            for side in (SIDE_LEFT, SIDE_RIGHT)
        }

    def observe(
        self, side: str, matches: Sequence[SlotMatch], game_ts_ms: int
    ) -> Optional[SmoothedObservation]:
        state = self._sides[side]
        state.smoother.push_matches(matches)
        smoothed = state.smoother.current()
        guids = [g for g, _ in smoothed]
        key = tuple(guids)

        if not should_write(key, state.last_key, game_ts_ms, state.last_ts_ms,
                            self.write_interval_ms):
            return None

        confs = [c for _, c in smoothed]
        resolved = all(g is not None for g in guids)
        obs = SmoothedObservation(
            side=side,
            sample_ts_ms=game_ts_ms,
            slot_guids=guids,
            slot_confidences=confs,
            resolved=resolved,
            min_confidence=min(confs) if confs else 0.0,
            # comp_id needs the concrete guids; only meaningful when resolved.
            comp_id=comp_id_for([g for g in guids if g is not None]) if resolved else None,
        )
        state.last_key = key
        state.last_ts_ms = game_ts_ms
        return obs


# --- side assignment (SPEC §7.3, §8.2) ---------------------------------------


def _difflib_ratio(a: str, b: str) -> float:
    return difflib.SequenceMatcher(None, a.lower().strip(), b.lower().strip()).ratio() * 100.0


def _affinity(names: Sequence[str], roster: Sequence[str], scorer: Scorer) -> float:
    """Sum over each OCR'd name of its best match score against a roster."""
    return sum(max((scorer(n, r) for r in roster), default=0.0) for n in names)


def assign_sides(
    left_names: Sequence[str],
    right_names: Sequence[str],
    faction1_names: Sequence[str],
    faction2_names: Sequence[str],
    *,
    scorer: Scorer = _difflib_ratio,
    margin: float = DEFAULT_SIDE_MARGIN,
) -> Optional[str]:
    """Which faction is on side A (the LEFT HUD strip): 'faction1', 'faction2',
    or None if the OCR'd names don't clearly favour either orientation.

    Compares the two orientations (left=f1/right=f2 vs the swap) by total name
    affinity and picks the stronger, if it leads by ``margin`` (SPEC §8.2)."""
    direct = _affinity(left_names, faction1_names, scorer) + _affinity(right_names, faction2_names, scorer)
    swap = _affinity(left_names, faction2_names, scorer) + _affinity(right_names, faction1_names, scorer)
    if direct - swap > margin:
        return "faction1"
    if swap - direct > margin:
        return "faction2"
    return None


# --- player resolution (SPEC §8.2) -------------------------------------------


def resolve_player(
    ocr_name: str,
    roster: Sequence[tuple[str, str]],   # (player_id, nickname)
    *,
    scorer: Scorer = _difflib_ratio,
    threshold: float = DEFAULT_NAME_MATCH_THRESHOLD,
) -> Optional[str]:
    """Fuzzy-match one OCR'd in-game name against a candidate list of five
    (SPEC §8.2). Returns player_id above ``threshold``, else None (review)."""
    best_id: Optional[str] = None
    best_score = threshold
    for player_id, nickname in roster:
        score = scorer(ocr_name, nickname)
        if score >= best_score:
            best_score, best_id = score, player_id
    return best_id


# --- runtime capture loop (dxcam + matcher; not unit-tested) -----------------


def run_capture(  # pragma: no cover - runtime-only path
    db: "Any",
    faceit_db_path: str,
    *,
    demo_code: str,
    hud_variant: str = "default",
    speed: float = 1.0,
    fps: float = 1.5,
    duration_s: Optional[float] = None,
    side_a_team: Optional[str] = None,
    write_interval_ms: int = DEFAULT_WRITE_INTERVAL_MS,
    confidence_floor: float = DEFAULT_CONFIDENCE_FLOOR,
    require_division: Optional[str] = None,
    dry_run: bool = False,
) -> dict[str, int]:
    """Sample the replay under speed-mode playback, match each side, temporally
    smooth, and persist observations on change/interval (SPEC §7). Loops until
    ``duration_s`` elapses (game-time) or the operator interrupts.

    Everything about the map is derived from ``demo_code`` (SPEC §7); only the
    hero portraits are read off the screen.
    """
    from .context import derive_code_context
    from .faceit import connect_ro, hero_roles as load_hero_roles, load_heroes, resolve_team_id
    from .match import (
        crop_roi, face_subrect, make_template_scorer, match_frame, pad_rect,
    )

    cv2, _np = _import_cv2_np_for_capture()

    ctx = derive_code_context(db, faceit_db_path, demo_code)
    if require_division is not None and ctx.division != require_division:
        raise CaptureError(
            f"{demo_code} is a {ctx.division or 'unknown'}-division game "
            f"({ctx.championship_name}); owscout is set to {require_division} only. "
            f"Pass --division all to override.")
    log.info("capturing %s: %s game %d (%s)", demo_code, ctx.match_id, ctx.game_no, ctx.map_name)

    # Establish which faction is on the LEFT HUD strip (side A). OCR-based auto
    # assignment (SPEC §8.2) needs an OCR backend; without one, the operator sets
    # it explicitly, else we default to faction1 and warn.
    side_a_faction = "faction1"
    with connect_ro(faceit_db_path) as fdb:
        hero_roles = load_hero_roles(fdb)
        hero_names = {h.guid: h.name for h in load_heroes(fdb)}
        if side_a_team is not None:
            tid = resolve_team_id(fdb, side_a_team)
            side_a_faction = "faction1" if tid == ctx.faction1_team_id else "faction2"
        else:
            log.warning("no --side-a-team given and OCR side assignment unavailable; "
                        "assuming side A (left) = %s", ctx.faction1_team_name)
    for _h in db.list_custom_heroes():  # include operator-added (live-game) heroes
        hero_names[_h.guid] = _h.name
        if _h.role:
            hero_roles[_h.guid] = _h.role

    height_width = _profile_and_refs(db, cv2, hud_variant)
    profile, refs = height_width
    banned = {b.hero_guid for b in ctx.bans}

    map_instance_id: Optional[int] = None
    if not dry_run:
        map_instance_id = db.upsert_map_instance_from_context(
            ctx, side_a_faction, profile_id=profile.id, map_verified=None)

    session = CaptureSession(profile.team_size, write_interval_ms=write_interval_ms)
    score_fn = make_template_scorer(cv2)
    side_slots = {s: [face_subrect(r) for r in profile.slots[s]]
                  for s in (SIDE_LEFT, SIDE_RIGHT)}

    counts = {"frames": 0, "written": 0, "skipped": 0}
    integ = {"resolved_slots": 0, "banned_hits": 0, "low_conf": 0}
    map_mismatch: Optional[int] = None
    map_checked = False
    warned_ban = False
    start = time.perf_counter()
    period = 1.0 / fps
    try:
        while True:
            frame, w, h = grab_frame()
            if (w, h) != (profile.resolution_w, profile.resolution_h):
                counts["skipped"] += 1
                continue
            game_ts = game_time_ms(time.perf_counter() - start, speed)
            if duration_s is not None and (time.perf_counter() - start) >= duration_s:
                break

            # §9.2: verify the map matches the code on the first parsed frame.
            if not map_checked and map_instance_id is not None:
                map_mismatch = _verify_map(db, cv2, frame, profile, ctx, map_instance_id)
                map_checked = True

            counts["frames"] += 1
            for side in (SIDE_LEFT, SIDE_RIGHT):
                matches = match_frame(
                    frame, side_slots[side], refs, hero_roles, banned, hero_names,
                    confidence_floor=confidence_floor,
                    crop_fn=_padded_crop, score_fn=score_fn,
                )
                obs = session.observe(side, matches, game_ts)
                if obs is None:
                    continue
                integ["resolved_slots"] += sum(1 for g in obs.slot_guids if g is not None)
                integ["low_conf"] += sum(1 for g in obs.slot_guids if g is None)
                # §9.1: a slot resolving to a banned hero is provably wrong —
                # the ROI profile is likely stale. Do not write it.
                hits = banned_hero_hits(obs.slot_guids, banned)
                if hits:
                    integ["banned_hits"] += len(hits)
                    if not warned_ban:
                        names = ", ".join(hero_names.get(g, g) for g in hits)
                        log.error("Slot resolved to banned hero %s — ROI profile likely "
                                  "stale after patch. Run `owscout calibrate`.", names)
                        warned_ban = True
                    continue
                if map_mismatch == 1:   # refuse to write on a map mismatch (§9.2)
                    continue
                if not dry_run and map_instance_id is not None:
                    _persist_observation(db, map_instance_id, obs, matches,
                                         hero_roles, hero_names)
                    counts["written"] += 1
            time.sleep(period)
    except KeyboardInterrupt:
        log.info("interrupted by operator")

    # §9.1: a high banned-hit rate means the ROIs have drifted — fail the run.
    over = over_ban_hit_threshold(integ["banned_hits"], integ["resolved_slots"])
    if not dry_run:
        db.insert_capture_log(
            demo_code=demo_code, map_instance_id=map_instance_id,
            samples_taken=counts["frames"], samples_written=counts["written"],
            low_confidence=integ["low_conf"], banned_hero_hits=integ["banned_hits"],
            map_mismatch=map_mismatch, errors=1 if over else 0,
        )
        # Mark a broken run failed; a good run stays a DRAFT (not greenlit) until
        # the operator reviews and finalizes it.
        if over:
            db.upsert_code_status(demo_code, "failed")
    log.info("done: %d frames, %d observations written, %d skipped (%d banned-hits, mismatch=%s)",
             counts["frames"], counts["written"], counts["skipped"],
             integ["banned_hits"], map_mismatch)
    if over:
        raise CaptureError(
            f"banned-hero hit rate {integ['banned_hits']}/{integ['resolved_slots']} "
            f"exceeds {BAN_HIT_FAIL_RATE:.0%} — ROI profile is stale, run `owscout calibrate`")
    return counts


def run_hotkey_capture(  # pragma: no cover - runtime-only path
    db: "Any",
    faceit_db_path: str,
    *,
    demo_code: str,
    hud_variant: str = "default",
    side_a_team: Optional[str] = None,
    hotkey: str = "f8",
    round_hotkey: str = "f7",
    submap_hotkey: str = "f6",
    undo_hotkey: str = "f9",
    attack_toggle_hotkey: str = "f5",
    confidence_floor: float = DEFAULT_CONFIDENCE_FLOOR,
    require_division: Optional[str] = None,
    emit: Callable[[str], None] = print,
    debug_dir: Optional[str] = None,
    dry_run: bool = False,
) -> dict[str, int]:
    """Snapshot capture: instead of a continuous loop, the operator navigates the
    replay (using OW's bookmarks to jump to spawn / post-fight moments where comps
    change) and presses ``hotkey`` to grab the comp on screen. Comps are step
    functions, so snapshotting the steps is faster and cleaner than sampling.

    The hotkey callback only signals; the grab/match/write all happen on the main
    thread (SQLite is single-thread)."""
    import threading

    from .context import derive_code_context
    from .faceit import connect_ro, hero_roles as load_hero_roles, load_heroes, resolve_team_id
    from .match import crop_roi, face_subrect, make_template_scorer, match_frame, pad_rect

    try:
        import keyboard
    except ImportError as exc:
        raise CaptureError(
            "the 'keyboard' package is required for hotkey capture — "
            "`pip install -e .[capture]`") from exc

    cv2, _np = _import_cv2_np_for_capture()
    ctx = derive_code_context(db, faceit_db_path, demo_code)
    if require_division is not None and ctx.division != require_division:
        raise CaptureError(
            f"{demo_code} is a {ctx.division or 'unknown'}-division game "
            f"({ctx.championship_name}); owscout is set to {require_division} only. "
            f"Pass --division all to override.")

    side_a_faction = "faction1"
    with connect_ro(faceit_db_path) as fdb:
        hero_roles = load_hero_roles(fdb)
        hero_names = {h.guid: h.name for h in load_heroes(fdb)}
        if side_a_team is not None:
            tid = resolve_team_id(fdb, side_a_team)
            side_a_faction = "faction1" if tid == ctx.faction1_team_id else "faction2"
        else:
            log.warning("no --side-a-team given; assuming side A (left) = %s",
                        ctx.faction1_team_name)
    for _h in db.list_custom_heroes():  # include operator-added (live-game) heroes
        hero_names[_h.guid] = _h.name
        if _h.role:
            hero_roles[_h.guid] = _h.role

    profile, refs = _profile_and_refs(db, cv2, hud_variant)
    banned = {b.hero_guid for b in ctx.bans}
    map_instance_id: Optional[int] = None
    if not dry_run:
        map_instance_id = db.upsert_map_instance_from_context(
            ctx, side_a_faction, profile_id=profile.id, map_verified=None)
    score_fn = make_template_scorer(cv2)
    side_slots = {s: [face_subrect(r) for r in profile.slots[s]] for s in (SIDE_LEFT, SIDE_RIGHT)}

    snap_evt, done_evt = threading.Event(), threading.Event()
    keyboard.add_hotkey(hotkey, snap_evt.set)
    keyboard.add_hotkey("esc", done_evt.set)
    emit(f"HOTKEY capture ready for {ctx.map_name} ({ctx.faction1_team_name} vs "
          f"{ctx.faction2_team_name}).")
    emit(f"  Jump to key moments in the replay, press '{hotkey}' to snapshot the comp. "
          f"Press 'esc' when done.")

    # Control maps rotate between sub-maps with different geometry; let the operator
    # tag the current sub-map with number keys so snapshots are attributed to it.
    from .maps import submaps_for
    submaps = submaps_for(ctx.map_name)
    cur_sub: list[Optional[str]] = [None]
    used_subs: set[str] = set()   # sub-maps already played this map
    if submaps:
        def _cycle_sub() -> None:
            # Offer the sub-maps not yet played; fall back to all once exhausted.
            pool = [s for s in submaps if s not in used_subs] or list(submaps)
            nxt = pool[0] if cur_sub[0] not in pool else pool[
                (pool.index(cur_sub[0]) + 1) % len(pool)]
            cur_sub[0] = nxt
            used_subs.add(nxt)
            left = [s for s in submaps if s not in used_subs]
            emit(f"  sub-map -> {nxt}" + (f"  (remaining: {', '.join(left)})" if left else ""))
        keyboard.add_hotkey(submap_hotkey, _cycle_sub)
        _cycle_sub()   # control maps start on a sub-map; operator can change it
        emit(f"  CONTROL MAP — press '{submap_hotkey}' to pick the sub-map "
             f"(of {', '.join(submaps)}); '{round_hotkey}' advances to the next one.")

    # Attack/defend. Escort/Hybrid only: RED (side 'b') attacks round 1, and the
    # teams swap each round. From round 3 (both teams fully capped) the attacker is
    # decided by time banks, not parity — so the operator confirms it there.
    phased = (ctx.map_category or "").strip().lower() in ("escort", "hybrid", "assault")
    attacker = ["b"]   # side currently attacking

    def _phase_for(side: str) -> Optional[str]:
        if not phased:
            return None
        return "attack" if side == attacker[0] else "defend"

    def _toggle_attacker() -> None:
        attacker[0] = "a" if attacker[0] == "b" else "b"
        who = ctx.faction1_team_name if attacker[0] == "a" else ctx.faction2_team_name
        emit(f"  attacking now: side {attacker[0]} ({who or '?'})")
    if phased:
        keyboard.add_hotkey(attack_toggle_hotkey, _toggle_attacker)
        emit(f"  {ctx.map_category}: red (right) attacks round 1. "
             f"Press '{attack_toggle_hotkey}' to correct who is attacking.")

    # Round marker: press round_hotkey at each round start / point capture so the
    # snapshots segment into rounds (see how comps change round to round).
    cur_round = [1]

    def _next_round() -> None:
        cur_round[0] += 1
        emit(f"  round -> {cur_round[0]}")
        if phased:
            _toggle_attacker()
            if cur_round[0] >= 3 and cur_round[0] % 2 == 1:
                emit(f"  ROUND {cur_round[0]}: who attacks is decided by time bank — "
                     f"press '{attack_toggle_hotkey}' if it is the other team.")
        if submaps:
            remaining = [s for s in submaps if s not in used_subs]
            if remaining:
                cur_sub[0] = remaining[0]
                used_subs.add(remaining[0])
                emit(f"  sub-map -> {cur_sub[0]}  ('{submap_hotkey}' to pick another)")
    keyboard.add_hotkey(round_hotkey, _next_round)
    emit(f"  Press '{round_hotkey}' at each new round / point capture (currently round 1).")

    # Undo: drop the last written snapshot (both sides).
    undo_evt = threading.Event()
    keyboard.add_hotkey(undo_hotkey, undo_evt.set)
    emit(f"  Press '{undo_hotkey}' to UNDO the last snapshot.")

    snaps = 0
    written = 0
    last_kept: Optional[tuple[Any, ...]] = None  # (comp a, comp b, round, sub) last KEPT
    written_ts: list[int] = []                   # sample_ts of each kept snapshot (undo)
    while not done_evt.is_set():
        if undo_evt.is_set():
            undo_evt.clear()
            if written_ts and not dry_run and map_instance_id is not None:
                ts = written_ts.pop()
                db.delete_observations_at(map_instance_id, ts)
                snaps = max(0, snaps - 1)
                last_kept = None      # so the same comp can be re-captured
                emit(f"  UNDID the last snapshot ({snaps} kept)")
            else:
                emit("  nothing to undo")
            continue
        if not snap_evt.wait(timeout=0.15):
            continue
        snap_evt.clear()
        frame, w, h = grab_frame()
        if (w, h) != (profile.resolution_w, profile.resolution_h):
            emit(f"  resolution {w}x{h} != profile — skipped")
            continue
        if debug_dir is not None:  # diagnostics: save the exact frame we matched
            import os as _os
            _os.makedirs(debug_dir, exist_ok=True)
            dpath = _os.path.join(debug_dir, f"snap_{snaps + 1:02d}_{w}x{h}.png")
            cv2.imwrite(dpath, frame)
            emit(f"  saved debug frame {dpath}")
        matches_by_side = {
            side: match_frame(frame, side_slots[side], refs, hero_roles, banned,
                              hero_names, confidence_floor=confidence_floor,
                              crop_fn=_padded_crop, score_fn=score_fn)
            for side in (SIDE_LEFT, SIDE_RIGHT)
        }
        # Skip a repeat: same round/sub-map, and the comps either identical or
        # differing ONLY by slots that dropped to unknown (a worse read of the same
        # moment is not new information). A new round/sub-map always keeps.
        ga = tuple(m.hero_guid for m in matches_by_side[SIDE_LEFT])
        gb = tuple(m.hero_guid for m in matches_by_side[SIDE_RIGHT])
        if last_kept is not None:
            la, lb, lr, ls = last_kept
            if ((lr, ls) == (cur_round[0], cur_sub[0])
                    and _only_lost_known(la, ga) and _only_lost_known(lb, gb)):
                emit("  (unchanged / only unknowns — skipped)")
                continue
        last_kept = (ga, gb, cur_round[0], cur_sub[0])
        written_ts.append(snaps)
        line = []
        for side in (SIDE_LEFT, SIDE_RIGHT):
            matches = matches_by_side[side]
            if not dry_run and map_instance_id is not None:
                if _persist_matches(db, map_instance_id, side, snaps, matches,
                                    hero_roles, hero_names, sub_map=cur_sub[0],
                                    round_no=cur_round[0], phase=_phase_for(side)):
                    written += 1
            shown = "/".join((hero_names.get(m.hero_guid or "", "?")[:4] if m.resolved else "??")
                             for m in matches)
            line.append(f"{side}:{shown}")
        snaps += 1
        sub_tag = f"  [{cur_sub[0]}]" if cur_sub[0] else ""
        emit(f"  snap {snaps} (R{cur_round[0]}): " + "   ".join(line) + sub_tag)

    keyboard.clear_all_hotkeys()
    # Do NOT greenlight the code here — a capture is a DRAFT until the operator
    # reviews it and finalizes. Finalizing marks the code captured and lets the
    # map into exports (see Database.finalize_map).
    emit(f"done. {snaps} snapshot(s) captured as a DRAFT — review and finalize "
         "to include it in the scout data.")
    return {"snaps": snaps, "written": written}


def _padded_crop(frame: Frame, rect: Any) -> Any:
    """Crop a ROI with a small margin so the matcher can slide the ref inside it
    (see match.MATCH_PAD_PX). Matching only — refs are learned from the tight ROI."""
    from .match import crop_roi as _crop, pad_rect as _pad
    return _crop(frame, _pad(rect))


def _only_lost_known(prev: Sequence[Optional[str]], new: Sequence[Optional[str]]) -> bool:
    """True when ``new`` differs from ``prev`` only by slots that dropped to unknown.

    A snapshot that reads the same comp but with more '??' is a worse read of the
    same moment, not new information — so it counts as a repeat. A slot changing to
    a DIFFERENT hero, or resolving from '??' to a hero, is a real change.
    """
    if len(prev) != len(new):
        return False
    for p, n in zip(prev, new):
        if p == n or n is None:
            continue
        return False
    return True


def _persist_matches(  # pragma: no cover
    db: "Any", map_instance_id: int, side: str, ts: int, matches: Sequence[SlotMatch],
    hero_roles: dict[str, str], hero_names: dict[str, str],
    sub_map: Optional[str] = None, round_no: Optional[int] = None,
    phase: Optional[str] = None,
) -> bool:
    """Persist one frame's matches as a single observation (no smoothing). Returns
    True if the observation fully resolved."""
    from .comps import canonical_comp

    guids = [m.hero_guid for m in matches]
    resolved = all(g is not None for g in guids) and len(guids) > 0
    comp = (canonical_comp([g for g in guids if g is not None], hero_roles, hero_names)
            if resolved else None)
    slots = [
        {"slot_index": i, "hero_guid": m.hero_guid, "confidence": m.confidence,
         "is_dead": 1 if m.state == "dead" else 0, "expected_role": None,
         "ingame_name_raw": None, "player_id": None}
        for i, m in enumerate(matches)
    ]
    db.upsert_comp_observation(
        map_instance_id=map_instance_id, side=side, sample_ts_ms=ts,
        comp_id=comp.comp_id if comp else None,
        min_slot_confidence=min((m.confidence for m in matches), default=0.0),
        resolved=1 if resolved else 0, slots=slots, comp=comp, sub_map=sub_map,
        round_no=round_no, phase=phase,
    )
    return resolved


def _verify_map(  # pragma: no cover - runtime-only path
    db: "Any", cv2: Any, frame: Any, profile: Any, ctx: Any, map_instance_id: int
) -> Optional[int]:
    """§9.2: OCR the map name and compare to the code's expected map. Returns
    1 (mismatch), 0 (match), or None (could not check). On mismatch, flags the
    instance unverified and refuses further writes (the caller enforces that)."""
    ocr = _ocr_map_name(cv2, frame, profile)
    if not ocr or not ctx.map_name:
        return None
    ok = map_names_match(ocr, ctx.map_name)
    db.set_map_verified(map_instance_id, 1 if ok else 0)
    if not ok:
        log.error("MAP MISMATCH: replay shows %r but demo_code %s is recorded as %r "
                  "(match %s) — refusing to write. demoURLs index likely misaligned "
                  "(see SPEC §9.2).", ocr, ctx.demo_code, ctx.map_name, ctx.match_id)
    return 0 if ok else 1


def _ocr_map_name(cv2: Any, frame: Any, profile: Any) -> Optional[str]:  # pragma: no cover
    """OCR the on-screen map name. Requires both an OCR backend (pytesseract)
    and a calibrated map-name ROI; until a map-name anchor is calibrated this
    returns None (check skipped, not failed)."""
    return None


def _import_cv2_np_for_capture() -> tuple[Any, Any]:  # pragma: no cover
    try:
        import cv2
        import numpy as np
    except ImportError as exc:
        raise CaptureError(
            "opencv-python + numpy are required for capture — `pip install -e .[capture]`"
        ) from exc
    return cv2, np


def _profile_and_refs(db: "Any", cv2: Any, hud_variant: str) -> tuple[Any, Any]:  # pragma: no cover
    frame, w, h = grab_frame()
    profile = db.get_active_profile(w, h, hud_variant)
    if profile is None:
        raise CaptureError(
            f"no calibrated profile for {w}x{h} '{hud_variant}' — run `owscout calibrate`")
    refs = db.get_refs(profile.id)
    if not refs:
        raise CaptureError(
            f"no refs for profile #{profile.id} — run `owscout refs capture` first")
    return profile, refs


def _persist_observation(  # pragma: no cover
    db: "Any", map_instance_id: int, obs: "SmoothedObservation", matches: Sequence[SlotMatch],
    hero_roles: dict[str, str], hero_names: dict[str, str],
) -> None:
    from .comps import canonical_comp

    slots = [
        {"slot_index": i, "hero_guid": obs.slot_guids[i],
         "confidence": obs.slot_confidences[i],
         "is_dead": 1 if matches[i].state == "dead" else 0,
         "expected_role": None, "ingame_name_raw": None, "player_id": None}
        for i in range(len(obs.slot_guids))
    ]
    # A resolved observation references a comps row (FK) — build + pass it so the
    # DB layer inserts the comp in the same transaction.
    comp = None
    if obs.resolved:
        guids = [g for g in obs.slot_guids if g is not None]
        comp = canonical_comp(guids, hero_roles, hero_names)
    db.upsert_comp_observation(
        map_instance_id=map_instance_id, side=obs.side, sample_ts_ms=obs.sample_ts_ms,
        comp_id=obs.comp_id, min_slot_confidence=obs.min_confidence,
        resolved=1 if obs.resolved else 0, slots=slots, comp=comp,
    )

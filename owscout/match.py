"""``owscout match`` — constraint-aware matching of a single frame (SPEC §13
step 3, the gate).

This is where the accuracy comes from (SPEC §8.1): before matching a slot we
reduce the candidate ref set by the map's bans (a banned hero is impossible, not
unlikely) and by the expected role for that slot (the observer HUD orders slots
by role). A tank slot becomes 1-of-14, not 1-of-52.

The reduction and orchestration are pure and injectable, so the gate's logic is
unit-tested without the game or OpenCV. The actual per-ROI template match and
dead-state detection are the injected defaults, exercised only at runtime.
"""

from __future__ import annotations

import logging
import os
from collections import deque
from dataclasses import dataclass
from typing import Any, Callable, Deque, Optional, Sequence

from .db import Database
from .errors import CaptureError
from .faceit import (
    KNOWN_ROLES,
    connect_ro,
    hero_roles as load_hero_roles,
    load_bans,
    load_heroes,
    load_team_roles,
    resolve_team_id,
    team_ids_for_map,
)
from .models import STATE_ALIVE, STATE_DEAD, HeroRef, Rect, RoiProfile

log = logging.getLogger("owscout.match")

# Best template-match score below this and we refuse to resolve the slot (SPEC
# §8.3). Better a NULL for review than a confident wrong answer.
#
# The right value depends on the ref source, and matching is argmax over a
# constrained set, so the floor only gates resolved-vs-review, not correctness:
#   * observer-derived refs (refs capture/from-frame): correct ~0.83-0.92, worst
#     wrong ~0.53 (validated on real frames, screenshots/).
#   * one-image gallery-sheet refs (refs from-sheet): correct ~0.56-0.83, worst
#     wrong <0.48 (validated on a real observer frame).
# 0.55 resolves both while rejecting wrong heroes and empty slots; observer refs,
# as they accumulate, sit comfortably above it.
DEFAULT_CONFIDENCE_FLOOR = 0.55

# Mean-saturation below this routes the ROI to the 'dead' (desaturated) ref set
# before matching (SPEC §8.3). Tunable; the gate is where you learn the value.
DEFAULT_DEAD_SATURATION = 40.0

# NOTE (operator-confirmed, 2026-07-15): the observer HUD slot order is NOT fixed
# by role — it varies frame to frame. So we do NOT pre-assign an expected role by
# slot position. Instead each slot is matched against the full non-banned ref set
# and the role is read off the matched hero (heroes.role). The team's known 1/2/2
# composition (from round_players) is used as a consistency check, not a per-slot
# filter. This supersedes the fixed-order reading of SPEC §8.1 step 2.

# The ult indicator (charge "N%" or the ready checkmark) sits to the LEFT of the
# portrait and never overlaps the face (operator-confirmed 2026-07-17, verified
# on screenshots/dead/). The hero face occupies roughly the right ~58% of the
# cell. We start the crop at 0.42 so it captures the FULL face width while staying
# clear of the ult digits (which end ~0.42 even at 99%). Applied identically to
# ref capture and to matching so the two stay aligned. Widening from the old 0.55
# (right 45%, which cut the face in half) to 0.42 keeps self-match ~0.99 and
# nudges the hard cross-ult-charge case up (0.877 -> 0.894 on real frames).
ULT_OVERLAY_LEFT_FRACTION = 0.42

# Operators box the full HUD cell (portrait + player name + ability bar). We keep
# only the TOP band of the cell and STOP ABOVE THE NAME BAR — the real vertical
# constraint. The name bar's background flips (black when the hero is dead, grey
# when alive), so any crop that reaches it matches badly across a hero's own
# alive/dead frames. Verified on real 2560x1440 frames (screenshots/dead/): at
# 0.45 the same hero across DEAD vs ALIVE frames self-matches ~0.88; at 0.52 the
# name bar starts leaking in and it falls to ~0.72; by 0.62 it's ~0.51. So 0.45
# is the tallest safe band — it holds the eyes/brow/upper face, cleanly above the
# name bar. (This is NOT about the ult number, which sits to the left — see above.)
PORTRAIT_TOP_FRACTION = 0.45

# Injected primitive signatures.
CropFn = Callable[[Any, Rect], Any]
ScoreFn = Callable[[Any, HeroRef], float]

# Rolling window (frames) for temporal smoothing (SPEC §8.3). A good per-frame
# rate becomes a reliable output only after smoothing out per-frame blips.
DEFAULT_SMOOTHING_WINDOW = 5


@dataclass
class SlotMatch:
    slot_index: int
    matched_role: Optional[str]   # role of the matched hero, read from heroes.role
    state: str
    hero_guid: Optional[str]
    hero_name: Optional[str]
    confidence: float
    resolved: bool
    candidates: int


# --- pure constraint logic (unit-tested) -------------------------------------


def role_counts(team_roles: Sequence[str]) -> dict[str, int]:
    """Count the known roles in a team's line-up (e.g. {Tank:1, Damage:2,
    Support:2}). Unlabelled entries are ignored. Used to sanity-check that a
    matched comp has a plausible composition, not to filter slots."""
    counts: dict[str, int] = {}
    for role in team_roles:
        if role in KNOWN_ROLES:
            counts[role] = counts.get(role, 0) + 1
    return counts


def composition_consistent(
    matched_roles: Sequence[Optional[str]], team_roles: Sequence[str]
) -> bool:
    """True if the roles of the matched heroes match the team's known
    composition. Only meaningful when every slot resolved and the team is fully
    labelled; otherwise returns True (nothing to contradict)."""
    expected = role_counts(team_roles)
    if not expected or any(r is None for r in matched_roles):
        return True
    got: dict[str, int] = {}
    for role in matched_roles:
        if role is not None:
            got[role] = got.get(role, 0) + 1
    return got == expected


def face_subrect(
    rect: Rect,
    left_fraction: float = ULT_OVERLAY_LEFT_FRACTION,
    top_fraction: float = PORTRAIT_TOP_FRACTION,
) -> Rect:
    """The face-only sub-ROI of a portrait cell: the top-right band, past the
    ult-charge overlay (left ``left_fraction``) and above the player name/ability
    bar (keep the top ``top_fraction`` of the cell) — SPEC §8.3.

    Must be applied identically wherever a portrait is cropped — ref capture and
    matching — so a ref and a live crop describe the same pixels.
    """
    if not 0.0 <= left_fraction < 1.0:
        raise ValueError(f"left_fraction must be in [0, 1), got {left_fraction}")
    if not 0.0 < top_fraction <= 1.0:
        raise ValueError(f"top_fraction must be in (0, 1], got {top_fraction}")
    cut = round(rect.w * left_fraction)
    height = round(rect.h * top_fraction)
    return Rect(rect.x + cut, rect.y, rect.w - cut, height)


def reduce_candidates(
    refs: Sequence[HeroRef],
    *,
    state: Optional[str],
    expected_role: Optional[str],
    banned_guids: set[str],
    hero_roles: dict[str, str],
) -> list[HeroRef]:
    """The reduced candidate set for one slot: not banned, and (if given)
    matching ``state`` and/or ``expected_role`` (SPEC §8.1). ``state=None`` keeps
    both alive and dead refs — the default, since dead-vs-alive is decided by
    which ref scores highest, not by a pre-check (see :func:`match_frame`)."""
    out: list[HeroRef] = []
    for ref in refs:
        if state is not None and ref.state != state:
            continue
        if ref.hero_guid in banned_guids:
            continue
        if expected_role is not None and hero_roles.get(ref.hero_guid) != expected_role:
            continue
        out.append(ref)
    return out


def match_frame(
    frame: Any,
    slots: Sequence[Rect],
    refs: Sequence[HeroRef],
    hero_roles: dict[str, str],
    banned_guids: set[str],
    hero_names: dict[str, str],
    *,
    confidence_floor: float,
    crop_fn: CropFn,
    score_fn: ScoreFn,
) -> list[SlotMatch]:
    """Match every slot against the full non-banned ref set, considering BOTH
    alive and dead refs; the winning ref's state decides alive/dead (SPEC §8.1,
    §8.3). We do not pre-route by saturation — real data showed naturally-pale
    heroes (e.g. Reaper) sit below any sane "dead" threshold while alive, so the
    score decides. The HUD slot order is not role-fixed, so role is read from
    whichever hero wins. Pure orchestration over injected crop/score primitives."""
    results: list[SlotMatch] = []
    candidates = reduce_candidates(
        refs, state=None, expected_role=None,
        banned_guids=banned_guids, hero_roles=hero_roles,
    )
    for i, rect in enumerate(slots):
        crop = crop_fn(frame, rect)
        best_ref: Optional[HeroRef] = None
        best_score = 0.0
        for ref in candidates:
            score = score_fn(crop, ref)
            if score > best_score:
                best_score, best_ref = score, ref
        resolved = best_ref is not None and best_score >= confidence_floor
        guid = best_ref.hero_guid if best_ref else None
        state = best_ref.state if best_ref else STATE_ALIVE
        results.append(SlotMatch(
            slot_index=i,
            matched_role=hero_roles.get(guid) if (resolved and guid) else None,
            state=state,
            hero_guid=guid if resolved else None,
            hero_name=hero_names.get(guid) if (resolved and guid) else None,
            confidence=best_score,
            resolved=resolved,
            candidates=len({r.hero_guid for r in candidates}),
        ))
    return results


def format_matches(results: Sequence[SlotMatch]) -> str:
    """Human-readable stdout block for the gate (SPEC §13.3)."""
    lines = [
        f"{'slot':<4} {'role':<8} {'state':<5} {'conf':>5}  {'cands':>5}  hero",
        "-" * 52,
    ]
    for r in results:
        role = r.matched_role or "-"
        hero = r.hero_name or ("(below floor)" if not r.resolved else r.hero_guid or "?")
        flag = "" if r.resolved else "  <-- unresolved"
        lines.append(
            f"{r.slot_index:<4} {role:<8} {r.state:<5} {r.confidence:>5.2f}  "
            f"{r.candidates:>5}  {hero}{flag}"
        )
    resolved = sum(1 for r in results if r.resolved)
    lines.append("-" * 52)
    lines.append(f"resolved {resolved}/{len(results)} slots")
    return "\n".join(lines)


# --- temporal smoothing (SPEC §8.3; unit-tested) -----------------------------

# One window entry: (hero_guid or None, confidence).
SlotSample = tuple[Optional[str], float]


def modal_slot(window: Sequence[SlotSample]) -> SlotSample:
    """The modal hero over a slot's rolling window, with its mean confidence.

    Counts every entry including ``None`` (unresolved), so a slot only smooths to
    a hero when that hero is seen in the majority of recent frames — a transient
    mismatch or a couple of low-confidence blanks cannot flip it. Ties break
    toward the most recently seen value. Empty window -> unresolved.
    """
    if not window:
        return (None, 0.0)
    counts: dict[Optional[str], int] = {}
    conf_sum: dict[Optional[str], float] = {}
    last_index: dict[Optional[str], int] = {}
    for i, (guid, conf) in enumerate(window):
        counts[guid] = counts.get(guid, 0) + 1
        conf_sum[guid] = conf_sum.get(guid, 0.0) + conf
        last_index[guid] = i
    best = max(counts, key=lambda g: (counts[g], last_index[g]))
    mean_conf = conf_sum[best] / counts[best]
    return (best, mean_conf)


class TemporalSmoother:
    """Per-slot rolling window over successive frames of one side (SPEC §8.3)."""

    def __init__(self, num_slots: int, window: int = DEFAULT_SMOOTHING_WINDOW) -> None:
        self.window = window
        self._hist: list[Deque[SlotSample]] = [
            deque(maxlen=window) for _ in range(num_slots)
        ]

    def push(self, per_slot: Sequence[SlotSample]) -> None:
        for i, sample in enumerate(per_slot):
            self._hist[i].append(sample)

    def push_matches(self, matches: Sequence[SlotMatch]) -> None:
        self.push([(m.hero_guid, m.confidence) for m in matches])

    def current(self) -> list[SlotSample]:
        """The smoothed (hero_guid, mean_confidence) for each slot."""
        return [modal_slot(list(h)) for h in self._hist]


# --- cv2 primitives (runtime defaults; not unit-tested) ----------------------


def _import_cv2_np() -> tuple[Any, Any]:  # pragma: no cover - runtime-only path
    try:
        import cv2
        import numpy as np
    except ImportError as exc:
        raise CaptureError(
            "opencv-python + numpy are required for match — `pip install -e .[capture]`"
        ) from exc
    return cv2, np


def crop_roi(frame: Any, rect: Rect) -> Any:  # pragma: no cover
    return frame[rect.y : rect.y + rect.h, rect.x : rect.x + rect.w]


# A ref this many times larger than the live crop is a "sheet" ref (a full
# gallery portrait, not a tight observer crop). The observer face sits at a
# different framing/scale inside it, so we search over scales instead of a
# single resize. Range covers the observer-face-within-sheet scale (~0.7).
SHEET_REF_SIZE_FACTOR = 1.4
SHEET_SEARCH_SCALES = (0.55, 0.60, 0.65, 0.70, 0.75, 0.80, 0.85)


def make_template_scorer(cv2: Any) -> ScoreFn:  # pragma: no cover
    """Best TM_CCOEFF_NORMED score of a ref against the crop (SPEC §8.3).

    Observer-derived refs are ~crop-sized and matched with a single resize. Refs
    from a hero-gallery sheet are larger and framed differently, so the crop is
    searched within them across a scale range (the argmax over scales), which is
    what makes a one-image ref library discriminate.

    The image cache keys on (path, mtime), so overwriting a ref file — e.g.
    re-learning a hero to correct a mislabel — is picked up on the next score
    instead of serving a stale image for the life of the scorer."""
    cache: dict[str, tuple[int, Any]] = {}

    def score(crop: Any, ref: HeroRef) -> float:
        try:
            st = os.stat(ref.image_path)
            mtime = st.st_mtime_ns ^ st.st_size  # size guards same-ns overwrites
        except OSError:
            mtime = 0
        entry = cache.get(ref.image_path)
        if entry is None or entry[0] != mtime:
            img = cv2.imread(ref.image_path)
            if img is None:
                log.warning("could not read ref image %s", ref.image_path)
                return 0.0
            cache[ref.image_path] = (mtime, img)
        else:
            img = entry[1]
        ch, cw = crop.shape[0], crop.shape[1]
        rh, rw = img.shape[0], img.shape[1]
        if rh > ch * SHEET_REF_SIZE_FACTOR and rw > cw * SHEET_REF_SIZE_FACTOR:
            best = 0.0
            for s in SHEET_SEARCH_SCALES:
                tw, th = int(rw * s), int(rh * s)
                if tw < 8 or th < 8 or tw >= rw or th >= rh:
                    continue
                res = cv2.matchTemplate(img, cv2.resize(crop, (tw, th)), cv2.TM_CCOEFF_NORMED)
                best = max(best, float(res.max()))
            return best
        template = cv2.resize(img, (cw, ch))
        result = cv2.matchTemplate(crop, template, cv2.TM_CCOEFF_NORMED)
        return float(result.max())

    return score


# --- runtime driver (loads assets, prints; not unit-tested) ------------------


def run_match(  # pragma: no cover - runtime-only path
    db: Database,
    faceit_db_path: str,
    *,
    frame_path: str,
    match_id: str,
    game_no: int,
    team: str,
    side: str,
    hud_variant: str,
    confidence_floor: float = DEFAULT_CONFIDENCE_FLOOR,
) -> list[SlotMatch]:
    """Load one frame + its faceit context + the ref library, match, print."""
    cv2, _np = _import_cv2_np()

    frame = cv2.imread(frame_path)
    if frame is None:
        raise CaptureError(f"could not read frame: {frame_path}")
    height, width = int(frame.shape[0]), int(frame.shape[1])

    profile = db.get_active_profile(width, height, hud_variant)
    if profile is None:
        raise CaptureError(
            f"no calibrated profile for {width}x{height} '{hud_variant}' — "
            "run `owscout calibrate` first"
        )
    assert profile.id is not None
    refs = db.get_refs(profile.id)
    if not refs:
        raise CaptureError(
            f"no refs for profile #{profile.id} — run `owscout refs capture` first"
        )

    with connect_ro(faceit_db_path) as fdb:
        team_id = resolve_team_id(fdb, team)
        if team_id is None:
            raise CaptureError(f"team not found in faceit DB: {team!r}")
        f1, f2 = team_ids_for_map(fdb, match_id)
        if team_id not in (f1, f2):
            raise CaptureError(
                f"team {team!r} did not play match {match_id} "
                f"(factions: {f1}, {f2})"
            )
        banned = set(load_bans(fdb, match_id, game_no))
        team_roles = load_team_roles(fdb, match_id, game_no, team_id)
        hero_roles = load_hero_roles(fdb)
        hero_names = {h.guid: h.name for h in load_heroes(fdb)}

    # Crop the face region (past the ult-charge overlay) uniformly with refs.
    slots = [face_subrect(r) for r in _side_slots(profile, side)]

    results = match_frame(
        frame, slots, refs, hero_roles, banned, hero_names,
        confidence_floor=confidence_floor,
        crop_fn=crop_roi,
        score_fn=make_template_scorer(cv2),
    )

    print(
        f"match {match_id} game {game_no} — {team} on side '{side}' "
        f"@ {width}x{height} '{hud_variant}', {len(banned)} ban(s)"
    )
    print(format_matches(results))
    # Composition sanity check against the team's known 1/2/2 (SPEC round_players).
    expected_comp = role_counts(team_roles)
    if expected_comp:
        matched = [r.matched_role for r in results]
        ok = composition_consistent(matched, team_roles)
        print(
            f"team composition {_fmt_counts(expected_comp)}; "
            f"matched {'consistent' if ok else 'INCONSISTENT — check unresolved slots'}"
        )
    return results


def _side_slots(profile: RoiProfile, side: str) -> list[Rect]:
    if side not in profile.slots:
        raise CaptureError(f"unknown side {side!r}; profile has {sorted(profile.slots)}")
    return profile.slots[side]


def _fmt_counts(counts: dict[str, int]) -> str:
    return "/".join(f"{counts.get(r, 0)}{r[0]}" for r in ("Tank", "Damage", "Support"))

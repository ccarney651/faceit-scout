"""``owscout refs`` — the reference-portrait library (SPEC §6, build step 2).

Reference icons must come from the client, at the operator's exact resolution
(SPEC §6) — wiki/CDN art does not match in-game rendering. ``refs capture``
walks the authoritative hero roster from ``faceit.heroes`` and, for each hero in
each visual state (alive / dead), crops the profile's reference ROI and stores
the image plus a perceptual hash. ``refs verify`` reports gaps and near-collisions.

The perceptual-hash and set logic is pure and unit-tested; the frame grab, crop
and operator prompts are isolated below and exercised only when the game is running.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Iterable, NamedTuple, Optional

from .errors import CaptureError
from .db import Database
from .faceit import connect_ro, load_heroes
from .models import REF_STATES, STATE_ALIVE, FaceitHero, HeroRef, Rect, RoiProfile

log = logging.getLogger("owscout.refs")

# phash is a 64-bit hash rendered as 16 hex chars.
PHASH_BITS = 64
# Default "suspiciously similar" threshold for refs verify. Two DIFFERENT
# heroes whose portraits hash within this Hamming distance risk silent
# misclassification (SPEC §6).
DEFAULT_CLOSE_THRESHOLD = 6


# --- perceptual hashing (pure) -----------------------------------------------


def hamming_hex(a: str, b: str) -> int:
    """Hamming distance between two hex-encoded hashes of equal width."""
    if len(a) != len(b):
        raise ValueError(f"hash width mismatch: {len(a)} vs {len(b)}")
    return bin(int(a, 16) ^ int(b, 16)).count("1")


def phash_image(image: Any) -> str:  # pragma: no cover - needs cv2/numpy
    """64-bit DCT perceptual hash of a BGR crop, as 16 hex chars.

    Grayscale -> 32x32 -> DCT -> low-frequency 8x8 (excluding the DC term's
    dominance) -> bit per coefficient above the median.
    """
    import cv2
    import numpy as np

    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if image.ndim == 3 else image
    small = cv2.resize(gray, (32, 32), interpolation=cv2.INTER_AREA)
    dct = cv2.dct(small.astype(np.float32))
    low = dct[:8, :8]
    median = float(np.median(low))
    bits = (low > median).flatten()
    value = 0
    for bit in bits:
        value = (value << 1) | int(bit)
    return f"{value:0{PHASH_BITS // 4}x}"


# --- verification (pure) -----------------------------------------------------


def find_missing(
    heroes: Iterable[FaceitHero],
    refs: Iterable[HeroRef],
    required_states: tuple[str, ...] = (STATE_ALIVE,),
) -> dict[str, list[str]]:
    """For each hero missing a required state, the states it lacks.

    ``alive`` is required; ``dead`` is an optional robustness bonus (the matcher
    identifies a dead hero from its alive ref anyway), so it is not required by
    default. Keyed by hero_guid; only heroes with a missing state appear.
    """
    have: dict[str, set[str]] = {}
    for r in refs:
        have.setdefault(r.hero_guid, set()).add(r.state)
    missing: dict[str, list[str]] = {}
    for hero in heroes:
        gaps = [s for s in required_states if s not in have.get(hero.guid, set())]
        if gaps:
            missing[hero.guid] = gaps
    return missing


class ClosePair(NamedTuple):
    ref_a: HeroRef
    ref_b: HeroRef
    distance: int


def find_close_pairs(
    refs: list[HeroRef], threshold: int = DEFAULT_CLOSE_THRESHOLD
) -> list[ClosePair]:
    """Pairs of refs for DIFFERENT heroes whose phashes are within ``threshold``.

    Same-hero alive/dead similarity is expected and ignored; the hazard is two
    distinct heroes colliding. Sorted closest-first.
    """
    pairs: list[ClosePair] = []
    for i in range(len(refs)):
        for j in range(i + 1, len(refs)):
            a, b = refs[i], refs[j]
            if a.hero_guid == b.hero_guid:
                continue
            dist = hamming_hex(a.phash, b.phash)
            if dist <= threshold:
                pairs.append(ClosePair(a, b, dist))
    pairs.sort(key=lambda p: p.distance)
    return pairs


# --- refs directory ----------------------------------------------------------


def default_refs_dir(db_path: str) -> str:
    """Where ref crops are stored: a ``refs/`` dir next to the owscout DB."""
    return str(Path(db_path).resolve().parent / "refs")


def _ref_image_path(refs_dir: str | Path, profile_id: int, hero: FaceitHero, state: str) -> Path:
    safe = "".join(ch if ch.isalnum() else "_" for ch in hero.name).strip("_") or hero.guid
    out = Path(refs_dir) / str(profile_id)
    out.mkdir(parents=True, exist_ok=True)
    return out / f"{safe}_{state}.png"


# --- interactive drivers (cv2 + capture; not unit-tested) --------------------


def run_refs_capture(  # pragma: no cover - runtime-only path
    db: Database,
    faceit_db_path: str,
    *,
    hud_variant: str,
    side: str,
    slot: int,
    states: tuple[str, ...] = REF_STATES,
    only: Optional[str] = None,
    refs_dir: str | Path,
    dry_run: bool = False,
) -> int:
    """Walk the hero roster and capture reference crops. Returns count written."""
    from . import capture  # local: keep heavy deps out of import time

    cv2 = _import_cv2()

    frame, width, height = capture.grab_frame()
    profile = db.get_active_profile(width, height, hud_variant)
    if profile is None:
        raise CaptureError(
            f"no calibrated profile for {width}x{height} '{hud_variant}' — "
            "run `owscout calibrate` first"
        )
    # Crop the same face region matching uses, so refs and live crops align.
    from .match import face_subrect
    roi = face_subrect(_reference_roi(profile, side, slot))

    with connect_ro(faceit_db_path) as fdb:
        heroes = load_heroes(fdb)
    if only:
        needle = only.lower()
        heroes = [h for h in heroes if needle in h.name.lower()]
        if not heroes:
            raise CaptureError(f"no hero matches --only {only!r}")

    written = 0
    print(
        f"Capturing {len(heroes)} hero(es) x {len(states)} state(s) from "
        f"side '{side}' slot {slot}. Get each hero on screen, then ENTER."
    )
    for hero in heroes:
        for state in states:
            action = input(
                f"  {hero.name} [{state}] — ENTER=capture, s=skip, q=quit: "
            ).strip().lower()
            if action == "q":
                print(f"stopped. {written} ref(s) written.")
                return written
            if action == "s":
                continue
            frame, fw, fh = capture.grab_frame()
            if (fw, fh) != (profile.resolution_w, profile.resolution_h):
                raise CaptureError(
                    f"resolution changed to {fw}x{fh}; profile is "
                    f"{profile.resolution_w}x{profile.resolution_h} — refs must "
                    "match the calibrated resolution"
                )
            crop = _crop(frame, roi)
            phash = phash_image(crop)
            if dry_run:
                log.info("dry-run: would store %s [%s] phash=%s", hero.name, state, phash)
                continue
            assert profile.id is not None
            path = _ref_image_path(refs_dir, profile.id, hero, state)
            cv2.imwrite(str(path), crop)
            db.save_ref(
                hero_guid=hero.guid,
                profile_id=profile.id,
                state=state,
                image_path=str(path),
                phash=phash,
                source="capture",
            )
            written += 1
            log.info("stored %s [%s] -> %s", hero.name, state, path)
    print(f"done. {written} ref(s) written.")
    return written


def _detect_sheet_grid(cv2: Any, img: Any) -> tuple[list[tuple[int, int]], list[tuple[int, int]]]:  # pragma: no cover
    """Find the portrait column and row spans of a gallery sheet by projecting
    brightness (portraits are bright on a dark background)."""
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY).astype("float32")

    def spans(proj: Any, min_len: int) -> list[tuple[int, int]]:
        thr = float(proj.mean()) * 0.5
        out: list[tuple[int, int]] = []
        i, n = 0, len(proj)
        while i < n:
            if proj[i] > thr:
                j = i
                while j < n and proj[j] > thr:
                    j += 1
                if j - i >= min_len:
                    out.append((i, j))
                i = j
            else:
                i += 1
        return out

    cols = spans(gray.mean(axis=0), img.shape[1] // 20)
    rows = spans(gray.mean(axis=1), img.shape[0] // 20)
    return cols, rows


def run_refs_from_sheet(  # pragma: no cover - runtime-only path
    db: Database,
    faceit_db_path: str,
    image_path: str,
    *,
    hud_variant: str,
    refs_dir: str | Path,
    dry_run: bool = False,
) -> int:
    """Build the whole ref library from ONE hero-gallery screenshot. Detects the
    portrait grid, maps cells to the case-insensitively-sorted ``faceit.heroes``
    (which matches the game's alphabetical gallery order), and stores each
    portrait as a ref. Writes a labeled image to VERIFY the mapping."""
    cv2 = _import_cv2()

    img = cv2.imread(image_path)
    if img is None:
        raise CaptureError(f"could not read image: {image_path}")
    profile = db.latest_active_profile(hud_variant)
    if profile is None:
        raise CaptureError(
            f"no calibrated profile for '{hud_variant}' — run `owscout calibrate` first")
    assert profile.id is not None

    cols, rows = _detect_sheet_grid(cv2, img)
    cells = [(r, c) for r in range(len(rows)) for c in range(len(cols))]
    with connect_ro(faceit_db_path) as fdb:
        heroes = sorted(load_heroes(fdb), key=lambda h: h.name.lower())
    n = min(len(heroes), len(cells))
    if len(cells) < len(heroes):
        log.warning("grid found %d cells but roster has %d heroes — mapping first %d",
                    len(cells), len(heroes), n)
    print(f"grid: {len(cols)} cols x {len(rows)} rows; mapping {n} heroes (alphabetical).")

    labeled = img.copy()
    out_dir = Path(refs_dir) / str(profile.id)
    out_dir.mkdir(parents=True, exist_ok=True)
    written = 0
    for i in range(n):
        hero = heroes[i]
        r, c = cells[i]
        (y0, y1), (x0, x1) = rows[r], cols[c]
        cell = img[y0:y1, x0:x1]
        phash = phash_image(cell)
        cv2.rectangle(labeled, (x0, y0), (x0 + min(230, x1 - x0), y0 + 34), (0, 0, 0), -1)
        cv2.putText(labeled, hero.name, (x0 + 3, y0 + 26),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2)
        if not dry_run:
            path = out_dir / f"{_safe(hero)}_sheet.png"
            cv2.imwrite(str(path), cell)
            db.save_ref(hero_guid=hero.guid, profile_id=profile.id, state="alive",
                        image_path=str(path), phash=phash, source="capture")
        written += 1

    verify_path = out_dir / "_sheet_labeled.png"
    cv2.imwrite(str(verify_path), labeled)
    print(f"stored {written} refs from sheet.")
    print(f"VERIFY the mapping is correct: {verify_path}")
    return written


def _safe(hero: FaceitHero) -> str:
    return "".join(ch if ch.isalnum() else "_" for ch in hero.name).strip("_") or hero.guid


def resolve_hero_name(heroes: list[FaceitHero], name: str) -> Optional[FaceitHero]:
    """Fuzzy-resolve an operator-typed hero name to a roster hero: exact, then
    unique substring, then closest by edit distance."""
    import difflib
    needle = name.strip().lower()
    if not needle:
        return None
    for h in heroes:
        if h.name.lower() == needle:
            return h
    subs = [h for h in heroes if needle in h.name.lower()]
    if len(subs) == 1:
        return subs[0]
    if len(subs) > 1:
        return None  # ambiguous — let the caller re-prompt
    match = difflib.get_close_matches(needle, [h.name.lower() for h in heroes], n=1, cutoff=0.6)
    if match:
        return next(h for h in heroes if h.name.lower() == match[0])
    return None


def run_refs_from_frame(  # pragma: no cover - runtime-only path
    db: Database,
    faceit_db_path: str,
    *,
    hud_variant: str,
    refs_dir: str | Path,
    state: str = "alive",
    dry_run: bool = False,
) -> int:
    """Batch capture: grab ONE observer frame and, for each of the 10 slots, show
    the face crop and let the operator name the hero (blank = skip an unpicked or
    already-known slot). Stores a ref per named slot. The efficient way to build
    the library — a few frames across varied comps cover the roster.
    """
    from . import capture

    cv2 = _import_cv2()
    from .match import face_subrect
    from .models import SIDE_LEFT, SIDE_RIGHT

    frame, width, height = capture.grab_frame()
    profile = db.get_active_profile(width, height, hud_variant)
    if profile is None:
        raise CaptureError(
            f"no calibrated profile for {width}x{height} '{hud_variant}' — "
            "run `owscout calibrate` first"
        )
    assert profile.id is not None
    with connect_ro(faceit_db_path) as fdb:
        heroes = load_heroes(fdb)

    print("Naming heroes in this frame. For each portrait: type the hero name, "
          "or blank to skip (unpicked/already-have), or 'q' to finish.")
    written = 0
    win = "owscout refs — name this hero"
    for side in (SIDE_LEFT, SIDE_RIGHT):
        for slot in range(profile.team_size):
            roi = face_subrect(profile.slots[side][slot])
            crop = _crop(frame, roi)
            preview = cv2.resize(crop, (roi.w * 3, roi.h * 3), interpolation=cv2.INTER_NEAREST)
            cv2.imshow(win, preview)
            cv2.waitKey(1)
            while True:
                raw = input(f"  side {side} slot {slot}: hero name (blank=skip, q=quit): ").strip()
                if raw.lower() == "q":
                    cv2.destroyWindow(win)
                    print(f"done. {written} ref(s) written.")
                    return written
                if not raw:
                    hero = None
                    break
                hero = resolve_hero_name(heroes, raw)
                if hero is None:
                    print(f"    '{raw}' didn't resolve (ambiguous or unknown) — try again.")
                    continue
                break
            if hero is None:
                continue
            phash = phash_image(crop)
            if dry_run:
                log.info("dry-run: would store %s [%s] phash=%s", hero.name, state, phash)
                written += 1
                continue
            path = _ref_image_path(refs_dir, profile.id, hero, state)
            cv2.imwrite(str(path), crop)
            db.save_ref(hero_guid=hero.guid, profile_id=profile.id, state=state,
                        image_path=str(path), phash=phash, source="capture")
            written += 1
            print(f"    stored {hero.name}")
    cv2.destroyWindow(win)
    print(f"done. {written} ref(s) written.")
    return written


def run_refs_verify(
    db: Database,
    faceit_db_path: str,
    *,
    hud_variant: str,
    close_threshold: int = DEFAULT_CLOSE_THRESHOLD,
) -> int:
    """Report heroes missing refs and near-duplicate portraits. Returns an exit
    code (0 clean, 1 if anything is missing)."""
    profile = db.latest_active_profile(hud_variant)
    if profile is None:
        raise CaptureError(
            f"no calibrated profile for '{hud_variant}' — run `owscout calibrate` first"
        )
    assert profile.id is not None

    with connect_ro(faceit_db_path) as fdb:
        heroes = load_heroes(fdb)
    refs = db.get_refs(profile.id)

    missing = find_missing(heroes, refs)
    names = {h.guid: h.name for h in heroes}

    print(
        f"profile #{profile.id}  {profile.resolution_w}x{profile.resolution_h} "
        f"'{profile.hud_variant}' — {len(refs)} ref(s) for {len(heroes)} heroes"
    )
    if missing:
        print(f"\nmissing refs ({len(missing)} hero(es)):")
        for guid, states in missing.items():
            print(f"  {names.get(guid, guid):<20} missing: {', '.join(states)}")
    else:
        print("\nall heroes have a ref.")

    close = find_close_pairs(refs, close_threshold)
    if close:
        print(f"\nsuspiciously similar refs (Hamming <= {close_threshold}):")
        for pair in close:
            print(
                f"  d={pair.distance}  "
                f"{names.get(pair.ref_a.hero_guid, pair.ref_a.hero_guid)}[{pair.ref_a.state}]"
                f"  vs  "
                f"{names.get(pair.ref_b.hero_guid, pair.ref_b.hero_guid)}[{pair.ref_b.state}]"
            )
    else:
        print(f"\nno ref pairs within Hamming {close_threshold}.")

    return 1 if missing else 0


def _reference_roi(profile: RoiProfile, side: str, slot: int) -> Rect:
    if side not in profile.slots:
        raise CaptureError(f"unknown side {side!r}; profile has {sorted(profile.slots)}")
    slots = profile.slots[side]
    if not 0 <= slot < len(slots):
        raise CaptureError(f"slot {slot} out of range 0..{len(slots) - 1} for side {side!r}")
    return slots[slot]


def _import_cv2() -> Any:  # pragma: no cover - runtime-only path
    try:
        import cv2
    except ImportError as exc:
        raise CaptureError(
            "opencv-python is required for refs capture — `pip install -e .[capture]`"
        ) from exc
    return cv2


def _crop(frame: Any, rect: Rect) -> Any:  # pragma: no cover
    return frame[rect.y : rect.y + rect.h, rect.x : rect.x + rect.w]

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
from .models import REF_STATES, FaceitHero, HeroRef, Rect, RoiProfile

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
    heroes: Iterable[FaceitHero], refs: Iterable[HeroRef]
) -> dict[str, list[str]]:
    """For each hero missing one or more states, the states it lacks.

    Keyed by hero_guid; only heroes with at least one missing state appear.
    """
    have: dict[str, set[str]] = {}
    for r in refs:
        have.setdefault(r.hero_guid, set()).add(r.state)
    missing: dict[str, list[str]] = {}
    for hero in heroes:
        gaps = [s for s in REF_STATES if s not in have.get(hero.guid, set())]
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
        print("\nall heroes have alive + dead refs.")

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

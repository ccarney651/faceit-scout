"""``owscout calibrate`` — ROI capture and persistence (SPEC §5, build step 1).

Pixel coordinates live in the DB, never in source. Nothing works without this
step (SPEC §13). The command:

1. Grabs the current game window at native resolution and saves the full frame.
2. Operator drags a box over each team's hero portrait strip (left / right).
   Each strip is subdivided into ``team_size`` equal ROIs and shown for
   confirmation.
3. Operator drags 2-3 anchor boxes over fixed HUD furniture (objective bar,
   timer, scoreboard chrome). Used at runtime to tell a live match view from a
   menu / killcam / loading screen.
4. The profile is persisted to ``roi_profiles``, keyed on
   (resolution_w, resolution_h, hud_variant).

The pure geometry / assembly (``subdivide_strip``, ``build_profile``) is kept
separate from the interactive cv2/capture I/O so it is testable without the game
running.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from .errors import CaptureError
from .db import Database
from .models import (
    SIDE_LEFT,
    SIDE_RIGHT,
    WORKING_RESOLUTION,
    Anchor,
    Rect,
    RoiProfile,
)

log = logging.getLogger("owscout.calibrate")


# --- pure geometry / assembly (unit-tested) ----------------------------------


def subdivide_strip(strip: Rect, count: int) -> list[Rect]:
    """Split a hero-portrait strip into ``count`` equal, gap-free ROIs.

    Portraits sit side-by-side along the strip's longer axis, so we split along
    that axis. Any remainder pixels are handed to the leading slots so the ROIs
    tile the strip exactly — no gaps, no overlap.
    """
    if count <= 0:
        raise ValueError(f"team_size must be positive, got {count}")
    if strip.is_empty:
        raise ValueError(f"strip has non-positive size: {strip}")

    horizontal = strip.w >= strip.h
    total = strip.w if horizontal else strip.h
    if total < count:
        raise ValueError(
            f"strip is too small ({total}px) to hold {count} slots"
        )

    base, remainder = divmod(total, count)
    rects: list[Rect] = []
    offset = 0
    for i in range(count):
        size = base + (1 if i < remainder else 0)
        if horizontal:
            rects.append(Rect(strip.x + offset, strip.y, size, strip.h))
        else:
            rects.append(Rect(strip.x, strip.y + offset, strip.w, size))
        offset += size
    return rects


def build_profile(
    *,
    resolution_w: int,
    resolution_h: int,
    hud_variant: str,
    team_size: int,
    left_strip: Rect,
    right_strip: Rect,
    anchors: list[Anchor],
) -> RoiProfile:
    """Assemble a :class:`RoiProfile` from the operator's raw selections."""
    slots = {
        SIDE_LEFT: subdivide_strip(left_strip, team_size),
        SIDE_RIGHT: subdivide_strip(right_strip, team_size),
    }
    return RoiProfile(
        resolution_w=resolution_w,
        resolution_h=resolution_h,
        hud_variant=hud_variant,
        team_size=team_size,
        slots=slots,
        anchors=anchors,
    )


# --- interactive driver (cv2 + screen capture; not unit-tested) --------------


def run_calibration(
    db: Database,
    *,
    hud_variant: str,
    team_size: int,
    frame_dir: str | Path,
    dry_run: bool = False,
) -> RoiProfile:
    """Grab a frame, run the interactive selection, and persist the profile.

    Returns the built profile (with ``id`` set when persisted).
    """
    from . import capture  # local: keep heavy deps out of import time

    cv2 = _import_cv2()

    frame, width, height = capture.grab_frame()
    log.info("grabbed frame at %dx%d", width, height)
    if (width, height) != WORKING_RESOLUTION:
        # SPEC §5: assume 2560x1440 but derive it; a profile is valid only at
        # the resolution it was calibrated on. Warn, do not refuse — refusal is
        # a capture-time concern.
        log.warning(
            "resolution %dx%d is not the assumed working resolution %dx%d; "
            "this profile will be valid only at %dx%d",
            width, height, WORKING_RESOLUTION[0], WORKING_RESOLUTION[1],
            width, height,
        )

    frame_path = capture.save_frame(frame, frame_dir, f"{width}x{height}_{hud_variant}")
    log.info("saved full frame to %s", frame_path)

    left = _select_box(cv2, frame, "LEFT team hero strip (side A) — drag, then ENTER")
    right = _select_box(cv2, frame, "RIGHT team hero strip (side B) — drag, then ENTER")

    profile = build_profile(
        resolution_w=width,
        resolution_h=height,
        hud_variant=hud_variant,
        team_size=team_size,
        left_strip=left,
        right_strip=right,
        anchors=[],
    )
    _preview_slots(cv2, frame, profile.slots)

    profile.anchors = _select_anchors(cv2, frame)

    if dry_run:
        log.info(
            "dry-run: not persisting profile (%dx%d '%s', %d slots/side, %d anchors)",
            width, height, hud_variant, team_size, len(profile.anchors),
        )
        return profile

    profile_id = db.save_profile(profile)
    log.info("saved roi_profile id=%d", profile_id)
    print(
        f"saved roi_profile id={profile_id} for {width}x{height} '{hud_variant}' "
        f"({team_size} slots/side, {len(profile.anchors)} anchors)"
    )
    return profile


def _import_cv2() -> Any:
    try:
        import cv2
    except ImportError as exc:  # pragma: no cover - runtime-only path
        raise CaptureError(
            "opencv-python is required for calibrate — `pip install -e .[capture]`"
        ) from exc
    return cv2


def _select_box(cv2: Any, frame: Any, prompt: str) -> Rect:  # pragma: no cover
    """Drag a single ROI via cv2.selectROI. Raises if the selection is empty."""
    window = "owscout calibrate"
    x, y, w, h = cv2.selectROI(window, frame, showCrosshair=True, fromCenter=False)
    cv2.destroyWindow(window)
    rect = Rect(int(x), int(y), int(w), int(h))
    if rect.is_empty:
        raise RuntimeError(f"empty selection for: {prompt}")
    return rect


def _preview_slots(cv2: Any, frame: Any, slots: dict[str, list[Rect]]) -> None:  # pragma: no cover
    """Draw the subdivided ROIs and wait for the operator to confirm."""
    preview = frame.copy()
    for rects in slots.values():
        for r in rects:
            cv2.rectangle(preview, (r.x, r.y), (r.x + r.w, r.y + r.h), (0, 255, 0), 2)
    window = "owscout calibrate — subdivided slots (any key to confirm)"
    cv2.imshow(window, preview)
    cv2.waitKey(0)
    cv2.destroyWindow(window)


def _select_anchors(cv2: Any, frame: Any) -> list[Anchor]:  # pragma: no cover
    """Collect 2-3 named anchor boxes over fixed HUD furniture."""
    anchors: list[Anchor] = []
    print(
        "\nAnchors: drag 2-3 boxes over fixed HUD furniture (objective bar, "
        "timer, scoreboard chrome). Blank name when done."
    )
    while True:
        default = _suggest_anchor_name(len(anchors))
        name = input(f"  anchor name [{default}] (blank to finish): ").strip()
        if not name:
            if len(anchors) >= 2:
                break
            print(f"  need at least 2 anchors ({len(anchors)} so far)")
            continue
        rect = _select_box(cv2, frame, f"anchor '{name}'")
        anchors.append(Anchor(name=name, rect=rect))
        if len(anchors) >= 3:
            print("  3 anchors captured (the recommended maximum).")
            break
    return anchors


def _suggest_anchor_name(index: int) -> str:
    suggestions = ("objective_bar", "timer", "scoreboard")
    return suggestions[index] if index < len(suggestions) else f"anchor_{index}"


def default_frame_dir(db_path: str) -> str:
    """Where to save the full calibration frame: a ``calibration/`` dir next to
    the owscout DB."""
    return str(Path(db_path).resolve().parent / "calibration")

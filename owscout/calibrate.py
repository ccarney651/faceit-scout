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
from typing import Any, Optional

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


# --- auto-calibration --------------------------------------------------------
# Normalized (fractions of screen width/height) bounding strips for the two
# 5-portrait rosters in the observer HUD, averaged over hand calibrations at
# 2560x1440. The HUD sits at fixed fractions of the screen, so scaling these to
# any 16:9 resolution reproduces a hand calibration to within a pixel or two -
# inside the matcher's slide tolerance (round-tripped: 1080p and 1440p both land
# on the measured boxes). Non-16:9 (ultrawide) or a non-default in-game UI scale
# will be off; those still calibrate by hand, which the confirm preview prompts.
AUTO_STRIPS: dict[str, tuple[float, float, float, float]] = {
    SIDE_LEFT:  (0.0506, 0.0832, 0.2579, 0.0675),   # x, y, w, h as fractions
    SIDE_RIGHT: (0.6912, 0.0818, 0.2573, 0.0705),
}


def auto_profile(
    width: int, height: int, *, hud_variant: str, team_size: int = 5,
) -> RoiProfile:
    """A profile drawn from the known HUD proportions - no dragging. Reuses the
    same strip->slots split as manual calibration, so the geometry is identical
    to a hand calibration that boxed the rosters perfectly. Accurate on standard
    16:9 at default UI scale; callers should still preview it so an off case can
    fall back to manual."""
    def strip(side: str) -> Rect:
        fx, fy, fw, fh = AUTO_STRIPS[side]
        return Rect(round(fx * width), round(fy * height),
                    round(fw * width), round(fh * height))
    return build_profile(
        resolution_w=width, resolution_h=height, hud_variant=hud_variant,
        team_size=team_size, left_strip=strip(SIDE_LEFT),
        right_strip=strip(SIDE_RIGHT), anchors=[],
    )


# --- interactive driver (cv2 + screen capture; not unit-tested) --------------


def run_calibration(
    db: Database,
    *,
    hud_variant: str,
    team_size: int,
    frame_dir: str | Path,
    capture_anchors: bool = False,
    dry_run: bool = False,
) -> RoiProfile:
    """Grab a frame, run the interactive selection, and persist the profile.

    Anchors (fixed-HUD landmarks) are off by default — they were meant for a
    live-view validity gate that is not wired, so capturing them is just friction.
    Pass ``capture_anchors=True`` to collect them if that gate is ever added.

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

    print("\nCALIBRATION — a window will open. Drag a box, then press ENTER "
          "(or SPACE) to confirm each one.\n")
    left = _select_box(cv2, frame,
                       "STEP 1/3: box the LEFT team's 5 hero portraits, then ENTER")
    right = _select_box(cv2, frame,
                        "STEP 2/3: box the RIGHT team's 5 hero portraits, then ENTER")

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

    if capture_anchors:
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


def run_auto_calibration(
    db: Database,
    *,
    hud_variant: str,
    team_size: int,
    frame_dir: str | Path,
    confirm: bool = True,
    dry_run: bool = False,
) -> Optional[RoiProfile]:
    """Auto-detect the ROI boxes from HUD proportions and save - no dragging.

    With ``confirm`` a preview opens: ENTER saves the auto boxes; ESC drops to
    HAND calibration ON THE SAME FRAME (box each team's 5 portraits) - one frame,
    one continuous window flow, so an off auto guess (ultrawide / scaled HUD /
    windowed OW) recovers without a second grab. Always returns the saved profile.
    """
    from . import capture

    cv2 = _import_cv2()
    frame, width, height = capture.grab_frame()
    log.info("auto-calibrate grabbed frame at %dx%d", width, height)
    capture.save_frame(frame, frame_dir, f"{width}x{height}_{hud_variant}")
    profile = auto_profile(width, height, hud_variant=hud_variant, team_size=team_size)

    if confirm and not _confirm_slots(cv2, frame, profile.slots):
        # Draw by hand on the SAME frame - no second grab, no separate flow.
        left = _select_box(
            cv2, frame, "DRAW 1/2: box the LEFT team's 5 hero portraits, then ENTER")
        right = _select_box(
            cv2, frame, "DRAW 2/2: box the RIGHT team's 5 hero portraits, then ENTER")
        profile = build_profile(
            resolution_w=width, resolution_h=height, hud_variant=hud_variant,
            team_size=team_size, left_strip=left, right_strip=right, anchors=[])
        _preview_slots(cv2, frame, profile.slots)

    if dry_run:
        return profile
    profile_id = db.save_profile(profile)
    log.info("saved roi_profile id=%d for %dx%d '%s'",
             profile_id, width, height, hud_variant)
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
    """Drag a single ROI via cv2.selectROI. The prompt is the window title, so the
    step instruction is visible while dragging. Raises if the selection is empty."""
    x, y, w, h = cv2.selectROI(prompt, frame, showCrosshair=True, fromCenter=False)
    cv2.destroyWindow(prompt)
    rect = Rect(int(x), int(y), int(w), int(h))
    if rect.is_empty:
        raise RuntimeError(
            f"nothing was boxed for: {prompt}. Drag a box before pressing ENTER.")
    return rect


def _preview_slots(cv2: Any, frame: Any, slots: dict[str, list[Rect]]) -> None:  # pragma: no cover
    """Draw the subdivided ROIs and wait for the operator to confirm."""
    preview = frame.copy()
    for rects in slots.values():
        for r in rects:
            cv2.rectangle(preview, (r.x, r.y), (r.x + r.w, r.y + r.h), (0, 255, 0), 2)
    window = "STEP 3/3: do the green boxes sit on the portraits? press any key to save"
    cv2.imshow(window, preview)
    cv2.waitKey(0)
    cv2.destroyWindow(window)


def _confirm_slots(cv2: Any, frame: Any, slots: dict[str, list[Rect]]) -> bool:  # pragma: no cover
    """Show the auto-detected boxes; ENTER (any key but ESC) accepts, ESC rejects
    so the caller falls back to manual calibration."""
    preview = frame.copy()
    for rects in slots.values():
        for r in rects:
            cv2.rectangle(preview, (r.x, r.y), (r.x + r.w, r.y + r.h), (0, 255, 0), 2)
    window = ("AUTO-CALIBRATE: green boxes on the portraits?  ENTER = save   "
              "ESC = draw by hand   (if way off: OW must be BORDERLESS/FULLSCREEN)")
    cv2.imshow(window, preview)
    key = cv2.waitKey(0)
    cv2.destroyWindow(window)
    cv2.waitKey(1)   # pump so the window actually closes
    return key != 27   # 27 = ESC


def _select_anchors(cv2: Any, frame: Any, limit: int = 3) -> list[Anchor]:  # pragma: no cover
    """Collect optional anchor boxes over fixed HUD furniture — click-only, no
    typing (so it works in the windowed app too). Draw a box and press ENTER to
    keep it, or press ESC / 'c' to finish. Anchors are auto-named."""
    anchors: list[Anchor] = []
    print("\nSTEP 4/4 (optional): box fixed HUD landmarks (timer, objective bar) "
          "as extra reference. Press ENTER after each box, or press ESC / 'c' to "
          "finish — you can also finish with none.")
    while len(anchors) < limit:
        title = (f"STEP 4/4 (optional): box a fixed HUD element then ENTER, "
                 f"or ESC/c to finish  [{len(anchors)} so far]")
        x, y, w, h = cv2.selectROI(title, frame, showCrosshair=True, fromCenter=False)
        cv2.destroyWindow(title)
        rect = Rect(int(x), int(y), int(w), int(h))
        if rect.is_empty:  # ESC / cancel -> done
            break
        anchors.append(Anchor(name=f"anchor_{len(anchors) + 1}", rect=rect))
    print(f"  {len(anchors)} anchor(s) captured.")
    return anchors


def default_frame_dir(db_path: str) -> str:
    """Where to save the full calibration frame: a ``calibration/`` dir next to
    the owscout DB."""
    return str(Path(db_path).resolve().parent / "calibration")

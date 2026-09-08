"""Auto-calibration draws the ROI boxes from known HUD proportions.

Calibration is the one manual step; auto_profile removes the dragging on standard
16:9. The guarantee tested here: it reproduces a hand calibration to within a
pixel or two (the matcher's slide tolerance) and never emits a box off-screen.
"""

from __future__ import annotations

import pytest

from owdb.calibrate import AUTO_STRIPS, auto_profile
from owdb.models import SIDE_LEFT, SIDE_RIGHT


def test_five_slots_per_side() -> None:
    p = auto_profile(1920, 1080, hud_variant="default")
    assert len(p.slots[SIDE_LEFT]) == 5
    assert len(p.slots[SIDE_RIGHT]) == 5


def test_reproduces_the_1440p_hand_calibration() -> None:
    """The layout came from 1440p hand calibrations; regenerating at 1440p must
    land back on those boxes (measured side-a slot0 ~ x129 y119 w132 h99)."""
    p = auto_profile(2560, 1440, hud_variant="default")
    s0 = p.slots[SIDE_LEFT][0]
    assert abs(s0.x - 129) <= 2
    assert abs(s0.y - 119) <= 2
    assert abs(s0.w - 132) <= 2
    assert abs(s0.h - 99) <= 3


def test_slots_scale_with_resolution() -> None:
    """1080p portraits are 0.75x of 1440p (proportional HUD)."""
    p1440 = auto_profile(2560, 1440, hud_variant="default").slots[SIDE_LEFT][0]
    p1080 = auto_profile(1920, 1080, hud_variant="default").slots[SIDE_LEFT][0]
    assert p1080.w == pytest.approx(p1440.w * 0.75, abs=2)
    assert p1080.h == pytest.approx(p1440.h * 0.75, abs=2)


def test_slots_are_gap_free_and_in_order() -> None:
    slots = auto_profile(1920, 1080, hud_variant="default").slots[SIDE_LEFT]
    xs = [s.x for s in slots]
    assert xs == sorted(xs)                       # left-to-right
    for a, b in zip(slots, slots[1:], strict=False):
        # next slot starts within a pixel of where the previous ends (tiling).
        assert abs((a.x + a.w) - b.x) <= 1


def test_every_box_is_on_screen() -> None:
    for w, h in ((1920, 1080), (2560, 1440), (3840, 2160)):
        p = auto_profile(w, h, hud_variant="default")
        for side in (SIDE_LEFT, SIDE_RIGHT):
            for r in p.slots[side]:
                assert r.x >= 0 and r.x + r.w <= w
                assert r.y >= 0 and r.y + r.h <= h


def test_left_and_right_strips_are_mirrored_halves() -> None:
    """Left roster in the left third, right roster in the right third - a sanity
    check that the two strips didn't get swapped or overlap the centre."""
    assert AUTO_STRIPS[SIDE_LEFT][0] < 0.35
    assert AUTO_STRIPS[SIDE_RIGHT][0] > 0.65


def test_vertical_placement_ignores_the_frames_aspect_ratio() -> None:
    """The HUD scales with the rendered width, so a frame that is not 16:9 must
    not move the strips vertically.

    AUTO_STRIPS' y/h are fractions of HEIGHT, which is only equivalent to the
    real HUD proportions at 16:9. Measured against a live 2570x1393 window
    capture (aspect 1.845), that put the strips 10-12px too high and 6px too
    short - and the offset sweep in the browser tool steps by 0.01 of height,
    13.9px there, so it cannot even resolve an error that size. It plateaued at
    4/10 portraits recognised.
    """
    wide = auto_profile(2560, 1440, hud_variant="default").slots[SIDE_LEFT][0]
    squashed = auto_profile(2560, 1300, hud_variant="default").slots[SIDE_LEFT][0]
    assert squashed.y == wide.y, "same width, so the HUD sits at the same height"
    assert squashed.h == wide.h, "same width, so the portraits are the same size"


def test_lands_near_the_2570x1393_window_capture() -> None:
    """Ground truth read out of a live session (2026-09-07), not a screenshot.

    The operator hand-set the boxes over a window capture and reported
    boxes.a = x135.5 y125.5 w660.1 h100.4 at videoWidth 2570 x 1393. Horizontal
    was already correct (dx +5.5, dw -2.7); the whole error was vertical.
    Tolerances are loose because a hand-drawn box carries a few px of jitter and
    the window's own top chrome is inside the frame.
    """
    s0 = auto_profile(2570, 1393, hud_variant="default").slots[SIDE_LEFT][0]
    assert abs(s0.x - 135.5) <= 7
    assert abs(s0.w - 132.0) <= 7
    assert abs(s0.y - 125.5) <= 7
    assert abs(s0.h - 100.4) <= 4

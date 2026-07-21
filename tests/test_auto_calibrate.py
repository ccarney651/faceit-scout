"""Auto-calibration draws the ROI boxes from known HUD proportions.

Calibration is the one manual step; auto_profile removes the dragging on standard
16:9. The guarantee tested here: it reproduces a hand calibration to within a
pixel or two (the matcher's slide tolerance) and never emits a box off-screen.
"""

from __future__ import annotations

import pytest

from owscout.calibrate import AUTO_STRIPS, auto_profile
from owscout.models import SIDE_LEFT, SIDE_RIGHT


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
    for a, b in zip(slots, slots[1:]):
        # next slot starts within a pixel of where the previous ends (tiling).
        assert abs((a.x + a.w) - b.x) <= 1


def test_every_box_is_on_screen() -> None:
    for w, h in ((1920, 1080), (2560, 1440), (3840, 2160)):
        p = auto_profile(w, h, hud_variant="default")
        for side in (SIDE_LEFT, SIDE_RIGHT):
            for r in p.slots[side]:
                assert 0 <= r.x and r.x + r.w <= w
                assert 0 <= r.y and r.y + r.h <= h


def test_left_and_right_strips_are_mirrored_halves() -> None:
    """Left roster in the left third, right roster in the right third - a sanity
    check that the two strips didn't get swapped or overlap the centre."""
    assert AUTO_STRIPS[SIDE_LEFT][0] < 0.35
    assert AUTO_STRIPS[SIDE_RIGHT][0] > 0.65

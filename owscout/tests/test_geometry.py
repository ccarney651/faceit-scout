"""Strip subdivision: SPEC §5 step 2 — each strip splits into team_size equal
gap-free ROIs."""

from __future__ import annotations

import pytest

from owscout.calibrate import subdivide_strip
from owscout.models import Rect


def test_horizontal_strip_splits_evenly() -> None:
    slots = subdivide_strip(Rect(100, 40, 500, 60), 5)
    assert len(slots) == 5
    assert all(s.w == 100 and s.h == 60 and s.y == 40 for s in slots)
    assert [s.x for s in slots] == [100, 200, 300, 400, 500]


def test_slots_tile_the_strip_exactly() -> None:
    """No gaps, no overlap: slots cover the strip end to end."""
    strip = Rect(10, 10, 503, 60)  # 503 not divisible by 5
    slots = subdivide_strip(strip, 5)
    # widths sum to the strip width; remainder goes to leading slots.
    assert sum(s.w for s in slots) == strip.w
    assert [s.w for s in slots] == [101, 101, 101, 100, 100]
    # each slot starts where the previous ended.
    for prev, nxt in zip(slots, slots[1:]):
        assert nxt.x == prev.x + prev.w
    assert slots[0].x == strip.x
    assert slots[-1].x + slots[-1].w == strip.x + strip.w


def test_vertical_strip_splits_along_height() -> None:
    slots = subdivide_strip(Rect(20, 0, 40, 300), 5)
    assert all(s.w == 40 and s.x == 20 for s in slots)
    assert [s.y for s in slots] == [0, 60, 120, 180, 240]


def test_team_size_agnostic() -> None:
    assert len(subdivide_strip(Rect(0, 0, 600, 50), 6)) == 6


def test_invalid_count_rejected() -> None:
    with pytest.raises(ValueError):
        subdivide_strip(Rect(0, 0, 500, 60), 0)


def test_strip_too_small_rejected() -> None:
    # Fewer pixels along the split (longer) axis than slots requested.
    with pytest.raises(ValueError):
        subdivide_strip(Rect(0, 0, 3, 2), 5)


def test_empty_strip_rejected() -> None:
    with pytest.raises(ValueError):
        subdivide_strip(Rect(0, 0, 0, 60), 5)

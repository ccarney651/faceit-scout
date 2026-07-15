"""Profile assembly, JSON round-trip, and roi_profiles persistence."""

from __future__ import annotations

from pathlib import Path
from typing import Iterator

import pytest

from owscout.calibrate import build_profile
from owscout.db import Database
from owscout.models import Anchor, Rect, RoiProfile


def _sample_profile(hud_variant: str = "default") -> RoiProfile:
    return build_profile(
        resolution_w=2560,
        resolution_h=1440,
        hud_variant=hud_variant,
        team_size=5,
        left_strip=Rect(100, 40, 500, 60),
        right_strip=Rect(1960, 40, 500, 60),
        anchors=[
            Anchor("objective_bar", Rect(1200, 20, 160, 30)),
            Anchor("timer", Rect(1240, 0, 80, 20)),
        ],
    )


@pytest.fixture()
def db(tmp_path: Path) -> Iterator[Database]:
    database = Database(str(tmp_path / "owscout.sqlite3"))
    yield database
    database.close()


def test_build_profile_shapes() -> None:
    p = _sample_profile()
    assert set(p.slots) == {"a", "b"}
    assert len(p.slots["a"]) == 5 and len(p.slots["b"]) == 5
    assert p.slots["a"][0] == Rect(100, 40, 100, 60)


def test_json_roundtrip() -> None:
    p = _sample_profile()
    assert RoiProfile.slots_from_json(p.slots_json()) == p.slots
    assert RoiProfile.anchors_from_json(p.anchors_json()) == p.anchors


def test_valid_at_resolution() -> None:
    p = _sample_profile()
    assert p.valid_at(2560, 1440)
    assert not p.valid_at(1920, 1080)


def test_save_and_get_active_roundtrip(db: Database) -> None:
    p = _sample_profile()
    pid = db.save_profile(p)
    assert pid > 0 and p.id == pid

    loaded = db.get_active_profile(2560, 1440, "default")
    assert loaded is not None
    assert loaded.slots == p.slots
    assert loaded.anchors == p.anchors
    assert loaded.team_size == 5
    assert loaded.retired_at is None


def test_recalibration_retires_previous(db: Database) -> None:
    first = db.save_profile(_sample_profile())
    second = db.save_profile(_sample_profile())
    assert second != first

    # Only the latest is active for that (resolution, variant).
    active = db.get_active_profile(2560, 1440, "default")
    assert active is not None and active.id == second

    rows = db.conn.execute(
        "SELECT id, retired_at FROM roi_profiles ORDER BY id"
    ).fetchall()
    assert len(rows) == 2
    assert rows[0]["id"] == first and rows[0]["retired_at"] is not None
    assert rows[1]["id"] == second and rows[1]["retired_at"] is None


def test_variants_are_independent(db: Database) -> None:
    db.save_profile(_sample_profile("default"))
    db.save_profile(_sample_profile("stream_overlay"))
    # Saving one variant must not retire the other.
    assert db.get_active_profile(2560, 1440, "default") is not None
    assert db.get_active_profile(2560, 1440, "stream_overlay") is not None


def test_missing_profile_is_none(db: Database) -> None:
    assert db.get_active_profile(1920, 1080, "default") is None

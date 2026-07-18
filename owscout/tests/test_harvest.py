"""Ref-harvest and coverage: turning Review corrections into library improvements."""

from pathlib import Path
from typing import Iterator

import pytest

from owscout.db import Database


@pytest.fixture()
def db(tmp_path: Path) -> Iterator[Database]:
    database = Database(str(tmp_path / "owscout.sqlite3"))
    yield database
    database.close()


ROLES = {"ram": "tank", "soj": "damage", "mei": "damage",
         "luc": "support", "kir": "support", "mauga": "tank"}
NAMES = {g: g.upper() for g in ROLES}


def _map_with_obs(db: Database, tmp_path: Path, guids: list[str],
                  confidences: list[float]) -> int:
    """One map with one observation whose slots carry crops on disk."""
    with db.transaction() as c:
        c.execute("""INSERT INTO map_instances (source_type, match_id, game_no, demo_code)
                     VALUES ('faceit', 'm1', 1, 'CODE1')""")
        mid = int(c.execute("SELECT id FROM map_instances").fetchone()["id"])
    slots = []
    for i, (g, conf) in enumerate(zip(guids, confidences)):
        crop = tmp_path / f"crop_{i}.png"
        crop.write_bytes(b"not-a-real-png")      # only the PATH matters here
        slots.append({"slot_index": i, "hero_guid": g, "confidence": conf,
                      "is_dead": 0, "crop_path": str(crop)})
    db.upsert_comp_observation(
        map_instance_id=mid, side="a", sample_ts_ms=0, comp_id=None,
        min_slot_confidence=min(confidences), resolved=0, slots=slots)
    return mid


def test_crop_paths_survive_the_round_trip(db: Database, tmp_path: Path) -> None:
    """The whole feature rests on this: if the crop path is not stored at capture,
    a correction has no pixels to learn from."""
    mid = _map_with_obs(db, tmp_path, ["ram", "soj"], [0.9, 0.6])
    rows = db.conn.execute(
        "SELECT crop_path FROM comp_slots ORDER BY slot_index").fetchall()
    assert all(r["crop_path"] for r in rows)
    assert db.harvest_candidates(mid, "a", "soj")


def test_harvest_prefers_the_worst_appearance(db: Database, tmp_path: Path) -> None:
    """The lowest-confidence crop is the one the current ref actually failed on,
    so it is the most useful thing to learn from - not an easy repeat."""
    mid = _map_with_obs(db, tmp_path, ["ram", "soj"], [0.9, 0.6])
    # Add a second, higher-confidence appearance of the same hero.
    crop2 = tmp_path / "crop_hi.png"; crop2.write_bytes(b"x")
    db.upsert_comp_observation(
        map_instance_id=mid, side="a", sample_ts_ms=100, comp_id=None,
        min_slot_confidence=0.95, resolved=0,
        slots=[{"slot_index": 0, "hero_guid": "soj", "confidence": 0.95,
                "is_dead": 0, "crop_path": str(crop2)}])
    best = db.harvest_candidates(mid, "a", "soj", limit=2)
    assert best[0].endswith("crop_1.png")      # the 0.60 one, not the 0.95 one


def test_correction_is_logged_as_ground_truth(db: Database, tmp_path: Path) -> None:
    """Confidence cannot distinguish a confidently WRONG ref from an uncertain
    one. An operator correction can, so it is recorded."""
    mid = _map_with_obs(db, tmp_path, ["ram", "soj"], [0.9, 0.95])
    n = db.correct_hero_in_map(mid, "a", "soj", "mei",
                               hero_roles=ROLES, hero_names=NAMES)
    assert n == 1
    row = db.conn.execute("SELECT * FROM hero_corrections").fetchone()
    assert (row["wrong_guid"], row["right_guid"], row["side"]) == ("soj", "mei", "a")


def test_no_correction_logged_when_nothing_matched(db: Database, tmp_path: Path) -> None:
    """A no-op fix must not pollute the coverage report with a phantom failure."""
    mid = _map_with_obs(db, tmp_path, ["ram", "soj"], [0.9, 0.95])
    assert db.correct_hero_in_map(mid, "a", "mauga", "mei",
                                  hero_roles=ROLES, hero_names=NAMES) == 0
    assert db.conn.execute("SELECT COUNT(*) FROM hero_corrections").fetchone()[0] == 0


def test_harvest_candidates_ignores_slots_without_a_crop(db: Database) -> None:
    """Captures predating crop storage have NULL paths; harvesting must degrade to
    'nothing to learn' rather than erroring."""
    with db.transaction() as c:
        c.execute("""INSERT INTO map_instances (source_type, match_id, game_no)
                     VALUES ('faceit', 'm2', 1)""")
        mid = int(c.execute("SELECT id FROM map_instances").fetchone()["id"])
    db.upsert_comp_observation(
        map_instance_id=mid, side="a", sample_ts_ms=0, comp_id=None,
        min_slot_confidence=0.5, resolved=0,
        slots=[{"slot_index": 0, "hero_guid": "ram", "confidence": 0.5, "is_dead": 0}])
    assert db.harvest_candidates(mid, "a", "ram") == []

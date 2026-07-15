"""Capture persistence: map_instance from context, comps, and idempotent
observation+slots writes (SPEC §4, §12)."""

from __future__ import annotations

from pathlib import Path
from typing import Iterator

import pytest

from owscout.comps import canonical_comp
from owscout.db import Database
from owscout.models import CodeContext


@pytest.fixture()
def db(tmp_path: Path) -> Iterator[Database]:
    database = Database(str(tmp_path / "owscout.sqlite3"))
    yield database
    database.close()


def _ctx(winner: str | None = "faction2") -> CodeContext:
    return CodeContext(
        demo_code="ABC123", match_id="M1", game_no=1,
        map_guid="g-kr", map_name="Kings Row", map_category="Hybrid",
        faction1_team_id="tA", faction1_team_name="Alpha",
        faction2_team_id="tB", faction2_team_name="Bravo",
        winner_faction=winner, bans=[], players=[], already_captured=False,
    )


# --- map_instances -----------------------------------------------------------


def test_map_instance_derives_sides_and_winner(db: Database) -> None:
    mid = db.upsert_map_instance_from_context(_ctx(), side_a_faction="faction2")
    row = db.conn.execute("SELECT * FROM map_instances WHERE id=?", (mid,)).fetchone()
    # side A = faction2 (Bravo) since we said so; winner faction2 -> side 'a'.
    assert row["side_a_team_id"] == "tB" and row["side_a_label"] == "Bravo"
    assert row["side_b_team_id"] == "tA" and row["side_b_label"] == "Alpha"
    assert row["winner_side"] == "a"
    assert row["source_type"] == "faceit" and row["map_name"] == "Kings Row"


def test_map_instance_winner_side_b(db: Database) -> None:
    mid = db.upsert_map_instance_from_context(_ctx(winner="faction2"), side_a_faction="faction1")
    row = db.conn.execute("SELECT winner_side FROM map_instances WHERE id=?", (mid,)).fetchone()
    assert row["winner_side"] == "b"   # faction2 won but is on side B


def test_map_instance_no_winner(db: Database) -> None:
    mid = db.upsert_map_instance_from_context(_ctx(winner=None), side_a_faction="faction1")
    row = db.conn.execute("SELECT winner_side FROM map_instances WHERE id=?", (mid,)).fetchone()
    assert row["winner_side"] is None


def test_map_instance_idempotent(db: Database) -> None:
    first = db.upsert_map_instance_from_context(_ctx(), side_a_faction="faction1")
    second = db.upsert_map_instance_from_context(_ctx(), side_a_faction="faction1")
    assert first == second
    assert db.conn.execute("SELECT COUNT(*) FROM map_instances").fetchone()[0] == 1


def test_map_instance_rejects_bad_side(db: Database) -> None:
    with pytest.raises(ValueError):
        db.upsert_map_instance_from_context(_ctx(), side_a_faction="left")


# --- comps -------------------------------------------------------------------


def test_upsert_comp_idempotent(db: Database) -> None:
    comp = canonical_comp(["a", "b", "c"], {"a": "Tank"}, {"a": "A"})
    db.upsert_comp(comp)
    db.upsert_comp(comp)
    rows = db.conn.execute("SELECT * FROM comps").fetchall()
    assert len(rows) == 1
    assert rows[0]["comp_id"] == comp.comp_id and rows[0]["team_size"] == 3


# --- comp_observations + slots ----------------------------------------------


def _obs(db: Database, ts: int, guids: list[str | None], resolved: int) -> int:
    mid = db.upsert_map_instance_from_context(_ctx(), side_a_faction="faction1")
    slots = [{"slot_index": i, "hero_guid": g, "confidence": 0.9,
              "is_dead": 0, "expected_role": None, "ingame_name_raw": None,
              "player_id": None} for i, g in enumerate(guids)]
    return db.upsert_comp_observation(
        map_instance_id=mid, side="a", sample_ts_ms=ts, comp_id=None,
        min_slot_confidence=0.9, resolved=resolved, slots=slots)


def test_observation_and_slots_written(db: Database) -> None:
    oid = _obs(db, 1000, ["A", "B", None], resolved=0)
    slots = db.conn.execute(
        "SELECT * FROM comp_slots WHERE observation_id=? ORDER BY slot_index", (oid,)
    ).fetchall()
    assert [s["hero_guid"] for s in slots] == ["A", "B", None]


def test_observation_idempotent_on_key(db: Database) -> None:
    _obs(db, 1000, ["A", "B"], resolved=0)
    _obs(db, 1000, ["A", "C"], resolved=1)   # same (map,side,ts) -> UPDATE
    obs = db.conn.execute("SELECT * FROM comp_observations").fetchall()
    assert len(obs) == 1 and obs[0]["resolved"] == 1
    # Slots were rewritten, not appended.
    slots = db.conn.execute("SELECT hero_guid FROM comp_slots ORDER BY slot_index").fetchall()
    assert [s["hero_guid"] for s in slots] == ["A", "C"]


def test_distinct_timestamps_are_separate_rows(db: Database) -> None:
    _obs(db, 1000, ["A", "B"], resolved=1)
    _obs(db, 2000, ["A", "B"], resolved=1)
    assert db.conn.execute("SELECT COUNT(*) FROM comp_observations").fetchone()[0] == 2


def test_resolved_observation_inserts_its_comp(db: Database) -> None:
    # A resolved observation's comp_id FKs into comps; passing `comp` must insert
    # it in the same transaction (regression: FK failure without it).
    mid = db.upsert_map_instance_from_context(_ctx(), side_a_faction="faction1")
    comp = canonical_comp(["g-ram", "g-ana"], {"g-ram": "Tank"}, {"g-ram": "Ramattra"})
    slots = [{"slot_index": 0, "hero_guid": "g-ram", "confidence": 0.9, "is_dead": 0,
              "expected_role": None, "ingame_name_raw": None, "player_id": None},
             {"slot_index": 1, "hero_guid": "g-ana", "confidence": 0.9, "is_dead": 0,
              "expected_role": None, "ingame_name_raw": None, "player_id": None}]
    db.upsert_comp_observation(map_instance_id=mid, side="a", sample_ts_ms=0,
                              comp_id=comp.comp_id, min_slot_confidence=0.9, resolved=1,
                              slots=slots, comp=comp)
    row = db.conn.execute("SELECT comp_id, resolved FROM comp_observations").fetchone()
    assert row["resolved"] == 1 and row["comp_id"] == comp.comp_id
    assert db.conn.execute("SELECT COUNT(*) FROM comps").fetchone()[0] == 1

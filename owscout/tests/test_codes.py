"""codes list/age (SPEC §7) and the review resolve loop (SPEC appendix)."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Iterator, cast

import pytest

from owscout.comps import comp_id_for
from owscout.db import Database
from owscout.models import CodeContext


@pytest.fixture()
def db(tmp_path: Path) -> Iterator[Database]:
    database = Database(str(tmp_path / "owscout.sqlite3"))
    yield database
    database.close()


def _faceit(path: Path) -> str:
    """Two matches: one pre-wipe (dead), one post-wipe (alive), with codes."""
    c = sqlite3.connect(str(path))
    c.executescript("""
        CREATE TABLE games(match_id TEXT, game_no INT, map_guid TEXT, demo_code TEXT);
        CREATE TABLE matches(id TEXT PRIMARY KEY, faction1_team_id TEXT, faction2_team_id TEXT,
                            finished_at TEXT, championship_id TEXT);
        CREATE TABLE championships(id TEXT PRIMARY KEY, name TEXT);
        CREATE TABLE maps(guid TEXT PRIMARY KEY, name TEXT, category TEXT);
        CREATE TABLE teams(id TEXT PRIMARY KEY, name TEXT);
    """)
    c.execute("INSERT INTO championships VALUES('cm','S9 Master Central'),('ce','S9 Expert Central')")
    c.execute("INSERT INTO teams VALUES('tA','Alpha'),('tB','Bravo'),('tC','Cabra')")
    c.execute("INSERT INTO maps VALUES('m-ilios','Ilios','Control')")
    # pre-wipe match (2026-07-08) and post-wipe match (2026-07-15), both Master
    c.execute("INSERT INTO matches VALUES('OLD','tA','tB','2026-07-08T20:00:00Z','cm')")
    c.execute("INSERT INTO matches VALUES('NEW','tA','tC','2026-07-15T20:00:00Z','cm')")
    c.executemany("INSERT INTO games VALUES(?,?,?,?)", [
        ("OLD", 1, "m-ilios", "OLD111"),
        ("NEW", 1, "m-ilios", "NEW111"),
        ("NEW", 2, "m-ilios", "NEW222"),
    ])
    c.commit(); c.close()
    return str(path)


# --- codes list --------------------------------------------------------------


def test_list_codes_hides_wiped_by_default(db: Database, tmp_path: Path) -> None:
    fp = _faceit(tmp_path / "faceit.sqlite3")
    rows = db.list_codes(fp)
    codes = {r.demo_code for r in rows}
    assert codes == {"NEW111", "NEW222"}          # OLD111 pre-dates 2026-07-14 wipe
    assert all(not r.wiped for r in rows)


def test_list_codes_include_wiped(db: Database, tmp_path: Path) -> None:
    fp = _faceit(tmp_path / "faceit.sqlite3")
    rows = db.list_codes(fp, include_wiped=True)
    old = next(r for r in rows if r.demo_code == "OLD111")
    assert old.wiped is True
    assert {r.demo_code for r in rows} == {"OLD111", "NEW111", "NEW222"}


def test_list_codes_newest_first(db: Database, tmp_path: Path) -> None:
    fp = _faceit(tmp_path / "faceit.sqlite3")
    rows = db.list_codes(fp, include_wiped=True)
    assert rows[0].finished_at >= rows[-1].finished_at  # type: ignore[operator]


def test_list_codes_by_team(db: Database, tmp_path: Path) -> None:
    fp = _faceit(tmp_path / "faceit.sqlite3")
    rows = db.list_codes(fp, team="Cabra")
    assert {r.demo_code for r in rows} == {"NEW111", "NEW222"}  # Cabra only in NEW


def test_list_codes_captured_flag_and_uncaptured(db: Database, tmp_path: Path) -> None:
    fp = _faceit(tmp_path / "faceit.sqlite3")
    ctx = CodeContext(demo_code="NEW111", match_id="NEW", game_no=1, map_guid="m-ilios",
                      map_name="Ilios", map_category="Control", faction1_team_id="tA",
                      faction1_team_name="Alpha", faction2_team_id="tC", faction2_team_name="Cabra",
                      winner_faction=None, bans=[], players=[], already_captured=False)
    db.upsert_map_instance_from_context(ctx, side_a_faction="faction1")
    rows = {r.demo_code: r for r in db.list_codes(fp)}
    assert rows["NEW111"].captured is True and rows["NEW222"].captured is False
    assert {r.demo_code for r in db.list_codes(fp, uncaptured=True)} == {"NEW222"}


def test_list_codes_division_filter(db: Database, tmp_path: Path) -> None:
    fp = _faceit(tmp_path / "faceit.sqlite3")
    con = sqlite3.connect(fp)
    con.execute("INSERT INTO matches VALUES('EXP','tA','tB','2026-07-15T20:00:00Z','ce')")
    con.execute("INSERT INTO games VALUES('EXP',1,'m-ilios','EXP111')")
    con.commit(); con.close()
    assert "EXP111" not in {r.demo_code for r in db.list_codes(fp)}          # master default
    assert "EXP111" in {r.demo_code for r in db.list_codes(fp, division="expert")}
    assert {"NEW111", "NEW222", "EXP111"} <= {r.demo_code for r in db.list_codes(fp, division=None)}


def test_code_age_summary(db: Database, tmp_path: Path) -> None:
    fp = _faceit(tmp_path / "faceit.sqlite3")
    s = db.code_age_summary(fp)
    assert s["latest_wipe"] == "2026-07-14"
    assert s["total_codes"] == 3
    assert s["alive_codes"] == 2 and s["dead_codes"] == 1


# --- codes mark --------------------------------------------------------------


def test_codes_mark_roundtrip(db: Database) -> None:
    db.upsert_code_status("NEW111", "skipped", "not relevant")
    assert db.get_code_status("NEW111") == "skipped"


# --- review ------------------------------------------------------------------


def _seed_unresolved(db: Database) -> int:
    ctx = CodeContext(demo_code="NEW111", match_id="NEW", game_no=1, map_guid=None,
                      map_name="Ilios", map_category=None, faction1_team_id="tA",
                      faction1_team_name="Alpha", faction2_team_id="tC", faction2_team_name="Cabra",
                      winner_faction=None, bans=[], players=[], already_captured=False)
    mid = db.upsert_map_instance_from_context(ctx, side_a_faction="faction1")
    slots: list[dict[str, object]] = [
        {"slot_index": 0, "hero_guid": "g-ram", "confidence": 0.9, "is_dead": 0,
         "expected_role": None, "ingame_name_raw": None, "player_id": None},
        {"slot_index": 1, "hero_guid": None, "confidence": 0.5, "is_dead": 0,
         "expected_role": None, "ingame_name_raw": None, "player_id": None}]
    db.upsert_comp_observation(map_instance_id=mid, side="a", sample_ts_ms=1000,
                              comp_id=None, min_slot_confidence=0.5, resolved=0, slots=slots)
    return mid


def test_unresolved_queue_lists_gaps(db: Database) -> None:
    _seed_unresolved(db)
    queue = db.unresolved_observations()
    assert len(queue) == 1
    slots = cast("list[dict[str, object]]", queue[0]["slots"])
    gaps = [s for s in slots if s["hero_guid"] is None]
    assert [s["slot_index"] for s in gaps] == [1]


def test_resolve_slot_completes_and_canonicalises(db: Database) -> None:
    _seed_unresolved(db)
    obs_id = cast(int, db.unresolved_observations()[0]["id"])
    roles = {"g-ram": "Tank", "g-ana": "Support"}
    names = {"g-ram": "Ramattra", "g-ana": "Ana"}
    done = db.resolve_slot(obs_id, 1, "g-ana", hero_roles=roles, hero_names=names)
    assert done is True
    # Observation now resolved with the canonical comp id, and out of the queue.
    assert db.unresolved_observations() == []
    row = db.conn.execute("SELECT comp_id, resolved FROM comp_observations").fetchone()
    assert row["resolved"] == 1 and row["comp_id"] == comp_id_for(["g-ram", "g-ana"])
    assert db.conn.execute("SELECT COUNT(*) FROM comps").fetchone()[0] == 1


def test_resolve_slot_partial_stays_unresolved(db: Database) -> None:
    # Seed an observation with TWO gaps; resolving one keeps it in the queue.
    ctx = CodeContext(demo_code="X", match_id="NEW", game_no=2, map_guid=None,
                      map_name="Ilios", map_category=None, faction1_team_id="tA",
                      faction1_team_name="A", faction2_team_id="tC", faction2_team_name="C",
                      winner_faction=None, bans=[], players=[], already_captured=False)
    mid = db.upsert_map_instance_from_context(ctx, side_a_faction="faction1")
    slots: list[dict[str, object]] = [
        {"slot_index": 0, "hero_guid": None, "confidence": 0.5, "is_dead": 0,
         "expected_role": None, "ingame_name_raw": None, "player_id": None},
        {"slot_index": 1, "hero_guid": None, "confidence": 0.5, "is_dead": 0,
         "expected_role": None, "ingame_name_raw": None, "player_id": None}]
    oid = db.upsert_comp_observation(map_instance_id=mid, side="a", sample_ts_ms=1,
                                     comp_id=None, min_slot_confidence=0.5, resolved=0, slots=slots)
    done = db.resolve_slot(oid, 0, "g-ram", hero_roles={}, hero_names={})
    assert done is False
    assert len(db.unresolved_observations()) == 1

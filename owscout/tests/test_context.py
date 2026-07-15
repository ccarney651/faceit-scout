"""Step 4: schema/wipe seeding, read-only ATTACH, and --code context derivation."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Iterator

import pytest

from owscout.context import (
    AmbiguousCode,
    CodeNotFound,
    derive_code_context,
    format_context,
)
from owscout.db import Database


# --- fixtures ----------------------------------------------------------------


@pytest.fixture()
def db(tmp_path: Path) -> Iterator[Database]:
    database = Database(str(tmp_path / "owscout.sqlite3"))
    yield database
    database.close()


def _build_faceit(path: Path) -> str:
    """A minimal faceit DB with one map (code ABC123): Kings Row, teams Alpha vs
    Bravo, Bravo wins, 2 bans, 10 players."""
    c = sqlite3.connect(str(path))
    c.executescript(
        """
        CREATE TABLE games(match_id TEXT, game_no INT, map_guid TEXT, map_category TEXT,
                           winner_faction TEXT, demo_code TEXT);
        CREATE TABLE matches(id TEXT PRIMARY KEY, faction1_team_id TEXT, faction2_team_id TEXT);
        CREATE TABLE maps(guid TEXT PRIMARY KEY, name TEXT, category TEXT);
        CREATE TABLE teams(id TEXT PRIMARY KEY, name TEXT);
        CREATE TABLE heroes(guid TEXT PRIMARY KEY, name TEXT, role TEXT);
        CREATE TABLE hero_bans(match_id TEXT, game_no INT, hero_guid TEXT, ban_order INT,
                              banned_by_faction TEXT);
        CREATE TABLE round_players(match_id TEXT, game_no INT, team_id TEXT, player_id TEXT, role TEXT);
        CREATE TABLE players(id TEXT PRIMARY KEY, nickname TEXT);
        """
    )
    c.execute("INSERT INTO matches VALUES('M1','tA','tB')")
    c.execute("INSERT INTO teams VALUES('tA','Alpha'),('tB','Bravo')")
    c.execute("INSERT INTO maps VALUES('map-kr','Kings Row','Hybrid')")
    c.execute("INSERT INTO games VALUES('M1',1,'map-kr','Hybrid','faction2','ABC123')")
    c.execute("INSERT INTO heroes VALUES('h-ram','Ramattra','Tank'),('h-sojourn','Sojourn','Damage')")
    c.executemany("INSERT INTO hero_bans VALUES(?,?,?,?,?)", [
        ("M1", 1, "h-ram", 1, "faction1"),
        ("M1", 1, "h-sojourn", 2, "faction2"),
    ])
    roster = []
    for i in range(5):
        roster.append(("M1", 1, "tA", f"pa{i}", "Tank" if i == 0 else "Damage"))
        roster.append(("M1", 1, "tB", f"pb{i}", "Support" if i < 2 else "Damage"))
    c.executemany("INSERT INTO round_players VALUES(?,?,?,?,?)", roster)
    c.executemany("INSERT INTO players VALUES(?,?)",
                  [(f"pa{i}", f"AlphaGuy{i}") for i in range(5)]
                  + [(f"pb{i}", f"BravoGuy{i}") for i in range(5)])
    c.commit()
    c.close()
    return str(path)


# --- schema / wipe seeding ---------------------------------------------------


def test_all_tables_created(db: Database) -> None:
    names = {r["name"] for r in db.conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'")}
    expected = {"roi_profiles", "hero_refs", "game_builds", "scrims", "map_instances",
                "comps", "comp_observations", "comp_slots", "player_aliases",
                "capture_log", "wipes", "code_status"}
    assert expected <= names


def test_wipe_seeded_idempotently(tmp_path: Path) -> None:
    p = str(tmp_path / "ow.sqlite3")
    Database(p).close()
    db2 = Database(p)  # re-open: init_schema runs again
    try:
        assert db2.latest_wipe_date() == "2026-07-14"
        assert db2.conn.execute("SELECT COUNT(*) FROM wipes").fetchone()[0] == 1
    finally:
        db2.close()


def test_map_instance_check_constraint(db: Database) -> None:
    # A faceit instance needs match_id+game_no and no scrim_id; violating raises.
    with pytest.raises(sqlite3.IntegrityError):
        db.conn.execute(
            "INSERT INTO map_instances (source_type, match_id, game_no, scrim_id, "
            "map_verified) VALUES ('faceit','M1',1,5,1)"
        )


def test_code_status_upsert(db: Database) -> None:
    db.upsert_code_status("ABC123", "captured", "done")
    assert db.get_code_status("ABC123") == "captured"
    db.upsert_code_status("ABC123", "failed")
    assert db.get_code_status("ABC123") == "failed"  # updated, not duplicated
    assert db.conn.execute("SELECT COUNT(*) FROM code_status").fetchone()[0] == 1


# --- ATTACH read-only --------------------------------------------------------


def test_attach_is_read_only(db: Database, tmp_path: Path) -> None:
    fp = _build_faceit(tmp_path / "faceit.sqlite3")
    db.attach_faceit(fp)
    # Reads work...
    assert db.conn.execute("SELECT COUNT(*) FROM faceit.teams").fetchone()[0] == 2
    # ...writes to faceit are rejected at the SQLite level.
    with pytest.raises(sqlite3.OperationalError):
        db.conn.execute("INSERT INTO faceit.teams VALUES('x','X')")


def test_attach_is_idempotent(db: Database, tmp_path: Path) -> None:
    fp = _build_faceit(tmp_path / "faceit.sqlite3")
    db.attach_faceit(fp)
    db.attach_faceit(fp)  # second call is a no-op, not an error
    assert db.conn.execute("SELECT COUNT(*) FROM faceit.games").fetchone()[0] == 1


# --- context derivation ------------------------------------------------------


def test_derive_full_context(db: Database, tmp_path: Path) -> None:
    fp = _build_faceit(tmp_path / "faceit.sqlite3")
    ctx = derive_code_context(db, fp, "ABC123")
    assert (ctx.match_id, ctx.game_no) == ("M1", 1)
    assert ctx.map_name == "Kings Row" and ctx.map_category == "Hybrid"
    assert ctx.faction1_team_name == "Alpha" and ctx.faction2_team_name == "Bravo"
    assert ctx.winner_faction == "faction2"
    assert ctx.team_name(ctx.winner_faction) == "Bravo"
    assert len(ctx.bans) == 2
    assert ctx.bans[0].hero_name == "Ramattra"
    assert ctx.bans[0].banned_by_team_id == "tA"  # faction1 -> Alpha
    assert len(ctx.players) == 10
    assert {p.faction for p in ctx.players} == {"faction1", "faction2"}
    assert not ctx.already_captured


def test_already_captured_flag(db: Database, tmp_path: Path) -> None:
    fp = _build_faceit(tmp_path / "faceit.sqlite3")
    db.attach_faceit(fp)
    db.conn.execute(
        "INSERT INTO map_instances (source_type, match_id, game_no, map_verified) "
        "VALUES ('faceit','M1',1,1)"
    )
    db.conn.commit()
    ctx = derive_code_context(db, fp, "ABC123")
    assert ctx.already_captured is True


def test_code_not_found(db: Database, tmp_path: Path) -> None:
    fp = _build_faceit(tmp_path / "faceit.sqlite3")
    with pytest.raises(CodeNotFound):
        derive_code_context(db, fp, "NOPE00")


def test_ambiguous_code(db: Database, tmp_path: Path) -> None:
    fp = _build_faceit(tmp_path / "faceit.sqlite3")
    con = sqlite3.connect(fp)
    con.execute("INSERT INTO games VALUES('M1',2,'map-kr','Hybrid','faction1','ABC123')")
    con.commit()
    con.close()
    with pytest.raises(AmbiguousCode):
        derive_code_context(db, fp, "ABC123")


def test_format_context_smoke(db: Database, tmp_path: Path) -> None:
    fp = _build_faceit(tmp_path / "faceit.sqlite3")
    out = format_context(derive_code_context(db, fp, "ABC123"))
    assert "Kings Row" in out and "Ramattra" in out and "Bravo" in out

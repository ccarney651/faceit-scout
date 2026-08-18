"""tools/build_capture_data.py — the codes feed the browser capture app reads.

The app renders ONE dropdown and filters codes by string equality on
``division`` (docs/capture/index.html: buildDivisions / the `c.division===dv`
filter). So once a second region ships, a bare tier label silently merges two
regions' codes under a single "Master". These tests pin the region-qualified
labels that prevent that.
"""
from __future__ import annotations

import importlib.util
import json
import sqlite3
import sys
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import pytest

TOOL = Path(__file__).resolve().parents[1] / "tools" / "build_capture_data.py"

# One role-locked lineup, the shape every real team-game has: 8303 of 8356 in the
# database are exactly 1 Tank / 2 Damage / 2 Support.
LINEUP = [("p1", "Tank"), ("p2d", "Damage"), ("p3d", "Damage"),
          ("p4s", "Support"), ("p5s", "Support")]


def _load_tool(monkeypatch: pytest.MonkeyPatch, db_path: Path, out_path: Path) -> Any:
    """Import build_capture_data with its paths pointed at the fixture.

    Both are read at import time, so the env must be set before loading and the
    module reloaded per test rather than cached in sys.modules.
    """
    monkeypatch.setenv("FACEIT_DB", str(db_path))
    monkeypatch.setenv("CAPTURE_OUT", str(out_path))
    spec = importlib.util.spec_from_file_location("build_capture_data_under_test", TOOL)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def _fixture_db(path: Path, wipe: str) -> None:
    """Two regions x one tier each, both with a post-wipe coded game."""
    con = sqlite3.connect(path)
    con.executescript(
        """
        CREATE TABLE championships(id TEXT PRIMARY KEY, name TEXT);
        CREATE TABLE teams(id TEXT PRIMARY KEY, name TEXT);
        CREATE TABLE maps(guid TEXT PRIMARY KEY, name TEXT, category TEXT);
        CREATE TABLE matches(id TEXT PRIMARY KEY, championship_id TEXT,
                             finished_at TEXT, faction1_team_id TEXT,
                             faction2_team_id TEXT);
        CREATE TABLE games(match_id TEXT, game_no INT, map_guid TEXT,
                           map_category TEXT, demo_code TEXT);
        CREATE TABLE players(id TEXT PRIMARY KEY, nickname TEXT, game_name TEXT);
        CREATE TABLE round_players(match_id TEXT, game_no INT, team_id TEXT,
                                   player_id TEXT, role TEXT);
        CREATE TABLE heroes(guid TEXT PRIMARY KEY, name TEXT, role TEXT);
        """
    )
    # The browser reads a slot's role off the hero recognised in it, so the feed
    # has to carry guid -> role; nothing else in the app knows a built-in hero's.
    con.execute("INSERT INTO heroes VALUES('0x02E000000000007A','DVa','Tank')")
    con.execute("INSERT INTO heroes VALUES('0x02E0000000000029','Tracer','Damage')")
    con.execute("INSERT INTO heroes VALUES('0x02E000000000013B','Ana','Support')")
    con.execute("INSERT INTO heroes VALUES('0x02E00000000000FF','Nameless',NULL)")
    con.execute("INSERT INTO maps VALUES('m1','Ilios','Control')")
    con.execute("INSERT INTO teams VALUES('t1','Alpha')")
    con.execute("INSERT INTO teams VALUES('t2','Bravo')")
    rows = [
        ("c-em", "S9 EMEA Master Central - Regular Season", "mt-em", "EMCODE"),
        ("c-ne", "S9 NA Expert Central - Regular Season", "mt-ne", "NECODE"),
        # No region in the name (a one-off cup): must be DROPPED, not mislabelled.
        ("c-cup", "Winter Master Invitational", "mt-cup", "CUPCODE"),
    ]
    for cid, cname, mid, code in rows:
        con.execute("INSERT INTO championships VALUES(?,?)", (cid, cname))
        con.execute("INSERT INTO matches VALUES(?,?,?,?,?)",
                    (mid, cid, f"{wipe}T20:00:00Z", "t1", "t2"))
        con.execute("INSERT INTO games VALUES(?,1,'m1','Control',?)", (mid, code))
        # A full role-locked five, because the browser's player assignment needs
        # an exact 1/2/2 cover to constrain against (engine/assign.js).
        for pid, role in LINEUP:
            con.execute("INSERT INTO round_players VALUES(?,1,'t1',?,?)", (mid, pid, role))
    for pid, _role in LINEUP:
        con.execute("INSERT INTO players VALUES(?,?,?)",
                    (pid, f"nick-{pid}", "GameName#1234" if pid == "p1" else f"Game{pid}"))
    con.commit()
    con.close()


def _build(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> dict[str, Any]:
    db, out = tmp_path / "faceit.sqlite3", tmp_path / "data.json"
    mod = _load_tool(monkeypatch, db, out)
    # One day AFTER the wipe, so every fixture game passes the post-wipe filter.
    after = date.fromisoformat(mod.CODE_WIPE_DATE) + timedelta(days=1)
    _fixture_db(db, after.isoformat())
    mod.main()
    return json.loads(out.read_text(encoding="utf-8"))


def test_both_regions_emit_qualified_division_labels(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    payload = _build(monkeypatch, tmp_path)
    by_code = {c["code"]: c["division"] for c in payload["codes"]}
    assert by_code == {"EMCODE": "EMEA Master", "NECODE": "NA Expert"}


def test_unregioned_championship_is_dropped_not_mislabelled(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A cup naming a tier but no region has no correct dropdown entry. Dropping
    it is honest; filing it under some default region is not."""
    payload = _build(monkeypatch, tmp_path)
    assert "CUPCODE" not in {c["code"] for c in payload["codes"]}


def test_divisions_list_is_region_major_and_matches_the_codes(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The dropdown is built from this list, so its order is the render order and
    every entry must be selectable (i.e. actually present on a code)."""
    payload = _build(monkeypatch, tmp_path)
    assert payload["divisions"] == ["EMEA Master", "NA Expert"]
    assert set(payload["divisions"]) == {c["division"] for c in payload["codes"]}
    assert payload["regions"] == ["EMEA", "NA"]


def test_region_of_matches_whole_words_only(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Same guard as faceit_sync.export._region_of and owdb.db.list_codes."""
    mod = _load_tool(monkeypatch, tmp_path / "x.sqlite3", tmp_path / "x.json")
    assert mod._region("S9 NA Master Central - Regular Season") == "NA"
    assert mod._region("S9 EMEA Master Central - Regular Season") == "EMEA"
    assert mod._region("S9 Open Nationals") is None
    assert mod._division("S9 Open Nationals") is None
    assert mod._division("S9 NA Expert Central - Regular Season") == "NA Expert"
    # A region with no tier is as unusable as a tier with no region.
    assert mod._division("S9 NA Central - Regular Season") is None


def test_rosters_are_keyed_by_match_for_included_codes_only(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The app looks rosters up by match_id off a selected code, so a roster for
    a dropped championship is dead weight the feed should not ship."""
    payload = _build(monkeypatch, tmp_path)
    assert set(payload["rosters"]) == {c["match_id"] for c in payload["codes"]}


def test_lineups_are_keyed_per_game_and_carry_roles(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The browser constrains player assignment by role, so the feed must carry it."""
    payload = _build(monkeypatch, tmp_path)
    keys = {f"{c['match_id']}:{c['game_no']}" for c in payload["codes"]}
    assert set(payload["lineups"]) == keys

    team = payload["lineups"]["mt-em:1"]["t1"]
    assert sorted(p["role"] for p in team["players"]) == [
        "Damage", "Damage", "Support", "Support", "Tank"]


def test_a_lineup_is_the_five_who_played_that_game_not_the_match_squad(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """This is the whole reason `lineups` exists beside `rosters`.

    27% of real match-teams field more than five players once substitutes are
    counted. assign.js needs an EXACT COVER of five over five slots — hand it six
    and the damage group has three candidates for two slots, the role constraint
    stops constraining, and a substitute who never played this game becomes a
    candidate for it.
    """
    db, out = tmp_path / "faceit.sqlite3", tmp_path / "data.json"
    mod = _load_tool(monkeypatch, db, out)
    after = date.fromisoformat(mod.CODE_WIPE_DATE) + timedelta(days=1)
    _fixture_db(db, after.isoformat())

    # Game 2 of the same match, with one damage player substituted out.
    con = sqlite3.connect(db)
    con.execute("INSERT INTO players VALUES('psub','subnick','SubGameName')")
    con.execute("INSERT INTO games VALUES('mt-em',2,'m1','Control','EMCODE2')")
    for pid, role in LINEUP:
        if pid == "p3d":
            continue
        con.execute("INSERT INTO round_players VALUES('mt-em',2,'t1',?,?)", (pid, role))
    con.execute("INSERT INTO round_players VALUES('mt-em',2,'t1','psub','Damage')")
    con.commit()
    con.close()

    mod.main()
    payload = json.loads(out.read_text(encoding="utf-8"))

    g1 = {p["id"] for p in payload["lineups"]["mt-em:1"]["t1"]["players"]}
    g2 = {p["id"] for p in payload["lineups"]["mt-em:2"]["t1"]["players"]}
    assert len(g1) == len(g2) == 5, "a lineup must be exactly the five who played"
    assert "p3d" in g1 and "p3d" not in g2, "the substituted player leaked into game 2"
    assert "psub" in g2 and "psub" not in g1, "the substitute leaked into game 1"

    # The per-match roster is the union, and is exactly what would break assign.js.
    assert len(payload["rosters"]["mt-em"]["t1"]["players"]) == 6


def test_hero_roles_are_shipped_for_the_slot_role_lookup(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """assign.js reads the slot's role off the recognised hero. The browser has no
    other source for a built-in hero's role — only CUSTOM_HEROES carried one."""
    payload = _build(monkeypatch, tmp_path)
    assert payload["hero_roles"]["0x02E000000000007A"] == "Tank"
    assert payload["hero_roles"]["0x02E0000000000029"] == "Damage"
    # A hero with no role is omitted rather than defaulted — a wrong role would
    # put a real player in the wrong candidate group.
    assert "0x02E00000000000FF" not in payload["hero_roles"]


def test_a_missing_faceit_role_is_null_not_invented(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """FACEIT returns a '-' sentinel when a game's stats never captured. Guessing
    a role there would put a real player in the wrong candidate group."""
    db, out = tmp_path / "faceit.sqlite3", tmp_path / "data.json"
    mod = _load_tool(monkeypatch, db, out)
    after = date.fromisoformat(mod.CODE_WIPE_DATE) + timedelta(days=1)
    _fixture_db(db, after.isoformat())

    con = sqlite3.connect(db)
    con.execute("UPDATE round_players SET role='-' WHERE match_id='mt-em' AND player_id='p1'")
    con.commit()
    con.close()

    mod.main()
    payload = json.loads(out.read_text(encoding="utf-8"))
    roles = {p["id"]: p["role"] for p in payload["lineups"]["mt-em:1"]["t1"]["players"]}
    assert roles["p1"] is None

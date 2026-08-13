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
                                   player_id TEXT);
        """
    )
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
        con.execute("INSERT INTO round_players VALUES(?,1,'t1','p1')", (mid,))
    con.execute("INSERT INTO players VALUES('p1','nick','GameName#1234')")
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


def test_team_rosters_cover_every_team_not_just_coded_matches(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Scrim opponent identification needs every team, not the coded few.

    `rosters` is keyed by match and only covers post-wipe coded games, which is
    right for attributing a capture. Identifying a scrim opponent matches ten
    HUD names against the whole league: on the real database that is 159 teams
    against about 8 reachable through `rosters`, so a per-match feed would leave
    almost every opponent unidentifiable.
    """
    db, out = tmp_path / "faceit.sqlite3", tmp_path / "data.json"
    mod = _load_tool(monkeypatch, db, out)
    after = date.fromisoformat(mod.CODE_WIPE_DATE) + timedelta(days=1)
    _fixture_db(db, after.isoformat())

    # A team whose only match predates the wipe and carries no code: invisible
    # to `rosters`, and exactly the kind of opponent a scrim runs into.
    con = sqlite3.connect(db)
    con.execute("INSERT INTO teams VALUES('t3','Charlie')")
    con.execute("INSERT INTO championships VALUES('c-old','S9 EMEA Master Central - Regular Season')")
    con.execute("INSERT INTO matches VALUES('mt-old','c-old','2020-01-01T20:00:00Z','t3','t1')")
    con.execute("INSERT INTO games VALUES('mt-old',1,'m1','Control',NULL)")
    con.execute("INSERT INTO round_players VALUES('mt-old',1,'t3','p2')")
    con.execute("INSERT INTO players VALUES('p2','oldnick','OldGameName')")
    con.commit(); con.close()

    mod.main()
    payload = json.loads(out.read_text(encoding="utf-8"))

    tr = payload["team_rosters"]
    assert "t3" in tr, "a team with no coded game is missing from team_rosters"
    assert tr["t3"]["name"] == "Charlie"
    assert [p["game_name"] for p in tr["t3"]["players"]] == ["OldGameName"]

    # And it is genuinely wider than the per-match feed it supplements.
    reachable_via_rosters = {tid for m in payload["rosters"].values() for tid in m}
    assert set(tr) > reachable_via_rosters, (
        "team_rosters is no wider than rosters - the whole point is the teams "
        "that have no live coded match"
    )


def test_team_rosters_accumulate_a_squad_across_matches(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Subs and stand-ins must accumulate, not be per-match.

    A season's substitutes are precisely the names that still identify a lineup
    when two players are on smurf accounts, so the roster has to be the union.
    """
    db, out = tmp_path / "faceit.sqlite3", tmp_path / "data.json"
    mod = _load_tool(monkeypatch, db, out)
    after = date.fromisoformat(mod.CODE_WIPE_DATE) + timedelta(days=1)
    _fixture_db(db, after.isoformat())

    con = sqlite3.connect(db)
    con.execute("INSERT INTO players VALUES('p9','subnick','SubPlayer')")
    # Same team t1, a different match, a player who appeared only there.
    con.execute("INSERT INTO round_players VALUES('mt-ne',1,'t1','p9')")
    con.commit(); con.close()

    mod.main()
    payload = json.loads(out.read_text(encoding="utf-8"))
    names = {p["game_name"] for p in payload["team_rosters"]["t1"]["players"]}
    assert {"GameName#1234", "SubPlayer"} <= names, (
        f"t1's roster did not accumulate across matches: {names}"
    )

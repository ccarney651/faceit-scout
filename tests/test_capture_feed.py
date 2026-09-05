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
    # Every region the site ships, whether or not this fixture has codes in it:
    # the app reads this to group the dropdown. Compared against the exporter's
    # tuple rather than a copy of it, so adding a region cannot leave a stale
    # literal here asserting the previous season's world.
    from faceit_sync.export import REGIONS
    assert payload["regions"] == list(REGIONS)


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
    con.execute("INSERT INTO round_players VALUES('mt-old',1,'t3','p2','Tank')")
    con.execute("INSERT INTO players VALUES('p2','oldnick','OldGameName')")
    con.commit()
    con.close()

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
    con.execute("INSERT INTO round_players VALUES('mt-ne',1,'t1','p9','Damage')")
    con.commit()
    con.close()

    mod.main()
    payload = json.loads(out.read_text(encoding="utf-8"))
    names = {p["game_name"] for p in payload["team_rosters"]["t1"]["players"]}
    assert {"GameName#1234", "SubPlayer"} <= names, (
        f"t1's roster did not accumulate across matches: {names}"
    )


def test_capture_feed_regions_match_the_exporter(
        monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """build_capture_data.py keeps its own REGIONS tuple. A region added to the
    site but not to the feed is a division missing from the capture app's
    dropdown, with nothing anywhere to say so."""
    from faceit_sync.export import REGIONS

    db = tmp_path / "feed.sqlite3"
    _fixture_db(db, "2026-07-28")
    mod = _load_tool(monkeypatch, db, tmp_path / "out.json")
    assert tuple(mod.REGIONS) == REGIONS


def test_capture_feed_tiers_match_the_exporter(
        monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Same drift, one tuple over: the feed's own TIERS builds the app's division
    list. A tier the site knows and the feed does not is a division nobody can
    pick a code from, with nothing anywhere to say so."""
    from faceit_sync.export import TIERS

    db = tmp_path / "feed.sqlite3"
    _fixture_db(db, "2026-07-28")
    mod = _load_tool(monkeypatch, db, tmp_path / "out.json")
    assert tuple(mod.TIERS) == TIERS


def test_team_rosters_cover_only_the_active_season(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A team that did not return for the new season is not a scrim opponent.

    Matching a scrim against last season's squad is not a near miss - it writes
    a team that no longer plays into a private scrim log. The pool is therefore
    the newest season that HAS data, which also stops it growing by a season
    every year.

    The season is compared numerically, not lexically: sorted as strings 's9'
    beats 's10', which would pin the pool to the season that just ended.
    """
    db, out = tmp_path / "faceit.sqlite3", tmp_path / "data.json"
    mod = _load_tool(monkeypatch, db, out)
    after = date.fromisoformat(mod.CODE_WIPE_DATE) + timedelta(days=1)
    _fixture_db(db, after.isoformat())

    # Season 10 arrives. Charlie plays; the S9-only teams never come back.
    con = sqlite3.connect(db)
    con.execute("INSERT INTO teams VALUES('t3','Charlie')")
    con.execute("INSERT INTO championships VALUES('c-s10',"
                "'S10 EMEA Master Central - Regular Season')")
    con.execute("INSERT INTO matches VALUES('mt-s10','c-s10',"
                "'2027-01-05T20:00:00Z','t3','t1')")
    con.execute("INSERT INTO round_players VALUES('mt-s10',1,'t3','p7','Tank')")
    con.execute("INSERT INTO players VALUES('p7','newnick','NewGameName')")
    con.commit()
    con.close()

    mod.main()
    payload = json.loads(out.read_text(encoding="utf-8"))

    tr = payload["team_rosters"]
    assert set(tr) == {"t3"}, (
        f"team_rosters should hold the active season's teams only, got {set(tr)}"
    )
    assert [p["game_name"] for p in tr["t3"]["players"]] == ["NewGameName"]


def test_seeding_next_season_does_not_empty_the_roster_pool(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A seeded season is not a played one, and the pool must not hand over yet.

    Season 10's championships and fixtures enter the database when its rooms are
    seeded - days before its first game. Choosing the pool off championship names
    alone flipped it to S10 at that moment and shipped ZERO teams, which is not a
    degraded scrim opponent list but no opponent identification at all, in the
    week when last season's squads are still the best guess available.
    """
    db, out = tmp_path / "faceit.sqlite3", tmp_path / "data.json"
    mod = _load_tool(monkeypatch, db, out)
    after = date.fromisoformat(mod.CODE_WIPE_DATE) + timedelta(days=1)
    _fixture_db(db, after.isoformat())

    # The next season is seeded: a championship and a fixture, nobody has played.
    con = sqlite3.connect(db)
    con.execute("INSERT INTO championships VALUES('c-s10',"
                "'S10 EMEA Master Central - Regular Season')")
    con.execute("INSERT INTO matches VALUES('mt-s10','c-s10',"
                "'2027-01-05T20:00:00Z','t1','t2')")
    con.commit()
    con.close()

    mod.main()
    tr = json.loads(out.read_text(encoding="utf-8"))["team_rosters"]
    assert tr, "seeding S10 emptied the pool - the season handover fired too early"
    assert set(tr) == {"t1"}, (
        f"the pool should still be the season that has actually played, got {set(tr)}"
    )


def test_a_sub_seen_only_last_season_is_dropped_but_their_team_survives(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Scoping is per player-row, not per team.

    A team that carries over keeps its entry; the stand-in who played for them
    last season and not this one is no longer one of their names.
    """
    db, out = tmp_path / "faceit.sqlite3", tmp_path / "data.json"
    mod = _load_tool(monkeypatch, db, out)
    after = date.fromisoformat(mod.CODE_WIPE_DATE) + timedelta(days=1)
    _fixture_db(db, after.isoformat())

    con = sqlite3.connect(db)
    # A stand-in who only ever appeared in the S9 fixture matches.
    con.execute("INSERT INTO players VALUES('p9','subnick','SubPlayer')")
    con.execute("INSERT INTO round_players VALUES('mt-ne',1,'t1','p9','Damage')")
    # Alpha carries over into S10 with its regular five.
    con.execute("INSERT INTO championships VALUES('c-s10',"
                "'S10 EMEA Master Central - Regular Season')")
    con.execute("INSERT INTO matches VALUES('mt-s10','c-s10',"
                "'2027-01-05T20:00:00Z','t1','t2')")
    for pid, role in LINEUP:
        con.execute("INSERT INTO round_players VALUES('mt-s10',1,'t1',?,?)", (pid, role))
    con.commit()
    con.close()

    mod.main()
    payload = json.loads(out.read_text(encoding="utf-8"))

    names = {p["game_name"] for p in payload["team_rosters"]["t1"]["players"]}
    assert "SubPlayer" not in names, (
        f"a stand-in from the previous season is still in the pool: {names}"
    )
    assert "GameName#1234" in names, "the carried-over five were dropped too"


def test_a_season_less_championship_is_left_out_of_team_rosters(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A row that cannot be dated can never age out.

    Keeping one-off cups would quietly rebuild the unbounded pool, one
    undateable championship at a time. Dropping mirrors _division(), which
    drops a region-less name rather than mislabelling it.
    """
    db, out = tmp_path / "faceit.sqlite3", tmp_path / "data.json"
    mod = _load_tool(monkeypatch, db, out)
    after = date.fromisoformat(mod.CODE_WIPE_DATE) + timedelta(days=1)
    _fixture_db(db, after.isoformat())

    con = sqlite3.connect(db)
    # Plays for Alpha in the Winter Invitational only, which names no season.
    con.execute("INSERT INTO players VALUES('p8','cupnick','CupOnly')")
    con.execute("INSERT INTO round_players VALUES('mt-cup',1,'t1','p8','Damage')")
    con.commit()
    con.close()

    mod.main()
    payload = json.loads(out.read_text(encoding="utf-8"))

    names = {p["game_name"] for p in payload["team_rosters"]["t1"]["players"]}
    assert "CupOnly" not in names, (
        f"an undateable championship's player is in the pool: {names}"
    )


def test_rosters_are_unscoped_when_no_championship_names_a_season(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """With nothing to scope by, an empty pool would identify nobody.

    The filter exists to drop STALE teams; a database that never names a season
    has no stale teams to drop, so it keeps them all rather than shipping a
    feed that silently identifies no opponent at all.
    """
    db, out = tmp_path / "faceit.sqlite3", tmp_path / "data.json"
    mod = _load_tool(monkeypatch, db, out)
    after = date.fromisoformat(mod.CODE_WIPE_DATE) + timedelta(days=1)
    _fixture_db(db, after.isoformat())

    con = sqlite3.connect(db)
    con.execute("UPDATE championships SET name = replace(name, 'S9 ', '')")
    con.commit()
    con.close()

    mod.main()
    payload = json.loads(out.read_text(encoding="utf-8"))

    assert payload["team_rosters"], (
        "no season anywhere emptied the pool - every scrim opponent would now "
        "be unidentifiable"
    )


def test_capture_feed_and_exporter_share_one_definition_of_the_season(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """One source, not two copies.

    The feed decides which rosters are live and the exporter decides which
    season the site renders. If those drift, the capture app matches scrims
    against a season the site is not showing. `REGIONS` is already a copy that
    needed a test to hold it in place; this one is shared outright, and this
    asserts it stays shared.
    """
    from faceit_sync import export
    from faceit_sync.models import newest_season, season_of

    assert export._season_of is season_of
    assert export._newest_season is newest_season

    db = tmp_path / "feed.sqlite3"
    _fixture_db(db, "2026-07-28")
    mod = _load_tool(monkeypatch, db, tmp_path / "out.json")
    assert mod.season_of is season_of
    assert mod.newest_season is newest_season


def test_team_roster_players_are_emitted_in_a_stable_order(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The feed is committed, so an unstable order diffs the file against itself.

    Player order carries no meaning to the app - opponent identification builds
    a set - but the season filter had to drop the GROUP BY that used to impose
    an order, and the whole 126 KB file churning on every CI build is noise that
    hides real changes.
    """
    db, out = tmp_path / "faceit.sqlite3", tmp_path / "data.json"
    mod = _load_tool(monkeypatch, db, out)
    after = date.fromisoformat(mod.CODE_WIPE_DATE) + timedelta(days=1)
    _fixture_db(db, after.isoformat())

    # Inserted in the opposite order to the one they must come out in, so the
    # database's natural row order cannot pass this by accident.
    con = sqlite3.connect(db)
    for pid in ("p0z", "p0a"):
        con.execute("INSERT INTO players VALUES(?,?,?)", (pid, pid, pid.upper()))
        con.execute("INSERT INTO round_players VALUES('mt-em',1,'t1',?,'Damage')", (pid,))
    con.commit()
    con.close()
    mod.main()

    players = json.loads(out.read_text(encoding="utf-8"))["team_rosters"]["t1"]["players"]
    ids = [p["id"] for p in players]
    assert ids == sorted(ids), f"team roster order is not stable: {ids}"

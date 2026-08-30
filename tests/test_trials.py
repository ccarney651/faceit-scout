"""The local trialist comparison tool (`faceit-sync trials`).

Design: specs/2026-08-30-trialist-comparison-design.md
"""

from __future__ import annotations

import io
import json
import re

import responses
from conftest import RESTART_DC_ID, make_client, register_match
from test_export import _payload

from faceit_sync.db import Database
from faceit_sync.export import build_dashboard_data, export_html
from faceit_sync.sync import SyncEngine
from faceit_sync.trials import (
    build_search_index,
    build_trials_page,
    write_trials_page,
)


def _ingest(db: Database) -> None:
    register_match(responses, RESTART_DC_ID, prefix="restart_dc", democracy=True)
    SyncEngine(make_client()[0], db).ingest_match(RESTART_DC_ID, force_refresh=True)


@responses.activate
def test_build_dashboard_data_returns_what_export_html_inlines(db: Database) -> None:
    """The anti-drift guard. The trials page and the site must build their payload
    through one code path, so extracting the builder has to be behaviour-free:
    what it returns is byte-for-byte what the dashboard ships."""
    _ingest(db)
    buf = io.StringIO()
    export_html(db, buf)
    inlined = _payload(buf)

    built = json.loads(json.dumps(build_dashboard_data(db)))

    # built_at is the wall clock at call time; the two calls are seconds apart.
    assert inlined.pop("built_at")
    assert built.pop("built_at")
    assert built == inlined


# --- search index ----------------------------------------------------------
# The index is a pure function of the payload, so these build a minimal payload
# by hand rather than ingesting: the shape under test is small and explicit.

def _p(nick: str, game: str, role: str | None, games: int, last: str) -> dict:
    return {"nick": nick, "game_name": game, "role": role,
            "games": games, "last_seen": last, "elo": None, "stats": None}


def _div(name: str, team: str, roster: list[dict]) -> dict:
    """A division whose per-game rosters agree with its team roster: one game per
    map the roster claims. `maps` is counted from the games (see
    test_maps_counts_playoff_games_too), so a roster with no games behind it
    would count zero."""
    matches = []
    for p in roster:
        matches.append({
            "id": f"m-{p['nick']}", "finished_at": p["last_seen"],
            "games": [{"map": "Ilios", "map_category": "Control", "game_no": i,
                       "winner_team": team,
                       "rosters": [{"team": team,
                                    "players": [{"nick": p["nick"],
                                                 "role": p["role"]}]}]}
                      for i in range(p["games"])],
        })
    return {"summary": {"championship": name},
            "teams": [{"name": team, "roster": roster}],
            "matches": matches}


def test_search_index_carries_both_the_faceit_and_the_in_game_name() -> None:
    """The whole point of the search bar: a shortlist is written in in-game
    names, FACEIT knows nicknames, and they differ. Both must be searchable."""
    data = {"divisions": {"c1": _div(
        "S9 EMEA Expert Central - Regular Season", "FXHND",
        [_p("Pixels99", "pixels", "Support", 64, "2026-08-10T19:46:51Z")])}}

    entry, = build_search_index(data)

    assert entry["nick"] == "Pixels99"
    assert entry["game"] == "pixels"
    assert entry["role"] == "Support"
    assert entry["region"] == "EMEA"
    assert entry["tier"] == "Expert"
    assert entry["team"] == "FXHND"
    assert entry["maps"] == 64


def test_search_index_collapses_one_player_across_divisions() -> None:
    """A player who moved division mid-season is ONE search result: maps summed,
    identity taken from wherever they most recently played."""
    data = {"divisions": {
        "c1": _div("S9 EMEA Expert Central - Regular Season", "Harmony",
                   [_p("mover", "Mover", "Damage", 55, "2026-07-20T00:00:00Z")]),
        "c2": _div("S9 EMEA Master Central - Regular Season", "Redline",
                   [_p("mover", "Mover", "Support", 12, "2026-08-10T00:00:00Z")]),
    }}

    entry, = build_search_index(data)

    assert entry["maps"] == 67
    assert entry["team"] == "Redline"
    assert entry["tier"] == "Master"
    assert entry["last"] == "2026-08-10T00:00:00Z"


def test_search_index_spans_every_region_in_the_payload() -> None:
    """Candidates may come from anywhere; narrowing to one region would hide
    them. The index carries all regions at once and labels each."""
    data = {"divisions": {
        "c1": _div("S9 EMEA Expert Central - Regular Season", "Harmony",
                   [_p("euro", "Euro", "Damage", 10, "2026-07-20T00:00:00Z")]),
        "c2": _div("S9 NA Master Central - Regular Season", "Bears",
                   [_p("yank", "Yank", "Tank", 20, "2026-07-21T00:00:00Z")]),
    }}

    regions = {e["nick"]: e["region"] for e in build_search_index(data)}

    assert regions == {"euro": "EMEA", "yank": "NA"}


# --- role bucketing --------------------------------------------------------
# Per-game roles ride on every roster entry (export.py:457), so the real split is
# computable and the lossy dominant-role rollup on teams[].roster[] is not used.

def _game(team: str, players: list[tuple[str, str | None]], no: int = 1) -> dict:
    return {"map": "Ilios", "map_category": "Control", "game_no": no,
            "winner_team": team,
            "rosters": [{"team": team,
                         "players": [{"nick": n, "role": r} for n, r in players]}]}


def _div_with_games(name: str, games: list[dict], *, playoffs: list[dict] | None = None) -> dict:
    d = _div(name, "Harmony", [])
    d["matches"] = [{"id": "m1", "games": games}]
    if playoffs is not None:
        d["playoffs"] = [{"id": "p1", "games": playoffs}]
    return d


def _tables_for(nick: str, games: list[dict], **kw) -> list[str]:
    data = {"divisions": {"c1": _div_with_games(
        "S9 EMEA Expert Central - Regular Season", games, **kw)}}
    entry, = [e for e in build_search_index(data) if e["nick"] == nick]
    return entry["tables"]


def test_single_role_player_lands_in_exactly_one_table() -> None:
    assert _tables_for("solo", [_game("Harmony", [("solo", "Damage")], no=i)
                                for i in range(10)]) == ["Damage"]


def test_a_second_role_on_a_tenth_of_maps_adds_a_second_table() -> None:
    """The Warglabidoo case: 60 maps of Damage next to 7 of Tank is real flex,
    and a trial is exactly when you want to know about it."""
    games = [_game("Harmony", [("flex", "Damage")], no=i) for i in range(9)]
    games.append(_game("Harmony", [("flex", "Tank")], no=9))

    assert _tables_for("flex", games) == ["Damage", "Tank"]


def test_a_second_role_below_a_tenth_of_maps_does_not() -> None:
    """One stand-in game is not a hero pool. Without a floor every DPS who
    covered a tank once turns up in the tank table."""
    games = [_game("Harmony", [("dabbler", "Damage")], no=i) for i in range(19)]
    games.append(_game("Harmony", [("dabbler", "Tank")], no=19))

    assert _tables_for("dabbler", games) == ["Damage"]


def test_a_role_played_only_in_the_playoffs_still_counts() -> None:
    """Team-facing reads that stop at the group stage are a bug this repo has
    already shipped once. Playoff games are league games."""
    regular = [_game("Harmony", [("late", "Damage")], no=i) for i in range(9)]
    post = [_game("Harmony", [("late", "Tank")], no=0)]

    assert _tables_for("late", regular, playoffs=post) == ["Damage", "Tank"]


def test_a_player_faceit_recorded_no_role_for_lands_in_unassigned() -> None:
    """63 of 44150 game rows carry no role. Dropping them would silently lose a
    pooled player; an Unassigned table keeps them visible."""
    assert _tables_for("ghost", [_game("Harmony", [("ghost", None)], no=i)
                                 for i in range(5)]) == ["Unassigned"]


def test_maps_counts_playoff_games_too() -> None:
    """teams[].roster[] is rolled up per championship and playoffs are their own
    championship, so the roster's `games` silently stops at the group stage.
    Measured against live data: Warglabidoo's roster says 55 maps, his actual
    season is 67. The search result must not disagree with the table beside it."""
    data = {"divisions": {"c1": {
        "summary": {"championship": "S9 EMEA Expert Central - Regular Season"},
        "teams": [{"name": "Harmony", "roster": [
            {"nick": "warg", "game_name": "Warg", "role": "Damage",
             "games": 2, "last_seen": "2026-07-20T00:00:00Z", "elo": 2400}]}],
        "matches": [{"id": "m1", "finished_at": "2026-07-20T00:00:00Z",
                     "games": [_game("Harmony", [("warg", "Damage")], no=0),
                               _game("Harmony", [("warg", "Damage")], no=1)]}],
        "playoffs": [{"id": "p1", "finished_at": "2026-08-10T00:00:00Z",
                      "games": [_game("Harmony", [("warg", "Damage")], no=0)]}],
    }}}

    entry, = build_search_index(data)

    assert entry["maps"] == 3
    assert entry["last"] == "2026-08-10T00:00:00Z"
    assert entry["game"] == "Warg"      # in-game name still comes from the roster
    assert entry["elo"] == 2400


# --- the page --------------------------------------------------------------

@responses.activate
def test_trials_page_is_self_contained(db: Database) -> None:
    """It is opened from disk with no server, so every asset must be inlined."""
    _ingest(db)

    page = build_trials_page(build_dashboard_data(db))

    assert page.startswith("<!doctype html>")
    assert "<script src" not in page
    assert 'src="http' not in page and "src='http" not in page
    assert "url(http" not in page and "@import" not in page


@responses.activate
def test_trials_page_javascript_is_syntactically_valid(db: Database, tmp_path) -> None:
    """The page renders its whole body in JS, so ONE syntax error yields a
    completely blank page that no bracket check catches. Run the real parser."""
    import re
    import shutil
    import subprocess

    import pytest

    node = shutil.which("node")
    if not node:
        pytest.skip("node not available to parse the trials JS")

    _ingest(db)
    page = build_trials_page(build_dashboard_data(db))

    blocks = re.findall(r"<script>(.*?)</script>", page, re.S)
    assert blocks, "no <script> block found in the trials page"
    for i, block in enumerate(blocks):
        script = tmp_path / f"trials{i}.js"
        script.write_text(block, encoding="utf-8")
        proc = subprocess.run([node, "--check", str(script)],
                              capture_output=True, text=True)
        assert proc.returncode == 0, f"trials JS block {i} is invalid:\n{proc.stderr}"


@responses.activate
def test_trials_page_embeds_the_search_index(db: Database) -> None:
    """Search runs client-side against an inlined index, so it has to be there."""
    _ingest(db)
    data = build_dashboard_data(db)
    index = build_search_index(data)
    assert index, "fixture produced no players to index"

    page = build_trials_page(data)

    blob = re.search(r"var __TRIALS_INDEX__=(\[.*?\]);\n", page, re.S)
    assert blob is not None, "no inlined search index in the page"
    embedded = json.loads(blob.group(1).replace("\\u003c", "<"))
    assert [e["nick"] for e in embedded] == [e["nick"] for e in index]
    assert all("game" in e and "tables" in e for e in embedded)


@responses.activate
def test_write_trials_page_writes_the_file(db: Database, tmp_path) -> None:
    _ingest(db)
    out = tmp_path / "trials.html"

    count = write_trials_page(db, str(out))

    assert count == 1                       # divisions with data
    assert out.read_text(encoding="utf-8").startswith("<!doctype html>")


def test_write_trials_page_reports_nothing_to_build(db: Database, tmp_path) -> None:
    """An empty DB writes no file rather than a page with no players in it."""
    out = tmp_path / "trials.html"

    assert write_trials_page(db, str(out)) == 0
    assert not out.exists()


def test_a_player_name_cannot_break_out_of_the_script_block() -> None:
    """Nicknames are player-chosen text inlined into a <script>. Escaping every
    `<` as \\u003c closes both the `</script>` and the `<!--` breakout; JSON.parse
    decodes it back, so the round trip is lossless."""
    hostile = "</script><script>alert(1)</script>"
    data = {"divisions": {"c1": _div(
        "S9 EMEA Expert Central - Regular Season", hostile,
        [_p(hostile, "x", "Damage", 1, "2026-07-20T00:00:00Z")])}}

    page = build_trials_page(data)

    # Exactly the closers the shell itself opens - the payload contributes none.
    assert page.count("</script>") == page.count("<script>")
    assert "\\u003c/script>" in page


# --- the CLI ---------------------------------------------------------------

@responses.activate
def test_cli_trials_writes_the_page(db: Database, tmp_path, capsys) -> None:
    from faceit_sync.cli import main

    _ingest(db)
    out = tmp_path / "t.html"

    code = main(["--db", db.path, "trials", "--out", str(out)])

    assert code == 0
    assert out.read_text(encoding="utf-8").startswith("<!doctype html>")


def test_cli_trials_fails_loudly_on_an_empty_database(db: Database, tmp_path) -> None:
    """Exit non-zero rather than leaving the operator with a page that silently
    has nobody in it."""
    from faceit_sync.cli import main

    out = tmp_path / "t.html"

    assert main(["--db", db.path, "trials", "--out", str(out)]) == 1
    assert not out.exists()

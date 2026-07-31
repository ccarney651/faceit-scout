"""Behavioural tests for the dashboard's pure decision helpers.

The dashboard is one big JS template, so its *presentation* is only smoke-tested
(``node --check`` over the generated script). The decisions that can mislead a
coach — how a capture sample is dated, which maps get recommended as targets,
what a zero-denominator coverage row says — live in pure functions declared
ahead of ``bootApp`` precisely so they can be executed here for real.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess

import pytest

from faceit_sync._dashboard import HTML_TEMPLATE


def _pure_js() -> str:
    """Everything in the dashboard script above bootApp: no DOM, no globals."""
    m = re.search(r"<script>(.*)</script>", HTML_TEMPLATE, re.S)
    assert m, "no <script> block in the dashboard template"
    head, sep, _ = m.group(1).partition("function bootApp(")
    assert sep, "bootApp not found — the pure/impure split moved"
    return head


def _run(body: str, tmp_path) -> object:
    """Run `body` (a JS function body returning a value) against those helpers."""
    node = shutil.which("node")
    if not node:
        pytest.skip("node not available to run the dashboard helpers")
    src = tmp_path / "pure.js"
    src.write_text(
        _pure_js() + "\nconsole.log(JSON.stringify((()=>{" + body + "})()));",
        encoding="utf-8",
    )
    proc = subprocess.run([node, str(src)], capture_output=True, text=True)
    assert proc.returncode == 0, f"node failed:\n{proc.stderr}"
    return json.loads(proc.stdout)


# --- capture sample dating -------------------------------------------------
# A replay-code wipe is a patch. Labelling pre-patch comps "captures since
# <wipe date>" claims a freshness the sample does not have, in the one direction
# that misleads a coach into trusting stale comps.

def test_capture_sample_reports_its_real_date_range(tmp_path) -> None:
    got = _run("return capSample(['2026-07-15','2026-07-27','2026-07-20'],"
               "'2026-07-28');", tmp_path)
    assert got["from"] == "2026-07-15"
    assert got["to"] == "2026-07-27"
    assert got["n"] == 3


def test_capture_sample_flags_a_wholly_pre_patch_sample(tmp_path) -> None:
    got = _run("return capSample(['2026-07-15','2026-07-27'],'2026-07-28');",
               tmp_path)
    assert got["stale"] is True


def test_capture_sample_is_not_stale_once_it_includes_post_patch_games(tmp_path) -> None:
    got = _run("return capSample(['2026-07-27','2026-07-29'],'2026-07-28');",
               tmp_path)
    assert got["stale"] is False


def test_capture_label_states_the_range_and_the_patch_caveat(tmp_path) -> None:
    label = _run("return capLabelText(capSample(['2026-07-15','2026-07-27'],"
                 "'2026-07-28'),'2026-07-28');", tmp_path)
    assert "2026-07-15" in label and "2026-07-27" in label
    # It must say the sample predates the patch, not that it postdates it.
    assert "before" in label.lower()
    assert "since 2026-07-28" not in label


def test_capture_label_is_empty_without_a_sample(tmp_path) -> None:
    assert _run("return capLabelText(capSample([],'2026-07-28'),'2026-07-28');",
                tmp_path) == ""


# --- which maps to target --------------------------------------------------
# "Their worst" must never surface maps they win on: an undefeated team has no
# weak map, and naming their 100% maps as targets is worse than saying nothing.

_DOMINANT = "{'Oasis':{games:8,wins:8},'Runasapi':{games:7,wins:7}}"
_MIXED = ("{'Oasis':{games:8,wins:7},'Runasapi':{games:6,wins:1},"
          "'Ilios':{games:4,wins:2},'Solo':{games:1,wins:0}}")


def test_no_target_maps_for_a_team_that_wins_everywhere(tmp_path) -> None:
    assert _run(f"return worstMaps({_DOMINANT}).rows;", tmp_path) == []


def test_target_maps_are_the_ones_below_their_own_baseline(tmp_path) -> None:
    got = _run(f"return worstMaps({_MIXED});", tmp_path)
    maps = [r["m"] for r in got["rows"]]
    assert maps[0] == "Runasapi", f"weakest map should lead, got {maps}"
    assert "Oasis" not in maps, "a map they win above baseline is not a target"
    assert 0 <= got["baseline"] <= 100


def test_single_game_maps_are_too_thin_to_target(tmp_path) -> None:
    maps = [r["m"] for r in _run(f"return worstMaps({_MIXED});", tmp_path)["rows"]]
    assert "Solo" not in maps


# --- player ranking --------------------------------------------------------
# Rankings run off FACEIT's own per-game stats, which exist for every player in
# every division, so these must work with no capture data anywhere.

_ROSTER = """[
  {nick:'ace',   team:'A', role:'Tank',    elo:2100, stats:{games:20,kd:1.4,dmg:6000}},
  {nick:'mid',   team:'B', role:'Tank',    elo:1900, stats:{games:18,kd:1.1,dmg:5000}},
  {nick:'cameo', team:'C', role:'Tank',    elo:2500, stats:{games:2, kd:9.9,dmg:9000}},
  {nick:'dps',   team:'A', role:'Damage',  elo:2000, stats:{games:15,kd:1.3,dmg:8000}},
  {nick:'nostat',team:'D', role:'Tank',    elo:null, stats:null}
]"""


def test_ranking_ignores_players_below_the_sample_floor(tmp_path) -> None:
    got = _run(f"return rankPlayers({_ROSTER},{{key:'kd'}}).map(p=>p.nick);", tmp_path)
    assert "cameo" not in got, "a 2-map cameo must not top a rate-based table"
    assert got[0] == "ace"


def test_ranking_never_puts_a_player_without_the_stat_above_one_with_it(tmp_path) -> None:
    got = _run(f"return rankPlayers({_ROSTER},{{key:'kd',minGames:0}}).map(p=>p.nick);",
               tmp_path)
    assert got[-1] == "nostat"


def test_ranking_filters_by_role(tmp_path) -> None:
    got = _run(f"return rankPlayers({_ROSTER},{{key:'elo',role:'Damage'}})"
               ".map(p=>p.nick);", tmp_path)
    assert got == ["dps"]


def test_counts_are_ranked_without_a_rate_floor(tmp_path) -> None:
    """Maps played is a count, not a rate: a 2-map player belongs in that table,
    they just sit at the bottom of it."""
    got = _run(f"return rankPlayers({_ROSTER}.map(p=>({{...p,maps:p.stats?p.stats.games:0}}))"
               ",{key:'maps'}).map(p=>p.nick);", tmp_path)
    assert got[0] == "ace"
    assert "cameo" in got


def test_elo_ranking_keeps_players_who_have_no_stat_sample(tmp_path) -> None:
    """Elo comes off the match feed even when the stat rows were zeroed."""
    got = _run("return rankPlayers([{nick:'x',elo:1500,stats:null}],{key:'elo'})"
               ".map(p=>p.nick);", tmp_path)
    assert got == ["x"]


# --- hero win rates --------------------------------------------------------
# Derived from captured comps joined to the match result. Ban counts show what
# the league RESPECTS; this shows what actually wins, on the same sample.

_PG = """{
  'm1:1': {'Won':{'Ruins':['Mauga','Kiriko'],'Well':['Mauga','Juno']},
           'Lost':{'Ruins':['Sigma','Kiriko'],'Well':['Sigma','Kiriko']}},
  'm1:2': {'Won':{'Circuit Royal':['Mauga','Juno']},
           'Lost':{'Circuit Royal':['Sigma','Kiriko']}},
  'm2:1': {'Won':{'Ilios':['Mauga']}, 'Lost':{'Ilios':['Sigma']}}
}"""
_WIN = "{'m1:1':'Won','m1:2':'Won','m2:1':'Won'}"


def test_hero_win_rate_splits_winners_from_losers(tmp_path) -> None:
    got = {r["hero"]: r for r in
           _run(f"return heroWinRates({_PG},{_WIN},{{minMaps:1}});", tmp_path)}
    assert got["Mauga"]["wr"] == 100 and got["Mauga"]["maps"] == 3
    assert got["Sigma"]["wr"] == 0 and got["Sigma"]["maps"] == 3


def test_a_hero_on_several_sub_maps_counts_once_per_map(tmp_path) -> None:
    """Control maps carry two sub-map comps; the unit of record is the map."""
    got = {r["hero"]: r for r in
           _run(f"return heroWinRates({_PG},{_WIN},{{minMaps:1}});", tmp_path)}
    assert got["Juno"]["maps"] == 2, "Juno played m1:1 (one sub-map) and m1:2"
    # Kiriko: winner's side of m1:1 (both sub-maps = one map) plus the loser's
    # side of m1:1 and m1:2 = 3 maps, 1 won.
    assert got["Kiriko"]["maps"] == 3 and got["Kiriko"]["wins"] == 1


def test_thin_heroes_are_left_out(tmp_path) -> None:
    heroes = [r["hero"] for r in
              _run(f"return heroWinRates({_PG},{_WIN},{{minMaps:3}});", tmp_path)]
    assert "Juno" not in heroes, "Juno has 2 maps and must not clear a 3-map floor"
    assert sorted(heroes) == ["Kiriko", "Mauga", "Sigma"]


def test_games_with_no_known_winner_are_skipped(tmp_path) -> None:
    assert _run(f"return heroWinRates({_PG},{{}},{{minMaps:1}});", tmp_path) == []


# --- scouting coverage wording --------------------------------------------

def test_zero_scoutable_games_does_not_read_as_fully_scouted(tmp_path) -> None:
    got = _run("return coverageState(3,0,0,'2026-07-28');", tmp_path)
    assert got["kind"] == "wiped"
    assert "fully scouted" not in got["text"].lower()
    assert "2026-07-28" in got["text"]


def test_every_scoutable_game_captured_reads_as_fully_scouted(tmp_path) -> None:
    got = _run("return coverageState(20,14,14,'2026-07-28');", tmp_path)
    assert got["kind"] == "full"
    assert "fully scouted" in got["text"].lower()


def test_partial_coverage_is_neither(tmp_path) -> None:
    assert _run("return coverageState(20,14,9,'2026-07-28');",
                tmp_path)["kind"] == "partial"


# --- remembered division ---------------------------------------------------
# Two regions ship, so opening on VIEWS[0] every time makes NA visitors re-pick
# their region on every visit. The stored id is a hint, never trusted blindly:
# divisions change between seasons and the page renders its whole body off the
# active view, so an unknown id must degrade to the first view.

VIEWS_JS = ("[{id:'em',region:'EMEA'},{id:'ee',region:'EMEA'},"
            "{id:'nm',region:'NA'}]")


def test_remembered_division_is_reopened(tmp_path) -> None:
    assert _run(f"return pickDivision('nm',{VIEWS_JS});", tmp_path) == "nm"


def test_unknown_stored_division_falls_back_to_the_first_view(tmp_path) -> None:
    """A division that no longer exists (last season's, or a region dropped from
    the build) must not leave the active view dangling — that renders nothing."""
    assert _run(f"return pickDivision('s8-emea-open',{VIEWS_JS});",
                tmp_path) == "em"


def test_no_stored_division_opens_the_first_view(tmp_path) -> None:
    """First visit: localStorage returns null, and on file:// origins the read
    throws and is caught as null."""
    assert _run(f"return pickDivision(null,{VIEWS_JS});", tmp_path) == "em"


def test_pick_division_survives_an_empty_view_list(tmp_path) -> None:
    """An export with no divisions is already an error upstream; it must still
    not throw here, because a throw during boot yields a blank page."""
    assert _run("return pickDivision('em',[]);", tmp_path) is None


# --- Matches tab default mode --------------------------------------------
# Landing a visitor on an empty "Playoffs" panel is a worse first screen than
# landing them on the (populated) regular-season list, so the toggle should
# only default to Playoffs once real playoff matches exist.

def test_default_matches_mode_is_played_when_no_playoff_matches(tmp_path) -> None:
    got = _run("return defaultMatchesMode([]);", tmp_path)
    assert got == "played"


def test_default_matches_mode_is_playoffs_once_any_playoff_match_exists(tmp_path) -> None:
    got = _run(
        "return defaultMatchesMode([{status:'SCHEDULED'}]);", tmp_path
    )
    assert got == "playoffs"


def test_default_matches_mode_is_playoffs_when_playoffs_are_finished(tmp_path) -> None:
    got = _run(
        "return defaultMatchesMode([{status:'FINISHED'}]);", tmp_path
    )
    assert got == "playoffs"

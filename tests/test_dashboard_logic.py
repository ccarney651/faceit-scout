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
    proc = subprocess.run([node, str(src)], capture_output=True, text=True,
                          encoding="utf-8")
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


# --- playoffs bracket: column placement ------------------------------------
# FACEIT double-elim playoff matches carry `group` (bracket leg: 1 = upper,
# 2 = lower) and `round` (stage within it). The bracket columns are upper
# rounds (4/2/1), lower rounds (2/2/1/1), then the grand final — so the column
# must come from BOTH fields, or every upper-bracket round collapses into one.

def test_playoff_stage_key_upper_rounds_map_to_their_columns(tmp_path) -> None:
    # 8-team Master bracket: ubRounds=3, lbRounds=4.
    got = _run("return [" +
               "playoffStageKey({group:1,round:1},3,4)," +
               "playoffStageKey({group:1,round:2},3,4)," +
               "playoffStageKey({group:1,round:3},3,4)];", tmp_path)
    assert got == [0, 1, 2]


def test_playoff_stage_key_lower_rounds_sit_after_the_upper_bracket(tmp_path) -> None:
    got = _run("return [" +
               "playoffStageKey({group:2,round:1},3,4)," +
               "playoffStageKey({group:2,round:4},3,4)];", tmp_path)
    assert got == [3, 6]


def test_playoff_stage_key_unknown_leg_falls_to_the_grand_final_column(tmp_path) -> None:
    got = _run("return [" +
               "playoffStageKey({group:3,round:1},3,4)," +
               "playoffStageKey({group:null,round:2},3,4)];", tmp_path)
    assert got == [7, 7]   # 3 upper + 4 lower columns


def test_playoff_stage_key_round_one_is_the_first_column_of_its_leg(tmp_path) -> None:
    assert _run("return playoffStageKey({group:2,round:1},2,3);", tmp_path) == 2


def test_playoff_stage_key_a_round_beyond_a_leg_is_the_grand_final(tmp_path) -> None:
    # FACEIT numbers the grand final inside group 1/2 on real brackets: a round
    # past the leg's configured span must land in the GF column, not a wrong stage.
    got = _run("return [" +
               "playoffStageKey({group:1,round:4},3,4)," +   # upper bracket has 3 rounds
               "playoffStageKey({group:2,round:5},3,4)," +   # lower bracket has 4 rounds
               "playoffStageKey({group:1,round:3},3,4)];", tmp_path)
    assert got == [7, 7, 2]   # both over-spans -> GF; round 3 stays the upper final


def test_playoff_stage_key_gf_clamp_scales_to_the_bracket_size(tmp_path) -> None:
    # 16-team Expert bracket: ubRounds=4, lbRounds=6 -> GF column 10.
    got = _run("return [" +
               "playoffStageKey({group:1,round:5},4,6)," +
               "playoffStageKey({group:2,round:7},4,6)," +
               "playoffStageKey({group:2,round:6},4,6)];", tmp_path)
    assert got == [10, 10, 9]   # over-span -> GF; LB round 6 is the last LB column


# --- click-to-codes: code lookup + resolution -----------------------------
# codeLookup/codesFor are pure data transforms (no DOM, no esc/el/rcChip), so
# they're declared above bootApp and directly testable here.

_ONE_MATCH = ("[{id:'m1',f1:'Alpha',f2:'Bravo',finished_at:'2026-07-20',"
              "games:[{game_no:1,map:'Ilios',map_category:'Control',"
              "demo_code:'ABC123',winner_faction:'faction1'},"
              "{game_no:2,map:'Circuit Royal',map_category:'Escort',"
              "demo_code:null,winner_faction:'faction2'}]}]")


def test_code_lookup_indexes_by_match_and_game(tmp_path) -> None:
    got = _run(f"return [...codeLookup({_ONE_MATCH},'Alpha').entries()]"
               ".map(([k])=>k);", tmp_path)
    assert got == ["m1:1"]   # game 2 has no demo_code -> excluded


def test_code_lookup_carries_opponent_and_result_for_the_given_team(tmp_path) -> None:
    got = _run(f"return codeLookup({_ONE_MATCH},'Alpha').get('m1:1');", tmp_path)
    assert got["opp"] == "Bravo" and got["won"] is True and got["code"] == "ABC123"
    assert got["map"] == "Ilios"


def test_code_lookup_flips_opponent_for_the_other_team(tmp_path) -> None:
    got = _run(f"return codeLookup({_ONE_MATCH},'Bravo').get('m1:1');", tmp_path)
    assert got["opp"] == "Alpha" and got["won"] is False


_LOOKUP = ("codeLookup(" + _ONE_MATCH + ",'Alpha')")


def test_codes_for_resolves_and_sorts_newest_first(tmp_path) -> None:
    two = ("[{id:'m2',f1:'Alpha',f2:'Charlie',finished_at:'2026-07-25',"
           "games:[{game_no:1,map:'Oasis',map_category:'Control',"
           "demo_code:'ZZZ999',winner_faction:'faction1'}]}]")
    got = _run(
        f"const lk=codeLookup([...{_ONE_MATCH},...{two}],'Alpha');"
        "return codesFor(['m1:1','m2:1'], lk).map(r=>r.code);", tmp_path)
    assert got == ["ZZZ999", "ABC123"]   # 07-25 before 07-20


def test_codes_for_silently_drops_an_unresolvable_key(tmp_path) -> None:
    got = _run(f"return codesFor(['m1:1','nope:9'], {_LOOKUP}).map(r=>r.code);", tmp_path)
    assert got == ["ABC123"]


def test_code_lookup_marks_a_pre_wipe_game_as_dead(tmp_path) -> None:
    got = _run(f"return codeLookup({_ONE_MATCH},'Alpha','2026-07-28').get('m1:1').dead;", tmp_path)
    assert got is True   # game finished 2026-07-20, wipe was 2026-07-28


def test_code_lookup_does_not_mark_a_post_wipe_game_as_dead(tmp_path) -> None:
    got = _run(f"return codeLookup({_ONE_MATCH},'Alpha','2026-07-15').get('m1:1').dead;", tmp_path)
    assert got is False   # game finished 2026-07-20, wipe was 2026-07-15


def test_code_lookup_without_a_wipe_date_marks_nothing_dead(tmp_path) -> None:
    got = _run(f"return codeLookup({_ONE_MATCH},'Alpha').get('m1:1').dead;", tmp_path)
    assert got is False


# --- match detail page: pure helpers ---------------------------------------
# divisionOfMatch/mapPipClass/scoutedCount are pure data transforms (no DOM,
# no esc/el/CAPTURED), so they're declared above bootApp and directly
# testable here, same discipline as codeLookup/codesFor.

_DIVS = "{a:{matches:[{id:'m1'}]}, b:{matches:[{id:'m2'},{id:'m3'}]}}"


def test_division_of_match_finds_the_owning_division(tmp_path) -> None:
    assert _run(f"return divisionOfMatch({_DIVS},'m2');", tmp_path) == "b"


def test_division_of_match_returns_null_for_an_unknown_id(tmp_path) -> None:
    assert _run(f"return divisionOfMatch({_DIVS},'nope');", tmp_path) is None


def test_map_pip_class_is_f1win_when_faction1_won(tmp_path) -> None:
    got = _run("return mapPipClass({winner_faction:'faction1'});", tmp_path)
    assert got == "f1win"


def test_map_pip_class_is_f2win_when_faction2_won(tmp_path) -> None:
    got = _run("return mapPipClass({winner_faction:'faction2'});", tmp_path)
    assert got == "f2win"


def test_map_pip_class_is_empty_with_no_winner(tmp_path) -> None:
    got = _run("return mapPipClass({winner_faction:null});", tmp_path)
    assert got == ""


_SCOUT_MATCH = ("{id:'m1',games:[{game_no:1,map:'Ilios'},{game_no:2,map:'Oasis'},"
                "{game_no:3,map:null}]}")   # game 3: not played (series ended 2-0)


def test_scouted_count_only_counts_played_maps(tmp_path) -> None:
    got = _run(f"return scoutedCount({_SCOUT_MATCH}, new Set());", tmp_path)
    assert got == {"done": 0, "total": 2}


def test_scouted_count_counts_captured_games(tmp_path) -> None:
    got = _run(
        f"return scoutedCount({_SCOUT_MATCH}, new Set(['m1:1']));", tmp_path
    )
    assert got == {"done": 1, "total": 2}


# --- capture queue: league-wide + per-match --------------------------------
# The nav badge and the Overview "Most wanted" list run off scoutQueue; per-match
# Scout buttons off matchLiveTodo. Both must agree with coverageState: a code is
# only dead once a patch wiped it AND the game was never captured.

_LIVE_MATCH = ("{id:'m1',f1:'Alpha',f2:'Bravo',finished_at:'2026-07-30',"
               "games:[{game_no:1,map:'Ilios',demo_code:'AAA111'},"
               "{game_no:2,map:'Oasis',demo_code:'BBB222'}]}")
_PREWIPE_MATCH = ("{id:'m2',f1:'Alpha',f2:'Charlie',finished_at:'2026-07-20',"
                  "games:[{game_no:1,map:'Numbani',demo_code:'CCC333'}]}")


def test_match_live_todo_lists_coded_uncaptured_games(tmp_path) -> None:
    got = _run(
        f"return matchLiveTodo({_LIVE_MATCH}, new Set(), null).map(g=>g.demo_code);",
        tmp_path)
    assert got == ["AAA111", "BBB222"]


def test_match_live_todo_drops_captured_games(tmp_path) -> None:
    got = _run(
        f"return matchLiveTodo({_LIVE_MATCH}, new Set(['m1:1']), null).map(g=>g.demo_code);",
        tmp_path)
    assert got == ["BBB222"]


def test_match_live_todo_drops_pre_wipe_uncaptured_codes(tmp_path) -> None:
    got = _run(
        f"return matchLiveTodo({_PREWIPE_MATCH}, new Set(), '2026-07-28');", tmp_path)
    assert got == []   # finished 07-20, wiped 07-28, never captured -> dead


def test_match_live_todo_has_nothing_for_a_captured_pre_wipe_game(tmp_path) -> None:
    """A pre-wipe game captured in time stays in the coverage COUNTS but is no
    longer a to-do — nothing left to scout for it."""
    got = _run(
        f"return matchLiveTodo({_PREWIPE_MATCH}, new Set(['m2:1']), '2026-07-28');",
        tmp_path)
    assert got == []


_DIVS2 = (
    "{a:{summary:{championship:'EMEA Master'},matches:["
    "{id:'m1',f1:'Alpha',f2:'Bravo',finished_at:'2026-07-30',games:["
    "{game_no:1,map:'Ilios',demo_code:'AAA111'},"
    "{game_no:2,map:'Oasis',demo_code:'BBB222'}]}]},"
    "b:{summary:{championship:'NA Master'},matches:["
    "{id:'m2',f1:'Alpha',f2:'Charlie',finished_at:'2026-07-20',games:["
    "{game_no:1,map:'Numbani',demo_code:'CCC333'}]},"
    "{id:'m3',f1:'Delta',f2:'Echo',finished_at:'2026-08-01',games:["
    "{game_no:1,map:'Push',demo_code:'DDD444'}]}]}}"
)


def test_scout_queue_collects_live_uncaptured_codes_newest_first(tmp_path) -> None:
    got = _run(
        f"return scoutQueue({_DIVS2}, new Set(), '2026-07-28').map(r=>r.code);", tmp_path)
    assert got == ["DDD444", "AAA111", "BBB222"]   # m2 is pre-wipe -> dead, excluded


def test_scout_queue_excludes_captured_games(tmp_path) -> None:
    got = _run(
        f"return scoutQueue({_DIVS2}, new Set(['m1:1','m3:1']), '2026-07-28').map(r=>r.code);",
        tmp_path)
    assert got == ["BBB222"]


def test_scout_queue_carries_team_map_and_division(tmp_path) -> None:
    r = _run(f"return scoutQueue({_DIVS2}, new Set(), '2026-07-28');", tmp_path)[-1]
    assert r["f1"] == "Alpha" and r["map"] == "Oasis" and r["div"] == "EMEA Master"


def test_scout_queue_without_a_wipe_treats_every_code_as_live(tmp_path) -> None:
    got = _run(f"return scoutQueue({_DIVS2}, new Set(), null).map(r=>r.code);", tmp_path)
    assert len(got) == 4


# ---------------------------------------------------------------------------
# Capture recommendations (mapCoverage)
# ---------------------------------------------------------------------------
# Numbani (Hybrid): 5 played, 0 captured. Ilios (Control): 4 played, 0 captured.
# Rialto (Escort): 1 played (below the 3-game floor).
_MATCHES = (
    "[{id:'m1',finished_at:'2026-08-01',games:["
    "{game_no:1,map:'Numbani',demo_code:'A1',map_category:'Hybrid'},"
    "{game_no:2,map:'Numbani',demo_code:'A2',map_category:'Hybrid'},"
    "{game_no:3,map:'Numbani',demo_code:'A3',map_category:'Hybrid'}]},"
    "{id:'m2',finished_at:'2026-08-02',games:["
    "{game_no:1,map:'Numbani',demo_code:'B1',map_category:'Hybrid'},"
    "{game_no:2,map:'Numbani',demo_code:'B2',map_category:'Hybrid'}]},"
    "{id:'m3',finished_at:'2026-08-03',games:["
    "{game_no:1,map:'Ilios',demo_code:'C1',map_category:'Control'},"
    "{game_no:2,map:'Ilios',demo_code:'C2',map_category:'Control'},"
    "{game_no:3,map:'Ilios',demo_code:'C3',map_category:'Control'},"
    "{game_no:4,map:'Ilios',demo_code:'C4',map_category:'Control'}]},"
    "{id:'m4',finished_at:'2026-08-04',games:["
    "{game_no:1,map:'Rialto',demo_code:'D1',map_category:'Escort'}]}]"
)


def test_map_coverage_ranks_by_unseen_playtime_and_drops_below_the_floor(
        tmp_path) -> None:
    got = _run(f"return mapCoverage({_MATCHES}, new Set(), null);", tmp_path)
    names = [r["map"] for r in got]
    # Numbani: 5 unseen Hybrid games (100 est. min) beats Ilios' 4 Control (56).
    assert names == ["Numbani", "Ilios"]   # Rialto's 1 game is below the floor
    numb = got[0]
    assert numb["played"] == 5 and numb["captured"] == 0 and numb["pct"] == 0
    assert numb["needed"] == 3             # ceil(5 * 0.5) - 0
    assert numb["unseenMin"] == 100        # 5 * 20 (Hybrid)
    assert numb["liveCode"] == "B1"        # newest live unscouted code (m2), for the link


def test_map_coverage_drops_a_map_that_reached_the_target(tmp_path) -> None:
    # Capture 3 of Numbani's 5 games -> 60% covered -> needed 0 -> not listed.
    got = _run(
        "return mapCoverage(%s, new Set(['m1:1','m1:2','m1:3']), null).map(r=>r.map);" %
        _MATCHES, tmp_path)
    assert got == ["Ilios"]


def test_map_coverage_counts_only_live_codes_as_capturable(tmp_path) -> None:
    # Wipe on 2026-08-01: m1's codes are dead, so Numbani's live code is the
    # first from m2 ('B1'). It stays recommendable (2 live games) — but a map
    # whose ONLY uncaptured games are pre-wipe would drop out entirely.
    got = _run(f"return mapCoverage({_MATCHES}, new Set(), '2026-08-01');", tmp_path)
    numb = got[0]
    assert numb["map"] == "Numbani" and numb["liveCode"] == "B1"
    # All-Ilios map below floor excluded; a fully-dead map is never recommended.
    dead = _run(
        "return mapCoverage([{id:'m9',finished_at:'2026-07-01',games:["
        "{game_no:1,map:'Nepal',demo_code:'Z9',map_category:'Control'},"
        "{game_no:2,map:'Nepal',demo_code:'Z8',map_category:'Control'},"
        "{game_no:3,map:'Nepal',demo_code:'Z7',map_category:'Control'}]}],"
        " new Set(), '2026-08-01');", tmp_path)
    assert dead == []   # 3 games played but every code is pre-wipe -> not capturable


def test_map_coverage_needed_is_clamped_at_zero_when_fully_captured(tmp_path) -> None:
    # Capture every Numbani game: needed must clamp to 0, and the map drops out.
    got = _run(
        "return mapCoverage(%s, new Set(['m1:1','m1:2','m1:3','m2:1','m2:2']), null);" %
        _MATCHES, tmp_path)
    assert not any(r["map"] == "Numbani" for r in got)
    for r in got:
        assert r["needed"] >= 0


def test_map_coverage_counts_finished_playoff_games_as_league_play(tmp_path) -> None:
    # A finished bracket entry is a full match object, so playoff games are
    # capturable league play like any other — and a live playoff code is the
    # freshest capture target on the site (scoutQueue already unions playoffs).
    got = _run(
        "return mapCoverage(["
        "{id:'r1',finished_at:'2026-08-05',games:["
        "{game_no:1,map:'Numbani',demo_code:'R1',map_category:'Hybrid'}]},"
        "{id:'p1',status:'FINISHED',playoff:true,finished_at:'2026-08-07',games:["
        "{game_no:1,map:'Numbani',demo_code:'P1',map_category:'Hybrid'},"
        "{game_no:2,map:'Numbani',demo_code:'P2',map_category:'Hybrid'},"
        "{game_no:3,map:'Numbani',demo_code:'P3',map_category:'Hybrid'}]}],"
        " new Set(), null);", tmp_path)
    numb = got[0]
    assert numb["map"] == "Numbani"
    assert numb["played"] == 4          # 1 regular + 3 playoff games
    assert numb["needed"] == 2          # ceil(4 * 0.5) - 0
    assert numb["liveCode"] == "P1"     # freshest code is the playoff one


def test_map_coverage_counts_a_captured_playoff_game(tmp_path) -> None:
    # Capture keys are (match_id, game_no) for playoff matches too; a captured
    # playoff game must count as covered, not as an unseen live code.
    got = _run(
        "return mapCoverage([{id:'p1',status:'FINISHED',playoff:true,"
        "finished_at:'2026-08-07',games:["
        "{game_no:1,map:'Numbani',demo_code:'P1',map_category:'Hybrid'},"
        "{game_no:2,map:'Numbani',demo_code:'P2',map_category:'Hybrid'},"
        "{game_no:3,map:'Numbani',demo_code:'P3',map_category:'Hybrid'}]}],"
        " new Set(['p1:2']), null);", tmp_path)[0]
    assert got["captured"] == 1 and got["played"] == 3 and got["live"] == 2



# --- draft simulator: pure decision engine + explainers ---------------------
# simModelFrom/divBanBaseFrom/mapsFrom/banSuggest/sigLift/mapCompare/autoMap/
# autoBan/allowedCatsFor and the explainers are pure (no DOM, no esc/inc/
# MAP_CAT/CODE_WIPE), so they're declared above bootApp and directly testable.

_ONE = ("[{id:'m1',f1:'Alpha',f2:'Bravo',finished_at:'2026-07-01',"
        "games:[{game_no:1,map:'Oasis',map_category:'Control',map_picked_by:'Alpha',"
        "bans:[{team:'Alpha',hero:'D.Va',order:1},{team:'Bravo',hero:'Kiriko',order:2}]},"
        "{game_no:2,map:'Runasapi',map_category:'Push',map_picked_by:'Bravo',"
        "bans:[{team:'Alpha',hero:'D.Va',order:2},{team:'Bravo',hero:'Kiriko',order:1}]}]}]")


def test_sim_model_counts_only_that_team_s_picks_and_bans(tmp_path) -> None:
    got = _run(f"return simModelFrom({_ONE},'Alpha',0);", tmp_path)
    assert got["pick"] == {"Oasis": 1}            # Bravo picked Runasapi, not Alpha
    assert got["bansAll"] == {"D.Va": 2}          # Kiriko is Bravo's ban
    assert got["banByMap"]["Oasis"] == {"D.Va": 1}
    assert got["ngames"] == 2


def test_sim_model_tracks_game_keys_for_drilldown(tmp_path) -> None:
    # JSON.stringify turns a Set into {}, so spread the sets out to arrays in JS
    # before returning them through the harness.
    gkPick = _run(f"return [...simModelFrom({_ONE},'Alpha',0).gkPick['Oasis']].sort();",
                  tmp_path)
    assert gkPick == ["m1:1"]
    gkBanAll = _run(f"return [...simModelFrom({_ONE},'Alpha',0).gkBanAll['D.Va']].sort();",
                    tmp_path)
    assert gkBanAll == ["m1:1", "m1:2"]
    gkBanMap = _run(f"return [...simModelFrom({_ONE},'Alpha',0).gkBanMap['Oasis']['D.Va']].sort();",
                    tmp_path)
    assert gkBanMap == ["m1:1"]


def test_sim_model_windows_to_the_newest_maps(tmp_path) -> None:
    three = ("[{id:'w1',f1:'Alpha',f2:'B',finished_at:'2026-07-01',"
             "games:[{game_no:1,map:'Oasis',map_category:'Control',map_picked_by:'Alpha',"
             "bans:[{team:'Alpha',hero:'D.Va',order:1}]}]},"
             "{id:'w2',f1:'Alpha',f2:'B',finished_at:'2026-07-02',"
             "games:[{game_no:1,map:'Ilios',map_category:'Control',map_picked_by:'Alpha',"
             "bans:[{team:'Alpha',hero:'D.Va',order:1}]}]},"
             "{id:'w3',f1:'Alpha',f2:'B',finished_at:'2026-07-03',"
             "games:[{game_no:1,map:'Nepal',map_category:'Control',map_picked_by:'Alpha',"
             "bans:[{team:'Alpha',hero:'Zarya',order:1}]}]}]")
    full = _run(f"return simModelFrom({three},'Alpha',0);", tmp_path)
    assert full["pick"] == {"Oasis": 1, "Ilios": 1, "Nepal": 1} and full["ngames"] == 3
    win = _run(f"return simModelFrom({three},'Alpha',2);", tmp_path)
    assert win["pick"] == {"Ilios": 1, "Nepal": 1} and win["ngames"] == 2  # newest two


_MODEL = ("{banByMap:{Oasis:{'D.Va':3,Zarya:1}},bansAll:{Zarya:10,'D.Va':3,Kiriko:2},"
          "pick:{},gkPick:{},gkBanAll:{},gkBanMap:{}}")


def test_ban_suggest_ranks_a_strong_overall_staple_above_one_on_map_ban(tmp_path) -> None:
    got = _run(f"return banSuggest({_MODEL},'Oasis',new Set()).map(s=>s.hero);", tmp_path)
    assert got == ["Zarya", "D.Va", "Kiriko"]   # 1*2+10 > 3*2+3 > 0+2


def test_ban_suggest_excludes_illegal_heroes_and_caps_at_seven(tmp_path) -> None:
    got = _run(f"return banSuggest({_MODEL},'Oasis',new Set(['Zarya'])).map(s=>s.hero);",
               tmp_path)
    assert got == ["D.Va", "Kiriko"]
    big = ("{banByMap:{Oasis:{}},bansAll:"
           "{A:8,B:7,C:6,D:5,E:4,F:3,G:2,H:1,I:0},pick:{},gkPick:{},gkBanAll:{},gkBanMap:{}}")
    assert len(_run(f"return banSuggest({big},'Oasis',new Set());", tmp_path)) == 7


def test_sig_lift_requires_a_real_sample_and_lift(tmp_path) -> None:
    model = "{banByMap:{},bansAll:{'D.Va':5,Zarya:1},pick:{},gkPick:{},gkBanAll:{},gkBanMap:{}}"
    base = "{all:{'D.Va':0.1},first:{}}"
    assert _run(f"return sigLift({model},{base},'D.Va').sig;", tmp_path) is True
    assert _run(f"return sigLift({model},{base},'Zarya').sig;", tmp_path) is False  # < SIG_MIN
    assert _run(f"return sigLift({model},{{all:{{}},first:{{}}}},'D.Va').lift;",
                tmp_path) is None  # no field baseline -> no lift, no sig


def test_map_compare_prefers_team_picks_then_division_picks_then_plays(tmp_path) -> None:
    assert _run("return mapCompare('Oasis','Ilios',{Oasis:2},{Oasis:5},{Oasis:5});",
                tmp_path) < 0   # team picks beat everything
    assert _run("return mapCompare('Ilios','Oasis',{}, {Oasis:5},{Oasis:5});",
                tmp_path) > 0   # division picks beat nothing
    assert _run("return mapCompare('Ilios','Oasis',{}, {}, {Oasis:3});",
                tmp_path) > 0   # raw plays are the last resort
    assert _run("return mapCompare('Ilios','Oasis',{}, {}, {});",
                tmp_path) < 0   # ties break alphabetically (Ilios < Oasis)


def test_auto_map_respects_used_and_category(tmp_path) -> None:
    pool = "{Oasis:'Control',Ilios:'Control',Nepal:'Control',Blizzard:'Push'}"
    got = _run("return autoMap({},{Oasis:5},{}, ['Control'], new Set(['Oasis']),"
               f"{pool});", tmp_path)
    assert got == "Ilios"


def test_allowed_cats_g1_is_control_and_repeats_only_after_all_used(tmp_path) -> None:
    pool = ("{Oasis:'Control',Blizzard:'Push',Midtown:'Escort',Runasapi:'Push',"
            "Antarctic:'Flashpoint',Numbani:'Hybrid'}")
    assert _run(f"return allowedCatsFor(true, new Set(), {pool});", tmp_path) == ["Control"]
    fresh = _run(f"return allowedCatsFor(false, new Set(['Oasis']), {pool});", tmp_path)
    assert len(fresh) == 4 and "Control" not in fresh          # all non-Control, all fresh
    all4 = _run("return allowedCatsFor(false, new Set(['Blizzard','Midtown','Runasapi',"
                f"'Antarctic','Numbani']), {pool});", tmp_path)
    assert len(all4) == 4                                      # every mode used -> repeats


def test_auto_ban_returns_null_when_everything_is_illegal(tmp_path) -> None:
    assert _run(f"return autoBan({_MODEL},'Oasis',new Set(['Zarya','D.Va','Kiriko']));",
                tmp_path) is None
    assert _run(f"return autoBan({_MODEL},'Oasis',new Set());", tmp_path) == "Zarya"


def test_map_explain_phrases_team_data_vs_division_fallback(tmp_path) -> None:
    assert _run("return mapExplain('Alpha','Oasis','Control',5,10,true).text;",
                tmp_path).startswith("Alpha picked Oasis 5×")
    assert "most-picked Control" in _run(
        "return mapExplain('Alpha','Oasis','Control',5,10,true).text;", tmp_path)
    fall = _run("return mapExplain('Alpha','Oasis','Control',0,10,true);", tmp_path)
    assert "no Alpha pick history" in fall["text"] and "division's most-picked" in fall["text"]
    assert fall["thin"] is False   # the fallback text itself carries the caveat
    none = _run("return mapExplain('Alpha','Oasis','Control',0,0,false);", tmp_path)
    assert "no pick data" in none["text"] and none["thin"] is False


def test_map_explain_flags_a_single_pick_as_thin(tmp_path) -> None:
    got = _run("return mapExplain('Alpha','Oasis','Control',1,10,false);", tmp_path)
    assert got["thin"] is True


def test_ban_explain_phrases_overall_on_map_and_signature(tmp_path) -> None:
    text = _run("return banExplain('Alpha','Oasis','D.Va',5,2,true,true,true).text;", tmp_path)
    assert "most-banned hero overall" in text and "2 of them on Oasis" in text
    assert "★ signature" in text
    assert _run("return banExplain('Alpha','Oasis','D.Va',5,2,true,true,true).thin;",
                tmp_path) is False


def test_ban_explain_phrases_an_on_map_only_top(tmp_path) -> None:
    text = _run("return banExplain('Alpha','Oasis','D.Va',4,3,false,true,false).text;",
                tmp_path)
    assert "most-banned hero on Oasis" in text and "3× here" in text and "4× this season" in text
    assert "most-banned hero overall" not in text      # overall leader is someone else


def test_ban_explain_never_claims_most_after_an_override(tmp_path) -> None:
    text = _run("return banExplain('Alpha','Oasis','Zarya',4,0,false,false,false).text;",
                tmp_path)
    assert "banned 4× this season" in text and "most-banned" not in text


def test_ban_explain_flags_no_history_and_single_case(tmp_path) -> None:
    assert "no ban history" in _run(
        "return banExplain('Alpha','Oasis','Zarya',0,0,false,false,false).text;", tmp_path)
    assert _run("return banExplain('Alpha','Oasis','Zarya',1,1,false,false,false).thin;",
                tmp_path) is True


def test_mode_explain_mentions_league_share_and_team_preference(tmp_path) -> None:
    text = _run("return modeExplain('Alpha','Escort',38,2).text;", tmp_path)
    assert "38% of picks" in text and "picked Escort maps 2×" in text


def test_div_ban_base_shares_sum_to_one_and_guard_zero_total(tmp_path) -> None:
    got = _run(f"return divBanBaseFrom({_ONE});", tmp_path)
    assert round(got["all"]["D.Va"] + got["all"]["Kiriko"], 9) == 1
    empty = _run("return divBanBaseFrom([{id:'m',f1:'A',f2:'B',games:"
                 "[{game_no:1,map:'Oasis',map_category:'Control',bans:[]}]}]);", tmp_path)
    assert empty["all"] == {}


# --- efficiency rating (PER-style) -----------------------------------------
# Per-map stat averages z-scored against the division's same-role players, so a
# rating is only ever relative to the role it was computed in. The rules under
# test: nothing below the sample floor, nothing against fewer than EFF_GROUP_MIN
# peers, and a stat with no variance inside the role is not part of the rating.

_EFF = """[
  {nick:'t1', team:'A', role:'Tank',    stats:{games:10,dmg:9000,heal:0,  mit:15000,kd:2.0}},
  {nick:'t2', team:'A', role:'Tank',    stats:{games:10,dmg:8000,heal:0,  mit:14000,kd:1.6}},
  {nick:'t3', team:'B', role:'Tank',    stats:{games:10,dmg:7000,heal:0,  mit:13000,kd:1.2}},
  {nick:'t4', team:'B', role:'Tank',    stats:{games:10,dmg:6000,heal:0,  mit:12000,kd:0.8}},
  {nick:'t5', team:'C', role:'Tank',    stats:{games:10,dmg:5000,heal:0,  mit:11000,kd:0.4}},
  {nick:'s1', team:'C', role:'Support', stats:{games:10,dmg:300, heal:5000,mit:1200,kd:0.5}},
  {nick:'s2', team:'D', role:'Support', stats:{games:10,dmg:600, heal:6000,mit:1400,kd:0.6}},
  {nick:'s3', team:'D', role:'Support', stats:{games:10,dmg:900, heal:7000,mit:1600,kd:0.7}},
  {nick:'s4', team:'E', role:'Support', stats:{games:10,dmg:1200,heal:8000,mit:1800,kd:0.8}},
  {nick:'s5', team:'E', role:'Support', stats:{games:10,dmg:1500,heal:9000,mit:2000,kd:0.9}},
  {nick:'cameo', team:'F', role:'Tank', stats:{games:2,  dmg:9999,heal:0,  mit:9999,kd:9.9}},
  {nick:'x1', team:'G', role:'Damage',  stats:{games:10,dmg:6000,heal:0,  mit:12000,kd:1.0}},
  {nick:'x2', team:'G', role:'Damage',  stats:{games:10,dmg:5000,heal:0,  mit:10000,kd:0.8}}
]"""


def _eff_players(tmp_path) -> object:
    return _run(f"const ps={_EFF};"
                f"const es=efficiencyRatings(ps.map(p=>({{group:p.role,stats:p.stats}})));"
                f"ps.forEach((p,i)=>{{p.eff=es[i];}});"
                "return ps;", tmp_path)


def test_efficiency_rates_best_and_worst_within_the_cohort(tmp_path) -> None:
    ps = _eff_players(tmp_path)
    t1 = next(p for p in ps if p["nick"] == "t1")   # top tank
    t5 = next(p for p in ps if p["nick"] == "t5")   # bottom tank
    assert t1["eff"]["eff"] > 0 and t5["eff"]["eff"] < 0
    assert t1["eff"]["eff"] > t5["eff"]["eff"]


def test_efficiency_below_the_sample_floor_is_no_rating(tmp_path) -> None:
    cameo = next(p for p in _eff_players(tmp_path) if p["nick"] == "cameo")
    assert cameo["eff"]["eff"] is None


def test_efficiency_needs_enough_same_role_peers(tmp_path) -> None:
    x1 = next(p for p in _eff_players(tmp_path) if p["nick"] == "x1")
    assert x1["eff"]["groupN"] == 2          # only one peer to compare against
    assert x1["eff"]["eff"] is None          # a z vs one other player is not a rating


def test_efficiency_drops_a_stat_with_no_variance_in_the_role(tmp_path) -> None:
    t1 = next(p for p in _eff_players(tmp_path) if p["nick"] == "t1")
    assert "heal" not in t1["eff"]["comps"]  # no tank heals: not part of the rating
    assert t1["eff"]["eff"] > 1.3            # heal's absence must not drag it down


def test_efficiency_composite_is_the_mean_of_its_components(tmp_path) -> None:
    t1 = next(p for p in _eff_players(tmp_path) if p["nick"] == "t1")
    e = t1["eff"]
    zs = [e["comps"][k]["z"] for k in ("dmg", "mit", "kd")]   # heal excluded for tanks
    assert abs(e["eff"] - sum(zs) / len(zs)) < 1e-9


def test_efficiency_is_relative_within_the_support_role(tmp_path) -> None:
    ps = _eff_players(tmp_path)
    s5 = next(p for p in ps if p["nick"] == "s5")   # top support
    s1 = next(p for p in ps if p["nick"] == "s1")   # bottom support
    assert s5["eff"]["eff"] > 0 and s1["eff"]["eff"] < 0


def test_rank_players_by_efficiency_keeps_unrated_players_last(tmp_path) -> None:
    got = _run(f"const ps={_EFF};"
               f"const es=efficiencyRatings(ps.map(p=>({{group:p.role,stats:p.stats}})));"
               f"ps.forEach((p,i)=>{{p.eff=es[i];}});"
               "return rankPlayers(ps,{key:'eff'}).map(p=>p.nick);", tmp_path)
    assert got[0] in ("t1", "s5")              # the co-leaders (+1.414) lead, nick tie-break
    assert "cameo" not in got                  # below the rate floor: filtered out
    assert got[-2:] == ["x1", "x2"]            # rated never sorts below unrated
    assert got[-3] == "t5"                     # lowest eff (-1.414) sits right before the unrated
    assert all(n in got for n in ("t1", "t5", "s5", "s1"))


# --- team compare: radar math -------------------------------------------------
# compareAxes/radarPoints are pure (no DOM, no DATA), declared above bootApp.
# They take pre-computed per-team sources — aggregate()'s agg + owscout scout +
# a team-eff summary — and only normalize: fixed caps to 0..100, sample floors
# to dim, and axes neither side sampled are dropped outright.

_COMPARE_A = ("({games:10, gwins:6, mapStats:{Oasis:{games:5,wins:3},Ilios:{games:5,wins:3}},"
              " bans:{'D.Va':3,'Kiriko':2}, mapsPicked:{Oasis:4}})")
_COMPARE_B = ("({games:10, gwins:3, mapStats:{Oasis:{games:10,wins:3}},"
              " bans:{'D.Va':6}, mapsPicked:{Oasis:3}})")
_COMPARE_SA = ("{scout:{adapt:{families:5,swaps_per_map:1.2},"
               " hero_pool:[{hero:'D.Va',pick_rate:.4},{hero:'Winston',pick_rate:.1},{hero:'Rein',pick_rate:.02}],"
               " games:8, rounds:40}}")
_COMPARE_SB = "{scout:{adapt:{families:2,swaps_per_map:0.3}, hero_pool:[], games:4, rounds:10}}"


def _axes(tmp_path, a=_COMPARE_A, b=_COMPARE_B, sa=_COMPARE_SA, sb=_COMPARE_SB,
          ea="null", eb="null") -> object:
    return _run(f"return compareAxes({a},{b},{sa},{sb},{ea},{eb});", tmp_path)


def _byid(rows, axis_id) -> dict:
    return next(r for r in rows if r["id"] == axis_id)


def test_compare_axes_caps_raw_values_to_100(tmp_path) -> None:
    got = _axes(tmp_path)
    assert _byid(got, "mapwr")["a"]["val"] == 60.0        # 6/10 maps won
    assert _byid(got, "mapwr")["b"]["val"] == 30.0        # 3/10 maps won
    assert _byid(got, "pool")["a"]["val"] == 20.0         # 2 distinct maps, cap 10
    assert _byid(got, "banpress")["a"]["val"] == 25.0     # 5 bans / 10 games, cap 2
    assert _byid(got, "pick")["a"]["val"] == 40.0         # 4 picked / 10 games


def test_compare_axes_caps_never_exceed_100(tmp_path) -> None:
    big = "({games:2, gwins:2, mapStats:{a:{games:2,wins:2}}, bans:{}, mapsPicked:{}})"
    got = _axes(tmp_path, a=big, b=big, sa="null", sb="null")
    assert _byid(got, "mapwr")["a"]["val"] == 100.0
    assert _byid(got, "mapwr")["b"]["val"] == 100.0
    assert all(0 <= r["a"]["val"] <= 100 and 0 <= r["b"]["val"] <= 100 for r in got)


def test_compare_axes_dims_below_floor(tmp_path) -> None:
    # A has 2 games (below the 5-game floor); B has 10. A's mapwr is dimmed.
    few = "({games:2, gwins:1, mapStats:{a:{games:2,wins:1}}, bans:{}, mapsPicked:{}})"
    got = _axes(tmp_path, a=few, b=_COMPARE_B, sa="null", sb="null")
    assert _byid(got, "mapwr")["a"]["ok"] is False
    assert _byid(got, "mapwr")["b"]["ok"] is True
    assert _byid(got, "mapwr")["a"]["n"] == 2


def test_compare_axes_drops_axis_missing_on_both_sides(tmp_path) -> None:
    got = _axes(tmp_path, sa="null", sb="null", ea="{mean:1,n:4}", eb="{mean:1,n:4}")
    ids = {r["id"] for r in got}
    assert not ids & {"families", "heropool", "swaps"}        # both sides lack captures -> dropped
    assert {"mapwr", "pool", "banpress", "pick", "eff"} <= ids


def test_compare_axes_one_sided_capture_dims_the_other(tmp_path) -> None:
    got = _axes(tmp_path, sa=_COMPARE_SA, sb="null")
    assert "families" in {r["id"] for r in got}              # A captured -> axis present
    assert _byid(got, "families")["a"]["ok"] is True
    assert _byid(got, "families")["b"]["ok"] is False        # B has no capture sample


def test_compare_team_eff_uses_qualified_players_only(tmp_path) -> None:
    got = _axes(tmp_path, ea="{mean:1.2,n:4}", eb="{mean:null,n:0}")
    e = _byid(got, "eff")
    assert e["a"]["raw"] == 1.2 and e["a"]["val"] == 100.0   # cap 0.5 → 1.2 exceeds cap, clamped to 100
    assert e["a"]["ok"] is True                              # n=4 >= 3 peers
    assert e["b"]["raw"] is None and e["b"]["ok"] is False


def test_compare_team_eff_needs_three_qualified_players(tmp_path) -> None:
    got = _axes(tmp_path, ea="{mean:0.5,n:2}", eb="{mean:0.5,n:2}")
    e = _byid(got, "eff")
    assert e["a"]["ok"] is False                             # 2 peers is not a rating


def test_radar_points_vertices(tmp_path) -> None:
    got = _run("return radarPoints([100,50,0,100],0,0,100);", tmp_path)
    # 12 o'clock start, clockwise: up, right, down, left.
    assert abs(got[0]["x"] - 0) < 1e-9 and abs(got[0]["y"] + 100) < 1e-9
    assert abs(got[1]["x"] - 50) < 1e-9 and abs(got[1]["y"] - 0) < 1e-9
    assert abs(got[2]["x"] - 0) < 1e-9 and abs(got[2]["y"] - 0) < 1e-9
    assert abs(got[3]["x"] + 100) < 1e-9 and abs(got[3]["y"] - 0) < 1e-9


def test_radar_points_null_skips_the_vertex_and_zero_radius_is_empty(tmp_path) -> None:
    got = _run("return radarPoints([null,50,100,50],0,0,100);", tmp_path)
    assert got[0] is None
    assert abs(got[1]["x"] - 50) < 1e-9 and abs(got[1]["y"] - 0) < 1e-9
    assert abs(got[2]["x"] - 0) < 1e-9 and abs(got[2]["y"] - 100) < 1e-9
    assert abs(got[3]["x"] + 50) < 1e-9 and abs(got[3]["y"] - 0) < 1e-9
    assert _run("return radarPoints([100,100],0,0,0);", tmp_path) == []


# --- power rankings ---------------------------------------------------------
# Series Elo orders the table (K=32); Map Elo (K=12) is a supporting column
# only. Walkovers carry no maps and must not move either rating. Order of the
# input array must not matter — only chronology (finished_at) does.

def _match(f1, f2, winner, finished_at, game_winners, walkover=False):
    games = [{"winner_faction": w} for w in game_winners]
    return {
        "finished_at": finished_at, "f1": f1, "f2": f2,
        "winner": winner, "walkover": walkover, "games": games,
    }


def test_power_rankings_bo1_match_updates_both_ratings_exactly(tmp_path) -> None:
    # Single-game match keeps Series and Map Elo identical formulas with no
    # intermediate steps, so the exact post-match numbers are hand-checkable:
    # both start at 1500 (expected score 0.5 each way), A wins ->
    # ra = 1500 + K*(1-0.5), rb = 1500 + K*(0-0.5).
    m = [_match("A", "B", "faction1", "2026-01-01T00:00:00Z", ["faction1"])]
    got = _run(f"return powerRankings({json.dumps(m)});", tmp_path)
    by_name = {r["name"]: r for r in got}
    assert by_name["A"]["rating"] == 1516
    assert by_name["B"]["rating"] == 1484
    assert by_name["A"]["mapRating"] == 1506
    assert by_name["B"]["mapRating"] == 1494
    assert by_name["A"]["n"] == 1 and by_name["B"]["n"] == 1
    assert by_name["A"]["provisional"] is True   # n=1 < POWER_MIN_N


def test_power_rankings_orders_by_series_rating_descending(tmp_path) -> None:
    m = [_match("A", "B", "faction1", "2026-01-01T00:00:00Z", ["faction1"])]
    got = _run(f"return powerRankings({json.dumps(m)});", tmp_path)
    assert [r["name"] for r in got] == ["A", "B"]


def test_power_rankings_bo5_win_moves_both_ratings_in_the_winners_favor(tmp_path) -> None:
    m = [_match("A", "B", "faction1", "2026-01-01T00:00:00Z",
                ["faction1", "faction1", "faction2", "faction1"])]
    got = _run(f"return powerRankings({json.dumps(m)});", tmp_path)
    by_name = {r["name"]: r for r in got}
    assert by_name["A"]["rating"] > 1500 > by_name["B"]["rating"]
    assert by_name["A"]["mapRating"] > 1500 > by_name["B"]["mapRating"]


def test_power_rankings_excludes_walkovers(tmp_path) -> None:
    m = [_match("A", "B", "faction1", "2026-01-01T00:00:00Z", [], walkover=True)]
    got = _run(f"return powerRankings({json.dumps(m)});", tmp_path)
    assert got == []


def test_power_rankings_is_order_independent_of_input_array_order(tmp_path) -> None:
    m1 = _match("A", "B", "faction1", "2026-01-01T00:00:00Z", ["faction1"])
    m2 = _match("A", "B", "faction2", "2026-01-08T00:00:00Z", ["faction2"])
    forward = _run(f"return powerRankings({json.dumps([m1, m2])});", tmp_path)
    backward = _run(f"return powerRankings({json.dumps([m2, m1])});", tmp_path)
    assert forward == backward


def test_power_rankings_provisional_flag_boundary(tmp_path) -> None:
    # A plays 4 distinct opponents (n=4, below POWER_MIN_N=5) -> provisional.
    opponents = ["C", "D", "E", "F"]
    matches = [_match("A", opp, "faction1", f"2026-01-0{i+1}T00:00:00Z", ["faction1"])
               for i, opp in enumerate(opponents)]
    got = _run(f"return powerRankings({json.dumps(matches)});", tmp_path)
    a = next(r for r in got if r["name"] == "A")
    assert a["n"] == 4
    assert a["provisional"] is True

    matches.append(_match("A", "G", "faction1", "2026-01-05T00:00:00Z", ["faction1"]))
    got5 = _run(f"return powerRankings({json.dumps(matches)});", tmp_path)
    a5 = next(r for r in got5 if r["name"] == "A")
    assert a5["n"] == 5
    assert a5["provisional"] is False


def test_power_rankings_history_is_one_point_per_match_in_order(tmp_path) -> None:
    m1 = _match("A", "B", "faction1", "2026-01-01T00:00:00Z", ["faction1"])
    m2 = _match("A", "C", "faction2", "2026-01-08T00:00:00Z", ["faction2"])
    got = _run(f"return powerRankings({json.dumps([m1, m2])});", tmp_path)
    a = next(r for r in got if r["name"] == "A")
    assert len(a["history"]) == 2
    assert a["history"][0] == 1516          # after beating B (see bo1 test above)
    assert a["history"][1] < a["history"][0]  # then lost to C, rating dropped


# --- sparkline points --------------------------------------------------------
# Turns a rating history into normalized SVG polyline points. A single-point
# history still has to render a visible flat line, not collapse to nothing —
# a team's first result shouldn't be an invisible sparkline.

def test_sparkline_empty_history_is_empty_string(tmp_path) -> None:
    assert _run("return sparklinePoints([], 60, 20);", tmp_path) == ""


def test_sparkline_single_point_is_a_flat_centered_line(tmp_path) -> None:
    assert _run("return sparklinePoints([1500], 60, 20);", tmp_path) == "0,10 60,10"


def test_sparkline_two_points_span_the_full_box(tmp_path) -> None:
    # Lower rating first -> higher on screen is lower y (SVG y grows downward),
    # so the rising [1500,1600] history must end at y=0 (top), not y=20.
    got = _run("return sparklinePoints([1500,1600], 60, 20);", tmp_path)
    assert got == "0.0,20.0 60.0,0.0"


def test_sparkline_flat_history_stays_centered(tmp_path) -> None:
    got = _run("return sparklinePoints([1500,1500,1500], 60, 20);", tmp_path)
    # equal values -> span defaults to 1 so it doesn't divide by zero; every
    # point should land at the same y.
    ys = [p.split(',')[1] for p in got.split(' ')]
    assert len(set(ys)) == 1

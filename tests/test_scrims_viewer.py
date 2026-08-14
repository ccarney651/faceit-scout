"""docs/scrims.html — the private scrims viewer's analysis helpers.

Extracts the pure functions and runs them under Node, the same way
tests/test_capture_scrim.py does for the capture app. The viewer keeps its
analysis inline rather than in an engine module because its CSP allows only
inline scripts (`script-src 'unsafe-inline'`, no `'self'`), so there is nothing
to import.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

APP = Path(__file__).resolve().parents[1] / "docs" / "scrims.html"


def _pure_js() -> str:
    html = APP.read_text(encoding="utf-8")
    start = html.index("const SCRIM_MODES")
    end = html.index("// ---------- opponent registry ----------")
    return html[start:end]


def _run(body: str) -> object:
    node = shutil.which("node")
    if not node:
        pytest.skip("node not available to run the viewer's helpers")
    src = _pure_js() + "\nconsole.log(JSON.stringify((()=>{" + body + "})()));"
    proc = subprocess.run([node, "-e", src], capture_output=True, text=True)
    assert proc.returncode == 0, f"node failed:\n{proc.stderr}"
    return json.loads(proc.stdout)


def _role_map() -> dict[str, list[str]]:
    """The viewer's hero->role table, which sits outside the pure region."""
    html = APP.read_text(encoding="utf-8")
    start = html.index("const ROLE_MAP = {")
    end = html.index("};", start) + 2
    node = shutil.which("node")
    if not node:
        pytest.skip("node not available to read the role table")
    src = html[start:end] + "\nconsole.log(JSON.stringify(ROLE_MAP));"
    proc = subprocess.run([node, "-e", src], capture_output=True, text=True)
    assert proc.returncode == 0, f"node failed:\n{proc.stderr}"
    return json.loads(proc.stdout)


def _scrims_and_maps() -> tuple[str, str]:
    scrims = json.dumps([
        {"id": "s1", "date": "2026-08-13"},
        {"id": "s2", "date": "2026-07-20"},
    ])
    maps = json.dumps([
        {"scrim_id": "s1", "map_category": "Control"},
        {"scrim_id": "s1", "map_category": "Control"},
        {"scrim_id": "s1", "map_category": "Hybrid"},
        {"scrim_id": "s2", "map_category": "Push"},
    ])
    return scrims, maps


def test_coverage_reports_every_mode_including_unplayed_ones() -> None:
    """The point is the mode you have NOT played, so modes are listed, not derived.

    Deriving them from the captured maps would hide exactly the gap this is for.
    """
    scrims, maps = _scrims_and_maps()
    cov = _run(f"return mapCoverage({scrims}, {maps}, '2026-08-14');")
    modes = {c["mode"] for c in cov}
    assert {"Control", "Escort", "Hybrid", "Push", "Flashpoint"} <= modes
    assert "Clash" not in modes, "Clash is no longer played competitively"
    by = {c["mode"]: c for c in cov}
    assert by["Escort"]["games"] == 0 and by["Escort"]["last"] is None
    assert by["Escort"]["days"] is None


def test_coverage_counts_games_and_dates_the_most_recent() -> None:
    scrims, maps = _scrims_and_maps()
    by = {c["mode"]: c for c in _run(f"return mapCoverage({scrims}, {maps}, '2026-08-14');")}
    assert by["Control"]["games"] == 2
    assert by["Control"]["last"] == "2026-08-13"
    assert by["Control"]["days"] == 1
    assert by["Push"]["days"] == 25, "Push was three and a half weeks ago"


def test_coverage_puts_the_least_practised_first() -> None:
    """The ordering is the recommendation: never-played, then longest since."""
    scrims, maps = _scrims_and_maps()
    cov = _run(f"return mapCoverage({scrims}, {maps}, '2026-08-14');")
    played = [c["mode"] for c in cov if c["games"]]
    assert cov[0]["games"] == 0, "an unplayed mode should lead"
    assert played.index("Push") < played.index("Control"), (
        "the stalest played mode should come before the freshest"
    )


def test_voided_maps_do_not_count_as_practice() -> None:
    """A restarted map was not practice; counting it claims coverage you skipped."""
    scrims = json.dumps([{"id": "s1", "date": "2026-08-13"}])
    maps = json.dumps([
        {"scrim_id": "s1", "map_category": "Push", "void": True},
        {"scrim_id": "s1", "map_category": "Control"},
    ])
    by = {c["mode"]: c for c in _run(f"return mapCoverage({scrims}, {maps}, '2026-08-14');")}
    assert by["Push"]["games"] == 0, "a voided map still counted as practice"
    assert by["Control"]["games"] == 1


def test_coverage_falls_back_to_created_at_when_a_scrim_has_no_date() -> None:
    """An auto-created block has no date field until it is named and saved."""
    scrims = json.dumps([{"id": "s1", "created_at": "2026-08-10T19:00:00Z"}])
    maps = json.dumps([{"scrim_id": "s1", "map_category": "Control"}])
    by = {c["mode"]: c for c in _run(f"return mapCoverage({scrims}, {maps}, '2026-08-14');")}
    assert by["Control"]["last"] == "2026-08-10"
    assert by["Control"]["days"] == 4


def test_an_unexpected_mode_still_appears() -> None:
    """A mode the list does not know about must not vanish from the log."""
    scrims = json.dumps([{"id": "s1", "date": "2026-08-13"}])
    maps = json.dumps([{"scrim_id": "s1", "map_category": "Brawl"}])
    by = {c["mode"]: c for c in _run(f"return mapCoverage({scrims}, {maps}, '2026-08-14');")}
    assert by["Brawl"]["games"] == 1


def test_viewer_resolves_opponents_through_the_registry() -> None:
    """Renaming a remembered group once must relabel every scrim against them.

    So the viewer has to read the registry rather than the name string frozen
    onto each scrim record when it was captured.
    """
    html = APP.read_text(encoding="utf-8")
    assert "async function loadOpponents()" in html
    assert "function opponentOf(s)" in html
    assert "await loadOpponents();" in html, "the registry is never loaded"
    # And the places that show an opponent must go through it.
    assert html.count("opponentLabelHtml(s)") >= 2, (
        "a scrim's opponent is still rendered from the frozen string"
    )
    assert "esc(s.opponent||'opponent')" not in html, (
        "an opponent is still rendered without consulting the registry"
    )


DEMO = APP.parent / "scrims-demo.json"


def test_demo_fixture_uses_real_teams_and_real_hero_guids() -> None:
    """A demo of "Team A / Player 1" teaches nothing about whether this is worth using.

    Real FACEIT entrants and real hero GUIDs, so the sample looks like what the
    operator would actually see.
    """
    d = json.loads(DEMO.read_text(encoding="utf-8"))
    assert d["demo"] is True
    assert d["scrims"] and d["scrim_maps"]
    names = {s.get("team_us") for s in d["scrims"]} | {s.get("opponent") for s in d["scrims"]}
    names.discard(None)
    assert names, "no team names in the demo"
    assert not any(n.lower().startswith(("team a", "team b", "example")) for n in names), (
        f"placeholder team names in the demo: {names}"
    )
    guids = {g for m in d["scrim_maps"] for o in m["observations"] for g in o["heroes"]}
    assert guids, "the demo has no hero observations"
    assert all(g.startswith("0x") for g in guids), f"not real hero GUIDs: {sorted(guids)[:3]}"


def test_demo_says_plainly_that_the_results_are_invented() -> None:
    """It names real teams and real players, so the disclaimer is not decoration.

    Without it, someone could read the page as a record of games those teams
    actually played.
    """
    d = json.loads(DEMO.read_text(encoding="utf-8"))
    note = d["note"].lower()
    assert "never happened" in note or "invented" in note, d["note"]
    assert "real" in note, "it should say the teams themselves are real"
    html = APP.read_text(encoding="utf-8")
    assert "function demoBanner()" in html
    assert "DEMO?demoBanner():''" in html.replace(" ", ""), "the banner is never rendered"


def test_demo_never_writes_to_the_real_database() -> None:
    """Trying the demo must not leave invented scrims in someone's own data."""
    html = APP.read_text(encoding="utf-8")
    start = html.index("async function loadDemo()")
    end = html.index("async function loadData()")
    body = html[start:end]
    for forbidden in ("idbPutIn", "objectStore(", "readwrite"):
        assert forbidden not in body, f"loadDemo touches storage: {forbidden}"


def test_demo_dates_stay_recent_rather_than_ageing() -> None:
    """Committed absolute dates would read as "played 200 days ago" within a year."""
    d = json.loads(DEMO.read_text(encoding="utf-8"))
    assert any("@@MINUS" in str(s.get("date", "")) for s in d["scrims"]), (
        "demo dates are absolute and will rot"
    )
    html = APP.read_text(encoding="utf-8")
    assert "function demoDate(" in html, "nothing resolves the relative dates"


def test_demo_covers_the_cases_the_viewer_is_meant_to_show() -> None:
    """The sample has to exercise what makes the page worth looking at."""
    d = json.loads(DEMO.read_text(encoding="utf-8"))
    assert any(s.get("opponent_team_id") for s in d["scrims"]), "no league opponent"
    assert any(s.get("opponent_id") for s in d["scrims"]), "no remembered group"
    assert any(not s.get("opponent_team_id") and not s.get("opponent_id")
               for s in d["scrims"]), "no unidentified opponent"
    assert any(m.get("void") for m in d["scrim_maps"]), "no voided restart"
    modes = {m["map_category"] for m in d["scrim_maps"]}
    assert len(modes) >= 4, f"too few modes to make coverage meaningful: {modes}"


def test_coverage_breaks_a_mode_down_by_map() -> None:
    """A mode total hides that you have played Ilios twice and Nepal never.

    The per-map breakdown is the actionable half: "play Control more" is not a
    plan, "you have never scrimmed Nepal" is.
    """
    scrims = json.dumps([{"id": "s1", "date": "2026-08-13"}])
    maps = json.dumps([
        {"scrim_id": "s1", "map_category": "Control", "map_name": "Ilios"},
        {"scrim_id": "s1", "map_category": "Control", "map_name": "Ilios"},
        {"scrim_id": "s1", "map_category": "Control", "map_name": "Busan"},
    ])
    by = {c["mode"]: c for c in _run(f"return mapCoverage({scrims}, {maps}, '2026-08-14');")}
    ctrl = by["Control"]["maps"]
    assert ctrl["Ilios"] == 2
    assert ctrl["Busan"] == 1
    assert ctrl["Nepal"] == 0, "an unplayed map in the pool must still be listed"
    assert set(ctrl) >= {"Antarctic Peninsula", "Lijiang Tower", "Oasis", "Samoa"}


def test_clash_is_gone_from_the_pool() -> None:
    """No longer played competitively, so it is noise in every list."""
    html = APP.read_text(encoding="utf-8")
    start = html.index("const POOL = {")
    pool = html[start:html.index("};", start)]
    assert "Clash" not in pool
    assert "Anubis" not in pool and "Hanaoka" not in pool


def test_the_view_can_be_scoped_to_a_period() -> None:
    """A year of scrims can span two or three teams.

    Mixing them produces hero pools that belong to nobody, so the range is a
    first-class control rather than a nicety.
    """
    html = APP.read_text(encoding="utf-8")
    assert "function applyRange(data)" in html
    assert "function renderRangeBar()" in html
    assert "function wireRangeBar(" in html
    assert "Custom…" in html or "Custom" in html, "no custom range option"
    # It must filter the loaded data rather than re-read storage, or switching
    # range would be a round-trip to IndexedDB on every change.
    start = html.index("function applyRange(data)")
    body = html[start:start + 800]
    assert "idbGetAll" not in body, "applyRange re-reads storage instead of filtering"


# ---------------------------------------------------------------------------
# Comp analysis — the parity work with the league Scout pages.
#
# A five-hero shorthand keeps these readable: T/T2 are tanks, D* damage, S*
# support. ROLES is the guid -> role map the page builds from refs.json.
# ---------------------------------------------------------------------------

ROLES = json.dumps({"T": "Tank", "T2": "Tank",
                    "D1": "Damage", "D2": "Damage", "D3": "Damage",
                    "S1": "Support", "S2": "Support", "S3": "Support"})


def test_four_shared_heroes_is_the_same_comp() -> None:
    got = _run(f"return sameComp(['T','D1','D2','S1','S2'],"
               f"               ['T','D1','D2','S1','S3'], {ROLES});")
    assert got is True


def test_three_shared_is_the_same_comp_only_with_the_same_tank() -> None:
    """The tank anchors comp identity in 5v5 — swap it and it is a different plan."""
    with_tank = _run(f"return sameComp(['T','D1','D2','S1','S2'],"
                     f"               ['T','D1','D2','S3','D3'], {ROLES});")
    without = _run(f"return sameComp(['T','D1','D2','S1','S2'],"
                   f"              ['T2','D1','D2','S3','D3'], {ROLES});")
    assert with_tank is True
    assert without is False, "a different tank with three shared heroes is a different comp"


def test_a_comp_run_on_both_halves_of_a_map_is_one_win_not_two() -> None:
    """W-L is counted over distinct maps. Counting segments would let a single
    won map report 2-0 and inflate every comp played on Escort or Control."""
    insts = json.dumps([
        {"heroes": ["T", "D1", "D2", "S1", "S2"], "mapKey": "m1", "result": "win"},
        {"heroes": ["T", "D1", "D2", "S1", "S2"], "mapKey": "m1", "result": "win"},
    ])
    fams = _run(f"return clusterComps({insts}, {ROLES});")
    assert len(fams) == 1
    assert fams[0]["samples"] == 2, "both segments should still be counted as samples"
    assert fams[0]["maps"] == 1
    assert fams[0]["wins"] == 1, "one won map was counted twice"


def test_a_comp_with_no_recorded_result_is_not_reported_as_a_loss() -> None:
    insts = json.dumps([{"heroes": ["T", "D1", "D2", "S1", "S2"],
                         "mapKey": "m1", "result": None}])
    f = _run(f"return clusterComps({insts}, {ROLES});")[0]
    assert (f["wins"], f["losses"], f["draws"]) == (0, 0, 0)


def test_hero_pool_is_counted_in_rounds_not_maps() -> None:
    """The whole point of the metric: a hero played every round is a staple, one
    played for a single point is not, and counting maps flattens both to "1 map"."""
    maps = json.dumps([{
        "id": "m1", "map_category": "Control",
        "observations": [
            {"side": "a", "round_no": 1, "sub_map": "Lighthouse", "heroes": ["T", "D1"]},
            {"side": "a", "round_no": 2, "sub_map": "Ruins", "heroes": ["T", "D1"]},
            {"side": "a", "round_no": 3, "sub_map": "Well", "heroes": ["T", "D2"]},
        ],
    }])
    pool = _run(f"return heroPool({maps}, 'a');")
    assert pool["total"] == 3
    assert pool["counts"]["T"] == 3, "the staple should read as every round"
    assert pool["counts"]["D2"] == 1, "the one-off should not read like the staple"


def test_two_snapshots_in_one_round_do_not_double_count_that_round() -> None:
    """Otherwise a round that happened to be captured twice would out-weigh one
    captured once, and the denominator would stop meaning rounds."""
    maps = json.dumps([{
        "id": "m1", "map_category": "Push",
        "observations": [
            {"side": "a", "round_no": 1, "ts": 1, "heroes": ["T", "D1"]},
            {"side": "a", "round_no": 1, "ts": 2, "heroes": ["T", "D1"]},
        ],
    }])
    pool = _run(f"return heroPool({maps}, 'a');")
    assert pool["total"] == 1
    assert pool["counts"]["T"] == 1


def test_a_voided_map_contributes_no_rounds_and_no_comps() -> None:
    maps = json.dumps([{"id": "m1", "void": True, "map_category": "Push",
                        "observations": [{"side": "a", "round_no": 1,
                                          "heroes": ["T", "D1", "D2", "S1", "S2"]}]}])
    assert _run(f"return heroPool({maps}, 'a');")["total"] == 0
    assert _run(f"return compInstances({maps}, 'a');") == []


def test_segments_follow_the_mode_the_map_is_played_as() -> None:
    """A Hybrid attack comp and a Hybrid defend comp are different decisions;
    averaging them over the map hides both."""
    got = _run("""
      const ctrl = {map_category:'Control'}, hyb = {map_category:'Hybrid'},
            push = {map_category:'Push'};
      return [segmentOf(ctrl, {sub_map:'Ruins', round_no:2}),
              segmentOf(hyb, {phase:'attack', round_no:1}),
              segmentOf(hyb, {phase:'defend', round_no:2}),
              segmentOf(push, {round_no:1})];
    """)
    assert got == ["Ruins", "Attack", "Defend", "Map"]


def test_a_comp_change_between_segments_is_not_a_swap() -> None:
    """Picking a different comp for the next point is an OPENER, not a mid-map
    answer to the enemy. Counting it fills the swap list with ordinary choices."""
    m = json.dumps({
        "id": "m1", "map_category": "Control",
        "observations": [
            {"side": "a", "round_no": 1, "sub_map": "Lighthouse", "ts": 1,
             "heroes": ["T", "D1", "D2", "S1", "S2"]},
            {"side": "a", "round_no": 2, "sub_map": "Ruins", "ts": 2,
             "heroes": ["T2", "D3", "D2", "S1", "S3"]},
        ],
    })
    assert _run(f"return swapEvents({m}, 'a', {ROLES});") == []


def test_a_swap_inside_a_segment_is_reported_with_what_it_faced() -> None:
    m = json.dumps({
        "id": "m1", "map_category": "Push",
        "observations": [
            {"side": "a", "round_no": 1, "ts": 1, "heroes": ["T", "D1", "D2", "S1", "S2"]},
            {"side": "b", "round_no": 1, "ts": 2, "heroes": ["T2", "D3", "D2", "S1", "S3"]},
            {"side": "a", "round_no": 1, "ts": 3, "heroes": ["T", "D1", "D3", "S1", "S2"]},
        ],
    })
    evs = _run(f"return swapEvents({m}, 'a', {ROLES});")
    assert len(evs) == 1
    assert evs[0]["out"] == ["D2"] and evs[0]["in"] == ["D3"]
    assert evs[0]["kind"] == "flex", "four heroes shared is the same comp family"
    assert "D3" in evs[0]["vs"], "the enemy lineup at that moment is the trigger"


def test_a_partial_read_is_not_reported_as_four_players_swapping() -> None:
    """A snapshot where two portraits failed to read would otherwise look like a
    mass substitution, which is the most alarming possible false positive."""
    m = json.dumps({
        "id": "m1", "map_category": "Push",
        "observations": [
            {"side": "a", "round_no": 1, "ts": 1, "heroes": ["T", "D1", "D2", "S1", "S2"]},
            {"side": "a", "round_no": 1, "ts": 2, "heroes": ["T", "D1", "D2"]},
        ],
    })
    assert _run(f"return swapEvents({m}, 'a', {ROLES});") == []


def test_an_ever_present_enemy_hero_is_not_reported_as_a_trigger() -> None:
    """Baseline subtraction. A hero the enemy fields in every snapshot did not
    cause anything — without this, the trigger column just names their staple."""
    def obs(rnd, ts, side, heroes):
        return {"side": side, "round_no": rnd, "ts": ts, "heroes": heroes}

    # S3 is on the enemy team in every single snapshot; D3 only appears at the
    # two moments the swap is made.
    maps = json.dumps([{
        "id": "m1", "map_category": "Push", "observations": [
            obs(1, 1, "b", ["T2", "D1", "D2", "S1", "S3"]),
            obs(1, 2, "a", ["T", "D1", "D2", "S1", "S2"]),
            obs(1, 3, "b", ["T2", "D3", "D2", "S1", "S3"]),
            obs(1, 4, "a", ["T", "D1", "D3", "S1", "S2"]),
        ]}, {
        "id": "m2", "map_category": "Push", "observations": [
            obs(1, 1, "b", ["T2", "D1", "D2", "S1", "S3"]),
            obs(1, 2, "a", ["T", "D1", "D2", "S1", "S2"]),
            obs(1, 3, "b", ["T2", "D3", "D2", "S1", "S3"]),
            obs(1, 4, "a", ["T", "D1", "D3", "S1", "S2"]),
        ]}])
    swaps = _run(f"return aggregateSwaps({maps}, 'a', {ROLES});")
    assert len(swaps) == 1 and swaps[0]["count"] == 2
    assert "D3" in swaps[0]["vs"], "the hero that actually showed up is the trigger"
    assert "S3" not in swaps[0]["vs"], (
        "an enemy hero present in every snapshot was reported as a trigger"
    )


def test_the_opponents_record_is_the_mirror_of_ours() -> None:
    """Results are captured from our point of view, so a map we won is a map they
    lost. Reusing our result for their comps would invert their entire W-L."""
    maps = json.dumps([{"id": "m1", "map_category": "Push", "result": "win",
                        "observations": [
                            {"side": "b", "round_no": 1,
                             "heroes": ["T", "D1", "D2", "S1", "S2"]}]}])
    inst = _run(f"return compInstances({maps}, 'b');")[0]
    assert inst["result"] == "loss"


def test_an_observation_written_by_the_capture_page_is_understood() -> None:
    """The capture page writes `round_no`; a hand-built fixture may write `round`.
    Reading only one of them silently collapses every map to a single round."""
    got = _run("return [obsRound({round_no:3}), obsRound({round:2}), obsRound({})];")
    assert got == [3, 2, 1]


def test_the_demo_fixture_matches_what_the_capture_page_actually_writes() -> None:
    """The demo drove the analysis with `round:1` on every observation, so every
    map looked like one round with no segments. A fixture in a shape the real
    capture never produces proves nothing about the real page."""
    d = json.loads(DEMO.read_text(encoding="utf-8"))
    obs = [o for m in d["scrim_maps"] for o in m["observations"]]
    assert obs, "no observations in the demo"
    assert all("round_no" in o for o in obs), "demo observations use a field capture never writes"
    assert all("ts" in o for o in obs), "no timestamps, so swap ordering is unverifiable"
    assert any(o.get("sub_map") for o in obs), "no Control sub-maps"
    assert any(o.get("phase") == "attack" for o in obs), "no attack/defend phases"
    assert len({o["round_no"] for o in obs}) > 1, "every observation is in round 1"


def test_the_demo_snapshots_both_teams_in_the_same_frame() -> None:
    """A real snapshot reads both teams off one frame, so every timestamp carries
    both sides. The generator once emitted one side's whole sequence first, which
    left every swap with no enemy lineup recorded at or before it — the trigger
    analysis found nothing and looked broken rather than empty.
    """
    d = json.loads(DEMO.read_text(encoding="utf-8"))
    for m in d["scrim_maps"]:
        if m.get("void"):
            continue
        by_ts: dict[int, set[str]] = {}
        for o in m["observations"]:
            by_ts.setdefault(o["ts"], set()).add(o["side"])
        lonely = {ts: s for ts, s in by_ts.items() if s != {"a", "b"}}
        assert not lonely, f"{m['id']} has one-sided frames at {sorted(lonely)}"


def test_the_demo_shows_a_recurring_swap_with_a_trigger() -> None:
    """The swap panel is a headline feature; a sample that leaves it empty
    advertises the opposite of what it is meant to."""
    d = json.loads(DEMO.read_text(encoding="utf-8"))
    maps = json.dumps([m for m in d["scrim_maps"] if not m.get("void")])
    # Roles come from the page's own inference, which the extracted region does
    # not include — build the same map from the demo's heroes by GUID here.
    swaps = _run(f"return aggregateSwaps({maps}, 'b', {{}});")
    recurring = [s for s in swaps if s["count"] > 1]
    assert recurring, "the demo contains no recurring swap"
    assert any(s["vs"] for s in recurring), "no recurring swap has a trigger"


def test_the_viewers_role_table_agrees_with_the_authoritative_seats() -> None:
    """This page has no build step, so its hero->role table is a hand-kept copy of
    faceit_sync/subroles.py. It had already drifted: "D.Va", "Soldier: 76" and
    "Lifeweaver" are display spellings that refs.json never writes, so those
    heroes matched nothing and dropped out of every role split — and ten 2026
    heroes were absent entirely, landing in an "Other" card.

    A copy with no check is a copy that drifts, so this is the check.
    """
    from faceit_sync.subroles import SUBROLE

    base = {"Tank": "tank", "Hitscan": "damage", "Flex DPS": "damage",
            "Main Support": "support", "Flex Support": "support"}
    want: dict[str, str] = {}
    for hero, seat in SUBROLE.items():
        want[hero] = base[seat]

    got = _role_map()
    have = {h: role for role, heroes in got.items() for h in heroes}

    assert have == want, (
        f"role table disagrees with subroles.py — "
        f"missing {sorted(set(want) - set(have))}, "
        f"unknown {sorted(set(have) - set(want))}, "
        f"wrong {sorted(h for h in set(have) & set(want) if have[h] != want[h])}"
    )


def test_every_hero_a_capture_can_write_has_a_role() -> None:
    """Names come off refs.json, so anything in refs and not in the role table
    renders in an "Other" card that means nothing to a reader."""
    refs = json.loads((APP.parent / "capture" / "refs.json").read_text(encoding="utf-8"))["refs"]
    names = {r["n"] for r in refs if r.get("n")}
    got = _role_map()
    have = {h for heroes in got.values() for h in heroes}
    assert not (names - have), f"heroes with no role: {sorted(names - have)}"


def test_an_undated_scrim_is_never_hidden_by_a_range() -> None:
    """An auto-created block has no date until it is saved; losing it would look
    like data loss rather than filtering."""
    html = APP.read_text(encoding="utf-8")
    start = html.index("function applyRange(data)")
    body = html[start:start + 800]
    assert "if(!d) return true" in body.replace(" ", "").replace("if(!d)returntrue", "if(!d) return true") \
        or "if(!d) return true" in body, "undated scrims are not explicitly kept"

"""Derived-output statistics (SPEC §10): Wilson bound, sample-depth rendering,
fallback chain, and comp/player aggregation."""

from __future__ import annotations

from owscout.derive import (
    FallbackCell,
    ObsRow,
    aggregate_comps,
    choose_level,
    modal_comp,
    player_pool,
    render_rate,
    synthetic_comp,
    wilson_lower_bound,
)


# --- Wilson ------------------------------------------------------------------


def test_wilson_penalises_small_n() -> None:
    # 2/2 (100%) must score BELOW 18/20 (90%) — the whole point of §10.3.
    assert wilson_lower_bound(2, 2) < wilson_lower_bound(18, 20)


def test_wilson_bounds() -> None:
    assert wilson_lower_bound(0, 0) == 0.0
    assert 0.0 <= wilson_lower_bound(5, 10) <= 1.0
    # More evidence at the same rate raises the lower bound.
    assert wilson_lower_bound(50, 100) > wilson_lower_bound(5, 10)


# --- render_rate (sample-depth presentation rule) ----------------------------


def test_render_rate_below_min_is_raw_fraction() -> None:
    assert render_rate(2, 2, min_samples=5) == "2/2"       # never "100%"
    assert render_rate(1, 3, min_samples=5) == "1/3"


def test_render_rate_at_or_above_min_is_pct_with_n() -> None:
    assert render_rate(3, 6, min_samples=5) == "50% (n=6)"


def test_render_rate_zero() -> None:
    assert render_rate(0, 0) == "0/0"


# --- fallback chain ----------------------------------------------------------


def test_choose_level_first_meeting_min() -> None:
    cells = [FallbackCell("team+map", 2), FallbackCell("team+category", 6),
             FallbackCell("team+all", 30)]
    assert choose_level(cells, min_samples=5).level == "team+category"


def test_choose_level_falls_to_broadest_when_all_thin() -> None:
    cells = [FallbackCell("team+map", 1), FallbackCell("team+category", 2),
             FallbackCell("team+all", 3)]
    assert choose_level(cells, min_samples=5).level == "team+all"


def test_choose_level_takes_first_when_deep() -> None:
    cells = [FallbackCell("team+map", 8), FallbackCell("team+all", 40)]
    assert choose_level(cells, min_samples=5).level == "team+map"


# --- comp aggregation --------------------------------------------------------


def _obs(comp: str, mi: int, side: str, won: bool, map_guid: str = "m", team: str = "t") -> ObsRow:
    return ObsRow(comp_id=comp, hero_names=comp.upper(), map_instance_id=mi,
                  side=side, map_guid=map_guid, team_id=team, won=won)


def test_aggregate_sorted_by_wilson_not_winrate() -> None:
    rows = (
        # comp A: 1 map, won -> 100% but n=1
        [_obs("A", 1, "a", True)]
        # comp B: 6 maps, 5 wins -> 83% but much more evidence
        + [_obs("B", 10 + i, "a", i < 5) for i in range(6)]
    )
    stats = aggregate_comps(rows)
    assert stats[0].comp_id == "B"   # Wilson ranks B above the 100%-off-1 A
    a = next(s for s in stats if s.comp_id == "A")
    assert a.win_rate == 1.0 and a.wilson < stats[0].wilson


def test_win_attribution_is_proportional_on_shared_map() -> None:
    # One team-map, two comps (a swap): 3 samples of A, 1 of B; the map was won.
    rows = [_obs("A", 1, "a", True), _obs("A", 1, "a", True),
            _obs("A", 1, "a", True), _obs("B", 1, "a", True)]
    stats = {s.comp_id: s for s in aggregate_comps(rows)}
    assert round(stats["A"].games, 3) == 0.75    # 3/4 sample share
    assert round(stats["B"].games, 3) == 0.25
    assert round(stats["A"].wins, 3) == 0.75     # win split proportionally


def test_distinct_maps_and_teams_counted() -> None:
    rows = [_obs("A", 1, "a", True, map_guid="m1", team="t1"),
            _obs("A", 2, "a", False, map_guid="m2", team="t2")]
    s = aggregate_comps(rows)[0]
    assert s.distinct_maps == 2 and s.distinct_teams == 2 and s.samples == 2


# --- modal comp --------------------------------------------------------------


def test_modal_comp_by_maps_with_record() -> None:
    rows = [
        _obs("A", 1, "a", True), _obs("A", 2, "a", False),  # A on 2 maps: 1-1
        _obs("B", 3, "a", True),                            # B on 1 map
    ]
    mc = modal_comp(rows)
    assert mc is not None and mc.comp_id == "A"
    assert mc.maps == 2 and mc.wins == 1 and mc.losses == 1


def test_modal_comp_none_when_empty() -> None:
    assert modal_comp([]) is None


# --- synthetic comp ----------------------------------------------------------


def test_synthetic_comp_top_per_role() -> None:
    roles = {"tank1": "Tank", "tank2": "Tank", "d1": "Damage", "d2": "Damage",
             "s1": "Support", "s2": "Support"}
    guids = {"A": ["tank1", "d1", "d2", "s1", "s2"],
             "B": ["tank2", "d1", "d2", "s1", "s2"]}
    rows = [_obs("A", 1, "a", True), _obs("A", 2, "a", True), _obs("B", 3, "a", True)]
    synth = synthetic_comp(rows, roles, guids)
    picks: dict[str, list[str]] = {role: [] for role in ("Tank", "Damage", "Support")}
    for role, guid in synth:
        picks[role].append(guid)
    assert picks["Tank"] == ["tank1"]          # tank1 in 2 comps beats tank2 in 1
    assert len(picks["Damage"]) == 2 and len(picks["Support"]) == 2


# --- player pool -------------------------------------------------------------


def test_player_pool_by_distinct_maps() -> None:
    roles = {"g-winston": "Tank", "g-ram": "Tank"}
    # map 1: mostly Winston; map 2: Winston; map 3: Ramattra
    rows = [(1, "g-winston"), (1, "g-winston"), (1, "g-ram"),
            (2, "g-winston"), (3, "g-ram")]
    entries, total = player_pool(rows, roles)
    assert total == 3
    top = entries[0]
    assert top.hero_guid == "g-winston" and top.maps == 2
    assert round(top.pick_rate, 3) == round(2 / 3, 3)

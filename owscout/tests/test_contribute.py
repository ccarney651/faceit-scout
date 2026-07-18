"""The multi-contributor exchange format and the first-wins merge."""

from pathlib import Path
from typing import Any

from owscout.contribute import (
    CONTRIB_FORMAT,
    MapKey,
    merge_first_wins,
    to_obs_details,
)


def _contrib(who: str, maps: list[tuple[str, int, list[str]]]) -> dict[str, Any]:
    """A contribution claiming (match_id, game_no) with one observation each."""
    return {
        "format": CONTRIB_FORMAT, "contributor": who, "tool_version": "test",
        "maps": [{"match_id": mid, "game_no": g, "map_name": "Ilios",
                  "map_category": "Control", "side_a_team": "Alpha",
                  "side_b_team": "Bravo", "winner_side": "a", "bans": [],
                  "observations": [{"side": "a", "ts": 0, "sub_map": None,
                                    "round_no": 1, "phase": None, "heroes": heroes}]}
                 for mid, g, heroes in maps],
    }


def test_same_map_from_two_contributors_is_counted_once() -> None:
    """The bug this exists to prevent: merging on local ids double-counted a
    shared map, which inflates every rate that divides by map or round count."""
    alice = _contrib("alice", [("m1", 1, ["ram", "soj"])])
    bob = _contrib("bob", [("m1", 1, ["ram", "mei"])])     # SAME real game
    merged = merge_first_wins([alice, bob])
    assert len(merged.maps) == 1
    assert merged.owner[MapKey("m1", 1)] == "alice"        # first submission owns it
    assert merged.ignored == [("bob", MapKey("m1", 1))]
    assert merged.maps[MapKey("m1", 1)]["observations"][0]["heroes"] == ["ram", "soj"]


def test_contributor_can_update_their_own_map() -> None:
    """Strict first-wins would reject a contributor's own re-scout after they
    fixed a misread in Review - discarding the improvement, not a duplicate."""
    first = _contrib("alice", [("m1", 1, ["ram", "soj"])])
    fixed = _contrib("alice", [("m1", 1, ["ram", "mauga"])])
    merged = merge_first_wins([first, fixed])
    assert merged.maps[MapKey("m1", 1)]["observations"][0]["heroes"] == ["ram", "mauga"]
    assert merged.ignored == []


def test_different_maps_from_many_contributors_all_survive() -> None:
    merged = merge_first_wins([
        _contrib("alice", [("m1", 1, ["ram"])]),
        _contrib("bob", [("m1", 2, ["soj"])]),          # same match, different game
        _contrib("carol", [("m2", 1, ["mei"])]),
    ])
    assert len(merged.maps) == 3
    assert set(merged.owner.values()) == {"alice", "bob", "carol"}


def test_map_without_a_faceit_identity_is_skipped() -> None:
    """Local-only captures (scrims) have no globally meaningful identity, so they
    cannot be merged with anyone else's and must not enter the shared set."""
    bad = {"format": CONTRIB_FORMAT, "contributor": "alice", "tool_version": "t",
           "maps": [{"match_id": None, "game_no": None, "observations": []}]}
    assert merge_first_wins([bad]).maps == {}


def test_obs_details_never_leak_local_ids() -> None:
    """map_instance_id is re-issued per merge; two contributors' maps must land on
    distinct handles regardless of what either machine called them."""
    merged = merge_first_wins([
        _contrib("alice", [("m1", 1, ["ram"])]),
        _contrib("bob", [("m2", 1, ["soj"])]),
    ])
    rows = to_obs_details(merged.maps)
    assert len({r.map_instance_id for r in rows}) == 2
    assert all(isinstance(r.map_instance_id, int) for r in rows)


def test_curator_override_reassigns_a_map() -> None:
    """First-wins' weakness is that quality tracks who was fastest: a bad first
    submission locks a map. The committed override is the auditable fix."""
    alice = _contrib("alice", [("m1", 1, ["ram", "soj"])])     # first, but bad
    bob = _contrib("bob", [("m1", 1, ["ram", "mauga"])])
    merged = merge_first_wins([alice, bob], overrides={MapKey("m1", 1): "bob"})
    assert merged.owner[MapKey("m1", 1)] == "bob"
    assert merged.maps[MapKey("m1", 1)]["observations"][0]["heroes"] == ["ram", "mauga"]
    assert merged.ignored == [("alice", MapKey("m1", 1))]


def test_override_for_absent_contributor_falls_back() -> None:
    """An override naming someone with no view of the map must degrade to
    first-wins - never make the map vanish from the dataset."""
    alice = _contrib("alice", [("m1", 1, ["ram"])])
    merged = merge_first_wins([alice], overrides={MapKey("m1", 1): "ghost"})
    assert merged.owner[MapKey("m1", 1)] == "alice"
    assert MapKey("m1", 1) in merged.maps


def test_overrides_file_is_not_read_as_a_contribution(tmp_path: Path) -> None:
    """overrides.json lives in the same directory; it must be reserved, not
    loaded, warned about and skipped as a malformed contribution."""
    import json
    from owscout.contribute import contribution_files, load_overrides
    (tmp_path / "alice.json").write_text(json.dumps(
        _contrib("alice", [("m1", 1, ["ram"])])), encoding="utf-8")
    (tmp_path / "overrides.json").write_text(json.dumps(
        {"format": 1, "overrides": [
            {"match_id": "m1", "game_no": 1, "prefer": "bob",
             "reason": "alice had the wrong left team"}]}), encoding="utf-8")
    assert [p.name for p in contribution_files(tmp_path)] == ["alice.json"]
    assert load_overrides(tmp_path) == {MapKey("m1", 1): "bob"}


def test_malformed_overrides_degrade_to_first_wins(tmp_path: Path) -> None:
    from owscout.contribute import load_overrides
    (tmp_path / "overrides.json").write_text("{not json", encoding="utf-8")
    assert load_overrides(tmp_path) == {}

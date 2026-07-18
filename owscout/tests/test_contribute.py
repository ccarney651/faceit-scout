"""The multi-contributor exchange format and the first-wins merge."""

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

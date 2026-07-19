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


def _known(mid: str = "m1", game: int = 1, teams: tuple[str, str] = ("Alpha", "Bravo"),
           code: str | None = "CODE1") -> dict[MapKey, Any]:
    from owscout.contribute import KnownGame
    return {MapKey(mid, game): KnownGame(
        teams=frozenset(t.lower() for t in teams), demo_code=code)}


def test_invented_game_is_rejected() -> None:
    """The advertised trust property, now actually enforced: a contributed map
    must name a game FACEIT has a record of."""
    from owscout.contribute import validate_maps
    contrib = _contrib("alice", [("ghost-match", 1, ["ram"])])
    cleaned, rejects = validate_maps(contrib, _known())
    assert cleaned["maps"] == []
    assert "does not exist" in rejects[0][1]


def test_wrong_team_name_is_rejected() -> None:
    """The signature of scouting the WRONG replay code and attaching it to this
    match - which would silently poison another team's report."""
    from owscout.contribute import validate_maps
    contrib = _contrib("alice", [("m1", 1, ["ram"])])
    contrib["maps"][0]["side_a_team"] = "Imposters"
    cleaned, rejects = validate_maps(contrib, _known())
    assert cleaned["maps"] == [] and "did not play" in rejects[0][1]


def test_correct_map_passes_case_insensitively() -> None:
    from owscout.contribute import validate_maps
    contrib = _contrib("alice", [("m1", 1, ["ram"])])
    contrib["maps"][0].update(side_a_team="ALPHA", side_b_team="bravo",
                              demo_code="CODE1")
    cleaned, rejects = validate_maps(contrib, _known())
    assert len(cleaned["maps"]) == 1 and rejects == []


def test_code_mismatch_rejected_but_lenient_when_faceit_has_none() -> None:
    """Some matches never get a published code, yet the operator may hold one -
    that must pass. A code that CONTRADICTS a published one must not."""
    from owscout.contribute import validate_maps
    wrong = _contrib("alice", [("m1", 1, ["ram"])])
    wrong["maps"][0]["demo_code"] = "OTHER9"
    assert validate_maps(wrong, _known())[0]["maps"] == []
    lenient = _contrib("alice", [("m1", 1, ["ram"])])
    lenient["maps"][0]["demo_code"] = "OTHER9"
    assert len(validate_maps(lenient, _known(code=None))[0]["maps"]) == 1


def test_rejection_is_per_view_not_per_map() -> None:
    """Alice's bad view of a REAL game must not block Bob's good view: validation
    runs before ownership, so Bob still wins the map."""
    from owscout.contribute import merged_payload
    alice = _contrib("alice", [("m1", 1, ["ram", "soj"])])
    alice["maps"][0]["side_a_team"] = "Imposters"          # bad view, real game
    bob = _contrib("bob", [("m1", 1, ["ram", "mauga"])])
    payload = merged_payload([alice, bob], {"ram": "tank"}, {"ram": "RAM"},
                             known=_known())
    assert payload["maps_rejected"] == 1
    assert payload["maps_merged"] == 1                      # bob's view survived


class _FakeResp:
    def __init__(self, status: int, body: dict[str, Any] | None = None):
        self.status_code = status
        self._body: dict[str, Any] = body or {}

    def json(self) -> dict[str, Any]:
        return self._body


class _FakeSession:
    """Records the exact requests the client would send - no network."""

    def __init__(self, get_status: int = 404, get_body: dict[str, Any] | None = None):
        self.calls: list[tuple[Any, ...]] = []
        self._get = _FakeResp(get_status, get_body)

    def get(self, url: str, **kw: Any) -> _FakeResp:
        self.calls.append(("GET", url, kw))
        return self._get

    def put(self, url: str, **kw: Any) -> _FakeResp:
        self.calls.append(("PUT", url, kw))
        return _FakeResp(201, {"commit": {"sha": "abc123"}})


def test_push_creates_a_new_contribution_file() -> None:
    from owscout.contribute import push_contribution
    sess = _FakeSession(get_status=404)
    out = push_contribution(b'{"format":1}', repo="o/r", token="tok",
                            path="data/captures/alice.json", session=sess)
    assert out == {"action": "created", "commit": "abc123"}
    method, url, kw = sess.calls[-1]
    assert method == "PUT" and url.endswith("data/captures/alice.json")
    assert "sha" not in kw["json"]                      # create, not update
    assert kw["headers"]["Authorization"] == "Bearer tok"


def test_push_updates_with_the_existing_sha() -> None:
    """Re-publishing must UPDATE the contributor's file (self-update is the
    merge's improvement path), which the API only allows with the current sha."""
    from owscout.contribute import push_contribution
    sess = _FakeSession(get_status=200, get_body={"sha": "oldsha"})
    out = push_contribution(b"x", repo="o/r", token="t",
                            path="data/captures/alice.json", session=sess)
    assert out["action"] == "updated"
    assert sess.calls[-1][2]["json"]["sha"] == "oldsha"


def test_push_failures_carry_a_plain_hint() -> None:
    """Teammates will hit these, not read API docs: the message must say what to
    actually do."""
    import pytest
    from owscout.contribute import push_contribution

    class _Denied(_FakeSession):
        def put(self, url: str, **kw: Any) -> _FakeResp:
            return _FakeResp(401)

    with pytest.raises(RuntimeError, match="token is wrong or expired"):
        push_contribution(b"x", repo="o/r", token="bad",
                          path="p.json", session=_Denied())


def test_endpoint_push_sends_name_and_token_headers() -> None:
    """The open-access contract: identity travels in headers, the server forces
    it into the file - the body's contributor field is never trusted."""
    from owscout.contribute import push_to_endpoint

    class _Ok(_FakeSession):
        def post(self, url: str, **kw: Any) -> _FakeResp:
            self.calls.append(("POST", url, kw))
            return _FakeResp(200, {"action": "created", "maps": 3})

    sess = _Ok()
    out = push_to_endpoint(b"{}", endpoint="https://up.example/", name="alice",
                           token="t" * 24, session=sess)
    assert out["action"] == "created"
    _, _, kw = sess.calls[-1]
    assert kw["headers"]["X-Owscout-Name"] == "alice"
    assert kw["headers"]["X-Owscout-Token"] == "t" * 24


def test_endpoint_errors_surface_the_server_message() -> None:
    """The worker's messages are written for humans ('name is already used from
    another install') - the client must show them, not swallow them."""
    import pytest
    from owscout.contribute import push_to_endpoint

    class _Taken(_FakeSession):
        def post(self, url: str, **kw: Any) -> _FakeResp:
            return _FakeResp(403, {"error": "the name 'alice' is already used "
                                            "from another install"})

    with pytest.raises(RuntimeError, match="already used from another install"):
        push_to_endpoint(b"{}", endpoint="https://up.example/", name="alice",
                         token="t" * 24, session=_Taken())

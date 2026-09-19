"""The multi-contributor exchange format and the first-wins merge."""

from pathlib import Path
from typing import Any

from owdb.contribute import (
    CONTRIB_FORMAT,
    MapKey,
    load_excludes,
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


def test_exclude_undoes_an_accidental_publish() -> None:
    """The un-scout escape hatch: an excluded map leaves the merge entirely, so
    it's neither in the report nor the captured feed - the code frees up again."""
    alice = _contrib("alice", [("m1", 1, ["ram"]), ("m1", 2, ["soj"])])
    merged = merge_first_wins([alice], excludes={MapKey("m1", 2)})
    assert MapKey("m1", 1) in merged.maps        # the good map stays
    assert MapKey("m1", 2) not in merged.maps    # the excluded one is gone
    assert ("alice", MapKey("m1", 2)) in merged.ignored


def test_load_excludes_reads_the_overrides_file(tmp_path: Path) -> None:
    (tmp_path / "overrides.json").write_text(
        '{"exclude": [{"match_id": "1-abc", "game_no": 2}]}', encoding="utf-8")
    assert load_excludes(tmp_path) == {MapKey("1-abc", 2)}


def test_load_excludes_degrades_on_missing_or_malformed(tmp_path: Path) -> None:
    assert load_excludes(tmp_path) == set()          # no file
    (tmp_path / "overrides.json").write_text("{ not json", encoding="utf-8")
    assert load_excludes(tmp_path) == set()          # malformed -> empty, no raise


def test_excluded_map_leaves_the_captured_feed() -> None:
    """End to end through merged_payload: the excluded game is absent from
    captured_games, which is exactly what un-hides it in the apps."""
    from owdb.contribute import merged_payload
    alice = _contrib("alice", [("m1", 1, ["ram"]), ("m1", 2, ["soj"])])
    payload = merged_payload([alice], {}, {"ram": "Ramattra", "soj": "Sojourn"},
                             excludes={MapKey("m1", 2)})
    assert "m1:1" in payload["captured_games"]
    assert "m1:2" not in payload["captured_games"]
    assert payload["maps_excluded"] == 1


def test_captured_durations_carries_measured_map_lengths() -> None:
    """The replay bot measures each map's real length off the scrubber bar. That
    must reach the payload keyed by the same 'match_id:game_no' as
    captured_games — and a map without a measurement (a browser capture, or an
    old artifact) must not appear as a bogus duration."""
    from owdb.contribute import merged_payload
    alice = _contrib("alice", [("m1", 1, ["ram"]), ("m1", 2, ["soj"])])
    alice["maps"][0]["duration_sec"] = 840
    payload = merged_payload([alice], {}, {"ram": "Ramattra", "soj": "Sojourn"})
    assert payload["captured_durations"] == {"m1:1": 840}
    assert "m1:2" not in payload["captured_durations"]


def test_overrides_file_is_not_read_as_a_contribution(tmp_path: Path) -> None:
    """overrides.json lives in the same directory; it must be reserved, not
    loaded, warned about and skipped as a malformed contribution."""
    import json

    from owdb.contribute import contribution_files, load_overrides
    (tmp_path / "alice.json").write_text(json.dumps(
        _contrib("alice", [("m1", 1, ["ram"])])), encoding="utf-8")
    (tmp_path / "overrides.json").write_text(json.dumps(
        {"format": 1, "overrides": [
            {"match_id": "m1", "game_no": 1, "prefer": "bob",
             "reason": "alice had the wrong left team"}]}), encoding="utf-8")
    assert [p.name for p in contribution_files(tmp_path)] == ["alice.json"]
    assert load_overrides(tmp_path) == {MapKey("m1", 1): "bob"}


def test_malformed_overrides_degrade_to_first_wins(tmp_path: Path) -> None:
    from owdb.contribute import load_overrides
    (tmp_path / "overrides.json").write_text("{not json", encoding="utf-8")
    assert load_overrides(tmp_path) == {}


def _known(mid: str = "m1", game: int = 1, teams: tuple[str, str] = ("Alpha", "Bravo"),
           code: str | None = "CODE1") -> dict[MapKey, Any]:
    from owdb.contribute import KnownGame
    return {MapKey(mid, game): KnownGame(
        teams=frozenset(t.lower() for t in teams), demo_code=code)}


def test_invented_game_is_rejected() -> None:
    """The advertised trust property, now actually enforced: a contributed map
    must name a game FACEIT has a record of."""
    from owdb.contribute import validate_maps
    contrib = _contrib("alice", [("ghost-match", 1, ["ram"])])
    cleaned, rejects = validate_maps(contrib, _known())
    assert cleaned["maps"] == []
    assert "does not exist" in rejects[0][1]


def test_wrong_team_name_is_rejected() -> None:
    """The signature of scouting the WRONG replay code and attaching it to this
    match - which would silently poison another team's report."""
    from owdb.contribute import validate_maps
    contrib = _contrib("alice", [("m1", 1, ["ram"])])
    contrib["maps"][0]["side_a_team"] = "Imposters"
    cleaned, rejects = validate_maps(contrib, _known())
    assert cleaned["maps"] == [] and "did not play" in rejects[0][1]


def test_correct_map_passes_case_insensitively() -> None:
    from owdb.contribute import validate_maps
    contrib = _contrib("alice", [("m1", 1, ["ram"])])
    contrib["maps"][0].update(side_a_team="ALPHA", side_b_team="bravo",
                              demo_code="CODE1")
    cleaned, rejects = validate_maps(contrib, _known())
    assert len(cleaned["maps"]) == 1 and rejects == []


def test_code_mismatch_rejected_but_lenient_when_faceit_has_none() -> None:
    """Some matches never get a published code, yet the operator may hold one -
    that must pass. A code that CONTRADICTS a published one must not."""
    from owdb.contribute import validate_maps
    wrong = _contrib("alice", [("m1", 1, ["ram"])])
    wrong["maps"][0]["demo_code"] = "OTHER9"
    assert validate_maps(wrong, _known())[0]["maps"] == []
    lenient = _contrib("alice", [("m1", 1, ["ram"])])
    lenient["maps"][0]["demo_code"] = "OTHER9"
    assert len(validate_maps(lenient, _known(code=None))[0]["maps"]) == 1


def test_rejection_is_per_view_not_per_map() -> None:
    """Alice's bad view of a REAL game must not block Bob's good view: validation
    runs before ownership, so Bob still wins the map."""
    from owdb.contribute import merged_payload
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
    from owdb.contribute import push_contribution
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
    from owdb.contribute import push_contribution
    sess = _FakeSession(get_status=200, get_body={"sha": "oldsha"})
    out = push_contribution(b"x", repo="o/r", token="t",
                            path="data/captures/alice.json", session=sess)
    assert out["action"] == "updated"
    assert sess.calls[-1][2]["json"]["sha"] == "oldsha"


def test_push_failures_carry_a_plain_hint() -> None:
    """Teammates will hit these, not read API docs: the message must say what to
    actually do."""
    import pytest

    from owdb.contribute import push_contribution

    class _Denied(_FakeSession):
        def put(self, url: str, **kw: Any) -> _FakeResp:
            return _FakeResp(401)

    with pytest.raises(RuntimeError, match="token is wrong or expired"):
        push_contribution(b"x", repo="o/r", token="bad",
                          path="p.json", session=_Denied())


def test_endpoint_push_sends_name_and_token_headers() -> None:
    """The open-access contract: identity travels in headers, the server forces
    it into the file - the body's contributor field is never trusted."""
    from owdb.contribute import push_to_endpoint

    class _Ok(_FakeSession):
        def post(self, url: str, **kw: Any) -> _FakeResp:
            self.calls.append(("POST", url, kw))
            return _FakeResp(200, {"action": "created", "maps": 3})

    sess = _Ok()
    out = push_to_endpoint(b"{}", endpoint="https://up.example/", name="alice",
                           token="t" * 24, session=sess)
    assert out["action"] == "created"
    _, _, kw = sess.calls[-1]
    assert kw["headers"]["X-Owdb-Name"] == "alice"
    assert kw["headers"]["X-Owdb-Token"] == "t" * 24


def test_endpoint_errors_surface_the_server_message() -> None:
    """The worker's messages are written for humans ('name is already used from
    another install') - the client must show them, not swallow them."""
    import pytest

    from owdb.contribute import push_to_endpoint

    class _Taken(_FakeSession):
        def post(self, url: str, **kw: Any) -> _FakeResp:
            return _FakeResp(403, {"error": "the name 'alice' is already used "
                                            "from another install"})

    with pytest.raises(RuntimeError, match="already used from another install"):
        push_to_endpoint(b"{}", endpoint="https://up.example/", name="alice",
                         token="t" * 24, session=_Taken())


def test_player_pools_from_slot_pairs() -> None:
    """Player attribution rides as (hero, player) pairs straight from comp_slots
    - the canonical comp is sorted, so zipping it with players would scramble
    who played what."""
    from owdb.contribute import MapKey, player_pools
    maps = {MapKey("m1", 1): {
        "side_a_team": "Alpha", "side_b_team": "Bravo",
        "observations": [
            {"side": "a", "ts": 0, "round_no": 1, "sub_map": None,
             "heroes": ["ram", "soj"],
             "pairs": [["ram", "p1"], ["soj", "p2"]]},
            {"side": "a", "ts": 50, "round_no": 2, "sub_map": None,
             "heroes": ["ram", "mei"],
             "pairs": [["ram", "p1"], ["mei", None]]},   # unresolved slot
        ],
    }}
    pools = player_pools(maps, {"p1": "Javi44", "p2": "BuFayez2"},
                         {"ram": "RAM", "soj": "SOJ", "mei": "MEI"})
    alpha = {p["player"]: p for p in pools["Alpha"]}
    assert alpha["Javi44"]["rounds"] == 2
    assert alpha["Javi44"]["heroes"][0] == {"hero": "RAM", "rounds": 2, "share": 1.0}
    assert alpha["BuFayez2"]["rounds"] == 1
    # the unresolved MEI slot attributed to nobody - never guessed
    assert all(h["hero"] != "MEI" for p in pools["Alpha"] for h in p["heroes"])


def test_player_pools_splits_a_swapped_round_by_segment_duration() -> None:
    """A mid-round swap (two observations sharing one round_no, different
    heroes) must split that round's credit proportionally to how long each
    hero's segment measured - not credit both a full round (the bug the old
    round-key-set dedup had) and not drop either (the bug voting-to-one-
    winner had before segmentation existed)."""
    import pytest
    from owdb.contribute import MapKey, player_pools
    maps = {MapKey("m1", 1): {
        "side_a_team": "Alpha", "side_b_team": "Bravo",
        "observations": [
            {"side": "a", "ts": 0, "round_no": 1, "sub_map": None,
             "heroes": ["dva"], "pairs": [["dva", "p1"]]},
            {"side": "a", "ts": 180000, "round_no": 1, "sub_map": None,
             "heroes": ["dmon"], "pairs": [["dmon", "p1"]]},
            {"side": "a", "ts": 240000, "round_no": 1, "sub_map": None,
             "heroes": ["dmon"], "pairs": [["dmon", "p1"]]},
        ],
    }}
    pools = player_pools(maps, {"p1": "Javi44"}, {"dva": "D.Va", "dmon": "D.Mon"})
    heroes = {h["hero"]: h for h in pools["Alpha"][0]["heroes"]}
    # segment durations: DVA 0->180000ms (180s), D.Mon 180000->240000ms (60s,
    # closed out by the round's own last observed ts, not a next round)
    assert heroes["D.Va"]["rounds"] == pytest.approx(0.75, abs=0.01)
    assert heroes["D.Mon"]["rounds"] == pytest.approx(0.25, abs=0.01)
    assert pools["Alpha"][0]["rounds"] == pytest.approx(1.0, abs=0.01)


def test_primary_hero_per_game_weights_by_duration_not_round_count() -> None:
    """A player who spent most of a swapped round on the second hero should be
    attributed to that hero, not whichever hero merely appeared in more
    distinct rounds."""
    from owdb.contribute import MapKey, rank_player_heroes
    maps = {MapKey("m1", 1): {
        "observations": [
            {"side": "a", "ts": 0, "round_no": 1, "sub_map": None,
             "pairs": [["dva", "p1"]]},
            {"side": "a", "ts": 10000, "round_no": 1, "sub_map": None,
             "pairs": [["dmon", "p1"]]},
            {"side": "a", "ts": 290000, "round_no": 1, "sub_map": None,
             "pairs": [["dmon", "p1"]]},
        ],
    }}
    stats = {("m1", 1, "p1"): {"elims": 5, "deaths": 4, "damage": 2000,
                               "healing": 0, "mitigation": 800, "captured": True}}
    ranks = rank_player_heroes(maps, stats, {"dva": "tank", "dmon": "tank"})
    # D.Mon held the slot 10s -> 290s (280s) vs D.Va's 0s -> 10s (10s), so the
    # whole game's stat line attributes to D.Mon.
    assert ("p1", "dmon") in ranks
    assert ranks[("p1", "dmon")]["games"] == 1


def test_observations_without_pairs_are_simply_absent() -> None:
    """Captures made before OCR attribution have no pairs; they must not crash
    or fabricate players."""
    from owdb.contribute import MapKey, player_pools
    maps = {MapKey("m1", 1): {
        "side_a_team": "Alpha", "side_b_team": None,
        "observations": [{"side": "a", "ts": 0, "heroes": ["ram"]}],
    }}
    assert player_pools(maps, {}, {}) == {}


def test_per_game_players_rides_hero_player_pairs() -> None:
    """(hero, player) pairs per observation become a per-game, per-player hero map
    ('mid:gno' -> {nick: hero name}) for the site's per-map stat tables."""
    from owdb.contribute import merged_payload
    alice = _contrib("alice", [("m1", 1, ["ram", "soj"]), ("m1", 2, ["ram"])])
    alice["maps"][0]["observations"][0]["pairs"] = [["ram", "p1"], ["soj", "p2"]]
    alice["maps"][1]["observations"][0]["pairs"] = [["ram", "p1"]]
    payload = merged_payload(
        [alice], {}, {"ram": "Ramattra", "soj": "Sojourn"},
        player_names={"p1": "Javi44", "p2": "BuFayez2"})
    assert payload["per_game_players"]["m1:1"] == {
        "Javi44": "Ramattra", "BuFayez2": "Sojourn"}
    assert payload["per_game_players"]["m1:2"] == {"Javi44": "Ramattra"}


def test_per_game_players_skips_unknown_player_ids() -> None:
    """A pair whose player id has no nickname in the faceit roster can't be shown
    as a row - it must be omitted, not crash or emit an empty-nick key."""
    from owdb.contribute import merged_payload
    alice = _contrib("alice", [("m1", 1, ["ram"])])
    alice["maps"][0]["observations"][0]["pairs"] = [["ram", "ghost-id"]]
    payload = merged_payload([alice], {}, {"ram": "Ramattra"}, player_names={})
    assert payload["per_game_players"] == {}


def test_captured_feed_parses() -> None:
    from owdb.contribute import fetch_captured_games

    class _Feed(_FakeSession):
        def get(self, url: str, **kw: Any) -> _FakeResp:
            return _FakeResp(200, {"format": 1, "captured": ["m1:1", "m2:3"]})

    assert fetch_captured_games(session=_Feed()) == {"m1:1", "m2:3"}


def test_captured_feed_never_blocks_scouting() -> None:
    """Offline, a 404, or a format this build cannot read must all degrade to
    'nothing known to be claimed' - never to an error that stops the operator
    picking a code."""
    from owdb.contribute import fetch_captured_games

    class _Down(_FakeSession):
        def get(self, url: str, **kw: Any) -> _FakeResp:
            raise OSError("no network")

    class _Missing(_FakeSession):
        def get(self, url: str, **kw: Any) -> _FakeResp:
            return _FakeResp(404)

    class _Future(_FakeSession):
        def get(self, url: str, **kw: Any) -> _FakeResp:
            return _FakeResp(200, {"format": 99, "captured": ["m1:1"]})

    assert fetch_captured_games(session=_Down()) == set()
    assert fetch_captured_games(session=_Missing()) == set()
    assert fetch_captured_games(session=_Future()) == set()


def test_rank_player_heroes_tank_weights_kd_over_damage() -> None:
    """Operator call: tank blend leads with k/d (elims/deaths), then deaths, then
    damage. A great-k/d, modest-damage tank must out-rank a big-damage, poor-k/d
    one on the same hero."""
    from owdb.contribute import MapKey, rank_player_heroes

    maps: dict[Any, Any] = {}
    stats: dict[Any, Any] = {}

    def add(pid: str, mid: str, elims: int, deaths: int, dmg: int) -> None:
        for gno in (1, 2):                      # 2 games each -> confident
            maps[MapKey(mid, gno)] = {
                "observations": [{"side": "a", "round_no": 1, "sub_map": None,
                                  "pairs": [["ram", pid]]}]}
            stats[(mid, gno, pid)] = {"elims": elims, "deaths": deaths, "damage": dmg,
                                      "healing": 0, "mitigation": 2000, "captured": True}

    add("P1", "M1", 20, 2, 4000)                # k/d 10, lowest damage
    add("P2", "M2", 12, 4, 6000)                # k/d 3
    add("P3", "M3", 8, 8, 9000)                 # k/d 1, highest damage
    ranks = rank_player_heroes(maps, stats, {"ram": "tank"})

    assert ranks[("P1", "ram")]["rank"] == 1    # best k/d wins despite least damage
    assert ranks[("P3", "ram")]["rank"] == 3    # most damage can't save worst k/d
    assert ranks[("P1", "ram")]["avg"]["kd"] == 10.0


def test_rank_player_heroes_thin_group_keeps_avg_but_no_rank() -> None:
    """A hero only one captured player has played can't be ranked - the average
    is still returned, but no rank/of/pct (they'd be a meaningless '1 of 1')."""
    from owdb.contribute import MapKey, rank_player_heroes

    maps = {MapKey("M1", 1): {"side_a_team": "A", "side_b_team": "B",
            "observations": [{"side": "a", "round_no": 1, "sub_map": None,
                              "pairs": [["ana", "P1"]]}]}}
    stats = {("M1", 1, "P1"): {"elims": 5, "deaths": 4, "damage": 2000,
                               "healing": 6000, "mitigation": 800, "captured": True}}
    info = rank_player_heroes(maps, stats, {"ana": "support"})[("P1", "ana")]
    assert "rank" not in info
    assert info["avg"]["healing"] == 6000 and info["games"] == 1


def test_rank_player_heroes_scopes_by_division() -> None:
    """Tier safety: a Master pool and an Expert player on the same hero must not
    pool. The Master group of 3 ranks among itself (of==3, not 4), and the lone
    Expert player - a group of 1 - gets no rank."""
    from owdb.contribute import MapKey, rank_player_heroes

    maps: dict[Any, Any] = {}
    stats: dict[Any, Any] = {}

    def add(pid: str, mid: str, champ: str, dmg: int) -> None:
        for gno in (1, 2):
            maps[MapKey(mid, gno)] = {"observations": [
                {"side": "a", "round_no": 1, "sub_map": None, "pairs": [["ram", pid]]}]}
            stats[(mid, gno, pid)] = {"elims": 10, "deaths": 4, "damage": dmg,
                                      "healing": 0, "mitigation": 2000,
                                      "champ": champ, "captured": True}

    add("P1", "M1", "emea-master", 8000)
    add("P2", "M2", "emea-master", 5000)
    add("P3", "M3", "emea-master", 3000)
    add("PX", "MX", "emea-expert", 9999)      # different pool - must not mix in
    ranks = rank_player_heroes(maps, stats, {"ram": "tank"})

    assert ranks[("P1", "ram")]["of"] == 3    # 3 Master players, not 4
    assert ranks[("P1", "ram")]["rank"] == 1
    assert "rank" not in ranks[("PX", "ram")]  # Expert group of 1 -> unranked


def test_rank_player_heroes_splits_low_data_players() -> None:
    """Low-data players (< confident_min games) are still ranked, but SEPARATELY,
    so a one-game sample never outranks a real one. The caller lists them apart."""
    from owdb.contribute import MapKey, rank_player_heroes

    maps: dict[Any, Any] = {}
    stats: dict[Any, Any] = {}

    def add(pid: str, mid: str, ngames: int, dmg: int) -> None:
        for gno in range(1, ngames + 1):
            maps[MapKey(mid, gno)] = {"observations": [
                {"side": "a", "round_no": 1, "sub_map": None, "pairs": [["ram", pid]]}]}
            stats[(mid, gno, pid)] = {"elims": 10, "deaths": 4, "damage": dmg,
                                      "healing": 0, "mitigation": 2000,
                                      "champ": "em", "captured": True}

    add("P1", "M1", 2, 9000)
    add("P2", "M2", 2, 6000)
    add("P3", "M3", 1, 3000)          # one game -> low_data, ranked separately
    ranks = rank_player_heroes(maps, stats, {"ram": "tank"})
    # confident players ranked among themselves
    assert ranks[("P1", "ram")]["low_data"] is False and ranks[("P1", "ram")]["rank"] == 1
    assert ranks[("P2", "ram")]["low_data"] is False and ranks[("P2", "ram")]["of"] == 2
    # the single-game player is included but ranked in the low-data list
    assert ranks[("P3", "ram")]["low_data"] is True
    assert ranks[("P3", "ram")]["rank"] == 1 and ranks[("P3", "ram")]["of"] == 1
    assert ranks[("P3", "ram")]["games"] == 1


# --- season scoping --------------------------------------------------------
# data/captures/<season>/ was the ONLY thing scoping a contribution to a season,
# and a directory cannot scope what is inside the file placed in it. On
# 2026-09-08 a publish of two S10 matches carried 31 S9 playoff maps with it -
# the browser page uploads every map in its IndexedDB - and 25 of them reached
# the live site as season 10 coverage. These pin the guard that stops it.

def _known_seasons() -> dict[MapKey, Any]:
    from owdb.contribute import KnownGame
    teams = frozenset({"alpha", "bravo"})
    return {
        MapKey("m1", 1): KnownGame(teams=teams, demo_code="CODE1", season="s10"),
        MapKey("old", 1): KnownGame(teams=teams, demo_code="CODE1", season="s9"),
        MapKey("new", 1): KnownGame(teams=teams, demo_code="CODE1", season=None),
    }


def test_map_from_another_season_is_rejected() -> None:
    from owdb.contribute import validate_maps
    contrib = _contrib("alice", [("old", 1, ["ram"])])
    cleaned, rejects = validate_maps(contrib, _known_seasons(), season="s10")
    assert cleaned["maps"] == []
    assert "s9" in rejects[0][1] and "s10" in rejects[0][1], rejects


def test_map_from_this_season_passes() -> None:
    from owdb.contribute import validate_maps
    contrib = _contrib("alice", [("m1", 1, ["ram"])])
    cleaned, rejects = validate_maps(contrib, _known_seasons(), season="s10")
    assert len(cleaned["maps"]) == 1 and rejects == []


def test_unresolvable_season_is_kept() -> None:
    """The rule that matters most. A match FACEIT has not filed under a
    championship yet - which is every match played in the hours after a season
    opens - must NOT be thrown out. Dropping only what provably belongs to
    ANOTHER season is what separates the mistake from the real work."""
    from owdb.contribute import validate_maps
    contrib = _contrib("alice", [("new", 1, ["ram"])])
    cleaned, rejects = validate_maps(contrib, _known_seasons(), season="s10")
    assert len(cleaned["maps"]) == 1 and rejects == []


def test_no_target_season_checks_nothing() -> None:
    """Callers that do not name a season keep the old behaviour exactly."""
    from owdb.contribute import validate_maps
    contrib = _contrib("alice", [("old", 1, ["ram"])])
    assert len(validate_maps(contrib, _known_seasons())[0]["maps"]) == 1


# --- the screen code -------------------------------------------------------
# Every identifying field on a captured map (match_id, game_no, code, both team
# names) comes from the operator's SELECTION; only the comps come from the
# screen. A capture filed against the wrong match is therefore internally
# consistent and passes every check here - the game exists, the season matches,
# the teams are the ones FACEIT lists, the code agrees. The browser is the only
# witness that anything was wrong, so it now sends what it read.

def test_a_map_whose_screen_code_contradicts_its_filing_is_rejected() -> None:
    from owdb.contribute import validate_maps
    contrib = _contrib("alice", [("m1", 1, ["ram"])])
    contrib["maps"][0].update(demo_code="CODE1", screen_code="OTHER9")
    cleaned, rejects = validate_maps(contrib, _known())
    assert cleaned["maps"] == []
    assert "OTHER9" in rejects[0][1] and "CODE1" in rejects[0][1], rejects


def test_a_screen_code_that_agrees_passes() -> None:
    from owdb.contribute import validate_maps
    contrib = _contrib("alice", [("m1", 1, ["ram"])])
    contrib["maps"][0].update(demo_code="CODE1", screen_code="CODE1")
    cleaned, rejects = validate_maps(contrib, _known())
    assert len(cleaned["maps"]) == 1 and rejects == []


def test_an_absent_screen_code_is_not_evidence_of_anything() -> None:
    """The banner is not always on screen and OCR can simply fail. Absence must
    mean unknown, never wrong - the same rule the season guard follows."""
    from owdb.contribute import validate_maps
    for missing in ({}, {"screen_code": None}, {"screen_code": ""}):
        contrib = _contrib("alice", [("m1", 1, ["ram"])])
        contrib["maps"][0].update(demo_code="CODE1", **missing)
        cleaned, rejects = validate_maps(contrib, _known())
        assert len(cleaned["maps"]) == 1, (missing, rejects)


def test_a_snapshot_taken_under_a_different_code_rejects_the_map() -> None:
    """The replay changing mid-map is the case per-observation codes exist for:
    the map is filed under a code that really was on screen once, so nothing at
    map level looks wrong. Two matches under one code is the same wrong
    attribution, only harder to see."""
    from owdb.contribute import validate_maps
    contrib = _contrib("alice", [("m1", 1, ["ram"])])
    m = contrib["maps"][0]
    m.update(demo_code="CODE1", screen_code="CODE1")
    m["observations"] = [{"side": "a", "heroes": ["ram"], "screen_code": "CODE1"},
                         {"side": "b", "heroes": ["ana"], "screen_code": "OTHER9"}]
    cleaned, rejects = validate_maps(contrib, _known())
    assert cleaned["maps"] == []
    assert "OTHER9" in rejects[0][1], rejects


def test_a_verified_view_outranks_an_earlier_unverified_one() -> None:
    """First-wins decides who owns a map, and quality is then a function of who
    was fastest. A view that confirmed the replay code off the screen is better
    evidence than one that never could, so it wins regardless of order - the
    losing view is still retained, exactly as first-wins already retains it."""
    from owdb.contribute import merge_first_wins
    early = _contrib("alice", [("m1", 1, ["ram"])])          # no screen_code
    late = _contrib("bob", [("m1", 1, ["ana"])])
    late["maps"][0]["screen_code"] = "CODE1"
    res = merge_first_wins([early, late])
    assert res.owner[MapKey("m1", 1)] == "bob"
    assert ("alice", MapKey("m1", 1)) in res.ignored, "the losing view is kept"


def test_first_wins_still_decides_between_two_verified_views() -> None:
    from owdb.contribute import merge_first_wins
    a = _contrib("alice", [("m1", 1, ["ram"])]); a["maps"][0]["screen_code"] = "CODE1"
    b = _contrib("bob", [("m1", 1, ["ana"])]); b["maps"][0]["screen_code"] = "CODE1"
    assert merge_first_wins([a, b]).owner[MapKey("m1", 1)] == "alice"


def test_an_override_still_beats_a_verified_view() -> None:
    """The curator's escape hatch stays the last word."""
    from owdb.contribute import merge_first_wins
    early = _contrib("alice", [("m1", 1, ["ram"])])
    late = _contrib("bob", [("m1", 1, ["ana"])]); late["maps"][0]["screen_code"] = "CODE1"
    res = merge_first_wins([early, late], overrides={MapKey("m1", 1): "alice"})
    assert res.owner[MapKey("m1", 1)] == "alice"


# --- FACEIT owns the result and the bans ----------------------------------
#
# Both live capture paths (replay bot and browser) write winner_side=None and
# bans=[], on the grounds that FACEIT already has them. Nothing put them back,
# so from S10 onwards every captured comp on the site read 0 wins and the ban
# reads were empty league-wide (found 2026-09-19: 298/298 bot maps). The merge
# is where FACEIT's record and the capture meet, so it is filled here - which
# also repairs every past capture on the next CI rebuild.

def _known_result(winner: str | None = "bravo",
                  bans: tuple[str, ...] = ()) -> dict[MapKey, Any]:
    from owdb.contribute import KnownGame
    return {MapKey("m1", 1): KnownGame(
        teams=frozenset({"alpha", "bravo"}), demo_code="CODE1",
        winner=winner, bans=bans)}


def _one_map(**over: Any) -> dict[str, Any]:
    c = _contrib("alice", [("m1", 1, ["ram"])])
    c["maps"][0].update(over)
    return c


def test_faceit_winner_fills_a_capture_that_left_it_blank() -> None:
    from owdb.contribute import validate_maps
    cleaned, _ = validate_maps(_one_map(winner_side=None), _known_result())
    assert cleaned["maps"][0]["winner_side"] == "b"


def test_faceit_winner_follows_the_captures_own_orientation() -> None:
    """Side a/b is whichever team the capture put on the left, not FACEIT's
    faction1 - getting this backwards would credit every win to the loser."""
    from owdb.contribute import validate_maps
    cleaned, _ = validate_maps(
        _one_map(winner_side=None, side_a_team="Bravo", side_b_team="Alpha"),
        _known_result())
    assert cleaned["maps"][0]["winner_side"] == "a"


def test_faceit_winner_overrides_a_contributed_one() -> None:
    from owdb.contribute import validate_maps
    cleaned, _ = validate_maps(_one_map(winner_side="a"), _known_result())
    assert cleaned["maps"][0]["winner_side"] == "b"


def test_no_faceit_winner_keeps_the_contributed_one() -> None:
    from owdb.contribute import validate_maps
    cleaned, _ = validate_maps(_one_map(winner_side="a"), _known_result(winner=None))
    assert cleaned["maps"][0]["winner_side"] == "a"


def test_faceit_bans_fill_an_empty_list_in_ban_order() -> None:
    from owdb.contribute import validate_maps
    cleaned, _ = validate_maps(_one_map(bans=[]),
                               _known_result(bans=("0xFIRST", "0xSECOND")))
    assert cleaned["maps"][0]["bans"] == ["0xFIRST", "0xSECOND"]


def test_no_faceit_bans_keeps_the_contributed_list() -> None:
    from owdb.contribute import validate_maps
    cleaned, _ = validate_maps(_one_map(bans=["0xMINE"]), _known_result(bans=()))
    assert cleaned["maps"][0]["bans"] == ["0xMINE"]


def test_the_contribution_itself_is_not_mutated() -> None:
    from owdb.contribute import validate_maps
    contrib = _one_map(winner_side=None)
    validate_maps(contrib, _known_result())
    assert contrib["maps"][0]["winner_side"] is None


def test_a_filled_winner_reaches_the_comp_record() -> None:
    """The end the bug was visible at: a captured comp's W-L."""
    from owdb.contribute import to_obs_rows, validate_maps
    cleaned, _ = validate_maps(_one_map(winner_side=None, observations=[
        {"side": "b", "ts": 0, "sub_map": None, "round_no": 1, "phase": None,
         "heroes": ["ram"]}]), _known_result())
    maps = {MapKey("m1", 1): cleaned["maps"][0]}
    rows = to_obs_rows(maps, {"ram": "tank"}, {"ram": "Ramattra"})
    assert [r.won for r in rows] == [True]


# --- sentinel guids are slot states, never heroes -------------------------
#
# ABSENT / UNSELECTED / DEAD are what a capture reads for an empty card, the
# grey pre-lock-in silhouette, and a death marker. The merge writes `heroes`
# into comps verbatim, so one arriving from ANY contributor becomes a hero
# called "ABSENT" on the site. Filtered here because this is the one place
# every contributor's data passes through.

def test_sentinel_guids_are_dropped_at_ingest() -> None:
    from owdb.contribute import validate_maps
    contrib = _one_map(observations=[{
        "side": "a", "ts": 0, "sub_map": None, "round_no": 1, "phase": None,
        "heroes": ["ram", "ABSENT", "UNSELECTED", "DEAD", "soj"],
        "pairs": [["ram", "p1"], ["ABSENT", "p2"], ["UNSELECTED", None],
                  ["DEAD", "p4"], ["soj", "p5"]]}])
    cleaned, _ = validate_maps(contrib, _known_result())
    o = cleaned["maps"][0]["observations"][0]
    assert o["heroes"] == ["ram", "soj"]
    assert o["pairs"] == [["ram", "p1"], ["soj", "p5"]]


def test_an_observation_of_nothing_but_sentinels_is_dropped() -> None:
    from owdb.contribute import validate_maps
    contrib = _one_map(observations=[
        {"side": "a", "ts": 0, "sub_map": None, "round_no": 1, "phase": None,
         "heroes": ["ram"]},
        {"side": "b", "ts": 0, "sub_map": None, "round_no": 1, "phase": None,
         "heroes": ["ABSENT", "ABSENT"]}])
    cleaned, _ = validate_maps(contrib, _known_result())
    assert [o["side"] for o in cleaned["maps"][0]["observations"]] == ["a"]


# --- team identity is the FACEIT team id, not its name ---------------------
#
# FACEIT teams rename at any time, even after the roster lock, and validation
# re-runs against CURRENT names on every CI build. Checked by name, a map that
# was accepted when captured is silently dropped the week its team renames:
# 54 of 298 S10 bot maps on 2026-09-19 ("VTY Velociraptors" is now
# "VTY Nine Lives"), and 33 of 62 of one contributor's S9 maps by season end.
# Every contribution carries side_{a,b}_team_id; names stay only as a fallback.

def _known_ids(winner_id: str | None = "t2") -> dict[MapKey, Any]:
    from owdb.contribute import KnownGame
    return {MapKey("m1", 1): KnownGame(
        teams=frozenset({"new alpha", "bravo"}), demo_code="CODE1",
        team_ids=frozenset({"t1", "t2"}), winner_id=winner_id)}


def _captured_before_rename(**over: Any) -> dict[str, Any]:
    fields = dict(side_a_team="Alpha", side_b_team="Bravo",
                  side_a_team_id="t1", side_b_team_id="t2")
    return _one_map(**{**fields, **over})


def test_a_team_renamed_after_capture_is_still_accepted() -> None:
    from owdb.contribute import validate_maps
    cleaned, rejects = validate_maps(_captured_before_rename(), _known_ids())
    assert rejects == [] and len(cleaned["maps"]) == 1


def test_a_team_id_that_did_not_play_is_rejected() -> None:
    """Still the wrong-replay guard - just keyed on something that holds still."""
    from owdb.contribute import validate_maps
    # Names that DO match FACEIT today, so only the id can be what rejects it.
    cleaned, rejects = validate_maps(
        _captured_before_rename(side_a_team="New Alpha", side_b_team_id="t9"),
        _known_ids())
    assert cleaned["maps"] == [] and "did not play" in rejects[0][1]


def test_the_winner_is_found_by_team_id_after_a_rename() -> None:
    from owdb.contribute import validate_maps
    cleaned, _ = validate_maps(_captured_before_rename(winner_side=None),
                               _known_ids(winner_id="t1"))
    assert cleaned["maps"][0]["winner_side"] == "a"


def test_known_games_reads_the_winner_and_bans_from_faceit(tmp_path: Path) -> None:
    import sqlite3
    from owdb.contribute import known_games
    db = tmp_path / "faceit.sqlite3"
    con = sqlite3.connect(db)
    con.executescript("""
        CREATE TABLE teams (id TEXT, name TEXT);
        CREATE TABLE championships (id TEXT, name TEXT);
        CREATE TABLE matches (id TEXT, championship_id TEXT,
                              faction1_team_id TEXT, faction2_team_id TEXT);
        CREATE TABLE games (match_id TEXT, game_no INT, demo_code TEXT,
                            winner_faction TEXT);
        CREATE TABLE hero_bans (match_id TEXT, game_no INT, hero_guid TEXT,
                                ban_order INT, banned_by_faction TEXT);
        INSERT INTO teams VALUES ('t1', 'Alpha'), ('t2', 'Bravo');
        INSERT INTO matches VALUES ('m1', NULL, 't1', 't2');
        INSERT INTO games VALUES ('m1', 1, 'CODE1', 'faction2'),
                                 ('m1', 2, 'CODE2', NULL);
        INSERT INTO hero_bans VALUES ('m1', 1, '0xSECOND', 2, 'faction2'),
                                     ('m1', 1, '0xFIRST', 1, 'faction1');
    """)
    con.commit(); con.close()
    known = known_games(str(db))
    assert known[MapKey("m1", 1)].team_ids == frozenset({"t1", "t2"})
    assert known[MapKey("m1", 1)].winner_id == "t2"
    assert known[MapKey("m1", 2)].winner_id is None
    assert known[MapKey("m1", 1)].winner == "bravo"
    assert known[MapKey("m1", 1)].bans == ("0xFIRST", "0xSECOND")
    assert known[MapKey("m1", 2)].winner is None
    assert known[MapKey("m1", 2)].bans == ()

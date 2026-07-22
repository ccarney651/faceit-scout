"""Per-team scouting report assembly (owscout.scout)."""

from owscout.models import ObsDetail
from owscout.scout import team_scout

ROLES = {"ram": "tank", "dva": "tank", "soj": "damage", "mei": "damage",
         "reaper": "damage", "ashe": "damage", "luc": "support", "kir": "support",
         "ana": "support"}
NAMES = {g: g.upper() for g in ROLES}


def _obs(mi: int, side: str, ts: int, guids: list[str], cat: str, winner: str, *,
         sub: str | None = None, rnd: int | None = None, phase: str | None = None,
         mn: str = "King's Row") -> ObsDetail:
    return ObsDetail(map_instance_id=mi, side=side, sample_ts_ms=ts, sub_map=sub, phase=phase,
                     round_no=rnd, hero_guids=tuple(guids), map_name=mn,
                     map_category=cat, side_a_team="Alpha", side_b_team="Bravo",
                     winner_side=winner)


def test_overall_uses_opening_comp_per_game() -> None:
    base = ["ram", "soj", "mei", "luc", "kir"]
    swapped = ["ram", "soj", "reaper", "luc", "kir"]  # mid-map flex, not the opening
    details = [
        _obs(1, "a", 0, base, "hybrid", "a"),      # game 1 opens base, won
        _obs(1, "a", 100, swapped, "hybrid", "a"),  # later swap same game
        _obs(2, "a", 0, base, "hybrid", "b"),      # game 2 opens base, lost
    ]
    rep = team_scout(details, ROLES, NAMES)
    alpha = rep["Alpha"]
    overall = alpha["overall"]
    assert len(overall) == 1                    # one family (base, swap folds in)
    fam = overall[0]
    assert fam["maps"] == 2 and fam["wins"] == 1 and fam["losses"] == 1


def test_hybrid_splits_attack_and_defend_segments() -> None:
    atk = ["ram", "soj", "mei", "luc", "kir"]
    dfd = ["dva", "reaper", "mei", "ana", "kir"]
    # Escort/Hybrid: side 'b' (red) attacks on round 1, defends on round 2.
    details = [
        _obs(1, "b", 0, atk, "hybrid", "b", rnd=1),
        _obs(1, "b", 200, dfd, "hybrid", "b", rnd=2),
    ]
    rep = team_scout(details, ROLES, NAMES)
    kings = rep["Bravo"]["maps"]["King's Row"]["segments"]
    assert set(kings) == {"attack", "defend"}
    assert kings["attack"]["open"][0]["heroes"] == ["KIR", "LUC", "MEI", "RAM", "SOJ"]


def test_control_splits_by_sub_map() -> None:
    a = ["ram", "soj", "mei", "luc", "kir"]
    details = [
        _obs(1, "a", 0, a, "control", "a", sub="Lighthouse", mn="Ilios"),
        _obs(1, "a", 100, a, "control", "a", sub="Ruins", mn="Ilios"),
    ]
    ilios = team_scout(details, ROLES, NAMES)["Alpha"]["maps"]["Ilios"]["segments"]
    assert set(ilios) == {"Lighthouse", "Ruins"}


def test_ban_response_shows_openings_when_hero_banned() -> None:
    from owscout.scout import ban_response
    # Mei banned in 2 of Alpha's games; not in a 3rd. Threshold min_games=2.
    d = [
        _obs(1, "a", 0, ["ram", "soj", "ashe", "luc", "kir"], "hybrid", "a"),
        _obs(2, "a", 0, ["ram", "ashe", "soj", "luc", "ana"], "hybrid", "a"),
        _obs(3, "a", 0, ["ram", "soj", "mei", "luc", "kir"], "hybrid", "a"),
    ]
    d = [x._replace(bans=("mei",)) if x.map_instance_id in (1, 2) else x for x in d]
    rows = ban_response(d, ROLES, NAMES)["Alpha"]
    assert len(rows) == 1
    assert rows[0]["banned"] == "MEI" and rows[0]["games"] == 2
    assert "ASHE" in rows[0]["opens"][0]["heroes"]


def test_hero_pool_counts_rounds_not_maps() -> None:
    """A hero played every round is a staple; one played for a single point is
    not. Counting maps flattens both to '1 map' and loses that distinction."""
    staple = ["ram", "soj", "mei", "luc", "kir"]
    cameo = ["ram", "soj", "reaper", "luc", "kir"]   # reaper for one round only
    details = [
        _obs(1, "a", 0, staple, "control", "a", sub="Lighthouse", rnd=1, mn="Ilios"),
        _obs(1, "a", 100, staple, "control", "a", sub="Ruins", rnd=2, mn="Ilios"),
        _obs(1, "a", 200, cameo, "control", "a", sub="Well", rnd=3, mn="Ilios"),
    ]
    rep = team_scout(details, ROLES, NAMES)["Alpha"]
    assert rep["rounds"] == 3
    pool = {h["hero"]: h for h in rep["hero_pool"]}
    assert pool["MEI"]["rounds"] == 2 and pool["REAPER"]["rounds"] == 1
    assert pool["RAM"]["rounds"] == 3 and pool["RAM"]["pick_rate"] == 1.0
    assert pool["RAM"]["role"] == "tank"          # drives the per-role split


def test_swaps_are_reported_per_map() -> None:
    """The map card shows the swaps seen on THAT map, so they must be bucketed by
    map and not folded into the team-wide total."""
    base = ["ram", "soj", "mei", "luc", "kir"]
    swapped = ["ram", "soj", "reaper", "luc", "kir"]
    details = [
        _obs(1, "a", 0, base, "hybrid", "a"),                       # King's Row
        _obs(1, "a", 100, swapped, "hybrid", "a"),                  # swap here
        _obs(2, "a", 0, base, "control", "a", sub="Ruins", mn="Ilios"),
    ]
    maps = team_scout(details, ROLES, NAMES)["Alpha"]["maps"]
    kings = maps["King's Row"]["swaps"]
    assert len(kings) == 1
    assert kings[0]["out"] == ["MEI"] and kings[0]["in"] == ["REAPER"]
    assert maps["Ilios"]["swaps"] == []


def test_matchups_pair_opening_with_enemy_opening() -> None:
    """Counter-scout needs each game's opening PAIRED with the enemy's - the
    aggregates cannot answer 'what do they do against comps like ours'."""
    mine = ["ram", "soj", "mei", "luc", "kir"]
    theirs = ["dva", "reaper", "ashe", "ana", "kir"]
    details = [
        _obs(1, "a", 0, mine, "hybrid", "a"),
        _obs(1, "b", 5, theirs, "hybrid", "a"),
    ]
    rep = team_scout(details, ROLES, NAMES)
    mu = rep["Alpha"]["matchups"]
    assert len(mu) == 1
    assert mu[0]["open"] == [g.upper() for g in mine]
    assert mu[0]["vs"] == [g.upper() for g in theirs]
    assert mu[0]["won"] is True and mu[0]["map"] == "King's Row"
    assert mu[0]["opp"] == "Bravo"          # opponent TEAM name, for "vs <team>"
    # and the enemy's entry mirrors it
    bmu = rep["Bravo"]["matchups"][0]
    assert bmu["vs"] == [g.upper() for g in mine] and bmu["won"] is False
    assert bmu["opp"] == "Alpha"


def test_matchups_carry_match_identity_for_recency_and_history() -> None:
    """The map history orders games by real match date and links opponents, so
    each matchup must carry the FACEIT match_id/game_no the dashboard joins on."""
    mine = ["ram", "soj", "mei", "luc", "kir"]
    details = [_obs(1, "a", 0, mine, "hybrid", "a")._replace(match_id="M7", game_no=2)]
    mu = team_scout(details, ROLES, NAMES)["Alpha"]["matchups"][0]
    assert mu["match_id"] == "M7" and mu["game_no"] == 2


def test_adaptability_change_after_loss() -> None:
    """Losing game 1 then opening game 2 with a DIFFERENT comp family counts as
    adapting; a one-hero flex within the family does not."""
    stubborn = ["ram", "soj", "mei", "luc", "kir"]
    flexed = ["ram", "soj", "reaper", "luc", "kir"]     # same family (4 shared + tank)
    newcomp = ["dva", "ashe", "reaper", "ana", "kir"]   # different family
    details = [
        _obs(1, "a", 0, stubborn, "control", "b", mn="Ilios"),      # lost g1
        _obs(2, "a", 0, flexed, "hybrid", "b"),                     # lost g2, only flexed
        _obs(3, "a", 0, newcomp, "escort", "a", mn="Dorado"),       # g3: real change
    ]
    # same match, sequential games
    details = [d._replace(match_id="M1", game_no=i + 1) for i, d in enumerate(details)]
    adapt = team_scout(details, ROLES, NAMES)["Alpha"]["adapt"]
    assert adapt["loss_followups"] == 2          # g1->g2 and g2->g3 both follow losses
    assert adapt["changed_after_loss"] == 1      # only g2->g3 changed family


def test_adaptability_ignores_cross_match_sequences() -> None:
    """Game 1 of a NEW match following a loss in another match is not a
    'response' - only consecutive games of the same series count."""
    a = ["ram", "soj", "mei", "luc", "kir"]
    b = ["dva", "ashe", "reaper", "ana", "kir"]
    details = [
        _obs(1, "a", 0, a, "control", "b", mn="Ilios")._replace(match_id="M1", game_no=3),
        _obs(2, "a", 0, b, "hybrid", "a")._replace(match_id="M2", game_no=1),
    ]
    adapt = team_scout(details, ROLES, NAMES)["Alpha"]["adapt"]
    assert adapt["loss_followups"] == 0

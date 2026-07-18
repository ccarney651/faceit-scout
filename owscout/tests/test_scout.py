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

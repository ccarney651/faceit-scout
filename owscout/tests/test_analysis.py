"""Comp identity + swap analysis (owscout.analysis)."""

from owscout.analysis import (
    classify_transition,
    phase_of,
    same_comp,
    swap_events,
    tank_of,
)

# A small role map. Tanks: rein, dva, ram. DPS: sojourn, mei, reaper, ashe.
# Supports: lucio, kiriko, ana, bap.
ROLES = {
    "rein": "tank", "dva": "tank", "ram": "tank",
    "sojourn": "damage", "mei": "damage", "reaper": "damage", "ashe": "damage",
    "lucio": "support", "kiriko": "support", "ana": "support", "bap": "support",
}


def test_phase_of_escort_hybrid_flips_by_round() -> None:
    # Round 1: red (b) attacks, blue (a) defends.
    assert phase_of("Escort", "b", 1) == "attack"
    assert phase_of("Escort", "a", 1) == "defend"
    assert phase_of("Hybrid", "b", 1) == "attack"
    # Round 2: they flip.
    assert phase_of("Hybrid", "b", 2) == "defend"
    assert phase_of("Hybrid", "a", 2) == "attack"


def test_phase_of_mirrored_maps_have_no_phase() -> None:
    for cat in ("Control", "Flashpoint", "Push", "control", None, "", "Weird"):
        assert phase_of(cat, "a", 1) is None
        assert phase_of(cat, "b", 2) is None


def test_phase_of_defaults_round_to_one() -> None:
    assert phase_of("Escort", "b", None) == "attack"


def test_tank_of() -> None:
    assert tank_of(["ram", "sojourn", "mei", "lucio", "kiriko"], ROLES) == "ram"
    assert tank_of(["sojourn", "mei", "lucio", "kiriko", "ana"], ROLES) is None


def test_same_comp_four_shared() -> None:
    a = ["ram", "sojourn", "mei", "lucio", "kiriko"]
    b = ["ram", "sojourn", "mei", "lucio", "ana"]  # 1 support flexed -> 4 shared
    assert same_comp(a, b, ROLES)


def test_same_comp_three_shared_with_tank() -> None:
    a = ["ram", "sojourn", "mei", "lucio", "kiriko"]
    b = ["ram", "sojourn", "reaper", "lucio", "ana"]  # shares ram+sojourn+lucio (tank in)
    assert same_comp(a, b, ROLES)


def test_not_same_comp_three_shared_without_tank() -> None:
    a = ["ram", "sojourn", "mei", "lucio", "kiriko"]
    # shares sojourn+mei+lucio (3) but tanks differ (ram vs dva) -> different comp
    b = ["dva", "sojourn", "mei", "lucio", "ana"]
    assert not same_comp(a, b, ROLES)


def test_not_same_comp_tank_swap_is_core() -> None:
    a = ["ram", "sojourn", "mei", "lucio", "kiriko"]
    b = ["dva", "sojourn", "mei", "lucio", "kiriko"]  # 4 shared -> STILL same comp
    assert same_comp(a, b, ROLES)  # 4 shared overrides even a tank change


def test_classify_transition_flex_vs_core() -> None:
    base = ["ram", "sojourn", "mei", "lucio", "kiriko"]
    flex = ["ram", "sojourn", "reaper", "lucio", "kiriko"]  # 1 DPS swap
    core = ["dva", "reaper", "ashe", "bap", "kiriko"]       # whole new comp
    assert classify_transition(base, base, ROLES).kind == "none"
    t_flex = classify_transition(base, flex, ROLES)
    assert t_flex.kind == "flex"
    assert t_flex.out_heroes == ["mei"] and t_flex.in_heroes == ["reaper"]
    assert classify_transition(base, core, ROLES).kind == "core"


def test_swap_events_tags_enemy_and_skips_no_change() -> None:
    # own timeline: base -> base (no change) -> core swap; enemy shows a D.Va when they swap.
    base = ["ram", "sojourn", "mei", "lucio", "kiriko"]
    answer = ["dva", "reaper", "mei", "bap", "kiriko"]
    enemy1 = ["rein", "ashe", "sojourn", "lucio", "ana"]
    enemy2 = ["dva", "reaper", "sojourn", "lucio", "ana"]  # enemy brought D.Va
    snaps = [(base, enemy1), (base, enemy1), (answer, enemy2)]
    events = swap_events(snaps, ROLES)
    assert len(events) == 1
    ev = events[0]
    assert ev.kind == "core"
    assert "dva" in ev.vs_enemy

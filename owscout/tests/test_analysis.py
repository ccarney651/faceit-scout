"""Comp identity + swap analysis (owscout.analysis)."""

from owscout.analysis import (
    CompInstance,
    PlayerSlot,
    classify_player_transition,
    classify_transition,
    cluster_comps,
    confirmed_swap_events,
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


# --- player-confirmed swap detection -----------------------------------------
# A hero-set change alone can't tell a real swap (same player, new hero) apart
# from a personnel substitution (a different player entered on a different
# hero) - both look identical as a plain hero-set diff. classify_player_transition
# only calls it a swap when every slot's player identity is known on both sides
# AND the same players are still present (see docstring for the "why").


def test_classify_player_transition_confirms_a_real_swap() -> None:
    # Same five players throughout; "sym-player" moved from mei to reaper.
    prev = [PlayerSlot("p-tank", "ram"), PlayerSlot("p-dps1", "sojourn"),
            PlayerSlot("p-sym", "mei"), PlayerSlot("p-sup1", "lucio"),
            PlayerSlot("p-sup2", "kiriko")]
    curr = [PlayerSlot("p-tank", "ram"), PlayerSlot("p-dps1", "sojourn"),
            PlayerSlot("p-sym", "reaper"), PlayerSlot("p-sup1", "lucio"),
            PlayerSlot("p-sup2", "kiriko")]
    t = classify_player_transition(prev, curr, ROLES)
    assert t is not None and t.kind == "flex"
    assert t.out_heroes == ["mei"] and t.in_heroes == ["reaper"]


def test_classify_player_transition_excludes_a_personnel_substitution() -> None:
    # The exact reported bug: sivaartt (on mei) is subbed for alison (on
    # reaper). The hero set changes identically to the real-swap case above,
    # but this is personnel churn, not a tactical decision - must not count.
    prev = [PlayerSlot("p-tank", "ram"), PlayerSlot("p-dps1", "sojourn"),
            PlayerSlot("p-sivaartt", "mei"), PlayerSlot("p-sup1", "lucio"),
            PlayerSlot("p-sup2", "kiriko")]
    curr = [PlayerSlot("p-tank", "ram"), PlayerSlot("p-dps1", "sojourn"),
            PlayerSlot("p-alison", "reaper"), PlayerSlot("p-sup1", "lucio"),
            PlayerSlot("p-sup2", "kiriko")]
    assert classify_player_transition(prev, curr, ROLES) is None


def test_classify_player_transition_excludes_unconfirmed_when_a_slot_is_unknown() -> None:
    # One slot's attribution never resolved (OCR miss) - can't rule out a
    # substitution hiding there, so don't guess either way.
    prev = [PlayerSlot("p-tank", "ram"), PlayerSlot(None, "sojourn"),
            PlayerSlot("p-sym", "mei"), PlayerSlot("p-sup1", "lucio"),
            PlayerSlot("p-sup2", "kiriko")]
    curr = [PlayerSlot("p-tank", "ram"), PlayerSlot(None, "sojourn"),
            PlayerSlot("p-sym", "reaper"), PlayerSlot("p-sup1", "lucio"),
            PlayerSlot("p-sup2", "kiriko")]
    assert classify_player_transition(prev, curr, ROLES) is None


def test_classify_player_transition_none_when_no_hero_change() -> None:
    same = [PlayerSlot("p-tank", "ram"), PlayerSlot("p-dps1", "sojourn"),
            PlayerSlot("p-sym", "mei"), PlayerSlot("p-sup1", "lucio"),
            PlayerSlot("p-sup2", "kiriko")]
    assert classify_player_transition(same, same, ROLES) is None


def test_confirmed_swap_events_skips_substitutions_but_keeps_real_swaps() -> None:
    enemy = ["rein", "ashe", "sojourn", "lucio", "ana"]
    real_swap_prev = [PlayerSlot("p1", "ram"), PlayerSlot("p2", "sojourn"),
                       PlayerSlot("p3", "mei"), PlayerSlot("p4", "lucio"),
                       PlayerSlot("p5", "kiriko")]
    real_swap_curr = [PlayerSlot("p1", "ram"), PlayerSlot("p2", "sojourn"),
                       PlayerSlot("p3", "reaper"), PlayerSlot("p4", "lucio"),
                       PlayerSlot("p5", "kiriko")]
    sub_curr = [PlayerSlot("p1", "ram"), PlayerSlot("p2", "sojourn"),
                PlayerSlot("p6", "ashe"), PlayerSlot("p4", "lucio"),
                PlayerSlot("p5", "kiriko")]   # p3 subbed out for p6
    snaps = [(real_swap_prev, enemy), (real_swap_curr, enemy), (sub_curr, enemy)]
    events = confirmed_swap_events(snaps, ROLES)
    assert len(events) == 1   # only the p3 mei->reaper swap; the sub is excluded
    assert events[0].out_heroes == ["mei"] and events[0].in_heroes == ["reaper"]


# --- comp-family clustering --------------------------------------------------


def test_cluster_comps_folds_flex_variants_into_one_family() -> None:
    base = ("ram", "sojourn", "mei", "lucio", "kiriko")
    flex = ("ram", "sojourn", "reaper", "lucio", "kiriko")  # 1 DPS swap -> same comp
    other = ("dva", "reaper", "ashe", "bap", "kiriko")      # different comp
    insts = [
        CompInstance(base, True, "m1"),
        CompInstance(flex, False, "m2"),
        CompInstance(base, True, "m3"),
        CompInstance(other, False, "m4"),
    ]
    fams = cluster_comps(insts, ROLES)
    assert len(fams) == 2
    top = fams[0]  # the ram family (3 games) sorts first
    assert top.maps == 3 and top.samples == 3
    assert top.wins == 2 and top.losses == 1
    assert round(top.win_rate, 2) == 0.67
    assert len(top.variants) == 2  # base + flex folded together


def test_cluster_comps_separates_tank_change_without_4_shared() -> None:
    a = ("ram", "sojourn", "mei", "lucio", "kiriko")
    b = ("dva", "sojourn", "mei", "bap", "ana")   # tank + 2 supports differ -> different
    fams = cluster_comps([CompInstance(a, True, "m1"), CompInstance(b, True, "m2")], ROLES)
    assert len(fams) == 2


def test_cluster_comps_surfaces_majority_bans() -> None:
    """A comp carries the bans it lives under: heroes banned out in a strict
    majority of the games the comp was run (each game's ban set counted once)."""
    from owscout.analysis import CompInstance, cluster_comps

    comp = ("ram", "soj", "mei", "luc", "kir")
    insts = [
        CompInstance(comp, True, "g1", bans=("sombra", "widow")),
        CompInstance(comp, False, "g2", bans=("sombra",)),
        CompInstance(comp, True, "g3", bans=("mauga",)),
    ]
    fam = cluster_comps(insts, {"ram": "tank"})[0]
    assert fam.bans == ["sombra"]        # 2 of 3 games; widow/mauga only 1 each


def test_cluster_comps_collects_game_keys_for_click_to_codes() -> None:
    """A family exposes the FACEIT match:game keys behind it, so the dashboard
    can resolve them to replay codes. Instances with no code_key (older/synthetic
    data) are silently excluded rather than polluting the list with None."""
    from owscout.analysis import CompInstance, cluster_comps

    base = ("ram", "sojourn", "mei", "lucio", "kiriko")
    flex = ("ram", "sojourn", "reaper", "lucio", "kiriko")  # same family (1 flex)
    insts = [
        CompInstance(base, True, "m1", code_key="a1:1"),
        CompInstance(flex, False, "m2", code_key="a1:2"),
        CompInstance(base, True, "m3", code_key=None),   # no FACEIT identity known
    ]
    fam = cluster_comps(insts, ROLES)[0]
    assert fam.game_keys == ["a1:1", "a1:2"]

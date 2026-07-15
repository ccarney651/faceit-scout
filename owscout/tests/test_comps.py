"""Comp canonicalisation: sha1 order-independence and role counts (SPEC §4, §12)."""

from __future__ import annotations

from owscout.comps import canonical_comp, comp_id_for

ROLES = {"g-ram": "Tank", "g-soj": "Damage", "g-tracer": "Damage",
         "g-ana": "Support", "g-kiri": "Support"}
NAMES = {"g-ram": "Ramattra", "g-soj": "Sojourn", "g-tracer": "Tracer",
         "g-ana": "Ana", "g-kiri": "Kiriko"}
FIVE = list(ROLES)


def test_comp_id_is_order_independent() -> None:
    assert comp_id_for(FIVE) == comp_id_for(list(reversed(FIVE)))
    assert comp_id_for(["a", "b", "c"]) == comp_id_for(["c", "a", "b"])


def test_different_heroes_different_id() -> None:
    assert comp_id_for(["a", "b", "c"]) != comp_id_for(["a", "b", "d"])


def test_canonical_comp_counts_roles() -> None:
    comp = canonical_comp(FIVE, ROLES, NAMES)
    assert (comp.tank_count, comp.damage_count, comp.support_count) == (1, 2, 2)
    assert comp.team_size == 5
    assert comp.hero_guids == sorted(FIVE)  # canonical order
    assert comp.hero_names_sorted == "Ana, Kiriko, Ramattra, Sojourn, Tracer"


def test_canonical_comp_collapses_duplicates() -> None:
    # A comp is a set — a duplicated guid does not inflate the size.
    comp = canonical_comp(["g-ram", "g-ram", "g-ana"], ROLES, NAMES)
    assert comp.team_size == 2
    assert comp.hero_guids == ["g-ana", "g-ram"]


def test_unlabelled_role_ignored_in_counts() -> None:
    comp = canonical_comp(["g-ram", "g-unknown"], ROLES, NAMES)
    assert comp.tank_count == 1
    assert comp.damage_count == 0 and comp.support_count == 0

"""Composition canonicalisation (SPEC §4 ``comps``, build step 5).

A comp is a *set* of heroes, not an ordered list — "Reinhardt + Ana + ..." is
the same comp however the HUD ordered the slots. ``comp_id`` is the sha1 of the
sorted hero_guids, so canonicalisation is order-independent by construction.

Pure module — no I/O, fully unit-tested.
"""

from __future__ import annotations

import hashlib
from typing import Mapping, Sequence

from .faceit import KNOWN_ROLES
from .models import Comp


def comp_id_for(hero_guids: Sequence[str]) -> str:
    """The canonical id: sha1 of the sorted, comma-joined hero_guids."""
    canonical = ",".join(sorted(hero_guids))
    return hashlib.sha1(canonical.encode("utf-8")).hexdigest()


def canonical_comp(
    hero_guids: Sequence[str],
    hero_roles: Mapping[str, str],
    hero_names: Mapping[str, str],
) -> Comp:
    """Build a :class:`Comp` from a set of hero_guids. Duplicate guids are
    collapsed (a comp is a set); role counts use ``hero_roles`` and ignore
    unlabelled heroes."""
    unique = sorted(set(hero_guids))
    counts = {"Tank": 0, "Damage": 0, "Support": 0}
    for guid in unique:
        role = hero_roles.get(guid)
        if role in KNOWN_ROLES:
            counts[role] += 1
    names = sorted(hero_names.get(g, g) for g in unique)
    return Comp(
        comp_id=comp_id_for(unique),
        hero_guids=unique,
        hero_names_sorted=", ".join(names),
        tank_count=counts["Tank"],
        damage_count=counts["Damage"],
        support_count=counts["Support"],
        team_size=len(unique),
    )

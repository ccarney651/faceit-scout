"""Comp identity and swap analysis — the scouting interpretation layer.

A 'comp' is a *family*, not an exact five-hero lineup. Two lineups are the same
comp when they share **>=4 heroes**, or share **exactly 3 that include the same
tank** (in 5v5 the tank anchors a comp's identity — you can flex both DPS or a
support without changing how it's played). A mid-map change is then classified:

  * FLEX swap  — still the same comp (1-2 heroes changed, core intact),
  * CORE swap  — a genuinely different comp.

"what do they swap versus" attaches the enemy lineup at the moment of the swap,
so a core swap can be attributed to the opponent's comp (or a single enemy hero,
e.g. answering a D.Va).

Everything here is pure — it operates on hero identifiers (guids or names, as long
as the caller is consistent) plus a role map — so it is unit-tested without the
game or DB.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Sequence

# hero identifier -> role ('tank' | 'damage' | 'support'), case-insensitive.
Roles = dict[str, str]


# Categories that have an attacking and a defending team. Everything else
# (Control/Flashpoint/Push) is a mirrored fight and therefore has no phase.
_PHASED_CATEGORIES = {"escort", "hybrid", "assault"}


def phase_of(
    map_category: Optional[str], side: str, round_no: Optional[int]
) -> Optional[str]:
    """'attack' / 'defend' for one HUD side, or None when the map has no phase.

    Operator rule: on Escort/Hybrid the RED team (right HUD side 'b') attacks
    first and BLUE ('a') defends first, and they flip each round. Control /
    Flashpoint / Push are mirrored (no phase). Unknown round defaults to 1."""
    cat = (map_category or "").strip().lower()
    if cat not in _PHASED_CATEGORIES:
        return None
    red_attacks = ((round_no or 1) % 2 == 1)   # red attacks on odd rounds
    attack_side = "b" if red_attacks else "a"
    return "attack" if side == attack_side else "defend"


def tank_of(lineup: Sequence[str], roles: Roles) -> Optional[str]:
    """The tank in a lineup (first hero whose role is 'tank'), or None."""
    for h in lineup:
        if (roles.get(h) or "").lower() == "tank":
            return h
    return None


def same_comp(a: Sequence[str], b: Sequence[str], roles: Roles) -> bool:
    """Whether two lineups are the same comp family: share >=4 heroes, or share
    exactly 3 including the same tank."""
    shared = set(a) & set(b)
    if len(shared) >= 4:
        return True
    if len(shared) == 3:
        ta = tank_of(a, roles)
        return ta is not None and ta in shared and tank_of(b, roles) == ta
    return False


@dataclass(frozen=True)
class Transition:
    """One classified change between two consecutive lineups of a team."""

    kind: str            # 'none' | 'flex' | 'core'
    out_heroes: list[str]  # heroes dropped
    in_heroes: list[str]   # heroes brought in


def classify_transition(
    prev: Sequence[str], curr: Sequence[str], roles: Roles
) -> Transition:
    """Classify prev -> curr as no change, a flex swap (same comp), or a core
    swap (different comp), with the heroes out/in."""
    sp, sc = set(prev), set(curr)
    if sp == sc:
        return Transition("none", [], [])
    kind = "flex" if same_comp(prev, curr, roles) else "core"
    return Transition(kind, sorted(sp - sc), sorted(sc - sp))


@dataclass(frozen=True)
class CompInstance:
    """One game's worth of a comp: the lineup a team ran on a map (usually the
    opening comp), whether they won, and a key identifying the game for
    distinct-map counting."""

    heroes: tuple[str, ...]
    won: bool
    map_key: str


@dataclass
class CompFamily:
    """A clustered comp family: a representative lineup plus every variation folded
    into it, with win/loss aggregated over distinct games."""

    heroes: list[str]                 # representative (most-common) lineup
    samples: int
    maps: int
    wins: int
    losses: int
    win_rate: float
    variants: list[tuple[str, ...]]   # distinct lineups in this family


def cluster_comps(instances: Sequence[CompInstance], roles: Roles) -> list[CompFamily]:
    """Group comp instances into families via :func:`same_comp` (>=4 shared, or 3
    including the tank). Greedy: the most-frequent lineup anchors a family and
    absorbs the lineups that match it. Families are sorted most-played first."""
    from collections import Counter

    # Canonicalise each lineup to a sorted tuple so order never splits a family.
    norm: list[tuple[tuple[str, ...], bool, str]] = [
        (tuple(sorted(i.heroes)), i.won, i.map_key) for i in instances
    ]
    freq = Counter(h for h, _, _ in norm)
    order = [h for h, _ in freq.most_common()]
    assigned: set[tuple[str, ...]] = set()
    families: list[CompFamily] = []
    for anchor in order:
        if anchor in assigned:
            continue
        members = {anchor}
        assigned.add(anchor)
        for other in order:
            if other not in assigned and same_comp(anchor, other, roles):
                members.add(other)
                assigned.add(other)
        insts = [(h, won, mk) for (h, won, mk) in norm if h in members]
        n = len(insts)
        maps = len({mk for _, _, mk in insts})
        wins = sum(1 for _, won, _ in insts if won)
        families.append(CompFamily(
            heroes=list(anchor), samples=n, maps=maps, wins=wins, losses=n - wins,
            win_rate=(wins / n if n else 0.0), variants=sorted(members)))
    families.sort(key=lambda f: (f.maps, f.samples), reverse=True)
    return families


@dataclass(frozen=True)
class SwapEvent:
    """A reportable mid-map swap, with the enemy lineup it was made against."""

    kind: str              # 'flex' | 'core'
    out_heroes: list[str]
    in_heroes: list[str]
    vs_enemy: list[str]    # the opponent's lineup at the moment of the swap


def swap_events(
    snapshots: Sequence[tuple[Sequence[str], Sequence[str]]], roles: Roles
) -> list[SwapEvent]:
    """Walk a team's ordered snapshots — each ``(own_lineup, enemy_lineup)`` — and
    emit a SwapEvent for every real change (flex or core), tagged with the enemy
    lineup present when the swap happened. No-change steps are skipped."""
    events: list[SwapEvent] = []
    for i in range(1, len(snapshots)):
        prev_own = snapshots[i - 1][0]
        curr_own, curr_enemy = snapshots[i]
        t = classify_transition(prev_own, curr_own, roles)
        if t.kind != "none":
            events.append(SwapEvent(t.kind, t.out_heroes, t.in_heroes, list(curr_enemy)))
    return events

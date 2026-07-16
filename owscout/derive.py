"""Derived output — the scouting statistics (SPEC §10, build step 8).

The binding constraint on this whole layer is sample depth (median ~2 games per
team-map), so every rule in §10.0 is enforced here:

* always report ``n`` (samples + distinct maps) beside a percentage;
* never render a bare percentage below ``--min-samples`` — show the raw fraction;
* fall back ``(team, map) -> (team, map_category) -> (team, all)`` when a cell is
  thin, and state which level was used.

Unresolved observations never reach here (the queries filter ``resolved = 1``).
This module is pure — it aggregates rows the DB layer hands it — and is
unit-tested, including the Wilson interval that ``comps top`` sorts by.
"""

from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Iterable, Optional, Sequence

DEFAULT_MIN_SAMPLES = 5
WILSON_Z = 1.96  # 95% confidence


# --- statistics (unit-tested) ------------------------------------------------


def wilson_lower_bound(wins: float, n: float, z: float = WILSON_Z) -> float:
    """Lower bound of the Wilson score interval for a proportion. ``comps top``
    sorts by this so a 100%-off-2-games comp cannot top the list (SPEC §10.3).
    Handles fractional counts (weighted win attribution)."""
    if n <= 0:
        return 0.0
    p = wins / n
    z2 = z * z
    denom = 1.0 + z2 / n
    centre = p + z2 / (2.0 * n)
    margin = z * math.sqrt((p * (1.0 - p) + z2 / (4.0 * n)) / n)
    return max(0.0, (centre - margin) / denom)


def render_rate(wins: float, n: int, min_samples: int = DEFAULT_MIN_SAMPLES) -> str:
    """A win rate that never lies by presentation (SPEC §10.0): below
    ``min_samples`` show the raw fraction, otherwise a percentage — always with n."""
    if n <= 0:
        return "0/0"
    if n < min_samples:
        return f"{int(round(wins))}/{n}"
    return f"{100.0 * wins / n:.0f}% (n={n})"


# --- sample-depth fallback chain (unit-tested) -------------------------------


@dataclass(frozen=True)
class FallbackCell:
    """One level of the §10.0 fallback: a label, its sample count, its value."""

    level: str
    n: int
    payload: object = None


def choose_level(
    cells: Sequence[FallbackCell], min_samples: int = DEFAULT_MIN_SAMPLES
) -> FallbackCell:
    """Walk the fallback chain and return the first cell meeting ``min_samples``;
    if none do, return the broadest (last) cell. Never silently substitute — the
    caller reports ``.level`` so the user sees which was used (SPEC §10.0)."""
    if not cells:
        raise ValueError("fallback chain is empty")
    for cell in cells:
        if cell.n >= min_samples:
            return cell
    return cells[-1]


# --- comp aggregation for `comps top` (unit-tested) --------------------------


@dataclass
class ObsRow:
    """One resolved observation, flattened for aggregation."""

    comp_id: str
    hero_names: str
    map_instance_id: int
    side: str
    map_guid: Optional[str]
    team_id: Optional[str]
    won: bool
    team_name: Optional[str] = None


@dataclass
class CompStat:
    comp_id: str
    hero_names: str
    samples: int
    distinct_maps: int
    distinct_teams: int
    games: float          # weighted by sample share on each team-map (§10.3)
    wins: float
    win_rate: float
    wilson: float


@dataclass
class _Acc:
    hero_names: str = ""
    samples: int = 0
    maps: set[str] = field(default_factory=set)
    teams: set[str] = field(default_factory=set)
    games: float = 0.0
    wins: float = 0.0


def aggregate_comps(rows: Iterable[ObsRow]) -> list[CompStat]:
    """Aggregate resolved observations into per-comp stats, sorted by Wilson
    lower bound (never raw win rate — SPEC §10.3).

    Win attribution is proportional to a comp's share of samples on each
    team-map (a team may run several comps across one map), so the map result is
    split, not double-counted."""
    # Group by (map_instance, side); within each, weight comps by sample share.
    by_teammap: dict[tuple[int, str], list[ObsRow]] = defaultdict(list)
    for r in rows:
        by_teammap[(r.map_instance_id, r.side)].append(r)

    acc: dict[str, _Acc] = defaultdict(_Acc)
    for group in by_teammap.values():
        total = len(group)
        counts: dict[str, int] = defaultdict(int)
        for r in group:
            counts[r.comp_id] += 1
        ref = group[0]  # map_guid/team_id/won are per team-map
        for comp_id, cnt in counts.items():
            weight = cnt / total
            a = acc[comp_id]
            a.hero_names = next(r.hero_names for r in group if r.comp_id == comp_id)
            a.samples += cnt
            if ref.map_guid is not None:
                a.maps.add(ref.map_guid)
            if ref.team_id is not None:
                a.teams.add(ref.team_id)
            a.games += weight
            a.wins += weight if ref.won else 0.0

    stats = [
        CompStat(
            comp_id=cid, hero_names=a.hero_names, samples=a.samples,
            distinct_maps=len(a.maps), distinct_teams=len(a.teams),
            games=a.games, wins=a.wins,
            win_rate=(a.wins / a.games if a.games else 0.0),
            wilson=wilson_lower_bound(a.wins, a.games),
        )
        for cid, a in acc.items()
    ]
    stats.sort(key=lambda s: (s.wilson, s.samples), reverse=True)
    return stats


# --- per-team comp view for `scout team` (unit-tested) -----------------------


@dataclass
class ModalComp:
    hero_names: str
    comp_id: str
    maps: int          # distinct team-maps this exact comp was run
    wins: int
    losses: int


def modal_comp(rows: Iterable[ObsRow]) -> Optional[ModalComp]:
    """The exact 5 a team ran most often, by distinct team-maps (not samples),
    with its record. Honest — the comp they actually fielded (SPEC §10.2)."""
    # Reduce each team-map to the comp(s) seen; count maps per comp + record.
    per_map: dict[tuple[int, str], list[ObsRow]] = defaultdict(list)
    for r in rows:
        per_map[(r.map_instance_id, r.side)].append(r)
    maps_for: dict[str, int] = defaultdict(int)
    wins_for: dict[str, int] = defaultdict(int)
    losses_for: dict[str, int] = defaultdict(int)
    names: dict[str, str] = {}
    for group in per_map.values():
        # the dominant comp on this team-map
        counts: dict[str, int] = defaultdict(int)
        for r in group:
            counts[r.comp_id] += 1
            names[r.comp_id] = r.hero_names
        dominant = max(counts, key=lambda c: counts[c])
        maps_for[dominant] += 1
        if group[0].won:
            wins_for[dominant] += 1
        else:
            losses_for[dominant] += 1
    if not maps_for:
        return None
    top = max(maps_for, key=lambda c: maps_for[c])
    return ModalComp(hero_names=names[top], comp_id=top, maps=maps_for[top],
                     wins=wins_for[top], losses=losses_for[top])


def synthetic_comp(
    rows: Iterable[ObsRow], hero_roles: dict[str, str], comp_hero_guids: dict[str, list[str]]
) -> list[tuple[str, str]]:
    """Top hero per role slot across a team's comps — a composite the team may
    never have actually fielded (SPEC §10.2, label it SYNTHETIC in output).
    Returns [(role, hero_guid)] for 1 Tank / 2 Damage / 2 Support."""
    counts: dict[str, dict[str, int]] = {"Tank": defaultdict(int),
                                         "Damage": defaultdict(int),
                                         "Support": defaultdict(int)}
    for r in rows:
        for guid in comp_hero_guids.get(r.comp_id, []):
            role = hero_roles.get(guid)
            if role in counts:
                counts[role][guid] += 1
    picks: list[tuple[str, str]] = []
    for role, take in (("Tank", 1), ("Damage", 2), ("Support", 2)):
        ranked = sorted(counts[role].items(), key=lambda kv: kv[1], reverse=True)
        picks.extend((role, guid) for guid, _ in ranked[:take])
    return picks


# --- per-player hero pool for `scout player` (unit-tested) -------------------


@dataclass
class PoolEntry:
    hero_guid: str
    role: Optional[str]
    maps: int          # distinct maps the player was seen on this hero
    pick_rate: float   # maps_on_hero / total_maps


def dashboard_comps(rows: Iterable[ObsRow]) -> dict[str, object]:
    """Team-keyed captured-comp summary for the faceit-scout dashboard (§10). This
    is the sync artifact: owscout writes it, the dashboard reads it — a git-native
    hand-off, no shared database."""
    from collections import defaultdict

    by_team: dict[str, list[ObsRow]] = defaultdict(list)
    for r in rows:
        if r.team_name:
            by_team[r.team_name].append(r)
    teams: dict[str, object] = {}
    for team, trows in by_team.items():
        stats = aggregate_comps(trows)
        team_maps = len({(r.map_instance_id, r.side) for r in trows})
        teams[team] = {
            "maps_captured": team_maps,
            "comps": [
                {"heroes": [h.strip() for h in c.hero_names.split(",")],
                 "samples": c.samples, "maps": c.distinct_maps,
                 "games": round(c.games, 2), "wins": round(c.wins, 2),
                 "win_rate": round(c.win_rate, 3), "wilson": round(c.wilson, 3)}
                for c in stats
            ],
        }
    return {"teams": teams}


def player_pool(
    rows: Iterable[tuple[int, str]],   # (map_instance_id, hero_guid) resolved for the player
    hero_roles: dict[str, str],
) -> tuple[list[PoolEntry], int]:
    """A player's hero pool by distinct maps (a map on one hero counts once, not
    per sample), with pick rate and total maps n (SPEC §10.1)."""
    # One hero per (player, map): the hero they spent the most samples on.
    per_map: dict[int, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for mi, guid in rows:
        per_map[mi][guid] += 1
    hero_maps: dict[str, int] = defaultdict(int)
    for counts in per_map.values():
        main = max(counts, key=lambda g: counts[g])
        hero_maps[main] += 1
    total = len(per_map)
    entries = [
        PoolEntry(hero_guid=g, role=hero_roles.get(g), maps=m,
                  pick_rate=(m / total if total else 0.0))
        for g, m in sorted(hero_maps.items(), key=lambda kv: kv[1], reverse=True)
    ]
    return entries, total

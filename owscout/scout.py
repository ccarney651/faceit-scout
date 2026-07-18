"""Turn captured observations into a per-team scouting report.

Pure orchestration over :mod:`owscout.analysis`: for each team it clusters the
comps they opened with — overall and per map/segment — into families with
win/loss. A *segment* is the attack/defend phase on Escort/Hybrid, the sub-map on
Control, else the whole map. Consumes ``ObsDetail`` rows (from
``Database.observation_details``) so it is testable without a DB.
"""

from __future__ import annotations

from typing import Any, Iterable, Optional

from .analysis import CompFamily, CompInstance, Roles, cluster_comps, phase_of
from .models import ObsDetail


def _segment(d: ObsDetail) -> Optional[str]:
    """The scouting segment for an observation: 'attack'/'defend' (Escort/Hybrid),
    else the control sub-map, else None (single-geometry map)."""
    return phase_of(d.map_category, d.side, d.round_no) or d.sub_map


def _team_of(d: ObsDetail) -> Optional[str]:
    return d.side_a_team if d.side == "a" else d.side_b_team


def _family_dict(f: CompFamily, names: dict[str, str]) -> dict[str, Any]:
    return {
        "heroes": [names.get(g, g) for g in f.heroes],
        "maps": f.maps, "wins": f.wins, "losses": f.losses,
        "win_rate": round(f.win_rate, 3), "samples": f.samples,
        "variants": len(f.variants),
    }


def team_scout(
    details: Iterable[ObsDetail], roles: Roles, hero_names: dict[str, str]
) -> dict[str, dict[str, Any]]:
    """Per team: ``overall`` top comp families and ``maps`` -> segment -> families,
    each family the comp they OPENED a game/segment with, clustered by identity
    and win/loss-aggregated. Clustering runs on guids; output uses hero names."""
    # Group observations by (map_instance, side) = one game for one team.
    games: dict[tuple[int, str], list[ObsDetail]] = {}
    for d in details:
        games.setdefault((d.map_instance_id, d.side), []).append(d)

    # Per team: overall opening instances, and per (map, segment) opening instances.
    overall: dict[str, list[CompInstance]] = {}
    by_map: dict[str, dict[str, dict[str, list[CompInstance]]]] = {}
    for (mi, side), obs in games.items():
        team = _team_of(obs[0])
        if not team:
            continue
        obs.sort(key=lambda d: d.sample_ts_ms)
        won = obs[0].winner_side == side
        game_key = f"{mi}:{side}"
        # Overall opening = the first lineup seen this game.
        first = obs[0]
        overall.setdefault(team, []).append(
            CompInstance(first.hero_guids, won, game_key))
        # Opening per segment = first lineup seen in each segment.
        seen: set[Optional[str]] = set()
        mp = first.map_name or "?"
        for d in obs:
            seg = _segment(d)
            if seg in seen:
                continue
            seen.add(seg)
            slot = by_map.setdefault(team, {}).setdefault(mp, {}).setdefault(
                seg or "all", [])
            slot.append(CompInstance(d.hero_guids, won, game_key))

    report: dict[str, dict[str, Any]] = {}
    teams = set(overall) | set(by_map)
    for team in teams:
        maps_out: dict[str, Any] = {}
        for mp, segs in by_map.get(team, {}).items():
            maps_out[mp] = {
                seg: [_family_dict(f, hero_names)
                      for f in cluster_comps(insts, roles)]
                for seg, insts in segs.items()
            }
        report[team] = {
            "overall": [_family_dict(f, hero_names)
                        for f in cluster_comps(overall.get(team, []), roles)],
            "maps": maps_out,
        }
    return report

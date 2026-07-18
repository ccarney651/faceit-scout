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


def scout_payload(db: Any, faceit_db_path: str) -> dict[str, Any]:
    """The full owscout_comps.json payload: the existing per-team comp summary
    (derive.dashboard_comps) enriched with each team's scouting report under
    ``teams[team]["scout"]``. Reads roles/names from faceit + custom heroes."""
    from .derive import dashboard_comps
    from .faceit import connect_ro, hero_roles as load_roles, load_heroes

    payload = dashboard_comps(db.resolved_observations())
    with connect_ro(faceit_db_path) as fdb:
        roles = load_roles(fdb)
        names = {h.guid: h.name for h in load_heroes(fdb)}
    for h in db.list_custom_heroes():
        names[h.guid] = h.name
        if h.role:
            roles[h.guid] = h.role
    report = team_scout(db.observation_details(), roles, names)
    teams = payload["teams"]
    assert isinstance(teams, dict)
    for team, r in report.items():
        teams.setdefault(team, {"maps_captured": 0, "comps": []})["scout"] = r
    return payload


def _enemy_at(enemy_obs: list[ObsDetail], ts: int) -> tuple[str, ...]:
    """The enemy lineup as of ``ts`` — their most recent observation at or before
    it (dedupe means the sides don't share timestamps)."""
    lineup: tuple[str, ...] = ()
    for e in enemy_obs:  # enemy_obs is sorted by ts
        if e.sample_ts_ms <= ts:
            lineup = e.hero_guids
        else:
            break
    return lineup


def aggregate_swaps(
    details: Iterable[ObsDetail], roles: Roles, hero_names: dict[str, str]
) -> dict[str, list[dict[str, Any]]]:
    """Per team, recurring mid-map swaps with what they were made against. For each
    (out, in, kind) swap: how often it happened and the enemy heroes present in at
    least half its occurrences (the trigger — e.g. answering a D.Va)."""
    from collections import Counter

    from .analysis import swap_events

    by_map: dict[int, list[ObsDetail]] = {}
    for d in details:
        by_map.setdefault(d.map_instance_id, []).append(d)

    agg: dict[str, dict[tuple[Any, ...], dict[str, Any]]] = {}
    for obs in by_map.values():
        sides: dict[str, list[ObsDetail]] = {"a": [], "b": []}
        for d in sorted(obs, key=lambda x: x.sample_ts_ms):
            sides[d.side].append(d)
        for side, opp in (("a", "b"), ("b", "a")):
            own = sides[side]
            if not own:
                continue
            team = own[0].side_a_team if side == "a" else own[0].side_b_team
            if not team:
                continue
            snaps = [(o.hero_guids, _enemy_at(sides[opp], o.sample_ts_ms)) for o in own]
            for ev in swap_events(snaps, roles):
                key = (tuple(ev.out_heroes), tuple(ev.in_heroes), ev.kind)
                slot = agg.setdefault(team, {}).setdefault(
                    key, {"count": 0, "vs": Counter()})
                slot["count"] += 1
                slot["vs"].update(ev.vs_enemy)

    out: dict[str, list[dict[str, Any]]] = {}
    for team, swaps in agg.items():
        rows = []
        for (o, i, kind), v in sorted(swaps.items(), key=lambda kv: -kv[1]["count"]):
            n = v["count"]
            thresh = max(2, (n + 1) // 2)
            vs = [hero_names.get(g, g) for g, c in v["vs"].most_common() if c >= thresh]
            rows.append({
                "out": [hero_names.get(x, x) for x in o],
                "in": [hero_names.get(x, x) for x in i],
                "kind": kind, "count": n, "vs": vs[:4],
            })
        out[team] = rows
    return out


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
    details = list(details)  # iterated more than once (games + swaps)
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

    swaps = aggregate_swaps(details, roles, hero_names)
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
            "swaps": swaps.get(team, []),
        }
    return report

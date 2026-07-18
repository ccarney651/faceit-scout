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


# Key for the per-map swap buckets; "|" cannot appear in a team or map name.
_MAP_KEY = "|"


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
    details: Iterable[ObsDetail], roles: Roles, hero_names: dict[str, str],
    *, per_map: bool = False,
) -> dict[str, Any]:
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
            mp = own[0].map_name or "?"
            for ev in swap_events(snaps, roles):
                key = (tuple(ev.out_heroes), tuple(ev.in_heroes), ev.kind)
                bucket = _MAP_KEY.join((team, mp)) if per_map else team
                slot = agg.setdefault(bucket, {}).setdefault(
                    key, {"count": 0, "vs": Counter()})
                slot["count"] += 1
                slot["vs"].update(ev.vs_enemy)

    out: dict[str, Any] = {}
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


def ban_response(
    details: Iterable[ObsDetail], roles: Roles, hero_names: dict[str, str],
    *, min_games: int = 2,
) -> dict[str, list[dict[str, Any]]]:
    """Per team, how they open when a given hero is banned. For each hero banned
    in >= ``min_games`` of a team's games, the opening comp families they ran in
    those games. Surfaces 'when Sojourn is banned they open Ashe'."""
    # One opening instance per game, carrying that game's bans.
    games: dict[tuple[int, str], list[ObsDetail]] = {}
    for d in details:
        games.setdefault((d.map_instance_id, d.side), []).append(d)

    # team -> banned_guid -> list[CompInstance] (openings when that hero was banned)
    by_ban: dict[str, dict[str, list[CompInstance]]] = {}
    for (mi, side), obs in games.items():
        team = _team_of(obs[0])
        if not team:
            continue
        obs.sort(key=lambda d: d.sample_ts_ms)
        first = obs[0]
        inst = CompInstance(first.hero_guids, first.winner_side == side, f"{mi}:{side}")
        for ban in set(first.bans):
            by_ban.setdefault(team, {}).setdefault(ban, []).append(inst)

    out: dict[str, list[dict[str, Any]]] = {}
    for team, bans in by_ban.items():
        rows: list[dict[str, Any]] = []
        for ban_guid, insts in bans.items():
            games_n = len({i.map_key for i in insts})
            if games_n < min_games:
                continue
            rows.append({
                "banned": hero_names.get(ban_guid, ban_guid),
                "games": games_n,
                "opens": [_family_dict(f, hero_names)
                          for f in cluster_comps(insts, roles)][:3],
            })
        rows.sort(key=lambda r: int(r["games"]), reverse=True)
        out[team] = rows
    return out


def _segment(d: ObsDetail) -> Optional[str]:
    """The scouting segment for an observation: 'attack'/'defend' (Escort/Hybrid),
    else the control sub-map, else None (single-geometry map).

    The phase RECORDED at capture wins — from round 3 the attacker is decided by
    time banks, not round parity, so the operator confirms it live. phase_of is the
    fallback for observations captured before phase was stored.
    """
    return d.phase or phase_of(d.map_category, d.side, d.round_no) or d.sub_map


def _team_of(d: ObsDetail) -> Optional[str]:
    return d.side_a_team if d.side == "a" else d.side_b_team


def _family_dict(f: CompFamily, names: dict[str, str]) -> dict[str, Any]:
    return {
        "heroes": [names.get(g, g) for g in f.heroes],
        "maps": f.maps, "wins": f.wins, "losses": f.losses,
        "win_rate": round(f.win_rate, 3), "samples": f.samples,
        "variants": len(f.variants),
    }


_SEG_LEAD = {"attack": "When attacking", "defend": "When defending"}


def narrate_map(team: str, map_name: str, segs: dict[str, Any]) -> str:
    """A plain-language summary of how a team opens a map, per segment. This is
    the wordier drill-down view; the team overview stays compact/structured."""
    parts: list[str] = []
    for seg, fams in segs.items():
        if not fams:
            continue
        top = fams[0]
        heroes = ", ".join(top["heroes"])
        rec = f'{top["wins"]}W-{top["losses"]}L'
        maps = top["maps"]
        if seg in _SEG_LEAD:
            lead = f'{_SEG_LEAD[seg]} {map_name}'
        elif seg == "all":
            lead = f'On {map_name}'
        else:
            lead = f'On {map_name} ({seg})'
        s = (f'{lead}, {team} opens {heroes} '
             f'({maps} map{"" if maps == 1 else "s"}, {rec}).')
        if top.get("variants", 1) > 1:
            s += f' They flex within it ({top["variants"]} lineups seen).'
        if len(fams) > 1:
            alt = fams[1]
            s += f' Otherwise: {", ".join(alt["heroes"])} ({alt["maps"]}).'
        parts.append(s)
    return " ".join(parts)


def narrate_swaps(team: str, swaps: list[dict[str, Any]]) -> str:
    """A sentence on how a team adapts mid-map, and what they answer."""
    if not swaps:
        return ""
    s = swaps[0]
    out, inn = ", ".join(s["out"]), ", ".join(s["in"])
    kind = "changes comp" if s["kind"] == "core" else "flexes"
    # ASCII only: these strings reach the Windows console via the CLI, which is
    # cp1252 and would crash on arrows/multiplication signs.
    txt = (f'Mid-map {team} most often {kind}: {out} -> {inn} '
           f'({s["count"]}x).')
    if s.get("vs"):
        txt += f' Usually against {", ".join(s["vs"][:3])}.'
    return txt


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

    # Per team: overall opening instances, per (map, segment) open+settled
    # instances, and the hero pool (which heroes they play at all).
    overall: dict[str, list[CompInstance]] = {}
    by_map: dict[str, dict[str, dict[str, dict[str, list[CompInstance]]]]] = {}
    pool: dict[str, dict[str, set[str]]] = {}     # team -> hero -> game keys
    team_games: dict[str, set[str]] = {}
    team_rounds: dict[str, set[str]] = {}
    for (mi, side), obs in games.items():
        team = _team_of(obs[0])
        if not team:
            continue
        obs.sort(key=lambda d: d.sample_ts_ms)
        won = obs[0].winner_side == side
        game_key = f"{mi}:{side}"
        first = obs[0]
        mp = first.map_name or "?"
        overall.setdefault(team, []).append(
            CompInstance(first.hero_guids, won, game_key))
        team_games.setdefault(team, set()).add(game_key)
        # Hero pool counts ROUNDS, not maps: a hero played every round of a map is
        # a staple, one played for a single point is not, and counting maps hides
        # that difference entirely.
        for d in obs:
            round_key = f"{game_key}:{d.round_no or 0}:{d.sub_map or ''}"
            team_rounds.setdefault(team, set()).add(round_key)
            for g in d.hero_guids:
                pool.setdefault(team, {}).setdefault(g, set()).add(round_key)
        # Per segment keep BOTH what they opened on and what they settled into —
        # the comp a team ends a point on is often the more useful intel.
        seg_first: dict[str, ObsDetail] = {}
        seg_last: dict[str, ObsDetail] = {}
        for d in obs:
            key = _segment(d) or "all"
            seg_first.setdefault(key, d)
            seg_last[key] = d
        for key, fd in seg_first.items():
            slot = by_map.setdefault(team, {}).setdefault(mp, {}).setdefault(
                key, {"open": [], "settled": []})
            slot["open"].append(CompInstance(fd.hero_guids, won, game_key))
            slot["settled"].append(
                CompInstance(seg_last[key].hero_guids, won, game_key))

    swaps = aggregate_swaps(details, roles, hero_names)
    swaps_by_map = aggregate_swaps(details, roles, hero_names, per_map=True)
    bans = ban_response(details, roles, hero_names)
    report: dict[str, dict[str, Any]] = {}
    teams = set(overall) | set(by_map)
    for team in teams:
        maps_out: dict[str, Any] = {}
        opens_only: dict[str, list[dict[str, Any]]] = {}
        for mp, segs in by_map.get(team, {}).items():
            fams = {
                seg: {
                    "open": [_family_dict(f, hero_names)
                             for f in cluster_comps(both["open"], roles)],
                    "settled": [_family_dict(f, hero_names)
                                for f in cluster_comps(both["settled"], roles)],
                }
                for seg, both in segs.items()
            }
            opens_only = {seg: v["open"] for seg, v in fams.items()}
            maps_out[mp] = {"segments": fams,
                            "swaps": swaps_by_map.get(_MAP_KEY.join((team, mp)), []),
                            "narrative": narrate_map(team, mp, opens_only)}
        total = len(team_games.get(team, ()))
        rounds_total = len(team_rounds.get(team, ()))
        hero_pool: list[dict[str, Any]] = [
            {"hero": hero_names.get(g, g), "role": roles.get(g), "rounds": len(ks),
             "pick_rate": round(len(ks) / rounds_total, 3) if rounds_total else 0.0}
            for g, ks in pool.get(team, {}).items()]
        hero_pool.sort(key=lambda r: (-int(r["rounds"]), str(r["hero"])))
        report[team] = {
            "overall": [_family_dict(f, hero_names)
                        for f in cluster_comps(overall.get(team, []), roles)],
            "maps": maps_out,
            "games": total,
            "rounds": rounds_total,
            "hero_pool": hero_pool,
            "swaps": swaps.get(team, []),
            "swap_narrative": narrate_swaps(team, swaps.get(team, [])),
            "ban_response": bans.get(team, []),
        }
    return report

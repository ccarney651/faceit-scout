"""Export and analysis over the ingested SQLite data."""

from __future__ import annotations

import csv
import html
import json
import os
import sqlite3
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any, TextIO

from ._dashboard import HTML_TEMPLATE
from .db import Database
from .hero_icons import load_hero_icons
from .models import is_playoff_name
from .subroles import SEAT_ORDER, seat_of
from .team_logos import build_team_logos

# On mirrored modes (Control, Flashpoint, Push) the sides are symmetric, so which
# team "attacks first" is competitively meaningless. Attack-order only matters on
# the asymmetric modes below.
ASYMMETRIC_CATEGORIES = ("Escort", "Hybrid")

_GAME_ROWS_SQL = """
SELECT m.id AS match_id, m.round, m.group_no, m.status, m.best_of,
       m.winner_faction AS match_winner,
       g.game_no, g.map_guid, mp.name AS map_name, g.map_category,
       g.faction1_score, g.faction2_score, g.winner_faction AS game_winner,
       g.attacking_first_faction, g.side_picked_by_faction,
       g.was_restarted, g.demo_code,
       t1.name AS faction1_team, t2.name AS faction2_team
FROM matches m
JOIN games g            ON g.match_id = m.id
LEFT JOIN maps mp       ON mp.guid = g.map_guid
LEFT JOIN teams t1      ON t1.id = m.faction1_team_id
LEFT JOIN teams t2      ON t2.id = m.faction2_team_id
WHERE m.championship_id = ?
ORDER BY m.round, m.group_no, m.id, g.game_no
"""


def export_csv(db: Database, championship_id: str, out: TextIO) -> int:
    rows = db.conn.execute(_GAME_ROWS_SQL, (championship_id,)).fetchall()
    if not rows:
        return 0
    writer = csv.DictWriter(out, fieldnames=list(rows[0].keys()))
    writer.writeheader()
    for r in rows:
        writer.writerow({k: r[k] for k in r})
    return len(rows)


def export_json(db: Database, championship_id: str, out: TextIO) -> int:
    c = db.conn
    matches = c.execute(
        "SELECT * FROM matches WHERE championship_id = ? ORDER BY round, group_no, id",
        (championship_id,),
    ).fetchall()
    result: list[dict[str, Any]] = []
    for m in matches:
        mid = m["id"]
        games = c.execute(
            "SELECT * FROM games WHERE match_id = ? ORDER BY game_no", (mid,)
        ).fetchall()
        game_objs: list[dict[str, Any]] = []
        for g in games:
            gno = g["game_no"]
            bans = c.execute(
                """SELECT hb.hero_guid, h.name AS hero_name, hb.ban_order,
                          hb.banned_by_faction
                   FROM hero_bans hb LEFT JOIN heroes h ON h.guid = hb.hero_guid
                   WHERE hb.match_id = ? AND hb.game_no = ? ORDER BY hb.ban_order""",
                (mid, gno),
            ).fetchall()
            players = c.execute(
                "SELECT * FROM round_players WHERE match_id = ? AND game_no = ?",
                (mid, gno),
            ).fetchall()
            game_objs.append({
                **_row(g),
                "hero_bans": [_row(b) for b in bans],
                "round_players": [_row(p) for p in players],
            })
        result.append({**_row(m), "games": game_objs})
    json.dump(result, out, indent=2)
    out.write("\n")
    return len(result)


def _row(r: sqlite3.Row) -> dict[str, Any]:
    return {k: r[k] for k in r}


def team_stats(db: Database, team_name: str) -> dict[str, Any] | None:
    """Ban tendencies, map picks and win rates for a team (by name)."""
    c = db.conn
    trow = c.execute(
        "SELECT id, name FROM teams WHERE name = ? COLLATE NOCASE", (team_name,)
    ).fetchone()
    if trow is None:
        return None
    team_id = trow["id"]

    # Which faction was this team, per match?  (a CTE reused below)
    side_cte = """
    WITH team_side AS (
        SELECT id AS match_id, winner_faction,
               CASE WHEN faction1_team_id = :tid THEN 'faction1'
                    WHEN faction2_team_id = :tid THEN 'faction2' END AS side
        FROM matches
        WHERE faction1_team_id = :tid OR faction2_team_id = :tid
    )
    """

    rec = c.execute(
        side_cte + """
        SELECT COUNT(*) AS matches,
               SUM(CASE WHEN winner_faction = side THEN 1 ELSE 0 END) AS wins
        FROM team_side""",
        {"tid": team_id},
    ).fetchone()
    matches = rec["matches"] or 0
    wins = rec["wins"] or 0

    game_rec = c.execute(
        side_cte + """
        SELECT COUNT(*) AS games,
               SUM(CASE WHEN g.winner_faction = ts.side THEN 1 ELSE 0 END) AS game_wins
        FROM team_side ts JOIN games g ON g.match_id = ts.match_id""",
        {"tid": team_id},
    ).fetchone()
    games = game_rec["games"] or 0
    game_wins = game_rec["game_wins"] or 0

    bans = c.execute(
        side_cte + """
        SELECT h.name AS hero, COUNT(*) AS n
        FROM team_side ts
        JOIN hero_bans hb ON hb.match_id = ts.match_id AND hb.banned_by_faction = ts.side
        LEFT JOIN heroes h ON h.guid = hb.hero_guid
        GROUP BY hb.hero_guid ORDER BY n DESC, hero""",
        {"tid": team_id},
    ).fetchall()

    picks = c.execute(
        side_cte + """
        SELECT mp2.name AS map, COUNT(*) AS n
        FROM team_side ts
        JOIN map_picks mpk ON mpk.match_id = ts.match_id AND mpk.picked_by_faction = ts.side
        LEFT JOIN maps mp2 ON mp2.guid = mpk.map_guid
        GROUP BY mpk.map_guid ORDER BY n DESC, map""",
        {"tid": team_id},
    ).fetchall()

    unattributed_bans = c.execute(
        side_cte + """
        SELECT COUNT(*) AS n
        FROM team_side ts
        JOIN hero_bans hb ON hb.match_id = ts.match_id
        WHERE hb.banned_by_faction IS NULL""",
        {"tid": team_id},
    ).fetchone()["n"] or 0

    return {
        "team": trow["name"],
        "team_id": team_id,
        "matches": matches,
        "match_wins": wins,
        "match_win_rate": round(wins / matches, 3) if matches else None,
        "games": games,
        "game_wins": game_wins,
        "game_win_rate": round(game_wins / games, 3) if games else None,
        "ban_tendencies": [{"hero": b["hero"], "count": b["n"]} for b in bans],
        "map_picks": [{"map": p["map"], "count": p["n"]} for p in picks],
        "bans_with_unknown_attribution": unattributed_bans,
    }


# --- self-contained HTML dashboard -------------------------------------------

def _attack_first_panels(
    game_rows: list[Any], attack_cycles: Mapping[str, Any]
) -> tuple[dict[str, Any], dict[str, Any]]:
    """(total, extra) attacking-first panels using the DECIDING attack/defend cycle.
    Normal games (max score <= 3) use FACEIT's round-1 attacker; extra-round games
    (score > 3) use owscout's round-3 attacker from ``attack_cycles`` and are
    dropped when not captured. Each panel: {by_map:[{name,category,games,
    atk_first_wins}], total_games, atk_first_wins}."""
    from collections import defaultdict
    cat: dict[str, str] = {}
    tot: dict[str, list[int]] = defaultdict(lambda: [0, 0])   # map -> [games, wins]
    ext: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    tg = tw = eg = ew = 0
    for r in game_rows:
        mp = r["name"]
        cat[mp] = r["category"]
        s1, s2 = r["faction1_score"] or 0, r["faction2_score"] or 0
        if max(s1, s2) <= 3:                        # normal 2-round game -> round 1
            if r["attacking_first_faction"] and r["winner_faction"]:
                won = 1 if r["winner_faction"] == r["attacking_first_faction"] else 0
                tot[mp][0] += 1
                tot[mp][1] += won
                tg += 1
                tw += won
        else:                                       # extra rounds -> round-3 attacker
            ci = attack_cycles.get(f"{r['match_id']}:{r['game_no']}")
            if ci and ci.get("decider") == 3:
                won = 1 if ci.get("won") else 0
                tot[mp][0] += 1
                tot[mp][1] += won
                tg += 1
                tw += won
                ext[mp][0] += 1
                ext[mp][1] += won
                eg += 1
                ew += won

    def panel(agg: dict[str, list[int]], g: int, w: int) -> dict[str, Any]:
        by_map = [{"name": mp, "category": cat[mp], "games": v[0], "atk_first_wins": v[1]}
                  for mp, v in sorted(agg.items(), key=lambda kv: -kv[1][0])]
        return {"by_map": by_map, "total_games": g, "atk_first_wins": w}
    return panel(tot, tg, tw), panel(ext, eg, ew)


def _dashboard_data(db: Database, cid: str,
                    attack_cycles: Mapping[str, Any] | None = None) -> dict[str, Any]:
    from collections import Counter, defaultdict
    c = db.conn

    def _p(a: tuple[Any, ...]) -> Any:
        # allow either named params (a single dict) or positional (a tuple)
        return a[0] if len(a) == 1 and isinstance(a[0], dict) else a

    def rows(sql: str, *a: Any) -> list[dict[str, Any]]:
        return [dict(r) for r in c.execute(sql, _p(a)).fetchall()]

    def scalar(sql: str, *a: Any) -> Any:
        r = c.execute(sql, _p(a)).fetchone()
        return None if r is None else r[0]

    champ = c.execute("SELECT * FROM championships WHERE id=?", (cid,)).fetchone()
    in_champ = "(SELECT id FROM matches WHERE championship_id=:c)"

    summary = {
        "championship": champ["name"] if champ else cid,
        "region": champ["region"] if champ else None,
        # Counts are of PLAYED matches only. Scheduled/upcoming fixtures live in
        # `upcoming` below and must not inflate totals or (worse) read as walkovers.
        "matches": scalar("SELECT COUNT(*) FROM matches WHERE championship_id=? AND status='FINISHED'", cid),
        "forfeits": scalar("SELECT COUNT(*) FROM matches WHERE championship_id=? AND status='FINISHED' AND forfeit=1", cid),
        "walkovers": scalar("""SELECT COUNT(*) FROM matches m WHERE m.championship_id=:c AND m.status='FINISHED'
            AND NOT EXISTS (SELECT 1 FROM games g WHERE g.match_id=m.id AND g.map_guid IS NOT NULL)""", {"c": cid}),
        "played_games": scalar(f"SELECT COUNT(*) FROM games WHERE match_id IN {in_champ} AND map_guid IS NOT NULL", {"c": cid}),
        "teams": scalar("SELECT COUNT(DISTINCT id) FROM teams WHERE id IN "
                        "(SELECT faction1_team_id FROM matches WHERE championship_id=:c "
                        "UNION SELECT faction2_team_id FROM matches WHERE championship_id=:c)", {"c": cid}),
        "players": scalar(f"SELECT COUNT(DISTINCT player_id) FROM round_players WHERE match_id IN {in_champ}", {"c": cid}),
        "date_from": scalar("SELECT MIN(finished_at) FROM matches WHERE championship_id=?", cid),
        "date_to": scalar("SELECT MAX(finished_at) FROM matches WHERE championship_id=?", cid),
        "matches_with_attribution": scalar(
            f"SELECT COUNT(DISTINCT match_id) FROM hero_bans WHERE banned_by_faction IS NOT NULL AND match_id IN {in_champ}", {"c": cid}),
        "restarted_games": scalar(f"SELECT COUNT(*) FROM games WHERE was_restarted=1 AND match_id IN {in_champ}", {"c": cid}),
        "dc_games": scalar(f"SELECT COUNT(DISTINCT match_id||'/'||game_no) FROM round_players WHERE stats_captured=0 AND match_id IN {in_champ}", {"c": cid}),
    }

    teams = rows("""
      WITH sides AS (
        SELECT id mid, winner_faction wf, faction1_team_id t1, faction2_team_id t2
        FROM matches WHERE championship_id=:c AND status='FINISHED'
      ), tm AS (
        SELECT t1 team, CASE WHEN wf='faction1' THEN 1 ELSE 0 END win FROM sides WHERE t1 IS NOT NULL
        UNION ALL
        SELECT t2 team, CASE WHEN wf='faction2' THEN 1 ELSE 0 END win FROM sides WHERE t2 IS NOT NULL
      ), gm AS (
        SELECT g.match_id mid, g.faction1_score f1s, g.faction2_score f2s,
               m.faction1_team_id t1, m.faction2_team_id t2
        FROM games g JOIN matches m ON m.id=g.match_id
        WHERE m.championship_id=:c AND g.map_guid IS NOT NULL
      ), tg AS (
        SELECT team, SUM(games) games, SUM(wins) wins FROM (
          SELECT t1 team, COUNT(*) games,
                 SUM(CASE WHEN f1s > f2s THEN 1 ELSE 0 END) wins
          FROM gm WHERE t1 IS NOT NULL GROUP BY t1
          UNION ALL
          SELECT t2 team, COUNT(*),
                 SUM(CASE WHEN f2s > f1s THEN 1 ELSE 0 END)
          FROM gm WHERE t2 IS NOT NULL GROUP BY t2
        ) GROUP BY team
      )
      SELECT te.name, COUNT(*) matches, SUM(win) wins,
             MAX(tg.games) games, MAX(tg.wins) game_wins,
             ROUND(100.0*SUM(win)/COUNT(*),1) win_pct,
             ROUND(100.0*MAX(tg.wins)/NULLIF(MAX(tg.games),0),1) map_win_pct
      FROM tm JOIN teams te ON te.id=tm.team
      LEFT JOIN tg ON tg.team=tm.team
      GROUP BY tm.team
      ORDER BY win_pct DESC, wins DESC""", {"c": cid})

    # Current roster per team, rolled up from round_players: who has played for
    # each team, most-recent + most-used first, so a scout sees the squad at a
    # glance. One row per game played, so `games` counts maps (a bo3 = up to 3).
    # `last_seen` is the match date, used to sort and to flag the last lineup.
    # Stats + elo ride along on the same rows: FACEIT reports them for every player
    # of every match, so these are the one player signal that works at full league
    # coverage — no capture required. Zeroed (hazard A) rows are stored NULL, so the
    # stat sample is counted separately from maps played.
    roster_rows = rows("""
      SELECT te.name team, rp.player_id pid,
             COALESCE(p.nickname, rp.player_id) nick, p.game_name gname,
             rp.role role, m.finished_at fin, rp.elo_snapshot elo,
             rp.eliminations e, rp.deaths d, rp.damage dmg,
             rp.healing heal, rp.damage_mitigated mit
      FROM round_players rp
      JOIN matches m ON m.id=rp.match_id
      JOIN teams te ON te.id=rp.team_id
      LEFT JOIN players p ON p.id=rp.player_id
      WHERE m.championship_id=:c AND rp.team_id IS NOT NULL""", {"c": cid})
    _agg: dict[tuple[str, str], dict[str, Any]] = {}
    _roles: dict[tuple[str, str], Counter[str]] = defaultdict(Counter)
    _last_match: dict[str, str] = {}          # team -> its most recent match date
    _STAT_KEYS = ("e", "d", "dmg", "heal", "mit")
    for rr in roster_rows:
        key = (rr["team"], rr["pid"])
        a = _agg.setdefault(key, {"nick": rr["nick"], "game_name": rr["gname"],
                                  "games": 0, "last_seen": "", "elo": None,
                                  "elo_at": "", "sgames": 0,
                                  **{k: 0 for k in _STAT_KEYS}})
        a["games"] += 1
        fin = rr["fin"] or ""
        if fin > a["last_seen"]:
            a["last_seen"] = fin
        if fin > _last_match.get(rr["team"], ""):
            _last_match[rr["team"]] = fin
        if rr["role"]:
            _roles[key][rr["role"]] += 1
        # Elo is a snapshot per game; the most recent one is the current rating.
        if rr["elo"] is not None and fin >= a["elo_at"]:
            a["elo"], a["elo_at"] = int(rr["elo"]), fin
        if rr["e"] is not None and rr["d"] is not None:
            a["sgames"] += 1
            for k, col in zip(_STAT_KEYS, ("e", "d", "dmg", "heal", "mit"), strict=True):
                a[k] += rr[col] or 0
    team_rosters: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for (team, pid), a in _agg.items():
        rc = _roles[(team, pid)]
        n = a["sgames"]
        stats = None
        if n:
            # Per-map averages, and k/d on the season totals (not a mean of ratios).
            stats = {
                "games": n,
                "elims": round(a["e"] / n, 1), "deaths": round(a["d"] / n, 1),
                "dmg": round(a["dmg"] / n), "heal": round(a["heal"] / n),
                "mit": round(a["mit"] / n),
                "kd": round(a["e"] / max(a["d"], 1), 2),
            }
        team_rosters[team].append({
            "nick": a["nick"], "game_name": a["game_name"], "games": a["games"],
            "last_seen": a["last_seen"], "elo": a["elo"], "stats": stats,
            "role": rc.most_common(1)[0][0] if rc else None,
            # Played in the team's most recent match = part of the current lineup.
            "current": bool(a["last_seen"]) and a["last_seen"] == _last_match.get(team, ""),
        })
    for _team, pls in team_rosters.items():
        pls.sort(key=lambda x: (x["last_seen"], x["games"]), reverse=True)
    for t in teams:
        t["roster"] = team_rosters.get(t["name"], [])

    heroes = rows(f"""
      SELECT h.name, h.role, h.guid, COUNT(*) bans
      FROM hero_bans b JOIN heroes h ON h.guid=b.hero_guid
      WHERE b.match_id IN {in_champ} GROUP BY b.hero_guid ORDER BY bans DESC""", {"c": cid})
    bans_by_role = rows(f"""
      SELECT h.role, COUNT(*) n FROM hero_bans b JOIN heroes h ON h.guid=b.hero_guid
      WHERE b.match_id IN {in_champ} GROUP BY h.role ORDER BY n DESC""", {"c": cid})

    maps = rows(f"""
      SELECT mp.name, mp.category, COUNT(*) games
      FROM games g JOIN maps mp ON mp.guid=g.map_guid
      WHERE g.map_guid IS NOT NULL AND g.match_id IN {in_champ}
      GROUP BY g.map_guid ORDER BY games DESC""", {"c": cid})

    # Attack-first advantage (asymmetric modes). Uses the DECIDING attack/defend
    # cycle: round 1 for normal games (FACEIT), round 3 for games that went to
    # extra rounds (owscout capture, keyed match:game). Uncaptured extra-round
    # games can't be decided and drop out. Two panels: total and extra-round only.
    ph = ",".join("?" for _ in ASYMMETRIC_CATEGORIES)
    atk_rows = rows(f"""
      SELECT mp.name, mp.category, g.faction1_score, g.faction2_score,
             g.attacking_first_faction, g.winner_faction, g.match_id, g.game_no
      FROM games g JOIN maps mp ON mp.guid=g.map_guid
      WHERE mp.category IN ({ph})
        AND g.match_id IN (SELECT id FROM matches WHERE championship_id=?)""",
      *ASYMMETRIC_CATEGORIES, cid)
    atk_panel, atk_extra = _attack_first_panels(atk_rows, attack_cycles or {})

    matches: list[dict[str, Any]] = []
    team_names: set[str] = set()
    team_avatars: dict[str, str | None] = {}
    for m in c.execute("""SELECT m.*, t1.name f1name, t2.name f2name,
                                 t1.avatar_url f1avatar, t2.avatar_url f2avatar
                          FROM matches m LEFT JOIN teams t1 ON t1.id=m.faction1_team_id
                                         LEFT JOIN teams t2 ON t2.id=m.faction2_team_id
                          WHERE m.championship_id=? AND m.status='FINISHED'
                          ORDER BY m.round, m.group_no, m.id""", (cid,)):
        f1, f2 = m["f1name"], m["f2name"]
        a1, a2 = m["f1avatar"], m["f2avatar"]
        if f1:
            team_names.add(f1)
            if a1 and not team_avatars.get(f1):
                team_avatars[f1] = a1
        if f2:
            team_names.add(f2)
            if a2 and not team_avatars.get(f2):
                team_avatars[f2] = a2

        def team_of(faction: str | None, *, f1: str = f1, f2: str = f2) -> str | None:
            return f1 if faction == "faction1" else f2 if faction == "faction2" else None

        # team_id -> team name, so per-game rosters can be grouped by side.
        tid_name = {m["faction1_team_id"]: f1, m["faction2_team_id"]: f2}

        gs: list[dict[str, Any]] = []
        for g in rows("""SELECT g.game_no, mp.name map, g.map_category, g.faction1_score f1,
                                g.faction2_score f2, g.winner_faction, g.was_restarted, g.demo_code
                         FROM games g LEFT JOIN maps mp ON mp.guid=g.map_guid
                         WHERE g.match_id=? ORDER BY g.game_no""", m["id"]):
            gno = g["game_no"]
            bans = [
                {"hero": b["hero"], "role": b["role"], "faction": b["faction"],
                 "team": team_of(b["faction"]), "order": b["ban_order"]}
                for b in rows("""SELECT h.name hero, h.role, hb.banned_by_faction faction, hb.ban_order
                                 FROM hero_bans hb LEFT JOIN heroes h ON h.guid=hb.hero_guid
                                 WHERE hb.match_id=? AND hb.game_no=? ORDER BY hb.ban_order""",
                              m["id"], gno)
            ]
            mp_by = scalar("SELECT picked_by_faction FROM map_picks WHERE match_id=? AND game_no=?",
                           m["id"], gno)
            # Per-game rosters: which 5 played for each team, with role + stats.
            by_team: dict[str, list[dict[str, Any]]] = {}
            for rp in rows("""SELECT rp.team_id, COALESCE(p.nickname, rp.player_id) nick,
                                     rp.role, rp.stats_captured cap, rp.eliminations e,
                                     rp.deaths d, rp.damage dmg, rp.healing heal
                              FROM round_players rp LEFT JOIN players p ON p.id=rp.player_id
                              WHERE rp.match_id=? AND rp.game_no=?""", m["id"], gno):
                tname = tid_name.get(rp["team_id"]) or "?"
                by_team.setdefault(tname, []).append({
                    "nick": rp["nick"], "role": rp["role"], "cap": bool(rp["cap"]),
                    "e": rp["e"], "d": rp["d"], "dmg": rp["dmg"], "heal": rp["heal"],
                })
            rosters = [{"team": t, "players": pls} for t, pls in by_team.items()]
            gs.append({
                "game_no": gno, "map": g["map"], "map_category": g["map_category"],
                "f1": g["f1"], "f2": g["f2"], "winner_faction": g["winner_faction"],
                "winner_team": team_of(g["winner_faction"]),
                "was_restarted": g["was_restarted"], "demo_code": g["demo_code"],
                "map_picked_by": team_of(mp_by), "bans": bans, "rosters": rosters,
            })
        s1 = sum(1 for g in gs if g["winner_faction"] == "faction1")
        s2 = sum(1 for g in gs if g["winner_faction"] == "faction2")
        matches.append({
            "id": m["id"], "round": m["round"], "group": m["group_no"],
            "finished_at": m["finished_at"],  # ISO8601 — sorts lexicographically
            "f1": f1, "f2": f2,
            "forfeit": bool(m["forfeit"]),
            "walkover": not any(g["map"] for g in gs),
            "series": f"{s1}-{s2}", "winner": m["winner_faction"],
            "winner_team": team_of(m["winner_faction"]), "best_of": m["best_of"],
            "games": gs,
        })

    # Upcoming fixtures: matches ingested but not yet FINISHED (status SCHEDULED /
    # ongoing). Teams may be TBD in a bracket's later rounds -> name is NULL.
    upcoming = rows("""
      SELECT m.id, m.round, m.group_no "group", m.scheduled_at, m.status, m.best_of,
             t1.name f1, t2.name f2
      FROM matches m LEFT JOIN teams t1 ON t1.id=m.faction1_team_id
                     LEFT JOIN teams t2 ON t2.id=m.faction2_team_id
      WHERE m.championship_id=:c AND m.status!='FINISHED'
      ORDER BY (m.scheduled_at IS NULL), m.scheduled_at, m.round, m.group_no""", {"c": cid})

    return {
        "summary": summary, "teams": teams, "heroes": heroes,
        "bans_by_role": bans_by_role, "maps": maps,
        "attacking_first": atk_panel,
        "attacking_first_extra": atk_extra,
        "matches": matches,
        "upcoming": upcoming,
        "team_names": sorted(team_names),
        "team_avatars": team_avatars,
    }


# The FACEIT League skill tiers, strongest to weakest. Championship names carry
# the tier word ("S9 EMEA Master Central …", "… Expert …", "… Advanced …",
# "… Open …"). Order drives the site's division switcher (strongest first).
TIERS: tuple[str, ...] = ("Master", "Expert", "Advanced", "Open")


def _tier_of(name: str | None) -> str | None:
    """The skill tier a championship name encodes, or None (see :data:`TIERS`)."""
    if not name:
        return None
    return next((t for t in TIERS if t in name), None)


REGIONS: tuple[str, ...] = ("EMEA", "NA")


def _region_of(name: str | None) -> str | None:
    """The region a championship name encodes ('EMEA' | 'NA' | None).

    Matched as a WHOLE WORD, mirroring ``owscout.db.list_codes``: a bare
    substring test would classify any name merely containing those letters
    ("Open Nationals") as NA. Harmless while the site shipped one region and
    EMEA was tested first; load-bearing now that a mis-classified division
    would land in the wrong region's switcher.
    """
    if not name:
        return None
    words = name.upper().replace("-", " ").split()
    return next((r for r in REGIONS if r in words), None)


def _is_playoff(name: str | None) -> bool:
    """A playoff/knockout championship, separate from the '... - Regular Season'
    divisions. Its matches feed the Playoffs tab as real results but must NOT
    enter regular-season standings/meta — so it's classified out of the tier
    views and attached to the matching division instead."""
    return is_playoff_name(name)


def export_html(db: Database, out: TextIO, championship_id: str | None = None,
                only_tier: str | None = None, only_region: str | None = None,
                data_path: str | None = None) -> int:
    """Render the multi-division dashboard.

    With ``championship_id`` set, only that division is included; otherwise every
    championship in the database becomes a switchable division. ``only_tier``
    (master/expert/advanced/open) and ``only_region`` ('emea'/'na') restrict the
    dashboard; the DB may hold several divisions across tiers and regions.
    Returns the number of divisions with data.
    """
    want_tier: str | None = None
    if only_tier:
        w = only_tier.strip().lower()
        want_tier = next((t for t in TIERS if t.lower() == w), None)
    want_region: str | None = None
    if only_region:
        w = only_region.strip().lower()
        want_region = "EMEA" if w.startswith("e") else "NA" if w.startswith("n") else None

    if championship_id:
        cids = [championship_id]
    else:
        rows = db.conn.execute("SELECT id, name FROM championships ORDER BY name").fetchall()
        if want_tier:
            rows = [r for r in rows if _tier_of(r["name"]) == want_tier]
        if want_region:
            rows = [r for r in rows if _region_of(r["name"]) == want_region]
        cids = [str(r["id"]) for r in rows]

    # Split off playoff championships: they become the Playoffs tab's real results
    # (attached to their region+tier division below), never their own view/standings.
    name_by_cid = {str(r["id"]): r["name"] for r in
                   db.conn.execute("SELECT id, name FROM championships").fetchall()}
    playoff_cids = [cid for cid in cids if _is_playoff(name_by_cid.get(cid))]
    cids = [cid for cid in cids if cid not in set(playoff_cids)]

    # Captured comps synced in from owscout (if present). Loaded once, up front, so
    # the per-game deciding-cycle data (attack_cycles) can feed each division's
    # attacking-first panel. Team-keyed JSON from `owscout ... contribute merge`.
    owscout_comps: dict[str, object] = {}
    owscout_captured: list[str] = []
    owscout_wipe: object = None
    owscout_cycles: dict[str, object] = {}
    owscout_pergame: dict[str, object] = {}
    owscout_pergame_players: dict[str, object] = {}
    owscout_contributors: list[object] = []
    oc_path = os.environ.get("OWSCOUT_COMPS", "owscout_comps.json")
    if os.path.exists(oc_path):
        try:
            with open(oc_path, encoding="utf-8") as fh:
                oc = json.load(fh)
            owscout_comps = oc.get("teams", {})
            owscout_captured = list(oc.get("captured_games", []))
            owscout_wipe = oc.get("code_wipe_date")
            owscout_cycles = oc.get("attack_cycles", {})
            owscout_pergame = oc.get("per_game_comps", {})
            owscout_pergame_players = oc.get("per_game_players", {})
            owscout_contributors = oc.get("contributor_stats", [])
        except (json.JSONDecodeError, OSError):
            owscout_comps = {}

    divisions: dict[str, Any] = {}
    heroes: dict[str, Any] = {}
    maps: dict[str, Any] = {}
    team_avatars: dict[str, str | None] = {}
    ordered: list[tuple[str, str]] = []
    for cid in cids:
        d = _dashboard_data(db, cid, attack_cycles=owscout_cycles)
        if not d["summary"]["matches"]:
            continue
        for h in d.pop("heroes"):
            heroes.setdefault(h["name"], {"name": h["name"], "role": h["role"]})
        for m in d.pop("maps"):
            maps.setdefault(m["name"], {"name": m["name"], "category": m["category"]})
        for name, url in d.pop("team_avatars", {}).items():
            if url and not team_avatars.get(name):
                team_avatars[name] = url
        d.pop("bans_by_role", None)
        divisions[cid] = d
        ordered.append((str(d["summary"]["championship"]), cid))

    if not divisions:
        return 0

    # Attach each playoff championship's played series to the matching region+tier
    # division, so the Playoffs tab shows real results the moment those matches are
    # ingested — without polluting regular-season standings/meta (separate
    # championship). A no-op until a "... - Playoffs" championship exists.
    if playoff_cids:
        rt_reg = {}
        for cid, d in divisions.items():
            r, t = _region_of(str(d["summary"]["championship"])), _tier_of(str(d["summary"]["championship"]))
            if r and t:
                rt_reg[(r, t)] = cid
        for pcid in playoff_cids:
            pnm = name_by_cid.get(pcid)
            preg, ptier = _region_of(pnm), _tier_of(pnm)
            reg_cid = rt_reg.get((preg, ptier)) if preg and ptier else None
            if not reg_cid:
                continue
            pd = _dashboard_data(db, pcid, attack_cycles=owscout_cycles)
            # A bracket entry per playoff match — finished (with a result) and
            # scheduled (upcoming slot). TBD slots (teams not yet resolved) carry
            # NULL team names. The Playoffs tab lays these out by round.
            # Finished entries carry the FULL match object (id, per-game maps/
            # scores/rosters/replay codes) so a scouted playoff game gets the same
            # match page + comps preview as a regular-season one; the bracket and
            # detail page both read this same array. `status` is added here — the
            # finished match dict doesn't carry it, and the bracket lays finished
            # vs upcoming out by it.
            bracket = [
                {**m, "status": "FINISHED", "playoff": True}
                for m in pd["matches"]
            ] + [
                {**u, "forfeit": False, "finished_at": None,
                 "winner_team": None, "series": None, "playoff": True}
                for u in pd["upcoming"]
            ]
            if bracket:
                divisions[reg_cid].setdefault("playoffs", []).extend(bracket)

    # Build the switcher "views": every division present in a region (tiers
    # strongest-first, see TIERS), then a merged "Combined" of all of them — so
    # EMEA Master/Expert/Advanced/Open/Combined, then the same for NA. Region and
    # tier are read from the championship name.
    by_region_tier: dict[tuple[str, str], str] = {}
    for cid, d in divisions.items():
        nm = str(d["summary"]["championship"])
        r, t = _region_of(nm), _tier_of(nm)
        if r and t:
            by_region_tier[(r, t)] = cid

    views: list[dict[str, Any]] = []
    used: set[str] = set()
    for region in REGIONS:
        present = [(t, by_region_tier[(region, t)]) for t in TIERS
                   if (region, t) in by_region_tier]
        for t, cid in present:
            views.append({"id": cid, "label": f"{region} {t}",
                          "divisions": [cid], "region": region})
            used.add(cid)
        if len(present) > 1:
            views.append({"id": f"{region.lower()}-combined", "label": f"{region} Combined",
                          "divisions": [cid for _, cid in present], "region": region})
    # Any division whose name didn't classify still gets a plain view (fallback).
    for name, cid in sorted(ordered):
        if cid not in used:
            views.append({"id": cid, "label": name, "divisions": [cid], "region": None})

    # Full hero roster (every hero, not just those banned this season) so the draft
    # simulator can ban off-meta picks like Torbjörn that never show up in the data.
    roster = [
        {"name": r["name"], "role": r["role"]}
        for r in db.conn.execute(
            "SELECT name, role FROM heroes ORDER BY name"
        ).fetchall()
    ]

    # Inline team logos so the dashboard remains a single self-contained file.
    # This call fetches only logos that are not already cached; failures degrade
    # to "no logo" rather than breaking the build.
    inlined_team_avatars = build_team_logos(team_avatars)

    data = {
        "divisions": divisions,
        "views": views,
        "heroes": [dict(h, subrole=seat_of(str(h.get("name") or ""))) for h in heroes.values()],
        "roster": roster,
        "maps": list(maps.values()),
        "owscout_comps": owscout_comps,
        "owscout_captured": owscout_captured,
        "owscout_pergame": owscout_pergame,
        "owscout_pergame_players": owscout_pergame_players,
        "owscout_contributors": owscout_contributors,
        "team_avatars": inlined_team_avatars,
        "code_wipe": owscout_wipe,
        # When this page was generated - so anyone can tell at a glance whether
        # their contribution has landed yet.
        # Where the page asks for an on-demand rebuild (the upload worker).
        "refresh_endpoint": os.environ.get(
            "OWSCOUT_REFRESH_ENDPOINT",
            "https://owscout-upload.owscout.workers.dev/refresh"),
        "seat_order": list(SEAT_ORDER),
        "built_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        # Inlined hero portraits so comps read as icons, not five words. Empty
        # when the art isn't present; the page then falls back to text chips.
        "hero_icons": load_hero_icons(),
    }
    title = "FACEIT OW2 — League Scouting"
    # ensure_ascii + escaping every `<` as \u003c closes the `<!--` breakout hole
    # as well as the `</script>` one: a leading "<!" in any string can't begin an
    # HTML comment inside the inlined blob. json.loads() (and JSON.parse) decode
    # \u003c back to `<` transparently, so the round-trip is lossless.
    payload = json.dumps(data, ensure_ascii=True).replace("<", "\\u003c")
    if data_path:
        # Shell build: the data lives in a sibling file the page fetches. This is
        # the seam next-season gating hooks into (serve data.json from the
        # authenticated Worker instead of Pages). The page stays a static shell.
        with open(data_path, "w", encoding="utf-8") as dh:
            dh.write(payload)
        inline = "// data.json is fetched at runtime (shell build)"
    else:
        # Single-file build (default): data inlined, so index.html works offline
        # and from file:// with nothing else to serve.
        inline = f"var __OWSCOUT_DATA__={payload};"
    out.write(HTML_TEMPLATE.replace("__TITLE__", html.escape(title))
                           .replace("// __DATA_INLINE__", inline))
    return len(divisions)

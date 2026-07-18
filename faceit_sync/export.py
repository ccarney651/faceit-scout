"""Export and analysis over the ingested SQLite data."""

from __future__ import annotations

import csv
import html
import json
from datetime import datetime, timezone
import os
import sqlite3
from typing import Any, Optional, TextIO

from ._dashboard import HTML_TEMPLATE
from .db import Database
from .hero_icons import load_hero_icons

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
        writer.writerow({k: r[k] for k in r.keys()})
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
    return {k: r[k] for k in r.keys()}


def team_stats(db: Database, team_name: str) -> Optional[dict[str, Any]]:
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

def _dashboard_data(db: Database, cid: str) -> dict[str, Any]:
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
        "matches": scalar("SELECT COUNT(*) FROM matches WHERE championship_id=?", cid),
        "forfeits": scalar("SELECT COUNT(*) FROM matches WHERE championship_id=? AND forfeit=1", cid),
        "walkovers": scalar(f"""SELECT COUNT(*) FROM matches m WHERE m.championship_id=:c
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
        FROM matches WHERE championship_id=:c
      ), tm AS (
        SELECT t1 team, CASE WHEN wf='faction1' THEN 1 ELSE 0 END win FROM sides WHERE t1 IS NOT NULL
        UNION ALL
        SELECT t2 team, CASE WHEN wf='faction2' THEN 1 ELSE 0 END win FROM sides WHERE t2 IS NOT NULL
      )
      SELECT te.name, COUNT(*) matches, SUM(win) wins,
             ROUND(100.0*SUM(win)/COUNT(*),1) win_pct
      FROM tm JOIN teams te ON te.id=tm.team GROUP BY tm.team
      ORDER BY win_pct DESC, wins DESC""", {"c": cid})

    heroes = rows(f"""
      SELECT h.name, h.role, COUNT(*) bans
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

    # Attack-first advantage, asymmetric modes only (Escort/Hybrid).
    ph = ",".join("?" for _ in ASYMMETRIC_CATEGORIES)
    atk = rows(f"""
      SELECT mp.name, mp.category, COUNT(*) games,
             SUM(CASE WHEN g.winner_faction=g.attacking_first_faction THEN 1 ELSE 0 END) atk_first_wins
      FROM games g JOIN maps mp ON mp.guid=g.map_guid
      WHERE g.attacking_first_faction IS NOT NULL AND g.winner_faction IS NOT NULL
        AND mp.category IN ({ph}) AND g.match_id IN (SELECT id FROM matches WHERE championship_id=?)
      GROUP BY g.map_guid ORDER BY games DESC""", *ASYMMETRIC_CATEGORIES, cid)
    atk_total = c.execute(f"""
      SELECT COUNT(*) games,
             SUM(CASE WHEN g.winner_faction=g.attacking_first_faction THEN 1 ELSE 0 END) w
      FROM games g JOIN maps mp ON mp.guid=g.map_guid
      WHERE g.attacking_first_faction IS NOT NULL AND g.winner_faction IS NOT NULL
        AND mp.category IN ({ph}) AND g.match_id IN (SELECT id FROM matches WHERE championship_id=?)""",
      (*ASYMMETRIC_CATEGORIES, cid)).fetchone()

    matches: list[dict[str, Any]] = []
    team_names: set[str] = set()
    for m in c.execute("""SELECT m.*, t1.name f1name, t2.name f2name
                          FROM matches m LEFT JOIN teams t1 ON t1.id=m.faction1_team_id
                                         LEFT JOIN teams t2 ON t2.id=m.faction2_team_id
                          WHERE m.championship_id=? ORDER BY m.round, m.group_no, m.id""", (cid,)):
        f1, f2 = m["f1name"], m["f2name"]
        if f1:
            team_names.add(f1)
        if f2:
            team_names.add(f2)

        def team_of(faction: Optional[str]) -> Optional[str]:
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
            "f1": f1, "f2": f2, "forfeit": bool(m["forfeit"]),
            "walkover": not any(g["map"] for g in gs),
            "series": f"{s1}-{s2}", "winner": m["winner_faction"],
            "winner_team": team_of(m["winner_faction"]), "best_of": m["best_of"],
            "games": gs,
        })

    return {
        "summary": summary, "teams": teams, "heroes": heroes,
        "bans_by_role": bans_by_role, "maps": maps,
        "attacking_first": {
            "by_map": atk,
            "total_games": atk_total["games"] or 0,
            "atk_first_wins": atk_total["w"] or 0,
        },
        "matches": matches,
        "team_names": sorted(team_names),
    }


def export_html(db: Database, out: TextIO, championship_id: Optional[str] = None) -> int:
    """Render the multi-division dashboard.

    With ``championship_id`` set, only that division is included; otherwise every
    championship in the database becomes a switchable division. Returns the number
    of divisions with data.
    """
    if championship_id:
        cids = [championship_id]
    else:
        cids = [str(r["id"]) for r in
                db.conn.execute("SELECT id FROM championships ORDER BY name").fetchall()]

    divisions: dict[str, Any] = {}
    heroes: dict[str, Any] = {}
    maps: dict[str, Any] = {}
    ordered: list[tuple[str, str]] = []
    for cid in cids:
        d = _dashboard_data(db, cid)
        if not d["summary"]["matches"]:
            continue
        for h in d.pop("heroes"):
            heroes.setdefault(h["name"], {"name": h["name"], "role": h["role"]})
        for m in d.pop("maps"):
            maps.setdefault(m["name"], {"name": m["name"], "category": m["category"]})
        d.pop("bans_by_role", None)
        divisions[cid] = d
        ordered.append((str(d["summary"]["championship"]), cid))

    if not divisions:
        return 0

    # Build the switcher "views": each real division, plus a merged "Combined"
    # per region (Master + Expert), in the order EMEA Master/Expert/Combined then
    # NA Master/Expert/Combined. Region/tier are read from the championship name.
    def region_of(name: str) -> Optional[str]:
        u = name.upper()
        return "EMEA" if "EMEA" in u else "NA" if "NA" in u else None

    def tier_of(name: str) -> Optional[str]:
        return "Master" if "Master" in name else "Expert" if "Expert" in name else None

    by_region_tier: dict[tuple[str, str], str] = {}
    for cid, d in divisions.items():
        nm = str(d["summary"]["championship"])
        r, t = region_of(nm), tier_of(nm)
        if r and t:
            by_region_tier[(r, t)] = cid

    views: list[dict[str, Any]] = []
    used: set[str] = set()
    for region in ("EMEA", "NA"):
        m, e = by_region_tier.get((region, "Master")), by_region_tier.get((region, "Expert"))
        if m:
            views.append({"id": m, "label": f"{region} Master", "divisions": [m], "region": region})
            used.add(m)
        if e:
            views.append({"id": e, "label": f"{region} Expert", "divisions": [e], "region": region})
            used.add(e)
        if m and e:
            views.append({"id": f"{region.lower()}-combined", "label": f"{region} Combined",
                          "divisions": [m, e], "region": region})
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

    # Captured comps synced in from owscout (if present). Team-keyed JSON written
    # by `owscout export --format dashboard --out owscout_comps.json`; the operator
    # commits it and the dashboard renders it on team Scout pages. Git-native sync,
    # no shared database.
    owscout_comps: dict[str, object] = {}
    owscout_captured: list[str] = []
    owscout_wipe: object = None
    oc_path = os.environ.get("OWSCOUT_COMPS", "owscout_comps.json")
    if os.path.exists(oc_path):
        try:
            with open(oc_path, encoding="utf-8") as fh:
                oc = json.load(fh)
            owscout_comps = oc.get("teams", {})
            # "match_id:game_no" keys of captured games - drives the scouted
            # badges and each team's still-to-scout queue on the page.
            owscout_captured = list(oc.get("captured_games", []))
            owscout_wipe = oc.get("code_wipe_date")
        except (json.JSONDecodeError, OSError):
            owscout_comps = {}

    data = {
        "divisions": divisions,
        "views": views,
        "heroes": list(heroes.values()),
        "roster": roster,
        "maps": list(maps.values()),
        "owscout_comps": owscout_comps,
        "owscout_captured": owscout_captured,
        "code_wipe": owscout_wipe,
        # When this page was generated - so anyone can tell at a glance whether
        # their contribution has landed yet.
        "built_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        # Inlined hero portraits so comps read as icons, not five words. Empty
        # when the art isn't present; the page then falls back to text chips.
        "hero_icons": load_hero_icons(),
    }
    title = "FACEIT OW2 — League Scouting"
    payload = json.dumps(data).replace("</", "<\\/")
    out.write(HTML_TEMPLATE.replace("__TITLE__", html.escape(title)).replace("__DATA__", payload))
    return len(divisions)

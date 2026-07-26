"""Emit docs/capture/data.json — the codes + rosters feed the browser capture
app consumes instead of crawling FACEIT. CI-run (reads faceit.sqlite3); the app
fetches it same-origin. Scoped to EMEA, all tiers, post-wipe coded games.

    faceit-sync ... export ...          # (CI already builds the DB)
    .venv/Scripts/python tools/build_capture_data.py

data.json:
  { built_at, code_wipe_date, divisions:[...],
    codes: [{code,match_id,game_no,map,division,team_a,team_b,t1,t2,finished_at}],
    rosters: { <match_id>: { <team_id>: {name, players:[{nick,game_name}]} } } }
Whether a code is already scouted is read from the sibling docs/captured.json,
so it is not duplicated here.
"""
from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime, timezone

FACEIT_DB = os.environ.get("FACEIT_DB", "faceit.sqlite3")
OUT = os.path.join("docs", "capture", "data.json")
REGION = "EMEA"
CODE_WIPE_DATE = "2026-07-14"          # league-wide replay-code wipe (SPEC §2)
TIERS = ("Master", "Expert", "Advanced", "Open")


def _tier(name: str) -> str | None:
    return next((t for t in TIERS if t in (name or "")), None)


def main() -> None:
    con = sqlite3.connect(FACEIT_DB)
    con.row_factory = sqlite3.Row
    codes: list[dict[str, object]] = []
    rosters: dict[str, dict[str, dict[str, object]]] = {}
    seen_divs: set[str] = set()

    rows = con.execute(
        """
        SELECT g.demo_code code, g.match_id, g.game_no,
               mp.name map, m.finished_at, ch.name champ,
               m.faction1_team_id t1, m.faction2_team_id t2,
               t1.name team_a, t2.name team_b
        FROM games g
        JOIN matches m ON m.id = g.match_id
        JOIN championships ch ON ch.id = m.championship_id
        LEFT JOIN maps  mp ON mp.guid = g.map_guid
        LEFT JOIN teams t1 ON t1.id = m.faction1_team_id
        LEFT JOIN teams t2 ON t2.id = m.faction2_team_id
        WHERE g.demo_code IS NOT NULL AND g.demo_code <> ''
          AND (' ' || ch.name || ' ') LIKE ?
          AND substr(m.finished_at, 1, 10) > ?
        ORDER BY m.finished_at DESC, g.game_no
        """,
        (f"% {REGION} %", CODE_WIPE_DATE),
    ).fetchall()

    match_ids: set[str] = set()
    for r in rows:
        tier = _tier(r["champ"])
        if not tier:
            continue
        seen_divs.add(tier)
        codes.append({
            "code": r["code"], "match_id": r["match_id"], "game_no": r["game_no"],
            "map": r["map"], "division": tier,
            "team_a": r["team_a"], "team_b": r["team_b"],
            "t1": r["t1"], "t2": r["t2"], "finished_at": r["finished_at"],
        })
        match_ids.add(r["match_id"])

    # One roster set per match (the players who appeared, per team). game_name is
    # the Battle.net HUD name — kept for the future OCR/attribution phase.
    for mid in match_ids:
        by_team: dict[str, dict[str, object]] = {}
        for rp in con.execute(
            """SELECT rp.team_id, te.name tname,
                      COALESCE(p.nickname, rp.player_id) nick, p.game_name gname
               FROM round_players rp
               LEFT JOIN players p ON p.id = rp.player_id
               LEFT JOIN teams te ON te.id = rp.team_id
               WHERE rp.match_id = ? AND rp.team_id IS NOT NULL
               GROUP BY rp.team_id, rp.player_id""",
            (mid,),
        ):
            slot = by_team.setdefault(rp["team_id"], {"name": rp["tname"], "players": []})
            slot["players"].append({"nick": rp["nick"], "game_name": rp["gname"]})
        rosters[mid] = by_team
    con.close()

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    payload = {
        "built_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "code_wipe_date": CODE_WIPE_DATE,
        "region": REGION,
        "divisions": [t for t in TIERS if t in seen_divs],
        "codes": codes,
        "rosters": rosters,
    }
    with open(OUT, "w", encoding="utf-8") as fh:
        json.dump(payload, fh)
    print(f"wrote {OUT}  ({len(codes)} codes across {sorted(seen_divs)}, "
          f"{len(rosters)} matches, {os.path.getsize(OUT)//1024} KB)")


if __name__ == "__main__":
    main()

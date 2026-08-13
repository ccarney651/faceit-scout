"""Emit docs/scrims-demo.json — the sample scrim block the viewer shows in demo
mode, so someone landing on an empty Scrims page can see what a filled-in one
looks like.

Built from REAL FACEIT teams, real lineups and real hero GUIDs, because a demo
full of "Team A / Player 1" teaches nothing about whether the tool is worth
using. The scrims themselves are invented: nobody played these maps, and the
viewer labels the whole page as sample data for exactly that reason.

    .venv/Scripts/python.exe tools/build_scrim_demo.py

Regenerate when the roster data changes materially. The output is committed —
unlike a real scrim database, which is private and never leaves the browser.
"""
from __future__ import annotations

import collections
import json
import pathlib
import random
import sqlite3

ROOT = pathlib.Path(__file__).resolve().parents[1]
DB = ROOT / "faceit.sqlite3"
REFS = ROOT / "docs" / "capture" / "refs.json"
OUT = ROOT / "docs" / "scrims-demo.json"

# A believable practice block: one of each mode, one mode deliberately stale so
# the coverage strip has something to say, and a voided restart.
SESSIONS = [
    # (days ago, opponent kind, maps: [(map, mode, us, them, result)])
    (1, "league", [
        ("Ilios", "Control", 2, 1, "win"),
        ("King's Row", "Hybrid", 3, 2, "win"),
        ("Colosseo", "Push", 1, 2, "loss"),
    ]),
    (3, "league", [
        ("Dorado", "Escort", 2, 3, "loss"),
        ("Dorado", "Escort", 0, 0, None),      # restarted - voided
        ("Suravasa", "Flashpoint", 3, 1, "win"),
        ("Busan", "Control", 2, 0, "win"),
    ]),
    (8, "group", [
        ("Antarctic Peninsula", "Control", 1, 2, "loss"),
        ("Circuit Royal", "Escort", 3, 3, "draw"),
    ]),
    (26, "unknown", [
        ("Runasapi", "Push", 2, 1, "win"),
    ]),
]

# Comps that actually get run, by mode, so the hero pools look like a real
# team's rather than a random draw. 1-2-2 throughout.
COMPS = [
    ["Winston", "Tracer", "Sojourn", "Kiriko", "Lucio"],        # dive
    ["Ramattra", "Cassidy", "Ashe", "Ana", "Baptiste"],         # poke
    ["Reinhardt", "Mei", "Reaper", "Lucio", "Ana"],             # rush
    ["Sigma", "Ashe", "Sojourn", "Ana", "Illari"],              # poke 2
    ["DVa", "Genji", "Tracer", "Kiriko", "Juno"],              # dive 2
    ["Orisa", "Junkrat", "Bastion", "Baptiste", "Brigitte"],    # bunker
]


def hero_guids() -> dict[str, str]:
    refs = json.loads(REFS.read_text(encoding="utf-8"))["refs"]
    out: dict[str, str] = {}
    for r in refs:
        if r.get("n") and r.get("g") and r["n"] not in out:
            out[r["n"]] = r["g"]
    return out


def real_lineups(limit: int) -> list[dict[str, object]]:
    """Teams that genuinely fielded a five together, with those five."""
    con = sqlite3.connect(DB)
    seen: dict[tuple[str, str, str], set[str]] = collections.defaultdict(set)
    for mid, gno, tid, tname, gname, nick in con.execute(
        """SELECT rp.match_id, rp.game_no, rp.team_id, t.name, p.game_name, p.nickname
           FROM round_players rp
           JOIN players p ON p.id = rp.player_id
           JOIN teams t ON t.id = rp.team_id
           WHERE rp.team_id IS NOT NULL"""
    ):
        n = (gname or nick or "").strip()
        if n:
            seen[(mid, gno, tid, tname)].add(n)
    con.close()

    picked: dict[str, dict[str, object]] = {}
    for (_mid, _gno, tid, tname), names in seen.items():
        # ASCII-only names keep the demo legible in every font the page may
        # fall back to; the point is realism, not an encoding stress test.
        if len(names) == 5 and tid not in picked and all(n.isascii() for n in names):
            picked[tid] = {"team_id": tid, "name": tname, "players": sorted(names)}
        if len(picked) >= limit:
            break
    return list(picked.values())


def main() -> None:
    rnd = random.Random(20260814)          # stable output across rebuilds
    guids = hero_guids()
    missing = [h for c in COMPS for h in c if h not in guids]
    assert not missing, f"no GUID for {sorted(set(missing))} — refs.json changed?"

    teams = real_lineups(6)
    assert len(teams) >= 4, f"only {len(teams)} usable lineups found"
    us, opp_a, opp_b = teams[0], teams[1], teams[2]

    scrims: list[dict[str, object]] = []
    maps: list[dict[str, object]] = []
    opponents = [{
        "id": "demo-opp-mix", "kind": "local_group", "team_id": None,
        "label": "Korean scrim partner",
        "roster_names": ["haru", "jinwoo", "minseo", "taeyang", "yuna"],
        "first_seen": "2026-07-01T19:00:00Z", "times_played": 4,
    }]

    for i, (days_ago, kind, rows) in enumerate(SESSIONS):
        sid = f"demo-s{i+1}"
        s: dict[str, object] = {
            "id": sid, "team_us": us["name"],
            "date": f"@@MINUS{days_ago}@@",        # resolved to a real date in the browser
            "created_at": f"@@MINUS{days_ago}@@T19:00:00Z",
            "notes": "",
        }
        if kind == "league":
            other = opp_a if i == 0 else opp_b
            s["opponent"] = other["name"]
            s["opponent_team_id"] = other["team_id"]
        elif kind == "group":
            s["opponent_id"] = "demo-opp-mix"
        # kind == "unknown": no opponent at all, which is a normal outcome
        scrims.append(s)

        for j, (mp, mode, a, b, result) in enumerate(rows):
            voided = result is None
            obs = []
            if not voided:
                # Two comps per side per map, so swaps and pools have something
                # to show without pretending to a full round-by-round capture.
                for side in ("a", "b"):
                    for comp in rnd.sample(COMPS, 2):
                        obs.append({"side": side, "round": 1,
                                    "heroes": [guids[h] for h in comp]})
            maps.append({
                "id": f"{sid}:{j+1}", "scrim_id": sid, "map_no": j + 1,
                "map_name": mp, "map_category": mode, "code": None,
                "score": {"us": a, "them": b}, "result": result,
                "void": voided, "observations": obs, "scrim": True,
            })

    OUT.write_text(json.dumps({
        "demo": True,
        # The banner supplies its own "Sample data." lead-in; do not repeat it here.
        "note": "These scrims never happened — the teams and players are real "
                "FACEIT League entrants, the results are invented.",
        "scrims": scrims, "scrim_maps": maps, "opponents": opponents,
    }, indent=1), encoding="utf-8")
    print(f"wrote {OUT}  ({len(scrims)} scrims, {len(maps)} maps, "
          f"teams: {us['name']} vs {opp_a['name']}/{opp_b['name']})")


if __name__ == "__main__":
    main()

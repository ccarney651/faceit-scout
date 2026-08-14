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

# Comps that actually get run, so the hero pools look like a real team's rather
# than a random draw. 1-2-2 throughout.
#
# Each side gets a SMALL set with one staple, because that is what makes the
# analysis readable: a hero pool counted in rounds only says something when some
# heroes are played nearly every round and others are not.
DIVE = ["Winston", "Tracer", "Sojourn", "Kiriko", "Lucio"]
POKE = ["Ramattra", "Cassidy", "Ashe", "Ana", "Baptiste"]
RUSH = ["Reinhardt", "Mei", "Reaper", "Lucio", "Ana"]
POKE2 = ["Sigma", "Ashe", "Sojourn", "Ana", "Illari"]
DIVE2 = ["DVa", "Genji", "Tracer", "Kiriko", "Juno"]
BUNKER = ["Orisa", "Junkrat", "Bastion", "Baptiste", "Brigitte"]

# (comp, weight) — the first is the staple, so it shows up as one.
PLAYBOOK = {
    "a": [(DIVE, 5), (POKE2, 2), (RUSH, 1)],
    "b": [(POKE, 4), (BUNKER, 2), (DIVE2, 2)],
}

# A habitual mid-map answer: when the enemy fields the trigger, this side swaps.
# Recurring with a consistent trigger is exactly what the swap analysis reports,
# so the demo has to contain some or the panel reads empty.
SWAPS = {
    "a": [("Winston", "Sigma", "Bastion"), ("Tracer", "Cassidy", "Brigitte")],
    "b": [("Orisa", "DVa", "Tracer"), ("Ashe", "Sombra", "Winston")],
}

# Some teams scrim with hero bans and some do not, so the sample shows both:
# the two most recent blocks use them, the older ones do not. Each side has
# heroes it habitually bans, which is what makes "preferred bans" and "how they
# open under a ban" say anything at all.
BANS = {"a": ["Ashe", "Ramattra"], "b": ["Winston", "Sojourn"]}

# What a side falls back to when its staple hero is banned out. Without this the
# ban-response panel would show the same opener under every ban and prove
# nothing about whether the analysis works.
BAN_FALLBACK = {
    "Winston": "Sigma", "Sojourn": "Cassidy", "Tracer": "Genji",
    "Ashe": "Sombra", "Ramattra": "Orisa", "Kiriko": "Baptiste",
}

CONTROL_SUBMAPS = {
    "Ilios": ["Lighthouse", "Ruins", "Well"],
    "Busan": ["Downtown", "Sanctuary", "MEKA Base"],
    "Antarctic Peninsula": ["Icebreaker", "Labs", "Sublevel"],
}


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


def rounds_for(map_name: str, mode: str, rnd: random.Random) -> list[dict[str, object]]:
    """The segments of one map, as the capture page records them.

    Control is played to sub-maps, Escort and Hybrid alternate attack and defend,
    and Push and Flashpoint are mirrored so neither side attacks. Getting this
    right in the demo matters: every per-segment breakdown on the page reads
    these fields, and a fixture that puts everything in "round 1" would make the
    analysis look broken rather than empty.
    """
    if mode == "Control":
        subs = CONTROL_SUBMAPS.get(map_name, ["Point A", "Point B", "Point C"])
        n = rnd.choice([2, 3])
        return [{"round_no": i + 1, "sub_map": subs[i], "phase_a": None}
                for i in range(n)]
    if mode in ("Escort", "Hybrid"):
        # Two halves: we attack first, then defend. Round 3+ would be time-bank
        # overtime, which is rarer and not worth complicating the sample with.
        return [{"round_no": 1, "sub_map": None, "phase_a": "attack"},
                {"round_no": 2, "sub_map": None, "phase_a": "defend"}]
    return [{"round_no": 1, "sub_map": None, "phase_a": None}]


def pick_comp(side: str, rnd: random.Random,
              banned: frozenset[str] = frozenset()) -> list[str]:
    pool = [c for c, w in PLAYBOOK[side] for _ in range(w)]
    comp = list(rnd.choice(pool))
    # A banned hero cannot be fielded. Substituting rather than re-rolling keeps
    # the rest of the comp intact, which is how a team actually responds.
    for i, h in enumerate(comp):
        if h in banned:
            alt = BAN_FALLBACK.get(h)
            comp[i] = alt if alt and alt not in comp else h
    return comp


def bans_for(scrim_index: int, rnd: random.Random) -> list[dict[str, object]]:
    """The bans on one map, as the capture page records them.

    `by` is who MADE the ban; the capture page allows leaving it unset, so one
    is left unattributed to prove the analysis handles it.
    """
    rows = []
    for side in ("a", "b"):
        hero = rnd.choice(BANS[side])
        rows.append({"hero": hero, "by": "us" if side == "a" else "them"})
    if rnd.random() < 0.3:
        rows[-1]["by"] = None
    return rows


def apply_swap(side: str, comp: list[str], enemy: list[str], rnd: random.Random,
               banned: frozenset[str] = frozenset()) -> list[str] | None:
    """This side's habitual answer to what the enemy is fielding, if it applies."""
    for out_h, in_h, trigger in SWAPS[side]:
        if in_h in banned:
            continue
        if trigger in enemy and out_h in comp and in_h not in comp:
            if rnd.random() < 0.8:      # habitual, not mechanical
                return [in_h if h == out_h else h for h in comp]
    return None


def main() -> None:
    rnd = random.Random(20260814)          # stable output across rebuilds
    guids = hero_guids()
    all_heroes = {h for c in PLAYBOOK.values() for comp, _ in c for h in comp}
    all_heroes |= {h for rows in SWAPS.values() for r in rows for h in r}
    missing = [h for h in all_heroes if h not in guids]
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
        # The two most recent blocks scrim with bans, the older ones without -
        # both are normal, and the viewer has to read correctly either way.
        uses_bans = i < 2
        s["uses_bans"] = uses_bans
        scrims.append(s)

        for j, (mp, mode, a, b, result) in enumerate(rows):
            voided = result is None
            bans = bans_for(i, rnd) if uses_bans and not voided else []
            banned = frozenset(b["hero"] for b in bans)
            obs = []
            if not voided:
                ts = 0
                for seg in rounds_for(mp, mode, rnd):
                    ts += 1000
                    # A snapshot captures BOTH teams in the same frame, so every
                    # frame emits both sides. Emitting one side's whole sequence
                    # first would leave a swap with no enemy lineup recorded at
                    # or before it, and the trigger analysis would find nothing.
                    now = {s: pick_comp(s, rnd, banned) for s in ("a", "b")}
                    frames = [dict(now)]
                    after = {s: apply_swap(s, now[s], now["b" if s == "a" else "a"], rnd, banned)
                             for s in ("a", "b")}
                    if any(after.values()):
                        frames.append({s: after[s] or now[s] for s in ("a", "b")})
                    for k, frame in enumerate(frames):
                        for side in ("a", "b"):
                            phase = None
                            if seg["phase_a"]:
                                phase = seg["phase_a"] if side == "a" else (
                                    "defend" if seg["phase_a"] == "attack" else "attack")
                            obs.append({
                                "side": side, "ts": ts + k * 400,
                                "round_no": seg["round_no"],
                                "sub_map": seg["sub_map"], "phase": phase,
                                "heroes": [guids[h] for h in frame[side]],
                            })
            maps.append({
                "id": f"{sid}:{j+1}", "scrim_id": sid, "map_no": j + 1,
                "map_name": mp, "map_category": mode, "code": None,
                "score": {"us": a, "them": b}, "result": result,
                "void": voided, "observations": obs, "scrim": True,
                "bans": [{"g": guids[b["hero"]], "n": b["hero"], "by": b["by"]}
                         for b in bans],
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

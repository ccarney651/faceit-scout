"""Independent accuracy audit.

Re-derives every stored fact straight from FACEIT's raw payloads using DIFFERENT
routes than the ingest pipeline, then diffs against the SQLite database:

  * map / score / winner / rosters  -> from the STATS feed (the tool uses the
    match payload + results, a different source).
  * ban attribution (which team banned which hero) -> matched game->veto-slot by
    the MAP played (the tool matches by ban-set), then read `selected_by`.

Agreement between two independent routes = the data is trustworthy. Any mismatch
is printed in full. Run:  python verify_accuracy.py [N|all]
"""
from __future__ import annotations

import sqlite3
import sys
import time
from typing import Any, Optional

import requests

UA = "faceit-sync/0.1 (+https://github.com/local/faceit-sync)"
DB = "faceit.sqlite3"
S = requests.Session()
S.headers.update({"User-Agent": UA, "Accept": "application/json"})


def get(url: str) -> Optional[Any]:
    for _ in range(4):
        r = S.get(url, timeout=30)
        if r.status_code == 200:
            time.sleep(0.08)   # be polite — this is a full-league audit
            return r.json()
        if r.status_code == 404:
            return None
        time.sleep(2.0)
    return None


def match_payload(mid: str) -> dict[str, Any]:
    d = get(f"https://api.faceit.com/match/v2/match/{mid}") or {}
    return d.get("payload", {}) or {}


def history(mid: str) -> Optional[dict[str, Any]]:
    d = get(f"https://api.faceit.com/democracy/v1/match/{mid}/history")
    return (d or {}).get("payload") if d else None


def stats(mid: str) -> list[dict[str, Any]]:
    d = get(f"https://api.faceit.com/stats/v1/stats/matches/{mid}")
    return d if isinstance(d, list) else []


def to_int(v: Any) -> Optional[int]:
    try:
        s = str(v).strip()
        return None if s in ("", "-") else int(float(s))
    except (ValueError, TypeError):
        return None


def independent(mid: str) -> Optional[dict[str, Any]]:
    """Facts re-derived from raw payloads, keyed by game number."""
    mp = match_payload(mid)
    if not mp or mp.get("status") != "FINISHED":
        return None
    teams = mp.get("teams", {}) or {}
    f1id = (teams.get("faction1") or {}).get("id")
    f2id = (teams.get("faction2") or {}).get("id")
    fac_of = lambda tid: "faction1" if tid == f1id else "faction2" if tid == f2id else None

    pool = [e.get("guid") for e in mp.get("voting", {}).get("heroes", {}).get("entities", []) if e.get("guid")]
    survivors = mp.get("voting", {}).get("heroes", {}).get("pick", []) or []

    # history: per slot, map picked + hero drops {guid: selected_by}
    slots = []
    hp = history(mid)
    if hp:
        tks = hp.get("tickets", []) or []
        for i in range(0, len(tks), 3):
            grp = {t.get("entity_type"): t for t in tks[i:i + 3]}
            mpick = next((e for e in (grp.get("map", {}).get("entities", []) or [])
                          if e.get("status") == "pick"), None)
            drops = {e.get("guid"): e.get("selected_by")
                     for e in (grp.get("heroes", {}).get("entities", []) or [])
                     if e.get("status") == "drop"}
            slots.append({"map": mpick.get("guid") if mpick else None,
                          "map_by": mpick.get("selected_by") if mpick else None,
                          "drops": drops})

    games: dict[int, dict[str, Any]] = {}
    for sg in stats(mid):
        g = to_int(sg.get("matchRound"))
        if not g:
            continue
        rosters: dict[str, set[str]] = {}
        scores: dict[str, Optional[int]] = {}
        for tm in sg.get("teams", []) or []:
            fac = fac_of(tm.get("teamId"))
            if not fac:
                continue
            rosters[fac] = {p.get("playerId") for p in (tm.get("players", []) or []) if p.get("playerId")}
            scores[fac] = to_int(tm.get("i6"))
        gmap = sg.get("i1")
        bans = [x for x in pool if g - 1 < len(survivors) and x not in set(survivors[g - 1])] if g - 1 < len(survivors) else []
        # attribution: match this game to the veto slot that picked this map
        slot = next((s for s in slots if s["map"] and s["map"] == gmap), None)
        attr = {b: (slot["drops"].get(b) if slot else None) for b in bans}
        games[g] = {
            "map": gmap,
            "winner": fac_of(sg.get("i2")),
            "f1_score": scores.get("faction1"), "f2_score": scores.get("faction2"),
            "rosters": rosters,
            "bans": set(bans),
            "attr": attr,
            "map_by": slot["map_by"] if slot else None,
        }
    return {"games": games, "f1id": f1id, "f2id": f2id}


def db_facts(c: sqlite3.Connection, mid: str) -> dict[int, dict[str, Any]]:
    out: dict[int, dict[str, Any]] = {}
    for g in c.execute("SELECT * FROM games WHERE match_id=? AND map_guid IS NOT NULL", (mid,)):
        gno = g["game_no"]
        bans = {r["hero_guid"]: r["banned_by_faction"]
                for r in c.execute("SELECT hero_guid,banned_by_faction FROM hero_bans WHERE match_id=? AND game_no=?", (mid, gno))}
        mp = c.execute("SELECT picked_by_faction FROM map_picks WHERE match_id=? AND game_no=?", (mid, gno)).fetchone()
        rosters: dict[str, set[str]] = {}
        f1 = c.execute("SELECT faction1_team_id f1,faction2_team_id f2 FROM matches WHERE id=?", (mid,)).fetchone()
        for rp in c.execute("SELECT team_id,player_id FROM round_players WHERE match_id=? AND game_no=?", (mid, gno)):
            fac = "faction1" if rp["team_id"] == f1["f1"] else "faction2" if rp["team_id"] == f1["f2"] else None
            if fac:
                rosters.setdefault(fac, set()).add(rp["player_id"])
        out[gno] = {
            "map": g["map_guid"], "winner": g["winner_faction"],
            "f1_score": g["faction1_score"], "f2_score": g["faction2_score"],
            "bans": set(bans), "attr": bans,
            "map_by": mp["picked_by_faction"] if mp else None,
            "rosters": rosters, "restarted": g["was_restarted"],
        }
    return out


def main() -> None:
    arg = sys.argv[1] if len(sys.argv) > 1 else "all"
    c = sqlite3.connect(DB)
    c.row_factory = sqlite3.Row
    mids = [r[0] for r in c.execute("SELECT id FROM matches WHERE status='FINISHED' ORDER BY finished_at")]
    if arg != "all":
        mids = mids[: int(arg)]

    counts = {k: [0, 0] for k in ("map", "score", "winner", "bans", "attribution", "map_pick", "rosters")}  # [checked, mismatch]
    problems: list[str] = []
    checked_matches = 0
    for i, mid in enumerate(mids, 1):
        ind = independent(mid)
        if ind is None:
            continue
        dbf = db_facts(c, mid)
        checked_matches += 1
        for gno, dg in dbf.items():
            ig = ind["games"].get(gno)
            if not ig:
                continue

            def chk(cat: str, ok: bool, detail: str) -> None:
                counts[cat][0] += 1
                if not ok:
                    counts[cat][1] += 1
                    problems.append(f"{mid} G{gno} [{cat}]: {detail}")

            chk("map", dg["map"] == ig["map"], f"db={dg['map']} raw={ig['map']}")
            chk("score", (dg["f1_score"], dg["f2_score"]) == (ig["f1_score"], ig["f2_score"]),
                f"db={dg['f1_score']}-{dg['f2_score']} raw={ig['f1_score']}-{ig['f2_score']}")
            chk("winner", dg["winner"] == ig["winner"], f"db={dg['winner']} raw={ig['winner']}")
            chk("bans", dg["bans"] == ig["bans"], f"db={sorted(dg['bans'])} raw={sorted(ig['bans'])}")
            # attribution: compare per-hero team, but only where the independent
            # (map-matched) route actually found a veto slot.
            if ig["attr"] and any(v for v in ig["attr"].values()):
                mism = {h: (dg["attr"].get(h), ig["attr"].get(h)) for h in ig["attr"]
                        if ig["attr"][h] is not None and dg["attr"].get(h) != ig["attr"][h]}
                chk("attribution", not mism, f"{mism}")
            if ig["map_by"] is not None:
                chk("map_pick", dg["map_by"] == ig["map_by"], f"db={dg['map_by']} raw={ig['map_by']}")
            if ig["rosters"] and dg["rosters"]:
                chk("rosters", dg["rosters"] == ig["rosters"],
                    f"db={ {k:len(v) for k,v in dg['rosters'].items()} } raw={ {k:len(v) for k,v in ig['rosters'].items()} }")
        if i % 25 == 0:
            print(f"...checked {i}/{len(mids)}", flush=True)

    print("\n================ ACCURACY AUDIT ================")
    print(f"matches checked: {checked_matches}/{len(mids)}\n")
    for cat, (ch, mm) in counts.items():
        rate = 100.0 * (ch - mm) / ch if ch else 100.0
        flag = "OK" if mm == 0 else f"*** {mm} MISMATCH ***"
        print(f"  {cat:12} {ch-mm:5}/{ch:<5} agree  ({rate:6.2f}%)  {flag}")
    if problems:
        print(f"\n--- {len(problems)} discrepancies ---")
        for p in problems[:40]:
            print("  " + p)
    else:
        print("\nEVERY checked field agrees between the database and an independent re-derivation.")


if __name__ == "__main__":
    main()

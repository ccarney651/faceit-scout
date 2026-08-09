"""Audit committed captures for mis-attributed sides/teams.

**Why `winner_side` cannot be used for this.** It is DERIVED
(`owdb.db._winner_side`) from FACEIT's winning faction plus whichever faction
the operator said was side A. Checking it against FACEIT is therefore circular:
it agrees by construction no matter which way the sides were set.

The independent signal is **player attribution**. Auto-detect OCRs the HUD name
bars and tags each slot with a FACEIT player id (`observations[].pairs` =
[hero_guid, player_id]). Those ids come from reading the screen, not from the
side assignment -- so if the players tagged on side A actually play for the team
recorded as side B, the sides are swapped. That is the one failure mode
merge-time validation cannot catch: a swap names two teams that BOTH really
played the match, so every name still validates.

Verdicts per map:
  SWAPPED   sides are backwards -- the majority of tagged players on each side
            belong to the other side's team. Fix with data/captures/overrides.json
            or by re-scouting.
  OK        tagged players match the recorded sides.
  UNTAGGED  no player tags (pre-auto-detect capture) -- cannot be checked here.
  UNKNOWN   FACEIT has no roster for that game, so there is nothing to check
            against.

    .venv/Scripts/python tools/audit_capture_sides.py
    .venv/Scripts/python tools/audit_capture_sides.py --verbose
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import sqlite3
from collections import Counter
from typing import Any

FACEIT_DB = os.environ.get("FACEIT_DB", "faceit.sqlite3")
CAPTURE_DIR = os.environ.get("CAPTURE_DIR", os.path.join("data", "captures"))

# A side must be this fraction of confidently-attributed tags to call it, so one
# stray OCR hit never flips a verdict on its own.
MIN_TAGS = 3
MAJORITY = 0.6


def _rosters(con: sqlite3.Connection) -> dict[tuple[str, int], dict[str, str]]:
    """(match_id, game_no) -> {player_id: team_id} straight from FACEIT."""
    out: dict[tuple[str, int], dict[str, str]] = {}
    for r in con.execute(
        "SELECT match_id, game_no, player_id, team_id FROM round_players "
        "WHERE team_id IS NOT NULL"
    ):
        out.setdefault((str(r[0]), int(r[1])), {})[str(r[2])] = str(r[3])
    return out


def _audit_map(m: dict[str, Any], roster: dict[str, str]) -> dict[str, Any]:
    """Compare each side's tagged players against the team recorded for it.

    A side with NO tags is evidence of nothing -- an auto-detect that only ran
    on one side (common: it fires per-side, and OCR can fail on just one HUD
    half) must not be scored the same as a side whose tags actively point at
    the wrong team. Only an actual pointer at the other declared team counts as
    swap evidence; silence does not.
    """
    said = {"a": m.get("side_a_team_id"), "b": m.get("side_b_team_id")}
    # How often each side's tags land on each team, counted per observation slot.
    hits: dict[str, Counter[str]] = {"a": Counter(), "b": Counter()}
    for o in m.get("observations", []):
        side = o.get("side")
        if side not in hits:
            continue
        for pair in o.get("pairs") or []:
            if not isinstance(pair, (list, tuple)) or len(pair) != 2:
                continue
            team = roster.get(str(pair[1]))
            if team:
                hits[side][team] += 1

    tagged = sum(sum(c.values()) for c in hits.values())
    if not tagged:
        return {"verdict": "UNTAGGED", "tags": 0, "detail": ""}

    # Per side: which team its tags point at, and how cleanly -- or None if
    # there isn't enough (or clean enough) evidence to call it either way.
    resolved: dict[str, str | None] = {}
    shares: dict[str, float] = {}
    for side, c in hits.items():
        total = sum(c.values())
        if total < MIN_TAGS:
            resolved[side], shares[side] = None, 0.0
            continue
        team, n = c.most_common(1)[0]
        shares[side] = n / total
        resolved[side] = team if n / total >= MAJORITY else None

    # Classify each RESOLVED side against what was declared -- a side with no
    # resolution contributes no outcome at all, positive or negative.
    outcomes: dict[str, str | None] = {}
    for side, other in (("a", "b"), ("b", "a")):
        team = resolved[side]
        if team is None:
            outcomes[side] = None
        elif team == said[side]:
            outcomes[side] = "match"
        elif team == said[other]:
            outcomes[side] = "swap"
        else:
            outcomes[side] = "other"     # points at neither declared team

    seen = {v for v in outcomes.values() if v is not None}
    detail = f"a->{shares['a']:.0%} b->{shares['b']:.0%} ({tagged} tags)"

    if not seen:
        return {"verdict": "UNTAGGED", "tags": tagged,
                "detail": "tags too sparse/mixed to judge · " + detail}
    if seen == {"match"}:
        return {"verdict": "OK", "tags": tagged, "detail": detail}
    if seen == {"swap"}:
        return {"verdict": "SWAPPED", "tags": tagged, "detail": detail}
    return {"verdict": "SUSPECT", "tags": tagged,
            "detail": "conflicting evidence across sides · " + detail}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--verbose", action="store_true",
                    help="list every map, not just the problems")
    args = ap.parse_args()

    con = sqlite3.connect(FACEIT_DB)
    rosters = _rosters(con)
    teams = {str(r[0]): str(r[1]) for r in con.execute("SELECT id, name FROM teams")}
    con.close()

    tally: Counter[str] = Counter()
    problems: list[str] = []
    lines: list[str] = []

    for path in sorted(glob.glob(os.path.join(CAPTURE_DIR, "*.json"))):
        with open(path, encoding="utf-8") as fh:
            doc = json.load(fh)
        who = doc.get("contributor") or os.path.basename(path)
        for m in doc.get("maps", []):
            key = (str(m.get("match_id")), int(m.get("game_no") or 0))
            roster = rosters.get(key)
            if not roster:
                tally["UNKNOWN"] += 1
                continue
            res = _audit_map(m, roster)
            tally[res["verdict"]] += 1
            label = (f"{res['verdict']:<8} {who:<22} {m.get('map_name','?'):<12} "
                     f"{m.get('demo_code','?'):<8} "
                     f"{teams.get(str(m.get('side_a_team_id')), m.get('side_a_team','?'))}"
                     f" | {teams.get(str(m.get('side_b_team_id')), m.get('side_b_team','?'))}"
                     f"   {res['detail']}")
            lines.append(label)
            if res["verdict"] in ("SWAPPED", "SUSPECT"):
                problems.append(label)

    total = sum(tally.values())
    print(f"audited {total} captured maps from {CAPTURE_DIR}\n")
    for v in ("OK", "SWAPPED", "SUSPECT", "UNTAGGED", "UNKNOWN"):
        if tally[v]:
            print(f"  {v:<9} {tally[v]}")
    checked = tally["OK"] + tally["SWAPPED"] + tally["SUSPECT"]
    if checked:
        print(f"\n  {tally['OK']}/{checked} checkable maps have correct sides "
              f"({tally['OK'] / checked:.0%})")

    if args.verbose:
        print("\n--- every map ---")
        for ln in sorted(lines):
            print("  " + ln)
    elif problems:
        print("\n--- problems ---")
        for ln in problems:
            print("  " + ln)
    if not problems:
        print("\nNo mis-attributed sides found.")
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())

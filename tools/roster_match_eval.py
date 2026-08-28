"""How safe is the 3-of-5 opponent-identification bar against real rosters?

Evidence for specs/2026-08-12-scrim-mode-design.md §4.2. Takes every real
5-player lineup that actually played a game and asks how many OTHER teams that
lineup would also match at each threshold. A lineup matching two teams at the
bar is ambiguous; one matching the wrong team alone is a misidentification.

Scoped to the ACTIVE season, exactly as tools/build_capture_data.py scopes the
`team_rosters` it ships — both the pool and the lineups tested against it. A
number measured over a pool the app does not use would describe nothing.

Re-run it when the season turns over or the roster data grows — the bar is only
as good as the collision rate it was chosen against. It is worth re-running the
first week of a new season in particular: the pool is then the teams that have
already played, not the whole league.

    .venv/Scripts/python.exe tools/roster_match_eval.py
"""
import collections
import pathlib
import sqlite3
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from faceit_sync.models import newest_season, season_of  # noqa: E402

con = sqlite3.connect(pathlib.Path(__file__).resolve().parents[1] / "faceit.sqlite3")

SEASON = newest_season(
    r[0] for r in con.execute("select name from championships"))
print(f"active season: {SEASON}")

# Accumulated roster per team, within the active season.
roster = collections.defaultdict(set)
for tid, gn, nick, champ in con.execute("""
        select rp.team_id, p.game_name, p.nickname, ch.name
        from round_players rp
        join players p on p.id = rp.player_id
        join matches m on m.id = rp.match_id
        join championships ch on ch.id = m.championship_id
        where rp.team_id is not null"""):
    if season_of(champ) != SEASON:
        continue
    n = (gn or nick or "").strip().lower()
    if n:
        roster[tid].add(n)

# Real lineups: the five players who actually played one game together.
lineups = collections.defaultdict(set)
for mid, gno, tid, gn, nick, champ in con.execute("""
        select rp.match_id, rp.game_no, rp.team_id, p.game_name, p.nickname,
               ch.name
        from round_players rp
        join players p on p.id = rp.player_id
        join matches m on m.id = rp.match_id
        join championships ch on ch.id = m.championship_id
        where rp.team_id is not null"""):
    if season_of(champ) != SEASON:
        continue
    n = (gn or nick or "").strip().lower()
    if n:
        lineups[(mid, gno, tid)].add(n)

lineups = {k: v for k, v in lineups.items() if len(v) == 5}
print(f"real 5-player lineups: {len(lineups)}   teams: {len(roster)}")

for bar in (3, 4, 5):
    ambiguous = wrong = correct = missed = 0
    for (mid, gno, tid), five in lineups.items():
        hits = [t for t, r in roster.items() if len(five & r) >= bar]
        if not hits:
            missed += 1
        elif hits == [tid]:
            correct += 1
        elif tid in hits:
            ambiguous += 1
        else:
            wrong += 1
    tot = len(lineups)
    print(f"\nbar = {bar} of 5")
    print(f"  identified uniquely and correctly : {correct:5d}  ({100*correct/tot:5.1f}%)")
    print(f"  ambiguous (right team + others)   : {ambiguous:5d}  ({100*ambiguous/tot:5.1f}%)")
    print(f"  WRONG team only                   : {wrong:5d}  ({100*wrong/tot:5.1f}%)")
    print(f"  no match at all                   : {missed:5d}  ({100*missed/tot:5.1f}%)")

# With the design's tie-break: most hits wins, ties are inconclusive.
print("\n--- with 'highest overlap wins' tie-break, bar = 3 ---")
resolved = tied = wrong = 0
for (mid, gno, tid), five in lineups.items():
    scored = sorted(((len(five & r), t) for t, r in roster.items() if len(five & r) >= 3),
                    reverse=True)
    if not scored:
        continue
    top = scored[0][0]
    winners = [t for s, t in scored if s == top]
    if len(winners) > 1:
        tied += 1
    elif winners[0] == tid:
        resolved += 1
    else:
        wrong += 1
print(f"  resolved to the right team : {resolved}")
print(f"  tied (no team assigned)    : {tied}")
print(f"  resolved to the WRONG team : {wrong}")

# The real case: some of the five are smurfs the database has never seen.
print("\n--- smurfs: replace N of 5 names with unknown accounts, bar = 3 ---")
import random
random.seed(7)
for smurfs in (1, 2, 3):
    correct = tied = wrong = none = 0
    for i, ((mid, gno, tid), five) in enumerate(lineups.items()):
        names = list(five)
        random.shuffle(names)
        seen = set(names[smurfs:])                       # the rest are smurfs
        seen |= {f"smurf{i}_{k}" for k in range(smurfs)}
        scored = sorted(((len(seen & r), t) for t, r in roster.items() if len(seen & r) >= 3),
                        reverse=True)
        if not scored:
            none += 1
            continue
        top = scored[0][0]
        winners = [t for s, t in scored if s == top]
        if len(winners) > 1:
            tied += 1
        elif winners[0] == tid:
            correct += 1
        else:
            wrong += 1
    tot = len(lineups)
    print(f"  {smurfs} smurf(s): correct {correct:5d} ({100*correct/tot:5.1f}%)   "
          f"tied {tied:4d}   WRONG {wrong:4d}   unidentified {none:5d} ({100*none/tot:5.1f}%)")

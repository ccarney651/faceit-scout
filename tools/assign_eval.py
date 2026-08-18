"""How accurate is role-constrained player assignment, and where must it abstain?

Evidence for specs/2026-08-16-player-assignment-design.md 3, and the source of the
FLOOR constant in docs/capture/engine/assign.js. Ground truth is by construction:
we know the real five-player, role-tagged lineup for every team-game, so we shuffle
it into HUD slots, corrupt the names to model OCR, and ask each resolver to put it
back. Reports correct / WRONG / abstained per five slots.

The WRONG column is the one that matters. The old name-only matcher is never wrong
(it just gives up); a resolver that fills slots in is only an improvement if it does
not start inventing attributions, and FLOOR is what holds that line -- at FLOOR 0
the same code produced 33.6% wrong assignments once the reads went to garbage.

CAVEAT, and it is not a small one: the corruption model is uniform independent
per-character noise. Real tesseract errors are systematic and correlated (l/I/1,
rn/m, whole-name failures). These curves rank the thresholds and validate the
logic; they do not predict field accuracy. Replace them with measured reads once
capture sessions have populated playersRaw (design doc 7).

Re-run it when the season turns over or the rosters grow, exactly as with the
3-of-5 bar in tools/roster_match_eval.py.

    .venv/Scripts/python.exe tools/assign_eval.py

simScore here is 100 * difflib ratio; names.js _matchTotal is a hand port of exactly
that (Ratcliff/Obershelp), so the two agree.
"""
import collections
import difflib
import itertools
import pathlib
import random
import sqlite3
import unicodedata

DB = pathlib.Path(__file__).resolve().parents[1] / "faceit.sqlite3"

STRONG = 75          # names.js STRONG_NAME_SCORE
ASCII = set("abcdefghijklmnopqrstuvwxyz0123456789_-.'~ ")
TRANSLIT = {'ø':'o','ł':'l','đ':'d','ħ':'h','ŧ':'t','ŋ':'n','ɓ':'b','ƒ':'f','ŀ':'l',
            'ɛ':'e','ɠ':'g','ƕ':'h','ǃ':'!','ǂ':'t','ß':'ss','æ':'ae','œ':'oe',
            'þ':'p','ð':'d','ı':'i','ſ':'s'}

def fold(s, translit):
    """names.js normName; `translit` toggles the proposed non-decomposable fix."""
    s = str(s or '').split('#')[0]
    if translit:
        s = ''.join(TRANSLIT.get(c, TRANSLIT.get(c.lower(), c)) for c in s)
    s = ''.join(c for c in unicodedata.normalize('NFD', s)
                if not unicodedata.combining(c))
    return s.lower().strip()

def sim(a, b):
    return 100.0 * difflib.SequenceMatcher(None, a, b).ratio() if (a or b) else 0.0

def ocr(name, err, rng):
    """What tesseract emits: nearest allowed glyph (always transliterated to ASCII,
    the whitelist is not optional), then `err` per-character noise."""
    base = fold(name, translit=True)
    base = ''.join(c if c in ASCII else '' for c in base)   # non-Latin -> nothing
    out = []
    for c in base:
        if rng.random() >= err:
            out.append(c)
        elif rng.random() < 0.5:
            out.append(rng.choice('abcdefghijklmnopqrstuvwxyz0123456789'))
        # else: dropped
    return ''.join(out)

def greedy(reads, roster, translit):
    """Current matcher — index.html:attribute(). Best-scoring pair above STRONG,
    1:1, then a single process-of-elimination step."""
    cand = []
    for i, r in enumerate(reads):
        if not r:
            continue
        for p in roster:
            s = max(sim(r, fold(n, translit)) for n in p['names'])
            cand.append((s, i, p['id']))
    cand.sort(reverse=True)
    out, used_i, used_p = [None] * 5, set(), set()
    for s, i, pid in cand:
        if s < STRONG:
            break
        if i in used_i or pid in used_p:
            continue
        out[i] = pid
        used_i.add(i)
        used_p.add(pid)
    open_i = [i for i in range(5) if out[i] is None]
    open_p = [p['id'] for p in roster if p['id'] not in used_p]
    if len(open_i) == 1 and len(open_p) == 1:
        out[open_i[0]] = open_p[0]
    return out

def role_constrained(reads, roster, slot_roles, translit, margin, floor=0.0, strong=None):
    """Proposed: the hero at each slot fixes its role, so only same-role players are
    candidates. Optimal (not greedy) assignment inside each role group; abstain when
    the best pairing does not beat the runner-up by `margin`."""
    out = [None] * 5
    by_role = collections.defaultdict(list)
    for p in roster:
        by_role[p['role']].append(p)
    for role, slots in collections.defaultdict(
            list, {r: [i for i, sr in enumerate(slot_roles) if sr == r]
                   for r in set(slot_roles)}).items():
        players = by_role.get(role, [])
        if not players or len(players) != len(slots):
            continue                       # role data missing -> leave unresolved
        scored = []
        for perm in itertools.permutations(players):
            total = sum(max(sim(reads[s], fold(n, translit)) for n in perm[k]['names'])
                        for k, s in enumerate(slots))
            scored.append((total, perm))
        scored.sort(key=lambda x: -x[0])
        best = scored[0]
        # A forced group (the tank: one role, one player) is correct from the role
        # constraint alone and needs no name evidence at all. Anything larger needs
        # BOTH a lead over the runner-up AND an absolute score floor -- without the
        # floor, pure noise invents a lead and gets confidently assigned.
        if len(scored) == 1:
            pass
        elif best[0] - scored[1][0] < margin:
            continue
        else:
            # `strong`: one decisive read carries its partner by elimination, so the
            # group mean must not veto it. Barely moves the needle here (+0.5pp)
            # because uniform per-character noise degrades all five names together;
            # real OCR fails per NAME, which is where it earns its keep. What this
            # harness does establish is that it costs nothing: the wrong-assignment
            # rate is identical with and without, at every error level.
            per = max(max(sim(reads[s], fold(n, translit)) for n in best[1][k]["names"])
                      for k, s in enumerate(slots))
            decisive = strong is not None and per >= strong
            if best[0] / len(slots) < floor and not decisive:
                continue
        for k, s in enumerate(slots):
            out[s] = best[1][k]['id']
    return out

def main():
    con = sqlite3.connect(DB)
    games = collections.defaultdict(list)
    for mid, gno, tid, pid, role, gn, nick in con.execute("""
            select rp.match_id, rp.game_no, rp.team_id, rp.player_id, rp.role,
                   p.game_name, p.nickname
            from round_players rp join players p on p.id = rp.player_id
            where rp.team_id is not null and rp.role in ('Tank','Damage','Support')"""):
        names = [n for n in ((gn or '').strip(), (nick or '').strip()) if n]
        if names:
            games[(mid, gno, tid)].append(
                {'id': pid, 'role': role, 'names': names, 'hud': names[0]})

    lineups = [(k, v) for k, v in games.items() if len(v) == 5
               and collections.Counter(p['role'] for p in v) ==
                   {'Tank': 1, 'Damage': 2, 'Support': 2}]

    print(f"{len(lineups)} real team-games with a complete 1/2/2 lineup\n")
    hdr = (f"{'OCR err':>8} | {'greedy: ok':>10} {'wrong':>6} {'null':>5} "
           f"| {'role-c: ok':>10} {'wrong':>6} {'null':>5}")

    # (floor, strong): the shipped gate is the last row. The earlier rows are the
    # evidence for it - floor 0 is what 33.6% wrong looks like, 60 is what being
    # too cautious costs, and the strong=None row isolates the decisive-read clause.
    for floor, strong in ((0.0, None), (30.0, None), (45.0, None), (60.0, None),
                          (45.0, 75.0)):
        lbl = "mean only" if strong is None else f"mean OR one slot >= {strong:.0f}"
        print(f"=== abstention floor = {floor:.0f}, {lbl} ===")
        print(hdr)
        for err in (0.0, 0.15, 0.30, 0.50, 0.75, 1.0):
            rng = random.Random(12345)
            tot = collections.Counter()
            for _, roster in lineups:
                slots = roster[:]
                rng.shuffle(slots)
                reads = [ocr(p['hud'], err, rng) for p in slots]
                truth = [p['id'] for p in slots]
                slot_roles = [p['role'] for p in slots]
                for tag, got in (('g', greedy(reads, roster, True)),
                                 ('r', role_constrained(reads, roster, slot_roles,
                                                        True, 1.0, floor, strong))):
                    for i in range(5):
                        if got[i] is None:
                            tot[tag + 'null'] += 1
                        elif got[i] == truth[i]:
                            tot[tag + 'ok'] += 1
                        else:
                            tot[tag + 'wrong'] += 1
            n = len(lineups) * 5
            print(f"{err:>8.0%} | {tot['gok']/n:>9.1%} {tot['gwrong']/n:>6.1%} "
                  f"{tot['gnull']/n:>5.1%} | {tot['rok']/n:>9.1%} "
                  f"{tot['rwrong']/n:>6.1%} {tot['rnull']/n:>5.1%}")
        print()

if __name__ == '__main__':
    main()

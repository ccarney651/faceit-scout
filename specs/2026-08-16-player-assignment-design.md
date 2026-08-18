# Player assignment from role constraints — design

**Date:** 2026-08-16
**Scope:** league capture (`docs/capture/index.html`) only. Scrims are explicitly
out of scope — see §8.
**Status:** approved, implementing.

## 1. The problem

`attribute()` (`docs/capture/index.html`) resolves a HUD slot to a FACEIT player
using **name similarity alone**: each slot takes its best-scoring roster player
above `STRONG_NAME_SCORE` (75), one player per slot, plus one
process-of-elimination step when exactly one slot and one player remain.

When OCR cannot read the names, it returns nothing. Stylised Battle.net names
make this common — `The best in the west` fields `ÄL7ÖTĦÌ` and `Mź7w`, which
`tessedit_char_whitelist` (plain ASCII) can only ever render approximately.

The result is that hero observations are captured with no player attached, which
is why `comp_slots.player_id` is **0 of 1620 rows**.

## 2. The insight

FACEIT records a **role per player per game** (`round_players.role`, sourced from
the `i16` stats field — see `faceit_sync/sync.py`). Overwatch tournament play is
role-locked, and the data confirms it:

```
8303/8356 team-games are exactly 1 Tank / 2 Damage / 2 Support (99.37%)
```

All 53 exceptions are a *missing* role (the `-` sentinel from a failed stats
capture), never a genuine 2-tank comp.

The role of the hero recognised in a slot therefore **partitions the candidates**.
A comp that is read correctly reduces the search from 120 permutations to
1 × 2 × 2 = 4, and the tank is determined outright with no name evidence at all.

This is the same reduction `owdb/match.py` already applies to *hero* matching
("a tank slot becomes a 1-of-14 decision instead of 1-of-52"). We are applying it
to *player* matching.

## 3. Measured behaviour

`tools/assign_eval.py` shuffles every real 1/2/2 lineup into HUD slots, corrupts
the names to model OCR, and asks each resolver to put it back. Ground truth is
known by construction.

Shipped gate (floor 45, or one slot at `STRONG_NAME_SCORE`), 8303 team-games:

```
 OCR err | greedy: ok  wrong  null | role-c: ok  wrong  null
      0% |    100.0%   0.0%  0.0% |    100.0%   0.0%  0.0%
     15% |     94.4%   0.0%  5.6% |    100.0%   0.0%  0.0%
     30% |     63.5%   0.0% 36.5% |     98.9%   0.0%  1.1%
     50% |     23.5%   0.0% 76.5% |     86.0%   0.0% 13.9%
     75% |      3.0%   0.0% 97.0% |     38.7%   0.1% 61.2%
    100% |      0.0%   0.0% 100.0% |     20.0%   0.0% 79.9%
```

At 30% character error, slot tagging goes from 63.5% to 98.9%. At 50%, from
23.5% to 86.0%. The bottom row is the floor of the design: with names
contributing **nothing**, 20% of slots — precisely the tank — are still correct,
and none are wrong.

**The `wrong` column is the whole safety argument, and it depends on the floor.**
With `floor = 0` the same resolver produced **33.6% wrong** assignments at total
garbage, because uniform noise manufactures a score lead between two candidates.
Floor 60 is strictly worse than 45 (56.9% vs 85.5% correct at 50% error under
the mean-only gate, both zero wrong); floor 30 reintroduces 1.5% wrong.
**45 dominates.**

### Validated against real frames (2026-08-16)

The synthetic curves have since been checked against **real tesseract output on
real HUD frames**, using `tools/real_frame_eval/`. Ground truth is free when a
frame shows its replay code: the code resolves to a match and game, which gives
the exact role-tagged lineup. Eight frames, 80 slots:

```
  OLD (name-only)          68 correct, 0 wrong, 12 unresolved    85.0%
  NEW (role-constrained)   80 correct, 0 wrong,  0 unresolved   100.0%
```

**The synthetic model was wrong in one important way.** It corrupts every name a
little; real OCR destroys *whole names* while leaving others pristine. Tesseract
returned `4.04` for a clean, legible `PROXY` in six of the eight frames. And
`JODAN` read perfectly in all eight yet matched nothing, because FACEIT's stored
`game_name` for that player says `Arclite` — the battletag is stale against the
live Battle.net name. Role plus elimination recovered both.

That difference is also why §4.2 accepts a single decisive read (below): the
mean-only gate abstained on a pair where one name scored 88 and its partner was
destroyed, losing a slot the old matcher got right.

### The crop was the real bottleneck (2026-08-18)

The frames above were cropped by the *evaluation harness*, which self-calibrates
the name row from the image. Production did not: `nameCanvas()` took a fixed
48-90% of the calibration cell's height, and the calibration box is fitted to the
hero **portraits**. On a real frame that band straddles the portrait bottom, the
name and the health bar — and the bar, a solid bright block, dominates it. So the
harness was measuring the resolver on crops production never produced.

Re-run over the same nine frames with real tesseract, comparing the production
geometry against a located row:

```
                   reads correct alone   attributed   wrong
  fixed 48-90%          15/90              36/90        2
  located row           77/90              90/90        0
```

That is very likely why `comp_slots.player_id` was 0 of 1620 historically, and it
means the 2026-08-16 live session's 6/10 was measuring the crop, not the
resolver.

The fix is `engine/frames.js nameRow()`: find the name row once **per side**
across the whole five-slot strip, and use it for all five crops. Per slot it does
not work, and two attempts proved it — the hero portrait sits inside the cell
above the name and its art is transition-dense, and a long name can out-score the
health bar. Both failures are recorded in `tools/real_frame_eval/README.md` so
they are not tried a third time.

Note what did *not* change: the resolver. Every one of the thirteen reads still
wrong on their own is recovered by the role constraint, `PROXY`→`404f` included.
The two gates are doing exactly what §3 said they would; they were simply being
fed a picture of a health bar.

### What this evidence is still not

The corruption model behind the first table remains uniform per-character noise,
and the real-frame check is two lineups over nine frames — 90 slots, not 90
independent situations. It also supplies slot roles from ground truth, so it
tests the assignment logic assuming hero recognition is correct. `45` stays a
provisional number.

The floor has also never been exercised in anger since the crop was fixed: at
90/90 with clean reads, nothing in this evidence tells us where it bites.

The live session that followed (2026-08-18, `3DQNHD`, Oasis) tagged **10/10 with
none wrong and none abstained**, against 6/10 with four abstentions on the same
code before the crop fix — and it did it on The best in the west, the roster in
1 above. So the design works end to end.

The per-slot outcomes were eight `matched` and two `forced`, and they cover every
mechanism this document argues for: both tanks forced with no name evidence (and
independently confirmed by clean reads of `AYZO` and `FAISAL`); one annihilated
read, `"1.7-1'4"` for `GRank`, recovered because its support partner read `"ZAK"`
decisively (§4.2's single-decisive-read clause); and `"MZ7W"`/`"AL7OTHI"` matching
`Mź7w`/`ÄL7ÖTĦÌ` through §4.4's transliteration.

The floor still has not been tested. Nothing abstained, and the one destroyed
read was rescued by elimination rather than by clearing a score bar — so `45`
remains a number derived from a synthetic model, and ten real reads is nowhere
near enough to re-derive it.

And all of it assumes calibration put the box on the portraits. It does live —
auto-calibrate reported 10/10 portraits confident on 2026-08-18 — but it does not
on the frames in `screenshots/`, whose HUD geometry differs from a live capture's.
The eval derives its boxes from the pixels for that reason; see
`tools/real_frame_eval/README.md`.

## 4. Design

### 4.1 Per-game lineups in the feed — required, not optional

`data.json`'s `rosters` is keyed by `match_id` and groups by
`(team_id, player_id)` across the whole match. Substitutions therefore inflate it:

```
per-MATCH team roster sizes: {5: 1650, 6: 473, 7: 117, 8: 20}
match-teams with >5 players: 610/2260 = 27.0%
```

A 6-player roster offers 3 damage candidates for 2 damage slots. The exact cover
that makes the role constraint work is gone, and a substitute who never played
that game becomes a candidate.

So `build_capture_data.py` gains a **new, additive** key:

```
lineups: { "<match_id>:<game_no>": { <team_id>: {
             name, players: [{id, nick, game_name, role}] } } }
```

Additive because `rosters` is consumed by scrim opponent
identification, which wants the
*accumulated* squad. Both shapes are correct for their own consumer; neither
should be bent to serve the other. `lineups` is emitted only for coded games, so
the size cost is bounded by the code list.

A player whose role is missing (the `-` sentinel) is emitted with `role: null`.
The resolver then finds that role group short by one and leaves the whole group
unresolved — the safe reading, since the alternative is inventing a role for a
real player and putting them in the wrong candidate set. It affects 0.6% of
team-games.

### 4.2 `engine/assign.js` — the resolver

A new pure module beside `names.js`, exported as `window.OWDBAssign` and as
CommonJS, with a co-located `assign.test.js` under `node:test`.

```
assign(reads, lineup, slotRoles, opts) -> { ids: [id|null x5], conf: [n x5] }
```

- Group the five slots by the role of the hero recognised in each.
- Group the lineup's players by their FACEIT role.
- For each role group where the counts match, score **every** permutation
  (at most 2! per group) and take the best — optimal within the group, not
  greedy. Greedy is what the current matcher does, and it is what loses the
  pairs.
- **A group of size one is forced**: assign it with no name evidence at all.
  This is the tank, and it is where the 20% floor comes from.
- Any larger group must clear the `MARGIN` gate — a lead over the runner-up
  permutation — and then **either** a mean per-slot score of at least
  `FLOOR = 45`, **or** one slot matching decisively (at `STRONG_NAME_SCORE`).
  One decisive read settles its partner by elimination, and the mean must not
  veto that; the wrong-assignment rate is identical with and without the clause
  at every error level. Failing the gates abstains — both slots stay `null`.
- Where role counts disagree (a misrecognised portrait, or missing role data),
  that group is left unresolved rather than forced.

### 4.3 Hero misrecognition

The slot's role comes from the recognised hero, so a misread portrait puts a slot
in the wrong candidate group. The mitigation already exists in the native path:
`roles_consistent` (`owdb/match.py`) checks the implied role counts against the
known 1/2/2 and rejects the read when they disagree. `assign.js` applies the same
check — a comp whose implied roles are not 1/2/2 resolves only the groups that do
line up.

### 4.4 `normName` transliteration

`normName` folds accents by NFD decomposition, which only works on characters
that *decompose*. `ø ł đ ħ ŧ ŋ ɓ ƒ ŀ ɛ ɠ ƕ ǂ ß` have no canonical decomposition,
so the roster keeps a glyph the ASCII-restricted OCR can never emit:

```
"ŚŁØŴ"  roster folds to "słøw"  but OCR sees "slow"  score=50.0  (below 75)
"ŦŪX"   roster folds to "ŧux"   but OCR sees "tux"   score=66.7  (below 75)
```

A transliteration table added to `normName` fixes these. It affects **10 of 1304
players** — small, but correct and independently testable, and it is a fold fix
rather than an OCR change.

### 4.5 Widening the OCR whitelist — rejected

Considered and rejected. Both sides are deliberately folded to ASCII: the roster
by `normName`, the OCR by `tessedit_char_whitelist`. Emitting `Ħ` from OCR only
helps if the roster stops folding, and the fold is what makes the comparison
robust to a diacritic OCR misreads — the lever fights itself. Widening also
degrades the 96% of names that read fine today by adding decoder classes, and
`eng.traineddata` most likely has no class for these glyphs to begin with.

Measured ceiling: with a *perfect* ASCII read, every player except 5 non-Latin
names already matches. The character set is not where the accuracy is going —
ordinary OCR noise is, and that is what §4.2 addresses.

## 5. Where it plugs in

`detectSides()` and `retagPlayers()` in `index.html`, replacing the `attribute()`
calls. Both already have the recognised heroes per slot available, which is what
supplies `slotRoles`.

`attribute()` is retained as the fallback for a code whose `lineups` entry is
absent (an older feed, or a match whose stats never captured), so a stale
`data.json` degrades to today's behaviour rather than to nothing.

## 6. Confidence, and what consumes it

Each slot carries a confidence: `forced` (role-determined, no name evidence),
`matched` (cleared both gates), or `null` (abstained). Stored alongside the
existing `playersRaw` so a later matcher improvement can re-resolve old captures
offline.

The review panel surfaces abstained slots first — they are exactly the ones an
operator can fix in one click, and there are now few of them.

## 7. Replacing the synthetic model

The resolver persists the raw read beside the confirmed assignment. Once real
capture sessions have populated `playersRaw` and the operator has confirmed or
corrected the tags, `tools/assign_eval.py` gains a second mode that measures
against **real** reads instead of synthetic corruption, and `FLOOR` is re-derived
from it. Until then the 45 is explicitly provisional.

## 8. Out of scope

**Scrims.** The role and exact-lineup data used here exists only for a coded
league match. `scrim.html` faces an opponent it must first identify from the HUD
itself, with no FACEIT match behind it. Adapting this to scrims means degrading
the prior to historical role frequencies, which is a separate design.

**Hero-pool priors.** Once `comp_slots.player_id` is populated, a player's hero
pool discriminates a pair with no name signal at all. It is cold-start today
(0 rows) and deliberately deferred — this design is what generates its input.

## 9. Verification

- `assign.test.js` under `node:test`: forced tank, clean pair, ambiguous pair
  abstains, floor rejects noise, role-count mismatch leaves the group unresolved,
  missing role treated as wildcard.
- `names.test.js`: transliteration cases from §4.4.
- pytest: the feed emits `lineups` with roles; per-game keying holds; the
  existing capture-attribution suite still passes.
- `tools/assign_eval.py` re-runnable — re-run it when rosters change.
- `frames.test.js`: the locator prefers the name row over the brighter health
  bars below it and the busier portrait art above it, survives a bright scene
  behind the HUD, and returns null on a featureless band rather than inventing a
  row.
- `tools/real_frame_eval/rowfind_sweep.py`: nine frames x four capture
  resolutions x twenty-five perturbed calibration boxes, 1800/1800 landing on the
  name row; `rowfind_parity.py` then runs the **shipped** JS over those same real
  pixels, so the Python used for sweeping cannot drift from what ships.

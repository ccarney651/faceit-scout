# Replay-bot segment observations — design

## 0. Why this exists

`resolve.js` votes a round's samples to one winning hero per slot
(`vote.js`) and reports `contested` when the winner didn't get a clear
majority. `emit.js`'s `fromRounds()` then ships one observation per
round-side — and, only when *some* slot in the round was contested, a
second observation for the *whole side* at the round's midpoint, with
every contested slot's alt swapped in at once.

This conflates two different things `contested` can mean: noisy reads on
a slot that never changed hero, and a genuine mid-round hero swap.
`confusion_matrix.out.json` shows Tracer and Vendetta aren't even close
as templates, so a Tracer→Vendetta disagreement seen live is a real
swap, not noise — and today it's either voted away to whichever hero had
more samples (the other hero vanishes from the record entirely) or, if
it triggered `contested`, smeared into one blended round-midpoint
observation that mistimes the swap and drags in four slots that never
changed. Downstream, `owdb/contribute.py`'s `player_pools()` and
`_primary_hero_per_game()` dedupe by round, so a hero present anywhere
in a round is worth exactly one round of credit regardless of how much
of the round it was actually played — a swapped round should split
credit, not double it or drop half of it.

Per `ARCHITECTURE.md` §9, observations are already raw timestamped
samples — this closes the gap between what the schema already allows
and what the pipeline currently produces, without changing the schema.

Explicitly out of scope: `timeline.js`'s fixed 3/5-samples-per-round
sampling density. Moving to an interval-based scheme (e.g. every ~60s)
would improve swap detection further, but it's a separate throughput
trade-off the operator hasn't decided yet. This design works with
whatever samples exist today and gets better as density does.

## 1. What changes

Three files, no schema change:

- `resolve.js` — `resolveSlot()` gains a `segments` field per slot.
- `emit.js` — `fromRounds()` walks segments instead of the round-level
  midpoint hack.
- `owdb/contribute.py` — `player_pools()` and `_primary_hero_per_game()`
  weight by segment duration (ms) instead of round-count.

`review/server.js`'s `applyCorrections()` needs one addition (collapse
`segments` on a human correction); the review UI itself is unchanged —
operators still see and correct one resolved guid per slot per round.

## 2. Segmentation (`resolve.js`)

`resolveSlot(cells, roleKnown, player)` currently takes `cells` (the
slot's per-sample reads, in order) and returns one winner. It needs the
matching per-sample timestamps too, so the caller (`rounds()`) passes
the round's samples (`mine`, which already carries `.t`) alongside
`cells` — same data it already has in scope, just threaded one level
deeper.

New pure helper, alongside `runnerUp()`:

```js
// Run-length encode a slot's raw guid sequence into stable stretches.
// A lone misread (1 sample) is absorbed into the segment around it —
// SEGMENT_MIN_RUN consecutive samples must agree before a new segment
// starts, so noise doesn't fragment a slot that never actually changed.
//
// Samples inside the round's first ASSEMBLE_GRACE_S seconds are
// dropped before segmenting: the opening stretch of a round is the
// same pre-render/spawn window timeline.js's ASSEMBLE_STARTS_BY_S
// already excludes at the map level, applied here per-round. That
// window goes uncredited to any hero rather than guessed.
function segmentSlot(cells, times, roundFromT) {
  var SEGMENT_MIN_RUN = 2;
  var ASSEMBLE_GRACE_S = 10;
  // ... filter samples with times[i] < roundFromT + ASSEMBLE_GRACE_S,
  // then run-length the remaining (guid, t) pairs with the min-run
  // threshold, returning [{guid, name, from_t, reads}] in time order.
}
```

`resolveSlot()`'s existing return value (`guid`, `name`, `support`,
`contested`, `alt_guid`, `flags`, …) is unchanged — it's still the
whole-round vote, which is what the review UI reads and edits. It gains
one new field:

```js
segments: segmentSlot(cells, sampleTimes, round.from_t)
```

A round with a stable slot produces one segment (`from_t` = the first
post-grace sample's time). A round with one real swap produces two (or
more, if it flickers back — each confirmed run is its own segment).
This is strictly additive to the existing return shape, so nothing that
reads `resolveSlot()`'s other fields needs to change.

`rounds()` passes `round.from_t` and the matching per-sample times
through to `resolveSlot()`; both are already in scope in the loop that
builds `cells`.

## 3. Emission (`emit.js`)

`fromRounds()`'s per-round, per-side block currently does:

1. Emit one observation at `round.from_t` with every slot's winning
   guid.
2. If any slot was contested, emit one more observation at the round's
   midpoint with every slot's `alt_guid` (or `guid`, if that particular
   slot wasn't the contested one) swapped in.

It becomes:

1. Collect the side's 5 slots' `segments` arrays.
2. Take the union of every segment's `from_t` across all 5 slots as the
   side's boundary times for this round, sorted.
3. At each boundary time, emit one observation whose `heroes[slot]` is
   whichever of that slot's segments is active at that time (forward-
   filled from the most recent segment start ≤ the boundary — a slot
   that didn't swap contributes the same guid at every boundary).
4. A slot with no segments (empty round-side, as today) drops out of
   `heroes`/`pairs` for that observation, same absence-handling as now.

A round with no swaps anywhere produces exactly one observation per
side — byte-identical to today's output for the common case, just
computed a different way. Only a round with a real swap produces extra
observations, one per actual swap moment, with only the slot(s) that
swapped changing between them — fixing both problems in `fromRounds()`
at once (mistimed midpoint, blending unrelated slots).

`pairs` (player attribution) is unaffected — attribution is once-per-map
per `specs/2026-09-10-replay-bot-player-attribution-design.md` §2, so
every emitted observation for a slot carries that slot's fixed
`player_id` regardless of which segment is active.

## 4. Duration weighting (`owdb/contribute.py`)

`player_pools()` currently does:

```python
rk = f"{match_id}:{game_no}:{side}:{round_no}:{sub_map}"
agg[team][pid][guid].add(rk)   # presence, not duration
```

A hero present anywhere in a round earns one full round-key regardless
of how long it was actually played. With segmentation, a swapped round
now emits two observations sharing one `round_no` but different guids —
unchanged, this would double-count (both heroes get a full round).

Replaced with a millisecond accumulator:

```python
agg[team][pid][guid] += duration_ms   # float sum, not a set
```

`duration_ms` for one slot's segment (one observation's `pairs` entry)
is computed by grouping that map's observations by `(side, slot)`,
sorting by `ts`, and taking the gap to the *next* observation in that
group. The last segment in a round borrows the gap to the *next
round's* first observation for that side (a small, accepted
over-count — the inter-round break is short relative to a round, and
threading round boundaries through the schema to trim it exactly isn't
worth the complexity). The last segment of a map's last round has no
"next" to borrow from; it's dropped rather than guessed, the same
"missing beats wrong" rule the module already applies elsewhere.

For every existing single-segment-per-round case (all human
contributions, all non-swap bot rounds — the overwhelming majority of
data today), this produces the exact same relative ranking as the old
round-count, just measured in ms instead of round-units: one segment
per round, one gap per round. `player_pools()`'s existing tests assert
ordering/ratios, not absolute round-counts, so they should not need to
change; add new tests only for the swapped-round case.

`_primary_hero_per_game()` gets the same treatment — replace its
round-key `set()` accumulator with the same ms-duration sum, so a
player's "primary hero" for a game is whichever hero they spent the
most *time* on, not the most rounds-with-any-presence.

## 5. Human correction (`review/server.js`)

`applyCorrections()`'s `kind === 'hero'` branch already resets
`slot.contested = false; slot.alt_guid = null` — the operator is
asserting one hero for the whole round, overriding whatever the machine
saw. It gains one line to match: `slot.segments = null` (or omitted;
`fromRounds()` treats a missing `segments` as "one segment spanning the
whole round," so old review artifacts saved before this change replay
correctly with no migration).

Editing individual segments in the review UI is out of scope — a
correction always collapses to one hero for the round, same as today.

## 6. Testing

- `resolve.test.js` — new cases for `segmentSlot()`: stable slot → one
  segment; a confirmed swap → two; a single-sample flicker → absorbed,
  still one; samples inside the assemble grace window excluded.
- `emit.test.js` — a no-swap round emits the same single observation as
  before (regression pin); a one-slot swap emits exactly one extra
  observation, at the real swap time, with only that slot differing
  from the previous one.
- `owdb/tests/test_contribute.py` — a swapped round splits credit
  proportionally to segment duration instead of crediting both heroes a
  full round; existing `player_pools`/`_primary_hero_per_game` tests
  continue to pass unchanged.
- `tools/replay_bot/review/server.test.js` — a hero correction clears
  `segments` alongside `contested`/`alt_guid` in `applyCorrections()`.

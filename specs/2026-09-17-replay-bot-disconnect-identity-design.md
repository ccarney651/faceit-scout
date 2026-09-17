# Replay-bot disconnect slot-shift + per-sample identity — design

## 0. Why this exists

Two real, confirmed bugs share one root cause: the pipeline assumes a HUD
side's five grid positions are a stable, permanent mapping to five roster
players for the life of a map. That assumption is false whenever a player
disconnects mid-round.

**Bug 1 — slot-shift on disconnect (PLANS.md, "Replay bot" §, P2, previously
unscoped).** When a player disconnects, Overwatch's replay HUD does not
leave their card blank in place — it removes it and compacts every player
to its right one slot to the left. The fixed 5-way pixel grid `calib.js`
reads does not know the row shrank, so:

- The disconnected player's own fixed grid position now shows whoever
  shifted into it (a **different real player's** hero, misread as a
  same-slot swap).
- The single rightmost grid position, regardless of which slot actually
  disconnected, reads empty (`ABSENT_GUID`) — correctly detecting *an*
  absence, but attributing it to the wrong player.

Confirmed live on `H5Q9WE` (2026-09-17 retroactive audit + real pixel
inspection): `bones` (slot 3) disconnected for ~135s. During that window,
`SANTY` (slot 4) visually compacted into slot 3's fixed pixel territory —
so slot 3 read `D.Mon` (Santy's hero, not bones'), and slot 4 read
`ABSENT_GUID` (genuinely a hole, but not because Santy left). The operator
confirmed the general mechanic: **up to 4 slots can shift**, depending on
which of the 5 original slots disconnects (slot 0 leaving shifts all 4
others; slot 3 leaving shifts only 1).

**Bug 2 — attribution shares the same fragility.** `attribute.js`'s
`attributeMap()` resolves each side's player_id-per-slot from OCR'd names
on **one frame** (falling forward through up to the first 4 kept samples if
the very first is unreadable — `run.js`'s existing candidate loop). If a
disconnect is already underway on every one of those early candidate
frames, attribution is built from shifted data and gets it wrong the same
way the hero-read does.

Both bugs are the same underlying problem: the pipeline keys per-sample
hero reads by **visual position**, when the only thing resolve.js can
safely assume continuity of is **player identity**. This design fixes both
by resolving identity from names, per sample, and using it to re-key
reads into a stable canonical slot before anything else touches them.

## 1. Scope

**In:**

- A per-sample name-OCR read, alongside the existing per-sample hero read
  (`phases.readHud`) — new raw data captured, not yet interpreted.
- A new pure, batch aggregation pass (`attribute.js`, reworked) that runs
  once a map's samples are all collected: establishes each side's
  canonical `player_id → slot` mapping from every sample's name reads
  (not one frame), then re-keys every sample's hero-cell array from
  visual position into canonical slot order.
- Attribution (`player_id` per slot) becomes a direct byproduct of that
  same aggregation, replacing `run.js`'s current "first 4 frames, pick the
  one with the most assigned slots" loop.
- Reconnection: no special-case logic — once a returning player's name is
  legible again, they match their already-established canonical slot
  normally.

**Out:**

- Any change to `resolve.js`, `emit.js`, `owdb/contribute.py`, or the
  segment/flag schema. This design's whole point is that resolve.js keeps
  receiving samples that are already in stable canonical-slot order,
  exactly the shape it expects today. `segmentSlot`, `Vote.slot`,
  `cross-role-swap`, `takeover-frame` — none of it changes.
- Restructuring the pipeline around player identity as the primary key
  throughout (considered and rejected — see §3.1). Slot index stays the
  external contract; only the mapping from visual position to slot index
  becomes per-sample instead of assumed-fixed.
- Any change to the name-OCR quality itself (contrast, PSM mode, fill
  ceiling) — 2026-09-15's fixes are reused unchanged, just invoked more
  often.
- `assign.js`'s matching algorithm itself — reused unmodified, run more
  often rather than rewritten.
- The single-unattributed-teammate elimination rule (PLANS.md P3) — related
  (both are "use roster completeness to resolve an ambiguous slot"), but a
  separate, smaller idea. Not blocked by this design; can land before,
  after, or alongside it.

## 2. Cost

Measured directly (`tesseract.js`, real PSM-8/whitelist settings matching
production, warm worker): **~28ms per name-crop `recognize()` call.** A full
sample's 10 names (5 slots × 2 sides) costs **~280ms**.

Against the measured per-visit baseline (`specs/2026-09-14-replay-bot-30s-
capture-design.md` §2.1: ~3.9s/visit, seek + settle + grab + read
dominating): **~7% overhead per sample.** Real, but small relative to what
already exists — no cadence or retention change needed to afford it.

## 3. Architecture

### 3.1 Two designs considered

**A — positional patch (chosen).** Keep slot index as the stable key
everywhere downstream of capture. Add one new pure aggregation pass between
capture and `resolve.rounds()` that re-keys each sample's 5-cell array from
visual position into canonical slot order, using per-sample name identity
as the correction signal. `resolve.js` is untouched.

**B — identity-first pipeline.** Restructure `resolve.js` itself to build
segments per player identity rather than per slot index, with slot index
becoming a display-time concern only.

**B rejected**: much larger blast radius (`resolve.js`, `emit.js`, the
review page's slot-indexed rendering, `owdb/contribute.py`'s consumer side
all assume slot index today), more risk, and it does not solve anything A
doesn't — the only thing that ever needs to survive a disconnect is "which
slot does this sample's data belong to," which A already answers.

### 3.2 Data flow

```
capture (per sample, per side)
  phases.readHud()          -> 5 hero-cell reads, VISUAL position order (unchanged)
  phases.readNames()  [NEW] -> 5 raw OCR strings, VISUAL position order

                    |
                    v  (all of a map's samples collected)

attribute.js's new aggregation pass (batch, pure, runs once per map):
  1. Per sample, per side: Assign.assign(rawNames, roster, slotRolesFor(...))
     -> a candidate player_id per VISUAL position for that sample alone.
     (Same call `attributeMap` already makes per-frame today - just made
     once per sample instead of once per map.)
  2. Aggregate step 1's results across every sample, per side: for each
     VISUAL position, the MODE (most frequent, not necessarily >50% -
     three-way noise on a rare sample should not deny an otherwise-clear
     mode) player_id assigned there across all samples becomes that
     position's canonical owner. (Rare/brief disconnects are a minority of
     a round's samples by construction, so the modal position is the
     undisturbed one.)
  3. canonicalSlotOf(player_id) is now fixed for the whole map: slot index
     = the visual position that player_id owned in the mode.
  4. Re-key: for EVERY sample, for each VISUAL position that sample
     matched a player_id (step 1's per-sample result, not just the mode
     samples), move that position's hero-cell read to
     canonicalSlotOf(player_id) in the OUTPUT sample. A canonical slot no
     visual position matched this sample becomes ABSENT_GUID for that
     slot, that sample - correctly attributed now, not dumped on whichever
     visual position happened to be short a card.

  Output: the map's samples, now in stable canonical-slot order (same
  shape `resolve.rounds()` already consumes) + a player_id-per-slot
  attribution map (step 3, directly - no separate resolution needed).

resolve.rounds(correctedSamples, rounds, opts)   -- UNCHANGED
```

### 3.3 Why aggregation must be a batch pass, not a live per-sample decision

The canonical mapping cannot be known from the first few samples alone —
that is the exact bootstrapping problem `run.js`'s current "first 4
frames" attribution loop already has, just for a different reason (OCR
legibility there; disconnect timing here). Waiting until every sample is
captured, then resolving canonical order from the whole map's majority,
sidesteps it entirely and costs nothing extra: `resolve.rounds()` already
runs as a batch pass after capture finishes, so this new pass sits
directly before it in the same place in `run.js`'s per-map flow.

## 4. New functions / changed contracts

- **`phases.readNames(io, ocr, framePath)`** [NEW] — mirrors `readHud`'s
  shape but returns raw OCR strings (`{a: [string x5], b: [string x5]}`),
  reusing `Nameplate.nameRow`/`nameCrop` exactly as `attributeMap` already
  does internally. Kept separate from `readHud` (different concern: text,
  not hero portraits), called alongside it from the same per-sample
  capture step.
- **`attribute.js`'s core function, reworked.** `attributeMap(img, sample,
  feed, code)` (single frame) is replaced by a function taking the whole
  map's collected samples (hero reads + name reads together) and returning
  `{ correctedSamples, attribution }`. `playersFor`/`rosterNames`/
  `slotRolesFor` are unchanged and still used internally.
  `Names.confidentOrientation` (which team is on which screen side) is
  still a once-per-map decision, unaffected by this design (a screen-side
  swap doesn't change mid-map) — still resolved once, from the aggregated
  name reads' best sample, and applied before the per-slot remap.
- **`run.js`**: replace the "first 4 samples, pick the one with the most
  assigned slots" loop with one call to the new aggregation, over every
  collected sample.

## 5. Error handling / ambiguity

Same standing rule as every other detector in this pipeline: abstain
rather than guess.

- **A sample's name read doesn't confidently match anyone** (garbled OCR,
  `Assign.assign`'s floor/margin gates already refuse it): that visual
  position casts no vote for that sample, for either the majority
  aggregation or the per-sample re-key. With ~20+ samples per round (30s
  cadence, `specs/2026-09-14-...`), one bad sample doesn't threaten the
  majority; a run of them just means less evidence, not wrong evidence.
- **A slot's player_id never wins a clear majority across the whole map**
  (e.g. disconnected for most of it, or consistently illegible): that slot
  stays unattributed (`player_id: null`, `attribution-abstained` — the
  same flag and meaning it has today), not a forced guess.
- **A round where a slot's canonical owner is NEVER seen in any sample**:
  falls back to today's existing behavior for an unresolved slot — flagged,
  not guessed. (The single-unattributed-teammate elimination rule, PLANS.md
  P3, would help exactly this case if it lands — not required by this
  design, complementary to it.)
- **Reconnection**: no detection logic needed. Once the returning player's
  name is legible again, `Assign.assign` matches them to their
  already-established canonical slot like any other sample. The gap in
  between is however many samples read `ABSENT_GUID` for that slot — real
  information, correctly attributed to the right slot for the first time.

## 6. Testing

Pure, batch function operating on already-collected data — fully testable
with synthetic fixtures (fabricated OCR strings + hero reads), no real
captures or live Tesseract calls needed in the suite, matching this
codebase's existing convention for `resolve.js`/`emit.js`.

Planned cases (TDD, one test per case, red before green):

- Baseline: no disconnect, every sample agrees — canonical order equals
  visual order, attribution matches every slot.
- A single mid-round disconnect at an INTERIOR slot (not slot 4) — confirm
  the shifted samples get re-keyed back to the correct canonical slots, and
  the vacated slot (not the visually-rightmost one) reads `ABSENT_GUID` for
  that window, not the shifted-into slot.
- Disconnect at slot 4 (rightmost) — confirm NO shift is inferred (nothing
  to re-key), matching the existing correct behavior for this one case.
- A 4-slot shift (slot 0 disconnects) — confirm all 4 downstream slots
  re-key correctly.
- Reconnection — confirm samples after the return match the original
  canonical slot again, with no drift.
- Garbled/unreadable names on the disconnect sample itself — confirm the
  slot degrades to `ABSENT_GUID`/unattributed rather than a wrong guess.
- A name that never confidently matches anyone across the whole map —
  confirm that slot stays `attribution-abstained`, not forced.

The real `H5Q9WE`/`P1PXQK` examples that motivated this are documented here
for the record, but cannot become automated regression fixtures directly —
only the already-*matched* hero reads were retained for them (per-sample
raw OCR name strings were never recorded, since this capability doesn't
exist yet). The first live run after this ships is the real-world
validation; the synthetic suite is what TDD builds against.

## 7. Risks / open questions carried into implementation

- `run.js`'s per-map flow changes at the exact point where attribution is
  currently resolved — moderate blast radius for a single map's pipeline,
  low risk to the batch overnight loop as a whole (a per-map failure here
  already degrades to "no names" today per §6 of the original attribution
  design, and should continue to on any new failure mode, not fail the
  map).
- This does not, by itself, fix the OTHER known slot-index-adjacent gap
  (PLANS.md's single-unattributed-teammate elimination rule) — noted as
  complementary, not a blocker either direction.

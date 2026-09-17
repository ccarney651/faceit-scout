# Replay-bot disconnect slot-shift + per-sample identity — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A disconnected player's card no longer misattributes hero reads to the wrong slot (a 1-4 slot compaction shift), and attribution is built from every sample instead of one fragile frame.

**Architecture:** A new per-sample name-OCR read (`phases.readNames`) is captured alongside the existing hero read. Once a map's samples are all collected, a new pure batch function in `attribute.js` (`attributeFromSamples`) establishes each side's canonical `player_id → slot` map from every sample's name-matches (not one frame), then re-keys every sample's hero-cell array from visual position into canonical slot order — defaulting to no change whenever identity is unclear, so hero data is never lost just because a name was hard to read. `resolve.js` is untouched; it keeps consuming samples in the same shape it always has.

**Tech Stack:** Node.js (CommonJS modules), `tesseract.js` (OCR, already wired), `@napi-rs/canvas`, `node:test`/`node:assert`.

**Spec:** `specs/2026-09-17-replay-bot-disconnect-identity-design.md`

## Global Constraints

- No change to `resolve.js`, `emit.js`, `owdb/contribute.py`, or the segment/flag schema (spec §1).
- Identity evidence only ever ADDS a correction — it must never remove/lose hero-read data by being absent or unclear (spec §3.2's HIGH/LOW claim priority; this is the exact regression an earlier draft of the design had).
- Reuse `Assign.assign`/`Names.simScore`/`Names.STRONG_NAME_SCORE` unmodified — no new matching algorithm.
- `attribute.js`'s new core function must be a pure, synchronous function (no OCR calls inside it — OCR already happened at capture time). Fully testable with synthetic fixtures, no real captures or live Tesseract calls in the suite.
- TDD throughout: write the failing test, watch it fail for the right reason, then implement.

---

## Task 1: `phases.readNames()` — per-sample name OCR

**Files:**
- Modify: `tools/replay_bot/phases.js`
- Test: `tools/replay_bot/phases.test.js`

**Interfaces:**
- Produces: `async function readNames(io, ocr, framePath)` → `Promise<{a: [string,string,string,string,string], b: [string,string,string,string,string]}>`. `ocr` is `(canvas) => Promise<string>`, the same shape `attribute.js`'s `make(ocr)` already takes. A side whose name row cannot be found (`Nameplate.nameRow` returns null) contributes five empty strings for that side, same fallback `attributeMap` already uses today (`BLANK_READS`).

- [ ] **Step 1: Write the failing test**

Add to `tools/replay_bot/phases.test.js`, near the existing `readHud` tests:

```js
// ---- readNames: per-sample name OCR, mirrors readHud's shape -------------
//
// 2026-09-17: the disconnect slot-shift design (specs/2026-09-17-replay-bot-
// disconnect-identity-design.md) needs per-sample name identity, not the
// once-per-map single frame attribute.js reads today. readNames is the new
// per-sample read; a later task teaches attribute.js to use it aggregated
// across a whole map. This task only adds the read itself.

test('readNames OCRs all 10 name crops, five per side, in slot order', async () => {
  const img = frameWithSlots({});
  const io = { loadImage: async () => img };
  const seen = [];
  const ocr = async (crop) => { seen.push(crop); return 'SOMENAME'; };
  const names = await P.readNames(io, ocr, 'unused-path');
  assert.strictEqual(names.a.length, 5);
  assert.strictEqual(names.b.length, 5);
  assert.strictEqual(seen.length, 10, 'one OCR call per name crop, both sides');
  names.a.forEach((n) => assert.strictEqual(n, 'SOMENAME'));
  names.b.forEach((n) => assert.strictEqual(n, 'SOMENAME'));
});

test('readNames falls back to five blanks for a side whose name row cannot be found', async () => {
  // frameWithSlots paints only the FROZEN.boxes region - a frame with
  // nothing but black outside it has no name-row band Nameplate.nameRow can
  // find on side b if we blank it out entirely.
  const f = calib.FROZEN.frame;
  const img = canvas.createCanvas(f.w, f.h); // all-black, no boxes painted at all
  const io = { loadImage: async () => img };
  const ocr = async () => 'UNUSED';
  const names = await P.readNames(io, ocr, 'unused-path');
  assert.deepStrictEqual(names.a, ['', '', '', '', '']);
  assert.deepStrictEqual(names.b, ['', '', '', '', '']);
});
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `node --test tools/replay_bot/phases.test.js`
Expected: FAIL with `P.readNames is not a function`.

- [ ] **Step 3: Implement `readNames` in `tools/replay_bot/phases.js`**

Add near `readHud` (after its closing brace). `phases.js` already has `var Nameplate = require('./nameplate.js');` at the top (confirm; if not present, add it the same way `Crop`/`calib` are required at the top of the file) and already requires `calib`.

```js
  // Per-sample name-OCR read - mirrors readHud's shape but returns raw text,
  // not a hero match. Reuses Nameplate.nameRow/nameCrop exactly as
  // attribute.js's (soon-to-be-former) attributeMap did internally - see
  // specs/2026-09-17-replay-bot-disconnect-identity-design.md §4. Kept
  // separate from readHud (a different concern: text, not hero portraits),
  // called alongside it from sampleAt.
  var BLANK_NAMES = ['', '', '', '', ''];
  async function readNames(io, ocr, framePath) {
    var img = await io.loadImage(framePath);
    var out = { a: BLANK_NAMES.slice(), b: BLANK_NAMES.slice() };
    var sides = ['a', 'b'];
    for (var s = 0; s < sides.length; s++) {
      var side = sides[s];
      var row = Nameplate.nameRow(img, calib.FROZEN.boxes[side]);
      if (!row) continue;
      var slotCells = calib.slots(side);
      var got = [];
      for (var i = 0; i < slotCells.length; i++) {
        got.push(await ocr(Nameplate.nameCrop(img, slotCells[i], row)));
      }
      out[side] = got;
    }
    return out;
  }
```

Add `readNames: readNames,` to the `Mod` object at the bottom of `phases.js` (next to `readHud: readHud,` if it's listed there — check the existing `Mod` block and add it alongside).

`phases.js` does not currently require `nameplate.js` (confirmed: its require block at the top of the file is `path`, `@napi-rs/canvas`, `calib.js`, `crop.js`, `match.js`, `timeline.js`, `driver.js`, `timing.js` — no `nameplate.js`). Add `var Nameplate = require('./nameplate.js');` to that block, right after `var Crop = require('./crop.js');`.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `node --test tools/replay_bot/phases.test.js`
Expected: PASS, all tests including the two new ones.

- [ ] **Step 5: Run the full replay_bot suite to check for regressions**

Run: `node --test tools/replay_bot/*.test.js`
Expected: PASS, same count as before plus 2.

- [ ] **Step 6: Commit**

```bash
git add tools/replay_bot/phases.js tools/replay_bot/phases.test.js
git commit -m "replay-bot: add phases.readNames, per-sample name OCR"
```

---

## Task 2: Wire `readNames` into `sampleAt()`

**Files:**
- Modify: `tools/replay_bot/phases.js` (`sampleAt`, around line 451-498)
- Test: `tools/replay_bot/phases.test.js`

**Interfaces:**
- Consumes: `readNames(io, ocr, framePath)` from Task 1.
- Produces: `sampleAt`'s return value gains a `names` field: `{a:[...5], b:[...5]}`. When `opts.ocr` is not provided, `names` is `{a:['','','','',''], b:['','','','','']}` (blank, never throws) — every existing call site that doesn't care about names keeps working unchanged.

- [ ] **Step 1: Write the failing test**

Add to `tools/replay_bot/phases.test.js`, near the existing `sampleAt` tests (the ones using `t.ctx`):

These reuse `ctxWith`/`queuedMatcher`/`readOf`/`Corpus`/`GUID_A`/`skip`,
all already defined earlier in `phases.test.js` for the existing `sampleAt`
tests (search for `function ctxWith` — it builds `{ ctx, matcher, kept,
grabs }` from a real corpus frame path + a queue of canned reads). Same
`{ skip }` conditional the existing `sampleAt` tests use — these need the
real `probe-panelopen-live.png` corpus frame on disk, exactly like their
neighbors, and skip themselves when it's absent (`corpus.js`'s documented
convention).

```js
test('sampleAt reads names alongside heroes when an ocr function is given', { skip }, async () => {
  const frame = Corpus.at('probe-panelopen-live.png');
  const read = readOf(GUID_A);
  const t = ctxWith(frame, [read]);
  const ocr = async () => 'PLATE';
  const s = await P.sampleAt(t.ctx, 60, {
    matcher: t.matcher, stepS: 30, mmss: (x) => String(x), log: () => {},
    prev: read, prevPrev: read, firstOfRound: false, ocr,
  });
  assert.deepStrictEqual(s.names.a, ['PLATE', 'PLATE', 'PLATE', 'PLATE', 'PLATE']);
  assert.deepStrictEqual(s.names.b, ['PLATE', 'PLATE', 'PLATE', 'PLATE', 'PLATE']);
});

test('sampleAt defaults to blank names when no ocr function is given (existing callers unaffected)', { skip }, async () => {
  const frame = Corpus.at('probe-panelopen-live.png');
  const read = readOf(GUID_A);
  const t = ctxWith(frame, [read]);
  const s = await P.sampleAt(t.ctx, 60, {
    matcher: t.matcher, stepS: 30, mmss: (x) => String(x), log: () => {},
    prev: read, prevPrev: read, firstOfRound: false,
  });
  assert.deepStrictEqual(s.names, { a: ['', '', '', '', ''], b: ['', '', '', '', ''] });
});
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `node --test tools/replay_bot/phases.test.js`
Expected: FAIL — `s.names` is `undefined`.

- [ ] **Step 3: Implement in `sampleAt`**

In `tools/replay_bot/phases.js`, inside `sampleAt` (around line 474-497), after `framePath`/`read` are finalized by the retry logic and before the `shouldKeep` check:

```js
    var framePath = ready.path;
    var read = await readHud(io, o.matcher, framePath);

    // ONE SECOND LOOK IF IT LOOKS WRONG. ...
    if (worstOf(read) < LOW_SCORE) {
      var retryPath = await io.grabTo('t' + t + '-again');
      var retry = await readHud(io, o.matcher, retryPath);
      if (worstOf(retry) > worstOf(read)) {
        log('        (first read was mid-transition, took a second look)');
        read = retry;
        framePath = retryPath;
      }
    }

    // Names are read from whichever frame the retry logic above settled on,
    // the same frame the hero read came from - never a second, different
    // grab. Optional: a caller that doesn't pass ocr (existing tests, any
    // path that doesn't need identity) gets blanks, never a crash. See
    // specs/2026-09-17-replay-bot-disconnect-identity-design.md.
    var names = o.ocr ? await readNames(io, o.ocr, framePath) : { a: BLANK_NAMES.slice(), b: BLANK_NAMES.slice() };

    if (shouldKeep(read, o.prev, o.prevPrev, o.firstOfRound)) {
      framePath = io.keepAs ? await io.keepAs('t' + t, framePath) : framePath;
    } else {
      log(mmss(t).padStart(6) + '  unchanged - not kept');
      framePath = null;
    }
    return { t: t, at: at, a: read.a, b: read.b, names: names, framePath: framePath, worst: worstOf(read) };
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `node --test tools/replay_bot/phases.test.js`
Expected: PASS.

- [ ] **Step 5: Run the full replay_bot suite**

Run: `node --test tools/replay_bot/*.test.js`
Expected: PASS, no regressions in the other 4 existing `sampleAt` tests (they don't pass `ocr`, so they get blank names and are otherwise unaffected).

- [ ] **Step 6: Commit**

```bash
git add tools/replay_bot/phases.js tools/replay_bot/phases.test.js
git commit -m "replay-bot: read names alongside heroes in sampleAt"
```

---

## Task 3: Thread names through `capture.captureMap()`'s per-sample loop

**Files:**
- Modify: `tools/replay_bot/capture.js` (around lines 217-231 for the `captureMap` opts, and line 386-395 for the per-sample loop)
- Test: `tools/replay_bot/capture.test.js`

**Interfaces:**
- Consumes: `sampleAt`'s `names` field from Task 2.
- Produces: `captureMap`'s returned `samples[]` array, each entry gains `names: {a:[...5], b:[...5]}` alongside the existing `t`, `at`, `a`, `b`, `framePath`.

- [ ] **Step 1: Write the failing test**

Find the existing test(s) in `tools/replay_bot/capture.test.js` that call `captureMap` and assert on the shape of `got.samples[0]` (search for `captureMap(` and `samples[0]`). Add an assertion to the SAME test (or a new one right next to it, following its exact setup) confirming `names` comes through:

```js
// Extend the existing captureMap sample-shape test (or add immediately
// after it) - names must survive the same round-trip framePath/a/b already do.
assert.deepStrictEqual(got.samples[0].names, { a: ['', '', '', '', ''], b: ['', '', '', '', ''] });
```

(No `ocr` is wired into `captureMap`'s test stub yet — this task only proves `names` survives the round-trip from `sampleAt` into the pushed sample; Task 5 wires a real `ocr` callback in from `run.js`. Blank names round-tripping correctly is the right thing to prove here.)

- [ ] **Step 2: Run the test to verify it fails**

Run: `node --test tools/replay_bot/capture.test.js`
Expected: FAIL — `got.samples[0].names` is `undefined`.

- [ ] **Step 3: Implement in `capture.js`**

Line ~395:

```js
        samples.push({ t: s.t, at: s.at, a: s.a, b: s.b, names: s.names, framePath: s.framePath });
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `node --test tools/replay_bot/capture.test.js`
Expected: PASS.

- [ ] **Step 5: Run the full replay_bot suite**

Run: `node --test tools/replay_bot/*.test.js`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add tools/replay_bot/capture.js tools/replay_bot/capture.test.js
git commit -m "replay-bot: carry per-sample names through captureMap"
```

---

## Task 4: `attribute.js`'s new aggregation function

This is the core of the design (spec §3.2). Read `specs/2026-09-17-replay-bot-disconnect-identity-design.md` §3.2 and §5 in full before starting this task — the algorithm below implements them exactly, including WHY the HIGH/LOW claim priority exists (an earlier draft without it silently drops hero data for any slot whose name is persistently hard to OCR, unrelated to any disconnect — that is a regression this task must not reintroduce).

**Files:**
- Modify: `tools/replay_bot/attribute.js` (replaces `attributeMap`/`make` with the new function; `playersFor`/`rosterNames`/`slotRolesFor` are unchanged)
- Test: `tools/replay_bot/attribute.test.js` (replaces the `attributeMap`-specific tests with new ones for `attributeFromSamples`; `playersFor`/`slotRolesFor` tests are unchanged)

**Interfaces:**
- Consumes: `samples` — an array of `{t, a: [cell x5], b: [cell x5], names: {a:[string x5], b:[string x5]}}`, exactly the shape Task 3 produces (each `cell` is `{name, guid, score}`, the same shape `resolve.rounds()` already consumes per slot). `feed` (has `.hero_roles`, `.lineups`). `code` (has `.match_id`, `.game_no`, `.t1`, `.t2`).
- Produces: `function attributeFromSamples(samples, feed, code)` (SYNCHRONOUS — no OCR calls left to await; they already happened at capture time) returning:
  ```js
  {
    correctedSamples: [{ t, a: [cell x5], b: [cell x5] }, ...],  // same length/order as input samples
    attribution: {
      a: { ids: [id|null x5], conf: [conf|null x5] },
      b: { ids: [id|null x5], conf: [conf|null x5] },
    },
    orientation: 'direct' | 'swapped' | null,
  }
  ```
  `conf` values: `'matched'` for a slot `attributeFromSamples` placed a player_id in — matching the existing convention `resolve.js`/`review/server.js` already read (`'matched'`, `'forced'`, `'operator'`, or `null`); this task only ever produces `'matched'` or `null`.

- [ ] **Step 1: Write the failing tests**

Replace the `attributeMap`-specific tests in `tools/replay_bot/attribute.test.js` (the ones calling `A.make(ocr).attributeMap(...)` — search for `attributeMap` and `A.make`) with the following. Keep the file's existing `playersFor`/`slotRolesFor` tests, and keep the existing `CODE`/`lineupFeed()`/`sampleHeroes()` fixtures exactly as they already are (real content, already in the file — `CODE = { match_id: 'm1', game_no: 1, t1: 'team-a', t2: 'team-b' }`; `lineupFeed()`'s `team-a` roster is Noki/Tank, Vilperttis/Damage, Jøpez/Damage, Lambinen/Support, Karhu/Support; `team-b` is Rawan/Tank, Møøn/Damage, Cat/Damage, Çioüdo/Support, Zayano/Support; `hero_roles` maps guids `tank1`→Tank, `dmg1`/`dmg2`→Damage, `sup1`/`sup2`→Support). Only replace the `attributeMap`-calling tests themselves, with the following.

```js
// ---- attributeFromSamples -------------------------------------------------
//
// specs/2026-09-17-replay-bot-disconnect-identity-design.md. Pure, synchronous,
// no image loading or OCR here - names are already-extracted text by the time
// this runs (phases.readNames, captured once per sample, aggregated here
// across a whole map). Uses the file's existing lineupFeed()/CODE fixtures -
// team-a: Noki(tank1)/Vilperttis(dmg1)/Jøpez(dmg2)/Lambinen(sup1)/Karhu(sup2).
// team-b: Rawan(tank1)/Møøn(dmg1)/Cat(dmg2)/Çioüdo(sup1)/Zayano(sup2).

// One sample's worth of {a, b} hero cells + {a, b} name-OCR strings. `heroes`
// is five [guid, score] pairs per side.
function sample(t, namesA, namesB, heroesA, heroesB) {
  const cell = ([guid, score]) => ({ name: guid, guid, score });
  return {
    t,
    a: heroesA.map(cell), b: heroesB.map(cell),
    names: { a: namesA, b: namesB },
  };
}

const NAMES_A = ['Noki', 'Vilperttis', 'Jøpez', 'Lambinen', 'Karhu'];
const NAMES_B = ['Rawan', 'Møøn', 'Cat', 'Çioüdo', 'Zayano'];
const HEROES = [['tank1', 0.9], ['dmg1', 0.9], ['dmg2', 0.9], ['sup1', 0.9], ['sup2', 0.9]];
const ABSENT_HEROES = [['tank1', 0.9], ['dmg1', 0.9], ['dmg2', 0.9], ['sup1', 0.9], ['ABSENT', null]];

test('attributeFromSamples resolves every slot when nothing ever disconnects', () => {
  const samples = [
    sample(30, NAMES_A, NAMES_B, HEROES, HEROES),
    sample(60, NAMES_A, NAMES_B, HEROES, HEROES),
    sample(90, NAMES_A, NAMES_B, HEROES, HEROES),
  ];
  const out = A.attributeFromSamples(samples, lineupFeed(), CODE);
  assert.strictEqual(out.correctedSamples.length, 3);
  out.correctedSamples.forEach((s) => {
    assert.strictEqual(s.a[0].guid, 'tank1', "slot 0 is Noki's hero");
    assert.strictEqual(s.a[4].guid, 'sup2', "slot 4 is Karhu's hero");
  });
  assert.deepStrictEqual(out.attribution.a.ids, ['a-noki', 'a-vilperttis', 'a-jopez', 'a-lambinen', 'a-karhu']);
});

test('a mid-round disconnect at an interior slot re-keys the shifted samples back to the right canonical slot', () => {
  // Lambinen (slot 3, sup1) disconnects; Karhu (slot 4, sup2) visually
  // compacts into slot 3's position. Position 4 reads nothing. Three
  // "before" samples to one "during" sample, so the canonical vote clearly
  // favors the undisturbed majority (spec §3.2's MODE, not needing >50%,
  // but this keeps the test unambiguous either way).
  const duringNamesA = ['Noki', 'Vilperttis', 'Jøpez', 'Karhu', ''];
  const duringHeroesA = [['tank1', 0.9], ['dmg1', 0.9], ['dmg2', 0.9], ['sup2', 0.9], ['ABSENT', null]];
  const samples = [
    sample(30, NAMES_A, NAMES_B, HEROES, HEROES),
    sample(60, NAMES_A, NAMES_B, HEROES, HEROES),
    sample(90, NAMES_A, NAMES_B, HEROES, HEROES),
    sample(120, duringNamesA, NAMES_B, duringHeroesA, HEROES), // side a only - side b never disconnects
  ];
  const out = A.attributeFromSamples(samples, lineupFeed(), CODE);

  const shiftedA = out.correctedSamples[3].a; // the t=120 sample, side a
  assert.strictEqual(shiftedA[3].guid, 'ABSENT', 'slot 3 (the real leaver, Lambinen) reads absent, not slot 4');
  assert.strictEqual(shiftedA[4].guid, 'sup2', "slot 4's hero read (Karhu) is recovered from visual position 3");
});

test('disconnect at the rightmost slot needs no shift - already correct today, must stay correct', () => {
  const namesGone = ['Noki', 'Vilperttis', 'Jøpez', 'Lambinen', ''];
  const samples = [
    sample(30, NAMES_A, NAMES_B, HEROES, HEROES),
    sample(60, NAMES_A, NAMES_B, HEROES, HEROES),
    sample(90, namesGone, NAMES_B, ABSENT_HEROES, HEROES),
  ];
  const out = A.attributeFromSamples(samples, lineupFeed(), CODE);
  assert.strictEqual(out.correctedSamples[2].a[4].guid, 'ABSENT');
  assert.strictEqual(out.correctedSamples[2].a[3].guid, 'sup1', 'slot 3 (Lambinen) unaffected, no shift needed');
});

test('a 4-slot shift (slot 0 disconnects) re-keys all four downstream slots', () => {
  // Noki (slot 0, tank1) disconnects - Vilperttis/Jøpez/Lambinen/Karhu all
  // compact one slot to the left; position 4 reads nothing.
  const duringNamesA = ['Vilperttis', 'Jøpez', 'Lambinen', 'Karhu', ''];
  const duringHeroesA = [['dmg1', 0.9], ['dmg2', 0.9], ['sup1', 0.9], ['sup2', 0.9], ['ABSENT', null]];
  const samples = [
    sample(30, NAMES_A, NAMES_B, HEROES, HEROES),
    sample(60, NAMES_A, NAMES_B, HEROES, HEROES),
    sample(90, NAMES_A, NAMES_B, HEROES, HEROES),
    sample(120, duringNamesA, NAMES_B, duringHeroesA, HEROES),
  ];
  const out = A.attributeFromSamples(samples, lineupFeed(), CODE);
  const shifted = out.correctedSamples[3].a;
  assert.strictEqual(shifted[0].guid, 'ABSENT', 'Noki genuinely gone');
  assert.strictEqual(shifted[1].guid, 'dmg1', "Vilperttis' hero recovered into slot 1");
  assert.strictEqual(shifted[2].guid, 'dmg2', "Jøpez' hero recovered into slot 2");
  assert.strictEqual(shifted[3].guid, 'sup1', "Lambinen's hero recovered into slot 3");
  assert.strictEqual(shifted[4].guid, 'sup2', "Karhu's hero recovered into slot 4");
});

test('reconnection: samples after the return match the original canonical slot again', () => {
  const duringNamesA = ['Noki', 'Vilperttis', 'Jøpez', 'Karhu', ''];
  const duringHeroesA = [['tank1', 0.9], ['dmg1', 0.9], ['dmg2', 0.9], ['sup2', 0.9], ['ABSENT', null]];
  const samples = [
    sample(30, NAMES_A, NAMES_B, HEROES, HEROES),
    sample(60, NAMES_A, NAMES_B, HEROES, HEROES),
    sample(90, duringNamesA, NAMES_B, duringHeroesA, HEROES),  // Lambinen disconnects
    sample(120, NAMES_A, NAMES_B, HEROES, HEROES),             // reconnected
    sample(150, NAMES_A, NAMES_B, HEROES, HEROES),
  ];
  const out = A.attributeFromSamples(samples, lineupFeed(), CODE);
  assert.strictEqual(out.correctedSamples[3].a[3].guid, 'sup1', "back to Lambinen's hero after reconnecting");
  assert.strictEqual(out.correctedSamples[3].a[4].guid, 'sup2', "Karhu correctly back in her own slot too");
});

test('a name illegible on EVERY sample, unrelated to any disconnect, does not lose hero data', () => {
  // Vilperttis' name (slot 1) never OCRs to anything usable - persistently
  // bad plate, nothing to do with a disconnect. The hero read must survive.
  const namesA = ['Noki', '', 'Jøpez', 'Lambinen', 'Karhu'];
  const samples = [
    sample(30, namesA, NAMES_B, HEROES, HEROES),
    sample(60, namesA, NAMES_B, HEROES, HEROES),
  ];
  const out = A.attributeFromSamples(samples, lineupFeed(), CODE);
  assert.strictEqual(out.correctedSamples[0].a[1].guid, 'dmg1', 'hero data survives even though the name never resolved');
  assert.strictEqual(out.attribution.a.ids[1], null, 'attribution correctly stays unresolved for this slot');
});
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `node --test tools/replay_bot/attribute.test.js`
Expected: FAIL — `A.attributeFromSamples is not a function`.

- [ ] **Step 3: Implement `attributeFromSamples` in `tools/replay_bot/attribute.js`**

Replace the `make(ocr)`/`attributeMap` function with this. `playersFor`, `slotRolesFor`, `rosterNames` stay exactly as they are. Remove the `calib`/`Nameplate` requires at the top of the file — this function no longer touches images or pixels at all, only the already-OCR'd `samples[].names`.

```js
  var Assign = require('../../docs/capture/engine/assign.js');
  var Names = require('../../docs/capture/engine/names.js');
  // calib/Nameplate requires REMOVED - no image access left in this file.

  var SIDES = ['a', 'b'];
  var BLANK_READS = ['', '', '', '', ''];

  function playersFor(feed, code, side) { /* UNCHANGED - keep exactly as-is */ }
  function slotRolesFor(heroRoles, reads) { /* UNCHANGED - keep exactly as-is */ }
  function rosterNames(players) { /* UNCHANGED - keep exactly as-is */ }

  // Every sample's per-side {ids, conf} from Assign.assign, run once per
  // sample instead of once per map (same call attributeMap always made,
  // just made more often - see design doc §4).
  function perSampleAssign(samples, leftTeam, rightTeam, heroRoles) {
    return samples.map(function (s) {
      var namesA = (s.names && s.names.a) || BLANK_READS;
      var namesB = (s.names && s.names.b) || BLANK_READS;
      return {
        a: Assign.assign(namesA, leftTeam, slotRolesFor(heroRoles, s.a)),
        b: Assign.assign(namesB, rightTeam, slotRolesFor(heroRoles, s.b)),
      };
    });
  }

  // Step A (design doc §3.2): the MODE player_id assign() placed at each
  // VISUAL position, across every sample - that player's canonical slot.
  // Ties broken by player_id string order, so two runs over the same
  // samples never disagree (the same convention resolve.js's runnerUp uses).
  function canonicalSlotsFor(assigned, side) {
    var counts = [{}, {}, {}, {}, {}]; // counts[visualPos][playerId] = n
    assigned.forEach(function (a) {
      a[side].ids.forEach(function (id, pos) {
        if (!id) return;
        counts[pos][id] = (counts[pos][id] || 0) + 1;
      });
    });
    var canonicalSlotOf = {}; // playerId -> slot
    for (var pos = 0; pos < 5; pos++) {
      var best = null, bestN = -1;
      Object.keys(counts[pos]).sort().forEach(function (id) {
        if (counts[pos][id] > bestN) { bestN = counts[pos][id]; best = id; }
      });
      if (best !== null) canonicalSlotOf[best] = pos;
    }
    return canonicalSlotOf;
  }

  // Step B (design doc §3.2): re-key one sample's hero cells from visual
  // position into canonical slot order. A HIGH claim (assign() confidently
  // placed a player this sample, and that player has an established
  // canonical slot) always wins over a LOW claim (default: this position's
  // read belongs to its own slot index, unchanged) for the same target
  // slot. This is what makes an unclear/illegible name degrade to "no
  // change" rather than "hero data lost" - see the design doc's regression
  // note in §3.2.
  var ABSENT_CELL = { name: null, guid: 'ABSENT', score: null };
  function rekeySample(rawCells, sampleIds, canonicalSlotOf) {
    var high = [null, null, null, null, null];
    var low = [null, null, null, null, null];
    for (var pos = 0; pos < 5; pos++) {
      var id = sampleIds[pos];
      var target = id && canonicalSlotOf[id] !== undefined ? canonicalSlotOf[id] : null;
      if (target !== null) high[target] = rawCells[pos];
      else low[pos] = rawCells[pos];
    }
    var out = [];
    for (var slot = 0; slot < 5; slot++) {
      out.push(high[slot] || low[slot] || ABSENT_CELL);
    }
    return out;
  }

  function attributeFromSamples(samples, feed, code) {
    var heroRoles = feed.hero_roles || {};
    var t1 = playersFor(feed, code, 'a');
    var t2 = playersFor(feed, code, 'b');

    if (!samples.length) {
      return {
        correctedSamples: [],
        attribution: {
          a: { ids: BLANK_READS.map(function () { return null; }), conf: BLANK_READS.map(function () { return null; }) },
          b: { ids: BLANK_READS.map(function () { return null; }), conf: BLANK_READS.map(function () { return null; }) },
        },
        orientation: null,
      };
    }

    // Orientation: the mode of every sample's own confidentOrientation call
    // - still a once-per-map fact (a screen-side swap can't change mid-map),
    // just decided from every sample instead of one frame.
    var orientVotes = {};
    samples.forEach(function (s) {
      var namesA = (s.names && s.names.a) || BLANK_READS;
      var namesB = (s.names && s.names.b) || BLANK_READS;
      var o = Names.confidentOrientation(namesA, namesB, rosterNames(t1), rosterNames(t2));
      if (o) orientVotes[o] = (orientVotes[o] || 0) + 1;
    });
    var orient = null, orientN = -1;
    Object.keys(orientVotes).sort().forEach(function (o) {
      if (orientVotes[o] > orientN) { orientN = orientVotes[o]; orient = o; }
    });
    var swapped = orient === 'b';
    var leftTeam = swapped ? t2 : t1;
    var rightTeam = swapped ? t1 : t2;

    var assigned = perSampleAssign(samples, leftTeam, rightTeam, heroRoles);
    var canonicalSlotOf = { a: canonicalSlotsFor(assigned, 'a'), b: canonicalSlotsFor(assigned, 'b') };

    var correctedSamples = samples.map(function (s, i) {
      return {
        t: s.t,
        a: rekeySample(s.a, assigned[i].a.ids, canonicalSlotOf.a),
        b: rekeySample(s.b, assigned[i].b.ids, canonicalSlotOf.b),
      };
    });

    var attribution = { a: { ids: [null, null, null, null, null], conf: [null, null, null, null, null] },
                         b: { ids: [null, null, null, null, null], conf: [null, null, null, null, null] } };
    SIDES.forEach(function (side) {
      Object.keys(canonicalSlotOf[side]).forEach(function (id) {
        var slot = canonicalSlotOf[side][id];
        attribution[side].ids[slot] = id;
        attribution[side].conf[slot] = 'matched';
      });
    });

    return {
      correctedSamples: correctedSamples,
      attribution: attribution,
      orientation: orient === null ? null : (swapped ? 'swapped' : 'direct'),
    };
  }

  var Mod = {
    attributeFromSamples: attributeFromSamples,
    playersFor: playersFor, slotRolesFor: slotRolesFor, rosterNames: rosterNames,
  };
```

Note `ABSENT_CELL`'s guid `'ABSENT'` matches `resolve.js`'s own `ABSENT_GUID` constant value (restated here for the same reason `resolve.js` restates it rather than requiring `phases.js` — see `resolve.js`'s own comment on `ABSENT_GUID` for the precedent).

- [ ] **Step 4: Run the tests to verify they pass**

Run: `node --test tools/replay_bot/attribute.test.js`
Expected: PASS, all tests including the 6 new ones.

- [ ] **Step 5: Run the full replay_bot suite**

Run: `node --test tools/replay_bot/*.test.js tools/replay_bot/review/*.test.js`
Expected: PASS. `review_out.test.js`/`review/server.test.js` don't call `attribute.js` directly (they consume already-resolved `rounds`), so this should not touch them - if anything fails here, it means something else imports `attribute.js`'s old `make`/`attributeMap` and needs updating (check with `grep -rn "attribute.js\|A\.make\|attributeMap" tools/replay_bot/*.js tools/replay_bot/review/*.js` before moving on).

- [ ] **Step 6: Commit**

```bash
git add tools/replay_bot/attribute.js tools/replay_bot/attribute.test.js
git commit -m "replay-bot: attribute.js resolves identity from every sample, not one frame"
```

---

## Task 5: Wire the new aggregation into `run.js`

**Files:**
- Modify: `tools/replay_bot/run.js` (the `attributor`/`A.make` setup around line 646, and the attribution call site around lines 889-910; the `captureMap` call around line 866; wherever `resolve.rounds()` is called with `got.samples`)
- Test: none new (this task is wiring; Task 4's tests already cover the aggregation logic itself; verify with a manual/integration smoke check per Step 4 below, not a new automated test)

**Interfaces:**
- Consumes: `A.attributeFromSamples(samples, feed, code)` from Task 4; `phases.sampleAt`'s `ocr`-aware `names` field from Task 2 (via `captureMap`, Task 3).
- Produces: `run.js`'s per-map flow now calls `resolve.rounds()` with `attribution.correctedSamples` instead of the raw `got.samples`, and uses `attribution.attribution`/`attribution.orientation` exactly where the old `attribution`/`attribution.orientation` variables were used.

- [ ] **Step 1: Find every current use of the old attribution flow**

Run: `grep -n "attributor\|attributeMap\|attribution\." tools/replay_bot/run.js`

Confirm the call sites this task must change: the `A.make(...)` setup (~line 646), the "first 4 samples" loop (~lines 889-910), and wherever `resolve.rounds(got.samples, ...)` or similar is called later using `got.samples` and the `attribution` variable this loop produced.

- [ ] **Step 2: Remove the old `attributor`/`A.make` setup**

Around line 646, remove:

```js
  const attributor = A.make(async (cv) => {
    const { data } = await ocrWorker.recognize(cv.toBuffer('image/png'));
    return data.text.trim();
  });
```

Keep the underlying `async (cv) => { const {data} = await ocrWorker.recognize(...); return data.text.trim(); }` function itself — it's still needed, just passed to `captureMap` now instead of `A.make`. Save it to a named variable, e.g. `const ocrPlate = async (cv) => { ... };`, declared once near where `ocrWorker` itself is created (it needs `ocrWorker` to already exist, so it must come after the `ocrWorker = await Tesseract.createWorker(...)` block).

- [ ] **Step 3: Pass `ocrPlate` into `captureMap` and replace the old attribution loop**

Around line 866, add `ocr: ocrPlate` to the `captureMap` call:

```js
      const got = await capture.captureMap({
        stepS: sessionStepS, afterViewer: setInterval,
        sampleQuiesceMs: args.sampleQuiesce,
        noDrag: args.noDrag,
        ocr: ocrPlate,
      });
```

Replace the entire "first 4 samples, pick the one with the most assigned slots" block (~lines 877-912ish — read the surrounding code to find its exact end, likely where `attribution` is finally settled and logged) with:

```js
      // Resolved from EVERY sample, not one frame - specs/2026-09-17-
      // replay-bot-disconnect-identity-design.md. A disconnect landing on
      // whichever frame used to be picked here could corrupt attribution
      // for the whole map; this can't happen once every sample votes.
      const identity = A.attributeFromSamples(got.samples, feed, code);
      const attribution = identity; // orientation/attribution/correctedSamples all live on this object now
```

- [ ] **Step 4: Update every downstream use of `got.samples` and the old `attribution` shape**

Find where `resolve.rounds(...)` is called for this map (search `resolve.rounds(` or `R.rounds(` in `run.js`) and change its first argument from `got.samples` to `identity.correctedSamples`. Find wherever `attribution.a`/`attribution.b`/`attribution.orientation` (or similarly-named fields) are read afterward (for `resolve.rounds`'s `opts.attribution`, for side-swap relabeling using `orientation`, for anything `review_out.js`/`emit.js` receive from `run.js`'s per-map result) and confirm they now read `identity.attribution.a`/`identity.attribution.b`/`identity.orientation` — same field names as the old `attribution` object had (`{a, b, orientation}`), so most of these call sites should need no further change beyond the rename from `attribution` to `identity` if you kept the old variable name, or nothing at all if you named the new object `attribution` as shown in Step 3.

- [ ] **Step 5: Manual smoke check (no automated test for this wiring task)**

Run a short, real capture against a live client with at least one already-imported replay code (per this repo's existing manual-testing convention — see `AGENTS.md`/`PLANS.md` for how a single-map manual run is normally done) and confirm:
- The run completes without throwing.
- The produced `.review.json`'s `rounds[].a/b[]` entries look sane (real guids, not all `ABSENT`).
- `attribution` (player_id per slot) is populated for a normal map with no disconnects.

This task is pure wiring with no new logic of its own (Task 4 already proved the aggregation algorithm correct in isolation) - a real end-to-end run is the appropriate check here, not a new unit test.

- [ ] **Step 6: Run the full test suite one more time**

Run: `node --test tools/replay_bot/*.test.js tools/replay_bot/review/*.test.js docs/capture/engine/*.test.js`
Expected: PASS, full count, no regressions anywhere in the repo.

- [ ] **Step 7: Commit**

```bash
git add tools/replay_bot/run.js
git commit -m "replay-bot: wire per-sample identity resolution into the capture loop"
```

---

## Post-implementation

- Update `PLANS.md`'s Replay bot section: mark the disconnect slot-shift item (P2) as fixed, referencing the design doc and this plan.
- Update `CHANGELOG.md` with a `### Fixed` entry summarizing the fix, matching this session's established style (see the `cross-role-swap`/`takeover-frame`/`DEAD_GUID` entries already in `CHANGELOG.md` under `## 2026-09-17` for the exact tone/format to match).
- Update `ARCHITECTURE.md`'s replay-bot section (§14, or wherever the attribution design is currently documented) to describe the new per-sample identity flow, replacing any remaining description of the old single-frame `attributeMap` approach.

const test = require('node:test');
const assert = require('node:assert');
const canvas = require('@napi-rs/canvas');
const P = require('./phases.js');
const Corpus = require('./corpus.js');
const calib = require('./calib.js');

const skip = Corpus.absent() || false;

// The composite phases - openEventsViewer, calibrateBar, ensurePanelOpen - are
// exercised end to end by capture.offline.test.js against recorded frames (the
// N/K ordering, the "would not open" and "forward key is not working" refusals).
// These cover the pieces that are unit-testable without a frame.

test('worstOf returns the least confident cell across both sides', () => {
  const read = {
    a: [{ score: 0.9 }, { score: 0.72 }, { score: 0.95 }],
    b: [{ score: 0.81 }, { score: 0.44 }, { score: 0.88 }],
  };
  assert.strictEqual(P.worstOf(read), 0.44);
});

test('worstOf is 1 for an empty read', () => {
  assert.strictEqual(P.worstOf({ a: [], b: [] }), 1);
});

// deriveDuration: measured off the bar span unless the caller was told one.
test('deriveDuration measures off the bar span with a playback rate', () => {
  const ref = { stepPx: 100, stepS: 20 };
  const d = P.deriveDuration({ ref, pxPerSec: 5, atZeroWidth: 40, told: null });
  // span = (x1 - x0 + 1 - 40) / 5 ; both `duration` and `implied` are that.
  assert.strictEqual(d.duration, d.implied);
  assert.ok(d.duration > 0);
});

test('deriveDuration falls back to stepPx/stepS without a rate', () => {
  const ref = { stepPx: 100, stepS: 20 };
  const withRate = P.deriveDuration({ ref, pxPerSec: 8.5, atZeroWidth: 40, told: null });
  const noRate = P.deriveDuration({ ref, pxPerSec: null, atZeroWidth: 40, told: null });
  assert.notStrictEqual(withRate.implied, noRate.implied);
  assert.ok(noRate.implied > 0);
});

test('deriveDuration keeps a told duration but still reports what the bar implied', () => {
  const ref = { stepPx: 100, stepS: 20 };
  const d = P.deriveDuration({ ref, pxPerSec: 5, atZeroWidth: 40, told: 999 });
  assert.strictEqual(d.duration, 999);
  assert.notStrictEqual(d.implied, 999);
});

// sampleAt: a seek that lands more than half a step off `t` is dropped, not
// labelled with a time it was never at. (The "still loading" drop needs a real
// frame for readyFrame's HUD check - capture.offline.test.js covers that path.)
test('sampleAt drops a seek that could not be corrected', async () => {
  const drv = { seekTo: async () => 130 };            // asked for 100, landed at 130
  const logs = [];
  const s = await P.sampleAt({ io: {}, drv }, 100,
    { stepS: 20, mmss: (x) => String(x), log: (l) => logs.push(l) });
  assert.strictEqual(s.missed, true);
  assert.strictEqual(s.reason, 'seek');
  assert.ok(logs.some((l) => /MISSED/.test(l)));
});

test('sampleAt keeps a seek that lands within half a step', async () => {
  // lands at 108 for a target of 100, step 20 -> |8| < 10, not a miss. It then
  // goes on to readyFrame, which needs a real frame, so this only checks the
  // miss gate did not fire early.
  const drv = { seekTo: async () => 108 };
  const io = { lastFrame: () => null, grabTo: async () => { throw new Error('stop here'); } };
  await assert.rejects(
    P.sampleAt({ io, drv }, 100, { stepS: 20, mmss: (x) => String(x), log: () => {} }),
    /stop here/, 'got past the miss gate to the frame grab');
});

// ---- change-detection retention (shouldKeep) ------------------------------
//
// Storage is bounded by distinct comp states, not by how often we visit: a
// sample earns its keep by differing from the previous one. These are the four
// ways a frame can earn it, plus the one way it cannot.

const GUID_A = ['noki', 'vilp', 'jopez', 'lamb', 'karhu'];
const GUID_B = ['noki', 'vilp', 'SWAP', 'lamb', 'karhu'];

function readOf(guids, score) {
  const s = (score === undefined) ? 0.9 : score;
  const side = (gs) => gs.map((g) => ({ name: g, guid: g, score: s }));
  return { a: side(guids), b: side(guids) };
}

test('shouldKeep: the first sample of a round is always kept', () => {
  const r = readOf(GUID_A);
  assert.strictEqual(P.shouldKeep(r, r, r, true), true);
});

test('shouldKeep: a sample with no predecessor is always kept', () => {
  const r = readOf(GUID_A);
  assert.strictEqual(P.shouldKeep(r, null, null, false), true);
});

test('shouldKeep: a moved hero guid is a change', () => {
  assert.strictEqual(P.shouldKeep(readOf(GUID_B), readOf(GUID_A), readOf(GUID_A), false), true);
});

test('shouldKeep: a read below LOW_SCORE is not confidently identical', () => {
  const low = readOf(GUID_A, P.LOW_SCORE - 0.1);
  assert.strictEqual(P.shouldKeep(low, readOf(GUID_A), readOf(GUID_A), false), true);
});

test('shouldKeep: a previous sample that disagreed with the one before it keeps', () => {
  // prev differs from prevPrev -> a swap is in progress, keep every frame.
  assert.strictEqual(P.shouldKeep(readOf(GUID_A), readOf(GUID_B), readOf(GUID_A), false), true);
});

test('shouldKeep: an identical, confident, settled read is not kept', () => {
  const r = readOf(GUID_A);
  assert.strictEqual(P.shouldKeep(r, r, r, false), false);
  // and with no prevPrev at all (the second sample of a round)
  assert.strictEqual(P.shouldKeep(r, r, null, false), false);
});

// ---- sampleAt: read-before-keep wiring ------------------------------------

// A matcher that serves one read per readHud call. readHud asks for side 'a'
// (five slots) then side 'b' (five slots) - ten match calls per read - so each
// queue entry is consumed exactly once and its per-slot results come out in
// order.
function queuedMatcher(reads) {
  let calls = 0;
  return {
    match: (crop, side) => {
      const r = reads[Math.floor(calls / 10)];
      const slot = calls % 5;
      calls++;
      return r[side][slot];
    },
  };
}

// sampleAt needs a real, HUD-present frame to read. The corpus frame is only
// there to satisfy readyFrame/readHud; the reads come from the stub matcher, so
// these tests are about the keep decision, not the OCR.
function ctxWith(framePath, reads) {
  const kept = [];
  const grabs = [];
  const io = {
    lastFrame: () => framePath,
    loadImage: (p) => canvas.loadImage(p),
    grabTo: async (tag) => { grabs.push(tag); return framePath; },
    keepAs: async (tag, src) => { kept.push({ tag, src }); return src; },
  };
  return { ctx: { io, drv: { seekTo: async (t) => t } }, matcher: queuedMatcher(reads), kept, grabs };
}

test('sampleAt: an unchanged, confident read keeps no frame and returns null', { skip }, async () => {
  const frame = Corpus.at('probe-panelopen-live.png');
  const read = readOf(GUID_A);
  const t = ctxWith(frame, [read]);
  const s = await P.sampleAt(t.ctx, 60, {
    matcher: t.matcher, stepS: 30, mmss: (x) => String(x), log: () => {},
    prev: read, prevPrev: read, firstOfRound: false,
  });
  assert.strictEqual(s.framePath, null, 'nothing changed, nothing stored');
  assert.strictEqual(t.kept.length, 0, 'keepAs was never called');
});

test('sampleAt: the first sample of a round is kept even when unchanged', { skip }, async () => {
  const frame = Corpus.at('probe-panelopen-live.png');
  const read = readOf(GUID_A);
  const t = ctxWith(frame, [read]);
  const s = await P.sampleAt(t.ctx, 60, {
    matcher: t.matcher, stepS: 30, mmss: (x) => String(x), log: () => {},
    prev: read, prevPrev: read, firstOfRound: true,
  });
  assert.strictEqual(s.framePath, frame, 'the round baseline frame is kept');
  assert.strictEqual(t.kept.length, 1);
  assert.strictEqual(t.kept[0].tag, 't60');
});

test('sampleAt: the retry runs before the keep decision, and a recovered same comp is dropped', { skip }, async () => {
  // First read is mid-transition (low score), the second look recovers to the
  // SAME comp as the previous sample. If the decision used the first read the
  // low score would have kept it; using the retry it is correctly not stored.
  const frame = Corpus.at('probe-panelopen-live.png');
  const low = readOf(GUID_A, P.LOW_SCORE - 0.2);
  const recovered = readOf(GUID_A, 0.9);
  const logs = [];
  const t = ctxWith(frame, [low, recovered]);
  const s = await P.sampleAt(t.ctx, 60, {
    matcher: t.matcher, stepS: 30, mmss: (x) => String(x), log: (l) => logs.push(l),
    prev: readOf(GUID_A), prevPrev: readOf(GUID_A), firstOfRound: false,
  });
  assert.strictEqual(t.grabs.length, 1, 'the one-second look fired');
  assert.strictEqual(s.worst, 0.9, 'the recovered read is the one reported');
  assert.strictEqual(s.framePath, null, 'recovered to the same comp -> not stored');
  assert.ok(logs.some((l) => /second look/.test(l)));
});

test('sampleAt: the retry frame is what a change keeps', { skip }, async () => {
  const frame = Corpus.at('probe-panelopen-live.png');
  const low = readOf(GUID_A, P.LOW_SCORE - 0.2);
  const swap = readOf(GUID_B, 0.9);
  const t = ctxWith(frame, [low, swap]);
  const s = await P.sampleAt(t.ctx, 60, {
    matcher: t.matcher, stepS: 30, mmss: (x) => String(x), log: () => {},
    prev: readOf(GUID_A), prevPrev: readOf(GUID_A), firstOfRound: false,
  });
  assert.strictEqual(s.framePath, frame, 'kept, on the retry');
  assert.strictEqual(t.kept.length, 1);
  assert.strictEqual(t.kept[0].src, frame, 'keepAs was handed the retry frame');
  assert.strictEqual(s.a[2].guid, 'SWAP', 'the retry read is the one returned');
});

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

// ---- readHud: a leaver's slot is never handed to the matcher --------------
//
// A disconnected player's card leaves the HUD outright - the cell is exposed
// scenery, not a portrait of the wrong hero - so matching it against the
// hero library is both pointless and risky (scenery scores low against
// everything, but not reliably below every real hero's floor). readHud must
// recognise the cell as absent from its own pixels, via crop.cellTint, before
// it ever reaches the matcher.

// A frame built at the real FROZEN geometry with every slot given its own
// solid colour, one HUD colour per side plus per-slot overrides - the same
// approach crop.test.js uses to exercise cellTint against real geometry.
function frameWithSlots(overrides) {
  const f = calib.FROZEN.frame;
  const cv = canvas.createCanvas(f.w, f.h);
  const cx = cv.getContext('2d');
  cx.fillStyle = '#000000';
  cx.fillRect(0, 0, f.w, f.h);
  const base = { a: '#1040a0', b: '#a01010' };
  ['a', 'b'].forEach((side) => {
    calib.slots(side).forEach((rect, i) => {
      const o = overrides && overrides[side] && overrides[side][i];
      cx.fillStyle = o || base[side];
      cx.fillRect(rect.x, rect.y, rect.w, rect.h);
    });
  });
  return cv;
}

test('readHud marks an untinted slot ABSENT without calling the matcher', async () => {
  const img = frameWithSlots({ a: { 3: '#808080' } });
  const io = { loadImage: async () => img };
  let calls = { a: 0, b: 0 };
  const matcher = {
    match: (crop, side) => {
      calls[side]++;
      return { score: 0.9, name: 'SomeHero', guid: '0xABC' };
    },
  };
  const read = await P.readHud(io, matcher, 'unused-path');
  assert.strictEqual(read.a[3].guid, 'ABSENT');
  assert.strictEqual(read.a[3].score, null);
  assert.strictEqual(calls.a, 4, 'the matcher was asked about the four present side-a slots only');
  assert.strictEqual(calls.b, 5, 'side b had no absent slots');
});

// ---- readHud: a dead-but-present slot reads DEAD, not ABSENT --------------
//
// 2026-09-17: a death desaturates the WHOLE card (badge included), so
// cellTint alone cannot tell it from a real disconnect - confirmed against
// real captures (P1PXQK, H5Q9WE) and by the operator directly ("the X means
// a player is dead"). readHud must ask crop.cellDeath before concluding
// ABSENT, and never hand a dead (desaturated, unreadable) portrait to the
// matcher either - same reasoning as ABSENT, different sentinel so
// resolve.js can treat it as "no evidence this sample", not "this player
// left".

test('readHud marks a dead-but-present slot DEAD, not ABSENT, and never asks the matcher', async () => {
  const img = frameWithSlots({ a: { 3: '#808080' } });
  const cx = img.getContext('2d');
  const mark = calib.deathMarker('a')[3];
  cx.fillStyle = 'rgb(216,34,80)'; // the X's own measured colour
  cx.fillRect(mark.x, mark.y, mark.w, mark.h);
  const io = { loadImage: async () => img };
  const calls = { a: 0, b: 0 };
  const matcher = {
    match: (crop, side) => { calls[side]++; return { score: 0.9, name: 'SomeHero', guid: '0xABC' }; },
  };
  const read = await P.readHud(io, matcher, 'unused-path');
  assert.strictEqual(read.a[3].guid, 'DEAD');
  assert.strictEqual(read.a[3].score, null);
  assert.strictEqual(calls.a, 4, 'the matcher was never asked about the dead slot');
});

test('readHud still matches every present slot normally', async () => {
  const img = frameWithSlots({ a: { 3: '#808080' } });
  const io = { loadImage: async () => img };
  const matcher = { match: () => ({ score: 0.9, name: 'SomeHero', guid: '0xABC' }) };
  const read = await P.readHud(io, matcher, 'unused-path');
  [0, 1, 2, 4].forEach((i) => assert.strictEqual(read.a[i].guid, '0xABC', 'slot ' + i + ' still matched'));
  read.b.forEach((c, i) => assert.strictEqual(c.guid, '0xABC', 'side b slot ' + i + ' still matched'));
});

// ---- readNames: per-sample name OCR, mirrors readHud's shape -------------
//
// 2026-09-17: the disconnect slot-shift design (specs/2026-09-17-replay-bot-
// disconnect-identity-design.md) needs per-sample name identity, not the
// once-per-map single frame attribute.js reads today. readNames is the new
// per-sample read; a later task teaches attribute.js to use it aggregated
// across a whole map. This task only adds the read itself.

// findNameRow needs real glyph-like light/dark transitions (see frames.js's
// own comment on it) - frameWithSlots' flat colour fills legitimately find
// no row, same as the "falls back to five blanks" test below. So the happy
// path is exercised against a real corpus frame, same convention as
// nameplate.test.js's 'nameRow finds a band under the portraits' and
// attribute.test.js's real-frame tests.
test('readNames OCRs all 10 name crops, five per side, in slot order', { skip }, async () => {
  const witness = Corpus.NAMEPLATES[0];
  const img = await canvas.loadImage(Corpus.at(witness.file));
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

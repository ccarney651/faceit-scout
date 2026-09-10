const test = require('node:test');
const assert = require('node:assert');
const P = require('./phases.js');

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

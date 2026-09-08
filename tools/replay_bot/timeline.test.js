const test = require('node:test');
const assert = require('node:assert');
const T = require('./timeline.js');

// `flags[i]` is true where the bar reads as a between-round break.
function flags(spec) {
  // "PPPBBBPPP" -> play/break per pixel, one char each
  return spec.split('').map((c) => c === 'B');
}

const OPTS = { x0: 0, duration: 90, minRun: 2 };

test('a bar with no breaks is one play segment', () => {
  const got = T.segments(flags('PPPPPPPPP'), OPTS);
  assert.strictEqual(got.length, 1);
  assert.strictEqual(got[0].play, true);
});

test('a break splits the bar into two play segments', () => {
  const got = T.segments(flags('PPPPBBPPPP'), OPTS).filter((s) => s.play);
  assert.strictEqual(got.length, 2);
});

test('segment edges convert to seconds across the bar', () => {
  // 10 px spanning 90s: each pixel is 9s.
  const got = T.segments(flags('PPPPPBBBBB'), { x0: 0, duration: 90, minRun: 2 });
  assert.strictEqual(got[0].from, 0);
  assert.ok(Math.abs(got[0].to - 45) < 5, `play should end near 45s, got ${got[0].to}`);
});

// The playhead knob and the event ticks are a few pixels wide and read as
// stray runs. Treating one as a round break would invent a boundary that is
// not there and cut a round in half.
test('a run too short to be a break is absorbed', () => {
  const got = T.segments(flags('PPPPBPPPP'), { x0: 0, duration: 90, minRun: 3 });
  assert.strictEqual(got.filter((s) => s.play).length, 1, 'one stray pixel is not a break');
});

test('a run at the minimum length still counts', () => {
  const got = T.segments(flags('PPPBBBPPP'), { x0: 0, duration: 90, minRun: 3 });
  assert.strictEqual(got.filter((s) => s.play).length, 2);
});

// Sampling plan. Points sit inside the segment, never on its edges, because a
// round's first and last instants are setup and aftermath - portraits there are
// unreliable or absent.
test('three samples land inside a segment, not on its edges', () => {
  const got = T.plan([{ play: true, from: 0, to: 100 }], 3);
  assert.deepStrictEqual(got, [25, 50, 75]);
});

test('five samples spread evenly for a map with no rounds', () => {
  const got = T.plan([{ play: true, from: 0, to: 60 }], 5);
  assert.deepStrictEqual(got, [10, 20, 30, 40, 50]);
});

test('every play segment is sampled, and breaks are never sampled', () => {
  const segs = [
    { play: true, from: 0, to: 100 },
    { play: false, from: 100, to: 200 },
    { play: true, from: 200, to: 300 },
  ];
  const got = T.plan(segs, 3);
  assert.strictEqual(got.length, 6, 'three per play segment, none for the break');
  assert.ok(got.every((t) => t <= 100 || t >= 200), 'nothing inside the break');
});

// The real measurement from the rig: a 17:42 Control replay whose bar showed
// two blue runs. This is the shape the sampler must produce for it.
test('the measured Control replay yields nine samples across three rounds', () => {
  const segs = [
    { play: true, from: 4, to: 406 },
    { play: false, from: 406, to: 526 },
    { play: true, from: 527, to: 743 },
    { play: false, from: 744, to: 805 },
    { play: true, from: 805, to: 1062 },
  ];
  const got = T.plan(segs, 3);
  assert.strictEqual(got.length, 9);
  assert.ok(got.every((t) => t > 0 && t < 1062));
});

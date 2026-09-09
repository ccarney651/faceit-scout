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

// Seeking is done by jumping to the start and pressing REPLAY FORWARD (X),
// which moves in fixed 20s steps. Snapping the plan to that grid makes every
// seek an exact number of keypresses - no scrubber dragging, and no drift from
// accumulated approximate seeks.
test('samples snap to the 20s grid the forward key actually moves in', () => {
  const got = T.plan([{ play: true, from: 0, to: 400 }], 3, { stepS: 20 });
  assert.deepStrictEqual(got, [100, 200, 300]);
  got.forEach((t) => assert.strictEqual(t % 20, 0, `${t} is not on the grid`));
});

// Unsnapped thirds of 0-50 are 12.5/25/37.5 - not one of them on the grid, so
// this fails loudly if snapping is absent rather than passing by luck.
test('samples off the grid are pulled onto it', () => {
  const got = T.plan([{ play: true, from: 0, to: 50 }], 3, { stepS: 20 });
  got.forEach((t) => assert.strictEqual(t % 20, 0, `${t} is not on the 20s grid`));
  got.forEach((t) => assert.ok(t >= 0 && t <= 50, `${t} escaped 0-50`));
});

// 100-115 contains exactly one grid point, 100. Thirds would be 103.75/107.5/
// 111.25, none of them reachable by keypress.
test('a segment shorter than one step collapses to the grid points it contains', () => {
  const got = T.plan([{ play: true, from: 100, to: 115 }], 3, { stepS: 20 });
  assert.ok(got.length >= 1, 'a short segment must not vanish');
  got.forEach((t) => assert.strictEqual(t % 20, 0, `${t} is not reachable`));
  got.forEach((t) => assert.ok(t >= 100 && t <= 115, `${t} escaped 100-115`));
});

// Thirds of 0-45 are 11.25/22.5/33.75, which snap to 20/20/40 - a duplicate.
// Two seeks to the same instant is a wasted 800ms grab of an identical frame.
test('snapping never produces the same instant twice', () => {
  const got = T.plan([{ play: true, from: 0, to: 45 }], 3, { stepS: 20 });
  assert.strictEqual(new Set(got).size, got.length, 'duplicate seeks waste a grab');
});

test('without a step, samples stay exactly where they fall', () => {
  const got = T.plan([{ play: true, from: 0, to: 50 }], 3);
  assert.deepStrictEqual(got, [12.5, 25, 37.5]);
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

// --- setup blips are not rounds -------------------------------------------
//
// Every map opens with a few seconds of "play" before the round proper. With a
// 60-second step the nearest reachable grid point to such a segment is 0:00, so
// the bot sampled the very start of the map - no portraits drawn yet - and read
// ten cells of confident nonsense.

test('a seven-second stretch of play is not a round', () => {
  const got = T.dropShortPlay([
    { from: 10, to: 17, play: true },
    { from: 17, to: 49, play: false },
    { from: 49, to: 299, play: true },
  ], 30);
  assert.deepStrictEqual(got.map((s) => s.play), [false, false, true]);
  assert.strictEqual(got[0].tooShort, true, 'marked, so it can be shown as setup');
});

test('a real round is left alone', () => {
  const got = T.dropShortPlay([{ from: 49, to: 299, play: true }], 30);
  assert.strictEqual(got[0].play, true);
  assert.strictEqual(got[0].tooShort, undefined);
});

test('dropping the blip changes how many samples the map gets', () => {
  const raw = [
    { from: 0, to: 10, play: false },
    { from: 10, to: 17, play: true },
    { from: 17, to: 49, play: false },
    { from: 49, to: 299, play: true },
  ];
  assert.strictEqual(T.samplesFor(raw), 3, 'two play segments looks like rounds');
  assert.strictEqual(T.samplesFor(T.dropShortPlay(raw, 30)), 5,
    'one real segment gets the denser single-segment sampling');
});

test('the plan no longer reaches for 0:00', () => {
  const segs = T.dropShortPlay([
    { from: 7, to: 21, play: true },
    { from: 21, to: 53, play: false },
    { from: 53, to: 555, play: true },
  ], 30);
  const plan = T.plan(segs, T.samplesFor(segs), { stepS: 60 });
  assert.ok(!plan.includes(0), 'sampling the first instant of a map reads no HUD at all');
});

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

// Sampling plan. Points sit on the skip grid the client's forward key can
// actually reach, strictly inside each play segment - a round's first and last
// instants are setup and aftermath, where portraits are unreliable or absent.

test('grid points sit strictly inside a segment, on the skip grid', () => {
  const got = T.planGrid([{ play: true, from: 50, to: 160 }], { stepS: 30 });
  assert.deepStrictEqual(got, [60, 90, 120, 150]);
  got.forEach((t) => assert.strictEqual(t % 30, 0, `${t} is off the 30s grid`));
});

// 45 is a selectable skip interval (the slider goes 5-60s), so the grid must
// plan on it too: points strictly inside the segment, every 45s.
test('the 45s grid plans points strictly inside a segment', () => {
  const got = T.planGrid([{ play: true, from: 50, to: 160 }], { stepS: 45 });
  assert.deepStrictEqual(got, [90, 135]);
  got.forEach((t) => assert.strictEqual(t % 45, 0, `${t} is off the 45s grid`));
  got.forEach((t) => assert.ok(t > 50 && t < 160, `${t} escaped the segment`));
});

// The first sample is the first reachable point after the round's start, not a
// fixed offset into the round: a round starting at 0:52 on a 30s grid is first
// sampled at 1:00, eight seconds in.
test('the first sample is the first reachable grid point after the round start', () => {
  const got = T.planGrid([{ play: true, from: 52, to: 406 }], { stepS: 30 });
  assert.strictEqual(got[0], 60);
  assert.strictEqual(got.length, 12, '60..390 at +30');
});

// A round ending exactly on a grid point must not be sampled at that instant -
// it is the boundary where the portraits are going away.
test('a segment ending on the grid is never sampled on its closing edge', () => {
  const got = T.planGrid([{ play: true, from: 40, to: 120 }], { stepS: 30 });
  assert.deepStrictEqual(got, [60, 90]);
  assert.ok(got.every((t) => t < 120), 'nothing on the closing edge');
});

test('every play segment is sampled, and breaks are never sampled', () => {
  const segs = [
    { play: true, from: 5, to: 100 },
    { play: false, from: 100, to: 200 },
    { play: true, from: 200, to: 300 },
  ];
  const got = T.planGrid(segs, { stepS: 30 });
  assert.strictEqual(got.length, 6, 'three per play segment, none for the break');
  assert.ok(got.every((t) => t < 100 || t >= 200), 'nothing inside the break');
});

// Two play segments closer together than a step can both land on the same grid
// point; the second grab would be of an identical frame, so it is dropped.
test('a grid point shared by two segments is planned once', () => {
  const segs = [
    { play: true, from: 5, to: 65 },
    { play: true, from: 60, to: 120 },
  ];
  const got = T.planGrid(segs, { stepS: 30 });
  assert.deepStrictEqual(got, [30, 60, 90]);
  assert.strictEqual(new Set(got).size, got.length, 'duplicate seeks waste a grab');
});

// 100-115 contains no reachable point on a 30s grid, so the nearest reachable
// instant to the segment's middle is taken instead - sampling somewhere beats
// not sampling the round at all.
test('a segment too short for the grid falls back to its nearest reachable middle', () => {
  const got = T.planGrid([{ play: true, from: 100, to: 115 }], { stepS: 30 });
  assert.strictEqual(got.length, 1, 'a short segment must not vanish');
  assert.strictEqual(got[0] % 30, 0, `${got[0]} is not reachable`);
});

// The grid must equal the client's skip interval, or a seek cannot land on it.
// Anything else is refused, not rounded into looking reachable.
test('a step that is not a skip interval is refused', () => {
  assert.throws(() => T.planGrid([{ play: true, from: 0, to: 100 }], { stepS: 7 }),
    /5\/10\/20\/30\/45\/60/);
  assert.throws(() => T.planGrid([{ play: true, from: 0, to: 100 }], {}),
    /5\/10\/20\/30\/45\/60/);
});

// The real measurement from the rig: a 17:42 Control replay whose bar showed
// two blue runs. This is the shape the sampler must produce for it - every
// 30s inside play.
test('the measured Control replay is sampled every 30s inside its three rounds', () => {
  const segs = [
    { play: true, from: 4, to: 406 },
    { play: false, from: 406, to: 526 },
    { play: true, from: 527, to: 743 },
    { play: false, from: 744, to: 805 },
    { play: true, from: 805, to: 1062 },
  ];
  const got = T.planGrid(segs, { stepS: 30 });
  assert.strictEqual(got.length, 29, '13 + 7 + 9 grid points');
  got.forEach((t) => assert.strictEqual(t % 30, 0, `${t} is off the grid`));
  got.forEach((t) => assert.ok(t > 0 && t < 1062, `${t} escaped the map`));
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

test('dropping the setup blip removes its reachable grid points', () => {
  const raw = [
    { from: 0, to: 10, play: false },
    { from: 10, to: 17, play: true },
    { from: 17, to: 49, play: false },
    { from: 49, to: 299, play: true },
  ];
  const rawPlan = T.planGrid(raw, { stepS: 30 });
  const dropped = T.planGrid(T.dropShortPlay(raw, 30), { stepS: 30 });
  assert.ok(dropped.length < rawPlan.length,
    'the setup stretch is no longer worth a sample');
  assert.ok(!dropped.includes(0), 'sampling the first instant of a map reads no HUD at all');
});

test('the plan no longer reaches for 0:00', () => {
  const segs = T.dropShortPlay([
    { from: 7, to: 21, play: true },
    { from: 21, to: 53, play: false },
    { from: 53, to: 555, play: true },
  ], 30);
  const plan = T.planGrid(segs, { stepS: 60 });
  assert.ok(!plan.includes(0), 'sampling the first instant of a map reads no HUD at all');
});

// THE ASSEMBLE PHASE IS NOT A ROUND, AND ONE MAP PROVED THE LENGTH TEST IS NOT
// ENOUGH. A hybrid in the first twenty-map league run opened with a stretch of
// play exactly 30 seconds long against a 30-second floor, so it survived by one
// second and the map was recorded with five rounds where four were played. The
// map-type check could not catch it either: hybrid has no upper bound, because
// a score past 3 goes to extra rounds.
//
// Raising the floor is the wrong lever. Assemble phases measured 7 to 30
// seconds across that run, but a REAL round can be short too - a Junkertown
// escort's second round ran 43 seconds - so a floor high enough to catch this
// starts eating rounds that were played.
//
// The structural fact is better: every map opens with an assemble phase, so a
// stretch of play starting at the very beginning of the bar is that phase and
// never a round. Every genuine first round in that run began between 0:49 and
// 0:58.
test('play starting at the very beginning of the bar is the assemble phase', () => {
  const got = T.dropShortPlay([
    { from: 0, to: 30, play: true },
    { from: 30, to: 58, play: false },
    { from: 58, to: 531, play: true },
  ], 30);
  assert.deepStrictEqual(got.map((s) => s.play), [false, false, true]);
  assert.strictEqual(got[0].tooShort, true, 'shown as setup, like any other non-round');
});

test('a long opening stretch is still not a round if it starts at zero', () => {
  const got = T.dropShortPlay([{ from: 0, to: 400, play: true }], 30);
  assert.strictEqual(got[0].play, false, 'nothing is played before the assemble phase');
});

// The bar does not always start exactly at zero - some maps read a few seconds
// of break first - so "at the beginning" has to allow for that.
test('play beginning a few seconds in is still the assemble phase', () => {
  const got = T.dropShortPlay([
    { from: 3, to: 33, play: true },
    { from: 33, to: 60, play: false },
    { from: 60, to: 500, play: true },
  ], 30);
  assert.deepStrictEqual(got.map((s) => s.play), [false, false, true]);
});

// And a short round in the MIDDLE of a map is a round: the Junkertown escort's
// 43-second second round is real, and dropping it loses half the map.
test('a short round later in the map is kept', () => {
  const got = T.dropShortPlay([
    { from: 49, to: 294, play: true },
    { from: 294, to: 367, play: false },
    { from: 367, to: 410, play: true },
  ], 30);
  assert.deepStrictEqual(got.map((s) => s.play), [true, false, true]);
});

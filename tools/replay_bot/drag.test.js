const test = require('node:test');
const assert = require('node:assert');
const D = require('./drag.js');
const calib = require('./calib.js');

// A bar calibrated the way capture.js calibrates one: zero at 95px, and one
// 60-second press worth 146.5px. These are real numbers from a live map.
const REF = { zeroX: 95, stepPx: 146.5, stepS: 60 };

test('a target second becomes the pixel that second sits at', () => {
  assert.strictEqual(D.plan(REF, 0, 0).toX, 95);
  assert.strictEqual(D.plan(REF, 0, 60).toX, Math.round(95 + 146.5));
  assert.strictEqual(D.plan(REF, 0, 120).toX, Math.round(95 + 293));
});

// The drag starts from where the playhead actually is, because grabbing the
// scrubber anywhere else is a click on the bar, which is a different gesture.
test('the drag starts at the playhead, not at an arbitrary point', () => {
  const p = D.plan(REF, 400, 600);
  assert.strictEqual(p.x, 400);
});

test('the drag runs along the bar, between its measured rows', () => {
  const t = calib.FROZEN.timeline;
  const p = D.plan(REF, 100, 300);
  assert.ok(p.y >= t.y0 && p.y <= t.y1, `y ${p.y} must lie on the bar (${t.y0}..${t.y1})`);
  assert.strictEqual(p.toY, p.y, 'a scrub is horizontal; drifting off the bar drops it');
});

// play_input.ps1 moves along the path rather than teleporting, because a drag
// with no intermediate points reads as a click at the start - the comment in
// that script says a scrollbar drag used to become exactly that.
test('the drag carries intermediate points', () => {
  const p = D.plan(REF, 100, 900);
  assert.ok(p.path.length >= 3, 'a teleport reads as a click');
  assert.strictEqual(p.path[0].x, 100);
  assert.strictEqual(p.path[p.path.length - 1].x, p.toX);
  assert.ok(p.path.every((q) => q.y === p.y), 'every point stays on the bar');
});

// The client tracks the scrubber by cursor position, and a hop too large
// between two points is not followed: probe_drag measured a 690px backward
// drag in 8 hops (86px each) land 100s short, the playhead having stopped
// following partway. Every hop stays under MAX_HOP_PX.
test('a long drag is split into hops the client can follow', () => {
  // playhead near 405s (x~1084), dragged back to 122s (x~393): ~690px.
  const p = D.plan(REF, 1084, 122);
  assert.ok(p.path.length > D.MIN_STEPS + 1, 'a long drag needs more than the floor');
  for (let i = 1; i < p.path.length; i++) {
    const hop = Math.abs(p.path[i].x - p.path[i - 1].x);
    assert.ok(hop <= D.MAX_HOP_PX, `hop ${hop}px exceeds MAX_HOP_PX ${D.MAX_HOP_PX}`);
  }
});

// A short drag does not collapse to a teleport just because the distance is
// under one hop - the floor keeps it a recognisable gesture.
test('a short drag keeps the minimum number of points', () => {
  const p = D.plan(REF, 100, 5);    // x~100 is ~2s; a few seconds is a few px
  assert.ok(Math.abs(p.toX - 100) < D.MAX_HOP_PX, 'this case must be under one hop');
  assert.strictEqual(p.path.length, D.MIN_STEPS + 1);
});

test('the plan is one drag event the player already understands', () => {
  const p = D.plan(REF, 100, 500);
  assert.strictEqual(p.type, 'drag');
  assert.strictEqual(p.button, 'left');
  assert.ok(p.holdMs > 0 && p.waitMs >= 0);
});

// A target outside the bar is a bug upstream - a sample planned past the end of
// the map - and clamping it silently would seek somewhere plausible and wrong.
test('a target off the end of the bar is refused, not clamped', () => {
  const t = calib.FROZEN.timeline;
  const beyond = (t.x1 - REF.zeroX) / REF.stepPx * REF.stepS + 120;
  assert.throws(() => D.plan(REF, 100, beyond), /off the bar/);
  assert.throws(() => D.plan(REF, 100, -30), /off the bar/);
});

// --- seeker: the driver-facing (toT) -> boolean ---------------------------

const seekerDeps = (over) => Object.assign({
  ref: () => REF,
  frame: async () => 'frame',
  loadImage: async (x) => x,
  playhead: () => ({ centre: 1084 }),   // ~405s on REF
  play: async () => {},
  log: () => {},
}, over);

test('the seeker drags from the playhead to the target once the bar is known', async () => {
  const played = [];
  const seek = D.seeker(seekerDeps({ play: async (evs) => { played.push(...evs); } }));
  assert.strictEqual(await seek(122), true);
  assert.strictEqual(played.length, 1);
  assert.strictEqual(played[0].type, 'drag');
  assert.strictEqual(played[0].x, 1084, 'starts at the playhead it read');
});

test('the seeker defers to the keys before the bar is calibrated', async () => {
  let played = false;
  const seek = D.seeker(seekerDeps({ ref: () => null, play: async () => { played = true; } }));
  assert.strictEqual(await seek(60), false);
  assert.strictEqual(played, false, 'nothing is dragged without a bar scale');
});

test('the seeker defers to the keys when the playhead is not readable', async () => {
  const seek = D.seeker(seekerDeps({
    playhead: () => null,
    play: async () => { throw new Error('must not drag'); },
  }));
  assert.strictEqual(await seek(60), false);
});

test('the seeker defers to the keys when the target is off the bar', async () => {
  const logs = [];
  const seek = D.seeker(seekerDeps({
    play: async () => { throw new Error('must not drag'); },
    log: (l) => logs.push(l),
  }));
  assert.strictEqual(await seek(99999), false);
  assert.ok(logs.some((l) => /drag skipped/.test(l)), 'and it says why');
});

// How precisely a drag can place the playhead, which is what decides whether
// this is worth doing at all. One pixel is a fraction of a second on every map
// measured, against a key press worth a fixed 60.
test('one pixel is worth well under a second on a real bar', () => {
  assert.ok(D.secondsPerPixel(REF) < 1, D.secondsPerPixel(REF) + 's per pixel');
  // the coarsest bar measured in the league run: a 22-minute map
  assert.ok(D.secondsPerPixel({ zeroX: 94.5, stepPx: 105, stepS: 60 }) < 1);
});

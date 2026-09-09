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

// How precisely a drag can place the playhead, which is what decides whether
// this is worth doing at all. One pixel is a fraction of a second on every map
// measured, against a key press worth a fixed 60.
test('one pixel is worth well under a second on a real bar', () => {
  assert.ok(D.secondsPerPixel(REF) < 1, D.secondsPerPixel(REF) + 's per pixel');
  // the coarsest bar measured in the league run: a 22-minute map
  assert.ok(D.secondsPerPixel({ zeroX: 94.5, stepPx: 105, stepS: 60 }) < 1);
});

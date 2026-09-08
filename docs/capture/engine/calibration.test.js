const test = require('node:test');
const assert = require('node:assert');

// calibration.js reaches for document/localStorage at make() time and resolves
// page globals as free variables; only the pure geometry is under test here.
global.document = { createElement: () => ({ width: 0, height: 0, getContext: () => ({}) }),
  getElementById: () => null };
global.localStorage = { getItem: () => null, setItem() {}, removeItem() {} };
global.boxes = {};
const C = require('./calibration.js');
const cal = C.make({ doc: global.document, video: { videoWidth: 0, videoHeight: 0 },
  ov: null, octx: null, boxKeys: ['a', 'b'] });

const rect = (w, h) => ({ x: 0, y: 0, w: w, h: h });

test('at 16:9 the projection is unchanged - the fix must be a no-op there', () => {
  // AUTO_STRIPS was measured on 16:9, so height*(fy) and width*(9/16)*(fy) are
  // the same number there. Any capture that already worked must keep working.
  const b = cal.boxesFromStrips(rect(2560, 1440), 0, 0).a;
  assert.ok(Math.abs(b.x - 0.0506 * 2560) < 0.01);
  assert.ok(Math.abs(b.y - 0.0832 * 1440) < 0.01);
  assert.ok(Math.abs(b.w - 0.2579 * 2560) < 0.01);
  assert.ok(Math.abs(b.h - 0.0675 * 1440) < 0.01);
});

test('a squashed frame does not move the HUD down or shrink it', () => {
  // The game renders the HUD to the width it is given. A window capture that is
  // not 16:9 must not drag the strips upward - which is exactly what projecting
  // y and h against HEIGHT does.
  const wide = cal.boxesFromStrips(rect(2560, 1440), 0, 0).a;
  const squashed = cal.boxesFromStrips(rect(2560, 1300), 0, 0).a;
  assert.strictEqual(squashed.y, wide.y);
  assert.strictEqual(squashed.h, wide.h);
  assert.strictEqual(squashed.x, wide.x);
  assert.strictEqual(squashed.w, wide.w);
});

test('it lands near the live 2570x1393 window capture', () => {
  // Ground truth read out of a real session on 2026-09-07 (not a screenshot):
  // boxes.a = x135.5 y125.5 w660.1 h100.4 at videoWidth 2570 x 1393.
  const b = cal.boxesFromStrips(rect(2570, 1393), 0, 0).a;
  assert.ok(Math.abs(b.x - 135.5) <= 7, 'x was ' + b.x);
  assert.ok(Math.abs(b.w - 660.1) <= 7, 'w was ' + b.w);
  assert.ok(Math.abs(b.y - 125.5) <= 7, 'y was ' + b.y);
  assert.ok(Math.abs(b.h - 100.4) <= 4, 'h was ' + b.h);
});

// ---------- the frame guard ----------
//
// Measured in the field 2026-09-07: a sweep candidate at y=-27.9 - partly ABOVE
// the top of the video - scored 10/10 confident, beating the real portraits at
// y=37.2. An out-of-frame crop comes back uniform black, and centred and
// L2-normalised that correlates strongly with almost any reference, so the
// scorer's most confident answer was a box not looking at the picture at all.
//
// The only reason calibration did not lock onto it is that the offset was
// outside the coarse sweep's range. That is luck, not a guard.

test('a box hanging off the top of the frame is refused', () => {
  assert.strictEqual(cal.withinFrame({ a: { x: 10, y: -27.9, w: 100, h: 97 },
                                       b: { x: 500, y: -27.9, w: 100, h: 97 } }, 2570, 1393), false);
});

test('a box running off the right edge is refused', () => {
  assert.strictEqual(cal.withinFrame({ a: { x: 10, y: 40, w: 100, h: 97 },
                                       b: { x: 2500, y: 40, w: 100, h: 97 } }, 2570, 1393), false);
});

test('a box fully inside the frame is allowed', () => {
  assert.strictEqual(cal.withinFrame({ a: { x: 175, y: 40.8, w: 662, h: 97 },
                                       b: { x: 1774, y: 40.8, w: 662, h: 97 } }, 2570, 1393), true);
});

test('a box flush against the frame edges is still inside it', () => {
  assert.strictEqual(cal.withinFrame({ a: { x: 0, y: 0, w: 100, h: 97 },
                                       b: { x: 2470, y: 1296, w: 100, h: 97 } }, 2570, 1393), true);
});

// ---------- per-strip independence ----------
//
// The strips must be placeable at DIFFERENT offsets. A single shared (dx, dy)
// cannot correct a width error, because the offset it leaves is
// f*(R.w - true_w) - small at the left strip's f=0.0506, large at the right
// strip's f=0.6912. Measured on a real frame 2026-09-07 the two strips wanted
// dx values 0.005 apart, about 13px, and the joint search placed the right
// strip correctly while putting the left one on the wrong row entirely.

test('a strip can be offset without moving the other', () => {
  const R = { x: 0, y: 0, w: 2570, h: 1393 };
  const a0 = cal.stripBox(R, 'a', 0, 0);
  const a1 = cal.stripBox(R, 'a', 0.005, 0);
  const b0 = cal.stripBox(R, 'b', 0, 0);
  assert.ok(Math.abs(a1.x - a0.x - 0.005 * R.w) < 0.01, 'the strip moved by dx*R.w');
  assert.strictEqual(cal.stripBox(R, 'b', 0, 0).x, b0.x, 'the other strip did not move');
});

test('stripBox agrees with boxesFromStrips when both strips share an offset', () => {
  const R = { x: 0, y: 0, w: 2560, h: 1440 };
  const joint = cal.boxesFromStrips(R, 0.003, -0.004);
  ['a', 'b'].forEach(side => {
    const one = cal.stripBox(R, side, 0.003, -0.004);
    ['x', 'y', 'w', 'h'].forEach(k =>
      assert.ok(Math.abs(one[k] - joint[side][k]) < 1e-9, side + '.' + k));
  });
});

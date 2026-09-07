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

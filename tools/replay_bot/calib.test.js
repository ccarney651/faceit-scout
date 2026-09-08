const test = require('node:test');
const assert = require('node:assert');
const C = require('./calib.js');

const near = (got, want, msg) =>
  assert.ok(Math.abs(got - want) < 0.001, `${msg}: got ${got}, want ${want}`);

test('the frozen geometry is the committed box, not the AUTO_STRIPS default', () => {
  // 129.536 is what boxes.a holds BEFORE "Use boxes" is pressed. Freezing it
  // would put every crop half a portrait off, while auto-calibrate cheerfully
  // reports 10/10. See the 2026-09-08 correction in the calibration memory.
  near(C.FROZEN.boxes.a.x, 55.33490566037736, 'boxes.a.x');
  assert.notStrictEqual(C.FROZEN.boxes.a.x, 129.536);
});

test('a side has five cells, one per player', () => {
  assert.strictEqual(C.cells('a').length, 5);
  assert.strictEqual(C.cells('b').length, 5);
});

test('a cell skips the ult-charge number and keeps the portrait', () => {
  const c = C.cells('a')[0];
  const b = C.FROZEN.boxes.a;
  const cw = b.w / 5;
  near(c.x, b.x + cw * C.FROZEN.ref.LF, 'left inset drops the ult %');
  near(c.w, cw * (1 - C.FROZEN.ref.LF), 'width is the remainder');
});

test('a cell keeps the top of the row, not the name or health pips', () => {
  const c = C.cells('a')[0];
  const b = C.FROZEN.boxes.a;
  near(c.y, b.y, 'starts at the top of the box');
  near(c.h, b.h * C.FROZEN.ref.TF, 'height is the top fraction only');
});

test('cells advance by exactly one fifth of the box', () => {
  const cs = C.cells('a');
  const cw = C.FROZEN.boxes.a.w / 5;
  near(cs[1].x - cs[0].x, cw, 'slot 1 to 2');
  near(cs[4].x - cs[3].x, cw, 'slot 4 to 5');
});

// The smoke check is the whole defence against a patch moving the HUD while the
// bot runs unattended. It must fail loudly rather than crop the wrong pixels.
test('a frame of unexpected size is refused', () => {
  const got = C.check({ w: 1920, h: 1080 });
  assert.strictEqual(got.ok, false);
  assert.match(got.reason, /1920x1080/);
});

test('a frame matching the bootstrap is accepted', () => {
  assert.strictEqual(C.check({ w: 2560, h: 1440 }).ok, true);
});

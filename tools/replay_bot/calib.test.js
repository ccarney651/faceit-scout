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
  near(c.w, cw * (1 - C.FROZEN.ref.LF - C.FROZEN.ref.RF), 'width drops the right gap-seam too');
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

// The round breaks only render on the scrubber while the replay events viewer
// is open, so the bot must know whether it is. K toggles it, which means a
// blind press is as likely to close it as open it.
test('a box full of panel rows reads as open', () => {
  assert.strictEqual(C.eventsViewerOpen(0.340), true);
});

test('a box with none of them reads as closed', () => {
  assert.strictEqual(C.eventsViewerOpen(0.015), false);
});

// 0.340 and 0.015 are the extremes crop.panelRowFraction returned over the
// whole retained corpus - the weakest open frame and the strongest closed one.
// corpus.test.js measures them again from the frames; this pins the threshold
// against them so a number moved by hand fails here too.
test('the open/closed threshold sits between the two measured states', () => {
  const t = C.FROZEN.eventsPanel.minPanelRows;
  assert.ok(t > 0.015 && t < 0.340, `threshold ${t} must separate the measurements`);
});

// --- is a replay even on screen? ------------------------------------------
//
// This used to be answered by the playhead, and that was wrong in a way that
// cost three codes: the media controls are HIDDEN when a replay opens, so a
// perfectly good replay shows no scrubber. The bot waited 90s for one inside a
// replay that was already playing, then ran the import chunk from inside it.
//
// The team plates are drawn either way - side a blue, side b red. Measured on
// real frames: 76.2/35.1 with the controls down, 49.8/43.0 mid-sample,
// 29.1/58.9 during assemble, and exactly 0.0/0.0 on a black loading screen.

test('a replay frame reads as a replay', () => {
  assert.strictEqual(C.hudPresent({ a: 76.2, b: 35.1 }), true, 'controls down');
  assert.strictEqual(C.hudPresent({ a: 49.8, b: 43.0 }), true, 'mid-sample');
  assert.strictEqual(C.hudPresent({ a: 29.1, b: 58.9 }), true, 'assemble phase');
});

test('a black loading screen does not', () => {
  assert.strictEqual(C.hudPresent({ a: 0, b: 0 }), false);
});

// Both sides have to be tinted. One alone could be anything the map happens to
// be showing - a red wall, a blue sky - and reading a menu as a replay is how
// clicks end up somewhere they mean something else.
test('one tinted side is not enough', () => {
  assert.strictEqual(C.hudPresent({ a: 60, b: 2 }), false);
  assert.strictEqual(C.hudPresent({ a: 2, b: 60 }), false);
});

test('the threshold sits between the loading screen and the tightest real frame', () => {
  assert.ok(C.HUD_TINT > 0 && C.HUD_TINT < 29,
    'below the smallest margin measured on a real replay, above black');
});

const test = require('node:test');
const assert = require('node:assert');
const { createCanvas } = require('@napi-rs/canvas');
const U = require('../../docs/capture/engine/util.js');
const Crop = require('./crop.js');

const REF = { REF_W: 64, REF_H: 36 };

// A solid source of one colour, big enough that the downscale has real pixels
// to average rather than edge cases.
function solid(css, w = 200, h = 100) {
  const cv = createCanvas(w, h);
  const cx = cv.getContext('2d');
  cx.fillStyle = css;
  cx.fillRect(0, 0, w, h);
  return cv;
}

const bytes = (b64) => U.b64bytes(b64);
const whole = (w, h) => ({ x: 0, y: 0, w, h });

test('a crop is exactly REF_W by REF_H bytes of greyscale', () => {
  const got = bytes(Crop.cell(solid('#ffffff'), whole(200, 100), REF));
  assert.strictEqual(got.length, REF.REF_W * REF.REF_H);
});

test('white crops to full brightness', () => {
  const got = bytes(Crop.cell(solid('#ffffff'), whole(200, 100), REF));
  assert.ok(got.every((v) => v === 255), 'every byte should be 255');
});

test('black crops to zero', () => {
  const got = bytes(Crop.cell(solid('#000000'), whole(200, 100), REF));
  assert.ok(got.every((v) => v === 0), 'every byte should be 0');
});

// These three pin the luma weights to learnCrop's 0.299/0.587/0.114. Any other
// greyscale formula - a plain mean, or BT.709's weights - still produces a
// plausible-looking crop that scores differently against every stored template,
// which would degrade matching everywhere without failing anything loudly.
test('red uses the 0.299 luma weight, not a channel mean', () => {
  const got = bytes(Crop.cell(solid('#ff0000'), whole(200, 100), REF));
  assert.strictEqual(got[0], Math.round(0.299 * 255));
});

test('green uses the 0.587 luma weight', () => {
  const got = bytes(Crop.cell(solid('#00ff00'), whole(200, 100), REF));
  assert.strictEqual(got[0], Math.round(0.587 * 255));
});

test('blue uses the 0.114 luma weight', () => {
  const got = bytes(Crop.cell(solid('#0000ff'), whole(200, 100), REF));
  assert.strictEqual(got[0], Math.round(0.114 * 255));
});

// The crop must read the requested rectangle, not the whole source. A half-and-
// half image cropped to its dark half must come back dark.
test('the crop reads its rectangle rather than the whole frame', () => {
  const cv = createCanvas(200, 100);
  const cx = cv.getContext('2d');
  cx.fillStyle = '#ffffff'; cx.fillRect(0, 0, 100, 100);
  cx.fillStyle = '#000000'; cx.fillRect(100, 0, 100, 100);

  const left = bytes(Crop.cell(cv, { x: 0, y: 0, w: 100, h: 100 }, REF));
  const right = bytes(Crop.cell(cv, { x: 100, y: 0, w: 100, h: 100 }, REF));
  assert.strictEqual(left[0], 255, 'left half is white');
  assert.strictEqual(right[0], 0, 'right half is black');
});

// --- the playhead ---------------------------------------------------------
//
// Where a seek actually landed. The first live run believed six samples were
// spread over fourteen minutes; the knob says they were all inside the first
// two, which is a failure no hero read could have shown.

const calib = require('./calib.js');

// A frame with the scrubber drawn into it: a mid-grey bar, a knob of `width`
// pixels at `at`, and optionally a narrow bright event tick.
function withBar(at, width, tickAt) {
  const f = calib.FROZEN.frame;
  const t = calib.FROZEN.timeline;
  const cv = createCanvas(f.w, f.h);
  const cx = cv.getContext('2d');
  cx.fillStyle = '#000000';
  cx.fillRect(0, 0, f.w, f.h);
  cx.fillStyle = '#4d4d4d';
  cx.fillRect(t.x0, t.y0, t.x1 - t.x0 + 1, t.y1 - t.y0 + 1);
  cx.fillStyle = '#ffffff';
  cx.fillRect(at, t.y0, width, t.y1 - t.y0 + 1);
  if (tickAt) cx.fillRect(tickAt, t.y0, 3, t.y1 - t.y0 + 1);
  return cv;
}

test('the playhead is found where it was drawn', () => {
  const got = Crop.playheadX(withBar(500, 40), calib);
  assert.deepStrictEqual([got.x0, got.width], [500, 40]);
  assert.strictEqual(got.centre, 519.5);
});

// Event ticks are bright too, and one taken for the knob would report a
// position the replay was never at - which is the exact class of error the
// playhead exists to catch.
test('a narrow event tick is not the playhead', () => {
  const got = Crop.playheadX(withBar(900, 40, 300), calib);
  assert.strictEqual(got.x0, 900, 'the widest run wins');
});

test('a frame with no playhead reports none rather than guessing', () => {
  assert.strictEqual(Crop.playheadX(withBar(500, 3), calib), null);
});

test('the playhead is found at either end of the bar', () => {
  const t = calib.FROZEN.timeline;
  assert.strictEqual(Crop.playheadX(withBar(t.x0, 40), calib).x0, t.x0);
  assert.strictEqual(Crop.playheadX(withBar(t.x1 - 39, 40), calib).x1, t.x1);
});

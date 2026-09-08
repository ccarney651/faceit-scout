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

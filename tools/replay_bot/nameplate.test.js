// Name-row/name-span cropping against a real frame. findNameRow/findNameSpan
// themselves are tested in docs/capture/engine/frames.test.js - this only
// checks the thin @napi-rs/canvas wrapper around them, the same split as the
// module itself. See nameplate.js and corpus.js's NAMEPLATES.
const test = require('node:test');
const assert = require('node:assert');
const canvas = require('@napi-rs/canvas');
const C = require('./corpus.js');
const calib = require('./calib.js');
const N = require('./nameplate.js');

const skip = C.absent() || false;
const witness = C.NAMEPLATES[0];

test('nameRow finds a band under the portraits, on both sides', { skip }, async () => {
  const img = await canvas.loadImage(C.at(witness.file));
  for (const side of ['a', 'b']) {
    const box = calib.FROZEN.boxes[side];
    const row = N.nameRow(img, box);
    assert.ok(row, side + ': expected a row');
    // The portrait fills the top TF of the box; the row must sit below it and
    // comfortably above the box's bottom edge (the health bar), not spanning
    // either.
    const portraitBottom = box.y + box.h * calib.FROZEN.ref.TF;
    assert.ok(row.y > portraitBottom, side + ': row starts inside the portrait');
    assert.ok(row.y + row.h < box.y + box.h, side + ': row runs past the box');
    assert.ok(row.h > 8 && row.h < box.h * 0.4, side + ': row height ' + row.h + ' is not name-sized');
  }
});

test('nameCrop produces a non-trivial canvas for every slot, both sides', { skip }, async () => {
  const img = await canvas.loadImage(C.at(witness.file));
  for (const side of ['a', 'b']) {
    const box = calib.FROZEN.boxes[side];
    const row = N.nameRow(img, box);
    const slots = calib.slots(side);
    slots.forEach((cell, i) => {
      const cv = N.nameCrop(img, cell, row);
      assert.ok(cv.width > 20 && cv.height > 20,
        side + i + ': crop is ' + cv.width + 'x' + cv.height);
    });
  }
});

test('the five slot columns tile the box left to right with no gap or overlap', () => {
  const box = calib.FROZEN.boxes.a;
  const slots = calib.slots('a');
  assert.strictEqual(slots.length, 5);
  slots.forEach((s, i) => {
    assert.strictEqual(s.y, box.y);
    assert.strictEqual(s.h, box.h);
    assert.ok(Math.abs(s.x - (box.x + i * (box.w / 5))) < 1e-6);
  });
  const last = slots[4];
  assert.ok(Math.abs((last.x + last.w) - (box.x + box.w)) < 1e-6);
});

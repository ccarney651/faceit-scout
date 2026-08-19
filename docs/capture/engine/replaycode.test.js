const test = require('node:test');
const assert = require('node:assert');
const R = require('./replaycode.js');

test('the alphabet is Crockford Base32', () => {
  assert.strictEqual(R.ALPHABET, '0123456789ABCDEFGHJKMNPQRSTVWXYZ');
  assert.strictEqual(R.ALPHABET.length, 32);
  for (const ch of 'ILOU') assert.ok(R.ALPHABET.indexOf(ch) === -1, ch + ' must not be in the alphabet');
});

test('a clean read passes through', () => {
  assert.strictEqual(R.foldCode('D9X9N2'), 'D9X9N2');
});

test('lower case is accepted, as Crockford decoders must', () => {
  assert.strictEqual(R.foldCode('d9x9n2'), 'D9X9N2');
});

test('OCR punctuation around the code is discarded', () => {
  // The crop carries the plate edges; the name-crop work showed OCR wraps a
  // legible string in invented punctuation.
  assert.strictEqual(R.foldCode('| D9X9N2 |'), 'D9X9N2');
  assert.strictEqual(R.foldCode('  D9X9N2\n'), 'D9X9N2');
});

test('I and L fold to 1, and O folds to 0 - the published decoder rule', () => {
  assert.strictEqual(R.foldCode('I9X9N2'), '19X9N2');
  assert.strictEqual(R.foldCode('L9X9N2'), '19X9N2');
  assert.strictEqual(R.foldCode('O9X9N2'), '09X9N2');
});

test('U is not folded - it fails the read', () => {
  // Crockford excludes U for accidental obscenity, not for visual ambiguity,
  // so there is no principled character to fold it to. Guessing V would be ours.
  assert.strictEqual(R.foldCode('U9X9N2'), null);
});

test('anything but exactly six characters is not a code', () => {
  assert.strictEqual(R.foldCode('D9X9N'), null);
  assert.strictEqual(R.foldCode('D9X9N23'), null);
  assert.strictEqual(R.foldCode(''), null);
  assert.strictEqual(R.foldCode(null), null);
  assert.strictEqual(R.foldCode(undefined), null);
});

test('a character outside the alphabet fails the whole read', () => {
  // Not "drop the bad character and hope" - five good characters and one
  // unknown is not five-sixths of a code, it is no code.
  assert.strictEqual(R.foldCode('D9X9N#'), null);
});

test('the crop is placed relative to the calibrated strip, not the screen', () => {
  // Two frames of the same HUD at different scales must produce boxes in the
  // same proportion. Screen fractions are what broke the HUD name band when
  // the window mode changed - see the 2026-08-18 changelog entry.
  const small = R.codeBox({ x: 57, y: 97, w: 700, h: 111 });
  const big = R.codeBox({ x: 114, y: 194, w: 1400, h: 222 });
  assert.ok(Math.abs((big.x - 114) / 1400 - (small.x - 57) / 700) < 1e-3);
  assert.ok(Math.abs(big.w / 1400 - small.w / 700) < 1e-3);
});

test('the crop sits above the strip and to its right', () => {
  const a = { x: 57, y: 97, w: 700, h: 111 };
  const box = R.codeBox(a);
  assert.ok(box.x > a.x + a.w, 'the code is right of the portrait strip');
  assert.ok(box.y + box.h < a.y, 'the code is above the portrait strip');
});

test('the crop lands on the code, using the strip auto-calibrate really produces', () => {
  // boxes.a read out of a live capture session on a 2560x1440 share, where the
  // code SZDPQQ occupies roughly x=838..938, y=67..90. Deliberately NOT a
  // hand-measured strip: the first version of this test used one, passed, and
  // the crop still missed in the field, because the offsets are fractions of
  // whatever box auto-calibrate hands over.
  const box = R.codeBox({ x: 129.536, y: 119.808, w: 660.224, h: 97.2 });
  assert.ok(box.x <= 838 && box.x + box.w >= 938,
    `the crop must contain x=838..938, got ${box.x}..${box.x + box.w}`);
  assert.ok(box.y <= 67 && box.y + box.h >= 90,
    `the crop must contain y=67..90, got ${box.y}..${box.y + box.h}`);
});

test('a missing or malformed strip yields no box rather than NaNs', () => {
  assert.strictEqual(R.codeBox(null), null);
  assert.strictEqual(R.codeBox({ x: 0, y: 0, w: 0, h: 0 }), null);
});

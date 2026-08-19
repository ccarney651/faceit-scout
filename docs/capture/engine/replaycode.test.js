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

// --- the geometry probes ---------------------------------------------------

test('the centre probe is the strip itself', () => {
  const a = { x: 129.536, y: 119.808, w: 660.224, h: 97.2 };
  const p = R.probeStrip(a, R.PROBES[0]);
  for (const k of ['x', 'y', 'w', 'h']) assert.ok(Math.abs(p[k] - a[k]) < 1e-9, k);
});

test('a probe scales about the strip centre, not its corner', () => {
  // A scout aims at the same five portraits and gets the extent slightly
  // wrong; nobody pins the top-left and stretches. Anchoring the corner would
  // make a scale probe indistinguishable from a translation probe.
  const a = { x: 100, y: 200, w: 600, h: 90 };
  const p = R.probeStrip(a, { s: 0.9 });
  assert.strictEqual(p.x + p.w / 2, a.x + a.w / 2);
  assert.strictEqual(p.y + p.h / 2, a.y + a.h / 2);
  assert.ok(p.w < a.w && p.h < a.h);
});

test('a probe shifts by fractions of the strip, so it scales with resolution', () => {
  // Expressed in pixels it would be a different probe at 1080p than at 4K,
  // and the tolerance it guards is measured in percent of the strip.
  const small = { x: 0, y: 0, w: 100, h: 20 };
  const big = { x: 0, y: 0, w: 1000, h: 200 };
  assert.strictEqual(R.probeStrip(small, { dx: 0.01 }).x / small.w,
                     R.probeStrip(big, { dx: 0.01 }).x / big.w);
});

test('every probe moves exactly one axis', () => {
  // The first attempt moved all three at once. It displaced further than any
  // single axis (refusing good reads) while moving too little vertically to
  // disturb a clipped crop (passing wrong ones). One axis per probe is the
  // measured fix - see tools/real_frame_eval/README.md.
  for (const p of R.PROBES) {
    const moved = ['dx', 'dy', 's'].filter(k => k === 's' ? (p.s !== undefined && p.s !== 1)
                                                          : !!p[k]);
    assert.ok(moved.length <= 1, 'probe moves ' + JSON.stringify(moved) + ': ' + JSON.stringify(p));
  }
});

test('the probes bracket the strip on both axes', () => {
  // A one-sided probe set cannot tell "correct" from "off in the direction I
  // did not look".
  const dxs = R.PROBES.map(p => p.dx || 0), dys = R.PROBES.map(p => p.dy || 0);
  assert.ok(Math.min(...dxs) < 0 && Math.max(...dxs) > 0, 'dx is not bracketed');
  assert.ok(Math.min(...dys) < 0 && Math.max(...dys) > 0, 'dy is not bracketed');
});

test('the vertical probe steps further than the horizontal one', () => {
  // A strip is ~7x wider than tall, so equal PERCENTAGES are wildly unequal
  // pixels. At 1% of height the vertical probe was about one pixel and let
  // H6R64B through as HARAAR.
  const dx = Math.max(...R.PROBES.map(p => Math.abs(p.dx || 0)));
  const dy = Math.max(...R.PROBES.map(p => Math.abs(p.dy || 0)));
  assert.ok(dy > dx, `dy probe ${dy} must exceed dx probe ${dx}`);
});

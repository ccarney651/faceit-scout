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


// --- checkAgainstSelected ------------------------------------------------
// The verdict the league capture page reaches on a map's FIRST snapshot: is
// the code on screen the match the operator chose to scout?

// A division's feed. Real codes from faceit.sqlite3's alphabet: Crockford
// Base32, six characters, no I/L/O/U.
const FEED = [
  { code: 'D9X9N2', team_a: 'Alpha', team_b: 'Bravo' },
  { code: 'B4K2M1', team_a: 'Delta', team_b: 'Echo' },
  { code: 'H6R64B', team_a: 'Foxtrot', team_b: 'Golf' },
];

test('the code on screen is the one selected', () => {
  const r = R.checkAgainstSelected('B4K2M1', FEED, 'B4K2M1');
  assert.equal(r.status, 'ok');
  assert.equal(r.code, 'B4K2M1');
});

test('a different code from the same feed is a mismatch, and names both', () => {
  const r = R.checkAgainstSelected('D9X9N2', FEED, 'B4K2M1');
  assert.equal(r.status, 'mismatch');
  assert.equal(r.code, 'D9X9N2', 'the code the screen is showing');
  assert.equal(r.selected, 'B4K2M1', 'the code the operator picked');
});

// A one-character miss is recoverable BECAUSE the feed exists: there is a right
// answer to compare against, which is what makes the league read trustworthy
// where the scrim read is not.
test('a near miss that folds to the selected code passes silently', () => {
  // B4K2M1 misread with one wrong character.
  const r = R.checkAgainstSelected('B4K2M7', FEED, 'B4K2M1');
  assert.equal(r.status, 'ok');
  assert.equal(r.code, 'B4K2M1');
  assert.equal(r.near, true, 'it passed on a near match, not an exact one');
});

test('a near miss that folds to a DIFFERENT code still blocks', () => {
  // One character off D9X9N2, nothing else in the feed is close.
  const r = R.checkAgainstSelected('D9X9N3', FEED, 'B4K2M1');
  assert.equal(r.status, 'mismatch');
  assert.equal(r.code, 'D9X9N2');
  assert.equal(r.near, true);
  assert.equal(r.read, 'D9X9N3', 'the raw read is kept so the modal can be honest');
});

// The rule the button already followed and the gate inherits: choosing either
// of two equally-near codes could file the capture against the wrong match,
// which is the exact failure this exists to prevent.
test('a tie between two feed codes abstains rather than guessing', () => {
  const feed = [{ code: 'D9X9N2' }, { code: 'D9X9N3' }, { code: 'B4K2M1' }];
  const r = R.checkAgainstSelected('D9X9N4', feed, 'B4K2M1');
  assert.equal(r.status, 'abstain');
  assert.equal(r.code, null);
});

test('a read that is in no feed code abstains, and does not block capture', () => {
  const r = R.checkAgainstSelected('ZZZZZZ', FEED, 'B4K2M1');
  assert.equal(r.status, 'abstain');
});

test('a failed OCR read abstains', () => {
  for (const bad of [null, '', undefined]) {
    assert.equal(R.checkAgainstSelected(bad, FEED, 'B4K2M1').status, 'abstain',
      'a read of ' + JSON.stringify(bad) + ' must not block capture');
  }
});

// Nothing selected means there is nothing to disagree with. The page gates
// capture on a selected code elsewhere; this must not invent a second opinion.
test('no selection abstains', () => {
  assert.equal(R.checkAgainstSelected('D9X9N2', FEED, null).status, 'abstain');
});

test('an empty feed abstains rather than calling everything a mismatch', () => {
  assert.equal(R.checkAgainstSelected('D9X9N2', [], 'B4K2M1').status, 'abstain');
  assert.equal(R.checkAgainstSelected('D9X9N2', null, 'B4K2M1').status, 'abstain');
});

// The selected code not being in the feed is a page bug, not an operator error,
// and blocking on it would accuse the operator of something they did not do.
test('a selection missing from the feed abstains', () => {
  assert.equal(R.checkAgainstSelected('D9X9N2', FEED, 'QQQQQQ').status, 'abstain');
});

// Codes differing in length are not one character apart in any useful sense -
// the Hamming walk in the matcher requires equal lengths.
test('a read of the wrong length never matches', () => {
  assert.equal(R.checkAgainstSelected('D9X9N', FEED, 'B4K2M1').status, 'abstain');
  assert.equal(R.checkAgainstSelected('D9X9N22', FEED, 'B4K2M1').status, 'abstain');
});

// ---------------------------------------------------------------------------
// recheckPinned - the verdict on every snapshot AFTER the first, once a code is
// pinned to the map.
//
// These exist because the mid-map guard shipped with no test at all: on
// 2026-09-08 the operator swapped replays mid-capture and the page said
// nothing, and neither the 907 pytest nor the 148 browser checks touched the
// path. The distinction the page could not draw - and therefore could not
// report - is 'unsure' versus 'same'.

test('the same code still on screen is not a change', () => {
  const r = R.recheckPinned('B4K2M1', FEED, 'B4K2M1');
  assert.equal(r.status, 'same');
  assert.equal(r.code, 'B4K2M1');
});

test('a different feed code on screen is a change, and names it', () => {
  const r = R.recheckPinned('D9X9N2', FEED, 'B4K2M1');
  assert.equal(r.status, 'changed');
  assert.equal(r.code, 'D9X9N2');
});

// UNSURE IS NOT SAME. The page reports these differently: 'same' is a
// confirmation the operator can trust, 'unsure' is a snapshot going into the
// record unverified. Collapsing them is what made the guard invisible.
test('an unreadable pass is unsure, never same', () => {
  for (const bad of [null, '', undefined]) {
    const r = R.recheckPinned(bad, FEED, 'B4K2M1');
    assert.equal(r.status, 'unsure',
      'a read of ' + JSON.stringify(bad) + ' must not be reported as confirmed');
  }
});

// A scrim replay, or any replay this league feed does not carry. The screen
// really did change, but the page cannot name what to, so it cannot say the
// capture is now filed against the wrong match - only that it cannot tell.
test('a code belonging to no feed entry is unsure, not a change', () => {
  const r = R.recheckPinned('ZZZZZZ', FEED, 'B4K2M1');
  assert.equal(r.status, 'unsure');
  assert.equal(r.code, null);
});

// One character apart is an OCR inference. Stopping a capture that is going
// fine on an inference is the same error the first-snapshot check refuses to
// make - see the near-match modal there.
test('a near match is unsure, and never stops a capture', () => {
  const r = R.recheckPinned('D9X9N4', FEED, 'B4K2M1');
  assert.equal(r.status, 'unsure');
  assert.ok(r.near, 'the page may want to say the read was close');
  // Named, because the page prints it: "one character off D9X9N2". A near
  // match that reports no candidate makes that sentence read "off null".
  assert.equal(r.code, 'D9X9N2');
});

test('a near match of the pinned code itself is unsure, not a change', () => {
  const r = R.recheckPinned('B4K2M2', FEED, 'B4K2M1');
  assert.equal(r.status, 'unsure');
});

// Nothing pinned means the guard was never armed - the caller gates on this,
// and this must not invent a second opinion.
test('no pinned code is unsure', () => {
  assert.equal(R.recheckPinned('D9X9N2', FEED, null).status, 'unsure');
});

test('an empty feed is unsure rather than a change', () => {
  assert.equal(R.recheckPinned('D9X9N2', [], 'B4K2M1').status, 'unsure');
  assert.equal(R.recheckPinned('D9X9N2', null, 'B4K2M1').status, 'unsure');
});

// The pinned code came from an exact feed match, so its absence means the feed
// moved under a live capture. That is a page problem, not a wrong replay.
test('a pinned code missing from the feed is unsure', () => {
  assert.equal(R.recheckPinned('D9X9N2', FEED, 'QQQQQQ').status, 'unsure');
});

test('a read of the wrong length is unsure', () => {
  assert.equal(R.recheckPinned('D9X9N', FEED, 'B4K2M1').status, 'unsure');
  assert.equal(R.recheckPinned('D9X9N22', FEED, 'B4K2M1').status, 'unsure');
});

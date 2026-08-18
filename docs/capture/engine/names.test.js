const test = require('node:test');
const assert = require('node:assert');
const Names = require('./names.js');

test('normName folds case and trims', () => {
  assert.equal(Names.normName('  Kirbz  '), 'kirbz');
});

test('normName drops a battletag discriminator', () => {
  // The ready-up list renders the real battletag; stored game_name values
  // carry no discriminator, so both forms must compare equal.
  assert.equal(Names.normName('Kirbz#2183'), Names.normName('Kirbz'));
});

// simScore's formula is `200 * matchTotal / (a.length + b.length)`, which is
// difflib's `ratio() * 100` (the two-in-numerator and two-lengths-in-
// denominator cancel) — i.e. a 0..100 scale, matching the exe's
// STRONG_NAME_SCORE=75 threshold this task also moves unchanged. index.html's
// own inline comment already said "// 0..100". Moved byte-identical: the
// task brief for this extraction documented the scale as 0..200, but that
// does not match either page's actual (unchanged) runtime behaviour, verified
// empirically before writing this file — correcting the expected numbers
// here rather than silently doubling the formula and de-calibrating
// STRONG_NAME_SCORE / AUTO_SIDE_MARGIN for every page that consumes it.
test('simScore is 100 for an exact match and 0 for empties', () => {
  assert.equal(Names.simScore('Kirbz', 'Kirbz'), 100);
  assert.equal(Names.simScore('', ''), 0);
});

test('simScore ignores case and surrounding whitespace', () => {
  assert.equal(Names.simScore(' KIRBZ ', 'kirbz'), 100);
});

test('a single-character OCR miss still clears STRONG_NAME_SCORE', () => {
  const s = Names.simScore('Kirbz', 'Klrbz');
  assert.ok(s < 100, `expected below exact, got ${s}`);
  assert.ok(s >= Names.STRONG_NAME_SCORE,
    `one-character miss must stay a strong match, got ${s}`);
});

test('an unrelated name scores far below the strong-match bar', () => {
  assert.ok(Names.simScore('Kirbz', 'Zzzzz') < Names.STRONG_NAME_SCORE);
});

// Stroked/barred Latin letters have no canonical decomposition, so the NFD fold
// alone left them in place while an ASCII-restricted OCR could only ever emit
// the base letter. See specs/2026-08-16-player-assignment-design.md 4.4.
test('normName transliterates stroked letters NFD cannot decompose', () => {
  assert.equal(Names.normName('ŚŁØŴ'), 'slow');
  assert.equal(Names.normName('ŦŪX'), 'tux');
  assert.equal(Names.normName('Ƕ2Ɓ'), 'h2b');
  assert.equal(Names.normName('Mßkn'), 'msskn');
});

test('a real HUD read now matches a stroked roster name', () => {
  // Before the transliteration these scored 50 and 66.7 against a bar of 75 -
  // unmatchable even with a flawless read.
  assert.ok(Names.simScore('slow', 'ŚŁØŴ') >= Names.STRONG_NAME_SCORE);
  assert.ok(Names.simScore('teddybear!', 'ŦeddyƁearǃ') >= Names.STRONG_NAME_SCORE);
});

test('normName leaves ordinary decomposable accents working as before', () => {
  assert.equal(Names.normName('Hēv'), 'hev');
  assert.equal(Names.normName('Mź7w'), 'mz7w');
});

test('affinity sums each name best match against the roster', () => {
  const roster = ['Kirbz', 'Vega'];
  assert.equal(Names.affinity(['Kirbz'], roster), 100);
  assert.equal(Names.affinity([], roster), 0);
});

test('confidentOrientation returns null when the sides are indistinguishable', () => {
  const r = ['One', 'Two'];
  assert.equal(Names.confidentOrientation(r, r, r, r), null);
});

test('confidentOrientation picks the direct orientation when the left side matches roster a', () => {
  const ours = ['Alison', 'Sivaartt', 'Kroxz', 'Zorrow', 'Benislover'];
  const theirs = ['One', 'Two', 'Three', 'Four', 'Five'];
  assert.equal(Names.confidentOrientation(ours, theirs, ours, theirs), 'a');
});

test('confidentOrientation detects a swap', () => {
  const ours = ['Alison', 'Sivaartt', 'Kroxz', 'Zorrow', 'Benislover'];
  const theirs = ['One', 'Two', 'Three', 'Four', 'Five'];
  assert.equal(Names.confidentOrientation(theirs, ours, ours, theirs), 'b');
});

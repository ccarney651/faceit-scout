// node --test docs/capture/replaycode.test.js
//
// The decision the league capture page makes on a map's FIRST snapshot: does
// the code on screen agree with the match the operator picked to scout? It is
// pure - a read, the division's feed, and the current selection in, a verdict
// out - so it belongs here rather than inside the page, where it could only be
// exercised through a browser and an OCR pass.
const test = require('node:test');
const assert = require('node:assert');
const RC = require('./engine/replaycode.js');

// A division's feed. Real codes from faceit.sqlite3's alphabet: Crockford
// Base32, six characters, no I/L/O/U.
const FEED = [
  { code: 'D9X9N2', team_a: 'Alpha', team_b: 'Bravo' },
  { code: 'B4K2M1', team_a: 'Delta', team_b: 'Echo' },
  { code: 'H6R64B', team_a: 'Foxtrot', team_b: 'Golf' },
];

test('the code on screen is the one selected', () => {
  const r = RC.checkAgainstSelected('B4K2M1', FEED, 'B4K2M1');
  assert.equal(r.status, 'ok');
  assert.equal(r.code, 'B4K2M1');
});

test('a different code from the same feed is a mismatch, and names both', () => {
  const r = RC.checkAgainstSelected('D9X9N2', FEED, 'B4K2M1');
  assert.equal(r.status, 'mismatch');
  assert.equal(r.code, 'D9X9N2', 'the code the screen is showing');
  assert.equal(r.selected, 'B4K2M1', 'the code the operator picked');
});

// A one-character miss is recoverable BECAUSE the feed exists: there is a right
// answer to compare against, which is what makes the league read trustworthy
// where the scrim read is not.
test('a near miss that folds to the selected code passes silently', () => {
  // B4K2M1 misread with one wrong character.
  const r = RC.checkAgainstSelected('B4K2M7', FEED, 'B4K2M1');
  assert.equal(r.status, 'ok');
  assert.equal(r.code, 'B4K2M1');
  assert.equal(r.near, true, 'it passed on a near match, not an exact one');
});

test('a near miss that folds to a DIFFERENT code still blocks', () => {
  // One character off D9X9N2, nothing else in the feed is close.
  const r = RC.checkAgainstSelected('D9X9N3', FEED, 'B4K2M1');
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
  const r = RC.checkAgainstSelected('D9X9N4', feed, 'B4K2M1');
  assert.equal(r.status, 'abstain');
  assert.equal(r.code, null);
});

test('a read that is in no feed code abstains, and does not block capture', () => {
  const r = RC.checkAgainstSelected('ZZZZZZ', FEED, 'B4K2M1');
  assert.equal(r.status, 'abstain');
});

test('a failed OCR read abstains', () => {
  for (const bad of [null, '', undefined]) {
    assert.equal(RC.checkAgainstSelected(bad, FEED, 'B4K2M1').status, 'abstain',
      'a read of ' + JSON.stringify(bad) + ' must not block capture');
  }
});

// Nothing selected means there is nothing to disagree with. The page gates
// capture on a selected code elsewhere; this must not invent a second opinion.
test('no selection abstains', () => {
  assert.equal(RC.checkAgainstSelected('D9X9N2', FEED, null).status, 'abstain');
});

test('an empty feed abstains rather than calling everything a mismatch', () => {
  assert.equal(RC.checkAgainstSelected('D9X9N2', [], 'B4K2M1').status, 'abstain');
  assert.equal(RC.checkAgainstSelected('D9X9N2', null, 'B4K2M1').status, 'abstain');
});

// The selected code not being in the feed is a page bug, not an operator error,
// and blocking on it would accuse the operator of something they did not do.
test('a selection missing from the feed abstains', () => {
  assert.equal(RC.checkAgainstSelected('D9X9N2', FEED, 'QQQQQQ').status, 'abstain');
});

// Codes differing in length are not one character apart in any useful sense -
// the Hamming walk in the matcher requires equal lengths.
test('a read of the wrong length never matches', () => {
  assert.equal(RC.checkAgainstSelected('D9X9N', FEED, 'B4K2M1').status, 'abstain');
  assert.equal(RC.checkAgainstSelected('D9X9N22', FEED, 'B4K2M1').status, 'abstain');
});

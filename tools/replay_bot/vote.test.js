const test = require('node:test');
const assert = require('node:assert');
const V = require('./vote.js');

const reading = (name, score) => ({ name: name, score: score });

test('a unanimous slot returns its hero with full support', () => {
  const got = V.slot([reading('Sojourn', 0.85), reading('Sojourn', 0.83), reading('Sojourn', 0.86)]);
  assert.strictEqual(got.name, 'Sojourn');
  assert.strictEqual(got.support, 1);
});

// Why this exists, stated honestly: on the one frame measured so far the bot
// agreed with the capture page on all ten slots, so this is not fixing an
// observed error. It is insurance for an unattended run over hundreds of maps,
// and it is nearly free - the sweep already samples a slot many times per
// round, which a human snapshotting once per round never does.
//
// It also cannot be replaced by a confidence threshold. Correct reads on the
// red plate ran as low as 0.805, so any cut-off strict enough to reject a bad
// read would reject good ones too. Repetition separates them; a number does not.
test('a lone misread is outvoted by the frames around it', () => {
  const readings = [];
  for (let i = 0; i < 11; i++) readings.push(reading('Sojourn', 0.85));
  readings.splice(4, 0, reading('Freja', 0.805));

  const got = V.slot(readings);
  assert.strictEqual(got.name, 'Sojourn');
  assert.ok(got.support > 0.9, `support should be high, got ${got.support}`);
});

test('support reports the share of frames that agreed', () => {
  const got = V.slot([reading('Ana', 0.9), reading('Ana', 0.9), reading('Kiriko', 0.9), reading('Ana', 0.9)]);
  assert.strictEqual(got.name, 'Ana');
  assert.strictEqual(got.support, 0.75);
});

// A slot genuinely split down the middle is a real hero swap, not noise, and
// the caller must be able to tell that apart from a confident read.
test('an even split is reported as contested rather than resolved silently', () => {
  const got = V.slot([reading('Ana', 0.9), reading('Ana', 0.9), reading('Kiriko', 0.9), reading('Kiriko', 0.9)]);
  assert.strictEqual(got.support, 0.5);
  assert.strictEqual(got.contested, true);
});

test('a clear winner is not marked contested', () => {
  const got = V.slot([reading('Ana', 0.9), reading('Ana', 0.9), reading('Ana', 0.9), reading('Kiriko', 0.9)]);
  assert.strictEqual(got.contested, false);
});

test('an empty slot yields nothing rather than throwing', () => {
  const got = V.slot([]);
  assert.strictEqual(got.name, null);
  assert.strictEqual(got.support, 0);
});

// Ties must not depend on object key order or input order, or two runs over the
// same replay could disagree.
test('a tie resolves deterministically by name', () => {
  const a = V.slot([reading('Zenyatta', 0.9), reading('Ana', 0.9)]);
  const b = V.slot([reading('Ana', 0.9), reading('Zenyatta', 0.9)]);
  assert.strictEqual(a.name, b.name);
  assert.strictEqual(a.name, 'Ana');
});

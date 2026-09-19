const test = require('node:test');
const assert = require('node:assert');
const G = require('./refsgate.js');

// A reference library shaped like docs/capture/refs.json, small enough to read.
function library(over) {
  return Object.assign({
    w: 64,
    h: 36,
    left_fraction: 0.42,
    top_fraction: 0.45,
    right_fraction: 0.06,
    refs: [
      { n: 'Ana', v: 'a', d: 'AAAA' },
      { n: 'Ana', v: 'b', d: 'BBBB' },
      { n: 'Cassidy', v: 'a', d: 'CCCC' },
    ],
  }, over);
}

function passingRecord(lib) {
  return { fingerprint: G.fingerprint(lib), passed_at: '2026-09-19T12:00:00Z' };
}

test('the same library fingerprints the same way twice', () => {
  assert.strictEqual(G.fingerprint(library()), G.fingerprint(library()));
});

// The 2026-09-15 regression changed every descriptor and nothing else - no
// hero appeared or vanished, so only the payload itself can give it away.
test('a changed descriptor changes the fingerprint', () => {
  const reverted = library({
    refs: [
      { n: 'Ana', v: 'a', d: 'AAAA' },
      { n: 'Ana', v: 'b', d: 'BBBB' },
      { n: 'Cassidy', v: 'a', d: 'ZZZZ' },
    ],
  });
  assert.notStrictEqual(G.fingerprint(library()), G.fingerprint(reverted));
});

// A library can be rebuilt against a different crop box with identical
// descriptors; that is the profile-4 incident, and it must not read as "same".
test('changed crop geometry changes the fingerprint', () => {
  assert.notStrictEqual(
    G.fingerprint(library()),
    G.fingerprint(library({ right_fraction: 0.08 })),
  );
});

test('adding a hero changes the fingerprint', () => {
  const withDoctrine = library({
    refs: library().refs.concat([{ n: 'Doctrine', v: 'a', d: 'DDDD' }]),
  });
  assert.notStrictEqual(G.fingerprint(library()), G.fingerprint(withDoctrine));
});

test('the order refs are listed in does not change the fingerprint', () => {
  const shuffled = library({ refs: library().refs.slice().reverse() });
  assert.strictEqual(G.fingerprint(library()), G.fingerprint(shuffled));
});

test('the gate passes when the library is the one the sweep passed on', () => {
  const lib = library();
  const verdict = G.check(lib, passingRecord(lib));
  assert.strictEqual(verdict.ok, true);
});

test('the gate refuses when the library changed since the sweep passed', () => {
  const verdict = G.check(library({ right_fraction: 0.08 }), passingRecord(library()));
  assert.strictEqual(verdict.ok, false);
  assert.match(verdict.reason, /refs\.json has changed/i);
});

test('the gate refuses when no sweep has ever passed', () => {
  const verdict = G.check(library(), null);
  assert.strictEqual(verdict.ok, false);
  assert.match(verdict.reason, /match_accuracy_sweep/);
});

// The whole point is that the operator can act on the refusal without
// going and reading this file.
test('a refusal names the sweep that clears it', () => {
  const verdict = G.check(library({ right_fraction: 0.08 }), passingRecord(library()));
  assert.match(verdict.reason, /match_accuracy_sweep/);
});

const test = require('node:test');
const assert = require('node:assert');
const S = require('./segment.js');

// In production a hero is a GUID ("0x02E00000000001EC", or "custom:d_mon" for
// an operator-added one), never a display name. Segmentation only ever compares
// and unions these as opaque strings, so readable names are used here to keep
// failures legible - if that ever stops being true, these fixtures must change
// to guids first.
const DIVE = ['Winston', 'D.Va', 'Tracer', 'Genji', 'Lucio'];
const POKE = ['Sigma', 'Orisa', 'Widowmaker', 'Ashe', 'Baptiste'];

// One sample of the sweep, as sweep.js appends it.
function obs(over) {
  return Object.assign({
    t: 0,
    clock: '9:57',
    score_a: 0,
    score_b: 0,
    heroes_a: DIVE.slice(),
    heroes_b: POKE.slice(),
  }, over);
}

test('a sweep with no score change is a single round', () => {
  const rounds = S.rounds([
    obs({ t: 0 }), obs({ t: 30 }), obs({ t: 60 }),
  ], { mapCategory: 'Control' });
  assert.strictEqual(rounds.length, 1);
});

// The pool is the whole point of sampling inside a round rather than only at
// its boundaries: it is what catches a swap the opening comp cannot show.
test('a hero swapped in mid-round joins the pool but not the opening comp', () => {
  const rounds = S.rounds([
    obs({ t: 0, heroes_a: DIVE.slice() }),
    obs({ t: 30, heroes_a: ['Reinhardt'].concat(DIVE.slice(1)) }),
  ], { mapCategory: 'Control' });
  assert.ok(rounds[0].pool.a.includes('Reinhardt'), 'swap should reach the pool');
  assert.ok(!rounds[0].opening.a.includes('Reinhardt'), 'swap must not rewrite the opener');
  assert.strictEqual(rounds[0].pool.a.length, 6);
});

test('a side that never swapped has a pool of exactly its five', () => {
  const rounds = S.rounds([obs({ t: 0 }), obs({ t: 30 })], { mapCategory: 'Control' });
  assert.deepStrictEqual(rounds[0].pool.b, POKE.slice().sort());
});

test('a score change ends the round and starts the next', () => {
  const rounds = S.rounds([
    obs({ t: 0, score_a: 0, score_b: 0 }),
    obs({ t: 30, score_a: 0, score_b: 0 }),
    obs({ t: 60, score_a: 1, score_b: 0 }),
    obs({ t: 90, score_a: 1, score_b: 0 }),
  ], { mapCategory: 'Control' });
  assert.strictEqual(rounds.length, 2);
  assert.deepStrictEqual([rounds[0].from_t, rounds[0].to_t], [0, 30]);
  assert.deepStrictEqual([rounds[1].from_t, rounds[1].to_t], [60, 90]);
});

test('each side scoring separately makes three rounds, not two', () => {
  const rounds = S.rounds([
    obs({ t: 0, score_a: 0, score_b: 0 }),
    obs({ t: 30, score_a: 1, score_b: 0 }),
    obs({ t: 60, score_a: 1, score_b: 1 }),
  ], { mapCategory: 'Control' });
  assert.strictEqual(rounds.length, 3);
});

test("a round's opening comp is the heroes at its first sample", () => {
  const rounds = S.rounds([
    obs({ t: 0, heroes_a: DIVE.slice() }),
    obs({ t: 30, heroes_a: ['Reinhardt'].concat(DIVE.slice(1)) }),
  ], { mapCategory: 'Control' });
  assert.deepStrictEqual(rounds[0].opening.a, DIVE);
});

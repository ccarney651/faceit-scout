const test = require('node:test');
const assert = require('node:assert');
const S = require('./screen.js');

const flat = (v) => new Array(S.W * S.H).fill(v);

test('the same picture is the same screen', () => {
  assert.strictEqual(S.distance(flat(100), flat(100)), 0);
  assert.strictEqual(S.looksLike(flat(100), flat(100)).same, true);
});

test('a different picture is not', () => {
  assert.strictEqual(S.looksLike(flat(20), flat(200)).same, false);
});

// "No fingerprint" must never read as "matches" - a chunk with nothing stored
// would otherwise be judged safe to play on any screen at all.
test('a missing fingerprint is unknown, not a match', () => {
  assert.strictEqual(S.distance(null, flat(100)), null);
  assert.deepStrictEqual(S.looksLike(null, flat(100)), { known: false, same: false, distance: null });
  assert.strictEqual(S.looksLike(flat(100), []).known, false);
});

test('fingerprints of different sizes are not comparable', () => {
  assert.strictEqual(S.distance([1, 2, 3], [1, 2]), null);
});

// The numbers this is built on, measured on real frames from the run where the
// bot clicked into the ESC menu:
//
//   two ESC-menu frames      3.4     the same screen
//   ESC menu vs a replay    82.0     different
//   ESC menu vs loading     29.0     different
//   TWO REPLAY FRAMES       55.1     ALSO different
//
// That last one is why this is used for menus only. A replay is a moving
// picture of a different map every time; "is this a replay" is answered by the
// team plates instead (calib.hudPresent).
test('the tolerance sits between the same menu and a different screen', () => {
  assert.ok(S.SAME > 3.4, 'two frames of one menu must match');
  assert.ok(S.SAME < 29.0, 'a menu must not match a loading screen');
});

test('a thumbnail is coarse enough to survive a moved mouse', () => {
  assert.ok(S.W * S.H <= 32 * 18, 'a whole screen in under 600 cells');
});

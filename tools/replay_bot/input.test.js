const test = require('node:test');
const assert = require('node:assert');
const I = require('./input.js');

test('a successful send reports how many keys went out', () => {
  const got = I.parse('SENT 4 keys\n');
  assert.strictEqual(got.ok, true);
  assert.strictEqual(got.n, 4);
});

test('a refusal to foreground is a failure, not a silent no-op', () => {
  const got = I.parse('ERR could not foreground Overwatch');
  assert.strictEqual(got.ok, false);
  assert.match(got.reason, /foreground/);
});

test('an unknown key is reported rather than swallowed', () => {
  const got = I.parse('ERR unknown key Q');
  assert.strictEqual(got.ok, false);
  assert.match(got.reason, /unknown key Q/);
});

test('output with no contract line is a failure', () => {
  assert.strictEqual(I.parse('').ok, false);
});

// Settling. The UI shifts into place for under a second after a seek, so the
// bot waits for two consecutive frames to agree rather than trusting a fixed
// delay - the delay that is long enough on a good day is not on a bad one.
test('settle returns as soon as two frames agree', async () => {
  let calls = 0;
  const settle = I.makeSettle({
    grab: async () => `f${calls++}`,
    diff: async (a, b) => (a === 'f0' || b === 'f1' ? 99 : 0),
    threshold: 1,
    maxTries: 10,
    waitMs: 0,
  });
  const got = await settle();
  assert.strictEqual(got.settled, true);
  assert.ok(calls < 10, 'should stop early once stable, not exhaust its tries');
});

test('settle gives up rather than hanging on a screen that never stops moving', async () => {
  const settle = I.makeSettle({
    grab: async () => 'x',
    diff: async () => 999,
    threshold: 1,
    maxTries: 3,
    waitMs: 0,
  });
  const got = await settle();
  assert.strictEqual(got.settled, false);
  assert.strictEqual(got.tries, 3);
});

test('settle reports the motion it finally saw, for diagnosis', async () => {
  const settle = I.makeSettle({
    grab: async () => 'x',
    diff: async () => 0.4,
    threshold: 1,
    maxTries: 5,
    waitMs: 0,
  });
  const got = await settle();
  assert.strictEqual(got.settled, true);
  assert.strictEqual(got.motion, 0.4);
});

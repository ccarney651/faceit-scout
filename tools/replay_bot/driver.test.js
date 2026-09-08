const test = require('node:test');
const assert = require('node:assert');
const D = require('./driver.js');

const STEP = 20;
const count = (plan, key) => plan.filter((k) => k === key).length;

test('seeking forward is that many presses of the forward key', () => {
  assert.deepStrictEqual(D.seekPlan(0, 100, STEP), ['X', 'X', 'X', 'X', 'X']);
});

test('seeking forward from a known position only covers the difference', () => {
  assert.deepStrictEqual(D.seekPlan(100, 160, STEP), ['X', 'X', 'X']);
});

test('already there costs nothing', () => {
  assert.deepStrictEqual(D.seekPlan(100, 100, STEP), []);
});

// Position is unknown when a replay has just opened. Guessing it would put
// every later sample in the wrong place, so an unknown origin always restarts
// from a known one.
test('an unknown position restarts from the beginning', () => {
  const plan = D.seekPlan(null, 60, STEP);
  assert.strictEqual(plan[0], 'B', 'must jump to start first');
  assert.strictEqual(count(plan, 'X'), 3);
});

test('a short step backwards uses the back key', () => {
  const plan = D.seekPlan(200, 100, STEP);
  assert.deepStrictEqual(plan, ['Z', 'Z', 'Z', 'Z', 'Z']);
});

// Rewinding from late in a long map costs far more presses than starting over.
// Each press is a round trip to the game, so the cheaper route matters.
test('a long step backwards restarts instead of rewinding', () => {
  const plan = D.seekPlan(1000, 20, STEP);
  assert.deepStrictEqual(plan, ['B', 'X']);
});

test('the cheaper of the two routes is always chosen', () => {
  const back = D.seekPlan(400, 300, STEP);
  const restart = D.seekPlan(400, 20, STEP);
  assert.ok(back.length <= 5, 'small rewind stays a rewind');
  assert.ok(restart[0] === 'B', 'big rewind restarts');
});

// Driving the whole plan through an injected sender, so the sequencing is
// verified without a single keystroke reaching the game.
test('a whole sample plan is driven in order, from a known origin', async () => {
  const sent = [];
  const drv = D.make({
    send: async (k) => { sent.push(k); },
    focus: async () => { sent.push('<focus>'); },
    settle: async () => {},
  });

  await drv.seekTo(40);
  await drv.seekTo(100);

  assert.strictEqual(sent[0], '<focus>', 'focus is taken before any key');
  assert.strictEqual(sent[1], 'B', 'first seek restarts from a known origin');
  assert.strictEqual(count(sent, 'X'), 5, '2 presses then 3 more, not 2 then 5');
});

test('the driver remembers where it is between seeks', async () => {
  const sent = [];
  const drv = D.make({ send: async (k) => sent.push(k), focus: async () => {}, settle: async () => {} });
  await drv.seekTo(40);
  assert.strictEqual(drv.position(), 40);
  await drv.seekTo(100);
  assert.strictEqual(drv.position(), 100);
});

// The UI shifts into place for a moment after a seek. Grabbing during that
// window reads a HUD mid-transition, so the driver must wait for it.
test('the driver settles after seeking, before anything reads the screen', async () => {
  const order = [];
  const drv = D.make({
    send: async (k) => order.push('key:' + k),
    focus: async () => {},
    settle: async () => order.push('settle'),
  });
  await drv.seekTo(40);
  assert.strictEqual(order[order.length - 1], 'settle', 'settle comes last');
});

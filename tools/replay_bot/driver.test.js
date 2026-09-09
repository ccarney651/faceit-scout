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
  const spawns = [];
  const drv = D.make({
    // One call per seek, carrying the whole key sequence - a spawn per key
    // would cost ~800ms each and make a 50-press seek take 40 seconds.
    sendKeys: async (keys) => { spawns.push(keys); keys.forEach((k) => sent.push(k)); },
    focus: async () => { sent.push('<focus>'); },
    settle: async () => {},
  });

  await drv.seekTo(40);
  await drv.seekTo(100);

  assert.strictEqual(sent[0], '<focus>', 'focus is taken before any key');
  assert.strictEqual(sent[1], 'B', 'first seek restarts from a known origin');
  assert.strictEqual(count(sent, 'X'), 5, '2 presses then 3 more, not 2 then 5');
  assert.strictEqual(spawns.length, 2, 'one batched call per seek, not one per key');
});

test('the driver remembers where it is between seeks', async () => {
  const sent = [];
  const drv = D.make({ sendKeys: async (ks) => ks.forEach((k) => sent.push(k)), focus: async () => {}, settle: async () => {} });
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
    sendKeys: async (ks) => ks.forEach((k) => order.push('key:' + k)),
    focus: async () => {},
    settle: async () => order.push('settle'),
  });
  await drv.seekTo(40);
  assert.strictEqual(order[order.length - 1], 'settle', 'settle comes last');
});

// The events viewer is a toggle, and the first live run read a wrong timeline
// because it was closed. These pin the "measure, then press at most once"
// rule: pressing when it is already open would close it, and pressing twice
// would put it back where it started.
test('an already-open events viewer is left alone', async () => {
  let presses = 0;
  const got = await D.ensureEventsViewer({
    read: async () => 0.755,
    isOpen: (f) => f >= 0.5,
    toggle: async () => { presses++; },
  });
  assert.strictEqual(presses, 0, 'a press would have closed it');
  assert.deepStrictEqual([got.open, got.pressed], [true, false]);
});

test('a closed events viewer is opened with one press', async () => {
  let presses = 0;
  const reads = [0.211, 0.755];
  const got = await D.ensureEventsViewer({
    read: async () => reads.shift(),
    isOpen: (f) => f >= 0.5,
    toggle: async () => { presses++; },
  });
  assert.strictEqual(presses, 1, 'exactly one press, since K toggles');
  assert.deepStrictEqual([got.open, got.pressed], [true, true]);
});

// A panel that does not open must be reported, not pressed at again. The
// caller stops the map: a closed panel means the scrubber shows no round
// breaks, and the timeline read would be confidently wrong.
test('a viewer that will not open is reported rather than retried', async () => {
  let presses = 0;
  const got = await D.ensureEventsViewer({
    read: async () => 0.211,
    isOpen: (f) => f >= 0.5,
    toggle: async () => { presses++; },
  });
  assert.strictEqual(presses, 1, 'one press, then give up');
  assert.strictEqual(got.open, false);
  assert.strictEqual(got.after, 0.211, 'reports what it measured');
});

test('the events key is K, and pressing it settles like a seek', async () => {
  const order = [];
  const drv = D.make({
    sendKeys: async (ks) => ks.forEach((k) => order.push('key:' + k)),
    focus: async () => {},
    settle: async () => order.push('settle'),
  });
  await drv.eventsViewer();
  assert.deepStrictEqual(order, ['key:K', 'settle']);
});

// --- seeks are checked, not trusted --------------------------------------
//
// The client ignores a seek key that arrives while it is still seeking, so a
// batch can silently land short. Every later sample then sits somewhere the
// bot does not know about, and nothing in the output looks wrong.

function driverAt(positions, sent) {
  return D.make({
    sendKeys: async (ks) => ks.forEach((k) => sent.push(k)),
    focus: async () => {},
    settle: async () => {},
    position: async () => positions.shift(),
    stepS: 20,
  });
}

test('a seek that lands where it was asked to is not corrected', async () => {
  const sent = [];
  const drv = driverAt([100], sent);
  assert.strictEqual(await drv.seekTo(100), 100);
  assert.strictEqual(sent.filter((k) => k === 'X').length, 5, 'five presses, no more');
});

test('a seek that lands short is corrected by the shortfall', async () => {
  const sent = [];
  const drv = driverAt([60, 100], sent);       // landed at 60, then correct
  assert.strictEqual(await drv.seekTo(100), 100);
  assert.strictEqual(sent.filter((k) => k === 'X').length, 7, '5 asked, then 2 more');
});

// Believing the target after correction fails is the failure mode that started
// all this: the bot reported 14:40 and was at 1:42.
test('a seek that cannot be corrected reports where it actually is', async () => {
  const sent = [];
  const drv = driverAt([20, 20, 20, 20, 20], sent);
  const got = await drv.seekTo(200);
  assert.strictEqual(got, 20, 'the measurement wins, not the intent');
  assert.strictEqual(drv.position(), 20);
});

test('correction gives up rather than pressing forever', async () => {
  const sent = [];
  const drv = D.make({
    sendKeys: async (ks) => ks.forEach((k) => sent.push(k)),
    focus: async () => {},
    settle: async () => {},
    position: async () => 20,
    maxCorrections: 2,
    stepS: 20,
  });
  await drv.seekTo(200);
  const batches = sent.filter((k) => k === 'B').length;
  assert.ok(batches <= 3, 'one attempt plus two corrections, then stop');
});

// A frame with no readable playhead is not a reason to invent a position, but
// it is also not a reason to stop: the caller decides.
test('an unreadable playhead falls back to the requested position', async () => {
  const sent = [];
  const drv = driverAt([null], sent);
  assert.strictEqual(await drv.seekTo(100), 100);
});

test('without a position reader the driver behaves as it always did', async () => {
  const sent = [];
  const drv = D.make({
    sendKeys: async (ks) => ks.forEach((k) => sent.push(k)),
    focus: async () => {},
    settle: async () => {},
  });
  await drv.seekTo(40);
  assert.deepStrictEqual(sent, ['B', 'X', 'X']);
});

// --- N then K, and the verdict is the change ------------------------------
//
// The media controls have to be up before the events viewer will open, so N is
// pressed every time. A run that pressed only K measured 0.023 before and
// 0.023 after: the key did nothing at all, and the map was refused.

function viewerCtx(opts) {
  const o = opts || {};
  const reads = o.reads.slice();
  const log = [];
  return {
    log,
    ctx: {
      read: async () => (reads.length > 1 ? reads.shift() : reads[0]),
      isOpen: (f) => f >= 0.35,
      mediaVisible: o.mediaVisible === undefined ? undefined : async () => o.mediaVisible(),
      showMedia: async () => { log.push('N'); },
      toggle: async () => { log.push('K'); },
    },
  };
}

test('the media controls are shown before the events viewer is toggled', async () => {
  const v = viewerCtx({ reads: [0.0, 0.6], mediaVisible: () => true });
  const got = await D.ensureEventsViewer(v.ctx);
  assert.deepStrictEqual(v.log, ['N', 'K'], 'N first, every time');
  assert.strictEqual(got.open, true);
  assert.deepStrictEqual(got.steps, ['N', 'K']);
});

// A quick-play escort is one round, so its events panel is nearly empty and an
// OPEN one reads dimmer (0.252) than a CLOSED panel on a busy Control map
// (0.211). No level can separate those; the rise can.
test('a press that raises the panel counts as open below the level', async () => {
  const v = viewerCtx({ reads: [0.0, 0.252], mediaVisible: () => true });
  const got = await D.ensureEventsViewer(v.ctx);
  assert.strictEqual(got.open, true, '0.252 is under the 0.35 level but rose 0.252');
  assert.ok(Math.abs(got.rose - 0.252) < 1e-9);
});

test('a press that changes nothing is still a closed viewer', async () => {
  const v = viewerCtx({ reads: [0.023, 0.023], mediaVisible: () => true });
  const got = await D.ensureEventsViewer(v.ctx);
  assert.strictEqual(got.open, false, 'exactly what the failed run measured');
});

// N is a toggle: pressing it when the controls are already up hides them, and
// then K has nothing to open.
test('N going the wrong way is pressed again to put it back', async () => {
  let up = false;
  const v = viewerCtx({ reads: [0.0, 0.6] });
  v.ctx.mediaVisible = async () => { const was = up; up = true; return was; };
  const got = await D.ensureEventsViewer(v.ctx);
  assert.deepStrictEqual(v.log, ['N', 'N', 'K'], 'a second N restores the controls');
  assert.deepStrictEqual(got.steps, ['N', 'N again', 'K']);
});

test('controls that will not show mean K is never pressed', async () => {
  const v = viewerCtx({ reads: [0.0, 0.0], mediaVisible: () => false });
  const got = await D.ensureEventsViewer(v.ctx);
  assert.strictEqual(got.open, false);
  assert.ok(!v.log.includes('K'), 'nothing to open, so nothing is pressed at it');
  assert.match(got.reason, /media controls/);
});

test('an already-open viewer needs neither key', async () => {
  const v = viewerCtx({ reads: [0.755], mediaVisible: () => true });
  const got = await D.ensureEventsViewer(v.ctx);
  assert.deepStrictEqual(v.log, [], 'no press at all');
  assert.strictEqual(got.open, true);
});

test('showing the media controls settles, like every other UI move', async () => {
  const order = [];
  const drv = D.make({
    sendKeys: async (ks) => ks.forEach((k) => order.push('key:' + k)),
    focus: async () => {},
    settle: async () => order.push('settle'),
  });
  await drv.mediaControls();
  assert.deepStrictEqual(order, ['key:N', 'settle']);
});

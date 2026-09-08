const test = require('node:test');
const assert = require('node:assert');
const Sweep = require('./sweep.js');

// A driver that records where it was told to seek instead of touching a game.
// This is the seam the real driver.js plugs into; nothing in sweep.js knows
// whether a replay or a directory of PNGs is on the other side.
function fakeDriver() {
  const seeks = [];
  return {
    seeks,
    async seekTo(t) { seeks.push(t); },
    async close() {},
  };
}

// `reads` maps a timestamp to what the HUD reader returned there; anything not
// listed reads as null, which is how an unreadable frame arrives.
function fakeRead(reads) {
  return async function (frame, t) {
    return Object.prototype.hasOwnProperty.call(reads, t) ? reads[t] : null;
  };
}

const ok = { clock: '9:57', score_a: 0, score_b: 0, heroes_a: [], heroes_b: [] };

async function grab() { return { fake: true }; }

test('the sweep samples on a fixed interval', async () => {
  const driver = fakeDriver();
  await Sweep.run({
    driver, grab, read: fakeRead({ 0: ok, 30: ok, 60: ok }),
    intervalS: 30, maxInvalid: 2, capS: 300,
  });
  assert.deepStrictEqual(driver.seeks.slice(0, 3), [0, 30, 60]);
});

test('a sample keeps the timestamp it was taken at', async () => {
  const obs = await Sweep.run({
    driver: fakeDriver(), grab, read: fakeRead({ 0: ok, 30: ok }),
    intervalS: 30, maxInvalid: 2, capS: 300,
  });
  assert.deepStrictEqual(obs.map((o) => o.t), [0, 30]);
});

// The replay ran out. Without this the sweep would seek to the cap on every
// map, spending minutes of client time past the end of every one.
test('consecutive unreadable frames end the sweep', async () => {
  const driver = fakeDriver();
  const obs = await Sweep.run({
    driver, grab, read: fakeRead({ 0: ok, 30: ok }),
    intervalS: 30, maxInvalid: 2, capS: 3000,
  });
  assert.strictEqual(obs.length, 2, 'only the readable frames are kept');
  assert.ok(driver.seeks.length < 10, 'should stop early, not run to the cap');
});

// A single dropped frame mid-map - a killcam, a scoreboard overlay - must not
// be mistaken for the end of the replay.
test('one unreadable frame between good ones does not end the sweep', async () => {
  const obs = await Sweep.run({
    driver: fakeDriver(), grab, read: fakeRead({ 0: ok, 60: ok }),
    intervalS: 30, maxInvalid: 2, capS: 300,
  });
  assert.deepStrictEqual(obs.map((o) => o.t), [0, 60]);
});

test('the cap stops a replay whose frames never stop reading', async () => {
  const driver = fakeDriver();
  const reads = {};
  for (let t = 0; t <= 1000; t += 30) reads[t] = ok;
  const obs = await Sweep.run({
    driver, grab, read: fakeRead(reads),
    intervalS: 30, maxInvalid: 2, capS: 90,
  });
  assert.ok(obs.every((o) => o.t <= 90), 'nothing past the cap');
});

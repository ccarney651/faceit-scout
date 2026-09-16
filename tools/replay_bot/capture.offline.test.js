// The capture's refusals, run against recorded frames instead of a live client.
//
// EVERY ONE OF THESE COST A REPLAY CODE TO FIND, AND A CODE IMPORTS ONCE. What
// they have in common is that the client was not where the code assumed and the
// code carried on anyway; what they now have in common is that they are
// reproducible for nothing, from frames already on disk. See fakeio.js.
const test = require('node:test');
const assert = require('node:assert');
const canvas = require('@napi-rs/canvas');
const C = require('./capture.js');
const F = require('./fakeio.js');
const P = require('./phases.js');
const Corpus = require('./corpus.js');

const skip = Corpus.absent() || false;

// The guards all refuse long before anything is matched, and building the real
// matcher means reading the whole reference library off disk.
const NO_MATCHER = { read: () => ({ a: [], b: [] }) };
const run = (io, opts) => C.make(io).captureMap(Object.assign({ matcher: NO_MATCHER }, opts));

test('a frame that is not the frozen resolution is refused before a key is pressed', async () => {
  const io = F.make({ screen: canvas.createCanvas(1920, 1080) });
  await assert.rejects(run(io), /calibration smoke check failed.*1920x1080/);
  assert.deepStrictEqual(io.keys, [], 'nothing may be pressed at a geometry it cannot read');
});

// A replay opens PLAYING, and every reading after this point assumes a still
// picture. SPACE is a toggle, so the press is measured rather than trusted.
test('a replay that will not stop is refused rather than read while it moves', { skip }, async () => {
  const still = Corpus.file('panel-shut-bright');
  const moving = [still, Corpus.file('assemble')];
  let n = 0;
  const io = F.make({ screen: (c) => (c.tag === 'pause' ? moving[n++ % 2] : still) });

  await assert.rejects(run(io), /the replay will not stop/);
  assert.deepStrictEqual(io.keys, ['SPACE'], 'pressed once, then believed the picture');
  assert.ok(io.slept > 0, 'the waits are still made, they are just not served');
});

// N THEN K, IN THAT ORDER AND EVERY TIME. The media controls have to be up
// before the events viewer will open; a run that pressed only K sat at 0.023
// before and after, having done nothing.
test('the panel is refused when K does not open it, and N went first', { skip }, async () => {
  const io = F.make({ screen: Corpus.file('panel-shut-bright') });

  await assert.rejects(run(io), /events viewer would not open/);
  assert.deepStrictEqual(io.keys, ['N', 'K']);
});

// K is a toggle too, so a panel that is already open must be left alone - the
// press that "makes sure" is the press that shuts it.
test('an open panel is not toggled, and the run goes on to the bar', { skip }, async () => {
  const io = F.make({ screen: Corpus.file('panel-open') });

  // One frame cannot move, so the forward key looks broken - which is the next
  // guard along, and exactly where this run should get to.
  await assert.rejects(run(io), /the forward key is not working/);
  assert.deepStrictEqual(io.keys, ['N', 'B', 'X'], 'no K: the panel was already open');
});

// The skip-interval chunk walks through the client's options menu, and a trip
// through a menu can leave the events panel shut behind it. The check that
// catches that was comparing a ROW FRACTION against a BRIGHTNESS FRACTION -
// two different units, one threshold - which could as easily have pressed K on
// an open panel and shut it.
test('a panel the options menu shut is reopened', { skip }, async () => {
  const open = Corpus.at('probe-panelopen-live.png');
  const shut = Corpus.at('probe-panelshut-live.png');
  let throughMenu = false;
  const io = F.make({
    screen: (c) => {
      if (!throughMenu) return open;
      return c.keys.filter((k) => k === 'K').length ? open : shut;
    },
  });

  await assert.rejects(run(io, { afterViewer: async () => { throughMenu = true; } }),
    /the forward key is not working/);
  assert.strictEqual(io.keys.filter((k) => k === 'K').length, 1,
    'K once, to reopen what the menu shut - and not once more');
});

test('a panel the options menu left alone is not touched', { skip }, async () => {
  const io = F.make({ screen: Corpus.at('probe-panelopen-live.png') });

  await assert.rejects(run(io, { afterViewer: async () => {} }),
    /the forward key is not working/);
  assert.deepStrictEqual(io.keys, ['N', 'B', 'X'], 'no K on a panel that stayed open');
});

// CHANGE-DETECTION RETENTION, run against recorded frames. captureMap's full
// pipeline cannot be driven offline - the bar calibration needs a knob that
// moves, and one frame cannot move - so this drives the per-visit code that
// DID change (phases.sampleAt) across a whole map's worth of visits, mirroring
// captureMap's bookkeeping exactly: prev/prevPrev baseline, reset and first-of-
// round flag at round boundaries, and only a kept frame hitting keepAs. The
// frame on screen is the corpus HUD; the reads come from a stub matcher, so the
// assertion is about the RETENTION POLICY (stored count = distinct comp states,
// not visit count), not the OCR.
const GUID_A = ['noki', 'vilp', 'jopez', 'lamb', 'karhu'];
const GUID_B = ['noki', 'vilp', 'SWAP', 'lamb', 'karhu'];
function readOf(guids) {
  const side = (gs) => gs.map((g) => ({ name: g, guid: g, score: 0.9 }));
  return { a: side(guids), b: side(guids) };
}

// visits: [{ t, read, firstOfRound }] - one per 30s-grid point of a map.
async function runVisits(frame, visits) {
  const io = F.make({ screen: frame });
  const reads = visits.map((v) => v.read);
  let calls = 0;
  const matcher = {
    match: (crop, side) => {
      const r = reads[Math.floor(calls / 10)];
      const slot = calls % 5;
      calls++;
      return r[side][slot];
    },
  };
  let prev = null, prevPrev = null;
  for (const v of visits) {
    const s = await P.sampleAt({ io, drv: { seekTo: async () => v.t } }, v.t, {
      matcher, stepS: 30, mmss: (x) => String(x), log: () => {},
      prev, prevPrev, firstOfRound: v.firstOfRound,
    });
    assert.ok(!s.missed, 'visit t=' + v.t + ' landed');
    prevPrev = prev;
    prev = { a: s.a, b: s.b };
  }
  return io.kept;
}

test('a stable round stores one frame, not one per grid point', { skip }, async () => {
  const frame = Corpus.at('probe-panelopen-live.png');
  const A = readOf(GUID_A);
  const kept = await runVisits(frame, [
    { t: 60, read: A, firstOfRound: true },
    { t: 90, read: A, firstOfRound: false },
    { t: 120, read: A, firstOfRound: false },
    { t: 150, read: A, firstOfRound: true },
    { t: 180, read: A, firstOfRound: false },
    { t: 210, read: A, firstOfRound: false },
  ]);
  assert.strictEqual(kept.length, 2, 'one kept frame per round, six visits');
  assert.deepStrictEqual(kept.map((k) => k.tag), ['t60', 't150']);
});

test('a mid-round swap stores one frame per distinct comp state', { skip }, async () => {
  const frame = Corpus.at('probe-panelopen-live.png');
  const A = readOf(GUID_A);
  const B = readOf(GUID_B);
  const kept = await runVisits(frame, [
    { t: 60, read: A, firstOfRound: true },
    { t: 90, read: A, firstOfRound: false },
    { t: 120, read: B, firstOfRound: false },   // the swap
    { t: 150, read: B, firstOfRound: false },
    { t: 180, read: B, firstOfRound: true },
    { t: 210, read: B, firstOfRound: false },
  ]);
  // Round 1: baseline A (t60), the swap frame B (t120), and the frame after it
  // (t150) - the previous sample just disagreed with the one before it, a
  // transition in progress that keeps every frame it can get. Round 2: its own
  // baseline (t180). t90 and t210 are confident repeats and drop.
  assert.strictEqual(kept.length, 4, 'distinct states plus the transition frames');
  assert.deepStrictEqual(kept.map((k) => k.tag), ['t60', 't120', 't150', 't180']);
});

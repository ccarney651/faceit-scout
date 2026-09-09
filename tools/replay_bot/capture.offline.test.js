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
const Corpus = require('./corpus.js');

const skip = Corpus.absent() || false;

// The guards all refuse long before anything is matched, and building the real
// matcher means reading the whole reference library off disk.
const NO_MATCHER = { read: () => ({ a: [], b: [] }) };
const run = (io) => C.make(io).captureMap({ matcher: NO_MATCHER });

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

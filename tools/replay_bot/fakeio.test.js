const test = require('node:test');
const assert = require('node:assert');
const path = require('path');
const F = require('./fakeio.js');

test('every grab is served the scripted screen, and the tag is recorded', async () => {
  const io = F.make({ screen: 'esc-menu.png' });
  assert.strictEqual(await io.grabTo('timeline'), 'esc-menu.png');
  assert.strictEqual(await io.grabTo('panel'), 'esc-menu.png');
  assert.deepStrictEqual(io.grabs, [
    { tag: 'timeline', frame: 'esc-menu.png' },
    { tag: 'panel', frame: 'esc-menu.png' },
  ]);
});

test('a scripted sequence hands out one screen per grab, in order', async () => {
  const io = F.make({ screen: ['a.png', 'b.png'] });
  assert.strictEqual(await io.grabTo('one'), 'a.png');
  assert.strictEqual(await io.grabTo('two'), 'b.png');
});

// A run that grabs more than the script describes has walked off the path the
// script was written for. Repeating the last frame would hide that; every
// cascade this harness exists to catch began with the code carrying on past
// the point where the screen stopped matching its assumptions.
test('a sequence that runs out refuses rather than repeating itself', async () => {
  const io = F.make({ screen: ['a.png'] });
  await io.grabTo('one');
  await assert.rejects(() => io.grabTo('two'),
    /grab 2 \(two\).*script has 1/);
});

test('a script can answer differently depending on what has been pressed', async () => {
  const io = F.make({ screen: (c) => (c.keys.includes('k') ? 'open.png' : 'shut.png') });
  assert.strictEqual(await io.grabTo('panel'), 'shut.png');
  await io.sendKeys(['k']);
  assert.strictEqual(await io.grabTo('panel'), 'open.png');
});

test('keys are recorded flat, in the order they were sent', async () => {
  const io = F.make({ screen: 'x.png' });
  await io.sendKeys(['n']);
  await io.sendKeys(['k', 'space']);
  assert.deepStrictEqual(io.keys, ['n', 'k', 'space']);
});

test('a settle takes one frame and leaves it as the last frame', async () => {
  const io = F.make({ screen: 'x.png' });
  const r = await io.settle();
  assert.deepStrictEqual(r, { settled: true, frame: 'x.png' });
  assert.strictEqual(io.lastFrame(), 'x.png');
  assert.deepStrictEqual(io.grabs.map((g) => g.tag), ['settle']);
});

test('a quiesce is a settle under its own tag', async () => {
  const io = F.make({ screen: 'x.png' });
  assert.deepStrictEqual(await io.quiesce(), { settled: true, frame: 'x.png' });
  assert.deepStrictEqual(io.grabs.map((g) => g.tag), ['q']);
});

test('there is no last frame before anything has been grabbed', () => {
  assert.strictEqual(F.make({ screen: 'x.png' }).lastFrame(), null);
});

// keepAs copies a PNG on the rig. Here it only has to say which frame was kept
// under which name - a test that wrote files would leave litter behind.
test('keeping a frame records the name without touching the disk', async () => {
  const io = F.make({ screen: 'x.png' });
  await io.settle();
  assert.strictEqual(io.keepAs('t180'), 'x.png');
  assert.deepStrictEqual(io.kept, [{ tag: 't180', frame: 'x.png' }]);
});

test('keeping names an explicit frame over the last one', async () => {
  const io = F.make({ screen: 'x.png' });
  await io.settle();
  assert.strictEqual(io.keepAs('t0', 'other.png'), 'other.png');
});

// Sleeping for real would make an offline run as slow as a live one, and the
// point of the harness is that it costs nothing. The waits are still counted,
// because a wait that vanishes is a wait nobody notices growing.
test('sleeping is counted, not served', async () => {
  const io = F.make({ screen: 'x.png' });
  const t0 = Date.now();
  await io.sleep(6000);
  await io.sleep(250);
  assert.ok(Date.now() - t0 < 500, 'the harness must not actually wait');
  assert.strictEqual(io.slept, 6250);
});

test('log lines are collected instead of printed', async () => {
  const io = F.make({ screen: 'x.png' });
  io.log('events viewer open');
  assert.deepStrictEqual(io.logs, ['events viewer open']);
});

test('frame names are resolved against a frames directory when one is given', async () => {
  const io = F.make({ screen: 'cap-pause-80.png', framesDir: '/frames' });
  assert.strictEqual(await io.grabTo('pause'), path.join('/frames', 'cap-pause-80.png'));
});

// Some screens are worth describing rather than finding: "a frame at the wrong
// resolution" is a guard worth a test and not worth a 7MB PNG in the corpus.
// A screen that is already a picture is handed straight to the code under test.
test('a screen can be a picture instead of a path', async () => {
  const canvas = require('@napi-rs/canvas');
  const pic = canvas.createCanvas(1920, 1080);
  const io = F.make({ screen: pic });
  const got = await io.loadImage(await io.grabTo('timeline'));
  assert.strictEqual(got, pic);
  assert.strictEqual(got.width, 1920);
});

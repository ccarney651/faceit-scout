const test = require('node:test');
const assert = require('node:assert');
const CS = require('./clientstate.js');

// --- clearEscMenu ----------------------------------------------------------
// One ESC press was not reliably taken by the client, and a menu still up when
// the import chunk plays sends every click to the wrong control. 2026-09-10,
// one full run in ten died on it.

function escFake({ upFor }) {
  // Menu reads as "up" for the first `upFor` checks, then down.
  let checks = 0;
  const keys = [];
  const kept = [];
  return {
    keys, kept,
    isUp: () => Promise.resolve(checks++ < upFor),
    sendKeys: (k) => { keys.push(k.join('+')); return Promise.resolve(); },
    wait: () => Promise.resolve(),
    io: {
      grabTo: () => Promise.resolve('frame.bmp'),
      keepAs: (tag) => { kept.push(tag); return Promise.resolve(`frames/${tag}.png`); },
    },
  };
}

const escOpts = (f, over) => Object.assign({
  sendKeys: f.sendKeys, wait: f.wait, escWait: 0, tries: 3, tag: 'ABC123', isUp: f.isUp,
}, over);

test('clearEscMenu does nothing when the menu is not up', async () => {
  const f = escFake({ upFor: 0 });
  const n = await CS.clearEscMenu(f.io, escOpts(f));
  assert.strictEqual(n, 0);
  assert.deepStrictEqual(f.keys, []);
});

test('clearEscMenu presses ESC once for a menu that clears on the first press', async () => {
  const f = escFake({ upFor: 1 });
  const n = await CS.clearEscMenu(f.io, escOpts(f));
  assert.strictEqual(n, 1);
  assert.deepStrictEqual(f.keys, ['ESC']);
});

test('clearEscMenu keeps pressing while the menu stays up, within the limit', async () => {
  const f = escFake({ upFor: 2 });
  const n = await CS.clearEscMenu(f.io, escOpts(f));
  assert.strictEqual(n, 2);
});

test('clearEscMenu fails the map and keeps a code-tagged frame when the menu will not close', async () => {
  const f = escFake({ upFor: 99 });
  await assert.rejects(
    CS.clearEscMenu(f.io, escOpts(f)),
    (e) => /will not close after 3 presses/.test(e.message) && /esc-stuck-ABC123/.test(e.message));
  assert.strictEqual(f.keys.length, 3);
  assert.deepStrictEqual(f.kept, ['esc-stuck-ABC123']);
});

test('clearEscMenu still fails loudly if keeping the diagnostic frame throws', async () => {
  const f = escFake({ upFor: 99 });
  f.io.grabTo = () => Promise.reject(new Error('grab failed'));
  await assert.rejects(
    CS.clearEscMenu(f.io, escOpts(f)),
    (e) => /will not close after 3 presses/.test(e.message));
});

// --- waitFor -------------------------------------------------------------

test('waitFor returns once the condition matches `want`', async () => {
  let calls = 0;
  const io = { sleep: () => Promise.resolve() };
  const ok = await CS.waitFor(io, true, 9999, 'the replay', () => {
    calls += 1;
    return Promise.resolve(calls >= 3);   // ready on the third poll
  });
  assert.strictEqual(ok, true);
  assert.strictEqual(calls, 3);
});

test('waitFor throws with the label when it times out', async () => {
  const io = { sleep: () => Promise.resolve() };
  await assert.rejects(
    CS.waitFor(io, true, -1, 'the replay to load', () => Promise.resolve(false)),
    /timed out.*the replay to load/);
});

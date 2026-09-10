const test = require('node:test');
const assert = require('node:assert');
const RUN = require('./run.js');

test('flags are read off the command line', () => {
  const a = RUN.parseArgs(['--limit', '3', '--codes', 'AAA111,BBB222', '--dry']);
  assert.strictEqual(a.limit, 3);
  assert.deepStrictEqual(a.codes, ['AAA111', 'BBB222']);
  assert.strictEqual(a.dry, true);
});

test('no flags means the feed, every code, for real', () => {
  const a = RUN.parseArgs([]);
  assert.deepStrictEqual([a.codes, a.limit, a.dry, a.staleOk], [null, null, false, false]);
});

// Ad-hoc codes are for testing the loop on replays that are not league games.
// Inventing a map name for them would send a fiction downstream, where nothing
// could tell it from a real reading.
test('ad-hoc codes carry nulls, not invented fields', () => {
  const q = RUN.synthesise(['j8k2qp']);
  assert.strictEqual(q[0].code, 'J8K2QP');
  assert.strictEqual(q[0].map, null);
  assert.strictEqual(q[0].map_guid, null);
  assert.strictEqual(q[0].t1, null);
});

test('ad-hoc codes get their own game numbers, so neither skips the other', () => {
  const q = RUN.synthesise(['AAA111', 'BBB222']);
  assert.deepStrictEqual(q.map((c) => c.game_no), [1, 2]);
});

// The worst outcome this tool has: a feed built before the last patch lists
// codes the client refuses, the queue calls them all pending, and every
// one-shot import is spent on a code that cannot work.
test('a feed built today is fresh', () => {
  const now = Date.parse('2026-09-09T14:00:00Z');
  const got = RUN.feedFreshness({ built_at: '2026-09-09T03:00:00Z' }, now);
  assert.strictEqual(got.fresh, true);
});

test('a feed built yesterday is not', () => {
  const now = Date.parse('2026-09-09T14:00:00Z');
  const got = RUN.feedFreshness({ built_at: '2026-09-08T22:00:00Z' }, now);
  assert.strictEqual(got.fresh, false);
  assert.strictEqual(got.built, '2026-09-08');
});

test('a feed with no build date is never fresh', () => {
  assert.strictEqual(RUN.feedFreshness({}, Date.now()).fresh, false);
  assert.strictEqual(RUN.feedFreshness(null, Date.now()).fresh, false);
});

// Requiring this file must never start driving the client - which is what these
// tests do, on every run.
test('requiring run.js does not start a run', () => {
  assert.strictEqual(typeof RUN.parseArgs, 'function');
});

// --- clearEscMenu -----------------------------------------------------------
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
  const n = await RUN.clearEscMenu(f.io, escOpts(f));
  assert.strictEqual(n, 0);
  assert.deepStrictEqual(f.keys, []);
});

test('clearEscMenu presses ESC once for a menu that clears on the first press', async () => {
  const f = escFake({ upFor: 1 });
  const n = await RUN.clearEscMenu(f.io, escOpts(f));
  assert.strictEqual(n, 1);
  assert.deepStrictEqual(f.keys, ['ESC']);
});

test('clearEscMenu keeps pressing while the menu stays up, within the limit', async () => {
  const f = escFake({ upFor: 2 });
  const n = await RUN.clearEscMenu(f.io, escOpts(f));
  assert.strictEqual(n, 2);
});

test('clearEscMenu fails the map and keeps a code-tagged frame when the menu will not close', async () => {
  const f = escFake({ upFor: 99 });
  await assert.rejects(
    RUN.clearEscMenu(f.io, escOpts(f)),
    (e) => /will not close after 3 presses/.test(e.message) && /esc-stuck-ABC123/.test(e.message));
  assert.strictEqual(f.keys.length, 3);
  assert.deepStrictEqual(f.kept, ['esc-stuck-ABC123']);
});

test('clearEscMenu still fails loudly if keeping the diagnostic frame throws', async () => {
  const f = escFake({ upFor: 99 });
  f.io.grabTo = () => Promise.reject(new Error('grab failed'));
  await assert.rejects(
    RUN.clearEscMenu(f.io, escOpts(f)),
    (e) => /will not close after 3 presses/.test(e.message));
});

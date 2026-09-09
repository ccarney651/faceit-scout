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

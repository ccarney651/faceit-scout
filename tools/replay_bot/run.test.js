const test = require('node:test');
const assert = require('node:assert');
const fs = require('fs');
const os = require('os');
const path = require('path');
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

// --code-stack cycles a codestack.js file (console §14.3b) instead of a
// finite queue. chunkSpeed left unset (null) means "read TIMING live at every
// map", not "use whatever TIMING said when the process started" - that is
// what lets a console Save apply without restarting the loop.
test('--code-stack is read, and chunkSpeed defaults to null not a snapshot', () => {
  const a = RUN.parseArgs(['--code-stack', 'state/console_codes.json']);
  assert.strictEqual(a.codeStack, 'state/console_codes.json');
  assert.strictEqual(a.chunkSpeed, null);
});

test('--chunk-speed still pins one value for the whole run', () => {
  assert.strictEqual(RUN.parseArgs(['--chunk-speed', '1.5']).chunkSpeed, 1.5);
});

test('no --code-stack means codeStack is null', () => {
  assert.strictEqual(RUN.parseArgs([]).codeStack, null);
});

// --after is a precise instant, for when a patch's deliberate day-early wipe
// date (owdb/db.py _SEED_WIPES) leaves a cluster of same-day pre-patch games
// looking alive - see queue.js's day-granularity `pending()` filter, which
// this does not replace.
test('--after is read, and absent by default', () => {
  assert.strictEqual(RUN.parseArgs(['--after', '2026-09-08T18:00:00Z']).after,
    '2026-09-08T18:00:00Z');
  assert.strictEqual(RUN.parseArgs([]).after, null);
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

// --codes and --code-stack exist to replay a small reusable set (codestack.js)
// and that set is routinely real league codes, not throwaway ones. A code
// already in the feed must come back with ITS real match data, or attribute.js
// has no lineup to work with and abstains every slot on a map that was never
// actually ad-hoc - which is what a 2026-09-11 console-loop pass on 20 real
// FACEIT codes hit (zero attribution, though every code was a real match).
test('a code already in the feed is not treated as ad-hoc', () => {
  const feed = {
    codes: [{
      code: 'ne1hka', match_id: '1-real-match', game_no: 4, map: 'Aatlis',
      map_guid: '0x0800000000000F35', map_category: 'Flashpoint',
      team_a: 'Fellowship of the INT', team_b: 'no ego',
      t1: 'team-a-id', t2: 'team-b-id', finished_at: '2026-09-09T19:17:09Z',
    }],
  };
  const q = RUN.synthesise(['NE1HKA'], feed);
  assert.strictEqual(q[0].match_id, '1-real-match');
  assert.strictEqual(q[0].game_no, 4);
  assert.strictEqual(q[0].map, 'Aatlis');
  assert.strictEqual(q[0].t1, 'team-a-id');
});

test('a code not in the feed still falls back to ad-hoc nulls', () => {
  const q = RUN.synthesise(['ZZZ999'], { codes: [{ code: 'AAA111', match_id: 'x', game_no: 1 }] });
  assert.strictEqual(q[0].match_id, 'adhoc');
  assert.strictEqual(q[0].map, null);
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

// A failed code must go back into the queue on its own, up to the cap -
// putting it back is exactly what NOT being in attemptedKeys() means.
test('a failed code under the retry cap is not "done" - it stays in the queue', () => {
  const state = { 'm1:1': { status: 'failed', fail_count: 1 } };
  assert.deepStrictEqual(RUN.attemptedKeys(state), []);
});

test('a failed code that has hit the retry cap is "done" - no more auto-retries', () => {
  const state = { 'm1:1': { status: 'failed', fail_count: RUN.FAIL_RETRY_CAP } };
  assert.deepStrictEqual(RUN.attemptedKeys(state), ['m1:1']);
});

test('a failed entry with no fail_count yet (pre-existing data) counts as one failure', () => {
  const state = { 'm1:1': { status: 'failed' } };
  assert.deepStrictEqual(RUN.attemptedKeys(state), []);
});

test('captured, captured-with-misses and an orphaned "opened" entry are all done regardless of fail_count', () => {
  const state = {
    'm1:1': { status: 'captured' },
    'm1:2': { status: 'captured-with-misses' },
    'm1:3': { status: 'opened' },
  };
  assert.deepStrictEqual(RUN.attemptedKeys(state).sort(), ['m1:1', 'm1:2', 'm1:3']);
});

// -- The loop-mode per-code cap (specs/2026-09-14-replay-bot-code-stack-retry-handoff.md).
// The loop never touches the ledger, so its failure counting is a side table
// keyed by code and scoped to the run; only a failure AFTER the replay loaded
// counts toward the cap, so an import or environmental failure cannot drive a
// pool code out of rotation.
function tmpStack(codes) {
  const f = path.join(os.tmpdir(), 'owdb-run-stack-test-' + process.pid + '-' +
    Math.random().toString(36).slice(2) + '.json');
  require('./codestack.js').save(f, codes);
  return f;
}

test('countLoopFailure ignores a failure before the import succeeded', () => {
  const fails = new Map();
  assert.deepStrictEqual(RUN.countLoopFailure(fails, 'AAA111', false),
    { count: null, retired: false });
  assert.strictEqual(fails.size, 0);
});

test('countLoopFailure counts only post-import failures and retires at the cap', () => {
  const fails = new Map();
  assert.deepStrictEqual(RUN.countLoopFailure(fails, 'AAA111', true), { count: 1, retired: false });
  assert.deepStrictEqual(RUN.countLoopFailure(fails, 'AAA111', true), { count: 2, retired: false });
  assert.deepStrictEqual(RUN.countLoopFailure(fails, 'AAA111', true),
    { count: RUN.FAIL_RETRY_CAP, retired: true });
  assert.deepStrictEqual(RUN.countLoopFailure(fails, 'AAA111', true),
    { count: RUN.FAIL_RETRY_CAP + 1, retired: true }, 'stays retired, never un-retires');
});

test('countLoopFailure keeps codes separate', () => {
  const fails = new Map();
  RUN.countLoopFailure(fails, 'AAA111', true);
  assert.deepStrictEqual(RUN.countLoopFailure(fails, 'BBB222', true), { count: 1, retired: false });
  assert.strictEqual(fails.get('AAA111'), 1);
});

test('pullLoopCode skips retired codes but keeps the stack shape', () => {
  const cs = require('./codestack.js');
  // Nothing retired: the top code is returned and the stack rotates normally.
  let f = tmpStack(['AAA111', 'BBB222', 'CCC333']);
  try {
    const next = RUN.pullLoopCode(f, new Set());
    assert.strictEqual(next.code, 'AAA111');
    assert.deepStrictEqual(next.skipped, [], 'nothing to skip');
    assert.deepStrictEqual(cs.load(f), ['BBB222', 'CCC333', 'AAA111']);
  } finally { fs.unlinkSync(f); }

  // Two of three retired: both are rotated to the bottom on the way to the
  // one that is still live, and are still in the file afterwards - retired
  // for the run, not deleted.
  f = tmpStack(['AAA111', 'CCC333', 'BBB222']);
  try {
    const next = RUN.pullLoopCode(f, new Set(['AAA111', 'CCC333']));
    assert.strictEqual(next.code, 'BBB222');
    assert.deepStrictEqual(next.skipped, ['AAA111', 'CCC333']);
    assert.deepStrictEqual(cs.load(f), ['AAA111', 'CCC333', 'BBB222'],
      'a full rotation restored the order - retired ones were rotated past, not removed');
  } finally { fs.unlinkSync(f); }
});

test('pullLoopCode stops when every code is retired for the run', () => {
  const f = tmpStack(['AAA111', 'BBB222']);
  try {
    const next = RUN.pullLoopCode(f, new Set(['AAA111', 'BBB222']));
    assert.strictEqual(next.allRetired, true);
    assert.deepStrictEqual(next.skipped.sort(), ['AAA111', 'BBB222']);
  } finally { fs.unlinkSync(f); }
});

test('pullLoopCode on an empty stack is empty, not allRetired', () => {
  const f = tmpStack([]);
  try {
    assert.deepStrictEqual(RUN.pullLoopCode(f, new Set()), { empty: true });
  } finally { fs.unlinkSync(f); }
});

// The feed is regenerated locally sometimes by a writer that leaves a BOM
// (build_capture_data.py never does; a PowerShell redirect does). run.js used
// to hand back the fallback for such a file, which turned every code in the
// loop into an adhoc map with no attribution context. readJson strips the
// leading BOM first, exactly like recorder.js already does.
test('readJson strips a leading BOM before parsing', () => {
  const f = path.join(os.tmpdir(), 'owdb-bom-' + process.pid + '.json');
  try {
    fs.writeFileSync(f, '\ufeff{"codes":["AAA111"],"built_at":"2026-09-14T22:13:33Z"}', 'utf8');
    assert.deepStrictEqual(RUN.readJson(f, null), { codes: ['AAA111'], built_at: '2026-09-14T22:13:33Z' });
    assert.deepStrictEqual(RUN.readJson(f + '.missing', { codes: [] }), { codes: [] },
      'a missing file still hands back the fallback');
  } finally { fs.unlinkSync(f); }
});

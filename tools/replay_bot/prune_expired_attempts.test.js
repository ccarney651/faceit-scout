const test = require('node:test');
const assert = require('node:assert');
const P = require('./prune_expired_attempts.js');

function feedWith(codes) {
  return { code_wipe_date: '2026-09-07', codes };
}

test('expiredKeys finds attempts for codes the region-aware wipe calc now considers dead', () => {
  const feed = feedWith([
    { code: 'A', match_id: 'm1', game_no: 1, division: 'NA Expert', finished_at: '2026-09-08T00:00:00Z' },
    { code: 'B', match_id: 'm2', game_no: 1, division: 'EMEA Master', finished_at: '2026-09-08T00:00:00Z' },
  ]);
  const attempts = {
    'm1:1': { code: 'A', status: 'failed' },
    'm2:1': { code: 'B', status: 'failed' },
  };
  assert.deepStrictEqual(P.expiredKeys(feed, attempts), ['m1:1']);
});

test('expiredKeys ignores a key with no match in the feed at all (e.g. an ad-hoc test code)', () => {
  const feed = feedWith([]);
  const attempts = { 'adhoc:1': { code: 'X', status: 'captured' } };
  assert.deepStrictEqual(P.expiredKeys(feed, attempts), []);
});

test('expiredKeys leaves a still-live code alone', () => {
  const feed = feedWith([
    { code: 'A', match_id: 'm1', game_no: 1, division: 'NA Expert', finished_at: '2026-09-09T00:00:00Z' },
  ]);
  const attempts = { 'm1:1': { code: 'A', status: 'failed' } };
  assert.deepStrictEqual(P.expiredKeys(feed, attempts), []);
});

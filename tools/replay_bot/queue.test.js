const test = require('node:test');
const assert = require('node:assert');
const Q = require('./queue.js');

// A code entry exactly as docs/capture/data.json ships it.
function code(over) {
  return Object.assign({
    code: '2T857A',
    match_id: '1-4007a070-2503-40f1-926e-ac744e35d1ac',
    game_no: 1,
    map: 'Samoa',
    map_category: 'Control',
    map_guid: '0x0800000000000EC0',
    division: 'NA Expert',
    team_a: 'CrossCanines',
    team_b: 'ELMT Normal',
    t1: '61589e03-7216-4c6f-9824-8a44108b7b0b',
    t2: '4d38c549-3743-4d98-b5f2-3b859b7dc08d',
    finished_at: '2026-09-08T02:33:20Z',
  }, over);
}

test('a game finished before the wipe can never be replayed, so it is dropped', () => {
  const codes = [code({ finished_at: '2026-08-17T10:00:00Z' })];
  assert.deepStrictEqual(Q.pending(codes, { wipeDate: '2026-08-18' }), []);
});

// The wipe invalidates games finished ON the wipe day as well as before it.
// Relaxing the comparison to `>=` would queue codes that can never load.
test('a game finished on the wipe day itself is dropped, not kept', () => {
  const codes = [code({ finished_at: '2026-08-18T23:59:59Z' })];
  assert.deepStrictEqual(Q.pending(codes, { wipeDate: '2026-08-18' }), []);
});

test('a map already captured is not replayed again', () => {
  const codes = [
    code({ code: 'DONE', match_id: 'm1', game_no: 2 }),
    code({ code: 'TODO', match_id: 'm1', game_no: 3 }),
  ];
  const got = Q.pending(codes, { wipeDate: '2026-08-18', done: ['m1:2'] });
  assert.deepStrictEqual(got.map((c) => c.code), ['TODO']);
});

test('done-ness is per game, so another map of the same match still runs', () => {
  const codes = [code({ code: 'G1', match_id: 'm1', game_no: 1 })];
  const got = Q.pending(codes, { wipeDate: '2026-08-18', done: ['m1:2'] });
  assert.deepStrictEqual(got.map((c) => c.code), ['G1']);
});

test('the queue runs oldest game first, whatever order the feed arrived in', () => {
  const codes = [
    code({ code: 'THIRD', finished_at: '2026-09-03T00:00:00Z' }),
    code({ code: 'FIRST', finished_at: '2026-09-01T00:00:00Z' }),
    code({ code: 'SECOND', finished_at: '2026-09-02T00:00:00Z' }),
  ];
  const got = Q.pending(codes, { wipeDate: '2026-08-18' }).map((c) => c.code);
  assert.deepStrictEqual(got, ['FIRST', 'SECOND', 'THIRD']);
});

// TRIAGE MATTERS AFTER ALL, JUST NOT BY EXPIRY. Every live code does die at the
// same wipe, so nothing in the queue is "expiring soonest" - but the league
// produces about 127 coded games a day across all regions and tiers, which is
// roughly nine hours of capture a week against a patch cadence of about one.
// The queue does not reliably fit before the deadline, so WHICH codes get the
// client's time is the whole question.
test('the queue can be narrowed to the divisions worth scouting', () => {
  const codes = [
    code({ code: 'MINE', division: 'EMEA Master' }),
    code({ code: 'ALSO', division: 'EMEA Advanced' }),
    code({ code: 'NOPE', division: 'NA Intermediate' }),
  ];
  const got = Q.pending(codes, {
    wipeDate: '2026-08-18', divisions: ['EMEA Master', 'EMEA Advanced'],
  }).map((c) => c.code);
  assert.deepStrictEqual(got.sort(), ['ALSO', 'MINE']);
});

test('a division filter matches loosely, so "EMEA" takes every EMEA tier', () => {
  const codes = [
    code({ code: 'M', division: 'EMEA Master' }),
    code({ code: 'E', division: 'EMEA Expert' }),
    code({ code: 'N', division: 'NA Master' }),
  ];
  const got = Q.pending(codes, { wipeDate: '2026-08-18', divisions: ['EMEA'] })
    .map((c) => c.code);
  assert.deepStrictEqual(got.sort(), ['E', 'M']);
});

// Scouting is usually about specific opponents, and a team appears as either
// side of a match.
test('the queue can be narrowed to particular teams, on either side', () => {
  const codes = [
    code({ code: 'A', team_a: 'Wasp', team_b: 'NewGens' }),
    code({ code: 'B', team_a: 'Crabs', team_b: 'Wasp' }),
    code({ code: 'C', team_a: 'Crabs', team_b: 'Lucky Charm' }),
  ];
  const got = Q.pending(codes, { wipeDate: '2026-08-18', teams: ['wasp'] })
    .map((c) => c.code);
  assert.deepStrictEqual(got.sort(), ['A', 'B']);
});

// Oldest-first stays the default: it is deterministic and it makes a resumed
// run pick up where it stopped. But when the queue will not finish, the freshest
// games are the ones worth having.
test('newest-first is available for when the queue will not finish', () => {
  const codes = [
    code({ code: 'OLD', finished_at: '2026-09-01T00:00:00Z' }),
    code({ code: 'NEW', finished_at: '2026-09-03T00:00:00Z' }),
    code({ code: 'MID', finished_at: '2026-09-02T00:00:00Z' }),
  ];
  assert.deepStrictEqual(
    Q.pending(codes, { wipeDate: '2026-08-18', newestFirst: true }).map((c) => c.code),
    ['NEW', 'MID', 'OLD']);
});

// A match is four or five games and they share a timestamp, so ordering by time
// keeps a match together either way - which is what makes a run's output usable
// as "this team, this match" rather than scattered maps.
test('the games of one match stay together under either order', () => {
  const codes = [
    code({ code: 'G1', match_id: 'm9', game_no: 1, finished_at: '2026-09-02T00:00:00Z' }),
    code({ code: 'OTHER', match_id: 'm8', finished_at: '2026-09-01T00:00:00Z' }),
    code({ code: 'G2', match_id: 'm9', game_no: 2, finished_at: '2026-09-02T00:00:00Z' }),
  ];
  for (const newestFirst of [false, true]) {
    const got = Q.pending(codes, { wipeDate: '2026-08-18', newestFirst }).map((c) => c.match_id);
    const first = got.indexOf('m9');
    assert.strictEqual(got[first + 1], 'm9', 'm9 games must be adjacent');
  }
});

test('no filters means the whole live queue, as before', () => {
  const codes = [code({ code: 'A', division: 'NA Expert' }), code({ code: 'B' })];
  assert.strictEqual(Q.pending(codes, { wipeDate: '2026-08-18' }).length, 2);
});

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

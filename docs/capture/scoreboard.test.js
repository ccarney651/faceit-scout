// docs/capture/scoreboard.test.js
// node:test fixtures for the scrim scoreboard parser. Fixtures are built from
// the exact format strings in tools/scrim_code/scrim_owdb.opy:
//   legend: 'K • D • DD • DT • ACC • UU'  (DPS / DB tank / HD support)
//   entry:  '{heroIcon} {K} • {D} • {DD} • {DT} • {X} • {UU}'
//   time:   '{icon} Match Time: {M}:{SS}'
// Run with:  node --test docs/capture/scoreboard.test.js

const test = require('node:test');
const assert = require('node:assert');
const SB = require('./scoreboard.js');

const BULLET = ' • ';
const LEGENDS = {
  dps: ['K', 'D', 'DD', 'DT', 'ACC', 'UU'].join(BULLET),
  tank: ['K', 'D', 'DD', 'DT', 'DB', 'UU'].join(BULLET),
  support: ['K', 'D', 'DD', 'DT', 'HD', 'UU'].join(BULLET),
};

function entry({ icon = '?', k, d, dd, dt, x, uu }) {
  return [icon, k, d, dd, dt, x, uu].join(BULLET);
}

// A full 10-player GroupMode-0 board: team1 block above team2 within each role.
function fullBoard() {
  return [
    'OW SCOUT SCRIM  2 - 3',
    LEGENDS.dps,
    entry({ k: 7, d: 3, dd: 4597, dt: 1957, x: '30%', uu: 1 }),   // t1 dps
    entry({ k: 16, d: 4, dd: 6811, dt: 2112, x: '45%', uu: 3 }),  // t1 dps
    entry({ k: 4, d: 10, dd: 3108, dt: 3496, x: '55%', uu: 2 }),  // t2 dps
    entry({ k: 3, d: 11, dd: 2684, dt: 4019, x: '13%', uu: 1 }),  // t2 dps
    LEGENDS.tank,
    entry({ k: 14, d: 3, dd: 7232, dt: 5915, x: 1696, uu: 2 }),   // t1 tank
    entry({ k: 10, d: 10, dd: 6069, dt: 10974, x: 4467, uu: 1 }), // t2 tank
    LEGENDS.support,
    entry({ k: 3, d: 7, dd: 974, dt: 2604, x: 2115, uu: 0 }),     // t1 supp
    entry({ k: 11, d: 4, dd: 7038, dt: 3419, x: 3597, uu: 2 }),   // t1 supp
    entry({ k: 1, d: 10, dd: 2364, dt: 3531, x: 5024, uu: 1 }),   // t2 supp
    entry({ k: 2, d: 10, dd: 1537, dt: 4631, x: 3571, uu: 1 }),   // t2 supp
    'Match Time: 9:57',
  ];
}

test('parses legends and role order', () => {
  const res = SB.parse([LEGENDS.dps, LEGENDS.tank, LEGENDS.support]);
  assert.deepStrictEqual(res.roles, ['dps', 'tank', 'support']);
  assert.strictEqual(res.entries.length, 0);
});

test('parses a full board with roles and stats', () => {
  const res = SB.parse(fullBoard());
  assert.strictEqual(res.entries.length, 10);
  assert.strictEqual(res.matchTime, '9:57');
  const dps = res.entries.filter((e) => e.role === 'dps');
  assert.strictEqual(dps.length, 4);
  assert.deepStrictEqual(
    { k: dps[0].k, d: dps[0].d, dd: dps[0].dd, dt: dps[0].dt, x: dps[0].x, uu: dps[0].uu },
    { k: 7, d: 3, dd: 4597, dt: 1957, x: '30%', uu: 1 },
  );
  const tanks = res.entries.filter((e) => e.role === 'tank');
  assert.strictEqual(tanks.length, 2);
  assert.strictEqual(tanks[0].x, 1696); // DB (blocked) column, no %
  const supps = res.entries.filter((e) => e.role === 'support');
  assert.strictEqual(supps.length, 4);
  assert.strictEqual(supps[0].x, 2115); // HD (healing) column
});

test('skips leading non-numeric icon token on entries', () => {
  const res = SB.parse([
    LEGENDS.dps,
    entry({ icon: 'Genji', k: 5, d: 2, dd: 3100, dt: 1200, x: '40%', uu: 2 }),
  ]);
  assert.strictEqual(res.entries.length, 1);
  assert.strictEqual(res.entries[0].k, 5);
  assert.strictEqual(res.entries[0].uu, 2);
});

test('ignores the header and empty lines', () => {
  const res = SB.parse(['OW SCOUT SCRIM  2 - 3', '', LEGENDS.dps, '   ']);
  assert.strictEqual(res.entries.length, 0);
  assert.strictEqual(res.matchTime, null);
});

test('handles bullets OCR-rendered as pipes or dots', () => {
  const line = '7 | 3 | 4597 | 1957 | 30% | 1';
  const res = SB.parse([LEGENDS.dps, line]);
  assert.strictEqual(res.entries.length, 1);
  assert.strictEqual(res.entries[0].k, 7);
  assert.strictEqual(res.entries[0].x, '30%');
});

test('match time fallback on bare M:SS token', () => {
  const res = SB.parse(['9:57']);
  assert.strictEqual(res.matchTime, '9:57');
});

test('assignTeams splits role blocks team1 then team2', () => {
  const res = SB.parse(fullBoard());
  SB.assignTeams(res, { dps: 2, tank: 1, support: 2 });
  const dps = res.entries.filter((e) => e.role === 'dps');
  assert.deepStrictEqual(dps.map((e) => e.team), ['a', 'a', 'b', 'b']);
  const tanks = res.entries.filter((e) => e.role === 'tank');
  assert.deepStrictEqual(tanks.map((e) => e.team), ['a', 'b']);
  const supps = res.entries.filter((e) => e.role === 'support');
  assert.deepStrictEqual(supps.map((e) => e.team), ['a', 'a', 'b', 'b']);
});

test('assignTeams leaves team null when counts do not match', () => {
  const res = SB.parse(fullBoard());
  SB.assignTeams(res, { dps: 3, tank: 3, support: 3 });
  res.entries.forEach((e) => assert.strictEqual(e.team, null));
});

test('parseScoreReadout reads a-centre score', () => {
  assert.deepStrictEqual(SB.parseScoreReadout('2 - 3'), { a: 2, b: 3 });
  assert.deepStrictEqual(SB.parseScoreReadout('SCORE 2–3'), { a: 2, b: 3 });
  assert.strictEqual(SB.parseScoreReadout('nothing here'), null);
});

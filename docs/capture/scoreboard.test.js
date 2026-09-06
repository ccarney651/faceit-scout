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
    'OWDB SCRIM  2 - 3',
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
  const res = SB.parse(['OWDB SCRIM  2 - 3', '', LEGENDS.dps, '   ']);
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

// ---------------------------------------------------------------------------
// The slot-ordered board, as it renders since scrim_owdb.opy started naming the
// player in each row. Transcribed from a live spectator frame, 2026-09-06.
const SLOT_BOARD = [
  'BANS  : NONE',
  'MAP   : NUMBANI',
  'K • D • DD • DT • ACC • UU',
  'K • D • DD • DT • DB • UU',
  'K • D • DD • DT • HD • UU',
  'TANK 1: 0 • 0 • 362 • 237 • 190 • 0',
  'DAMAGE 1: 1 • 0 • 188 • 118 • 0% • 0',
  'DAMAGE 2: 1 • 0 • 360 • 70 • 14% • 0',
  'SUPPORT 1: 0 • 0 • 0 • 100 • 272 • 0',
  'SUPPORT 2: 1 • 0 • 655 • 15 • 154 • 0',
  'TANK 2: 0 • 1 • 88 • 603 • 0 • 0',
  'DAMAGE 3: 0 • 1 • 120 • 250 • 0% • 0',
  'DAMAGE 4: 0 • 0 • 217 • 318 • 0% • 0',
  'SUPPORT 3: 0 • 1 • 115 • 278 • 157 • 0',
  'SUPPORT 4: 0 • 0 • 0 • 115 • 156 • 0',
  'MATCH TIME: 0:23',
];

test('a slot-ordered board reads all ten rows, named, in order', () => {
  const res = SB.parse(SLOT_BOARD);
  assert.strictEqual(res.layout, 'slot');
  assert.strictEqual(res.entries.length, 10);
  assert.strictEqual(res.matchTime, '0:23');
  assert.deepStrictEqual(res.entries.map((e) => e.name), [
    'TANK 1', 'DAMAGE 1', 'DAMAGE 2', 'SUPPORT 1', 'SUPPORT 2',
    'TANK 2', 'DAMAGE 3', 'DAMAGE 4', 'SUPPORT 3', 'SUPPORT 4',
  ]);
  assert.deepStrictEqual(res.entries[0], {
    k: 0, d: 0, dd: 362, dt: 237, x: 190, uu: 0, name: 'TANK 1', role: null,
    team: null,
  });
  assert.strictEqual(res.entries[1].x, '0%', 'a DPS row keeps its accuracy sign');
});

test('a slot-ordered board claims no role, because the legends do not label it', () => {
  // All three legends sit at the top, so the one above a row says nothing about
  // it. The caller knows each slot's hero and can say more; guessing 'support'
  // for all ten - which is what reading the last legend gives - is worse than
  // saying nothing.
  const res = SB.parse(SLOT_BOARD);
  res.entries.forEach((e) => assert.strictEqual(e.role, null));
  assert.deepStrictEqual(res.roles, ['dps', 'tank', 'support']);
});

test('the role-grouped board still labels its rows from the legend above them', () => {
  const res = SB.parse(fullBoard());
  assert.strictEqual(res.layout, 'role');
  assert.ok(res.entries.every((e) => e.role));
});

test('a name ending in a digit does not become a stat', () => {
  // "TANK 1" is why the stats are read from the RIGHT of the colon. Reading the
  // whole line leaves seven numbers, and the leading-icon guard only rescues
  // that by coincidence.
  const one = SB.parse(['K • D • DD • DT • DB • UU', 'TANK 1: 4 • 2 • 100 • 50 • 9 • 1']);
  assert.deepStrictEqual(
    { k: one.entries[0].k, d: one.entries[0].d, name: one.entries[0].name },
    { k: 4, d: 2, name: 'TANK 1' },
  );
  // An all-digits name is legal in Overwatch, and is the case a leading
  // non-numeric skip cannot survive at all.
  const two = SB.parse(['K • D • DD • DT • DB • UU', '1337: 4 • 2 • 100 • 50 • 9 • 1']);
  assert.strictEqual(two.entries[0].name, '1337');
  assert.strictEqual(two.entries[0].k, 4);
});

test('nameFromRaw drops what the hero icon made OCR emit in front of the name', () => {
  assert.strictEqual(SB.nameFromRaw('@ gcb: 1 • 2'), 'gcb');
  assert.strictEqual(SB.nameFromRaw('LÚCIOMAIN: 1 • 2'), 'LÚCIOMAIN');
  assert.strictEqual(SB.nameFromRaw('no colon here'), null);
});

test('an unnamed row still parses, for a board built before names existed', () => {
  const res = SB.parse(['K • D • DD • DT • DB • UU', '? • 4 • 2 • 100 • 50 • 9 • 1']);
  assert.strictEqual(res.entries[0].name, null);
  assert.strictEqual(res.entries[0].k, 4);
});

// ---------------------------------------------------------------------------
// The current board: white, no icons, padded columns, TEAM headers, one legend,
// and the player's name last. Widths match the pad3/pad3/pad7/pad7/pad7/pad4
// macros in scrim_owdb.opy.
const TEAM_BOARD = [
  'BANS  : NONE',
  'MAP   : COLOSSEO',
  '  K  D    DMG    TKN  A/D/H ULT : PLAYER',
  'TEAM 1',
  '  6 11  14861   7561    28%   6 : LEXRR',
  '  8 10   9943   9781    45%   4 : SCRAINE',
  ' 12  3  14435   4336    190   6 : ASHBORN',
  '  0  0    362    237  15334   0 : GCB',
  '  1  0    188    118    272   0 : PIXELS',
  'TEAM 2',
  '  4  6   4343   4883    21%   6 : HZL',
  '  6  9   4858   5013     0%   7 : SOUVLAKI',
  '  5  7   7618   5535    603   6 : AL7OTHI',
  '  4  6   8061   5011  13003   6 : JAVI',
  '  0  1     88    603    156   0 : SOCIAL',
  'MATCH TIME: 13:58',
];

test('the team-headed board reads teams from text, not from colour', () => {
  const res = SB.parse(TEAM_BOARD);
  assert.strictEqual(res.layout, 'team');
  assert.strictEqual(res.entries.length, 10);
  assert.deepStrictEqual(res.entries.map((e) => e.team),
    ['a', 'a', 'a', 'a', 'a', 'b', 'b', 'b', 'b', 'b']);
  assert.deepStrictEqual(res.entries.map((e) => e.name), [
    'LEXRR', 'SCRAINE', 'ASHBORN', 'GCB', 'PIXELS',
    'HZL', 'SOUVLAKI', 'AL7OTHI', 'JAVI', 'SOCIAL',
  ]);
  assert.deepStrictEqual(res.entries[0],
    { k: 6, d: 11, dd: 14861, dt: 7561, x: '28%', uu: 6, name: 'LEXRR', role: null, team: 'a' });
});

test('one legend is enough, and padding is not mistaken for a column', () => {
  const res = SB.parse(TEAM_BOARD);
  // The single header names no role - the sixth column varies row by row - so
  // it contributes nothing to roles, and must not be read as a player either.
  assert.deepStrictEqual(res.roles, []);
  assert.ok(SB.isColumnHeader(SB.tokenize('  K  D    DMG    TKN  A/D/H ULT : PLAYER')));
  assert.strictEqual(res.matchTime, '13:58');
  // Every row still yields exactly six values despite the leading spaces.
  res.entries.forEach((e) => {
    assert.ok(Number.isInteger(e.k) && Number.isInteger(e.d), 'k and d are numbers');
    assert.notStrictEqual(e.uu, null, 'the last column survived the padding');
  });
});

test('splitRow puts the name on the correct side of the colon', () => {
  // Name last: four or more numbers to the left says so.
  assert.deepStrictEqual(SB.splitRow('  6 11  14861   7561    28%   6 : LEXRR').name, 'LEXRR');
  // Name first, the format that shipped for an hour.
  assert.deepStrictEqual(SB.splitRow('LEXRR: 6 • 11 • 14861 • 7561 • 28% • 6').name, 'LEXRR');
  // No name at all, the format every existing replay renders.
  assert.strictEqual(SB.splitRow('? • 6 • 11 • 14861 • 7561 • 28% • 6').name, null);
});

test('a numeric name is still a name, on either side', () => {
  const last = SB.parse(['TEAM 1', '  6 11  14861   7561    28%   6 : 1337']);
  assert.strictEqual(last.entries[0].name, '1337');
  assert.strictEqual(last.entries[0].k, 6, 'the name did not become a stat');
});

// ---------------------------------------------------------------------------
// The current board: no names, hero icon LAST, numbers in fixed-width columns.
// Every row is the same length, which is what makes centred HUD lines align.
const ICON_BOARD = [
  'BANS  : NONE',
  'MAP   : NEON JUNCTION',
  '  K  D    DMG    TKN  A/D/H ULT HERO',
  'TEAM 1',
  '  0  0    362    237    190   0   &b',
  '  1  0    188    118     0%   0   Fog',
  'TEAM 2',
  '  0  1     88    603      0   0   $',
  'MATCH TIME: 0:48',
];

test('the icon trailing a row is discarded, not read as a stat', () => {
  const res = SB.parse(ICON_BOARD);
  assert.strictEqual(res.layout, 'team');
  assert.strictEqual(res.entries.length, 3);
  assert.deepStrictEqual(res.entries.map((e) => e.team), ['a', 'a', 'b']);
  res.entries.forEach((e) => assert.strictEqual(e.name, null, 'this board has no names'));
  assert.deepStrictEqual(res.entries[0],
    { k: 0, d: 0, dd: 362, dt: 237, x: 190, uu: 0, name: null, role: null, team: 'a' });
  assert.strictEqual(res.entries[1].x, '0%');
});

test('a last column welded to the icon still yields its value', () => {
  // OCR renders the icon as junk, and when that junk touches the last column
  // the token stops looking numeric. Dropping it would silently lose ULT.
  assert.strictEqual(SB.leadingNumber('0Fog'), '0');
  assert.strictEqual(SB.leadingNumber('12&b'), '12');
  assert.strictEqual(SB.leadingNumber('45%x'), '45%');
  assert.strictEqual(SB.leadingNumber('Fog'), null, 'pure junk stays junk');
  const res = SB.parse(['TEAM 1', '  6 11  14861   7561    28%   6&b']);
  assert.strictEqual(res.entries[0].uu, 6, 'the welded ULT survived');
});

test('zero padding is stripped, including from an accuracy', () => {
  // The board pads with zeros because Overwatch collapses runs of spaces, so
  // every stored value would otherwise carry a rendering artefact.
  const res = SB.parse([
    'KIL DTH DAMAG TAKEN A/D/H ULT',
    'TEAM 1',
    '000 001 00944 01594 00000 000  &b',
    '003 000 01045 00205 0040% 000  Fog',
  ]);
  assert.deepStrictEqual(res.entries[0],
    { k: 0, d: 1, dd: 944, dt: 1594, x: 0, uu: 0, name: null, role: null, team: 'a' });
  assert.strictEqual(res.entries[1].x, '40%', 'the padding is not part of the value');
  assert.strictEqual(res.entries[1].dd, 1045);
});

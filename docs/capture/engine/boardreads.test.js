const test = require('node:test');
const assert = require('node:assert');
const BR = require('./boardreads.js');

// A parsed board as scoreboard.js returns it: ten entries, five per team, in
// slot order within each block. Names are what the row printed.
function board(namesA, namesB, statFn) {
  const mk = (name, team, i) => Object.assign(
    { name: name, team: team, fields: 6 }, statFn ? statFn(team, i) : {});
  return {
    layout: 'slot',
    matchTime: '9:57',
    entries: namesA.map((n, i) => mk(n, 'a', i))
      .concat(namesB.map((n, i) => mk(n, 'b', i))),
  };
}

// The portrait bar read: five players per screen strip, left and right.
const BAR = { a: ['ALPHA', 'BRAVO', 'CHARLIE', 'DELTA', 'ECHO'],
              b: ['FOX', 'GOLF', 'HOTEL', 'INDIA', 'JULIET'] };

// ---------- the join ----------

test('a row whose name matches the bar joins by name, not by position', () => {
  // TEAM 1 printed in an order that does NOT match the left strip: if this
  // joined positionally every row would be wrong.
  const p = board(['ECHO', 'ALPHA', 'DELTA', 'BRAVO', 'CHARLIE'],
                  ['FOX', 'GOLF', 'HOTEL', 'INDIA', 'JULIET']);
  const rows = BR.joinRows(p, BAR);
  const echo = rows.find(r => r.player === 'ECHO');
  assert.strictEqual(echo.joined_by, 'name');
  assert.strictEqual(echo.slot, 4, 'ECHO is slot 4 on the bar, not row 0');
});

test('an OCR-mangled name still joins by name, fuzzily', () => {
  const p = board(['ALPHA', 'BRAV0', 'CHARLIE', 'DELTA', 'ECHO'],
                  ['FOX', 'GOLF', 'HOTEL', 'INDIA', 'JULIET']);
  const rows = BR.joinRows(p, BAR);
  const r = rows.find(x => x.slot === 1 && x.team === 'a');
  assert.strictEqual(r.player, 'BRAVO');
  assert.strictEqual(r.joined_by, 'name');
});

test('an unmatched name falls back to its slot position within the team block', () => {
  const p = board(['ALPHA', 'BRAVO', 'CHARLIE', 'DELTA', '???????'],
                  ['FOX', 'GOLF', 'HOTEL', 'INDIA', 'JULIET']);
  const rows = BR.joinRows(p, BAR);
  const r = rows.find(x => x.team === 'a' && x.slot === 4);
  assert.strictEqual(r.player, 'ECHO');
  assert.strictEqual(r.joined_by, 'slot');
});

test('the name matches decide which screen strip is TEAM 1', () => {
  // TEAM 1 is the RIGHT strip here. Nothing but the names can say so.
  const p = board(['FOX', 'GOLF', 'HOTEL', 'INDIA', '???????'],
                  ['ALPHA', 'BRAVO', 'CHARLIE', 'DELTA', 'ECHO']);
  const rows = BR.joinRows(p, BAR);
  const fallback = rows.find(x => x.joined_by === 'slot');
  assert.strictEqual(fallback.player, 'JULIET',
    'the unmatched TEAM 1 row is slot 4 of the RIGHT strip');
});

test('with no name matching anything, no row is attributed to a player', () => {
  const p = board(['???', '???', '???', '???', '???'],
                  ['???', '???', '???', '???', '???']);
  const rows = BR.joinRows(p, BAR);
  assert.strictEqual(rows.length, 10);
  assert.ok(rows.every(r => r.player === null),
    'without a strip mapping the positional fallback is unavailable');
  assert.ok(rows.every(r => r.team === 'a' || r.team === 'b'),
    'team and stats survive - only the player identity is withheld');
});

test('a role-grouped board is never attributed to a player', () => {
  const p = board(['ALPHA', 'BRAVO', 'CHARLIE', 'DELTA', 'ECHO'],
                  ['FOX', 'GOLF', 'HOTEL', 'INDIA', 'JULIET']);
  p.layout = 'role';
  const rows = BR.joinRows(p, BAR);
  assert.ok(rows.every(r => r.player === null && r.joined_by === null),
    'position means nothing in a role-grouped board, and a guess is worse than a gap');
});

// ---------- delta arithmetic ----------

const stats = (k, d, dd) => ({ k: k, d: d, dd: dd, dt: 0, x: 0, uu: 0 });

function read(round, matchTime, aStats, opts) {
  return Object.assign({
    round: round, match_time: matchTime, rounds_covered: 1,
    from_start: true, layout: 'slot',
    rows: aStats.map((s, i) => Object.assign(
      { slot: i, team: 'a', player: BAR.a[i], joined_by: 'name' }, s)),
  }, opts || {});
}

test('the first read of a map is that round outright, with nothing to subtract', () => {
  const r1 = read(1, '9:00', [stats(3, 1, 5000)]);
  const out = BR.deltas([r1]);
  assert.strictEqual(out[0].round, 1);
  assert.strictEqual(out[0].rows[0].k, 3);
});

test('a later round is the difference between consecutive reads', () => {
  const out = BR.deltas([
    read(1, '9:00', [stats(3, 1, 5000)]),
    read(2, '5:00', [stats(8, 2, 12000)]),
  ]);
  assert.strictEqual(out[1].rows[0].k, 5);
  assert.strictEqual(out[1].rows[0].d, 1);
  assert.strictEqual(out[1].rows[0].dd, 7000);
});

test('a skipped read makes the next delta span two rounds, and says so', () => {
  const out = BR.deltas([
    read(1, '9:00', [stats(3, 1, 5000)]),
    read(3, '2:00', [stats(11, 4, 20000)], { rounds_covered: 2 }),
  ]);
  assert.strictEqual(out[1].rounds_covered, 2);
  assert.strictEqual(out[1].rows[0].k, 8);
  assert.strictEqual(out[1].attributable_to_one_round, false);
});

test('a mid-map baseline is not attributable to a round', () => {
  const out = BR.deltas([read(2, '5:00', [stats(6, 2, 9000)], { from_start: false })]);
  assert.strictEqual(out[0].attributable_to_one_round, false,
    'those values include rounds nobody observed');
});

test('a stat that goes backwards is refused rather than reported negative', () => {
  // The board only accumulates, so this is a misread, not a real decrease.
  const out = BR.deltas([
    read(1, '9:00', [stats(3, 1, 5000)]),
    read(2, '5:00', [stats(1, 1, 5000)]),
  ]);
  assert.strictEqual(out[1].rows[0].k, null);
});

// ---------- MATCH TIME is the read's identity ----------

test('two reads sharing a MATCH TIME are the same moment, and the second is refused', () => {
  const first = read(1, '9:00', [stats(3, 1, 5000)]);
  assert.strictEqual(BR.acceptRead([first], read(2, '9:00', [stats(3, 1, 5000)])).ok, false);
});

test('a read at a new MATCH TIME is accepted', () => {
  const first = read(1, '9:00', [stats(3, 1, 5000)]);
  assert.strictEqual(BR.acceptRead([first], read(2, '5:00', [stats(8, 2, 9000)])).ok, true);
});

// ---------- evaluateRead: the whole decision, kept out of the page ----------
//
// scrim.html should orchestrate and render, not decide. Everything that
// determines whether a read is stored, blocked or refused lives here where it
// can be tested without a browser, an OCR worker or a game running.

const okBoard = () => board(BAR.a, BAR.b,
  () => ({ k: 1, d: 1, dd: 100, dt: 100, x: '10%', uu: 1 }));

test('a clean read is accepted and carries the joined rows', () => {
  const r = BR.evaluateRead(okBoard(), BAR, [], { round: 1, fromStart: true });
  assert.strictEqual(r.status, 'ok');
  assert.strictEqual(r.read.rows.length, 10);
  assert.strictEqual(r.read.round, 1);
  assert.strictEqual(r.read.from_start, true);
});

test('the events panel covering the board is reported as occlusion', () => {
  const r = BR.evaluateRead(
    { layout: null, entries: [], matchTime: null, raw: 'JAVI ALL EVENTS ROUND 1' },
    BAR, [], { round: 1 });
  assert.strictEqual(r.status, 'occluded');
  assert.match(r.why, /events panel/i);
});

test('a board of nine rows is refused - nobody knows which row is missing', () => {
  const p = okBoard(); p.entries.pop();
  const r = BR.evaluateRead(p, BAR, [], { round: 1 });
  assert.strictEqual(r.status, 'invalid');
});

test('a board without MATCH TIME is refused - the read has no identity', () => {
  const p = okBoard(); p.matchTime = null;
  assert.strictEqual(BR.evaluateRead(p, BAR, [], { round: 1 }).status, 'invalid');
});

test('a board that is not five and five is refused', () => {
  const p = okBoard();
  p.entries[9].team = 'a';
  assert.strictEqual(BR.evaluateRead(p, BAR, [], { round: 1 }).status, 'invalid');
});

test('re-reading the same MATCH TIME is a duplicate, not a fresh round', () => {
  const first = BR.evaluateRead(okBoard(), BAR, [], { round: 1 }).read;
  const again = BR.evaluateRead(okBoard(), BAR, [first], { round: 2 });
  assert.strictEqual(again.status, 'duplicate');
});

test('a read taken after a skip records how many rounds it covers', () => {
  const r = BR.evaluateRead(okBoard(), BAR, [], { round: 3, skipped: 1 });
  assert.strictEqual(r.read.rounds_covered, 2);
});

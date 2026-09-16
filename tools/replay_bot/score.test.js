const test = require('node:test');
const assert = require('node:assert');
const S = require('./score.js');

// Two vocabularies have to meet: the bot emits Blizzard hero GUIDs and names
// them from refs.json, owreplays.tv numbers its own. Normalised names join them
// with nothing left over on either side - checked live at 53 against 53.
test('hero names join across punctuation, case and accents', () => {
  assert.strictEqual(S.normaliseName('D.Va'), 'dva');
  assert.strictEqual(S.normaliseName('Lúcio'), 'lucio');
  assert.strictEqual(S.normaliseName('Soldier: 76'), 'soldier76');
  assert.strictEqual(S.normaliseName('Wrecking Ball'), 'wreckingball');
  assert.strictEqual(S.normaliseName('D.Mon'), 'dmon');
});

const joined = (slot, team, hero) => ({ time: 0, type: 'PLAYER_JOINED', slot, team, hero });
const picked = (time, slot, team, hero) => ({ time, type: 'PLAYER_PICKED_HERO', slot, team, hero });

const FIVE_V_FIVE = [
  joined(1, '1', 1), joined(2, '1', 2), joined(3, '1', 3), joined(4, '1', 4), joined(5, '1', 5),
  joined(6, '2', 6), joined(7, '2', 7), joined(8, '2', 8), joined(9, '2', 9), joined(10, '2', 10),
];

test('the opening composition is whoever joined on each side', () => {
  const tl = S.heroTimeline(FIVE_V_FIVE);
  assert.deepStrictEqual(S.heroesAt(tl, '1', 0).sort((a, b) => a - b), [1, 2, 3, 4, 5]);
  assert.deepStrictEqual(S.heroesAt(tl, '2', 0).sort((a, b) => a - b), [6, 7, 8, 9, 10]);
});

// A swap applies from its own timestamp onward and to that slot only. Reading a
// composition at the wrong time is indistinguishable from reading it wrong.
test('a swap takes effect at its own time, not before', () => {
  const tl = S.heroTimeline(FIVE_V_FIVE.concat([picked(120, 2, '1', 42)]));
  assert.ok(S.heroesAt(tl, '1', 119).includes(2), 'still the old hero a second earlier');
  assert.ok(!S.heroesAt(tl, '1', 119).includes(42));
  assert.ok(S.heroesAt(tl, '1', 120).includes(42), 'and the new one from its own second');
  assert.ok(!S.heroesAt(tl, '1', 120).includes(2));
  assert.strictEqual(S.heroesAt(tl, '1', 300).length, 5, 'a swap replaces, it does not add');
});

test('only the swapped slot changes', () => {
  const tl = S.heroTimeline(FIVE_V_FIVE.concat([picked(60, 3, '1', 99)]));
  assert.deepStrictEqual(S.heroesAt(tl, '1', 60).sort((a, b) => a - b), [1, 2, 4, 5, 99]);
  assert.deepStrictEqual(S.heroesAt(tl, '2', 60).sort((a, b) => a - b), [6, 7, 8, 9, 10]);
});

test('the last swap before the moment wins when there are several', () => {
  const tl = S.heroTimeline(FIVE_V_FIVE.concat([
    picked(60, 1, '1', 20), picked(200, 1, '1', 30), picked(400, 1, '1', 40),
  ]));
  assert.ok(S.heroesAt(tl, '1', 199).includes(20));
  assert.ok(S.heroesAt(tl, '1', 399).includes(30));
  assert.ok(S.heroesAt(tl, '1', 500).includes(40));
});

// Events arrive in whatever order the site stores them, so the timeline must
// not depend on it.
test('the timeline does not depend on the order events arrive in', () => {
  const shuffled = FIVE_V_FIVE.concat([picked(400, 1, '1', 40), picked(60, 1, '1', 20)]);
  const tl = S.heroTimeline(shuffled);
  assert.ok(S.heroesAt(tl, '1', 100).includes(20));
  assert.ok(S.heroesAt(tl, '1', 500).includes(40));
});

// The bot reads five portraits left to right; the site numbers its own slots.
// Nothing guarantees the two orders agree, so a composition is compared as a
// MULTISET - two Anas must need two Anas.
test('a composition is scored as a multiset, not a set', () => {
  assert.strictEqual(S.compare(['ana', 'ana', 'mercy'], ['ana', 'mercy', 'ana']).matched, 3);
  assert.strictEqual(S.compare(['ana', 'ana', 'mercy'], ['ana', 'mercy', 'mercy']).matched, 2);
});

test('a comparison names what was missed and what was invented', () => {
  const r = S.compare(['ana', 'mercy', 'dva'], ['ana', 'mercy', 'winston']);
  assert.strictEqual(r.matched, 2);
  assert.deepStrictEqual(r.missing, ['winston'], 'played, and not read');
  assert.deepStrictEqual(r.extra, ['dva'], 'read, and not played');
});

test('an empty read scores nothing rather than throwing', () => {
  assert.strictEqual(S.compare([], ['ana']).matched, 0);
  assert.strictEqual(S.compare(['ana'], []).matched, 0);
});

// ROUND_START is the independent check on the timeline read - the failure it
// catches is a three-round map read as one continuous segment, which was
// confidently wrong and invisible in the output.
test('rounds are counted off the round markers', () => {
  const evs = FIVE_V_FIVE.concat([
    { time: 10, type: 'ROUND_START', round: 1 },
    { time: 300, type: 'ROUND_END', round: 1 },
    { time: 330, type: 'ROUND_START', round: 2 },
    { time: 600, type: 'ROUND_END', round: 2 },
  ]);
  assert.deepStrictEqual(S.rounds(evs), [
    { no: 1, start: 10, end: 300 },
    { no: 2, start: 330, end: 600 },
  ]);
});

test('a round still open at the end of the replay is still a round', () => {
  const evs = [{ time: 10, type: 'ROUND_START', round: 1 }];
  assert.deepStrictEqual(S.rounds(evs), [{ no: 1, start: 10, end: null }]);
});

// FACEIT LEAGUE CODES ARE NOT ON owreplays.tv - they come back 403 "Invalid
// replay", because only replays somebody uploaded are there. So for the games
// this bot actually exists to scout there is no hero answer key at all, and the
// round structure is the only thing that can be checked. FACEIT supplies it:
// every game in the feed carries a map_category, and the mode fixes how many
// rounds are possible.
test('a map type says how many rounds are possible', () => {
  assert.deepStrictEqual(S.roundsExpected('Push'), [1, 1], 'one long round');
  assert.deepStrictEqual(S.roundsExpected('Flashpoint'), [1, 1], 'one long round');
  assert.deepStrictEqual(S.roundsExpected('Control'), [2, 3], 'best of three, so never one');
  assert.strictEqual(S.roundsExpected('Escort')[0], 2, 'attack and defend, so at least two');
  assert.strictEqual(S.roundsExpected('Hybrid')[0], 2);
});

// Escort and hybrid go to extra rounds when the score passes 3, so the upper
// bound is open. Refusing a fourth round would refuse a real game.
test('escort and hybrid have no upper bound, because extra rounds happen', () => {
  assert.ok(S.roundsExpected('Escort')[1] >= 6);
  assert.ok(S.checkRounds('Escort', 4).ok, 'four rounds is a long game, not an error');
  assert.ok(!S.checkRounds('Escort', 1).ok, 'one is impossible');
});

test('an unknown map type judges nothing rather than guessing', () => {
  const r = S.checkRounds('Deathmatch', 7);
  assert.strictEqual(r.ok, true);
  assert.strictEqual(r.known, false);
});

test('a round count outside the type says which way it is wrong', () => {
  assert.match(S.checkRounds('Flashpoint', 2).why, /Flashpoint.*1/);
  assert.match(S.checkRounds('Control', 1).why, /Control.*2/);
});

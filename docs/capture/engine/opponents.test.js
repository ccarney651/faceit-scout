const test = require('node:test');
const assert = require('node:assert');
const O = require('./opponents.js');

// A feed shaped like data.json's team_rosters.
const FEED = {
  team_rosters: {
    t1: { name: 'Qwiz Esports', players: [
      { game_name: 'Fairuz' }, { game_name: 'Dazedreox' }, { game_name: 'Tomavul' },
      { game_name: 'Mellun' }, { game_name: 'Nenonxx' }, { game_name: 'BenchWarmer' }] },
    t2: { name: 'ELMT Thunder', players: [
      { game_name: 'Faisal' }, { game_name: 'FreakyShadow' }, { game_name: 'Altcoin' },
      { game_name: 'GCB' }, { game_name: 'Minerabbit' }] },
    t3: { name: 'Sparse FC', players: [{ game_name: 'Solo' }, { game_name: 'Duo' }] },
  },
};

const QWIZ = ['Fairuz', 'Dazedreox', 'Tomavul', 'Mellun', 'Nenonxx'];

test('buildTeamIndex collects every team from team_rosters', () => {
  const idx = O.buildTeamIndex(FEED);
  assert.equal(idx.length, 3);
  const q = idx.find(t => t.team_id === 't1');
  assert.equal(q.name, 'Qwiz Esports');
  assert.ok(q.names.includes('fairuz'));
});

test('buildTeamIndex falls back to per-match rosters on an older feed', () => {
  const idx = O.buildTeamIndex({ rosters: { m1: { tX: { name: 'Legacy', players: [{ nick: 'OnlyNick' }] } } } });
  assert.equal(idx.length, 1);
  assert.deepEqual(idx[0].names, ['onlynick']);
});

test('buildTeamIndex merges a team appearing in both maps without duplicating', () => {
  const idx = O.buildTeamIndex({
    team_rosters: { t1: { name: 'Qwiz Esports', players: [{ game_name: 'Fairuz' }] } },
    rosters: { m1: { t1: { name: 'Qwiz Esports', players: [{ game_name: 'Dazedreox' }] } } },
  });
  assert.equal(idx.length, 1);
  assert.deepEqual(idx[0].names.sort(), ['dazedreox', 'fairuz']);
});

test('a full lineup identifies its team', () => {
  const got = O.identifyTeam(QWIZ, O.buildTeamIndex(FEED));
  assert.equal(got.team_id, 't1');
  assert.equal(got.name, 'Qwiz Esports');
  assert.equal(got.matched, 5);
  assert.equal(got.ambiguous, false);
});

test('two smurfs still identify the team, and are reported as unmatched', () => {
  // The case the three-of-five bar exists for.
  const seen = ['Fairuz', 'Dazedreox', 'Tomavul', 'xX_alt_Xx', 'throwaway123'];
  const got = O.identifyTeam(seen, O.buildTeamIndex(FEED));
  assert.equal(got.team_id, 't1');
  assert.equal(got.matched, 3);
  assert.deepEqual(got.unmatched.sort(), ['throwaway123', 'xx_alt_xx']);
});

test('three smurfs fall back to no team rather than to a wrong one', () => {
  const seen = ['Fairuz', 'Dazedreox', 'alt1', 'alt2', 'alt3'];
  assert.equal(O.identifyTeam(seen, O.buildTeamIndex(FEED)), null);
});

test('names match regardless of case, spacing or a battletag discriminator', () => {
  const seen = ['  FAIRUZ#2183 ', 'dazedreox', 'ToMaVuL', 'Mellun', 'Nenonxx'];
  assert.equal(O.identifyTeam(seen, O.buildTeamIndex(FEED)).team_id, 't1');
});

test('a tie assigns nobody and reports both candidates', () => {
  // Two teams sharing three of the five: guessing would attribute someone
  // else's comps to them.
  const idx = O.buildTeamIndex({ team_rosters: {
    a: { name: 'A', players: [{ game_name: 'one' }, { game_name: 'two' }, { game_name: 'three' }] },
    b: { name: 'B', players: [{ game_name: 'one' }, { game_name: 'two' }, { game_name: 'three' }] },
  } });
  const got = O.identifyTeam(['one', 'two', 'three', 'x', 'y'], idx);
  assert.equal(got.ambiguous, true);
  assert.equal(got.team_id, null);
  assert.equal(got.candidates.length, 2);
});

test('the better overlap wins over a weaker one', () => {
  const idx = O.buildTeamIndex({ team_rosters: {
    a: { name: 'A', players: ['one', 'two', 'three', 'four'].map(n => ({ game_name: n })) },
    b: { name: 'B', players: ['one', 'two', 'three'].map(n => ({ game_name: n })) },
  } });
  const got = O.identifyTeam(['one', 'two', 'three', 'four', 'z'], idx);
  assert.equal(got.ambiguous, false);
  assert.equal(got.team_id, 'a');
});

test('an unknown five identifies nothing', () => {
  assert.equal(O.identifyTeam(['a', 'b', 'c', 'd', 'e'], O.buildTeamIndex(FEED)), null);
});

// --- local groups ---------------------------------------------------------

test('a new group remembers the five it saw', () => {
  const g = O.newLocalGroup(['Kirbz', 'Vega', 'Tsu', 'HYDRAA', 'dridro'], 1755000000000);
  assert.equal(g.kind, 'local_group');
  assert.equal(g.times_played, 1);
  assert.equal(g.label, null);
  assert.ok(g.roster_names.includes('kirbz'));
});

test('the same group is recognised again despite one substitute', () => {
  const g = O.newLocalGroup(['Kirbz', 'Vega', 'Tsu', 'HYDRAA', 'dridro']);
  const hit = O.findLocalGroup(['Kirbz', 'Vega', 'Tsu', 'HYDRAA', 'aStandIn'], [g]);
  assert.ok(hit);
  assert.equal(hit.group.id, g.id);
});

test('an unrelated five is not mistaken for a known group', () => {
  const g = O.newLocalGroup(['Kirbz', 'Vega', 'Tsu', 'HYDRAA', 'dridro']);
  assert.equal(O.findLocalGroup(['a', 'b', 'c', 'd', 'e'], [g]), null);
});

test('merging absorbs the stand-in and counts the meeting', () => {
  const g = O.newLocalGroup(['Kirbz', 'Vega', 'Tsu', 'HYDRAA', 'dridro']);
  O.mergeIntoGroup(g, ['Kirbz', 'Vega', 'Tsu', 'HYDRAA', 'aStandIn']);
  assert.ok(g.roster_names.includes('astandin'));
  assert.equal(g.times_played, 2);
});

// --- smurf aliases --------------------------------------------------------

test('learned aliases make the same lineup identify outright next time', () => {
  const idx = O.buildTeamIndex(FEED);
  const seen = ['Fairuz', 'Dazedreox', 'Tomavul', 'xX_alt_Xx', 'throwaway123'];
  const first = O.identifyTeam(seen, idx);
  assert.equal(first.matched, 3);

  const store = O.learnAliases({}, first.team_id, first.unmatched);
  const second = O.identifyTeam(seen, O.indexWithAliases(idx, store));
  assert.equal(second.team_id, 't1');
  assert.equal(second.matched, 5, 'the alts should now count as known names');
});

test('aliases lift a three-smurf lineup back into identifiable range', () => {
  // The measured cliff: three smurfs leaves two known names. Once two of them
  // are learned, the same lineup clears the bar.
  const idx = O.buildTeamIndex(FEED);
  const store = O.learnAliases({}, 't1', ['alt1', 'alt2']);
  const got = O.identifyTeam(['Fairuz', 'Dazedreox', 'alt1', 'alt2', 'alt3'],
                             O.indexWithAliases(idx, store));
  assert.equal(got.team_id, 't1');
  assert.equal(got.matched, 4);
});

test('indexWithAliases does not mutate the index it is given', () => {
  const idx = O.buildTeamIndex(FEED);
  const before = idx.find(t => t.team_id === 't1').names.length;
  O.indexWithAliases(idx, { t1: ['brandnewalt'] });
  assert.equal(idx.find(t => t.team_id === 't1').names.length, before);
});

test('aliases are never learned against a null team', () => {
  assert.deepEqual(O.learnAliases({}, null, ['whoever']), {});
});

// --- sides ----------------------------------------------------------------

test('our own roster decides which side we are on', () => {
  assert.equal(O.ourSide(QWIZ, ['a', 'b', 'c', 'd', 'e'], QWIZ), 'left');
  assert.equal(O.ourSide(['a', 'b', 'c', 'd', 'e'], QWIZ, QWIZ), 'right');
});

test('sides stay unknown when neither side is us', () => {
  assert.equal(O.ourSide(['a', 'b', 'c'], ['d', 'e', 'f'], QWIZ), null);
});

test('sides stay unknown when both sides look like us', () => {
  // A mirror would otherwise silently pick one; the operator keeps control.
  assert.equal(O.ourSide(QWIZ, QWIZ, QWIZ), null);
});

test('sides stay unknown when we have no roster to compare', () => {
  assert.equal(O.ourSide(QWIZ, ['a'], []), null);
});

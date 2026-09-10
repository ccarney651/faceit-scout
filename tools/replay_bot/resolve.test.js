const test = require('node:test');
const assert = require('node:assert');
const R = require('./resolve.js');

// A per-sample read for one slot. The bot's samples carry {name, guid, score}
// per cell; these fixtures use short guids for legibility.
const rd = (guid, score) => ({ name: guid, guid: guid, score: score });
const five = (specs) => specs.map(([g, s]) => rd(g, s));

// One sample: five reads a side, at time t.
function sample(t, a, b) {
  return { t: t, a: five(a), b: five(b) };
}

const ROUNDS = [{ from_t: 0, to_t: 300 }, { from_t: 400, to_t: 700 }];
const ROLES = { tank: 'tank', dps1: 'damage', dps2: 'damage', sup1: 'support', sup2: 'support' };

// Every slot read the same hero every frame: full support, no flags.
test('a unanimous round resolves every slot with full support and no flags', () => {
  const comp = [['tank', 0.95], ['dps1', 0.95], ['dps2', 0.95], ['sup1', 0.95], ['sup2', 0.95]];
  const got = R.rounds(
    [sample(100, comp, comp), sample(200, comp, comp)],
    ROUNDS, { heroRoles: ROLES });

  assert.strictEqual(got.length, 2, 'every play round is emitted, sampled or not');
  assert.deepStrictEqual(got[0].flags, [], 'the sampled round is clean');
  const slot = got[0].a[0];
  assert.strictEqual(slot.guid, 'tank');
  assert.strictEqual(slot.support, 1);
  assert.strictEqual(slot.contested, false);
  assert.deepStrictEqual(slot.flags, []);
});

// One frame misreads a slot; the frames around it outvote it. The winner is
// right, but the disagreement is worth surfacing.
test('a lone misread is outvoted but leaves the slot flagged low-support', () => {
  const good = [['tank', 0.95], ['dps1', 0.95], ['dps2', 0.95], ['sup1', 0.95], ['sup2', 0.95]];
  const bad = [['WIDOW', 0.61], ['dps1', 0.95], ['dps2', 0.95], ['sup1', 0.95], ['sup2', 0.95]];
  const got = R.rounds(
    [sample(50, good, good), sample(150, bad, good), sample(250, good, good)],
    ROUNDS, { heroRoles: ROLES });

  const slot = got[0].a[0];
  assert.strictEqual(slot.guid, 'tank', 'two of three frames win');
  assert.ok(slot.support < 0.67 + 1e-9 && slot.support > 0.6, 'support ~0.67: ' + slot.support);
  assert.ok(slot.flags.includes('low-support'));
  assert.deepStrictEqual(slot.reads.slice().sort(), [0.61, 0.95, 0.95].sort());
});

// A genuine mid-round hero swap: half the frames one hero, half another. Must
// be reported as contested with the runner-up, not averaged to a winner.
test('an even split is contested and carries the runner-up', () => {
  const early = [['DVA', 0.95], ['dps1', 0.9], ['dps2', 0.9], ['sup1', 0.9], ['sup2', 0.9]];
  const late = [['DMON', 0.95], ['dps1', 0.9], ['dps2', 0.9], ['sup1', 0.9], ['sup2', 0.9]];
  const got = R.rounds(
    [sample(50, early, early), sample(150, early, early), sample(250, late, late), sample(290, late, late)],
    ROUNDS, { heroRoles: ROLES });

  const slot = got[0].a[0];
  assert.strictEqual(slot.contested, true);
  assert.ok(['DVA', 'DMON'].includes(slot.guid));
  assert.ok(['DVA', 'DMON'].includes(slot.alt_guid));
  assert.notStrictEqual(slot.guid, slot.alt_guid);
  assert.ok(slot.flags.includes('contested'));
});

// A slot no frame could read at all.
test('a slot that never read is null and flagged no-read', () => {
  const withHole = [['', 0], ['dps1', 0.9], ['dps2', 0.9], ['sup1', 0.9], ['sup2', 0.9]];
  const got = R.rounds([sample(100, withHole, withHole)], ROUNDS, { heroRoles: ROLES });

  const slot = got[0].a[0];
  assert.strictEqual(slot.guid, null);
  assert.ok(slot.flags.includes('no-read'));
});

// The best per-sample score for the winning hero is below LOW_SCORE.
test('a winner whose best frame still scored badly is flagged low-score', () => {
  const weak = [['SHION', 0.55], ['dps1', 0.9], ['dps2', 0.9], ['sup1', 0.9], ['sup2', 0.9]];
  const got = R.rounds([sample(100, weak, weak), sample(200, weak, weak)], ROUNDS, { heroRoles: ROLES });

  const slot = got[0].a[0];
  assert.strictEqual(slot.guid, 'SHION');
  assert.ok(slot.flags.includes('low-score'));
});

// Attribution abstained on a slot -> the slot carries a null player and a flag.
test('an abstained player attribution is flagged', () => {
  const comp = [['tank', 0.95], ['dps1', 0.95], ['dps2', 0.95], ['sup1', 0.95], ['sup2', 0.95]];
  const attribution = {
    a: { ids: ['p1', 'p2', null, 'p4', 'p5'], conf: ['matched', 'matched', null, 'forced', 'matched'] },
    b: { ids: ['q1', 'q2', 'q3', 'q4', 'q5'], conf: ['matched', 'matched', 'matched', 'matched', 'matched'] },
  };
  const got = R.rounds([sample(100, comp, comp)], ROUNDS, { heroRoles: ROLES, attribution: attribution });

  assert.strictEqual(got[0].a[2].player_id, null);
  assert.ok(got[0].a[2].flags.includes('attribution-abstained'));
  assert.strictEqual(got[0].a[0].player_id, 'p1');
  assert.strictEqual(got[0].a[3].player_conf, 'forced');
  assert.deepStrictEqual(got[0].a[0].flags, []);
});

// A hero guid the feed's role map has never heard of (a custom: guid, or a
// freshly-added hero) -> unknown-hero, so the operator confirms the read.
test('a hero absent from the role map is flagged unknown-hero', () => {
  const comp = [['custom:d_mon', 0.9], ['dps1', 0.95], ['dps2', 0.95], ['sup1', 0.95], ['sup2', 0.95]];
  const got = R.rounds([sample(100, comp, comp)], ROUNDS, { heroRoles: ROLES });

  assert.ok(got[0].a[0].flags.includes('unknown-hero'));
});

// A play segment that produced no samples at all still appears, flagged, so a
// whole round is never silently missing.
test('a round with zero samples is emitted and flagged round-unsampled', () => {
  const comp = [['tank', 0.95], ['dps1', 0.95], ['dps2', 0.95], ['sup1', 0.95], ['sup2', 0.95]];
  const got = R.rounds([sample(100, comp, comp)], ROUNDS, { heroRoles: ROLES });

  assert.strictEqual(got.length, 2, 'both rounds appear');
  assert.strictEqual(got[1].round_no, 2);
  assert.ok(got[1].flags.includes('round-unsampled'));
  assert.ok(got[1].a.every((s) => s.guid === null));
});

// Far fewer samples landed in a round than were planned for it.
test('a round that lost most of its planned samples is flagged sparse-round', () => {
  const comp = [['tank', 0.95], ['dps1', 0.95], ['dps2', 0.95], ['sup1', 0.95], ['sup2', 0.95]];
  const got = R.rounds([sample(100, comp, comp)], ROUNDS,
    { heroRoles: ROLES, planned: { 1: 4, 2: 0 } });

  assert.ok(got[0].flags.includes('sparse-round'), '1 of 4 planned landed');
});

test('resolve is pure: it does not mutate the samples it is given', () => {
  const comp = [['tank', 0.95], ['dps1', 0.95], ['dps2', 0.95], ['sup1', 0.95], ['sup2', 0.95]];
  const samples = [sample(100, comp, comp)];
  const snapshot = JSON.stringify(samples);
  R.rounds(samples, ROUNDS, { heroRoles: ROLES });
  assert.strictEqual(JSON.stringify(samples), snapshot);
});

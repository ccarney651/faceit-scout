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

// One frame misreads a slot; with 2-in-a-row confirmation restored
// (2026-09-14, the operator's rule - a swap must be seen twice to be
// counted), the lone WIDOW read is absorbed back into the tank run instead of
// becoming its own segment. `guid` is now chosen by playtime, and a single
// segment spans the whole tracked window by construction - support is 1
// regardless of the noisy vote underneath it. The noise still surfaces: the
// RAW vote (which the absorbed WIDOW read still counts against) drives
// `low-support` independently of the presented support number - which is the
// point: a slot whose frames did not agree is a reason to look even though
// the hero it presents, and its playtime share, are not in question.
test('a lone misread is outvoted for guid, absorbed into one segment, and flagged low-support', () => {
  const good = [['tank', 0.95], ['dps1', 0.95], ['dps2', 0.95], ['sup1', 0.95], ['sup2', 0.95]];
  const bad = [['WIDOW', 0.61], ['dps1', 0.95], ['dps2', 0.95], ['sup1', 0.95], ['sup2', 0.95]];
  const got = R.rounds(
    [sample(50, good, good), sample(150, bad, good), sample(250, good, good)],
    ROUNDS, { heroRoles: ROLES });

  const slot = got[0].a[0];
  assert.strictEqual(slot.guid, 'tank', 'the only segment, so playtime is moot - it is the presented hero');
  assert.strictEqual(slot.support, 1, 'one segment spans the whole tracked window by construction');
  assert.strictEqual(slot.segments.length, 1, 'the lone WIDOW read is absorbed, not a segment');
  assert.strictEqual(slot.segments[0].guid, 'tank');
  assert.ok(slot.flags.includes('low-support'), 'the raw vote still disagreed - a reason to look');
  assert.deepStrictEqual(slot.reads.slice().sort(), [0.61, 0.95, 0.95].sort(), 'the misread score is not dropped');
});

// A genuine mid-round hero swap, split down the middle BY PLAYTIME (DVA holds
// t50-175, DMON holds t175-300 - 125s each of the round's 300s). Must be
// reported as contested with the runner-up, not averaged to a winner. Sample
// COUNT is not what decides this any more - see the next test for a swap
// where the sample count ties but the playtime plainly does not.
test('a playtime-even split is contested and carries the runner-up', () => {
  const early = [['DVA', 0.95], ['dps1', 0.9], ['dps2', 0.9], ['sup1', 0.9], ['sup2', 0.9]];
  const late = [['DMON', 0.95], ['dps1', 0.9], ['dps2', 0.9], ['sup1', 0.9], ['sup2', 0.9]];
  const got = R.rounds(
    [sample(50, early, early), sample(175, late, late), sample(225, late, late)],
    ROUNDS, { heroRoles: ROLES });

  const slot = got[0].a[0];
  assert.strictEqual(slot.support, 0.5, '125s of 250s tracked - dead even');
  assert.strictEqual(slot.contested, true);
  assert.ok(['DVA', 'DMON'].includes(slot.guid));
  assert.ok(['DVA', 'DMON'].includes(slot.alt_guid));
  assert.notStrictEqual(slot.guid, slot.alt_guid);
  assert.ok(slot.flags.includes('contested'));
});

// The case that motivated the change (2026-09-15, from a live review): a 2-2
// SAMPLE tie that is an 80/20 PLAYTIME split, because the samples do not land
// evenly around the swap - DVA's two reads are 100s apart early, DMON's two
// are 40s apart right before the round ends. The old vote-count resolver
// called this contested; it is not, DVA plainly held the slot for most of the
// round.
test('a tied sample count is not contested when the playtime split is not close', () => {
  const dva = [['DVA', 0.95], ['dps1', 0.9], ['dps2', 0.9], ['sup1', 0.9], ['sup2', 0.9]];
  const dmon = [['DMON', 0.95], ['dps1', 0.9], ['dps2', 0.9], ['sup1', 0.9], ['sup2', 0.9]];
  const got = R.rounds(
    [sample(50, dva, dva), sample(150, dva, dva), sample(250, dmon, dmon), sample(290, dmon, dmon)],
    ROUNDS, { heroRoles: ROLES });

  const slot = got[0].a[0];
  assert.strictEqual(slot.guid, 'DVA', 'held the slot for 200 of the tracked 250s');
  assert.strictEqual(slot.support, 0.8);
  assert.strictEqual(slot.contested, false);
  assert.ok(!slot.flags.includes('contested'));
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

// A real swap across two multi-frame runs, all samples bunched early (X held
// the slot for only 20 of the round's 300s before Y took over and held it the
// rest of the way). The raw SAMPLE count is close (2 vs 3) - a vote-count
// resolver would call this borderline - but the PLAYTIME is not close at all,
// and low-support would be a misleading flag for a swap this one-sided.
test('a low-support-by-sample-count multi-segment swap is not flagged low-support', () => {
  const early = [['X', 0.9], ['dps1', 0.9], ['dps2', 0.9], ['sup1', 0.9], ['sup2', 0.9]];
  const late = [['Y', 0.9], ['dps1', 0.9], ['dps2', 0.9], ['sup1', 0.9], ['sup2', 0.9]];
  const got = R.rounds(
    [sample(20, early, early), sample(30, early, early),
     sample(40, late, late), sample(50, late, late), sample(60, late, late)],
    ROUNDS, { heroRoles: ROLES });

  const slot = got[0].a[0];
  assert.strictEqual(slot.segments.length, 2);
  assert.strictEqual(slot.guid, 'Y', 'held the slot for 260 of the tracked 280s');
  assert.ok(slot.support > 0.9, 'support: ' + slot.support);
  assert.strictEqual(slot.contested, false, 'not an even split - Y has an overwhelming majority');
  assert.ok(!slot.flags.includes('low-support'), 'a multi-segment slot is not noise');
});

// --- segmentSlot: run-length stable stretches, for real mid-round swaps ---

test('a stable slot (no swap) is one segment starting at its first post-grace read', () => {
  const comp = [['tank', 0.95], ['dps1', 0.95], ['dps2', 0.95], ['sup1', 0.95], ['sup2', 0.95]];
  const got = R.rounds(
    [sample(50, comp, comp), sample(150, comp, comp), sample(250, comp, comp)],
    ROUNDS, { heroRoles: ROLES });
  const segs = got[0].a[0].segments;
  assert.strictEqual(segs.length, 1);
  assert.strictEqual(segs[0].guid, 'tank');
  assert.strictEqual(segs[0].from_t, 50);
});

test('a lone misread is absorbed, not counted as a swap', () => {
  const good = [['tank', 0.95], ['dps1', 0.95], ['dps2', 0.95], ['sup1', 0.95], ['sup2', 0.95]];
  const bad = [['WIDOW', 0.61], ['dps1', 0.95], ['dps2', 0.95], ['sup1', 0.95], ['sup2', 0.95]];
  const got = R.rounds(
    [sample(50, good, good), sample(150, bad, good), sample(250, good, good)],
    ROUNDS, { heroRoles: ROLES });
  const segs = got[0].a[0].segments;
  assert.strictEqual(segs.length, 1, 'one run, the misread folded into it');
  assert.strictEqual(segs[0].guid, 'tank');
  assert.strictEqual(segs[0].from_t, 50);
  assert.deepStrictEqual(segs[0].reads.slice().sort(), [0.61, 0.95, 0.95].sort());
});

test('a swap confirmed by a second read becomes its own segment at its real time', () => {
  const early = [['DVA', 0.95], ['dps1', 0.9], ['dps2', 0.9], ['sup1', 0.9], ['sup2', 0.9]];
  const late = [['DMON', 0.95], ['dps1', 0.9], ['dps2', 0.9], ['sup1', 0.9], ['sup2', 0.9]];
  const got = R.rounds(
    [sample(50, early, early), sample(250, late, late), sample(290, late, late)],
    ROUNDS, { heroRoles: ROLES });
  const segs = got[0].a[0].segments;
  assert.strictEqual(segs.length, 2);
  assert.deepStrictEqual([segs[0].guid, segs[0].from_t], ['DVA', 50]);
  assert.deepStrictEqual([segs[1].guid, segs[1].from_t], ['DMON', 250], 'the real swap time, not a guessed midpoint');
});

test('a single differing read, never repeated, is absorbed - not a segment', () => {
  const early = [['DVA', 0.95], ['dps1', 0.9], ['dps2', 0.9], ['sup1', 0.9], ['sup2', 0.9]];
  const late = [['DMON', 0.95], ['dps1', 0.9], ['dps2', 0.9], ['sup1', 0.9], ['sup2', 0.9]];
  const got = R.rounds(
    [sample(50, early, early), sample(250, late, late)],
    ROUNDS, { heroRoles: ROLES });
  const segs = got[0].a[0].segments;
  assert.strictEqual(segs.length, 1, 'DMON never repeated, so no swap happened');
  assert.strictEqual(segs[0].guid, 'DVA');
  assert.deepStrictEqual(segs[0].reads.slice().sort(), [0.95, 0.95].sort());
});

// The trade the operator accepted when restoring the confirmation barrier
// (2026-09-14): a fast multi-hop swap where each hero is seen exactly once
// never repeats a guid, so its hops collapse back into the first segment
// instead of one segment per hero. The raw vote still surfaces it -
// contested with the runner-up as alt_guid - so it is not invisible, just
// without a timed segment of its own.
test('a three-way swap with one read each collapses to one segment, but stays contested', () => {
  const soj = [['SOJOURN', 0.6], ['dps1', 0.9], ['dps2', 0.9], ['sup1', 0.9], ['sup2', 0.9]];
  const ashe = [['ASHE', 0.85], ['dps1', 0.9], ['dps2', 0.9], ['sup1', 0.9], ['sup2', 0.9]];
  const tracer = [['TRACER', 0.89], ['dps1', 0.9], ['dps2', 0.9], ['sup1', 0.9], ['sup2', 0.9]];
  const got = R.rounds(
    [sample(50, soj, soj), sample(150, ashe, ashe), sample(250, tracer, tracer)],
    ROUNDS, { heroRoles: ROLES });
  const slot = got[0].a[0];
  const segs = slot.segments;
  assert.strictEqual(segs.length, 1, 'no guid ever repeated, so no confirmed segment');
  assert.strictEqual(segs[0].guid, 'SOJOURN', 'collapses onto the first-read hero');
  assert.strictEqual(slot.contested, true, 'the raw vote still says the slot split');
  assert.ok(slot.flags.includes('contested'));
});

test('a flicker back and forth produces one segment per run, in order', () => {
  const a2 = [['A', 0.9], ['dps1', 0.9], ['dps2', 0.9], ['sup1', 0.9], ['sup2', 0.9]];
  const b2 = [['B', 0.9], ['dps1', 0.9], ['dps2', 0.9], ['sup1', 0.9], ['sup2', 0.9]];
  const got = R.rounds(
    [sample(50, a2, a2), sample(100, b2, b2), sample(150, b2, b2),
     sample(200, a2, a2), sample(250, a2, a2)],
    ROUNDS, { heroRoles: ROLES });
  const segs = got[0].a[0].segments;
  assert.deepStrictEqual(segs.map((s) => s.guid), ['A', 'B', 'A']);
  assert.deepStrictEqual(segs.map((s) => s.from_t), [50, 100, 200]);
});

test('reads inside the first 10s of a round do not seed or extend a segment', () => {
  const comp = [['tank', 0.95], ['dps1', 0.95], ['dps2', 0.95], ['sup1', 0.95], ['sup2', 0.95]];
  const got = R.rounds(
    [sample(3, comp, comp), sample(7, comp, comp), sample(50, comp, comp)],
    ROUNDS, { heroRoles: ROLES });
  const segs = got[0].a[0].segments;
  assert.strictEqual(segs.length, 1);
  assert.strictEqual(segs[0].from_t, 50, 'the grace-window reads at 3s/7s are dropped, not used as the start');
});

test('a slot with only pre-grace reads has no segments at all', () => {
  const comp = [['tank', 0.95], ['dps1', 0.95], ['dps2', 0.95], ['sup1', 0.95], ['sup2', 0.95]];
  const got = R.rounds([sample(3, comp, comp), sample(7, comp, comp)], ROUNDS, { heroRoles: ROLES });
  assert.deepStrictEqual(got[0].a[0].segments, []);
});

test('a slot that never read at all has no segments', () => {
  const withHole = [['', 0], ['dps1', 0.9], ['dps2', 0.9], ['sup1', 0.9], ['sup2', 0.9]];
  const got = R.rounds([sample(100, withHole, withHole)], ROUNDS, { heroRoles: ROLES });
  assert.deepStrictEqual(got[0].a[0].segments, []);
});

test('an unsampled round emits empty slots with segments: []', () => {
  const comp = [['tank', 0.95], ['dps1', 0.95], ['dps2', 0.95], ['sup1', 0.95], ['sup2', 0.95]];
  const got = R.rounds([sample(100, comp, comp)], ROUNDS, { heroRoles: ROLES });
  assert.deepStrictEqual(got[1].a[0].segments, [], 'round 2 got zero samples');
});

test('resolve is pure: it does not mutate the samples it is given', () => {
  const comp = [['tank', 0.95], ['dps1', 0.95], ['dps2', 0.95], ['sup1', 0.95], ['sup2', 0.95]];
  const samples = [sample(100, comp, comp)];
  const snapshot = JSON.stringify(samples);
  R.rounds(samples, ROUNDS, { heroRoles: ROLES });
  assert.strictEqual(JSON.stringify(samples), snapshot);
});

// --- needsReview: drives review_out.js's initial status ---------------------

test('needsReview is false for a map with no flags at all', () => {
  const comp = [['tank', 0.95], ['dps1', 0.95], ['dps2', 0.95], ['sup1', 0.95], ['sup2', 0.95]];
  const got = R.rounds(
    [sample(100, comp, comp), sample(200, comp, comp), sample(500, comp, comp)],
    ROUNDS, { heroRoles: ROLES });
  assert.strictEqual(R.needsReview(got), false);
});

test('needsReview is false for a map whose only flag is a resolved swap', () => {
  const early = [['DVA', 0.95], ['dps1', 0.9], ['dps2', 0.9], ['sup1', 0.9], ['sup2', 0.9]];
  const late = [['DMON', 0.95], ['dps1', 0.9], ['dps2', 0.9], ['sup1', 0.9], ['sup2', 0.9]];
  const roles = Object.assign({ DVA: 'tank', DMON: 'tank' }, ROLES);
  const got = R.rounds(
    [sample(50, early, early), sample(175, late, late), sample(225, late, late), sample(500, late, late)],
    ROUNDS, { heroRoles: roles });
  assert.strictEqual(got[0].a[0].contested, true, 'sanity: this fixture is the playtime-even-split case');
  assert.strictEqual(R.needsReview(got), false, 'a resolved swap alone is not a reason to review');
});

test('needsReview is true for a genuine flag, contested or not', () => {
  const weak = [['SHION', 0.55], ['dps1', 0.9], ['dps2', 0.9], ['sup1', 0.9], ['sup2', 0.9]];
  const got = R.rounds([sample(100, weak, weak), sample(200, weak, weak)], ROUNDS, { heroRoles: ROLES });
  assert.ok(got[0].a[0].flags.includes('low-score'));
  assert.strictEqual(R.needsReview(got), true);
});

test('needsReview is true for a round-level flag (round-unsampled/sparse-round)', () => {
  const comp = [['tank', 0.95], ['dps1', 0.95], ['dps2', 0.95], ['sup1', 0.95], ['sup2', 0.95]];
  const got = R.rounds([sample(100, comp, comp)], ROUNDS, { heroRoles: ROLES });
  assert.ok(got[1].flags.includes('round-unsampled'));
  assert.strictEqual(R.needsReview(got), true);
});

// --- leaver detection: ABSENT and UNSELECTED are their own states, not ------
// --- generic no-read / unknown-hero noise ----------------------------------
//
// phases.readHud never hands a matcher an untinted cell (see its ABSENT_GUID)
// - it hands resolve.js the sentinel directly. A slot that reads ABSENT every
// frame is a card that left the HUD outright, which is a different fact from
// "we could not read whoever is there" (no-read) and must not be graded as an
// unrecognised hero either.

test('a slot whose card left the HUD resolves ABSENT, flagged player-absent', () => {
  const gone = [[R.ABSENT_GUID, null], ['dps1', 0.9], ['dps2', 0.9], ['sup1', 0.9], ['sup2', 0.9]];
  const got = R.rounds([sample(100, gone, gone), sample(200, gone, gone)], ROUNDS, { heroRoles: ROLES });

  const slot = got[0].a[0];
  assert.strictEqual(slot.guid, R.ABSENT_GUID);
  assert.deepStrictEqual(slot.flags, ['player-absent']);
});

test('an UNSELECTED read resolves to it, flagged not-picked, not unknown-hero', () => {
  const picking = [[R.UNSELECTED_GUID, 0.9], ['dps1', 0.9], ['dps2', 0.9], ['sup1', 0.9], ['sup2', 0.9]];
  const got = R.rounds([sample(100, picking, picking), sample(200, picking, picking)], ROUNDS, { heroRoles: ROLES });

  const slot = got[0].a[0];
  assert.strictEqual(slot.guid, R.UNSELECTED_GUID);
  assert.deepStrictEqual(slot.flags, ['not-picked']);
});

test('a leaver never has a player to attribute - that alone does not add a second flag', () => {
  // A real capture attributes an ABSENT slot's necessarily-empty name row to
  // no player, every time - that is not new information once player-absent
  // already says so; flagging it too would just say the same fact twice.
  const gone = [[R.ABSENT_GUID, null], ['dps1', 0.9], ['dps2', 0.9], ['sup1', 0.9], ['sup2', 0.9]];
  const attribution = {
    a: { ids: [null, 'p2', 'p3', 'p4', 'p5'], conf: [null, 'matched', 'matched', 'matched', 'matched'] },
    b: { ids: ['q1', 'q2', 'q3', 'q4', 'q5'], conf: ['matched', 'matched', 'matched', 'matched', 'matched'] },
  };
  const got = R.rounds(
    [sample(100, gone, gone), sample(200, gone, gone)],
    [{ from_t: 0, to_t: 300 }], { heroRoles: ROLES, attribution: attribution });

  assert.deepStrictEqual(got[0].a[0].flags, ['player-absent']);
});

test('needsReview does not fire for not-picked alone - every map opens with it', () => {
  // UNSELECTED is the correct answer for the hero-select seconds every map
  // starts with, on every slot. Flagging it the way low-score/unknown-hero
  // do would put every single map in front of an operator for nothing.
  const picking = [[R.UNSELECTED_GUID, 0.9], ['dps1', 0.9], ['dps2', 0.9], ['sup1', 0.9], ['sup2', 0.9]];
  const got = R.rounds(
    [sample(100, picking, picking), sample(200, picking, picking)],
    [{ from_t: 0, to_t: 300 }], { heroRoles: ROLES });
  assert.strictEqual(R.needsReview(got), false);
});

// A leaver is rare enough - unlike "still picking" - that the operator wants
// to see it: 2026-09-16, "im okay with leavers triggering a flag as its
// fairly uncommon."
test('needsReview DOES fire for player-absent - a leaver is rare enough to be worth a look', () => {
  const gone = [[R.ABSENT_GUID, null], ['dps1', 0.9], ['dps2', 0.9], ['sup1', 0.9], ['sup2', 0.9]];
  const comp = [['tank', 0.95], ['dps1', 0.95], ['dps2', 0.95], ['sup1', 0.95], ['sup2', 0.95]];
  const got = R.rounds(
    [sample(100, gone, comp), sample(200, gone, comp)],
    [{ from_t: 0, to_t: 300 }], { heroRoles: ROLES });
  assert.strictEqual(R.needsReview(got), true);
});

// tools/replay_bot/reprocess_hero_match.test.js
// Covers guardAgainstRegression(): the pure logic that stops reprocessing
// from making an already-good read WORSE.
//
// Root cause it guards against (found 2026-09-19, live corpus reprocess):
// review_out.js's mapEntry() only writes a round/side's per-sample gallery
// for samples that had a savable framePath - a sample lost at capture time
// (no framePath) silently shrinks the gallery instead of leaving any trace.
// When the ONE surviving gallery sample happens to fall inside resolve.js's
// ASSEMBLE_GRACE_S window, segmentSlot() correctly drops it as a pick-phase
// read - but with no OTHER sample to fall back on, the round/side goes from
// a real single-segment read to no-read. Reprocessing has strictly LESS
// evidence than the original live capture did (the original had access to
// frames that were never retained to disk) so it must never let this look
// like new information - the original round/side's data is authoritative
// whenever reprocessing would only make it worse.

const test = require('node:test');
const assert = require('node:assert');
const { guardAgainstRegression } = require('./reprocess_hero_match.js');

const slot = (guid) => ({ guid, name: guid, support: 1, reads: [0.9], contested: false, alt_guid: null, segments: [], flags: [] });
const noRead = () => ({ guid: null, name: null, support: 0, reads: [], contested: false, alt_guid: null, segments: [], flags: ['no-read'] });
const round = (round_no, a, b) => ({ round_no, from_t: 0, to_t: 300, a, b, flags: [] });

test('a round/side that regressed from a real guid to no-read is reverted to its original data', () => {
  const original = [round(1, [slot('TANK'), slot('DPS1'), slot('DPS2'), slot('SUP1'), slot('SUP2')], [slot('WIDOW'), slot('DPS1'), slot('DPS2'), slot('SUP1'), slot('SUP2')])];
  const reprocessed = [round(1, [noRead(), noRead(), noRead(), noRead(), noRead()], [slot('WIDOW'), slot('DPS1'), slot('DPS2'), slot('SUP1'), slot('SUP2')])];

  const got = guardAgainstRegression(original, reprocessed);

  assert.deepStrictEqual(got[0].a, original[0].a, 'side a regressed, so it reverts whole-cloth to the original');
  assert.deepStrictEqual(got[0].b, reprocessed[0].b, 'side b did not regress, so the reprocessed (possibly improved) read stands');
});

test('a genuine hero correction (guid changes but stays non-null) is not touched', () => {
  const original = [round(1, [slot('SOJOURN'), slot('DPS1'), slot('DPS2'), slot('SUP1'), slot('SUP2')], [slot('TANK'), slot('DPS1'), slot('DPS2'), slot('SUP1'), slot('SUP2')])];
  const reprocessed = [round(1, [slot('ASHE'), slot('DPS1'), slot('DPS2'), slot('SUP1'), slot('SUP2')], [slot('TANK'), slot('DPS1'), slot('DPS2'), slot('SUP1'), slot('SUP2')])];

  const got = guardAgainstRegression(original, reprocessed);

  assert.deepStrictEqual(got, reprocessed, 'no null appeared anywhere, so nothing reverts');
});

test('a slot that was already no-read and stays no-read is not treated as a regression', () => {
  const original = [round(1, [noRead(), slot('DPS1'), slot('DPS2'), slot('SUP1'), slot('SUP2')], [slot('TANK'), slot('DPS1'), slot('DPS2'), slot('SUP1'), slot('SUP2')])];
  const reprocessed = [round(1, [noRead(), slot('DPS1'), slot('DPS2'), slot('SUP1'), slot('SUP2')], [slot('TANK'), slot('DPS1'), slot('DPS2'), slot('SUP1'), slot('SUP2')])];

  const got = guardAgainstRegression(original, reprocessed);

  assert.deepStrictEqual(got, reprocessed);
});

test('a genuine recovery (original no-read, reprocessed finds a guid) is kept, not reverted', () => {
  const original = [round(1, [noRead(), slot('DPS1'), slot('DPS2'), slot('SUP1'), slot('SUP2')], [slot('TANK'), slot('DPS1'), slot('DPS2'), slot('SUP1'), slot('SUP2')])];
  const reprocessed = [round(1, [slot('MERCY'), slot('DPS1'), slot('DPS2'), slot('SUP1'), slot('SUP2')], [slot('TANK'), slot('DPS1'), slot('DPS2'), slot('SUP1'), slot('SUP2')])];

  const got = guardAgainstRegression(original, reprocessed);

  assert.strictEqual(got[0].a[0].guid, 'MERCY', 'null -> real guid is an improvement, never a regression');
});

test('one regressed slot among five on a side reverts the whole side, matching the observed failure shape', () => {
  // The live incident reverted all 5 slots on both sides together (the whole
  // round/side shares one sample set) - a single regressed slot is enough to
  // signal "this round/side's recovered evidence was insufficient" for all 5.
  const original = [round(1, [slot('A1'), slot('A2'), slot('A3'), slot('A4'), slot('A5')], [])];
  const reprocessed = [round(1, [slot('A1'), noRead(), slot('A3'), slot('A4'), slot('A5')], [])];

  const got = guardAgainstRegression(original, reprocessed);

  assert.deepStrictEqual(got[0].a, original[0].a);
});

test('rounds the map never touched (no frames) pass through unchanged', () => {
  const original = [round(1, [slot('A')], []), round(2, [slot('B')], [])];
  const reprocessed = [round(1, [slot('A')], []), round(2, [slot('B')], [])];

  const got = guardAgainstRegression(original, reprocessed);

  assert.deepStrictEqual(got, reprocessed);
});

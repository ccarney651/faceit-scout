const test = require('node:test');
const assert = require('node:assert');
const EM = require('./emit.js');

const A = ['0x02E00000000001EC', '0x02E00000000004E3', 'custom:d_mon',
  '0x02E000000000052C', '0x02E000000000013B'];
const B = ['0x02E0000000000200', '0x02E0000000000201', '0x02E0000000000202',
  '0x02E0000000000203', '0x02E0000000000204'];

function obs(over) {
  return Object.assign({
    t: 0, clock: '9:57', score_a: 0, score_b: 0,
    heroes_a: A.slice(), heroes_b: B.slice(),
  }, over);
}

// One round covering everything, as segment.rounds() returns it.
function oneRound(samples) {
  return [{ index: 0, from_t: samples[0].t, to_t: samples[samples.length - 1].t }];
}

// A code entry as docs/capture/data.json ships it. Note the renames: `map`
// becomes `map_name`, `code` becomes `demo_code`, and t1/t2 become the side
// team ids. Getting either team the wrong way round would attribute every comp
// on the map to the opponent, which no downstream check would catch.
function codeEntry(over) {
  return Object.assign({
    code: '2T857A',
    match_id: '1-4007a070',
    game_no: 2,
    map: 'Samoa',
    map_category: 'Control',
    map_guid: '0x0800000000000EC0',
    division: 'NA Expert',
    team_a: 'CrossCanines',
    team_b: 'ELMT Normal',
    t1: 'team-one-id',
    t2: 'team-two-id',
    finished_at: '2026-09-08T02:33:20Z',
  }, over);
}

const PROFILE = { w: 2560, h: 1440, hud_variant: 'replay-bot' };

// Provenance is the whole reason the bot's output is segregated: a run can be
// audited, weighted or ignored wholesale, and bot rows can be compared against
// an operator's on the same map. A file that claimed to be browser-0.2 would
// make its own output unauditable.
test('the contribution file announces itself as bot-produced', () => {
  const f = EM.file([], { contributor: 'replay-bot' });
  assert.strictEqual(f.tool_version, 'replay-bot-0.1');
  assert.notStrictEqual(f.tool_version, 'browser-0.2');
  assert.strictEqual(f.contributor, 'replay-bot');
  assert.strictEqual(f.format, 1);
});

test('the file carries the maps it was given', () => {
  const s = [obs({ t: 0 })];
  const m = EM.mapRecord(codeEntry(), s, oneRound(s), { profile: PROFILE });
  const f = EM.file([m], { contributor: 'replay-bot' });
  assert.strictEqual(f.maps.length, 1);
  assert.strictEqual(f.maps[0].demo_code, '2T857A');
});

test('the map record renames the feed fields onto the contribution schema', () => {
  const s = [obs({ t: 0 })];
  const m = EM.mapRecord(codeEntry(), s, oneRound(s), { profile: PROFILE });
  assert.strictEqual(m.demo_code, '2T857A');
  assert.strictEqual(m.map_name, 'Samoa');
  assert.strictEqual(m.game_no, 2);
  assert.strictEqual(m.side_a_team_id, 'team-one-id');
  assert.strictEqual(m.side_a_team, 'CrossCanines');
  assert.strictEqual(m.side_b_team_id, 'team-two-id');
  assert.strictEqual(m.side_b_team, 'ELMT Normal');
});

test('the bot leaves FACEIT-owned fields alone rather than inventing them', () => {
  const s = [obs({ t: 0 })];
  const m = EM.mapRecord(codeEntry(), s, oneRound(s), { profile: PROFILE });
  assert.strictEqual(m.winner_side, null, 'FACEIT knows the winner, the bot does not');
  assert.deepStrictEqual(m.bans, [], 'FACEIT supplies bans');
});

test('every observation is an absence, never a guess, for what the bot cannot read', () => {
  const s = [obs({ t: 0 })];
  const m = EM.mapRecord(codeEntry(), s, oneRound(s), { profile: PROFILE });
  m.observations.forEach((o) => {
    assert.strictEqual(o.sub_map, null);
    assert.strictEqual(o.phase, null);
    assert.deepStrictEqual(o.pairs, []);
  });
});

test('attribution zips ids onto heroes in slot order, for both sides', () => {
  const s = [obs({ t: 0 })];
  const attribution = {
    a: { ids: ['p1', 'p2', null, 'p4', 'p5'], conf: ['matched', 'matched', null, 'forced', 'matched'] },
    b: { ids: ['q1', 'q2', 'q3', 'q4', 'q5'], conf: ['matched', 'matched', 'matched', 'matched', 'matched'] },
  };
  const m = EM.mapRecord(codeEntry(), s, oneRound(s), { profile: PROFILE, attribution });
  const [oa, ob] = m.observations;
  assert.deepStrictEqual(oa.pairs, A.map((g, i) => [g, attribution.a.ids[i]]));
  assert.deepStrictEqual(ob.pairs, B.map((g, i) => [g, attribution.b.ids[i]]));
  // An abstained slot is a null player_id written through, not a dropped pair -
  // a missing pair and an abstained one must stay tellable apart.
  assert.strictEqual(oa.pairs.length, 5);
  assert.strictEqual(oa.pairs[2][1], null);
});

test('a side missing from the attribution result still yields pairs: []', () => {
  const s = [obs({ t: 0 })];
  const attribution = { a: { ids: ['p1', 'p2', 'p3', 'p4', 'p5'], conf: [] } };
  const m = EM.mapRecord(codeEntry(), s, oneRound(s), { profile: PROFILE, attribution });
  const [oa, ob] = m.observations;
  assert.strictEqual(oa.pairs.length, 5);
  assert.deepStrictEqual(ob.pairs, []);
});

test('a sample becomes one observation per side, because the schema is per-side', () => {
  const s = [obs({ t: 0 })];
  const got = EM.observations(s, oneRound(s));
  assert.strictEqual(got.length, 2);
  assert.deepStrictEqual(got.map((o) => o.side), ['a', 'b']);
});

test("each side's observation carries that side's heroes", () => {
  const s = [obs({ t: 0 })];
  const got = EM.observations(s, oneRound(s));
  assert.deepStrictEqual(got[0].heroes, A);
  assert.deepStrictEqual(got[1].heroes, B);
});

test('a sample is stamped with the round it falls in, 1-based like owdb', () => {
  const s = [obs({ t: 0 }), obs({ t: 30 }), obs({ t: 60 })];
  const rounds = [
    { index: 0, from_t: 0, to_t: 30 },
    { index: 1, from_t: 60, to_t: 60 },
  ];
  const got = EM.observations(s, rounds);
  assert.deepStrictEqual(got.map((o) => o.round_no), [1, 1, 1, 1, 2, 2]);
});

// A sample outside every round means segmentation and the sweep disagree. That
// is a bug worth seeing, so it must not be quietly filed under round 1.
test('a sample in no round is stamped null rather than guessed', () => {
  const s = [obs({ t: 999 })];
  const got = EM.observations(s, [{ index: 0, from_t: 0, to_t: 30 }]);
  assert.strictEqual(got[0].round_no, null);
});

// sample_ts_ms is milliseconds; the sweep counts seconds. Dropping this
// conversion would put every observation of a 20-minute map inside the first
// 1.2 seconds of it.
test('ts is milliseconds, not the sweep\'s seconds', () => {
  const s = [obs({ t: 90 })];
  const got = EM.observations(s, oneRound(s));
  assert.strictEqual(got[0].ts, 90000);
});

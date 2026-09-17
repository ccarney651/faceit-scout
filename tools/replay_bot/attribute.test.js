// attribute.js: which FACEIT player is in which HUD slot, resolved from a
// whole map's already-collected samples. Pure, synchronous, no image loading
// or OCR here - names are already-extracted text by the time this runs
// (phases.readNames, captured once per sample, aggregated here across a
// whole map). See specs/2026-09-17-replay-bot-disconnect-identity-design.md.
const test = require('node:test');
const assert = require('node:assert');
const A = require('./attribute.js');

const CODE = { match_id: 'm1', game_no: 1, t1: 'team-a', t2: 'team-b' };

function lineupFeed() {
  return {
    hero_roles: { tank1: 'Tank', dmg1: 'Damage', dmg2: 'Damage', sup1: 'Support', sup2: 'Support' },
    lineups: {
      'm1:1': {
        'team-a': {
          players: [
            { id: 'a-noki', nick: 'noki_ow', game_name: 'Noki', role: 'Tank' },
            { id: 'a-vilperttis', nick: 'vilp', game_name: 'Vilperttis', role: 'Damage' },
            { id: 'a-jopez', nick: 'jopez_ow', game_name: 'Jøpez', role: 'Damage' },
            { id: 'a-lambinen', nick: 'lambi', game_name: 'Lambinen', role: 'Support' },
            { id: 'a-karhu', nick: 'karhu_ow', game_name: 'Karhu', role: 'Support' },
          ],
        },
        'team-b': {
          players: [
            { id: 'b-rawan', nick: 'rawan_ow', game_name: 'Rawan', role: 'Tank' },
            { id: 'b-moon', nick: 'moon_ow', game_name: 'Møøn', role: 'Damage' },
            { id: 'b-cat', nick: 'cat_ow', game_name: 'Cat', role: 'Damage' },
            { id: 'b-cioudo', nick: 'cioudo_ow', game_name: 'Çioüdo', role: 'Support' },
            { id: 'b-zayano', nick: 'zayano_ow', game_name: 'Zayano', role: 'Support' },
          ],
        },
      },
    },
  };
}

// The hero already recognised in each slot - roles line up 1-1 with
// lineupFeed()'s players above, so the role constraint alone should be able
// to place every slot once real names confirm the ordering.
function sampleHeroes() {
  return {
    a: [{ guid: 'tank1' }, { guid: 'dmg1' }, { guid: 'dmg2' }, { guid: 'sup1' }, { guid: 'sup2' }],
    b: [{ guid: 'tank1' }, { guid: 'dmg1' }, { guid: 'dmg2' }, { guid: 'sup1' }, { guid: 'sup2' }],
  };
}

test('playersFor returns [] when the feed has no lineup for this code', () => {
  assert.deepStrictEqual(A.playersFor({}, CODE, 'a'), []);
  assert.deepStrictEqual(A.playersFor({ lineups: {} }, CODE, 'a'), []);
});

test('playersFor returns [] when the lineup has no entry for this team id', () => {
  const feed = { lineups: { 'm1:1': { 'some-other-team': { players: [] } } } };
  assert.deepStrictEqual(A.playersFor(feed, CODE, 'a'), []);
});

test('playersFor carries both game_name and nick, so either can match', () => {
  const players = A.playersFor(lineupFeed(), CODE, 'a');
  assert.strictEqual(players.length, 5);
  assert.deepStrictEqual(players[0], { id: 'a-noki', names: ['Noki', 'noki_ow'], role: 'Tank' });
});

test('slotRolesFor looks up each slot\'s recognised hero in hero_roles', () => {
  const heroRoles = { g1: 'Tank', g2: 'Damage' };
  const reads = [{ guid: 'g1' }, { guid: 'g2' }, { guid: 'unknown' }, null, { guid: undefined }];
  assert.deepStrictEqual(A.slotRolesFor(heroRoles, reads), ['Tank', 'Damage', null, null, null]);
});

// ---- attributeFromSamples -------------------------------------------------
//
// specs/2026-09-17-replay-bot-disconnect-identity-design.md. Pure, synchronous,
// no image loading or OCR here - names are already-extracted text by the time
// this runs (phases.readNames, captured once per sample, aggregated here
// across a whole map). Uses the file's existing lineupFeed()/CODE fixtures -
// team-a: Noki(tank1)/Vilperttis(dmg1)/Jøpez(dmg2)/Lambinen(sup1)/Karhu(sup2).
// team-b: Rawan(tank1)/Møøn(dmg1)/Cat(dmg2)/Çioüdo(sup1)/Zayano(sup2).

// One sample's worth of {a, b} hero cells + {a, b} name-OCR strings. `heroes`
// is five [guid, score] pairs per side.
function sample(t, namesA, namesB, heroesA, heroesB) {
  const cell = ([guid, score]) => ({ name: guid, guid, score });
  return {
    t,
    a: heroesA.map(cell), b: heroesB.map(cell),
    names: { a: namesA, b: namesB },
  };
}

const NAMES_A = ['Noki', 'Vilperttis', 'Jøpez', 'Lambinen', 'Karhu'];
const NAMES_B = ['Rawan', 'Møøn', 'Cat', 'Çioüdo', 'Zayano'];
const HEROES = [['tank1', 0.9], ['dmg1', 0.9], ['dmg2', 0.9], ['sup1', 0.9], ['sup2', 0.9]];
const ABSENT_HEROES = [['tank1', 0.9], ['dmg1', 0.9], ['dmg2', 0.9], ['sup1', 0.9], ['ABSENT', null]];

test('attributeFromSamples resolves every slot when nothing ever disconnects', () => {
  const samples = [
    sample(30, NAMES_A, NAMES_B, HEROES, HEROES),
    sample(60, NAMES_A, NAMES_B, HEROES, HEROES),
    sample(90, NAMES_A, NAMES_B, HEROES, HEROES),
  ];
  const out = A.attributeFromSamples(samples, lineupFeed(), CODE);
  assert.strictEqual(out.correctedSamples.length, 3);
  out.correctedSamples.forEach((s) => {
    assert.strictEqual(s.a[0].guid, 'tank1', "slot 0 is Noki's hero");
    assert.strictEqual(s.a[4].guid, 'sup2', "slot 4 is Karhu's hero");
  });
  assert.deepStrictEqual(out.attribution.a.ids, ['a-noki', 'a-vilperttis', 'a-jopez', 'a-lambinen', 'a-karhu']);
});

test('a mid-round disconnect at an interior slot re-keys the shifted samples back to the right canonical slot', () => {
  // Lambinen (slot 3, sup1) disconnects; Karhu (slot 4, sup2) visually
  // compacts into slot 3's position. Position 4 reads nothing. Three
  // "before" samples to one "during" sample, so the canonical vote clearly
  // favors the undisturbed majority (spec §3.2's MODE, not needing >50%,
  // but this keeps the test unambiguous either way).
  const duringNamesA = ['Noki', 'Vilperttis', 'Jøpez', 'Karhu', ''];
  const duringHeroesA = [['tank1', 0.9], ['dmg1', 0.9], ['dmg2', 0.9], ['sup2', 0.9], ['ABSENT', null]];
  const samples = [
    sample(30, NAMES_A, NAMES_B, HEROES, HEROES),
    sample(60, NAMES_A, NAMES_B, HEROES, HEROES),
    sample(90, NAMES_A, NAMES_B, HEROES, HEROES),
    sample(120, duringNamesA, NAMES_B, duringHeroesA, HEROES), // side a only - side b never disconnects
  ];
  const out = A.attributeFromSamples(samples, lineupFeed(), CODE);

  const shiftedA = out.correctedSamples[3].a; // the t=120 sample, side a
  assert.strictEqual(shiftedA[3].guid, 'ABSENT', 'slot 3 (the real leaver, Lambinen) reads absent, not slot 4');
  assert.strictEqual(shiftedA[4].guid, 'sup2', "slot 4's hero read (Karhu) is recovered from visual position 3");
});

test('disconnect at the rightmost slot needs no shift - already correct today, must stay correct', () => {
  const namesGone = ['Noki', 'Vilperttis', 'Jøpez', 'Lambinen', ''];
  const samples = [
    sample(30, NAMES_A, NAMES_B, HEROES, HEROES),
    sample(60, NAMES_A, NAMES_B, HEROES, HEROES),
    sample(90, namesGone, NAMES_B, ABSENT_HEROES, HEROES),
  ];
  const out = A.attributeFromSamples(samples, lineupFeed(), CODE);
  assert.strictEqual(out.correctedSamples[2].a[4].guid, 'ABSENT');
  assert.strictEqual(out.correctedSamples[2].a[3].guid, 'sup1', 'slot 3 (Lambinen) unaffected, no shift needed');
});

test('a 4-slot shift (slot 0 disconnects) re-keys all four downstream slots', () => {
  // Noki (slot 0, tank1) disconnects - Vilperttis/Jøpez/Lambinen/Karhu all
  // compact one slot to the left; position 4 reads nothing.
  const duringNamesA = ['Vilperttis', 'Jøpez', 'Lambinen', 'Karhu', ''];
  const duringHeroesA = [['dmg1', 0.9], ['dmg2', 0.9], ['sup1', 0.9], ['sup2', 0.9], ['ABSENT', null]];
  const samples = [
    sample(30, NAMES_A, NAMES_B, HEROES, HEROES),
    sample(60, NAMES_A, NAMES_B, HEROES, HEROES),
    sample(90, NAMES_A, NAMES_B, HEROES, HEROES),
    sample(120, duringNamesA, NAMES_B, duringHeroesA, HEROES),
  ];
  const out = A.attributeFromSamples(samples, lineupFeed(), CODE);
  const shifted = out.correctedSamples[3].a;
  assert.strictEqual(shifted[0].guid, 'ABSENT', 'Noki genuinely gone');
  assert.strictEqual(shifted[1].guid, 'dmg1', "Vilperttis' hero recovered into slot 1");
  assert.strictEqual(shifted[2].guid, 'dmg2', "Jøpez' hero recovered into slot 2");
  assert.strictEqual(shifted[3].guid, 'sup1', "Lambinen's hero recovered into slot 3");
  assert.strictEqual(shifted[4].guid, 'sup2', "Karhu's hero recovered into slot 4");
});

test('reconnection: samples after the return match the original canonical slot again', () => {
  const duringNamesA = ['Noki', 'Vilperttis', 'Jøpez', 'Karhu', ''];
  const duringHeroesA = [['tank1', 0.9], ['dmg1', 0.9], ['dmg2', 0.9], ['sup2', 0.9], ['ABSENT', null]];
  const samples = [
    sample(30, NAMES_A, NAMES_B, HEROES, HEROES),
    sample(60, NAMES_A, NAMES_B, HEROES, HEROES),
    sample(90, duringNamesA, NAMES_B, duringHeroesA, HEROES),  // Lambinen disconnects
    sample(120, NAMES_A, NAMES_B, HEROES, HEROES),             // reconnected
    sample(150, NAMES_A, NAMES_B, HEROES, HEROES),
  ];
  const out = A.attributeFromSamples(samples, lineupFeed(), CODE);
  assert.strictEqual(out.correctedSamples[3].a[3].guid, 'sup1', "back to Lambinen's hero after reconnecting");
  assert.strictEqual(out.correctedSamples[3].a[4].guid, 'sup2', "Karhu correctly back in her own slot too");
});

test('a name illegible on EVERY sample, unrelated to any disconnect, does not lose hero data', () => {
  // Neither Damage name ever OCRs to anything usable - persistently bad
  // plates, nothing to do with a disconnect. Both must stay blank (not just
  // one): assign.js's own decisive-elimination path (a single STRONG_NAME_
  // SCORE-clean read resolves its partner by elimination in a two-player
  // pool, unmodified pre-existing behaviour) would otherwise still resolve
  // the slot from the OTHER Damage player's clean name - this test is about
  // genuine, whole-pool ambiguity, not one lucky partner read. The hero
  // reads must survive regardless.
  const namesA = ['Noki', '', '', 'Lambinen', 'Karhu'];
  const samples = [
    sample(30, namesA, NAMES_B, HEROES, HEROES),
    sample(60, namesA, NAMES_B, HEROES, HEROES),
  ];
  const out = A.attributeFromSamples(samples, lineupFeed(), CODE);
  assert.strictEqual(out.correctedSamples[0].a[1].guid, 'dmg1', 'hero data survives even though the name never resolved');
  assert.strictEqual(out.attribution.a.ids[1], null, 'attribution correctly stays unresolved for this slot');
});

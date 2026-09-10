// attribute.js: player attribution, without a real tesseract worker.
// The crop against a real frame is exercised here too (nameRow/nameCrop are
// not injected - only OCR is, matching how `io` is injected everywhere else
// in the bot), with a fake OCR standing in for tesseract so the suite stays
// fast and deterministic. See specs/2026-09-10-replay-bot-player-attribution-design.md.
const test = require('node:test');
const assert = require('node:assert');
const canvas = require('@napi-rs/canvas');
const C = require('./corpus.js');
const A = require('./attribute.js');

const skip = C.absent() || false;
const witness = C.NAMEPLATES[0];

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

// A custom: guid (D.Mon, or any hero FACEIT has not added yet) is absent from
// the feed's guid->role map. heroes.js's name-keyed ROLE_MAP is the fallback,
// so a role-locked tank still gets attributed.
test('slotRolesFor falls back to the name-keyed role map for a custom hero', () => {
  const reads = [
    { guid: 'custom:d_mon', name: 'D.Mon' },
    { guid: '0xKnown', name: 'Ana' },
    { guid: 'custom:nobody', name: 'Nobody' },
  ];
  assert.deepStrictEqual(
    A.slotRolesFor({ '0xKnown': 'Support' }, reads),
    ['Tank', 'Support', null]);
});

test('attributeMap resolves all ten slots against a real frame with an injected OCR', { skip }, async () => {
  const img = await canvas.loadImage(C.at(witness.file));
  const calls = [];
  const ocr = async () => { throw new Error('should not be called - see stubbed reads below'); };
  // Stubbing the OCR call itself (rather than asserting on the crop) keeps
  // this test about attribute.js's wiring, not about tesseract's accuracy -
  // that is measured live (§7 of the design), not in this suite. The reads
  // returned are exactly what real tesseract read off this frame tonight.
  const reads = { a: witness.a.slice(), b: witness.b.slice() };
  let i = { a: 0, b: 0 };
  const stub = A.make(async (cv) => {
    calls.push(cv);
    // Side is inferred from call order: five for a, then five for b.
    const side = calls.length <= 5 ? 'a' : 'b';
    const idx = side === 'a' ? calls.length - 1 : calls.length - 6;
    return reads[side][idx];
  });

  const out = await stub.attributeMap(img, sampleHeroes(), lineupFeed(), CODE);
  assert.strictEqual(calls.length, 10);

  assert.deepStrictEqual(out.a.ids, ['a-noki', 'a-vilperttis', 'a-jopez', 'a-lambinen', 'a-karhu']);
  assert.deepStrictEqual(out.b.ids, ['b-rawan', 'b-moon', 'b-cat', 'b-cioudo', 'b-zayano']);
  out.a.conf.concat(out.b.conf).forEach((c) => assert.ok(c === 'forced' || c === 'matched'));
});

// The replay viewer put the feed's team B on the LEFT strip. attributeMap must
// notice from the names and match each screen side against the team actually on
// it - otherwise every hero is filed under the opponent.
test('attributeMap detects a swapped orientation and assigns each side its real team', { skip }, async () => {
  const img = await canvas.loadImage(C.at(witness.file));
  // The frame's left names are team-a's, right are team-b's. Feed team-a/-b as
  // if the FEED had them the other way round: now the LEFT screen shows the
  // feed's "team B".
  const swappedFeed = lineupFeed();
  const tmp = swappedFeed.lineups['m1:1']['team-a'];
  swappedFeed.lineups['m1:1']['team-a'] = swappedFeed.lineups['m1:1']['team-b'];
  swappedFeed.lineups['m1:1']['team-b'] = tmp;

  const calls = [];
  const reads = { a: witness.a.slice(), b: witness.b.slice() };
  const stub = A.make(async () => {
    calls.push(1);
    const side = calls.length <= 5 ? 'a' : 'b';
    return reads[side][side === 'a' ? calls.length - 1 : calls.length - 6];
  });
  const out = await stub.attributeMap(img, sampleHeroes(), swappedFeed, CODE);

  assert.strictEqual(out.orientation, 'swapped', 'code.t2 is on the left');
  // The left screen shows Noki's team (a-* ids, now under the feed's team-b
  // key). Matched against the team actually on that side, not code.t1's.
  assert.deepStrictEqual(out.a.ids, ['a-noki', 'a-vilperttis', 'a-jopez', 'a-lambinen', 'a-karhu']);
  assert.deepStrictEqual(out.b.ids, ['b-rawan', 'b-moon', 'b-cat', 'b-cioudo', 'b-zayano']);
});

test('attributeMap reports orientation direct when the feed order holds', { skip }, async () => {
  const img = await canvas.loadImage(C.at(witness.file));
  const calls = [];
  const reads = { a: witness.a.slice(), b: witness.b.slice() };
  const stub = A.make(async () => {
    calls.push(1);
    const side = calls.length <= 5 ? 'a' : 'b';
    return reads[side][side === 'a' ? calls.length - 1 : calls.length - 6];
  });
  const out = await stub.attributeMap(img, sampleHeroes(), lineupFeed(), CODE);
  assert.strictEqual(out.orientation, 'direct');
});

test('attributeMap abstains every slot rather than guessing, when the feed has no lineup', { skip }, async () => {
  const img = await canvas.loadImage(C.at(witness.file));
  const stub = A.make(async () => 'irrelevant');
  const out = await stub.attributeMap(img, sampleHeroes(), {}, CODE);
  assert.deepStrictEqual(out.a.ids, [null, null, null, null, null]);
  assert.deepStrictEqual(out.b.ids, [null, null, null, null, null]);
  assert.strictEqual(out.orientation, null, 'no roster, so the side cannot be proven');
});

test('attributeMap still forces the singleton role when the name row cannot be found', async () => {
  // A blank canvas has no text anywhere, so nameRow legitimately finds
  // nothing - the real degraded path, not a mock standing in for it.
  const cv = canvas.createCanvas(2560, 1440);
  cv.getContext('2d').fillStyle = '#222'; cv.getContext('2d').fillRect(0, 0, 2560, 1440);

  const ocrCalls = [];
  const stub = A.make(async (x) => { ocrCalls.push(x); return 'unused'; });
  const out = await stub.attributeMap(cv, sampleHeroes(), lineupFeed(), CODE);

  assert.strictEqual(ocrCalls.length, 0, 'OCR must not run over an unlocated row');
  // Tank is a one-player pool - the constraint alone settles it, no name
  // evidence needed or used. Damage and Support are two-player pools: with
  // every read empty, both permutations score an identical 0 and assign()
  // correctly abstains rather than guessing which of the tied two is which.
  assert.strictEqual(out.a.ids[0], 'a-noki');
  assert.strictEqual(out.a.conf[0], 'forced');
  assert.deepStrictEqual(out.a.ids.slice(1), [null, null, null, null]);
  assert.strictEqual(out.b.ids[0], 'b-rawan');
  assert.strictEqual(out.b.conf[0], 'forced');
});

const test = require('node:test');
const assert = require('node:assert');
const B = require('./banrow.js');
const H = require('./heroes.js');

// The catalogue shape refs.json produces, using the spellings it really writes.
const CAT = [
  { n: 'Sombra', g: 'g-sombra' }, { n: 'Mauga', g: 'g-mauga' },
  { n: 'DVa', g: 'g-dva' }, { n: 'Lucio', g: 'g-lucio' },
  { n: 'Torbjorn', g: 'g-torb' }, { n: 'Soldier 76', g: 'g-s76' },
  { n: 'Ana', g: 'g-ana' }, { n: 'Genji', g: 'g-genji' },
];
const IDX = B.buildHeroIndex(CAT);
const ROLE = H.inferRole;

test('the display spellings the workshop draws reach the refs.json entries', () => {
  // Verified in game 2026-08-27: the HUD draws these, refs.json stores the
  // right-hand column, and one normalization has to bridge them.
  assert.strictEqual(B.normalizeHeroName('D.VA'), B.normalizeHeroName('DVa'));
  assert.strictEqual(B.normalizeHeroName('LÚCIO'), B.normalizeHeroName('Lucio'));
  assert.strictEqual(B.normalizeHeroName('TORBJÖRN'), B.normalizeHeroName('Torbjorn'));
  assert.strictEqual(B.normalizeHeroName('SOLDIER: 76'), B.normalizeHeroName('Soldier 76'));
});

test('findRow pulls the labelled line out of a multi-line OCR read', () => {
  const text = 'OWDB SCRIM\nBANS  : SOMBRA | MAUGA\nMAP   : SAMOA\n';
  assert.strictEqual(B.findRow(text, 'BANS'), 'SOMBRA | MAUGA');
  assert.strictEqual(B.findRow(text, 'MAP'), 'SAMOA');
  assert.strictEqual(B.findRow(text, 'NOPE'), null);
});

test('two bans of different roles are accepted and resolved to guids', () => {
  const r = B.parseBans('BANS  : SOMBRA | MAUGA', IDX, ROLE);
  assert.strictEqual(r.ok, true);
  assert.strictEqual(r.none, false);
  assert.deepStrictEqual(r.bans.map(b => b.g), ['g-sombra', 'g-mauga']);
});

test('an explicit none is a fact, not a failure to read', () => {
  const r = B.parseBans('BANS  : NONE', IDX, ROLE);
  assert.strictEqual(r.ok, true);
  assert.strictEqual(r.none, true);
  assert.deepStrictEqual(r.bans, []);
});

test('a missing row abstains rather than reporting no bans', () => {
  const r = B.parseBans('MAP   : SAMOA', IDX, ROLE);
  assert.strictEqual(r.ok, false);
  assert.match(r.why, /could not find/i);
});

test('exactly one ban is a misread - the game cannot start that way', () => {
  const r = B.parseBans('BANS  : SOMBRA', IDX, ROLE);
  assert.strictEqual(r.ok, false);
  assert.match(r.why, /two|one/i);
});

test('two bans sharing a role is a misread - the workshop forbids it', () => {
  const r = B.parseBans('BANS  : SOMBRA | GENJI', IDX, ROLE);
  assert.strictEqual(r.ok, false);
  assert.match(r.why, /role/i);
});

test('the role check runs on the catalogue spelling, not the OCR text', () => {
  // inferRole knows "Soldier 76" and does NOT know "SOLDIER: 76". Taking the
  // role from the OCR string would skip R2 for every punctuated hero, which is
  // precisely the set this module exists to handle. Both of these are Damage.
  const r = B.parseBans('BANS  : SOLDIER: 76 | GENJI', IDX, ROLE);
  assert.strictEqual(r.ok, false);
  assert.match(r.why, /role/i);
});

test('a hero resolves to the catalogue spelling, not what the OCR read', () => {
  const r = B.parseBans('BANS  : D.VA | GENJI', IDX, ROLE);
  assert.strictEqual(r.ok, true);
  assert.deepStrictEqual(r.bans.map(b => b.n), ['DVa', 'Genji']);
});

test('an unreadable hero abstains instead of guessing a near match', () => {
  const r = B.parseBans('BANS  : SOMBKA | MAUGA', IDX, ROLE);
  assert.strictEqual(r.ok, false);
  assert.match(r.why, /SOMBKA/);
});

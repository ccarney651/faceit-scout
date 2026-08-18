const test = require('node:test');
const assert = require('node:assert');
const Assign = require('./assign.js');

// A real lineup, deliberately the hostile one: The best in the west, whose
// Battle.net names an ASCII-restricted OCR mangles. See the design doc 1.
const LINEUP = [
  { id: 'p-tank', role: 'Tank',    names: ['Faisal', 'CP3_ow'] },
  { id: 'p-dps1', role: 'Damage',  names: ['ÄL7ÖTĦÌ', 'hadramout1'] },
  { id: 'p-dps2', role: 'Damage',  names: ['FreakyShadow', 'FreakyShadow'] },
  { id: 'p-sup1', role: 'Support', names: ['MineRabbit', 'MineRabbit'] },
  { id: 'p-sup2', role: 'Support', names: ['Mź7w', 'Mz7w'] },
];
const SLOT_ROLES = ['Tank', 'Damage', 'Damage', 'Support', 'Support'];

test('the tank is forced by the role constraint with no name evidence at all', () => {
  // Every read is garbage. The tank slot still resolves, because only one player
  // on the roster can possibly be standing in it.
  const r = Assign.assign(['', '', '', '', ''], LINEUP, SLOT_ROLES);
  assert.equal(r.ids[0], 'p-tank');
  assert.equal(r.conf[0], 'forced');
});

test('an unreadable HUD never guesses inside a contested pair', () => {
  const r = Assign.assign(['', '', '', '', ''], LINEUP, SLOT_ROLES);
  // Damage and support pairs each have two candidates and no evidence: abstain.
  assert.deepEqual(r.ids.slice(1), [null, null, null, null]);
  assert.deepEqual(r.conf.slice(1), [null, null, null, null]);
});

test('clean reads resolve every slot', () => {
  const r = Assign.assign(
    ['Faisal', 'AL7OTHI', 'FreakyShadow', 'MineRabbit', 'Mz7w'],
    LINEUP, SLOT_ROLES);
  assert.deepEqual(r.ids, ['p-tank', 'p-dps1', 'p-dps2', 'p-sup1', 'p-sup2']);
});

test('one good read in a pair resolves the partner by elimination', () => {
  // Only MineRabbit reads; the other support slot is settled because the pair is
  // an exact cover of two players over two slots.
  const r = Assign.assign(['', '', '', 'MineRabbit', 'xxxxx'], LINEUP, SLOT_ROLES);
  assert.equal(r.ids[3], 'p-sup1');
  assert.equal(r.ids[4], 'p-sup2');
});

test('the assignment is optimal, not greedy, inside a group', () => {
  // Reads arrive in the swapped order. A greedy first-best-wins pass can strand
  // the second slot; scoring whole permutations cannot.
  const r = Assign.assign(['Faisal', 'FreakyShadow', 'AL7OTHI', 'Mz7w', 'MineRabbit'],
    LINEUP, SLOT_ROLES);
  assert.deepEqual(r.ids, ['p-tank', 'p-dps2', 'p-dps1', 'p-sup2', 'p-sup1']);
});

test('the floor rejects noise that happens to favour one candidate', () => {
  // Junk that leans very slightly toward one support. Without FLOOR this is
  // exactly the case that produced 33.6% wrong assignments in the eval.
  const r = Assign.assign(['', '', '', 'm', 'zzzz'], LINEUP, SLOT_ROLES);
  assert.equal(r.ids[3], null);
  assert.equal(r.ids[4], null);
});

test('a role-count mismatch leaves that group unresolved but not the others', () => {
  // A misrecognised portrait puts three heroes in the damage group. The damage
  // slots are abandoned; the tank is unaffected.
  const roles = ['Tank', 'Damage', 'Damage', 'Damage', 'Support'];
  const r = Assign.assign(['Faisal', 'AL7OTHI', 'FreakyShadow', 'x', 'MineRabbit'],
    LINEUP, roles);
  assert.equal(r.ids[0], 'p-tank');
  assert.deepEqual(r.ids.slice(1, 4), [null, null, null]);
});

test('a player with no role from FACEIT leaves their group unresolved, never forced', () => {
  const lineup = LINEUP.map(p => p.id === 'p-dps2' ? { ...p, role: null } : p);
  const r = Assign.assign(['Faisal', 'AL7OTHI', 'FreakyShadow', 'MineRabbit', 'Mz7w'],
    lineup, SLOT_ROLES);
  assert.equal(r.ids[0], 'p-tank');       // unaffected
  assert.equal(r.ids[3], 'p-sup1');       // unaffected
  assert.deepEqual(r.ids.slice(1, 3), [null, null]);
});

test('a stroked Battle.net name matches through the transliteration fold', () => {
  // The whole point of the names.js fix: OCR can only ever emit "al7othi".
  const r = Assign.assign(['', 'AL7OTHI', 'zzzzzzz', '', ''], LINEUP, SLOT_ROLES);
  assert.equal(r.ids[1], 'p-dps1');
  assert.equal(r.conf[1], 'matched');
});

test('one decisive read carries its partner even when the pair mean is low', () => {
  // The real case from screenshots/Screenshot 2026-07-15 231549.png: tesseract
  // returned "H0Qf" for a perfectly legible PROXY while TWERKNATION read at 88.
  // The pair mean lands just under FLOOR, and vetoing both would lose a slot the
  // old name-only matcher resolved.
  const lineup = [
    { id: 'p-tank', role: 'Tank',    names: ['Mappsy'] },
    { id: 'p-sup1', role: 'Support', names: ['Proxy', 'Proxystyle'] },
    { id: 'p-sup2', role: 'Support', names: ['TWERKNATION', 'sexy_eden'] },
    { id: 'p-dps1', role: 'Damage',  names: ['Szatan', 'SzatanOW'] },
    { id: 'p-dps2', role: 'Damage',  names: ['Arclite'] },
  ];
  const roles = ['Support', 'Tank', 'Support', 'Damage', 'Damage'];
  const r = Assign.assign(['H0Qf', 'MAPPSY', "5.TWERKNATION'", 'JODAN', 'SZATAN'],
    lineup, roles);
  assert.equal(r.ids[2], 'p-sup2', 'the decisive read must be assigned');
  assert.equal(r.ids[0], 'p-sup1', 'its partner follows by elimination');
});

test('a decisive read still cannot rescue a group with no separation', () => {
  // Two players sharing an alias: the permutations tie, so the margin gate holds
  // even though one read matches outright. Elimination needs something to
  // eliminate.
  const lineup = [
    { id: 'p-tank', role: 'Tank',    names: ['Mappsy'] },
    { id: 'p-sup1', role: 'Support', names: ['Same'] },
    { id: 'p-sup2', role: 'Support', names: ['Same'] },
    { id: 'p-dps1', role: 'Damage',  names: ['Szatan'] },
    { id: 'p-dps2', role: 'Damage',  names: ['Arclite'] },
  ];
  const roles = ['Support', 'Tank', 'Support', 'Damage', 'Damage'];
  const r = Assign.assign(['Same', 'MAPPSY', 'Same', 'Szatan', 'Arclite'], lineup, roles);
  assert.equal(r.ids[0], null);
  assert.equal(r.ids[2], null);
});

test('an empty lineup resolves nothing rather than throwing', () => {
  const r = Assign.assign(['a', 'b', 'c', 'd', 'e'], [], SLOT_ROLES);
  assert.deepEqual(r.ids, [null, null, null, null, null]);
});

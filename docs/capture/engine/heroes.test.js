const test = require('node:test');
const assert = require('node:assert');
const H = require('./heroes.js');

test('every hero belongs to exactly one of the three roles', () => {
  const seen = {};
  for (const role of ['tank', 'damage', 'support']) {
    assert.ok(Array.isArray(H.ROLE_MAP[role]), role + ' is missing');
    for (const h of H.ROLE_MAP[role]) {
      assert.ok(!seen[h], h + ' is listed under two roles');
      seen[h] = role;
    }
  }
});

test('inferRole answers with the display-cased role', () => {
  assert.strictEqual(H.inferRole('Reinhardt'), 'Tank');
  assert.strictEqual(H.inferRole('Genji'), 'Damage');
  assert.strictEqual(H.inferRole('Ana'), 'Support');
});

test('inferRole is case-insensitive, because refs and feeds disagree on case', () => {
  assert.strictEqual(H.inferRole('reinhardt'), 'Tank');
  assert.strictEqual(H.inferRole('GENJI'), 'Damage');
});

test('inferRole says nothing rather than guessing', () => {
  assert.strictEqual(H.inferRole('Not A Hero'), null);
  assert.strictEqual(H.inferRole(''), null);
  assert.strictEqual(H.inferRole(null), null);
});

// The panel groups heroes the way the in-game hero select does: three role
// blocks, alphabetical within each. Alphabetical order is the whole reason a
// grid beats the dropdown it replaces - a hero has one findable place.
test('byRole returns the three roles in play order, each sorted by name', () => {
  const groups = H.byRole([
    { g: '1', n: 'Zenyatta' }, { g: '2', n: 'Ana' }, { g: '3', n: 'Genji' },
    { g: '4', n: 'Reinhardt' }, { g: '5', n: 'Ashe' }, { g: '6', n: 'D.Mon' },
  ]);
  assert.deepStrictEqual(groups.map(x => x.role), ['Tank', 'Damage', 'Support']);
  assert.deepStrictEqual(groups[0].heroes.map(h => h.n), ['D.Mon', 'Reinhardt']);
  assert.deepStrictEqual(groups[1].heroes.map(h => h.n), ['Ashe', 'Genji']);
  assert.deepStrictEqual(groups[2].heroes.map(h => h.n), ['Ana', 'Zenyatta']);
});

test('a hero with no known role is still offered, under its own group', () => {
  // A custom hero the operator taught the capture page, or one added to the
  // game before this table caught up. Dropping it would make it unbannable.
  const groups = H.byRole([{ g: '1', n: 'Ana' }, { g: '2', n: 'Mystery' }]);
  const other = groups.find(x => x.role === 'Other');
  assert.ok(other, 'an unknown hero must not vanish from the picker');
  assert.deepStrictEqual(other.heroes.map(h => h.n), ['Mystery']);
});

test('byRole omits a role nobody in the catalogue plays', () => {
  const groups = H.byRole([{ g: '1', n: 'Ana' }]);
  assert.deepStrictEqual(groups.map(x => x.role), ['Support']);
});

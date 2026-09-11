const test = require('node:test');
const assert = require('node:assert');
const fs = require('fs');
const os = require('os');
const path = require('path');
const CS = require('./codestack.js');

function tmpFile() {
  return path.join(os.tmpdir(), 'owdb-codestack-test-' + process.pid + '-' + Math.random().toString(36).slice(2) + '.json');
}

test('save then load round-trips, uppercased', () => {
  const f = tmpFile();
  try {
    CS.save(f, ['abc123', 'DEF456']);
    assert.deepStrictEqual(CS.load(f), ['ABC123', 'DEF456']);
  } finally { fs.unlinkSync(f); }
});

test('load of a missing file is an empty stack, not a throw', () => {
  assert.deepStrictEqual(CS.load(path.join(os.tmpdir(), 'owdb-does-not-exist-' + Date.now() + '.json')), []);
});

test('save rejects a bad code', () => {
  const f = tmpFile();
  assert.throws(() => CS.save(f, ['has spaces']), /bad code/);
});

test('rotate pulls the top and pushes it to the bottom', () => {
  const f = tmpFile();
  try {
    CS.save(f, ['AAA111', 'BBB222', 'CCC333']);
    assert.strictEqual(CS.rotate(f), 'AAA111');
    assert.deepStrictEqual(CS.load(f), ['BBB222', 'CCC333', 'AAA111']);
    assert.strictEqual(CS.rotate(f), 'BBB222');
    assert.deepStrictEqual(CS.load(f), ['CCC333', 'AAA111', 'BBB222']);
  } finally { fs.unlinkSync(f); }
});

test('rotate on an empty stack returns null and does not throw', () => {
  const f = tmpFile();
  try {
    CS.save(f, []);
    assert.strictEqual(CS.rotate(f), null);
  } finally { fs.unlinkSync(f); }
});

test('a stack of N codes returns to its start every N rotations', () => {
  const f = tmpFile();
  try {
    const start = ['A1', 'B2', 'C3', 'D4', 'E5'];
    CS.save(f, start);
    const seen = [];
    for (let i = 0; i < start.length; i++) seen.push(CS.rotate(f));
    assert.deepStrictEqual(seen, start, 'one full cycle visits every code once, in order');
    assert.deepStrictEqual(CS.load(f), start, 'and lands back where it started');
  } finally { fs.unlinkSync(f); }
});

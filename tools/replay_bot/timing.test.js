const test = require('node:test');
const assert = require('node:assert');
const fs = require('fs');
const os = require('os');
const path = require('path');

// timing.js reads/writes tools/replay_bot/state/console_timing.json. These
// tests must not touch a real operator's file, so each one moves it aside.
const T = require('./timing.js');
const REAL = T.OVERRIDE;

function withNoOverride(fn) {
  const bak = REAL + '.testbak-' + process.pid;
  const had = fs.existsSync(REAL);
  if (had) fs.renameSync(REAL, bak);
  try { T.reload(); return fn(); }
  finally {
    try { fs.unlinkSync(REAL); } catch (e) { /* ignore */ }
    if (had) fs.renameSync(bak, REAL);
    T.reload();
  }
}

test('the defaults are the measured values', () => {
  withNoOverride(() => {
    assert.strictEqual(T.seek.gapMs, 700);
    assert.strictEqual(T.sample.quiesceMs, 500);
    assert.strictEqual(T.quiesce.ms, 400);
    assert.strictEqual(T.drag.hopPx, 24);
    assert.strictEqual(T.chunk.speed, 2);
    assert.strictEqual(T.esc.tries, 3);
  });
});

test('every namespace is an object of numbers', () => {
  for (const ns of T.NS) {
    assert.strictEqual(typeof T.DEFAULTS[ns], 'object');
    for (const k of Object.keys(T.DEFAULTS[ns])) {
      assert.strictEqual(typeof T.DEFAULTS[ns][k], 'number', ns + '.' + k);
    }
  }
});

test('applyOver takes known numeric keys and ignores the rest', () => {
  const fresh = JSON.parse(JSON.stringify(T.DEFAULTS));
  T.applyOver(fresh, {
    drag: { prePress: 12, bogusKey: 99 },
    bogusNs: { x: 1 },
    seek: { gapMs: 'soon' },
  });
  assert.strictEqual(fresh.drag.prePress, 12);
  assert.strictEqual(fresh.drag.bogusKey, undefined);
  assert.strictEqual(fresh.seek.gapMs, T.DEFAULTS.seek.gapMs, 'non-number ignored');
  assert.strictEqual(fresh.bogusNs, undefined);
});

test('save merges, clamps, and reload picks it up', () => {
  withNoOverride(() => {
    T.save({ drag: { prePress: 7, hopPx: -5 }, esc: { tries: 0 } });
    assert.strictEqual(T.drag.prePress, 7);
    assert.strictEqual(T.drag.hopPx, 1, 'hopPx floors at 1');
    assert.strictEqual(T.esc.tries, 1, 'a count floors at 1');
    assert.strictEqual(T.seek.gapMs, T.DEFAULTS.seek.gapMs, 'untouched knob stays default');

    // a second save merges rather than replacing
    T.save({ seek: { gapMs: 650 } });
    assert.strictEqual(T.drag.prePress, 7, 'earlier save survives');
    assert.strictEqual(T.seek.gapMs, 650);

    T.clearSaved();
    assert.strictEqual(T.drag.prePress, T.DEFAULTS.drag.prePress);
  });
});

test('save rejects a non-numeric value', () => {
  withNoOverride(() => {
    assert.throws(() => T.save({ drag: { prePress: 'fast' } }), /bad value for drag\.prePress/);
  });
});

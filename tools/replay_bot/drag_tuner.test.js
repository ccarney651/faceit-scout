const test = require('node:test');
const assert = require('node:assert');
const Tuner = require('./drag_tuner.js');

test('cleanTiming coerces every knob to a clamped integer', () => {
  const t = Tuner.cleanTiming({ prePress: '40', postPress: 30.6, perPoint: 16,
    dwell: 120, hopPx: 24, settle: 500 });
  assert.deepStrictEqual(t, { prePress: 40, postPress: 31, perPoint: 16,
    dwell: 120, hopPx: 24, settle: 500 });
});

test('cleanTiming floors the waits at zero and hopPx at one', () => {
  const t = Tuner.cleanTiming({ prePress: -5, postPress: -1, perPoint: 0,
    dwell: 0, hopPx: 0, settle: -100 });
  assert.strictEqual(t.prePress, 0);
  assert.strictEqual(t.perPoint, 0);
  assert.strictEqual(t.hopPx, 1, 'plan() divides a distance by hopPx');
  assert.strictEqual(t.settle, 0);
});

test('cleanTiming rejects a missing or non-numeric knob', () => {
  assert.throws(() => Tuner.cleanTiming({ prePress: 40 }), /postPress/);
  assert.throws(() => Tuner.cleanTiming(Object.assign(
    { prePress: 1, postPress: 1, perPoint: 1, dwell: 1, hopPx: 1 },
    { settle: 'soon' })), /settle/);
});

test('safeTarget accepts a sane number of seconds and rejects the rest', () => {
  assert.strictEqual(Tuner.safeTarget('120'), 120);
  assert.strictEqual(Tuner.safeTarget(0), 0);
  assert.throws(() => Tuner.safeTarget(-1), /out of range/);
  assert.throws(() => Tuner.safeTarget(99999), /out of range/);
  assert.throws(() => Tuner.safeTarget('soon'), /out of range/);
});

test('crossOrigin passes a loopback request and blocks the rest', () => {
  assert.strictEqual(Tuner.crossOrigin({ headers: { host: '127.0.0.1:8788' } }), false);
  assert.strictEqual(Tuner.crossOrigin({ headers: { host: 'localhost:8788' } }), false);
  assert.strictEqual(Tuner.crossOrigin({ headers: { host: 'evil.example' } }), true);
  assert.strictEqual(Tuner.crossOrigin({
    headers: { host: 'localhost:8788', origin: 'http://evil.example' } }), true);
  assert.strictEqual(Tuner.crossOrigin({
    headers: { host: 'localhost:8788', origin: 'http://localhost:8788' } }), false);
});

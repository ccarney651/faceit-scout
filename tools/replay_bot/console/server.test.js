const test = require('node:test');
const assert = require('node:assert');
const fs = require('fs');
const path = require('path');
const Srv = require('./server.js');
const TIMING = require('../timing.js');

test('crossOrigin allows loopback and blocks the rest', () => {
  assert.strictEqual(Srv.crossOrigin({ headers: { host: 'localhost:8789' } }), false);
  assert.strictEqual(Srv.crossOrigin({ headers: { host: '127.0.0.1:8789' } }), false);
  assert.strictEqual(Srv.crossOrigin({ headers: { host: 'attacker.example' } }), true);
  assert.strictEqual(Srv.crossOrigin({
    headers: { host: 'localhost', origin: 'https://evil.test' } }), true);
});

test('safeCode normalises and rejects junk', () => {
  assert.strictEqual(Srv.safeCode('j8k2qp'), 'J8K2QP');
  assert.throws(() => Srv.safeCode('has spaces'), /bad code/);
  assert.throws(() => Srv.safeCode(''), /bad code/);
});

test('safeSeconds rejects out-of-range', () => {
  assert.strictEqual(Srv.safeSeconds('300'), 300);
  assert.throws(() => Srv.safeSeconds(-1), /out of range/);
  assert.throws(() => Srv.safeSeconds(99999), /out of range/);
});

test('the code stack round-trips and rotate moves the top to the bottom', () => {
  const bak = Srv.CODES_FILE + '.testbak-' + process.pid;
  const had = fs.existsSync(Srv.CODES_FILE);
  if (had) fs.renameSync(Srv.CODES_FILE, bak);
  try {
    Srv.saveCodes(['AAA111', 'BBB222', 'CCC333']);
    assert.deepStrictEqual(Srv.loadCodes(), ['AAA111', 'BBB222', 'CCC333']);
    // one rotation, as the import phase does it
    const c = Srv.loadCodes();
    Srv.saveCodes(c.slice(1).concat([c[0]]));
    assert.deepStrictEqual(Srv.loadCodes(), ['BBB222', 'CCC333', 'AAA111']);
  } finally {
    try { fs.unlinkSync(Srv.CODES_FILE); } catch (e) { /* ignore */ }
    if (had) fs.renameSync(bak, Srv.CODES_FILE);
  }
});

test('withTiming applies an override for the call and restores it after', async () => {
  const before = TIMING.drag.prePress;
  let during = null;
  const ret = await Srv.withTiming({ drag: { prePress: before + 33 } }, async () => {
    during = TIMING.drag.prePress;
    return 'result';
  });
  assert.strictEqual(during, before + 33, 'the override is live inside the call');
  assert.strictEqual(TIMING.drag.prePress, before, 'and gone after');
  assert.strictEqual(ret, 'result');
});

test('withTiming with nothing to override is a passthrough', async () => {
  assert.strictEqual(await Srv.withTiming(null, async () => 7), 7);
  assert.strictEqual(await Srv.withTiming({}, async () => 8), 8);
});

test('every phase is an async function', () => {
  for (const [name, fn] of Object.entries(Srv.PHASES)) {
    assert.strictEqual(typeof fn, 'function', name);
  }
});

test('import refuses without confirm', async () => {
  await assert.rejects(Srv.PHASES.import({ st: { lines: [] } }, {}), /confirm/);
});

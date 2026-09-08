const test = require('node:test');
const assert = require('node:assert');
const path = require('path');
const G = require('./grab.js');

test('a successful capture line yields the path and its true size', () => {
  const got = G.parse('OK 2560 1440 C:\\tmp\\f.png\n');
  assert.strictEqual(got.ok, true);
  assert.strictEqual(got.w, 2560);
  assert.strictEqual(got.h, 1440);
  assert.strictEqual(got.path, 'C:\\tmp\\f.png');
});

test('a path containing spaces survives parsing', () => {
  const got = G.parse('OK 2560 1440 C:\\Users\\me\\My Frames\\f.png');
  assert.strictEqual(got.path, 'C:\\Users\\me\\My Frames\\f.png');
});

test('an error line is reported, not silently treated as a frame', () => {
  const got = G.parse('ERR no running Overwatch process with a main window');
  assert.strictEqual(got.ok, false);
  assert.match(got.reason, /no running Overwatch/);
});

// PowerShell writes warnings and progress noise to stdout readily. The contract
// line is the one that starts with OK, wherever it lands.
test('the result line is found among surrounding noise', () => {
  const got = G.parse('some warning\nOK 2560 1440 C:\\tmp\\f.png\ntrailing\n');
  assert.strictEqual(got.ok, true);
  assert.strictEqual(got.w, 2560);
});

test('output with no contract line at all is a failure, not a crash', () => {
  const got = G.parse('');
  assert.strictEqual(got.ok, false);
  assert.ok(got.reason.length > 0);
});

// Integration. Only meaningful with Overwatch actually running, so it skips
// rather than fails when it is not - a red suite on a machine without the game
// would train everyone to ignore it.
test('captures the live window at the size calibration expects', async (t) => {
  const out = path.join(__dirname, 'frames', 'grab-test.png');
  let got;
  try {
    got = await G.capture(out);
  } catch (e) {
    return t.skip('Overwatch not running: ' + e.message);
  }
  if (!got.ok) return t.skip('Overwatch not capturable: ' + got.reason);

  const calib = require('./calib.js');
  assert.strictEqual(calib.check({ w: got.w, h: got.h }).ok, true,
    `captured ${got.w}x${got.h}, frozen geometry expects ` +
    `${calib.FROZEN.frame.w}x${calib.FROZEN.frame.h}`);
});

// tools/replay_bot/input.js
// The Node side of sending keys, and waiting for the screen to stop moving.
// See specs/2026-09-08-replay-bot-design.md §4.
//
// Two jobs that belong together because they bracket every seek: put the keys
// in, then wait until the result has settled enough to be worth reading.
//
// SETTLING IS MEASURED, NOT TIMED. After a seek the HUD shifts into place for
// under a second, and a frame grabbed during that window shows a half-arranged
// interface - portraits missing, sliding, or mid-fade. A fixed delay long
// enough on a good day is not long enough on a bad one, and is wasted time on
// every good one. So the bot grabs twice and compares: when consecutive frames
// agree, the UI has stopped moving, whatever that took.
//
// A screen that never settles is a real failure - a menu left open, a killcam,
// an animation that does not end - so settling gives up after maxTries and says
// so rather than blocking the run forever.

(function (global) {
  'use strict';

  var path = require('path');
  var fs = require('fs');
  var os = require('os');
  var execFile = require('child_process').execFile;
  var seqNo = 0;

  var SCRIPT = path.join(__dirname, 'send_keys.ps1');

  // MEASURED ON THE RIG, 2026-09-09. The replay viewer ignores a seek key that
  // arrives while it is still seeking, and the loss is silent - the keys are
  // delivered, the client simply does not act on them. Five presses of REPLAY
  // FORWARD landed:
  //
  //     45ms gap -> 1 of 5      300ms -> 3 of 5
  //    150ms gap -> 1 of 5      600ms -> 5 of 5      1000ms -> 5 of 5
  //
  // 45ms was the old default, which is why the first live run advanced exactly
  // one 20-second step per batch however many keys it sent, and sampled six
  // points inside the first two minutes of a seventeen-minute map while
  // reporting that it had covered all of it.
  //
  // THERE IS NO CLIFF. Bisecting for one, twice, gave two different answers:
  // 550ms dropped a press in one run and landed all five in the next, and 375ms
  // landed 2 of 5 then 4 of 5. Acceptance is probabilistic - presumably a race
  // against however long that particular seek takes - so a threshold found by
  // one clean bisection is a threshold found by luck.
  //
  // 700ms sits above every failure yet observed (the highest was 550ms). It
  // costs a few seconds of seeking per map, and the driver verifies the result
  // regardless, because a gap that is usually enough is not a thing to trust
  // hundreds of unrepeatable maps to.
  var SEEK_GAP_MS = 700;

  function parse(stdout) {
    var lines = String(stdout).split(/\r?\n/);
    for (var i = 0; i < lines.length; i++) {
      var line = lines[i].trim();
      var m = /^SENT (\d+) keys$/.exec(line);
      if (m) return { ok: true, n: Number(m[1]), reason: null };
      if (/^ERR /.test(line)) return { ok: false, n: 0, reason: line.slice(4) };
    }
    return {
      ok: false,
      n: 0,
      reason: 'no SENT or ERR line: ' + JSON.stringify(String(stdout).slice(0, 200)),
    };
  }

  // Send a whole key sequence in one process. The script foregrounds Overwatch
  // itself and refuses if it cannot, because keys sent to an unfocused window
  // are silently discarded and would leave the bot believing it had seeked.
  async function sendKeys(keys, opts) {
    var gapMs = (opts && opts.gapMs) || SEEK_GAP_MS;
    var keyFile = path.join(os.tmpdir(), 'owdb-keys-' + process.pid + '-' + (seqNo++) + '.txt');
    fs.writeFileSync(keyFile, keys.join(String.fromCharCode(10)), 'utf8');

    var H = require('./host.js');
    try {
      var line = await H.keys(keyFile, gapMs, keys.length);
      if (line) {
        try { fs.unlinkSync(keyFile); } catch (e) { /* already gone */ }
        var got = parse(line);
        if (!got.ok) throw new Error('send refused: ' + got.reason);
        return got;
      }
    } catch (e) {
      if (/send refused/.test(e.message)) {
        try { fs.unlinkSync(keyFile); } catch (e2) { /* already gone */ }
        throw e;
      }
      // anything else is the host failing, not the keys: use the script
    }
    return await sendKeysBySpawn(keys, opts);
  }

  function sendKeysBySpawn(keys, opts) {
    // Via a file, one key per line. Inline arguments were tried three ways and
    // all of them broke on Node/PowerShell separator disagreement; a path has
    // nothing in it to re-split.
    var keyFile = path.join(os.tmpdir(), 'owdb-keys-' + process.pid + '-' + (seqNo++) + '.txt');
    fs.writeFileSync(keyFile, keys.join(String.fromCharCode(10)), 'utf8');

    var args = ['-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass',
      '-File', SCRIPT, '-KeyFile', keyFile];
    args.push('-GapMs', String((opts && opts.gapMs) || SEEK_GAP_MS));

    return new Promise(function (resolve, reject) {
      execFile('powershell', args, { windowsHide: true }, function (err, stdout, stderr) {
        try { fs.unlinkSync(keyFile); } catch (e) {}
        if (err && !stdout) {
          reject(new Error('send failed to run: ' + (stderr || err.message)));
          return;
        }
        var got = parse(stdout);
        if (!got.ok) {
          reject(new Error('send refused: ' + got.reason));
          return;
        }
        resolve(got);
      });
    });
  }

  // Build a settle() for driver.js. `grab` returns something `diff` can compare;
  // in production those are a PNG path and a pixel difference.
  function makeSettle(opts) {
    var grab = opts.grab;
    var diff = opts.diff;
    var threshold = opts.threshold;
    var maxTries = opts.maxTries || 8;
    var waitMs = opts.waitMs === undefined ? 120 : opts.waitMs;

    return async function settle() {
      var prev = await grab();
      for (var i = 1; i <= maxTries; i++) {
        if (waitMs) await new Promise(function (r) { setTimeout(r, waitMs); });
        var cur = await grab();
        var motion = await diff(prev, cur);
        if (motion <= threshold) {
          return { settled: true, tries: i, motion: motion, frame: cur };
        }
        prev = cur;
      }
      return { settled: false, tries: maxTries, motion: null, frame: prev };
    };
  }

  var Mod = {
    SCRIPT: SCRIPT,
    SEEK_GAP_MS: SEEK_GAP_MS,
    sendKeysBySpawn: sendKeysBySpawn,
    parse: parse,
    sendKeys: sendKeys,
    makeSettle: makeSettle,
  };

  if (typeof module !== 'undefined' && module.exports) module.exports = Mod;
  else global.OWDBReplayInput = Mod;
})(typeof self !== 'undefined' ? self : this);

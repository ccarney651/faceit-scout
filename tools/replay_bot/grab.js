// tools/replay_bot/grab.js
// Producing a frame from the live Overwatch window.
// See specs/2026-09-08-replay-bot-design.md §5.
//
// One of only two modules that touch the outside world, and the smaller one.
// The capture itself lives in grab_window.ps1 because the working method is a
// Win32 call (PrintWindow with PW_RENDERFULLCONTENT) with no usable Node
// binding; this side finds the script, runs it, and refuses to invent a frame
// when it fails.
//
// The output contract is deliberately one line - `OK <w> <h> <path>` - because
// PowerShell writes warnings and progress noise to stdout freely, and a parser
// that scanned for anything looser would eventually read a warning as a frame.
//
// The size in that line is not decoration. DPI virtualisation silently reports
// a 125%-scaled 2560x1440 display as 2048x1152, so the caller checks the
// captured size against the frozen geometry before trusting a single crop.

(function (global) {
  'use strict';

  var path = require('path');
  var execFile = require('child_process').execFile;

  var SCRIPT = path.join(__dirname, 'grab_window.ps1');

  // Read the one contract line out of whatever PowerShell produced.
  function parse(stdout) {
    var lines = String(stdout).split(/\r?\n/);

    for (var i = 0; i < lines.length; i++) {
      var line = lines[i].trim();

      // `OK <w> <h> <path>` - the path may contain spaces, so it is everything
      // after the third field rather than a fourth field.
      var m = /^OK (\d+) (\d+) (.+)$/.exec(line);
      if (m) {
        return { ok: true, w: Number(m[1]), h: Number(m[2]), path: m[3], reason: null };
      }

      if (/^ERR /.test(line)) {
        return { ok: false, reason: line.slice(4), w: 0, h: 0, path: null };
      }
    }

    return {
      ok: false,
      w: 0,
      h: 0,
      path: null,
      reason: 'no OK or ERR line in capture output: ' + JSON.stringify(String(stdout).slice(0, 200)),
    };
  }

  // Capture the window to `outPath`. Resolves with the same shape parse()
  // returns; a failed capture resolves ok:false rather than throwing, so a
  // sweep can record the miss and carry on to the next sample.
  function capture(outPath) {
    return new Promise(function (resolve, reject) {
      execFile('powershell', [
        '-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass',
        '-File', SCRIPT, '-Out', outPath,
      ], { windowsHide: true }, function (err, stdout, stderr) {
        if (err && !stdout) {
          reject(new Error('capture failed to run: ' + (stderr || err.message)));
          return;
        }
        resolve(parse(stdout));
      });
    });
  }

  var Mod = {
    SCRIPT: SCRIPT,
    parse: parse,
    capture: capture,
  };

  if (typeof module !== 'undefined' && module.exports) module.exports = Mod;
  else global.OWDBReplayGrab = Mod;
})(typeof self !== 'undefined' ? self : this);

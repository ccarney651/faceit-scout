// tools/replay_bot/host.js
// One PowerShell process, kept alive, doing the grabs and the key sends.
//
// MEASURED, WHICH IS THE WHOLE REASON THIS EXISTS: a bare PowerShell spawn is
// 211ms on this rig, one that runs Add-Type is 341ms, and a complete window
// grab is 497ms. Two thirds of every capture was process startup, paid about
// twenty times a map - roughly seven seconds per map spent starting PowerShell
// and nothing else.
//
// The commands are line in, line out, over stdin and stdout (see host.ps1), and
// the contract lines are the same ones the standalone scripts print, so the
// parsers do not change and neither does what a caller sees.
//
// IT FALLS BACK. If the host will not start, or dies mid-run, `available()`
// goes false and grab.js and input.js spawn the standalone script per call
// exactly as they used to - slower, and still correct. A performance
// optimisation that can take the night down with it is not worth having.
//
// ONE REQUEST AT A TIME. There is a single process with a single stdout, so the
// requests are serialised; concurrency here would be a parsing problem, not a
// speed-up, because the work behind each command is serial anyway.

(function (global) {
  'use strict';

  var path = require('path');
  var spawn = require('child_process').spawn;

  var SCRIPT = path.join(__dirname, 'host.ps1');
  var START_TIMEOUT_MS = 15000;
  var DEFAULT_TIMEOUT_MS = 20000;

  var child = null;
  var ready = false;
  var disabled = process.env.OWDB_NO_HOST === '1';
  var queue = [];
  var current = null;
  var buffer = '';
  var starting = null;

  function log() { /* deliberately quiet: the callers do the reporting */ }

  function kill() {
    if (!child) return;
    try { child.stdin.end(); } catch (e) { /* already gone */ }
    try { child.kill(); } catch (e) { /* already gone */ }
    child = null;
    ready = false;
  }

  // Everything waiting is failed rather than left hanging: a caller that never
  // hears back stalls the run forever, which is worse than a loud failure.
  function failAll(reason) {
    var err = new Error('powershell host: ' + reason);
    if (current) { current.reject(err); current = null; }
    queue.splice(0).forEach(function (job) { job.reject(err); });
  }

  function onLine(line) {
    if (!current) return;                 // stray output between requests
    if (!current.re.test(line) && !/^ERR /.test(line)) return;
    var job = current;
    current = null;
    clearTimeout(job.timer);
    job.resolve(line);
    pump();
  }

  function pump() {
    if (current || !queue.length || !ready) return;
    current = queue.shift();
    current.timer = setTimeout(function () {
      var job = current;
      current = null;
      // A host that stopped answering is a host that gets replaced. Killing it
      // now means the next request starts a fresh one rather than queueing
      // behind something that will never reply.
      kill();
      job.reject(new Error('powershell host: timed out after ' + job.timeoutMs + 'ms'));
      failAll('the host stopped responding');
    }, current.timeoutMs);
    child.stdin.write(current.line + String.fromCharCode(10));
  }

  function start() {
    if (starting) return starting;
    starting = new Promise(function (resolve) {
      var proc;
      try {
        proc = spawn('powershell', ['-NoProfile', '-NonInteractive', '-ExecutionPolicy',
          'Bypass', '-File', SCRIPT], { windowsHide: true });
      } catch (e) {
        disabled = true;
        resolve(false);
        return;
      }

      var settled = false;
      var giveUp = setTimeout(function () {
        if (settled) return;
        settled = true;
        disabled = true;
        kill();
        resolve(false);
      }, START_TIMEOUT_MS);

      proc.stdout.setEncoding('utf8');
      proc.stdout.on('data', function (chunk) {
        buffer += chunk;
        var lines = buffer.split(String.fromCharCode(10));
        buffer = lines.pop();
        lines.forEach(function (raw) {
          var line = raw.trim();
          if (!line) return;
          if (!ready) {
            if (line === 'READY') {
              ready = true;
              if (!settled) { settled = true; clearTimeout(giveUp); resolve(true); }
              pump();
            }
            return;
          }
          onLine(line);
        });
      });

      proc.on('exit', function () {
        ready = false;
        child = null;
        if (!settled) { settled = true; clearTimeout(giveUp); disabled = true; resolve(false); }
        failAll('the host exited');
      });
      proc.on('error', function () {
        if (!settled) { settled = true; clearTimeout(giveUp); disabled = true; resolve(false); }
      });

      // NOTHING HERE KEEPS NODE ALIVE. A caller that forgets close() would
      // otherwise hang forever on an open pipe, waiting for a host that is
      // waiting for it - which is exactly what happened to the test suite, 72
      // seconds of a process with no work left to do.
      //
      // Safe because an in-flight request always has its timeout timer pending,
      // and a pending timer does hold the loop open: the process can only exit
      // while the host is idle.
      try {
        proc.unref();
        proc.stdin.unref();
        proc.stdout.unref();
        if (proc.stderr) proc.stderr.unref();
      } catch (e) { /* older Node without unref on a pipe */ }

      child = proc;
    });
    return starting;
  }

  // Whether the host is usable. Starts it on first call; false means callers
  // should use the standalone scripts.
  async function available() {
    if (disabled) return false;
    if (ready) return true;
    starting = null;                      // a dead host is restarted, once
    return await start();
  }

  function request(line, re, timeoutMs) {
    return new Promise(function (resolve, reject) {
      queue.push({
        line: line,
        re: re,
        timeoutMs: timeoutMs || DEFAULT_TIMEOUT_MS,
        resolve: resolve,
        reject: reject,
        timer: null,
      });
      pump();
    });
  }

  async function grab(outPath) {
    if (!await available()) return null;
    return await request('GRAB ' + outPath, /^OK \d+ \d+ /, DEFAULT_TIMEOUT_MS);
  }

  // The timeout has to cover the keys themselves: a fifty-press seek at 700ms
  // apart is thirty-five seconds of deliberate waiting, and timing that out
  // would kill a host that is working perfectly.
  async function keys(keyFile, gapMs, count) {
    if (!await available()) return null;
    var budget = 5000 + (count || 1) * ((gapMs || 700) + 200);
    return await request('KEYS ' + keyFile + ' ' + gapMs, /^SENT \d+ keys$/, budget);
  }

  async function rect() {
    if (!await available()) return null;
    return await request('RECT', /^OK -?\d+ -?\d+ \d+ \d+$/, DEFAULT_TIMEOUT_MS);
  }

  function close() {
    failAll('closing');
    if (child) {
      try { child.stdin.write('QUIT' + String.fromCharCode(10)); } catch (e) { /* gone */ }
    }
    kill();
    starting = null;
  }

  // A host left running would keep Node alive after the work is done.
  process.on('exit', kill);

  var Mod = {
    SCRIPT: SCRIPT,
    available: available,
    grab: grab,
    keys: keys,
    rect: rect,
    close: close,
    isReady: function () { return ready; },
  };

  if (typeof module !== 'undefined' && module.exports) module.exports = Mod;
  else global.OWDBReplayHost = Mod;
  void log;
})(typeof self !== 'undefined' ? self : this);

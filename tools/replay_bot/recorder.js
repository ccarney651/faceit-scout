// tools/replay_bot/recorder.js
// Recording the mouse and keyboard once, and replaying it per code.
// See specs/2026-09-08-replay-bot-design.md §4 and ARCHITECTURE.md §14.
//
// Seeking inside a replay is arithmetic (driver.js), but GETTING INTO one is
// mouse work - the career menu, the replay list, the import dialog. Those have
// no keyboard route, so something has to click them.
//
// THE COORDINATES ARE RECORDED, NOT REASONED. The obvious alternative was to
// read the buttons' positions off a screenshot and hardcode them, and it is a
// trap: screenshots of this rig arrive at 2557x1437 while the window's client
// area is 2560x1440, so every coordinate taken from one is a guess that is
// wrong by a few pixels in an unknown direction. Recording puts the operator's
// own successful clicks on file - they landed once, in the real window, at
// coordinates the machine measured rather than inferred.
//
// What is recorded is a CHUNK: one short named step, like open-import. Small
// chunks compose, can be re-recorded one at a time when Blizzard moves a menu,
// and keep the part that must vary - the code - explicit.
//
// Coordinates are stored RELATIVE TO THE CLIENT AREA, so a moved window is
// harmless; only a resized one invalidates a chunk, and that is refused rather
// than scaled. A scaled click lands plausibly close and on nothing.
//
// SEEKING IS NEVER RECORDED. B plus n presses of X is exact and cannot drift,
// while a recorded scrub would be a pixel drag meaning something different in
// every replay. Recording is for the menus, and stops at the replay.

(function (global) {
  'use strict';

  var path = require('path');
  var fs = require('fs');
  var os = require('os');
  var execFile = require('child_process').execFile;

  var DIR = path.join(__dirname, 'chunks');
  var RECORD = path.join(__dirname, 'record_input.ps1');
  var PLAY = path.join(__dirname, 'play_input.ps1');
  var RECT = path.join(__dirname, 'window_rect.ps1');

  var CODE = '$CODE';

  // A long recorded pause is the operator thinking, not the UI working. This
  // caps those without flattening the short waits real transitions need.
  var MAX_WAIT_MS = 3000;
  var DEFAULT_HOLD_MS = 60;

  // A press that strays further than this is a drag, not a click. A hand never
  // holds a mouse perfectly still, so zero would make every click a drag.
  var DRAG_MIN_PX = 6;
  var DRAG_PATH_POINTS = 8;

  // One notch of a wheel, per Windows. Notches within WHEEL_GAP_MS of each
  // other are one gesture.
  var WHEEL_NOTCH = 120;
  var WHEEL_GAP_MS = 400;

  // ---------------------------------------------------------------- pure ----

  // Raw poll events to a chunk's event list.
  //
  // record_input.ps1 reports button and key transitions in screen coordinates;
  // this pairs them into whole actions, converts to client-relative
  // coordinates, and keeps the gaps between them.
  //
  // A click is placed where the button went DOWN, not where it came up. The
  // press is what the UI acts on, and drifting a pixel before release is
  // normal.
  // record_input.ps1 sends the modifiers held at press time as a joined string,
  // because PowerShell 5.1 serialises a one-element array as a bare string and
  // the shape would otherwise depend on how many were held.
  function modsOf(e) {
    return String(e.mods || '').split(',').filter(function (m) { return m; });
  }

  function normalise(raw, rect) {
    var out = [];
    var downs = {};
    var active = null;
    var wheel = null;
    var lastT = raw.length ? raw[0].t : 0;

    function push(ev, startT, endT) {
      ev.waitMs = Math.max(0, Math.min(MAX_WAIT_MS, Math.round(startT - lastT)));
      ev.holdMs = Math.max(1, Math.round(endT - startT));
      out.push(ev);
      lastT = endT;
    }

    // Wheel notches arrive one message at a time; a person turning a wheel
    // produces a burst of them. They are collected into one scroll so playback
    // can reproduce the gesture rather than a hundred separate flicks.
    function flushWheel() {
      if (!wheel) return;
      push({
        type: 'scroll',
        x: wheel.x - rect.ox,
        y: wheel.y - rect.oy,
        notches: Math.round(wheel.delta / WHEEL_NOTCH),
      }, wheel.from, wheel.to);
      wheel = null;
    }

    raw.forEach(function (e) {
      if (e.type !== 'wheel') flushWheel();

      if (e.type === 'down') {
        downs[e.button] = { ev: e, moves: [] };
        active = e.button;
        return;
      }

      if (e.type === 'move') {
        if (active && downs[active]) downs[active].moves.push(e);
        return;
      }

      if (e.type === 'wheel') {
        var sameRun = wheel &&
          Math.sign(wheel.delta) === Math.sign(e.delta) &&
          e.t - wheel.to <= WHEEL_GAP_MS;
        if (sameRun) {
          wheel.delta += e.delta;
          wheel.to = e.t;
        } else {
          flushWheel();
          wheel = { x: e.x, y: e.y, delta: e.delta, from: e.t, to: e.t };
        }
        return;
      }

      if (e.type === 'keydown') {
        downs['key:' + e.key] = { ev: e, moves: [] };
        return;
      }

      if (e.type === 'up') {
        var d = downs[e.button];
        if (!d) return;                 // an up with no down, from before the recording
        delete downs[e.button];
        if (active === e.button) active = null;

        // A press that moved is a DRAG, and the difference matters: a scrollbar
        // dragged from its top to its middle, replayed as a click where the
        // press started, does nothing at all. Straying further than a few
        // pixels is the test - a hand never holds a mouse perfectly still.
        var path = d.moves.concat([e]);
        var strayed = path.some(function (m) {
          return Math.abs(m.x - d.ev.x) > DRAG_MIN_PX || Math.abs(m.y - d.ev.y) > DRAG_MIN_PX;
        });

        if (!strayed) {
          push({
            type: 'click',
            button: d.ev.button,
            x: d.ev.x - rect.ox,
            y: d.ev.y - rect.oy,
          }, d.ev.t, e.t);
          return;
        }

        push({
          type: 'drag',
          button: d.ev.button,
          x: d.ev.x - rect.ox,
          y: d.ev.y - rect.oy,
          toX: e.x - rect.ox,
          toY: e.y - rect.oy,
          path: thin(d.moves, DRAG_PATH_POINTS).map(function (m) {
            return { x: m.x - rect.ox, y: m.y - rect.oy };
          }),
        }, d.ev.t, e.t);
        return;
      }

      if (e.type === 'keyup') {
        var k = downs['key:' + e.key];
        if (!k) return;
        delete downs['key:' + e.key];
        var ev = { type: 'key', key: k.ev.key };
        if (k.ev.vk !== undefined) ev.vk = k.ev.vk;
        var mods = modsOf(k.ev);
        if (mods.length) ev.mods = mods;
        push(ev, k.ev.t, e.t);
      }
    });

    flushWheel();
    return out;
  }

  // Keep at most `n` points of a path, evenly spaced. Playback moves the
  // pointer along them; a hundred points would be a hundred sleeps, and the
  // shape of a scrollbar drag is not what makes it work.
  function thin(points, n) {
    if (points.length <= n) return points.slice();
    var out = [];
    for (var i = 0; i < n; i++) {
      out.push(points[Math.round(i * (points.length - 1) / (n - 1))]);
    }
    return out;
  }

  // Replace the keystrokes that spelled the replay code with a placeholder.
  //
  // The operator types a REAL code while recording, because the dialog will not
  // advance without one - so what gets recorded is a sequence that actually
  // worked. This then finds those keystrokes by matching them against the code
  // that was typed, and swaps them for `$CODE`.
  //
  // Only a contiguous run spelling the WHOLE code counts. Codes are six
  // characters of Crockford Base32, and single letters of one turn up all over
  // a recording; matching anything shorter would gut the chunk.
  function substituteCode(events, code) {
    // A Ctrl+V IS the code arriving in the field. Nothing else in these menus
    // is worth pasting, and the operator's own flow is copy the code, import,
    // paste - so this is the normal path, not a special case.
    //
    // It is also better than typing: the client accepted a paste when the chunk
    // was recorded, and one clipboard write replaces six keystrokes that each
    // have to land.
    for (var p = 0; p < events.length; p++) {
      var ev = events[p];
      if (ev.type !== 'key' || ev.key !== 'V') continue;
      if ((ev.mods || []).indexOf('ctrl') === -1) continue;
      var pasted = {
        type: 'paste',
        value: CODE,
        waitMs: ev.waitMs,
        holdMs: DEFAULT_HOLD_MS,
      };
      return {
        events: events.slice(0, p).concat([pasted], events.slice(p + 1)),
        found: true,
      };
    }

    var want = String(code || '').toUpperCase();
    if (!want) return { events: events.slice(), found: false };

    for (var i = 0; i <= events.length - want.length; i++) {
      var spelled = '';
      for (var j = 0; j < want.length; j++) {
        var e = events[i + j];
        if (!e || e.type !== 'key' || e.key.length !== 1) { spelled = null; break; }
        spelled += e.key;
      }
      if (spelled !== want) continue;

      var typed = {
        type: 'text',
        value: CODE,
        waitMs: events[i].waitMs,
        holdMs: DEFAULT_HOLD_MS,
      };
      return {
        events: events.slice(0, i).concat([typed], events.slice(i + want.length)),
        found: true,
      };
    }
    return { events: events.slice(), found: false };
  }

  // Whether a chunk can be replayed into the window as it is now.
  //
  // Coordinates mean nothing without the client area they were measured in, so
  // a different size is refused outright rather than scaled.
  function validate(chunk, rect, code) {
    if (!chunk.events || !chunk.events.length) {
      return { ok: false, reason: 'chunk "' + chunk.name + '" has no events' };
    }
    if (chunk.client.w !== rect.w || chunk.client.h !== rect.h) {
      return {
        ok: false,
        reason: 'chunk "' + chunk.name + '" was recorded in a ' + chunk.client.w +
          'x' + chunk.client.h + ' client area, this one is ' + rect.w + 'x' +
          rect.h + ' - re-record it',
      };
    }
    var needsCode = chunk.events.some(function (e) {
      return (e.type === 'text' || e.type === 'paste') && e.value === CODE;
    });
    if (needsCode && !code) {
      return {
        ok: false,
        reason: 'chunk "' + chunk.name + '" types a code, and none was given',
      };
    }
    return { ok: true, reason: null };
  }

  // A chunk plus the window's current position, to the plan play_input.ps1
  // runs: coordinates in screen space, and `$CODE` as this replay's code.
  function resolve(chunk, rect, code) {
    var chk = validate(chunk, rect, code);
    if (!chk.ok) throw new Error(chk.reason);

    return chunk.events.map(function (e) {
      if (e.type === 'click') {
        return {
          type: 'click',
          button: e.button,
          x: e.x + rect.ox,
          y: e.y + rect.oy,
          waitMs: e.waitMs,
          holdMs: e.holdMs,
        };
      }
      if (e.type === 'drag') {
        return {
          type: 'drag',
          button: e.button,
          x: e.x + rect.ox,
          y: e.y + rect.oy,
          toX: e.toX + rect.ox,
          toY: e.toY + rect.oy,
          path: (e.path || []).map(function (p) {
            return { x: p.x + rect.ox, y: p.y + rect.oy };
          }),
          waitMs: e.waitMs,
          holdMs: e.holdMs,
        };
      }
      if (e.type === 'scroll') {
        return {
          type: 'scroll',
          x: e.x + rect.ox,
          y: e.y + rect.oy,
          notches: e.notches,
          waitMs: e.waitMs,
          holdMs: e.holdMs,
        };
      }
      if (e.type === 'text' || e.type === 'paste') {
        return {
          type: e.type,
          value: e.value === CODE ? String(code).toUpperCase() : e.value,
          waitMs: e.waitMs,
          holdMs: e.holdMs,
        };
      }
      return {
        type: 'key',
        key: e.key,
        vk: e.vk === undefined ? null : e.vk,
        mods: e.mods || [],
        waitMs: e.waitMs,
        holdMs: e.holdMs,
      };
    });
  }

  // A finished recording to the chunk that gets stored.
  function build(name, raw, rect, code) {
    var sub = substituteCode(normalise(raw, rect), code);
    return {
      chunk: {
        name: name,
        recorded_at: new Date().toISOString(),
        client: { w: rect.w, h: rect.h },
        events: sub.events,
      },
      codeFound: sub.found,
    };
  }

  // ----------------------------------------------------------------- I/O ----

  function ps(script, args) {
    return new Promise(function (done, reject) {
      execFile('powershell', ['-NoProfile', '-NonInteractive', '-ExecutionPolicy',
        'Bypass', '-File', script].concat(args || []),
      { windowsHide: true, maxBuffer: 8 * 1024 * 1024 },
      function (err, stdout, stderr) {
        if (err && !stdout) {
          reject(new Error(path.basename(script) + ' failed to run: ' +
            (stderr || err.message)));
          return;
        }
        done(String(stdout));
      });
    });
  }

  // One contract line out of whatever PowerShell produced, the way grab.js and
  // input.js read theirs - anything looser eventually reads a warning as data.
  function contractLine(stdout, re, what) {
    var lines = String(stdout).split(/\r?\n/);
    for (var i = 0; i < lines.length; i++) {
      var line = lines[i].trim();
      var m = re.exec(line);
      if (m) return m;
      if (/^ERR /.test(line)) throw new Error(line.slice(4));
    }
    throw new Error('no ' + what + ' line: ' +
      JSON.stringify(String(stdout).slice(0, 200)));
  }

  // Where the Overwatch client area sits on screen right now.
  async function windowRect() {
    var m = contractLine(await ps(RECT, []), /^OK (-?\d+) (-?\d+) (\d+) (\d+)$/, 'OK');
    return { ox: Number(m[1]), oy: Number(m[2]), w: Number(m[3]), h: Number(m[4]) };
  }

  // Chunk names become file paths, and gui.js takes them off an HTTP request,
  // so they are checked rather than trusted. Nothing here needs a dot or a
  // slash, and refusing both is cheaper than reasoning about traversal.
  function safeName(name) {
    var s = String(name === undefined || name === null ? '' : name);
    if (!/^[A-Za-z0-9][A-Za-z0-9_-]{0,39}$/.test(s)) {
      throw new Error('bad chunk name: ' + JSON.stringify(s));
    }
    return s;
  }

  function chunkPath(name) { return path.join(DIR, safeName(name) + '.json'); }

  function load(name) {
    var p = chunkPath(name);
    if (!fs.existsSync(p)) throw new Error('no chunk "' + name + '" at ' + p);
    return JSON.parse(fs.readFileSync(p, 'utf8'));
  }

  function save(chunk) {
    if (!fs.existsSync(DIR)) fs.mkdirSync(DIR, { recursive: true });
    fs.writeFileSync(chunkPath(chunk.name), JSON.stringify(chunk, null, 2) + '\n', 'utf8');
    return chunkPath(chunk.name);
  }

  // The raw recording file to events.
  //
  // A LEADING BOM IS STRIPPED, because a PowerShell that writes one turns the
  // first line into something JSON.parse rejects with "Unexpected token" and a
  // caret pointing at a character that does not print. The writer avoids it
  // now; this makes sure a writer that forgets can never cost an evening.
  function parseRaw(text) {
    return String(text)
      .replace(/^﻿/, '')
      .split(String.fromCharCode(10))
      .map(function (l) { return l.trim().replace(/^﻿/, ''); })
      .filter(function (l) { return l; })
      .map(function (l) { return JSON.parse(l); });
  }

  // Record one chunk. The operator performs the step; F10 ends it.
  async function record(name, opts) {
    var o = opts || {};
    var rect = await windowRect();
    if (!fs.existsSync(DIR)) fs.mkdirSync(DIR, { recursive: true });
    var rawPath = path.join(DIR, '.raw-' + safeName(name) + '.jsonl');

    await ps(RECORD, ['-Out', rawPath, '-MaxSeconds', String(o.maxSeconds || 120)]);

    var raw = parseRaw(fs.readFileSync(rawPath, 'utf8'));
    fs.unlinkSync(rawPath);

    var built = build(name, raw, rect, o.code);
    return {
      path: save(built.chunk),
      chunk: built.chunk,
      codeFound: built.codeFound,
      rect: rect,
    };
  }

  // Play one chunk into the live window - or, with `dryRun`, walk it without
  // touching the mouse, the keyboard or the clipboard.
  //
  // THE DRY RUN IS NOT A NICETY. Every real attempt at open-import spends a
  // replay code that cannot be imported again, and the first attempt died on a
  // PowerShell type error before sending a single click - a failure that cost
  // nothing only by luck. The dry run does every cast, lookup and binding the
  // real path does, so a plan that walks clean will not fall over halfway
  // through a sequence with the pointer already inside a menu.
  async function play(name, opts) {
    var o = opts || {};
    var chunk = load(name);
    var rect = await windowRect();
    var plan = resolve(chunk, rect, o.code);

    var planPath = path.join(os.tmpdir(),
      'owdb-plan-' + process.pid + '-' + name + '.json');
    fs.writeFileSync(planPath, JSON.stringify(plan), 'utf8');
    var args = ['-Plan', planPath];
    if (o.dryRun) args.push('-DryRun');
    try {
      var out = await ps(PLAY, args);
      var m = contractLine(out, /^PLAYED (\d+) events$/, 'PLAYED');
      return {
        ok: true,
        n: Number(m[1]),
        planned: plan.length,
        dryRun: !!o.dryRun,
        would: String(out).split(String.fromCharCode(10))
          .map(function (l) { return l.trim(); })
          .filter(function (l) { return /^WOULD /.test(l); }),
      };
    } finally {
      try { fs.unlinkSync(planPath); } catch (e) { /* already gone */ }
    }
  }

  var Mod = {
    DIR: DIR,
    safeName: safeName,
    CODE: CODE,
    MAX_WAIT_MS: MAX_WAIT_MS,
    DRAG_MIN_PX: DRAG_MIN_PX,
    WHEEL_NOTCH: WHEEL_NOTCH,
    parseRaw: parseRaw,
    normalise: normalise,
    substituteCode: substituteCode,
    validate: validate,
    resolve: resolve,
    build: build,
    load: load,
    save: save,
    chunkPath: chunkPath,
    windowRect: windowRect,
    record: record,
    play: play,
  };

  if (typeof module !== 'undefined' && module.exports) module.exports = Mod;
  else global.OWDBReplayRecorder = Mod;

  // ----------------------------------------------------------------- CLI ----
  //
  //   node recorder.js record open-import --code J8K2QP
  //   node recorder.js check  open-import --code 7QR4M0   (sends nothing)
  //   node recorder.js play   open-import --code 7QR4M0
  //   node recorder.js list
  //
  // The chunks the run needs are to-replays, open-import, confirm-import,
  // open-replay and open-events. Record them one at a time, in the state each
  // one starts from, and keep them short - a chunk that spans two menus has to
  // be re-recorded whole the first time Blizzard moves either of them.

  if (typeof module !== 'undefined' && require.main === module) {
    var argv = process.argv.slice(2);
    var cmd = argv[0];
    var name = argv[1];
    var flag = function (f) {
      var i = argv.indexOf(f);
      return i === -1 ? null : argv[i + 1];
    };

    (async function () {
      if (cmd === 'list') {
        if (!fs.existsSync(DIR)) { console.log('no chunks recorded yet'); return; }
        fs.readdirSync(DIR).filter(function (f) { return /\.json$/.test(f); })
          .forEach(function (f) {
            var c = JSON.parse(fs.readFileSync(path.join(DIR, f), 'utf8'));
            var codes = c.events.filter(function (e) { return e.type === 'text'; }).length;
            console.log(`  ${c.name.padEnd(16)} ${String(c.events.length).padStart(3)} events` +
              `  ${c.client.w}x${c.client.h}  ${c.recorded_at.slice(0, 10)}` +
              `${codes ? '  types the code' : ''}`);
          });
        return;
      }

      if (cmd === 'record' && name) {
        var code = flag('--code');
        console.log(`recording "${name}".`);
        console.log('  Alt-tab into Overwatch and perform the step; F10 ends it.');
        console.log('  Nothing outside the Overwatch window is recorded.');
        if (code) console.log(`  Type the code ${code.toUpperCase()} where it is asked for.`);
        else console.log('  (no --code given, so nothing will be replaced by a placeholder)');

        var got = await record(name, { code: code, maxSeconds: Number(flag('--max')) || 120 });
        console.log(`\nsaved ${got.chunk.events.length} events to ${got.path}`);
        got.chunk.events.forEach(function (e) {
          console.log('  +' + String(e.waitMs).padStart(5) + 'ms  ' +
            (e.type === 'click' ? `click ${e.button} at ${e.x},${e.y}`
              : e.type === 'text' ? `type ${e.value}` : `key ${e.key}`));
        });
        if (code && !got.codeFound) {
          console.log(`\nWARNING: ${code.toUpperCase()} was never typed, so this chunk has no ` +
            'placeholder in it. If it was meant to open a replay, re-record it.');
        }
        return;
      }

      if ((cmd === 'play' || cmd === 'check') && name) {
        var dry = cmd === 'check';
        var played = await play(name, { code: flag('--code'), dryRun: dry });
        played.would.forEach(function (l) { console.log('  ' + l); });
        console.log(`${dry ? 'checked' : 'played'} ${played.n} of ${played.planned} events`);
        return;
      }

      console.error('usage: node recorder.js record|play|check <name> ' +
        '[--code XXXXXX] | list');
      process.exit(1);
    })().catch(function (e) { console.error('FAILED: ' + e.message); process.exit(1); });
  }
})(typeof self !== 'undefined' ? self : this);

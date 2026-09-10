// tools/replay_bot/timing.js
// Every wait the replay bot spends, in one place - and the override file the
// console writes to tune them.
//
// WHY ONE FILE. These numbers were literals scattered across capture.js,
// input.js, drag.js and run.js, and almost every one of them has been wrong at
// least once in a way that produced confident nonsense: a 45ms seek gap that
// landed one press in five, a drag that finished 100s short, samples read while
// the HUD was still sliding. Tuning them meant editing four files and running a
// probe per constant. The console (tools/replay_bot/console/) turns each one on
// a slider instead; this is the config it reads and writes.
//
// WHAT IS AND IS NOT HERE. Only the numbers worth tuning against a live client -
// the ones with a measured history of being wrong. Structural constants that
// have never moved (MIN_PLAY_S, MOTION_DIFF, MIN_STEPS, LOW_SCORE) stay as plain
// consts in their own modules; making everything a knob would bury the six that
// matter.
//
// HOW IT LOADS. The defaults below, with state/console_timing.json merged over
// them when the console has written one (numbers only, by namespace and key, so
// a typo in the file is ignored rather than silently steering a run). The file
// lives under state/ because it is per-machine, like the attempt ledger - a rig
// with a slow client wants different numbers, and they must never travel in a
// commit. Once a set holds across several sessions, move it into the DEFAULTS
// here in an ordinary commit and delete the file.

(function (global) {
  'use strict';

  var fs = require('fs');
  var path = require('path');

  var OVERRIDE = path.join(__dirname, 'state', 'console_timing.json');

  // ---- the defaults, every one measured -----------------------------------

  var DEFAULTS = {
    // Divides the recorded waits inside every menu chunk (recorder.resolve).
    // A 2026-09-10 sweep ran the loop clean at 1x-2.5x and BROKE at 3x:
    // open-import's click on VIEW landed before the button had drawn. 2x is the
    // fast default that held; do not go above 2.5 until open-import waits for
    // the button rather than timing the click.
    chunk: { speed: 2 },

    // ESC at a stuck menu. One press was not enough - the client drops a key
    // that arrives mid-transition, the same way seeks are dropped - so it is
    // pressed up to `tries` times, `waitMs` apart, re-checking between each.
    // 2026-09-10: one run in ten hit this.
    esc: { tries: 3, waitMs: 1200 },

    // Waiting for the client to load an imported replay, then for it to be
    // ready for control input.
    //   timeoutMs  how long to wait for the team plates to draw before failing
    //   settleMs   an extra beat after they draw - the two live "K did not open
    //              the panel" failures (2026-09-10) both hit the window where
    //              the replay has rendered but N/K do not land yet
    //   tries/waitMs  readyFrame's poll for the HUD (capture.js): a loading
    //              screen is black, still, and settles beautifully, so the
    //              signal is the HUD being drawn, polled not read once
    load: { timeoutMs: 90000, settleMs: 500, tries: 12, waitMs: 400 },

    // Waiting for a replay to close after leave-replay.
    exit: { timeoutMs: 30000 },

    // The poll cadence for screen-state checks. A grab already costs ~0.5s, so
    // a 1s poll is a real poll, not a busy loop.
    poll: { ms: 1000 },

    // After N raises the media controls, the poll for the playhead to draw -
    // which doubles as the check that N went the right way. THIS USED TO BE ONE
    // READ ~400ms AFTER N AND IT COST TWO CODES (XTK7MM, 4TNEAJ, 2026-09-10):
    // the read was too early, saw nothing, and pressed N again, hiding the
    // controls it had just shown.
    media: { tries: 10, waitMs: 250 },

    // The gap between seek keypresses. The client ignores a key that arrives
    // while it is still seeking, silently. Measured landing for five presses:
    // 45ms and 150ms land 1, 300ms lands 3, 600ms and 1000ms land 5. THERE IS
    // NO CLIFF - bisecting twice gave 550ms dropping a press in one run and
    // landing all five in the next - so 700ms sits above every failure yet seen
    // and driver.seekTo verifies the result regardless.
    seek: { gapMs: 700 },

    // The seek-by-drag gesture (drag.js). Each is a Start-Sleep in
    // play_input.ps1's drag branch except hopPx, which sets the path density.
    //   prePress   cursor reaches the scrubber -> mouse button down
    //   postPress  button down -> the path walk begins
    //   perPoint   pause at each point along the path
    //   dwell      last point -> button up. The client's scrubber lags a fast
    //              walk; too short and the release snaps it back (a 25ms/
    //              no-dwell path landed 100s short), too long and it coasts
    //              past (~2s over on a 10ms/80ms one).
    //   hopPx      the path is split so the cursor never jumps further than
    //              this - the client stops following a bigger jump and the
    //              release snaps to wherever it stopped (a 690px drag in 86px
    //              hops landed 100s short).
    drag: { prePress: 40, postPress: 30, perPoint: 16, dwell: 120, hopPx: 24 },

    // An extra beat after a SEEK settles, before the HUD is read. The seek's
    // own settle watches the play area (y 200-1100); the portrait band above it
    // (y ~95-205) finishes drawing a little later. Every sample after the first
    // on the 2026-09-10 ten-map run came back mid-transition without this.
    // (run.js --sample-quiesce overrides it for a run.)
    sample: { quiesceMs: 500 },

    // The generic post-seek wait before a one-frame grab (capture.js quiesce).
    // THIS WAS ZERO, AND ZERO WAS RIGHT UNTIL GRABBING GOT FAST: a PowerShell
    // spawn plus PrintWindow ran ~0.5s, so the HUD had finished moving by the
    // time the frame was taken. host.js took a grab to 204ms and the reads
    // started landing mid-transition. Re-measure with probe_limits.js if the
    // grab time moves again, in either direction.
    quiesce: { ms: 400 },
  };

  var NS = Object.keys(DEFAULTS);

  // ---- load / reload / save ----------------------------------------------

  function clone(o) { return JSON.parse(JSON.stringify(o)); }

  // The live object every module reads. Mutated in place by reload() so a
  // consumer that captured the reference at require() time still sees changes.
  var T = clone(DEFAULTS);

  // Merge `over` onto `target`, in place: known namespaces, known keys, finite
  // numbers only.
  function applyOver(target, over) {
    if (!over || typeof over !== 'object') return target;
    NS.forEach(function (ns) {
      if (!over[ns] || typeof over[ns] !== 'object') return;
      Object.keys(target[ns]).forEach(function (k) {
        var v = over[ns][k];
        if (typeof v === 'number' && isFinite(v)) target[ns][k] = v;
      });
    });
    return target;
  }

  // Back to the defaults, then the override file re-applied. Returns T.
  function reload() {
    var fresh = clone(DEFAULTS);
    var over = null;
    try { over = JSON.parse(fs.readFileSync(OVERRIDE, 'utf8')); } catch (e) { /* none */ }
    applyOver(fresh, over);
    NS.forEach(function (ns) { T[ns] = fresh[ns]; });
    return T;
  }

  // Write `partial` (a {ns:{key:number}} subset) merged over whatever the file
  // already holds, clamped to sane bounds, and reload from it. Returns T.
  function save(partial) {
    var current = null;
    try { current = JSON.parse(fs.readFileSync(OVERRIDE, 'utf8')); } catch (e) { current = {}; }
    NS.forEach(function (ns) {
      if (!partial || !partial[ns]) return;
      current[ns] = current[ns] || {};
      Object.keys(DEFAULTS[ns]).forEach(function (k) {
        if (partial[ns][k] === undefined) return;
        var v = Number(partial[ns][k]);
        if (!isFinite(v)) throw new Error('bad value for ' + ns + '.' + k + ': ' +
          JSON.stringify(partial[ns][k]));
        current[ns][k] = clamp(ns, k, v);
      });
    });
    fs.mkdirSync(path.dirname(OVERRIDE), { recursive: true });
    fs.writeFileSync(OVERRIDE, JSON.stringify(current, null, 2) + '\n', 'utf8');
    return reload();
  }

  function clearSaved() {
    try { fs.unlinkSync(OVERRIDE); } catch (e) { /* was not there */ }
    return reload();
  }

  // Floors that keep a value from breaking the code that reads it: a count
  // cannot be zero, drag.plan divides by hopPx, chunk.speed under 1 would slow
  // a chunk below how it was recorded. Everything else floors at 0.
  function clamp(ns, k, v) {
    v = Math.round(v);
    if (k === 'tries') return Math.max(1, v);
    if (ns === 'drag' && k === 'hopPx') return Math.max(1, v);
    if (ns === 'chunk' && k === 'speed') return Math.max(1, v);
    if (ns === 'poll' && k === 'ms') return Math.max(1, v);
    return Math.max(0, v);
  }

  reload();

  // The functions ride on T for the console's convenience; consumers only ever
  // read the namespaces, and applyOver/reload iterate NS, so the extra keys are
  // harmless.
  T.DEFAULTS = DEFAULTS;
  T.NS = NS;
  T.OVERRIDE = OVERRIDE;
  T.reload = reload;
  T.save = save;
  T.clearSaved = clearSaved;
  T.applyOver = applyOver;

  if (typeof module !== 'undefined' && module.exports) module.exports = T;
  else global.OWDBReplayTiming = T;
})(typeof self !== 'undefined' ? self : this);

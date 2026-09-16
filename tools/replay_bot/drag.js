// tools/replay_bot/drag.js
// Seeking by dragging the scrubber to a computed pixel, instead of pressing the
// skip key n times.
//
// WHY. The skip key moves a fixed interval - 60 seconds, once the once-a-session
// options trip has set it - and the client SILENTLY IGNORES a press that arrives
// while it is still seeking, so presses need a 700ms gap and every one is
// verified against the playhead. Crossing five minutes therefore costs five
// presses and about three and a half seconds. Measured over a twenty-map league
// run, sampling was 15.7s of a 35.6s map: the largest single cost in the loop.
//
// A drag crosses any distance in one gesture.
//
// "SEEKING IS NEVER RECORDED" STILL HOLDS, AND THIS IS NOT THAT. recorder.js
// refuses to record a scrub because a recorded one is a fixed pixel drag that
// means a different time on every map, the bar's scale being different each
// time. This computes the target from THIS map's measured bar - capture.js
// calibrates zeroX and stepPx per map by pressing the key once and looking - so
// the pixel means the intended second wherever it lands. It is then checked
// against the playhead like any other seek, and a miss is a miss either way.
//
// IT IS ALSO MORE PRECISE THAN THE KEY, WHICH FIXES A REAL BUG. Samples snap to
// multiples of the 60-second step, so a short round cannot be sampled inside:
// a Junkertown escort's second round ran 43 seconds, the nearest grid point
// landed in the break before it, and the round was captured with nothing in it.
// On the bars measured in that run one pixel is worth 0.18 to 0.57 seconds.

(function (global) {
  'use strict';

  var calib = require('./calib.js');
  var T = require('./timeline.js');
  var TIMING = require('./timing.js');   // the seek gesture's waits live in TIMING.drag

  // Points along the drag. play_input.ps1's own comment records that a drag
  // with no intermediate points used to arrive as a click at the start, so the
  // path is not decoration - and MIN_STEPS keeps even a tiny drag a gesture.
  var MIN_STEPS = 8;

  // How long the button stays down. Long enough for the client to register a
  // grab on the scrubber rather than a click on the bar. Not one of the tuned
  // knobs: play_input.ps1's drag branch derives the real hold from the path
  // walk plus `dwell`, and only reads this for the dry-run summary.
  var HOLD_MS = 220;

  function secondsPerPixel(ref) {
    return ref.stepS / ref.stepPx;
  }

  // The one drag event that puts the playhead at `toS`, starting from wherever
  // it is now (`fromX`, read off the frame).
  //
  // A target beyond the bar is refused rather than clamped: it means a sample
  // was planned past the end of the map, and dragging to the end instead would
  // read a plausible frame from the wrong moment.
  // `timing` overrides TIMING.drag for this one plan - what the console passes
  // to try live slider values without writing the override file. Omitted, the
  // module config (with state/console_timing.json folded in) applies.
  function plan(ref, fromX, toS, timing) {
    var t = timing ? Object.assign({}, TIMING.drag, timing) : TIMING.drag;
    var bar = calib.FROZEN.timeline;
    var toX = Math.round(T.xForSeconds(toS, ref));
    if (toX < bar.x0 || toX > bar.x1) {
      throw new Error('t=' + Math.round(toS) + 's is at x=' + toX +
        ', off the bar (' + bar.x0 + '..' + bar.x1 + ') - the sample plan ' +
        'reaches past this map');
    }

    // The middle of the bar's measured rows: a scrub that drifts off the bar is
    // dropped by the client, and the bar is only a few pixels tall.
    var y = Math.round((bar.y0 + bar.y1) / 2);
    var from = Math.round(fromX);

    var hop = Math.max(1, t.hopPx);
    var steps = Math.max(MIN_STEPS, Math.ceil(Math.abs(toX - from) / hop));
    var path = [];
    for (var i = 0; i <= steps; i++) {
      path.push({ x: Math.round(from + (toX - from) * (i / steps)), y: y });
    }

    return {
      type: 'drag',
      button: 'left',
      x: from,
      y: y,
      toX: toX,
      toY: y,
      path: path,
      waitMs: 0,
      holdMs: HOLD_MS,
      // Stamped on the event so play_input.ps1 reads them off the plan rather
      // than restating the numbers a second time.
      prePress: t.prePress,
      postPress: t.postPress,
      perPoint: t.perPoint,
      dwell: t.dwell,
    };
  }

  // A seek-by-drag bound to one map and one client, in the shape the driver
  // wants: `(toT) -> boolean`, true if it dragged and false if the counted key
  // presses should take over instead. `deps` is everything that touches the
  // outside world or the run's state:
  //
  //   ref()          {zeroX, stepPx, stepS} for THIS map's bar, or null before
  //                  calibration has measured it - drag has no scale yet
  //   frame()        the current frame (path or image) to read the playhead off
  //   loadImage(x)   decode it
  //   playhead(img)  {centre} in pixels, or null when the knob is not drawn
  //   play(events)   perform the gesture
  //   log(line)      note a skipped drag
  //
  // It declines - returns false - rather than guessing whenever it cannot do
  // the seek honestly: no bar scale, no readable playhead, or a target off the
  // bar (a sample planned past the end of the map, which the caller's
  // miss-detection then drops).
  function seeker(deps) {
    return async function (toT) {
      var ref = deps.ref();
      if (!ref) return false;
      var knob = deps.playhead(await deps.loadImage(await deps.frame()));
      if (!knob) return false;
      var ev;
      try {
        ev = plan(ref, knob.centre, toT);
      } catch (e) {
        deps.log('    (drag skipped: ' + e.message + ')');
        return false;
      }
      await deps.play([ev]);
      return true;
    };
  }

  var Mod = {
    MIN_STEPS: MIN_STEPS,
    HOLD_MS: HOLD_MS,
    TIMING: TIMING,          // the timing.js config; the gesture's knobs are TIMING.drag
    plan: plan,
    seeker: seeker,
    secondsPerPixel: secondsPerPixel,
  };

  if (typeof module !== 'undefined' && module.exports) module.exports = Mod;
  else global.OWDBReplayDrag = Mod;
})(typeof self !== 'undefined' ? self : this);

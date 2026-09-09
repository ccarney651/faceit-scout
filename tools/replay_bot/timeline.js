// tools/replay_bot/timeline.js
// Reading round structure off the replay scrubber, and planning where to sample.
// See specs/2026-09-08-replay-bot-design.md §4.
//
// The replay bar draws between-round breaks in a different colour from play
// time, so the round structure of a map is sitting there in the UI - no need to
// infer it from score changes after the fact, and no need to sample blindly on
// a fixed interval hoping to catch each round.
//
// Measured on the rig against a 17:42 three-round Control replay, the bar
// spanned x=73..2449 and showed exactly two coloured runs, at 6:46-8:46 and
// 12:24-13:25. Three play segments, two breaks, correct.
//
// BREAKS ARE DETECTED BY COLOUR, NOT BRIGHTNESS. Luminance along the bar is
// polluted by event ticks and the playhead knob, which are bright; the blue
// channel's lead over red is clean. `minRun` then discards anything too narrow
// to be a real break - a stray tick read as a boundary would cut a round in
// half and invent a segment that never happened.
//
// Sampling deliberately avoids segment edges. A round's first and last instants
// are setup and aftermath, where portraits are absent, stale, or mid-transition.

(function (global) {
  'use strict';

  // Per-pixel break flags to timed segments across the bar.
  //
  // `flags[i]` corresponds to bar pixel x0+i; `duration` is the replay's total
  // length in seconds, which the scrubber prints beside the current time.
  function segments(flags, opts) {
    var duration = opts.duration;
    var minRun = opts.minRun || 1;
    var n = flags.length;
    if (!n) return [];

    var spp = duration / n;

    // Run-length encode, then absorb runs too short to be meaningful into
    // whatever preceded them.
    var runs = [];
    var cur = flags[0];
    var start = 0;
    for (var i = 1; i < n; i++) {
      if (flags[i] !== cur) {
        runs.push({ v: cur, a: start, b: i - 1 });
        cur = flags[i];
        start = i;
      }
    }
    runs.push({ v: cur, a: start, b: n - 1 });

    var kept = [];
    runs.forEach(function (r) {
      var len = r.b - r.a + 1;
      if (len < minRun && kept.length) {
        kept[kept.length - 1].b = r.b;
        return;
      }
      if (len < minRun && !kept.length) {
        // A short leading run has nothing to merge into; treat it as play so
        // the map does not start with a phantom break.
        kept.push({ v: false, a: r.a, b: r.b });
        return;
      }
      if (kept.length && kept[kept.length - 1].v === r.v) {
        kept[kept.length - 1].b = r.b;
        return;
      }
      kept.push({ v: r.v, a: r.a, b: r.b });
    });

    return kept.map(function (r) {
      return {
        play: !r.v,
        from: r.a * spp,
        to: (r.b + 1) * spp,
      };
    });
  }

  // Timestamps to grab, in order. `n` points per play segment, evenly spaced
  // strictly inside it: i/(n+1) for i in 1..n.
  //
  // With `stepS`, points are snapped to that grid. Seeking is done by jumping
  // to the start and pressing REPLAY FORWARD, which moves in fixed 20s steps,
  // so an unsnapped target is simply not reachable - asking for 1:42 would mean
  // dragging the scrubber to a pixel, which is both imprecise and mouse work.
  // On the grid, every seek is an exact number of keypresses from a known
  // origin, so errors cannot accumulate across a map.
  //
  // Snapping can collide (two thirds of a short round rounding to the same
  // step), and duplicates are dropped rather than spending an 800ms grab on a
  // frame already captured.
  function plan(segs, n, opts) {
    var step = opts && opts.stepS;
    var out = [];

    segs.forEach(function (s) {
      if (!s.play) return;
      var span = s.to - s.from;
      var pts = [];
      for (var i = 1; i <= n; i++) pts.push(s.from + span * (i / (n + 1)));

      if (!step) {
        out = out.concat(pts);
        return;
      }

      // The reachable points inside this segment.
      var lo = Math.ceil(s.from / step) * step;
      var hi = Math.floor(s.to / step) * step;

      var snapped = pts.map(function (t) {
        var g = Math.round(t / step) * step;
        if (lo > hi) {
          // A segment too short to contain any grid point at all. Fixed-step
          // seeking cannot land inside it, so take the nearest reachable
          // instant to its middle and accept being marginally outside - the
          // alternative is not sampling the segment at all.
          return Math.round(((s.from + s.to) / 2) / step) * step;
        }
        return Math.min(hi, Math.max(lo, g));
      });

      out = out.concat(snapped.filter(function (t, i) {
        return snapped.indexOf(t) === i;
      }));
    });

    // Dedupe across the whole plan, preserving order.
    return out.filter(function (t, i) { return out.indexOf(t) === i; });
  }

  // How many samples a map of this kind deserves. Maps with rounds get fewer
  // per segment because they have several segments; a map with one continuous
  // segment needs more within it to see the same amount of the match.
  function samplesFor(segs) {
    return segs.filter(function (s) { return s.play; }).length > 1 ? 3 : 5;
  }

  // Playhead position to seconds, and back.
  //
  // `ref` is measured per map, never assumed: `zeroX` is where the knob sits
  // after JUMP TO START, and `stepPx` is how far one press of REPLAY FORWARD
  // moves it. Pixels per second differ by map - a 20-second step measured 45px
  // on a 17-minute Control replay and 69px on an 11-minute Escort one - so a
  // constant here would be wrong on every map but one.
  function secondsAt(x, ref) {
    return (x - ref.zeroX) / ref.stepPx * ref.stepS;
  }

  // The same, snapped to the grid seeking can actually reach. Positions are
  // whole presses from the start, so a target between steps is not a target.
  function stepAt(x, ref) {
    return Math.round((x - ref.zeroX) / ref.stepPx);
  }

  function xForSeconds(t, ref) {
    return ref.zeroX + (t / ref.stepS) * ref.stepPx;
  }

  // The client's own list of skip intervals. Measured values are snapped to it
  // because the setting is one of these, not an arbitrary number - and a
  // measurement that lands nowhere near any of them means something else is
  // wrong and should be refused rather than rounded into looking fine.
  var INTERVALS = [5, 10, 20, 30, 60];

  // What one press of REPLAY FORWARD is worth in seconds, from how far it moved
  // the knob and how fast the knob moves during playback.
  //
  // THE SETTING CANNOT BE TRUSTED ACROSS SESSIONS. Replay viewer options are a
  // known Blizzard bug: they apply while the client runs and revert to defaults
  // at the next start, so an interval set to 60 last night is 20 tonight and
  // nothing on screen says which. Assuming 20 when it is 60 would place every
  // sample at a third of its intended time - inside the wrong round, with a
  // wholly plausible-looking result.
  function stepSecondsFrom(stepPx, pxPerSec, opts) {
    var allowed = (opts && opts.allowed) || INTERVALS;
    var tolerance = (opts && opts.tolerance) === undefined ? 0.2 : opts.tolerance;
    if (!(pxPerSec > 0) || !(stepPx > 0)) {
      return { ok: false, raw: null, stepS: null, reason: 'nothing moved' };
    }

    var raw = stepPx / pxPerSec;
    var best = allowed[0];
    allowed.forEach(function (v) {
      if (Math.abs(v - raw) < Math.abs(best - raw)) best = v;
    });
    var off = Math.abs(best - raw) / best;
    return {
      ok: off <= tolerance,
      raw: raw,
      stepS: best,
      reason: off <= tolerance ? null :
        'a press measured ' + raw.toFixed(1) + 's, which is not near any of ' +
        allowed.join('/') + 's - the playback rate or the step reading is wrong',
    };
  }

  // Play segments too short to be a round, reclassified as breaks.
  //
  // Every map measured so far opens with a blip of play a few seconds long -
  // 0:10-0:17 on one, 0:07-0:21 on another - which is the assemble phase, not a
  // round. It matters more than it looks: with a 60-second step the only grid
  // point anywhere near such a segment is 0:00, so the bot sampled the very
  // start of the map, where no portraits are drawn yet, and read ten cells of
  // confident nonsense (Zarya 0.52, Jetpack Cat 0.47) that would have gone
  // straight into the output.
  function dropShortPlay(segs, minPlayS) {
    return segs.map(function (s) {
      if (!s.play || (s.to - s.from) >= minPlayS) return s;
      return { from: s.from, to: s.to, play: false, tooShort: true };
    });
  }

  var Mod = {
    INTERVALS: INTERVALS,
    dropShortPlay: dropShortPlay,
    stepSecondsFrom: stepSecondsFrom,
    secondsAt: secondsAt,
    stepAt: stepAt,
    xForSeconds: xForSeconds,
    segments: segments,
    plan: plan,
    samplesFor: samplesFor,
  };

  if (typeof module !== 'undefined' && module.exports) module.exports = Mod;
  else global.OWDBReplayTimeline = Mod;
})(typeof self !== 'undefined' ? self : this);

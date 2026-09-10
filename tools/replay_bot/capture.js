// tools/replay_bot/capture.js
// Capturing one already-open replay: the part run.js and capture_map.js share.
// See ARCHITECTURE.md §14.
//
// This was capture_map.js's body until there were two callers for it. Forking
// it would have been the obvious cheap move and the wrong one - this repo
// already keeps `tools/capture_divergence.py` around because two copies of the
// same capture logic drifted apart once, and the second copy is always the one
// nobody remembers to fix.
//
// What lives here is the sequence proven on a live replay on 2026-09-09:
//
//   1. Grab a frame, and refuse it if it is not the size the geometry was
//      frozen at.
//   2. Open the events viewer, because the scrubber only draws round breaks
//      while it is showing - measured, then pressed at most once.
//   3. Calibrate the bar against THIS map: jump to start, read the playhead,
//      press forward once, read it again. A 20-second step was 45px on one map
//      and 69px on another, so the scale is never assumed. The bar's span then
//      gives the map's duration, which is what lets a run work unattended.
//   4. Read the round structure off the bar, place samples inside the play
//      segments, and drive to each one - verifying every seek against the
//      playhead, because the client silently ignores seek keys that arrive
//      while it is already seeking.

(function (global) {
  'use strict';

  var fs = require('fs');
  var path = require('path');
  var canvas = require('@napi-rs/canvas');
  var G = require('./grab.js');
  var I = require('./input.js');
  var D = require('./driver.js');
  var calib = require('./calib.js');
  var Crop = require('./crop.js');
  var T = require('./timeline.js');
  var Drag = require('./drag.js');
  var Recorder = require('./recorder.js');
  var TIMING = require('./timing.js');
  var P = require('./phases.js');

  var STEP_S = 20;

  // Below this a match is a suggestion, not a reading. vote.js resolves a slot
  // across frames downstream; this makes a doubtful cell visible in the
  // meantime rather than averaged away. (phases.js has its own copy for
  // sampleAt's re-read; they mean the same thing.)
  var LOW_SCORE = 0.6;

  // The stages of a capture - the events viewer, bar calibration, the structure
  // read, the sample loop - are phases.js now, so the console can run any one
  // alone. The waits they spend live in timing.js (TIMING.quiesce, .sample,
  // .load, .media), each with its measured history there.

  var mmss = function (s) {
    return Math.floor(s / 60) + ':' + String(Math.round(s % 60)).padStart(2, '0');
  };

  // The frame math (pixelDiff/pixels) and the client-waits (ensurePaused,
  // readyFrame, barFrame, measureRate, worstOf) are phases.js now; makeIo below
  // reaches for P.pixelDiff the same way the phases do.
  var pixelDiff = P.pixelDiff;

  // Everything that touches the machine, in one object, so a caller can point
  // the capture at recorded frames instead of a live client.
  //
  // A GRAB COSTS 497ms AND ONLY 156ms OF IT IS WORK. Measured on the rig: a
  // bare PowerShell spawn is 211ms, a spawn that runs Add-Type is 341ms, and
  // the capture itself is the small remainder. So the way to make a sample
  // faster is to take fewer frames, not to make each one quicker - and the
  // settle already ends holding a frame the screen has stopped moving in, which
  // is exactly what the position check and the sample both want.
  //
  // `lastFrame()` hands that frame on. It cut two of the four grabs a sample
  // used to take.
  function makeIo(opts) {
    var framesDir = opts.framesDir;
    var log = opts.log || function () {};
    var n = 0;
    var lastSettled = null;

    // Every grab this makes is scratch until keepAs says otherwise - a settle,
    // a pause check, a quiesce, a probe, a calibration read. Written as .bmp
    // (grab.js and host.ps1 pick the encoder off the extension: 65ms against a
    // PNG's 210ms) and tracked here so a map that finishes cleanly does not
    // leave thirty raw frames on disk for every handful that became samples.
    var transient = [];

    async function grabTo(tag) {
      var p = path.join(framesDir, 'cap-' + tag + '-' + (n++) + '.bmp');
      var r = await G.capture(p);
      if (!r.ok) throw new Error('grab failed: ' + r.reason);
      transient.push(p);
      return p;
    }

    // With the replay paused a settle agrees on its first comparison, so the
    // retries only ever cost time when something is genuinely still moving -
    // and five of them is plenty to establish that.
    var settle = I.makeSettle({
      grab: function () { return grabTo('settle'); },
      diff: pixelDiff,
      threshold: 0.6,
      maxTries: 5,
      waitMs: 100,
    });

    return {
      log: log,
      grabTo: grabTo,
      loadImage: canvas.loadImage,
      sendKeys: function (keys) { return I.sendKeys(keys); },
      // One computed mouse gesture into the live window. Named on the io so the
      // driver reaches seeking-by-drag the same way it reaches seeking-by-key,
      // and fakeio.js can record the events instead of moving a real cursor.
      playEvents: function (events) { return Recorder.playEvents(events, { name: 'seek' }); },
      settle: async function () {
        var r = await settle();
        lastSettled = r.frame;
        if (!r.settled) log('    (warning: screen never settled)');
        return r;
      },
      // The cheap alternative: wait long enough for a seek to have drawn, then
      // take ONE frame.
      //
      // Comparing two frames costs a second and, with the replay paused, spends
      // it confirming something that is almost always already true. The sample
      // loop uses this instead and checks the result rather than the process -
      // a frame caught mid-transition shows up as a low match score, and that
      // is the thing worth reacting to.
      quiesce: async function (ms) {
        await realSleep(ms === undefined ? TIMING.quiesce.ms : ms);
        lastSettled = await grabTo('q');
        return { settled: true, frame: lastSettled };
      },
      lastFrame: function () { return lastSettled; },
      // Named here so the live io and fakeio.js have the same surface, and
      // nothing has to know which of the two it is holding.
      sleep: realSleep,
      // Retained frames are a regression corpus, so a frame that gets read as a
      // sample is kept under a name that says which sample it was - always as
      // a .png, because the corpus is read by tools with no idea a .bmp is
      // even possible. The source is scratch (.bmp or .png, whichever this
      // grabbed it as), so this decodes and re-encodes rather than copying
      // bytes under a lying extension - a raw BMP copied to a .png name reads
      // fine until the day something opens it expecting one.
      keepAs: function (tag, src) {
        var from = src || lastSettled;
        if (!from) return null;
        var dest = path.join(framesDir, 'cap-' + tag + '-' + (n++) + '.png');
        return canvas.loadImage(from).then(function (img) {
          var cv = canvas.createCanvas(img.width, img.height);
          cv.getContext('2d').drawImage(img, 0, 0);
          fs.writeFileSync(dest, cv.toBuffer('image/png'));
          return dest;
        });
      },
      // Called once a map is done: sweepTransient on success, so the scratch
      // frames do not outlive the map they were taken for.
      sweepTransient: function () {
        transient.forEach(function (p) {
          try { fs.unlinkSync(p); } catch (e) { /* already gone, or never written */ }
        });
        transient = [];
      },
      // Called on failure. A diagnosis never reaches for every scratch frame a
      // failed map took - finding the stuck-assemble-phase bug that 7V4END hit
      // used exactly two, out of the fifty-odd it left behind: the very first
      // grab and one near where the capture actually broke. So this keeps the
      // first plus the most recent KEEP_ON_FAILURE and drops the rest, rather
      // than every scratch frame forever - a failed map that loops (retrying a
      // settle that never settles, say) used to cost as much disk as it took
      // retries, unbounded. The kept handful is re-encoded to .png because it
      // is staying for good now, and BMP exists for grab speed, not permanence.
      forgetTransient: function () {
        if (!transient.length) return Promise.resolve();
        var keep = transient.length > KEEP_ON_FAILURE
          ? [transient[0]].concat(transient.slice(-(KEEP_ON_FAILURE - 1)))
          : transient.slice();
        var keepSet = {};
        keep.forEach(function (p) { keepSet[p] = true; });

        transient.forEach(function (p) {
          if (keepSet[p]) return;
          try { fs.unlinkSync(p); } catch (e) { /* already gone, or never written */ }
        });

        var converted = keep.map(function (p) {
          if (!/\.bmp$/i.test(p)) return Promise.resolve(p);
          var dest = p.replace(/\.bmp$/i, '.png');
          return canvas.loadImage(p).then(function (img) {
            var cv = canvas.createCanvas(img.width, img.height);
            cv.getContext('2d').drawImage(img, 0, 0);
            fs.writeFileSync(dest, cv.toBuffer('image/png'));
            fs.unlinkSync(p);
            return dest;
          });
        });

        transient = [];
        return Promise.all(converted);
      },
    };
  }

  // First plus most recent, on a failure: covers "what did the map open on"
  // and "what was on screen when it broke" without keeping the noisy middle
  // of a run that retried the same check dozens of times.
  var KEEP_ON_FAILURE = 12;

  var realSleep = function (ms) { return new Promise(function (r) { setTimeout(r, ms); }); };

  function make(io) {
    var log = io.log || function () {};

    async function captureMap(opts) {
      var o = opts || {};

      // Phase timings, because the last three performance guesses were wrong in
      // three different ways and a printed number ends the argument.
      var marks = [];
      var mark0 = Date.now();
      var since = mark0;
      function mark(name) {
        var now = Date.now();
        marks.push({ name: name, ms: now - since });
        since = now;
      }
      var told = o.told || null;
      var stepS = o.stepS || STEP_S;

      var M = o.matcher || P.makeMatcher();

      // Where the playhead says we are, in seconds. Null before the bar is
      // calibrated, and on any frame with no readable knob - which the driver
      // treats as "no answer", never as a position.
      var ref = null;
      var positionNow = async function () {
        // The settle that just ran left a still frame; reading the playhead off
        // that costs a decode rather than another half-second grab.
        var fresh = io.lastFrame && io.lastFrame();
        var knob = Crop.playheadX(await io.loadImage(fresh || await io.grabTo('pos')), calib);
        if (!knob || !ref) return null;
        return T.secondsAt(knob.centre, ref);
      };

      // Held as an object because stepS is filled in after the driver exists -
      // measuring the step needs the driver to press the keys.
      // Setup presses (N, K, and the two calibration keys) get the careful
      // two-frame settle, because a panel read while it is still drawing is
      // measured as a brightness and then believed. Sampling gets a single
      // fixed wait - a half-drawn HUD announces itself in the scores - and
      // that ONE wait is shared: the settle inside driver.seekTo leaves the
      // frame the sample loop then reads, rather than each paying its own.
      var sampling = false;
      var sampleQuiesceMs = function () {
        return o.sampleQuiesceMs != null ? o.sampleQuiesceMs : TIMING.sample.quiesceMs;
      };

      // Seek by dragging the scrubber straight to the target second, instead of
      // pressing the skip key n times with a 700ms gap between each. The key
      // moves a fixed interval and the client silently ignores a press that
      // lands mid-seek, so crossing five minutes was five presses and ~3.5s;
      // one drag crosses any distance in ~3s. drag.js turns the target second
      // into the pixel it sits at on THIS map's measured bar (`ref`), so the
      // playhead check that guards a key seek guards this one too.
      //
      // Declines to the keys when there is nothing to drag from - the bar is
      // not calibrated yet, or no readable playhead - and when the target is
      // off the bar, which the sample loop's miss-detection then drops.
      var seekDrag = Drag.seeker({
        ref: function () { return ref; },
        frame: function () { return (io.lastFrame && io.lastFrame()) || io.grabTo('drag-from'); },
        loadImage: io.loadImage,
        playhead: function (img) { return Crop.playheadX(img, calib); },
        play: io.playEvents,
        log: log,
      });

      var drvCtx = {
        sendKeys: io.sendKeys,
        focus: async function () {},
        settle: function () { return sampling ? io.quiesce(sampleQuiesceMs()) : io.settle(); },
        position: positionNow,
        seekDrag: o.noDrag ? undefined : seekDrag,
        stepS: stepS,
      };
      var drv = D.make(drvCtx);

      var ctx = { io: io, drv: drv, log: log };

      // 1. A frame, and the guard that the HUD is where it was frozen.
      var img0 = await io.loadImage(await io.grabTo('timeline'));
      var chk = calib.check({ w: img0.width, h: img0.height });
      if (!chk.ok) throw new Error('calibration smoke check failed: ' + chk.reason);

      // 1b. Stop the replay before anything waits for the screen to be still.
      mark('first frame');
      var stopped = await P.ensurePaused(io, drv);
      log('replay ' + (stopped.pressed ? 'was playing, paused it' : 'already paused'));
      if (!stopped.paused) {
        throw new Error('the replay will not stop - every read after this would ' +
          'be of a moving picture');
      }
      mark('pause check');

      // 2. The events viewer, without which the scrubber shows no round breaks.
      var viewer = await P.openEventsViewer(ctx);
      img0 = viewer.img0;
      mark('events viewer');

      // 2b. The once-a-session trip to set the skip interval - needs the
      //     controls up, must land before the step is measured - then a check
      //     that the menu did not leave the panel shut behind it.
      if (o.afterViewer) {
        await o.afterViewer();
        img0 = (await P.ensurePanelOpen(ctx)).img0;
      }
      mark('interval chunk');

      // 3. The bar's scale on this map, and how many seconds one press is worth.
      var cal = await P.calibrateBar(ctx, { stepS: o.stepS, log: log });
      ref = cal.ref;
      stepS = cal.stepS;
      drvCtx.stepS = stepS;
      var pxPerSec = cal.pxPerSec;
      mark('bar calibration');

      var dur = P.deriveDuration({
        ref: ref, pxPerSec: pxPerSec, atZeroWidth: cal.atZero.width, told: told,
      });
      var duration = dur.duration;
      var implied = dur.implied;
      log('one step = ' + ref.stepPx.toFixed(1) + 'px (' + stepS + 's), zero at ' + ref.zeroX);
      log('duration ' + mmss(duration) + ' (' + (told ? 'given' : 'measured off the bar') +
        (told ? ', bar implies ' + mmss(implied) : '') + ')');

      // 4. Round structure, and where to sample inside it.
      var struct = P.readStructure(img0, {
        ref: ref, duration: duration, stepS: stepS, log: log, mmss: mmss,
      });
      var segs = struct.segments;
      var plan = struct.plan;

      // 5. Drive to each sample and read the HUD. The driver is in sampling mode
      //    now - its settle is the fixed quiesce, not the two-frame one.
      var samples = [];
      var missed = [];
      sampling = true;
      for (var i = 0; i < plan.length; i++) {
        var t = plan[i];
        var started = Date.now();
        var s = await P.sampleAt(ctx, t, {
          matcher: M, stepS: stepS, mmss: mmss, log: log,
        });
        if (s.missed) {
          missed.push({ t: s.t, at: s.at, reason: s.reason === 'seek' ? undefined : s.reason });
          continue;
        }
        samples.push({ t: s.t, at: s.at, a: s.a, b: s.b, framePath: s.framePath });
        log(mmss(t).padStart(6) + '  (' + ((Date.now() - started) / 1000).toFixed(1) + 's)');
        ['a', 'b'].forEach(function (side) {
          log('        ' + side + ': ' + s[side].map(function (r) {
            return r.name + ' ' + r.score.toFixed(2) + (r.score < LOW_SCORE ? ' ??' : '');
          }).join(' | '));
        });
      }

      mark('samples');
      var total = (Date.now() - mark0) / 1000;
      log('');
      log('time: ' + marks.filter(function (m) { return m.ms >= 200; })
        .map(function (m) { return m.name + ' ' + (m.ms / 1000).toFixed(1) + 's'; })
        .join(', ') + '  = ' + total.toFixed(1) + 's');

      return {
        viewer: viewer,
        ref: ref,
        timings: marks,
        stepS: stepS,
        pxPerSec: pxPerSec,
        duration: duration,
        impliedDuration: implied,
        segments: segs,
        plan: plan,
        samples: samples,
        missed: missed,
      };
    }

    return { captureMap: captureMap };
  }

  // The play segments as emit.js wants rounds: from_t/to_t, in order. Round
  // numbers come from the scrubber, not from watching the score change.
  function roundsOf(segments) {
    return segments.filter(function (s) { return s.play; })
      .map(function (s) { return { from_t: s.from, to_t: s.to }; });
  }

  // Samples in the shape emit.js reads: GUIDs, per side. A name never travels.
  function observationsOf(samples) {
    return samples.map(function (s) {
      return {
        t: s.t,
        heroes_a: s.a.map(function (x) { return x.guid; }),
        heroes_b: s.b.map(function (x) { return x.guid; }),
      };
    });
  }

  function doubtfulOf(samples) {
    var out = [];
    samples.forEach(function (s) {
      ['a', 'b'].forEach(function (side) {
        s[side].forEach(function (x) {
          if (x.score < LOW_SCORE) {
            out.push({ t: s.t, side: side, name: x.name, score: x.score });
          }
        });
      });
    });
    return out;
  }

  var Mod = {
    STEP_S: STEP_S,
    LOW_SCORE: LOW_SCORE,
    mmss: mmss,
    pixelDiff: pixelDiff,
    makeIo: makeIo,
    make: make,
    roundsOf: roundsOf,
    observationsOf: observationsOf,
    doubtfulOf: doubtfulOf,
  };

  if (typeof module !== 'undefined' && module.exports) module.exports = Mod;
  else global.OWDBReplayCapture = Mod;
})(typeof self !== 'undefined' ? self : this);

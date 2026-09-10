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
  var Match = require('./match.js');
  var T = require('./timeline.js');

  var STEP_S = 20;

  // Below this a match is a suggestion, not a reading. Downstream, vote.js
  // resolves a slot across frames; this is what makes a doubtful cell visible
  // in the meantime rather than averaged away.
  var LOW_SCORE = 0.6;

  // How long a seek needs to have drawn before its frame is worth reading.
  //
  // THIS WAS ZERO, AND ZERO WAS RIGHT UNTIL GRABBING GOT FAST. probe_limits.js
  // seeks, reads immediately, then reads the same position again once
  // everything has stopped, and compares the least confident of the ten cells:
  // across two runs and four delays the early read matched the settled one
  // every time, 0.66 at +0ms against 0.66 at +640ms. The reason was that a grab
  // was not free - a PowerShell spawn plus PrintWindow ran about half a second,
  // so the HUD had long finished moving by the time the frame was taken. The
  // wait was waiting for something that had already happened.
  //
  // The old comment here ended "if grabbing ever gets fast (a persistent host
  // would make it ~150ms), measure this again - the free wait disappears with
  // it". Then host.js took a grab from 585ms to 204ms and nobody did. The free
  // wait went with it, exactly as predicted, and the reads started landing
  // mid-transition: TEN OF THE TWENTY-EIGHT SAMPLES in the first five-map
  // competitive run needed a second look, which is the loop noticing a bad
  // frame and paying for another grab to replace it.
  //
  // 400ms costs about 2s a map and buys back most of those retakes, each of
  // which was a grab of its own. Worth re-measuring with probe_limits.js if the
  // grab time moves again - in either direction.
  //
  // Menus still get the two-frame settle, because a half-drawn panel is
  // measured and then believed; a half-drawn HUD only scores badly, and the
  // sample loop re-reads when it does.
  var QUIESCE_MS = 400;

  // Shorter than this, a stretch of play is the assemble phase rather than a
  // round. Every map measured opens with one.
  var MIN_PLAY_S = 30;

  // Mean absolute difference above which two frames are a moving picture rather
  // than the same still one. A settled screen sits under 0.6; a playing replay
  // is far above this.
  var MOTION_DIFF = 1.5;

  // How long to let the client finish loading before giving up on a frame.
  var LOAD_TRIES = 12;
  var LOAD_WAIT_MS = 400;

  var mmss = function (s) {
    return Math.floor(s / 60) + ':' + String(Math.round(s % 60)).padStart(2, '0');
  };

  // Mean absolute difference over the play area. The control bar animates on
  // its own, so it is excluded - otherwise the screen would never read as
  // settled.
  async function pixelDiff(pa, pb) {
    var a = await pixels(pa);
    var b = await pixels(pb);
    var sum = 0, n = 0;
    for (var y = 200; y < 1100; y += 8) {
      for (var x = 0; x < a.img.width; x += 8) {
        var i = (y * a.img.width + x) * 4;
        sum += Math.abs(a.data[i] - b.data[i]) +
          Math.abs(a.data[i + 1] - b.data[i + 1]) +
          Math.abs(a.data[i + 2] - b.data[i + 2]);
        n += 3;
      }
    }
    return sum / n;
  }

  async function pixels(p) {
    var img = await canvas.loadImage(p);
    var cv = canvas.createCanvas(img.width, img.height);
    cv.getContext('2d').drawImage(img, 0, 0);
    return { img: img, data: cv.getContext('2d').getImageData(0, 0, img.width, img.height).data };
  }

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
        await realSleep(ms === undefined ? QUIESCE_MS : ms);
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

  // Waiting is something that touches the machine too, so it comes out of the
  // injected io like every other machine-touching thing. Offline, the harness
  // counts the waits instead of serving them, which is the difference between
  // a run that costs a second and one that costs a minute for no reason.
  function napOf(io) { return (io && io.sleep) || realSleep; }

  // Is the replay moving, and stop it if it is.
  //
  // THIS IS WORTH A MINUTE A MAP. A replay opens PLAYING, and settling is
  // defined as two consecutive frames agreeing - which never happens while the
  // picture is moving. Every settle before the first pause ran its full retries
  // and gave up, about seven seconds each, for N, for K, and for both
  // calibration presses. The bot looked like it was doing nothing because it
  // was: proving, four times over, that a playing replay does not hold still.
  //
  // MOTION IS MEASURED ON THE PICTURE, not on the playhead. Two frames a
  // quarter-second apart differ enormously while a replay plays and barely at
  // all when it is stopped, so the signal is huge and the test is quick. The
  // playhead would work too, but it moves slowly - under two pixels a second on
  // a long map - so it needs a second of waiting to say anything, and it cannot
  // say anything at all before the media controls are up.
  //
  // SPACE is a toggle, so this measures first and presses only if it must.
  async function ensurePaused(io, drv) {
    var sleep = napOf(io);
    async function moving() {
      var a = await io.grabTo('pause');
      await sleep(250);
      var b = await io.grabTo('pause');
      return await pixelDiff(a, b) > MOTION_DIFF;
    }

    if (!await moving()) return { known: true, paused: true, pressed: false };
    await drv.pause();
    await sleep(400);
    return { known: true, paused: !await moving(), pressed: true };
  }

  // A frame with the replay actually on screen.
  //
  // A LOADING SCREEN IS BLACK, PERFECTLY STILL, AND SETTLES BEAUTIFULLY. That
  // is the worst possible input: every readiness test built so far - two frames
  // agreeing, waiting a fixed time, the picture not moving - says a loading
  // screen is ready, and the matcher then scores hero templates against black
  // and returns 0.29 to 0.63 with no sign anything is wrong. It happened three
  // ways in one run: two samples of a map read as nonsense, and another map
  // died calibrating because the bar was not there.
  //
  // The media controls are absent while the client loads, so the playhead is
  // the signal. No playhead means WAIT, not read, and not fail.
  async function readyFrame(io, first) {
    var sleep = napOf(io);
    var p = first || await io.grabTo('ready');
    for (var i = 0; i < LOAD_TRIES; i++) {
      var img = await io.loadImage(p);
      // The HUD, not the playhead: the media controls hide themselves, and a
      // frame with the portraits drawn is exactly what a sample needs.
      if (calib.hudPresent(Crop.hudTint(img, calib))) return { path: p, img: img };
      await sleep(LOAD_WAIT_MS);
      p = await io.grabTo('ready');
    }
    return null;
  }

  // The same wait, for the bar rather than the HUD. Calibration needs the
  // playhead specifically, and by then N has been pressed so it should be up.
  async function barFrame(io, first) {
    var sleep = napOf(io);
    var p = first || await io.grabTo('bar');
    for (var i = 0; i < LOAD_TRIES; i++) {
      var img = await io.loadImage(p);
      if (Crop.playheadX(img, calib)) return { path: p, img: img };
      await sleep(LOAD_WAIT_MS);
      p = await io.grabTo('bar');
    }
    return null;
  }

  // Pixels per second of playback, by playing the replay and watching the knob.
  //
  // SPACE is a toggle like every other control here, so whether the replay is
  // already playing is measured rather than assumed - two reads a beat apart,
  // and a press only if nothing moved.
  async function measureRate(io, drv) {
    var sleep = napOf(io);
    async function knob(tag) {
      var k = Crop.playheadX(await io.loadImage(await io.grabTo(tag)), calib);
      if (!k) throw new Error('lost the playhead while timing playback');
      return k.centre;
    }

    var a = await knob('rate');
    await sleep(1200);
    var b = await knob('rate');
    var pressed = false;
    if (b === a) {
      await drv.pause();               // SPACE - start it playing
      pressed = true;
      await sleep(600);
      a = await knob('rate');
      await sleep(1200);
      b = await knob('rate');
      if (b === a) throw new Error('the replay will not play, so a press cannot be timed');
    }

    var from = b;
    var t0 = Date.now();
    await sleep(6000);
    var to = await knob('rate');
    var elapsed = (Date.now() - t0) / 1000;

    // Leave it as it was found: paused, so nothing drifts under the sampling.
    if (!pressed) await drv.pause();
    await io.settle();

    return { pxPerSec: (to - from) / elapsed, elapsed: elapsed };
  }

  // The least confident cell of a read, which is what says whether a frame was
  // caught mid-transition.
  function worstOf(read) {
    var worst = 1;
    ['a', 'b'].forEach(function (side) {
      read[side].forEach(function (r) { if (r.score < worst) worst = r.score; });
    });
    return worst;
  }

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

      var M = o.matcher || Match.make(require(
        path.join(__dirname, '../../docs/capture/refs.json')), { PAD: calib.FROZEN.ref.PAD });

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
      // measured as a brightness and then believed. Sampling gets the cheap
      // one, because a half-drawn HUD announces itself in the scores.
      var sampling = false;
      var drvCtx = {
        sendKeys: io.sendKeys,
        focus: async function () {},
        settle: function () { return sampling ? io.quiesce() : io.settle(); },
        position: positionNow,
        stepS: stepS,
      };
      var drv = D.make(drvCtx);

      // 1. A frame, and the guard that the HUD is where it was frozen.
      var img0 = await io.loadImage(await io.grabTo('timeline'));
      var chk = calib.check({ w: img0.width, h: img0.height });
      if (!chk.ok) throw new Error('calibration smoke check failed: ' + chk.reason);

      // 1b. Stop the replay before anything waits for the screen to be still.
      //     The media controls may not be up yet, in which case this cannot see
      //     the playhead and the attempt is repeated after step 2.
      mark('first frame');
      var stopped = await ensurePaused(io, drv);
      log('replay ' + (stopped.pressed ? 'was playing, paused it' : 'already paused'));
      if (!stopped.paused) {
        throw new Error('the replay will not stop - every read after this would ' +
          'be of a moving picture');
      }

      mark('pause check');

      // 2. The events viewer, without which the bar shows no round breaks.
      //
      //    N then K, in that order and every time: the media controls have to
      //    be up before the events viewer will open. A run that pressed only K
      //    sat at 0.023 before and after, having done nothing.
      //
      // DIAGNOSTIC LOGGING BELOW, added 2026-09-10 after two live failures
      // ("K did not open the panel") that could not be reverse-engineered from
      // the frames alone - ruled out "still in the assemble phase" (K also
      // failed well into live round-1 gameplay in one manual repro) and found
      // Crop.playheadX can false-positive on a bright background element at
      // the scrubber's own pixel band (measured a 495px run on one map, where
      // a real knob is ~40px - see specs/2026-09-10-replay-bot-player-attribution-design.md's
      // sibling investigation notes). This logs the raw playhead run (width
      // tells a real knob from a false positive) and the panel reading at
      // every step, so the next live occurrence is diagnosable from the log
      // alone rather than needing frames reconstructed after the fact.
      var t0Viewer = Date.now();
      function logPlayheadState(step) {
        var knob = Crop.playheadX(img0, calib);
        log('    [diag +' + (Date.now() - t0Viewer) + 'ms] ' + step + ': playhead=' +
          (knob ? ('x' + knob.x0 + '-' + knob.x1 + ' w' + knob.width) : 'none'));
      }
      var viewer = await D.ensureEventsViewer({
        read: async function () {
          img0 = await io.loadImage(await io.grabTo('panel'));
          var rows = Crop.panelRowFraction(img0, calib);
          log('    [diag +' + (Date.now() - t0Viewer) + 'ms] read: panelRows=' + rows.toFixed(3));
          return rows;
        },
        isOpen: calib.eventsViewerOpen,
        // The playhead is drawn only while the media controls are up, so it
        // doubles as the check that N went the right way.
        mediaVisible: async function () {
          logPlayheadState('mediaVisible check');
          return !!Crop.playheadX(img0, calib);
        },
        showMedia: async function () {
          await drv.mediaControls();
          img0 = await io.loadImage(io.lastFrame());
          logPlayheadState('after N');
        },
        toggle: async function () {
          await drv.eventsViewer();
          img0 = await io.loadImage(io.lastFrame());
          logPlayheadState('after K');
        },
      });
      log('events viewer ' + (viewer.open ? 'open' : 'CLOSED') +
        ' (panel rows ' + (viewer.after === null ? '?' : viewer.after.toFixed(3)) +
        (viewer.steps.length ? ', pressed ' + viewer.steps.join(' then ') : ', untouched') + ')');
      if (!viewer.open) {
        throw new Error('events viewer would not open' +
          (viewer.reason ? ' - ' + viewer.reason : '') +
          ' - the scrubber shows no round breaks without it, so the timeline ' +
          'read would be wrong');
      }

      mark('events viewer');

      // 2b. Anything that needs the controls up but must happen before the
      //     measuring starts - in practice, the once-a-session trip to set the
      //     skip interval to 60s. The options button only exists once N and K
      //     have put the controls on screen, and the interval has to change
      //     BEFORE the step is measured, or the run caches the old one.
      if (o.afterViewer) {
        await o.afterViewer();

        // A trip through a menu can leave the panel shut, so it is looked at
        // again rather than assumed.
        //
        // THIS USED TO COMPARE A ROW FRACTION AGAINST A BRIGHTNESS FRACTION.
        // It was a rise test from the brightness era - a drop from a reading
        // known to be open - and when the reading became structural the two
        // sides of the subtraction stopped being the same quantity. Nothing
        // said so: on one map it would never reopen a shut panel, and on
        // another it would press K on an open one and shut it. Asking whether
        // the panel is open is now simply a question worth asking, the same
        // way driver.ensureEventsViewer stopped dancing around it.
        img0 = await io.loadImage(await io.grabTo('timeline'));
        if (!calib.eventsViewerOpen(Crop.panelRowFraction(img0, calib))) {
          log('the events panel closed while the menu was open - reopening');
          await drv.eventsViewer();
          img0 = await io.loadImage(await io.grabTo('timeline'));
          if (!calib.eventsViewerOpen(Crop.panelRowFraction(img0, calib))) {
            throw new Error('the events panel would not reopen after the options ' +
              'menu, so the scrubber shows no round breaks');
          }
        }
        if (!Crop.playheadX(img0, calib)) {
          throw new Error('the media controls are gone after the options menu, ' +
            'so there is no bar to read');
        }
      }

      mark('interval chunk');

      // 3. The bar's scale, measured on this map by moving it and looking.
      await io.sendKeys([D.KEY.jumpToStart]);
      await io.settle();
      var zeroFrame = await barFrame(io, io.lastFrame());
      await io.sendKeys([D.KEY.forward]);
      await io.settle();
      var oneFrame = await barFrame(io, io.lastFrame());
      if (!zeroFrame || !oneFrame) {
        throw new Error('the bar never appeared - the replay is still loading, or ' +
          'the media controls are down');
      }
      var atZero = Crop.playheadX(zeroFrame.img, calib);
      var atOne = Crop.playheadX(oneFrame.img, calib);

      ref = { zeroX: atZero.centre, stepPx: atOne.centre - atZero.centre, stepS: stepS };
      if (ref.stepPx <= 0) {
        throw new Error('one press moved ' + ref.stepPx + 'px - the forward key is not working');
      }

      // 3b. How many SECONDS is one press? Measured, never read off the setting.
      //
      //     The client's time-skip interval is a known Blizzard bug: replay
      //     viewer options apply while the client runs and revert to defaults
      //     at the next start. An interval set to 60 last night is 20 tonight,
      //     and nothing on screen says which. Assuming 20 when it is really 60
      //     would put every sample at a third of its intended time - in the
      //     wrong round, with an entirely plausible-looking result.
      //
      //     So the replay itself is the ruler: play it for a few seconds and
      //     watch the knob. That gives pixels per second, and the step divided
      //     by it is the interval. It costs about eight seconds a map and pays
      //     for itself many times over whenever the interval really is 60.
      var pxPerSec = null;
      if (!o.stepS) {
        var rate = await measureRate(io, drv);
        pxPerSec = rate.pxPerSec;
        var derived = T.stepSecondsFrom(ref.stepPx, pxPerSec, {});
        if (!derived.ok) throw new Error(derived.reason);
        stepS = derived.stepS;
        ref.stepS = stepS;
        drvCtx.stepS = stepS;
        log('playback ' + pxPerSec.toFixed(2) + 'px/s, one press = ' +
          derived.raw.toFixed(1) + 's -> taken as ' + stepS + 's');
      }

      mark('bar calibration');
      drv.reset();

      var bar = calib.FROZEN.timeline;
      var span = bar.x1 - bar.x0 + 1 - atZero.width;
      // With a measured playback rate the duration is a measurement too, rather
      // than the bar span divided by an assumed step.
      var implied = Math.round(pxPerSec ? span / pxPerSec : (span / ref.stepPx) * ref.stepS);
      var duration = told || implied;
      log('one step = ' + ref.stepPx.toFixed(1) + 'px (' + stepS + 's), zero at ' + ref.zeroX);
      log('duration ' + mmss(duration) + ' (' + (told ? 'given' : 'measured off the bar') +
        (told ? ', bar implies ' + mmss(implied) : '') + ')');

      // 4. Round structure, and where to sample inside it.
      var segs = T.dropShortPlay(T.segments(Crop.barFlags(img0, calib), {
        duration: duration,
        minRun: calib.FROZEN.timeline.minRunPx,
      }), MIN_PLAY_S);
      segs.forEach(function (sg) {
        log('  ' + (sg.play ? 'PLAY ' : sg.tooShort ? 'setup' : 'BREAK') +
          '  ' + mmss(sg.from) + ' - ' + mmss(sg.to));
      });

      var per = T.samplesFor(segs);
      var plan = T.plan(segs, per, { stepS: stepS });
      log('');
      log(per + ' samples per round -> ' + plan.length + ' grabs: ' +
        plan.map(mmss).join(', '));

      // 5. Drive to each sample and read the HUD.
      async function readHud(framePath) {
        var img = await io.loadImage(framePath);
        var crops = Crop.all(img, calib);
        var out = { a: [], b: [] };
        ['a', 'b'].forEach(function (side) {
          out[side] = crops[side].map(function (c) { return M.match(c, side); });
        });
        return out;
      }

      var samples = [];
      var missed = [];
      sampling = true;
      for (var i = 0; i < plan.length; i++) {
        var t = plan[i];
        var started = Date.now();
        var at = await drv.seekTo(t);

        // A seek that could not be corrected is a sample somewhere else. The
        // measurement wins: drop it rather than label a frame with a time it
        // was never at.
        if (Math.abs(at - t) >= stepS / 2) {
          missed.push({ t: t, at: at });
          log(mmss(t).padStart(6) + '  MISSED - landed at ' + mmss(at) + ', dropped');
          continue;
        }

        // The frame the seek left behind IS the sample - unless the client is
        // still loading, in which case it is black and would read as ten heroes
        // that are not there.
        var ready = await readyFrame(io, io.lastFrame());
        if (!ready) {
          missed.push({ t: t, at: at, reason: 'still loading' });
          log(mmss(t).padStart(6) + '  NOT LOADED - dropped');
          continue;
        }
        var framePath = io.keepAs ? await io.keepAs('t' + t, ready.path) : ready.path;
        var read = await readHud(framePath);

        // ONE SECOND LOOK IF IT LOOKS WRONG. A frame caught while the HUD is
        // still sliding into place scores badly, and that is cheaper to detect
        // than to prevent: the alternative was a two-frame settle before every
        // sample, paying a second each time to avoid a case that is rare.
        if (worstOf(read) < LOW_SCORE) {
          var retry = await readHud(await io.grabTo('t' + t + '-again'));
          if (worstOf(retry) > worstOf(read)) {
            log('        (first read was mid-transition, took a second look)');
            read = retry;
          }
        }
        samples.push({ t: t, at: at, a: read.a, b: read.b, framePath: framePath });

        log(mmss(t).padStart(6) + '  (' + ((Date.now() - started) / 1000).toFixed(1) + 's)');
        ['a', 'b'].forEach(function (side) {
          log('        ' + side + ': ' + read[side].map(function (r) {
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

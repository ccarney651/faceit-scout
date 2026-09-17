// tools/replay_bot/phases.js
// The stages of capturing one already-open replay, each callable on its own.
// See ARCHITECTURE.md §14.
//
// capture.js's captureMap was one 300-line function doing four jobs: raising
// the events viewer, calibrating the bar against this map, reading the round
// structure off the scrubber, and driving to each sample. The console
// (tools/replay_bot/console/) needs to run any one of those alone - to watch it,
// time it, retry it with a different wait - so they live here as units, and
// captureMap is a short sequence over them.
//
// THE SEAMS ARE THE SAME ONES captureMap ALWAYS USED. Every function here takes
// the injected `io` (capture.js's makeIo, or fakeio) and a `drv` (driver.js),
// so the offline corpus exercises this code unchanged. `ctx` is
// `{ io, drv, log }`; a phase that needs more takes it as a second argument.

(function (global) {
  'use strict';

  var path = require('path');
  var canvas = require('@napi-rs/canvas');
  var calib = require('./calib.js');
  var Crop = require('./crop.js');
  var Nameplate = require('./nameplate.js');
  var Match = require('./match.js');
  var T = require('./timeline.js');
  var D = require('./driver.js');
  var TIMING = require('./timing.js');

  // Mean absolute difference above which two frames are a moving picture rather
  // than the same still one. A settled screen sits under 0.6; a playing replay
  // is far above this.
  var MOTION_DIFF = 1.5;

  // Shorter than this, a stretch of play is the assemble phase rather than a
  // round. Every map measured opens with one.
  var MIN_PLAY_S = 30;

  // Below this a match is a suggestion, not a reading - a doubtful cell the
  // sample loop re-reads and downstream vote.js can see rather than average away.
  var LOW_SCORE = 0.6;

  var realSleep = function (ms) { return new Promise(function (r) { setTimeout(r, ms); }); };

  // Waiting touches the machine too, so it comes out of the injected io like
  // every other machine-touching thing. Offline the harness counts the waits
  // instead of serving them.
  function napOf(io) { return (io && io.sleep) || realSleep; }

  function makeMatcher() {
    return Match.make(
      require(path.join(__dirname, '../../docs/capture/refs.json')),
      { PAD: calib.FROZEN.ref.PAD });
  }

  // ---- frame math --------------------------------------------------------

  async function pixels(p) {
    var img = await canvas.loadImage(p);
    var cv = canvas.createCanvas(img.width, img.height);
    cv.getContext('2d').drawImage(img, 0, 0);
    return { img: img, data: cv.getContext('2d').getImageData(0, 0, img.width, img.height).data };
  }

  // Mean absolute difference over the play area. The control bar animates on its
  // own, so it is excluded - otherwise the screen would never read as settled.
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

  // The least confident cell of a read, which is what says whether a frame was
  // caught mid-transition.
  function worstOf(read) {
    var worst = 1;
    ['a', 'b'].forEach(function (side) {
      read[side].forEach(function (r) { if (r.score < worst) worst = r.score; });
    });
    return worst;
  }

  // ---- waits on the client ----------------------------------------------

  // Is the replay moving, and stop it if it is.
  //
  // THIS IS WORTH A MINUTE A MAP. A replay opens PLAYING, and settling is two
  // consecutive frames agreeing - which never happens while the picture moves.
  // Motion is measured on the PICTURE, not the playhead: two frames a
  // quarter-second apart differ enormously while a replay plays and barely at
  // all when it is stopped. SPACE is a toggle, so this measures first and
  // presses only if it must.
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
  // A LOADING SCREEN IS BLACK, PERFECTLY STILL, AND SETTLES BEAUTIFULLY - the
  // worst possible input, because every readiness test says it is ready and the
  // matcher then scores hero templates against black and returns 0.29-0.63 with
  // no sign anything is wrong. The HUD being drawn is the signal; no HUD means
  // WAIT, not read, and not fail.
  async function readyFrame(io, first) {
    var sleep = napOf(io);
    var p = first || await io.grabTo('ready');
    for (var i = 0; i < TIMING.load.tries; i++) {
      var img = await io.loadImage(p);
      if (calib.hudPresent(Crop.hudTint(img, calib))) return { path: p, img: img };
      await sleep(TIMING.load.waitMs);
      p = await io.grabTo('ready');
    }
    return null;
  }

  // The same wait, for the bar rather than the HUD. Calibration needs the
  // playhead specifically, and by then N has been pressed so it should be up.
  async function barFrame(io, first) {
    var sleep = napOf(io);
    var p = first || await io.grabTo('bar');
    for (var i = 0; i < TIMING.load.tries; i++) {
      var img = await io.loadImage(p);
      if (Crop.playheadX(img, calib)) return { path: p, img: img };
      await sleep(TIMING.load.waitMs);
      p = await io.grabTo('bar');
    }
    return null;
  }

  // Pixels per second of playback, by playing the replay and watching the knob.
  // SPACE is a toggle, so whether it is already playing is measured, not assumed.
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

  // ---- the composite phases --------------------------------------------

  // 2. Raise the events viewer, without which the scrubber shows no round
  //    breaks - closed, a three-round Control map reads as one continuous
  //    segment, confidently and wrongly.
  //
  //    N then K, in that order and every time: the media controls have to be up
  //    before the events viewer will open (a run that pressed only K sat at
  //    0.023 before and after). The diagnostic logging below was added
  //    2026-09-10 after two live "K did not open the panel" failures that could
  //    not be reverse-engineered from the frames: Crop.playheadX can
  //    false-positive on a bright background element at the scrubber's own pixel
  //    band, so this logs the raw playhead run (width tells a real ~40px knob
  //    from a 495px false positive) and the panel reading at every step.
  //
  // Throws with captureMap's message if it will not open. Returns
  // { open, steps, after, img0 } - img0 is the last frame, for readStructure.
  async function openEventsViewer(ctx) {
    var io = ctx.io, drv = ctx.drv, log = ctx.log || function () {};
    var img0 = await io.loadImage(await io.grabTo('panel'));
    var t0 = Date.now();
    function logPlayheadState(step) {
      var knob = Crop.playheadX(img0, calib);
      log('    [diag +' + (Date.now() - t0) + 'ms] ' + step + ': playhead=' +
        (knob ? ('x' + knob.x0 + '-' + knob.x1 + ' w' + knob.width) : 'none'));
    }

    var viewer = await D.ensureEventsViewer({
      read: async function () {
        img0 = await io.loadImage(await io.grabTo('panel'));
        var rows = Crop.panelRowFraction(img0, calib);
        log('    [diag +' + (Date.now() - t0) + 'ms] read: panelRows=' + rows.toFixed(3));
        return rows;
      },
      isOpen: calib.eventsViewerOpen,
      mediaVisible: async function () {
        for (var i = 0; i < TIMING.media.tries; i++) {
          await io.sleep(TIMING.media.waitMs);
          img0 = await io.loadImage(await io.grabTo('media-check'));
          logPlayheadState('mediaVisible check');
          if (Crop.playheadX(img0, calib)) return true;
        }
        return false;
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
    return { open: true, steps: viewer.steps, after: viewer.after, img0: img0 };
  }

  // 2b. A trip through the options menu (the once-a-session skip-interval chunk)
  //     can leave the events panel shut behind it. Asking whether it is open is
  //     simply a question worth asking - this used to compare a row fraction
  //     against a brightness fraction, two different units against one
  //     threshold, and could as easily press K on an open panel and shut it.
  //     Returns { img0 }.
  async function ensurePanelOpen(ctx) {
    var io = ctx.io, drv = ctx.drv, log = ctx.log || function () {};
    var img0 = await io.loadImage(await io.grabTo('timeline'));
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
    return { img0: img0 };
  }

  // 3. The bar's scale, measured on this map by moving it and looking: jump to
  //    start, read the playhead, press forward once, read it again. A 20-second
  //    step was 45px on one map and 69px on another, so nothing is assumed.
  //
  //    3b. How many SECONDS is one press is MEASURED, never read off the
  //    setting - the client's time-skip interval is a Blizzard bug that reverts
  //    at every restart, so assuming 20 when it is really 60 puts every sample
  //    at a third of its time, in the wrong round, looking reasonable.
  //
  // opts: { stepS?, log }. stepS given skips the timed-playback measurement.
  // Returns { ref, stepS, pxPerSec, atZero } (atZero carries the knob width the
  // duration calc needs).
  async function calibrateBar(ctx, opts) {
    var io = ctx.io, drv = ctx.drv;
    var o = opts || {};
    var log = o.log || function () {};
    var stepS = o.stepS || 20;

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

    var ref = { zeroX: atZero.centre, stepPx: atOne.centre - atZero.centre, stepS: stepS };
    if (ref.stepPx <= 0) {
      throw new Error('one press moved ' + ref.stepPx + 'px - the forward key is not working');
    }

    var pxPerSec = null;
    if (!o.stepS) {
      var rate = await measureRate(io, drv);
      pxPerSec = rate.pxPerSec;
      var derived = T.stepSecondsFrom(ref.stepPx, pxPerSec, {});
      if (!derived.ok) throw new Error(derived.reason);
      stepS = derived.stepS;
      ref.stepS = stepS;
      log('playback ' + pxPerSec.toFixed(2) + 'px/s, one press = ' +
        derived.raw.toFixed(1) + 's -> taken as ' + stepS + 's');
    }
    drv.reset();
    return { ref: ref, stepS: stepS, pxPerSec: pxPerSec, atZero: atZero };
  }

  // The map's duration, in seconds. Measured off the bar span (with a measured
  // playback rate it is a measurement too), unless the caller was told one.
  function deriveDuration(o) {
    var bar = calib.FROZEN.timeline;
    var span = bar.x1 - bar.x0 + 1 - o.atZeroWidth;
    var implied = Math.round(o.pxPerSec
      ? span / o.pxPerSec
      : (span / o.ref.stepPx) * o.ref.stepS);
    return { duration: o.told || implied, implied: implied };
  }

  // 4. Round structure off the scrubber, and where to sample inside it.
  //    Returns { segments, per, plan }.
  function readStructure(img0, o) {
    var log = o.log || function () {};
    var mmss = o.mmss || function (s) { return String(s); };
    var segs = T.dropShortPlay(T.segments(Crop.barFlags(img0, calib), {
      duration: o.duration,
      minRun: calib.FROZEN.timeline.minRunPx,
    }), MIN_PLAY_S);
    segs.forEach(function (sg) {
      log('  ' + (sg.play ? 'PLAY ' : sg.tooShort ? 'setup' : 'BREAK') +
        '  ' + mmss(sg.from) + ' - ' + mmss(sg.to));
    });
    var plan = T.planGrid(segs, { stepS: o.stepS });
    log('');
    log('every ' + o.stepS + 's inside play -> ' + plan.length + ' grabs: ' +
      plan.map(mmss).join(', '));
    return { segments: segs, per: plan.length, plan: plan };
  }

  // A disconnected player's card is gone from the HUD outright, not a
  // portrait of the wrong hero - the cell shows whatever the 3D scene behind
  // it looks like. Matching that against the hero library is pointless (it
  // is not a hero) and risky (scenery does not reliably score below every
  // real hero's floor the way a genuine misread does). resolve.js's
  // resolveSlot special-cases this exact string; see its ABSENT_GUID.
  var ABSENT_GUID = 'ABSENT';

  // A dead-but-present player's whole card desaturates - badge included, not
  // just the portrait - so cellTint alone reads it exactly like a real
  // disconnect (confirmed on real captures 2026-09-17: P1PXQK, H5Q9WE; "the
  // X means a player is dead" - operator). crop.cellDeath looks for the red
  // elimination X a death always draws and a real disconnect never does.
  // Distinct from ABSENT_GUID so resolve.js can tell "no evidence this
  // sample" (dead - the hero doesn't actually change) from "this player
  // left" (a genuine leaver).
  var DEAD_GUID = 'DEAD';

  // Match the ten HUD cells of one frame. `matcher` is a makeMatcher() result
  // or anything with .match(crop, side). A cell whose own tint fails
  // calib.cellPresent (crop.cellTint) never reaches the matcher at all - see
  // ABSENT_GUID/DEAD_GUID above.
  async function readHud(io, matcher, framePath) {
    var img = await io.loadImage(framePath);
    var crops = Crop.all(img, calib);
    var tint = Crop.cellTint(img, calib);
    var dead = Crop.cellDeath(img, calib);
    var out = { a: [], b: [] };
    ['a', 'b'].forEach(function (side) {
      out[side] = crops[side].map(function (c, i) {
        if (!calib.cellPresent(tint[side][i])) {
          return { score: null, name: null, guid: dead[side][i] ? DEAD_GUID : ABSENT_GUID };
        }
        return matcher.match(c, side);
      });
    });
    return out;
  }

  // Per-sample name-OCR read - mirrors readHud's shape but returns raw text,
  // not a hero match. Reuses Nameplate.nameRow/nameCrop exactly as
  // attribute.js's (soon-to-be-former) attributeMap did internally - see
  // specs/2026-09-17-replay-bot-disconnect-identity-design.md §4. Kept
  // separate from readHud (a different concern: text, not hero portraits),
  // called alongside it from sampleAt.
  var BLANK_NAMES = ['', '', '', '', ''];
  async function readNames(io, ocr, framePath) {
    var img = await io.loadImage(framePath);
    var out = { a: BLANK_NAMES.slice(), b: BLANK_NAMES.slice() };
    var sides = ['a', 'b'];
    for (var s = 0; s < sides.length; s++) {
      var side = sides[s];
      var row = Nameplate.nameRow(img, calib.FROZEN.boxes[side]);
      if (!row) continue;
      var slotCells = calib.slots(side);
      var got = [];
      for (var i = 0; i < slotCells.length; i++) {
        got.push(await ocr(Nameplate.nameCrop(img, slotCells[i], row)));
      }
      out[side] = got;
    }
    return out;
  }

  // Should this sample's frame be kept? Read-before-keep: a frame earns its
  // keep by differing from the previous one, because storage is bounded by
  // distinct comp states, not by how often we visit. A keep fires when ANY of:
  //
  //  - any slot's guid changed since the previous sample - the hero set moved;
  //  - any slot reads below LOW_SCORE - this frame is not confidently identical
  //    to the last one, and may be the transition evidence;
  //  - the previous sample disagreed with the one before it - a swap or
  //    transition is in progress and needs every frame it can get.
  //
  // The first sample of a round is always kept: it is the round's baseline
  // comp, and review_out.js derives its portrait strips from it.
  function shouldKeep(read, prev, prevPrev, firstOfRound) {
    if (firstOfRound || !prev) return true;
    var sides = ['a', 'b'];
    for (var s = 0; s < sides.length; s++) {
      var side = sides[s];
      for (var i = 0; i < read[side].length; i++) {
        var r = read[side][i];
        var p = prev[side] && prev[side][i];
        if (r && p && r.guid && p.guid && r.guid !== p.guid) return true;
        if (r && r.score !== undefined && r.score < LOW_SCORE) return true;
      }
    }
    if (!prevPrev) return false;
    for (var s2 = 0; s2 < sides.length; s2++) {
      var side2 = sides[s2];
      for (var i2 = 0; i2 < prev[side2].length; i2++) {
        var pr = prev[side2][i2];
        var pp = prevPrev[side2] && prevPrev[side2][i2];
        if (pr && pp && pr.guid && pp.guid && pr.guid !== pp.guid) return true;
      }
    }
    return false;
  }

  // 5. Drive to one sample time and read the HUD there. `drv` is expected to be
  //    already configured for sampling (its settle is the fixed quiesce, not the
  //    two-frame one). opts: { matcher, stepS, prev?, prevPrev?, firstOfRound?,
  //    mmss?, log? }.
  //
  //    READ BEFORE KEEP: the read comes first, and keepAs fires only on change
  //    (see shouldKeep), so an unchanged round stores one frame a round and a
  //    swap stores one frame per distinct state. Without `prev` (a one-off
  //    console sample, or the first visit of a map) the frame is always kept.
  //
  //    Returns { t, at, a, b, framePath, worst } on success, or
  //    { t, at, missed: true, reason } when the seek could not be corrected or
  //    the client is still loading - the measurement wins, a misplaced frame is
  //    dropped rather than labelled with a time it was never at.
  async function sampleAt(ctx, t, opts) {
    var io = ctx.io, drv = ctx.drv;
    var o = opts || {};
    var log = o.log || function () {};
    var mmss = o.mmss || function (s) { return String(s); };
    var stepS = o.stepS || 20;

    var at = await drv.seekTo(t);
    if (Math.abs(at - t) >= stepS / 2) {
      log(mmss(t).padStart(6) + '  MISSED - landed at ' + mmss(at) + ', dropped');
      return { t: t, at: at, missed: true, reason: 'seek' };
    }

    // The frame the seek left behind IS the sample - the settle inside
    // driver.seekTo already paused for the portrait band to draw and left it in
    // io.lastFrame() - unless the client is still loading, in which case it is
    // black and would read as ten heroes that are not there.
    var ready = await readyFrame(io, io.lastFrame());
    if (!ready) {
      log(mmss(t).padStart(6) + '  NOT LOADED - dropped');
      return { t: t, at: at, missed: true, reason: 'still loading' };
    }

    var framePath = ready.path;
    var read = await readHud(io, o.matcher, framePath);

    // KEEP LOOKING WHILE IT LOOKS WRONG, WITHIN A BUDGET. A frame caught
    // mid-transition scores badly, and that is cheaper to detect than to
    // prevent - but scrub-to-legible latency varies with connection/disk/
    // scrub distance (specs/[[replay-scrubbing-timing-variance]]), so a
    // single blind extra look is sometimes not enough. Polls on a short
    // interval until the read clears LOW_SCORE or the budget runs out,
    // keeping whichever read scored best across every attempt - runs BEFORE
    // the keep decision, so a read that recovers is compared on its values
    // and its frame is what a change would keep.
    var settleStepMs = o.settleStepMs != null ? o.settleStepMs : TIMING.sample.settleStepMs;
    var settleMaxMs = o.settleMaxMs != null ? o.settleMaxMs : TIMING.sample.settleMaxMs;
    var settleDeadline = Date.now() + settleMaxMs;
    var extraLooks = 0;
    while (worstOf(read) < LOW_SCORE && Date.now() < settleDeadline) {
      await realSleep(settleStepMs);
      extraLooks++;
      var tryPath = await io.grabTo('t' + t + '-again');
      var tryRead = await readHud(io, o.matcher, tryPath);
      if (worstOf(tryRead) > worstOf(read)) {
        read = tryRead;
        framePath = tryPath;
      }
    }
    if (extraLooks === 1 && worstOf(read) >= LOW_SCORE) {
      log('        (first read was mid-transition, took a second look)');
    } else if (extraLooks > 1 && worstOf(read) >= LOW_SCORE) {
      log('        (first read was mid-transition, took ' + extraLooks + ' extra looks to settle)');
    } else if (extraLooks > 0) {
      log('        (warning: never settled after ' + extraLooks +
        ' extra look' + (extraLooks === 1 ? '' : 's') + ')');
    }

    // Names are read from whichever frame the retry logic above settled on,
    // the same frame the hero read came from - never a second, different
    // grab. Optional: a caller that doesn't pass ocr (existing tests, any
    // path that doesn't need identity) gets blanks, never a crash. See
    // specs/2026-09-17-replay-bot-disconnect-identity-design.md.
    var names = o.ocr ? await readNames(io, o.ocr, framePath) : { a: BLANK_NAMES.slice(), b: BLANK_NAMES.slice() };

    if (shouldKeep(read, o.prev, o.prevPrev, o.firstOfRound)) {
      framePath = io.keepAs ? await io.keepAs('t' + t, framePath) : framePath;
    } else {
      log(mmss(t).padStart(6) + '  unchanged - not kept');
      framePath = null;
    }
    return { t: t, at: at, a: read.a, b: read.b, names: names, framePath: framePath, worst: worstOf(read) };
  }

  var Mod = {
    MOTION_DIFF: MOTION_DIFF,
    MIN_PLAY_S: MIN_PLAY_S,
    LOW_SCORE: LOW_SCORE,
    napOf: napOf,
    realSleep: realSleep,
    makeMatcher: makeMatcher,
    pixels: pixels,
    pixelDiff: pixelDiff,
    worstOf: worstOf,
    ensurePaused: ensurePaused,
    readyFrame: readyFrame,
    barFrame: barFrame,
    measureRate: measureRate,
    openEventsViewer: openEventsViewer,
    ensurePanelOpen: ensurePanelOpen,
    calibrateBar: calibrateBar,
    deriveDuration: deriveDuration,
    readStructure: readStructure,
    readHud: readHud,
    readNames: readNames,
    ABSENT_GUID: ABSENT_GUID,
    DEAD_GUID: DEAD_GUID,
    shouldKeep: shouldKeep,
    sampleAt: sampleAt,
  };

  if (typeof module !== 'undefined' && module.exports) module.exports = Mod;
  else global.OWDBReplayPhases = Mod;
})(typeof self !== 'undefined' ? self : this);

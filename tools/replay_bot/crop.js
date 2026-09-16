// tools/replay_bot/crop.js
// Turning a region of a captured frame into the 64x36 greyscale buffer the
// hero matcher compares against. See specs/2026-09-08-replay-bot-design.md §3.1.
//
// THIS FILE DELIBERATELY MIRRORS learnCrop() IN docs/capture/engine/refs.js,
// STEP FOR STEP, and that is the whole point of it.
//
// Every reference portrait in refs.json was produced by drawing into a canvas
// with imageSmoothingEnabled/imageSmoothingQuality='high' and then taking luma
// at 0.299/0.587/0.114. The matcher does not compare pictures; it compares
// numbers that came out of that exact pipeline. Resample differently - a
// hand-rolled bilinear, a box filter, BT.709 weights - and the crop still looks
// perfectly fine to a human while scoring differently against every stored
// template. Nothing fails; matching just quietly gets worse.
//
// So the resampler is a real canvas rather than arithmetic of our own, and the
// base64 encoder is util.js's shipped bytesToB64 rather than a copy. The bot
// runs the same code the browser does, and cannot drift from it.

(function (global) {
  'use strict';

  var createCanvas = require('@napi-rs/canvas').createCanvas;
  var U = require('../../docs/capture/engine/util.js');

  // One portrait cell, as base64 of REF_W*REF_H greyscale bytes.
  //
  // `img` is anything canvas will draw - a decoded image or another canvas.
  // `rect` is the region in frame coordinates, from calib.cells().
  function cell(img, rect, ref) {
    var w = ref.REF_W;
    var h = ref.REF_H;

    var cv = createCanvas(w, h);
    var cx = cv.getContext('2d', { willReadFrequently: true });
    cx.imageSmoothingEnabled = true;
    cx.imageSmoothingQuality = 'high';
    cx.drawImage(img, rect.x, rect.y, rect.w, rect.h, 0, 0, w, h);

    var d = cx.getImageData(0, 0, w, h).data;
    var px = new Uint8Array(w * h);
    for (var j = 0, k = 0; j < d.length; j += 4, k++) {
      px[k] = Math.round(0.299 * d[j] + 0.587 * d[j + 1] + 0.114 * d[j + 2]);
    }
    return U.bytesToB64(px);
  }

  // All ten cells of a frame, side 'a' slots 0-4 then side 'b' slots 0-4, which
  // is the order the rest of the bot expects them in.
  function all(img, calib) {
    var out = { a: [], b: [] };
    ['a', 'b'].forEach(function (side) {
      calib.cells(side).forEach(function (rect) {
        out[side].push(cell(img, rect, calib.FROZEN.ref));
      });
    });
    return out;
  }

  // Per-pixel break flags along the replay scrubber, for timeline.js to turn
  // into rounds. The pixel reading lives here, with the rest of the canvas
  // work, so timeline.js can stay pure and testable on plain arrays.
  //
  // Rows are averaged across the bar's core to shrug off single-row noise, and
  // a break is decided on the blue channel's lead over red rather than on
  // brightness - ticks and the playhead are bright, and would otherwise read
  // as structure.
  function barFlags(img, calib) {
    var t = calib.FROZEN.timeline;
    var w = img.width;
    var cv = createCanvas(w, img.height);
    var cx = cv.getContext('2d', { willReadFrequently: true });
    cx.drawImage(img, 0, 0);
    var d = cx.getImageData(0, 0, w, img.height).data;

    var out = [];
    for (var x = t.x0; x <= t.x1; x++) {
      var r = 0, b = 0, n = 0;
      for (var y = t.y0; y <= t.y1; y++) {
        var i = (y * w + x) * 4;
        r += d[i];
        b += d[i + 2];
        n++;
      }
      out.push((b / n) - (r / n) > t.blueLead);
    }
    return out;
  }

  // How much of the events-panel box is made of the panel's own rows, which is
  // how the bot tells whether the replay events viewer is open.
  //
  // BRIGHTNESS CANNOT ANSWER THIS AND THREE MAPS PROVED IT. The panel is
  // translucent, so what it reads depends on the map behind it - on a dark map
  // it brightens the box (0.045 -> 0.770), on a neon one it DARKENS it
  // (0.548 -> 0.519). Closed readings ranged 0.045 to 0.548 and open ones 0.519
  // to 0.770: overlapping, in both directions, so neither a level nor a rise
  // can separate them. Two maps were refused with the panel plainly open on
  // screen.
  //
  // FLATNESS CANNOT ANSWER IT EITHER, WHICH TOOK LONGER TO FIND. The panel is a
  // stack of flat bars - the round rows and the two dropdowns - and on the
  // three maps that were to hand, counting uniform rows separated the states
  // cleanly. It does not generalise: a night sky is uniform, so is a loading
  // screen, so is a black frame, and so is the ESC menu. Run over the retained
  // frames rather than three maps, closed spanned 0.000 to 1.000 against open
  // 0.345 to 0.805, and six frames with no panel on them at all were read as
  // having one.
  //
  // The panel's bars are flat AND LIGHT, and the bars that are read are the two
  // DROPDOWNS, not the round rows.
  //
  // THE ROUND ROWS ARE A DIFFERENT PANEL ON EVERY MAP TYPE. Push and Flashpoint
  // play one long round, Control up to three, Escort and Hybrid at least two -
  // so a fraction taken over them means something different each time. Measured
  // live: three-round frames read 0.340 and up, and a one-round map read 0.170
  // against a threshold of 0.15, on a panel that was plainly open.
  //
  // The dropdowns are there whenever the panel is, whatever the map. They are
  // read as two boxes rather than one because of the gap between them: a row
  // crossing it goes white, dark, white, which is not uniform and reads as no
  // panel at all. The weaker of the two is the answer, so a lucky bright patch
  // in one place cannot carry it - and across every labelled frame the weakest
  // open reading is 0.587 while nothing shut registers anything at all.
  //
  // See corpus.js: every frame behind those numbers was labelled by looking.
  function panelRowFraction(img, calib) {
    var p = calib.FROZEN.eventsPanel;
    var cv = createCanvas(img.width, img.height);
    var cx = cv.getContext('2d', { willReadFrequently: true });
    cx.drawImage(img, 0, 0);
    var d = cx.getImageData(0, 0, img.width, img.height).data;

    function fractionOf(box) {
      var flat = 0, rows = 0;
      for (var y = box.y0; y < box.y1; y++) {
        var sum = 0, sum2 = 0, n = 0;
        for (var x = box.x0; x < box.x1; x += 2) {
          var i = (y * img.width + x) * 4;
          var l = 0.299 * d[i] + 0.587 * d[i + 1] + 0.114 * d[i + 2];
          sum += l;
          sum2 += l * l;
          n++;
        }
        var mean = sum / n;
        var sd = Math.sqrt(Math.max(0, sum2 / n - mean * mean));
        if (sd < p.flatSd && mean > p.panelRowLum) flat++;
        rows++;
      }
      return rows ? flat / rows : 0;
    }

    var worst = 1;
    p.dropdowns.forEach(function (box) {
      var f = fractionOf(box);
      if (f < worst) worst = f;
    });
    return worst;
  }

  // How much of the events-panel box is bright. Kept because the probes and the
  // retained frames are full of it, but it decides nothing any more. It has to know, because the
  // scrubber only draws round breaks while that panel is showing, and K
  // toggles it - so pressing K blind would close it half the time.
  function panelBrightFraction(img, calib) {
    var p = calib.FROZEN.eventsPanel;
    var cv = createCanvas(img.width, img.height);
    var cx = cv.getContext('2d', { willReadFrequently: true });
    cx.drawImage(img, 0, 0);
    var d = cx.getImageData(0, 0, img.width, img.height).data;

    var bright = 0, n = 0;
    for (var y = p.y0; y < p.y1; y += 4) {
      for (var x = p.x0; x < p.x1; x += 4) {
        var i = (y * img.width + x) * 4;
        var l = 0.299 * d[i] + 0.587 * d[i + 1] + 0.114 * d[i + 2];
        if (l > p.brightAt) bright++;
        n++;
      }
    }
    return n ? bright / n : 0;
  }

  // Where the playhead knob is, so a seek can be checked rather than trusted.
  //
  // THIS IS THE ONLY WAY TO KNOW A SEEK LANDED. The driver counts presses, and
  // counting is exact right up until the client ignores one - which it does,
  // silently, while it is busy seeking. Six frames retained from the first live
  // run all read the same ten heroes, and the reason was visible only here: the
  // knob had moved exactly 45px between consecutive samples, one 20-second
  // step, no matter how many presses had been sent. The bot believed it was at
  // 14:40 and was at 1:42.
  //
  // The knob is found as the widest bright run along the bar's core rows,
  // BETWEEN playheadMinPx and playheadMaxPx wide. In those frames it was the
  // ONLY run over luma 200, exactly 40px wide, with the played side at ~186 and
  // the unplayed side at ~77 - so widest-run is deliberate belt and braces
  // against a bright event tick, not a guess. The upper bound rejects a wide
  // bright band that is scenery showing through with the controls down, not a
  // knob (see calib.FROZEN.timeline.playheadMaxPx).
  //
  // Returns null when no run is in range, because a missing playhead is a
  // frame worth refusing rather than a position worth inventing.
  function playheadX(img, calib) {
    var t = calib.FROZEN.timeline;
    var cv = createCanvas(img.width, img.height);
    var cx = cv.getContext('2d', { willReadFrequently: true });
    cx.drawImage(img, 0, 0);
    var d = cx.getImageData(0, 0, img.width, img.height).data;

    var best = null;
    var start = -1;
    for (var x = t.x0; x <= t.x1 + 1; x++) {
      var hot = false;
      if (x <= t.x1) {
        var l = 0, n = 0;
        for (var y = t.y0; y <= t.y1; y++) {
          var i = (y * img.width + x) * 4;
          l += 0.299 * d[i] + 0.587 * d[i + 1] + 0.114 * d[i + 2];
          n++;
        }
        hot = (l / n) > t.playheadBright;
      }
      if (hot && start < 0) start = x;
      if (!hot && start >= 0) {
        var run = { x0: start, x1: x - 1, width: x - start, centre: (start + x - 1) / 2 };
        var inRange = run.width >= t.playheadMinPx &&
          (t.playheadMaxPx === undefined || run.width <= t.playheadMaxPx);
        if (inRange && (!best || run.width > best.width)) best = run;
        start = -1;
      }
    }
    return best;
  }

  // How strongly each side's portrait band is tinted with its team colour.
  //
  // THIS IS WHAT "A REPLAY IS ON SCREEN" LOOKS LIKE. The playhead was used for
  // that and it was wrong: the media controls are HIDDEN when a replay opens,
  // so a perfectly good replay showed no scrubber, run.js waited 90 seconds for
  // one, gave up - and then played the import chunk inside the replay it had
  // failed to notice, clicking at coordinates that meant something else
  // entirely.
  //
  // The plates are always there and always coloured: side a blue, side b red.
  //
  // ONLY THE PORTRAIT BAND IS READ, AND NOT READING IT COST A CODE. This used
  // to average the whole plate box, which also takes in the name plates, the
  // health pips, and whatever the map shows in the gaps between the five cells.
  // On a bright blue map that is enough to cancel team B's red outright: 4.8
  // against a threshold of 15, on a replay that was open on screen at the time.
  // run.js reads this to decide whether a replay loaded, so it waited its 90
  // seconds, gave up, and spent the code. That was RCR3NK.
  //
  // The fix is the crop `cells` already uses and for the same stated reason -
  // "below that sit the name plate and the health pips, and both are poison".
  // Keeping the top TF of the box takes the tinted band and nothing else.
  // Measured over every frame known to be a replay because its events panel is
  // open: the dimmest reads 31.3, against exactly 0.0 on a loading screen, a
  // black frame and the ESC menu. The threshold of 15 never moved.
  function hudTint(img, calib) {
    var cv = createCanvas(img.width, img.height);
    var cx = cv.getContext('2d', { willReadFrequently: true });
    cx.drawImage(img, 0, 0);
    var d = cx.getImageData(0, 0, img.width, img.height).data;

    var out = {};
    ['a', 'b'].forEach(function (side) {
      var box = calib.FROZEN.boxes[side];
      var r = 0, b = 0, n = 0;
      var bottom = Math.round(box.y + box.h * calib.FROZEN.ref.TF);
      for (var y = Math.round(box.y); y < bottom; y += 3) {
        for (var x = Math.round(box.x); x < Math.round(box.x + box.w); x += 3) {
          var i = (y * img.width + x) * 4;
          r += d[i];
          b += d[i + 2];
          n++;
        }
      }
      // Signed towards the side's own colour, so both are positive in a replay.
      out[side] = n ? (side === 'a' ? (b - r) / n : (r - b) / n) : 0;
    });
    return out;
  }

  var Mod = {
    cell: cell,
    hudTint: hudTint,
    all: all,
    barFlags: barFlags,
    panelBrightFraction: panelBrightFraction,
    panelRowFraction: panelRowFraction,
    playheadX: playheadX,
  };

  if (typeof module !== 'undefined' && module.exports) module.exports = Mod;
  else global.OWDBReplayCrop = Mod;
})(typeof self !== 'undefined' ? self : this);

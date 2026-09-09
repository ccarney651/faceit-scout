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

  // How much of the events-panel box is bright, which is how the bot tells
  // whether the replay events viewer is open. It has to know, because the
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

  var Mod = {
    cell: cell,
    all: all,
    barFlags: barFlags,
    panelBrightFraction: panelBrightFraction,
  };

  if (typeof module !== 'undefined' && module.exports) module.exports = Mod;
  else global.OWDBReplayCrop = Mod;
})(typeof self !== 'undefined' ? self : this);

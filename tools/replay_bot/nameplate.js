// tools/replay_bot/nameplate.js
// Cropping the name strip under a side's five portraits, for OCR.
// See specs/2026-09-10-replay-bot-player-attribution-design.md §3.
//
// docs/capture/engine/frames.js's findNameRow/findNameSpan are pure pixel
// math - no DOM - and are required directly, unmodified, the same way
// match.js already requires refs.js. Only the thin canvas-cropping glue
// around them (nameRow/cellNameSpan/nameCanvas, defined inside frames.js's
// make(ctx) because ctx.doc is a browser DOM) needs mirroring here against
// @napi-rs/canvas, for the same reason crop.js mirrors refs.js's learnCrop()
// rather than carrying a DOM shim for it.
//
// GEOMETRY IS NOT THE LIVE TOOL'S. frames.js's NAME_BAND_TOP/BOT (0.30-1.15)
// are fitted to getDisplayMedia geometry, and player-attribution-live's own
// notes say replay geometry differs from live's by ~6% width/~14% height on
// the portrait strip - the exact mistake calibration-relative-geometry warns
// against repeating. The constants below were read off real replay-bot
// frames (cap-t0-741.png, both sides, 2026-09-10): the portrait fills
// 0-0.45 of the box height (TF, already known), the name text sits at
// roughly 0.55-0.72, and the health bar starts around 0.85. The search band
// is wider than that measurement on both sides, the same way the live tool's
// is wider than its own fallback - findNameRow does its own fine
// localisation inside whatever band it is handed.
//
// calib.cells(side) is the WRONG box for this: it already restricts height to
// TF (portrait-only), because that is what the hero matcher wants. The name
// row search needs the FULL per-side box (calib.FROZEN.boxes[side]) - the
// same x/w calib.cells() already reports, but the untouched height.

(function (global) {
  'use strict';

  var canvas = require('@napi-rs/canvas');
  var Frames = require('../../docs/capture/engine/frames.js');

  var NAME_BAND_TOP = 0.48, NAME_BAND_BOT = 0.85;

  function imageData(img, x, y, w, h) {
    w = Math.max(1, Math.round(w));
    h = Math.max(1, Math.round(h));
    var cv = canvas.createCanvas(w, h);
    var cx = cv.getContext('2d', { willReadFrequently: true });
    cx.drawImage(img, x, y, w, h, 0, 0, w, h);
    return { data: cx.getImageData(0, 0, w, h).data, w: w, h: h };
  }

  // Where the name row sits for ONE SIDE's whole strip, in frame coordinates:
  // { y, h, t } (t is the luminance threshold findNameRow settled on, which
  // cellNameSpan needs too), or null when nothing text-like was found.
  //
  // Called ONCE PER SIDE, mirroring the live tool exactly and for the same
  // reason: the five names share a row, so across the whole strip they
  // reinforce each other while what defeats a single cell - the portrait
  // above it, a bright scene showing through the plate - averages out.
  function nameRow(img, box) {
    var y0 = box.y + box.h * NAME_BAND_TOP, y1 = box.y + box.h * NAME_BAND_BOT;
    var band = imageData(img, box.x, y0, box.w, y1 - y0);
    var found = Frames.findNameRow(band.data, band.w, band.h);
    if (!found) return null;
    var pad = Math.max(2, Math.round(found.h * 0.25));
    var y = Math.max(0, y0 + found.y - pad);
    return { y: y, h: found.h + 2 * pad, t: found.t };
  }

  // Where the glyphs are within ONE slot's name band, in frame coordinates:
  // { x, w } | null. `cell` only needs x/w - calib.cells(side)[i] already
  // has the right ones, since the horizontal slot boundaries do not depend on
  // TF.
  function cellNameSpan(img, cell, row) {
    var span = imageData(img, cell.x, row.y, cell.w, row.h);
    var found = Frames.findNameSpan(span.data, span.w, span.h, row.t);
    return found ? { x: cell.x + found.x, w: found.w } : null;
  }

  // The final crop for OCR: grayscale, 6x upscale, a light contrast stretch -
  // exactly nameCanvas()'s recipe, because tesseract was tuned against that
  // recipe's output, not a screenshot's.
  //
  // Falls back to a padded, un-spanned crop at the row's own bounds when
  // findNameSpan finds nothing, so an unreadable slot costs nothing more than
  // before - never a thrown error over one bad cell.
  function nameCrop(img, cell, row) {
    var padX = Math.max(4, Math.round(cell.w * 0.05));
    var sx = Math.max(0, cell.x - padX), sw = cell.w + 2 * padX;
    var span = cellNameSpan(img, cell, row);
    if (span) { sx = span.x; sw = span.w; }

    var sc = 6;
    var cv = canvas.createCanvas(Math.max(1, Math.round(sw * sc)), Math.max(1, Math.round(row.h * sc)));
    var cx = cv.getContext('2d', { willReadFrequently: true });
    cx.imageSmoothingEnabled = true;
    cx.drawImage(img, sx, row.y, sw, row.h, 0, 0, cv.width, cv.height);
    var im = cx.getImageData(0, 0, cv.width, cv.height), d = im.data;
    for (var i = 0; i < d.length; i += 4) {
      var g = 0.299 * d[i] + 0.587 * d[i + 1] + 0.114 * d[i + 2];
      g = (g - 128) * 1.5 + 140; g = g < 0 ? 0 : g > 255 ? 255 : g;
      d[i] = d[i + 1] = d[i + 2] = g;
    }
    cx.putImageData(im, 0, 0);
    return cv;
  }

  var Mod = {
    NAME_BAND_TOP: NAME_BAND_TOP,
    NAME_BAND_BOT: NAME_BAND_BOT,
    nameRow: nameRow,
    cellNameSpan: cellNameSpan,
    nameCrop: nameCrop,
  };

  if (typeof module !== 'undefined' && module.exports) module.exports = Mod;
  else global.OWDBReplayNameplate = Mod;
})(typeof self !== 'undefined' ? self : this);

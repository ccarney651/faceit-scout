// docs/capture/engine/frames.js
// Screen-share + frame-grab layer shared by index.html and scrim.html:
// grabbing a still frame from the shared <video> element, converting
// portrait cells to grayscale for the hero matcher, rendering HUD-name crops
// for OCR, finding the letterboxed content rect inside a raw capture, and
// tearing capture down.
//
// Extracted from the two hand-maintained forks (see
// tools/capture_divergence.py): ensureWork, grabFrame, grayCanvas,
// cellGrayPadded, nameCanvas, detectContentRect, togglePreview and
// readyForCapture were byte-identical between the pages. stopCapture
// diverged by -16 characters - not by drift, but by design: index.html
// releases its live-scouting claim on teardown (releaseClaim(), a system
// scrims don't have) and scrim.html does not. This module must never know
// which page is running it, so stopCapture takes the teardown from
// ctx.onStop: index.html passes releaseClaim, scrim.html passes null.
//
// ctx = {doc, video, onStop} - only those three. REF_W/REF_H/PAD/LF/TF (the
// reference-template geometry, loaded from refs.json) and boxes/
// selectedCode (calibration + UI state) are deliberately NOT part of ctx:
// they're page-level globals each page declares identically before its
// inline script runs, exactly like engine/util.js's scl()/evp() close over
// vid/ov. Classic <script src> tags and the page's inline script share one
// global lexical scope, so these free-variable lookups resolve at call
// time, after the page has defined them. The same is true of
// clearCalPreview/drawOverlay/updateBtns, which stay page-side and are
// called the same way from stopCapture.
//
// make(ctx) is a factory, not a set of static functions like engine/idb.js:
// each page calls it once and keeps the instance. The work canvas below is
// created once per instance and reused by ensureWork/cellGrayPadded,
// matching the original single page-scoped `work`/`wctx` pair.
//
// Consumes OWDBUtil.b64bytes (engine/util.js) for grayCanvas, looked up
// lazily at call time so this file has no hard load-order requirement on
// util.js and no eager `require` that would break a test loading this
// source in isolation.
//
// Works as a browser global (`window.OWDBFrames`) and as a CommonJS module
// for node:test / pytest.

(function (global) {
  'use strict';

  function getUtil() {
    if (typeof module !== 'undefined' && module.exports) return require('./util.js');
    return global.OWDBUtil;
  }

  // --- name-row location ---------------------------------------------------
  //
  // Every constant here was swept over the nine real frames in screenshots/,
  // each at four capture resolutions and with the calibration box shifted and
  // stretched (tools/real_frame_eval/rowfind_sweep.py). Re-run that sweep
  // before changing any of them.

  // Search window for the name row, as a fraction of the calibration box's
  // height. Starts below the portraits (top_fraction is 0.45) and runs past
  // the bottom of the box, because the box is fitted to the portraits and the
  // names hang underneath them.
  var NAME_BAND_TOP = 0.30, NAME_BAND_BOT = 1.15;
  // A full health bar fills ~0.55 of the strip and a name ~0.15-0.32, so this
  // is what tells the two apart. It has to be a fill test and not a "which is
  // brighter" or "which is first" test: the bar out-scores a short name on
  // brightness, and the hero portrait sits ABOVE the name, so both of those
  // shortcuts were tried and both picked the wrong band.
  var NAME_FILL_MAX = 0.42;
  var NAME_RUN_FRAC = 0.35;   // rows scoring this share of the peak join a run

  // findNameRow(rgba, w, h) -> { y, h } | null
  //
  // `rgba` is the search band of ONE side's strip, w x h, as ImageData.data.
  // Returns the text row's position within that band.
  //
  // Text is a row with many horizontal light/dark transitions that does not
  // fill the strip; the run of such rows sitting in the quietest surroundings
  // wins, because the HUD draws the names on a dark plate and nothing else in
  // the band has empty rows above and below it.
  function findNameRow(rgba, w, h) {
    if (!w || !h || !rgba || rgba.length < w * h * 4) return null;
    var lum = new Uint8Array(w * h), hist = new Uint32Array(256), i, j, y, x;
    for (i = 0, j = 0; j < w * h; i += 4, j++) {
      var g = (0.299 * rgba[i] + 0.587 * rgba[i + 1] + 0.114 * rgba[i + 2]) | 0;
      lum[j] = g; hist[g]++;
    }
    // The 88th percentile picks glyph strokes out of the plate. Clamped
    // because a bright scene behind the HUD can push it to 255, which would
    // select nothing at all - four box variants in the sweep did exactly that.
    var want = Math.floor(w * h * 0.88), acc = 0, T = 0;
    for (T = 0; T < 256; T++) { acc += hist[T]; if (acc >= want) break; }
    if (T < 120) T = 120; else if (T > 230) T = 230;

    var fill = new Float64Array(h), tr = new Float64Array(h), score = new Float64Array(h), max = 0;
    for (y = 0; y < h; y++) {
      var on = 0, ch = 0, prev = false, base = y * w;
      for (x = 0; x < w; x++) {
        var v = lum[base + x] > T;
        if (v) on++;
        if (x && v !== prev) ch++;
        prev = v;
      }
      fill[y] = on / w; tr[y] = ch / w;
      score[y] = fill[y] <= NAME_FILL_MAX ? tr[y] : 0;
      if (score[y] > max) max = score[y];
    }
    if (max <= 0) return null;

    // Mean fill of the three rows either side of a run. A run that reaches the
    // edge of the band has no such rows, and is penalised for it - whatever it
    // is, it continues past where we looked.
    function quiet(s, e) {
      var a = 0, na = 0, b = 0, nb = 0, k;
      for (k = Math.max(0, s - 3); k < s; k++) { a += fill[k]; na++; }
      for (k = e + 1; k < Math.min(h, e + 4); k++) { b += fill[k]; nb++; }
      a = na ? a / na : 0.5; b = nb ? b / nb : 0.5;
      return Math.max(0, 1 - (a + b) / 0.20);
    }

    var thr = NAME_RUN_FRAC * max, best = null, bestv = -1, start = -1;
    for (y = 0; y <= h; y++) {
      var inRun = y < h && score[y] >= thr;
      if (inRun && start < 0) start = y;
      else if (!inRun && start >= 0) {
        var end = y - 1, sum = 0;
        for (var k = start; k <= end; k++) sum += tr[k];
        var v2 = (sum / (end - start + 1)) * quiet(start, end);
        if (v2 > bestv) { bestv = v2; best = [start, end]; }
        start = -1;
      }
    }
    if (!best) return null;
    return { y: best[0], h: best[1] - best[0] + 1, t: T };
  }

  // findNameSpan(rgba, w, h, threshold) -> { x, w } | null
  //
  // Where the glyphs are within ONE cell's name band. The cell crop is padded
  // by 5% of its width on each side, which on a tight HUD reaches into the
  // NEIGHBOURING name plate and drags its border in - tesseract reads those
  // bars as `|`, `i`, `§` or `}`, and they are what stopped clean reads
  // matching a roster. Measured over twelve real frames, live and archived:
  // padding gives 75/120 exact reads with 57 stray characters, cropping to the
  // glyph run gives 110/120 with 2, and no frame got worse.
  //
  // A run touching the very edge is that border - UNLESS it is wide, because a
  // name like CHEESEBURGER genuinely fills its cell and must not be clipped.
  function findNameSpan(rgba, w, h, threshold) {
    if (!w || !h || !rgba || rgba.length < w * h * 4) return null;
    var t = threshold || 200, on = new Uint8Array(w), x, y;
    for (y = 0; y < h; y++) {
      for (x = 0; x < w; x++) {
        var i = ((y * w + x) << 2);
        var g = (0.299 * rgba[i] + 0.587 * rgba[i + 1] + 0.114 * rgba[i + 2]);
        if (g > t) on[x] = 1;
      }
    }
    var runs = [], st = -1;
    for (x = 0; x <= w; x++) {
      if (x < w && on[x]) { if (st < 0) st = x; }
      else if (st >= 0) { runs.push([st, x]); st = -1; }
    }
    var EDGE = 2, WIDE = 6;
    runs = runs.filter(function (r) {
      var touches = r[0] <= EDGE || r[1] >= w - EDGE;
      return !touches || (r[1] - r[0]) > WIDE;
    });
    if (!runs.length) return null;
    var lo = w, hi = 0;
    runs.forEach(function (r) { if (r[0] < lo) lo = r[0]; if (r[1] > hi) hi = r[1]; });
    var pad = 4;
    lo = Math.max(0, lo - pad); hi = Math.min(w, hi + pad);
    return { x: lo, w: hi - lo };
  }

  function make(ctx) {
    // Reused across every ensureWork/cellGrayPadded call, same as the
    // original module-scoped `work`/`wctx` pair each page declared once.
    var work = ctx.doc.createElement('canvas');
    var wctx = null;

    function ensureWork() {
      work.width = REF_W + 2 * PAD;
      work.height = REF_H + 2 * PAD;
      wctx = work.getContext('2d', { willReadFrequently: true });
    }

    function cellGrayPadded(frame, cell) {
      var fx = cell.x + cell.w * LF, fy = cell.y, fw = cell.w * (1 - LF), fh = cell.h * TF;
      wctx.drawImage(frame, fx, fy, fw, fh, 0, 0, work.width, work.height);
      var d = wctx.getImageData(0, 0, work.width, work.height).data;
      var g = new Float32Array(work.width * work.height);
      for (var i = 0, j = 0; i < d.length; i += 4, j++) g[j] = 0.299 * d[i] + 0.587 * d[i + 1] + 0.114 * d[i + 2];
      return g;
    }

    function grabFrame() {
      var c = ctx.doc.createElement('canvas');
      c.width = ctx.video.videoWidth; c.height = ctx.video.videoHeight;
      c.getContext('2d').drawImage(ctx.video, 0, 0);
      return c;
    }

    // Render a stored grayscale crop to a (scaled) canvas for the review portraits.
    function grayCanvas(b64, scale) {
      scale = scale || 2;
      var px = getUtil().b64bytes(b64);
      var tmp = ctx.doc.createElement('canvas'); tmp.width = REF_W; tmp.height = REF_H;
      var im = tmp.getContext('2d').createImageData(REF_W, REF_H);
      for (var i = 0, j = 0; i < px.length; i++, j += 4) { im.data[j] = im.data[j + 1] = im.data[j + 2] = px[i]; im.data[j + 3] = 255; }
      tmp.getContext('2d').putImageData(im, 0, 0);
      var cv = ctx.doc.createElement('canvas'); cv.width = REF_W * scale; cv.height = REF_H * scale;
      var cx = cv.getContext('2d'); cx.imageSmoothingEnabled = false; cx.drawImage(tmp, 0, 0, cv.width, cv.height);
      return cv;
    }

    // Where the name row sits inside one side's five-slot strip, in frame
    // coordinates: { y, h }, or null when nothing text-like was found.
    //
    // Call this ONCE PER SIDE and hand the result to all five nameCanvas()
    // calls. The row is deliberately not found per slot: all five names share
    // one row, so across the strip they reinforce each other while the noise
    // that defeats a single cell - the hero portrait above the name, a bright
    // scene showing through the plate - averages out. Two per-slot attempts
    // failed exactly there (see the header of tools/real_frame_eval/).
    function nameRow(frame, box) {
      var fw = frame.width, fh = frame.height;
      var x0 = Math.max(0, Math.round(box.x)), x1 = Math.min(fw, Math.round(box.x + box.w));
      var y0 = Math.max(0, Math.round(box.y + box.h * NAME_BAND_TOP));
      var y1 = Math.min(fh, Math.round(box.y + box.h * NAME_BAND_BOT));
      if (x1 - x0 < 8 || y1 - y0 < 6) return null;
      var cv = ctx.doc.createElement('canvas');
      cv.width = x1 - x0; cv.height = y1 - y0;
      var cx = cv.getContext('2d', { willReadFrequently: true });
      cx.drawImage(frame, x0, y0, cv.width, cv.height, 0, 0, cv.width, cv.height);
      var found = findNameRow(cx.getImageData(0, 0, cv.width, cv.height).data, cv.width, cv.height);
      if (!found) return null;
      // Tesseract wants a little air around the glyphs; the run itself is their
      // exact extent.
      var pad = Math.max(2, Math.round(found.h * 0.25));
      var y = Math.max(0, y0 + found.y - pad);
      return { y: y, h: Math.min(fh - y, found.h + 2 * pad), t: found.t };
    }

    // Pixels of one cell's name band, for findNameSpan. Sampled at native
    // resolution from the cell alone - the span is meaningless across cells.
    function cellNameSpan(frame, cell, sy, sh, t) {
      var x0 = Math.max(0, Math.round(cell.x)), x1 = Math.min(frame.width, Math.round(cell.x + cell.w));
      var y0 = Math.max(0, Math.round(sy)), y1 = Math.min(frame.height, Math.round(sy + sh));
      if (x1 - x0 < 8 || y1 - y0 < 4) return null;
      var cv = ctx.doc.createElement('canvas');
      cv.width = x1 - x0; cv.height = y1 - y0;
      var cx = cv.getContext('2d', { willReadFrequently: true });
      cx.drawImage(frame, x0, y0, cv.width, cv.height, 0, 0, cv.width, cv.height);
      var span = findNameSpan(cx.getImageData(0, 0, cv.width, cv.height).data, cv.width, cv.height, t);
      return span ? { x: x0 + span.x, w: span.w } : null;
    }

    // Without a row, the name bar is assumed to sit at ~48-90% of each portrait
    // cell's height (mirror of the .exe's read_hud_names). That assumption is
    // why this function needs `row`: on a real 2557x1438 frame the 48-90% band
    // straddles the portrait bottom, the name AND the health bar, and the bar
    // is the brightest thing in it - real tesseract returned letter-soup for 75
    // of 90 slots. With the located row it reads 77 of 90 outright, and every
    // one of the 90 resolves once assign.js applies the role constraint.
    // Grayscale + 6x upscale + a light contrast stretch lift the ~10px text
    // enough for OCR.
    function nameCanvas(frame, cell, row) {
      var padX = Math.max(4, Math.round(cell.w * 0.05));
      var sx = Math.max(0, cell.x - padX), sw = cell.w + 2 * padX, sc = 6;
      var sy = row ? row.y : cell.y + cell.h * 0.48, sh = row ? row.h : cell.h * 0.42;
      // With a row in hand, crop to the GLYPHS rather than to the padded cell:
      // the pad reaches into the neighbouring plate and its border reads as
      // stray characters. Falls back to the padded cell when nothing is found,
      // so an unreadable slot is no worse off than before.
      if (row) {
        var span = cellNameSpan(frame, cell, sy, sh, row.t);
        if (span) { sx = span.x; sw = span.w; }
      }
      var cv = ctx.doc.createElement('canvas');
      cv.width = Math.max(1, Math.round(sw * sc)); cv.height = Math.max(1, Math.round(sh * sc));
      var cx = cv.getContext('2d', { willReadFrequently: true }); cx.imageSmoothingEnabled = true; cx.imageSmoothingQuality = 'high';
      cx.drawImage(frame, sx, sy, sw, sh, 0, 0, cv.width, cv.height);
      var im = cx.getImageData(0, 0, cv.width, cv.height), d = im.data;
      for (var i = 0; i < d.length; i += 4) {
        var g = 0.299 * d[i] + 0.587 * d[i + 1] + 0.114 * d[i + 2];
        g = (g - 128) * 1.5 + 140; g = g < 0 ? 0 : g > 255 ? 255 : g; d[i] = d[i + 1] = d[i + 2] = g;
      }
      cx.putImageData(im, 0, 0);
      return cv;
    }

    // Find the game render area inside the capture, stripping near-black
    // letterbox / pillarbox (odd aspect ratios / resolutions), capped at 20%
    // per edge. Does NOT strip a window title bar (it isn't black) - share
    // the whole screen for that.
    function detectContentRect() {
      var W = ctx.video.videoWidth, H = ctx.video.videoHeight;
      if (!W) return { x: 0, y: 0, w: W, h: H };
      var sw = Math.min(320, W), sh = Math.max(1, Math.round(H * sw / W));
      var cv = ctx.doc.createElement('canvas'); cv.width = sw; cv.height = sh;
      var cx = cv.getContext('2d', { willReadFrequently: true }); cx.drawImage(ctx.video, 0, 0, sw, sh);
      var d = cx.getImageData(0, 0, sw, sh).data, BLACK = 24;
      var rowMax = function (y) { var m = 0; for (var x = 0; x < sw; x++) { var i = (y * sw + x) * 4, g = Math.max(d[i], d[i + 1], d[i + 2]); if (g > m) m = g; } return m; };
      var colMax = function (x) { var m = 0; for (var y = 0; y < sh; y++) { var i = (y * sw + x) * 4, g = Math.max(d[i], d[i + 1], d[i + 2]); if (g > m) m = g; } return m; };
      var cY = Math.floor(sh * 0.2), cX = Math.floor(sw * 0.2);
      var t = 0; while (t < cY && rowMax(t) < BLACK) t++;
      var b = sh - 1; while (b > sh - 1 - cY && rowMax(b) < BLACK) b--;
      var l = 0; while (l < cX && colMax(l) < BLACK) l++;
      var r = sw - 1; while (r > sw - 1 - cX && colMax(r) < BLACK) r--;
      var sx = W / sw, sy = H / sh;
      return { x: l * sx, y: t * sy, w: (r - l + 1) * sx, h: (b - t + 1) * sy };
    }

    // index.html passes onStop: releaseClaim (the live-scouting claim
    // system); scrim.html passes onStop: null - scrims have no claims.
    function stopCapture() {
      clearCalPreview();
      if (ctx.video.srcObject) {
        ctx.video.srcObject.getTracks().forEach(function (t) { t.stop(); });
        ctx.video.srcObject = null;
      }
      if (ctx.onStop) ctx.onStop();
      drawOverlay();
      updateBtns();
      ctx.doc.getElementById('calhint').textContent =
        'Screen capture stopped. Click Share my screen to resume.';
    }

    function togglePreview() {
      var L = ctx.doc.getElementById('layout'); L.classList.toggle('nopreview');
      ctx.doc.getElementById('hidep').textContent = L.classList.contains('nopreview') ? 'Show preview' : 'Hide preview';
    }

    function readyForCapture() {
      return !!(ctx.video.srcObject && boxes.a && boxes.b && selectedCode());
    }

    return {
      ensureWork: ensureWork,
      grabFrame: grabFrame,
      grayCanvas: grayCanvas,
      cellGrayPadded: cellGrayPadded,
      nameRow: nameRow,
      nameCanvas: nameCanvas,
      detectContentRect: detectContentRect,
      stopCapture: stopCapture,
      togglePreview: togglePreview,
      readyForCapture: readyForCapture,
    };
  }

  var Mod = { make: make, findNameRow: findNameRow, findNameSpan: findNameSpan };

  if (typeof module !== 'undefined' && module.exports) module.exports = Mod;
  else global.OWDBFrames = Mod;
})(typeof self !== 'undefined' ? self : this);

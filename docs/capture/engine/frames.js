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
// ctx = {doc, video, onStop} - only those three. REF_W/REF_H/PAD/LF/TF/RF (the
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
  //
  // 2026-09-15: that fill test used to be against a FIXED ceiling (0.42),
  // which assumed the plate under the name is always dark. A light-blue or
  // saturated-red team-colour plate breaks that assumption exactly the way a
  // fixed brightness value once broke the scrim scoreboard's read (see
  // scrim.html's scoreCanvas comment) - the whole row, glyphs and gaps alike,
  // sits above a flat 0.42 ceiling, so real text gets zeroed out or shredded
  // into a one-pixel sliver. The fix is the same one that fixed the
  // scoreboard: judge a row against its OWN LOCAL surroundings, not a value
  // that only held for the plates it was tuned on. NAME_FILL_MARGIN is how
  // much fuller a row may be than the plate immediately around it (sampled
  // from a window of nearby rows, gapped so a text row's own coverage does
  // not inflate its own baseline) and still count as candidate text.
  //
  // specs/2026-09-15-nameplate-fill-heuristic-handoff.md root-caused this;
  // tools/replay_bot/nameplate_fill_sweep.js is the harness that measured
  // the replacement - a global-median-relative ceiling never recovered the
  // fragmented case at any tested margin (ruled out), while both a raised
  // fixed ceiling and this local one recovered all 3 known-bad crops and
  // plateaued at an identical, bounded ~11.7% footprint of the 780-strip
  // 2026-09-15 corpus once the margin/ceiling was generous enough. The local
  // form is kept because a fixed ceiling is the same kind of number that
  // already failed once (0.42 itself) and would need retuning again for the
  // next plate brighter than anything measured so far; a local margin
  // adapts to a plate's own brightness without a human in the loop.
  //
  // NAME_FILL_FLOOR keeps the OLD fixed value as a floor under the new local
  // one, not a replacement for it: frames.test.js's synthetic dark-plate case
  // caught a real regression here first - a wide, genuinely near-black band
  // (this repo has no adversarial-enough real crop for it, only a synthetic
  // one) makes the local baseline near 0, so a margin alone can compute a
  // ceiling BELOW 0.42 and re-zero text that the original constant always
  // passed. `localBg + margin` only ever RAISES the ceiling above the floor,
  // for a plate brighter than the floor already assumed; it never lowers it.
  // Re-run frames.test.js, nameplate_fill_sweep.js, and
  // tools/real_frame_eval/rowfind_parity.py's dark-plate corpus (wherever
  // screenshots/ is available) before changing any constant below.
  var NAME_FILL_FLOOR = 0.42;
  var NAME_FILL_MARGIN = 0.30;
  var NAME_RUN_FRAC = 0.35;   // rows scoring this share of the peak join a run

  // findNameRow(rgba, w, h) -> { y, h } | null
  //
  // `rgba` is the search band of ONE side's strip, w x h, as ImageData.data.
  // Returns the text row's position within that band.
  //
  // Text is a row with many horizontal light/dark transitions that does not
  // fill much MORE of the strip than the plate around it already does; the
  // run of such rows sitting in the quietest surroundings wins, because
  // nothing else in the band has empty rows above and below it.
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
    }

    // Each row's own LOCAL plate baseline: mean fill of a window of nearby
    // rows, gapped around the row itself so a genuine text row's own
    // coverage cannot inflate the baseline it is being judged against. The
    // window scales with the band's height the same way the scoreboard's
    // blur radius scales with its crop - both are standing in for "about the
    // size of a glyph's neighbourhood," not a fixed pixel count.
    var WIN = Math.max(6, Math.round(h * 0.2)), GAP = Math.max(2, Math.round(WIN * 0.25));
    for (y = 0; y < h; y++) {
      var s = 0, n = 0;
      for (var k2 = Math.max(0, y - WIN); k2 <= Math.min(h - 1, y + WIN); k2++) {
        if (Math.abs(k2 - y) <= GAP) continue;
        s += fill[k2]; n++;
      }
      var localBg = n ? s / n : fill[y];
      var ceiling = Math.min(0.97, Math.max(NAME_FILL_FLOOR, localBg + NAME_FILL_MARGIN));
      score[y] = fill[y] <= ceiling ? tr[y] : 0;
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

  // applyNameContrast(d) -> undefined (mutates d in place)
  //
  // `d` is an ImageData.data RGBA buffer for a name crop, already upscaled.
  // Stretches luminance to the crop's own observed 2nd-98th percentile range
  // instead of a fixed formula.
  //
  // 2026-09-15: the previous recipe, `(g-128)*1.5+140` clamped to [0,255],
  // assumed glyph and plate sit far apart in luminance - true for a dark
  // plate (background near 0, glyph near 250, the pair this was tuned
  // against) but false for a bright/team-coloured one, where both already
  // sit near 255 and the fixed formula clips them together to flat white:
  // findNameRow's fix (same date) locates the row correctly, but there was
  // nothing left in the crop for tesseract to read. Stretching to what the
  // crop ITSELF actually contains adapts to either case without needing to
  // know which one a given plate is.
  //
  // Measured (tools/replay_bot/nameplate_contrast_sweep.js): on 20 known-bad
  // bright-plate crops this raises slots landing a confident name match from
  // 5% to 11% - a real but partial recovery, not a full fix (most of these
  // crops are still unreadable; some may be a harder problem than contrast,
  // e.g. an outlined/embossed glyph style that stays hollow even at full
  // contrast). On 20 already-good dark-plate crops it is not merely neutral
  // but BETTER - 84/100 confident matches against the old formula's 79/100 -
  // with a single isolated regression, so this replaces the old recipe
  // everywhere rather than branching on plate brightness. A
  // stretch-then-morphological-close variant (meant to solidify a hollow
  // glyph into a filled one) measured WORSE (7%) and was dropped - re-run
  // that harness before trying morphology again.
  function applyNameContrast(d) {
    var n = d.length / 4, i, p;
    if (!n) return;
    var lum = new Float32Array(n);
    for (i = 0, p = 0; p < d.length; i++, p += 4) {
      lum[i] = 0.299 * d[p] + 0.587 * d[p + 1] + 0.114 * d[p + 2];
    }
    var sorted = Float32Array.from(lum).sort();
    var lo = sorted[Math.floor(n * 0.02)];
    var hi = sorted[Math.floor(n * 0.98)];
    var range = hi - lo;
    // A featureless crop (no row, no glyph, just plate) has next to no
    // spread between its 2nd and 98th percentile - stretching THAT to fill
    // 0-255 would manufacture contrast out of sensor noise, not reveal any.
    // Left as plain luminance instead of amplified into speckle; either way
    // tesseract reads nothing from it, but this stays predictable rather
    // than surprising (findNameRow already returns null rather than invent
    // a row for exactly this case - same instinct, applied here).
    if (range < 8) {
      for (i = 0, p = 0; p < d.length; i++, p += 4) d[p] = d[p + 1] = d[p + 2] = lum[i];
      return;
    }
    for (i = 0, p = 0; p < d.length; i++, p += 4) {
      var v = (lum[i] - lo) * 255 / range;
      v = v < 0 ? 0 : v > 255 ? 255 : v;
      d[p] = d[p + 1] = d[p + 2] = v;
    }
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
      var fx = cell.x + cell.w * LF, fy = cell.y, fw = cell.w * (1 - LF - RF), fh = cell.h * TF;
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
    // Grayscale + 6x upscale + applyNameContrast's percentile stretch lift
    // the ~10px text enough for OCR.
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
      var im = cx.getImageData(0, 0, cv.width, cv.height);
      applyNameContrast(im.data);
      cx.putImageData(im, 0, 0);
      return cv;
    }

    // Find the game render area inside the capture, stripping near-black
    // letterbox / pillarbox (odd aspect ratios / resolutions), capped at 20%
    // per edge. Does NOT strip a window title bar (it isn't black) - share
    // the whole screen for that.
    // The replay-code crop: upscale hard, then push contrast, exactly as
    // nameCanvas does for HUD names. The code sits on a semi-transparent plate
    // over arbitrary game art - the same problem, and contrast is what solved
    // it there (15/90 reads to 77/90).
    //
    // The contrast level is the CALLER'S, because no single one works. A hard
    // boost rescued the screenshot frames and destroyed a live one - the plate
    // is semi-transparent, so what sits behind it decides whether a boost
    // sharpens the glyphs or saturates them away. readReplayCode tries several
    // and takes them only when they agree; see there.
    function codeCanvas(frame, box, contrast) {
      var sc = 6;
      contrast = contrast || 1.0;
      var cv = ctx.doc.createElement('canvas');
      cv.width = Math.max(1, Math.round(box.w * sc));
      cv.height = Math.max(1, Math.round(box.h * sc));
      var cx = cv.getContext('2d', { willReadFrequently: true });
      cx.imageSmoothingEnabled = true; cx.imageSmoothingQuality = 'high';
      cx.drawImage(frame, box.x, box.y, box.w, box.h, 0, 0, cv.width, cv.height);
      var im = cx.getImageData(0, 0, cv.width, cv.height), d = im.data;
      for (var i = 0; i < d.length; i += 4) {
        var g = 0.299 * d[i] + 0.587 * d[i + 1] + 0.114 * d[i + 2];
        g = (g - 128) * contrast + 140; g = g < 0 ? 0 : g > 255 ? 255 : g;
        d[i] = d[i + 1] = d[i + 2] = g;
      }
      cx.putImageData(im, 0, 0);
      return cv;
    }

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
      codeCanvas: codeCanvas,
      detectContentRect: detectContentRect,
      stopCapture: stopCapture,
      togglePreview: togglePreview,
      readyForCapture: readyForCapture,
    };
  }

  var Mod = { make: make, findNameRow: findNameRow, findNameSpan: findNameSpan, applyNameContrast: applyNameContrast };

  if (typeof module !== 'undefined' && module.exports) module.exports = Mod;
  else global.OWDBFrames = Mod;
})(typeof self !== 'undefined' ? self : this);

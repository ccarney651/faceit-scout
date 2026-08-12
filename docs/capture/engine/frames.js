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

    // Name bar sits at ~48-90% of each portrait cell's height (mirror of the
    // .exe's read_hud_names); grayscale + 6x upscale + a light contrast
    // stretch lift the ~10px text enough for OCR.
    function nameCanvas(frame, cell) {
      var padX = Math.max(4, Math.round(cell.w * 0.05));
      var sx = Math.max(0, cell.x - padX), sy = cell.y + cell.h * 0.48, sw = cell.w + 2 * padX, sh = cell.h * 0.42, sc = 6;
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
      nameCanvas: nameCanvas,
      detectContentRect: detectContentRect,
      stopCapture: stopCapture,
      togglePreview: togglePreview,
      readyForCapture: readyForCapture,
    };
  }

  var Mod = { make: make };

  if (typeof module !== 'undefined' && module.exports) module.exports = Mod;
  else global.OWDBFrames = Mod;
})(typeof self !== 'undefined' ? self : this);

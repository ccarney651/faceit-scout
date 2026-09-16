// tools/replay_bot/screen.js
// Recognising which screen the client is on, so a chunk is never clicked blind.
//
// EVERY CASCADE TONIGHT STARTED THE SAME WAY: the client was not where the
// chunk assumed, the chunk clicked anyway, and the coordinates meant something
// else there. A replay that opened without being noticed became an import
// played from inside a replay; a leave-replay whose click missed left the ESC
// menu up, and the next import clicked SOCIAL and CAREER PROFILE instead. Each
// one cost live codes, and none of them was detectable from the outputs - only
// from the frames afterwards.
//
// A chunk therefore carries a FINGERPRINT of the screen it was played from, and
// playback refuses when the screen does not match. The fingerprint is a 32x18
// greyscale thumbnail: coarse enough that a different replay list or a moved
// mouse does not matter, specific enough that a menu, a replay and a loading
// screen are plainly different pictures.
//
// It is LEARNED rather than recorded. Chunks recorded before this existed have
// none, and re-recording open-import costs a replay code - so the first time a
// chunk demonstrably works, the screen it started from is stored, and every run
// after that is checked against it.

(function (global) {
  'use strict';

  var createCanvas = require('@napi-rs/canvas').createCanvas;

  var W = 32;
  var H = 18;

  // Two screens are the same screen below this mean absolute difference, per
  // pixel, on a 0-255 scale. A replay list with different rows in it moves a
  // few points; a menu against a replay moves tens.
  var SAME = 18;

  function thumb(img) {
    var cv = createCanvas(W, H);
    var cx = cv.getContext('2d', { willReadFrequently: true });
    cx.imageSmoothingEnabled = true;
    cx.drawImage(img, 0, 0, W, H);
    var d = cx.getImageData(0, 0, W, H).data;
    var out = new Array(W * H);
    for (var i = 0, k = 0; i < d.length; i += 4, k++) {
      out[k] = Math.round(0.299 * d[i] + 0.587 * d[i + 1] + 0.114 * d[i + 2]);
    }
    return out;
  }

  // Mean absolute difference between two thumbnails. Null for anything that is
  // not a pair of comparable fingerprints, because "no fingerprint" must never
  // read as "matches".
  function distance(a, b) {
    if (!a || !b || a.length !== b.length || !a.length) return null;
    var sum = 0;
    for (var i = 0; i < a.length; i++) sum += Math.abs(a[i] - b[i]);
    return sum / a.length;
  }

  function looksLike(a, b, tolerance) {
    var d = distance(a, b);
    if (d === null) return { known: false, same: false, distance: null };
    var tol = tolerance === undefined ? SAME : tolerance;
    return { known: true, same: d <= tol, distance: d };
  }

  var Mod = {
    W: W,
    H: H,
    SAME: SAME,
    thumb: thumb,
    distance: distance,
    looksLike: looksLike,
  };

  if (typeof module !== 'undefined' && module.exports) module.exports = Mod;
  else global.OWDBReplayScreen = Mod;
})(typeof self !== 'undefined' ? self : this);

// tools/replay_bot/calib.js
// The frozen HUD geometry, and the smoke check that guards it.
// See specs/2026-09-08-replay-bot-design.md §5.
//
// PROVENANCE OF THESE NUMBERS, which is the only thing that makes them valid:
// captured 2026-09-08 on the rig, from a getDisplayMedia share of the OVERWATCH
// WINDOW (not the display) at 2560x1440, borderless windowed, by running
// auto-calibrate, pressing "Use boxes", confirming the page said calibration
// looked good at 10/10, and only then reading boxes.a/boxes.b out of the page.
//
// Every one of those steps matters, and one of them nearly went wrong:
//
//   Auto-calibrate reports "10/10 portraits confident" for a detection it has
//   NOT yet committed. Read boxes.a at that moment and you get the AUTO_STRIPS
//   default - (129.536, 119.808, 660.224, 97.2) - which is shifted right by
//   about half a portrait and hangs down onto the health pips. It looks like a
//   real measurement and it is not one. Drawn over the frame the error is
//   obvious; as a number it is invisible.
//
// So: do not edit these by hand, do not transfer them from a display share, and
// do not re-derive them from a screenshot. Re-run the bootstrap.

(function (global) {
  'use strict';

  var FROZEN = {
    frame: { w: 2560, h: 1440 },
    boxes: {
      a: { x: 55.33490566037736, y: 98, w: 706.25, h: 103.97607478673905 },
      b: { x: 1799.3349056603774, y: 95, w: 706.25, h: 108.85047245433347 },
    },
    // Mirrors refs.json. The page defaults these and then overwrites them from
    // the refs library, so they are recorded from the live page, not the
    // literals in index.html.
    ref: { REF_W: 64, REF_H: 36, LF: 0.42, TF: 0.45, PAD: 2 },
  };

  // The five portrait crops for one side, left to right.
  //
  // A row cell is a fifth of the box. The crop then drops the left LF of it,
  // which is the ult-charge number, and keeps only the top TF, which is the
  // portrait - below that sit the name plate and the health pips, and both are
  // poison for a matcher trained on faces.
  function cells(side) {
    var b = FROZEN.boxes[side];
    var cw = b.w / 5;
    var out = [];
    for (var i = 0; i < 5; i++) {
      out.push({
        x: b.x + i * cw + cw * FROZEN.ref.LF,
        y: b.y,
        w: cw * (1 - FROZEN.ref.LF),
        h: b.h * FROZEN.ref.TF,
      });
    }
    return out;
  }

  // Cheap per-run guard. Not a calibration - the rig does not change between
  // runs, but Blizzard's HUD can, and the bot runs right after every patch
  // because that is when codes are freshest. Refusing loudly beats writing
  // hundreds of maps of confident wrong comps.
  function check(frame) {
    if (frame.w !== FROZEN.frame.w || frame.h !== FROZEN.frame.h) {
      return {
        ok: false,
        reason: 'frame is ' + frame.w + 'x' + frame.h + ', bootstrap froze ' +
          FROZEN.frame.w + 'x' + FROZEN.frame.h + ' - re-run the bootstrap',
      };
    }
    return { ok: true, reason: null };
  }

  var Mod = {
    FROZEN: FROZEN,
    cells: cells,
    check: check,
  };

  if (typeof module !== 'undefined' && module.exports) module.exports = Mod;
  else global.OWDBReplayCalib = Mod;
})(typeof self !== 'undefined' ? self : this);

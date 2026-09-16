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
    //
    // RF is refs.json's right_fraction (owdb/match.py's CELL_RIGHT_TRIM_FRACTION):
    // face_subrect trims this off the right of every cell too, clearing the
    // HUD's card gap-seam. Added 2026-09-12 - refs.json got a matching rebuild
    // in the training pipeline (commit 4b2ad24) but this file didn't, so every
    // live crop was ~6% wider than the ref it was scored against.
    ref: { REF_W: 64, REF_H: 36, LF: 0.42, TF: 0.45, RF: 0.06, PAD: 2 },

    // The replay scrubber, measured on the same rig and frame. y0..y1 are the
    // bar's core rows, found by scanning for the band of steady mid luminance
    // (~73) that sits below the event-tick band (~1230-1246) and above the
    // controls.
    //
    // blueLead is how far the blue channel must exceed red for a pixel to read
    // as a between-round break. Breaks are detected by COLOUR because the bar's
    // brightness is polluted by ticks and the playhead, which are bright white.
    //
    // minRunPx discards runs too narrow to be a real break - the playhead knob
    // is a few pixels of blue, and taking it for a boundary would cut a round
    // in half and invent a segment that never happened.
    //
    // playheadBright/playheadMinPx/playheadMaxPx find the knob, which is how the
    // bot checks where a seek actually landed rather than trusting that it
    // landed. In all six frames retained from the first live run the bar's core
    // rows held exactly ONE run brighter than 200: the knob, 40px wide, at luma
    // 255, with the played side at ~186 and the unplayed side at ~77. Event
    // ticks sit above these rows and do not intrude.
    //
    // playheadMinPx/playheadMaxPx bound how wide a bright run may be and still
    // be the knob. With the media controls DOWN there is no knob, and the bar's
    // y-band is just scenery - on XTK7MM (2026-09-10) that scenery held a 537px
    // run of sunlit pavement AND a 27px offcut, either of which read as the
    // playhead and let ensureEventsViewer press K at a closed panel. Every knob
    // actually drawn across the corpus measures 39-65px (parked at the far left
    // it is 39; the widest, on a dark map, 65), so 33-100 keeps all of them and
    // rejects both of XTK7MM's false runs and 4TNEAJ's 14px one.
    timeline: {
      x0: 73, x1: 2449, y0: 1254, y1: 1262, blueLead: 20, minRunPx: 15,
      playheadBright: 200, playheadMinPx: 33, playheadMaxPx: 100,
    },

    // The replay events viewer - the ROUND 1/2/3 panel down the left.
    //
    // THE SCRUBBER ONLY DRAWS ROUND BREAKS WHILE THIS PANEL IS OPEN. With it
    // closed the bar is one unbroken run, and timeline.js reads a three-round
    // Control map as a single continuous segment - confidently, and wrongly.
    //
    // K toggles it, so a blind press is as likely to close it as open it. The
    // bot measures instead: the panel is a large pale rectangle, and the
    // fraction of bright pixels in this box separates the two states.
    //
    // MEASURED ON TWO MAPS, AND THE SPREAD IS THE POINT:
    //
    //     Control, Busan     0.755 open   0.211 closed
    //     Escort, Gibraltar  0.504 open   0.024 closed
    //
    // The panel is translucent, so how bright it reads depends on the map
    // behind it. The first threshold was 0.5, chosen from the Busan pair alone,
    // and Gibraltar's open panel read 0.504 - it passed by four thousandths.
    // A map one shade brighter behind the panel would have aborted the run.
    //
    // 0.35 sits above the highest closed reading and below the lowest open one,
    // with room either side. If a future map lands between 0.211 and 0.504,
    // this stops being a threshold problem and becomes a "measure the panel by
    // pressing K and comparing" problem.
    // minBrightFrac only answers "was it ALREADY open"; whether a press worked
    // is decided by the rise, in driver.ensureEventsViewer. See the readings
    // there - an open panel on one map reads dimmer than a closed one on
    // another, so the level alone cannot separate the two states.
    // minPanelRows is the test; brightAt/minBrightFrac survive only because the
    // probes still print a brightness. A row counts as part of a dropdown when
    // it is uniform across the box (sd under flatSd) AND light (mean over
    // panelRowLum). Both halves are load-bearing, and both were learned the
    // expensive way.
    //
    // FLATNESS ALONE WAS MEASURED ON THREE MAPS AND WRONG ON SIX FRAMES. The
    // first cut counted uniform rows and nothing else, over the ROUND rows:
    // closed 0.000/0.120/0.000 against open 0.595/0.690/0.345, so 0.22 looked
    // like it sat in a gap. Over the whole retained corpus it is not there - a
    // night sky, a loading screen, a black frame and the ESC MENU are all
    // perfectly uniform, and read 0.490 to 1.000.
    //
    // REQUIRING LIGHT ROWS FIXED THAT AND LEFT A WORSE PROBLEM: THE ROUND ROWS
    // ARE NOT THE SAME PANEL ON EVERY MAP. Push and Flashpoint play one long
    // round, Control up to three, Escort and Hybrid at least two. Three-round
    // frames read 0.340 and up; a live one-round map read 0.170 against a
    // threshold of 0.15, and would have been refused on a panel that was
    // plainly open on screen.
    //
    // The dropdowns do not vary. Measured over every labelled frame - 12 open,
    // 16 shut, one of the pairs taken seconds apart on one map with only K
    // pressed between them - the weakest open reading is 0.587 and NOTHING
    // shut registers at all. 0.25 is less than half the weakest open, and the
    // shut side has no floor to clear.
    eventsPanel: {
      // The panel's two dropdowns - the player picker and ALL EVENTS - which
      // are there whenever it is open, on every map. Measured as two boxes
      // because there is a gap between them and a row crossing it is not
      // uniform, which reads as no panel at all.
      dropdowns: [
        { x0: 40, x1: 250, y0: 212, y1: 258 },
        { x0: 310, x1: 520, y0: 212, y1: 258 },
      ],
      minPanelRows: 0.25, flatSd: 12, panelRowLum: 170,
      // The old box, over the ROUND rows. panelBrightFraction still reads it
      // and the probes still print it; nothing decides anything on it.
      x0: 30, x1: 530, y0: 280, y1: 480,
      minBrightFrac: 0.35, brightAt: 170,
    },
  };

  // Whether a replay is on screen at all, from the team tint crop.js read off
  // the two portrait bands.
  //
  // Both sides must be tinted: a black loading screen reads 0.0 on each, and a
  // replay reads tens. This does NOT depend on the media controls being up,
  // which is the whole point - they are hidden when a replay opens.
  //
  // 15 was chosen against a smallest-measured-margin of 29, and it holds: over
  // every frame known to be a replay because its events panel is open, the
  // dimmest reads 31.3 against exactly 0.0 for a loading screen, a black frame
  // and the ESC menu. What had drifted was the REGION, not the number - see
  // crop.hudTint, and the code it cost.
  var HUD_TINT = 15;

  function hudPresent(tint) {
    return tint.a >= HUD_TINT && tint.b >= HUD_TINT;
  }

  // Whether the events viewer is open, given the panel-row fraction crop.js
  // read out of the box. See crop.panelRowFraction for why it is neither
  // brightness nor flatness on its own.
  function eventsViewerOpen(panelRows) {
    return panelRows >= FROZEN.eventsPanel.minPanelRows;
  }

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
        w: cw * (1 - FROZEN.ref.LF - FROZEN.ref.RF),
        h: b.h * FROZEN.ref.TF,
      });
    }
    return out;
  }

  // The five FULL slot columns for one side, left to right - unlike cells(),
  // not narrowed past the ult-charge number and not shortened to the
  // portrait. The name plate sits centred under the whole slot, including the
  // space cells() drops for the portrait match, so nameplate.js's per-slot
  // span-finding needs this box instead: cropping to cells()'s narrower x
  // clips the first letter of a name that starts under where the ult-charge
  // number was.
  function slots(side) {
    var b = FROZEN.boxes[side];
    var cw = b.w / 5;
    var out = [];
    for (var i = 0; i < 5; i++) {
      out.push({ x: b.x + i * cw, y: b.y, w: cw, h: b.h });
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
    HUD_TINT: HUD_TINT,
    hudPresent: hudPresent,
    cells: cells,
    slots: slots,
    check: check,
    eventsViewerOpen: eventsViewerOpen,
  };

  if (typeof module !== 'undefined' && module.exports) module.exports = Mod;
  else global.OWDBReplayCalib = Mod;
})(typeof self !== 'undefined' ? self : this);

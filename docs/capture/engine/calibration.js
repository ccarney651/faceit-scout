// docs/capture/engine/calibration.js
// Screen-calibration UI shared by index.html and scrim.html: locating the
// two 5-portrait strips (auto or by hand), previewing a candidate placement
// before it's committed, and drawing/rescaling the calibration overlay.
//
// Extracted from the two hand-maintained forks (see
// tools/capture_divergence.py): boxesFromStrips, scoreBoxes, commitCal,
// clearCalPreview, retryCal, enterFsCal and calOk were byte-identical.
// calMsg diverged by +15 chars but only cosmetically - index.html used a
// literal em dash, scrim.html a — escape; same string either way.
//
// autoCalibrate (-281), drawOverlay (+191) and pickBox (+186) diverged for
// real, and NOT in index.html's favour: scrim.html is ahead here. It carries
// a scoreboard/score_readout calibration feature (the "Set SCOREBOARD box" /
// "Set SCORE box" buttons, wired only in scrim.html) that index.html has no
// UI for. All three took the scrim.html body because each addition is a
// strict superset. renderCalPreview's +20 was read in full and is the same
// cosmetic em-dash-escape drift as calMsg, not a behaviour change.
//
// CORRECTION (fix round 1): the scoreboard/score_readout handling in
// drawOverlay/autoCalibrate is NOT inert on index.html just because
// index.html has no button that SETS those keys. Both pages read the SAME
// localStorage['owdb_cap_boxes'] key (index.html:614, scrim.html:509,
// pre-existing, unrelated to this extraction) - so if the same browser ever
// calibrated scrim.html's scoreboard/score_readout boxes, index.html's
// `boxes` picks them up too, and would render/carry-forward a box it has no
// UI to show or clear. `ctx.boxKeys` (below) closes that gap by filtering at
// read time instead of relying on "the key is never set here", which was
// only true in isolation, not in a shared-profile browsing session.
//
// pendingCal (the candidate placement awaiting the scout's "Use these
// boxes" confirmation) and AUTO_STRIPS (the fixed HUD-strip geometry, a
// mirror of owdb/calibrate.py AUTO_STRIPS) were page-scoped globals in both
// forks but read only by functions in this cluster, so they moved in as
// module state instead of ctx - see work/wctx in engine/frames.js for the
// precedent of instance-private state that isn't part of ctx.
//
// boxes/drawMode/dragS/dragC (the persisted box store and the in-progress
// manual-drag state) stay page-level globals, exactly like engine/frames.js
// leaves boxes/selectedCode alone: each page's own mousedown/mousemove/
// mouseup listeners and frames.js's readyForCapture also read or write them,
// so this module reads/writes them as free variables instead of importing
// them through ctx. The same is true of bestMatch/readComp (hero-matching,
// not yet extracted), REFS, and the page's own selfTest/updateBtns/
// setStageHint - all resolved at call time, after the page has defined
// them, via the shared global lexical scope classic <script> tags get.
//
// ctx = {doc, video, ov, octx, boxKeys} - doc/video/ov/octx are the DOM
// handles this module can't reach any other way (a Node test harness has no
// document/canvas). boxKeys is the list of `boxes` keys THIS PAGE owns
// (index.html: ['a','b']; scrim.html: ['a','b','scoreboard','score_readout']).
// It exists because both pages read the SAME localStorage key
// ('owdb_cap_boxes', pre-existing, not owned by this module) - so `boxes` on
// index.html can still contain a leftover boxes.scoreboard/score_readout if
// the same browser was ever used to calibrate scrim.html. Without boxKeys,
// drawOverlay/autoCalibrate would render/carry-forward a box the current
// page has no UI to set or clear, which is a real visible regression, not a
// hypothetical one. Every other dependency is a free-variable lookup, same
// convention as engine/frames.js.
//
// Works as a browser global (`window.OWDBCalibration`) and as a CommonJS
// module for node:test / pytest.

(function (global) {
  'use strict';

  // Mirror of owdb/calibrate.py AUTO_STRIPS: the HUD sits at fixed screen
  // fractions, so the two 5-portrait strips derive from the captured
  // resolution alone - no dragging needed for the common case.
  var AUTO_STRIPS = { a: [0.0506, 0.0832, 0.2579, 0.0675], b: [0.6912, 0.0818, 0.2573, 0.0705] };

  function make(ctx) {
    // {boxes, ok} - candidate placement awaiting the scout's confirmation;
    // never written to the persisted `boxes` until commitCal(). Instance
    // state (see frames.js's work/wctx) because nothing outside this
    // cluster reads it.
    var pendingCal = null;

    // The 'a'/'b' portrait boxes are universal; anything else in
    // ctx.boxKeys (scrim.html's 'scoreboard'/'score_readout') is page-owned
    // extra UI. Keys NOT in ctx.boxKeys are never drawn or carried forward,
    // even if present in the shared localStorage-derived `boxes` object -
    // see the module header for why that can happen.
    function extraBoxKeys() {
      return (ctx.boxKeys || []).filter(function (k) { return k !== 'a' && k !== 'b'; });
    }

    // THE VERTICAL FRACTIONS ARE PROJECTED AGAINST WIDTH, NOT HEIGHT.
    //
    // AUTO_STRIPS was measured on 16:9, where height === width * 9/16, so this
    // is algebraically identical there - a no-op on every capture that already
    // worked, which is why it is safe. It only differs when the frame is NOT
    // 16:9, and a window capture routinely is not: the game renders the HUD to
    // the width it is given, so a squashed frame must not drag the HUD upward.
    //
    // Measured against a live 2570x1393 window capture (aspect 1.845) on
    // 2026-09-07, the height-relative form put the strips 10-12px too high and
    // 6px too short, and auto-calibrate plateaued at 4/10 portraits. It could
    // not correct itself because the sweep below stepped by 0.01 of height -
    // 13.9px there, COARSER THAN THE ERROR, so it could only choose between
    // 10px short and 4px over. Hence the finer second pass, too.
    //
    // `dy` is a fraction of that same reference height, so the sweep's steps
    // stay proportional to the HUD rather than to the frame.
    // ONE strip. Each is searched INDEPENDENTLY - see autoCalibrate.
    function stripBox(R, side, dx, dy) {
      var st = AUTO_STRIPS[side], refH = R.w * 9 / 16;
      return { x: R.x + (st[0] + dx) * R.w, y: R.y + (st[1] + dy) * refH,
               w: st[2] * R.w, h: st[3] * refH };
    }

    function boxInFrame(b, W, H) {
      return !!b && b.x >= 0 && b.y >= 0 && b.x + b.w <= W && b.y + b.h <= H;
    }

    // {distinct, sum} over ONE strip's five cells.
    function scoreStrip(frame, b, side) {
      ensureWork();
      var seen = {}, distinct = 0, sum = 0, i;
      for (i = 0; i < 5; i++) {
        var gp = cellGrayPadded(frame, { x: b.x + i * b.w / 5, y: b.y, w: b.w / 5, h: b.h });
        if (cellRms(gp) < MIN_RMS) continue;
        var m = bestMatch(gp, side, true);
        sum += m.score;
        if (m.score >= CONFIDENT && !seen[m.name]) { seen[m.name] = 1; distinct++; }
      }
      return { distinct: distinct, sum: sum };
    }

    function boxesFromStrips(R, dx, dy) {
      var o = {}, refH = R.w * 9 / 16;
      ['a', 'b'].forEach(function (s) {
        var st = AUTO_STRIPS[s], fx = st[0], fy = st[1], fw = st[2], fh = st[3];
        o[s] = { x: R.x + (fx + dx) * R.w, y: R.y + (fy + dy) * refH, w: fw * R.w, h: fh * refH };
      });
      return o;
    }

    // EVERY CELL MUST BE INSIDE THE FRAME BEFORE IT IS SCORED.
    //
    // Measured in the field on 2026-09-07: a candidate at y=-27.9, hanging off
    // the top of the video, scored 10/10 confident and beat the real portraits
    // at y=37.2. drawImage outside the source bounds yields uniform black, and
    // centred and L2-normalised that correlates strongly with almost any
    // reference - so the most confident placement the scorer could find was one
    // not looking at the picture at all.
    //
    // Calibration only escaped it because that offset lay outside the coarse
    // sweep's range. That is luck, and it is the reason the range must not be
    // widened without this guard in front of it.
    function withinFrame(cand, W, H) {
      return ['a', 'b'].every(function (side) {
        var b = cand[side];
        return !!b && b.x >= 0 && b.y >= 0 && b.x + b.w <= W && b.y + b.h <= H;
      });
    }

    // BOTH ranking metrics from ONE pass over the ten cells.
    //
    // The sweep needs the confident-cell count as well as the summed score, and
    // the obvious way to get it - calling calOk() per candidate - is a trap that
    // cost a measured, user-visible freeze on the Auto-calibrate button.
    // calOk() goes through readComp(), which per call does a FULL-FRAME
    // grabFrame() (3.6 megapixels here), builds ten DOM rows with innerHTML,
    // and matches with fast=false, which tries NINE offsets per cell instead of
    // one. Over a hundred-plus candidates that is roughly a hundredfold blowup
    // of what the sweep is supposed to cost.
    //
    // So: count here, in the loop that is already computing the scores, using
    // the same centre-only match the sweep has always used. The threshold is
    // CONFIDENT, matching calOk's. Centre-only scores run at or below
    // best-of-nine, which makes this if anything a stricter test - and stricter
    // is what a calibration sweep wants, because a box that only matches when
    // the matcher is allowed to slide is a box that is not aligned.
    var CONFIDENT = 0.55;

    // RANKING COUNTS DISTINCT HEROES PER SIDE, NOT CONFIDENT CELLS.
    //
    // Overwatch 2 is role locked, so a team cannot field the same hero twice:
    // five cells on one side must resolve to five different heroes. Noise
    // cannot fake that. A confident-CELL count can be faked trivially, and was
    // - measured on a real frame the operator exported on 2026-09-07:
    //
    //   ok=6 distinct=2  y=48.0   "Torbjorn" x8            <- won on ok
    //   ok=5 distinct=5  y=127.5  the actual ten portraits  <- lost
    //   ok=5 distinct=2  y=37.2   "Ashe" x8
    //
    // The correct placement read ten plausible distinct heroes and was beaten
    // by one reading the same hero eight times, because ten barely-passing
    // cells outrank nine strong ones. Scored over the 36 frames in
    // screenshots/ by distinct heroes - the honest measure, since it is not the
    // quantity being optimised:
    //
    //   rank by ok        mean 4.50   8+: 11/38
    //   rank by sum       mean 5.74   8+: 17/38
    //   rank by distinct  mean 6.16   8+: 18/38   <- shipped
    //
    // A low-contrast crop is refused outright: a near-uniform region has a tiny
    // L2 norm, and dividing by it turns noise into a confident correlation.
    // Real portrait cells never measured below 25.8 RMS over those frames, so
    // 12 discards none of them. It does NOT catch the case above - those crops
    // are textured, just not portraits - which is why the distinct test carries
    // the weight and this only closes the flat-region hole.
    var MIN_RMS = 12;

    function cellRms(gp) {
      var W = REF_W + 2 * PAD, m = 0, ss = 0, n = REF_W * REF_H, i, x, y, v;
      for (y = 0; y < REF_H; y++) for (x = 0; x < REF_W; x++) m += gp[(y + PAD) * W + x + PAD];
      m /= n;
      for (y = 0; y < REF_H; y++) for (x = 0; x < REF_W; x++) { v = gp[(y + PAD) * W + x + PAD] - m; ss += v * v; }
      return Math.sqrt(ss / n);
    }

    // {ok, distinct, sum} in ONE pass over the ten cells - see the note above
    // scoreBoxes for why this may not call calOk() per candidate.
    function scoreCandidate(frame, bxs) {
      ensureWork();
      var sum = 0, ok = 0, distinct = 0;
      ['a', 'b'].forEach(function (side) {
        var b = bxs[side], seen = {}, i;
        for (i = 0; i < 5; i++) {
          var cell = { x: b.x + i * b.w / 5, y: b.y, w: b.w / 5, h: b.h };
          var gp = cellGrayPadded(frame, cell);
          if (cellRms(gp) < MIN_RMS) continue;
          var m = bestMatch(gp, side, true);
          sum += m.score;
          if (m.score >= CONFIDENT) {
            ok++;
            if (!seen[m.name]) { seen[m.name] = 1; distinct++; }
          }
        }
      });
      return { ok: ok, distinct: distinct, sum: sum };
    }

    // Sum of the 10 cells' best centre-match scores - higher = better aligned.
    // Kept as-is for callers outside the sweep.
    function scoreBoxes(frame, bxs) {
      return scoreCandidate(frame, bxs).sum;
    }

    // Confidence helper shared by the post-commit self-test and the
    // pre-commit preview: how many of the 10 portrait cells score
    // confidently (>= 0.55).
    // DISTINCT confident heroes per side, for the same reason the sweep ranks
    // that way: the operator was shown "9/10 portraits confident" over a
    // placement that had read the same hero ten times. A number that can say 9
    // when every row is wrong is worse than no number.
    function calOk(bx) {
      var comp = readComp(bx);
      if (!comp) return null;
      var total = 0;
      [comp.a, comp.b].forEach(function (side) {
        var seen = {};
        side.forEach(function (s) {
          if (s.score >= 0.55 && s.name && s.name !== '??') seen[s.name] = 1;
        });
        total += Object.keys(seen).length;
      });
      return total;
    }

    function calMsg(ok) {
      return ok >= 8 ? '<span class="ok">calibration looks good — ' + ok + '/10 portraits recognised.</span>'
        : ok >= 5 ? 'calibration: ' + ok + '/10 recognised — usable; nudge the boxes if some read ??.'
        : '<span class="warn">only ' + ok + '/10 recognised — boxes look misaligned; try Auto-calibrate, or drag them right on the portraits. If the preview is not showing the game at all, share the Overwatch window instead of the whole screen.</span>';
    }

    // Auto-calibrate: the HUD sits at fixed fractions of the screen (mirror
    // of owdb/calibrate.py AUTO_STRIPS), so the two 5-portrait strips derive
    // from the captured resolution - no dragging. Self-test then confirms
    // alignment.
    function autoCalibrate() {
      if (!ctx.video.videoWidth) {
        var w = '<span class="warn">Share your screen first.</span>';
        ctx.doc.getElementById('calhint').innerHTML = w; setStageHint(w); return;
      }
      var R = detectContentRect();
      var best = boxesFromStrips(R, 0, 0);
      // The strips are fixed screen fractions, but a window title bar or
      // HUD-position variance shifts everything. When the ref library is
      // loaded, sweep a small offset and keep the placement that recognises
      // the most portraits. No refs or no improvement => the base strips
      // (previous behaviour). Blind-safe.
      if (REFS.length) {
        var frame = grabFrame();
        var FW = ctx.video.videoWidth, FH = ctx.video.videoHeight;

        // EACH STRIP IS SEARCHED INDEPENDENTLY.
        //
        // A single shared (dx, dy) shifts both strips together, which cannot
        // correct a WIDTH error: the offset it leaves is f*(R.w - true_w),
        // small at the left strip's f=0.05 and large at the right strip's
        // f=0.69. On a frame the operator exported 2026-09-07 the two strips
        // wanted dx values 0.005 apart - about 13px - and the joint search
        // split the difference, placing the RIGHT strip correctly (five heroes,
        // all confirmed right by the operator) and the LEFT strip wrong (one of
        // five). Searched independently the left strip lands on the box that
        // operator had drawn by hand.
        //
        // RANKED BY DISTINCT HEROES, not by confident cells. Overwatch 2 is
        // role locked, so five cells on a side must be five different heroes
        // and noise cannot fake that; a confident-CELL count can be, and was -
        // a placement reading "Torbjorn" eight times outranked the real
        // portraits because ten barely-passing cells beat nine strong ones.
        //
        // Scored over screenshots/ with tools/real_frame_eval/calibrate_eval.py,
        // by distinct heroes (the honest measure - it is not what the search
        // optimises when ranking by ok or sum):
        //
        //   joint,     rank by ok        mean 4.50   <- what this replaces
        //   joint,     rank by sum       mean 5.74
        //   joint,     rank by distinct  mean 6.16
        //   per-strip, rank by distinct  mean 6.71   <- shipped
        //
        // Cost is unchanged: five cells per candidate instead of ten, and two
        // searches instead of one.
        // THE FINE STEP MUST BE FINER THAN THE MATCHER'S TOLERANCE.
        //
        // Measured on the operator's own crops 2026-09-07, sliding one strip
        // horizontally a pixel at a time against the real references:
        //
        //   LEFT  +8px  distinct=1   +10px distinct=3   +12px distinct=4
        //         +14px distinct=1
        //   RIGHT  +0px distinct=5    -4px distinct=0    +4px distinct=4
        //
        // The window in which a strip reads at all is about FOUR PIXELS wide.
        // The old fine step of 0.0025 is 6.4px on a 2570-wide frame and the
        // coarse step 12.85px, so the grid straddled that window and landed on
        // +6px or +19px - both distinct=1. It could not reach the answer.
        //
        // This is also why the right strip has always worked and the left never
        // has: AUTO_STRIPS' right fraction happens to be accurate, and its left
        // fraction is about 4px out - an error smaller than the step that was
        // supposed to correct it.
        //
        // FINE_SPAN 3 at 0.001 covers +/-0.003, more than the 0.0025 worst-case
        // distance from a coarse grid point. Over screenshots/, by distinct
        // heroes: 0.0025/span2 6.71, 0.001/span3 7.47, 0.001/span5 7.50,
        // 0.0005/span6 7.53 - the last two cost 2.5x and 3.5x the fine passes
        // for 0.03 and 0.06, which is noise.
        var COARSE = 0.005, SPAN_X = 4, SPAN_Y = 16, FINE = 0.001, FINE_SPAN = 3, STARTS = 2;
        var betterS = function (r, cur) {
          return r.distinct > cur.distinct
                 || (r.distinct === cur.distinct && r.sum > cur.sum);
        };

        ['a', 'b'].forEach(function (side) {
          var bestBox = stripBox(R, side, 0, 0);
          var bestS = boxInFrame(bestBox, FW, FH)
            ? scoreStrip(frame, bestBox, side) : { distinct: -1, sum: -Infinity };
          var list = [];
          for (var dyi = -SPAN_Y; dyi <= SPAN_Y; dyi++) {
            for (var dxi = -SPAN_X; dxi <= SPAN_X; dxi++) {
              var bx = stripBox(R, side, dxi * COARSE, dyi * COARSE);
              if (!boxInFrame(bx, FW, FH)) continue;
              list.push({ s: scoreStrip(frame, bx, side), dx: dxi * COARSE, dy: dyi * COARSE, box: bx });
            }
          }
          list.sort(function (p, q) {
            return (q.s.distinct - p.s.distinct) || (q.s.sum - p.s.sum);
          });
          for (var si = 0; si < STARTS && si < list.length; si++) {
            var seed = list[si];
            if (betterS(seed.s, bestS)) { bestS = seed.s; bestBox = seed.box; }
            for (var fy = -FINE_SPAN; fy <= FINE_SPAN; fy++) {
              for (var fx = -FINE_SPAN; fx <= FINE_SPAN; fx++) {
                var b2 = stripBox(R, side, seed.dx + fx * FINE, seed.dy + fy * FINE);
                if (!boxInFrame(b2, FW, FH)) continue;
                var r2 = scoreStrip(frame, b2, side);
                if (betterS(r2, bestS)) { bestS = r2; bestBox = b2; }
              }
            }
            if (bestS.distinct === 5) break;   // nothing can beat five of five
          }
          best[side] = bestBox;
        });
      }
      // scrim.html only: carry forward any already-set scoreboard/
      // score_readout boxes - auto-calibrate only re-places the two
      // portrait strips. Filtered by ctx.boxKeys so a leftover
      // boxes.scoreboard/score_readout from a shared browser profile is
      // never carried forward on a page that doesn't own those keys.
      extraBoxKeys().forEach(function (extra) { if (boxes[extra]) best[extra] = boxes[extra]; });
      // Preview BEFORE commit: show where the boxes WOULD go and how
      // confident the read is, so a bad placement is rejected instead of
      // silently saved. Nothing is written until the scout clicks "Use
      // these boxes".
      pendingCal = { boxes: best, ok: calOk(best) };
      renderCalPreview(); drawOverlay();
    }

    function renderCalPreview() {
      var p = ctx.doc.getElementById('calpreview');
      if (!p || !pendingCal) return;
      var ok = pendingCal.ok;
      var head = ok == null ? 'Auto-calibrate found the boxes — review the placement below.'
        : ok >= 8 ? '<span class="ok">' + ok + '/10 portraits confident — this looks right.</span>'
        : ok >= 5 ? ok + '/10 portraits confident — usable, but check the boxes below.'
        : '<span class="warn">only ' + ok + '/10 portraits confident — the placement is likely off.</span>';
      p.querySelector('.calprev-msg').innerHTML = head;
      p.style.display = 'block';
      ctx.doc.getElementById('calhint').innerHTML = head; setStageHint(head);
    }

    function commitCal() {
      if (!pendingCal) return;
      boxes = pendingCal.boxes; pendingCal = null;
      localStorage.setItem('owdb_cap_boxes', JSON.stringify(boxes));
      var p = ctx.doc.getElementById('calpreview'); if (p) p.style.display = 'none';
      drawOverlay(); updateBtns(); selfTest();
    }

    function retryCal() {
      if (!ctx.video.srcObject) { clearCalPreview(); return; }
      autoCalibrate();
    }

    function clearCalPreview() {
      pendingCal = null;
      var p = ctx.doc.getElementById('calpreview'); if (p) p.style.display = 'none';
      drawOverlay();
    }

    // Set which box we're about to draw, updating the hint in both the page
    // and the (fullscreen) stage. Used by the setup buttons and the
    // in-stage buttons alike. The scoreboard/score_readout branches are
    // scrim.html-only (its setSb/setSr buttons); `side` is never
    // 'scoreboard' or 'score_readout' on index.html, so they're inert there.
    function pickBox(side) {
      clearCalPreview(); drawMode = side;
      var t = side === 'a' ? 'Drag a box over the 5 BLUE (left) portraits.'
        : side === 'b' ? 'Drag a box over the 5 RED (right) portraits.'
        : side === 'scoreboard' ? 'Drag a box over the scrim scoreboard panel (top-left, below the portraits).'
        : 'Drag a box over the top-centre score readout (e.g. 2 - 3).';
      ctx.doc.getElementById('calhint').textContent = t; setStageHint(t);
    }

    // Fullscreen calibration: blow the preview up to the whole screen so the
    // boxes are easy to place on a 2K/4K monitor. The page's
    // fullscreenchange listener re-fits the overlay (fitOverlay/drawOverlay)
    // so it stays pixel-aligned with the enlarged video.
    function enterFsCal() {
      var s = ctx.doc.getElementById('stage');
      if (s.requestFullscreen) s.requestFullscreen().catch(function () {});
    }

    function fitOverlay() {
      ctx.ov.width = ctx.video.clientWidth; ctx.ov.height = ctx.video.clientHeight;
      drawOverlay();
    }

    function drawOverlay() {
      var octx = ctx.octx;
      octx.clearRect(0, 0, ctx.ov.width, ctx.ov.height);
      var s = scl();
      // During a calibration preview, draw the PROPOSED boxes (accent,
      // dashed) instead of the committed ones - the scout reviews the
      // candidate placement before committing it.
      var src = pendingCal ? pendingCal.boxes : boxes;
      ['a', 'b'].forEach(function (side) {
        if ((ctx.boxKeys || []).indexOf(side) === -1) return;
        var b = src[side]; if (!b) return;
        octx.strokeStyle = pendingCal ? css('--accent') : (side === 'a' ? css('--blue') : css('--red'));
        octx.lineWidth = 2; octx.strokeRect(b.x * s, b.y * s, b.w * s, b.h * s);
        octx.setLineDash(pendingCal ? [4, 3] : [3, 3]); octx.lineWidth = 1;
        for (var i = 1; i < 5; i++) {
          var x = (b.x + i * b.w / 5) * s;
          octx.beginPath(); octx.moveTo(x, b.y * s); octx.lineTo(x, (b.y + b.h) * s); octx.stroke();
        }
        octx.setLineDash([]);
      });
      // scrim.html only: filtered by ctx.boxKeys so a leftover
      // boxes.scoreboard/boxes.score_readout from a shared browser profile
      // (both pages read the same localStorage key) is never drawn on a
      // page that doesn't own those keys.
      extraBoxKeys().forEach(function (side) {
        var b = boxes[side]; if (!b) return;
        octx.strokeStyle = css('--accent'); octx.lineWidth = 2;
        octx.strokeRect(b.x * s, b.y * s, b.w * s, b.h * s);
      });
      if (dragS && dragC) {
        octx.strokeStyle = css('--accent'); octx.lineWidth = 2;
        octx.strokeRect(Math.min(dragS.x, dragC.x), Math.min(dragS.y, dragC.y), Math.abs(dragC.x - dragS.x), Math.abs(dragC.y - dragS.y));
      }
    }

    return {
      autoCalibrate: autoCalibrate,
      boxesFromStrips: boxesFromStrips,
      scoreBoxes: scoreBoxes,
      scoreCandidate: scoreCandidate,
      scoreStrip: scoreStrip,
      stripBox: stripBox,
      withinFrame: withinFrame,
      pickBox: pickBox,
      commitCal: commitCal,
      renderCalPreview: renderCalPreview,
      clearCalPreview: clearCalPreview,
      retryCal: retryCal,
      enterFsCal: enterFsCal,
      calMsg: calMsg,
      calOk: calOk,
      drawOverlay: drawOverlay,
      fitOverlay: fitOverlay,
    };
  }

  var Mod = { make: make };

  if (typeof module !== 'undefined' && module.exports) module.exports = Mod;
  else global.OWDBCalibration = Mod;
})(typeof self !== 'undefined' ? self : this);

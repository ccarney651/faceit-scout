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

    function scoreCandidate(frame, bxs) {
      ensureWork();
      var sum = 0, ok = 0;
      ['a', 'b'].forEach(function (side) {
        var b = bxs[side];
        for (var i = 0; i < 5; i++) {
          var cell = { x: b.x + i * b.w / 5, y: b.y, w: b.w / 5, h: b.h };
          var s = bestMatch(cellGrayPadded(frame, cell), side, true).score;
          sum += s;
          if (s >= CONFIDENT) ok++;
        }
      });
      return { ok: ok, sum: sum };
    }

    // Sum of the 10 cells' best centre-match scores - higher = better aligned.
    // Kept as-is for callers outside the sweep.
    function scoreBoxes(frame, bxs) {
      return scoreCandidate(frame, bxs).sum;
    }

    // Confidence helper shared by the post-commit self-test and the
    // pre-commit preview: how many of the 10 portrait cells score
    // confidently (>= 0.55).
    function calOk(bx) {
      var comp = readComp(bx);
      if (!comp) return null;
      return comp.a.concat(comp.b).filter(function (s) { return s.score >= 0.55; }).length;
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
        // RANK BY CONFIDENT CELLS FIRST, summed score only as a tie-break.
        // The sum rewards ten mediocre correlations over nine good ones, which
        // put the coarse pass in the wrong basin in the field - it settled on
        // 8/10 while a placement 4px away scored 10/10, and the fine pass only
        // searches around the coarse winner so it could not recover.
        var rank = function (cand) {
          if (!withinFrame(cand, FW, FH)) return null;
          return scoreCandidate(frame, cand);
        };
        var better = function (r, cur) {
          return r && (r.ok > cur.ok || (r.ok === cur.ok && r.sum > cur.sum));
        };
        var bestRank = rank(best) || { ok: -1, sum: -Infinity };
        var bx = 0, by = 0;
        // COARSE PASS, then a FINE one around its winner. A single 0.01 pass
        // cannot resolve an offset smaller than 0.01 of the reference height,
        // and the real residual measured in the field was about half a step -
        // so the coarse pass alone is guaranteed to stop a few pixels out, on
        // whichever side happens to score better. Two passes cost 85 + 49
        // candidates against the 85 this replaces.
        var sweep = function (step, spanX, spanY, cx, cy) {
          for (var dyi = -spanY; dyi <= spanY; dyi++) {
            for (var dxi = -spanX; dxi <= spanX; dxi++) {
              var dx = cx + dxi * step, dy = cy + dyi * step;
              if (dx === bx && dy === by) continue;
              var cand = boxesFromStrips(R, dx, dy), r = rank(cand);
              if (better(r, bestRank)) { bestRank = r; best = cand; bx = dx; by = dy; }
            }
          }
        };
        // The coarse range stays WIDE on purpose. A window capture offsets the
        // game inside the captured surface by an amount no fraction of the
        // frame predicts - measured at -83px in the field - so the sweep is
        // load-bearing there rather than a refinement, and narrowing it would
        // break the case it exists to serve.
        sweep(0.01, 2, 8, 0, 0);
        // Span 2, not 3: the fine step is 0.0025 and the coarse step 0.01, so
        // +/-2 fine steps already bridges half a coarse step, which is the most
        // the coarse winner can be out by. Span 3 was 49 candidates for no extra
        // reach. 85 + 25 passes, against the 85 this whole sweep started at.
        sweep(0.0025, 2, 2, bx, by);
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

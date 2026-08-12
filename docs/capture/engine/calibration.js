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

    function boxesFromStrips(R, dx, dy) {
      var o = {};
      ['a', 'b'].forEach(function (s) {
        var st = AUTO_STRIPS[s], fx = st[0], fy = st[1], fw = st[2], fh = st[3];
        o[s] = { x: R.x + (fx + dx) * R.w, y: R.y + (fy + dy) * R.h, w: fw * R.w, h: fh * R.h };
      });
      return o;
    }

    // Sum of the 10 cells' best centre-match scores - higher = better aligned.
    function scoreBoxes(frame, bxs) {
      ensureWork();
      var sum = 0;
      ['a', 'b'].forEach(function (side) {
        var b = bxs[side];
        for (var i = 0; i < 5; i++) {
          var cell = { x: b.x + i * b.w / 5, y: b.y, w: b.w / 5, h: b.h };
          sum += bestMatch(cellGrayPadded(frame, cell), side, true).score;
        }
      });
      return sum;
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
        : '<span class="warn">only ' + ok + '/10 recognised — boxes look misaligned; try Auto-calibrate, or drag them right on the portraits (OW must be borderless/fullscreen, 16:9).</span>';
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
        var frame = grabFrame(), bestScore = scoreBoxes(frame, best);
        for (var dyi = -8; dyi <= 8; dyi++) {
          for (var dxi = -2; dxi <= 2; dxi++) {
            if (!dyi && !dxi) continue;
            var cand = boxesFromStrips(R, dxi * 0.01, dyi * 0.01), sc = scoreBoxes(frame, cand);
            if (sc > bestScore) { bestScore = sc; best = cand; }
          }
        }
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

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

    // ------------------------------------------------ HUD structure detection
    //
    // THE HUD IS LOCATED BY ITS OWN STRUCTURE, NOT BY A FRACTION OF THE FRAME.
    //
    // AUTO_STRIPS is a hand measurement off one 1440p capture, and a fixed
    // fraction cannot survive a change of display mode. Measured 2026-09-07
    // over four configurations of the same replay on the same machine:
    //
    //   config                     frame       true band rows   tile pitch
    //   SCREEN   + windowed      2560x1440       120..195         132.5
    //   SCREEN   + borderless    2560x1440        98..179         141.5
    //   OW window + borderless   2560x1440        98..179         141.5
    //   OW window + windowed     2570x1385       120..195         132.5
    //
    // Borderless tiles are ~7% larger than windowed ones on the same monitor
    // because the HUD scales with the game's CONTENT HEIGHT, and a title bar
    // takes 29px of it away. The old sweep can translate a box but never
    // resize it, so it read 4/10 on the borderless frames and 10/10 on the one
    // windowed configuration it was measured against.
    //
    // What survives all four: the five tiles are a periodic run of team-colour
    // blobs, and their PITCH gives the scale directly. Measured run starts -
    //
    //   SCREEN + windowed     132  266  398  530  662   -> pitch 132.5
    //   SCREEN + borderless    56  198  340  480  622   -> pitch 141.5
    //
    // Everything else follows: w = 5*pitch, h = w * the strip's own aspect
    // ratio (taken from AUTO_STRIPS, the one thing in it that IS scale-free),
    // y = the band's top row.
    //
    // Confirmed in the field 2026-09-08: all four configurations read 10/10,
    // and so did a deliberately SHRUNKEN game window - a content height, and
    // therefore a HUD scale and a pitch, that no table could have held. That
    // run was also on a swept palette, so both stages composed.
    //
    // KNOWN GAP, accepted rather than fixed: inverting OW's defaults (friendly
    // RED, enemy BLUE) leaves the right strip correct and misplaces the left.
    // It degrades honestly - the preview reported 6/10 - and it needs a
    // deliberate settings change to reach. See
    // tests/test_capture_strip_detect.py's swapped-defaults test.
    //
    // NOTE THIS KEYS ON RUN STARTS, NOT RUN WIDTHS. An earlier attempt measured
    // the band's horizontal EXTENT and blew the width out to 945-1199 against a
    // true 659, because the centre objective bar is the same blue as the left
    // team. A run's START is immune to that: the objective bar can only ever
    // extend a run to the right, never move where it began.
    var TILES = 5;

    // Team-colour tests. Deliberately not a hue bucket: a straight
    // channel-dominance test measured cleanly on all four configurations, and
    // the hue-generic versions tried alongside it did not (the map background
    // wins a hue histogram). This is the reason detectStrips can fail and the
    // sweep below is kept as a fallback rather than deleted.
    var SAT_MIN = 60;
    function isTeamA(r, g, b) { return b > 110 && b - r > 50 && b - g > 20; }
    function isTeamB(r, g, b) { return r > 110 && r - b > 50 && r - g > 50; }

    // A strip's height as a fraction of its width, from AUTO_STRIPS itself -
    // the vertical fractions are projected against width*9/16 (see stripBox),
    // so this ratio is the part of the table that does not depend on scale.
    function stripAspect(side) {
      var st = AUTO_STRIPS[side];
      return st[3] * 9 / 16 / st[2];
    }

    // The box's left edge sits slightly left of the first colour run: the tile
    // art starts before its coloured header does. Measured 2.5px at pitch
    // 132.5 on the frame whose hand-set box the operator confirmed.
    var EDGE_LEAD = 2.5 / 132.5;

    // Contiguous stretches of `cols` above `thr`, merging gaps of <= `gap`.
    function profileRuns(cols, thr, gap) {
      var out = [], s = -1, last = -1, x;
      for (x = 0; x < cols.length; x++) {
        if (cols[x] <= thr) continue;
        if (s < 0) { s = x; last = x; continue; }
        if (x > last + gap) { out.push([s, last]); s = x; }
        last = x;
      }
      if (s >= 0) out.push([s, last]);
      return out;
    }

    function coefVar(a) {
      var n = a.length, m = 0, i, v, ss = 0;
      for (i = 0; i < n; i++) m += a[i];
      m /= n;
      if (!m) return Infinity;
      for (i = 0; i < n; i++) { v = a[i] - m; ss += v * v; }
      return Math.sqrt(ss / n) / Math.abs(m);
    }

    // Five evenly spaced colour blobs => {x0, pitch}. The evenness test is what
    // separates the tiles from the rest of a busy HUD row: five runs whose
    // spacing varies by more than 6% are not a portrait strip.
    function fiveRuns(cols, thr, minWide) {
      var all = profileRuns(cols, thr, 4), rs = [], i, k;
      for (i = 0; i < all.length; i++) {
        if (all[i][1] - all[i][0] + 1 >= minWide) rs.push(all[i]);
      }
      var best = null;
      for (i = 0; i + TILES <= rs.length; i++) {
        var st = [], wd = [], d = [], bad = false;
        for (k = 0; k < TILES; k++) { st.push(rs[i + k][0]); wd.push(rs[i + k][1] - rs[i + k][0] + 1); }
        for (k = 1; k < TILES; k++) { d.push(st[k] - st[k - 1]); if (st[k] <= st[k - 1]) bad = true; }
        if (bad) continue;
        var cv = coefVar(d);
        if (cv > 0.06 || coefVar(wd) > 0.25) continue;
        var m = 0;
        for (k = 0; k < d.length; k++) m += d[k];
        if (!best || cv < best.cv) best = { cv: cv, x0: st[0], pitch: m / d.length };
      }
      return best;
    }

    // Phase of a five-tooth comb at a KNOWN pitch. Used for the side whose own
    // runs are too broken to measure - on a frame where one team's colour bleeds
    // into the map, the other team still fixes the pitch, and only the offset is
    // left to find.
    function combPhase(cols, pitch) {
      var n = cols.length, cs = new Float64Array(n + 1), i, x;
      for (i = 0; i < n; i++) cs[i + 1] = cs[i] + cols[i];
      var seg = function (a, b) {
        a = Math.max(0, Math.min(n, Math.round(a)));
        b = Math.max(0, Math.min(n, Math.round(b)));
        return b > a ? cs[b] - cs[a] : 0;
      };
      var tooth = 0.55 * pitch, span = (TILES - 1) * pitch + tooth;
      var bestV = -Infinity, bestX = 0;
      for (x = 0; x <= n - span; x++) {
        var on = 0, off = 0;
        for (i = 0; i < TILES; i++) on += seg(x + i * pitch, x + i * pitch + tooth);
        for (i = 0; i < TILES - 1; i++) off += seg(x + i * pitch + tooth, x + (i + 1) * pitch);
        var v = on - 1.2 * off;
        if (v > bestV) { bestV = v; bestX = x; }
      }
      return bestX;
    }

    // Candidate row ranges where BOTH halves carry team colour, longest first.
    //
    // Requiring both halves is what keeps the "TEAM 1" banner above the tiles
    // out of the band: measured on frame.png, a one-sided test called the band
    // 18px too tall, and 18px is four times the matcher's tolerance.
    //
    // TWO THINGS THIS MUST NOT DO, both measured on the operator's
    // colourblind capture of 2026-09-08 (orange vs lime):
    //
    // - Take the single longest run. The strongest run in that frame is rows
    //   26..79, ABOVE the tiles, and it beat the real band outright.
    // - Trust a run to be contiguous. The real band at 98..147 broke into runs
    //   of 13, 12 and 10 rows, because a tile is only team-coloured at its
    //   header and name plate - the portrait art in the middle is not - so the
    //   density dips mid-tile and falls under the threshold.
    //
    // So: merge across small gaps, and return several candidates rather than
    // betting on one. The hero matcher is what settles which is right, and it
    // already scores every proposal.
    var BAND_GAP = 14;        // rows; spans the mid-tile dip measured above
    var BAND_TRIES = 3;

    function bandCandidates(rowA, rowB, H) {
      var maxA = 0, maxB = 0, y;
      for (y = 0; y < H; y++) {
        if (rowA[y] > maxA) maxA = rowA[y];
        if (rowB[y] > maxB) maxB = rowB[y];
      }
      if (maxA < 20 || maxB < 20) return [];
      var both = new Float64Array(H), maxBoth = 0;
      for (y = 0; y < H; y++) {
        both[y] = Math.min(rowA[y] / maxA, rowB[y] / maxB);
        if (both[y] > maxBoth) maxBoth = both[y];
      }
      if (maxBoth < 0.2) return [];
      var thr = 0.35 * maxBoth, raw = [];
      y = 0;
      while (y < H) {
        if (both[y] <= thr) { y++; continue; }
        var j = y;
        while (j + 1 < H && both[j + 1] > thr) j++;
        raw.push([y, j]);
        y = j + 1;
      }
      var merged = [], i;
      for (i = 0; i < raw.length; i++) {
        if (merged.length && raw[i][0] - merged[merged.length - 1][1] <= BAND_GAP) {
          merged[merged.length - 1][1] = raw[i][1];
        } else merged.push([raw[i][0], raw[i][1]]);
      }
      // Merged spans first - the fragmented real band only exists as one of
      // these - then the raw runs, in case a merge joined two real structures.
      var out = [], seen = {};
      [merged, raw].forEach(function (list) {
        list.slice().sort(function (p, q) { return (q[1] - q[0]) - (p[1] - p[0]); })
          .forEach(function (r) {
            var key = r[0] + ':' + r[1];
            if (seen[key] || r[1] - r[0] + 1 < 8) return;
            seen[key] = 1;
            out.push({ y0: r[0], y1: r[1], h: r[1] - r[0] + 1 });
          });
      });
      return out.slice(0, BAND_TRIES);
    }

    // Column occupancy for the band's rows only, under a pair of colour tests.
    function bandColumns(data, W, H, band, inA, inB) {
      var half = W >> 1, colA = new Float64Array(half), colB = new Float64Array(W - half);
      var y, x, i, r, g, b;
      for (y = band.y0; y <= band.y1; y++) {
        for (x = 0; x < W; x++) {
          i = (y * W + x) * 4;
          r = data[i]; g = data[i + 1]; b = data[i + 2];
          if (Math.max(r, g, b) - Math.min(r, g, b) <= SAT_MIN) continue;
          if (x < half) { if (inA(r, g, b)) colA[x]++; }
          else if (inB(r, g, b)) colB[x - half]++;
        }
      }
      return { a: colA, b: colB };
    }

    // Two column profiles + a band => the two boxes, or null.
    function colMax(c) {
      var m = 0, i;
      for (i = 0; i < c.length; i++) if (c[i] > m) m = c[i];
      return m;
    }

    // THE COLUMN THRESHOLD COMES FROM THE COLUMN PROFILE, NOT THE BAND HEIGHT.
    //
    // A column count can never exceed the band's height, so band.h * 0.30 is
    // only the right threshold when the band hugs the tiles. Let the band run
    // tall - which it does the moment two candidate bands merge - and the
    // threshold climbs past anything the tiles can reach, so fiveRuns finds
    // nothing and the placement is silently lost rather than scored badly.
    function stripsFromBand(cols, band, W) {
      var half = W >> 1, minWide = Math.max(4, 0.01 * W);
      var fa = fiveRuns(cols.a, 0.30 * colMax(cols.a), minWide);
      var fb = fiveRuns(cols.b, 0.30 * colMax(cols.b), minWide);
      if (!fa && !fb) return null;
      // The cleaner side sets the pitch; a side whose own reading disagrees by
      // more than 3% is not trusted with it and gets the comb instead.
      var lead = (!fb || (fa && fa.cv <= fb.cv)) ? fa : fb;
      var pitch = lead.pitch;
      if (pitch * TILES > half + 0.10 * W) return null;
      var out = { pitch: pitch, bandTop: band.y0 };
      [['a', fa, cols.a, 0], ['b', fb, cols.b, half]].forEach(function (t) {
        var side = t[0], f = t[1], c = t[2], off = t[3];
        var x0 = (f && Math.abs(f.pitch - pitch) / pitch < 0.03) ? f.x0 : combPhase(c, pitch);
        var w = TILES * pitch;
        out[side] = { x: x0 + off - EDGE_LEAD * pitch, y: band.y0, w: w, h: stripAspect(side) * w };
      });
      return out;
    }

    // {a, b, pitch, bandTop} or null. `data` is RGBA for the TOP of the frame
    // (H rows of W pixels) - the HUD never sits below that, and scanning the
    // whole frame would cost several times as much for nothing.
    //
    // Pure: no DOM, no canvas, no module state. That is what lets a node test
    // drive it over synthetic pixels; see tests/test_capture_strip_detect.py.
    function detectStrips(data, W, H) {
      var half = W >> 1, y, x, i, r, g, b;
      var rowA = new Float64Array(H), rowB = new Float64Array(H);
      for (y = 0; y < H; y++) {
        var ca = 0, cb = 0;
        for (x = 0; x < W; x++) {
          i = (y * W + x) * 4;
          r = data[i]; g = data[i + 1]; b = data[i + 2];
          if (Math.max(r, g, b) - Math.min(r, g, b) <= SAT_MIN) continue;
          if (x < half) { if (isTeamA(r, g, b)) ca++; }
          else if (isTeamB(r, g, b)) cb++;
        }
        rowA[y] = ca; rowB[y] = cb;
      }
      var bands = bandCandidates(rowA, rowB, H), bi;
      for (bi = 0; bi < bands.length; bi++) {
        var got = stripsFromBand(
          bandColumns(data, W, H, bands[bi], isTeamA, isTeamB), bands[bi], W);
        if (got) return got;
      }
      return null;
    }

    // ---------------------------------------------- custom / colourblind UI
    //
    // OW's accessibility options let a player recolour the team and enemy UI,
    // and some of the people this tool is for run it that way. detectStrips
    // above keys on blue and red, so for them it finds nothing at all.
    //
    // The structure is the same whatever the colours are - five evenly spaced
    // tiles of ONE colour on the left and five of ANOTHER on the right - so
    // this sweeps hue instead of assuming it. What it must NOT do is pick the
    // hue by mass: measured 2026-09-07, the two most common saturated hues in
    // the top of a frame are the MAP, and choosing that way failed on all six
    // real capture frames. The palette is chosen by whether it yields a band
    // and five evenly spaced runs, and the hero matcher settles the rest.
    //
    // 24 windows of 30 degrees at 15-degree steps, so a team colour that
    // straddles a boundary is still covered whole by some window.
    var HUE_BINS = 24;
    // The two windows must not OVERLAP - that is all. A window spans two bins,
    // so two bins apart is the whole requirement, and anything stricter starts
    // discarding real palettes: measured on a frame the operator captured
    // 2026-09-08 with OW's accessibility colours on, the teams were orange
    // (bin 1, 15 degrees) and lime (bin 4, 60 degrees), THREE bins apart. A
    // 60-degree rule rejected the true pair before it was ever scored, and
    // auto-calibrate fell through to the sweep and read 2/10.
    var HUE_SEP = 2;
    // THE MATCHER RANKS THE PALETTES, NOT THEIR PIXEL MASS.
    //
    // Mass was the obvious ranking and it is the wrong one, for the same
    // reason picking the hue by mass was: the map outweighs the HUD. Measured
    // on a magenta team over a purple map, the four highest-mass pairs were
    // all the BACKGROUND rather than the tiles - and their runs pass the
    // evenness test, because the holes the tiles punch in a background are as
    // periodic as the tiles themselves. The correct pair was fifth.
    //
    // So mass only decides what gets LOOKED at. Scoring a candidate where it
    // stands costs ten cell matches, against the ~770 a refine costs, so the
    // shortlist can be wide as long as only the best of it is refined.
    var PALETTE_TRIES = 24;   // proposals scored where they stand
    var PALETTE_REFINE = 2;   // ...of which this many earn a refine

    function hueBin(r, g, b) {
      var mx = Math.max(r, g, b), mn = Math.min(r, g, b), s = mx - mn;
      if (s <= SAT_MIN || mx <= 100) return -1;
      var h;
      if (mx === r) h = ((g - b) / s + 6) % 6;
      else if (mx === g) h = (b - r) / s + 2;
      else h = (r - g) / s + 4;
      var k = Math.floor(h * HUE_BINS / 6);
      return ((k % HUE_BINS) + HUE_BINS) % HUE_BINS;
    }

    function inHueWindow(w) {
      var w1 = (w + 1) % HUE_BINS;
      return function (r, g, b) { var k = hueBin(r, g, b); return k === w || k === w1; };
    }

    // Per-row counts for every hue bin and both halves, in ONE pass. The pair
    // search that follows then works on H-length arrays instead of pixels,
    // which is what keeps a 576-pair sweep affordable.
    function hueRowCounts(data, W, H) {
      var half = W >> 1, acc = new Float64Array(2 * HUE_BINS * H), y, x, i, k;
      for (y = 0; y < H; y++) {
        for (x = 0; x < W; x++) {
          i = (y * W + x) * 4;
          k = hueBin(data[i], data[i + 1], data[i + 2]);
          if (k < 0) continue;
          acc[((x < half ? 0 : 1) * HUE_BINS + k) * H + y]++;
        }
      }
      return acc;
    }

    // Candidate placements under swept team colours, best palette first.
    function detectStripsByHue(data, W, H) {
      var acc = hueRowCounts(data, W, H), profs = [[], []], s, w, y;
      for (s = 0; s < 2; s++) {
        for (w = 0; w < HUE_BINS; w++) {
          var p = new Float64Array(H);
          var b0 = (s * HUE_BINS + w) * H, b1 = (s * HUE_BINS + (w + 1) % HUE_BINS) * H;
          for (y = 0; y < H; y++) p[y] = acc[b0 + y] + acc[b1 + y];
          profs[s].push(p);
        }
      }
      var pairs = [], wa, wb, sep;
      for (wa = 0; wa < HUE_BINS; wa++) {
        for (wb = 0; wb < HUE_BINS; wb++) {
          sep = Math.abs(wa - wb);
          if (Math.min(sep, HUE_BINS - sep) < HUE_SEP) continue;
          var bands = bandCandidates(profs[0][wa], profs[1][wb], H);
          for (var bi = 0; bi < bands.length; bi++) {
            var band = bands[bi], mass = 0;
            for (y = band.y0; y <= band.y1; y++) mass += profs[0][wa][y] + profs[1][wb][y];
            pairs.push({ wa: wa, wb: wb, band: band, mass: mass });
          }
        }
      }
      pairs.sort(function (p, q) { return q.mass - p.mass; });
      // DEDUPE BY PLACEMENT, NOT BY PALETTE.
      //
      // Adjacent hue windows overlap by a bin, so a team colour sitting near a
      // boundary is caught by two of them and yields the SAME boxes twice.
      // Measured on the operator's neon-blue/magenta frame, the shortlist held
      // about twelve distinct placements in twenty-four slots, and the correct
      // one came twenty-first - it only just survived the cap. Deduping on the
      // geometry rather than the hues doubles what a slot is worth.
      var out = [];
      var same = function (g) {
        return out.some(function (h) {
          return Math.abs(h.bandTop - g.bandTop) <= 3
            && Math.abs(h.pitch - g.pitch) / g.pitch < 0.01
            && Math.abs(h.a.x - g.a.x) <= 3 && Math.abs(h.b.x - g.b.x) <= 3;
        });
      };
      for (var i = 0; i < pairs.length && out.length < PALETTE_TRIES; i++) {
        var pr = pairs[i];
        var cols = bandColumns(data, W, H, pr.band, inHueWindow(pr.wa), inHueWindow(pr.wb));
        var got = stripsFromBand(cols, pr.band, W);
        if (got && !same(got)) { got.hues = [pr.wa, pr.wb]; out.push(got); }
      }
      return out;
    }

    // Detection lands within a few pixels; the matcher closes the last of it.
    // The window in which a strip reads at all is about four pixels wide, so
    // this is a nudge, not a search - 7x11 placements against the sweep's 300+.
    function refineStrip(frame, box, side, W, H) {
      var best = { s: { distinct: -1, sum: -Infinity }, box: box }, dx, dy;
      for (dx = -3; dx <= 3; dx++) {
        for (dy = -5; dy <= 5; dy++) {
          var b = { x: box.x + dx, y: box.y + dy, w: box.w, h: box.h };
          if (!boxInFrame(b, W, H)) continue;
          var s = scoreStrip(frame, b, side);
          if (s.distinct > best.s.distinct || (s.distinct === best.s.distinct && s.sum > best.s.sum)) {
            best = { s: s, box: b };
          }
        }
      }
      return best;
    }

    // What a proposal reads WHERE IT STANDS - ten cell matches, no search.
    // Cheap enough to run over every proposal, which is what lets the matcher
    // rather than pixel mass decide which ones are worth refining.
    function scoreDetection(frame, det, W, H) {
      if (!det) return -1;
      var total = 0;
      ['a', 'b'].forEach(function (side) {
        if (!boxInFrame(det[side], W, H)) return;
        total += Math.max(scoreStrip(frame, det[side], side).distinct, 0);
      });
      return total;
    }

    // Refine both strips of a proposed placement and report what it reads.
    // {ok} alone when the proposal is empty, so a caller can compare stages
    // without special-casing null.
    function takeDetection(frame, det, W, H) {
      var out = { ok: 0 };
      if (!det) return out;
      ['a', 'b'].forEach(function (side) {
        var rr = refineStrip(frame, det[side], side, W, H);
        out[side] = rr.box;
        out.ok += Math.max(rr.s.distinct, 0);
      });
      return out;
    }

    // Read the top of the frame once, for detectStrips. 30% is well clear of
    // the band in every configuration measured (the lowest was 130/1393).
    function topPixels(frame, W, H) {
      var h = Math.max(1, Math.round(H * 0.30));
      return { data: frame.getContext('2d').getImageData(0, 0, W, h).data, w: W, h: h };
    }

    // Structure detection is right or it is nothing, so a partial read hands
    // over to the sweep rather than being averaged with it.
    var DETECT_ACCEPT = 8;

    // Auto-calibrate: locate the two 5-portrait strips from the HUD's own
    // structure (detectStrips), falling back to the fixed-fraction sweep when
    // that finds nothing. Self-test then confirms alignment.
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

        // A CASCADE, CHEAPEST FIRST, AND THE MATCHER DECIDES.
        //
        // Stage 1 finds the HUD by its own structure on the default palette.
        // Measured over the six real capture frames in screenshots/, by
        // distinct heroes: 10/10 on all six, where stage 3 reads 10, 6, 6, 6,
        // 4, 4. It costs one pass over the top of the frame plus ~800 cell
        // matches, against the sweep's 3000+.
        //
        // Stage 2 sweeps the team colours for a player running OW's
        // accessibility palette, and only runs when stage 1 came up short - so
        // the common case never pays for it.
        //
        // Stage 3 is the fixed-fraction sweep that shipped before. It cannot
        // correct a scale error, so it is a floor, not a second opinion.
        //
        // No stage is trusted on its own say-so: every candidate is scored by
        // the hero matcher, and the best-scoring placement wins whichever
        // stage proposed it.
        var top = null;
        try { top = topPixels(frame, FW, FH); }
        catch (e) { top = null; }     // tainted or zero-sized frame: skip to the sweep
        var bestDet = null, found = 0;
        var consider = function (det) {
          if (!det) return;
          var t = takeDetection(frame, det, FW, FH);
          if (t.a && t.ok > found) { found = t.ok; bestDet = t; }
        };
        if (top) {
          consider(detectStrips(top.data, top.w, top.h));       // stage 1
          if (found < DETECT_ACCEPT) {                          // stage 2
            var pal = detectStripsByHue(top.data, top.w, top.h), pi;
            var ranked = [];
            for (pi = 0; pi < pal.length; pi++) {
              ranked.push({ det: pal[pi], s: scoreDetection(frame, pal[pi], FW, FH) });
            }
            ranked.sort(function (p, q) { return q.s - p.s; });
            for (pi = 0; pi < ranked.length && pi < PALETTE_REFINE
                         && found < DETECT_ACCEPT; pi++) consider(ranked[pi].det);
          }
        }
        if (bestDet && found >= DETECT_ACCEPT) { best.a = bestDet.a; best.b = bestDet.b; }

        var sweepOk = 0;
        if (found < DETECT_ACCEPT) {                            // stage 3

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
          sweepOk += Math.max(bestS.distinct, 0);
        });

        // A partial structure detection still beats a worse sweep - the sweep
        // is the floor, not the tie-breaker.
        if (bestDet && found > sweepOk) { best.a = bestDet.a; best.b = bestDet.b; }
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
      detectStrips: detectStrips,
      detectStripsByHue: detectStripsByHue,
      fiveRuns: fiveRuns,
      stripAspect: stripAspect,
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

// docs/capture/engine/tour.js
// Guided first-capture tour shared by index.html and scrim.html: a
// non-blocking walkthrough that highlights the actual control to click and
// auto-advances the moment that action is done, so a new user is led
// through the flow without ever hunting for a button.
//
// Extracted from the two hand-maintained forks (see
// tools/capture_divergence.py): highlight, render, open, done, next, prev
// and tick (tourHighlight/tourRender/tourOpen/tourDone/tourNext/tourPrev/
// tourTick before this move) were byte-identical - only the MECHANISM
// moved. tourDefs (-77, each page's own step copy: share -> calibrate ->
// [pick a replay | start a scrim map] -> capture -> [publish | finish]) and
// updateGuide (-289, the separate always-visible stepper card) stay in the
// page - see ctx.steps below.
//
// isFirstVisit (-68) and maybeShowTour/maybeShow (-18) diverge for real,
// not cosmetically: index.html also treats a returning scout with a saved
// name as not-first-visit / never re-toured (a name means they've already
// published once); scrim.html has no name concept and instead skips
// scouts who already have a saved scrim map. Both are page policy, carried
// in as ctx.firstVisitExtra and ctx.skipIf rather than branched on inside
// the module.
//
// tourIdx stays a page-level global exactly like engine/calibration.js
// leaves boxes/drawMode alone: each page's own fullscreenchange handler
// reads tourIdx directly (to hide the tour panel during fullscreen
// calibration), so this module reads/writes it as a free variable via the
// shared global lexical scope classic <script> tags get, resolved at call
// time. _firstVisit is the same story - updateGuide (page copy, not moved)
// writes it directly once all its own steps are done. tourSteps and
// tourManualAt, by contrast, were read only inside this cluster in both
// pages, so they moved in as module instance state instead - see work/wctx
// in engine/frames.js for the precedent.
//
// LOCALSTORAGE KEY: index.html uses 'owdb_tour_done', scrim.html uses
// 'owdb_tour_done_scrim' (ctx.tourKey) - two DIFFERENT keys, deliberately,
// so completing one page's tour does not suppress the other's. This was
// already true and already commented in scrim.html before this extraction
// ("Separate dismissal key so completing the League tour doesn't suppress
// this one.") - carried forward unchanged, not decided here. It is NOT the
// same situation as engine/calibration.js's boxes/'owdb_cap_boxes', which
// IS one shared key across both pages (see that module's header) - the two
// clusters made opposite, and in both cases deliberate, choices.
//
// ctx = {doc, steps, tourKey, firstVisitExtra, skipIf} - doc is the DOM
// handle (a Node test harness has no document); steps is the page's own
// tourDefs() array; tourKey is the page's dismissal key; firstVisitExtra
// (optional, index.html only) and skipIf (optional) are the two bits of
// page policy described above.
//
// Works as a browser global (`window.OWDBTour`) and as a CommonJS module
// for node:test / pytest.

(function (global) {
  'use strict';

  function make(ctx) {
    // tourSteps/tourManualAt: instance state, nothing outside this cluster
    // reads either on either page (see header - tourIdx is the one exception).
    var tourSteps = [], tourManualAt = 0;

    function highlight(targetId) {
      ctx.doc.querySelectorAll('.tour-highlight').forEach(function (e) { e.classList.remove('tour-highlight'); });
      if (!targetId) return;
      var el = ctx.doc.getElementById(targetId); if (!el) return;
      el.classList.add('tour-highlight');
      try { el.scrollIntoView({ behavior: 'smooth', block: 'center' }); } catch (e) {}
    }

    function render() {
      var t = ctx.doc.getElementById('tour'), s = tourSteps[tourIdx]; if (!t || !s) return;
      t.querySelector('.tour-count').textContent = (tourIdx + 1) + ' / ' + tourSteps.length;
      t.querySelector('.tour-title').textContent = s.t;
      t.querySelector('.tour-body').innerHTML = s.body;
      var nxt = t.querySelector('#tourNext');
      nxt.textContent = s.btn || 'Next';
      // Back arrow: only once there's a step behind you.
      t.querySelector('#tourPrev').style.visibility = (tourIdx === 0) ? 'hidden' : 'visible';
      highlight(s.target);
    }

    function open() {
      tourSteps = ctx.steps;
      tourIdx = tourSteps.findIndex(function (s) { return !s.done(); });   // resume at first incomplete step
      if (tourIdx < 0) { localStorage.setItem(ctx.tourKey, '1'); return; }
      var t = ctx.doc.getElementById('tour'); t.classList.add('open'); t.style.display = 'block';
      render();
    }

    function done(silent) {
      localStorage.setItem(ctx.tourKey, '1');
      var t = ctx.doc.getElementById('tour'); if (t) { t.classList.remove('open'); t.style.display = 'none'; }
      highlight(null);
      if (!silent) toast('Tour closed — the <b>How it works</b> card above has the same steps any time.', 'info');
    }

    function next() {
      if (tourIdx >= 0 && tourIdx < tourSteps.length - 1) { tourIdx++; tourManualAt = Date.now(); render(); }
      else { done(true); }
    }

    function prev() {
      if (tourIdx > 0) { tourIdx--; tourManualAt = Date.now(); render(); }
    }

    function tick() {
      if (tourIdx < 0) return;
      if (Date.now() - tourManualAt < 2500) return;   // grace period after a manual step
      if (tourSteps[tourIdx].done()) next();   // auto-advance as each action happens
    }

    function maybeShow() {
      if (!HAS_CAPTURE) return;
      if (localStorage.getItem(ctx.tourKey) === '1') return;
      if (ctx.skipIf && ctx.skipIf()) { localStorage.setItem(ctx.tourKey, '1'); return; }
      open();
    }

    function isFirstVisit() {
      if (_firstVisit !== null) return _firstVisit;
      var extra = ctx.firstVisitExtra ? ctx.firstVisitExtra() : true;
      return (_firstVisit = extra && !(boxes.a && boxes.b));
    }

    return {
      open: open,
      next: next,
      prev: prev,
      render: render,
      tick: tick,
      highlight: highlight,
      done: done,
      isFirstVisit: isFirstVisit,
      maybeShow: maybeShow,
    };
  }

  var Mod = { make: make };

  if (typeof module !== 'undefined' && module.exports) module.exports = Mod;
  else global.OWDBTour = Mod;
})(typeof self !== 'undefined' ? self : this);

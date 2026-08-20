// docs/capture/engine/overlay.js
// Floating pop-out control panel (Document Picture-in-Picture) shared by
// index.html and scrim.html: the always-on-top window a scout parks next to
// the game so they never have to alt-tab back to the browser.
//
// Extracted from the two hand-maintained forks (see
// tools/capture_divergence.py): pipColors and restylePipPanel were
// byte-identical - they moved in unchanged. Everything else - popout,
// renderPipControls, pipPanelCss, setPopBtn, maybeAutoPop, gestureAutoPop -
// diverged for real, and NOT cosmetically: index.html's panel (the league
// page) carries controls scrim.html's does not - a "Re-detect sides"
// button, "spent" sub-map dimming (usedSubmaps), an auto-fetch checkbox, and
// a dedicated Finish row big enough to be the one "commit" action - and is
// sized/padded to fit them. THAT DIVERGENCE IS BY DESIGN, NOT DRIFT: it is
// not reconciled into one branching function. Instead ctx carries it as
// data - the module owns the MECHANISM (open the PiP window, wire the
// shared buttons, keep the button/state in sync) and renders whatever the
// page hands it:
//   - ctx.controls: ordered list of {id, render(el, doc, mk)} row
//     descriptors. renderPipControls() finds each id in the PiP document
//     and calls render() with a button-maker helper the module owns (mk was
//     byte-identical in both pages). The FIRST row is also the "is the
//     panel DOM built yet" gate, same as the original's `if(!main) return`.
//   - ctx.middleHtml / ctx.finishHtml: the row-container markup popout()
//     splices into the panel body, before/after the Left/Right team panels.
//     Both pages currently put their Finish row in finishHtml. EVERY id in
//     ctx.controls must appear in one of these two strings: renderPipControls
//     skips ids it cannot find in the panel document, so a row declared but
//     not slotted here simply never appears, with no error anywhere.
//   - ctx.panelCss(c) / ctx.bodyStyle(c): the two pages are genuinely
//     different designs here (index.html is denser - smaller padding/type -
//     because it fits more rows into the same-ish window), not one page
//     with "extra" rules appended, so this is page content passed straight
//     through, not merged.
//   - ctx.width/height, ctx.labels{off,on}, ctx.toasts{noDPIP,autoPop},
//     ctx.tick(el): panel size, the pop button's two label states, the two
//     toast strings, and how the "R2 - 4 snaps" info line renders (index.html's
//     is richer - map name/category, team names - scrim.html's is one line).
//   - ctx.afterOpen(w) (optional): index.html-only post-open wiring (the
//     auto-fetch checkbox synced to the main page's).
//
// pipWin/target/session/drawMode stay page-level globals exactly like
// engine/calibration.js leaves boxes/drawMode alone: they're read and
// written by code outside this cluster too (the toast-into-panel lookup in
// each page's own message helper, the read() function's target.A/B writes,
// the main page's autofetch checkbox onchange reaching into the open
// panel), so this module reads/writes them as free variables via the
// shared global lexical scope classic <script> tags get, resolved at call
// time - same convention, same reason.
//
// The auto-pop arm/pending flags (index.html's pipAutoShown/pipAutoPending,
// scrim.html's _pipAuto/_pipPending - two different names for the same
// thing) were read only inside this cluster in both pages, so they moved in
// as module instance state instead - see work/wctx in engine/frames.js for
// the precedent of instance-private state that isn't part of ctx.
//
// ctx = {doc, width, height, labels:{off,on}, toasts:{noDPIP,autoPop},
//   panelCss(c), bodyStyle(c), middleHtml, finishHtml, controls, tick(el),
//   afterOpen(w)}. doc is the main-document DOM handle (a Node test harness
// has no document); everything else is described above.
//
// Works as a browser global (`window.OWDBOverlay`) and as a CommonJS module
// for node:test / pytest.

(function (global) {
  'use strict';

  function make(ctx) {
    // Arms the "open the panel on the next click/keypress once the tool is
    // capture-ready" behaviour (maybeAutoPop) and the gesture that actually
    // fires it (gestureAutoPop). Instance state: nothing outside this
    // cluster reads either flag on either page.
    var autoShown = false, autoPending = false;

    // Reads the palette currently active on this page (via getComputedStyle,
    // not a guessed token table) so the control panel always matches -
    // including palettes added after this code was written.
    function pipColors() {
      var cs = getComputedStyle(document.documentElement), v = function (n) { return cs.getPropertyValue(n).trim(); };
      return {
        bg: v('--bg'), surface2: v('--surface2'), fg: v('--fg'), muted: v('--muted'), line: v('--line'), line2: v('--line2'),
        accent: v('--accent'), onAccent: v('--on-accent'), good: v('--good'), mid: v('--mid'), bad: v('--bad'),
        // Side colours. The panel labels the two teams by the HUD's blue/red,
        // which the palette expresses as the tank/damage role tokens - taking
        // them from here rather than restating the hex keeps the pop-out and
        // the page saying the same blue.
        tank: v('--tank'), damage: v('--damage'),
        // Corner radii. The pop-out is a separate document and never loads
        // theme.css, so the scale has to travel with the colours or the panel
        // ends up the one surface still picking its own numbers.
        rSm: v('--r-sm'), rMd: v('--r-md'),
      };
    }

    function pipPanelCss(c) {
      return ctx.panelCss(c);
    }

    // Re-applies the current palette to an already-open control panel, so a
    // mid-session palette change doesn't require closing and reopening it.
    function restylePipPanel() {
      if (!pipWin || pipWin.closed) return;
      var c = pipColors();
      pipWin.document.body.style.background = c.bg; pipWin.document.body.style.color = c.fg;
      var st = pipWin.document.getElementById('pipstyle'); if (st) st.textContent = pipPanelCss(c);
    }

    // Controls are rebuilt per map (each page's startMap-equivalent calls
    // this) so sub-map / flip buttons always match the current map - the
    // whole loop runs with no alt-tab. ctx.controls[0] doubles as the
    // "is the panel DOM built yet" gate, same as the original's
    // `if(!main) return`.
    function renderPipControls() {
      setPopBtn();
      if (!pipWin || pipWin.closed) return;
      var d = pipWin.document;
      var main = d.getElementById(ctx.controls[0].id);
      if (!main) return;
      var mk = function (p, t, fn, cls) {
        var b = d.createElement('button'); b.textContent = t; if (cls) b.className = cls; b.onclick = fn; p.appendChild(b);
      };
      ctx.controls.forEach(function (row) {
        var el = d.getElementById(row.id);
        if (el) row.render(el, d, mk);
      });
    }

    async function popout() {
      if (!('documentPictureInPicture' in window)) { toast(ctx.toasts.noDPIP, 'warn'); return; }
      if (pipWin && !pipWin.closed) return;   // already open - keep the one window
      try {
        var w = await documentPictureInPicture.requestWindow({ width: ctx.width, height: ctx.height });
        pipWin = w; autoShown = true; setPopBtn();
        var c = pipColors();
        w.document.body.style.cssText = ctx.bodyStyle(c);
        var st = w.document.createElement('style'); st.id = 'pipstyle'; st.textContent = pipPanelCss(c);
        w.document.head.appendChild(st);
        w.document.body.innerHTML = '<div id="pinfo"></div><div id="pmsg"></div>' + ctx.middleHtml +
          '<div class="pt"><h3 id="phA">Left</h3><div id="poutA"></div></div>' +
          '<div class="pt"><h3 id="phB">Right</h3><div id="poutB"></div></div>' + ctx.finishHtml;
        target = { A: w.document.getElementById('poutA'), B: w.document.getElementById('poutB') };
        if (ctx.afterOpen) ctx.afterOpen(w);
        renderPipControls();
        w.document.addEventListener('keydown', handleKey);   // shortcuts work from the control panel too
        // Map + teams: the operator is watching the game, not the browser
        // tab, so the one place they DO see (this floating panel) should
        // say what's being scouted without needing to alt-tab back.
        var tick = function () {
          if (w.closed) return;
          var el = w.document.getElementById('pinfo');
          if (el) ctx.tick(el);
          // Name the two read-out columns after the teams actually on those
          // sides. "Left" and "Right" are true but useless: the one thing the
          // operator needs from this panel is WHICH team is on the left, and
          // reading it off a header sitting directly above that team's heroes
          // beats holding it in your head from a line further up.
          if (ctx.slotLabels) {
            var n = ctx.slotLabels() || {};
            var hA = w.document.getElementById('phA'), hB = w.document.getElementById('phB');
            if (hA) hA.textContent = n.left || 'Left';
            if (hB) hB.textContent = n.right || 'Right';
          }
        };
        w._tick = setInterval(tick, 600); tick();
        w.addEventListener('pagehide', function () {
          clearInterval(w._tick); pipWin = null; setPopBtn();
          target = { A: document.getElementById('outA'), B: document.getElementById('outB') };
        });
      } catch (err) {
        toast('Pop-out failed: ' + esc(err && err.message ? err.message : String(err)), 'bad');
      }
    }

    // Reflect the control panel's open/closed state on the (prominent)
    // button.
    function setPopBtn() {
      var b = ctx.doc.getElementById('pop'); if (!b) return;
      var on = !!(pipWin && !pipWin.closed);
      b.classList.toggle('on', on);
      b.textContent = on ? ctx.labels.on : ctx.labels.off;
    }

    // Auto-open the control panel: the tool is "ready for capture" when the
    // screen is shared, both boxes are set, and a replay code is picked.
    // Browsers only allow requestWindow() inside a user gesture, so we can't
    // open it the moment `ready` flips by itself - instead we ARM it then,
    // and fire it on the next click or capture keypress. Only ever
    // auto-opens once per page load; after the scout closes it themselves we
    // don't fight them, the button reopens it.
    function maybeAutoPop() {
      if (autoShown || !('documentPictureInPicture' in window)) return;
      if (!readyForCapture()) { autoPending = false; return; }
      if (!autoPending) { autoPending = true; toast(ctx.toasts.autoPop, 'info', 4500); }
    }

    function gestureAutoPop() {
      if (!autoPending || drawMode) return;
      autoPending = false; popout();
    }

    return {
      popout: popout,
      maybeAutoPop: maybeAutoPop,
      gestureAutoPop: gestureAutoPop,
      setPopBtn: setPopBtn,
      pipColors: pipColors,
      pipPanelCss: pipPanelCss,
      renderPipControls: renderPipControls,
      restylePipPanel: restylePipPanel,
    };
  }

  var Mod = { make: make };

  if (typeof module !== 'undefined' && module.exports) module.exports = Mod;
  else global.OWDBOverlay = Mod;
})(typeof self !== 'undefined' ? self : this);

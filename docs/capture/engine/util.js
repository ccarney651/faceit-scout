// docs/capture/engine/util.js
// Small generic helpers shared by index.html and scrim.html: HTML escaping,
// CSS custom-property reads, video/overlay scale + event-point math, base64
// <-> bytes conversion for reference templates, the typing-focus guard used
// by the keyboard-shortcut handler, and the toast/modal UI primitives.
//
// css/scl/evp close over page-level globals (`document`, and — for scl/evp —
// the `vid`/`ov` DOM-element consts each page declares identically before
// its inline script starts calling them). That works because classic
// <script src> tags and the page's inline <script> share one global lexical
// scope, so the free-variable lookup resolves at call time, after those
// consts exist. toast/uiModal/uiConfirm touch the DOM only through
// `document`, which both pages provide identically.
//
// Reconciled from the two hand-maintained forks (see
// tools/capture_divergence.py): esc, css, scl, ico, evp, b64bytes,
// bytesToB64, isTyping, toast and uiConfirm were identical between the
// pages. uiModal had drifted by 9 characters — index.html's collect-mode
// field scan used `m.querySelectorAll('input,select')`, scrim.html's added
// ',textarea'. This is real (not cosmetic) drift: scrim.html's OCR-import
// fallback puts a <textarea id="rawocr"> inside a collect:true modal and
// reads the edited text back via fields.rawocr. Took the superset —
// 'input,select,textarea' — since adding textarea support cannot affect
// index.html, which has no textarea in any collect modal.
//
// Works as a browser global (`window.OWDBUtil`) and as a CommonJS module for
// node:test / pytest.

(function (global) {
  'use strict';

  function esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }

  function css(v) {
    return getComputedStyle(document.documentElement).getPropertyValue(v).trim() || '#8087ff';
  }

  function scl() {
    return vid.videoWidth ? vid.clientWidth / vid.videoWidth : 1;
  }

  var ICONS = {
    info: '<svg class="ticon" viewBox="0 0 16 16" fill="none"><circle cx="8" cy="8" r="7" stroke="currentColor" stroke-width="1.6"/><path d="M8 7.2v3.6" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/><circle cx="8" cy="4.9" r="1.1" fill="currentColor"/></svg>',
    ok: '<svg class="ticon" viewBox="0 0 16 16" fill="none"><circle cx="8" cy="8" r="7" stroke="currentColor" stroke-width="1.6"/><path d="M5.2 8.2l2 2 3.6-4.2" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/></svg>',
    warn: '<svg class="ticon" viewBox="0 0 16 16" fill="none"><path d="M8 2.3l6 10.4H2z" stroke="currentColor" stroke-width="1.6" stroke-linejoin="round"/><path d="M8 6.6v3" stroke="currentColor" stroke-width="1.7" stroke-linecap="round"/><circle cx="8" cy="11.1" r="1" fill="currentColor"/></svg>',
    bad: '<svg class="ticon" viewBox="0 0 16 16" fill="none"><circle cx="8" cy="8" r="7" stroke="currentColor" stroke-width="1.6"/><path d="M5.6 5.6l4.8 4.8M10.4 5.6l-4.8 4.8" stroke="currentColor" stroke-width="1.7" stroke-linecap="round"/></svg>',
    // functional affordances (buttons + inline status) — same 16px stroke style
    sparkle: '<svg class="ticon" viewBox="0 0 16 16" fill="none"><path d="M8 2.2l1.5 4.3 4.3 1.5-4.3 1.5L8 13.8l-1.5-4.3-4.3-1.5 4.3-1.5z" stroke="currentColor" stroke-width="1.4" stroke-linejoin="round"/></svg>',
    fullscreen: '<svg class="ticon" viewBox="0 0 16 16" fill="none"><path d="M3 6.5V3h3.5M10 3h3v3.5M13 9.5V13H9.5M6 13H3V9.5" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/></svg>',
    refresh: '<svg class="ticon" viewBox="0 0 16 16" fill="none"><path d="M13.2 8a5.2 5.2 0 1 1-1.5-3.7" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/><path d="M13.5 2.4v2.4H11" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/></svg>',
    skip: '<svg class="ticon" viewBox="0 0 16 16" fill="none"><path d="M4 3.8l7 4.2-7 4.2z" fill="currentColor"/><path d="M11.5 3.5v9" stroke="currentColor" stroke-width="1.7" stroke-linecap="round"/></svg>',
    overlay: '<svg class="ticon" viewBox="0 0 16 16" fill="none"><rect x="2" y="3" width="12" height="10" rx="1.6" stroke="currentColor" stroke-width="1.5"/><rect x="8.6" y="8.4" width="4.4" height="3.6" rx="1" fill="currentColor"/></svg>',
    swap: '<svg class="ticon" viewBox="0 0 16 16" fill="none"><path d="M3.5 5h9M3.5 5l2-2M3.5 5l2 2M12.5 11h-9M12.5 11l-2-2M12.5 11l-2 2" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/></svg>',
    lock: '<svg class="ticon" viewBox="0 0 16 16" fill="none"><rect x="3.4" y="7.3" width="9.2" height="5.9" rx="1.5" stroke="currentColor" stroke-width="1.5"/><path d="M5.4 7.3V5.7a2.6 2.6 0 0 1 5.2 0v1.6" stroke="currentColor" stroke-width="1.5"/></svg>',
    fixreads: '<svg class="ticon" viewBox="0 0 16 16" fill="none"><circle cx="8" cy="8" r="3.6" stroke="currentColor" stroke-width="1.6"/><path d="M8 1.8v2M8 12.2v2M1.8 8h2M12.2 8h2" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/></svg>',
    nophone: '<svg class="ticon" viewBox="0 0 16 16" fill="none"><rect x="4" y="2" width="8" height="12" rx="1.6" stroke="currentColor" stroke-width="1.5"/><path d="M6.2 11.5h3.6" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/><path d="M2 2l12 12" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/></svg>',
  };
  function ico(n) { return ICONS[n] || ''; }

  function evp(e) {
    var r = ov.getBoundingClientRect();
    return { x: e.clientX - r.left, y: e.clientY - r.top };
  }

  function b64bytes(s) {
    var b = atob(s);
    var u = new Uint8Array(b.length);
    for (var i = 0; i < b.length; i++) u[i] = b.charCodeAt(i);
    return u;
  }

  function bytesToB64(u8) {
    var s = '';
    for (var i = 0; i < u8.length; i++) s += String.fromCharCode(u8[i]);
    return btoa(s);
  }

  function isTyping(el) {
    return el && (/^(INPUT|SELECT|TEXTAREA)$/.test(el.tagName) || el.isContentEditable);
  }

  // Transient top-right notification for one-off events (saved / published /
  // failures). Persistent state stays in the inline status spans next to its
  // controls.
  function toast(msg, kind, ms) {
    kind = kind || 'info'; ms = ms || 5200;
    var host = document.getElementById('toasts');
    if (!host) { host = document.createElement('div'); host.id = 'toasts'; document.body.appendChild(host); }
    var t = document.createElement('div'); t.className = 'toast ' + kind;
    t.innerHTML = '<span class="ti">' + (ICONS[kind] || ICONS.info) + '</span><span>' + msg + '</span>';
    host.appendChild(t);
    var kill = function () { t.classList.add('out'); setTimeout(function () { t.remove(); }, 280); };
    var timer = setTimeout(kill, ms);
    t.onclick = function () { clearTimeout(timer); kill(); };
    return t;
  }

  // Promise-based modal — replaces native prompt/confirm/alert so dialogs match
  // the page. opts: {title, body|bodyHtml, actions:[{label,value,ghost}], escapeValue,
  // collect} — with collect, resolves {value, fields:{id:text}} reading the
  // modal's inputs/selects. Enter in a field triggers the last (primary) action.
  // The floating control panel, when one is open. Registered by engine/overlay.js
  // rather than passed per call: a modal that forgets to mirror is invisible to
  // an operator watching Overwatch, and "remember to pass it" is exactly how
  // that gets forgotten. Every uiModal caller mirrors automatically.
  var pipGetter = null;
  function setPipGetter(fn) { pipGetter = fn; }
  function livePip() {
    try { var w = pipGetter && pipGetter(); return (w && !w.closed) ? w : null; }
    catch (e) { return null; }
  }

  // A modal is a QUESTION, and the whole point of the pop-out panel is that the
  // operator never alt-tabs. Asking on a page they cannot see is a hang: on
  // 2026-09-08 the wrong-match guard blocked correctly and the operator, working
  // from the panel, saw nothing at all. So the question is drawn in BOTH
  // documents and either one answers it; the first answer closes the other.
  //
  // `collect` modals are NOT mirrored - they read values back out of their own
  // inputs, and two copies of a form is a question about which one is real. The
  // panel gets a line pointing at the main window instead. Nothing mid-capture
  // uses collect today.
  function mirrorIntoPip(w, opts, done) {
    var d = w.document;
    var back = d.getElementById('owdb-mback');
    if (!back) {
      back = d.createElement('div'); back.id = 'owdb-mback';
      back.style.cssText = 'position:fixed;inset:0;z-index:99999;display:flex;'
        + 'align-items:center;justify-content:center;padding:10px;'
        + 'background:rgba(0,0,0,.62);font:13px system-ui,sans-serif';
      d.body.appendChild(back);
    }
    back.innerHTML = ''; back.style.display = 'flex';
    var card = d.createElement('div');
    card.style.cssText = 'background:#16181d;color:#e9ecf1;border:1px solid #333a45;'
      + 'border-radius:10px;padding:12px 13px;max-width:100%;max-height:100%;overflow:auto;'
      + 'box-shadow:0 10px 34px rgba(0,0,0,.6)';
    if (opts.title) {
      var h = d.createElement('div');
      h.style.cssText = 'font-weight:700;font-size:13px;margin-bottom:6px';
      h.textContent = opts.title; card.appendChild(h);
    }
    var b = d.createElement('div');
    b.style.cssText = 'font-size:12px;color:#aab2bf;line-height:1.5;margin-bottom:10px';
    if (opts.collect) {
      b.textContent = 'Answer this in the main owdb window.';
    } else if (opts.bodyHtml) { b.innerHTML = opts.bodyHtml; } else if (opts.body) { b.textContent = opts.body; }
    card.appendChild(b);
    if (!opts.collect) {
      var row = d.createElement('div');
      row.style.cssText = 'display:flex;gap:6px;justify-content:flex-end;flex-wrap:wrap';
      (opts.actions || [{ label: 'OK', value: true }]).forEach(function (a) {
        var btn = d.createElement('button'); btn.type = 'button'; btn.textContent = a.label;
        btn.style.cssText = 'padding:6px 11px;border-radius:7px;cursor:pointer;font:inherit;'
          + 'font-weight:700;border:1px solid #3a4250;'
          + (a.ghost ? 'background:#20242b;color:#cfd6e0' : 'background:#5b6ee1;color:#fff;border-color:#5b6ee1');
        btn.onclick = function () { done(a.value); };
        row.appendChild(btn);
      });
      card.appendChild(row);
    }
    back.appendChild(card);
  }
  function clearPipModal(w) {
    try {
      var back = w && !w.closed && w.document.getElementById('owdb-mback');
      if (back) { back.innerHTML = ''; back.style.display = 'none'; }
    } catch (e) { /* the panel can close mid-answer; nothing to clean up then */ }
  }

  function uiModal(opts) {
    return new Promise(function (res) {
      var back = document.getElementById('mback'); back.innerHTML = '';
      var m = document.createElement('div'); m.className = 'modal';
      if (opts.title) { var h = document.createElement('h3'); h.textContent = opts.title; m.appendChild(h); }
      var body = document.createElement('div'); body.className = 'mbody';
      if (opts.bodyHtml) body.innerHTML = opts.bodyHtml; else if (opts.body) body.textContent = opts.body;
      m.appendChild(body);
      var row = document.createElement('div'); row.className = 'mrow';
      var pip = livePip();
      var settled = false;
      var done = function (v) {
        if (settled) return;              // both copies are live; the first answer wins
        settled = true;
        back.classList.remove('open'); back.innerHTML = ''; document.removeEventListener('keydown', onkey, true);
        if (pip) clearPipModal(pip);
        if (!opts.collect) { res(v); return; }
        var fields = {}; m.querySelectorAll('input,select,textarea').forEach(function (el) { fields[el.id] = el.value; }); res({ value: v, fields: fields });
      };
      var acts = opts.actions || [{ label: 'OK', value: true }];
      acts.forEach(function (a) {
        var b = document.createElement('button'); b.type = 'button'; b.textContent = a.label;
        if (a.ghost) b.className = 'ghost'; b.onclick = function () { done(a.value); }; row.appendChild(b);
      });
      m.appendChild(row); back.appendChild(m); back.classList.add('open');
      // Draw the same question in the control panel, so an operator watching
      // Overwatch can answer without alt-tabbing back to a page they cannot see.
      if (pip) { try { mirrorIntoPip(pip, opts, done); } catch (e) { pip = null; } }
      var onkey = function (e) { if (e.key === 'Escape') { e.stopPropagation(); done(opts.escapeValue !== undefined ? opts.escapeValue : null); } };
      document.addEventListener('keydown', onkey, true);
      // Escape works from whichever window has focus - the panel takes keyboard
      // shortcuts already, so it must not be the one place Escape does nothing.
      if (pip) { try { pip.document.addEventListener('keydown', onkey, true); } catch (e) { /* panel closed */ } }
      var primary = row.lastChild;
      m.querySelectorAll('input').forEach(function (inp) { inp.addEventListener('keydown', function (e) { if (e.key === 'Enter') { e.preventDefault(); primary.click(); } }); });
      var first = m.querySelector('input,select'); if (first) first.focus();
    });
  }

  function uiConfirm(msg, title) {
    return uiModal({
      title: title || 'Are you sure?', body: msg, escapeValue: false,
      actions: [{ label: 'Cancel', value: false, ghost: true }, { label: 'Confirm', value: true }],
    });
  }

  var Mod = {
    esc: esc,
    css: css,
    scl: scl,
    ico: ico,
    evp: evp,
    b64bytes: b64bytes,
    bytesToB64: bytesToB64,
    isTyping: isTyping,
    toast: toast,
    uiModal: uiModal,
    uiConfirm: uiConfirm,
    setPipGetter: setPipGetter,
  };

  if (typeof module !== 'undefined' && module.exports) module.exports = Mod;
  else global.OWDBUtil = Mod;
})(typeof self !== 'undefined' ? self : this);

// tools/replay_bot/console/server.js
// The replay-bot console: run any capture phase on its own against the live
// client, watch it, time it, retry it with a different wait. See ARCHITECTURE.md
// §14 and specs/2026-09-10-replay-bot-console-design.md.
//
//   node tools/replay_bot/console/server.js     then open http://127.0.0.1:8789
//
// WHAT IT IS FOR. run.js is an unattended loop; when a phase of it misbehaves
// the only way to look was to spend another code and read the frames after. This
// runs one phase at a time - clear the ESC menu, open the events viewer,
// calibrate the bar, seek to a second, grab and read the HUD, leave - holding a
// live session so calibrate-then-seek works across clicks, and serving every
// frame a phase took back to the page.
//
// COST. Only the `import` phase spends a code, and only from the rotating
// 20-code stack (state/console_codes.json): pull the top, import it, push it to
// the bottom. 20 is well clear of the client's 10-import ring, so a code that
// comes back around has long since been evicted and re-imports cleanly. It is
// behind an explicit confirm and a spent-this-session counter.
//
// LOCAL ONLY. Binds 127.0.0.1, rejects a cross-origin or non-loopback request
// the way review/server.js does, and runs one phase at a time - a phase owns the
// machine's mouse and keyboard.

const http = require('http');
const fs = require('fs');
const path = require('path');

const H = require('../host.js');
const I = require('../input.js');
const D = require('../driver.js');
const R = require('../recorder.js');
const CS = require('../clientstate.js');
const P = require('../phases.js');
const C = require('../capture.js');
const Drag = require('../drag.js');
const calib = require('../calib.js');
const Crop = require('../crop.js');
const T = require('../timeline.js');
const TIMING = require('../timing.js');

const HOST = '127.0.0.1';
const PORT = Number(process.env.OWDB_CONSOLE_PORT) || 8789;
const PAGE = path.join(__dirname, 'page.html');
const RBOT = path.join(__dirname, '..');
const FRAMES = path.join(RBOT, 'frames');
const CODES_FILE = path.join(RBOT, 'state', 'console_codes.json');
const FEED = path.join(RBOT, '..', '..', 'docs', 'capture', 'data.json');

const wait = (ms) => new Promise((r) => setTimeout(r, ms));

// ---------------------------------------------------------------- pure ----

function readJson(p, fallback) {
  try { return JSON.parse(fs.readFileSync(p, 'utf8')); } catch (e) { return fallback; }
}

// A code typed into the game, checked the same way gui.js checks one.
function safeCode(code) {
  const s = String(code == null ? '' : code).trim().toUpperCase();
  if (!/^[A-Z0-9]{1,12}$/.test(s)) throw new Error('bad code: ' + JSON.stringify(code));
  return s;
}

function safeSeconds(v) {
  const n = Number(v);
  if (!Number.isFinite(n) || n < 0 || n > 7200) {
    throw new Error('seconds out of range: ' + JSON.stringify(v));
  }
  return n;
}

// The loopback / cross-origin guard from review/server.js: the Host header must
// name loopback (kills DNS rebinding), and a mutating request may not carry a
// cross-origin Origin (kills the form-POST CSRF with no preflight).
function crossOrigin(req) {
  const host = String(req.headers.host || '').split(':')[0].toLowerCase();
  if (host !== 'localhost' && host !== '127.0.0.1' && host !== '[::1]') return true;
  const origin = req.headers.origin;
  if (origin) {
    try {
      const h = new URL(origin).hostname.toLowerCase();
      if (h !== 'localhost' && h !== '127.0.0.1' && h !== '::1') return true;
    } catch (e) { return true; }
  }
  return false;
}

// The 20-code rotating stack. `pull` takes the top and pushes it to the bottom.
function loadCodes() {
  const raw = readJson(CODES_FILE, { codes: [] });
  return Array.isArray(raw.codes) ? raw.codes.map(safeCode) : [];
}
function saveCodes(codes) {
  fs.mkdirSync(path.dirname(CODES_FILE), { recursive: true });
  fs.writeFileSync(CODES_FILE, JSON.stringify({ codes }, null, 2) + '\n', 'utf8');
}

// Run `fn` with `over` (a {ns:{key:number}} subset) merged onto TIMING in place,
// then restore. The console runs one phase at a time, so the mutation is never
// concurrent - this is how a slider value is tried without saving it.
async function withTiming(over, fn) {
  if (!over || !Object.keys(over).length) return fn();
  const snap = JSON.parse(JSON.stringify(pickNs(TIMING)));
  TIMING.applyOver(TIMING, over);
  try { return await fn(); }
  finally { TIMING.NS.forEach((ns) => { TIMING[ns] = snap[ns]; }); }
}
function pickNs(t) {
  const out = {};
  t.NS.forEach((ns) => { out[ns] = t[ns]; });
  return out;
}

// ---------------------------------------------------------------- session ----
//
// io + driver + the bar it has calibrated, held across requests so a seek can
// follow a calibrate. Rebuilt by /api/session/reset.

function makeSession() {
  const lines = [];
  const io = C.makeIo({ framesDir: FRAMES, log: (m) => lines.push(String(m)) });
  const st = { ref: null, stepS: null, sampling: false, lines };

  const drvCtx = {
    sendKeys: io.sendKeys,
    focus: async () => {},
    settle: () => (st.sampling
      ? io.quiesce(TIMING.sample.quiesceMs)
      : io.settle()),
    position: async () => {
      const fresh = io.lastFrame && io.lastFrame();
      const knob = Crop.playheadX(
        await io.loadImage(fresh || await io.grabTo('pos')), calib);
      if (!knob || !st.ref) return null;
      return T.secondsAt(knob.centre, st.ref);
    },
    seekDrag: Drag.seeker({
      ref: () => st.ref,
      frame: () => (io.lastFrame && io.lastFrame()) || io.grabTo('drag-from'),
      loadImage: io.loadImage,
      playhead: (img) => Crop.playheadX(img, calib),
      play: io.playEvents,
      log: (m) => lines.push(m),
    }),
    stepS: 20,
  };
  const drv = D.make(drvCtx);
  return { io, drv, drvCtx, st };
}

// ---------------------------------------------------------------- phases ----
//
// Each returns a plain result; the handler adds the log lines and a fresh frame.
// `ctx` for the phases is { io, drv, log }.

function ctxOf(s) {
  return { io: s.io, drv: s.drv, log: (m) => s.st.lines.push(String(m)) };
}

const PHASES = {
  grab: async (s) => {
    const p = await s.io.grabTo('console');
    return { frame: path.basename(p) };
  },

  clientState: async (s) => ({
    inReplay: await CS.inReplay(s.io),
    escMenuUp: await CS.escMenuUp(s.io),
    replayHistoryUp: await CS.replayHistoryUp(s.io),
  }),

  clearEsc: async (s) => {
    const n = await CS.clearEscMenu(s.io, {
      sendKeys: I.sendKeys, wait, escWait: TIMING.esc.waitMs,
      tries: TIMING.esc.tries, tag: 'console', log: (m) => s.st.lines.push(m),
    });
    return { presses: n };
  },

  backOutOfList: async (s) => {
    let back = 0;
    for (; await CS.replayHistoryUp(s.io); back++) {
      if (back >= 2) throw new Error('still on the replay list after 2 ESCs');
      await I.sendKeys(['ESC']);
      await wait(TIMING.esc.waitMs);
    }
    return { escs: back };
  },

  import: async (s, args) => {
    if (!args.confirm) throw new Error('import spends a code - pass confirm:true');
    const codes = loadCodes();
    if (!codes.length) throw new Error('the code stack is empty - load codes first');
    const code = codes[0];
    s.st.lines.push('importing ' + code + ' (stack: ' + codes.length + ')');
    await R.play('open-import', { code, speed: TIMING.chunk.speed });
    saveCodes(codes.slice(1).concat([code]));           // rotate: top -> bottom
    spent += 1;
    await CS.waitFor(s.io, true, TIMING.load.timeoutMs, 'the replay to load');
    await wait(TIMING.load.settleMs);
    return { code, spentThisSession: spent, nextUp: loadCodes()[0] || null };
  },

  leave: async (s) => {
    if (!await CS.inReplay(s.io)) return { note: 'not in a replay' };
    await R.play('leave-replay', { speed: TIMING.chunk.speed });
    await CS.waitFor(s.io, false, TIMING.exit.timeoutMs, 'the replay to close');
    return { left: true };
  },

  setInterval: async (s) => {
    if (!fs.existsSync(R.chunkPath('set-interval'))) {
      throw new Error('no "set-interval" chunk recorded');
    }
    await R.play('set-interval', { speed: TIMING.chunk.speed });
    await P.ensurePanelOpen(ctxOf(s));
    return { done: true };
  },

  pause: async (s) => {
    const r = await P.ensurePaused(s.io, s.drv);
    return { paused: r.paused, pressed: r.pressed };
  },

  eventsViewer: async (s) => {
    const r = await P.openEventsViewer(ctxOf(s));
    return { open: r.open, steps: r.steps, panelRows: r.after };
  },

  calibrateBar: async (s, args) => {
    const r = await P.calibrateBar(ctxOf(s), {
      stepS: args.stepS ? safeSeconds(args.stepS) : undefined,
      log: (m) => s.st.lines.push(String(m)),
    });
    s.st.ref = r.ref;
    s.st.stepS = r.stepS;
    s.drvCtx.stepS = r.stepS;
    const dur = P.deriveDuration({
      ref: r.ref, pxPerSec: r.pxPerSec, atZeroWidth: r.atZero.width, told: null,
    });
    return {
      ref: r.ref, stepS: r.stepS, pxPerSec: r.pxPerSec,
      duration: dur.duration, secondsPerPixel: r.ref.stepS / r.ref.stepPx,
    };
  },

  measureRate: async (s) => {
    const r = await P.measureRate(s.io, s.drv);
    return { pxPerSec: r.pxPerSec, elapsed: r.elapsed };
  },

  structure: async (s, args) => {
    if (!s.st.ref) throw new Error('calibrate the bar first');
    const img = await s.io.loadImage(await s.io.grabTo('structure'));
    const duration = args.duration
      ? safeSeconds(args.duration)
      : P.deriveDuration({
          ref: s.st.ref, pxPerSec: null,
          atZeroWidth: 0, told: null,
        }).implied;
    const r = P.readStructure(img, {
      ref: s.st.ref, duration, stepS: s.st.stepS,
      log: (m) => s.st.lines.push(String(m)),
      mmss: C.mmss,
    });
    return { segments: r.segments, per: r.per, plan: r.plan, duration };
  },

  seek: async (s, args) => {
    if (!s.st.ref) throw new Error('calibrate the bar first');
    const t = safeSeconds(args.t);
    s.st.sampling = false;
    const at = await s.drv.seekTo(t);
    return { target: t, landed: at, errS: at - t };
  },

  sample: async (s, args) => {
    if (!s.st.ref) throw new Error('calibrate the bar first');
    const t = safeSeconds(args.t);
    s.st.sampling = true;
    const matcher = s.matcher || (s.matcher = P.makeMatcher());
    const r = await P.sampleAt(ctxOf(s), t, {
      matcher, stepS: s.st.stepS, mmss: C.mmss,
      log: (m) => s.st.lines.push(String(m)),
    });
    s.st.sampling = false;
    if (r.missed) return { missed: true, reason: r.reason, target: t, landed: r.at };
    return {
      target: t, landed: r.at, worst: r.worst,
      a: r.a.map(hero), b: r.b.map(hero),
      frame: r.framePath ? path.basename(r.framePath) : null,
    };
  },
};

const hero = (x) => ({ name: x.name, score: Number(x.score.toFixed(2)) });

// ---------------------------------------------------------------- server ----

let session = null;
let busy = null;
let spent = 0;

function sessionOf() {
  if (!session) session = makeSession();
  return session;
}

async function exclusive(what, fn) {
  if (busy) throw new Error('already running "' + busy + '" - one phase at a time');
  busy = what;
  const s = sessionOf();
  s.st.lines.length = 0;
  try {
    const out = await fn(s);
    // A fresh frame to show, unless the phase already named one.
    let frame = out && out.frame;
    if (!frame) {
      try { frame = path.basename(await s.io.grabTo('console-view')); } catch (e) { /* ok */ }
    }
    return { ok: true, result: out, log: s.st.lines.slice(), frame };
  } finally {
    busy = null;
  }
}

function send(res, code, body, type) {
  res.writeHead(code, {
    'Content-Type': type || 'application/json',
    'Cache-Control': 'no-store',
  });
  res.end(typeof body === 'string' || Buffer.isBuffer(body) ? body : JSON.stringify(body));
}

function readBody(req) {
  return new Promise((resolve, reject) => {
    let n = 0;
    const parts = [];
    req.on('data', (c) => {
      n += c.length;
      if (n > 65536) { reject(new Error('body too large')); req.destroy(); return; }
      parts.push(c);
    });
    req.on('end', () => {
      try { resolve(parts.length ? JSON.parse(Buffer.concat(parts).toString('utf8')) : {}); }
      catch (e) { reject(new Error('body is not JSON')); }
    });
    req.on('error', reject);
  });
}

async function state() {
  let rect = null;
  let rectError = null;
  try { rect = await R.windowRect(); } catch (e) { rectError = e.message; }
  const feed = readJson(FEED, {});
  return {
    rect, rectError, busy, spentThisSession: spent,
    timing: pickNs(TIMING),
    defaults: TIMING.DEFAULTS,
    codes: loadCodes(),
    wipeDate: feed.code_wipe_date || null,
    feedBuilt: feed.built_at || null,
    calibrated: !!(session && session.st.ref),
    phases: Object.keys(PHASES),
  };
}

const ROUTES = {
  'GET /api/state': async () => state(),

  'POST /api/run': async (body) => {
    const name = String(body.phase || '');
    if (!PHASES[name]) throw new Error('no phase "' + name + '"');
    return withTiming(body.timing, () => exclusive(name, (s) => PHASES[name](s, body.args || {})));
  },

  'POST /api/session/reset': async () => {
    if (busy) throw new Error('a phase is running');
    try { session && session.io.sweepTransient && session.io.sweepTransient(); } catch (e) { /* ok */ }
    session = null;
    return { reset: true };
  },

  'POST /api/timing/save': async (body) => {
    TIMING.save(body.timing || {});
    return { saved: pickNs(TIMING) };
  },

  'POST /api/timing/reset': async () => {
    TIMING.clearSaved();
    return { timing: pickNs(TIMING) };
  },

  'POST /api/codes': async (body) => {
    const codes = (Array.isArray(body.codes) ? body.codes : String(body.codes || '')
      .split(/[\s,]+/)).map((c) => c.trim()).filter(Boolean).map(safeCode);
    saveCodes(codes);
    return { codes };
  },

  'POST /api/codes/rotate': async () => {
    const codes = loadCodes();
    if (codes.length) saveCodes(codes.slice(1).concat([codes[0]]));
    return { codes: loadCodes() };
  },
};

function createServer() {
  return http.createServer(async (req, res) => {
    const url = req.url.split('?')[0];

    if (crossOrigin(req)) { send(res, 403, { error: 'cross-origin request refused' }); return; }

    if (req.method === 'GET' && (url === '/' || url === '/index.html')) {
      send(res, 200, fs.readFileSync(PAGE), 'text/html; charset=utf-8');
      return;
    }

    if (req.method === 'GET' && url.startsWith('/frames/')) {
      const name = path.basename(decodeURIComponent(url.slice('/frames/'.length)));
      const abs = path.join(FRAMES, name);
      if (!abs.startsWith(FRAMES + path.sep) || !fs.existsSync(abs)) {
        send(res, 404, 'not found', 'text/plain'); return;
      }
      const type = name.endsWith('.bmp') ? 'image/bmp' : 'image/png';
      send(res, 200, fs.readFileSync(abs), type);
      return;
    }

    const route = ROUTES[req.method + ' ' + url];
    if (!route) { send(res, 404, { error: 'no route ' + req.method + ' ' + url }); return; }

    try {
      const body = req.method === 'POST' ? await readBody(req) : {};
      send(res, 200, await route(body));
    } catch (e) {
      send(res, 400, { error: e.message });
    }
  });
}

function main() {
  if (!fs.existsSync(FRAMES)) fs.mkdirSync(FRAMES, { recursive: true });
  process.on('SIGINT', () => { try { H.close(); } catch (e) {} process.exit(0); });
  createServer().listen(PORT, HOST, () => {
    console.log(`replay-bot console on http://${HOST}:${PORT}`);
    console.log('  Overwatch must be running. Ctrl-C to stop.');
  });
}

module.exports = {
  crossOrigin, safeCode, safeSeconds, loadCodes, saveCodes, pickNs, withTiming,
  PHASES, createServer, CODES_FILE,
};

if (require.main === module) main();

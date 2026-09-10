// tools/replay_bot/drag_tuner.js
// A local page for tuning the seek-by-drag gesture's timings by hand.
//
//   node tools/replay_bot/drag_tuner.js      then open http://127.0.0.1:8788
//
// WHY THIS EXISTS. drag.js's TIMING and the settle after a seek were found by
// guess-and-probe, and the guesses kept being wrong in ways that produced
// confident nonsense: a drag that landed 100s short, samples read
// mid-transition. probe_drag/probe_limits measure one number per run and take a
// couple of minutes each. The gesture is finicky enough that a slider you can
// nudge between drags beats a bisection - so this puts each hardcoded timing on
// a slider, runs one real drag (or the four-target sweep) with the live values,
// and reports both whether it LANDED and whether the HUD had SETTLED by the
// time it was read.
//
// COSTS NO CODES. Like probe_drag, it needs a replay already open with the
// media controls up (press N). A code is spent on IMPORTING a replay, never on
// watching one already in the history list.
//
// LOCAL ONLY, and one operation at a time - the same rules as gui.js. It binds
// 127.0.0.1 because what it exposes is "run PowerShell that drags in the game",
// it rejects a cross-origin or non-loopback request the way review/server.js
// does, and it refuses a second request while a drag is in flight because both
// own the machine's mouse.
//
// Save writes drag_timing.json, which drag.js loads over its defaults. That
// file is gitignored and temporary: once a set of numbers holds across several
// replays, write them into drag.js's TIMING as the new defaults in an ordinary
// commit and delete the json.

const http = require('http');
const fs = require('fs');
const path = require('path');
const canvas = require('@napi-rs/canvas');

const G = require('./grab.js');
const H = require('./host.js');
const I = require('./input.js');
const D = require('./driver.js');
const R = require('./recorder.js');
const Drag = require('./drag.js');
const calib = require('./calib.js');
const Crop = require('./crop.js');
const Match = require('./match.js');
const T = require('./timeline.js');

const HOST = '127.0.0.1';
const PORT = Number(process.env.OWDB_TUNER_PORT) || 8788;
const PAGE = path.join(__dirname, 'drag_tuner.html');
const FRAMES = path.join(__dirname, 'frames');
const OVERRIDE = path.join(__dirname, 'drag_timing.json');
const REFS = require(path.join(__dirname, '../../docs/capture/refs.json'));

const KNOBS = ['prePress', 'postPress', 'perPoint', 'dwell', 'hopPx', 'settle'];

const wait = (ms) => new Promise((r) => setTimeout(r, ms));
const M = Match.make(REFS, { PAD: calib.FROZEN.ref.PAD });

// ---------------------------------------------------------------- pure ----

// Body -> a clean TIMING object: every knob present, a finite number, clamped
// to something the game can be asked to wait. hopPx cannot be zero (plan()
// divides a distance by it); the rest floor at zero.
function cleanTiming(raw) {
  const out = {};
  for (const k of KNOBS) {
    const v = Number((raw || {})[k]);
    if (!Number.isFinite(v)) {
      throw new Error('bad value for ' + k + ': ' + JSON.stringify((raw || {})[k]));
    }
    out[k] = Math.max(k === 'hopPx' ? 1 : 0, Math.round(v));
  }
  return out;
}

function safeTarget(v) {
  const n = Number(v);
  if (!Number.isFinite(n) || n < 0 || n > 7200) {
    throw new Error('target seconds out of range: ' + JSON.stringify(v));
  }
  return n;
}

function readJson(p) {
  try { return JSON.parse(fs.readFileSync(p, 'utf8')); } catch (e) { return null; }
}

// Same loopback/cross-origin guard review/server.js uses: the Host header must
// name loopback (kills DNS rebinding), and a mutating request may not carry a
// cross-origin Origin (kills the form-POST CSRF that has no preflight).
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

// ----------------------------------------------------------------- rig ----

let frameNo = 0;
async function grab(tag) {
  const p = path.join(FRAMES, `drag-tuner-${tag}-${frameNo++}.png`);
  const r = await G.capture(p);
  if (!r.ok) throw new Error('grab failed: ' + r.reason);
  return canvas.loadImage(p);
}

async function knob(tag) {
  const k = Crop.playheadX(await grab(tag), calib);
  return k ? k.centre : null;
}

// The least confident of the ten HUD cells - what a frame caught mid-transition
// shows up as. A settled frame scores the same as one read later still.
async function worstCell(img) {
  const crops = Crop.all(img, calib);
  let worst = 1;
  for (const side of ['a', 'b']) {
    for (const c of crops[side]) {
      const s = M.match(c, side).score;
      if (s < worst) worst = s;
    }
  }
  return worst;
}

// This map's bar, calibrated exactly the way capture.js and probe_drag do it:
// jump to start, read the playhead, press the skip key once, read it again.
async function calibrateBar() {
  const img = await grab('start');
  const chk = calib.check({ w: img.width, h: img.height });
  if (!chk.ok) throw new Error(chk.reason);
  if (!calib.hudPresent(Crop.hudTint(img, calib))) {
    throw new Error('no replay on screen - open one from the history list first');
  }
  if (!Crop.playheadX(img, calib)) {
    throw new Error('no playhead - press N in the replay to bring the media controls up');
  }

  await I.sendKeys([D.KEY.jumpToStart]);
  await wait(900);
  const zeroX = await knob('zero');
  await I.sendKeys([D.KEY.forward]);
  await wait(900);
  const oneX = await knob('one');
  if (zeroX === null || oneX === null) throw new Error('lost the playhead while calibrating');

  const stepPx = oneX - zeroX;
  if (stepPx <= 0) throw new Error(`one press moved ${stepPx}px - is the replay paused?`);
  return { zeroX, stepPx, stepS: 60 };
}

// One drag to `toS` with the live timing, then wait `settle` and read where the
// playhead landed and how settled the HUD was. Mirrors probe_drag's inner loop,
// plus the worst-cell read.
async function oneDrag(ref, toS, timing) {
  const fromX = await knob('from');
  if (fromX === null) throw new Error('lost the playhead before the drag');

  const t0 = Date.now();
  await R.playEvents([Drag.plan(ref, fromX, toS, timing)], { name: 'drag-tune' });
  await wait(timing.settle);
  const after = await grab('after');
  const took = (Date.now() - t0) / 1000;

  const landed = Crop.playheadX(after, calib);
  if (!landed) return { target: toS, landedS: null, errS: null, worst: null, took };

  const landedS = T.secondsAt(landed.centre, ref);
  return {
    target: toS,
    landedS,
    errS: landedS - toS,
    worst: await worstCell(after),
    took,
  };
}

// probe_drag's target set, dropped to what fits this map.
function sweepTargets(ref) {
  const span = (calib.FROZEN.timeline.x1 - ref.zeroX) / ref.stepPx * 60;
  return [120, 300, 600, 180].filter((t) => t < span - 60);
}

// Old drag-tuner frames pile up fast over a tuning session; keep only the
// latest run's, so a bad landing still has frames to look at.
function clearFrames() {
  if (!fs.existsSync(FRAMES)) { fs.mkdirSync(FRAMES, { recursive: true }); return; }
  for (const f of fs.readdirSync(FRAMES)) {
    if (/^drag-tuner-.*\.png$/.test(f)) {
      try { fs.unlinkSync(path.join(FRAMES, f)); } catch (e) { /* already gone */ }
    }
  }
}

// -------------------------------------------------------------- routes ----

let busy = null;
async function exclusive(what, fn) {
  if (busy) throw new Error('already ' + busy + ' - wait for it to finish');
  busy = what;
  try { return await fn(); } finally { busy = null; }
}

const ROUTES = {
  'GET /api/state': async function () {
    let rect = null;
    let rectError = null;
    try { rect = await R.windowRect(); } catch (e) { rectError = e.message; }
    return {
      rect,
      rectError,
      knobs: KNOBS,
      defaults: Drag.TIMING,          // drag.js's live TIMING (override folded in)
      saved: readJson(OVERRIDE),      // drag_timing.json, if drag.js is running off one
      busy,
    };
  },

  'POST /api/test': async function (body) {
    const timing = cleanTiming(body.timing);
    const target = safeTarget(body.target);
    return exclusive('testing', async function () {
      clearFrames();
      const ref = await calibrateBar();
      const span = Math.round((calib.FROZEN.timeline.x1 - ref.zeroX) / ref.stepPx * 60);
      if (target > span - 30) {
        throw new Error(`t=${target}s is off this ${Math.floor(span / 60)}:` +
          String(span % 60).padStart(2, '0') + ' map - pick a smaller target');
      }
      const row = await oneDrag(ref, target, timing);
      return { ref, timing, row };
    });
  },

  'POST /api/sweep': async function (body) {
    const timing = cleanTiming(body.timing);
    return exclusive('sweeping', async function () {
      clearFrames();
      const ref = await calibrateBar();
      const targets = sweepTargets(ref);
      if (!targets.length) throw new Error('this replay is too short to sweep');
      // Dragged from wherever the last one landed, not from a reset origin -
      // probe_drag's order (120, 300, 600, 180) ends on a backward drag on
      // purpose, since that is where the scrubber-lag bug showed up.
      const rows = [];
      for (const toS of targets) {
        rows.push(await oneDrag(ref, toS, timing));
      }
      const worstErr = Math.max.apply(null, rows.map((r) => Math.abs(r.errS == null ? 99 : r.errS)));
      return { ref, timing, rows, worstErr };
    });
  },

  'POST /api/save': async function (body) {
    const timing = cleanTiming(body.timing);
    fs.writeFileSync(OVERRIDE, JSON.stringify(timing, null, 2) + '\n', 'utf8');
    return { saved: timing, path: OVERRIDE };
  },

  'POST /api/clear-saved': async function () {
    let removed = false;
    try { fs.unlinkSync(OVERRIDE); removed = true; } catch (e) { /* was not there */ }
    return { removed, path: OVERRIDE };
  },
};

// -------------------------------------------------------------- server ----

function send(res, code, body, type) {
  res.writeHead(code, {
    'Content-Type': type || 'application/json',
    'Cache-Control': 'no-store',
  });
  res.end(typeof body === 'string' || Buffer.isBuffer(body) ? body : JSON.stringify(body));
}

function readBody(req) {
  return new Promise(function (resolve, reject) {
    let n = 0;
    const parts = [];
    req.on('data', function (c) {
      n += c.length;
      if (n > 8192) { reject(new Error('body too large')); req.destroy(); return; }
      parts.push(c);
    });
    req.on('end', function () {
      try { resolve(parts.length ? JSON.parse(Buffer.concat(parts).toString('utf8')) : {}); }
      catch (e) { reject(new Error('body is not JSON')); }
    });
    req.on('error', reject);
  });
}

function createServer() {
  return http.createServer(async function (req, res) {
    const url = req.url.split('?')[0];

    if (crossOrigin(req)) { send(res, 403, { error: 'cross-origin request refused' }); return; }

    if (req.method === 'GET' && (url === '/' || url === '/index.html')) {
      send(res, 200, fs.readFileSync(PAGE), 'text/html; charset=utf-8');
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
  // The grab/key host is unref'd, so leaving it open does not hold the process;
  // close it on the way out anyway, the way the probe tools do.
  process.on('SIGINT', function () { try { H.close(); } catch (e) {} process.exit(0); });

  createServer().listen(PORT, HOST, function () {
    console.log(`drag tuner on http://${HOST}:${PORT}`);
    console.log('  Overwatch must be running, with a replay open and its controls up (N).');
    console.log('  Ctrl-C to stop.');
  });
}

module.exports = { cleanTiming, safeTarget, crossOrigin, sweepTargets, createServer, KNOBS };

if (require.main === module) main();

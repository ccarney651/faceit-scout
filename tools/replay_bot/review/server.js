// tools/replay_bot/review/server.js
// The local review page's server. See
// specs/2026-09-10-replay-bot-autonomous-scouting-design.md §4.
//
//   node tools/replay_bot/review/server.js [<session>] [--open] [--port N]
//
// Reads out/<session>.review.json (newest by default), serves the page and the
// per-round portrait crops, takes corrections back, and on finalize rebuilds
// the contribution from the confirmed rounds. Upload POSTs that contribution to
// the same worker docs/capture/ uploads to, as contributor `replay-bot`.
//
// Dependency-free on purpose: Node's http, and the repo's own emit.js. No
// framework, no build step - it is one operator on localhost.

const http = require('http');
const fs = require('fs');
const path = require('path');
const crypto = require('crypto');

const Emit = require('../emit.js');
const RunJS = require('../run.js');

const RBOT = path.join(__dirname, '..');
const OUT = path.join(RBOT, 'out');
const STATE = path.join(RBOT, 'state');
const REPO = path.join(RBOT, '..', '..');
const FEED = path.join(REPO, 'docs', 'capture', 'data.json');
const REFS = path.join(REPO, 'docs', 'capture', 'refs.json');
const ICONS = path.join(REPO, 'docs', 'capture', 'hero_icons.json');
const PAGE = path.join(__dirname, 'page.html');
const RUNJS_PATH = path.join(RBOT, 'run.js');
const ENDPOINT = 'https://upload.owdb.io';
const CONTRIBUTOR = 'replay-bot';

// ---------------------------------------------------------------- pure ----

function readJson(p, fallback) {
  try { return JSON.parse(fs.readFileSync(p, 'utf8')); } catch (e) { return fallback; }
}

// The newest out/*.review.json, or null. A run writes the file per map, so
// "newest" is "the session still being reviewed" in the common case.
function newestReview(dir) {
  let best = null;
  let bestAt = -1;
  for (const f of (fs.existsSync(dir) ? fs.readdirSync(dir) : [])) {
    if (!f.endsWith('.review.json')) continue;
    const at = fs.statSync(path.join(dir, f)).mtimeMs;
    if (at > bestAt) { bestAt = at; best = path.join(dir, f); }
  }
  return best;
}

// { guid, name, role, icon } per hero, for the type-ahead. Deduped by guid over
// refs.json's per-variant entries; role from the feed, icon from hero_icons.json.
function heroList(refs, heroRoles, icons, customHeroes) {
  const seen = new Map();
  for (const r of (refs && refs.refs) || []) {
    if (seen.has(r.g)) continue;
    seen.set(r.g, {
      guid: r.g, name: r.n,
      role: (heroRoles && heroRoles[r.g]) || null,
      icon: (icons && icons[String(r.n).toLowerCase()]) || null,
    });
  }
  for (const guid of Object.keys(customHeroes || {})) {
    if (seen.has(guid)) continue;
    const c = customHeroes[guid];
    seen.set(guid, { guid, name: c.name || guid, role: c.role || null, icon: null });
  }
  return [...seen.values()].sort((a, b) => a.name.localeCompare(b.name));
}

// Replay one map's corrections over resolve.js's rounds, giving the rounds
// emit.fromRounds should ship. Corrections are data, applied here, so the
// machine's original read stays visible in the artifact beside them (§4.3).
function applyCorrections(rounds, corrections) {
  const out = JSON.parse(JSON.stringify(rounds || []));
  for (const c of corrections || []) {
    const round = out.find((r) => r.round_no === c.round_no);
    if (!round) continue;
    const slot = (round[c.side] || [])[c.slot];
    if (!slot) continue;
    if (c.kind === 'hero') {
      slot.guid = c.now_guid || null;
      slot.name = c.now_name || c.now_guid || null;
      slot.contested = false;
      slot.alt_guid = null;
      slot.segments = null;
      slot.flags = (slot.flags || []).filter((f) => f === 'attribution-abstained');
    } else if (c.kind === 'player') {
      slot.player_id = c.now_id || null;
      slot.player_conf = c.now_id ? 'operator' : null;
      slot.flags = (slot.flags || []).filter((f) => f !== 'attribution-abstained');
    }
  }
  return out;
}

// Failure messages are free text (thrown from wherever the loop broke), so
// categorising them is substring matching against the handful of distinct
// failure modes run.js actually raises - not a general classifier. Order
// matters only in that each message should match exactly one rule; add new
// rules above the fallback as run.js grows new failure text.
const FAILURE_RULES = [
  [/forward key is not working/, 'seek-stuck', 'seek key unresponsive'],
  [/events viewer would not open/, 'events-viewer', "events viewer wouldn't open"],
  [/could not foreground Overwatch/, 'focus', 'client focus lost'],
  [/timed out.*waiting for the replay to load/, 'load-timeout', 'replay load timeout'],
  [/ESC menu will not close/, 'stuck-menu', 'stuck menu (ESC)'],
];
function categorizeFailure(msg) {
  const m = String(msg || '');
  for (const [re, id, label] of FAILURE_RULES) if (re.test(m)) return { id, label };
  return { id: 'other', label: 'other' };
}

// state/attempts.json's failed entries, joined against the feed for map/team
// context and tagged with a category - what the review page's failures panel
// filters on. Sorted oldest first, same order the run attempted them in.
function buildRunArgs(body) {
  const args = [];
  if (body && body.divisions) args.push('--divisions', String(body.divisions));
  if (body && body.teams) args.push('--teams', String(body.teams));
  if (body && body.limit) args.push('--limit', String(body.limit));
  return args;
}

function startRun(ctx, body) {
  const args = buildRunArgs(body);
  try { fs.unlinkSync(path.join(ctx.stateDir, 'loop_stop.flag')); } catch (e) { /* fine */ }
  const proc = ctx.spawn(process.execPath, [RUNJS_PATH].concat(args), { cwd: ctx.repoDir });
  const run = { proc, log: [], subscribers: [], startedAt: Date.now(), exitInfo: null };
  const onData = (buf) => {
    const line = buf.toString();
    run.log.push(line);
    if (run.log.length > 5000) run.log.shift();
    run.subscribers.forEach((r) => r.write('data: ' + JSON.stringify(line) + '\n\n'));
  };
  proc.stdout.on('data', onData);
  proc.stderr.on('data', onData);
  proc.on('exit', (code, signal) => {
    run.exitInfo = { code, signal, at: Date.now() };
    run.subscribers.forEach((r) => r.end());
    run.subscribers = [];
  });
  ctx.run = run;
  return run;
}

const PRUNE_PATH = path.join(RBOT, 'prune_frames.js');

function runPrune(ctx, session) {
  return new Promise((resolve) => {
    const child = ctx.spawn(process.execPath, [PRUNE_PATH, session], { cwd: ctx.repoDir });
    let out = '';
    child.stdout.on('data', (b) => { out += b.toString(); });
    child.stderr.on('data', (b) => { out += b.toString(); });
    child.on('exit', () => resolve(out.trim()));
    child.on('error', (e) => resolve('prune failed to start: ' + e.message));
  });
}

const REFRESH_ENDPOINT = 'https://upload.owdb.io/refresh';
const REFRESH_WAIT_MS = 130000; // ~2min the worker takes, plus margin

async function startRefresh(ctx) {
  const feed = readJson(ctx.feedPath, {});
  if (RunJS.feedFreshness(feed, Date.now()).fresh) {
    ctx.refresh = { state: 'fresh', at: Date.now() };
    return ctx.refresh;
  }
  let res;
  try {
    res = await ctx.fetch(REFRESH_ENDPOINT, { method: 'POST' });
  } catch (e) {
    ctx.refresh = { state: 'failed', error: String(e && e.message || e) };
    return ctx.refresh;
  }
  if (!res.ok) {
    ctx.refresh = { state: 'failed', error: 'refresh endpoint returned ' + res.status };
    return ctx.refresh;
  }
  ctx.refresh = { state: 'pending', startedAt: Date.now() };
  ctx.setTimeout(async () => {
    try {
      await ctx.exec('git', ['fetch', 'origin'], { cwd: ctx.repoDir });
      await ctx.exec('git', ['checkout', 'origin/main', '--', 'docs/capture/data.json'], { cwd: ctx.repoDir });
      const nowFeed = readJson(ctx.feedPath, {});
      ctx.refresh = RunJS.feedFreshness(nowFeed, Date.now()).fresh
        ? { state: 'done', at: Date.now() }
        : { state: 'stale', error: 'still not built today after refresh' };
    } catch (e) {
      ctx.refresh = { state: 'failed', error: String(e && e.message || e) };
    }
  }, REFRESH_WAIT_MS);
  return ctx.refresh;
}

function attemptsTally(attempts) {
  let done = 0, failed = 0;
  Object.values(attempts || {}).forEach((v) => {
    if (v && v.status === 'failed') failed += 1; else done += 1;
  });
  return { done, failed, total: done + failed };
}

function failureList(attempts, feedCodes) {
  const byCode = new Map((feedCodes || []).map((c) => [c.code, c]));
  const out = [];
  for (const v of Object.values(attempts || {})) {
    if (v.status !== 'failed') continue;
    const cat = categorizeFailure(v.error);
    const fc = byCode.get(v.code) || {};
    out.push({
      code: v.code, started_at: v.started_at || null, error: v.error || null,
      category: cat.id, category_label: cat.label,
      match_id: fc.match_id || null, game_no: fc.game_no != null ? fc.game_no : null,
      map: fc.map || null, division: fc.division || null,
      team_a: fc.team_a || null, team_b: fc.team_b || null,
    });
  }
  out.sort((a, b) => String(a.started_at).localeCompare(String(b.started_at)));
  return out;
}

// The reviewed artifact -> a format-1 contribution. `codeOf` looks a map's guid
// up in the feed when the artifact did not carry one (older sessions).
function finalize(review, feed) {
  const byKey = {};
  for (const c of (feed && feed.codes) || []) byKey[c.match_id + ':' + c.game_no] = c;
  const maps = (review.maps || []).map((m) => {
    const rounds = applyCorrections(m.rounds, m.corrections);
    const fc = byKey[m.match_id + ':' + m.game_no] || {};
    const code = {
      code: m.demo_code, match_id: m.match_id, game_no: m.game_no,
      map: m.map_name || fc.map, map_guid: m.map_guid || fc.map_guid,
      map_category: m.map_category || fc.map_category,
      team_a: m.side_a_team, team_b: m.side_b_team,
      t1: m.side_a_team_id, t2: m.side_b_team_id,
    };
    return Emit.mapRecordFromRounds(code, rounds, {
      profile: { w: 2560, h: 1440, hud_variant: 'replay-bot' },
      capturedAt: m.captured_at,
    });
  });
  return Emit.file(maps, { contributor: CONTRIBUTOR });
}

// The throwaway identity, same meaning as docs/capture/'s localStorage token:
// the first upload under a name claims it; losing the token means the curator
// reassigns, never data loss.
function uploadToken(stateDir) {
  const p = path.join(stateDir, 'upload-token.json');
  const existing = readJson(p, null);
  if (existing && existing.token) return existing.token;
  const token = crypto.randomBytes(24).toString('hex');
  fs.mkdirSync(stateDir, { recursive: true });
  fs.writeFileSync(p, JSON.stringify({ token }, null, 2) + '\n');
  return token;
}

async function uploadWith(fetchImpl, contribution, token) {
  const res = await fetchImpl(ENDPOINT, {
    method: 'POST',
    headers: {
      'X-Owdb-Name': CONTRIBUTOR,
      'X-Owdb-Token': token,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(contribution),
  });
  let body = {};
  try { body = await res.json(); } catch (e) { /* worker returned non-JSON */ }
  return { ok: res.ok, status: res.status, body };
}

// ------------------------------------------------------------- handler ----

function send(res, code, type, body) {
  res.writeHead(code, { 'Content-Type': type, 'Cache-Control': 'no-store' });
  res.end(body);
}
const sendJson = (res, code, obj) => send(res, code, 'application/json', JSON.stringify(obj));

// This server binds to loopback, but "on localhost" is not the same as "only
// reachable from a program the operator ran". A page open in the operator's
// browser can POST to http://localhost:<port>/upload, and a domain that
// resolves to 127.0.0.1 (DNS rebinding) can read /review.json - neither is
// something a review tool should allow. So:
//   - the Host header must name loopback (kills DNS rebinding: the attacker's
//     domain is what the browser sends), and
//   - a mutating request may not carry a cross-origin Origin (kills the CSRF
//     form-POST that has no preflight to stop it).
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

function readBody(req) {
  return new Promise((resolve, reject) => {
    let s = '';
    req.on('data', (c) => { s += c; if (s.length > 5e7) req.destroy(); });
    req.on('end', () => resolve(s));
    req.on('error', reject);
  });
}

// `ctx` is everything the handler touches: { outDir, session, feedPath,
// refsPath, iconsPath, stateDir, pagePath, fetch }. Tests pass their own.
async function handle(req, res, ctx) {
  const u = new URL(req.url, 'http://localhost');
  const p = u.pathname;

  try {
    if (crossOrigin(req)) return send(res, 403, 'text/plain', 'cross-origin request refused');

    if (req.method === 'GET' && (p === '/' || p === '/index.html')) {
      return send(res, 200, 'text/html', fs.readFileSync(ctx.pagePath));
    }

    if (req.method === 'GET' && p === '/review.json') {
      const r = readJson(currentReviewPath(ctx), null);
      return r ? sendJson(res, 200, r) : sendJson(res, 404, { error: 'no review artifact' });
    }

    if (req.method === 'GET' && p === '/failures') {
      const attempts = readJson(path.join(ctx.stateDir, 'attempts.json'), {});
      const feed = readJson(ctx.feedPath, {});
      return sendJson(res, 200, { failures: failureList(attempts, feed.codes) });
    }

    if (req.method === 'GET' && p === '/hero-list') {
      const feed = readJson(ctx.feedPath, {});
      const list = heroList(
        readJson(ctx.refsPath, { refs: [] }),
        feed.hero_roles || {},
        readJson(ctx.iconsPath, {}),
        collectCustomHeroes(readJson(currentReviewPath(ctx), { maps: [] })));
      return sendJson(res, 200, { heroes: list });
    }

    if (req.method === 'GET' && p.startsWith('/crops/')) {
      const rp = currentReviewPath(ctx);
      if (!rp) return send(res, 404, 'text/plain', 'no such crop');
      const rel = decodeURIComponent(p.slice('/crops/'.length));
      const cropsRoot = path.join(path.dirname(rp), path.basename(rp).replace(/\.review\.json$/, ''), 'crops');
      const abs = path.resolve(cropsRoot, rel);
      if ((abs !== cropsRoot && !abs.startsWith(cropsRoot + path.sep)) || !fs.existsSync(abs)) {
        return send(res, 404, 'text/plain', 'no such crop');
      }
      return send(res, 200, 'image/png', fs.readFileSync(abs));
    }

    if (req.method === 'POST' && p === '/save') {
      const rp = currentReviewPath(ctx);
      if (!rp) return sendJson(res, 404, { error: 'no review artifact' });
      const body = JSON.parse(await readBody(req));
      fs.writeFileSync(rp, JSON.stringify(body, null, 2) + '\n');
      return sendJson(res, 200, { ok: true });
    }

    if (req.method === 'POST' && p === '/finalize') {
      const rp = currentReviewPath(ctx);
      const review = readJson(rp, null);
      if (!review) return sendJson(res, 404, { error: 'no review artifact' });
      const contribution = finalize(review, readJson(ctx.feedPath, {}));
      const outPath = rp.replace(/\.review\.json$/, '.json');
      fs.writeFileSync(outPath, JSON.stringify(contribution, null, 2) + '\n');
      const obs = contribution.maps.reduce((n, m) => n + m.observations.length, 0);
      return sendJson(res, 200, { ok: true, maps: contribution.maps.length, observations: obs, wrote: outPath });
    }

    if (req.method === 'POST' && p === '/upload') {
      const rp = currentReviewPath(ctx);
      const review = readJson(rp, null);
      if (!review) return sendJson(res, 404, { error: 'no review artifact' });
      const unreviewed = (review.maps || []).filter((m) => m.status === 'unreviewed');
      if (unreviewed.length) {
        return sendJson(res, 409, { error: `${unreviewed.length} map(s) still unreviewed` });
      }
      const contribution = finalize(review, readJson(ctx.feedPath, {}));
      const result = await uploadWith(ctx.fetch, contribution, uploadToken(ctx.stateDir));
      if (result.ok) {
        result.prune = await runPrune(ctx, path.basename(rp, '.review.json'));
      }
      return sendJson(res, result.ok ? 200 : 502, result);
    }

    if (req.method === 'POST' && p === '/go') {
      const body = JSON.parse((await readBody(req)) || '{}');
      if (!body.confirmed) return sendJson(res, 400, { error: 'confirm Overwatch is on the Replay History tab first' });
      if (ctx.run && !ctx.run.exitInfo) return sendJson(res, 409, { error: 'a run is already active' });
      fs.mkdirSync(ctx.stateDir, { recursive: true });
      startRun(ctx, body);
      return sendJson(res, 200, { ok: true });
    }

    if (req.method === 'POST' && p === '/stop') {
      if (!ctx.run || ctx.run.exitInfo) return sendJson(res, 404, { error: 'no run active' });
      fs.mkdirSync(ctx.stateDir, { recursive: true });
      fs.writeFileSync(path.join(ctx.stateDir, 'loop_stop.flag'), '');
      return sendJson(res, 200, { ok: true, note: 'stopping after the current map' });
    }

    if (req.method === 'GET' && p === '/run-log') {
      if (!ctx.run) return sendJson(res, 404, { error: 'no run started yet' });
      res.writeHead(200, { 'content-type': 'text/event-stream', 'cache-control': 'no-cache', connection: 'keep-alive' });
      ctx.run.log.forEach((line) => res.write('data: ' + JSON.stringify(line) + '\n\n'));
      if (ctx.run.exitInfo) {
        res.write('event: done\ndata: ' + JSON.stringify(ctx.run.exitInfo) + '\n\n');
        return res.end();
      }
      ctx.run.subscribers.push(res);
      req.on('close', () => { ctx.run.subscribers = ctx.run.subscribers.filter((r) => r !== res); });
      return;
    }

    if (req.method === 'POST' && p === '/refresh-feed') {
      if (ctx.refresh && ctx.refresh.state === 'pending') {
        return sendJson(res, 409, { error: 'a refresh is already pending' });
      }
      const r = await startRefresh(ctx);
      return sendJson(res, 200, r);
    }

    if (req.method === 'GET' && p === '/status') {
      const feed = readJson(ctx.feedPath, {});
      const attempts = readJson(path.join(ctx.stateDir, 'attempts.json'), {});
      return sendJson(res, 200, {
        feed: RunJS.feedFreshness(feed, Date.now()),
        attempts: attemptsTally(attempts),
        running: !!(ctx.run && !ctx.run.exitInfo),
        exitInfo: (ctx.run && ctx.run.exitInfo) || null,
        hasReview: !!currentReviewPath(ctx),
        refresh: ctx.refresh || { state: 'idle' },
      });
    }

    return send(res, 404, 'text/plain', 'not found');
  } catch (e) {
    return sendJson(res, 500, { error: String(e && e.message || e) });
  }
}

function collectCustomHeroes(review) {
  const out = {};
  for (const m of (review && review.maps) || []) {
    for (const r of m.rounds || []) {
      for (const side of ['a', 'b']) {
        for (const s of r[side] || []) {
          if (s && s.guid && String(s.guid).indexOf('custom:') === 0) {
            out[s.guid] = { name: s.name || s.guid.slice(7), role: null };
          }
        }
      }
    }
  }
  return out;
}

// ---------------------------------------------------------------- main ----

function parseArgs(argv) {
  const flag = (n) => { const i = argv.indexOf(n); return i === -1 ? null : argv[i + 1]; };
  const positional = argv.filter((a, i) => !a.startsWith('--') && (i === 0 || !argv[i - 1].startsWith('--')));
  return {
    session: positional[0] || null,
    open: argv.includes('--open'),
    port: Number(flag('--port')) || 0,
  };
}

function resolveReviewPathIn(outDir, session) {
  if (!session) return newestReview(outDir);
  if (fs.existsSync(session)) return session;
  const named = path.join(outDir, session.endsWith('.review.json') ? session : session + '.review.json');
  return fs.existsSync(named) ? named : null;
}

function currentReviewPath(ctx) {
  return resolveReviewPathIn(ctx.outDir, ctx.session);
}

function main() {
  const args = parseArgs(process.argv.slice(2));
  const ctx = {
    outDir: OUT, session: args.session,
    feedPath: FEED, refsPath: REFS, iconsPath: ICONS,
    stateDir: STATE, pagePath: PAGE,
    fetch: (...a) => fetch(...a),
    setTimeout,
    exec: (cmd, args, opts) => new Promise((resolve, reject) => {
      require('child_process').execFile(cmd, args, opts, (err) => err ? reject(err) : resolve());
    }),
    repoDir: REPO,
    spawn: require('child_process').spawn,
  };
  const server = http.createServer((req, res) => handle(req, res, ctx));
  server.listen(args.port, '127.0.0.1', () => {
    const port = server.address().port;
    const link = `http://localhost:${port}/`;
    const rp = currentReviewPath(ctx);
    console.log(rp ? `review: ${path.basename(rp)}` : 'no review artifact yet - waiting for a run');
    console.log(`open ${link}`);
    if (args.open) {
      const cmd = process.platform === 'win32' ? 'start ""'
        : process.platform === 'darwin' ? 'open' : 'xdg-open';
      require('child_process').exec(`${cmd} ${link}`);
    }
  });
}

module.exports = {
  newestReview, heroList, applyCorrections, finalize, uploadToken, uploadWith,
  collectCustomHeroes, parseArgs, currentReviewPath, resolveReviewPathIn, handle,
  categorizeFailure, failureList, attemptsTally, buildRunArgs,
};

if (require.main === module) main();

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

const RBOT = path.join(__dirname, '..');
const OUT = path.join(RBOT, 'out');
const STATE = path.join(RBOT, 'state');
const REPO = path.join(RBOT, '..', '..');
const FEED = path.join(REPO, 'docs', 'capture', 'data.json');
const REFS = path.join(REPO, 'docs', 'capture', 'refs.json');
const ICONS = path.join(REPO, 'docs', 'capture', 'hero_icons.json');
const PAGE = path.join(__dirname, 'page.html');
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
      slot.flags = (slot.flags || []).filter((f) => f === 'attribution-abstained');
    } else if (c.kind === 'player') {
      slot.player_id = c.now_id || null;
      slot.player_conf = c.now_id ? 'operator' : null;
      slot.flags = (slot.flags || []).filter((f) => f !== 'attribution-abstained');
    }
  }
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

// `ctx` is everything the handler touches: { reviewPath, feedPath, refsPath,
// iconsPath, stateDir, pagePath, fetch }. Tests pass their own.
async function handle(req, res, ctx) {
  const u = new URL(req.url, 'http://localhost');
  const p = u.pathname;

  try {
    if (crossOrigin(req)) return send(res, 403, 'text/plain', 'cross-origin request refused');

    if (req.method === 'GET' && (p === '/' || p === '/index.html')) {
      return send(res, 200, 'text/html', fs.readFileSync(ctx.pagePath));
    }

    if (req.method === 'GET' && p === '/review.json') {
      const r = readJson(ctx.reviewPath, null);
      return r ? sendJson(res, 200, r) : sendJson(res, 404, { error: 'no review artifact' });
    }

    if (req.method === 'GET' && p === '/hero-list') {
      const feed = readJson(ctx.feedPath, {});
      const list = heroList(
        readJson(ctx.refsPath, { refs: [] }),
        feed.hero_roles || {},
        readJson(ctx.iconsPath, {}),
        collectCustomHeroes(readJson(ctx.reviewPath, { maps: [] })));
      return sendJson(res, 200, { heroes: list });
    }

    if (req.method === 'GET' && p.startsWith('/crops/')) {
      const rel = decodeURIComponent(p.slice('/crops/'.length));
      const cropsRoot = path.join(path.dirname(ctx.reviewPath),
        path.basename(ctx.reviewPath).replace(/\.review\.json$/, ''), 'crops');
      const abs = path.resolve(cropsRoot, rel);
      if ((abs !== cropsRoot && !abs.startsWith(cropsRoot + path.sep)) || !fs.existsSync(abs)) {
        return send(res, 404, 'text/plain', 'no such crop');
      }
      return send(res, 200, 'image/png', fs.readFileSync(abs));
    }

    if (req.method === 'POST' && p === '/save') {
      const body = JSON.parse(await readBody(req));
      fs.writeFileSync(ctx.reviewPath, JSON.stringify(body, null, 2) + '\n');
      return sendJson(res, 200, { ok: true });
    }

    if (req.method === 'POST' && p === '/finalize') {
      const review = readJson(ctx.reviewPath, null);
      if (!review) return sendJson(res, 404, { error: 'no review artifact' });
      const contribution = finalize(review, readJson(ctx.feedPath, {}));
      const outPath = ctx.reviewPath.replace(/\.review\.json$/, '.json');
      fs.writeFileSync(outPath, JSON.stringify(contribution, null, 2) + '\n');
      const obs = contribution.maps.reduce((n, m) => n + m.observations.length, 0);
      return sendJson(res, 200, { ok: true, maps: contribution.maps.length, observations: obs, wrote: outPath });
    }

    if (req.method === 'POST' && p === '/upload') {
      const review = readJson(ctx.reviewPath, null);
      if (!review) return sendJson(res, 404, { error: 'no review artifact' });
      const unreviewed = (review.maps || []).filter((m) => m.status === 'unreviewed');
      if (unreviewed.length) {
        return sendJson(res, 409, { error: `${unreviewed.length} map(s) still unreviewed` });
      }
      const contribution = finalize(review, readJson(ctx.feedPath, {}));
      const result = await uploadWith(ctx.fetch, contribution, uploadToken(ctx.stateDir));
      return sendJson(res, result.ok ? 200 : 502, result);
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

function resolveReviewPath(session) {
  if (!session) return newestReview(OUT);
  if (fs.existsSync(session)) return session;
  const named = path.join(OUT, session.endsWith('.review.json') ? session : session + '.review.json');
  return fs.existsSync(named) ? named : null;
}

function main() {
  const args = parseArgs(process.argv.slice(2));
  const reviewPath = resolveReviewPath(args.session);
  if (!reviewPath) {
    console.error('no review artifact found in ' + OUT + ' - run a capture first, or pass a path');
    process.exit(1);
  }
  const ctx = {
    reviewPath,
    feedPath: FEED, refsPath: REFS, iconsPath: ICONS,
    stateDir: STATE, pagePath: PAGE,
    fetch: (...a) => fetch(...a),
  };
  const server = http.createServer((req, res) => handle(req, res, ctx));
  server.listen(args.port, '127.0.0.1', () => {
    const port = server.address().port;
    const link = `http://localhost:${port}/`;
    console.log(`review: ${path.basename(reviewPath)}`);
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
  collectCustomHeroes, parseArgs, resolveReviewPath, handle,
};

if (require.main === module) main();

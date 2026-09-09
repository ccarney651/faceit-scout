// tools/replay_bot/scrape_codes.js
// Fresh replay codes from owreplays.tv, filtered to games shaped like a FACEIT
// one, and never one this account has already spent.
//
//   node tools/replay_bot/scrape_codes.js                 20 codes
//   node tools/replay_bot/scrape_codes.js --want 40       more
//   node tools/replay_bot/scrape_codes.js --json out.json for run.js --codes
//
// WHY THE MODE MATTERS. A FACEIT league game is 5v5 COMPETITIVE ROLE QUEUE, and
// nothing else on that site has its shape. Quick play is shorter and sparser -
// sparse single-round maps are what broke the first round detector. 6v6 is
// worse than useless: it draws SIX portraits a side, and the crop geometry is
// frozen at five, so every cell would read the wrong hero and nothing in the
// output would say so. Four of five codes picked by hand last night turned out
// to be quick play and three of those were 6v6.
//
// The site's own numbering does the work: gamemode 2 is Competitive, gametype 1
// is role queue, and the 6v6 gametypes (55197, 65788) are not in Competitive's
// list at all. So `?modes=2&gametypes=1` cannot return one.
//
// HOW IT READS THE SITE. There is no listing API. The page is server-rendered
// with the whole result set in an `__INITIAL_STATE__` script tag - codes,
// durations, patch level, and the site's own verification status - and it
// honours `modes`, `gametypes` and `page` as query parameters. Default order is
// newest first; passing `sort` at all returns nothing.
//
// THE PATCH LEVEL IS THE OTHER HARD FILTER, AND IT IS NOT OPTIONAL. Overwatch
// wipes replay codes at a patch, so a code from before the last one is dead and
// importing it achieves nothing. The site records the patch each replay was
// uploaded on, and that lines up with the wipe ledger exactly: uploads on
// 2.24.0.3 stop at 2026-09-08 12:42Z and 2.24.1.0 starts at 19:15Z, against
// owdb/db.py's `_SEED_WIPES` entry for "patch on the 8th ~19:00 UK". Same
// event, seen from two sides - which makes the site's PatchLevel an independent
// witness to a wipe date this project otherwise records only by observation.
//
// So the default is the NEWEST patch in the results and everything older is
// dropped. It matters: of ~100 competitive role-queue replays on the site, 83
// are on the wiped patch and would each cost a failed import. `--patch`
// overrides it, for a patch that turns out not to have wiped anything.
//
// A CODE IMPORTS ONCE, EVER. Everything this prints is checked against the
// attempt ledger and against state/seen_codes.json, which is where codes spent
// outside run.js are written down. Both are per-machine and gitignored, for the
// same reason: they record what THIS client has done.

const fs = require('fs');
const path = require('path');

const BASE = 'https://owreplays.tv/';
const STATE = path.join(__dirname, 'state');
const LEDGER = path.join(STATE, 'attempts.json');
const SEEN = path.join(STATE, 'seen_codes.json');

const MODE_COMPETITIVE = 2;
const GAMETYPE_ROLE_QUEUE = 1;

function readJson(p, fallback) {
  try { return JSON.parse(fs.readFileSync(p, 'utf8')); } catch (e) { return fallback; }
}

// Every code this client is known to have opened, from both places that know.
function spentCodes() {
  const out = new Set();
  const ledger = readJson(LEDGER, {});
  Object.values(ledger).forEach((a) => { if (a && a.code) out.add(a.code.toUpperCase()); });
  (readJson(SEEN, []) || []).forEach((c) => out.add(String(c).toUpperCase()));
  return out;
}

async function fetchPage(page) {
  const url = BASE + '?modes=' + MODE_COMPETITIVE +
    '&gametypes=' + GAMETYPE_ROLE_QUEUE + (page > 1 ? '&page=' + page : '');
  const res = await fetch(url, { headers: { 'user-agent': 'Mozilla/5.0' } });
  if (!res.ok) throw new Error(url + ' -> HTTP ' + res.status);
  const html = await res.text();
  const m = html.match(/id="__INITIAL_STATE__"[^>]*>([\s\S]*?)<\/script>/);
  if (!m) throw new Error('no __INITIAL_STATE__ on page ' + page + ' - the site changed');
  const state = JSON.parse(m[1].trim());
  return {
    replays: state['replay-table-store'].replays || [],
    pages: state['replay-table-store'].pages,
    maps: state['overwatch-store'].maps || [],
  };
}

// Seconds from the site's "HH:MM:SS" or "MM:SS".
function seconds(hhmmss) {
  if (!hhmmss) return null;
  const p = String(hhmmss).split(':').map(Number);
  if (p.some(isNaN)) return null;
  return p.reduce((acc, n) => acc * 60 + n, 0);
}

const flag = (f, d) => {
  const i = process.argv.indexOf(f);
  return i === -1 ? d : process.argv[i + 1];
};

async function main() {
  const want = Number(flag('--want', 20));
  const maxPages = Number(flag('--pages', 40));
  const minS = Number(flag('--min-seconds', 240));
  const jsonOut = flag('--json', null);
  const wantPatch = flag('--patch', null);

  const spent = spentCodes();
  console.log(`${spent.size} codes already spent on this client, skipping those`);

  // Gathered first and filtered by patch after, because the newest patch is
  // only known once some results are in.
  const found = [];
  let mapsById = null;
  let skippedSpent = 0, skippedShort = 0, skippedUnverified = 0;

  for (let page = 1; page <= maxPages && found.length < want * 3; page++) {
    const { replays, maps } = await fetchPage(page);
    if (!mapsById) {
      mapsById = new Map(maps.map((m) => [m.ID, m]));
    }
    if (!replays.length) break;

    for (const r of replays) {
      // The site's numbering is the guard: anything that is not competitive
      // role queue should never have been returned, so if one is, say so
      // rather than quietly keeping it.
      if (r.Mode !== MODE_COMPETITIVE || r.GameType !== GAMETYPE_ROLE_QUEUE) {
        console.log(`  ! ${r.Code} came back as mode ${r.Mode}/gametype ${r.GameType} - skipped`);
        continue;
      }
      const code = String(r.Code).toUpperCase();
      if (spent.has(code)) { skippedSpent++; continue; }
      // The site checks codes itself and says so. A code it cannot verify is
      // one the client will refuse, and refusing costs the same as importing.
      if (r.CodeVerificationStatus !== 'valid') { skippedUnverified++; continue; }
      const secs = seconds(r.Duration);
      if (secs !== null && secs < minS) { skippedShort++; continue; }

      const map = mapsById.get(r.Map);
      found.push({
        code,
        map: map ? map.map : '(map ' + r.Map + ')',
        category: map && map.mode ? map.mode : 'unknown',
        duration: r.Duration,
        seconds: secs,
        patch: r.PatchLevel,
        uploaded: r.Uploaded ? new Date(r.Uploaded * 1000).toISOString() : null,
      });
    }
  }

  // Newest patch wins: the list is newest-first, so it is the first one seen.
  const patch = wantPatch || (found.length ? found[0].patch : null);
  const dead = found.filter((f) => f.patch !== patch);
  const picked = found.filter((f) => f.patch === patch).slice(0, want);

  console.log(`skipped: ${skippedSpent} already spent, ${skippedUnverified} unverified, ` +
    `${skippedShort} shorter than ${minS}s, ${dead.length} on a patch older than ${patch}\n`);

  const w = (s, n) => String(s).padEnd(n);
  console.log(w('CODE', 8) + w('MAP', 24) + w('TYPE', 12) + w('LENGTH', 9) + 'PATCH');
  picked.forEach((p) => {
    console.log(w(p.code, 8) + w(p.map, 24) + w(p.category, 12) + w(p.duration, 9) + p.patch);
  });

  console.log(`\n${picked.length} codes, all on patch ${patch}` +
    (picked.length < want ? ` - only ${picked.length} of the ${want} asked for are on it` : ''));
  console.log('run.js --codes ' + picked.map((p) => p.code).join(','));

  if (jsonOut) {
    fs.writeFileSync(jsonOut, JSON.stringify(picked, null, 1));
    console.log('written to ' + jsonOut);
  }
}

main().catch((e) => { console.error('FAILED: ' + e.message); process.exitCode = 1; });

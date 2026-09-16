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
// attempt ledger, against state/seen_codes.json, and against the demo_codes in
// out/*.json - the contribution files, which are the record of what was
// actually captured. The ledger alone was not enough: it only knows about runs
// that went through run.js, and this tool offered two codes that were already
// sitting in last night's output.
//
// THE ANSWER KEY IS REPORTED, NOT REQUIRED, AND THAT IS A DELIBERATE CLIMBDOWN.
// The site serves a per-code event stream saying which hero each player was on
// and when, which is what score.js grades the bot against. Requiring one looked
// obviously right - why spend a code you cannot grade? - and it rejected every
// candidate, because the stream has three states and fresh codes are always in
// the wrong one:
//
//   ok              parsed; 8, 9 or 10 of the players, and only sometimes 10
//   in_progress     queued, and it is a slow queue - two codes uploaded last
//                   night were still in_progress eighteen hours later, and the
//                   API has queue positions and a subscription tier next to it
//   not_available   never
//
// Every code uploaded today is in_progress, so a scrape that insists on a key
// returns nothing at all. What is left is to drop `not_available`, print the
// state, and sort the keyed ones first. A code captured tonight may become
// gradeable in a day - the capture does not depend on the key, and the frames
// are kept, so score.js can be run again later against the same output.
//
// `--gradeable` restores the strict version for when a key already exists.

const fs = require('fs');
const path = require('path');

const BASE = 'https://owreplays.tv/';
const STATE = path.join(__dirname, 'state');
const LEDGER = path.join(STATE, 'attempts.json');
const SEEN = path.join(STATE, 'seen_codes.json');

const MODE_COMPETITIVE = 2;
const GAMETYPE_ROLE_QUEUE = 1;
const API = 'https://owreplays.tv/api/v2/';

function readJson(p, fallback) {
  try { return JSON.parse(fs.readFileSync(p, 'utf8')); } catch (e) { return fallback; }
}

// Every code this client is known to have opened, from all three places that
// know: the attempt ledger, the hand-kept list, and the contribution files -
// which are the only record of a map that was captured outside run.js.
function spentCodes() {
  const out = new Set();
  const ledger = readJson(LEDGER, {});
  Object.values(ledger).forEach((a) => { if (a && a.code) out.add(a.code.toUpperCase()); });
  (readJson(SEEN, []) || []).forEach((c) => out.add(String(c).toUpperCase()));

  const outDir = path.join(__dirname, 'out');
  let files = [];
  try { files = fs.readdirSync(outDir).filter((f) => f.endsWith('.json')); } catch (e) { /* none yet */ }
  for (const f of files) {
    const doc = readJson(path.join(outDir, f), null);
    if (!doc || !Array.isArray(doc.maps)) continue;
    doc.maps.forEach((m) => { if (m.demo_code) out.add(String(m.demo_code).toUpperCase()); });
  }
  return out;
}

// The state of this code's answer key, and how many of the ten players it
// names. An observation graded against a partial key can never be exactly right
// however well the bot read it, so the count matters as much as the state.
async function answerKey(code) {
  try {
    const res = await fetch(API + 'replay/' + code + '/events',
      { headers: { 'user-agent': 'Mozilla/5.0' } });
    if (!res.ok) return { status: 'http ' + res.status, players: 0 };
    const body = await res.json();
    const events = body.events || [];
    const slots = new Set();
    events.forEach((e) => {
      if (e.type === 'PLAYER_JOINED' && e.hero !== null && e.hero !== undefined) {
        slots.add(String(e.slot));
      }
    });
    return { status: body.status || 'unknown', players: slots.size };
  } catch (e) {
    return { status: 'unreachable', players: 0 };
  }
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
  const strictKey = process.argv.includes('--gradeable');

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
  const live = found.filter((f) => f.patch === patch);

  // Then the answer key: one request per candidate, to report its state and
  // drop the ones that will never have one.
  const keyed = [];
  let noKey = 0;
  for (const c of live) {
    const key = await answerKey(c.code);
    c.key = key;
    if (key.status === 'not_available') { noKey++; continue; }
    if (strictKey && key.players < 10) { noKey++; continue; }
    keyed.push(c);
  }

  // Gradeable first: a code that can be scored the moment it is captured is
  // worth more than one that might be scoreable later.
  keyed.sort((a, b) => (b.key.players - a.key.players));
  const picked = keyed.slice(0, want);

  console.log(`skipped: ${skippedSpent} already spent, ${skippedUnverified} unverified, ` +
    `${skippedShort} shorter than ${minS}s, ${dead.length} on a patch older than ${patch}` +
    `, ${noKey} whose answer key will never come` + `\n`);

  const w = (s, n) => String(s).padEnd(n);
  console.log(w('CODE', 8) + w('MAP', 24) + w('TYPE', 12) + w('LENGTH', 9) + 'ANSWER KEY');
  picked.forEach((p) => {
    const key = p.key.players ? p.key.players + '/10 players' : p.key.status;
    console.log(w(p.code, 8) + w(p.map, 24) + w(p.category, 12) + w(p.duration, 9) + key);
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

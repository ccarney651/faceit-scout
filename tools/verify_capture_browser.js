// Browser verification for the capture pages.
//
// The pytest suite checks syntax and shape; it cannot check behaviour through a
// real DOM, a real IndexedDB, or a real CSP. That gap has hidden live bugs more
// than once - scoreboard.js never loaded in production for months because the
// CSP blocked it, and the two capture pages could not both create their object
// stores in the same browser. This script closes as much of that gap as can be
// closed without a human at the keyboard.
//
// What it CANNOT check, and what still needs a person with Overwatch running:
// screen sharing, calibration against a live frame, hero-portrait recognition,
// and the floating overlay's behaviour over the game.
//
//   npm install playwright-core        # not a repo dependency; install ad hoc
//   .venv/Scripts/python.exe -m http.server 8000 --directory docs
//   node tools/verify_capture_browser.js
//
// Exits non-zero if any check fails. Serve over http - a file:// origin blocks
// the engine modules and uses a different IndexedDB, so it verifies nothing.

const path = require('path');
let chromium;
try {
  ({ chromium } = require('playwright-core'));
} catch (e) {
  console.error('playwright-core is not installed. Run: npm install playwright-core');
  process.exit(2);
}

const BASE = process.env.OWDB_BASE || 'http://127.0.0.1:8000';
const EXE = process.env.OWDB_CHROME || path.join(
  process.env.USERPROFILE || process.env.HOME,
  'AppData/Local/ms-playwright/chromium-1234/chrome-win64/chrome.exe');

const results = [];
const check = (name, pass, detail) =>
  results.push({ name, pass: !!pass, detail: detail == null ? '' : String(detail) });

const STORES = ['heroes', 'maps', 'refs', 'scrim_maps', 'scrims'];

async function main() {
  const browser = await chromium.launch({ executablePath: EXE });

  // --- 1. Pages load, modules resolve, no errors ----------------------------
  {
    const ctx = await browser.newContext();
    const errs = {};
    const open = async (url, key) => {
      const p = await ctx.newPage();
      errs[key] = [];
      p.on('console', m => m.type() === 'error' && errs[key].push(m.text()));
      p.on('pageerror', e => errs[key].push('PAGEERROR: ' + e.message));
      await p.goto(BASE + url, { waitUntil: 'load' });
      await p.waitForTimeout(1500);
      return p;
    };

    const league = await open('/capture/index.html', 'league');
    // Scoreboard is deliberately absent here: only scrim.html loads scoreboard.js.
    const lm = await league.evaluate(() => ['OWDBUtil', 'OWDBIdb', 'OWDBNames', 'OWDBFrames',
      'OWDBCalibration', 'OWDBRefs', 'OWDBOverlay', 'OWDBTour'].filter(n => typeof window[n] !== 'object'));
    check('league: every engine module loads', lm.length === 0, 'missing: ' + lm.join(','));
    check('league: no console errors', errs.league.length === 0, errs.league.join(' | '));

    const scrim = await open('/capture/scrim.html', 'scrim');
    const sm = await scrim.evaluate(() => ['OWDBUtil', 'OWDBIdb', 'OWDBNames', 'OWDBSession', 'Scoreboard']
      .filter(n => typeof window[n] !== 'object'));
    check('scrim: every engine module loads (incl. Scoreboard)', sm.length === 0, 'missing: ' + sm.join(','));
    check('scrim: no console errors', errs.scrim.length === 0, errs.scrim.join(' | '));
    check('scrim: pause overlay is gone',
      await scrim.evaluate(() => !document.getElementById('scrimpaused')));

    // The league-code block must never treat an unusable feed as "all clear".
    const feed = await scrim.evaluate(() => ({
      state: typeof CODE_FEED !== 'undefined' ? CODE_FEED : 'MISSING',
      warn: (document.getElementById('ctxwarn') || {}).textContent || '',
    }));
    check('scrim: feed state is reported, not assumed',
      ['ready', 'empty', 'failed', 'loading'].includes(feed.state), feed.state);
    if (feed.state !== 'ready') {
      check('scrim: an unusable feed warns the user', /unavailable/i.test(feed.warn), feed.warn.slice(0, 90));
    }

    const cls = await scrim.evaluate(() => {
      const idx = OWDBSession.buildCodeIndex({
        code_wipe_date: '2026-08-11',
        codes: [{ code: '1XMN5W', match_id: 'm1', game_no: 1, division: 'EMEA Master' }],
      });
      return {
        hit: OWDBSession.classifyCode('1XMN5W', idx, '2026-08-13'),
        loose: OWDBSession.classifyCode(' 1xmn5w ', idx, '2026-08-13'),
        miss: OWDBSession.classifyCode('ZZZZZZ', idx, '2026-08-13'),
        dead: OWDBSession.classifyCode('ZZZZZZ', idx, '2026-08-01'),
      };
    });
    check('block: a league code is refused, with its division',
      cls.hit.league && cls.hit.division === 'EMEA Master', JSON.stringify(cls.hit));
    check('block: matching tolerates case and whitespace', cls.loose.league === true);
    check('block: a genuine scrim code passes', cls.miss.league === false);
    check('block: a pre-wipe code is marked dead', cls.dead.dead === true);

    const scaf = await scrim.evaluate(() => {
      const idx = OWDBSession.buildCodeIndex({
        code_wipe_date: '2026-08-11',
        codes: [{ code: 'E39856', match_id: 'm1', game_no: 1, division: 'EMEA Master' }],
      });
      return OWDBSession.buildScaffold(parseScrimSessionText(
        "Suravasa AKS2A9\nVICTORY | 11-2\nKing's Row 3FPHN6\nVICTORY | 3-1\nOasis E39856\nDEFEAT | 1-2"),
        idx, '2026-08-13');
    });
    check('scaffold: reads every map off a replay-history dump', scaf.length === 3, 'got ' + scaf.length);
    check('scaffold: flags only the league row', scaf.filter(r => r.league).length === 1,
      JSON.stringify(scaf.map(r => [r.map_name, r.league])));
    check('scaffold: carries scores and results through',
      scaf[0].score.us === 11 && scaf[0].result === 'win', JSON.stringify(scaf[0]));

    const viewer = await open('/scrims.html', 'viewer');
    check('viewer: pause overlay is gone',
      await viewer.evaluate(() => !document.getElementById('scrimpaused')));
    check('viewer: no console errors', errs.viewer.length === 0, errs.viewer.join(' | '));
    await ctx.close();
  }

  // --- 2. Either capture page may be opened first ---------------------------
  // onupgradeneeded fires once per version, so a page that declares only its
  // own stores leaves the other page's stores uncreated. This is the check that
  // caught it; keep it.
  for (const [first, second] of [['/capture/index.html', '/capture/scrim.html'],
                                 ['/capture/scrim.html', '/capture/index.html']]) {
    const ctx = await browser.newContext();
    const errs = [];
    for (const url of [first, second]) {
      const p = await ctx.newPage();
      p.on('pageerror', e => errs.push(url.split('/').pop() + ': ' + e.message));
      await p.goto(BASE + url, { waitUntil: 'load' });
      await p.waitForTimeout(1200);
    }
    const p = await ctx.newPage();
    await p.goto(BASE + '/capture/scrim.html', { waitUntil: 'load' });
    const got = await p.evaluate(async (want) => {
      const db = await new Promise(r => { const q = indexedDB.open('owscout-capture'); q.onsuccess = () => r(q.result); });
      return { v: db.version, stores: want.filter(n => db.objectStoreNames.contains(n)) };
    }, STORES);
    const label = first.includes('index') ? 'league first' : 'scrim first';
    check(`ordering: ${label} still creates every store`,
      got.stores.length === STORES.length, 'v' + got.v + ' ' + got.stores.join(','));
    check(`ordering: ${label} raises no page errors`, errs.length === 0, errs.join(' | '));
    await ctx.close();
  }

  // --- 3. An existing v4 database upgrades without losing anything ----------
  {
    const ctx = await browser.newContext();
    const seed = await ctx.newPage();
    // Seed from a page that does NOT open the database, or deleteDatabase blocks.
    await seed.goto(BASE + '/theme.css', { waitUntil: 'load' });
    await seed.evaluate(async () => {
      await new Promise(r => { const d = indexedDB.deleteDatabase('owscout-capture'); d.onsuccess = d.onerror = d.onblocked = r; });
      const db = await new Promise(res => {
        const q = indexedDB.open('owscout-capture', 4);
        q.onupgradeneeded = () => {
          const d = q.result;
          d.createObjectStore('maps', { keyPath: 'id' });
          d.createObjectStore('refs', { keyPath: 'id' });
          d.createObjectStore('heroes', { keyPath: 'g' });
        };
        q.onsuccess = () => res(q.result);
      });
      await new Promise(r => {
        const tx = db.transaction(['refs', 'heroes'], 'readwrite');
        tx.objectStore('refs').put({ id: 'ref-hand-taught', hero: 'dva', px: [1, 2, 3] });
        tx.objectStore('heroes').put({ g: 'custom:d_mon', name: 'D.Mon', role: 'TANK' });
        tx.oncomplete = r;
      });
      db.close();
    });

    const after = await ctx.newPage();
    const upErrs = [];
    after.on('pageerror', e => upErrs.push(e.message));
    await after.goto(BASE + '/capture/index.html', { waitUntil: 'load' });
    await after.waitForTimeout(1500);
    const state = await after.evaluate(async (want) => {
      const db = await new Promise(r => { const q = indexedDB.open('owscout-capture'); q.onsuccess = () => r(q.result); });
      const read = s => new Promise(r => { const q = db.transaction(s, 'readonly').objectStore(s).getAll(); q.onsuccess = () => r(q.result); });
      return {
        v: db.version, stores: want.filter(n => db.objectStoreNames.contains(n)),
        refs: await read('refs'), heroes: await read('heroes'),
      };
    }, STORES);

    check('upgrade: a v4 database gains the missing stores',
      state.stores.length === STORES.length, 'v' + state.v + ' ' + state.stores.join(','));
    check('upgrade: hand-taught hero refs survive',
      state.refs.length === 1 && state.refs[0].id === 'ref-hand-taught', JSON.stringify(state.refs));
    check('upgrade: custom heroes survive',
      state.heroes.length === 1 && state.heroes[0].g === 'custom:d_mon', JSON.stringify(state.heroes));
    check('upgrade: raises no page errors', upErrs.length === 0, upErrs.join(' | '));
    await ctx.close();
  }

  await browser.close();

  const failed = results.filter(r => !r.pass);
  for (const r of results) {
    console.log((r.pass ? 'PASS  ' : 'FAIL  ') + r.name + (r.detail && !r.pass ? '  -- ' + r.detail : ''));
  }
  console.log('\n' + (results.length - failed.length) + '/' + results.length + ' passed');
  if (failed.length) console.log('\nStill needs a human with Overwatch open: screen share, calibration,\nportrait recognition, and the floating overlay over the game.');
  process.exit(failed.length ? 1 : 0);
}

main().catch(e => { console.error('HARNESS ERROR:', e); process.exit(2); });

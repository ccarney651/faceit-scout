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
  const browser = await chromium.launch({
    executablePath: EXE,
    // A fake capture device lets getDisplayMedia succeed without a human
    // picking a window, which is what makes the share -> calibrate -> stop
    // plumbing testable here. The frame is synthetic, so recognition ACCURACY
    // still needs real game pixels - but the wiring around it does not.
    args: ['--use-fake-ui-for-media-stream', '--use-fake-device-for-media-stream',
           '--auto-select-desktop-capture-source=Entire screen', '--allow-http-screen-capture'],
  });

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

  // --- 1b. The guided tour, on both pages ----------------------------------
  // Each page keeps its own first-visit key, so finishing one tour must not
  // suppress the other's. tour.js was extracted from both pages; this exercises
  // the extracted mechanism rather than trusting that the move was clean.
  for (const [url, key, label] of [['/capture/index.html', 'owdb_tour_done', 'league'],
                                   ['/capture/scrim.html', 'owdb_tour_done_scrim', 'scrim']]) {
    const ctx = await browser.newContext();
    const p = await ctx.newPage();
    const errs = [];
    p.on('pageerror', e => errs.push(e.message));
    await p.goto(BASE + url, { waitUntil: 'load' });
    await p.evaluate(k => localStorage.removeItem(k), key);   // force first visit
    await p.reload({ waitUntil: 'load' });
    await p.waitForTimeout(2000);

    // NB: #tour is position:fixed, so offsetParent is always null - visibility
    // has to be read from computed display and a non-zero box, not offsetParent.
    const shown = await p.evaluate(() => {
      const t = document.getElementById('tour');
      if (!t) return false;
      return getComputedStyle(t).display !== 'none' && t.getBoundingClientRect().height > 0;
    });
    check(`tour: opens on a first visit (${label})`, shown);

    if (shown) {
      const before = await p.evaluate(() => document.getElementById('tour').textContent);
      await p.evaluate(() => document.getElementById('tourNext').click());
      await p.waitForTimeout(400);
      const after = await p.evaluate(() => document.getElementById('tour').textContent);
      check(`tour: Next advances a step (${label})`, before !== after);

      await p.evaluate(() => document.getElementById('tourSkip').click());
      await p.waitForTimeout(400);
      const closed = await p.evaluate(() => {
        const t = document.getElementById('tour');
        return !t || getComputedStyle(t).display === 'none';
      });
      check(`tour: Skip closes it (${label})`, closed);
      check(`tour: completion is remembered (${label})`,
        await p.evaluate(k => !!localStorage.getItem(k), key));
    }
    check(`tour: no page errors (${label})`, errs.length === 0, errs.join(' | '));
    await ctx.close();
  }

  // --- 1c. Share -> auto-calibrate -> stop, on both pages -------------------
  // Exercises the frames.js and calibration.js extractions against a real
  // MediaStream. The frame is synthetic so nothing is recognised - that is
  // expected and is itself the point: auto-calibrate must report low confidence
  // and must NOT commit boxes without confirmation.
  for (const [url, label] of [['/capture/index.html', 'league'], ['/capture/scrim.html', 'scrim']]) {
    const ctx = await browser.newContext();
    const p = await ctx.newPage();
    const errs = [];
    p.on('pageerror', e => errs.push(e.message));
    await p.goto(BASE + url, { waitUntil: 'load' });
    await p.waitForTimeout(1200);

    // A dropped <script> request leaves the page's top-level destructure
    // throwing ReferenceError, so `share` never gets wired and every check
    // below fails as though the product were broken. Retry once and say
    // plainly which it was, rather than reporting a server hiccup as a bug.
    let ready = await p.evaluate(() => typeof window.OWDBUtil === 'object' && typeof window.OWDBFrames === 'object');
    if (!ready) {
      await p.reload({ waitUntil: 'load' });
      await p.waitForTimeout(1500);
      ready = await p.evaluate(() => typeof window.OWDBUtil === 'object' && typeof window.OWDBFrames === 'object');
    }
    check(`share: engine modules present before sharing (${label})`, ready,
      ready ? '' : 'engine scripts did not load twice running - serve docs/ and re-run');
    if (!ready) { await ctx.close(); continue; }

    await p.evaluate(() => document.getElementById('share').click());
    await p.waitForTimeout(3000);
    const shared = await p.evaluate(() => {
      const v = document.querySelector('video');
      return { stream: !!(v && v.srcObject), w: v ? v.videoWidth : 0,
               autocal: !document.getElementById('autocal').disabled };
    });
    check(`share: a stream attaches (${label})`, shared.stream && shared.w > 0, JSON.stringify(shared));
    check(`share: auto-calibrate becomes available (${label})`, shared.autocal);

    if (shared.stream) {
      const before = await p.evaluate(() => JSON.stringify(boxes || {}));
      await p.evaluate(() => document.getElementById('autocal').click());
      await p.waitForTimeout(8000);
      const cal = await p.evaluate((b) => {
        const prev = document.getElementById('calpreview');
        return {
          preview: prev ? getComputedStyle(prev).display !== 'none' : false,
          msg: ((document.getElementById('calhint') || {}).textContent || '').slice(0, 120),
          unchanged: JSON.stringify(boxes || {}) === b,
        };
      }, before);
      check(`calibrate: a confidence preview is shown (${label})`, cal.preview, cal.msg);
      // The guarantee that matters: a bad read must not silently become the
      // user's calibration. Only "Use these boxes" may commit.
      check(`calibrate: boxes are NOT committed without confirmation (${label})`, cal.unchanged);
      check(`calibrate: low confidence is reported honestly (${label})`,
        /0\/10|not confident|likely off|misaligned/i.test(cal.msg), cal.msg);

      await p.evaluate(() => document.getElementById('stopcap').click());
      await p.waitForTimeout(1000);
      const stopped = await p.evaluate(() => {
        const v = document.querySelector('video');
        return { stream: !!(v && v.srcObject),
                 hint: ((document.getElementById('calhint') || {}).textContent || '') };
      });
      check(`stop: the stream is released (${label})`, stopped.stream === false);
      check(`stop: the page says so (${label})`, /stopped/i.test(stopped.hint), stopped.hint.slice(0, 60));
    }
    check(`share/calibrate/stop: no page errors (${label})`, errs.length === 0, errs.join(' | '));
    await ctx.close();
  }

  // --- 1d. The OCR pipeline, end to end ------------------------------------
  // Screenshot import depends entirely on tesseract, loaded from a CDN through
  // a strict CSP that has silently killed browser APIs twice in this project.
  // Renders a replay-history-shaped image and runs it through the page's own
  // ocrTextFromImage() - the real path, which sets the multi-line page-seg
  // mode. (Calling recognize() directly inherits PSM 7, single line, and
  // returns nothing; that is a harness mistake, not a bug.)
  {
    const ctx = await browser.newContext();
    const p = await ctx.newPage();
    const netFail = [];
    p.on('requestfailed', r => netFail.push(r.url().slice(0, 80)));
    await p.goto(BASE + '/capture/scrim.html', { waitUntil: 'load' });
    await p.waitForTimeout(1500);

    const ocr = await p.evaluate(async () => {
      const c = document.createElement('canvas');
      c.width = 900; c.height = 260;
      const g = c.getContext('2d');
      g.fillStyle = '#000'; g.fillRect(0, 0, c.width, c.height);
      g.fillStyle = '#fff'; g.font = '30px monospace';
      ['ILIOS ABCD12 VICTORY 3 - 1', 'DORADO EFGH34 DEFEAT 2 - 3',
       'BUSAN IJKL56 VICTORY 2 - 0'].forEach((t, i) => g.fillText(t, 20, 60 + i * 60));
      const blob = await new Promise(r => c.toBlob(r, 'image/png'));
      try {
        const text = await ocrTextFromImage(blob);
        return { ok: true, rows: parseScrimSessionText(text || ''), text: (text || '').slice(0, 200) };
      } catch (e) { return { ok: false, error: String((e && e.message) || e) }; }
    });

    check('ocr: the worker loads and reads an image', ocr.ok, ocr.error);
    check('ocr: no network request was blocked (CSP)', netFail.length === 0, netFail.join(' | '));
    if (ocr.ok) {
      check('ocr: every map line is recovered', ocr.rows.length === 3,
        ocr.rows.length + ' rows from: ' + JSON.stringify(ocr.text));
      const names = ocr.rows.map(r => r.map_name);
      check('ocr: map names resolve', ['Ilios', 'Dorado', 'Busan'].every(n => names.includes(n)), names.join(','));
      const codes = ocr.rows.map(r => r.code).filter(Boolean);
      check('ocr: replay codes are recovered', codes.length >= 2, codes.join(','));
    }
    await ctx.close();
  }

  // --- 1e. Opponent identification, end to end -----------------------------
  // Drives the phase-2 flow with injected names, since only READING names off
  // a live HUD needs the game - everything downstream of that is testable here.
  {
    const ctx = await browser.newContext();
    const p = await ctx.newPage();
    const errs = [];
    p.on('pageerror', e => errs.push(e.message));
    await p.goto(BASE + '/capture/scrim.html', { waitUntil: 'load' });
    await p.waitForTimeout(1500);

    const r = await p.evaluate(async () => {
      const FEED = { team_rosters: {
        t1: { name: 'Them FC', players: ['Fairuz','Dazedreox','Tomavul','Mellun','Nenonxx'].map(n => ({ game_name: n })) },
        t2: { name: 'Us FC',   players: ['Alpha','Bravo','Charlie','Delta','Echo'].map(n => ({ game_name: n })) },
      } };
      LEAGUE_DATA = FEED;
      FACEIT_ROSTERS = {};
      Object.keys(FEED.team_rosters).forEach(id => {
        FACEIT_ROSTERS[FEED.team_rosters[id].name.toLowerCase()] = FEED.team_rosters[id]; });
      setOurTeamName('Us FC');
      localStorage.removeItem('owdb_team_aliases');
      await ensureScrim();

      const us = ['Alpha','Bravo','Charlie','Delta','Echo'];
      const out = {};

      const n1 = { a: us, b: ['Fairuz','Dazedreox','Tomavul','Mellun','Nenonxx'] };
      const r1 = await resolveScrimIdentity(n1);
      out.ourSide = r1.ourSide;
      out.kind = r1.opponent && r1.opponent.kind;
      out.label = r1.opponent && r1.opponent.label;

      // Two smurfs: identified anyway, and the alts are learned.
      const n2 = { a: us, b: ['Fairuz','Dazedreox','Tomavul','alt_one','alt_two'] };
      const r2 = await resolveScrimIdentity(n2);
      out.smurfMatched = r2.opponent && r2.opponent.matched;
      await commitScrimIdentity(r2, n2);
      out.aliases = (loadAliases()[r2.opponent.team_id] || []).length;

      // With those learned, three smurfs clears the bar again.
      const n3 = { a: us, b: ['Fairuz','Dazedreox','alt_one','alt_two','alt_three'] };
      const r3 = await resolveScrimIdentity(n3);
      out.afterLearningMatched = r3.opponent && r3.opponent.matched;

      // A mix nobody knows is remembered, and recognised next time.
      const mix = ['rand1','rand2','rand3','rand4','rand5'];
      const r4 = await resolveScrimIdentity({ a: us, b: mix });
      out.mixFirst = r4.opponent && r4.opponent.kind;
      await commitScrimIdentity(r4, { a: us, b: mix });
      const mix2 = ['rand1','rand2','rand3','rand4','standIn'];
      const r5 = await resolveScrimIdentity({ a: us, b: mix2 });
      out.mixAgain = r5.opponent && r5.opponent.kind;
      await commitScrimIdentity(r5, { a: us, b: mix2 });
      out.groups = (await idbOpponents()).length;

      // The panel must say who it decided on, and offer the right correction.
      const panel = () => ({
        shown: getComputedStyle(document.getElementById('oppbox')).display !== 'none',
        label: document.getElementById('opplabel').textContent,
        detail: document.getElementById('oppdetail').textContent,
        wrong: getComputedStyle(document.getElementById('oppwrong')).display !== 'none',
        name: getComputedStyle(document.getElementById('oppname')).display !== 'none',
      });
      const rl = await resolveScrimIdentity(n1); rl._names = n1; LAST_IDENTITY = rl; renderOpponent(rl);
      out.panelLeague = panel();
      const rg = await resolveScrimIdentity({ a: us, b: mix2 }); rg._names = { a: us, b: mix2 };
      LAST_IDENTITY = rg; renderOpponent(rg);
      out.panelGroup = panel();

      // "Not them" on a league identification: undoes the aliases AND keeps the
      // opponent as a separate group rather than throwing the read away.
      const rw = await resolveScrimIdentity(n2); rw._names = n2; LAST_IDENTITY = rw; renderOpponent(rw);
      await commitScrimIdentity(rw, n2);
      const groupsBeforeWrong = (await idbOpponents()).length;
      await onOpponentWrong();
      out.afterWrongKind = LAST_IDENTITY.opponent && LAST_IDENTITY.opponent.kind;
      out.groupsGainedByWrong = (await idbOpponents()).length - groupsBeforeWrong;
      out.scrimTeamIdCleared = !(activeScrim && activeScrim.opponent_team_id);

      out.aliasesAfterCorrection = (loadAliases()[r2.opponent.team_id] || []).length;
      return out;
    });

    check('identity: our own side is recognised', r.ourSide === 'left', r.ourSide);
    check('identity: a league opponent is named', r.kind === 'league_team' && r.label === 'Them FC',
      r.kind + '/' + r.label);
    check('identity: two smurfs still identify the team', r.smurfMatched === 3, String(r.smurfMatched));
    check('identity: the smurf accounts are learned', r.aliases === 2, String(r.aliases));
    check('identity: learned aliases lift a three-smurf lineup back over the bar',
      r.afterLearningMatched >= 3, String(r.afterLearningMatched));
    check('identity: an unknown mix is remembered', r.mixFirst === 'new_group', r.mixFirst);
    check('identity: the same mix is recognised next time', r.mixAgain === 'local_group', r.mixAgain);
    check('identity: a stand-in does not create a duplicate group', r.groups === 1, String(r.groups));
    check('identity: "not them" discards what it taught', r.aliasesAfterCorrection === 0,
      String(r.aliasesAfterCorrection));

    check('panel: names the league team it identified',
      r.panelLeague.shown && /Them FC/.test(r.panelLeague.label), JSON.stringify(r.panelLeague));
    check('panel: offers "not them" for a team, not "name them"',
      r.panelLeague.wrong && !r.panelLeague.name, JSON.stringify(r.panelLeague));
    check('panel: offers "name them" for a remembered group',
      r.panelGroup.name && !r.panelGroup.wrong, JSON.stringify(r.panelGroup));
    check('panel: says a group is not a league team',
      /not a league team/i.test(r.panelGroup.detail), r.panelGroup.detail);

    // Rejecting an identification must not throw the read away - those five
    // players are still an opponent, just not that one.
    check('correction: "not them" keeps them as a separate group',
      r.afterWrongKind === 'local_group' && r.groupsGainedByWrong === 1,
      r.afterWrongKind + ' / +' + r.groupsGainedByWrong);
    check('correction: "not them" unpins the team from the scrim', r.scrimTeamIdCleared);

    check('identity: no page errors', errs.length === 0, errs.join(' | '));
    await ctx.close();
  }

  // --- 1f. The scrims viewer, against seeded data --------------------------
  // Practice coverage and opponent resolution are what make this page a
  // practice log rather than a capture archive, and neither is visible without
  // data - so seed some.
  {
    const ctx = await browser.newContext();
    const seed = await ctx.newPage();
    await seed.goto(BASE + '/theme.css', { waitUntil: 'load' });   // holds no DB handle
    await seed.evaluate(async () => {
      await new Promise(r => { const d = indexedDB.deleteDatabase('owscout-capture'); d.onsuccess = d.onerror = d.onblocked = r; });
      const db = await new Promise(res => {
        const q = indexedDB.open('owscout-capture', 5);
        q.onupgradeneeded = () => { const d = q.result;
          ['maps','refs','scrims','scrim_maps','opponents'].forEach(s => d.createObjectStore(s, { keyPath: 'id' }));
          d.createObjectStore('heroes', { keyPath: 'g' }); };
        q.onsuccess = () => res(q.result);
      });
      const put = (s, r) => new Promise(done => { const tx = db.transaction(s, 'readwrite'); tx.objectStore(s).put(r); tx.oncomplete = done; });
      const old = new Date(Date.now() - 24 * 86400000).toISOString().slice(0, 10);
      const today = new Date().toISOString().slice(0, 10);
      await put('opponents', { id: 'opp-1', kind: 'local_group', label: 'Korean team',
                               roster_names: ['k1','k2','k3','k4','k5'], times_played: 3 });
      // Identified by id only: the label must come from the registry.
      await put('scrims', { id: 's2', team_us: 'Us FC', opponent_id: 'opp-1', date: old, created_at: old + 'T19:00:00Z' });
      await put('scrims', { id: 's1', team_us: 'Us FC', opponent_team_id: 't-league',
                            opponent: 'IGNIS CRIMSON', date: today, created_at: today + 'T19:00:00Z' });
      const obs = [{ side: 'a', heroes: ['h1', 'h2'] }];
      await put('scrim_maps', { id: 's1:1', scrim_id: 's1', map_no: 1, map_name: 'Ilios', map_category: 'Control', observations: obs });
      await put('scrim_maps', { id: 's2:1', scrim_id: 's2', map_no: 1, map_name: 'Runasapi', map_category: 'Push', observations: obs });
      // Voided: a restarted map was not practice and must not claim coverage.
      await put('scrim_maps', { id: 's2:2', scrim_id: 's2', map_no: 2, map_name: 'Dorado', map_category: 'Escort', observations: obs, void: true });
      db.close();
    });

    const v = await ctx.newPage();
    const verrs = [];
    v.on('pageerror', e => verrs.push(e.message));
    await v.goto(BASE + '/scrims.html', { waitUntil: 'load' });
    await v.waitForTimeout(2500);
    const vr = await v.evaluate(() => {
      const cells = [...document.querySelectorAll('.covcell')].map(c => ({
        mode: c.querySelector('.covmode').textContent,
        when: c.querySelector('.covwhen').textContent,
        state: c.className.replace('covcell ', ''),
      }));
      const by = {}; cells.forEach(c => { by[c.mode] = c; });
      const txt = document.body.textContent;
      return { count: cells.length, by,
               note: (document.querySelector('.covnote') || {}).textContent || '',
               leagueLink: !!document.querySelector('.oppout'),
               registryLabel: /Korean team/.test(txt), leagueLabel: /IGNIS CRIMSON/.test(txt) };
    });

    check('viewer: practice coverage renders every mode', vr.count >= 5, String(vr.count));   // 5 since Clash left the pool
    check('viewer: an unplayed mode says so', vr.by.Flashpoint && vr.by.Flashpoint.state === 'cov-never',
      JSON.stringify(vr.by.Flashpoint));
    check('viewer: a stale mode is flagged', vr.by.Push && vr.by.Push.state === 'cov-stale',
      JSON.stringify(vr.by.Push));
    check('viewer: a fresh mode is not flagged', vr.by.Control && vr.by.Control.state === 'cov-ok',
      JSON.stringify(vr.by.Control));
    check('viewer: a voided map does not claim coverage',
      vr.by.Escort && vr.by.Escort.state === 'cov-never', JSON.stringify(vr.by.Escort));
    check('viewer: it names the least-practised modes', /Least practised/.test(vr.note), vr.note);
    check('viewer: a group is labelled from the registry, not a frozen string', vr.registryLabel);
    check('viewer: a league opponent links out', vr.leagueLink && vr.leagueLabel);
    check('viewer: no page errors', verrs.length === 0, verrs.join(' | '));
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

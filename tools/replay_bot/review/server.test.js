const test = require('node:test');
const assert = require('node:assert');
const fs = require('fs');
const os = require('os');
const path = require('path');
const http = require('http');

const SV = require('./server.js');

// --- pure helpers --------------------------------------------------------

test('heroList dedupes per-variant refs and folds in role and icon', () => {
  const refs = { refs: [
    { n: 'Ana', g: 'g-ana', v: 'a' }, { n: 'Ana', g: 'g-ana', v: 'b' },
    { n: 'Reaper', g: 'g-reaper', v: 'a' },
  ] };
  const list = SV.heroList(refs, { 'g-ana': 'support', 'g-reaper': 'damage' },
    { ana: 'data:ana' }, {});
  assert.strictEqual(list.length, 2);
  const ana = list.find((h) => h.guid === 'g-ana');
  assert.deepStrictEqual([ana.name, ana.role, ana.icon], ['Ana', 'support', 'data:ana']);
});

test('heroList includes a session\'s custom heroes', () => {
  const list = SV.heroList({ refs: [] }, {}, {}, { 'custom:d_mon': { name: 'D.Mon', role: null } });
  assert.strictEqual(list[0].guid, 'custom:d_mon');
  assert.strictEqual(list[0].name, 'D.Mon');
});

test('categorizeFailure maps known error text to a stable category, unknown text to other', () => {
  assert.strictEqual(SV.categorizeFailure('one press moved 0px - the forward key is not working').id, 'seek-stuck');
  assert.strictEqual(SV.categorizeFailure('events viewer would not open - K did not open the panel').id, 'events-viewer');
  assert.strictEqual(SV.categorizeFailure('could not foreground Overwatch').id, 'focus');
  assert.strictEqual(SV.categorizeFailure('timed out after 90s waiting for the replay to load').id, 'load-timeout');
  assert.strictEqual(SV.categorizeFailure('the ESC menu will not close').id, 'stuck-menu');
  assert.strictEqual(SV.categorizeFailure('something nobody has seen before').id, 'other');
  assert.strictEqual(SV.categorizeFailure(undefined).id, 'other');
});

test('failureList keeps only failed attempts, joined against the feed, oldest first', () => {
  const attempts = {
    'm1:1': { code: 'AAA111', started_at: '2026-09-12T02:00:00Z', status: 'failed', error: 'could not foreground Overwatch' },
    'm1:2': { code: 'BBB222', started_at: '2026-09-12T01:00:00Z', status: 'failed', error: 'timed out after 90s waiting for the replay to load' },
    'm1:3': { code: 'CCC333', started_at: '2026-09-12T03:00:00Z', status: 'captured', samples: 5, missed: 0 },
  };
  const feedCodes = [
    { code: 'AAA111', match_id: 'm1', game_no: 1, map: 'Nepal', division: 'EMEA Master', team_a: 'Wasp', team_b: 'NewGens' },
  ];
  const out = SV.failureList(attempts, feedCodes);
  assert.strictEqual(out.length, 2);
  assert.deepStrictEqual(out.map((f) => f.code), ['BBB222', 'AAA111']);
  assert.strictEqual(out[1].category, 'focus');
  assert.strictEqual(out[1].map, 'Nepal');
  assert.strictEqual(out[0].map, null, 'a code missing from the feed still gets a row, just no map context');
});

const ROUNDS = () => ([{
  round_no: 1, from_t: 0, to_t: 300,
  a: [
    { guid: 'g-tank', name: 'Tank', contested: false, alt_guid: null, player_id: null, player_conf: null, flags: ['attribution-abstained'] },
    { guid: 'g-widow', name: 'Widow', contested: true, alt_guid: 'g-ashe', player_id: 'p2', player_conf: 'matched', flags: ['contested'] },
    { guid: 'g-d2', name: 'D2', contested: false, alt_guid: null, player_id: 'p3', player_conf: 'matched', flags: [] },
    { guid: 'g-s1', name: 'S1', contested: false, alt_guid: null, player_id: 'p4', player_conf: 'matched', flags: [] },
    { guid: 'g-s2', name: 'S2', contested: false, alt_guid: null, player_id: 'p5', player_conf: 'matched', flags: [] },
  ],
  b: [1, 2, 3, 4, 5].map((k) => ({ guid: 'gb' + k, name: 'B' + k, contested: false, alt_guid: null, player_id: 'q' + k, player_conf: 'matched', flags: [] })),
  flags: [],
}]);

test('applyCorrections replaces a hero and clears its flags, leaving the artifact untouched', () => {
  const rounds = ROUNDS();
  const snap = JSON.stringify(rounds);
  const out = SV.applyCorrections(rounds, [
    { kind: 'hero', round_no: 1, side: 'a', slot: 1, was_guid: 'g-widow', now_guid: 'g-ashe', now_name: 'Ashe' },
  ]);
  assert.strictEqual(out[0].a[1].guid, 'g-ashe');
  assert.strictEqual(out[0].a[1].contested, false);
  assert.strictEqual(out[0].a[1].segments, null, 'a correction asserts one hero for the whole round');
  assert.deepStrictEqual(out[0].a[1].flags, []);
  assert.strictEqual(JSON.stringify(rounds), snap, 'the input rounds are not mutated');
});

test('applyCorrections fills an abstained player and drops the flag', () => {
  const out = SV.applyCorrections(ROUNDS(), [
    { kind: 'player', round_no: 1, side: 'a', slot: 0, now_id: 'p1' },
  ]);
  assert.strictEqual(out[0].a[0].player_id, 'p1');
  assert.strictEqual(out[0].a[0].player_conf, 'operator');
  assert.ok(!out[0].a[0].flags.includes('attribution-abstained'));
});

test('finalize turns a reviewed artifact into a format-1 replay-bot contribution', () => {
  const review = { session: 's', maps: [{
    demo_code: 'ABC123', match_id: 'm1', game_no: 2, map_name: 'Busan', map_guid: '0xMAP',
    map_category: 'Control', side_a_team: 'Wasp', side_b_team: 'NewGens',
    side_a_team_id: 'ta', side_b_team_id: 'tb', captured_at: '2026-09-10T00:00:00Z',
    rounds: ROUNDS(), corrections: [
      { kind: 'hero', round_no: 1, side: 'a', slot: 1, now_guid: 'g-ashe', now_name: 'Ashe' },
    ], status: 'reviewed',
  }] };
  const contrib = SV.finalize(review, { codes: [] });
  assert.strictEqual(contrib.format, 1);
  assert.strictEqual(contrib.contributor, 'replay-bot');
  assert.strictEqual(contrib.tool_version, 'replay-bot-0.1');
  const m = contrib.maps[0];
  assert.strictEqual(m.demo_code, 'ABC123');
  assert.strictEqual(m.map_guid, '0xMAP');
  // one observation per side per round; the widow->ashe fix cleared the contest,
  // so side a is a single observation now, not two.
  const aObs = m.observations.filter((o) => o.side === 'a');
  assert.strictEqual(aObs.length, 1);
  assert.ok(aObs[0].heroes.includes('g-ashe'));
  assert.ok(!aObs[0].heroes.includes('g-widow'));
});

test('uploadToken is stable across calls and written to state/', () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'rbtok-'));
  const a = SV.uploadToken(dir);
  const b = SV.uploadToken(dir);
  assert.strictEqual(a, b);
  assert.ok(/^[0-9a-f]{48}$/.test(a));
  assert.ok(fs.existsSync(path.join(dir, 'upload-token.json')));
  fs.rmSync(dir, { recursive: true, force: true });
});

test('uploadWith sends the worker headers and returns its reply', async () => {
  let seen = null;
  const fakeFetch = async (url, init) => {
    seen = { url, init };
    return { ok: true, status: 200, json: async () => ({ action: 'created', maps: 3 }) };
  };
  const r = await SV.uploadWith(fakeFetch, { format: 1 }, 'tok123');
  assert.strictEqual(seen.url, 'https://upload.owdb.io');
  assert.strictEqual(seen.init.headers['X-Owdb-Name'], 'replay-bot');
  assert.strictEqual(seen.init.headers['X-Owdb-Token'], 'tok123');
  assert.deepStrictEqual(r, { ok: true, status: 200, body: { action: 'created', maps: 3 } });
});

// --- attemptsTally --------------------------------------------------------

test('attemptsTally counts failed vs everything else', () => {
  const tally = SV.attemptsTally({
    'm1:1': { status: 'failed' },
    'm1:2': { status: 'captured' },
    'm1:3': { status: 'failed' },
  });
  assert.deepStrictEqual(tally, { done: 1, failed: 2, total: 3 });
});

test('attemptsTally handles an empty or missing attempts object', () => {
  assert.deepStrictEqual(SV.attemptsTally({}), { done: 0, failed: 0, total: 0 });
  assert.deepStrictEqual(SV.attemptsTally(undefined), { done: 0, failed: 0, total: 0 });
});

// --- currentReviewPath ---------------------------------------------------

test('currentReviewPath finds the newest review when no session is pinned', () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'rbrev-path-'));
  fs.writeFileSync(path.join(dir, 'old.review.json'), '{}');
  const newer = path.join(dir, 'new.review.json');
  fs.writeFileSync(newer, '{}');
  fs.utimesSync(newer, new Date(), new Date(Date.now() + 60000));
  assert.strictEqual(SV.currentReviewPath({ outDir: dir, session: null }), newer);
});

test('currentReviewPath returns null when nothing exists yet', () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'rbrev-path-empty-'));
  assert.strictEqual(SV.currentReviewPath({ outDir: dir, session: null }), null);
});

test('currentReviewPath honours an explicit pinned session', () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'rbrev-path-pin-'));
  fs.writeFileSync(path.join(dir, 'a.review.json'), '{}');
  fs.writeFileSync(path.join(dir, 'b.review.json'), '{}');
  assert.strictEqual(
    SV.currentReviewPath({ outDir: dir, session: 'a' }),
    path.join(dir, 'a.review.json'));
});

// --- the handler over a temp session -----------------------------------

function tmpSession() {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'rbrev-'));
  const reviewPath = path.join(dir, 'replay-bot-2026-09-10.review.json');
  const sessionDir = path.join(dir, 'replay-bot-2026-09-10');
  fs.mkdirSync(path.join(sessionDir, 'crops'), { recursive: true });
  fs.writeFileSync(path.join(sessionDir, 'crops', 'ABC123-r1-a.png'), Buffer.from([1, 2, 3]));
  const review = { session: 'replay-bot-2026-09-10', maps: [{
    demo_code: 'ABC123', match_id: 'm1', game_no: 2, map_name: 'Busan', map_guid: '0xMAP',
    map_category: 'Control', side_a_team: 'Wasp', side_b_team: 'NewGens',
    side_a_team_id: 'ta', side_b_team_id: 'tb', captured_at: '2026-09-10T00:00:00Z',
    roster: { a: [], b: [] }, rounds: ROUNDS(), corrections: [], status: 'unreviewed',
    frames: { 1: { a: 'crops/ABC123-r1-a.png' } },
  }] };
  fs.writeFileSync(reviewPath, JSON.stringify(review));
  const feedPath = path.join(dir, 'feed.json');
  fs.writeFileSync(feedPath, JSON.stringify({ codes: [], hero_roles: {} }));
  const refsPath = path.join(dir, 'refs.json');
  fs.writeFileSync(refsPath, JSON.stringify({ refs: [{ n: 'Tank', g: 'g-tank', v: 'a' }] }));
  const iconsPath = path.join(dir, 'icons.json');
  fs.writeFileSync(iconsPath, JSON.stringify({}));
  const pagePath = path.join(dir, 'page.html');
  fs.writeFileSync(pagePath, '<!doctype html><title>x</title>');
  return {
    dir, reviewPath,
    ctx: { outDir: dir, session: null, feedPath, refsPath, iconsPath,
      stateDir: path.join(dir, 'state'), pagePath,
      fetch: async () => ({ ok: true, status: 200, json: async () => ({ action: 'created', maps: 1 }) }) },
  };
}

// Drive the handler through a real one-request server so req/res are genuine.
function once(ctx, method, urlPath, body, headers) {
  return new Promise((resolve) => {
    const srv = http.createServer((req, res) => SV.handle(req, res, ctx));
    srv.listen(0, '127.0.0.1', () => {
      const port = srv.address().port;
      const req = http.request({ host: '127.0.0.1', port, path: urlPath, method, headers: headers || {} }, (res) => {
        let buf = []; res.on('data', (d) => buf.push(d));
        res.on('end', () => {
          srv.close();
          const raw = Buffer.concat(buf);
          let body;
          try { body = JSON.parse(raw); } catch (e) { body = undefined; }
          resolve({ status: res.statusCode, buf: raw, body, headers: res.headers });
        });
      });
      if (body != null) req.end(typeof body === 'string' ? body : JSON.stringify(body));
      else req.end();
    });
  });
}

test('a request with a foreign Host header is refused (DNS rebinding)', async () => {
  const { dir, ctx } = tmpSession();
  const r = await once(ctx, 'GET', '/review.json', null, { Host: 'evil.example.com' });
  assert.strictEqual(r.status, 403);
  fs.rmSync(dir, { recursive: true, force: true });
});

test('a mutating request from a cross-origin page is refused (CSRF)', async () => {
  const { dir, ctx } = tmpSession();
  const r = await once(ctx, 'POST', '/upload', '{}', { Origin: 'https://evil.example.com' });
  assert.strictEqual(r.status, 403);
  const ok = await once(ctx, 'GET', '/review.json', null, { Origin: 'http://localhost:9999' });
  assert.strictEqual(ok.status, 200, 'a same-origin Origin is fine');
  fs.rmSync(dir, { recursive: true, force: true });
});

test('GET /review.json returns the artifact', async () => {
  const { dir, ctx } = tmpSession();
  const r = await once(ctx, 'GET', '/review.json');
  assert.strictEqual(r.status, 200);
  assert.strictEqual(JSON.parse(r.buf).maps[0].demo_code, 'ABC123');
  fs.rmSync(dir, { recursive: true, force: true });
});

test('GET /crops/<name> serves a crop and refuses a traversal', async () => {
  const { dir, ctx } = tmpSession();
  const ok = await once(ctx, 'GET', '/crops/ABC123-r1-a.png');
  assert.strictEqual(ok.status, 200);
  assert.strictEqual(ok.headers['content-type'], 'image/png');
  const bad = await once(ctx, 'GET', '/crops/' + encodeURIComponent('../../feed.json'));
  assert.strictEqual(bad.status, 404);
  fs.rmSync(dir, { recursive: true, force: true });
});

test('GET /failures reads state/attempts.json beside the session and categorises it', async () => {
  const { dir, ctx } = tmpSession();
  fs.mkdirSync(ctx.stateDir, { recursive: true });
  fs.writeFileSync(path.join(ctx.stateDir, 'attempts.json'), JSON.stringify({
    'm1:1': { code: 'AAA111', started_at: '2026-09-12T02:00:00Z', status: 'failed', error: 'could not foreground Overwatch' },
    'm1:2': { code: 'CCC333', started_at: '2026-09-12T03:00:00Z', status: 'captured', samples: 5, missed: 0 },
  }));
  const r = await once(ctx, 'GET', '/failures');
  assert.strictEqual(r.status, 200);
  const j = JSON.parse(r.buf);
  assert.strictEqual(j.failures.length, 1);
  assert.strictEqual(j.failures[0].code, 'AAA111');
  assert.strictEqual(j.failures[0].category, 'focus');
  fs.rmSync(dir, { recursive: true, force: true });
});

test('GET /failures returns an empty list when there is no attempts.json yet', async () => {
  const { dir, ctx } = tmpSession();
  const r = await once(ctx, 'GET', '/failures');
  assert.strictEqual(r.status, 200);
  assert.deepStrictEqual(JSON.parse(r.buf).failures, []);
  fs.rmSync(dir, { recursive: true, force: true });
});

test('GET /hero-list merges refs, feed roles and session customs', async () => {
  const { dir, ctx } = tmpSession();
  const r = await once(ctx, 'GET', '/hero-list');
  const names = JSON.parse(r.buf).heroes.map((h) => h.name);
  assert.ok(names.includes('Tank'));
  fs.rmSync(dir, { recursive: true, force: true });
});

test('POST /upload refuses while a map is unreviewed, then accepts', async () => {
  const { dir, ctx, reviewPath } = tmpSession();
  const blocked = await once(ctx, 'POST', '/upload');
  assert.strictEqual(blocked.status, 409);

  const review = JSON.parse(fs.readFileSync(reviewPath));
  review.maps[0].status = 'reviewed';
  await once(ctx, 'POST', '/save', review);
  const fakePrune = path.join(dir, 'fake-prune.js');
  fs.writeFileSync(fakePrune, `console.log('pruned');`);
  ctx.spawn = (execPath, args, opts) => require('child_process').spawn(execPath, [fakePrune], opts);
  ctx.repoDir = dir;

  const r = await once(ctx, 'POST', '/upload');
  assert.strictEqual(r.status, 200);
  assert.strictEqual(JSON.parse(r.buf).body.action, 'created');
  fs.rmSync(dir, { recursive: true, force: true });
});

function fakeRunScript(dir, { exitCode = 0, lines = ['starting', 'map 1 done'] } = {}) {
  const p = path.join(dir, 'fake-run.js');
  fs.writeFileSync(p, `
    const lines = ${JSON.stringify(lines)};
    let i = 0;
    const timer = setInterval(() => {
      if (i >= lines.length) { clearInterval(timer); process.exit(${exitCode}); return; }
      console.log(lines[i++]);
    }, 5);
  `);
  return p;
}

test('POST /go refuses without confirmation', async () => {
  const { dir, ctx } = tmpSession();
  const r = await once(ctx, 'POST', '/go', {});
  assert.strictEqual(r.status, 400);
  fs.rmSync(dir, { recursive: true, force: true });
});

test('POST /go spawns run.js and streams its output; POST /stop writes the flag', async () => {
  const { ctx, dir } = tmpSession();
  const fake = fakeRunScript(dir, { lines: ['line one', 'line two'] });
  ctx.spawn = (execPath, args, opts) => require('child_process').spawn(execPath, [fake], opts);
  ctx.repoDir = dir;
  fs.mkdirSync(ctx.stateDir, { recursive: true });

  const goRes = await once(ctx, 'POST', '/go', { confirmed: true });
  assert.strictEqual(goRes.status, 200);

  // Give the fake process a moment to emit and exit.
  await new Promise((r) => setTimeout(r, 100));

  const status = await once(ctx, 'GET', '/status');
  assert.strictEqual(status.body.running, false); // fake script exits fast
  assert.ok(status.body.exitInfo);
  assert.strictEqual(status.body.exitInfo.code, 0);
  fs.rmSync(dir, { recursive: true, force: true });
});

test('POST /go refuses a second run while one is active', async () => {
  const { ctx, dir } = tmpSession();
  const fake = fakeRunScript(dir, { lines: ['a', 'b', 'c', 'd', 'e', 'f'] });
  ctx.spawn = (execPath, args, opts) => require('child_process').spawn(execPath, [fake], opts);
  ctx.repoDir = dir;
  await once(ctx, 'POST', '/go', { confirmed: true });
  const second = await once(ctx, 'POST', '/go', { confirmed: true });
  assert.strictEqual(second.status, 409);
  if (ctx.run && ctx.run.proc) ctx.run.proc.kill(); // cleanup, avoid a hanging test process
});

test('POST /stop writes state/loop_stop.flag', async () => {
  const { ctx, dir } = tmpSession();
  const fake = fakeRunScript(dir, { lines: ['a', 'b', 'c', 'd', 'e', 'f'] });
  ctx.spawn = (execPath, args, opts) => require('child_process').spawn(execPath, [fake], opts);
  ctx.repoDir = dir;
  await once(ctx, 'POST', '/go', { confirmed: true });
  const stopRes = await once(ctx, 'POST', '/stop');
  assert.strictEqual(stopRes.status, 200);
  assert.ok(fs.existsSync(path.join(ctx.stateDir, 'loop_stop.flag')));
  if (ctx.run && ctx.run.proc) ctx.run.proc.kill();
});

test('buildRunArgs translates division/team/limit into run.js flags', () => {
  assert.deepStrictEqual(SV.buildRunArgs({}), []);
  assert.deepStrictEqual(
    SV.buildRunArgs({ divisions: 'EMEA Master', teams: 'Wasp,Crabs', limit: 5 }),
    ['--divisions', 'EMEA Master', '--teams', 'Wasp,Crabs', '--limit', '5']);
});

test('refresh-feed skips the network call when the feed is already fresh today', async () => {
  const { dir, ctx } = tmpSession();
  fs.writeFileSync(ctx.feedPath, JSON.stringify({ built_at: new Date().toISOString(), codes: [] }));
  let fetched = false;
  ctx.fetch = async () => { fetched = true; return { ok: true, status: 200 }; };
  const r = await once(ctx, 'POST', '/refresh-feed', {});
  assert.strictEqual(r.status, 200);
  assert.strictEqual(r.body.state, 'fresh');
  assert.strictEqual(fetched, false);
  fs.rmSync(dir, { recursive: true, force: true });
});

test('refresh-feed posts to the worker, then runs git checkout after the wait and re-checks freshness', async () => {
  const { dir, ctx } = tmpSession();
  fs.writeFileSync(ctx.feedPath, JSON.stringify({ built_at: '2020-01-01T00:00:00Z', codes: [] }));
  const calls = [];
  ctx.fetch = async (url, opts) => { calls.push(['fetch', url, opts.method]); return { ok: true, status: 200 }; };
  ctx.setTimeout = (fn) => { fn(); return 0; }; // fire immediately for the test
  // Simulate the checkout actually landing a fresh feed by the time the
  // delayed step runs.
  ctx.exec = async (cmd, args) => {
    calls.push(['exec', cmd, args.join(' ')]);
    if (args.join(' ').indexOf('checkout') !== -1) {
      fs.writeFileSync(ctx.feedPath, JSON.stringify({ built_at: new Date().toISOString(), codes: [] }));
    }
  };
  const r = await once(ctx, 'POST', '/refresh-feed', {});
  assert.strictEqual(r.status, 200);
  assert.strictEqual(r.body.state, 'pending');
  assert.strictEqual(calls[0][0], 'fetch');
  assert.strictEqual(calls[0][1], 'https://upload.owdb.io/refresh');
  assert.strictEqual(calls[1][0], 'exec');
  assert.strictEqual(calls[1][2], 'fetch origin');
  assert.strictEqual(calls[2][2], 'checkout origin/main -- docs/capture/data.json');
  // The setTimeout callback ran synchronously (test double), so ctx.refresh
  // should already reflect the outcome.
  assert.strictEqual(ctx.refresh.state, 'done');
  fs.rmSync(dir, { recursive: true, force: true });
});

test('refresh-feed reports failed when the worker call errors', async () => {
  const { dir, ctx } = tmpSession();
  fs.writeFileSync(ctx.feedPath, JSON.stringify({ built_at: '2020-01-01T00:00:00Z', codes: [] }));
  ctx.fetch = async () => ({ ok: false, status: 429 });
  const r = await once(ctx, 'POST', '/refresh-feed', {});
  assert.strictEqual(r.body.state, 'failed');
  fs.rmSync(dir, { recursive: true, force: true });
});

test('GET /status reports feed freshness, attempt tally, and idle run state', async () => {
  const { dir, ctx } = tmpSession();
  fs.mkdirSync(ctx.stateDir, { recursive: true });
  fs.writeFileSync(path.join(ctx.stateDir, 'attempts.json'), JSON.stringify({
    'm1:1': { status: 'captured' }, 'm1:2': { status: 'failed' },
  }));
  fs.writeFileSync(ctx.feedPath, JSON.stringify({
    built_at: new Date().toISOString(), codes: [], hero_roles: {},
  }));
  const r = await once(ctx, 'GET', '/status');
  assert.strictEqual(r.status, 200);
  assert.strictEqual(r.body.feed.fresh, true);
  assert.deepStrictEqual(r.body.attempts, { done: 1, failed: 1, total: 2 });
  assert.strictEqual(r.body.running, false);
  assert.strictEqual(r.body.hasReview, true);
  fs.rmSync(dir, { recursive: true, force: true });
});

test('a successful upload also runs prune_frames.js and reports its output', async () => {
  const { ctx, dir, reviewPath } = tmpSession();
  const review = JSON.parse(fs.readFileSync(reviewPath));
  review.maps[0].status = 'reviewed';
  fs.writeFileSync(reviewPath, JSON.stringify(review));
  const fakePrune = path.join(dir, 'fake-prune.js');
  fs.writeFileSync(fakePrune, `console.log('fake prune ran');`);
  ctx.spawn = (execPath, args, opts) => require('child_process').spawn(execPath, [fakePrune], opts);
  ctx.repoDir = dir;
  const r = await once(ctx, 'POST', '/upload', {});
  assert.strictEqual(r.status, 200);
  assert.match(r.body.prune, /fake prune ran/);
  fs.rmSync(dir, { recursive: true, force: true });
});

test('POST /finalize writes the contribution beside the artifact', async () => {
  const { dir, ctx, reviewPath } = tmpSession();
  const r = await once(ctx, 'POST', '/finalize');
  assert.strictEqual(r.status, 200);
  const j = JSON.parse(r.buf);
  assert.strictEqual(j.maps, 1);
  const contrib = JSON.parse(fs.readFileSync(reviewPath.replace('.review.json', '.json')));
  assert.strictEqual(contrib.contributor, 'replay-bot');
  fs.rmSync(dir, { recursive: true, force: true });
});

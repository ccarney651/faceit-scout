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
    dir,
    ctx: { reviewPath, feedPath, refsPath, iconsPath, stateDir: path.join(dir, 'state'), pagePath,
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
        res.on('end', () => { srv.close(); resolve({ status: res.statusCode, buf: Buffer.concat(buf), headers: res.headers }); });
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

test('GET /hero-list merges refs, feed roles and session customs', async () => {
  const { dir, ctx } = tmpSession();
  const r = await once(ctx, 'GET', '/hero-list');
  const names = JSON.parse(r.buf).heroes.map((h) => h.name);
  assert.ok(names.includes('Tank'));
  fs.rmSync(dir, { recursive: true, force: true });
});

test('POST /upload refuses while a map is unreviewed, then accepts', async () => {
  const { dir, ctx } = tmpSession();
  const blocked = await once(ctx, 'POST', '/upload');
  assert.strictEqual(blocked.status, 409);

  const review = JSON.parse(fs.readFileSync(ctx.reviewPath));
  review.maps[0].status = 'reviewed';
  await once(ctx, 'POST', '/save', review);

  const r = await once(ctx, 'POST', '/upload');
  assert.strictEqual(r.status, 200);
  assert.strictEqual(JSON.parse(r.buf).body.action, 'created');
  fs.rmSync(dir, { recursive: true, force: true });
});

test('POST /finalize writes the contribution beside the artifact', async () => {
  const { dir, ctx } = tmpSession();
  const r = await once(ctx, 'POST', '/finalize');
  assert.strictEqual(r.status, 200);
  const j = JSON.parse(r.buf);
  assert.strictEqual(j.maps, 1);
  const contrib = JSON.parse(fs.readFileSync(ctx.reviewPath.replace('.review.json', '.json')));
  assert.strictEqual(contrib.contributor, 'replay-bot');
  fs.rmSync(dir, { recursive: true, force: true });
});

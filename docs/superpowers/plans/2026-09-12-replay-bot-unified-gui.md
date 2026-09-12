# Replay-Bot Unified GUI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fold `run.js`'s capture loop into `tools/replay_bot/review/server.js` so one localhost GUI covers the whole scouting session — refresh the feed, confirm Overwatch is ready, run, review, upload — with no console commands.

**Architecture:** Extend the existing review/finalize/upload server in place (same command, same port convention) rather than adding a new entry point. It gains a handful of new endpoints (`/status`, `/refresh-feed`, `/go`, `/stop`, `/run-log`) backed by an in-memory `ctx.run` handle around a spawned `run.js` child process, plus a small addition to `run.js` itself (a file-based stop flag, since Windows doesn't deliver real POSIX signals to a spawned child). The existing review path also needs to stop being fixed at server startup, since a fresh run creates a *new* review artifact after the server is already running.

**Tech Stack:** Node.js, `node:test` (already the project's test runner for this directory), `http`/`child_process`/`fs` only — no new dependencies, no framework, no build step, no WebSocket library (Server-Sent Events for the log stream).

**Spec:** `specs/2026-09-12-replay-bot-unified-gui-design.md`

## Global Constraints

- Extend `tools/replay_bot/review/server.js` in place — same command
  (`node tools/replay_bot/review/server.js`), same port convention. Do not
  create a new entry point.
- Dependency-free: Node's built-in `http`, `fs`, `child_process` only.
- Overwatch readiness is a **manual** precondition in v1 — never automate
  launching the client or navigating its menus.
- Real scouting codes come only from `docs/capture/data.json` (the feed
  `run.js` already reads with no flags). Never wire the Go path to
  `scrape_codes.js`, `--codes`, or `--code-stack` — those are test-only per
  `run.js`'s own header comment.
- Never pass `run.js` the `--stale-ok` override automatically. A stale feed
  must surface as a visible refusal, not be silently bypassed.
- `prune_frames.js` runs only after a successful upload, never before or
  independently of one.
- All new server-side state (`ctx.run`, `ctx.refresh`) must be injectable in
  tests the same way `ctx.fetch` already is — no new global/module-level
  mutable state.

---

## Task 1: Dynamic review-path resolution

The server currently resolves `ctx.reviewPath` once in `main()` and refuses
to start at all if no review artifact exists yet
(`tools/replay_bot/review/server.js:342-348`). That's backwards for the Run
view: an operator starting a fresh overnight session has no review artifact
yet — the whole point of running is to create one — and once a run finishes,
the server needs to notice the *new* file without a restart.

**Files:**
- Modify: `tools/replay_bot/review/server.js`
- Modify: `tools/replay_bot/review/server.test.js`

**Interfaces:**
- Produces: `currentReviewPath(ctx)` — returns the review path to use right
  now (a fresh `newestReview(ctx.outDir)` lookup when `ctx.session` is
  unset, otherwise the pinned session), or `null` if none exists yet. Every
  later task that needs "the review file" calls this instead of reading a
  field off `ctx`.
- Consumes: existing `newestReview(dir)` (unchanged).

- [x] **Step 1: Write the failing tests**

Add to `tools/replay_bot/review/server.test.js` (near the other pure-helper
tests, before the `tmpSession()` section):

```javascript
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
```

Also update `tmpSession()` (around line 141-168) since it currently builds
`ctx.reviewPath` directly. Change its return and the `ctx` it builds to:

```javascript
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
```

Then fix the two call sites that read `ctx.reviewPath` directly (search the
file for `ctx.reviewPath` after the fixture change — they're in the
`/finalize` and `/upload` assertions) to use the `reviewPath` now returned
alongside `ctx` instead, e.g. `tmpSession()` callers currently do
`const { ctx } = tmpSession();` — change to
`const { ctx, reviewPath } = tmpSession();` and replace `ctx.reviewPath`
with `reviewPath` in those two assertions.

- [x] **Step 2: Run tests to verify they fail**

Run: `cd tools/replay_bot/review && node --test server.test.js`
Expected: FAIL — `SV.currentReviewPath is not a function`, plus failures in
any test still referencing the old `ctx.reviewPath` fixture shape.

- [x] **Step 3: Implement `currentReviewPath` and rewire the handlers**

In `tools/replay_bot/review/server.js`, replace the existing
`resolveReviewPath` function (around line 335-340) with:

```javascript
function resolveReviewPathIn(outDir, session) {
  if (!session) return newestReview(outDir);
  if (fs.existsSync(session)) return session;
  const named = path.join(outDir, session.endsWith('.review.json') ? session : session + '.review.json');
  return fs.existsSync(named) ? named : null;
}

function currentReviewPath(ctx) {
  return resolveReviewPathIn(ctx.outDir, ctx.session);
}
```

Update every handler in `handle()` that reads `ctx.reviewPath` to call
`currentReviewPath(ctx)` instead, resolving it once at the top of each
branch:

```javascript
    if (req.method === 'GET' && p === '/review.json') {
      const r = readJson(currentReviewPath(ctx), null);
      return r ? sendJson(res, 200, r) : sendJson(res, 404, { error: 'no review artifact' });
    }
```

```javascript
    if (req.method === 'GET' && p === '/hero-list') {
      const feed = readJson(ctx.feedPath, {});
      const list = heroList(
        readJson(ctx.refsPath, { refs: [] }),
        feed.hero_roles || {},
        readJson(ctx.iconsPath, {}),
        collectCustomHeroes(readJson(currentReviewPath(ctx), { maps: [] })));
      return sendJson(res, 200, { heroes: list });
    }
```

```javascript
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
```

```javascript
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
      return sendJson(res, result.ok ? 200 : 502, result);
    }
```

Now update `main()` (around line 342-367) to build `ctx.outDir`/`ctx.session`
instead of a precomputed path, and drop the hard failure:

```javascript
function main() {
  const args = parseArgs(process.argv.slice(2));
  const ctx = {
    outDir: OUT, session: args.session,
    feedPath: FEED, refsPath: REFS, iconsPath: ICONS,
    stateDir: STATE, pagePath: PAGE,
    fetch: (...a) => fetch(...a),
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
```

Finally, since `resolveReviewPath` no longer exists under that name, update
the `module.exports` block (around line 369-373) to export the new names:

```javascript
module.exports = {
  newestReview, heroList, applyCorrections, finalize, uploadToken, uploadWith,
  collectCustomHeroes, parseArgs, currentReviewPath, resolveReviewPathIn, handle,
  categorizeFailure, failureList,
};
```

- [x] **Step 4: Run tests to verify they pass**

Run: `cd tools/replay_bot/review && node --test server.test.js`
Expected: PASS, all tests including the pre-existing ones (they now go
through `tmpSession()`'s updated fixture).

- [x] **Step 5: Commit**

```bash
git add tools/replay_bot/review/server.js tools/replay_bot/review/server.test.js
git commit -m "replay-bot review server: resolve the review path dynamically per-request"
```

---

## Task 2: `attemptsTally` + `GET /status`

**Files:**
- Modify: `tools/replay_bot/review/server.js`
- Modify: `tools/replay_bot/review/server.test.js`

**Interfaces:**
- Consumes: `RunJS.feedFreshness(feed, now)` from `tools/replay_bot/run.js`
  (already exported there — confirm with
  `node -e "console.log(typeof require('./run.js').feedFreshness)"` from
  `tools/replay_bot/` if in doubt; it should print `function`).
- Produces: `attemptsTally(attempts)` → `{ done, failed, total }`. `/status`
  response shape: `{ feed, attempts, running, exitInfo, hasReview, refresh }`
  — later tasks populate `running`/`exitInfo` (Task 4) and `refresh`
  (Task 3) meaningfully; this task wires them to safe defaults
  (`running: false`, `exitInfo: null`, `refresh: { state: 'idle' }`) so the
  endpoint is usable standalone.

- [x] **Step 1: Write the failing tests**

Add to `server.test.js`:

```javascript
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
```

And a handler-level test, alongside the other `once(ctx, ...)` tests further
down the file:

```javascript
test('GET /status reports feed freshness, attempt tally, and idle run state', async () => {
  const { ctx } = tmpSession();
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
});
```

- [x] **Step 2: Run tests to verify they fail**

Run: `cd tools/replay_bot/review && node --test server.test.js`
Expected: FAIL — `SV.attemptsTally is not a function`, and a 404 from the
unhandled `/status` route.

- [x] **Step 3: Implement**

Add near `failureList` in `server.js`:

```javascript
const RunJS = require('../run.js');

function attemptsTally(attempts) {
  let done = 0, failed = 0;
  Object.values(attempts || {}).forEach((v) => {
    if (v && v.status === 'failed') failed += 1; else done += 1;
  });
  return { done, failed, total: done + failed };
}
```

Add the route inside `handle()`, before the final `return send(res, 404, ...)`:

```javascript
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
```

Add `attemptsTally` to `module.exports`.

- [x] **Step 4: Run tests to verify they pass**

Run: `cd tools/replay_bot/review && node --test server.test.js`
Expected: PASS.

- [x] **Step 5: Commit**

```bash
git add tools/replay_bot/review/server.js tools/replay_bot/review/server.test.js
git commit -m "replay-bot review server: add GET /status (feed freshness + attempt tally)"
```

---

## Task 3: `POST /refresh-feed`

**Files:**
- Modify: `tools/replay_bot/review/server.js`
- Modify: `tools/replay_bot/review/server.test.js`

**Interfaces:**
- Consumes: `ctx.fetch` (existing injectable), plus two **new** injectables
  this task adds: `ctx.exec(cmd, args, opts)` (a promisified
  `child_process.execFile`-shaped function — production default wraps the
  real thing; tests inject a fake) and `ctx.setTimeout` (production default
  is the global `setTimeout`; tests inject one that invokes immediately).
- Produces: `ctx.refresh` — `{ state: 'idle' | 'fresh' | 'pending' | 'done' | 'stale' | 'failed', ... }`,
  read by `/status` (Task 2) and by the Run view (Task 6).

Real endpoint is `https://upload.owdb.io/refresh` (`POST`, no body, no auth
— confirmed against `infra/upload-worker/worker.js`'s `/refresh` handler,
which fires a `repository_dispatch` and returns `200 {started:true}` or a
`429`/`502` error). It does not expose a way to poll for completion, so this
waits a fixed delay (matching the dashboard's own "~2 minutes, then reload"
copy) and then re-checks freshness itself.

- [x] **Step 1: Write the failing tests**

```javascript
test('refresh-feed skips the network call when the feed is already fresh today', async () => {
  const { ctx } = tmpSession();
  fs.writeFileSync(ctx.feedPath, JSON.stringify({ built_at: new Date().toISOString(), codes: [] }));
  let fetched = false;
  ctx.fetch = async () => { fetched = true; return { ok: true, status: 200 }; };
  const r = await once(ctx, 'POST', '/refresh-feed', {});
  assert.strictEqual(r.status, 200);
  assert.strictEqual(r.body.state, 'fresh');
  assert.strictEqual(fetched, false);
});

test('refresh-feed posts to the worker, then runs git checkout after the wait and re-checks freshness', async () => {
  const { ctx } = tmpSession();
  fs.writeFileSync(ctx.feedPath, JSON.stringify({ built_at: '2020-01-01T00:00:00Z', codes: [] }));
  const calls = [];
  ctx.fetch = async (url, opts) => { calls.push(['fetch', url, opts.method]); return { ok: true, status: 200 }; };
  ctx.exec = async (cmd, args) => { calls.push(['exec', cmd, args.join(' ')]); };
  ctx.setTimeout = (fn) => { fn(); return 0; }; // fire immediately for the test
  // Simulate the checkout actually landing a fresh feed by the time the
  // delayed step runs.
  const realFetch = ctx.fetch;
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
});

test('refresh-feed reports failed when the worker call errors', async () => {
  const { ctx } = tmpSession();
  fs.writeFileSync(ctx.feedPath, JSON.stringify({ built_at: '2020-01-01T00:00:00Z', codes: [] }));
  ctx.fetch = async () => ({ ok: false, status: 429 });
  const r = await once(ctx, 'POST', '/refresh-feed', {});
  assert.strictEqual(r.body.state, 'failed');
});
```

- [x] **Step 2: Run tests to verify they fail**

Run: `cd tools/replay_bot/review && node --test server.test.js`
Expected: FAIL — `/refresh-feed` unhandled (404), `ctx.refresh` undefined.

- [x] **Step 3: Implement**

```javascript
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
```

Route, before the final 404:

```javascript
    if (req.method === 'POST' && p === '/refresh-feed') {
      if (ctx.refresh && ctx.refresh.state === 'pending') {
        return sendJson(res, 409, { error: 'a refresh is already pending' });
      }
      const r = await startRefresh(ctx);
      return sendJson(res, 200, r);
    }
```

In `main()`, add the two new production defaults to `ctx`:

```javascript
    fetch: (...a) => fetch(...a),
    setTimeout,
    exec: (cmd, args, opts) => new Promise((resolve, reject) => {
      require('child_process').execFile(cmd, args, opts, (err) => err ? reject(err) : resolve());
    }),
    repoDir: REPO,
```

(`REPO` already exists as a module-level constant near the top of the file —
confirm it points at the repo root two levels up from
`tools/replay_bot/review/`.)

Add `attemptsTally`... already exported in Task 2; add nothing new to
`module.exports` for this task (`startRefresh` is exercised only through the
route in tests, matching how `uploadWith` is both exported and used
internally).

- [x] **Step 4: Run tests to verify they pass**

Run: `cd tools/replay_bot/review && node --test server.test.js`
Expected: PASS.

- [x] **Step 5: Commit**

```bash
git add tools/replay_bot/review/server.js tools/replay_bot/review/server.test.js
git commit -m "replay-bot review server: add POST /refresh-feed"
```

---

## Task 4: `run.js` stop flag, then `POST /go` / `POST /stop` / `GET /run-log`

Node's `child_process` cannot deliver a real `SIGINT` to a child on Windows
— `child.kill()` there terminates unconditionally rather than triggering the
child's own signal handler (this is Node's documented behavior, not a
guess: see the `child_process` docs' Windows caveats). `run.js` already has
exactly the right shape for a **file-based** stop, though — it already
checks `state/loop_pause.flag` at a safe "between maps" checkpoint. This
task adds a sibling `state/loop_stop.flag` for that same checkpoint, which
is what the GUI's `/stop` will actually use instead of `child.kill()`.

**Files:**
- Modify: `tools/replay_bot/run.js`
- Modify: `tools/replay_bot/run.test.js`
- Modify: `tools/replay_bot/review/server.js`
- Modify: `tools/replay_bot/review/server.test.js`

**Interfaces:**
- Produces (in `run.js`): checking `state/loop_stop.flag` sets the same
  internal `stopRequested` the `SIGINT` handler already sets. `main()`
  deletes any stale flag at start, so a leftover flag from a previous run
  never kills a brand-new one before it starts.
- Produces (in `server.js`): `buildRunArgs(body)` (pure, testable) →
  `string[]` of CLI args; `POST /go` (starts a run, refuses if one is
  active); `POST /stop` (writes the flag); `GET /run-log` (SSE stream of
  the run's stdout/stderr, replaying the buffered log to a new connection
  first).
- Consumes: `ctx.spawn` (new injectable, production default
  `require('child_process').spawn`), `ctx.repoDir` (added in Task 3).

### Part A — `run.js`'s stop flag

**No unit test for this part.** `main()`'s stop-flag handling lives inside a
large, side-effecting function that drives a live client and isn't
unit-testable in isolation — the existing test suite never calls `main()`
at all (per the file's own bottom-of-file "requiring must never drive the
client" guard). Writing a test here would mean either calling `main()`
(not possible in CI) or asserting against a string constant, which tests
nothing real. This part's correctness is verified for real by Task 4 Part
B's integration test (a fake `run.js`-shaped child script exercising the
actual flag file end to end through the server) and by the manual
end-to-end check in Task 4's final step. Go straight to implementation.

- [x] **Step 1: Implement the stop flag in `run.js`**

In `run.js`, immediately after the existing `PAUSE_FLAG` declaration
(around line 386):

```javascript
  const PAUSE_FLAG = path.join(__dirname, 'state', 'loop_pause.flag');
  const STOP_FLAG = path.join(__dirname, 'state', 'loop_stop.flag');
  try { fs.unlinkSync(STOP_FLAG); } catch (e) { /* fine if it wasn't there */ }
  let stopRequested = false;
```

And inside `checkpoint()` (around line 400-410), check it alongside the
pause flag:

```javascript
  async function checkpoint() {
    if (fs.existsSync(STOP_FLAG)) {
      stopRequested = true;
      console.log('\nstop requested (state/loop_stop.flag) - stopping after this map');
      return;
    }
    if (fs.existsSync(PAUSE_FLAG)) {
      console.log('paused - waiting for state/loop_pause.flag to clear ' +
        '(console Resume, or the hotkey)');
      while (!stopRequested && fs.existsSync(PAUSE_FLAG)) {
        if (fs.existsSync(STOP_FLAG)) { stopRequested = true; break; }
        await wait(TIMING.poll.ms);
      }
      if (!stopRequested) console.log('resumed');
    }
    TIMING.reload();
  }
```

- [x] **Step 2: Run the existing suite to confirm nothing broke**

Run: `cd tools/replay_bot && node --test run.test.js`
Expected: PASS (this change is additive to a code path the existing tests
don't drive end-to-end, since `main()` isn't called from tests per the
file's own bottom-of-file guard).

- [x] **Step 3: Commit**

```bash
git add tools/replay_bot/run.js
git commit -m "replay-bot: add a file-based stop flag alongside the pause flag"
```

### Part B — `POST /go`, `POST /stop`, `GET /run-log`

- [x] **Step 1: Write the failing tests**

For this part, spawn a small **fake run.js** rather than the real one (the
real one drives a live Overwatch client and can't run in a test). Create it
inline in the test via a temp file:

```javascript
function fakeRunScript(dir, { exitCode = 0, lines = ['starting', 'map 1 done'], hangMs = 0 } = {}) {
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
```

Add the tests:

```javascript
test('POST /go refuses without confirmation', async () => {
  const { ctx } = tmpSession();
  const r = await once(ctx, 'POST', '/go', {});
  assert.strictEqual(r.status, 400);
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
```

- [x] **Step 2: Run tests to verify they fail**

Run: `cd tools/replay_bot/review && node --test server.test.js`
Expected: FAIL — `/go`, `/stop` unhandled (404), `SV.buildRunArgs` missing.

- [x] **Step 3: Implement**

Add near the top of `server.js`, alongside the other module-level path
constants:

```javascript
const RUNJS_PATH = path.join(RBOT, 'run.js');
```

(`RBOT` should already exist as a constant near the top of the file,
pointing at `tools/replay_bot/` — confirm before adding a duplicate.)

Add the pure helper:

```javascript
function buildRunArgs(body) {
  const args = [];
  if (body && body.divisions) args.push('--divisions', String(body.divisions));
  if (body && body.teams) args.push('--teams', String(body.teams));
  if (body && body.limit) args.push('--limit', String(body.limit));
  return args;
}
```

Add the run-lifecycle logic:

```javascript
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
```

Routes, before the final 404:

```javascript
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
```

Add `ctx.spawn: require('child_process').spawn,` to `main()`'s `ctx`
construction. Add `buildRunArgs` to `module.exports`.

- [x] **Step 4: Run tests to verify they pass**

Run: `cd tools/replay_bot/review && node --test server.test.js`
Expected: PASS.

- [x] **Step 5: Commit**

```bash
git add tools/replay_bot/review/server.js tools/replay_bot/review/server.test.js
git commit -m "replay-bot review server: add POST /go, POST /stop, GET /run-log"
```

- [x] **Step 6: Manual verification against the real `run.js`**

This is the one piece this plan cannot unit-test honestly (per the design
doc's own testing section — child-process lifecycle against the real
client is integration-shaped). Before trusting `/stop` on a real overnight
run: start the server, `POST /go` with `{"confirmed": true, "limit": 1}`
against a real (or `--dry`-verified) feed, confirm the log stream shows
`run.js`'s own output, then `POST /stop` mid-run and confirm the process
exits after finishing its current map rather than being force-killed.

---

## Task 5: Wire `prune_frames.js` into a successful upload

**Files:**
- Modify: `tools/replay_bot/review/server.js`
- Modify: `tools/replay_bot/review/server.test.js`

**Interfaces:**
- Consumes: `ctx.spawn` (from Task 4), `tools/replay_bot/prune_frames.js`
  (existing script, takes an optional session name positional arg, prints
  one or two summary lines to stdout — see its own header comment).
- Produces: `result.prune` (string) added to a successful `/upload`
  response body only.

- [x] **Step 1: Write the failing test**

```javascript
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
});
```

- [x] **Step 2: Run test to verify it fails**

Run: `cd tools/replay_bot/review && node --test server.test.js`
Expected: FAIL — `r.body.prune` is `undefined`.

- [x] **Step 3: Implement**

Add near `startRun`:

```javascript
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
```

Update the `/upload` handler's success branch:

```javascript
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
```

- [x] **Step 4: Run tests to verify they pass**

Run: `cd tools/replay_bot/review && node --test server.test.js`
Expected: PASS.

- [x] **Step 5: Commit**

```bash
git add tools/replay_bot/review/server.js tools/replay_bot/review/server.test.js
git commit -m "replay-bot review server: prune frames after a successful upload"
```

---

## Task 6: `page.html` — the Run tab

**Files:**
- Modify: `tools/replay_bot/review/page.html`
- Create: `tools/replay_bot/review/landing.js` (pure landing-tab logic,
  extracted so it's testable in Node rather than only by eye in a browser)
- Create: `tools/replay_bot/review/landing.test.js`

**Interfaces:**
- Produces: `landingView(status)` → `'run' | 'review'`, given a `/status`
  response shape. Pure function, the one piece of this task's logic worth
  unit-testing per the design doc's own note that browser wiring otherwise
  needs a manual pass.
- Consumes: every endpoint from Tasks 2-5 (`/status`, `/refresh-feed`,
  `/go`, `/stop`, `/run-log`), plus the existing Review-view endpoints
  unchanged.

- [x] **Step 1: Write the failing test**

```javascript
// tools/replay_bot/review/landing.test.js
const test = require('node:test');
const assert = require('node:assert');
const { landingView } = require('./landing.js');

test('lands on Run when a run is active', () => {
  assert.strictEqual(landingView({ running: true, hasReview: true }), 'run');
});

test('lands on Run when nothing to review and no run has happened', () => {
  assert.strictEqual(landingView({ running: false, hasReview: false }), 'run');
});

test('lands on Review when a run just finished and there is something to review', () => {
  assert.strictEqual(landingView({ running: false, hasReview: true, exitInfo: { code: 0 } }), 'review');
});
```

- [x] **Step 2: Run test to verify it fails**

Run: `cd tools/replay_bot/review && node --test landing.test.js`
Expected: FAIL — module not found.

- [x] **Step 3: Implement**

```javascript
// tools/replay_bot/review/landing.js
// Which tab the page opens on: Run when there's a run in progress or
// nothing to review yet, Review when a run just produced something to look
// at. Extracted from page.html's bootstrap so it's unit-testable - the rest
// of the page's wiring is DOM plumbing, verified by hand per this project's
// "pytest/node --test cannot see through a real browser" limitation.
'use strict';
function landingView(status) {
  if (status && status.running) return 'run';
  if (status && status.hasReview) return 'review';
  return 'run';
}
module.exports = { landingView };
```

- [x] **Step 4: Run test to verify it passes**

Run: `cd tools/replay_bot/review && node --test landing.test.js`
Expected: PASS.

- [x] **Step 5: Commit**

```bash
git add tools/replay_bot/review/landing.js tools/replay_bot/review/landing.test.js
git commit -m "replay-bot review page: extract landing-tab decision as a pure function"
```

- [x] **Step 6: Add the Run tab to `page.html`**

Read the existing `page.html` first to match its current tab/section
pattern and styling before adding to it (it's a single dependency-free HTML
file — no build step). Add:

- A tab bar with **Run** / **Review** buttons, toggling which section is
  visible (`hidden` attribute, per this project's convention of toggling
  visibility that way rather than `style.display`).
- **Run** section containing:
  - A feed-freshness line and a **Refresh feed** button, calling
    `POST /refresh-feed` and polling `GET /status` every 2s while
    `refresh.state === 'pending'` to update it.
  - A checkbox: "Overwatch is open on the Replay History tab."
  - Optional division/team/limit text inputs (plain, matching `run.js`'s
    own flag names — no new vocabulary).
  - A **Go** button, disabled until the checkbox is ticked and
    `status.feed.fresh` is true; `POST /go` with
    `{ confirmed: true, divisions, teams, limit }` on click.
  - A **Stop** button, `POST /stop`, enabled only while `status.running`.
  - A log pane: on entering the Run tab (or right after Go), open
    `new EventSource('/run-log')` and append each `message` event's parsed
    string to the pane; on an `event: done` message, close the
    `EventSource` and re-poll `/status`.
- On page load, `fetch('/status')` and call `landingView(status)` (inline a
  copy of the same small function — this file has no module system, so
  duplicate the ~4 lines rather than trying to share a `require` with a
  browser context) to decide which tab starts visible.
- When a run's `done` event arrives and `status.hasReview` is true, switch
  to the Review tab automatically (matches the design doc's flow: no second
  command to remember).

Keep this addition self-contained (its own `<script>` block or a clearly
delimited section of the existing one) so it doesn't tangle with the
existing Review-view JS.

- [x] **Step 7: Manual verification**

Start the server (`node tools/replay_bot/review/server.js --open`),
confirm: the Run tab renders, `Refresh feed` reports a state without
crashing (fine if it reports `fresh` already), the checkbox gates `Go`,
and — using `--dry`-style low-risk conditions if a real run isn't
available — `Go` at least reaches the "feed not fresh" or "confirm
Overwatch" refusal paths correctly, and the log pane receives streamed
text without a page reload.

- [x] **Step 8: Commit**

```bash
git add tools/replay_bot/review/page.html
git commit -m "replay-bot review page: add the Run tab (fetch/precondition/go/stop/log)"
```

---

## Plan self-review notes

- **Spec coverage:** feed-refresh mechanics (Task 3), manual OW precondition
  (Task 6's checkbox, no automation added anywhere), one localhost page /
  dependency-free (all tasks extend the existing file, no new deps), SSE
  log stream (Task 4), auto-handoff to Review (Task 6), prune-after-upload
  (Task 5), dynamic review path so a new run's artifact is picked up
  (Task 1) are all covered. The design doc's two "open questions" (SSE vs
  polling, filter-flag naming) are resolved in-plan: SSE (Task 4), and
  reusing `run.js`'s own flag names verbatim (Task 6).
- **No automation of Overwatch launch/navigation** anywhere in this plan,
  per the confirmed decision — the checkbox in Task 6 is the entire
  "precondition" surface.
- **Windows signal caveat** is the one correction made mid-planning (the
  design doc assumed a signal-based Stop); Task 4 replaces it with the
  file-flag mechanism already proven by `PAUSE_FLAG`.

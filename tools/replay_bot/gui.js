// tools/replay_bot/gui.js
// A local page for recording and replaying menu chunks.
//
//   node tools/replay_bot/gui.js        then open http://127.0.0.1:8787
//
// The recorder is a good CLI and an awkward one to use in the middle of a
// recording session: every chunk is record, alt-tab, perform, F10, read the
// listing, play it back to check, re-record if it looked wrong. That is a loop
// with a state - which chunks exist, which are still missing - and a terminal
// does not hold state.
//
// So this is a page over the same functions. It does no work of its own: every
// button calls recorder.js, which is what the CLI calls, and the interesting
// logic stays where the tests are.
//
// LOCAL ONLY, and on purpose. It binds 127.0.0.1, because what it exposes is
// "run PowerShell that clicks in the game" and nothing on a network should be
// able to ask for that. Names off a request are checked by recorder.safeName
// before they are allowed near a file path.
//
// ONE OPERATION AT A TIME. Recording and playing both own the mouse and
// keyboard of the whole machine; two at once would fight, and the loser would
// be a chunk full of the other's clicks.

const http = require('http');
const fs = require('fs');
const path = require('path');
const R = require('./recorder.js');

const HOST = '127.0.0.1';
const PORT = Number(process.env.OWDB_GUI_PORT) || 8787;
const PAGE = path.join(__dirname, 'gui.html');

// The chunks a full run needs, in the order they happen. There are only two,
// because leaving a replay lands back on the replay history tab: the loop is
// open-import, capture, leave-replay, and round again. No chunk navigates to
// the replay list, since the client is already there.
//
// Recorded separately so that when Blizzard moves one menu, one chunk is
// re-recorded and not both - and re-recording open-import COSTS A LEAGUE CODE,
// because a code already imported cannot be imported again cleanly.
const WANTED = [
  {
    name: 'open-import',
    needsCode: true,
    from: 'the replay history tab',
    does: 'Import, paste the code, OK, Watch - the replay starts immediately',
  },
  {
    name: 'set-interval',
    needsCode: false,
    from: 'inside a replay, with the controls already up (press N then K first)',
    does: 'options -> time skip interval -> 60s -> back to the replay. The bot ' +
      'presses N and K itself before playing this, so record it from that ' +
      'state. Played once per session: the setting holds until the client ' +
      'restarts and then silently reverts, which is why it is measured too',
  },
  {
    name: 'leave-replay',
    needsCode: false,
    from: 'inside a replay, map finished',
    does: 'ESC, Leave Game - which lands back on the replay history tab',
  },
];

let busy = null;

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
      if (n > 4096) { reject(new Error('body too large')); req.destroy(); return; }
      parts.push(c);
    });
    req.on('end', function () {
      try { resolve(parts.length ? JSON.parse(Buffer.concat(parts).toString('utf8')) : {}); }
      catch (e) { reject(new Error('body is not JSON')); }
    });
    req.on('error', reject);
  });
}

// A code is typed into the game, so it is checked the same way a name is.
function safeCode(code) {
  if (code === undefined || code === null || code === '') return null;
  const s = String(code).trim().toUpperCase();
  if (!/^[A-Z0-9]{1,12}$/.test(s)) throw new Error('bad code: ' + JSON.stringify(code));
  return s;
}

function listChunks() {
  if (!fs.existsSync(R.DIR)) return [];
  return fs.readdirSync(R.DIR)
    .filter(function (f) { return /\.json$/.test(f); })
    .map(function (f) {
      const c = JSON.parse(fs.readFileSync(path.join(R.DIR, f), 'utf8'));
      return {
        name: c.name,
        recorded_at: c.recorded_at,
        client: c.client,
        events: c.events,
        typesCode: c.events.some(function (e) {
          return (e.type === 'text' || e.type === 'paste') && e.value === R.CODE;
        }),
      };
    });
}

// Exclusive access to the machine's mouse and keyboard, so a second request
// while one is running is refused rather than queued - the operator is standing
// at the game, and a recording that starts later than they think is worse than
// one that plainly did not start.
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
    return { rect: rect, rectError: rectError, wanted: WANTED, chunks: listChunks(), busy: busy };
  },

  'POST /api/record': async function (body) {
    const name = R.safeName(body.name);
    const code = safeCode(body.code);
    return exclusive('recording', async function () {
      const got = await R.record(name, { code: code, maxSeconds: Number(body.maxSeconds) || 120 });
      return {
        name: name,
        path: got.path,
        events: got.chunk.events,
        codeFound: got.codeFound,
        // A chunk recorded with a code that never got typed would put the
        // operator's own code into all 255 replays, so it is said plainly
        // rather than left in a log line.
        warning: !got.codeFound
          ? 'no code in this chunk - neither a Ctrl+V nor the typed code' +
            (code ? ' ' + code : '') + ', so it has no placeholder. Fine for ' +
            'leave-replay; wrong for anything that opens a replay.'
          : null,
      };
    });
  },

  // Checking touches nothing, so it needs no exclusive lock and no warning -
  // and it is the cheap thing to do before spending a code.
  'POST /api/check': async function (body) {
    return R.play(R.safeName(body.name), { code: safeCode(body.code), dryRun: true });
  },

  'POST /api/play': async function (body) {
    const name = R.safeName(body.name);
    const code = safeCode(body.code);
    return exclusive('playing', function () { return R.play(name, { code: code }); });
  },

  'POST /api/delete': async function (body) {
    const name = R.safeName(body.name);
    const p = R.chunkPath(name);
    if (!fs.existsSync(p)) throw new Error('no chunk "' + name + '"');
    fs.unlinkSync(p);
    return { deleted: name };
  },
};

const server = http.createServer(async function (req, res) {
  const url = req.url.split('?')[0];

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

server.listen(PORT, HOST, function () {
  console.log(`replay-bot recorder on http://${HOST}:${PORT}`);
  console.log('  Overwatch must be running. Ctrl-C to stop.');
});

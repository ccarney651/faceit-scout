// tools/replay_bot/run.js
// The unattended loop: queue, import, capture, leave, repeat.
//
//   node tools/replay_bot/run.js --dry              show the queue, touch nothing
//   node tools/replay_bot/run.js --limit 3          three maps from the feed
//   node tools/replay_bot/run.js --codes A1B2C3,... arbitrary codes, for testing
//
// IT OWNS THE MACHINE while it runs. Keys and clicks only land in a foreground
// client, so this is an overnight job on a rig nobody is using.
//
// ONE SHOT PER CODE, and that shapes everything here. A code already imported
// cannot be imported again cleanly - the client warns and demands a manual
// scroll-and-select, which ends an unattended run - and imports cannot be
// deleted. So:
//
//   - a code is written to the attempt log BEFORE it is opened, never after,
//     because a crash between opening and finishing must not look like a code
//     that was never tried;
//   - a failed map is a loss to report, not a retry to queue;
//   - the run stops after two consecutive failures rather than working its way
//     through the night burning codes on a client that is stuck in a menu.
//
// What makes that survivable is that every frame is kept. A better matcher can
// re-read a map later with no client time and no code; only a broken grab is
// unrecoverable, which is why the guards here refuse loudly.

const fs = require('fs');
const path = require('path');

const C = require('./capture.js');
const H = require('./host.js');
const R = require('./recorder.js');
const Q = require('./queue.js');
const E = require('./emit.js');
const calib = require('./calib.js');
const Crop = require('./crop.js');

const FRAMES = path.join(__dirname, 'frames');
const STATE = path.join(__dirname, 'state', 'attempts.json');
const OUT_DIR = path.join(__dirname, 'out');
const FEED = path.join(__dirname, '../../docs/capture/data.json');

const CONTRIBUTOR = 'replay-bot';
const LOAD_TIMEOUT_MS = 90000;
const EXIT_TIMEOUT_MS = 30000;
// A grab already costs half a second, so a one-second poll is a real poll and
// not a busy loop.
const POLL_MS = 1000;

// ------------------------------------------------------------------ pure ----

function parseArgs(argv) {
  const flag = (name) => {
    const i = argv.indexOf(name);
    return i === -1 ? null : argv[i + 1];
  };
  return {
    dry: argv.includes('--dry'),
    limit: Number(flag('--limit')) || null,
    codes: flag('--codes') ? flag('--codes').split(',').map((c) => c.trim()).filter(Boolean) : null,
    out: flag('--out'),
    staleOk: argv.includes('--stale-ok'),
    // Skips the timed-playback measurement when the operator already knows what
    // the client is set to. Wrong here means every sample lands somewhere else,
    // so it is a flag and not a default.
    stepS: Number(flag('--step')) || null,
    intervalChunk: flag('--interval-chunk'),
  };
}

// Bare codes to queue entries, for testing the loop on replays that are not
// league games. Every field the feed would supply is left null rather than
// invented - a made-up map name would travel downstream and be believed.
function synthesise(codes) {
  return codes.map((code, i) => ({
    code: code.toUpperCase(),
    match_id: 'adhoc',
    game_no: i + 1,
    map: null,
    map_guid: null,
    map_category: null,
    team_a: null,
    team_b: null,
    t1: null,
    t2: null,
    finished_at: new Date().toISOString(),
  }));
}

function attemptedKeys(state) {
  return Object.keys(state || {});
}

// Is this feed new enough to spend codes against?
//
// THE FEED GOES STALE AND STILL LOOKS FINE. A local data.json built before the
// last patch lists codes the client will refuse, and `code_wipe_date` is stale
// in exactly the same way, so the queue happily calls all 255 of them pending.
// Spending one-shot imports on a dead list is the worst outcome this tool has:
// every code is consumed, none captures, and no rerun is possible.
//
// CI rebuilds the feed, so "built today" is the cheap check that catches it.
function feedFreshness(feed, now) {
  var built = String((feed && feed.built_at) || '').slice(0, 10);
  var today = new Date(now).toISOString().slice(0, 10);
  return {
    built: built || '(none)',
    fresh: built === today,
    wipeDate: (feed && feed.code_wipe_date) || null,
  };
}

// ------------------------------------------------------------------- io ----

function readJson(p, fallback) {
  try { return JSON.parse(fs.readFileSync(p, 'utf8')); } catch (e) { return fallback; }
}

function writeJson(p, value) {
  fs.mkdirSync(path.dirname(p), { recursive: true });
  fs.writeFileSync(p, JSON.stringify(value, null, 2) + '\n', 'utf8');
}

const wait = (ms) => new Promise((r) => setTimeout(r, ms));

// Whether a replay is on screen, judged by the playhead being drawn. It is the
// one thing that is present in a replay and absent in the menus, and it is
// already read for seeking, so nothing new has to be calibrated for it.
async function inReplay(io) {
  try {
    const img = await io.loadImage(await io.grabTo('probe'));
    return !!Crop.playheadX(img, calib);
  } catch (e) {
    return false;
  }
}

async function waitFor(io, want, timeoutMs, label) {
  const until = Date.now() + timeoutMs;
  while (Date.now() < until) {
    if (await inReplay(io) === want) return true;
    await wait(POLL_MS);
  }
  throw new Error(`timed out after ${Math.round(timeoutMs / 1000)}s waiting for ${label}`);
}

// ----------------------------------------------------------------- main ----

async function main() {
  const args = parseArgs(process.argv.slice(2));
  const state = readJson(STATE, {});

  let queue;
  if (args.codes) {
    queue = synthesise(args.codes);
    console.log(`ad-hoc queue: ${queue.length} code${queue.length === 1 ? '' : 's'}`);
  } else {
    const feed = readJson(FEED, null);
    if (!feed) throw new Error('no feed at ' + FEED);

    const fresh = feedFreshness(feed, Date.now());
    console.log(`feed built ${fresh.built}, wipe ${fresh.wipeDate}`);
    if (!fresh.fresh && !args.staleOk) {
      throw new Error(`the feed was built ${fresh.built}, not today. Codes die at ` +
        'every patch and each one can only be imported once, so a stale feed ' +
        'spends the whole queue on codes that cannot work. Let CI rebuild it, ' +
        'or pass --stale-ok if you are certain.');
    }
    queue = Q.pending(feed.codes || [], {
      wipeDate: feed.code_wipe_date,
      done: attemptedKeys(state),
    });
    console.log(`feed has ${(feed.codes || []).length} codes, wipe ${feed.code_wipe_date}; ` +
      `${queue.length} pending after dropping wiped and already-attempted`);
  }

  if (args.limit) queue = queue.slice(0, args.limit);

  if (args.dry) {
    queue.forEach((c) => console.log(`  ${c.code}  ${c.match_id}:${c.game_no}  ` +
      `${c.map || '(unknown map)'}  ${c.finished_at}`));
    console.log(`\n--dry: nothing was opened. ${queue.length} would run.`);
    return;
  }
  if (!queue.length) { console.log('nothing to do'); return; }

  const io = C.makeIo({ framesDir: FRAMES, log: (m) => console.log(m) });
  const capture = C.make(io);

  // The time-skip interval is a per-SESSION thing, and both halves of handling
  // it matter.
  //
  // Setting it: a recorded chunk walks the replay's options and sets 60s, which
  // cuts a map's seek presses to a third. It runs once, inside the first
  // replay, because the setting then holds for the rest of the session.
  //
  // Trusting it: never. Replay viewer options are a known Blizzard bug - they
  // apply while the client runs and revert at the next start - so the first
  // map MEASURES what a press is actually worth by timing playback, and every
  // later map reuses that measured number rather than the setting's word.
  const intervalChunk = args.intervalChunk || 'set-interval';
  const haveIntervalChunk = fs.existsSync(R.chunkPath(intervalChunk));
  if (!haveIntervalChunk) {
    console.log(`no "${intervalChunk}" chunk recorded - running at whatever ` +
      'interval the client already has, which the first map will measure');
  }
  let sessionStepS = args.stepS || null;
  let first = true;
  const outPath = args.out ||
    path.join(OUT_DIR, `replay-bot-${new Date().toISOString().slice(0, 10)}.json`);
  const maps = readJson(outPath, { maps: [] }).maps || [];

  let consecutiveFailures = 0;

  for (const code of queue) {
    console.log(`\n=== ${code.code}  ${code.match_id}:${code.game_no}  ` +
      `${code.map || '(unknown map)'} ===`);

    // Keyed per GAME, matching queue.key: a match has several maps and each is
    // its own replay, so keying on match_id alone would skip every map after
    // the first.
    const key = `${code.match_id}:${code.game_no}`;

    // Written before the import, never after. A crash mid-map must not leave a
    // code looking untried, because trying it again cannot work.
    state[key] = {
      code: code.code,
      started_at: new Date().toISOString(),
      status: 'opened',
    };
    writeJson(STATE, state);
    try {
      const tOpen = Date.now();
      await R.play('open-import', { code: code.code });
      const tPlayed = Date.now();
      await waitFor(io, true, LOAD_TIMEOUT_MS, 'the replay to load');
      const tLoaded = Date.now();
      console.log(`import ${((tPlayed - tOpen) / 1000).toFixed(1)}s, ` +
        `client loaded the replay in ${((tLoaded - tPlayed) / 1000).toFixed(1)}s`);

      // The interval chunk runs INSIDE the capture, not before it: the options
      // button only exists once N and K have put the controls on screen, and
      // the interval must change before the step is measured.
      const setInterval = first && haveIntervalChunk ? async () => {
        console.log(`setting the skip interval (${intervalChunk}), once for this session`);
        await R.play(intervalChunk, {});
      } : null;

      // The first map measures the interval; the rest are told it, which saves
      // the eight seconds of timed playback per map.
      const got = await capture.captureMap({ stepS: sessionStepS, afterViewer: setInterval });
      if (!sessionStepS && got.stepS) {
        sessionStepS = got.stepS;
        console.log(`session step is ${sessionStepS}s - later maps will use it without re-timing`);
      }
      first = false;
      const record = E.mapRecord(code, C.observationsOf(got.samples), C.roundsOf(got.segments), {
        profile: { w: calib.FROZEN.frame.w, h: calib.FROZEN.frame.h, hud_variant: 'replay-bot' },
      });
      maps.push(record);

      // Written after every map, not at the end of the night. A run that dies
      // at map 90 must not lose 89 maps that can never be captured again.
      writeJson(outPath, E.file(maps, { contributor: CONTRIBUTOR }));

      console.log(`map took ${((Date.now() - tOpen) / 1000).toFixed(1)}s end to end`);
      state[key].status = got.missed.length ? 'captured-with-misses' : 'captured';
      state[key].samples = got.samples.length;
      state[key].missed = got.missed.length;
      writeJson(STATE, state);
      consecutiveFailures = 0;
      console.log(`captured ${got.samples.length} samples -> ${outPath}`);
    } catch (e) {
      consecutiveFailures++;
      state[key].status = 'failed';
      state[key].error = e.message;
      writeJson(STATE, state);
      console.log(`FAILED: ${e.message}`);
      if (consecutiveFailures >= 2) {
        console.log('two failures in a row - stopping rather than spending more codes ' +
          'against a client that is not where the chunks expect it');
        break;
      }
    }

    // Leave, whatever happened. If a replay is open this returns to the history
    // tab; if the client is already in the menus, playing the chunk would click
    // at coordinates that mean something else, so it is checked first.
    try {
      if (await inReplay(io)) {
        await R.play('leave-replay', {});
        await waitFor(io, false, EXIT_TIMEOUT_MS, 'the replay to close');
      }
    } catch (e) {
      console.log(`could not get back to the replay list: ${e.message}`);
      break;
    }
  }

  console.log(`\nrun finished. ${maps.length} map${maps.length === 1 ? '' : 's'} in ${outPath}`);
}

module.exports = { parseArgs, synthesise, attemptedKeys, feedFreshness };

// Only when run as a command. Requiring this file - which the tests do - must
// never start driving the client.
if (require.main === module) {
  main()
    .catch(function (e) { console.error('FAILED: ' + e.message); process.exitCode = 1; })
    // The PowerShell host holds a pipe, and a held pipe keeps Node alive after
    // the work is done.
    .then(function () { H.close(); });
}

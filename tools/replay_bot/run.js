// tools/replay_bot/run.js
// The unattended loop: queue, import, capture, leave, repeat.
//
//   node tools/replay_bot/run.js --dry              show the queue, touch nothing
//   node tools/replay_bot/run.js --limit 3          three maps from the feed
//   node tools/replay_bot/run.js --codes A1B2C3,... arbitrary codes, for testing
//   node tools/replay_bot/run.js --divisions "EMEA Master,EMEA Expert"
//   node tools/replay_bot/run.js --teams Wasp,Crabs --newest
//
// The league produces about 127 coded games a day across every region and tier,
// which is roughly nine hours of capture a week - hours the client cannot be
// used for anything else - against a patch cadence of about one week. The whole
// queue does not reliably fit before the wipe that kills it, so --divisions and
// --teams are how the client's time gets spent on the games worth having.
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
const S = require('./screen.js');
const I = require('./input.js');
const R = require('./recorder.js');
const Q = require('./queue.js');
const E = require('./emit.js');
const A = require('./attribute.js');
const Resolve = require('./resolve.js');
const RO = require('./review_out.js');
const calib = require('./calib.js');
const Crop = require('./crop.js');
const Tesseract = require('tesseract.js');

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
    divisions: flag('--divisions') ? flag('--divisions').split(',').map((d) => d.trim()).filter(Boolean) : null,
    teams: flag('--teams') ? flag('--teams').split(',').map((t) => t.trim()).filter(Boolean) : null,
    newestFirst: argv.includes('--newest'),
    // Skips the timed-playback measurement when the operator already knows what
    // the client is set to. Wrong here means every sample lands somewhere else,
    // so it is a flag and not a default.
    stepS: Number(flag('--step')) || null,
    intervalChunk: flag('--interval-chunk'),
    // Divides the waits inside every chunk. 1 is as recorded; probe_chunk.js
    // says what the client will actually keep up with.
    chunkSpeed: Number(flag('--chunk-speed')) || 1,
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

// How many planned sample times fell in each round, keyed by round_no. resolve.js
// compares this against how many actually landed to flag a mostly-missed round.
function countPlanned(plan, rounds) {
  var out = {};
  (rounds || []).forEach(function (r, i) {
    out[i + 1] = (plan || []).filter(function (t) {
      return t >= r.from_t && t <= r.to_t;
    }).length;
  });
  return out;
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

// Whether a replay is on screen, judged by the two team plates being tinted.
//
// NOT THE PLAYHEAD, which is what this used and why a run once did nothing at
// all: the media controls are HIDDEN when a replay opens, so there is no
// scrubber to find. The bot waited ninety seconds for one inside a replay that
// was already playing, gave up, and then ran the import chunk from inside that
// replay - clicking at coordinates that mean something else there.
//
// The plates are drawn whether the controls are up or not.
async function inReplay(io) {
  try {
    const img = await io.loadImage(await io.grabTo('probe'));
    return calib.hudPresent(Crop.hudTint(img, calib));
  } catch (e) {
    return false;
  }
}

// Whether the client is sitting in the ESC menu.
//
// Menus can be recognised as pictures; replays cannot. Two frames of the ESC
// menu differ by 3.4, and it differs from a replay by 82 - but two frames of a
// REPLAY differ from each other by 55, because the game behind the HUD is a
// different scene entirely. So this trick works here and nowhere else.
async function onScreen(io, name) {
  try {
    const known = readJson(path.join(__dirname, 'screens', name + '.json'), null);
    if (!known) return false;
    const img = await io.loadImage(await io.grabTo('probe'));
    return S.looksLike(S.thumb(img), known.thumb).same;
  } catch (e) {
    return false;
  }
}

const escMenuUp = (io) => onScreen(io, 'esc-menu');

// Whether the client is sitting on the career-profile REPLAYS list.
//
// THE IMPORT CHUNK NAVIGATES FROM WHEREVER IT IS, so starting a run already on
// this screen puts its first clicks somewhere else entirely. That is how 7V4END
// was lost: the code never imported, the bot waited its ninety seconds for a
// replay that was never opening, and every code after it worked because leaving
// the first map normalises the state. Only the FIRST code of a run is exposed,
// which is exactly the kind of fault that hides.
//
// The list's contents change as replays are imported and evicted, and that does
// not matter: across ninety seconds of probes the fingerprint moved between 0.6
// and 5.3 against a threshold of 18, while a replay sits at 100 and the ESC
// menu at 121.
const replayHistoryUp = (io) => onScreen(io, 'replay-history');

async function waitFor(io, want, timeoutMs, label) {
  const until = Date.now() + timeoutMs;
  while (Date.now() < until) {
    if (await inReplay(io) === want) return true;
    await wait(POLL_MS);
  }
  throw new Error(`timed out after ${Math.round(timeoutMs / 1000)}s waiting for ${label}`);
}

// Module-scoped so the top-level .then() below can terminate it on any exit
// path, success or failure - the same reason H.close() lives out there
// rather than inside main(). An unterminated worker holds Node open exactly
// as an unclosed PowerShell pipe does.
let ocrWorker = null;

// ----------------------------------------------------------------- main ----

async function main() {
  const args = parseArgs(process.argv.slice(2));
  const state = readJson(STATE, {});

  // Attribution wants the feed's lineups/hero_roles even on an ad-hoc run, so
  // it is read once here rather than staying scoped to the queue-building
  // branch below. An ad-hoc code has no lineup entry regardless (synthesise()
  // invents match_id 'adhoc'), so attribute.js just abstains every slot for
  // those - {} is a safe default, not a fallback that hides a real feed.
  let feed = {};

  let queue;
  if (args.codes) {
    queue = synthesise(args.codes);
    console.log(`ad-hoc queue: ${queue.length} code${queue.length === 1 ? '' : 's'}`);
  } else {
    feed = readJson(FEED, null);
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
      divisions: args.divisions,
      teams: args.teams,
      newestFirst: args.newestFirst,
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

  // One worker for the whole run, not one per map - tesseract's own startup
  // is the expensive part, and attribution only runs once per map anyway
  // (specs/2026-09-10-replay-bot-player-attribution-design.md §2).
  ocrWorker = await Tesseract.createWorker('eng');
  await ocrWorker.setParameters({
    tessedit_char_whitelist:
      'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789',
  });
  const attributor = A.make(async (cv) => {
    const { data } = await ocrWorker.recognize(cv.toBuffer('image/png'));
    return data.text.trim();
  });

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

  // The review artifact sits beside the contribution: same basename, .review.json,
  // with its crops under out/<session>/. The contribution is what uploads; this
  // is what the operator opens first (specs/2026-09-10-replay-bot-autonomous-scouting-design.md).
  const session = path.basename(outPath).replace(/\.json$/, '');
  const reviewPath = path.join(path.dirname(outPath), `${session}.review.json`);
  const sessionDir = path.join(path.dirname(outPath), session);
  const reviewMaps = readJson(reviewPath, { maps: [] }).maps || [];

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
      // The ESC menu is the other place the client gets stuck: a leave-replay
      // whose click misses leaves it up, and the import chunk then clicks
      // SOCIAL and CAREER PROFILE instead of the replay list. It is a static
      // screen, so it can be recognised outright.
      if (await escMenuUp(io)) {
        console.log('the ESC menu is up - clearing it before importing');
        await I.sendKeys(['ESC']);
        await wait(1200);
        if (await escMenuUp(io)) {
          throw new Error('the ESC menu will not close - the client is not where ' +
            'the chunks expect it');
        }
      }

      // The replay list is the other screen the import chunk cannot start from.
      // Backed out of rather than clicked through, and refused loudly if it
      // will not go - a chunk played from the wrong screen spends the code and
      // reports nothing useful.
      for (let back = 0; await replayHistoryUp(io); back++) {
        if (back >= 2) {
          throw new Error('the client is stuck on the replay list - the import ' +
            'chunk navigates from somewhere else, so playing it here would ' +
            'click blind and spend the code for nothing');
        }
        console.log('the replay list is up - backing out before importing');
        await I.sendKeys(['ESC']);
        await wait(1200);
      }

      // The import chunk clicks the replay history tab. Playing it while a
      // replay is still open puts those clicks somewhere else entirely, which
      // is how one failed map turned into a run that spent two more codes
      // achieving nothing.
      if (await inReplay(io)) {
        console.log('still inside a replay - leaving before importing');
        await R.play('leave-replay', { speed: args.chunkSpeed });
        await waitFor(io, false, EXIT_TIMEOUT_MS, 'the replay to close');
      }

      const tOpen = Date.now();
      await R.play('open-import', { code: code.code, speed: args.chunkSpeed });
      const tPlayed = Date.now();
      await waitFor(io, true, LOAD_TIMEOUT_MS, 'the replay to load');
      const tLoaded = Date.now();
      console.log(`import ${((tPlayed - tOpen) / 1000).toFixed(1)}s, ` +
        `client loaded the replay in ${((tLoaded - tPlayed) / 1000).toFixed(1)}s`);

      // waitFor returns the moment the team plates are drawn, which is NOT the
      // same as the client being ready for control input - the two live
      // "K did not open the panel" failures (2026-09-10) both hit this window,
      // where the replay has rendered but N/K do not land as expected yet.
      // A short beat here before the capture starts poking it. If the next
      // failure logs (capture.js's events-viewer diagnostics) show this
      // helped, or did not, tune or drop it then.
      await wait(500);

      // The interval chunk runs INSIDE the capture, not before it: the options
      // button only exists once N and K have put the controls on screen, and
      // the interval must change before the step is measured.
      const setInterval = first && haveIntervalChunk ? async () => {
        console.log(`setting the skip interval (${intervalChunk}), once for this session`);
        await R.play(intervalChunk, { speed: args.chunkSpeed });
      } : null;

      // The first map measures the interval; the rest are told it, which saves
      // the eight seconds of timed playback per map.
      const got = await capture.captureMap({ stepS: sessionStepS, afterViewer: setInterval });
      if (!sessionStepS && got.stepS) {
        sessionStepS = got.stepS;
        console.log(`session step is ${sessionStepS}s - later maps will use it without re-timing`);
      }
      first = false;

      // Resolved once per map, off the frame the first sample already read -
      // never per sample (specs/2026-09-10-replay-bot-player-attribution-design.md
      // §2). Attribution is additive: a captured map with hero comps but no
      // names is still real scouting value, and this is a one-shot code, so a
      // failure here degrades to no attribution rather than failing the map
      // (§6 of that design) - unlike everything else in this loop, which
      // refuses loudly.
      let attribution = null;
      if (got.samples.length) {
        try {
          const firstSample = got.samples[0];
          const frame = await io.loadImage(firstSample.framePath);
          attribution = await attributor.attributeMap(
            frame, { a: firstSample.a, b: firstSample.b }, feed, code);
        } catch (e) {
          console.log(`attribution failed, map keeps its hero reads without ` +
            `player names: ${e.message}`);
        }
      }

      const rounds = C.roundsOf(got.segments);
      const record = E.mapRecord(code, C.observationsOf(got.samples), rounds, {
        profile: { w: calib.FROZEN.frame.w, h: calib.FROZEN.frame.h, hud_variant: 'replay-bot' },
        attribution: attribution,
      });
      maps.push(record);

      // Written after every map, not at the end of the night. A run that dies
      // at map 90 must not lose 89 maps that can never be captured again.
      writeJson(outPath, E.file(maps, { contributor: CONTRIBUTOR }));

      // The review artifact, alongside. resolve.js votes each slot across the
      // round's frames and flags what to look at; review_out.js writes the
      // per-round portrait crops the review page shows. This does not touch the
      // contribution above - that stays per-sample until the review page's
      // finalize step rebuilds it from confirmed rounds.
      try {
        const resolved = Resolve.rounds(got.samples, rounds, {
          heroRoles: feed.hero_roles || {},
          attribution: attribution,
          planned: countPlanned(got.plan, rounds),
        });
        const reviewEntry = await RO.mapEntry(io, sessionDir, code, resolved, attribution, got, calib, feed);
        reviewMaps.push(reviewEntry);
        RO.writeSession(reviewPath, reviewMaps, { session, feedBuilt: feed.built_at });
        const flagged = resolved.reduce((n, r) => n + r.flags.length +
          r.a.concat(r.b).reduce((m, s) => m + s.flags.length, 0), 0);
        console.log(`review: ${resolved.length} round(s), ${flagged} flag(s) -> ${reviewPath}`);
      } catch (e) {
        console.log(`review artifact not written for this map: ${e.message}`);
      }

      console.log(`map took ${((Date.now() - tOpen) / 1000).toFixed(1)}s end to end`);
      state[key].status = got.missed.length ? 'captured-with-misses' : 'captured';
      state[key].samples = got.samples.length;
      state[key].missed = got.missed.length;
      writeJson(STATE, state);
      consecutiveFailures = 0;
      console.log(`captured ${got.samples.length} samples -> ${outPath}`);

      // The map succeeded, so the scratch frames it took along the way - a
      // settle, a pause check, every quiesce - are done being useful. The
      // samples that mattered are already copied out under keepAs.
      if (io.sweepTransient) io.sweepTransient();
    } catch (e) {
      consecutiveFailures++;
      state[key].status = 'failed';
      state[key].error = e.message;
      writeJson(STATE, state);
      console.log(`FAILED: ${e.message}`);

      // A failed map is the one time the scratch frames matter: only a broken
      // grab is unrecoverable, and finding out which requires looking at what
      // was actually on screen. forgetTransient keeps a bounded handful for
      // that rather than everything, and clears the tracker either way so the
      // next map's success does not sweep up what it kept.
      if (io.forgetTransient) await io.forgetTransient();

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
        await R.play('leave-replay', { speed: args.chunkSpeed });
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
    // the work is done. The OCR worker is the same shape of problem.
    .then(function () { H.close(); return ocrWorker ? ocrWorker.terminate() : null; });
}

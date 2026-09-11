// tools/replay_bot/run.js
// The unattended loop: queue, import, capture, leave, repeat.
//
//   node tools/replay_bot/run.js --dry              show the queue, touch nothing
//   node tools/replay_bot/run.js --limit 3          three maps from the feed
//   node tools/replay_bot/run.js --codes A1B2C3,... arbitrary codes, for testing
//   node tools/replay_bot/run.js --divisions "EMEA Master,EMEA Expert"
//   node tools/replay_bot/run.js --teams Wasp,Crabs --newest
//   node tools/replay_bot/run.js --codes A1B2C3 --no-drag   seek by key, not drag
//   node tools/replay_bot/run.js --code-stack state/console_codes.json
//                                            cycle a codestack.js file forever
//                                            instead of a finite queue - what
//                                            the console (§14.3b) drives to
//                                            simulate an overnight run
//
// PAUSING. Between maps (never mid-map - a map in progress always finishes)
// this checks for state/loop_pause.flag and, if present, waits for it to go
// away before starting the next one. console/hotkey.ps1 toggles that file from
// a global hotkey so the game can stay focused; the console's Pause/Resume
// buttons do the same thing. TIMING is reloaded at the same checkpoint, so a
// slider changed while paused applies to the next map without restarting this
// process. Ctrl-C is the same checkpoint: the first press finishes the current
// map then exits; a second forces an immediate exit.
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
const I = require('./input.js');
const CS = require('./clientstate.js');
const CodeStack = require('./codestack.js');
const R = require('./recorder.js');
const Q = require('./queue.js');
const E = require('./emit.js');
const A = require('./attribute.js');
const Resolve = require('./resolve.js');
const RO = require('./review_out.js');
const calib = require('./calib.js');
const TIMING = require('./timing.js');
const Tesseract = require('tesseract.js');

const FRAMES = path.join(__dirname, 'frames');
const STATE = path.join(__dirname, 'state', 'attempts.json');
const OUT_DIR = path.join(__dirname, 'out');
const FEED = path.join(__dirname, '../../docs/capture/data.json');

const CONTRIBUTOR = 'replay-bot';
// The waits this loop spends live in timing.js: TIMING.load.timeoutMs (waiting
// for an imported replay to draw), TIMING.exit.timeoutMs (for one to close),
// TIMING.poll.ms (the screen-state poll cadence - a grab already costs ~0.5s,
// so 1s is a real poll not a busy loop), TIMING.esc.tries (ESC at a stuck menu:
// one press is dropped if it lands mid-transition, the same as a seek key, and
// one run in ten hit this on 2026-09-10). The --load-settle / --esc-wait /
// --chunk-speed / --sample-quiesce flags still override per run.

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
    // A codestack.js file to cycle forever instead of a finite queue - see the
    // file header. Mutually pointless with --codes/--divisions/--teams, which
    // this does not check for; whichever branch main() takes wins.
    codeStack: flag('--code-stack'),
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
    // Divides the waits inside every chunk. A 2026-09-10 sweep ran the loop at
    // 1x / 1.5x / 2x / 2.5x clean and BROKE at 3x - open-import's click on the
    // VIEW button landed before the button had drawn, so the replay imported
    // but never opened and the run timed out. 2x is the fast default that
    // held; --chunk-speed pins it (down to 1 for a slow client, and no higher
    // than 2.5 until open-import waits for the button rather than timing the
    // click). Left null (not given), main() reads TIMING.chunk.speed AT EACH
    // MAP rather than once here - console_timing.json edited mid-run then
    // applies to the next map without a restart.
    chunkSpeed: flag('--chunk-speed') != null ? Number(flag('--chunk-speed')) : null,
    // Timing overrides, for sweeping the pipeline to find the fastest that
    // still reads clean. null leaves each at its measured default, re-read from
    // TIMING at every map for the same reason as chunkSpeed above.
    //   --sample-quiesce  ms after a seek settles, before the HUD is read
    //   --load-settle     ms after the replay loads, before capture starts
    //   --esc-wait        ms after an ESC press, before re-checking the screen
    sampleQuiesce: flag('--sample-quiesce') != null ? Number(flag('--sample-quiesce')) : null,
    loadSettle: flag('--load-settle') != null ? Number(flag('--load-settle')) : null,
    escWait: flag('--esc-wait') != null ? Number(flag('--esc-wait')) : null,
    // Seeks drag the scrubber by default; --no-drag forces the old counted key
    // presses, for an A/B against the drag or as an escape hatch if a client
    // update breaks it.
    noDrag: argv.includes('--no-drag'),
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

// Reading where the client is - inReplay / escMenuUp / replayHistoryUp - and
// clearEscMenu / waitFor all live in clientstate.js now, so the console can ask
// the same questions this loop asks between maps.

// Module-scoped so the top-level .then() below can terminate it on any exit
// path, success or failure - the same reason H.close() lives out there
// rather than inside main(). An unterminated worker holds Node open exactly
// as an unclosed PowerShell pipe does.
let ocrWorker = null;

// ----------------------------------------------------------------- main ----

async function main() {
  const args = parseArgs(process.argv.slice(2));
  const state = readJson(STATE, {});

  // Re-read at every map boundary rather than captured once, so a value edited
  // in state/console_timing.json while the loop is paused (console Save, or
  // hand-editing the file) applies to the next map without a restart - see the
  // file header. An explicit CLI flag still pins one value for the whole run.
  const chunkSpeed = () => args.chunkSpeed != null ? args.chunkSpeed : TIMING.chunk.speed;
  const escWaitMs = () => args.escWait != null ? args.escWait : TIMING.esc.waitMs;
  const loadSettleMs = () => args.loadSettle != null ? args.loadSettle : TIMING.load.settleMs;
  if (args.sampleQuiesce != null || args.loadSettle != null || args.escWait != null ||
      args.chunkSpeed != null || args.noDrag) {
    console.log(`timing: chunk-speed ${chunkSpeed()}, sample-quiesce ` +
      `${args.sampleQuiesce != null ? args.sampleQuiesce : 'default'}, load-settle ` +
      `${loadSettleMs()}, esc-wait ${escWaitMs()}, seek ${args.noDrag ? 'keys' : 'drag'}`);
  }

  // Attribution wants the feed's lineups/hero_roles even on an ad-hoc run, so
  // it is read once here rather than staying scoped to the queue-building
  // branch below. An ad-hoc code has no lineup entry regardless (synthesise()
  // invents match_id 'adhoc'), so attribute.js just abstains every slot for
  // those - {} is a safe default, not a fallback that hides a real feed.
  let feed = {};

  // --code-stack cycles a codestack.js file forever rather than working a
  // finite queue once - "leave it on overnight" without a real league code
  // going in. It never touches the attempt ledger: those codes are meant to be
  // re-imported, and the ledger's whole point is "never again".
  const looping = !!args.codeStack;
  let queue = [];

  if (looping) {
    const preview = CodeStack.load(args.codeStack);
    console.log(`code-stack: ${preview.length} code${preview.length === 1 ? '' : 's'} ` +
      `(${preview.join(', ') || 'empty'}) - cycling until stopped`);
  } else if (args.codes) {
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

  if (args.limit && !looping) queue = queue.slice(0, args.limit);

  if (args.dry) {
    if (looping) {
      console.log(`\n--dry: nothing was opened. Would cycle the stack above until stopped.`);
      return;
    }
    queue.forEach((c) => console.log(`  ${c.code}  ${c.match_id}:${c.game_no}  ` +
      `${c.map || '(unknown map)'}  ${c.finished_at}`));
    console.log(`\n--dry: nothing was opened. ${queue.length} would run.`);
    return;
  }
  if (!looping && !queue.length) { console.log('nothing to do'); return; }

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

  // The next-map checkpoint, both for a pause and for a graceful stop. Never
  // mid-map: a map in progress always finishes, so the client is never left
  // wherever a seek or a menu happened to be.
  const PAUSE_FLAG = path.join(__dirname, 'state', 'loop_pause.flag');
  let stopRequested = false;
  let sigints = 0;
  process.on('SIGINT', () => {
    sigints += 1;
    if (sigints === 1) {
      stopRequested = true;
      console.log('\nstopping after this map (Ctrl-C again to force)');
    } else {
      console.log('forcing exit');
      process.exit(130);
    }
  });

  async function checkpoint() {
    if (fs.existsSync(PAUSE_FLAG)) {
      console.log('paused - waiting for state/loop_pause.flag to clear ' +
        '(console Resume, or the hotkey)');
      while (!stopRequested && fs.existsSync(PAUSE_FLAG)) await wait(TIMING.poll.ms);
      if (!stopRequested) console.log('resumed');
    }
    // A slider edited while paused (or between any two maps) takes effect from
    // here - see the file header on why this is re-read rather than captured.
    TIMING.reload();
  }

  let consecutiveFailures = 0;
  let queueIndex = 0;
  let mapsRun = 0;

  while (true) {
    if (stopRequested) break;
    await checkpoint();
    if (stopRequested) break;
    if (looping && args.limit && mapsRun >= args.limit) {
      console.log(`limit of ${args.limit} map(s) reached`);
      break;
    }

    let code;
    if (looping) {
      const pulled = CodeStack.rotate(args.codeStack);
      if (!pulled) { console.log('the code stack is empty - stopping'); break; }
      code = synthesise([pulled])[0];
    } else {
      if (queueIndex >= queue.length) break;
      code = queue[queueIndex++];
    }
    mapsRun += 1;

    console.log(`\n=== ${code.code}  ${code.match_id}:${code.game_no}  ` +
      `${code.map || '(unknown map)'} ===`);

    // Keyed per GAME, matching queue.key: a match has several maps and each is
    // its own replay, so keying on match_id alone would skip every map after
    // the first. Skipped entirely when looping - a code-stack code is meant to
    // be imported again, and the attempt ledger's whole point is "never again".
    const key = `${code.match_id}:${code.game_no}`;

    if (!looping) {
      // Written before the import, never after. A crash mid-map must not leave
      // a code looking untried, because trying it again cannot work.
      state[key] = {
        code: code.code,
        started_at: new Date().toISOString(),
        status: 'opened',
      };
      writeJson(STATE, state);
    }
    try {
      // The ESC menu is the other place the client gets stuck: a leave-replay
      // whose click misses leaves it up, and the import chunk then clicks
      // SOCIAL and CAREER PROFILE instead of the replay list. It is a static
      // screen, so it can be recognised outright.
      await CS.clearEscMenu(io, {
        sendKeys: I.sendKeys, wait, escWait: escWaitMs(),
        tries: TIMING.esc.tries, tag: code.code, log: (m) => console.log(m),
      });

      // The replay list is the other screen the import chunk cannot start from.
      // Backed out of rather than clicked through, and refused loudly if it
      // will not go - a chunk played from the wrong screen spends the code and
      // reports nothing useful.
      for (let back = 0; await CS.replayHistoryUp(io); back++) {
        if (back >= 2) {
          throw new Error('the client is stuck on the replay list - the import ' +
            'chunk navigates from somewhere else, so playing it here would ' +
            'click blind and spend the code for nothing');
        }
        console.log('the replay list is up - backing out before importing');
        await I.sendKeys(["ESC"]);
        await wait(escWaitMs());
      }

      // The import chunk clicks the replay history tab. Playing it while a
      // replay is still open puts those clicks somewhere else entirely, which
      // is how one failed map turned into a run that spent two more codes
      // achieving nothing.
      if (await CS.inReplay(io)) {
        console.log('still inside a replay - leaving before importing');
        await R.play('leave-replay', { speed: chunkSpeed() });
        await CS.waitFor(io, false, TIMING.exit.timeoutMs, 'the replay to close');
      }

      const tOpen = Date.now();
      await R.play('open-import', { code: code.code, speed: chunkSpeed() });
      const tPlayed = Date.now();
      await CS.waitFor(io, true, TIMING.load.timeoutMs, 'the replay to load');
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
      await wait(loadSettleMs());

      // The interval chunk runs INSIDE the capture, not before it: the options
      // button only exists once N and K have put the controls on screen, and
      // the interval must change before the step is measured.
      const setInterval = first && haveIntervalChunk ? async () => {
        console.log(`setting the skip interval (${intervalChunk}), once for this session`);
        await R.play(intervalChunk, { speed: chunkSpeed() });
      } : null;

      // The first map measures the interval; the rest are told it, which saves
      // the eight seconds of timed playback per map.
      const got = await capture.captureMap({
        stepS: sessionStepS, afterViewer: setInterval,
        sampleQuiesceMs: args.sampleQuiesce,
        noDrag: args.noDrag,
      });
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

      // The replay viewer does not always put the feed's "team A" on the left,
      // and heroes_a is whatever is on the left. When attribution's name read
      // says the teams are the other way round, relabel so side_a carries the
      // team that is actually on the left - otherwise every comp on the map is
      // filed under the opponent. `null` orientation (read not clean enough to
      // be sure) keeps the feed's order and the review page flags it.
      const oriented = (attribution && attribution.orientation === 'swapped')
        ? Object.assign({}, code, {
            t1: code.t2, t2: code.t1, team_a: code.team_b, team_b: code.team_a })
        : code;
      if (attribution && attribution.orientation === 'swapped') {
        console.log(`sides: the replay shows ${code.team_b} on the left, not ${code.team_a} - relabelled`);
      } else if (attribution && attribution.orientation === null) {
        console.log('sides: name read was not decisive - kept feed order, review will flag it');
      }

      const rounds = C.roundsOf(got.segments);
      const record = E.mapRecord(oriented, C.observationsOf(got.samples), rounds, {
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
        const reviewEntry = await RO.mapEntry(io, sessionDir, oriented, resolved, attribution, got, calib, feed);
        reviewEntry.orientation = attribution ? attribution.orientation : null;
        reviewMaps.push(reviewEntry);
        RO.writeSession(reviewPath, reviewMaps, { session, feedBuilt: feed.built_at });
        const flagged = resolved.reduce((n, r) => n + r.flags.length +
          r.a.concat(r.b).reduce((m, s) => m + s.flags.length, 0), 0);
        console.log(`review: ${resolved.length} round(s), ${flagged} flag(s) -> ${reviewPath}`);
      } catch (e) {
        console.log(`review artifact not written for this map: ${e.message}`);
      }

      console.log(`map took ${((Date.now() - tOpen) / 1000).toFixed(1)}s end to end`);
      if (!looping) {
        state[key].status = got.missed.length ? 'captured-with-misses' : 'captured';
        state[key].samples = got.samples.length;
        state[key].missed = got.missed.length;
        writeJson(STATE, state);
      }
      consecutiveFailures = 0;
      console.log(`captured ${got.samples.length} samples -> ${outPath}`);

      // The map succeeded, so the scratch frames it took along the way - a
      // settle, a pause check, every quiesce - are done being useful. The
      // samples that mattered are already copied out under keepAs.
      if (io.sweepTransient) io.sweepTransient();
    } catch (e) {
      consecutiveFailures++;
      if (!looping) {
        state[key].status = 'failed';
        state[key].error = e.message;
        writeJson(STATE, state);
      }
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
      if (await CS.inReplay(io)) {
        await R.play('leave-replay', { speed: chunkSpeed() });
        await CS.waitFor(io, false, TIMING.exit.timeoutMs, 'the replay to close');
      }
    } catch (e) {
      console.log(`could not get back to the replay list: ${e.message}`);
      break;
    }
  }

  console.log(`\nrun finished. ${maps.length} map${maps.length === 1 ? '' : 's'} in ${outPath}` +
    (looping ? ` (${mapsRun} cycled)` : '') + (stopRequested ? ' - stopped' : ''));
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

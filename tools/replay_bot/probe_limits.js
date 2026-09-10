// tools/replay_bot/probe_limits.js
// How fast will the client actually go? Push each timing until it breaks, then
// back off - rather than picking a number that feels safe.
//
//   node tools/replay_bot/probe_limits.js            everything
//   node tools/replay_bot/probe_limits.js --gap      just the seek cadence
//   node tools/replay_bot/probe_limits.js --quiesce  just the read delay
//   node tools/replay_bot/probe_limits.js --gap --trials=5
//   node tools/replay_bot/probe_limits.js --quiesce --delays=0,125,250,375,500
//
// A REPLAY MUST BE OPEN AND PAUSED. Nothing here imports anything, so it costs
// no codes and can be run as often as you like.
//
// IT TAKES FOCUS for a couple of minutes.
//
// Every number the bot waits on started as a guess, and two of those guesses
// have already been wrong in ways that produced confident nonsense: a 45ms key
// gap that landed one press in five, and a settle that never converged because
// the replay was playing. So the defaults are worth measuring rather than
// defending, and this is what measures them.

const path = require('path');
const { loadImage } = require('@napi-rs/canvas');
const G = require('./grab.js');
const H = require('./host.js');
const I = require('./input.js');
const D = require('./driver.js');
const calib = require('./calib.js');
const Crop = require('./crop.js');
const Match = require('./match.js');
const REFS = require(path.join(__dirname, '../../docs/capture/refs.json'));

const FRAMES = path.join(__dirname, 'frames');
const wait = (ms) => new Promise((r) => setTimeout(r, ms));

let n = 0;
async function frame(tag) {
  const p = path.join(FRAMES, `probe-lim-${tag}-${n++}.png`);
  const r = await G.capture(p);
  if (!r.ok) throw new Error('grab failed: ' + r.reason);
  return p;
}

async function knob(tag) {
  const k = Crop.playheadX(await loadImage(await frame(tag)), calib);
  if (!k) throw new Error('no playhead - is a replay open with its controls up?');
  return k.centre;
}

// The least confident of the ten cells, which is what a half-drawn HUD shows up
// as. A frame read too early scores badly; a frame read late scores the same as
// one read later still.
function worst(read) {
  return Math.min.apply(null, ['a', 'b'].map(
    (side) => Math.min.apply(null, read[side].map((r) => r.score))));
}

async function readHud(M, framePath) {
  const img = await loadImage(framePath);
  const crops = Crop.all(img, calib);
  const out = {};
  ['a', 'b'].forEach((side) => { out[side] = crops[side].map((c) => M.match(c, side)); });
  return out;
}

// --- how close together can seek keys be sent? ------------------------------
//
// The client ignores a seek key that arrives while it is still seeking, and the
// loss is silent.
//
// THIS IS NOT A THRESHOLD, AND THE FIRST VERSION OF THIS FUNCTION ASSUMED IT
// WAS. Bisecting for a cliff, twice, gave two different answers with equal
// confidence: 550ms dropped a press in one run and landed all five in the next;
// 375ms landed 2 of 5, then 4 of 5. Acceptance is a race against however long
// that particular seek takes, so one clean pass says almost nothing.
//
// So each candidate is tried several times and what comes back is a rate. A gap
// worth using is one that has never once dropped a press, with a level of
// margin under it - not the lowest number that happened to work.
async function gapLimit(stepPx, presses, levels, trials) {
  async function landed(gapMs) {
    await I.sendKeys([D.KEY.jumpToStart]);
    await wait(1200);
    const from = await knob('g');
    await I.sendKeys(new Array(presses).fill(D.KEY.forward), { gapMs });
    await wait(1400);
    const to = await knob('g');
    return (to - from) / stepPx;
  }

  console.log('');
  console.log(`seek gap: ${trials} trials at each of ${levels.join('/')}ms, ` +
    `${presses} presses a trial`);

  const rows = [];
  for (const gapMs of levels) {
    const got = [];
    for (let i = 0; i < trials; i++) got.push(await landed(gapMs));
    const clean = got.filter((v) => v >= presses - 0.2).length;
    rows.push({ gapMs, clean, trials, got });
    console.log(`  ${String(gapMs).padStart(4)}ms  ${clean}/${trials} clean   ` +
      got.map((v) => v.toFixed(2)).join('  '));
  }

  const perfect = rows.filter((r) => r.clean === r.trials).map((r) => r.gapMs);
  const failed = rows.filter((r) => r.clean < r.trials).map((r) => r.gapMs);
  const worstFailure = failed.length ? Math.max.apply(null, failed) : null;

  console.log('');
  if (worstFailure !== null) {
    console.log(`  a press was dropped at ${worstFailure}ms, so anything at or below ` +
      'that is out regardless of how often it worked');
  }
  const safe = perfect.filter((g) => worstFailure === null || g > worstFailure);
  const recommend = safe.length ? Math.min.apply(null, safe) : Math.max.apply(null, levels);
  console.log(`  clean at ${perfect.join('/') || 'nothing'} -> use ${recommend}ms ` +
    `(currently ${I.SEEK_GAP_MS}ms)`);
  console.log('  run it again before changing anything: two runs disagreeing is the ' +
    'normal outcome here, and one run is one sample.');
  return { rows, recommend };
}

// --- how long after a seek is the HUD worth reading? ------------------------
//
// The bot waits QUIESCE_MS before grabbing. That wait was a guess, and it may
// be entirely free: a grab is a PowerShell spawn plus a PrintWindow, about half
// a second of its own, so by the time the frame is taken the HUD may already
// have finished moving. If reading immediately scores the same as reading after
// a pause, the pause is dead time.
async function quiesceNeed(M, delays) {
  console.log('\nread delay: does waiting before the grab change what is read?');
  const rows = [];

  for (const delay of delays) {
    await I.sendKeys([D.KEY.forward]);
    if (delay) await wait(delay);
    const early = worst(await readHud(M, await frame('q' + delay)));

    // The same position, read again well after everything has stopped, is the
    // control: if the early read matches it, nothing was gained by waiting.
    await wait(1200);
    const late = worst(await readHud(M, await frame('q' + delay + 'late')));

    rows.push({ delay, early, late });
    console.log(`  +${String(delay).padStart(4)}ms  worst cell ${early.toFixed(2)}` +
      `   settled ${late.toFixed(2)}   ${early >= late - 0.02 ? 'same' : 'WORSE'}`);
  }

  const clean = rows.filter((r) => r.early >= r.late - 0.02);
  if (clean.length) {
    console.log(`  reading at +${clean[0].delay}ms is as good as waiting -> ` +
      `SAMPLE_QUIESCE_MS could be ${clean[0].delay} (currently 500)`);
  } else {
    console.log('  every early read scored worse - the wait is doing real work, keep it');
  }
  return rows;
}

(async () => {
  const only = process.argv.slice(2);
  const all = !only.length || only.includes('--all');
  const M = Match.make(REFS, { PAD: calib.FROZEN.ref.PAD });

  // The bar's scale on this map, so a press can be counted in pixels.
  await I.sendKeys([D.KEY.jumpToStart]);
  await wait(1200);
  const zero = await knob('cal');
  await I.sendKeys([D.KEY.forward], { gapMs: 900 });
  await wait(1200);
  const one = await knob('cal');
  const stepPx = one - zero;
  if (stepPx <= 0) throw new Error(`one press moved ${stepPx}px - is the replay paused?`);
  console.log(`one step = ${stepPx.toFixed(1)}px`);

  const trials = Number((only.find((a) => a.startsWith('--trials=')) || '').split('=')[1]) || 3;
  if (all || only.includes('--gap')) {
    await gapLimit(stepPx, 5, [700, 600, 550, 500, 450], trials);
  }

  if (all || only.includes('--quiesce')) {
    // Somewhere into the map, so there are portraits to read at all.
    await I.sendKeys([D.KEY.jumpToStart]);
    await wait(1000);
    await I.sendKeys([D.KEY.forward, D.KEY.forward, D.KEY.forward]);
    await wait(1500);
    // Brackets the live SAMPLE_QUIESCE_MS (500). Override with --delays=a,b,c.
    var dArg = (only.find((a) => a.startsWith('--delays=')) || '').split('=')[1];
    var delays = dArg ? dArg.split(',').map(Number).filter((n) => !Number.isNaN(n))
      : [0, 125, 250, 375, 500];
    await quiesceNeed(M, delays);
  }

  console.log('\nNothing here changes any setting. Feed the numbers back and the ' +
    'defaults get moved deliberately, with the measurement recorded beside them.');
})()
  .catch((e) => { console.error('FAILED: ' + e.message); process.exitCode = 1; })
  .then(() => H.close());

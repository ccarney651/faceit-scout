// tools/replay_bot/probe_seek.js
// How many of the keys a seek sends does the client actually act on?
//
//   node tools/replay_bot/probe_seek.js [presses] [gapMs,gapMs,...]
//   node tools/replay_bot/probe_seek.js 5 45,150,300,600,1000
//
// IT TAKES FOCUS, like everything that sends keys. A replay must already be
// open; nothing here opens one.
//
// WHY THIS EXISTS. The first live run sampled six points it believed were
// spread over fourteen minutes. Every one read the same ten heroes, which is
// possible on Control and was taken for plausible. It was not: the playhead in
// the six retained frames had moved 45px between consecutive samples - one
// 20-second step - no matter whether the driver had sent eight presses, nine
// or ten. The whole run happened inside the first two minutes of the map.
//
// So a batch of n presses does NOT move n steps, and the count of presses that
// does land is the number this probe measures. The likely mechanism is that the
// viewer ignores input while it is seeking, which makes the answer a function
// of the gap between presses - so the gap is what is swept here.
//
// Everything is measured against the playhead rather than against what was
// asked for, because "the keys were sent" and "the replay moved" turned out to
// be different facts.

const path = require('path');
const { loadImage } = require('@napi-rs/canvas');
const G = require('./grab.js');
const I = require('./input.js');
const D = require('./driver.js');
const calib = require('./calib.js');
const Crop = require('./crop.js');

const FRAMES = path.join(__dirname, 'frames');
const STEP_S = 20;

let n = 0;
async function knob(tag) {
  const p = path.join(FRAMES, `probe-seek-${tag}-${n++}.png`);
  const r = await G.capture(p);
  if (!r.ok) throw new Error('grab failed: ' + r.reason);
  const img = await loadImage(p);
  const chk = calib.check({ w: img.width, h: img.height });
  if (!chk.ok) throw new Error(chk.reason);
  const k = Crop.playheadX(img, calib);
  if (!k) throw new Error('no playhead on the bar - is a replay open?');
  return k.centre;
}

const wait = (ms) => new Promise((r) => setTimeout(r, ms));

(async () => {
  const presses = Number(process.argv[2]) || 5;
  const gaps = (process.argv[3] || '45,150,300,600,1000').split(',').map(Number);

  // 1. The replay has to be still. A playing replay moves the playhead on its
  //    own, and every measurement below would be that motion plus the seek.
  //    SPACE toggles pause, so this measures before pressing - the same rule
  //    the events viewer taught.
  let a = await knob('idle');
  await wait(1500);
  let b = await knob('idle');
  if (a !== b) {
    console.log(`replay is playing (${a} -> ${b}), pausing`);
    await I.sendKeys([D.KEY.pause]);
    await wait(800);
    a = await knob('idle');
    await wait(1500);
    b = await knob('idle');
    if (a !== b) throw new Error(`still moving (${a} -> ${b}) - pause it by hand and re-run`);
  }
  console.log(`paused, playhead at ${b}`);

  // 2. What one step is worth in pixels, measured rather than assumed. One
  //    press, with a gap long enough that nothing can swallow it.
  await I.sendKeys([D.KEY.jumpToStart]);
  await wait(1200);
  const base = await knob('zero');
  await I.sendKeys([D.KEY.forward], { gapMs: 900 });
  await wait(1200);
  const one = await knob('one');
  const stepPx = one - base;
  if (stepPx <= 0) {
    throw new Error(`one press moved ${stepPx}px - the forward key is not working at all`);
  }
  console.log(`start at ${base}, one step = ${stepPx.toFixed(1)}px (${STEP_S}s)`);

  const bar = calib.FROZEN.timeline;
  const span = (bar.x1 - bar.x0 + 1) - 40;
  console.log(`implied map duration about ${Math.round(span / stepPx * STEP_S)}s ` +
    '(from the bar span, so approximate - it is here to say whether run.js can ' +
    'measure duration instead of being told it)\n');

  // 3. The sweep. Each trial restarts, so trials cannot contaminate each other
  //    and none of them runs off the end of the replay.
  console.log(`${presses} presses per trial:\n`);
  console.log('   gap    moved      landed   of');
  for (const gapMs of gaps) {
    await I.sendKeys([D.KEY.jumpToStart]);
    await wait(1200);
    const from = await knob('g' + gapMs);
    await I.sendKeys(new Array(presses).fill(D.KEY.forward), { gapMs });
    await wait(1500);
    const to = await knob('g' + gapMs);
    const landed = (to - from) / stepPx;
    console.log(`${String(gapMs).padStart(6)}ms ${(to - from).toFixed(1).padStart(7)}px ` +
      `${landed.toFixed(2).padStart(9)}   ${presses}`);
  }

  console.log('\nIf landed tracks the gap, seeking needs a slower cadence and the');
  console.log('cost per map is presses x gap. If it stays at 1 whatever the gap,');
  console.log('the client is coalescing repeats and the driver has to seek in');
  console.log('single verified steps, checking the playhead after each one.');
})().catch((e) => { console.error('FAILED: ' + e.message); process.exit(1); });

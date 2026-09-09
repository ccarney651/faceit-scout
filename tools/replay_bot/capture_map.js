// tools/replay_bot/capture_map.js
// Capture one already-open replay end to end, and report what it saw.
//
//   node tools/replay_bot/capture_map.js <durationMMSS>
//   node tools/replay_bot/capture_map.js 17:42
//
// This is run.js for a single map, minus the queue and minus opening the replay
// - the operator opens it by hand. That split is deliberate: seeking is keys and
// arithmetic, while opening a replay is mouse clicks at fixed coordinates, and
// proving the first without the second means a failure here has one cause.
//
// IT TAKES FOCUS. Keys only land while Overwatch is foreground, so the desktop
// is unusable while this runs. Roughly a minute per map.

const path = require('path');
const { loadImage, createCanvas } = require('@napi-rs/canvas');
const G = require('./grab.js');
const I = require('./input.js');
const D = require('./driver.js');
const calib = require('./calib.js');
const Crop = require('./crop.js');
const Match = require('./match.js');
const T = require('./timeline.js');

const FRAMES = path.join(__dirname, 'frames');
const REFS = require(path.join(__dirname, '../../docs/capture/refs.json'));

const mmss = (s) => Math.floor(s / 60) + ':' + String(Math.round(s % 60)).padStart(2, '0');

async function pixels(p) {
  const img = await loadImage(p);
  const cv = createCanvas(img.width, img.height);
  cv.getContext('2d').drawImage(img, 0, 0);
  return { img, data: cv.getContext('2d').getImageData(0, 0, img.width, img.height).data };
}

// Mean absolute difference over the play area. The control bar animates on its
// own, so it is excluded - otherwise the screen would never read as settled.
async function diff(pa, pb) {
  const [a, b] = await Promise.all([pixels(pa), pixels(pb)]);
  let sum = 0, n = 0;
  for (let y = 200; y < 1100; y += 8) {
    for (let x = 0; x < a.img.width; x += 8) {
      const i = (y * a.img.width + x) * 4;
      sum += Math.abs(a.data[i] - b.data[i]) +
        Math.abs(a.data[i + 1] - b.data[i + 1]) +
        Math.abs(a.data[i + 2] - b.data[i + 2]);
      n += 3;
    }
  }
  return sum / n;
}

let grabN = 0;
async function grabTo(tag) {
  const p = path.join(FRAMES, `cap-${tag}-${grabN++}.png`);
  const r = await G.capture(p);
  if (!r.ok) throw new Error('grab failed: ' + r.reason);
  return p;
}

(async () => {
  const arg = process.argv[2];
  if (!arg || !/^\d+:\d+$/.test(arg)) {
    console.error('usage: node capture_map.js <duration MM:SS>');
    process.exit(1);
  }
  const [m, s] = arg.split(':').map(Number);
  const duration = m * 60 + s;

  console.log(`duration ${arg} (${duration}s)`);

  // 1. Read the round structure off the scrubber, once.
  const first = await grabTo('timeline');
  const img0 = await loadImage(first);
  const chk = calib.check({ w: img0.width, h: img0.height });
  if (!chk.ok) throw new Error('calibration smoke check failed: ' + chk.reason);

  const segs = T.segments(Crop.barFlags(img0, calib), {
    duration,
    minRun: calib.FROZEN.timeline.minRunPx,
  });
  console.log('');
  segs.forEach((sg) => console.log(
    `  ${sg.play ? 'PLAY ' : 'BREAK'}  ${mmss(sg.from)} - ${mmss(sg.to)}`));

  const per = T.samplesFor(segs);
  const plan = T.plan(segs, per, { stepS: 20 });
  console.log(`\n${per} samples per round -> ${plan.length} grabs: ${plan.map(mmss).join(', ')}\n`);

  // 2. Drive the viewer to each sample and read the HUD.
  const M = Match.make(REFS, { PAD: calib.FROZEN.ref.PAD });
  const settle = I.makeSettle({
    grab: () => grabTo('settle'),
    diff,
    threshold: 0.6,
    maxTries: 8,
    waitMs: 150,
  });

  const drv = D.make({
    sendKeys: (keys) => I.sendKeys(keys),
    focus: async () => {},
    settle: async () => {
      const r = await settle();
      if (!r.settled) console.log('    (warning: screen never settled)');
    },
    stepS: 20,
  });

  const results = [];
  for (const t of plan) {
    const started = Date.now();
    await drv.seekTo(t);
    const frame = await grabTo('t' + t);
    const img = await loadImage(frame);
    const crops = Crop.all(img, calib);
    const read = {};
    for (const side of ['a', 'b']) {
      read[side] = crops[side].map((c) => M.match(c, side));
    }
    results.push({ t, read });
    console.log(`${mmss(t).padStart(6)}  (${((Date.now() - started) / 1000).toFixed(1)}s)`);
    for (const side of ['a', 'b']) {
      console.log('        ' + side + ': ' +
        read[side].map((r) => `${r.name} ${r.score.toFixed(2)}`).join(' | '));
    }
  }

  console.log('\ndone: ' + results.length + ' samples');
})().catch((e) => { console.error('FAILED: ' + e.message); process.exit(1); });

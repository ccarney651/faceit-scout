// tools/replay_bot/probe_drag.js
// Does dragging the scrubber land where it is aimed, and is it faster than
// pressing the skip key?
//
//   node tools/replay_bot/probe_drag.js
//
// COSTS NOTHING. It needs a replay open with the media controls up, and any
// replay already in the history list will do - a code is spent on IMPORTING,
// not on watching. Open one, press N, and run this.
//
// WHAT IT DOES. Calibrates the bar the way capture.js does - jump to start,
// read the playhead, press the skip key once, read it again - then for each
// target time drags the scrubber there and reads where the playhead actually
// ended up. It reports the error in seconds and the wall-clock cost, against
// the same seek done with key presses.
//
// WHAT WOULD MAKE IT A BAD IDEA. Three things this cannot be told in advance:
// whether the client treats a drag on the bar as a scrub or as a click that
// jumps somewhere else; whether letting go leaves the replay playing; and
// whether a drag needs the replay paused. All three show up in the numbers
// below as a landing error, so read them before trusting anything.

const path = require('path');
const canvas = require('@napi-rs/canvas');
const G = require('./grab.js');
const H = require('./host.js');
const I = require('./input.js');
const R = require('./recorder.js');
const D = require('./driver.js');
const Drag = require('./drag.js');
const calib = require('./calib.js');
const Crop = require('./crop.js');
const T = require('./timeline.js');

const FRAMES = path.join(__dirname, 'frames');
const wait = (ms) => new Promise((r) => setTimeout(r, ms));

let n = 0;
async function frame(tag) {
  const p = path.join(FRAMES, `probe-drag-${tag}-${n++}.png`);
  const r = await G.capture(p);
  if (!r.ok) throw new Error('grab failed: ' + r.reason);
  return canvas.loadImage(p);
}

async function knob(tag) {
  const k = Crop.playheadX(await frame(tag), calib);
  return k ? k.centre : null;
}

async function main() {
  const img = await frame('start');
  const chk = calib.check({ w: img.width, h: img.height });
  if (!chk.ok) throw new Error(chk.reason);
  if (!calib.hudPresent(Crop.hudTint(img, calib))) {
    throw new Error('no replay on screen - open one from the history list first');
  }
  if (!Crop.playheadX(img, calib)) {
    throw new Error('no playhead - press N to bring the media controls up');
  }

  // Calibrate this map's bar, exactly as the capture does.
  await I.sendKeys([D.KEY.jumpToStart]);
  await wait(900);
  const zeroX = await knob('zero');
  await I.sendKeys([D.KEY.forward]);
  await wait(900);
  const oneX = await knob('one');
  if (zeroX === null || oneX === null) throw new Error('lost the playhead while calibrating');

  const stepPx = oneX - zeroX;
  const ref = { zeroX, stepPx, stepS: 60 };
  console.log(`bar: zero at ${zeroX}px, one press = ${stepPx.toFixed(1)}px ` +
    `(${Drag.secondsPerPixel(ref).toFixed(2)}s per pixel)\n`);

  const span = (calib.FROZEN.timeline.x1 - zeroX) / stepPx * 60;
  const targets = [120, 300, 600, 180].filter((t) => t < span - 60);
  if (!targets.length) throw new Error('this replay is too short to probe');

  console.log('TARGET   LANDED    ERROR    TOOK');
  let worst = 0;
  for (const toS of targets) {
    const fromX = await knob('from');
    if (fromX === null) { console.log(`${toS}s  lost the playhead`); continue; }

    const t0 = Date.now();
    await R.playEvents([Drag.plan(ref, fromX, toS)], { name: 'drag' });
    await wait(500);
    const landedX = await knob('after');
    const took = (Date.now() - t0) / 1000;
    if (landedX === null) { console.log(`${toS}s  lost the playhead after the drag`); continue; }

    const landedS = T.secondsAt(landedX, ref);
    const err = landedS - toS;
    worst = Math.max(worst, Math.abs(err));
    console.log(`${String(toS).padStart(5)}s  ${landedS.toFixed(1).padStart(7)}s  ` +
      `${(err >= 0 ? '+' : '') + err.toFixed(1)}s`.padStart(8) + `  ${took.toFixed(1)}s`);
  }

  // The same journey by key, for comparison. Back to the start, then forward.
  await I.sendKeys([D.KEY.jumpToStart]);
  await wait(900);
  const presses = Math.round(targets[0] / 60);
  const t1 = Date.now();
  for (let i = 0; i < presses; i++) {
    await I.sendKeys([D.KEY.forward]);
    await wait(700);                       // the measured safe gap between seeks
  }
  const byKeyS = T.secondsAt(await knob('bykey'), ref);
  console.log(`\nby key: ${presses} presses reached ${byKeyS.toFixed(1)}s in ` +
    `${((Date.now() - t1) / 1000).toFixed(1)}s`);
  console.log(`worst drag error: ${worst.toFixed(1)}s`);
  console.log(worst < 2
    ? 'landing looks good - worth wiring into the capture'
    : 'landing is too loose to trust; look at the retained probe-drag-* frames');
}

main()
  .catch((e) => { console.error('FAILED: ' + e.message); process.exitCode = 1; })
  .then(() => H.close());

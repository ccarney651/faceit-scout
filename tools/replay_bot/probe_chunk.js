// tools/replay_bot/probe_chunk.js
// How fast can a recorded chunk be replayed before the client stops keeping up?
//
//   node tools/replay_bot/probe_chunk.js set-interval
//   node tools/replay_bot/probe_chunk.js set-interval --speeds 1,1.5,2,3,4
//
// A recorded wait is the operator waiting - partly for a menu to animate, and
// partly for themselves. open-import spends about four seconds of every map
// replaying those pauses, which is the largest single block left in a map that
// is otherwise down to grabs and key gaps.
//
// USE set-interval FOR THIS. It is the only chunk that can be replayed over and
// over for nothing: open-import spends a replay code every time it runs, and
// leave-replay exits the replay it needs. So the speed that set-interval
// tolerates is the evidence, and applying it to the others is a judgement -
// stated here rather than hidden, because they are different menus.
//
// The test is whether the chunk still LANDS WHERE IT SHOULD. It plays once at
// normal speed and keeps that end frame as the reference, then plays faster and
// compares: a missed click leaves a menu open or a dialog up, and the picture
// says so immediately.

const path = require('path');
const C = require('./capture.js');
const R = require('./recorder.js');
const H = require('./host.js');
const G = require('./grab.js');

const FRAMES = path.join(__dirname, 'frames');
const SAME_DIFF = 2.0;   // mean abs difference below which two frames are the same screen

let n = 0;
async function endFrame(tag) {
  const p = path.join(FRAMES, `probe-chunk-${tag}-${n++}.png`);
  const r = await G.capture(p);
  if (!r.ok) throw new Error('grab failed: ' + r.reason);
  return p;
}

const wait = (ms) => new Promise((r) => setTimeout(r, ms));

(async () => {
  const name = process.argv[2];
  if (!name) {
    console.error('usage: node probe_chunk.js <chunk> [--speeds 1,1.5,2,3] [--code XXXXXX]');
    process.exit(1);
  }
  const flag = (f) => {
    const i = process.argv.indexOf(f);
    return i === -1 ? null : process.argv[i + 1];
  };
  const speeds = (flag('--speeds') || '1.5,2,3').split(',').map(Number);
  const code = flag('--code');

  if (name === 'open-import') {
    console.error('open-import spends a replay code every time it plays, and a code ' +
      'cannot be imported twice. Probe set-interval instead and carry the answer over.');
    process.exit(1);
  }

  console.log(`reference: playing "${name}" at normal speed`);
  let started = Date.now();
  await R.play(name, { code });
  const at1 = ((Date.now() - started) / 1000).toFixed(1);
  await wait(600);
  const reference = await endFrame('ref');
  console.log(`  took ${at1}s, end state captured\n`);

  const results = [];
  for (const speed of speeds) {
    started = Date.now();
    await R.play(name, { code, speed });
    const took = (Date.now() - started) / 1000;
    await wait(600);
    const after = await endFrame('s' + speed);
    const diff = await C.pixelDiff(reference, after);
    const same = diff <= SAME_DIFF;
    results.push({ speed, took, diff, same });
    console.log(`  ${speed}x  ${took.toFixed(1)}s  frame differs by ${diff.toFixed(2)}  ` +
      `${same ? 'same end state' : 'ENDED SOMEWHERE ELSE'}`);
  }

  const good = results.filter((r) => r.same).map((r) => r.speed);
  const bad = results.filter((r) => !r.same).map((r) => r.speed);
  console.log('');
  if (bad.length) {
    console.log(`  it broke at ${Math.min.apply(null, bad)}x, so stay below that`);
  }
  const usable = good.filter((sp) => !bad.length || sp < Math.min.apply(null, bad));
  if (usable.length) {
    const fastest = Math.max.apply(null, usable);
    console.log(`  fastest clean: ${fastest}x, which took ${
      results.find((r) => r.speed === fastest).took.toFixed(1)}s against ${at1}s`);
    console.log(`  run it again before trusting it - one pass at a speed is one sample, ` +
      'and the seek probe has already shown how much these vary.');
  } else {
    console.log('  nothing faster than normal speed held up');
  }
})()
  .catch((e) => { console.error('FAILED: ' + e.message); process.exitCode = 1; })
  .then(() => H.close());

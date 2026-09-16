// tools/replay_bot/capture_map.js
// Capture one already-open replay end to end, and report what it saw.
//
//   node tools/replay_bot/capture_map.js            duration measured off the bar
//   node tools/replay_bot/capture_map.js 17:42      duration given, and compared
//
// This is run.js for a single map, minus the queue and minus opening the
// replay - the operator opens that by hand. The split is deliberate: it keeps a
// failure here down to one cause, and it is the tool to reach for when only the
// reading is in question.
//
// The capture itself lives in capture.js, because run.js does the same thing in
// a loop and two copies of it would drift.
//
// IT TAKES FOCUS. Keys only land while Overwatch is foreground, so the desktop
// is unusable while this runs. Roughly a minute per map.

const path = require('path');
const C = require('./capture.js');
const H = require('./host.js');

const FRAMES = path.join(__dirname, 'frames');

(async () => {
  const arg = process.argv[2];
  if (arg && !/^\d+:\d+$/.test(arg)) {
    console.error('usage: node capture_map.js [duration MM:SS]');
    console.error('  with no duration, it is measured off the scrubber');
    process.exit(1);
  }
  const told = arg ? Number(arg.split(':')[0]) * 60 + Number(arg.split(':')[1]) : null;

  const io = C.makeIo({ framesDir: FRAMES, log: (m) => console.log(m) });
  const got = await C.make(io).captureMap({ told });

  console.log('\ndone: ' + got.samples.length + ' samples' +
    (got.missed.length ? `, ${got.missed.length} dropped` : ''));

  const doubtful = C.doubtfulOf(got.samples);
  if (doubtful.length) {
    console.log(`\n${doubtful.length} cell${doubtful.length === 1 ? '' : 's'} below ` +
      `${C.LOW_SCORE} - worth looking at the frames before trusting them:`);
    doubtful.forEach((d) => console.log(
      `  ${C.mmss(d.t)} ${d.side}: ${d.name} ${d.score.toFixed(2)}`));
  }

  // Did the comps actually move across the map?
  //
  // The first run that got this far returned the same ten heroes at every
  // sample. That is possible on a Control map - teams do run one comp - but it
  // is also exactly what a stuck seek looks like, and the two were
  // indistinguishable from a wall of per-sample lines.
  for (const side of ['a', 'b']) {
    const seen = new Map();
    got.samples.forEach((s) => {
      const key = s[side].map((x) => x.name).slice().sort().join(', ');
      if (!seen.has(key)) seen.set(key, []);
      seen.get(key).push(C.mmss(s.t));
    });
    console.log('');
    console.log(`SIDE ${side}: ${seen.size} distinct comp${seen.size === 1 ? '' : 's'}`);
    for (const [comp, times] of seen) {
      console.log(`  ${String(times.length).padStart(2)}x  ${comp}`);
      console.log(`       at ${times.join(', ')}`);
    }
  }
})()
  .catch((e) => { console.error('FAILED: ' + e.message); process.exitCode = 1; })
  .then(() => H.close());

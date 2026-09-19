// tools/replay_bot/match_accuracy_sweep.js
// A broad-corpus regression check for the hero matcher, not a spot-check.
//
// WHY THIS EXISTS. Both refs.json fixes on record (2026-09-10's recalibration,
// which claimed Cassidy/Freja/Kiriko fixed at 0.84-0.92) validated against two
// or three hand-picked retained frames. Measured tonight (2026-09-16) against
// 1200+ real frames instead, Cassidy was the SINGLE WORST-SCORING hero of all
// 54 (mean 0.471) and 20 of 54 heroes averaged below LOW_SCORE - a broad
// accuracy gap a narrow validation cannot see, the same failure shape as the
// calibration-relative-geometry lesson (a hand-measured box scores perfectly
// offline and fails in the field). This sweeps the WHOLE retained corpus
// through the real production crop+match pipeline every time, so a future
// refs.json change is judged against thousands of live frames, not three.
//
//   node tools/replay_bot/match_accuracy_sweep.js              every retained frame
//   node tools/replay_bot/match_accuracy_sweep.js --limit 500  a faster, sampled run
//
// Exits non-zero when any hero's mean score falls below MEAN_FLOOR - run this
// before trusting a refs.json rebuild, the way corpus_sweep.js already guards
// the other detectors.
//
// Frames are gitignored (see frames/README.md), so this says nothing useful on
// a checkout that has not run the bot.

const fs = require('fs');
const path = require('path');
const { loadImage } = require('@napi-rs/canvas');
const calib = require('./calib.js');
const Crop = require('./crop.js');
const Match = require('./match.js');
const RefsGate = require('./refsgate.js');

const FRAMES_DIR = path.join(__dirname, 'frames');
const REFS = path.join(__dirname, '../../docs/capture/refs.json');
const GATE = path.join(__dirname, 'state', 'refs_gate.json');

// resolve.js's own LOW_SCORE, restated rather than imported - same reasoning
// as resolve.js's own restatement of phases.js's ABSENT_GUID: small constants
// cross-referenced by comment stay easier to reason about than an import graph
// that exists for one number.
const LOW_SCORE = 0.6;

// A single hero's MEAN across the whole corpus is a much stronger signal than
// any one low read - resolve.js already flags individual reads under
// LOW_SCORE, so this only needs to catch a hero that is chronically bad, not
// noisy. Set a little under LOW_SCORE so ordinary per-read variance around
// the floor does not trip it; a hero averaging under this is not noisy, it is
// broken, the way Cassidy was measured to be.
const MEAN_FLOOR = 0.55;
const MIN_SAMPLES = 20; // below this a hero's mean is too thin to judge

function parseArgs(argv) {
  const out = { limit: null };
  for (let i = 0; i < argv.length; i++) {
    if (argv[i] === '--limit') out.limit = parseInt(argv[++i], 10);
  }
  return out;
}

async function main() {
  const args = parseArgs(process.argv.slice(2));
  const all = fs.readdirSync(FRAMES_DIR).filter((f) => f.startsWith('cap-t') && f.endsWith('.png'));
  if (!all.length) {
    console.log('no retained frames in tools/replay_bot/frames/ - nothing to sweep ' +
      '(see frames/README.md; frames are gitignored and operator-local)');
    return;
  }

  // A deterministic, evenly-spread sample rather than the first N, so a
  // --limit run still covers the whole corpus's time range instead of
  // whichever session happened to write frames alphabetically first.
  let sample = all;
  if (args.limit && args.limit < all.length) {
    const step = Math.max(1, Math.floor(all.length / args.limit));
    sample = [];
    for (let i = 0; i < all.length; i += step) sample.push(all[i]);
  }

  const M = Match.make(require('../../docs/capture/refs.json'), { PAD: calib.FROZEN.ref.PAD });

  let geomFail = 0, n = 0;
  const scores = [];
  const byHero = {};

  for (const f of sample) {
    let img;
    try { img = await loadImage(path.join(FRAMES_DIR, f)); } catch (e) { continue; }
    if (!calib.check({ w: img.width, h: img.height }).ok) { geomFail++; continue; }

    const crops = Crop.all(img, calib);
    for (const side of ['a', 'b']) {
      crops[side].forEach((c) => {
        const r = M.match(c, side);
        if (r.score == null) return;
        n++;
        scores.push(r.score);
        (byHero[r.name] = byHero[r.name] || []).push(r.score);
      });
    }
  }

  if (!n) {
    console.log(`swept ${sample.length} frames, ${geomFail} failed the geometry check, 0 usable reads`);
    process.exitCode = 1;
    return;
  }

  scores.sort((a, b) => a - b);
  const pct = (p) => scores[Math.min(scores.length - 1, Math.floor(p * scores.length))];
  const below = (t) => scores.filter((s) => s < t).length;

  console.log(`swept ${sample.length} frames (of ${all.length} retained), ` +
    `${geomFail} failed the geometry check, ${n} cell reads`);
  console.log(`score distribution: p5=${pct(0.05).toFixed(3)} p25=${pct(0.25).toFixed(3)} ` +
    `median=${pct(0.5).toFixed(3)} p75=${pct(0.75).toFixed(3)} p95=${pct(0.95).toFixed(3)}`);
  console.log(`below ${LOW_SCORE} (LOW_SCORE): ${below(LOW_SCORE)}/${n} = ` +
    `${(100 * below(LOW_SCORE) / n).toFixed(1)}%`);
  console.log();

  const heroStats = Object.keys(byHero).map((name) => {
    const arr = byHero[name];
    const mean = arr.reduce((a, b) => a + b, 0) / arr.length;
    return { name, mean, n: arr.length };
  }).sort((a, b) => a.mean - b.mean);

  console.log('mean score by matched hero, worst first:');
  for (const h of heroStats) {
    const flag = h.mean < MEAN_FLOOR && h.n >= MIN_SAMPLES ? '  <-- BELOW MEAN_FLOOR' : '';
    console.log(`  ${h.name.padEnd(16)} mean=${h.mean.toFixed(3)}  n=${String(h.n).padStart(4)}${flag}`);
  }

  const broken = heroStats.filter((h) => h.mean < MEAN_FLOOR && h.n >= MIN_SAMPLES);
  console.log();
  if (broken.length) {
    console.log(`${broken.length} hero(es) averaging below ${MEAN_FLOOR} on ${MIN_SAMPLES}+ samples - ` +
      `refs.json needs a re-learn for: ${broken.map((h) => h.name).join(', ')}`);
    process.exitCode = 1;
  } else {
    console.log(`no hero averages below ${MEAN_FLOOR} on ${MIN_SAMPLES}+ samples.`);
    recordPass(sample.length, all.length);
  }
}

// Clearing run.js's refs gate (refsgate.js) is the point of passing, but only a
// FULL sweep may do it: --limit exists to iterate quickly, and a 50-frame
// sample that happens to miss the reverted heroes is exactly the narrow
// validation that let the 2026-09-15 regression through in the first place.
function recordPass(swept, retained) {
  if (swept < retained) {
    console.log(`\nsampled ${swept} of ${retained} frames, so the refs gate is NOT cleared - ` +
      'run without --limit to clear it.');
    return;
  }
  const library = JSON.parse(fs.readFileSync(REFS, 'utf8'));
  const record = {
    fingerprint: RefsGate.fingerprint(library),
    passed_at: new Date().toISOString(),
    frames: swept,
    heroes: new Set(library.refs.map((r) => r.n)).size,
  };
  fs.mkdirSync(path.dirname(GATE), { recursive: true });
  fs.writeFileSync(GATE, JSON.stringify(record, null, 1));
  console.log(`\nrefs gate cleared for library ${record.fingerprint} ` +
    `(${record.heroes} heroes, ${swept} frames) -> ${path.relative(process.cwd(), GATE)}`);
}

main().catch((e) => { console.error(e); process.exitCode = 1; });

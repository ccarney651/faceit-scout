// tools/replay_bot/corpus_sweep.js
// Run every detector over every retained frame, and print what it said.
//
// THIS IS HOW THE PANEL DETECTOR WAS CAUGHT. It had been measured on three
// maps, it separated them cleanly, and it was wrong on six frames that were
// already sitting on disk - a night sky, a loading screen, a black frame and
// the ESC menu all read as open panels, because all four are perfectly
// uniform. Nothing in any output said so. One pass over the corpus did.
//
// corpus.test.js pins the frames that have been looked at. This is the other
// half: a wide, unlabelled sweep, for finding the states nobody has labelled
// yet. Read it the way the probes are read - by looking at the numbers.
//
//   node tools/replay_bot/corpus_sweep.js              every frame, one line each
//   node tools/replay_bot/corpus_sweep.js --labelled   only the frames corpus.js names
//
// Frames are gitignored (see frames/README.md), so this says nothing useful on
// a checkout that has not run the bot.

const fs = require('fs');
const path = require('path');
const canvas = require('@napi-rs/canvas');
const calib = require('./calib.js');
const Crop = require('./crop.js');
const S = require('./screen.js');
const Corpus = require('./corpus.js');

const esc = require('./screens/esc-menu.json');

async function readingsFor(file) {
  const img = await canvas.loadImage(path.join(Corpus.DIR, file));
  if (!calib.check({ w: img.width, h: img.height }).ok) {
    return { file, size: img.width + 'x' + img.height };
  }
  const tint = Crop.hudTint(img, calib);
  const rows = Crop.panelRowFraction(img, calib);
  const knob = Crop.playheadX(img, calib);
  return {
    file,
    tintA: tint.a, tintB: tint.b,
    hud: calib.hudPresent(tint),
    rows, open: calib.eventsViewerOpen(rows),
    bright: Crop.panelBrightFraction(img, calib),
    playhead: knob ? knob.centre : null,
    esc: S.distance(S.thumb(img), esc.thumb),
  };
}

const n = (v, d) => (v === null || v === undefined ? '-' : v.toFixed(d));

async function main() {
  const labelledOnly = process.argv.includes('--labelled');
  const labels = new Map(Corpus.panels().map((p) => [p.file, p.open]));

  let files = labelledOnly
    ? [...labels.keys()]
    : fs.readdirSync(Corpus.DIR).filter((f) => f.endsWith('.png')).sort();
  files = files.filter((f) => fs.existsSync(path.join(Corpus.DIR, f)));

  if (!files.length) {
    console.log('no frames in ' + Corpus.DIR + ' - see frames/README.md');
    return;
  }

  console.log(['frame', 'tintA', 'tintB', 'hud', 'rows', 'open', 'bright', 'knob', 'esc', 'labelled'].join('\t'));

  const wrong = [];
  let worstOpen = 1, bestShut = 0;

  for (const f of files) {
    const r = await readingsFor(f);
    if (r.size) { console.log([f, r.size].join('\t')); continue; }
    const said = labels.has(f) ? (labels.get(f) ? 'open' : 'shut') : '';
    if (labels.has(f)) {
      if (r.open !== labels.get(f)) wrong.push(f + ': ' + said + ', read ' + (r.open ? 'open' : 'shut'));
      if (labels.get(f)) worstOpen = Math.min(worstOpen, r.rows);
      else bestShut = Math.max(bestShut, r.rows);
    }
    console.log([f, n(r.tintA, 1), n(r.tintB, 1), r.hud, n(r.rows, 3), r.open,
      n(r.bright, 3), n(r.playhead, 1), n(r.esc, 1), said].join('\t'));
  }

  console.log('');
  console.log(files.length + ' frames, ' + labels.size + ' of them labelled');
  console.log('events panel: worst open ' + n(worstOpen, 3) + ', best shut ' + n(bestShut, 3) +
    ', threshold ' + calib.FROZEN.eventsPanel.minPanelRows);
  if (wrong.length) {
    console.log('MISREAD (' + wrong.length + '):');
    wrong.forEach((w) => console.log('  ' + w));
    process.exitCode = 1;
  } else {
    console.log('every labelled frame read correctly');
  }
}

main().catch((e) => { console.error(e); process.exitCode = 1; });

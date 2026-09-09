// tools/replay_bot/verify_sheet.js
// The ten portraits of a frame, in colour, each labelled with what the matcher
// made of it - so a person can check the reads by looking.
//
// WHY THIS EXISTS. FACEIT league codes are not on owreplays.tv; they answer 403
// "Invalid replay", because only replays somebody uploaded are there. So for the
// games this bot exists to scout there is no hero answer key anywhere, and
// score.js can only check the round structure. The remaining way to know whether
// the heroes are right is for somebody to look - and the frames are all kept, so
// looking costs nothing and no replay has to be watched again.
//
//   node tools/replay_bot/verify_sheet.js frames/cap-t180-177.png sheet.png
//
// contact_sheet.js renders the same ten crops as the 64x36 GREYSCALE buffers the
// matcher actually compares, which is the right picture for judging geometry and
// the wrong one for judging a hero - half of them are unrecognisable at that
// size. This draws the colour crop big enough to name, with the matcher's guess
// and score under it. A cell whose label is wrong is a matcher error; a cell
// that is not a centred hero face is a geometry error, and that is what the
// other tool is for.

const fs = require('fs');
const path = require('path');
const { createCanvas, loadImage } = require('@napi-rs/canvas');
const calib = require('./calib.js');
const Crop = require('./crop.js');
const Match = require('./match.js');

const SCALE = 3;                 // portraits are small; this makes them namable
const PAD = 10;
const LABEL_H = 34;

async function main() {
  const inPath = process.argv[2];
  const outPath = process.argv[3] || 'verify-sheet.png';
  if (!inPath) {
    console.log('usage: node tools/replay_bot/verify_sheet.js <frame.png> [out.png]');
    process.exitCode = 1;
    return;
  }

  const img = await loadImage(inPath);
  const chk = calib.check({ w: img.width, h: img.height });
  if (!chk.ok) console.log('WARNING: ' + chk.reason);

  const M = Match.make(require(path.join(__dirname, '../../docs/capture/refs.json')),
    { PAD: calib.FROZEN.ref.PAD });
  // The same path the capture takes: crop.all makes the matcher buffers, and
  // the matcher scores each against the per-side reference variants.
  const crops = Crop.all(img, calib);
  const read = { a: [], b: [] };
  ['a', 'b'].forEach((side) => {
    read[side] = crops[side].map((c) => M.match(c, side));
  });

  const cellW = Math.round(calib.FROZEN.boxes.a.w / 5 * (1 - calib.FROZEN.ref.LF));
  const cellH = Math.round(calib.FROZEN.boxes.a.h * calib.FROZEN.ref.TF);
  const tileW = Math.round(cellW * SCALE / 2);
  const tileH = Math.round(cellH * SCALE / 2);

  const cv = createCanvas(PAD + 5 * (tileW + PAD), PAD + 2 * (tileH + LABEL_H + PAD) + 24);
  const cx = cv.getContext('2d');
  cx.fillStyle = '#15161a';
  cx.fillRect(0, 0, cv.width, cv.height);

  cx.fillStyle = '#9aa0a6';
  cx.font = '13px monospace';
  cx.fillText(path.basename(inPath) + '   -   top row is side A, bottom is side B', PAD, 16);

  ['a', 'b'].forEach((side, row) => {
    const cells = calib.cells(side);
    cells.forEach((c, i) => {
      const x = PAD + i * (tileW + PAD);
      const y = 24 + PAD + row * (tileH + LABEL_H + PAD);
      cx.drawImage(img, c.x, c.y, c.w, c.h, x, y, tileW, tileH);

      const hit = read[side][i] || {};
      const score = typeof hit.score === 'number' ? hit.score : 0;
      // The same threshold the capture log marks with ?? - below this a match is
      // a suggestion, not a reading.
      const doubtful = score < 0.6;
      cx.strokeStyle = doubtful ? '#e0603f' : '#3a3d44';
      cx.lineWidth = doubtful ? 3 : 1;
      cx.strokeRect(x - 0.5, y - 0.5, tileW + 1, tileH + 1);

      cx.fillStyle = doubtful ? '#e0603f' : '#e8eaed';
      cx.font = 'bold 15px system-ui, sans-serif';
      cx.fillText(String(hit.name || '?'), x, y + tileH + 17);
      cx.fillStyle = doubtful ? '#e0603f' : '#9aa0a6';
      cx.font = '13px monospace';
      cx.fillText(score.toFixed(2) + (doubtful ? '  ??' : ''), x, y + tileH + 31);
    });
  });

  fs.writeFileSync(outPath, cv.toBuffer('image/png'));
  console.log('wrote ' + outPath);
  ['a', 'b'].forEach((side) => {
    console.log('  ' + side + ': ' + read[side]
      .map((h) => h.name + ' ' + h.score.toFixed(2)).join(' | '));
  });
}

main().catch((e) => { console.error('FAILED: ' + e.message); process.exitCode = 1; });

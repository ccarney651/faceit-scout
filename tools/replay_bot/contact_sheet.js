// tools/replay_bot/contact_sheet.js
// Render the ten portrait crops of a frame side by side, so the geometry can be
// LOOKED AT rather than believed.
//
// This exists because the calibration failure this project has already had once
// was invisible in numbers and obvious in a picture: crops fitted to the wrong
// reference box scored 12/12 offline and read nothing at all live. A crop that
// is half a portrait off still produces a plausible buffer, a confident-looking
// match, and silent nonsense at scale.
//
// Usage (needs `npm install --no-save @napi-rs/canvas`):
//   node tools/replay_bot/contact_sheet.js [frame.png] [out.png]
//
// Every cell should be a centred hero face. Grey bands at an edge, name plates,
// or health pips creeping in all mean the frozen geometry in calib.js is wrong
// for this frame - re-run the bootstrap rather than nudging numbers.

const fs = require('fs');
const path = require('path');
const { createCanvas, loadImage } = require('@napi-rs/canvas');
const U = require('../../docs/capture/engine/util.js');
const calib = require('./calib.js');
const Crop = require('./crop.js');

const FRAMES = path.join(__dirname, 'frames');
const IN = process.argv[2] || path.join(FRAMES, '2026-09-08-busan-2560x1440.png');
const OUT = process.argv[3] || path.join(FRAMES, 'contact-sheet.png');

// Draw one 64x36 greyscale buffer as a visible tile.
function tile(b64) {
  const px = U.b64bytes(b64);
  const cv = createCanvas(calib.FROZEN.ref.REF_W, calib.FROZEN.ref.REF_H);
  const cx = cv.getContext('2d');
  const im = cx.createImageData(cv.width, cv.height);
  for (let k = 0; k < px.length; k++) {
    im.data[k * 4] = im.data[k * 4 + 1] = im.data[k * 4 + 2] = px[k];
    im.data[k * 4 + 3] = 255;
  }
  cx.putImageData(im, 0, 0);
  return cv;
}

(async () => {
  const img = await loadImage(IN);
  const crops = Crop.all(img, calib);

  const S = 4;
  const W = calib.FROZEN.ref.REF_W * S;
  const H = calib.FROZEN.ref.REF_H * S;
  const P = 8;
  const LBL = 22;

  const cv = createCanvas(5 * (W + P) + P, 2 * (H + LBL + P) + P);
  const cx = cv.getContext('2d');
  cx.fillStyle = '#111';
  cx.fillRect(0, 0, cv.width, cv.height);
  cx.font = '14px sans-serif';
  cx.imageSmoothingEnabled = false;

  ['a', 'b'].forEach((side, row) => {
    crops[side].forEach((b64, i) => {
      const x = P + i * (W + P);
      const y = P + row * (H + LBL + P) + LBL;
      cx.drawImage(tile(b64), 0, 0, calib.FROZEN.ref.REF_W, calib.FROZEN.ref.REF_H, x, y, W, H);
      cx.fillStyle = '#9cf';
      cx.fillText(side + i, x, y - 6);
    });
  });

  fs.writeFileSync(OUT, cv.toBuffer('image/png'));
  console.log('wrote ' + OUT + ' (' + cv.width + 'x' + cv.height + ')');
})();

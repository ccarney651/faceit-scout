// The shipped codeBox() must place the same rectangle as the Python prototype
// that was swept. Two implementations of one number drift; this is what catches
// it. Run from the repo root:
//   node tools/real_frame_eval/code_parity.js
const fs = require('fs');
const path = require('path');
const R = require('../../docs/capture/engine/replaycode.js');

const fitted = JSON.parse(fs.readFileSync(path.join(__dirname, 'code_offsets.json'), 'utf8'));
let bad = 0;
for (const [k, v] of Object.entries(fitted)) {
  if (Math.abs(R.OFFSETS[k] - v) > 1e-9) {
    console.error(`OFFSET DRIFT ${k}: module ${R.OFFSETS[k]} vs fitted ${v}`);
    bad++;
  }
}
// And the box itself, on the strips the sweep actually used.
for (const a of [{ x: 57, y: 97, w: 700, h: 111 }, { x: 127, y: 123, w: 660, h: 105 }]) {
  const b = R.codeBox(a);
  const bw = fitted.DW * a.w, bh = fitted.DH * a.h;
  const px = bw * fitted.PAD, py = bh * fitted.PAD;
  const want = {
    x: Math.round(a.x + fitted.DX * a.w - px), y: Math.round(a.y + fitted.DY * a.h - py),
    w: Math.round(bw + 2 * px), h: Math.round(bh + 2 * py),
  };
  for (const k of ['x', 'y', 'w', 'h']) {
    if (b[k] !== want[k]) { console.error(`BOX DRIFT ${k}: ${b[k]} vs ${want[k]}`); bad++; }
  }
}
if (bad) { console.error('parity FAILED'); process.exit(1); }
console.log('parity ok - shipped codeBox matches the swept offsets');

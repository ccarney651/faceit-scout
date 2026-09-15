// tools/replay_bot/match_search_check.js
// Before/after check for the widened matcher alignment search.
//
// Runs the SHIPPED matcher (docs/capture/engine/refs.js) two ways over the
// retained side-b strips: the OLD path (a crop centred in a PAD-padded ZERO
// buffer, searched +/-PAD - exactly what matchCrop used to do) and the NEW path
// (matchCrop, edge-clamped border, +/-MATCH_SEARCH at 1px). Prints the winner,
// score and margin so the change can be judged, not assumed.
//
// Geometry is calib.js FROZEN, transcribed here so the script has no calibration
// dependency: boxes.b, LF/RF/TF, and review_out.js's 12px strip top pad.
//
// Usage: node tools/replay_bot/match_search_check.js <strip.png> <slot,lineup>

'use strict';

const fs = require('fs');
const path = require('path');
const { loadImage } = require('@napi-rs/canvas');

const REPO = path.join(__dirname, '..', '..');
const Crop = require('./crop.js');
const Util = require(path.join(REPO, 'docs/capture/engine/util.js'));
const Refs = require(path.join(REPO, 'docs/capture/engine/refs.js'));

const REFS_JSON = JSON.parse(
  fs.readFileSync(path.join(REPO, 'docs/capture/refs.json'), 'utf8')
);

const BOX_B = { x: 1799.3349056603774, y: 95, w: 706.25, h: 108.85047245433347 };
const LF = 0.42;
const TF = 0.45;
const RF = 0.06;
const PAD_Y = 12;

function installGlobals() {
  global.REF_W = REFS_JSON.w;
  global.REF_H = REFS_JSON.h;
  global.PAD = 2;
  global.LF = REFS_JSON.left_fraction;
  global.TF = REFS_JSON.top_fraction;
  global.REFS = [];
  global.LOCAL_REFS = [];
  global.CUSTOM_HEROES = {};
  global.HERO_ICON = {};
  Object.keys(Util).forEach((k) => { global[k] = Util[k]; });
}

function cellsB() {
  const cw = BOX_B.w / 5;
  const out = [];
  for (let i = 0; i < 5; i++) {
    out.push({
      x: BOX_B.x + i * cw + cw * LF,
      y: BOX_B.y,
      w: cw * (1 - LF - RF),
      h: BOX_B.h * TF,
    });
  }
  return out;
}

// The OLD matchCrop: crop centred in a PAD-padded ZERO buffer, +/-PAD search.
function oldMatch(r, b64, side) {
  const px = Util.b64bytes(b64);
  const W = r.w + 2 * global.PAD;
  const gp = new Float32Array(W * (r.h + 2 * global.PAD));
  for (let y = 0; y < r.h; y++) {
    for (let x = 0; x < r.w; x++) {
      gp[(y + global.PAD) * W + (x + global.PAD)] = px[y * r.w + x];
    }
  }
  return refsHandle.bestMatch(gp, side, false);
}

installGlobals();
const refsHandle = Refs.make({ doc: { getElementById: () => null, createElement: () => { throw new Error('no canvas needed'); } } });
REFS_JSON.refs.forEach((rec) => { const t = refsHandle.refTemplate(rec); if (t) global.REFS.push(t); });

async function main() {
  const arg = process.argv[2];
  const expected = (process.argv[3] || '').split(',');
  if (!arg) { console.error('usage: node match_search_check.js <strip.png> <slot,lineup>'); process.exit(2); }
  const img = await loadImage(arg);

  const rects = cellsB();
  console.log('strip:', path.basename(arg));
  console.log('slot  expected     OLD winner          old    NEW winner          new    dx,dy  margin');
  let tOld = 0, tNew = 0;
  for (let i = 0; i < rects.length; i++) {
    const cell = rects[i];
    const stripRect = { x: cell.x - BOX_B.x, y: cell.y - (BOX_B.y - PAD_Y), w: cell.w, h: cell.h };
    const b64 = Crop.cell(img, stripRect, { REF_W: REFS_JSON.w, REF_H: REFS_JSON.h });

    let t = Date.now();
    const oldr = oldMatch(REFS_JSON, b64, 'b');
    tOld += Date.now() - t;

    t = Date.now();
    const newr = refsHandle.matchCrop(b64, 'b');
    tNew += Date.now() - t;

    const exp = (expected[i] || '').padEnd(12);
    console.log(
      `  ${i}   ${exp} ` +
      `${String(oldr.name).padEnd(18)} ${oldr.score.toFixed(3)}  ` +
      `${String(newr.name).padEnd(18)} ${newr.score.toFixed(3)}  ` +
      `(${newr.dx},${newr.dy})`
    );
  }
  console.log(`\nold search total ${tOld}ms   new search total ${tNew}ms (per strip, 5 slots)`);
}

main().catch((e) => { console.error(e); process.exit(1); });

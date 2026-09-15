const fs = require('fs');
const path = require('path');
const canvas = require(path.join('C:/Users/ccarn/faceit-sync/tools/replay_bot', 'node_modules/@napi-rs/canvas'));
const U = require('C:/Users/ccarn/faceit-sync/docs/capture/engine/util.js');
const Crop = require('C:/Users/ccarn/faceit-sync/tools/replay_bot/crop.js');
const Calib = require('C:/Users/ccarn/faceit-sync/tools/replay_bot/calib.js');
const refsJson = JSON.parse(fs.readFileSync('C:/Users/ccarn/faceit-sync/docs/capture/refs.json', 'utf8'));

const stripsDir = 'C:/Users/ccarn/faceit-sync/tools/replay_bot/out/replay-bot-2026-09-14/crops';
const strip = process.argv[2] ? path.join(stripsDir, process.argv[2]) : path.join(stripsDir, 'KH6ZNX-r2-b-s3.png');
const EXPECTED = process.argv[3] ? process.argv[3].split(',') : ['?', 'Baptiste', 'D.Mon', 'Lucio', 'Bastion'];

const box = Calib.FROZEN.boxes.b;
const PADY = 12;
const SX = box.x, SY = box.y - PADY;

function centeredCos(pxA, pxB, dx, dy) {
  const W = 64, H = 36;
  let sa = 0, sb = 0, n = 0;
  for (let y = 0; y < H; y++) for (let x = 0; x < W; x++) {
    const ax = x + dx, ay = y + dy;
    if (ax < 0 || ax >= W || ay < 0 || ay >= H) continue;
    sa += pxA[ay * W + ax]; sb += pxB[y * W + x]; n++;
  }
  sa /= n; sb /= n;
  let dot = 0, na = 0, nb = 0;
  for (let y = 0; y < H; y++) for (let x = 0; x < W; x++) {
    const ax = x + dx, ay = y + dy;
    if (ax < 0 || ax >= W || ay < 0 || ay >= H) continue;
    const a = pxA[ay * W + ax] - sa, b = pxB[y * W + x] - sb;
    dot += a * b; na += a * a; nb += b * b;
  }
  return dot / Math.sqrt(na * nb);
}

function bestAlign(pxA, pxB, range) {
  let best = { c: -2, dx: 0, dy: 0 };
  for (const dy of range) for (const dx of range) {
    const c = centeredCos(pxA, pxB, dx, dy);
    if (c > best.c) best = { c, dx, dy };
  }
  return best;
}

// Reference templates for a hero+side, from refs.json
function refTemplates(name, variant) {
  return refsJson.refs.filter(r => r.n === name && r.v === variant)
    .map(r => Float64Array.from(U.b64bytes(r.d)));
}

function liveCellForSlot(img, slot) {
  const cell = { x: box.x + slot * box.w / 5, y: box.y, w: box.w / 5, h: box.h };
  const face = {
    x: cell.x + cell.w * refsJson.left_fraction,
    y: cell.y,
    w: cell.w * (1 - refsJson.left_fraction - refsJson.right_fraction),
    h: cell.h * refsJson.top_fraction,
  };
  // map into strip coordinates (strip = box region shifted up by PADY)
  const rect = { x: face.x - SX, y: face.y - SY, w: face.w, h: face.h };
  const b64 = Crop.cell(img, rect, { REF_W: 64, REF_H: 36 });
  return Float64Array.from(U.b64bytes(b64));
}

(async () => {
  const img = await canvas.loadImage(fs.readFileSync(strip));
  console.log('strip', path.basename(strip), img.width + 'x' + img.height);

  // Expected lineups on KH6ZNX r2 side b: slot0 ?, slot1 Baptiste, slot2 D.Mon, slot3 Lucio, slot4 Bastion
  const expected = EXPECTED;
  for (let slot = 0; slot < 5; slot++) {
    const live = liveCellForSlot(img, slot);
    const cands = [];
    // score live against every hero's refs on this side
    const seen = new Set();
    for (const r of refsJson.refs) {
      if (r.v !== 'b' || seen.has(r.n)) continue;
      seen.add(r.n);
      for (const t of refTemplates(r.n, 'b')) {
        const b = bestAlign(t, live, [-4, -2, 0, 2, 4]);
        cands.push({ n: r.n, c: b.c, dx: b.dx, dy: b.dy, c0: centeredCos(t, live, 0, 0) });
      }
    }
    cands.sort((a, b) => b.c - a.c);
    const top = cands[0];
    console.log(`\nslot ${slot} (expected ${expected[slot]}):`);
    console.log(`  winner ${top.n}  best=${top.c.toFixed(3)} @dx=${top.dx},dy=${top.dy}   (0,0)=${top.c0.toFixed(3)}`);
    console.log('  runner-ups: ' + cands.slice(1, 4).map(c => `${c.n} ${c.c.toFixed(3)}@${c.dx},${c.dy}`).join('  '));
  }
})();
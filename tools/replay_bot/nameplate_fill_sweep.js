// tools/replay_bot/nameplate_fill_sweep.js
// Validation harness for the dark-plate fill-ceiling fix documented in
// specs/2026-09-15-nameplate-fill-heuristic-handoff.md.
//
// docs/capture/engine/frames.js's findNameRow now judges a row's fill
// against ITS OWN LOCAL plate baseline (floored at the old fixed 0.42, so a
// dark plate behaves exactly as before) instead of a flat ceiling. This
// harness checks that change two ways:
//   (1) the 3 known-broken bright/team-colour-plate crops from the
//       2026-09-15 390-map run - does the shipped algorithm now recover a
//       sane row on all three?
//   (2) every other r1 strip crop in that same run, comparing the SHIPPED
//       algorithm against the OLD fixed-0.42 one it replaced, as a
//       regression-safety proxy (does the new algorithm move a row that the
//       old one already found fine?).
//
// There is no hand-labelled ground truth here beyond the 3 known-bad crops;
// "old" for every other crop means "what the fixed-0.42 constant used to
// find", not an independently-verified truth. frames.test.js is the
// synthetic ground-truth check (and already caught one real regression in
// this fix's first draft - a margin with no floor could compute a ceiling
// BELOW 0.42 on a wide, genuinely dark band). The original dark-plate
// regression corpus (tools/real_frame_eval/rowfind_parity.py,
// screenshots/*.png) is NOT available on this machine (gitignored, no local
// copy) - re-run that check separately wherever screenshots/ exists before
// changing either constant again.
//
// Usage: node tools/replay_bot/nameplate_fill_sweep.js [session-dir]
//   default session: out/replay-bot-2026-09-15-full

'use strict';

const fs = require('fs');
const path = require('path');
const { loadImage, createCanvas } = require('@napi-rs/canvas');

const REPO = path.join(__dirname, '..', '..');
const Frames = require(path.join(REPO, 'docs/capture/engine/frames.js'));

const SESSION = process.argv[2] || path.join(__dirname, 'out', 'replay-bot-2026-09-15-full');
const CROPS = path.join(SESSION, 'crops');
const PAD_Y = 12;
// nameplate.js's own search band (NOT frames.js's live-tool band - replay
// geometry differs, per nameplate.js's header comment).
const NAME_BAND_TOP = 0.48, NAME_BAND_BOT = 0.85;

const KNOWN_BAD = [
  { file: 'BM1S86-r1-a.png', side: 'a', note: 'light-blue plate, total miss (reads.a all blank)' },
  { file: 'CENQKX-r1-a.png', side: 'a', note: 'light-blue plate, total miss (reads.a all blank)' },
  { file: '2RNA0B-r1-b.png', side: 'b', note: 'red plate, fragmented (reads.b garbage)' },
];

// The OLD algorithm (fixed 0.42 ceiling, no local baseline), kept here only
// as the "what did this replace" comparison point - mirrors frames.js's
// pre-2026-09-15 findNameRow exactly.
const OLD_FILL_MAX = 0.42, NAME_RUN_FRAC = 0.35;

function profile(rgba, w, h) {
  const lum = new Uint8Array(w * h), hist = new Uint32Array(256);
  for (let i = 0, j = 0; j < w * h; i += 4, j++) {
    const g = (0.299 * rgba[i] + 0.587 * rgba[i + 1] + 0.114 * rgba[i + 2]) | 0;
    lum[j] = g; hist[g]++;
  }
  const want = Math.floor(w * h * 0.88);
  let acc = 0, T = 0;
  for (T = 0; T < 256; T++) { acc += hist[T]; if (acc >= want) break; }
  if (T < 120) T = 120; else if (T > 230) T = 230;

  const fill = new Float64Array(h), tr = new Float64Array(h);
  for (let y = 0; y < h; y++) {
    let on = 0, ch = 0, prev = false;
    const base = y * w;
    for (let x = 0; x < w; x++) {
      const v = lum[base + x] > T;
      if (v) on++;
      if (x && v !== prev) ch++;
      prev = v;
    }
    fill[y] = on / w; tr[y] = ch / w;
  }
  return { fill, tr, T };
}

function quiet(fill, s, e, h) {
  let a = 0, na = 0, b = 0, nb = 0;
  for (let k = Math.max(0, s - 3); k < s; k++) { a += fill[k]; na++; }
  for (let k = e + 1; k < Math.min(h, e + 4); k++) { b += fill[k]; nb++; }
  a = na ? a / na : 0.5; b = nb ? b / nb : 0.5;
  return Math.max(0, 1 - (a + b) / 0.20);
}

function pickRun(score, tr, fill, h) {
  let max = 0;
  for (let y = 0; y < h; y++) if (score[y] > max) max = score[y];
  if (max <= 0) return null;
  const thr = NAME_RUN_FRAC * max;
  let best = null, bestv = -1, start = -1;
  for (let y = 0; y <= h; y++) {
    const inRun = y < h && score[y] >= thr;
    if (inRun && start < 0) start = y;
    else if (!inRun && start >= 0) {
      const end = y - 1;
      let sum = 0;
      for (let k = start; k <= end; k++) sum += tr[k];
      const v = (sum / (end - start + 1)) * quiet(fill, start, end, h);
      if (v > bestv) { bestv = v; best = [start, end]; }
      start = -1;
    }
  }
  return best ? { y: best[0], h: best[1] - best[0] + 1 } : null;
}

function findRowOld(rgba, w, h) {
  const { fill, tr } = profile(rgba, w, h);
  const score = new Float64Array(h);
  for (let y = 0; y < h; y++) score[y] = fill[y] <= OLD_FILL_MAX ? tr[y] : 0;
  return pickRun(score, tr, fill, h);
}

function walkR1(dir) {
  let ents;
  try { ents = fs.readdirSync(dir); } catch (e) { return []; }
  return ents.filter((n) => /-r1-[ab]\.png$/i.test(n)).sort();
}

function rebase(img) {
  return { x: 0, y: PAD_Y, w: img.width, h: img.height - 2 * PAD_Y };
}

async function band(img, box) {
  const y0 = box.y + box.h * NAME_BAND_TOP, y1 = box.y + box.h * NAME_BAND_BOT;
  const w = box.w, h = Math.max(1, Math.round(y1 - y0));
  const cv = createCanvas(w, h);
  const cx = cv.getContext('2d', { willReadFrequently: true });
  cx.drawImage(img, box.x, y0, w, h, 0, 0, w, h);
  return { data: cx.getImageData(0, 0, w, h).data, w, h, y0 };
}

async function main() {
  console.log(`session: ${SESSION}\n`);

  console.log('=== KNOWN-BAD CROPS (does the SHIPPED algorithm now recover them?) ===');
  let allRecovered = true;
  for (const kb of KNOWN_BAD) {
    const p = path.join(CROPS, kb.file);
    if (!fs.existsSync(p)) { console.log(`  ${kb.file}: MISSING`); continue; }
    const img = await loadImage(p);
    const box = rebase(img);
    const b = await band(img, box);
    const oldRow = findRowOld(b.data, b.w, b.h);
    const newRow = Frames.findNameRow(b.data, b.w, b.h);
    const sane = newRow && newRow.h >= 10 && newRow.h <= 25;
    if (!sane) allRecovered = false;
    console.log(`${kb.file} side=${kb.side}  (${kb.note})`);
    console.log(`  old (fixed 0.42): ${oldRow ? `y=${oldRow.y} h=${oldRow.h}` : 'null'}`);
    console.log(`  new (shipped):    ${newRow ? `y=${newRow.y} h=${newRow.h}` : 'null'}  ${sane ? '-> sane row height' : '-> STILL LOOKS BROKEN'}`);
  }
  console.log(`\n${allRecovered ? 'ALL 3 known-bad crops recovered a sane row.' : 'NOT ALL known-bad crops recovered - investigate before shipping.'}`);

  console.log('\n=== REGRESSION-SAFETY PROXY (r1 crops, whole session, new vs old) ===');
  const files = walkR1(CROPS);
  let total = 0, oldNull = 0, newNull = 0, changed = 0, recoveredFromNull = 0, degenerateFixed = 0, plausibleMoved = 0;
  const moved = [];
  for (const f of files) {
    const img = await loadImage(path.join(CROPS, f));
    const box = rebase(img);
    const b = await band(img, box);
    const oldRow = findRowOld(b.data, b.w, b.h);
    const newRow = Frames.findNameRow(b.data, b.w, b.h);
    total++;
    if (!oldRow) oldNull++;
    if (!newRow) newNull++;
    const isChanged = (!!oldRow !== !!newRow) || (oldRow && newRow && (oldRow.y !== newRow.y || oldRow.h !== newRow.h));
    if (isChanged) {
      changed++;
      if (!oldRow) recoveredFromNull++;
      else if (oldRow.h <= 2) degenerateFixed++;
      else { plausibleMoved++; if (moved.length < 20) moved.push({ f, oldRow, newRow }); }
    }
  }
  console.log(`${total} r1 strips`);
  console.log(`old (fixed 0.42): ${oldNull} null (${(100 * oldNull / total).toFixed(1)}%)`);
  console.log(`new (shipped):    ${newNull} null (${(100 * newNull / total).toFixed(1)}%)`);
  console.log(`\nrow differs from old on ${changed}/${total} (${(100 * changed / total).toFixed(1)}%):`);
  console.log(`  recovered-from-null: ${recoveredFromNull}`);
  console.log(`  fixed a degenerate (old h<=2px) fragment: ${degenerateFixed}`);
  console.log(`  moved a PLAUSIBLE old row (h>2px, worth an eyeball): ${plausibleMoved}`);
  moved.forEach((m) => console.log(`    MOVED ${m.f}: old y=${m.oldRow.y} h=${m.oldRow.h}  ->  new y=${m.newRow.y} h=${m.newRow.h}`));
}

main().catch((e) => { console.error(e); process.exit(1); });

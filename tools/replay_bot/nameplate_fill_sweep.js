// tools/replay_bot/nameplate_fill_sweep.js
// Measurement harness for the dark-plate fill-ceiling bug documented in
// specs/2026-09-15-nameplate-fill-heuristic-handoff.md. Compares candidate
// fixes for findNameRow()'s NAME_FILL_MAX against:
//   (1) the 3 known-broken bright/team-colour-plate crops from the
//       2026-09-15 390-map run (does a candidate recover a sane row?)
//   (2) every other r1 strip crop in that same run, using the SHIPPED
//       algorithm's own row as a regression-safety baseline (does a
//       candidate move a row that currently looks fine?)
//
// This does NOT decide the fix - see the handoff's §5 for the three
// directions and their tradeoffs. It only gives numbers to decide with.
// There is no hand-labelled ground truth here beyond the 3 known-bad crops;
// "baseline" for every other crop means "what the shipped 0.42 constant
// currently finds", not an independently-verified truth. The original
// dark-plate regression corpus (tools/real_frame_eval/rowfind_parity.py,
// screenshots/*.png) is NOT available on this machine (gitignored, no
// local copy) - re-run that check separately wherever screenshots/ exists
// before shipping any change.
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

// --- candidate row-finders, mirroring frames.js findNameRow's structure ---
// Kept in step manually with docs/capture/engine/frames.js, the same way
// tools/real_frame_eval/rowfind_proto.py mirrors it for the dark-plate sweep.
const NAME_RUN_FRAC = 0.35;

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

// A. fixed ceiling at a different constant.
function findRowFixed(rgba, w, h, ceiling) {
  const { fill, tr } = profile(rgba, w, h);
  const score = new Float64Array(h);
  for (let y = 0; y < h; y++) score[y] = fill[y] <= ceiling ? tr[y] : 0;
  return pickRun(score, tr, fill, h);
}

// B. ceiling relative to the band's own background fill (median across the
// band, on the theory that most rows are plate-only and text rows are the
// minority whose fill sits above that baseline by roughly a fixed margin).
function findRowRelative(rgba, w, h, margin) {
  const { fill, tr } = profile(rgba, w, h);
  const sorted = Array.from(fill).sort((a, b) => a - b);
  const bg = sorted[Math.floor(sorted.length / 2)];
  const ceiling = Math.min(0.97, bg + margin);
  const score = new Float64Array(h);
  for (let y = 0; y < h; y++) score[y] = fill[y] <= ceiling ? tr[y] : 0;
  return { row: pickRun(score, tr, fill, h), bg, ceiling };
}

// B2. ceiling relative to a LOCAL background fill per row (mean fill of a
// +/-8 row window, excluding the +/-2 rows nearest the candidate row itself,
// so the plate colour right around a name doesn't get diluted by whatever
// else - portrait bottom, health bar - sits elsewhere in the band). Adapts
// per-row instead of picking one scalar for the whole band.
function findRowLocalRelative(rgba, w, h, margin) {
  const { fill, tr } = profile(rgba, w, h);
  const score = new Float64Array(h);
  for (let y = 0; y < h; y++) {
    let sum = 0, n = 0;
    for (let k = Math.max(0, y - 8); k <= Math.min(h - 1, y + 8); k++) {
      if (Math.abs(k - y) <= 2) continue;
      sum += fill[k]; n++;
    }
    const localBg = n ? sum / n : fill[y];
    const ceiling = Math.min(0.97, localBg + margin);
    score[y] = fill[y] <= ceiling ? tr[y] : 0;
  }
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

const FIXED_CANDIDATES = [0.42, 0.50, 0.55, 0.60, 0.65, 0.70, 0.75, 0.80, 0.85, 0.90, 0.95];
const RELATIVE_MARGINS = [0.10, 0.15, 0.20, 0.25, 0.30, 0.35, 0.40];

async function main() {
  console.log(`session: ${SESSION}\n`);

  // --- Part 1: the 3 known-bad crops -------------------------------------
  console.log('=== KNOWN-BAD CROPS ===');
  for (const kb of KNOWN_BAD) {
    const p = path.join(CROPS, kb.file);
    if (!fs.existsSync(p)) { console.log(`  ${kb.file}: MISSING`); continue; }
    const img = await loadImage(p);
    const box = rebase(img);
    const b = await band(img, box);
    console.log(`\n${kb.file} side=${kb.side}  (${kb.note})`);
    console.log(`  band: ${b.w}x${b.h}px`);

    const shipped = Frames.findNameRow(b.data, b.w, b.h);
    console.log(`  shipped (0.42): ${shipped ? `y=${shipped.y} h=${shipped.h}` : 'null'}`);

    console.log('  fixed-ceiling sweep:');
    for (const c of FIXED_CANDIDATES) {
      const r = findRowFixed(b.data, b.w, b.h, c);
      console.log(`    ceiling=${c.toFixed(2)}: ${r ? `y=${r.y} h=${r.h}` : 'null'}`);
    }

    console.log('  relative-ceiling sweep (bg=median fill, ceiling=bg+margin):');
    for (const m of RELATIVE_MARGINS) {
      const { row, bg, ceiling } = findRowRelative(b.data, b.w, b.h, m);
      console.log(`    margin=${m.toFixed(2)} (bg=${bg.toFixed(3)} ceiling=${ceiling.toFixed(3)}): ${row ? `y=${row.y} h=${row.h}` : 'null'}`);
    }

    console.log('  local-relative-ceiling sweep (bg=+/-8 row window, ceiling=localBg+margin):');
    for (const m of RELATIVE_MARGINS) {
      const row = findRowLocalRelative(b.data, b.w, b.h, m);
      console.log(`    margin=${m.toFixed(2)}: ${row ? `y=${row.y} h=${row.h}` : 'null'}`);
    }
  }

  // --- Part 2: regression-safety proxy over the rest of the run ----------
  console.log('\n\n=== REGRESSION-SAFETY PROXY (r1 crops, whole session) ===');
  console.log('baseline = what the SHIPPED 0.42 ceiling currently finds - not independently verified truth.\n');

  const files = walkR1(CROPS);
  let total = 0, baseNull = 0;
  const fixedStats = new Map(FIXED_CANDIDATES.map((c) => [c, { changed: 0, nowNull: 0, recoveredFromNull: 0 }]));
  const relStats = new Map(RELATIVE_MARGINS.map((m) => [m, { changed: 0, nowNull: 0, recoveredFromNull: 0 }]));
  const localRelStats = new Map(RELATIVE_MARGINS.map((m) => [m, { changed: 0, nowNull: 0, recoveredFromNull: 0 }]));

  const sample85 = [];
  let degenerateFixed85 = 0, plausibleMoved85 = 0;
  const moved85 = [];
  for (const f of files) {
    const img = await loadImage(path.join(CROPS, f));
    const box = rebase(img);
    const b = await band(img, box);
    const base = Frames.findNameRow(b.data, b.w, b.h);
    total++;
    if (!base) baseNull++;

    for (const c of FIXED_CANDIDATES) {
      const r = findRowFixed(b.data, b.w, b.h, c);
      const s = fixedStats.get(c);
      const changedRow = (!!r !== !!base) || (r && base && (r.y !== base.y || r.h !== base.h));
      if (changedRow) s.changed++;
      if (!r) s.nowNull++;
      if (!base && r) s.recoveredFromNull++;
      if (c === 0.85 && changedRow && base) {
        if (sample85.length < 15) sample85.push({ f, baseY: base.y, baseH: base.h, newY: r ? r.y : null, newH: r ? r.h : null });
        if (base.h <= 2) degenerateFixed85++;
        else { plausibleMoved85++; if (moved85.length < 20) moved85.push({ f, base, r }); }
      }
    }
    for (const m of RELATIVE_MARGINS) {
      const { row: r } = findRowRelative(b.data, b.w, b.h, m);
      const s = relStats.get(m);
      const changedRow = (!!r !== !!base) || (r && base && (r.y !== base.y || r.h !== base.h));
      if (changedRow) s.changed++;
      if (!r) s.nowNull++;
      if (!base && r) s.recoveredFromNull++;
    }
    for (const m of RELATIVE_MARGINS) {
      const r = findRowLocalRelative(b.data, b.w, b.h, m);
      const s = localRelStats.get(m);
      const changedRow = (!!r !== !!base) || (r && base && (r.y !== base.y || r.h !== base.h));
      if (changedRow) s.changed++;
      if (!r) s.nowNull++;
      if (!base && r) s.recoveredFromNull++;
    }
  }

  console.log(`${total} r1 strips, ${baseNull} currently null under shipped 0.42 (${(100 * baseNull / total).toFixed(1)}%)\n`);
  console.log('fixed-ceiling candidates (vs shipped-0.42 baseline):');
  for (const c of FIXED_CANDIDATES) {
    const s = fixedStats.get(c);
    console.log(`  ceiling=${c.toFixed(2)}: row differs from baseline on ${s.changed}/${total} (${(100 * s.changed / total).toFixed(1)}%),  still/now null ${s.nowNull},  recovered-from-null ${s.recoveredFromNull}`);
  }
  console.log('\nrelative-ceiling candidates (global median bg, vs shipped-0.42 baseline):');
  for (const m of RELATIVE_MARGINS) {
    const s = relStats.get(m);
    console.log(`  margin=${m.toFixed(2)}: row differs from baseline on ${s.changed}/${total} (${(100 * s.changed / total).toFixed(1)}%),  still/now null ${s.nowNull},  recovered-from-null ${s.recoveredFromNull}`);
  }

  console.log('\nlocal-relative-ceiling candidates (+/-8 row window bg, vs shipped-0.42 baseline):');
  for (const m of RELATIVE_MARGINS) {
    const s = localRelStats.get(m);
    console.log(`  margin=${m.toFixed(2)}: row differs from baseline on ${s.changed}/${total} (${(100 * s.changed / total).toFixed(1)}%),  still/now null ${s.nowNull},  recovered-from-null ${s.recoveredFromNull}`);
  }

  console.log('\nsample of strips where ceiling=0.85 changed an ALREADY-NON-NULL baseline row');
  console.log('(the ones worth eyeballing for a health-bar false-positive, per the original');
  console.log('NAME_FILL_MAX comment\'s "brightest thing in the crop is the health bar" risk):');
  sample85.forEach((s) => {
    console.log(`  ${s.f}: base y=${s.baseY} h=${s.baseH}  ->  0.85 y=${s.newY} h=${s.newH}`);
  });
  console.log(`\nclassification of ALL non-null strips ceiling=0.85 changed: ${degenerateFixed85} were already degenerate (baseline h<=2px, same fragment bug as 2RNA0B) and got a sane row; ${plausibleMoved85} had a plausible-looking baseline row (h>2px) that MOVED - these are the ones that would need an eyeball check for a health-bar false-positive.`);
  moved85.forEach((m) => console.log(`  MOVED ${m.f}: base y=${m.base.y} h=${m.base.h}  ->  0.85 y=${m.r.y} h=${m.r.h}`));

  console.log('\nNOTE: "differs from baseline" is not "wrong" - on the 3 known-bad crops above,');
  console.log('differing from baseline IS the fix working. This count is only useful for the');
  console.log('MAJORITY of strips that are presumed dark-plate-and-fine today; a candidate that');
  console.log('recovers the known-bad crops while touching very few of the rest is the shape of');
  console.log('a good fix. Confirm any real change against tools/real_frame_eval/rowfind_parity.py');
  console.log('on a machine that still has the screenshots/ corpus before shipping.');
}

main().catch((e) => { console.error(e); process.exit(1); });

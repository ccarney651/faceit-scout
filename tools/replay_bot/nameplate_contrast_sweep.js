// tools/replay_bot/nameplate_contrast_sweep.js
// Measurement harness for the SECOND bright-plate bug found while applying
// the fill-ceiling fix in hindsight (PLANS.md P2, 2026-09-15): nameCrop()'s
// contrast stretch, (g-128)*1.5+140, is tuned for a dark plate where glyph
// and background sit far apart in luminance. On a bright/team-coloured
// plate both are already near 255, so the fixed stretch clips both to
// white - the row is found correctly (frames.js's fix works) but there is
// almost nothing left for tesseract to read. A quick spot-check with a
// percentile min-max stretch made the glyphs human-legible but tesseract
// still mostly failed - by eye, the glyph interior is close in luminance to
// the plate and only a thin outline stands out, so tesseract sees a hollow
// letter, not a solid one.
//
// This compares real tesseract OCR (same worker config as run.js) across
// candidate preprocessing strategies, against every "blank-ish" side (>=3 of
// 5 reads empty) in a session that still has an abstained slot with a
// roster to try - not just the couple of examples spot-checked by eye.
// Recovery is measured as: does the OCR text land within STRONG_NAME_SCORE
// of ANY of the map's 10 real players (both teams pooled, so this doesn't
// need to get left/right orientation right to count a genuine read).
//
// Usage: node tools/replay_bot/nameplate_contrast_sweep.js [session-dir...] [--limit N]
//   default: all three known sessions, --limit 25 blank-ish sides each

'use strict';

const fs = require('fs');
const path = require('path');
const { loadImage, createCanvas } = require('@napi-rs/canvas');
const Tesseract = require('tesseract.js');

const REPO = path.join(__dirname, '..', '..');
const Nameplate = require('./nameplate.js');
const Attribute = require('./attribute.js');
const Names = require(path.join(REPO, 'docs/capture/engine/names.js'));

const PAD_Y = 12;
const argv = process.argv.slice(2);
const limitIdx = argv.indexOf('--limit');
const LIMIT = limitIdx >= 0 ? Number(argv[limitIdx + 1]) : 25;
const sessionArgs = argv.filter((a, i) => a !== '--limit' && argv[i - 1] !== '--limit');
const SESSIONS = sessionArgs.length ? sessionArgs : [
  path.join(__dirname, 'out', 'replay-bot-2026-09-15-full'),
  path.join(__dirname, 'out', 'replay-bot-2026-09-12'),
  path.join(__dirname, 'out', 'replay-bot-2026-09-14'),
];

const FEED = JSON.parse(fs.readFileSync(path.join(REPO, 'docs', 'capture', 'data.json'), 'utf8'));
const STRONG = (Names && Names.STRONG_NAME_SCORE) || 75;

function rebaseBox(img) {
  return { x: 0, y: PAD_Y, w: img.width, h: img.height - 2 * PAD_Y };
}

function firstFramePath(map, side) {
  const frames = map.frames || {};
  const keys = Object.keys(frames).map(Number).sort((a, b) => a - b);
  for (const k of keys) {
    const f = frames[String(k)];
    if (f && f[side]) return f[side];
  }
  return null;
}

// --- candidate crop preprocessors ------------------------------------------
// All take (img, cell, row) like Nameplate.nameCrop and return a canvas.

function baselineCrop(img, cell, row) {
  return Nameplate.nameCrop(img, cell, row);
}

function grayscaleUpscale(img, cell, row) {
  // Shared setup for the two adaptive strategies: crop to the glyph span
  // (reusing Nameplate.cellNameSpan, the same targeting nameCrop uses),
  // upscale 6x, return the raw (un-contrast-adjusted) luminance buffer.
  const padX = Math.max(4, Math.round(cell.w * 0.05));
  let sx = Math.max(0, cell.x - padX), sw = cell.w + 2 * padX;
  const span = Nameplate.cellNameSpan(img, cell, row);
  if (span) { sx = span.x; sw = span.w; }
  const sc = 6;
  const cv = createCanvas(Math.max(1, Math.round(sw * sc)), Math.max(1, Math.round(row.h * sc)));
  const cx = cv.getContext('2d', { willReadFrequently: true });
  cx.imageSmoothingEnabled = true; cx.imageSmoothingQuality = 'high';
  cx.drawImage(img, sx, row.y, sw, row.h, 0, 0, cv.width, cv.height);
  const im = cx.getImageData(0, 0, cv.width, cv.height);
  const d = im.data;
  const lum = new Float32Array(d.length / 4);
  for (let i = 0, p = 0; p < d.length; i++, p += 4) lum[i] = 0.299 * d[p] + 0.587 * d[p + 1] + 0.114 * d[p + 2];
  return { cv, cx, im, d, lum, w: cv.width, h: cv.height };
}

// A. percentile min-max stretch (the quick spot-check from earlier).
function percentileStretchCrop(img, cell, row) {
  const g = grayscaleUpscale(img, cell, row);
  const sorted = Array.from(g.lum).sort((a, b) => a - b);
  const lo = sorted[Math.floor(sorted.length * 0.02)];
  const hi = sorted[Math.floor(sorted.length * 0.98)];
  const range = Math.max(1, hi - lo);
  for (let i = 0, p = 0; p < g.d.length; i++, p += 4) {
    const v = Math.max(0, Math.min(255, (g.lum[i] - lo) * 255 / range));
    g.d[p] = g.d[p + 1] = g.d[p + 2] = v;
  }
  g.cx.putImageData(g.im, 0, 0);
  return g.cv;
}

// B. percentile stretch + morphological close (dilate then erode with a
// small box-max/box-min) to solidify a hollow/outlined glyph into a filled
// one, which is what tesseract is actually trained to read.
function grayDilate(lum, w, h, r) {
  const out = new Float32Array(lum.length);
  for (let y = 0; y < h; y++) for (let x = 0; x < w; x++) {
    let m = 0;
    for (let dy = -r; dy <= r; dy++) for (let dx = -r; dx <= r; dx++) {
      const yy = y + dy, xx = x + dx;
      if (yy < 0 || yy >= h || xx < 0 || xx >= w) continue;
      const v = lum[yy * w + xx]; if (v > m) m = v;
    }
    out[y * w + x] = m;
  }
  return out;
}
function grayErode(lum, w, h, r) {
  const out = new Float32Array(lum.length);
  for (let y = 0; y < h; y++) for (let x = 0; x < w; x++) {
    let m = 255;
    for (let dy = -r; dy <= r; dy++) for (let dx = -r; dx <= r; dx++) {
      const yy = y + dy, xx = x + dx;
      if (yy < 0 || yy >= h || xx < 0 || xx >= w) continue;
      const v = lum[yy * w + xx]; if (v < m) m = v;
    }
    out[y * w + x] = m;
  }
  return out;
}
function percentileCloseCrop(img, cell, row) {
  const g = grayscaleUpscale(img, cell, row);
  const sorted = Array.from(g.lum).sort((a, b) => a - b);
  const lo = sorted[Math.floor(sorted.length * 0.02)];
  const hi = sorted[Math.floor(sorted.length * 0.98)];
  const range = Math.max(1, hi - lo);
  let stretched = new Float32Array(g.lum.length);
  for (let i = 0; i < g.lum.length; i++) stretched[i] = Math.max(0, Math.min(255, (g.lum[i] - lo) * 255 / range));
  // Close = dilate then erode. Radius ~ a stroke width at 6x upscale (glyph
  // strokes land ~6-10px wide at 6x from a ~1-2px native stroke).
  const r = 3;
  const closed = grayErode(grayDilate(stretched, g.w, g.h, r), g.w, g.h, r);
  for (let i = 0, p = 0; p < g.d.length; i++, p += 4) { g.d[p] = g.d[p + 1] = g.d[p + 2] = closed[i]; }
  g.cx.putImageData(g.im, 0, 0);
  return g.cv;
}

const STRATEGIES = {
  baseline: baselineCrop,
  percentile: percentileStretchCrop,
  'percentile+close': percentileCloseCrop,
};

async function ocr(worker, cv) {
  const { data } = await worker.recognize(cv.toBuffer('image/png'));
  return data.text.trim();
}

function bestScore(read, names) {
  let best = 0;
  for (const n of names) { const s = Names.simScore(read || '', n); if (s > best) best = s; }
  return best;
}

async function main() {
  const worker = await Tesseract.createWorker('eng');
  await worker.setParameters({
    tessedit_char_whitelist:
      'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789',
    // Matches run.js's shipped worker config (2026-09-15: PSM 8, "single
    // word" - see its comment). Keep this sweep's baseline in step with
    // production or its numbers stop meaning anything.
    tessedit_pageseg_mode: '8',
  });

  const totals = {};
  Object.keys(STRATEGIES).forEach((k) => { totals[k] = { slots: 0, strong: 0 }; });
  let casesChecked = 0;

  for (const sessionDir of SESSIONS) {
    const reviewPath = sessionDir + '.review.json';
    if (!fs.existsSync(reviewPath)) { console.log(`(skip, no review artifact: ${reviewPath})`); continue; }
    const review = JSON.parse(fs.readFileSync(reviewPath, 'utf8'));
    let taken = 0;
    for (const m of review.maps) {
      if (taken >= LIMIT) break;
      if (!m.attribution) continue;
      if ((m.corrections || []).length) continue;
      const codeObj = { match_id: m.match_id, game_no: m.game_no, t1: m.side_a_team_id, t2: m.side_b_team_id };
      const t1players = Attribute.playersFor(FEED, codeObj, 'a');
      const t2players = Attribute.playersFor(FEED, codeObj, 'b');
      const pool = Attribute.rosterNames(t1players).concat(Attribute.rosterNames(t2players));
      if (!pool.length) continue;

      for (const side of ['a', 'b']) {
        if (taken >= LIMIT) break;
        const ids = (m.attribution[side] && m.attribution[side].ids) || [];
        const reads = (m.attribution.reads && m.attribution.reads[side]) || [];
        const hasNull = ids.some((x) => x == null);
        const mostlyBlank = reads.filter((x) => !x || !x.trim()).length >= 3;
        if (!hasNull || !mostlyBlank) continue;

        const framePath = firstFramePath(m, side);
        if (!framePath) continue;
        const full = path.join(sessionDir, framePath);
        if (!fs.existsSync(full)) continue;
        const img = await loadImage(full);
        const box = rebaseBox(img);
        const row = Nameplate.nameRow(img, box);
        if (!row) continue;
        const cw = box.w / 5;

        taken++; casesChecked++;
        const perStrategy = {};
        for (const [name, fn] of Object.entries(STRATEGIES)) {
          let strong = 0;
          for (let i = 0; i < 5; i++) {
            const cell = { x: i * cw, y: box.y, w: cw, h: box.h };
            const cv = fn(img, cell, row);
            const text = await ocr(worker, cv);
            const s = bestScore(text, pool);
            totals[name].slots++;
            if (s >= STRONG) { totals[name].strong++; strong++; }
          }
          perStrategy[name] = strong;
        }
        console.log(`${path.basename(sessionDir)} ${path.basename(framePath)} side=${side}: ` +
          Object.entries(perStrategy).map(([k, v]) => `${k}=${v}/5`).join('  '));
      }
    }
  }

  await worker.terminate();

  console.log(`\n${casesChecked} blank-ish sides checked (5 slots each = ${casesChecked * 5} OCR calls per strategy)\n`);
  Object.entries(totals).forEach(([name, t]) => {
    console.log(`${name.padEnd(20)} ${t.strong}/${t.slots} slots landed within STRONG_NAME_SCORE (${STRONG}) of a real player (${(100 * t.strong / Math.max(1, t.slots)).toFixed(1)}%)`);
  });
}

main().catch((e) => { console.error(e); process.exit(1); });

// tools/replay_bot/match_search_sweep.js
// Regression sweep for the widened alignment search.
//
// The wider window buys back the mis-aligned portraits, but a wider window can
// also, in principle, let a WRONG hero win - which is the well-formed-wrong-read
// hazard the replay-code work already paid for once. So: run OLD and NEW over
// every retained strip crop and report every slot whose WINNER CHANGED, plus the
// score distribution either side.
//
// Usage: node tools/replay_bot/match_search_sweep.js [r1,r2,...]
//   default radii: 6,10,14
//
// Each radius needs its own Refs handle (make() captures ctx.search per handle).
// The cost is roughly linear in the probe count, and the probe count is quadratic
// in the radius, so the widest radius dominates the wall clock (~9 min at 14).

'use strict';

const fs = require('fs');
const path = require('path');
const { loadImage } = require('@napi-rs/canvas');

const REPO = path.join(__dirname, '..', '..');
const Crop = require('./crop.js');
const Util = require(path.join(REPO, 'docs/capture/engine/util.js'));
const Refs = require(path.join(REPO, 'docs/capture/engine/refs.js'));

const REFS_JSON = JSON.parse(fs.readFileSync(path.join(REPO, 'docs/capture/refs.json'), 'utf8'));

const BOXES = {
  a: { x: 55.33490566037736, y: 98, w: 706.25, h: 103.97607478673905 },
  b: { x: 1799.3349056603774, y: 95, w: 706.25, h: 108.85047245433347 },
};
const LF = 0.42, TF = 0.45, RF = 0.06, PAD_Y = 12;
const PAD = 2;
const CONF = 0.6;

const RADII = (process.argv[2] ? process.argv[2].split(',').map(Number) : [6, 10, 14]);
if (!RADII.length || RADII.some((r) => !(r > 0))) { console.error('bad radius list'); process.exit(2); }

// Edge probe: take the widest radius's boundary winners (|dx|==R or |dy|==R),
// which is exactly the set that MIGHT be truncated, and re-search them at a much
// wider radius. Cheap because the boundary is a small fraction of the slots -
// 344/10455 at r14 - so the extra handle costs seconds, not minutes. If those
// winners jump outward and gain score, R is truncating; if they barely move, they
// are degenerate crops and R is enough.
const EDGE_PROBES = [20, 28];

global.REF_W = REFS_JSON.w;
global.REF_H = REFS_JSON.h;
global.PAD = PAD;
global.LF = REFS_JSON.left_fraction;
global.TF = REFS_JSON.top_fraction;
global.REFS = [];
global.LOCAL_REFS = [];
global.CUSTOM_HEROES = {};
global.HERO_ICON = {};
Object.keys(Util).forEach((k) => { global[k] = Util[k]; });

const SHIM = { doc: { getElementById: () => null, createElement: () => { throw new Error('no canvas needed'); } } };
const handles = RADII.map((r) => ({ r, m: Refs.make(Object.assign({}, SHIM, { search: r })) }));
const R = handles[0].m;
const WIDEST = RADII[RADII.length - 1];
const edgeHandles = EDGE_PROBES.map((r) => ({ r, m: Refs.make(Object.assign({}, SHIM, { search: r })) }));
const EDGE = EDGE_PROBES.map(() => ({ n: 0, moved: 0, stillEdge: 0, riseSum: 0, confN: 0, confMoved: 0, list: [] }));
REFS_JSON.refs.forEach((rec) => { const t = R.refTemplate(rec); if (t) global.REFS.push(t); });

function oldMatch(b64, side) {
  const px = Util.b64bytes(b64);
  const W = REFS_JSON.w + 2 * PAD;
  const gp = new Float32Array(W * (REFS_JSON.h + 2 * PAD));
  for (let y = 0; y < REFS_JSON.h; y++) {
    for (let x = 0; x < REFS_JSON.w; x++) {
      gp[(y + PAD) * W + (x + PAD)] = px[y * REFS_JSON.w + x];
    }
  }
  return R.bestMatch(gp, side, false);
}

function walk(dir, out) {
  let ents;
  try { ents = fs.readdirSync(dir, { withFileTypes: true }); } catch (e) { return out; }
  ents.forEach((e) => {
    const p = path.join(dir, e.name);
    if (e.isDirectory()) walk(p, out);
    else if (/\.png$/i.test(e.name) && /-([ab])(-s\d+)?\.png$/i.test(e.name)) out.push(p);
  });
  return out;
}

function sideOf(name) { const m = /-([ab])(-s\d+)?\.png$/i.exec(name); return m ? m[1].toLowerCase() : null; }

function stats() {
  return { low: 0, edge: 0, changed: 0, confFlip: 0, vsBase: 0, time: 0, flips: [], offs: new Map(), perHero: new Map() };
}

async function main() {
  const strips = walk(path.join(__dirname, 'out'), []);
  console.log(`${strips.length} retained strip crops   radii: ${RADII.join(', ')}`);

  const changes = [];
  const S = RADII.map(() => stats());
  const base = S[0];
  let slots = 0, oldOut = 0, confident = 0;
  let oldTime = 0;

  for (const strip of strips) {
    const side = sideOf(path.basename(strip));
    const box = BOXES[side];
    if (!box) continue;
    let img;
    try { img = await loadImage(strip); } catch (e) { continue; }
    const cw = box.w / 5;
    for (let i = 0; i < 5; i++) {
      const cell = { x: box.x + i * cw + cw * LF, y: box.y, w: cw * (1 - LF - RF), h: box.h * TF };
      const r = { x: cell.x - box.x, y: cell.y - (box.y - PAD_Y), w: cell.w, h: cell.h };
      const b64 = Crop.cell(img, r, { REF_W: REFS_JSON.w, REF_H: REFS_JSON.h });

      let t = Date.now(); const o = oldMatch(b64, side); oldTime += Date.now() - t;
      const outs = handles.map((h, k) => {
        t = Date.now(); const x = h.m.matchCrop(b64, side); S[k].time += Date.now() - t; return x;
      });

      slots++;
      if (o.score < CONF) oldOut++;
      if (o.score >= CONF) confident++;

      outs.forEach((x, k) => {
        const s = S[k], rad = RADII[k];
        if (x.score < CONF) s.low++;
        if (Math.abs(x.dx) === rad || Math.abs(x.dy) === rad) s.edge++;
        if (x.name !== o.name) {
          s.changed++;
          if (o.score >= CONF) { s.confFlip++; if (s.flips.length < 15) s.flips.push({ strip: path.basename(strip), side, slot: i, old: o.name, oldScore: o.score, now: x.name, newScore: x.score, dx: x.dx, dy: x.dy }); }
        }
        if (k > 0 && (x.name !== outs[0].name || Math.abs(x.score - outs[0].score) > 0.02)) s.vsBase++;
        const ok = x.dx + ',' + x.dy;
        s.offs.set(ok, (s.offs.get(ok) || 0) + 1);
        const hk = x.name;
        if (!s.perHero.has(hk)) s.perHero.set(hk, { n: 0, sum: 0, low: 0, oldSum: 0 });
        const hh = s.perHero.get(hk); hh.n++; hh.sum += x.score; hh.oldSum += o.score; if (x.score < CONF) hh.low++;
      });

      const w = outs[outs.length - 1];
      if (Math.abs(w.dx) === WIDEST || Math.abs(w.dy) === WIDEST) {
        edgeHandles.forEach((eh, j) => {
          const p = eh.m.matchCrop(b64, side);
          const e = EDGE[j];
          e.n++;
          if (w.score >= CONF) e.confN++;
          if (p.name !== w.name) {
            e.moved++;
            if (w.score >= CONF) e.confMoved++;
            if (e.list.length < 12) e.list.push({ strip: path.basename(strip), side, slot: i, from: w.name, fromScore: w.score, to: p.name, toScore: p.score, dx: p.dx, dy: p.dy });
          }
          if (Math.abs(p.dx) === EDGE_PROBES[j] || Math.abs(p.dy) === EDGE_PROBES[j]) e.stillEdge++;
          e.riseSum += (p.score - w.score);
        });
      }

      if (o.name !== outs[0].name) changes.push({ strip: path.basename(strip), side, slot: i, old: o.name, oldScore: o.score, now: outs[0].name, newScore: outs[0].score, dx: outs[0].dx, dy: outs[0].dy });
    }
  }

  const pct = (n) => (100 * n / Math.max(1, slots)).toFixed(1);
  console.log(`slots compared: ${slots}`);
  console.log(`low-score (<${CONF}) slots: old ${oldOut}/${slots} (${pct(oldOut)}%)`);

  console.log(`\nRANGE CHECK (which radius?)`);
  RADII.forEach((rad, k) => {
    const s = S[k];
    const baseNote = k === 0 ? 'base' : `${s.vsBase} disagree with r${RADII[0]} (${pct(s.vsBase)}%)`;
    console.log(`  radius ${String(rad).padStart(2)} : edge ${s.edge} (${pct(s.edge)}%),  low ${s.low} (${pct(s.low)}%),  ` +
      `changed-from-old ${s.changed},  confident-flips ${s.confFlip} (of ${confident}, ${pct(s.confFlip)}%),  ${s.time}ms  |  ${baseNote}`);
  });

  console.log(`\nEDGE PROBE (is r${WIDEST} truncating?) - re-searched only the ${S[S.length - 1].edge} boundary winners of r${WIDEST} at a wider radius`);
  EDGE_PROBES.forEach((pr, j) => {
    const e = EDGE[j];
    if (!e.n) { console.log(`  radius ${pr}: no boundary slots to probe`); return; }
    console.log(`  radius ${pr}: winner moved on ${e.moved}/${e.n} (${(100 * e.moved / e.n).toFixed(1)}%),  still at the +/-${pr} edge ${e.stillEdge},  ` +
      `mean score change ${(e.riseSum / e.n).toFixed(3)};  confident boundary ${e.confN}, of those moved ${e.confMoved}`);
    e.list.forEach((c) => console.log(`    >> ${c.strip} ${c.side}${c.slot}: ${c.from} ${c.fromScore.toFixed(3)} -> ${c.to} ${c.toScore.toFixed(3)} at (${c.dx},${c.dy})`));
  });

  console.log(`\nconfident-flip hazard by radius (old >= ${CONF} but winner changed):`);  RADII.forEach((rad, k) => {
    const s = S[k];
    if (!s.flips.length) { console.log(`  radius ${rad}: none`); return; }
    console.log(`  radius ${rad}: ${s.confFlip}`);
    s.flips.forEach((c) => console.log(`    !! ${c.strip} ${c.side}${c.slot}: ${c.old} ${c.oldScore.toFixed(3)} -> ${c.now} ${c.newScore.toFixed(3)} at (${c.dx},${c.dy})`));
  });

  console.log(`\noffset histogram (top 12) per radius:`);
  RADII.forEach((rad, k) => {
    const top = [...S[k].offs.entries()].sort((a, b) => b[1] - a[1]).slice(0, 12);
    const atEdge = S[k].edge;
    console.log(`  radius ${rad}: ${top.map(([o, n]) => `${o}:${n}`).join('  ')}   [edge total ${atEdge}]`);
  });

  console.log(`\nhero means  (n, old, r${RADII[0]}, r${RADII[RADII.length - 1]}, ...)`);
  const names = [...base.perHero.keys()].filter((k) => base.perHero.get(k).n >= 8)
    .sort((a, b) => (base.perHero.get(b).oldSum / base.perHero.get(b).n) - (base.perHero.get(a).oldSum / base.perHero.get(a).n));
  const rhdr = RADII.map((r) => `r${r}`.padStart(7)).join('');
  console.log(`hero                 n    old${rhdr}`);
  names.forEach((k) => {
    const b = base.perHero.get(k);
    const cells = RADII.map((rad, j) => (S[j].perHero.get(k) ? (S[j].perHero.get(k).sum / S[j].perHero.get(k).n).toFixed(3).padStart(7) : '   n/a ')).join('');
    console.log(`${String(k).padEnd(18)} ${String(b.n).padStart(4)}  ${(b.oldSum / b.n).toFixed(3)}${cells}`);
  });

  console.log(`\nsearch time: old ${oldTime}ms  ` + RADII.map((r, k) => `${r}px ${S[k].time}ms (${(S[k].time / Math.max(1, slots)).toFixed(1)}ms/slot)`).join('  '));
}

main().catch((e) => { console.error(e); process.exit(1); });

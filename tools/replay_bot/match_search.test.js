// tools/replay_bot/match_search.test.js
// Guards the widened alignment search in docs/capture/engine/refs.js.
//
// The corpus sweep (match_search_sweep.js) measures the effect on real frames,
// but it needs the retained corpus and ~12 minutes. These tests pin the
// BEHAVIOUR with a synthetic library instead, so a regression trips in
// milliseconds:
//
//   - the LEGACY path (bestMatch with radius==null, what the two capture pages
//     call) still searches only +/-PAD and is still centre-only when fast;
//   - matchCrop recovers a crop translated by N px, for N up to the radius;
//   - matchCrop on an untranslated crop returns the centre winner, i.e. the
//     edge-clamped border does not bias a clean crop off-centre;
//   - matchCrop only ever scores same-side references.
//
// refs.js resolves REF_W/REF_H/PAD/REFS and util.js's helpers as FREE VARIABLES
// against globalThis under CommonJS - the same contract the pages honour (see
// match.js's header). Publish them here the same way match.js does.

'use strict';

const test = require('node:test');
const assert = require('node:assert');
const U = require('../../docs/capture/engine/util.js');
const Refs = require('../../docs/capture/engine/refs.js');

const W = 64, H = 36, PAD = 2;
const SHIM = { getElementById: () => null, createElement: () => { throw new Error('no canvas on the matching path'); } };

// A deterministic portrait-like pattern: a coarse random field bilinearly
// upsampled, so neighbouring pixels correlate (as an anti-aliased portrait
// does) while the peak stays sharp enough to have an unambiguous location.
//
// Deliberately NOT pixel-random: a 1px-pitch noise field has a correlation peak
// narrower than the search's own 2px coarse step, so the coarse pass samples
// only decorrelated positions and can miss an odd offset. Real portraits are
// anti-aliased and the 10455-slot corpus is recovered correctly; a sharper-than-
// real fixture would test the fixture, not the matcher.
function pattern(seed, cell) {
  const gw = Math.ceil(W / cell) + 1, gh = Math.ceil(H / cell) + 1;
  let s = seed >>> 0;
  const g = new Float32Array(gw * gh);
  for (let i = 0; i < g.length; i++) { s = (s * 1664525 + 1013904223) >>> 0; g[i] = (s >>> 24) & 0xff; }
  const px = new Uint8Array(W * H);
  for (let y = 0; y < H; y++) {
    for (let x = 0; x < W; x++) {
      const gx = Math.min(gw - 2, Math.floor(x / cell)), gy = Math.min(gh - 2, Math.floor(y / cell));
      const fx = (x - gx * cell) / cell, fy = (y - gy * cell) / cell;
      const i00 = gy * gw + gx, i10 = i00 + 1, i01 = i00 + gw, i11 = i01 + 1;
      const v = (g[i00] * (1 - fx) + g[i10] * fx) * (1 - fy) + (g[i01] * (1 - fx) + g[i11] * fx) * fy;
      px[y * W + x] = Math.round(v);
    }
  }
  return px;
}

// The reference as it appears in a live crop: shifted by (tx,ty) with the
// shifted-in edge repeated (the HUD has no black band there). This is the
// inverse of what matchCrop must recover, per its own construction.
function shiftClamp(px, tx, ty) {
  const out = new Uint8Array(W * H);
  for (let y = 0; y < H; y++) {
    for (let x = 0; x < W; x++) {
      const sx = Math.min(W - 1, Math.max(0, x - tx));
      const sy = Math.min(H - 1, Math.max(0, y - ty));
      out[y * W + x] = px[sy * W + sx];
    }
  }
  return out;
}

// The OLD matchCrop candidate: the crop centred in a ZERO-filled PAD border.
function zeroPadded(px) {
  const w2 = W + 2 * PAD;
  const gp = new Float32Array(w2 * (H + 2 * PAD));
  for (let y = 0; y < H; y++) for (let x = 0; x < W; x++) gp[(y + PAD) * w2 + (x + PAD)] = px[y * W + x];
  return gp;
}

global.REF_W = W;
global.REF_H = H;
global.PAD = PAD;
global.LF = 0.42;
global.TF = 0.45;
global.REFS = [];
global.LOCAL_REFS = [];
global.CUSTOM_HEROES = {};
global.HERO_ICON = {};
Object.keys(U).forEach((k) => { global[k] = U[k]; });

// No ctx.search -> the shipped default radius is what is under test.
const R = Refs.make({ doc: SHIM });

const PAT_A = pattern(1, 4);
const PAT_B = pattern(2, 4);
function bake(name, guid, variant, px) {
  const t = R.refTemplate({ n: name, g: guid, v: variant, d: U.bytesToB64(px) });
  assert.ok(t, 'synthetic ref bakes');
  global.REFS.push(t);
}
bake('Alpha', 'gA', 'a', PAT_A);
bake('Beta', 'gB', 'a', PAT_B);

test('legacy path (radius==null) still identifies a centred crop at offset 0', () => {
  const r = R.bestMatch(zeroPadded(PAT_A), 'a', false);
  assert.strictEqual(r.name, 'Alpha');
  assert.strictEqual(r.dx, 0);
  assert.strictEqual(r.dy, 0);
  assert.ok(r.score > 0.999, `self-match should be ~1.0, got ${r.score}`);
});

test('legacy path can never search past +/-PAD', () => {
  // The crop sits 4px off centre: the old three-step window cannot reach it.
  const r = R.bestMatch(zeroPadded(shiftClamp(PAT_A, 4, 0)), 'a', false);
  assert.ok(Math.abs(r.dx) <= PAD && Math.abs(r.dy) <= PAD, `legacy searched to (${r.dx},${r.dy})`);
});

test('fast=true is centre-only, even when a shifted position would score higher', () => {
  const gp = zeroPadded(shiftClamp(PAT_A, 4, 0));
  const fast = R.bestMatch(gp, 'a', true);
  assert.ok(fast.dx === 0 && fast.dy === 0, `fast searched to (${fast.dx},${fast.dy})`);
  const full = R.bestMatch(gp, 'a', false);
  assert.ok(fast.score <= full.score, 'centre-only cannot beat the searched offset');
});

test('matchCrop on an untranslated crop returns the centre winner', () => {
  // Regression guard for the edge-clamped border: a large pad must not let the
  // clamp invent an offset for a crop that is already aligned.
  const r = R.matchCrop(U.bytesToB64(PAT_A), 'a');
  assert.strictEqual(r.name, 'Alpha');
  assert.ok(r.dx === 0 && r.dy === 0, `offset (${r.dx},${r.dy})`);
  assert.ok(r.score > 0.999, `self-match should be ~1.0, got ${r.score}`);
});

test('matchCrop recovers a translation up to the search radius', () => {
  const cases = [[1, 0], [2, 1], [4, 1], [6, 0], [-6, 1], [8, 0], [-10, 1], [12, 2], [10, -4], [0, 3]];
  for (const [tx, ty] of cases) {
    const got = R.matchCrop(U.bytesToB64(shiftClamp(PAT_A, tx, ty)), 'a');
    assert.strictEqual(got.name, 'Alpha', `(${tx},${ty}) should read Alpha, got ${got.name}`);
    assert.ok(got.dx === tx, `(${tx},${ty}) x offset came back ${got.dx}`);
    assert.ok(got.dy === ty, `(${tx},${ty}) y offset came back ${got.dy}`);
  }
});

test('the shipped radius reaches 10+ px, which the old +/-2 window could not', () => {
  // A 10px horizontal translation is far outside the legacy window and outside
  // any radius below 10. If MATCH_SEARCH is ever lowered back toward 6 this
  // fails, which is the point - see the rationale comment in refs.js.
  const got = R.matchCrop(U.bytesToB64(shiftClamp(PAT_A, 10, 0)), 'a');
  assert.strictEqual(got.name, 'Alpha');
  assert.strictEqual(got.dx, 10);
});

test('matchCrop only scores same-side references', () => {
  const got = R.matchCrop(U.bytesToB64(PAT_A), 'b');
  assert.strictEqual(got.guid, null, 'no variant-b refs exist, so nothing may match');
  assert.strictEqual(got.name, '?');
});

test('a translation beyond the radius is clamped, not invented', () => {
  const far = shiftClamp(PAT_A, 20, 0);
  const got = R.matchCrop(U.bytesToB64(far), 'a');
  assert.ok(Math.abs(got.dx) <= 14 && Math.abs(got.dy) <= 14, `offset (${got.dx},${got.dy}) escaped the search window`);
});

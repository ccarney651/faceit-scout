const test = require('node:test');
const assert = require('node:assert');
const Frames = require('./frames.js');

// A synthetic five-slot strip with the three things that actually sit in the
// search band on a real HUD, in their real order:
//
//   the bottom of the hero portraits   - busy, coloured, no quiet rows
//   the name row                       - white glyphs on a dark plate
//   the health bars                    - one solid bright run per player
//
// Both of the shortcuts that were tried and reverted before this locator
// existed are represented here: the bars are BRIGHTER than the names (so "find
// the bar, take the band above it" and "take the brightest band" both fail) and
// the portrait art sits ABOVE the names (so "take the topmost strong band"
// fails). See tools/real_frame_eval/README.md.
const W = 300, H = 90;
const PORTRAIT = [0, 26];    // rows
const NAMES = [40, 53];      // rows - the answer
const BARS = [66, 76];       // rows

function strip(opts) {
  const o = opts || {};
  const d = new Uint8ClampedArray(W * H * 4).fill(255);
  const px = (x, y, v) => {
    const i = (y * W + x) * 4;
    d[i] = d[i + 1] = d[i + 2] = v; d[i + 3] = 255;
  };
  for (let y = 0; y < H; y++) for (let x = 0; x < W; x++) px(x, y, 40);
  // Portrait art: dense pseudo-random mid-tones, no quiet rows around it.
  // `bright` blows the parts of the band that are not the dark name plate out
  // to white, the way a bright map behind a translucent HUD does.
  let seed = 7;
  for (let y = PORTRAIT[0]; y <= PORTRAIT[1]; y++) {
    for (let x = 0; x < W; x++) {
      seed = (seed * 1103515245 + 12345) & 0x7fffffff;
      px(x, y, o.bright ? 250 + (seed % 6) : 90 + (seed % 130));
    }
  }
  if (o.bright) {
    for (let y = BARS[1] + 1; y < H; y++) for (let x = 0; x < W; x++) px(x, y, 255);
  }
  // Names: five words of 4px glyph strokes with 4px gaps, on the dark plate.
  if (!o.noNames) {
    for (let s = 0; s < 5; s++) {
      for (let g = 0; g < 6; g++) {
        const x0 = s * 60 + 12 + g * 8;
        for (let x = x0; x < x0 + 4; x++) {
          for (let y = NAMES[0]; y <= NAMES[1]; y++) px(x, y, 250);
        }
      }
    }
  }
  // Health bars: one bright run per slot, brighter and far wider than the text.
  for (let s = 0; s < 5; s++) {
    for (let x = s * 60 + 4; x < s * 60 + 56; x++) {
      for (let y = BARS[0]; y <= BARS[1]; y++) px(x, y, 255);
    }
  }
  return d;
}

test('finds the name row, not the brighter health bars below it', () => {
  const r = Frames.findNameRow(strip(), W, H);
  assert.ok(r, 'expected a row');
  assert.ok(Math.abs(r.y - NAMES[0]) <= 1, `top ${r.y}, want ~${NAMES[0]}`);
  assert.ok(Math.abs(r.y + r.h - 1 - NAMES[1]) <= 1, `bottom ${r.y + r.h - 1}, want ~${NAMES[1]}`);
});

test('finds the name row, not the busy portrait art above it', () => {
  const r = Frames.findNameRow(strip(), W, H);
  assert.ok(r.y > PORTRAIT[1], `picked the portrait band at y=${r.y}`);
});

test('a bright scene behind the HUD does not blank the threshold', () => {
  // The 88th percentile of a mostly-white band is 255, and `luma > 255` selects
  // nothing at all. Four real box variants in the sweep hit exactly this.
  const r = Frames.findNameRow(strip({ bright: true }), W, H);
  assert.ok(r, 'expected a row on a bright background');
  assert.ok(Math.abs(r.y - NAMES[0]) <= 1, `top ${r.y}, want ~${NAMES[0]}`);
});

test('returns null on a featureless band instead of inventing a row', () => {
  // Flat black: nothing crosses the threshold anywhere, so there is no run to
  // pick. A null tells nameCanvas() to fall back to the old fixed fractions.
  const d = new Uint8ClampedArray(W * H * 4).fill(0);
  for (let i = 3; i < d.length; i += 4) d[i] = 255;
  assert.equal(Frames.findNameRow(d, W, H), null);
});

test('with the names absent it still returns its best candidate', () => {
  // Documenting a real limit rather than pretending it away: the locator picks
  // the most text-like run in the band, and cannot tell that no run is a name.
  // Strip the names and it hands back the portrait bottom. Nothing downstream
  // trusts it blindly - the crop OCRs as garbage and assign.js's FLOOR makes
  // the slot abstain, exactly as it would for any unreadable HUD.
  const r = Frames.findNameRow(strip({ noNames: true }), W, H);
  assert.ok(r && r.y < NAMES[0], 'expected the portrait band, not the name row');
});

test('guards degenerate input', () => {
  assert.equal(Frames.findNameRow(new Uint8ClampedArray(0), 0, 0), null);
  assert.equal(Frames.findNameRow(new Uint8ClampedArray(16), 10, 10), null);
  assert.equal(Frames.findNameRow(null, 10, 10), null);
});

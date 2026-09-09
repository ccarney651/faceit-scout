// Detector regressions against real frames. See corpus.js for how they were
// labelled, and frames/README.md for why they are not in git.
const test = require('node:test');
const assert = require('node:assert');
const canvas = require('@napi-rs/canvas');
const C = require('./corpus.js');
const calib = require('./calib.js');
const Crop = require('./crop.js');
const S = require('./screen.js');
const esc = require('./screens/esc-menu.json');

const skip = C.absent() || false;

const load = (p) => canvas.loadImage(p);

test('every witness frame is the resolution the geometry was frozen at', { skip }, async () => {
  for (const name of Object.keys(C.WITNESSES)) {
    const img = await load(C.file(name));
    assert.deepStrictEqual(calib.check({ w: img.width, h: img.height }).ok, true, name);
  }
});

// THE DETECTOR THIS REPLACED WAS RIGHT ABOUT BRIGHT MAPS AND WRONG ABOUT DARK
// ONES, AND THAT COST CODES. A flatness reading alone calls a night sky, a
// loading screen and the ESC menu open panels, because all three are smooth.
test('the events panel is read open exactly where it is open', { skip }, async () => {
  const wrong = [];
  for (const p of C.panels()) {
    const img = await load(C.at(p.file));
    const said = calib.eventsViewerOpen(Crop.panelRowFraction(img, calib));
    if (said !== p.open) wrong.push(p.file + ' is ' + (p.open ? 'open' : 'shut') + ', read ' + said);
  }
  assert.deepStrictEqual(wrong, []);
});

test('the panel reading separates open from shut with room on both sides', { skip }, async () => {
  let worstOpen = 1, bestShut = 0;
  for (const p of C.panels()) {
    const v = Crop.panelRowFraction(await load(C.at(p.file)), calib);
    if (p.open) worstOpen = Math.min(worstOpen, v);
    else bestShut = Math.max(bestShut, v);
  }
  const t = calib.FROZEN.eventsPanel.minPanelRows;
  assert.ok(bestShut < t, 'the highest shut reading (' + bestShut.toFixed(3) + ') must sit under ' + t);
  assert.ok(worstOpen > t, 'the lowest open reading (' + worstOpen.toFixed(3) + ') must sit over ' + t);
  assert.ok(worstOpen / Math.max(bestShut, 0.001) > 5, 'and the gap must be wide, not a hair');
});

// The media controls hide themselves, so a replay is often on screen with no
// playhead drawn at all. Reading "is this a replay" off the bar was worth two
// codes before the tint answered it instead.
test('a replay is recognised while the media controls are down', { skip }, async () => {
  const img = await load(C.file('assemble'));
  assert.strictEqual(Crop.playheadX(img, calib), null, 'no bar is drawn here');
  assert.strictEqual(calib.hudPresent(Crop.hudTint(img, calib)), true);
});

test('a loading screen is not mistaken for a replay', { skip }, async () => {
  for (const name of ['loading', 'black', 'esc-menu']) {
    const tint = Crop.hudTint(await load(C.file(name)), calib);
    assert.strictEqual(calib.hudPresent(tint), false, name);
  }
});

// The tint threshold is 15 and the dimmest real replay frame here reads 15.1.
// That is not a margin, it is a coincidence, and the comment in calib.js
// claiming 29 was written before this frame existed. Pinned so that a threshold
// raised without measuring fails here instead of on a live code.
test('the dimmest replay frame clears the tint threshold, barely', { skip }, async () => {
  const tint = Crop.hudTint(await load(C.file('panel-open')), calib);
  const margin = Math.min(tint.a, tint.b) - calib.HUD_TINT;
  assert.ok(margin > 0, 'a real replay must read as one');
  assert.ok(margin < 1, 'and this frame is the one that says how little room is left: ' + margin.toFixed(1));
});

test('two frames of the ESC menu are the same screen, and a replay is not', { skip }, async () => {
  const print = async (n) => S.thumb(await load(C.file(n)));
  assert.strictEqual(S.looksLike(await print('esc-menu'), esc.thumb).same, true);
  assert.strictEqual(S.looksLike(await print('esc-menu-again'), esc.thumb).same, true);
  for (const n of ['panel-open', 'panel-shut-bright', 'assemble', 'loading']) {
    assert.strictEqual(S.looksLike(await print(n), esc.thumb).same, false, n);
  }
});

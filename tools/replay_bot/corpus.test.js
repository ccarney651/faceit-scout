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

// THE READING MUST NOT DEPEND ON HOW MANY ROUNDS THE MAP HAS. Push and
// Flashpoint have one long round, Control up to three, Escort and Hybrid at
// least two - so a reading taken off the ROUND rows means something different
// on every map type. It read 0.170 on a live one-round map against a threshold
// of 0.15, where the three-round frames read 0.340 and up. The panel's two
// dropdowns are there whatever the map, which is what is measured instead.
test('the panel reads the same on a one-round map as on a three-round one', { skip }, async () => {
  const oneRound = Crop.panelRowFraction(await load(C.at('probe-panelopen-live.png')), calib);
  const threeRound = Crop.panelRowFraction(await load(C.at('cap-panel-13.png')), calib);
  assert.ok(oneRound > 0.4, 'a one-round panel is still plainly a panel: ' + oneRound.toFixed(3));
  assert.ok(Math.abs(oneRound - threeRound) < 0.2,
    'and reads close to a three-round one (' + oneRound.toFixed(3) + ' vs ' + threeRound.toFixed(3) + ')');
});

// The only open/shut pair taken on one map seconds apart, with nothing else
// changed - so the difference between them is the panel and nothing else.
test('one K press is the whole difference between open and shut', { skip }, async () => {
  const open = Crop.panelRowFraction(await load(C.at('probe-panelopen-live.png')), calib);
  const shut = Crop.panelRowFraction(await load(C.at('probe-panelshut-live.png')), calib);
  assert.strictEqual(calib.eventsViewerOpen(open), true);
  assert.strictEqual(calib.eventsViewerOpen(shut), false);
  assert.strictEqual(shut, 0, 'a shut panel registers nothing at all, not a little');
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
  // A ratio was the wrong thing to assert. The replay list reads 0.022 - real,
  // harmless, and enough to collapse any ratio - while what actually matters is
  // that the threshold has room on BOTH sides of it.
  assert.ok(bestShut < t / 2,
    'the highest shut reading (' + bestShut.toFixed(3) + ') must sit well under ' + t);
  assert.ok(worstOpen > t * 1.5,
    'and the lowest open one (' + worstOpen.toFixed(3) + ') well over it');
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

// The measure used to be taken over the whole plate box, which catches the name
// plates, the health pips and whatever the map shows between the cells. On a
// bright blue map that cancelled team B's red entirely: 4.8 against a threshold
// of 15, on a replay that was on screen at the time. run.js reads exactly this
// to decide whether a replay loaded, waited 90 seconds, gave up, and spent the
// code - which is what happened to RCR3NK.
//
// GRADED AGAINST WHAT SOMEBODY SAW, NOT AGAINST THE OPEN PANEL. An earlier
// version of this took "the events viewer is open" to mean "a replay is
// readable", on the reasoning that the panel only exists inside a replay. The
// panel does - but the PLATES take a moment to paint after a seek, and a frame
// caught in that moment has an open panel, a playhead, and nothing at all where
// the portraits go. `mid-seek` is one. So the label is the human one.
test('a replay reads as a replay, and a frame without plates does not', { skip }, async () => {
  const wrong = [];
  for (const name of Object.keys(C.WITNESSES)) {
    const w = C.WITNESSES[name];
    const tint = Crop.hudTint(await load(C.file(name)), calib);
    if (calib.hudPresent(tint) !== w.hud) {
      wrong.push(name + ' should be ' + (w.hud ? 'a replay' : 'no replay') +
        ', read ' + Math.min(tint.a, tint.b).toFixed(1));
    }
  }
  assert.deepStrictEqual(wrong, []);
});

// How much room the threshold actually has, on the dimmest frame in the corpus
// whose plates are genuinely drawn. Everything reading lower is a seek caught
// mid-transition, which hudPresent is right to refuse - so this, not those, is
// the number that says whether 15 is safe.
test('the dimmest properly drawn replay clears the threshold with room', { skip }, async () => {
  const tint = Crop.hudTint(await load(C.file('dim-replay')), calib);
  const margin = Math.min(tint.a, tint.b) - calib.HUD_TINT;
  assert.ok(margin > 10, 'margin is only ' + margin.toFixed(1));
});

test('two frames of the ESC menu are the same screen, and a replay is not', { skip }, async () => {
  const print = async (n) => S.thumb(await load(C.file(n)));
  assert.strictEqual(S.looksLike(await print('esc-menu'), esc.thumb).same, true);
  assert.strictEqual(S.looksLike(await print('esc-menu-again'), esc.thumb).same, true);
  for (const n of ['panel-open', 'panel-shut-bright', 'assemble', 'loading']) {
    assert.strictEqual(S.looksLike(await print(n), esc.thumb).same, false, n);
  }
});

// The screen a run must not start on. Its contents change as replays are
// imported and evicted, which is why the fingerprint is a 32x18 thumbnail
// rather than anything finer.
test('the replay list is recognised, and is not mistaken for a replay', { skip }, async () => {
  const history = require('./screens/replay-history.json');
  const seen = S.thumb(await load(C.file('replay-history')));
  assert.strictEqual(S.looksLike(seen, history.thumb).same, true);

  for (const n of ['panel-open', 'panel-shut-bright', 'assemble', 'loading', 'esc-menu']) {
    assert.strictEqual(S.looksLike(await S.thumb(await load(C.file(n))), history.thumb).same,
      false, n + ' must not read as the replay list');
  }
});

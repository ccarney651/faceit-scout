const test = require('node:test');
const assert = require('node:assert');
const R = require('./recorder.js');

// A window that is not at the origin, because that is the case a client-
// relative recording exists to survive.
const RECT = { ox: 100, oy: 40, w: 2560, h: 1440 };

const down = (t, x, y) => ({ t, type: 'down', button: 'left', x, y });
const up = (t, x, y) => ({ t, type: 'up', button: 'left', x, y });
const keyDown = (t, key) => ({ t, type: 'keydown', key });
const keyUp = (t, key) => ({ t, type: 'keyup', key });

test('a press and release become one click', () => {
  const got = R.normalise([down(0, 500, 300), up(80, 500, 300)], RECT);
  assert.strictEqual(got.length, 1);
  assert.strictEqual(got[0].type, 'click');
  assert.strictEqual(got[0].holdMs, 80);
});

// The whole reason coordinates are stored relative: the window moves between
// sessions, and an absolute coordinate then points at the desktop.
test('clicks are stored relative to the client area, not the screen', () => {
  const got = R.normalise([down(0, 500, 300), up(60, 500, 300)], RECT);
  assert.deepStrictEqual([got[0].x, got[0].y], [400, 260]);
});

// The UI acts on the press. A few pixels of drift before release is normal and
// must not move the recorded point.
test('a click is placed where the button went down', () => {
  const got = R.normalise([down(0, 500, 300), up(60, 507, 312)], RECT);
  assert.deepStrictEqual([got[0].x, got[0].y], [400, 260]);
});

test('the gap between actions is kept, because menus animate', () => {
  const got = R.normalise([
    down(0, 500, 300), up(60, 500, 300),
    down(900, 700, 400), up(960, 700, 400),
  ], RECT);
  assert.strictEqual(got[1].waitMs, 840, '900 - 60, the gap after the first release');
});

// A pause of half a minute is the operator reading the screen, not the client
// working. Replaying it would waste a night.
test('an absurdly long pause is capped rather than replayed', () => {
  const got = R.normalise([
    down(0, 500, 300), up(60, 500, 300),
    down(60000, 700, 400), up(60060, 700, 400),
  ], RECT);
  assert.strictEqual(got[1].waitMs, R.MAX_WAIT_MS);
});

test('keys are recorded as keys, in order with the clicks', () => {
  const got = R.normalise([
    down(0, 500, 300), up(60, 500, 300),
    keyDown(200, 'A'), keyUp(240, 'A'),
    keyDown(300, 'ENTER'), keyUp(340, 'ENTER'),
  ], RECT);
  assert.deepStrictEqual(got.map((e) => e.type), ['click', 'key', 'key']);
  assert.deepStrictEqual(got.slice(1).map((e) => e.key), ['A', 'ENTER']);
});

// A key already held when recording started produces an up with no down. It is
// not an action anyone performed, and inventing a press for it would send a
// keystroke the operator never made.
test('a release with no press is dropped', () => {
  const got = R.normalise([keyUp(10, 'K'), keyDown(20, 'A'), keyUp(60, 'A')], RECT);
  assert.deepStrictEqual(got.map((e) => e.key), ['A']);
});

// --- the code placeholder -------------------------------------------------
//
// The operator types a real code while recording, because the import dialog
// will not accept anything else. What gets stored has to be the placeholder,
// or every replay would open the one that was recorded.

const typed = (str) => str.split('').map((c) => ({ type: 'key', key: c, waitMs: 30, holdMs: 40 }));

test('the typed code is replaced by the placeholder', () => {
  const events = [{ type: 'click', button: 'left', x: 10, y: 20, waitMs: 0, holdMs: 50 }]
    .concat(typed('J8K2QP'))
    .concat([{ type: 'key', key: 'ENTER', waitMs: 100, holdMs: 40 }]);

  const got = R.substituteCode(events, 'J8K2QP');
  assert.ok(got.found);
  assert.deepStrictEqual(got.events.map((e) => e.type), ['click', 'text', 'key']);
  assert.strictEqual(got.events[1].value, R.CODE);
});

test('the wait before the code survives the substitution', () => {
  const events = typed('J8K2QP');
  events[0].waitMs = 750;
  const got = R.substituteCode(events, 'J8K2QP');
  assert.strictEqual(got.events[0].waitMs, 750, 'the field takes a moment to focus');
});

test('a lowercase code still matches the keys, which are recorded uppercase', () => {
  assert.ok(R.substituteCode(typed('J8K2QP'), 'j8k2qp').found);
});

// Only the whole code counts. Codes are six Crockford Base32 characters and
// single letters of one appear all over a recording; matching a prefix would
// swallow unrelated keystrokes and drop real ones.
test('a partial match is not a code', () => {
  const got = R.substituteCode(typed('J8K2'), 'J8K2QP');
  assert.strictEqual(got.found, false);
  assert.strictEqual(got.events.length, 4, 'nothing was collapsed');
});

test('keys either side of the code are left alone', () => {
  const events = typed('AJ8K2QPB');
  const got = R.substituteCode(events, 'J8K2QP');
  assert.deepStrictEqual(got.events.map((e) => e.key || e.value), ['A', R.CODE, 'B']);
});

// A recording where the code was never found is a chunk that would type the
// operator's own code into every replay. record() reports it so that is loud.
test('a recording with no code in it says so', () => {
  assert.strictEqual(R.substituteCode(typed('ENTER'), 'J8K2QP').found, false);
});

// --- replaying ------------------------------------------------------------

const chunk = (events) => ({
  name: 'open-import',
  recorded_at: '2026-09-09T01:00:00.000Z',
  client: { w: 2560, h: 1440 },
  events,
});

test('client coordinates come back out as screen coordinates', () => {
  const got = R.resolve(chunk([{ type: 'click', button: 'left', x: 400, y: 260, waitMs: 0, holdMs: 60 }]),
    RECT, null);
  assert.deepStrictEqual([got[0].x, got[0].y], [500, 300]);
});

test('the placeholder becomes this replay is code', () => {
  const got = R.resolve(chunk([{ type: 'text', value: R.CODE, waitMs: 0, holdMs: 60 }]),
    RECT, 'j8k2qp');
  assert.strictEqual(got[0].value, 'J8K2QP');
});

// A resized window invalidates every coordinate in the chunk. Scaling them
// would put each click plausibly close to its button and on none of them, so
// this refuses instead - the same call calib.check() makes about frame size.
test('a chunk recorded at another size is refused, not scaled', () => {
  const chk = R.validate(chunk([{ type: 'click', button: 'left', x: 1, y: 1 }]),
    { ox: 0, oy: 0, w: 1920, h: 1080 }, null);
  assert.strictEqual(chk.ok, false);
  assert.match(chk.reason, /2560x1440.*1920x1080/);
});

test('a chunk that types a code refuses to play without one', () => {
  const chk = R.validate(chunk([{ type: 'text', value: R.CODE }]), RECT, null);
  assert.strictEqual(chk.ok, false);
  assert.match(chk.reason, /code/);
});

test('an empty chunk is refused, since a silent no-op looks like success', () => {
  assert.strictEqual(R.validate(chunk([]), RECT, null).ok, false);
});

// --- building a whole chunk ------------------------------------------------

test('a recording becomes a chunk carrying the size it was recorded at', () => {
  const built = R.build('open-import', [
    down(0, 500, 300), up(60, 500, 300),
    keyDown(200, 'J'), keyUp(230, 'J'),
    keyDown(260, '8'), keyUp(290, '8'),
    keyDown(320, 'K'), keyUp(350, 'K'),
    keyDown(380, '2'), keyUp(410, '2'),
    keyDown(440, 'Q'), keyUp(470, 'Q'),
    keyDown(500, 'P'), keyUp(530, 'P'),
    keyDown(600, 'ENTER'), keyUp(640, 'ENTER'),
  ], RECT, 'J8K2QP');

  assert.strictEqual(built.codeFound, true);
  assert.deepStrictEqual(built.chunk.client, { w: 2560, h: 1440 });
  assert.deepStrictEqual(built.chunk.events.map((e) => e.type),
    ['click', 'text', 'key']);
});

// The round trip is what matters: what was recorded on this window, replayed
// on the same window, must land on the same pixels.
test('record then replay lands on the pixels that were clicked', () => {
  const built = R.build('to-replays', [down(0, 1234, 567), up(60, 1234, 567)], RECT, null);
  const plan = R.resolve(built.chunk, RECT, null);
  assert.deepStrictEqual([plan[0].x, plan[0].y], [1234, 567]);
});

test('a window that moved still lands on the same button', () => {
  const built = R.build('to-replays', [down(0, 1234, 567), up(60, 1234, 567)], RECT, null);
  const moved = { ox: 300, oy: 140, w: 2560, h: 1440 };
  const plan = R.resolve(built.chunk, moved, null);
  assert.deepStrictEqual([plan[0].x, plan[0].y], [1434, 667], 'moved with the window');
});

// --- names become file paths ----------------------------------------------
//
// The CLI's names are typed by the operator, but gui.js takes them off an HTTP
// request, and both land in path.join. A dot or a slash has no business in a
// chunk name, so neither is allowed anywhere near one.

test('an ordinary chunk name is accepted', () => {
  assert.strictEqual(R.safeName('open-import'), 'open-import');
});

test('a name that climbs out of the chunks directory is refused', () => {
  assert.throws(() => R.safeName('../../AGENTS'), /bad chunk name/);
  assert.throws(() => R.safeName('a/b'), /bad chunk name/);
  assert.throws(() => R.safeName('a\b'), /bad chunk name/);
  assert.throws(() => R.safeName('open.import'), /bad chunk name/);
});

test('an empty name is refused rather than writing .json', () => {
  assert.throws(() => R.safeName(''), /bad chunk name/);
  assert.throws(() => R.safeName(null), /bad chunk name/);
});

test('the path of a chunk is inside the chunks directory', () => {
  assert.ok(R.chunkPath('open-import').startsWith(R.DIR));
});

// --- pasting, which is how the code really gets in ------------------------
//
// The operator's flow is copy the code, click Import, Ctrl+V, OK, Watch. The
// first recorder watched letters but not modifiers, so that Ctrl+V was stored
// as a bare V and the chunk typed the letter "v" into the code field. It read
// perfectly plausibly in the listing.

const ctrlV = (t) => [
  { t, type: 'keydown', key: 'V', mods: 'ctrl' },
  { t: t + 90, type: 'keyup', key: 'V', mods: 'ctrl' },
];

test('the modifiers held at press time are recorded with the key', () => {
  const got = R.normalise(ctrlV(0), RECT);
  assert.deepStrictEqual(got[0].mods, ['ctrl']);
});

test('a key pressed alone carries no modifiers', () => {
  const got = R.normalise([keyDown(0, 'V'), keyUp(90, 'V')], RECT);
  assert.strictEqual(got[0].mods, undefined);
});

// Nothing else in these menus is worth pasting, so a Ctrl+V is the code
// arriving - no --code needed to recognise it.
test('a Ctrl+V becomes the code placeholder, with no code given', () => {
  const got = R.substituteCode(R.normalise(ctrlV(0), RECT), null);
  assert.ok(got.found);
  assert.deepStrictEqual(got.events.map((e) => e.type), ['paste']);
  assert.strictEqual(got.events[0].value, R.CODE);
});

test('a bare V is left as a keystroke, since it is one', () => {
  const got = R.substituteCode(R.normalise([keyDown(0, 'V'), keyUp(90, 'V')], RECT), null);
  assert.strictEqual(got.found, false);
  assert.strictEqual(got.events[0].type, 'key');
});

test('a paste chunk refuses to play without a code, like a typed one', () => {
  const chk = R.validate(chunk([{ type: 'paste', value: R.CODE }]), RECT, null);
  assert.strictEqual(chk.ok, false);
  assert.match(chk.reason, /code/);
});

test('the paste carries this replay is code into the plan', () => {
  const got = R.resolve(chunk([{ type: 'paste', value: R.CODE, waitMs: 10, holdMs: 60 }]),
    RECT, 'j8k2qp');
  assert.deepStrictEqual([got[0].type, got[0].value], ['paste', 'J8K2QP']);
});

test('a modifier survives into the plan the player runs', () => {
  const got = R.resolve(chunk([{ type: 'key', key: 'A', mods: ['ctrl'], waitMs: 0, holdMs: 40 }]),
    RECT, null);
  assert.deepStrictEqual(got[0].mods, ['ctrl']);
});

// The whole round trip, from what the recorder script emits to what the player
// receives: the operator's real open-import, minus the clicks.
test('a recorded paste ends up as a code the player can put on the clipboard', () => {
  const built = R.build('open-import', [
    down(0, 2345, 463), up(61, 2345, 463),
    ...ctrlV(1300),
    down(2500, 1340, 833), up(2590, 1340, 833),
  ], RECT, null);

  assert.ok(built.codeFound, 'the paste is the code');
  const plan = R.resolve(built.chunk, RECT, '7QR4M0');
  assert.deepStrictEqual(plan.map((e) => e.type), ['click', 'paste', 'click']);
  assert.strictEqual(plan[1].value, '7QR4M0');
});

// --- drags, wheels and every other key -------------------------------------
//
// Three attempts at recording one options menu failed in three different ways:
// the wheel was invisible to a poller, dragging the scrollbar was recorded as a
// click where the drag started, and the arrow keys were not on the watch list.
// The hook-based recorder sees all of it; these pin what happens next.

const move = (t, x, y) => ({ t, type: 'move', x, y });
const wheel = (t, x, y, delta) => ({ t, type: 'wheel', x, y, delta });

test('a press that moves is a drag, with where it ended', () => {
  const got = R.normalise([
    down(0, 500, 300), move(20, 500, 340), move(40, 500, 420), up(60, 500, 480),
  ], RECT);
  assert.strictEqual(got[0].type, 'drag');
  assert.deepStrictEqual([got[0].x, got[0].y], [400, 260], 'starts where it was pressed');
  assert.deepStrictEqual([got[0].toX, got[0].toY], [400, 440], 'ends where it was released');
});

// A scrollbar dragged to its middle, replayed as a click where the press
// started, does nothing at all - which is what the old recorder produced.
test('a drag keeps a path for playback to follow', () => {
  const got = R.normalise([
    down(0, 500, 300), move(20, 500, 340), move(40, 500, 420), up(60, 500, 480),
  ], RECT);
  assert.ok(got[0].path.length >= 2);
  assert.deepStrictEqual(got[0].path[0], { x: 400, y: 300 });
});

// A hand never holds a mouse still, so a couple of stray pixels must not turn
// every click into a drag.
test('a press that barely moves is still a click', () => {
  const got = R.normalise([
    down(0, 500, 300), move(20, 502, 301), up(60, 503, 302),
  ], RECT);
  assert.strictEqual(got[0].type, 'click');
  assert.deepStrictEqual([got[0].x, got[0].y], [400, 260]);
});

test('the wheel is recorded, in notches', () => {
  const got = R.normalise([wheel(0, 800, 400, -120)], RECT);
  assert.strictEqual(got[0].type, 'scroll');
  assert.strictEqual(got[0].notches, -1);
  assert.deepStrictEqual([got[0].x, got[0].y], [700, 360]);
});

// One turn of a wheel is a burst of notch messages. Replaying a hundred
// separate flicks is not the same gesture.
test('a burst of notches is one scroll', () => {
  const got = R.normalise([
    wheel(0, 800, 400, -120), wheel(60, 800, 400, -120), wheel(120, 800, 400, -120),
  ], RECT);
  assert.strictEqual(got.length, 1);
  assert.strictEqual(got[0].notches, -3);
});

test('scrolling back the other way is a separate gesture', () => {
  const got = R.normalise([wheel(0, 800, 400, -120), wheel(60, 800, 400, 120)], RECT);
  assert.deepStrictEqual(got.map((e) => e.notches), [-1, 1]);
});

test('a long pause splits one wheel gesture from the next', () => {
  const got = R.normalise([wheel(0, 800, 400, -120), wheel(3000, 800, 400, -120)], RECT);
  assert.strictEqual(got.length, 2);
});

test('the arrow keys are recorded like any other key', () => {
  const got = R.normalise([
    { t: 0, type: 'keydown', key: 'DOWN', vk: 40 },
    { t: 40, type: 'keyup', key: 'DOWN', vk: 40 },
  ], RECT);
  assert.strictEqual(got[0].key, 'DOWN');
  assert.strictEqual(got[0].vk, 40, 'the code travels, so playback never guesses a name');
});

test('a drag comes back out in screen coordinates', () => {
  const got = R.resolve(chunk([{
    type: 'drag', button: 'left', x: 400, y: 260, toX: 400, toY: 440,
    path: [{ x: 400, y: 300 }], waitMs: 0, holdMs: 60,
  }]), RECT, null);
  assert.deepStrictEqual([got[0].x, got[0].y, got[0].toX, got[0].toY], [500, 300, 500, 480]);
  assert.deepStrictEqual(got[0].path[0], { x: 500, y: 340 });
});

test('a scroll comes back out in screen coordinates', () => {
  const got = R.resolve(chunk([
    { type: 'scroll', x: 700, y: 360, notches: -3, waitMs: 0, holdMs: 1 },
  ]), RECT, null);
  assert.deepStrictEqual([got[0].x, got[0].y, got[0].notches], [800, 400, -3]);
});

// Interleaving matters: a scroll that lands after the click it preceded would
// scroll a menu that is not open yet.
test('scrolls stay in order with the clicks around them', () => {
  const got = R.normalise([
    down(0, 10, 10), up(50, 10, 10),
    wheel(200, 800, 400, -120),
    down(400, 20, 20), up(450, 20, 20),
  ], RECT);
  assert.deepStrictEqual(got.map((e) => e.type), ['click', 'scroll', 'click']);
});

// A PowerShell that writes UTF-8 "with encoding utf8" writes a BOM, and the BOM
// lands in front of the first JSON line. JSON.parse then reports an unexpected
// token and points at a character that does not print.
test('a recording file with a BOM still parses', () => {
  const BOM = String.fromCharCode(0xFEFF);
  const NL = String.fromCharCode(10);
  const got = R.parseRaw(BOM + '{"t":927,"type":"down","button":"left","x":1,"y":2}' + NL);
  assert.strictEqual(got.length, 1);
  assert.strictEqual(got[0].t, 927);
});

test('carriage returns and blank lines are not events', () => {
  const NL = String.fromCharCode(10);
  const CR = String.fromCharCode(13);
  const got = R.parseRaw('{"t":1}' + CR + NL + NL + '{"t":2}' + CR + NL);
  assert.deepStrictEqual(got.map((e) => e.t), [1, 2]);
});

// --- replaying faster than it was performed --------------------------------
//
// A recorded wait is the operator waiting: partly for a menu to animate, partly
// for themselves. The import chunk spends about four seconds of a map on them.

test('speed divides the recorded waits', () => {
  const got = R.resolve(chunk([
    { type: 'click', button: 'left', x: 1, y: 1, waitMs: 1200, holdMs: 60 },
  ]), RECT, null, { speed: 2 });
  assert.strictEqual(got[0].waitMs, 600);
});

test('no speed given means play it exactly as recorded', () => {
  const got = R.resolve(chunk([
    { type: 'click', button: 'left', x: 1, y: 1, waitMs: 1200, holdMs: 60 },
  ]), RECT, null);
  assert.strictEqual(got[0].waitMs, 1200);
});

// Menus need some time to draw whatever the speed says. Zero would not be a
// faster version of the gesture, it would be a different one.
test('a wait never scales below the floor', () => {
  const got = R.resolve(chunk([
    { type: 'click', button: 'left', x: 1, y: 1, waitMs: 150, holdMs: 60 },
  ]), RECT, null, { speed: 10 });
  assert.strictEqual(got[0].waitMs, R.MIN_WAIT_MS);
});

test('speed applies to every kind of event', () => {
  const got = R.resolve(chunk([
    { type: 'click', button: 'left', x: 1, y: 1, waitMs: 800, holdMs: 60 },
    { type: 'scroll', x: 2, y: 2, notches: -2, waitMs: 800, holdMs: 1 },
    { type: 'drag', button: 'left', x: 3, y: 3, toX: 9, toY: 9, path: [], waitMs: 800, holdMs: 60 },
    { type: 'key', key: 'DOWN', vk: 40, waitMs: 800, holdMs: 40 },
    { type: 'paste', value: R.CODE, waitMs: 800, holdMs: 60 },
  ]), RECT, 'ABC123', { speed: 4 });
  assert.deepStrictEqual(got.map((e) => e.waitMs), [200, 200, 200, 200, 200]);
});

// node --test docs/capture/engine/contribution.test.js
const test = require('node:test');
const assert = require('node:assert');
const C = require('./contribution.js');

// The feed as data.json ships it: one entry per game, carrying the match_id the
// captured map records.
const FEED = [
  { code: '04C5WM', match_id: 'm-new', game_no: 1 },
  { code: '4PEMA1', match_id: 'm-new', game_no: 2 },
  { code: '2RW1PZ', match_id: 'm-new2', game_no: 1 },
];
const map = (id, n) => ({ match_id: id, game_no: n || 1, published: false });

test('maps the feed still carries are sent', () => {
  const r = C.splitBySeason([map('m-new'), map('m-new2')], FEED);
  assert.equal(r.send.length, 2);
  assert.deepStrictEqual(r.held, []);
});

// The exact shape of the 2026-09-08 incident: two matches' worth of current
// captures sitting in IndexedDB behind a pile of last season's.
test('last season\'s maps are held back, this season\'s still go', () => {
  const maps = [map('s9-a'), map('s9-b'), map('m-new'), map('s9-c'), map('m-new2')];
  const r = C.splitBySeason(maps, FEED);
  assert.deepStrictEqual(r.send.map((m) => m.match_id), ['m-new', 'm-new2']);
  assert.deepStrictEqual(r.held.map((m) => m.match_id), ['s9-a', 's9-b', 's9-c']);
});

test('an already-published map of this season is still re-sent', () => {
  // Re-publishing is deliberate: an operator may fix a map and send it again.
  // Only the SEASON decides what is held, never the published flag.
  const m = map('m-new'); m.published = true;
  assert.equal(C.splitBySeason([m], FEED).send.length, 1);
});

test('an empty feed filters nothing', () => {
  // A local checkout ships codes: []. Filtering against it would hold back
  // every map and read as a broken Publish button.
  const maps = [map('s9-a'), map('m-new')];
  assert.equal(C.splitBySeason(maps, []).send.length, 2);
  assert.equal(C.splitBySeason(maps, null).send.length, 2);
  assert.deepStrictEqual(C.splitBySeason(maps, []).held, []);
});

test('a feed whose entries carry no match_id filters nothing', () => {
  assert.equal(C.splitBySeason([map('s9-a')], [{ code: 'ABC123' }]).send.length, 1);
});

test('no maps is not an error', () => {
  const r = C.splitBySeason([], FEED);
  assert.deepStrictEqual(r, { send: [], held: [] });
  assert.deepStrictEqual(C.splitBySeason(null, FEED), { send: [], held: [] });
});

test('the note names the count and says where they went', () => {
  assert.equal(C.heldNote([]), '');
  assert.match(C.heldNote([map('a')]), /^1 saved map from an earlier season was not sent/);
  assert.match(C.heldNote([map('a'), map('b')]), /^2 saved maps from an earlier season were not sent/);
  assert.match(C.heldNote([map('a')]), /stays in this browser/);
});

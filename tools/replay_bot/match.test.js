const test = require('node:test');
const assert = require('node:assert');
const fs = require('fs');
const path = require('path');
const U = require('../../docs/capture/engine/util.js');
const Match = require('./match.js');

const REFS_JSON = JSON.parse(fs.readFileSync(
  path.join(__dirname, '../../docs/capture/refs.json'), 'utf8'));

const M = Match.make(REFS_JSON, { PAD: 2 });
const aRefs = REFS_JSON.refs.filter((r) => r.v === 'a');

test('the whole shipped library is loaded, both variants', () => {
  assert.strictEqual(M.refCount(), REFS_JSON.refs.length);
  assert.strictEqual(aRefs.length, 53);
});

// The strongest end-to-end check available offline: feed a stored reference
// back through the real matcher and it must identify itself. This exercises
// b64 decode, padding, centring, L2 normalisation and the cosine sweep - the
// entire path the bot's crops take.
test('a stored reference matches itself almost perfectly', () => {
  const ref = aRefs[0];
  const got = M.match(ref.d, 'a');
  assert.strictEqual(got.guid, ref.g);
  assert.ok(got.score > 0.99, `expected ~1.0, got ${got.score}`);
});

test('every hero in the library identifies itself', () => {
  const wrong = aRefs.filter((r) => M.match(r.d, 'a').guid !== r.g);
  assert.deepStrictEqual(wrong.map((r) => r.n), [], 'these failed to self-match');
});

// A crop of flat grey carries no signal at all. If that scored like a real
// portrait, the confidence number would be worthless as a gate and the bot
// would happily label blank frames.
test('a featureless crop does not score like a portrait', () => {
  const flat = U.bytesToB64(new Uint8Array(REFS_JSON.w * REFS_JSON.h).fill(128));
  assert.ok(M.match(flat, 'a').score < 0.5, 'flat grey should not look like a hero');
});

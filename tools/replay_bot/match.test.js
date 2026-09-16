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
  // Each hero contributes up to two variant-'a' entries (alive + dead, same
  // {n,g,v} shape - see build_capture_refs.py), so count distinct heroes, not
  // rows. The roster is ~53; keep a floor so a truncated rebuild still trips.
  const aGuids = new Set(aRefs.map((r) => r.g));
  assert.ok(aGuids.size >= 50, `only ${aGuids.size} heroes have a blue ref`);
  const bGuids = new Set(REFS_JSON.refs.filter((r) => r.v === 'b').map((r) => r.g));
  // custom:doctrine (2026-09-15): only a red-side capture exists so far - an
  // unreleased hero picked during its BlizzCon trial before FACEIT games were
  // meant to allow it (specs/... none yet, see PLANS.md/CHANGELOG.md). Remove
  // this exception once a blue-side ref is captured; until then the matcher
  // is known-weaker for Doctrine on the blue side specifically, not silently.
  const KNOWN_ONE_SIDED = new Set(['custom:doctrine']);
  const aCheck = new Set([...aGuids].filter((g) => !KNOWN_ONE_SIDED.has(g)));
  const bCheck = new Set([...bGuids].filter((g) => !KNOWN_ONE_SIDED.has(g)));
  assert.deepStrictEqual([...aCheck].sort(), [...bCheck].sort(),
    'blue and red libraries cover the same heroes (outside KNOWN_ONE_SIDED)');
  KNOWN_ONE_SIDED.forEach((g) => {
    assert.ok(bGuids.has(g) && !aGuids.has(g),
      `${g} is listed as known-one-sided but its actual coverage changed - update or remove the exception`);
  });
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

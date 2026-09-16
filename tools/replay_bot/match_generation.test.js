// Kept out of match.test.js on purpose: that file makes one matcher at module
// scope and every test in it uses that handle, so creating a second one here
// would stale it and fail tests that have nothing to do with this.
const test = require('node:test');
const assert = require('node:assert');
const fs = require('fs');
const path = require('path');
const Match = require('./match.js');

const REFS_JSON = JSON.parse(fs.readFileSync(
  path.join(__dirname, '../../docs/capture/refs.json'), 'utf8'));

// THE REFERENCE SET IS A GLOBAL, because this reuses the shipped refs.js engine
// and that engine reads free variables the way the capture pages set them up.
// Making a second matcher therefore re-points the first one, silently.
//
// That cost a real measurement: comparing a taught reference against the old one
// in a single process, both handles returned the NEW library, so "before" and
// "after" were identical and a fix that corrected 42 cells looked like it had
// done nothing. Sequential use is fine and the capture does it once per map;
// reaching for an OLDER handle afterwards is the bug, and it now says so.
test('a matcher handle refuses to answer once a newer one exists', () => {
  const first = Match.make(REFS_JSON, { PAD: 2 });
  const crop = REFS_JSON.refs[0].d;
  assert.ok(first.match(crop, 'a').name, 'works while it is the current one');

  const second = Match.make(REFS_JSON, { PAD: 2 });
  assert.ok(second.match(crop, 'a').name, 'the newer handle is fine');
  assert.throws(() => first.match(crop, 'a'), /stale|newer matcher/i,
    'the older one must refuse rather than quietly answer from the new library');
});

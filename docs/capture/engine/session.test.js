const test = require('node:test');
const assert = require('node:assert');
const Session = require('./session.js');

const DATA = {
  code_wipe_date: '2026-08-11',
  codes: [
    { code: 'E39856', map: 'Oasis', division: 'EMEA Master' },
    { code: 'ABCD12', map: 'Ilios', division: 'NA Expert' },
  ],
};

test('buildCodeIndex collects league codes and the wipe date', () => {
  const idx = Session.buildCodeIndex(DATA);
  assert.equal(idx.wipeDate, '2026-08-11');
  assert.ok(idx.codes.has('E39856'));
  assert.equal(idx.codes.size, 2);
});

test('buildCodeIndex tolerates a missing or empty feed', () => {
  const idx = Session.buildCodeIndex({});
  assert.equal(idx.wipeDate, null);
  assert.equal(idx.codes.size, 0);
});

test('a league code is flagged, with its division', () => {
  const idx = Session.buildCodeIndex(DATA);
  const got = Session.classifyCode('E39856', idx, '2026-08-12');
  assert.equal(got.league, true);
  assert.equal(got.division, 'EMEA Master');
});

test('code matching is case-insensitive and whitespace-tolerant', () => {
  const idx = Session.buildCodeIndex(DATA);
  assert.equal(Session.classifyCode(' e39856 ', idx, '2026-08-12').league, true);
});

test('a code that is not in the feed is not a league code', () => {
  const idx = Session.buildCodeIndex(DATA);
  assert.equal(Session.classifyCode('7DNNF1', idx, '2026-08-12').league, false);
});

test('a code captured before the last wipe is dead', () => {
  const idx = Session.buildCodeIndex(DATA);
  // The scrim was played on the 9th; the patch wiped codes on the 11th.
  assert.equal(Session.classifyCode('7DNNF1', idx, '2026-08-09').dead, true);
});

test('a code from after the last wipe is alive', () => {
  const idx = Session.buildCodeIndex(DATA);
  assert.equal(Session.classifyCode('7DNNF1', idx, '2026-08-12').dead, false);
});

test('with no known wipe date nothing is called dead', () => {
  const idx = Session.buildCodeIndex({});
  assert.equal(Session.classifyCode('7DNNF1', idx, '2026-08-09').dead, false);
});

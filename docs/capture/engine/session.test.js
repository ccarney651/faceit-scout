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

test('buildScaffold annotates parsed rows with league and wipe status', () => {
  const idx = Session.buildCodeIndex(DATA);
  const rows = [
    { map_name: 'Suravasa', map_category: 'Flashpoint', code: 'AKS2A9',
      score: {us: 11, them: 2}, result: 'win' },
    { map_name: 'Oasis', map_category: 'Control', code: 'E39856',
      score: {us: 1, them: 2}, result: 'loss' },
  ];
  const out = Session.buildScaffold(rows, idx, '2026-08-12');
  assert.equal(out.length, 2);
  assert.equal(out[0].league, false);
  assert.equal(out[0].dead, false);
  assert.equal(out[1].league, true, 'the Oasis row is a league match');
  assert.equal(out[1].division, 'EMEA Master');
});

test('buildScaffold keeps rows that have no code at all', () => {
  const idx = Session.buildCodeIndex(DATA);
  const rows = [{ map_name: "King's Row", map_category: 'Hybrid', code: null,
                  score: {us: 3, them: 1}, result: 'win' }];
  const out = Session.buildScaffold(rows, idx, '2026-08-12');
  assert.equal(out.length, 1);
  assert.equal(out[0].code, null);
  assert.equal(out[0].league, false);
});

test('buildScaffold marks every row dead when the session predates the wipe', () => {
  const idx = Session.buildCodeIndex(DATA);
  const rows = [{ map_name: 'Suravasa', map_category: 'Flashpoint',
                  code: 'AKS2A9', score: {us: 11, them: 2}, result: 'win' }];
  const out = Session.buildScaffold(rows, idx, '2026-08-01');
  assert.equal(out[0].dead, true);
});

// --- score/result disagreement -------------------------------------------
// From a real OCR run: tesseract read "2 - 0" as "2 - ©", the parser emitted
// score 0-0, and the row still claimed VICTORY. A confidently wrong 0-0 is
// worse than an admitted unknown, so rows like that are flagged.

test('a win with no surviving score is flagged suspect', () => {
  const idx = Session.buildCodeIndex(DATA);
  const out = Session.buildScaffold(
    [{ map_name: 'Busan', map_category: 'Control', code: 'IJKL56',
       score: { us: 0, them: 0 }, result: 'win' }], idx, '2026-08-13');
  assert.equal(out[0].score_suspect, true);
});

test('a win whose score says otherwise is flagged suspect', () => {
  const idx = Session.buildCodeIndex(DATA);
  const out = Session.buildScaffold(
    [{ map_name: 'Ilios', map_category: 'Control', code: 'ABCD12',
       score: { us: 1, them: 3 }, result: 'win' }], idx, '2026-08-13');
  assert.equal(out[0].score_suspect, true);
});

test('a draw that is not level is flagged suspect', () => {
  const idx = Session.buildCodeIndex(DATA);
  const out = Session.buildScaffold(
    [{ map_name: 'Nepal', map_category: 'Control', code: 'ZZZZ99',
       score: { us: 2, them: 1 }, result: 'draw' }], idx, '2026-08-13');
  assert.equal(out[0].score_suspect, true);
});

test('a consistent row is not flagged', () => {
  const idx = Session.buildCodeIndex(DATA);
  const out = Session.buildScaffold(
    [{ map_name: 'Ilios', map_category: 'Control', code: 'ABCD12',
       score: { us: 3, them: 1 }, result: 'win' },
     { map_name: 'Nepal', map_category: 'Control', code: 'ZZZZ99',
       score: { us: 2, them: 2 }, result: 'draw' }], idx, '2026-08-13');
  assert.equal(out[0].score_suspect, false);
  assert.equal(out[1].score_suspect, false);
});

test('a row with no result at all is not flagged', () => {
  // Nothing to contradict - the code and map are still the point of the row.
  const idx = Session.buildCodeIndex(DATA);
  const out = Session.buildScaffold(
    [{ map_name: 'Oasis', map_category: 'Control', code: 'E39856',
       score: { us: 0, them: 0 }, result: null }], idx, '2026-08-13');
  assert.equal(out[0].score_suspect, false);
});

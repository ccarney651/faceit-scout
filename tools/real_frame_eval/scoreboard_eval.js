// Score every scoreboard crop variant against the known board. Run from repo root:
//   node tools/real_frame_eval/scoreboard_crop.py first, then
//   node tools/real_frame_eval/scoreboard_eval.js scoreboard_crops
//
// The eight frames are ONE PAUSED BOARD photographed from eight camera angles,
// so the text is identical everywhere and the background is the only variable.
// That is what makes a variant comparison mean anything - see design section
// 8.4, where every earlier colour number turned out to be a measurement of
// whichever map the frames happened to come from.
//
// NO CHARACTER WHITELIST, deliberately. Section 8.3 measured one at 59/96
// against 66/96 without, and worse in fourteen of sixteen pairings: denied its
// first choice tesseract degrades the whole line rather than substituting the
// nearest allowed glyph.
const fs = require('fs');
const path = require('path');
const { createWorker } = require('tesseract.js');
const SB = require('../../docs/capture/scoreboard.js');
const TRUTH = JSON.parse(fs.readFileSync(path.join(__dirname, 'scoreboard_truth.json'), 'utf8'));

const ROWS = TRUTH.board.rows;
const COLS = ['k', 'd', 'dmg', 'tkn', 'x', 'ult'];
// The parser's field names for the same six columns.
const PARSED = { k: 'k', d: 'd', dmg: 'dd', tkn: 'dt', x: 'x', ult: 'uu' };

function norm(s) { return String(s == null ? '' : s).toUpperCase().replace(/[^A-Z0-9]/g, ''); }

// Levenshtein ratio, used only to pair a parsed row with the truth row it is
// most likely to BE. Rows are matched by name rather than by index because a
// dropped row would otherwise shift every row after it and score them all
// wrong, which measures the drop twice.
function ratio(a, b) {
  a = norm(a); b = norm(b);
  if (!a && !b) return 1;
  if (!a || !b) return 0;
  const d = Array.from({ length: a.length + 1 }, (_, i) => [i, ...Array(b.length).fill(0)]);
  for (let j = 0; j <= b.length; j++) d[0][j] = j;
  for (let i = 1; i <= a.length; i++)
    for (let j = 1; j <= b.length; j++)
      d[i][j] = Math.min(d[i - 1][j] + 1, d[i][j - 1] + 1,
                         d[i - 1][j - 1] + (a[i - 1] === b[j - 1] ? 0 : 1));
  return 1 - d[a.length][b.length] / Math.max(a.length, b.length);
}

function pair(entries) {
  // Greedy best-first over all (entry, truth row) pairs.
  const cand = [];
  entries.forEach((e, ei) => ROWS.forEach((r, ri) => cand.push([ratio(e.name, r.name), ei, ri])));
  cand.sort((p, q) => q[0] - p[0]);
  const usedE = new Set(), usedR = new Set(), out = [];
  for (const [sc, ei, ri] of cand) {
    if (sc < 0.5 || usedE.has(ei) || usedR.has(ri)) continue;
    usedE.add(ei); usedR.add(ri); out.push([entries[ei], ROWS[ri], sc]);
  }
  return out;
}

function score(parsed) {
  const s = { names: 0, values: 0, rows: 0, teams: 0, entries: parsed.entries.length,
              matchTime: parsed.matchTime === TRUTH.board.matchTime };
  for (const [e, r] of pair(parsed.entries)) {
    if (norm(e.name) === norm(r.name)) s.names++;
    let hit = 0;
    for (const c of COLS) if (String(e[PARSED[c]]) === String(r[c])) hit++;
    s.values += hit;
    if (hit === COLS.length) s.rows++;
    if (e.team === (r.team === 1 ? 'a' : 'b')) s.teams++;
  }
  return s;
}

(async () => {
  const dir = process.argv[2] || 'scoreboard_crops';
  const files = fs.readdirSync(dir).filter(f => f.endsWith('.png')).sort();
  const w = await createWorker('eng');
  await w.setParameters({ tessedit_pageseg_mode: '6' });

  const byVariant = {};
  console.log('frame    variant   values/60  rows/10  names/10  teams/10  time  entries');
  for (const f of files) {
    const [stem, variant] = path.basename(f, '.png').split('.');
    const { data } = await w.recognize(path.join(dir, f));
    const lines = (data.text || '').split('\n').map(s => s.replace(/\s+/g, ' ').trim()).filter(Boolean);
    const parsed = SB.parse(lines);
    const s = score(parsed);
    (byVariant[variant] = byVariant[variant] || []).push(s);
    console.log(
      stem.padEnd(8), variant.padEnd(9),
      String(s.values).padStart(6), '   ', String(s.rows).padStart(5), '   ',
      String(s.names).padStart(5), '   ', String(s.teams).padStart(5), '   ',
      s.matchTime ? ' y' : ' .', '  ', s.entries);
    fs.writeFileSync(path.join(dir, path.basename(f, '.png') + '.txt'), lines.join('\n'));
  }
  await w.terminate();

  console.log('\n== totals across all %d frames ==', Object.values(byVariant)[0].length);
  console.log('variant   values/%d  rows/%d  names/%d  teams/%d  time/%d',
    ROWS.length * COLS.length * 8, ROWS.length * 8, ROWS.length * 8, ROWS.length * 8, 8);
  const rank = Object.entries(byVariant).map(([v, a]) => [v,
    a.reduce((t, s) => t + s.values, 0), a.reduce((t, s) => t + s.rows, 0),
    a.reduce((t, s) => t + s.names, 0), a.reduce((t, s) => t + s.teams, 0),
    a.filter(s => s.matchTime).length]);
  rank.sort((p, q) => q[1] - p[1]);
  for (const [v, val, rows, names, teams, time] of rank)
    console.log(v.padEnd(9), String(val).padStart(7), String(rows).padStart(8),
                String(names).padStart(8), String(teams).padStart(8), String(time).padStart(7));
})();

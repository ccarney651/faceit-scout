// Score pad-vs-tight crops. Two measures, because they answer different
// questions: `exact` is how clean the OCR text is, and `matched` is whether the
// name resolves against a roster - which is what the product actually needs,
// and which tolerates junk that `exact` does not.
const fs = require('fs');
const path = require('path');
const N = require(path.resolve(__dirname, '../../docs/capture/engine/names.js'));
const O = require(path.resolve(__dirname, '../../docs/capture/engine/opponents.js'));

const reads = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'));
const truth = JSON.parse(fs.readFileSync(process.argv[3], 'utf8'));

const tot = {};
const perFrame = {};
for (const key of Object.keys(reads)) {
  const m = key.match(/^(.*)__(pad|tight)$/);
  if (!m) continue;
  const [, tag, variant] = m;
  if (!truth[tag]) continue;
  const t = (tot[variant] = tot[variant] || { exact: 0, matched: 0, n: 0, junk: 0 });
  const pf = (perFrame[tag] = perFrame[tag] || {});
  const f = (pf[variant] = { exact: 0, matched: 0 });
  for (const side of ['a', 'b']) {
    truth[tag][side].forEach((want, i) => {
      const got = (reads[key][`${side}${i}`] || '').trim();
      t.n++;
      if (got.toUpperCase() === want.toUpperCase()) { t.exact++; f.exact++; }
      // Does it still resolve? normSet is what side detection and opponent
      // identification actually compare with.
      if (O.normSet([got]).includes(O.normSet([want])[0])) { t.matched++; f.matched++; }
      // Characters OCR added that are not in the name.
      const extra = got.replace(/\s/g, '').length - want.replace(/\s/g, '').length;
      if (extra > 0) t.junk += extra;
    });
  }
}

console.log('variant   exact      resolves   stray chars');
for (const v of ['pad', 'tight']) {
  const t = tot[v];
  if (!t) continue;
  console.log(`${v.padEnd(8)} ${String(t.exact).padStart(3)}/${t.n}   ${String(t.matched).padStart(3)}/${t.n}   ${t.junk}`);
}
console.log('\nper frame (exact):');
for (const tag of Object.keys(perFrame).sort()) {
  const p = perFrame[tag];
  const d = (p.tight?.exact ?? 0) - (p.pad?.exact ?? 0);
  console.log(`  ${tag.padEnd(24)} pad ${String(p.pad?.exact ?? 0).padStart(2)}/10   tight ${String(p.tight?.exact ?? 0).padStart(2)}/10   ${d > 0 ? '+' + d : d}`);
}

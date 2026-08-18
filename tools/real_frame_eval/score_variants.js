// Score every crop variant on real tesseract output from every real frame.
//
//   OCR quality   simScore(read, the text the HUD actually renders)
//   attribution   assign.js against the role-tagged FACEIT lineup
//
// Usage: node score_variants.js <reads.json> <truth.json>
const fs = require('fs');
const path = require('path');
const ROOT = path.resolve(__dirname, '../../docs/capture/engine');
const N = require(path.join(ROOT, 'names.js'));
const A = require(path.join(ROOT, 'assign.js'));

const reads = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'));
const truth = JSON.parse(fs.readFileSync(process.argv[3], 'utf8'));
const VARIANTS = ['shipped', 'row', 'rowtight'];
const detail = process.argv.includes('--detail');

const tot = {};
for (const v of VARIANTS) tot[v] = { sim: 0, n: 0, ok: 0, wrong: 0, none: 0, top1: 0 };

for (const frame of Object.keys(truth).sort()) {
  const fr = truth[frame];
  if (!reads[frame]) { console.error('no reads for', frame); continue; }
  for (const side of ['a', 'b']) {
    const slots = fr.sides[side];
    const roster = slots.map(s => ({ id: s.id, names: s.names, role: s.role }));
    const roles = slots.map(s => s.role);
    for (const v of VARIANTS) {
      const r5 = [0, 1, 2, 3, 4].map(i => reads[frame][`${v}_${side}${i}`] ?? '');
      const res = A.assign(r5, roster, roles);
      const t = tot[v];
      slots.forEach((s, i) => {
        const sim = N.simScore(r5[i], s.hud);
        t.sim += sim; t.n++;
        // Does the read alone point at the right player, before any constraint?
        let best = null, bs = -1;
        for (const p of slots) {
          for (const nm of p.names) {
            const sc = N.simScore(r5[i], nm);
            if (sc > bs) { bs = sc; best = p.id; }
          }
        }
        if (bs >= N.STRONG_NAME_SCORE && best === s.id) t.top1++;
        if (res.ids[i] === s.id) t.ok++;
        else if (res.ids[i] === null) t.none++;
        else t.wrong++;
        if (detail && v === 'rowtight') {
          console.log(`  ${frame} ${side}${i} hud=${s.hud.padEnd(12)} read=${JSON.stringify(r5[i]).padEnd(16)} sim=${String(sim).padStart(3)} -> ${res.ids[i] === s.id ? 'OK' : res.ids[i] === null ? '--' : 'WRONG'}`);
        }
      });
    }
  }
}

console.log('\nvariant     meanSim  read-alone-correct   assigned: correct  wrong  abstain');
for (const v of VARIANTS) {
  const t = tot[v];
  console.log(`${v.padEnd(10)}  ${(t.sim / t.n).toFixed(1).padStart(6)}   ` +
    `${String(t.top1).padStart(3)}/${t.n}            ` +
    `${String(t.ok).padStart(4)}/${t.n}  ${String(t.wrong).padStart(4)}  ${String(t.none).padStart(4)}`);
}

// Old matcher vs new, on REAL tesseract output from a REAL frame.
// Frame: screenshots/Screenshot 2026-07-15 231525.png, replay code TJDE6W
// -> match 1-6ae9f2aa-863b-45a9-9e76-ecb2bf5144bf game 2 (from faceit.sqlite3).
const N = require('c:/Users/ccarn/faceit-sync/docs/capture/engine/names.js');
const A = require('c:/Users/ccarn/faceit-sync/docs/capture/engine/assign.js');

// Real OCR reads (node ocr_strips.js strips).
const READS = {
  a: ["4.04", "MAPPSY", "'TWERKNATION", "JODAN", "SZATAN"],
  b: ["HYBRID", "NITROX", "KRONUS", "ZYDRA", "SCRAINE"],
};

// Real lineups from faceit.sqlite3, in the HUD slot order visible in the frame.
// `names` is [game_name, nickname] exactly as teamRoster()/gameLineup() build it.
const TRUTH = {
  a: [ // Frost Tails, left
    { id: 'Proxystyle', role: 'Support', names: ['Proxy', 'Proxystyle'] },
    { id: 'Mappsy',     role: 'Tank',    names: ['Mappsy', 'Mappsy'] },
    { id: 'sexy_eden',  role: 'Support', names: ['TWERKNATION', 'sexy_eden'] },
    { id: 'Arclite',    role: 'Damage',  names: ['Arclite', 'Arclite'] },
    { id: 'SzatanOW',   role: 'Damage',  names: ['Szatan', 'SzatanOW'] },
  ],
  b: [ // ELMT Sunrise, right
    { id: 'HybridOW',  role: 'Tank',    names: ['Hybrid', 'HybridOW'] },
    { id: 'NitroxOW',  role: 'Support', names: ['Nitrox', 'NitroxOW'] },
    { id: 'kronus_ow', role: 'Support', names: ['kronus', 'kronus_ow'] },
    { id: 'zydra_ow',  role: 'Damage',  names: ['Zydra', 'zydra_ow'] },
    { id: 'scraine',   role: 'Damage',  names: ['Scraine', 'scraine'] },
  ],
};

// index.html attribute(): greedy 1:1 above STRONG_NAME_SCORE, then one
// process-of-elimination step.
function greedy(reads, roster) {
  const out = [null, null, null, null, null], cand = [];
  reads.forEach((r, i) => {
    if (!r) return;
    for (const p of roster) {
      let s = 0;
      for (const n of p.names) s = Math.max(s, N.simScore(r, n));
      cand.push({ i, id: p.id, s });
    }
  });
  cand.sort((x, y) => y.s - x.s);
  const usedSlot = new Set(), usedId = new Set();
  for (const c of cand) {
    if (c.s < N.STRONG_NAME_SCORE) break;
    if (usedSlot.has(c.i) || usedId.has(c.id)) continue;
    out[c.i] = c.id; usedSlot.add(c.i); usedId.add(c.id);
  }
  const openSlots = [0, 1, 2, 3, 4].filter(i => out[i] === null);
  const openIds = roster.filter(p => !usedId.has(p.id)).map(p => p.id);
  if (openSlots.length === 1 && openIds.length === 1) out[openSlots[0]] = openIds[0];
  return out;
}

let oldOk = 0, oldWrong = 0, newOk = 0, newWrong = 0;
for (const side of ['a', 'b']) {
  const lineup = TRUTH[side];
  const truth = lineup.map(p => p.id);
  const roles = lineup.map(p => p.role);   // hero recognition assumed correct
  const g = greedy(READS[side], lineup);
  const r = A.assign(READS[side], lineup, roles);

  console.log(`\n--- side ${side} (${side === 'a' ? 'Frost Tails' : 'ELMT Sunrise'}) ---`);
  for (let i = 0; i < 5; i++) {
    const mark = x => x === null ? 'null ' : (x === truth[i] ? 'OK   ' : 'WRONG');
    console.log(
      `  read=${JSON.stringify(READS[side][i]).padEnd(16)} truth=${truth[i].padEnd(12)}` +
      ` | old ${mark(g[i])} ${String(g[i]).padEnd(12)}` +
      ` | new ${mark(r.ids[i])} ${String(r.ids[i]).padEnd(12)} ${r.conf[i] || ''}`);
    if (g[i] === truth[i]) oldOk++; else if (g[i] !== null) oldWrong++;
    if (r.ids[i] === truth[i]) newOk++; else if (r.ids[i] !== null) newWrong++;
  }
}
console.log(`\nOLD  ${oldOk}/10 correct, ${oldWrong} wrong, ${10 - oldOk - oldWrong} unresolved`);
console.log(`NEW  ${newOk}/10 correct, ${newWrong} wrong, ${10 - newOk - newWrong} unresolved`);

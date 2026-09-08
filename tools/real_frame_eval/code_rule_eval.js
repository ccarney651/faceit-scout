// Run from the repo root:
//   node tools/real_frame_eval/code_rule_eval.js code_guard_crops
//
// Score the shipped acceptance rule against a relaxed one, over the purpose-built
// guard corpus (code_guard_crops: 5 probes x 3 contrasts x injected strip errors).
//
//   shipped : accept only when ALL FIVE probes return a code and all agree.
//   relaxed : accept when every probe that COULD read returns the same code, and
//             at least MIN_READABLE of them did.
//
// The gate is WRONG = 0 on the error cases. A refusal is a nuisance the operator
// retries past; a wrong code is a corrupted record indistinguishable from a good
// one. The unperturbed ('none') cases price what each rule costs when nothing is
// actually wrong - which is the case the operator hit on 2026-09-08, where three
// probes agreed on the right code and the read was thrown away.
const fs = require('fs');
const path = require('path');
const { createWorker } = require('tesseract.js');
const R = require('../../docs/capture/engine/replaycode.js');

const TRUTH = JSON.parse(fs.readFileSync(path.join(__dirname, 'code_truth.json'), 'utf8'));
const DIR = process.argv[2] || 'code_guard_crops';
const CONTRASTS = ['1.0', '1.45', '1.9'];
const PROBES = ['p0', 'p1', 'p2', 'p3', 'p4'];
const MIN_READABLE = 3;

(async () => {
  const files = fs.readdirSync(DIR).filter(f => f.endsWith('.png'));
  // stem__error-pN__contrast.png
  const cases = new Map();
  for (const f of files) {
    const m = /^(.+)__(.+)-(p\d)__([\d.]+)\.png$/.exec(f);
    if (!m) continue;
    const key = m[1] + '__' + m[2];
    if (!cases.has(key)) cases.set(key, {});
    cases.get(key)[m[3] + '|' + m[4]] = f;
  }
  const w = await createWorker('eng');
  await w.setParameters({ tessedit_pageseg_mode: '7', tessedit_char_whitelist: R.ALPHABET });

  const tally = {};
  const bump = (rule, bucket) => {
    tally[rule] = tally[rule] || { correct: 0, wrong: 0, refused: 0 };
    tally[rule][bucket]++;
  };
  const wrongs = [];
  let done = 0;
  for (const [key, imgs] of [...cases.entries()].sort()) {
    const stem = key.split('__')[0], err = key.split('__')[1];
    const want = TRUTH[stem];
    if (!want) continue;
    const answers = [];
    for (const p of PROBES) {
      const seen = [];
      for (const c of CONTRASTS) {
        const f = imgs[p + '|' + c];
        if (!f) continue;
        const { data } = await w.recognize(path.join(DIR, f));
        const one = R.foldCode((data && data.text || '').replace(/\s+/g, ''));
        if (one && seen.indexOf(one) === -1) seen.push(one);
      }
      answers.push(seen.length === 1 ? seen[0] : null);
    }
    const readable = answers.filter(a => a !== null);
    const distinct = [...new Set(readable)];
    const unperturbed = err === 'none';

    // shipped rule
    let got = (distinct.length === 1 && readable.length === answers.length) ? distinct[0] : null;
    bump('shipped|' + (unperturbed ? 'clean' : 'error'),
      got === null ? 'refused' : got === want ? 'correct' : 'wrong');
    if (got !== null && got !== want) wrongs.push(['shipped', key, want, got, answers.join(',')]);

    // relaxed rule
    got = (distinct.length === 1 && readable.length >= MIN_READABLE) ? distinct[0] : null;
    bump('relaxed|' + (unperturbed ? 'clean' : 'error'),
      got === null ? 'refused' : got === want ? 'correct' : 'wrong');
    if (got !== null && got !== want) wrongs.push(['relaxed', key, want, got, answers.join(',')]);

    if (++done % 20 === 0) console.error('...' + done + ' cases');
  }
  await w.terminate();

  console.log('\ncases scored: %d   (MIN_READABLE=%d)\n', done, MIN_READABLE);
  console.log('rule     set     correct  wrong  refused');
  for (const k of Object.keys(tally).sort()) {
    const t = tally[k], [rule, set] = k.split('|');
    console.log('%s %s %s %s %s',
      rule.padEnd(8), set.padEnd(7),
      String(t.correct).padStart(7), String(t.wrong).padStart(6), String(t.refused).padStart(8));
  }
  if (wrongs.length) {
    console.log('\nWRONG accepts (the gate is zero):');
    for (const r of wrongs) console.log('  ' + r.join('  '));
  } else {
    console.log('\nno wrong accepts under either rule.');
  }
})();

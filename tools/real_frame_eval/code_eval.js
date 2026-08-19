// Read every rendered code crop with real tesseract and score it against the
// known code. Run from the repo root:
//   node tools/real_frame_eval/code_eval.js code_crops
//
// The gate is WRONG=0. A low read rate is a nuisance the operator retries past;
// a wrong read is a corrupted record that looks exactly like a correct one.
const fs = require('fs');
const path = require('path');
const { createWorker } = require('tesseract.js');
const R = require('../../docs/capture/engine/replaycode.js');
const TRUTH = JSON.parse(fs.readFileSync(path.join(__dirname, 'code_truth.json'), 'utf8'));

(async () => {
  const dir = process.argv[2] || 'code_crops';
  const w = await createWorker('eng');
  await w.setParameters({
    tessedit_pageseg_mode: '7',
    tessedit_char_whitelist: R.ALPHABET,
  });
  let ok = 0, wrong = 0, none = 0;
  for (const f of fs.readdirSync(dir).filter(f => f.endsWith('.png')).sort()) {
    const stem = path.basename(f, '.png');
    const want = TRUTH[stem];
    if (!want) { console.log(stem.padEnd(10), 'no ground truth - skipped'); continue; }
    const { data } = await w.recognize(path.join(dir, f));
    const raw = (data.text || '').trim();
    const got = R.foldCode(raw);
    let verdict;
    if (got === want) { verdict = 'ok'; ok++; }
    else if (got === null) { verdict = 'NO READ'; none++; }
    else { verdict = 'WRONG'; wrong++; }
    console.log(stem.padEnd(10), 'want', want, 'raw', JSON.stringify(raw).padEnd(14),
                'got', String(got).padEnd(8), verdict);
  }
  await w.terminate();
  console.log(`\ncorrect ${ok}  no-read ${none}  WRONG ${wrong}`);
  if (wrong > 0) { console.error('GATE FAILED: a wrong read is a corrupted record'); process.exit(1); }
})();

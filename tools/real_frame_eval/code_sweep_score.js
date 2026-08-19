// Score every candidate crop set rendered by code_sweep.py, reusing one
// tesseract worker across all of them - worker startup dominates, recognition
// of a small crop does not.
//
//   node tools/real_frame_eval/code_sweep_score.js code_sweep_work/index.json
//
// Writes results.json beside the index. A candidate with ANY wrong read is
// reported as such and is disqualified by the caller regardless of its score.
const fs = require('fs');
const path = require('path');
const { createWorker } = require('tesseract.js');
const R = require('../../docs/capture/engine/replaycode.js');
const TRUTH = JSON.parse(fs.readFileSync(path.join(__dirname, 'code_truth.json'), 'utf8'));

(async () => {
  const indexPath = process.argv[2];
  const index = JSON.parse(fs.readFileSync(indexPath, 'utf8'));
  const w = await createWorker('eng');
  await w.setParameters({
    tessedit_pageseg_mode: '7',
    tessedit_char_whitelist: R.ALPHABET,
  });
  const results = [];
  for (const cand of index) {
    let correct = 0, wrong = 0, none = 0;
    for (const f of fs.readdirSync(cand.dir).filter(f => f.endsWith('.png')).sort()) {
      const want = TRUTH[path.basename(f, '.png')];
      if (!want) continue;
      const { data } = await w.recognize(path.join(cand.dir, f));
      const got = R.foldCode((data.text || '').trim());
      if (got === want) correct++;
      else if (got === null) none++;
      else wrong++;
    }
    results.push({ offsets: cand.offsets, correct, none, wrong });
    process.stdout.write(`${path.basename(cand.dir)} correct ${correct} none ${none} wrong ${wrong}\n`);
  }
  await w.terminate();
  fs.writeFileSync(path.join(path.dirname(indexPath), 'results.json'),
                   JSON.stringify(results, null, 2));
})();

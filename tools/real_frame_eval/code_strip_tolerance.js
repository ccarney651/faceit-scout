// Score the perturbed-strip crops through the SHIPPED read rule, so the answer
// is about the tool and not about tesseract in isolation.
//
// The rule (readReplayCode in both capture pages): run the contrast ladder,
// fold each pass, and accept only when the passes that produced a code all
// produced the SAME one. Disagreement refuses. That refusal is the only guard
// against a clipped glyph yielding six valid-but-wrong characters, which is
// precisely the failure a bad strip would cause - so evaluating single passes
// would measure the wrong thing.
//
//   node tools/real_frame_eval/code_strip_tolerance.js code_strip_crops
const fs = require('fs');
const path = require('path');
const { createWorker } = require('tesseract.js');
const R = require('../../docs/capture/engine/replaycode.js');

(async () => {
  const dir = process.argv[2] || 'code_strip_crops';
  const truth = JSON.parse(fs.readFileSync(path.join(dir, 'manifest.json'), 'utf8'));
  const files = fs.readdirSync(dir).filter(f => f.endsWith('.png')).sort();

  // stem__tag__contrast.png -> group by stem+tag, one ladder per group.
  const groups = new Map();
  for (const f of files) {
    const [stem, tag] = path.basename(f, '.png').split('__');
    const key = stem + '__' + tag;
    if (!groups.has(key)) groups.set(key, { stem, tag, files: [] });
    groups.get(key).files.push(f);
  }

  const w = await createWorker('eng');
  await w.setParameters({ tessedit_pageseg_mode: '7', tessedit_char_whitelist: R.ALPHABET });

  const byTag = new Map();
  const table = {};
  let done = 0;
  for (const { stem, tag, files: fl } of groups.values()) {
    const seen = [];
    for (const f of fl) {
      const { data } = await w.recognize(path.join(dir, f));
      const one = R.foldCode((data.text || '').replace(/\s+/g, ''));
      if (one && !seen.includes(one)) seen.push(one);
    }
    const want = truth[stem];
    const got = seen.length === 1 ? seen[0] : null;
    const verdict = got === want ? 'ok' : (got === null ? 'none' : 'WRONG');
    if (!byTag.has(tag)) byTag.set(tag, { ok: 0, none: 0, WRONG: 0, wrongs: [] });
    const b = byTag.get(tag);
    b[verdict]++;
    if (verdict === 'WRONG') b.wrongs.push(`${stem}:${want}->${got}`);
    (table[stem] = table[stem] || {})[tag] = { seen, got, want, verdict };
    if (++done % 40 === 0) process.stderr.write(`  ${done}/${groups.size}\n`);
  }
  await w.terminate();

  const order = [...byTag.keys()].sort();
  console.log('perturbation   correct  no-read  WRONG');
  for (const tag of order) {
    const b = byTag.get(tag);
    console.log(
      tag.padEnd(14),
      String(b.ok).padStart(5),
      String(b.none).padStart(8),
      String(b.WRONG).padStart(6),
      b.wrongs.length ? '  ' + b.wrongs.join(' ') : ''
    );
  }
  const totalWrong = order.reduce((n, t) => n + byTag.get(t).WRONG, 0);
  console.log(`\ntotal wrong across every perturbation: ${totalWrong}`);

  // Per-frame, per-offset ladder results, so a candidate guard can be tried
  // against this table without paying for tesseract again.
  fs.writeFileSync(path.join(dir, 'reads.json'), JSON.stringify(table, null, 1));
  console.log('wrote ' + path.join(dir, 'reads.json'));
})();

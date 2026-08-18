// OCR every crop under <dir>/<frame>/<variant>_<side><i>.png, configured
// exactly as the capture page configures its worker (psm 7 + gamertag
// whitelist), and write one JSON blob of every read.
const { createWorker } = require('tesseract.js');
const fs = require('fs');
const path = require('path');

(async () => {
  const root = process.argv[2], outFile = process.argv[3];
  const worker = await createWorker('eng');
  await worker.setParameters({
    tessedit_pageseg_mode: '7',
    tessedit_char_whitelist:
      "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_-.'~",
  });
  const out = {};
  for (const frame of fs.readdirSync(root)) {
    const dir = path.join(root, frame);
    if (!fs.statSync(dir).isDirectory()) continue;
    out[frame] = {};
    for (const f of fs.readdirSync(dir).filter(n => n.endsWith('.png'))) {
      const { data } = await worker.recognize(path.join(dir, f));
      out[frame][f.replace(/\.png$/, '')] = (data.text || '').replace(/\s+/g, ' ').trim();
      process.stderr.write('.');
    }
    process.stderr.write(' ' + frame + '\n');
  }
  await worker.terminate();
  fs.writeFileSync(outFile, JSON.stringify(out, null, 1));
  console.log('wrote', outFile);
})();

// Real tesseract.js over the real HUD crops, configured exactly as the capture
// page does: engine/refs.js sets tessedit_pageseg_mode 7, index.html adds the
// gamertag ASCII whitelist.
const { createWorker } = require('tesseract.js');
const fs = require('fs');
const path = require('path');

(async () => {
  const dir = process.argv[2];
  const worker = await createWorker('eng');
  await worker.setParameters({
    tessedit_pageseg_mode: '7',
    tessedit_char_whitelist:
      "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_-.'~",
  });
  const out = { a: [], b: [] };
  for (const side of ['a', 'b']) {
    for (let i = 0; i < 5; i++) {
      const f = path.join(dir, `${side}${i}.png`);
      const { data } = await worker.recognize(f);
      out[side].push((data.text || '').replace(/\s+/g, ' ').trim());
    }
  }
  await worker.terminate();
  console.log(JSON.stringify(out));
})();

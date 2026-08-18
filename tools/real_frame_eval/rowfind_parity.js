// Run the shipped engine/frames.js findNameRow over the raw bands dumped by
// rowfind_parity.py and print one JSON object of results.
const fs = require('fs');
const path = require('path');
const F = require(path.resolve(__dirname, '../../docs/capture/engine/frames.js'));

const dir = process.argv[2];
const out = {};
for (const { tag, w, h } of JSON.parse(fs.readFileSync(path.join(dir, 'index.json'), 'utf8'))) {
  const buf = fs.readFileSync(path.join(dir, tag + '.bin'));
  const r = F.findNameRow(new Uint8ClampedArray(buf.buffer, buf.byteOffset, buf.length), w, h);
  out[tag] = r ? [r.y, r.h] : null;
}
console.log(JSON.stringify(out));

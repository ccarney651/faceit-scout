// tools/replay_bot/build_capture_refs_resize.js
// Resize a batch of ref-capture images to REF_W x REF_H exactly the way
// crop.js's cell() resizes a LIVE crop, so a stored ref and a live read
// describe the same pixels.
//
// tools/build_capture_refs.py used to shrink these with
// cv2.resize(..., interpolation=cv2.INTER_AREA) - a different algorithm from
// the canvas imageSmoothingQuality='high' resize crop.js actually runs live.
// crop.js's own header warns about exactly this: a different resampler
// "looks perfectly fine to a human while scoring differently against every
// stored template. Nothing fails; matching just quietly gets worse." Measured
// 2026-09-16: the two algorithms disagree by a mean of 5.25 (max 59) on a
// 0-255 scale for the same source crop - not noise, a systematic mismatch,
// and worst on exactly the fine-detail heroes (Cassidy's hat brim, Zenyatta's
// face) whose matching had gone chronically bad.
//
// The ref-capture images themselves are saved at native resolution (Python's
// `_crop` is a plain array slice, no resize) - this is the ONLY place
// downsampling happens, so fixing it here is enough; no new capture needed.
//
// Usage: reads a JSON array of file paths from stdin, writes a JSON array of
// {path, b64} (b64 = base64 of REF_W*REF_H greyscale bytes, or null if the
// image could not be read) to stdout, same order.
//
//   node tools/replay_bot/build_capture_refs_resize.js < paths.json

'use strict';

const { loadImage, createCanvas } = require('@napi-rs/canvas');
const U = require('../../docs/capture/engine/util.js');

const REF_W = 64, REF_H = 36;

async function resizeOne(path) {
  let img;
  try {
    img = await loadImage(path);
  } catch (e) {
    return null;
  }
  // Mirrors crop.js's cell(): resize in colour via the canvas (this is the
  // step that must match), THEN take luma - not the other order.
  const cv = createCanvas(REF_W, REF_H);
  const cx = cv.getContext('2d', { willReadFrequently: true });
  cx.imageSmoothingEnabled = true;
  cx.imageSmoothingQuality = 'high';
  cx.drawImage(img, 0, 0, img.width, img.height, 0, 0, REF_W, REF_H);

  const d = cx.getImageData(0, 0, REF_W, REF_H).data;
  const px = new Uint8Array(REF_W * REF_H);
  for (let j = 0, k = 0; j < d.length; j += 4, k++) {
    px[k] = Math.round(0.299 * d[j] + 0.587 * d[j + 1] + 0.114 * d[j + 2]);
  }
  return U.bytesToB64(px);
}

async function main() {
  const chunks = [];
  for await (const chunk of process.stdin) chunks.push(chunk);
  const paths = JSON.parse(Buffer.concat(chunks).toString('utf8'));

  const out = [];
  for (const path of paths) {
    out.push({ path, b64: await resizeOne(path) });
  }
  process.stdout.write(JSON.stringify(out));
}

main().catch((e) => { console.error(e); process.exitCode = 1; });

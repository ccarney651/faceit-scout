"""Check the SHIPPED locator (engine/frames.js findNameRow) against real pixels.

rowfind_proto.py is a mirror of the JS, and mirrors drift. This dumps the exact
search band the browser would hand findNameRow(), for every frame / capture
resolution / perturbed calibration box in the sweep, runs the real JS over it,
and asserts the JS agrees with the prototype AND lands on the name row.
"""
import glob
import json
import pathlib
import subprocess
import sys

import numpy as np
from PIL import Image

sys.path.insert(0, 'tools/real_frame_eval')
from rowfind_proto import find_row, FILL_MAX, FRAC

NAT_W, NAT_H = 2557, 1438
BAND = (0.30, 1.15)
BOX = {'a': (57, 97, 700, 111), 'b': (1800, 97, 700, 111)}
PERTURB = [(dy, dh) for dy in (-15, -8, 0, 8, 15) for dh in (0.75, 0.9, 1.0, 1.15, 1.3)]
SCALES = [1.0, 1920 / NAT_W, 1600 / NAT_W, 1280 / NAT_W]

out = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else 'bands')
out.mkdir(parents=True, exist_ok=True)
index, expect = [], {}

for f in sorted(glob.glob('screenshots/*.png')):
    full = Image.open(f).convert('RGB')
    if full.size != (NAT_W, NAT_H):
        continue
    stem = pathlib.Path(f).stem.replace('Screenshot 2026-07-15 ', '')
    for sc in SCALES:
        im = full if sc == 1.0 else full.resize((round(NAT_W * sc), round(NAT_H * sc)), Image.LANCZOS)
        rgb = np.asarray(im)
        H, W, _ = rgb.shape
        for side, (bx, by, bw, bh) in BOX.items():
            for dy, dh in PERTURB:
                box = (bx * sc, (by + dy) * sc, bw * sc, bh * dh * sc)
                x0, x1 = max(0, int(box[0])), min(W, int(box[0] + box[2]))
                y0 = max(0, int(box[1] + box[3] * BAND[0]))
                y1 = min(H, int(box[1] + box[3] * BAND[1]))
                band = rgb[y0:y1, x0:x1]
                rgba = np.dstack([band, np.full(band.shape[:2], 255, np.uint8)]).astype(np.uint8)
                tag = f'{stem}_{round(W)}_{side}_{dy}_{dh}'
                (out / f'{tag}.bin').write_bytes(rgba.tobytes())
                index.append({'tag': tag, 'w': int(x1 - x0), 'h': int(y1 - y0)})
                r = find_row(rgb, box, band=BAND)
                expect[tag] = {
                    'proto': None if r is None else [r[0] - y0, r[1] - r[0] + 1],
                    'y0': y0, 'want': [158 / NAT_H * H, 171 / NAT_H * H],
                    'tol': max(3, round(4 * sc)),
                }

(out / 'index.json').write_text(json.dumps(index))
proc = subprocess.run(['node', 'tools/real_frame_eval/rowfind_parity.js', str(out)],
                      capture_output=True, text=True)
if proc.returncode:
    sys.exit(f'node failed:\n{proc.stdout}\n{proc.stderr}')
got = json.loads(proc.stdout)

def agrees(js, proto):
    # np.percentile interpolates; the JS picks its threshold from a 256-bin
    # histogram. That can move the run edge by a row, which the 25% pad
    # nameRow() adds absorbs - so allow one row of slack, not zero.
    if js is None or proto is None:
        return js == proto
    return abs(js[0] - proto[0]) <= 1 and abs(js[1] - proto[1]) <= 2


mismatch = [t for t in expect if not agrees(got[t], expect[t]['proto'])]
missed = []
for t, e in expect.items():
    g = got[t]
    if g is None:
        missed.append((t, 'none')); continue
    top, bot = e['y0'] + g[0], e['y0'] + g[0] + g[1] - 1
    if abs(top - e['want'][0]) > e['tol'] or abs(bot - e['want'][1]) > e['tol']:
        missed.append((t, f'{top}..{bot} want {e["want"][0]:.0f}..{e["want"][1]:.0f}'))

for t in mismatch[:10]:
    print(f'JS/proto MISMATCH {t}: js={got[t]} proto={expect[t]["proto"]}')
for t, why in missed[:10]:
    print(f'MISSED {t}: {why}')
print(f'{len(expect)} bands: {len(expect)-len(mismatch)} agree with the prototype, '
      f'{len(expect)-len(missed)} landed on the name row  '
      f'(FILL_MAX={FILL_MAX} FRAC={FRAC})')
sys.exit(1 if (mismatch or missed) else 0)

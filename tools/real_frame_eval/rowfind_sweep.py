"""Sweep the name-row locator over every real frame, perturbed boxes and
downscaled captures.

Truth for the native 2557x1438 frames: the HUD name text occupies y=158..171.
Everything is expressed as a fraction of frame height so the same truth holds
after a resize.
"""
import glob
import sys

import numpy as np
from PIL import Image

sys.path.insert(0, 'tools/real_frame_eval')
from rowfind_proto import find_row

NAT_W, NAT_H = 2557, 1438
TRUTH = (158 / NAT_H, 171 / NAT_H)
BOX = {'a': (57, 97, 700, 111), 'b': (1800, 97, 700, 111)}
FRAMES = [f for f in sorted(glob.glob('screenshots/*.png'))
          if Image.open(f).size == (NAT_W, NAT_H)]

# Calibration is never pixel-perfect, so shift the box's top and stretch its
# height; and the operator captures at whatever resolution the screen runs at.
PERTURB = [(dy, dh) for dy in (-15, -8, 0, 8, 15) for dh in (0.75, 0.9, 1.0, 1.15, 1.3)]
SCALES = [1.0, 1920 / NAT_W, 1600 / NAT_W, 1280 / NAT_W]

rows = []
for f in FRAMES:
    full = Image.open(f).convert('RGB')
    for sc in SCALES:
        im = full if sc == 1.0 else full.resize(
            (round(NAT_W * sc), round(NAT_H * sc)), Image.LANCZOS)
        rgb = np.asarray(im)
        H = rgb.shape[0]
        tol = max(3, round(4 * sc))
        for side, (bx, by, bw, bh) in BOX.items():
            for dy, dh in PERTURB:
                box = ((bx) * sc, (by + dy) * sc, bw * sc, bh * dh * sc)
                r = find_row(rgb, box)
                want = (TRUTH[0] * H, TRUTH[1] * H)
                ok = r is not None and abs(r[0] - want[0]) <= tol and abs(r[1] - want[1]) <= tol
                rows.append((f, sc, side, dy, dh, r, want, ok))

bad = [r for r in rows if not r[-1]]
for f, sc, side, dy, dh, r, want, _ in bad[:25]:
    got = 'none' if r is None else f'{r[0]}..{r[1]}'
    print(f'BAD {f.split(chr(92))[-1]:<34} w={round(NAT_W*sc):<5} {side} dy={dy:+3d} '
          f'dh={dh:.2f} -> {got:<10} want {want[0]:.0f}..{want[1]:.0f}')
print(f'\n{len(rows)-len(bad)}/{len(rows)} variants found the name row')

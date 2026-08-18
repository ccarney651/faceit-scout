"""Render the ten HUD name strips three ways, so the crops can be OCR'd and scored.

  shipped   engine/frames.js nameCanvas() as it stands: y = cell.y + 0.48h,
            height 0.42h. Straddles the portrait bottom, the name and the
            health bar.
  row       the per-side name-row locator (rowfind_proto) picks y/h once for
            all five slots; x is still the whole cell plus padding.
  rowtight  same y, plus a per-slot x span found from the same mask.

Preprocessing mirrors nameCanvas(): 6x upscale, greyscale, (g-128)*1.5+140.
"""
import json
import pathlib
import sys

import numpy as np
from PIL import Image

sys.path.insert(0, 'tools/real_frame_eval')
from rowfind_proto import find_row, profile

SC = 6


def _finish(img, out):
    c = img.resize((img.width * SC, img.height * SC), Image.LANCZOS).convert('L')
    c = c.point(lambda v: max(0, min(255, int((v - 128) * 1.5 + 140))))
    c.save(out)


def shipped_boxes(box):
    bx, by, bw, bh = box
    cw = bw / 5
    padX = max(4, round(cw * 0.05))
    return [(bx + i * cw - padX, by + bh * 0.48, cw + 2 * padX, bh * 0.42) for i in range(5)]


def row_boxes(rgb, box, tight):
    bx, by, bw, bh = box
    cw = bw / 5
    found = find_row(rgb, box, band=(0.30, 1.15))
    if found is None:
        return None
    y0, y1, T = found
    rh = y1 - y0 + 1
    pad = max(2, round(rh * 0.25))
    sy, sh = y0 - pad, rh + 2 * pad
    if not tight:
        padX = max(4, round(cw * 0.05))
        return [(bx + i * cw - padX, sy, cw + 2 * padX, sh) for i in range(5)]

    g = (0.299 * rgb[y0:y1 + 1, :, 0] + 0.587 * rgb[y0:y1 + 1, :, 1]
         + 0.114 * rgb[y0:y1 + 1, :, 2])
    on = g > T
    out = []
    gap = max(2, round(rh * 0.8))
    for i in range(5):
        cx0, cx1 = round(bx + i * cw), round(bx + (i + 1) * cw)
        col = on[:, cx0:cx1].any(axis=0)
        runs, st = [], None
        for j, v in enumerate(col):
            if v and st is None:
                st = j
            elif not v and st is not None:
                runs.append((st, j)); st = None
        if st is not None:
            runs.append((st, len(col)))
        merged = []
        for a, b in runs:
            if merged and a - merged[-1][1] < gap:
                merged[-1] = (merged[-1][0], b)
            else:
                merged.append((a, b))
        if not merged:
            padX = max(4, round(cw * 0.05))
            out.append((cx0 - padX, sy, cw + 2 * padX, sh)); continue
        a, b = max(merged, key=lambda r: r[1] - r[0])
        padX = max(3, round(rh * 0.4))
        out.append((cx0 + a - padX, sy, (b - a) + 2 * padX, sh))
    return out


def render(frame_path, boxes_by_side, outdir):
    img = Image.open(frame_path).convert('RGB')
    rgb = np.asarray(img)
    W, H = img.size
    outdir = pathlib.Path(outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    meta = {}
    for variant in ('shipped', 'row', 'rowtight'):
        for side, box in boxes_by_side.items():
            cells = (shipped_boxes(box) if variant == 'shipped'
                     else row_boxes(rgb, box, variant == 'rowtight'))
            if cells is None:
                meta[f'{variant}_{side}'] = None
                continue
            meta[f'{variant}_{side}'] = [[round(v, 1) for v in c] for c in cells]
            for i, (sx, sy, sw, sh) in enumerate(cells):
                crop = img.crop((max(0, round(sx)), max(0, round(sy)),
                                 min(W, round(sx + sw)), min(H, round(sy + sh))))
                _finish(crop, outdir / f'{variant}_{side}{i}.png')
    (outdir / 'meta.json').write_text(json.dumps(meta, indent=1))
    return meta


if __name__ == '__main__':
    BOX = {'a': (57, 97, 700, 111), 'b': (1800, 97, 700, 111)}
    m = render(sys.argv[1], BOX, sys.argv[2])
    print(json.dumps(m, indent=1))

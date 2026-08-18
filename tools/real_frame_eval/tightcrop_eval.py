"""Does cropping each name to its glyph run beat padding the whole cell?

The pad (5% of cell width each side) reaches into the NEIGHBOURING name plate
on tight HUD layouts and drags its border in, which tesseract reads as `|`,
`i`, `§` or `}`. Tightening to the glyph run - and explicitly dropping runs
that touch the cell edge, because those ARE the border - should remove it.

Measured over every frame with known ground truth, live and archived, because
the two sets have different cell spacing and an earlier measurement on the
archived set alone said tightening was slightly WORSE.
"""
import json
import pathlib
import sys

import numpy as np
from PIL import Image

sys.path.insert(0, 'tools/real_frame_eval')
from rowfind_proto import find_row

SC = 6
OLD_BOX = {'a': (57, 97, 700, 111), 'b': (1800, 97, 700, 111)}
LIVE_BOX = {'a': (129, 120, 660, 97), 'b': (1769, 118, 658, 101)}
OLD_A = ['PROXY', 'MAPPSY', 'TWERKNATION', 'JODAN', 'SZATAN']
OLD_B = ['HYBRID', 'NITROX', 'KRONUS', 'ZYDRA', 'SCRAINE']

FRAMES = {
    'Screenshot 2026-08-18 234927.png': (LIVE_BOX,
        ['GROKA', 'OTAKAW', 'JJUUZOU', 'CHEESEBURGER', 'OIDOPUAA'],
        ['GCB', 'KHALED', 'XYPHER', 'ASHBORN', 'NUT']),
    'Screenshot 2026-08-18 234953.png': (LIVE_BOX,
        ['GROKA', 'OTAKAW', 'KATTOS', 'CHEESEBURGER', 'OIDOPUAA'],
        ['GCB', 'SYNEX', 'XYPHER', 'ASHBORN', 'NUT']),
    'Screenshot 2026-08-18 235003.png': (LIVE_BOX,
        ['GROKA', 'OTAKAW', 'KATTOS', 'CHEESEBURGER', 'OIDOPUAA'],
        ['GCB', 'KHALED', 'XYPHER', 'ASHBORN', 'NUT']),
    'image.png': (OLD_BOX,
        ['MELLUN', 'RDY', 'DAZEDREOX', 'ENVII', 'HZL'],
        ['AUFY', 'ØØØØØ', 'WHITEBEARD', 'BUFAYEZ', 'JAMAL1505']),
}
for stem in ('200028', '231525', '231549', '231604', '231629', '231639', '231647', '231657'):
    FRAMES[f'Screenshot 2026-07-15 {stem}.png'] = (OLD_BOX, OLD_A, OLD_B)


def finish(crop, out):
    c = crop.resize((crop.width * SC, crop.height * SC), Image.LANCZOS).convert('L')
    c = c.point(lambda v: max(0, min(255, int((v - 128) * 1.5 + 140))))
    c.save(out)


def glyph_span(gray, cx0, cx1, ry, rh):
    """The glyph run inside one cell, or None. Runs touching the cell edge are
    the neighbouring plate's border, not a letter, and are dropped."""
    strip = gray[ry:ry + rh, cx0:cx1]
    on = (strip > 200).any(axis=0)
    runs, st = [], None
    for j, v in enumerate(on):
        if v and st is None:
            st = j
        elif not v and st is not None:
            runs.append((st, j)); st = None
    if st is not None:
        runs.append((st, len(on)))
    runs = [r for r in runs if not (r[0] <= 1 or r[1] >= len(on) - 1) or (r[1] - r[0]) > 6]
    if not runs:
        return None
    return cx0 + min(r[0] for r in runs) - 4, cx0 + max(r[1] for r in runs) + 4


def main(outdir):
    outdir = pathlib.Path(outdir)
    truth = {}
    for name, (box, ta, tb) in FRAMES.items():
        path = pathlib.Path('screenshots') / name
        if not path.exists():
            print('skip (missing):', name); continue
        im = Image.open(path).convert('RGB')
        rgb = np.asarray(im)
        gray = (0.299 * rgb[:, :, 0] + 0.587 * rgb[:, :, 1] + 0.114 * rgb[:, :, 2])
        W, H = im.size
        tag = name.replace('Screenshot ', '').replace('.png', '').replace(' ', '_')
        truth[tag] = {'a': ta, 'b': tb}
        for variant in ('pad', 'tight'):
            d = outdir / f'{tag}__{variant}'
            d.mkdir(parents=True, exist_ok=True)
            for side, (bx, by, bw, bh) in box.items():
                found = find_row(rgb, (bx, by, bw, bh), band=(0.30, 1.15))
                if not found:
                    print('no row:', tag, side); continue
                y0, y1, _ = found
                rh = y1 - y0 + 1
                pad = max(2, round(rh * 0.25))
                ry, rhp = y0 - pad, rh + 2 * pad
                cw = bw / 5
                padX = max(4, round(cw * 0.05))
                for i in range(5):
                    cx0, cx1 = round(bx + i * cw), round(bx + (i + 1) * cw)
                    if variant == 'tight':
                        span = glyph_span(gray, cx0, cx1, y0, rh)
                        sx, ex = span if span else (cx0 - padX, cx1 + padX)
                    else:
                        sx, ex = cx0 - padX, cx1 + padX
                    finish(im.crop((max(0, sx), max(0, ry), min(W, ex), min(H, ry + rhp))),
                           d / f'{side}{i}.png')
    (outdir / 'truth.json').write_text(json.dumps(truth, ensure_ascii=False), encoding='utf-8')
    print('rendered', len(truth), 'frames x 2 variants')


if __name__ == '__main__':
    main(sys.argv[1])

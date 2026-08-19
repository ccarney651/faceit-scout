"""Render the replay-code crop from a real frame, exactly as the browser would.

Preprocessing mirrors what the name crops needed (engine/frames.js nameCanvas):
upscale hard, greyscale, then push contrast. The code sits on a semi-transparent
plate over arbitrary game art, which is the same problem the name plates had -
and there the contrast step took reads from 15/90 to 77/90.

Geometry comes from the SHIPPED codeBox() offsets via code_offsets.json, written
by code_sweep.py, so this tool and the browser cannot disagree about where to
look. The constants below are duplicated in engine/frames.js codeCanvas(); they
must match, because the parity check compares rectangles and a different
contrast curve would still be two different images through the same box.
"""
import json
import pathlib
import sys

import numpy as np
from PIL import Image

sys.path.insert(0, 'tools/real_frame_eval')
from code_truth import strip_a

SCALE = 6
CONTRAST = 1.9        # harder than the name crops' 1.5: fewer, larger glyphs
MID = 140

DEFAULTS = {'DX': 1.079, 'DW': 0.127, 'DY': -0.495, 'DH': 0.198, 'PAD': 0.35}


def offsets():
    p = pathlib.Path('tools/real_frame_eval/code_offsets.json')
    if p.exists():
        return json.loads(p.read_text())
    return dict(DEFAULTS)


def code_box(a, o=None):
    o = o or offsets()
    x, y, w, h = a
    bw, bh = o['DW'] * w, o['DH'] * h
    px, py = bw * o['PAD'], bh * o['PAD']
    return (round(x + o['DX'] * w - px), round(y + o['DY'] * h - py),
            round(bw + 2 * px), round(bh + 2 * py))


def stem_of(frame_path):
    """'Screenshot 2026-07-15 231525.png' -> '231525'; 'image.png' -> 'image'."""
    return pathlib.Path(frame_path).stem.split()[-1]


def render(frame_path, out_dir, o=None):
    img = Image.open(frame_path).convert('RGB')
    a = strip_a(img.size)
    if a is None:
        return None
    bx, by, bw, bh = code_box(a, o)
    crop = img.crop((bx, by, bx + bw, by + bh)).resize(
        (bw * SCALE, bh * SCALE), Image.LANCZOS)
    g = np.asarray(crop.convert('L')).astype(np.int16)
    g = np.clip((g - 128) * CONTRAST + MID, 0, 255).astype(np.uint8)
    out_dir = pathlib.Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / (stem_of(frame_path) + '.png')
    Image.fromarray(g).save(out)
    return out


if __name__ == '__main__':
    import glob
    dest = sys.argv[1] if len(sys.argv) > 1 else 'code_crops'
    for f in sorted(glob.glob('screenshots/*.png')):
        p = render(f, dest)
        if p:
            print('rendered', p)

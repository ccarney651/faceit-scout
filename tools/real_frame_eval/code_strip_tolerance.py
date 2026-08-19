"""How wrong can the calibration strip be before the replay-code read breaks?

`codeBox()` is expressed as fractions OF THE TEAM 1 STRIP, so it inherits
whatever auto-calibrate produced. That is the design, and it is why the crop
survives every resolution tested. It also means the crop is only ever as good
as the strip - and the strip is not always auto-calibrate's.

Two ways a scout gets a different strip:

  - They drag the boxes by hand. `calMsg` in engine/calibration.js actively
    TELLS them to when auto-calibrate scores low ("drag them right on the
    portraits"), so this is a supported path, not misuse.
  - They are not on 16:9. AUTO_STRIPS' fractions mis-size, auto-calibrate
    cannot fix a scale error by sweeping translation, and the operator is
    pushed down the same manual path.

Both reduce to one question this can answer without an ultrawide monitor: how
far can the strip deviate before the code is misread? The failure that matters
is a WRONG code - six valid characters that belong to another game - because it
attributes a whole map's comps to the wrong match and looks exactly like a
correct read.

Perturbs each frame's own strip along one axis at a time (scale, then dx, then
dy) and renders the three-contrast ladder for each. Score with:
  node tools/real_frame_eval/code_strip_tolerance.js code_strip_crops
"""
import json
import pathlib
import shutil
import sys

import numpy as np
from PIL import Image

sys.path.insert(0, 'tools/real_frame_eval')
from code_crop import CONTRASTS, MID, SCALE, code_box, offsets, stem_of
from code_truth import CODES, strip_a

# One axis at a time: a combined sweep hides which axis is the tight one, and
# the answer is only actionable if it names the direction to be careful in.
# 1% steps across the range where the first coarse pass showed the boundary
# sits, so a candidate guard can be simulated offline against this table
# instead of re-running tesseract for every variant of it.
SCALES = [round(1 + i / 100, 2) for i in range(-5, 6)]
SHIFTS = [round(i / 100, 2) for i in range(-5, 6)]


def perturb(a, scale=1.0, dx=0.0, dy=0.0):
    """Scale about the strip's centre, then shift by fractions of its own size.

    Scaling about the centre is the honest model of a hand-drag: a scout aims
    at the same five portraits and gets the extent a little wrong, they do not
    anchor the top-left corner and stretch.
    """
    x, y, w, h = a
    cx, cy = x + w / 2, y + h / 2
    nw, nh = w * scale, h * scale
    return (cx - nw / 2 + dx * w, cy - nh / 2 + dy * h, nw, nh)


def render_one(img, a, out_dir, stem, tag, o):
    bx, by, bw, bh = code_box(a, o)
    if bw <= 0 or bh <= 0:
        return 0
    crop = img.crop((bx, by, bx + bw, by + bh)).resize((bw * SCALE, bh * SCALE), Image.LANCZOS)
    base = np.asarray(crop.convert('L')).astype(np.int16)
    for c in CONTRASTS:
        g = np.clip((base - 128) * c + MID, 0, 255).astype(np.uint8)
        Image.fromarray(g).save(out_dir / f"{stem}__{tag}__{c}.png")
    return 1


def main() -> None:
    dest = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else 'code_strip_crops')
    if dest.exists():
        shutil.rmtree(dest)
    dest.mkdir(parents=True)
    o = offsets()

    cases = []
    for s in SCALES:
        cases.append((f"scale{s:+.2f}".replace('+', ''), dict(scale=s)))
    for d in SHIFTS:
        cases.append((f"dx{d:+.2f}", dict(dx=d)))
    for d in SHIFTS:
        cases.append((f"dy{d:+.2f}", dict(dy=d)))

    manifest, n = {}, 0
    for f in sorted(pathlib.Path('screenshots').glob('*.png')):
        stem = stem_of(f)
        if stem not in CODES:
            continue
        img = Image.open(f).convert('RGB')
        a = strip_a(img.size)
        if a is None:
            continue
        for tag, kw in cases:
            n += render_one(img, perturb(a, **kw), dest, stem, tag, o)
        manifest[stem] = CODES[stem]

    (dest / 'manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    print(f"rendered {n} perturbed crops x {len(CONTRASTS)} contrasts "
          f"over {len(manifest)} frames, {len(cases)} perturbations each")


if __name__ == '__main__':
    main()

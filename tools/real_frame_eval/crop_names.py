"""Crop the ten HUD name strips from a real frame.

Preprocessing mirrors engine/frames.js nameCanvas(): 6x upscale, greyscale,
contrast g = (g-128)*1.5 + 140.

Geometry is self-calibrated from the frame rather than taken from roi_profiles:
this screenshot predates profile 1 by 16 minutes and is 2557x1438, and the stored
portrait boxes do not line up with its name row. Finding the text columns directly
keeps the test measuring OCR instead of my crop error.
"""
import pathlib
import sys

import numpy as np
from PIL import Image

SHOT = pathlib.Path(sys.argv[1])
OUT = pathlib.Path(sys.argv[2])
OUT.mkdir(parents=True, exist_ok=True)

img = Image.open(SHOT).convert('RGB')
W, H = img.size
g = np.asarray(img.convert('L')).astype(np.int16)

# The HUD name row sits just under the portraits and just above the health/ult
# bars. Density alone finds the BARS (solid white blocks outscore glyphs), so the
# row is taken from the layout: names occupy ~0.104-0.123 of frame height.
white = (g > 205)
top, bot = int(H * 0.104), int(H * 0.123)


def clusters(x0, x1, keep):
    """The five name-text runs in one team's half of the row.

    Both halves also contain background scenery bright enough to survive the
    threshold, so size-ranking picks junk. The HUD is anchored to the OUTER edge
    of the frame instead: team A's names are the leftmost five runs, team B's the
    rightmost five, and everything inboard of those is the map behind the HUD.
    """
    col = white[top:bot, x0:x1].sum(axis=0)
    on = col > 2
    runs, start = [], None
    for i, v in enumerate(on):
        if v and start is None:
            start = i
        elif not v and start is not None:
            runs.append((start + x0, i + x0))
            start = None
    if start is not None:
        runs.append((start + x0, x1))
    # Merge adjacent letters into one word; drop anything too narrow to be a name.
    merged = []
    for a, b in runs:
        if merged and a - merged[-1][1] < 20:
            merged[-1] = (merged[-1][0], b)
        else:
            merged.append((a, b))
    merged = [(a, b) for a, b in merged if b - a > 25]
    return merged[:5] if keep == 'left' else merged[-5:]


for side, (x0, x1, keep) in (('a', (0, W // 2, 'left')), ('b', (W // 2, W, 'right'))):
    runs = clusters(x0, x1, keep)
    assert len(runs) == 5, f"side {side}: found {len(runs)} name runs, expected 5"
    for i, (a, b) in enumerate(runs):
        pad = 10
        crop = img.crop((max(0, a - pad), top, min(W, b + pad), bot))
        crop = crop.resize((crop.width * 6, crop.height * 6), Image.LANCZOS).convert('L')
        crop = crop.point(lambda v: max(0, min(255, int((v - 128) * 1.5 + 140))))
        crop.save(OUT / f"{side}{i}.png")

print(f"wrote 10 strips from {SHOT.name} ({W}x{H}), name row y={top}..{bot}")

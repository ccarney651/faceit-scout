"""Render every crop variant for every real frame in screenshots/."""
import glob
import pathlib
import sys

from PIL import Image

sys.path.insert(0, 'tools/real_frame_eval')
from crop_variants import render

# The five-portrait strip per side, as auto-calibrate would place it on these
# 2557x1438 frames: portraits occupy y=97..147, which is the top 45% (refs.json
# top_fraction) of a 111px cell; cells are 140px wide from x=57 and x=1800.
BOX = {'a': (57, 97, 700, 111), 'b': (1800, 97, 700, 111)}
OUT = pathlib.Path(sys.argv[1])

for f in sorted(glob.glob('screenshots/*.png')):
    if Image.open(f).size != (2557, 1438):
        continue
    tag = pathlib.Path(f).stem.replace('Screenshot 2026-07-15 ', '').replace(' ', '_')
    render(f, BOX, OUT / tag)
    print('rendered', tag)

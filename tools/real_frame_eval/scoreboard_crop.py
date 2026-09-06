"""Render the scrim scoreboard crop from every truth frame, one PNG per
preprocessing variant, so `scoreboard_eval.js` can OCR and score them.

    python tools/real_frame_eval/scoreboard_crop.py [out_dir]

ONE CROP BOX FOR EVERY FRAME AND EVERY VARIANT. In the real tool the box is
operator-drawn ("Set SCOREBOARD box"), not derived from calibration, so there is
no geometry to reproduce - only a sensible box to fix. Fixing it is the point:
the whole reason this harness exists is that section 8.4 of the design found
every previous colour measurement had confounded the variable under test with
the map behind it. Change the box and you are measuring the box.

Variants, all upscaled 8x to match scoreCanvas():

  raw      what ships today. The colour crop, straight to tesseract.
  localg6  luminance minus its own local mean (BoxBlur r=12), gain 6, inverted
           to dark-on-light. THE WINNER, and by a wide margin - 286/480 values
           and 45/80 complete rows against raw's 109 and 16.

The families that lost are kept as functions rather than deleted, because each
answers a question that would otherwise get asked again:

  sat/satc  section 8.3's recommendation, the saturation channel. It assumed the
            board is the saturated thing on screen, which was true of TEAM
            COLOURED rows and is false of white ones - see the block above the
            definitions. 80/480, and zero rows on a dark frame.
  gray      plain luminance. The control proving the win is not merely "drop the
            colour": 82/480.
  lumhi     a hard GLOBAL bright threshold. The control proving the win is
            LOCALITY and not merely a bias toward bright pixels: 118/480, and
            5/80 teams because a global bright cut erases the coloured headers.
  tophat    morphological white top-hat. Locality helps; this particular
            morphology does not, at least at r=11. 86/480.

The transform is applied at NATIVE resolution and upscaled afterwards.
Upscaling first would let interpolation invent saturation along every glyph
edge, which is the signal `sat` is supposed to be reading.
"""
import json
import pathlib
import sys

import numpy as np
from PIL import Image, ImageFilter

SC = 8
ROOT = pathlib.Path(__file__).resolve().parents[2]
TRUTH = json.loads((pathlib.Path(__file__).parent / 'scoreboard_truth.json').read_text('utf8'))
SHOTS = ROOT / 'screenshots'


def frame_path(stem):
    return SHOTS / ('Screenshot 2026-09-06 %s.png' % stem)


def crop_of(img):
    b = TRUTH['box']
    w, h = img.size
    x, y = int(w * b['x']), int(h * b['y'])
    return img.crop((x, y, x + int(w * b['w']), y + int(h * b['h'])))


def upscale(img):
    return img.resize((img.width * SC, img.height * SC), Image.LANCZOS)


def variant_raw(crop):
    return upscale(crop)


def variant_gray(crop):
    return upscale(crop.convert('L'))


def _sat_array(crop):
    a = np.asarray(crop.convert('RGB')).astype(np.int16)
    return a.max(axis=2) - a.min(axis=2)


def variant_sat(crop):
    v = 255 - 1.6 * _sat_array(crop)
    return upscale(Image.fromarray(np.clip(v, 0, 255).astype(np.uint8), 'L'))


def variant_satc(crop):
    v = np.clip(255 - 1.6 * _sat_array(crop), 0, 255)
    v = np.clip((v - 128) * 1.5 + 140, 0, 255)
    return upscale(Image.fromarray(v.astype(np.uint8), 'L'))


# The saturation family below was section 8.3's recommendation and is kept only
# so the retraction stays reproducible. It scored 80/480 against the shipped
# path's 109 and, on a dark frame, read all four chrome lines and ZERO of ten
# rows. The reason is structural: it separates board from map by assuming the
# board is the saturated thing on screen, which was true when rows were team
# coloured and is false now they are white. White is the least saturated colour
# there is, so the channel erases precisely the text it was meant to rescue.
#
# What replaces it keys on LUMINANCE and on being LOCAL, because the rows are
# white - maximum luminance - and the failure is a bright background rather than
# a dark one. Each asks "is this brighter than what surrounds it" rather than
# "is this brighter than some fixed value", which is the question a global
# threshold cannot answer on a board drawn over an uncontrolled world.


def _to_dark_on_light(a):
    """Tesseract is happiest with dark text on a light ground; every local
    operator here produces the opposite, so they all end through this."""
    return Image.fromarray(np.clip(a, 0, 255).astype(np.uint8), 'L')


def variant_tophat(crop):
    # White top-hat: the image minus its morphological opening, which keeps
    # bright features THINNER than the structuring element and discards broad
    # bright regions. Glyph strokes are ~3px at native scale and a bright wall
    # is not, so the wall goes and the text stays. The HUD's dark glyph outline
    # helps here rather than hindering - it is the local minimum the opening
    # spreads back over the stroke.
    g = crop.convert('L')
    opened = g.filter(ImageFilter.MinFilter(11)).filter(ImageFilter.MaxFilter(11))
    d = np.asarray(g).astype(np.int16) - np.asarray(opened).astype(np.int16)
    return upscale(_to_dark_on_light(255 - d * 3))


def variant_local(crop):
    # Plain local contrast: brightness minus a blurred copy of itself. Cruder
    # than the top-hat and included to tell "local helps" apart from "this
    # particular morphology helps".
    g = crop.convert('L')
    bg = g.filter(ImageFilter.BoxBlur(12))
    d = np.asarray(g).astype(np.float32) - np.asarray(bg).astype(np.float32)
    return upscale(_to_dark_on_light(255 - d * 4))


def variant_lumhi(crop):
    # A hard global stretch at the top of the range: white text is at or near
    # 255 and most map pixels are not. The control for whether the LOCALITY of
    # the two above is what matters, or merely their bias toward bright pixels.
    g = np.asarray(crop.convert('L')).astype(np.float32)
    return upscale(_to_dark_on_light(255 - (g - 160) * 4))


def local_with(radius, gain):
    """`variant_local` with its two knobs exposed, for sweeping.

    RADIUS is what counts as "surroundings". Too small and the blur follows the
    glyph itself, so the text subtracts away; too large and it stops being local
    and the operator degrades toward a global threshold. Text is ~20px tall at
    native scale, so the useful range is bounded either side by that.

    GAIN is how hard the difference is stretched before clipping. It trades
    faint strokes recovered against background texture promoted into ink.
    """
    def fn(crop):
        g = crop.convert('L')
        bg = g.filter(ImageFilter.BoxBlur(radius))
        d = np.asarray(g).astype(np.float32) - np.asarray(bg).astype(np.float32)
        return upscale(_to_dark_on_light(255 - d * gain))
    return fn


# Radius 12 and gain 6 are measured, not chosen. Sweeping radius at fixed gain
# (6/12/20) moved 236/239/235 - flat, so the radius only has to be roughly the
# scale of a glyph. Sweeping gain at fixed radius (4/6/8/12) moved 239/286/225/160,
# which is a real peak: below it faint strokes never reach ink, above it the
# background texture does.
VARIANTS = {
    'raw': variant_raw,
    'localg6': local_with(12, 6),
}


def main():
    out = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else 'scoreboard_crops')
    out.mkdir(parents=True, exist_ok=True)
    for stem in TRUTH['frames']:
        p = frame_path(stem)
        if not p.exists():
            print('MISSING', p)
            continue
        crop = crop_of(Image.open(p).convert('RGB'))
        for name, fn in VARIANTS.items():
            dest = out / ('%s.%s.png' % (stem, name))
            fn(crop).save(dest)
        print(stem, crop.size, '->', ' '.join(VARIANTS))
    print('\nwrote', len(list(out.glob('*.png'))), 'crops to', out)


if __name__ == '__main__':
    main()

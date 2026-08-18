"""Prototype of the per-side name-row locator, for tuning against real frames.

The shipped version lives in engine/frames.js; this exists so the thresholds can
be swept over screenshots/ without a browser. Keep the two in step.
"""
import numpy as np


def profile(rgb, box, band=(0.35, 1.15)):
    """Per-row fill / horizontal-transition counts over one side's whole strip."""
    bx, by, bw, bh = box
    H, W, _ = rgb.shape
    x0, x1 = max(0, int(bx)), min(W, int(bx + bw))
    y0, y1 = max(0, int(by + bh * band[0])), min(H, int(by + bh * band[1]))
    sub = rgb[y0:y1, x0:x1].astype(np.int32)
    g = 0.299 * sub[:, :, 0] + 0.587 * sub[:, :, 1] + 0.114 * sub[:, :, 2]
    # 88th percentile picks the glyph strokes out of the plate, but a bright
    # scene behind the HUD can push it to 255 and select nothing at all -
    # clamp it so there is always a usable text/background split.
    T = float(min(max(np.percentile(g, 88), 120.0), 230.0))
    on = g > T
    fill = on.mean(axis=1)
    tr = (on[:, 1:] != on[:, :-1]).sum(axis=1) / on.shape[1]
    return y0, y1, fill, tr, on, T


FILL_MAX = 0.42     # a full health bar fills ~0.55 of the strip; text ~0.15-0.32
FRAC = 0.35         # rows scoring this fraction of the peak join the run


def find_row(rgb, box, band=(0.35, 1.15), verbose=False):
    y0, y1, fill, tr, on, T = profile(rgb, box, band)
    score = np.where(fill <= FILL_MAX, tr, 0.0)
    if score.max() <= 0:
        return None
    runs, st = [], None
    thr = FRAC * score.max()
    for i, v in enumerate(score >= thr):
        if v and st is None:
            st = i
        elif not v and st is not None:
            runs.append((st, i - 1)); st = None
    if st is not None:
        runs.append((st, len(score) - 1))

    def quiet(s, e):
        above = fill[max(0, s - 3):s]
        below = fill[e + 1:e + 4]
        a = above.mean() if len(above) else 0.5
        b = below.mean() if len(below) else 0.5
        return max(0.0, 1.0 - (a + b) / 0.20)

    best, bestv = None, -1
    for s, e in runs:
        v = tr[s:e + 1].mean() * quiet(s, e)
        if verbose:
            print(f'    run y={y0+s}..{y0+e} meanTr={tr[s:e+1].mean():.3f} '
                  f'quiet={quiet(s,e):.2f} score={v:.3f}')
        if v > bestv:
            best, bestv = (s, e), v
    s, e = best
    return y0 + s, y0 + e, T

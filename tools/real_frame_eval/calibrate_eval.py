"""Score auto-calibration against every real frame in screenshots/.

WHY THIS EXISTS. Auto-calibrate is the first thing a new contributor does and
the whole capture funnel is behind it, so "it works on my machine" is not a
standard it can be held to. Until now every judgement about the sweep came from
one operator's screen, one capture mode at a time, and two of those judgements
were wrong in opposite directions on the same afternoon.

WHAT IT REPLICATES. The real path, not an approximation of it:
  boxesFromStrips()  - engine/calibration.js, including the width-relative
                       projection of the vertical fractions
  cellGrayPadded()   - engine/frames.js: crop (x + w*LF, y, w*(1-LF), h*TF),
                       scale to (REF_W+2*PAD)x(REF_H+2*PAD), grayscale by
                       0.299/0.587/0.114
  bestMatch(fast)    - engine/refs.js: centre offset only, mean-centred and
                       L2-normalised correlation against refs.json
  withinFrame()      - candidates that leave the frame are refused, because an
                       off-frame crop is uniform black and correlates highly
                       with almost anything (measured 2026-09-07: y=-27.9
                       scored 10/10)

CAVEAT, and it is the same one recorded in the calibration-relative-geometry
note: these frames are screenshots, and a screenshot's HUD does not necessarily
sit where a live capture's does. So a score here is NOT a promise about live.
What it is good for is COMPARISON - does a change to AUTO_STRIPS, to the sweep's
range, or to its step size make more of these frames read, or fewer. Run it
before and after, and never trust an improvement measured on one frame.

THE FRAMES ARE NOT IN THE REPOSITORY. screenshots/ is gitignored, same as the
other real_frame_eval tools' inputs, so the numbers in this file's docstrings
and in engine/calibration.js are a record of what WAS measured rather than
something a fresh clone can reproduce. Keep the frames that produced a decision;
a frame that shows a failure is worth more than ten that pass. To add one from a
live session, with the replay showing the board:

    grabFrame().toBlob(b => { const a = document.createElement('a');
      a.href = URL.createObjectURL(b); a.download = 'frame.png'; a.click(); });

That is the real captured frame, not a screenshot of the browser, and it is the
only input that reproduces what the tool actually sees.

Usage:
    .venv/Scripts/python.exe tools/real_frame_eval/calibrate_eval.py
    .venv/Scripts/python.exe tools/real_frame_eval/calibrate_eval.py --sweep
"""
from __future__ import annotations

import argparse
import base64
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
REFS_JSON = ROOT / "docs" / "capture" / "refs.json"
SHOTS = ROOT / "screenshots"

PAD = 2
CONFIDENT = 0.55
AUTO_STRIPS = {
    "a": (0.0506, 0.0832, 0.2579, 0.0675),
    "b": (0.6912, 0.0818, 0.2573, 0.0705),
}


def load_refs():
    d = json.loads(REFS_JSON.read_text(encoding="utf-8"))
    w, h, lf, tf = d["w"], d["h"], d["left_fraction"], d["top_fraction"]
    by_variant: dict[str, list] = {"a": [], "b": []}
    for r in d["refs"]:
        px = np.frombuffer(base64.b64decode(r["d"]), dtype=np.uint8).astype(np.float64)
        c = px - px.mean()
        norm = np.sqrt((c * c).sum()) or 1.0
        by_variant[r["v"]].append((r["n"], c, norm))
    # Stack per variant so one matmul scores every hero at once.
    packed = {}
    for v, items in by_variant.items():
        names = [i[0] for i in items]
        mat = np.stack([i[1] / i[2] for i in items])       # each row L2-normalised
        packed[v] = (names, mat)
    return w, h, lf, tf, packed


REF_W, REF_H, LF, TF, PACKED = load_refs()
WORK_W, WORK_H = REF_W + 2 * PAD, REF_H + 2 * PAD


def strip_box(R, side, dx, dy):
    """One strip. Each is searched independently - see auto_calibrate."""
    rx, ry, rw, _ = R
    ref_h = rw * 9 / 16
    fx, fy, fw, fh = AUTO_STRIPS[side]
    return (rx + (fx + dx) * rw, ry + (fy + dy) * ref_h, fw * rw, fh * ref_h)


def score_strip(img, b, side):
    """{distinct, sum} over one strip's five cells."""
    seen, total = set(), 0.0
    x, y, w, h = b
    for i in range(5):
        g = cell_gray_padded(img, (x + i * w / 5, y, w / 5, h))
        win = g[PAD:PAD + REF_H, PAD:PAD + REF_W].ravel()
        c = win - win.mean()
        if np.sqrt((c * c).mean()) < MIN_RMS:
            continue
        n = np.sqrt((c * c).sum()) or 1.0
        names, mat = PACKED[side]
        v = mat @ c / n
        j = int(v.argmax())
        total += float(v[j])
        if v[j] >= CONFIDENT:
            seen.add(names[j])
    return len(seen), total


def in_frame(b, W, H):
    return b[0] >= 0 and b[1] >= 0 and b[0] + b[2] <= W and b[1] + b[3] <= H


def boxes_from_strips(R, dx, dy):
    """engine/calibration.js boxesFromStrips - vertical fractions against width."""
    rx, ry, rw, rh = R
    ref_h = rw * 9 / 16
    out = {}
    for side, (fx, fy, fw, fh) in AUTO_STRIPS.items():
        out[side] = (rx + (fx + dx) * rw, ry + (fy + dy) * ref_h, fw * rw, fh * ref_h)
    return out


def within_frame(cand, W, H):
    return all(b[0] >= 0 and b[1] >= 0 and b[0] + b[2] <= W and b[1] + b[3] <= H
               for b in cand.values())


def cell_gray_padded(img: Image.Image, cell):
    """engine/frames.js cellGrayPadded."""
    x, y, w, h = cell
    fx, fy = x + w * LF, y
    fw, fh = w * (1 - LF), h * TF
    box = (fx, fy, fx + fw, fy + fh)
    crop = img.resize((WORK_W, WORK_H), Image.BILINEAR, box=box)
    a = np.asarray(crop, dtype=np.float64)
    return 0.299 * a[..., 0] + 0.587 * a[..., 1] + 0.114 * a[..., 2]


MIN_RMS = 12.0

def best_score(gray, variant):
    """engine/refs.js bestMatch with fast=true: the centre offset only.

    Returns (score, hero) and refuses a crop with no contrast. A near-uniform
    crop - a white team banner, a black bar - has a tiny L2 norm, and dividing
    by it turns noise into a confident-looking correlation. Measured over these
    frames, real portrait cells never fall below 25.8 RMS, so 12 discards none
    of them.
    """
    win = gray[PAD:PAD + REF_H, PAD:PAD + REF_W].ravel()
    c = win - win.mean()
    if np.sqrt((c * c).mean()) < MIN_RMS:
        return -1.0, None
    n = np.sqrt((c * c).sum()) or 1.0
    names, mat = PACKED[variant]
    v = mat @ c / n
    i = int(v.argmax())
    return float(v[i]), names[i]


def score_candidate(img, cand, W, H):
    """engine/calibration.js scoreCandidate: {ok, sum} in one pass.

    A hero may not appear twice on one team - OW2 is role locked - so a side
    that returns the same hero for several cells is not reading portraits, it is
    reading noise that happens to sit nearest one reference. Only the best cell
    of a duplicated hero counts as confident. This is what catches a placement
    on the white team banners, where every cell came back the same hero at the
    same score just above threshold.
    """
    ok, total = 0, 0.0
    for side, b in cand.items():
        x, y, w, h = b
        seen = {}
        for i in range(5):
            s, hero = best_score(cell_gray_padded(img, (x + i * w / 5, y, w / 5, h)), side)
            total += max(s, 0.0)
            if s >= CONFIDENT and hero is not None:
                if s > seen.get(hero, -1):
                    seen[hero] = s
        ok += len(seen)
    return ok, total


def detect_content_rect(img: Image.Image):
    """engine/frames.js detectContentRect: trim near-black borders."""
    W, H = img.size
    sw = min(320, W)
    sh = max(1, round(H * sw / W))
    a = np.asarray(img.resize((sw, sh), Image.BILINEAR), dtype=np.int16)[..., :3].max(2)
    BLACK, cy, cx = 24, int(sh * 0.2), int(sw * 0.2)
    t = 0
    while t < cy and a[t].max() < BLACK:
        t += 1
    b = sh - 1
    while b > sh - 1 - cy and a[b].max() < BLACK:
        b -= 1
    l = 0
    while l < cx and a[:, l].max() < BLACK:
        l += 1
    r = sw - 1
    while r > sw - 1 - cx and a[:, r].max() < BLACK:
        r -= 1
    sx, sy = W / sw, H / sh
    return (l * sx, t * sy, (r - l + 1) * sx, (b - t + 1) * sy)


def auto_calibrate(img, coarse=0.005, span_x=4, span_y=16, fine=0.001,
                   fine_span=3, starts=2):
    """EACH STRIP IS SEARCHED INDEPENDENTLY.

    A single shared (dx, dy) shifts both strips together, which cannot correct a
    WIDTH error: the resulting offset is f*(R.w - true_w), small at the left
    strip's f=0.05 and large at the right strip's f=0.69. Measured on a frame
    the operator exported 2026-09-07, the two strips wanted dx values 0.005
    apart - about 13px - and the joint search compromised, placing the right
    strip correctly (Mauga/Hanzo/Mei/Mercy/Lucio, all confirmed correct) and the
    left strip wrong (only one of five right). Searched independently the left
    strip lands on the operator's own hand-set box.

    THE FINE STEP MUST BE FINER THAN THE MATCHER'S TOLERANCE. Sliding a strip
    a pixel at a time against the real references, on crops the operator
    exported 2026-09-07, the window in which a strip reads at all is about FOUR
    pixels wide: LEFT reads distinct=4 at +12px and distinct=1 at both +8 and
    +14. The old fine step of 0.0025 is 6.4px on a 2570-wide frame, so the grid
    straddled that window entirely. By distinct heroes over screenshots/:
    0.0025/span2 6.71, 0.001/span3 7.47, 0.001/span5 7.50, 0.0005/span6 7.53.
    """
    W, H = img.size
    R = detect_content_rect(img)
    out, oks = {}, 0
    for side in ("a", "b"):
        best = (-1, -1e9)
        best_box = strip_box(R, side, 0, 0)
        cands = []
        for iy in range(-span_y, span_y + 1):
            for ix in range(-span_x, span_x + 1):
                dx, dy = ix * coarse, iy * coarse
                b = strip_box(R, side, dx, dy)
                if not in_frame(b, W, H):
                    continue
                cands.append((score_strip(img, b, side), dx, dy, b))
        cands.sort(key=lambda t: t[0], reverse=True)
        for r, dx, dy, b in cands[:starts]:
            if r > best:
                best, best_box = r, b
            for iy in range(-fine_span, fine_span + 1):
                for ix in range(-fine_span, fine_span + 1):
                    b2 = strip_box(R, side, dx + ix * fine, dy + iy * fine)
                    if not in_frame(b2, W, H):
                        continue
                    rr = score_strip(img, b2, side)
                    if rr > best:
                        best, best_box = rr, b2
        out[side] = best_box
        oks += best[0]
    return oks, 0.0, 0.0, out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sweep", action="store_true",
                    help="also report the best score reachable anywhere in range")
    args = ap.parse_args()

    frames = sorted(p for p in SHOTS.glob("*.png"))
    rows, total = [], 0
    for p in frames:
        with Image.open(p) as im:
            im = im.convert("RGB")
            if im.size[0] < 2000:
                continue
            ok, dx, dy, _ = auto_calibrate(im)
            extra = ""
            if args.sweep:
                W, H = im.size
                R = detect_content_rect(im)
                bestok = -1
                for iy in range(-44, 17):
                    for ix in range(-12, 13):
                        cand = boxes_from_strips(R, ix * 0.0025, iy * 0.0025)
                        if not within_frame(cand, W, H):
                            continue
                        k, _s = score_candidate(im, cand, W, H)
                        bestok = max(bestok, k)
                extra = f"  ceiling {bestok}/10"
            rows.append((p.name, ok, dx, dy, extra))
            total += ok
            print(f"{p.name[-22:]:24s} {ok:2d}/10  dx={dx:+.4f} dy={dy:+.4f}{extra}")

    n = len(rows)
    if not n:
        print("no frames found")
        return 1
    good = sum(1 for r in rows if r[1] >= 8)
    print()
    print(f"{n} frames | mean {total / n:.2f}/10 | {good} at 8+/10 "
          f"({100 * good / n:.0f}%) | {sum(1 for r in rows if r[1] <= 4)} at 4-/10")
    return 0


if __name__ == "__main__":
    sys.exit(main())

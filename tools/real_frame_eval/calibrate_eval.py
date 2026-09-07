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


def best_score(gray, variant):
    """engine/refs.js bestMatch with fast=true: the centre offset only."""
    win = gray[PAD:PAD + REF_H, PAD:PAD + REF_W].ravel()
    c = win - win.mean()
    n = np.sqrt((c * c).sum()) or 1.0
    _, mat = PACKED[variant]
    return float((mat @ c).max() / n)


def score_candidate(img, cand, W, H):
    """engine/calibration.js scoreCandidate: {ok, sum} in one pass."""
    ok, total = 0, 0.0
    for side, b in cand.items():
        x, y, w, h = b
        for i in range(5):
            s = best_score(cell_gray_padded(img, (x + i * w / 5, y, w / 5, h)), side)
            total += s
            if s >= CONFIDENT:
                ok += 1
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


def auto_calibrate(img, coarse=0.005, span_x=4, span_y=16, fine=0.0025,
                   fine_span=2, starts=2):
    """The real two-pass sweep: a fine-ish coarse grid, then the top N refined.

    Chosen by measurement over these frames, not by taste:

        coarse .01  x2/y8   1 start   mean 7.67   8+: 26/36   4-: 4  ~110 passes
        coarse .005 x2/y16  1 start   mean 8.08   8+: 28/36   4-: 2  ~190
        coarse .005 x4/y16  1 start   mean 8.11   8+: 28/36   4-: 2  ~322
        coarse .005 x2/y16  top-2     mean 8.19   8+: 28/36   4-: 2  ~215
        coarse .005 x4/y16  top-2     mean 8.22   8+: 28/36   4-: 2  ~347  <-

    The single-start .01 grid was not merely coarse, it was WRONG on two frames:
    it settled on dy=+0.075 where the answer was -0.055, losing six portraits on
    one and five on the other, because the fine pass may only search around the
    coarse winner and so cannot leave a false basin. Refining the top TWO
    coarse candidates is what buys that back.

    x4 keeps the horizontal range at the shipped +/-0.02. x2 scores about the
    same on these frames and costs a third less, but halving a range no frame
    here exercises is how a tool breaks for the one operator who needs it.
    """
    W, H = img.size
    R = detect_content_rect(img)
    best = boxes_from_strips(R, 0, 0)
    best_rank = score_candidate(img, best, W, H) if within_frame(best, W, H) else (-1, -1e9)

    cand_list = []
    for iy in range(-span_y, span_y + 1):
        for ix in range(-span_x, span_x + 1):
            dx, dy = ix * coarse, iy * coarse
            cand = boxes_from_strips(R, dx, dy)
            if not within_frame(cand, W, H):
                continue
            cand_list.append((score_candidate(img, cand, W, H), dx, dy, cand))
    cand_list.sort(key=lambda t: t[0], reverse=True)

    bx = by = 0.0
    for r, dx, dy, cand in cand_list[:starts]:
        if r > best_rank:
            best_rank, best, bx, by = r, cand, dx, dy
        for iy in range(-fine_span, fine_span + 1):
            for ix in range(-fine_span, fine_span + 1):
                ndx, ndy = dx + ix * fine, dy + iy * fine
                c = boxes_from_strips(R, ndx, ndy)
                if not within_frame(c, W, H):
                    continue
                rr = score_candidate(img, c, W, H)
                if rr > best_rank:
                    best_rank, best, bx, by = rr, c, ndx, ndy
    return best_rank[0], bx, by, best


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

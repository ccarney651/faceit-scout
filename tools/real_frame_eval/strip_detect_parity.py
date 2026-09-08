"""Run the REAL engine/calibration.js detectStrips over the real capture frames.

WHY NOT JUST PORT IT TO PYTHON. calibrate_eval.py replicates the pipeline in
numpy, and a replica can agree with itself while disagreeing with the browser -
which is exactly how a previous feature scored 12/12 offline and read nothing
live (see the calibration-relative-geometry note). detectStrips is pure over an
RGBA byte array, so there is no need to replicate it: this feeds the shipped
module the same bytes a canvas would and reads back what it actually returns.

Python decodes the PNG and scores the resulting boxes with the matcher replica;
node runs the detector. Usage:

    .venv/Scripts/python.exe tools/real_frame_eval/strip_detect_parity.py
"""
from __future__ import annotations

import argparse
import colorsys
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))
import calibrate_eval as CE  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
CALIBRATION_JS = ROOT / "docs" / "capture" / "engine" / "calibration.js"
SHOTS = ROOT / "screenshots"

# Boxes confirmed by a free search over position AND scale, then checked by eye
# against the drawn overlay - see the 2026-09-07 session. x only; y and w are
# reported as errors against these.
TRUTH: dict[str, tuple[float, float, float]] = {
    "cfg-SCREEN-windowed.png": (129.5, 1769.5, 120),
    "cfg-SCREEN-BORDERLESS.png": (53.3, 1801.3, 98),
    "cfgOWDIRECT-BORDERLESSWINDOW.png": (53.3, 1801.3, 98),
    "cfgOWDIRECT-WINDOWED.png": (135.5, 1773.5, 120),
    "frame.png": (133.5, 1773.5, 130),
    "frame(1).png": (133.5, 1773.5, 130),
}

_DRIVER = r"""
const fs = require('fs');
var module = { exports: {} };
%(SRC)s
const Mod = module.exports;
const cal = Mod.make({
  doc: { getElementById: () => null, createElement: () => ({ getContext: () => ({}) }) },
  video: { videoWidth: 0, videoHeight: 0 },
  ov: { width: 0, height: 0 }, octx: {}, boxKeys: ['a', 'b'],
});
const meta = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'));
const data = new Uint8ClampedArray(fs.readFileSync(process.argv[3]));
console.log(JSON.stringify({
  fixed: cal.detectStrips(data, meta.w, meta.h),
  swept: cal.detectStripsByHue(data, meta.w, meta.h),
}));
"""


# OW's accessibility options replace the team and enemy UI colours. The portrait
# art itself is not repainted by that setting, so only the team-coloured pixels
# move. This is a simulation - a frame from someone actually running those
# settings would be worth more - but it is the only such frame available.
PALETTES: tuple[tuple[str, float, float], ...] = (
    ("default", 0.0, 0.0),
    ("purple/gold", -40.0, -70.0),
    ("teal/magenta", -45.0, 60.0),
    ("green/orange", -110.0, -25.0),
)


def recolour(a: np.ndarray, deg_a: float, deg_b: float) -> np.ndarray:
    if not deg_a and not deg_b:
        return a
    out = a.astype(np.float32).copy()
    r, g, b = out[..., 0], out[..., 1], out[..., 2]
    sat = out.max(2) - out.min(2)
    blue = (b > 90) & (b - r > 40) & (sat > 50)
    red = (r > 90) & (r - b > 40) & (r - g > 40) & (sat > 50)
    for mask, deg in ((blue, deg_a), (red, deg_b)):
        if not mask.any():
            continue
        px = out[mask] / 255.0
        hsv = np.array([colorsys.rgb_to_hsv(*q) for q in px])
        hsv[:, 0] = (hsv[:, 0] + deg / 360.0) % 1.0
        out[mask] = np.array([colorsys.hsv_to_rgb(*q) for q in hsv]) * 255.0
    return np.clip(out, 0, 255).astype(np.uint8)


def detect(node: str, driver: Path, img: Image.Image) -> dict:
    W, H = img.size
    h = max(1, round(H * 0.30))
    rgba = np.asarray(img.convert("RGBA"))[:h].tobytes()
    with tempfile.TemporaryDirectory() as td:
        meta = Path(td) / "meta.json"
        blob = Path(td) / "top.bin"
        meta.write_text(json.dumps({"w": W, "h": h}), encoding="utf-8")
        blob.write_bytes(rgba)
        proc = subprocess.run([node, str(driver), str(meta), str(blob)],
                              capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr)
    return json.loads(proc.stdout.strip() or "null")


def read_at(img: Image.Image, det: dict | None) -> tuple[int, dict]:
    """Refine both strips of a proposal and report distinct heroes."""
    if not det:
        return 0, {}
    oks, out = 0, {}
    for s in ("a", "b"):
        k, b = refine(img, (det[s]["x"], det[s]["y"], det[s]["w"], det[s]["h"]), s)
        oks += max(k, 0)
        out[s] = b
    return oks, out


def in_frame(b, W, H) -> bool:
    return b[0] >= 0 and b[1] >= 0 and b[0] + b[2] <= W and b[1] + b[3] <= H


def score(img: Image.Image, box, side: str) -> int:
    x, y, w, h = box
    seen = set()
    for i in range(5):
        s, hero = CE.best_score(CE.cell_gray_padded(img, (x + i * w / 5, y, w / 5, h)), side)
        if s >= CE.CONFIDENT and hero:
            seen.add(hero)
    return len(seen)


def refine(img: Image.Image, box, side: str):
    """engine/calibration.js refineStrip: +/-3 x, +/-5 y, ranked by distinct."""
    W, H = img.size
    x, y, w, h = box
    best, best_box = -1, box
    for dx in range(-3, 4):
        for dy in range(-5, 6):
            b = (x + dx, y + dy, w, h)
            if not in_frame(b, W, H):
                continue
            d = score(img, b, side)
            if d > best:
                best, best_box = d, b
    return best, best_box


def report_default(node: str, driver: Path) -> int:
    frames = sorted(p for p in SHOTS.glob("*.png"))
    total = n = good = refused = 0
    for p in frames:
        with Image.open(p) as im:
            im = im.convert("RGB")
            if im.size[0] < 2000:
                continue
            n += 1
            d = detect(node, driver, im)["fixed"]
            if d is None:
                refused += 1
                print(f"{p.name[-30:]:32s}  refused (no band)")
                continue
            oks, out = read_at(im, d)
            total += oks
            good += oks >= 8
            err = ""
            if p.name in TRUTH:
                tax, tbx, ty = TRUTH[p.name]
                err = (f"  dx_a={out['a'][0] - tax:+6.1f} dx_b={out['b'][0] - tbx:+6.1f}"
                       f" dy={out['a'][1] - ty:+5.1f}")
            print(f"{p.name[-30:]:32s} {oks:2d}/10  pitch={d['pitch']:6.2f} "
                  f"band={d['bandTop']}{err}")
    print()
    print(f"{n} frames | {n - refused} detected | mean over detected "
          f"{total / max(n - refused, 1):.2f}/10 | {good} at 8+ | {refused} refused")
    return 0


def report_palettes(node: str, driver: Path) -> int:
    """Stage 1 vs stage 2 over recoloured team UI - the colourblind case."""
    names = [f for f in TRUTH if (SHOTS / f).exists()]
    if not names:
        print("none of the known-truth frames are present in screenshots/")
        return 1
    head = "  ".join(f"{n:>14s}" for n, _, _ in PALETTES)
    print(f"{'frame':32s}  {head}")
    print(f"{'':32s}  " + "  ".join(f"{'fixed/swept':>14s}" for _ in PALETTES))
    for f in names:
        with Image.open(SHOTS / f) as im:
            im = im.convert("RGB")
            a = np.asarray(im)
            cells = []
            for _, da, db in PALETTES:
                img = im if not da and not db else Image.fromarray(recolour(a, da, db))
                got = detect(node, driver, img)
                fixed, _ = read_at(img, got["fixed"])
                swept = 0
                for cand in got["swept"]:
                    swept = max(swept, read_at(img, cand)[0])
                    if swept >= 8:
                        break
                cells.append(f"{fixed:>6d}/{swept:<7d}")
            print(f"{f[:31]:32s}  " + "  ".join(f"{c:>14s}" for c in cells))
    return 0


def report_frame(node: str, driver: Path, name: str) -> int:
    """Every proposal from both stages, and what each one actually reads.

    This is the loop for a frame that failed in the field: the stages are cheap
    and wrong-or-right in ways a single score hides, so print them all.
    """
    p = SHOTS / name
    if not p.exists():
        print(f"{p} not found")
        return 1
    with Image.open(p) as im:
        im = im.convert("RGB")
        got = detect(node, driver, im)
        print(f"{name}  {im.size[0]}x{im.size[1]}")
        one = got["fixed"]
        if one is None:
            print("  stage 1 (blue/red):  no band")
        else:
            oks, _ = read_at(im, one)
            print(f"  stage 1 (blue/red):  {oks}/10  pitch={one['pitch']:.2f} "
                  f"band={one['bandTop']}")
        if not got["swept"]:
            print("  stage 2 (hue sweep): nothing proposed")
        # The cascade scores every proposal WHERE IT STANDS and refines only
        # the best few, so `stands` is what actually decides the shortlist -
        # reporting only the refined score would flatter a candidate the real
        # code never refines.
        rows = []
        for i, cand in enumerate(got["swept"]):
            stands = sum(score(im, (cand[s]["x"], cand[s]["y"], cand[s]["w"], cand[s]["h"]), s)
                         for s in ("a", "b"))
            oks, _ = read_at(im, cand)
            rows.append((i, stands, oks, cand))
        picks = {i for i, _, _, _ in sorted(rows, key=lambda r: -r[1])[:2]}
        for i, stands, oks, cand in rows:
            hues = cand.get("hues")
            deg = f"{hues[0] * 15}/{hues[1] * 15} deg" if hues else "?"
            mark = "  <-- refined by the cascade" if i in picks else ""
            if i in picks and oks >= 8:
                mark = "  <-- ACCEPTED"
            print(f"  stage 2 candidate {i}: stands {stands:2d}/10 -> refined {oks:2d}/10  "
                  f"hues={hues} ({deg})  pitch={cand['pitch']:.2f} band={cand['bandTop']}  "
                  f"a.x={cand['a']['x']:.0f} b.x={cand['b']['x']:.0f}{mark}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--frame", metavar="NAME",
                    help="diagnose ONE frame: what each stage proposed and what "
                         "each proposal reads")
    ap.add_argument("--palettes", action="store_true",
                    help="compare the fixed palette against the hue sweep on "
                         "recoloured team UI (the colourblind case)")
    args = ap.parse_args()
    node = shutil.which("node")
    if not node:
        print("node not on PATH")
        return 1
    src = CALIBRATION_JS.read_text(encoding="utf-8")
    with tempfile.TemporaryDirectory() as td:
        driver = Path(td) / "driver.js"
        driver.write_text(_DRIVER % {"SRC": src}, encoding="utf-8")
        if not SHOTS.exists() or not any(SHOTS.glob("*.png")):
            print("screenshots/ is empty - it is gitignored; ask the operator for frames")
            return 1
        if args.frame:
            return report_frame(node, driver, args.frame)
        return report_palettes(node, driver) if args.palettes else report_default(node, driver)


if __name__ == "__main__":
    sys.exit(main())

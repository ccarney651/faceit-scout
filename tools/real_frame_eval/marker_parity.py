"""Run the REAL scoreboard.js findMarkerBox over the real capture frames.

WHY THIS EXISTS. `scoreboard.test.js` exercises findMarkerBox against synthetic
frames it paints itself, and those tests pass. On 2026-09-07 the detector was
nevertheless recorded as "has never succeeded in the field" and carried into
`specs/2026-09-07-calibration-robustness-handoff.md` as a known bug. It was
never measured: no console output, no frame, only the inference that because
Next round did not block on the events panel, the marker box must be null.

Running it over the operator's frames says otherwise - it finds the box on every
frame that actually has the two green rules drawn, including `frame(1).png`,
the frame exported during the test that was believed to prove it broken. The
frames are produced by the page's own `grabFrame()`, so the bytes here are the
bytes `autoBoardBox()` sees; colour space and scaling are not variables.

Same discipline as strip_detect_parity.py: python decodes the PNG, node runs the
SHIPPED module. A numpy replica of the detector could agree with itself while
the browser reads nothing, which is the failure mode this harness exists to
rule out.

`screenshots/` is gitignored, so this is operator-only - a fresh clone has no
frames to run it against. Usage:

    .venv/Scripts/python.exe tools/real_frame_eval/marker_parity.py
    .venv/Scripts/python.exe tools/real_frame_eval/marker_parity.py screenshots/frame(1).png
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
SHOTS = ROOT / "screenshots"
SCOREBOARD = ROOT / "docs" / "capture" / "scoreboard.js"

# The detector's own green test, mirrored here ONLY to explain a result - never
# to decide one. The verdict column always comes from the shipped module.
RUNNER = """
const fs = require('fs');
const SB = require(process.argv[2]);
const meta = JSON.parse(fs.readFileSync(process.argv[3], 'utf8'));
const raw = fs.readFileSync(process.argv[4]);
const data = new Uint8ClampedArray(raw.buffer, raw.byteOffset, raw.length);
console.log(JSON.stringify(SB.findMarkerBox(data, meta.w, meta.h)));
"""


def rule_rows(a: np.ndarray) -> tuple[int, int]:
    """Green pixels, and how many rows look like a rule to the detector."""
    r = a[:, :, 0].astype(np.int16)
    g = a[:, :, 1].astype(np.int16)
    b = a[:, :, 2].astype(np.int16)
    m = (g > 150) & (r < 120) & (b < 130) & ((g - r) > 60) & ((g - b) > 50)
    h, w = m.shape
    min_span = max(40, round(w * 0.08))
    rows = 0
    for y in range(h):
        xs = np.flatnonzero(m[y])
        if xs.size == 0:
            continue
        span = int(xs[-1] - xs[0] + 1)
        if span >= min_span and xs.size / span >= 0.8:
            rows += 1
    return int(m.sum()), rows


def run(paths: list[Path]) -> int:
    tmp = Path(tempfile.mkdtemp(prefix="marker_parity_"))
    runner = tmp / "runner.js"
    runner.write_text(RUNNER, encoding="utf-8")
    found = 0
    print("%-38s %11s %8s %9s  %s"
          % ("frame", "size", "greenpx", "rule rows", "findMarkerBox"))
    for p in paths:
        try:
            a = np.asarray(Image.open(p).convert("RGBA"))
        except Exception as exc:  # a directory of screenshots holds all sorts
            print("%-38s  unreadable: %s" % (p.name, exc))
            continue
        h, w, _ = a.shape
        green, rows = rule_rows(a)
        rgba = tmp / "frame.rgba"
        rgba.write_bytes(a.tobytes())
        meta = tmp / "frame.json"
        meta.write_text(json.dumps({"w": int(w), "h": int(h)}), encoding="utf-8")
        out = subprocess.run(
            ["node", str(runner), str(SCOREBOARD), str(meta), str(rgba)],
            capture_output=True, text=True, check=False)
        box = (out.stdout or out.stderr).strip() or "?"
        if box not in ("null", "?"):
            found += 1
        print("%-38s %11s %8d %9d  %s"
              % (p.name, "%dx%d" % (w, h), green, rows, box))
    print("\n%d of %d frames yielded a box." % (found, len(paths)))
    return found


if __name__ == "__main__":
    args = [Path(a) for a in sys.argv[1:]]
    run(args if args else sorted(SHOTS.glob("*.png")))

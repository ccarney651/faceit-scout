"""Browser capture app: the auto-calibrate sweep must not crash on a fresh page.

The offset-sweep in autoCalibrate() scores candidate box placements through
scoreBoxes() -> cellGrayPadded() -> the cached work-canvas context (wctx).
On a fresh page load wctx is undefined until ensureWork() runs, and readComp()
— the only other caller of ensureWork() — needs boxes already set. So the very
first Auto-calibrate click used to throw inside the sweep and silently do
nothing. scoreBoxes() now calls ensureWork() itself; this test pins that.

ensureWork/cellGrayPadded moved into docs/capture/engine/frames.js,
scoreBoxes into docs/capture/engine/calibration.js, and bestMatch itself
later into docs/capture/engine/refs.js (all three shared with scrim.html;
see tools/capture_divergence.py and each module's own docstring). scoreBoxes
still calls ensureWork/cellGrayPadded/bestMatch as bare identifiers, now
resolved through the free-variable convention all three modules document:
`const {ensureWork, cellGrayPadded} = frames`, `const {bestMatch} = refs`.
This test exercises the REAL frames.js, calibration.js and refs.js modules
(via their real make(), same as a page would), so the module boundary
doesn't hide a regression of the original bug.
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

ENGINE_FRAMES = Path(__file__).resolve().parents[1] / "docs" / "capture" / "engine" / "frames.js"
ENGINE_CALIBRATION = Path(__file__).resolve().parents[1] / "docs" / "capture" / "engine" / "calibration.js"
ENGINE_REFS = Path(__file__).resolve().parents[1] / "docs" / "capture" / "engine" / "refs.js"

_STUBS = r"""
const PAD=2, REF_W=64, REF_H=36, LF=0.42, TF=0.45;
const REFS=[
  {n:'Ana',  g:'g1', v:'a', c:new Float32Array(REF_W*REF_H), norm:1},
  {n:'Genji',g:'g2', v:'b', c:new Float32Array(REF_W*REF_H), norm:1},
];
function makeCtx(){ return { drawImage(){}, getImageData(){ return {data:new Uint8ClampedArray(1)}; }, putImageData(){} }; }
global.document={ createElement(t){ if(t!=='canvas') throw new Error('unexpected createElement '+t);
  return {width:300,height:150,getContext:()=>makeCtx()}; } };
global.localStorage={ setItem(){}, getItem:()=>null, removeItem(){} };
global.vid={videoWidth:1920,videoHeight:1080,srcObject:{}};
var module = { exports: {} };
"""

# Load the real modules and wire them exactly like index.html does
# (`const frames = OWDBFrames.make({doc, video, onStop}); const
# {ensureWork, cellGrayPadded} = frames;` then
# `const cal = OWDBCalibration.make({doc, video, ov, octx}); const
# {scoreBoxes} = cal;` then `const refs = OWDBRefs.make({doc}); const
# {bestMatch} = refs;`), so scoreBoxes below calls the actual production
# ensureWork/cellGrayPadded/scoreBoxes/bestMatch, not a re-implementation.
_WIRE_FRAMES = r"""
const OWDBFrames = module.exports;
const frames = OWDBFrames.make({ doc: global.document, video: global.vid, onStop: null });
const { ensureWork, cellGrayPadded } = frames;
"""

_WIRE_CAL = r"""
const OWDBCalibration = module.exports;
const cal = OWDBCalibration.make({ doc: global.document, video: global.vid, ov: {width:0,height:0}, octx: makeCtx() });
const { scoreBoxes } = cal;
"""

_WIRE_REFS = r"""
const OWDBRefs = module.exports;
const refs = OWDBRefs.make({ doc: global.document });
const { bestMatch } = refs;
"""

_BODY = r"""
// Fresh-session state: wctx is undefined here (ensureWork never called) —
// this is the exact crash the sweep used to hit.
const R={x:0,y:0,w:1920,h:1080};
const best={a:{x:97,y:89,w:495,h:73},b:{x:1327,y:88,w:494,h:76}};
const sc=scoreBoxes({}, best);
return (typeof sc==='number') && Number.isFinite(sc);
"""


def test_auto_calibrate_sweep_does_not_crash_on_fresh_session() -> None:
    node = shutil.which("node")
    if not node:
        pytest.skip("node not available to run the capture app's helpers")
    frames_src = ENGINE_FRAMES.read_text(encoding="utf-8")
    calibration_src = ENGINE_CALIBRATION.read_text(encoding="utf-8")
    refs_src = ENGINE_REFS.read_text(encoding="utf-8")
    src = (
        _STUBS + "\n" + frames_src + "\n" + _WIRE_FRAMES + "\n"
        + calibration_src + "\n" + _WIRE_CAL + "\n"
        + refs_src + "\n" + _WIRE_REFS + "\n"
        + "\nconsole.log(JSON.stringify((()=>{" + _BODY + "})()));"
    )
    # Written to a temp file rather than passed via `node -e` - three whole
    # modules (refs.js's header comment alone is a few KB) can exceed
    # Windows' CreateProcess command-line length limit ("[WinError 206] The
    # filename or extension is too long").
    script = Path(__file__).resolve().parent / "_tmp_autocalibrate_check.js"
    script.write_text(src, encoding="utf-8")
    try:
        proc = subprocess.run([node, str(script)], capture_output=True, text=True)
    finally:
        script.unlink(missing_ok=True)
    assert proc.returncode == 0, f"node failed:\n{proc.stderr}"
    assert proc.stdout.strip() == "true"

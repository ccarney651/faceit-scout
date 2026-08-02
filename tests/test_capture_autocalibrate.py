"""Browser capture app: the auto-calibrate sweep must not crash on a fresh page.

The offset-sweep in autoCalibrate() scores candidate box placements through
scoreBoxes() -> cellGrayPadded() -> the cached work-canvas context (wctx).
On a fresh page load wctx is undefined until ensureWork() runs, and readComp()
— the only other caller of ensureWork() — needs boxes already set. So the very
first Auto-calibrate click used to throw inside the sweep and silently do
nothing. scoreBoxes() now calls ensureWork() itself; this test pins that.
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

APP = Path(__file__).resolve().parents[1] / "docs" / "capture" / "index.html"


def _extract(start: str, end: str) -> str:
    html = APP.read_text(encoding="utf-8")
    s = html.index(start)
    e = html.index(end)
    assert e > s, "extraction anchors moved in index.html"
    return html[s : e + len(end)]


# The sweep function and the matcher block it depends on (ensureWork /
# cellGrayPadded / bestMatch). Anchors asserted inside _extract.
_SCORE = _extract("function scoreBoxes(frame, bxs){", "return sum; }")
_MATCHER = _extract("const work=document.createElement('canvas'); let wctx;", "return best; }")

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
    src = _STUBS + "\n" + _SCORE + "\n" + _MATCHER + "\nconsole.log(JSON.stringify((()=>{" + _BODY + "})()));"
    proc = subprocess.run([node, "-e", src], capture_output=True, text=True)
    assert proc.returncode == 0, f"node failed:\n{proc.stderr}"
    assert proc.stdout.strip() == "true"

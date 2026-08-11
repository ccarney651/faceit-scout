"""Browser capture app: a prior OCR load failure must not permanently block
side-detection on later Snapshot presses.

warmOcr() preloads tesseract.js in the background the moment the tool is
capture-ready, swallowing any rejection (to avoid unhandled-rejection
console spam). ensureSideResolved() used to check the resulting sticky
_ocrLoadFailed flag FIRST and refuse to even attempt detectSides() again if
it was set - so one transient failure (a network blip during that silent
background attempt, say) locked every subsequent Snapshot into an instant
"OCR engine failed to load" message for the rest of the session, with no
way forward except noticing and clicking the separate Re-detect button.
Since ocrWorker()/ocrNames() already clear their own caches on failure and
are now bounded by real timeouts (see test_capture_ocr_worker.py), retrying
on every Snapshot is cheap when the network recovered and still safe when
it hasn't. This pins that ensureSideResolved() tries again regardless of
the flag, and that a subsequent success clears the flag.
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
    e = html.index(end, s) + len(end)
    assert e > s, "extraction anchors moved in index.html"
    return html[s:e]


def _state() -> str:
    html = APP.read_text(encoding="utf-8")
    s = html.index("let _ocrWorker=null")
    e = html.index(";", s) + 1
    return html[s:e]


_ESC = ("function esc(s){return String(s==null?'':s).replace(/[&<>\"']/g,"
        "c=>({'&':'&amp;','<':'&lt;','>':'&gt;','\"':'&quot;',\"'\":'&#39;'}[c]));}")
_ENSURE = _extract("async function ensureSideResolved(){", "}finally{ s._detecting=false; }\n}")

_HARNESS = r"""
global.setDetectMsg=()=>{};
global.snapMsg=()=>{};
global.ocrProgress=()=>{};
global.ico=()=>'';
global.sideTeamName=()=>'Team A';
global.currentLeftId=()=>'t1';
"""


def _run(body: str) -> str:
    node = shutil.which("node")
    if not node:
        pytest.skip("node not available to run the capture app's helpers")
    src = _HARNESS + "\n" + _state() + "\n" + _ESC + "\n" + _ENSURE + "\n" + body
    proc = subprocess.run([node, "-e", src], capture_output=True, text=True, timeout=15)
    assert proc.returncode == 0, f"node failed:\n{proc.stderr}"
    return proc.stdout.strip()


def test_a_stale_load_failure_flag_does_not_block_a_fresh_attempt() -> None:
    body = r"""
    let calls=0;
    _ocrLoadFailed=true; _ocrLoadError='could not load the OCR library (offline?)';
    global.session={sideResolved:false};
    global.detectSides=async()=>{ calls++; return {left:'t1'}; };
    ensureSideResolved().then(ok => console.log(JSON.stringify({ok, calls})));
    """
    out = _run(body)
    import json
    result = json.loads(out)
    assert result == {"ok": True, "calls": 1}, result


def test_a_repeat_failure_still_reports_the_reason_not_a_silent_block() -> None:
    body = r"""
    _ocrLoadFailed=true; _ocrLoadError='could not load the OCR library (offline?)';
    global.session={sideResolved:false};
    let calls=0;
    global.detectSides=async()=>{ calls++; throw new Error('OCR is taking too long to load - try again'); };
    ensureSideResolved().then(ok => console.log(JSON.stringify({ok, calls})));
    """
    out = _run(body)
    import json
    result = json.loads(out)
    # It must have actually TRIED (not short-circuited) and surfaced false.
    assert result == {"ok": False, "calls": 1}, result

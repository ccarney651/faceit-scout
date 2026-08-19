"""Browser capture app (scrims): a stalled OCR read must not hang the page.

index.html got a read deadline and wedged-worker teardown when the reported
"detecting sides..." hang came back after the *load* timeout shipped: a
tesseract.js `recognize()` that never returns leaves the caller awaiting
forever, and because tesseract processes jobs sequentially on one worker, it
takes every later read down with it.

scrim.html never got that fix. It shares the same worker across four reads
(HUD names, the scoreboard's two crops, the replay code), so one wedged call
hangs all of them - and hangs them silently, which is the failure shape that
cost this branch the most time: ensureSideResolved's catch block cannot name
a reason for an error that never arrives.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

APP = Path(__file__).resolve().parents[1] / "docs" / "capture" / "scrim.html"


def _names_js(timeout_ms: int) -> str:
    html = APP.read_text(encoding="utf-8")
    # Anchored on the stable prefix, not the full var list, so adding another
    # _ocr* state var doesn't break this extraction - same as the equivalent
    # slice in test_capture_ocr_worker.py.
    state_start = html.index("let _ocrWorker=null")
    state = html[state_start:html.index(";", state_start) + 1]
    start = html.index("const OCR_READ_TIMEOUT_MS=")
    end = html.index("return out; }", start) + len("return out; }")
    body = html[start:end]
    assert "const OCR_READ_TIMEOUT_MS=8000;" in body, "read-timeout constant moved/changed"
    body = body.replace("const OCR_READ_TIMEOUT_MS=8000;", f"const OCR_READ_TIMEOUT_MS={timeout_ms};")
    return state + "\n" + body


def _run_names(body: str, timeout_ms: int = 50) -> str:
    node = shutil.which("node")
    if not node:
        pytest.skip("node not available to run the capture app's helpers")
    stubs = r"""
    global.boxes={a:{x:0,y:0,w:500,h:80}, b:{x:600,y:0,w:500,h:80}};
    global.vid={srcObject:{}};
    global.grabFrame=()=>({});
    global.nameRow=()=>({y:40,h:14});
    global.nameCanvas=()=>({});
    global.snapMsg=()=>{};
    """
    src = stubs + "\n" + _names_js(timeout_ms) + "\n" + body
    script = Path(__file__).resolve().parent / "_tmp_scrim_ocr_read_check.js"
    script.write_text(src, encoding="utf-8")
    try:
        proc = subprocess.run([node, str(script)], capture_output=True, text=True, timeout=15)
    finally:
        script.unlink(missing_ok=True)
    assert proc.returncode == 0, f"node failed:\n{proc.stderr}"
    return proc.stdout.strip()


def test_a_stalled_hud_name_read_times_out_instead_of_hanging_forever() -> None:
    body = r"""
    global.ocrWorker=async()=>({ setParameters: async()=>{}, recognize: () => new Promise(()=>{}), terminate: async()=>{} });
    readHudNames().then(
      () => console.log('FAIL:resolved'),
      e => console.log('rejected:' + e.message)
    );
    """
    out = _run_names(body)
    assert out == "rejected:OCR read timed out", out


def test_a_timed_out_hud_name_read_discards_the_wedged_worker() -> None:
    # One worker serves HUD names, the scoreboard and the replay code. Leaving
    # a wedged one cached hangs those too, so the read must throw it away.
    body = r"""
    let terminated=false;
    global.ocrWorker=async()=>({ setParameters: async()=>{}, recognize: () => new Promise(()=>{}), terminate: async()=>{ terminated=true; } });
    readHudNames().catch(()=>{}).then(() => {
      console.log(JSON.stringify({terminated, ocrWorkerCleared: _ocrWorker===null, loadingCleared: _ocrLoading===null}));
    });
    """
    result = json.loads(_run_names(body))
    assert result == {"terminated": True, "ocrWorkerCleared": True, "loadingCleared": True}, result


def test_a_read_that_answers_in_time_is_left_alone() -> None:
    # The deadline must not fire on a healthy read, and a healthy read must not
    # tear down the worker every other call needs.
    body = r"""
    let terminated=false;
    _ocrWorker={};   // the shared worker every other read on the page reuses
    global.ocrWorker=async()=>({ setParameters: async()=>{}, recognize: async()=>({data:{text:' Ana  '}}), terminate: async()=>{ terminated=true; } });
    readHudNames().then(
      names => console.log(JSON.stringify({first:names.a[0], slots:names.a.length+names.b.length, terminated, workerKept:_ocrWorker!==null})),
      e => console.log('FAIL:' + e.message)
    );
    """
    result = json.loads(_run_names(body))
    assert result == {"first": "Ana", "slots": 10, "terminated": False, "workerKept": True}, result


def test_every_ocr_read_on_the_page_is_behind_the_deadline() -> None:
    """The scoreboard and replay-code reads share the wedged worker too.

    Guarding only readHudNames would leave the hang reachable through the
    other three recognize() calls, and a worker wedged by any of them takes
    the HUD-name read down with it on the next attempt.
    """
    html = APP.read_text(encoding="utf-8")
    guard = html.index("async function ocrRead(")
    guard_end = html.index("\n}", guard) if "\n}" in html[guard:guard + 800] else guard + 800
    outside = html[:guard] + html[guard_end:]
    bare = re.findall(r"\bw\.recognize\(", outside)
    assert not bare, f"{len(bare)} recognize() call(s) bypass the read deadline"

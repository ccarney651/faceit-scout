"""Browser capture app: the tesseract.js loader must not hang or get poisoned.

ocrWorker() lazily loads tesseract.js + its own CDN assets (core wasm,
eng.traineddata) with no built-in deadline. A stalled (not failed - a real
network *error* already rejects via the script tag's onerror) connection
used to hang "detecting sides..." forever with no escape but a page reload,
and any genuine failure poisoned `_ocrLoading` for the rest of the session
(Re-detect/Auto-detect would just replay the same dead rejected promise).
This pins the fix: a race against a load timeout, and clearing _ocrLoading
on any failure so a later call actually retries.

ocrWorker() itself moved into docs/capture/engine/refs.js (shared with
scrim.html) - these tests now load the REAL module instead of extracting
raw text from index.html, same pattern as test_capture_autocalibrate.py
uses for engine/frames.js and engine/calibration.js. The page-level
OCR_LOAD_TIMEOUT_MS constant became ctx.ocrLoadTimeoutMs (see refs.js's
header) so these tests can shrink it without string-patching source text.

tessedit_char_whitelist deliberately stayed OUT of the shared ocrWorker() -
scrim.html reuses the same cached worker for scoreboard/screenshot OCR
(full sentences, spaces, dashes) that the HUD-gamertag whitelist would
mangle. index.html applies it itself, in ocrNames(), right after getting
the worker - see engine/refs.js's header and index.html's own ocrWorker
comment for the full reasoning. This file's whitelist test now covers both
halves of that split: ocrWorker() itself must NOT set it, and index.html's
ocrNames() must.
"""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

APP = Path(__file__).resolve().parents[1] / "docs" / "capture" / "index.html"
ENGINE_REFS = Path(__file__).resolve().parents[1] / "docs" / "capture" / "engine" / "refs.js"

# _ocrWorker/_ocrLoading/_ocrLoadFailed/_ocrLoadError are page-level globals
# refs.js's ocrWorker() reads/writes as free variables (see refs.js's header
# for why they can't be module-private) - declared here exactly like
# index.html declares them before engine/refs.js's functions are ever
# called.
_STATE = "let _ocrWorker=null, _ocrLoading=null, _ocrLoadFailed=false, _ocrLoadError=null;\n"

_DOC_STUB = r"""
global.document={ head:{appendChild(){}}, createElement(t){ if(t!=='script') throw new Error('unexpected createElement '+t);
  return {}; } };
var module = { exports: {} };
"""

_WIRE_REFS = r"""
const OWDBRefs = module.exports;
const refs = OWDBRefs.make({ doc: global.document, ocrLoadTimeoutMs: %(timeout_ms)d });
const { ocrWorker } = refs;
"""


def _run(body: str, timeout_ms: int = 50) -> str:
    node = shutil.which("node")
    if not node:
        pytest.skip("node not available to run the capture app's helpers")
    refs_src = ENGINE_REFS.read_text(encoding="utf-8")
    src = (
        _STATE + _DOC_STUB + "\n" + refs_src + "\n"
        + (_WIRE_REFS % {"timeout_ms": timeout_ms}) + "\n" + body
    )
    # Written to a temp file rather than passed via `node -e` - refs.js's
    # header comment alone is large enough to trip Windows' CreateProcess
    # command-line length limit ("[WinError 206] The filename or extension
    # is too long").
    script = Path(__file__).resolve().parent / "_tmp_ocr_worker_check.js"
    script.write_text(src, encoding="utf-8")
    try:
        proc = subprocess.run([node, str(script)], capture_output=True, text=True, timeout=15)
    finally:
        script.unlink(missing_ok=True)
    assert proc.returncode == 0, f"node failed:\n{proc.stderr}"
    return proc.stdout.strip()


def test_a_stalled_createworker_times_out_instead_of_hanging_forever() -> None:
    body = r"""
    let calls=0;
    global.Tesseract={ createWorker: () => { calls++; return new Promise(()=>{}); } }; global.window={ Tesseract: global.Tesseract };
    ocrWorker().then(
      () => { console.log('FAIL:resolved'); },
      e => { console.log('rejected:' + e.message); }
    );
    """
    out = _run(body)
    assert out.startswith("rejected:"), out
    assert "taking too long" in out


def test_a_timed_out_load_is_retried_not_replayed() -> None:
    # First attempt stalls forever and times out; second call must invoke
    # createWorker again (a fresh attempt), not reject with a cached failure
    # instantly without even trying.
    body = r"""
    let calls=0;
    global.Tesseract={ createWorker: () => { calls++; return new Promise(()=>{}); } }; global.window={ Tesseract: global.Tesseract };
    ocrWorker().catch(()=>{}).then(() => {
      ocrWorker().catch(()=>{});
      setTimeout(() => console.log('calls:' + calls), 20);
    });
    """
    out = _run(body)
    assert out == "calls:2", out


def test_an_outright_rejection_does_not_poison_future_attempts() -> None:
    # Simulates a genuine offline/integrity failure (rejects fast, no timeout
    # involved). A later retry after connectivity returns must try again.
    body = r"""
    let calls=0;
    global.Tesseract={ createWorker: () => { calls++;
      return calls===1 ? Promise.reject(new Error('offline')) : Promise.resolve({setParameters: async()=>{}}); } }; global.window={ Tesseract: global.Tesseract };
    ocrWorker().catch(e => console.log('first:' + e.message)).then(() => {
      ocrWorker().then(() => console.log('second:ok calls=' + calls));
    });
    """
    out = _run(body, timeout_ms=5000)
    assert "first:offline" in out
    assert "second:ok calls=2" in out


def test_a_successful_load_is_cached_and_not_reloaded() -> None:
    body = r"""
    let calls=0;
    global.Tesseract={ createWorker: () => { calls++; return Promise.resolve({setParameters: async()=>{}}); } }; global.window={ Tesseract: global.Tesseract };
    ocrWorker().then(() => ocrWorker()).then(() => console.log('calls:' + calls));
    """
    out = _run(body, timeout_ms=5000)
    assert out == "calls:1", out


def test_a_successful_load_clears_a_stale_failure_flag() -> None:
    # ensureSideResolved() surfaces _ocrLoadFailed as a "retrying..." hint but
    # deliberately does NOT let it block a fresh attempt (see
    # test_capture_ocr_load_retry.py) - that only stays honest if a real
    # success actually clears the flag back off, or the hint would show
    # forever even once OCR is healthy again.
    body = r"""
    _ocrLoadFailed=true; _ocrLoadError='could not load the OCR library (offline?)';
    global.Tesseract={ createWorker: () => Promise.resolve({setParameters: async()=>{}}) }; global.window={ Tesseract: global.Tesseract };
    ocrWorker().then(() => console.log(JSON.stringify({failed:_ocrLoadFailed})));
    """
    out = _run(body, timeout_ms=5000)
    assert out == '{"failed":false}', out


def test_ocr_worker_itself_does_not_restrict_the_charset_scrim_needs() -> None:
    # scrim.html reuses this SAME shared worker for readScoreboard()/
    # ocrTextFromImage() (full sentences: map names with spaces, "VICTORY"/
    # "DEFEAT", score dashes) - if ocrWorker() itself whitelisted the
    # HUD-gamertag charset, that reuse would silently mangle scrim.html's
    # scoreboard/screenshot OCR the first time the cached worker got reused
    # for anything but a HUD-name crop. Only the base pageseg_mode (what both
    # pages already used as the worker's resting configuration) belongs here.
    body = r"""
    let calls=[];
    global.Tesseract={ createWorker: () => Promise.resolve({ setParameters: async (p) => { calls.push(p); } }) };
    global.window={ Tesseract: global.Tesseract };
    ocrWorker().then(() => console.log(JSON.stringify(calls)));
    """
    out = _run(body, timeout_ms=5000)
    calls = json.loads(out)
    assert calls == [{"tessedit_pageseg_mode": "7"}], calls


def test_index_html_layers_the_gamertag_whitelist_onto_the_shared_worker() -> None:
    # The whitelist itself (see the module-boundary test above for why it's
    # NOT in engine/refs.js) is applied by index.html's own ocrNames(),
    # scoped to this page's own use of the shared worker.
    html = APP.read_text(encoding="utf-8")
    start = html.index("async function ocrNames()")
    end = html.index("return out; }", start) + len("return out; }")
    assert end > start, "ocrNames anchor moved in index.html"
    body = html[start:end]
    assert "const w=await ocrWorker();" in body
    assert "tessedit_char_whitelist" in body, "index.html no longer restricts the OCR charset for HUD names"
    marker = 'tessedit_char_whitelist:"'
    i = body.index(marker) + len(marker)
    whitelist = body[i:body.index('"', i)]
    for ch in "AZaz09_-.'~":
        assert ch in whitelist, f"{ch!r} missing from whitelist"
    assert " " not in whitelist, "whitelist should stay restrictive (no space) for HUD gamertags"


# ---------------------------------------------------------------------------
# ocrNames(): the per-name-crop recognize() loop has its own hang risk,
# separate from ocrWorker()'s load - the fix above only covered getting the
# worker loaded in the first place. A stalled/wedged w.recognize() call (the
# reported "detecting sides..." hang recurring even after the load fix
# shipped) left ocrNames() awaiting forever with no deadline of its own.
# ---------------------------------------------------------------------------

def _names_js(timeout_ms: int) -> str:
    html = APP.read_text(encoding="utf-8")
    # Anchored on the stable prefix, not the full var list, so adding another
    # _ocr* state var doesn't break this extraction again.
    state_start = html.index("let _ocrWorker=null")
    state_end = html.index(";", state_start) + 1
    state = html[state_start:state_end]
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
    global.grabFrame=()=>({});
    global.nameCanvas=()=>({});
    global.setDetectMsg=()=>{};
    global.ocrProgress=()=>{};
    """
    src = stubs + "\n" + _names_js(timeout_ms) + "\n" + body
    proc = subprocess.run([node, "-e", src], capture_output=True, text=True, timeout=15)
    assert proc.returncode == 0, f"node failed:\n{proc.stderr}"
    return proc.stdout.strip()


def test_a_stalled_recognize_call_times_out_instead_of_hanging_forever() -> None:
    body = r"""
    global.ocrWorker=async()=>({ setParameters: async()=>{}, recognize: () => new Promise(()=>{}), terminate: async()=>{} });
    ocrNames().then(
      () => console.log('FAIL:resolved'),
      e => console.log('rejected:' + e.message)
    );
    """
    out = _run_names(body)
    assert out == "rejected:OCR read timed out", out


def test_a_timed_out_read_discards_the_wedged_worker() -> None:
    # tesseract.js processes jobs sequentially per worker, so a call that
    # never returns likely wedges the whole worker, not just that one read -
    # the fix must throw the worker away (terminate + clear the module cache)
    # rather than let future reads queue forever behind the dead job.
    body = r"""
    let terminated=false;
    global.ocrWorker=async()=>({ setParameters: async()=>{}, recognize: () => new Promise(()=>{}), terminate: async()=>{ terminated=true; } });
    ocrNames().catch(()=>{}).then(() => {
      console.log(JSON.stringify({terminated, ocrWorkerCleared: _ocrWorker===null, loadingCleared: _ocrLoading===null}));
    });
    """
    out = _run_names(body)
    result = json.loads(out)
    assert result == {"terminated": True, "ocrWorkerCleared": True, "loadingCleared": True}, result


def test_a_healthy_recognize_call_reads_all_ten_names_normally() -> None:
    body = r"""
    let calls=0;
    global.ocrWorker=async()=>({ setParameters: async()=>{}, recognize: () => { calls++; return Promise.resolve({data:{text:'Player'+calls}}); } });
    ocrNames().then(names => console.log(JSON.stringify({calls, a:names.a, b:names.b})));
    """
    out = _run_names(body, timeout_ms=5000)
    result = json.loads(out)
    assert result["calls"] == 10
    assert result["a"] == ["Player1", "Player2", "Player3", "Player4", "Player5"]
    assert result["b"] == ["Player6", "Player7", "Player8", "Player9", "Player10"]

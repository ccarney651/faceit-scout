"""Browser capture app: the tesseract.js loader must not hang or get poisoned.

ocrWorker() lazily loads tesseract.js + its own CDN assets (core wasm,
eng.traineddata) with no built-in deadline. A stalled (not failed - a real
network *error* already rejects via the script tag's onerror) connection
used to hang "detecting sides..." forever with no escape but a page reload,
and any genuine failure poisoned `_ocrLoading` for the rest of the session
(Re-detect/Auto-detect would just replay the same dead rejected promise).
This pins the fix: a race against OCR_LOAD_TIMEOUT_MS, and clearing
_ocrLoading on any failure so a later call actually retries.
"""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

APP = Path(__file__).resolve().parents[1] / "docs" / "capture" / "index.html"


def _pure_js(timeout_ms: int) -> str:
    html = APP.read_text(encoding="utf-8")
    start = html.index("const OCR_LOAD_TIMEOUT_MS=")
    end = html.index("  return _ocrLoading; }") + len("  return _ocrLoading; }")
    assert end > start, "extraction anchors moved in index.html"
    js = html[start:end]
    assert "const OCR_LOAD_TIMEOUT_MS=30000;" in js, "timeout constant moved/changed"
    # Swap in a short timeout so the hang test doesn't take 30s.
    return js.replace("const OCR_LOAD_TIMEOUT_MS=30000;", f"const OCR_LOAD_TIMEOUT_MS={timeout_ms};")


def _run(body: str, timeout_ms: int = 50) -> str:
    node = shutil.which("node")
    if not node:
        pytest.skip("node not available to run the capture app's helpers")
    src = _pure_js(timeout_ms) + "\n" + body
    proc = subprocess.run([node, "-e", src], capture_output=True, text=True, timeout=15)
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


def test_worker_setup_whitelists_the_hud_gamertag_charset() -> None:
    # Restricting recognition to the charset HUD names actually use cuts stray
    # glyphs (border/icon bleed) from diluting simScore's fuzzy match ratio.
    body = r"""
    let captured=null;
    global.Tesseract={ createWorker: () => Promise.resolve({ setParameters: async (p) => { captured = p; } }) };
    global.window={ Tesseract: global.Tesseract };
    ocrWorker().then(() => console.log(JSON.stringify(captured)));
    """
    out = _run(body, timeout_ms=5000)
    params = json.loads(out)
    assert params["tessedit_pageseg_mode"] == "7"
    whitelist = params["tessedit_char_whitelist"]
    for ch in "AZaz09_-.'~":
        assert ch in whitelist, f"{ch!r} missing from whitelist"

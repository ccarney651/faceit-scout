"""Browser capture app: the CSP must actually permit the OCR stack it ships.

The capture pages carry their CSP in a <meta http-equiv> tag (not an HTTP
header, so `curl -I` shows nothing - which is why this hid for several
debugging rounds). It declared `worker-src https://cdn.jsdelivr.net`, but
tesseract.js does NOT spawn its worker from that URL: it builds a tiny
bootstrap Blob and calls `new Worker(URL.createObjectURL(blob))`, i.e. a
`blob:` URL. So every worker spawn was blocked by our own CSP, in every
browser (reported on both Firefox and Edge).

The failure was near-invisible from the app's side: the parent-side
ErrorEvent for a blocked/cross-origin worker is sanitised, and
tesseract.js's handler forwards `event.message` verbatim
(`M=function(t){F(t.message)}`), so the load promise rejected with literal
`undefined` and the UI could only say "OCR engine failed to load" with no
cause.

These tests pin the directives the OCR path actually needs, verified
end-to-end in a real browser (worker spawns, wasm core + eng.traineddata
load, recognize() returns correct text):
  - worker-src must allow `blob:`      (tesseract's Blob bootstrap worker)
  - script-src must allow wasm compilation (the OCR core is WebAssembly)
  - connect-src must allow `data:`     (the core's wasm fetch)
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

DOCS = Path(__file__).resolve().parents[1] / "docs"
# Both pages ship the tesseract.js OCR stack, so both need the same allowances.
OCR_PAGES = [DOCS / "capture" / "index.html", DOCS / "capture" / "scrim.html"]


def _csp(page: Path) -> dict[str, str]:
    html = page.read_text(encoding="utf-8")
    # The content attribute is delimited by one quote char but contains the
    # other (CSP keywords are single-quoted), so match on the actual delimiter
    # rather than a "any quote" character class.
    m = re.search(
        r'<meta\s+http-equiv=(["\'])Content-Security-Policy\1\s+content=(["\'])(.*?)\2',
        html, re.I | re.S,
    )
    assert m, f"{page.name} has no CSP meta tag"
    out: dict[str, str] = {}
    for part in m.group(3).split(";"):
        part = part.strip()
        if not part:
            continue
        name, _, value = part.partition(" ")
        out[name.strip().lower()] = value.strip()
    return out


@pytest.mark.parametrize("page", OCR_PAGES, ids=lambda p: p.name)
def test_worker_src_allows_blob_urls(page: Path) -> None:
    directives = _csp(page)
    worker_src = directives.get("worker-src")
    assert worker_src is not None, "worker-src missing (would fall back to default-src 'none')"
    assert "blob:" in worker_src, (
        f"{page.name}: worker-src={worker_src!r} blocks tesseract.js, which spawns its "
        "worker from a Blob URL - every OCR call fails with an unhelpful `undefined`"
    )


@pytest.mark.parametrize("page", OCR_PAGES, ids=lambda p: p.name)
def test_script_src_allows_wasm_compilation(page: Path) -> None:
    script_src = _csp(page).get("script-src", "")
    assert "'wasm-unsafe-eval'" in script_src or "'unsafe-eval'" in script_src, (
        f"{page.name}: script-src={script_src!r} blocks WebAssembly compilation - "
        "the tesseract OCR core is wasm"
    )


@pytest.mark.parametrize("page", OCR_PAGES, ids=lambda p: p.name)
def test_connect_src_allows_the_data_url_wasm_fetch(page: Path) -> None:
    connect_src = _csp(page).get("connect-src", "")
    assert "data:" in connect_src, (
        f"{page.name}: connect-src={connect_src!r} blocks the OCR core's data: wasm fetch"
    )


@pytest.mark.parametrize("page", OCR_PAGES, ids=lambda p: p.name)
def test_the_cdn_the_app_loads_tesseract_from_is_still_allowed(page: Path) -> None:
    # The app hardcodes a jsdelivr URL for tesseract.js; if that host is ever
    # dropped from script-src the library itself stops loading.
    html = page.read_text(encoding="utf-8")
    if "cdn.jsdelivr.net" not in html:
        pytest.skip(f"{page.name} no longer loads anything from jsdelivr")
    script_src = _csp(page).get("script-src", "")
    assert "https://cdn.jsdelivr.net" in script_src, (
        f"{page.name}: script-src={script_src!r} would block the tesseract.js library itself"
    )

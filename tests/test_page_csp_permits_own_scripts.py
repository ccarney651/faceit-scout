"""Every page's CSP must permit the scripts that page loads.

Three separate incidents in this project were one bug wearing different
clothes, and all three cost days:

  - `worker-src` named the CDN, but tesseract.js spawns its worker from a
    `blob:` URL, so every OCR worker was blocked.
  - `script-src` lacked `'self'`, so `scoreboard.js` had never loaded in
    production.
  - `script-src` lacked `'self'` on `docs/scrims.html` after it gained
    `capture/engine/heroes.js`, so the viewer rendered an empty shell.

They share a shape: the policy is correct for the page as it was, someone
adds a resource, and nothing complains anywhere a test can see. The policy
lives in a `<meta http-equiv>` tag, so `curl -I` shows nothing and the only
symptom is a console message in a real browser.

This is the cheap half of the guard - it reads every page and its own policy,
so a NEW page, or a new script on an old one, is covered the day it lands
rather than the day someone opens a browser. The expensive half lives in
tools/verify_capture_browser.js, which actually loads the pages.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

DOCS = Path(__file__).resolve().parents[1] / "docs"

# CI regenerates this one from faceit_sync/dashboard/head.html on every run, so
# a finding here would be reported against a file nobody edits. It is covered
# at its source instead.
# Matched on the path, not the basename: docs/capture/index.html is a real
# hand-authored page and an earlier draft of this filter silently excluded it.
# Frozen season archives (docs/s9/index.html, ...) are the same file one step
# further along: generated from the same template and then deliberately never
# rebuilt, so a finding against one could not be acted on even in principle.
GENERATED = {"index.html"} | {f"s{n}/index.html" for n in range(1, 30)}

PAGES = sorted(p for p in DOCS.rglob("*.html")
               if p.relative_to(DOCS).as_posix() not in GENERATED)


def _csp(html: str) -> str | None:
    m = re.search(r'http-equiv="Content-Security-Policy"[^>]*content="([^"]*)"', html)
    return m.group(1) if m else None


@pytest.mark.parametrize("page", PAGES, ids=lambda p: p.relative_to(DOCS).as_posix())
def test_page_csp_permits_the_scripts_it_loads(page: Path) -> None:
    html = page.read_text(encoding="utf-8", errors="replace")
    csp = _csp(html)
    if csp is None:
        return          # no policy, nothing to contradict
    srcs = re.findall(r'<script[^>]*\ssrc="([^"]+)"', html)
    if not srcs:
        return

    directive = re.search(r"script-src([^;]*)", csp)
    assert directive, (
        f"{page.name} loads {srcs} but its CSP has no script-src, "
        "so default-src falls through and blocks every one of them"
    )
    allowed = directive.group(1)

    local = [u for u in srcs if not re.match(r"https?:|//", u)]
    if local:
        assert "'self'" in allowed, (
            f"{page.name} loads {local} but script-src is '{allowed.strip()}' - "
            "same-origin scripts need 'self'"
        )
    for url in (u for u in srcs if u not in local):
        host = re.match(r"(?:https?:)?//([^/]+)", url)
        assert host and host.group(1) in allowed, (
            f"{page.name} loads {url}, which script-src '{allowed.strip()}' does not allow"
        )

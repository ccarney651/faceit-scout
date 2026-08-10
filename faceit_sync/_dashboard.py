"""Self-contained HTML dashboard template.

``export_html`` substitutes ``__TITLE__`` and the data blob into this template
(export.py). No external resources (fonts, scripts, images) — it opens by
double-clicking, works offline, and is safe under a strict CSP.

Design: a refined, information-first scouting tool. Cool slate neutrals with a
single indigo accent; Overwatch role colours (Tank/Damage/Support) as the only
categorical hues; a green→amber→red scale reserved for win rates. Tabs:
Overview → Scout a team → Players → League meta → Matches. Private scrims live
on their own page (`docs/scrims.html`) reached via the League/Scrims side
toggle in the top bar — this dashboard never touches the capture IndexedDB.

The template is assembled from static parts — see ``dashboard/`` — by plain
concatenation (no framework, no bundler). Editing a part file is editing the
page; run the JS syntax test after any change.
"""

import base64
import re
from pathlib import Path

_DASHBOARD_DIR = Path(__file__).resolve().parent / "dashboard"
_DOCS_DIR = Path(__file__).resolve().parent.parent / "docs"
_PARTS = ("head.html", "pure.js", "app.js", "boot.js")

_FONT_URL_RE = re.compile(r"url\('fonts/([^']+\.woff2)'\)")


def _inline_theme_css() -> str:
    """Read docs/theme.css and embed its fonts as base64 data URIs.

    docs/scrims.html and docs/capture/*.html link docs/theme.css directly
    (real files, real requests — fine, they aren't self-contained). The
    exported dashboard can't do that: it must stay a single file with zero
    external loads (tests/test_export.py::
    test_export_html_is_self_contained_and_valid), and its CSP's
    ``font-src data:`` wouldn't permit a separate font file anyway. So for
    this build only, every ``url('fonts/NAME.woff2')`` reference becomes a
    base64 data URI, and the whole file gets inlined into the page's
    ``<style>`` block in place of the ``__THEME_CSS__`` marker.
    """
    theme_css = (_DOCS_DIR / "theme.css").read_text(encoding="utf-8")

    def _embed(match: re.Match[str]) -> str:
        font_bytes = (_DOCS_DIR / "fonts" / match.group(1)).read_bytes()
        encoded = base64.b64encode(font_bytes).decode("ascii")
        return f"url(data:font/woff2;base64,{encoded})"

    return _FONT_URL_RE.sub(_embed, theme_css)


def _build_template() -> str:
    """Concatenate the dashboard's part files into ``HTML_TEMPLATE``.

    The page shell + CSS, the pure decision helpers (the code the tests
    execute), the ``bootApp`` body, and the data-delivery bootstrap each live
    in their own file under ``dashboard/``. Import-time assembly keeps the
    parts the single source of truth — no stale generated artifact to forget.
    The shared design tokens/primitives in docs/theme.css get inlined here
    (fonts base64-embedded) so the exported page stays self-contained while
    still sharing one canonical stylesheet with the capture app and scrims
    page.
    """
    parts = "".join(
        (_DASHBOARD_DIR / name).read_text(encoding="utf-8") for name in _PARTS
    )
    return parts.replace("/* __THEME_CSS__ */", _inline_theme_css())


HTML_TEMPLATE = _build_template()

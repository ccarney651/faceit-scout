"""Self-contained HTML dashboard template.

``export_html`` substitutes ``__TITLE__`` and the data blob into this template
(export.py). No external resources (fonts, scripts, images) — it opens by
double-clicking, works offline, and is safe under a strict CSP.

Design: a refined, information-first scouting tool. Cool slate neutrals with a
single indigo accent; Overwatch role colours (Tank/Damage/Support) as the only
categorical hues; a green→amber→red scale reserved for win rates. Tabs:
Overview → Scout a team → Players → League meta → Matches, plus a Scrims tab
for this browser's private comps.

The template is assembled from static parts — see ``dashboard/`` — by plain
concatenation (no framework, no bundler). Editing a part file is editing the
page; run the JS syntax test after any change.
"""

from pathlib import Path

_DASHBOARD_DIR = Path(__file__).resolve().parent / "dashboard"
_PARTS = ("head.html", "pure.js", "app.js", "boot.js")


def _build_template() -> str:
    """Concatenate the dashboard's part files into ``HTML_TEMPLATE``.

    The page shell + CSS, the pure decision helpers (the code the tests
    execute), the ``bootApp`` body, and the data-delivery bootstrap each live
    in their own file under ``dashboard/``. Import-time assembly keeps the
    parts the single source of truth — no stale generated artifact to forget.
    """
    return "".join(
        (_DASHBOARD_DIR / name).read_text(encoding="utf-8") for name in _PARTS
    )


HTML_TEMPLATE = _build_template()

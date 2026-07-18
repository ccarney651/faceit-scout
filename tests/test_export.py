"""Player-name capture and the self-contained HTML dashboard."""

from __future__ import annotations

import io
import json
import re

import responses

from faceit_sync.db import Database
from faceit_sync.export import export_html
from faceit_sync.sync import SyncEngine
from conftest import RESTART_DC_ID, make_client, register_match


def _ingest(db: Database) -> None:
    register_match(responses, RESTART_DC_ID, prefix="restart_dc", democracy=True)
    SyncEngine(make_client()[0], db).ingest_match(RESTART_DC_ID, force_refresh=True)


@responses.activate
def test_players_table_gets_nicknames(db: Database) -> None:
    _ingest(db)
    n = db.conn.execute("SELECT COUNT(*) FROM players WHERE nickname IS NOT NULL").fetchone()[0]
    assert n >= 10
    # A known roster nickname from the fixture resolves.
    row = db.conn.execute("SELECT id FROM players WHERE nickname = 'NENONX'").fetchone()
    assert row is not None


@responses.activate
def test_export_html_is_self_contained_and_valid(db: Database) -> None:
    _ingest(db)
    buf = io.StringIO()
    count = export_html(db, buf)          # all divisions (just the one ingested)
    doc = buf.getvalue()

    assert count == 1
    assert doc.startswith("<!doctype html>")
    # No external resource references (CSP/offline safe).
    assert "http://" not in doc and "https://" not in doc
    assert "<script src" not in doc and "<link" not in doc

    # Embedded data parses back to JSON and reflects the ingest.
    # (DATA is emitted on a single line, so match without DOTALL.)
    m = re.search(r"const DATA = (\{.*\});", doc)
    assert m is not None
    data = json.loads(m.group(1).replace("<\\/", "</"))
    assert len(data["divisions"]) == 1
    assert data["views"] and data["views"][0]["divisions"]
    div = next(iter(data["divisions"].values()))
    assert div["summary"]["matches"] == 1
    assert div["summary"]["dc_games"] == 1          # hazard A game present
    assert div["summary"]["matches_with_attribution"] == 1  # restart_dc has live democracy


def test_dashboard_javascript_is_syntactically_valid(tmp_path):
    """The dashboard renders its whole body in JS, so ONE syntax error (e.g. a
    duplicate `const`) yields a completely blank page — which balanced-bracket
    checks do not catch. Run the real parser over the generated script."""
    import re
    import shutil
    import subprocess

    import pytest

    node = shutil.which("node")
    if not node:
        pytest.skip("node not available to parse the dashboard JS")

    from faceit_sync._dashboard import HTML_TEMPLATE

    html = HTML_TEMPLATE.replace("__TITLE__", "t").replace(
        "__DATA__", '{"divisions":{},"views":[],"heroes":[],"roster":{},'
                    '"maps":[],"owscout_comps":{},"hero_icons":{}}')
    js = re.search(r"<script>(.*)</script>", html, re.S)
    assert js, "no <script> block found in the dashboard template"
    script = tmp_path / "dash.js"
    script.write_text(js.group(1), encoding="utf-8")
    proc = subprocess.run([node, "--check", str(script)],
                          capture_output=True, text=True)
    assert proc.returncode == 0, f"dashboard JS is invalid:\n{proc.stderr}"


def test_hero_icon_cache_is_committed_and_usable() -> None:
    """CI has no access to the 22 MB of source art, so the dashboard's portraits
    come from this committed cache. If it goes missing the page still builds -
    silently, with text chips instead of portraits - so assert it explicitly."""
    from faceit_sync.hero_icons import ICON_CACHE, load_hero_icons

    assert ICON_CACHE.is_file(), f"icon cache missing at {ICON_CACHE}"
    icons = load_hero_icons()
    assert len(icons) >= 40, f"only {len(icons)} icons cached"
    assert all(v.startswith("data:image/") for v in icons.values())
    # A few well-known slugs, incl. the punctuation-stripped ones.
    for hero in ("dva", "wreckingball", "kiriko"):
        assert hero in icons, f"{hero} missing from the icon cache"

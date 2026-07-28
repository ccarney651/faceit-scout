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
    # No external resource LOADS: the page must render completely offline, with
    # every asset inlined. Tested precisely rather than by banning the string
    # "https://" outright, because the refresh button legitimately holds an
    # endpoint URL - a user-initiated fetch, not a resource the page loads.
    assert "<script src" not in doc and "<link" not in doc
    assert 'src="http' not in doc and "src='http" not in doc
    assert "url(http" not in doc and "@import" not in doc
    # ...and the only outbound URLs are the ones we intend.
    urls = {u.rstrip('",;)') for u in re.findall(r"https?://[^\s\"'<>]+", doc)}
    allowed_hosts = {"owscout-upload.owscout.workers.dev"}
    external = {u for u in urls
                if u.split("/")[2] not in allowed_hosts} if urls else set()
    assert not external, f"unexpected external URLs in the dashboard: {external}"

    # Embedded data parses back to JSON and reflects the ingest. The default build
    # inlines it as `var __OWSCOUT_DATA__={...};` (single line, so no DOTALL).
    m = re.search(r"var __OWSCOUT_DATA__=(\{.*\});", doc)
    assert m is not None
    data = json.loads(m.group(1).replace("<\\/", "</"))
    assert len(data["divisions"]) == 1
    assert data["views"] and data["views"][0]["divisions"]
    div = next(iter(data["divisions"].values()))
    assert div["summary"]["matches"] == 1
    assert div["summary"]["dc_games"] == 1          # hazard A game present
    assert div["summary"]["matches_with_attribution"] == 1  # restart_dc has live democracy


@responses.activate
def test_external_data_build_is_a_shell_plus_datajson(db: Database, tmp_path) -> None:
    """--external-data: the page becomes a shell that fetches data.json (the seam
    for future gating), instead of inlining the payload."""
    _ingest(db)
    dp = tmp_path / "data.json"
    buf = io.StringIO()
    count = export_html(db, buf, data_path=str(dp))
    doc = buf.getvalue()
    assert count == 1
    # Shell: NO inline blob, but the fetch bootstrap is present.
    assert "var __OWSCOUT_DATA__=" not in doc
    assert "fetch('data.json'" in doc
    # data.json is written and parses back to the same payload shape.
    assert dp.is_file()
    data = json.loads(dp.read_text(encoding="utf-8").replace("<\\/", "</"))
    assert len(data["divisions"]) == 1 and data["views"]


def test_is_playoff_classifies_championships() -> None:
    """Playoff championships are split out of the tier views/standings and attached
    to their division as results; regular-season ones are not."""
    from faceit_sync.export import _is_playoff

    assert _is_playoff("S9 EMEA Master Central - Playoffs")
    assert _is_playoff("S9 NA Expert Central - Knockout Stage")
    assert not _is_playoff("S9 EMEA Master Central - Regular Season")
    assert not _is_playoff(None)


def test_tier_and_region_classify_championship_names() -> None:
    """The EMEA-Master-only site filter keys off these. Names carry both words."""
    from faceit_sync.export import _region_of, _tier_of

    assert _tier_of("S9 EMEA Master Central - Regular Season") == "Master"
    assert _tier_of("S9 NA Expert Central - Regular Season") == "Expert"
    assert _tier_of("S9 EMEA Advanced Central - Regular Season") == "Advanced"
    assert _tier_of("S9 EMEA Open - Regular Season") == "Open"
    assert _tier_of("Regular Season Group A") is None
    assert _tier_of(None) is None
    assert _region_of("S9 EMEA Master Central - Regular Season") == "EMEA"
    assert _region_of("S9 NA Expert Central - Regular Season") == "NA"
    assert _region_of("Some Open Qualifier") is None
    assert _region_of(None) is None


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
        "// __DATA_INLINE__",
        'var __OWSCOUT_DATA__={"divisions":{},"views":[],"heroes":[],"roster":{},'
        '"maps":[],"owscout_comps":{},"hero_icons":{}};')
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

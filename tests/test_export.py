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
    champ = db.conn.execute("SELECT id FROM championships LIMIT 1").fetchone()["id"]
    buf = io.StringIO()
    count = export_html(db, champ, buf)
    doc = buf.getvalue()

    assert count == 1
    assert doc.startswith("<!doctype html>")
    # No external resource references (CSP/offline safe).
    assert "http://" not in doc and "https://" not in doc
    assert "<script src" not in doc and "<link" not in doc

    # Embedded data parses back to JSON and reflects the ingest.
    m = re.search(r"const DATA = (\{.*?\});\nconst \$", doc, re.S)
    assert m is not None
    data = json.loads(m.group(1).replace("<\\/", "</"))
    assert data["summary"]["matches"] == 1
    assert data["summary"]["dc_games"] == 1          # hazard A game present
    assert data["summary"]["matches_with_attribution"] == 1  # restart_dc has live democracy

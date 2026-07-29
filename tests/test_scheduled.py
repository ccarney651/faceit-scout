"""Unplayed (scheduled) matches are stored as bare FIXTURES, not discarded.

The keyless league enumeration surfaces future fixtures; we keep them (teams /
schedule time / round, no games) so the site can show what's upcoming. A stored
scheduled match is always re-fetched (never skipped) and upgraded to a full
ingest once it reaches FINISHED. A cancelled / unknown-state match is ignored.
"""

from __future__ import annotations

import responses

from faceit_sync.client import MATCH_URL
from faceit_sync.db import Database
from faceit_sync.sync import SyncEngine
from conftest import make_client

MID = "1-00000000-0000-0000-0000-000000000000"


def _payload(status: str, **extra: object) -> dict:
    p = {
        "id": MID, "status": status, "results": [], "voting": {}, "demoURLs": [],
        "entity": {"id": "C", "name": "S9 EMEA Master Central - Regular Season"},
        "entityCustom": {"round": 15, "group": 1},
        "teams": {
            "faction1": {"id": "tA", "name": "Alpha", "roster": []},
            "faction2": {"id": "tB", "name": "Bravo", "roster": []},
        },
    }
    p.update(extra)
    return p


@responses.activate
def test_scheduled_match_is_stored_as_fixture(db: Database) -> None:
    responses.add(
        responses.GET, MATCH_URL.format(id=MID),
        json={"payload": _payload("SCHEDULED", schedule="2026-08-01T18:00:00Z")},
        status=200,
    )
    engine = SyncEngine(make_client()[0], db)
    assert engine.ingest_match(MID) == "inserted"
    row = db.conn.execute(
        "SELECT status, scheduled_at, round, "
        "(SELECT COUNT(*) FROM games WHERE match_id=matches.id) g "
        "FROM matches WHERE id=?", (MID,)).fetchone()
    assert row["status"] == "SCHEDULED"
    assert row["scheduled_at"] == "2026-08-01T18:00:00Z"
    assert row["round"] == 15 and row["g"] == 0
    # A stored scheduled match is never treated as "already stored" -> re-fetched
    # every run, so it upgrades the moment it finishes.
    assert engine._skip_stored(MID, force_refresh=False) is False


@responses.activate
def test_cancelled_match_is_not_stored(db: Database) -> None:
    responses.add(
        responses.GET, MATCH_URL.format(id=MID),
        json={"payload": _payload("CANCELLED")}, status=200,
    )
    engine = SyncEngine(make_client()[0], db)
    assert engine.ingest_match(MID) == "skipped"
    assert db.conn.execute("SELECT COUNT(*) FROM matches").fetchone()[0] == 0

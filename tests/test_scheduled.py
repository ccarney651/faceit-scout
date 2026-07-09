"""Unplayed (scheduled/ongoing) matches must never be ingested.

The keyless league enumeration can surface future fixtures; storing them would
leave empty rows that get re-fetched on every run. Ingest requires a FINISHED
status and actual results.
"""

from __future__ import annotations

import responses

from faceit_sync.client import MATCH_URL
from faceit_sync.db import Database
from faceit_sync.sync import SyncEngine
from conftest import make_client

MID = "1-00000000-0000-0000-0000-000000000000"


@responses.activate
def test_scheduled_match_is_not_stored(db: Database) -> None:
    responses.add(
        responses.GET, MATCH_URL.format(id=MID),
        json={"payload": {"id": MID, "status": "SCHEDULED", "results": [],
                          "entity": {"id": "C"}, "teams": {}}},
        status=200,
    )
    engine = SyncEngine(make_client()[0], db)
    assert engine.ingest_match(MID) == "skipped"
    # Nothing written — not even the championship/match rows.
    assert db.conn.execute("SELECT COUNT(*) FROM matches").fetchone()[0] == 0

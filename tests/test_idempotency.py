"""Re-running sync never duplicates rows; finished matches are skipped."""

from __future__ import annotations

import responses

from faceit_sync.db import Database
from faceit_sync.sync import SyncEngine
from conftest import RESTART_DC_ID, make_client, register_match

TABLES = ["matches", "games", "map_picks", "hero_bans", "round_players", "teams",
          "heroes", "maps"]


def _counts(db: Database) -> dict[str, int]:
    return {t: db.conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in TABLES}


@responses.activate
def test_double_ingest_is_idempotent(db: Database) -> None:
    register_match(responses, RESTART_DC_ID, prefix="restart_dc", democracy=True)
    client, _ = make_client()
    engine = SyncEngine(client, db)

    engine.ingest_match(RESTART_DC_ID, force_refresh=True)
    first = _counts(db)
    # Force a full re-ingest: delete+reinsert children must not duplicate.
    engine.ingest_match(RESTART_DC_ID, force_refresh=True)
    second = _counts(db)

    assert first == second
    assert first["matches"] == 1
    assert first["games"] == 3  # 3-0 sweep


@responses.activate
def test_finished_match_skipped_without_force(db: Database) -> None:
    register_match(responses, RESTART_DC_ID, prefix="restart_dc", democracy=True)
    client, _ = make_client()
    engine = SyncEngine(client, db)

    assert engine.ingest_match(RESTART_DC_ID) == "inserted"
    # Second run: stored FINISHED -> skipped, no new fetch of match detail needed.
    assert engine.ingest_match(RESTART_DC_ID) == "skipped"


@responses.activate
def test_run_matches_counts(db: Database) -> None:
    register_match(responses, RESTART_DC_ID, prefix="restart_dc", democracy=True)
    client, _ = make_client()
    engine = SyncEngine(client, db)

    # A room URL plus a duplicate bare id -> deduped to one ingest.
    refs = [
        f"https://www.faceit.com/en/ow2/room/{RESTART_DC_ID}",
        RESTART_DC_ID,
    ]
    result = engine.run_matches(refs)
    assert result.matches_seen == 1
    assert result.inserted == 1
    assert result.errors == 0

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


@responses.activate
def test_run_matches_reports_progress_even_when_a_match_fails(db: Database) -> None:
    """The bar must reach the end regardless of what happens to each match.

    A first-run bootstrap that stalls its progress bar on one bad match is worse
    than showing none at all, so a skip and an ingest error both still tick.
    """
    register_match(responses, RESTART_DC_ID, prefix="restart_dc", democracy=True)
    client, _ = make_client()
    engine = SyncEngine(client, db)

    seen: list[tuple[int, int]] = []
    # One good id, one that cannot be fetched (unregistered -> error path).
    refs = [RESTART_DC_ID, "1-deadbeef-0000-0000-0000-000000000000"]
    result = engine.run_matches(refs, progress=lambda d, t: seen.append((d, t)))

    assert seen == [(1, 2), (2, 2)]      # every match ticks exactly once, in order
    assert result.errors == 1            # and the failure was still counted


@responses.activate
def test_progress_callback_failure_cannot_abort_the_import(db: Database) -> None:
    """A broken display must not cost the user their bootstrap."""
    register_match(responses, RESTART_DC_ID, prefix="restart_dc", democracy=True)
    client, _ = make_client()
    engine = SyncEngine(client, db)

    def boom(done: int, total: int) -> None:
        raise RuntimeError("widget destroyed mid-sync")

    result = engine.run_matches([RESTART_DC_ID], progress=boom)
    assert result.inserted == 1

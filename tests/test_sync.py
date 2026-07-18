"""Replay-code backfill: re-fetching stored matches whose codes arrived late."""

from __future__ import annotations

from typing import Optional

from faceit_sync.db import Database
from faceit_sync.sync import SyncEngine
from conftest import make_client


def _match(db: Database, mid: str, age_days: int, code: Optional[str]) -> None:
    db.conn.execute("INSERT OR IGNORE INTO championships (id) VALUES ('c1')")
    db.conn.execute(
        "INSERT INTO matches (id, championship_id, status, finished_at, fetched_at) "
        "VALUES (?, 'c1', 'FINISHED', datetime('now', ?), datetime('now'))",
        (mid, f"-{age_days} days"))
    db.conn.execute(
        "INSERT INTO games (match_id, game_no, demo_code) VALUES (?, 1, ?)", (mid, code))
    db.conn.commit()


def test_recent_match_missing_codes_is_refetched(db: Database) -> None:
    """The bug this guards: FACEIT publishes replay codes AFTER a match finishes,
    but a plain fetch skips anything stored FINISHED - so those codes never
    arrived and the match stayed permanently un-capturable."""
    _match(db, "m1", age_days=2, code=None)
    assert db.matches_needing_backfill(14) == {"m1"}


def test_complete_or_old_matches_are_not_refetched(db: Database) -> None:
    """Each re-fetch costs an API call, so only matches that can still gain a code
    qualify: not the complete ones, not ones too old for a code to appear."""
    _match(db, "done", age_days=2, code="ABC123")
    _match(db, "old", age_days=90, code=None)
    assert db.matches_needing_backfill(14) == set()
    assert db.matches_needing_backfill(0) == set()      # 0 disables the window


def test_skip_stored_lets_a_backfill_candidate_through(db: Database) -> None:
    """_skip_stored is what all three fetch paths consult: a candidate must not be
    skipped, and a complete stored match must still be."""
    _match(db, "need", age_days=1, code=None)
    _match(db, "have", age_days=1, code="ABC123")
    engine = SyncEngine(make_client()[0], db)
    assert engine._skip_stored("need", force_refresh=False) is False
    assert engine._skip_stored("have", force_refresh=False) is True

"""Replay-code backfill: which stored matches are worth re-fetching.

The rule is narrow on purpose. Measured on 676 real matches, a missing replay
code is almost always permanent — replays were never published for that match —
so re-fetching every code-less match cost 44 API calls per run and recovered
nothing. Only a partial gap or a just-ingested match can still gain a code.
"""

from __future__ import annotations

from typing import Optional

from faceit_sync.db import Database
from faceit_sync.sync import SyncEngine
from conftest import make_client


def _match(db: Database, mid: str, age: str, codes: list[Optional[str]]) -> None:
    """Store a FINISHED match ``age`` ago (a SQLite modifier like '-2 days') whose
    games carry ``codes`` — None for a game with no replay code."""
    db.conn.execute("INSERT OR IGNORE INTO championships (id) VALUES ('c1')")
    db.conn.execute(
        "INSERT INTO matches (id, championship_id, status, finished_at, fetched_at) "
        "VALUES (?, 'c1', 'FINISHED', datetime('now', ?), datetime('now'))", (mid, age))
    for i, code in enumerate(codes, start=1):
        db.conn.execute(
            "INSERT INTO games (match_id, game_no, demo_code) VALUES (?, ?, ?)",
            (mid, i, code))
    db.conn.commit()


def test_partial_gap_is_refetched(db: Database) -> None:
    """Some games have codes and some do not: the only shape consistent with a
    publish that has not finished landing, so it is worth another look."""
    _match(db, "partial", "-2 days", ["ABC123", None, "DEF456"])
    assert db.matches_needing_backfill(14) == {"partial"}


def test_wholly_codeless_match_is_left_alone(db: Database) -> None:
    """The expensive mistake this guards. A match with no code on ANY game never
    had replays published; re-fetching it forever recovers nothing. 39 of the 44
    candidates under the old rule were this case."""
    _match(db, "never", "-2 days", [None, None, None])
    assert db.matches_needing_backfill(14) == set()


def test_wholly_codeless_but_just_ingested_gets_a_grace_period(db: Database) -> None:
    """A match stored moments after it ended may genuinely not have its codes up
    yet, so brand-new matches are re-checked even with nothing to compare against."""
    _match(db, "fresh", "-1 hours", [None, None])
    assert db.matches_needing_backfill(14, fresh_hours=12) == {"fresh"}
    # ...but the grace period expires rather than running forever.
    assert db.matches_needing_backfill(14, fresh_hours=0) == set()


def test_complete_and_out_of_window_matches_are_left_alone(db: Database) -> None:
    _match(db, "done", "-2 days", ["ABC123", "DEF456"])
    _match(db, "old", "-90 days", ["ABC123", None])   # partial, but far too old
    assert db.matches_needing_backfill(14) == set()
    assert db.matches_needing_backfill(0) == set()    # 0 disables backfill entirely


def test_skip_stored_consults_the_backfill_set(db: Database) -> None:
    """_skip_stored is what all three fetch paths call: a candidate must get
    through, and a settled match must still be skipped."""
    _match(db, "partial", "-1 days", ["ABC123", None])
    _match(db, "done", "-1 days", ["ABC123", "DEF456"])
    engine = SyncEngine(make_client()[0], db)
    assert engine._skip_stored("partial", force_refresh=False) is False
    assert engine._skip_stored("done", force_refresh=False) is True

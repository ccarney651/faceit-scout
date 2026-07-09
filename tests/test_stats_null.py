"""HAZARD A: zeroed stat rows -> NULL + stats_captured=False, never zeros."""

from __future__ import annotations

import responses

from faceit_sync.db import Database
from faceit_sync.sync import SyncEngine
from conftest import RESTART_DC_ID, make_client, register_match


@responses.activate
def test_zeroed_rows_become_null_not_zero(db: Database) -> None:
    register_match(responses, RESTART_DC_ID, prefix="restart_dc", democracy=True)
    SyncEngine(make_client()[0], db).ingest_match(RESTART_DC_ID, force_refresh=True)

    # In restart_dc game 3, one team DC'd at game end: role '-', all stats zeroed.
    uncaptured = db.conn.execute(
        """SELECT role, eliminations, deaths, assists, damage, healing
           FROM round_players
           WHERE game_no = 3 AND stats_captured = 0"""
    ).fetchall()
    assert len(uncaptured) == 5  # the whole DC'd team

    for r in uncaptured:
        assert r["role"] is None
        # The point: NULL, not 0.
        assert r["eliminations"] is None
        assert r["deaths"] is None
        assert r["assists"] is None
        assert r["damage"] is None
        assert r["healing"] is None

    # No row anywhere was zero-filled while marked uncaptured.
    zero_filled = db.conn.execute(
        "SELECT COUNT(*) FROM round_players WHERE stats_captured = 0 AND eliminations = 0"
    ).fetchone()[0]
    assert zero_filled == 0

    # Sanity: captured players DO have real (non-null) stats.
    captured = db.conn.execute(
        """SELECT eliminations FROM round_players
           WHERE stats_captured = 1 AND eliminations IS NOT NULL LIMIT 1"""
    ).fetchone()
    assert captured is not None

    # The game outcome is still valid (taken from results[], not the zeroed stats).
    winner = db.conn.execute(
        "SELECT winner_faction FROM games WHERE match_id = ? AND game_no = 3",
        (RESTART_DC_ID,),
    ).fetchone()["winner_faction"]
    assert winner in ("faction1", "faction2")

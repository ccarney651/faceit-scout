"""The durable /history veto feed recovers attribution when the live feed is gone.

The client tries ``/democracy/v1/match/{id}/history`` (which persists) before the
ephemeral live feed. Its entity shape differs (guid direct on the entity, order via
``round``, no ``config``), so this exercises the dual-format parser end to end.
"""

from __future__ import annotations

import responses

from faceit_sync.db import Database
from faceit_sync.sync import SyncEngine
from conftest import NORMAL_30_ID, make_client, register_match


@responses.activate
def test_history_feed_recovers_attribution(db: Database) -> None:
    # normal_30: a 3-0 sweep whose LIVE democracy has long expired (404), but
    # whose /history feed still serves the full veto with attribution.
    register_match(responses, NORMAL_30_ID, prefix="normal_30", democracy=True, veto="history")
    SyncEngine(make_client()[0], db).ingest_match(NORMAL_30_ID, force_refresh=True)

    played = db.conn.execute(
        "SELECT DISTINCT game_no FROM games WHERE match_id=? AND map_guid IS NOT NULL",
        (NORMAL_30_ID,),
    ).fetchall()
    assert len(played) == 3  # sweep

    # Every ban on every played game is attributed to a faction (the whole point).
    bans = db.conn.execute(
        "SELECT banned_by_faction FROM hero_bans WHERE match_id=?", (NORMAL_30_ID,)
    ).fetchall()
    assert len(bans) == 6  # 3 games x 2
    assert all(b["banned_by_faction"] in ("faction1", "faction2") for b in bans)

    # Map picks and side picks are attributed too (history has pick entities).
    picks = db.conn.execute(
        "SELECT picked_by_faction FROM map_picks WHERE match_id=? AND map_guid IS NOT NULL",
        (NORMAL_30_ID,),
    ).fetchall()
    assert all(p["picked_by_faction"] in ("faction1", "faction2") for p in picks)

    sides = db.conn.execute(
        "SELECT side_picked_by_faction FROM games WHERE match_id=? AND map_guid IS NOT NULL",
        (NORMAL_30_ID,),
    ).fetchall()
    assert all(s["side_picked_by_faction"] in ("faction1", "faction2") for s in sides)

    # No restarts in this clean sweep.
    assert db.conn.execute(
        "SELECT COUNT(*) FROM games WHERE match_id=? AND was_restarted=1", (NORMAL_30_ID,)
    ).fetchone()[0] == 0

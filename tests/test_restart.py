"""HAZARD B: a restarted game keeps its bans but loses veto attribution."""

from __future__ import annotations

import responses

from faceit_sync.db import Database
from faceit_sync.sync import SyncEngine, parse_match_id, dedupe_preserving_order
from conftest import RESTART_DC_ID, make_client, register_match


@responses.activate
def test_restarted_game_bans_recorded_attribution_null(db: Database) -> None:
    register_match(responses, RESTART_DC_ID, prefix="restart_dc", democracy=True)
    SyncEngine(make_client()[0], db).ingest_match(RESTART_DC_ID, force_refresh=True)

    # restart_dc: attribution is joined by BAN-SET, not slot index. On real data
    # game 1's ban pair matches no democracy veto slot (its ticket was wiped by
    # the restart), while games 2 and 3 match intact slots. So game 1 is the one
    # with known bans but NULL attribution.
    games = {
        r["game_no"]: r["was_restarted"]
        for r in db.conn.execute(
            "SELECT game_no, was_restarted FROM games WHERE match_id = ?",
            (RESTART_DC_ID,),
        ).fetchall()
    }
    # Exactly one played game lost its veto attribution.
    assert sum(games.values()) == 1
    restarted = next(gno for gno, r in games.items() if r == 1)
    assert restarted == 1  # concretely, game 1 on this match

    restarted_bans = db.conn.execute(
        "SELECT banned_by_faction FROM hero_bans WHERE match_id = ? AND game_no = ?",
        (RESTART_DC_ID, restarted),
    ).fetchall()
    assert len(restarted_bans) == 2                                  # bans ARE known...
    assert all(b["banned_by_faction"] is None for b in restarted_bans)  # ...actor is NOT

    # The other games keep full attribution.
    for gno in (gno for gno in games if gno != restarted):
        bans = db.conn.execute(
            "SELECT banned_by_faction FROM hero_bans WHERE match_id = ? AND game_no = ?",
            (RESTART_DC_ID, gno),
        ).fetchall()
        assert len(bans) == 2
        assert all(b["banned_by_faction"] in ("faction1", "faction2") for b in bans)

    # Reconciliation invariant: every played game has exactly one ban pair.
    per_game = db.conn.execute(
        "SELECT game_no, COUNT(*) n FROM hero_bans WHERE match_id = ? GROUP BY game_no",
        (RESTART_DC_ID,),
    ).fetchall()
    assert {r["game_no"]: r["n"] for r in per_game} == {1: 2, 2: 2, 3: 2}


def test_parse_match_id_from_url_and_bare() -> None:
    url = f"https://www.faceit.com/en/ow2/room/{RESTART_DC_ID}"
    assert parse_match_id(url) == RESTART_DC_ID
    assert parse_match_id(RESTART_DC_ID) == RESTART_DC_ID
    assert parse_match_id("not-a-match") is None
    assert dedupe_preserving_order(["a", "b", "a", "c"]) == ["a", "b", "c"]

"""C1: demoURLs are positional, so replay codes are only trusted when the
alignment is. A restarted game or a count mismatch drops ALL codes for the match
— otherwise game i gets labeled with its neighbor's replay."""

from __future__ import annotations

import json

import conftest
import responses
from conftest import NORMAL_30_ID, RESTART_DC_ID, make_client, register_match

from faceit_sync.db import Database
from faceit_sync.sync import SyncEngine


def _codes(db: Database, match_id: str) -> list[str]:
    return [
        r["demo_code"] for r in db.conn.execute(
            "SELECT demo_code FROM games WHERE match_id = ? ORDER BY game_no",
            (match_id,),
        ).fetchall()
    ]


def _register_with_demo_urls(responses_mock, match_id: str, prefix: str,
                             urls: list[str], *, veto: str) -> None:
    """register_match, but with the match fixture's demoURLs replaced by ``urls``."""
    orig = conftest.load_fixture

    def patched(name: str) -> str:
        text = orig(name)
        if name == f"{prefix}_match.json":
            payload = json.loads(text)
            payload["payload"]["demoURLs"] = urls
            text = json.dumps(payload)
        return text

    conftest.load_fixture = patched
    try:
        register_match(responses_mock, match_id, prefix=prefix, democracy=True, veto=veto)
    finally:
        conftest.load_fixture = orig


@responses.activate
def test_demo_codes_stored_when_alignment_is_clean(db: Database) -> None:
    """normal_30: a clean 3-0 sweep, 3 codes for 3 games -> every game keeps its replay."""
    register_match(responses, NORMAL_30_ID, prefix="normal_30", democracy=True, veto="history")
    SyncEngine(make_client()[0], db).ingest_match(NORMAL_30_ID, force_refresh=True)
    assert _codes(db, NORMAL_30_ID) == ["KR1HDD", "K6Z6D5", "4WVR3J"]


@responses.activate
def test_demo_codes_dropped_on_restarted_game(db: Database) -> None:
    """restart_dc: game 1's veto slot was wiped by a restart, so FACEIT's demoURLs
    order is no longer trustworthy -> ALL codes dropped rather than misattributed."""
    register_match(responses, RESTART_DC_ID, prefix="restart_dc", democracy=True)
    SyncEngine(make_client()[0], db).ingest_match(RESTART_DC_ID, force_refresh=True)
    assert _codes(db, RESTART_DC_ID) == [None, None, None]


@responses.activate
def test_demo_codes_dropped_on_length_mismatch(db: Database) -> None:
    """A demoURLs count that doesn't match the game count is ambiguous -> drop all."""
    _register_with_demo_urls(responses, NORMAL_30_ID, "normal_30", ["ONLY1"], veto="history")
    SyncEngine(make_client()[0], db).ingest_match(NORMAL_30_ID, force_refresh=True)
    assert _codes(db, NORMAL_30_ID) == [None, None, None]

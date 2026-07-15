"""Integrity checks (SPEC §9): banned-hero detection, map-name compare, and the
verify-codes / demoURLs-bug report."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Iterator

import pytest

from owscout.db import Database
from owscout.integrity import (
    VerifyCodesRow,
    banned_hero_hits,
    map_names_match,
    over_ban_hit_threshold,
    verify_codes_report,
)
from owscout.models import CodeContext


# --- §9.1 banned-hero -------------------------------------------------------


def test_banned_hits_found_and_none_ignored() -> None:
    assert banned_hero_hits(["a", None, "banned1", "b"], {"banned1", "banned2"}) == ["banned1"]


def test_no_banned_hits() -> None:
    assert banned_hero_hits(["a", "b", None], {"x"}) == []


def test_over_threshold() -> None:
    assert over_ban_hit_threshold(3, 100, rate=0.02) is True     # 3% > 2%
    assert over_ban_hit_threshold(1, 100, rate=0.02) is False    # 1% < 2%
    assert over_ban_hit_threshold(0, 0) is False                 # nothing resolved


# --- §9.2 map-name compare --------------------------------------------------


def test_map_names_exact_and_normalised() -> None:
    assert map_names_match("Kings Row", "Kings Row")
    assert map_names_match("king's row", "Kings Row")       # punctuation/case
    assert map_names_match("KINGSROW", "Kings Row")


def test_map_names_tolerates_ocr_noise() -> None:
    assert map_names_match("Kings R0w", "Kings Row")        # one-char OCR slip


def test_map_names_reject_different_map() -> None:
    assert not map_names_match("Ilios", "Kings Row")


def test_map_names_reject_empty() -> None:
    assert not map_names_match("", "Kings Row")


# --- §9.2 verify-codes report -----------------------------------------------


def _row(mv: int | None, restart: bool, gn: int = 1) -> VerifyCodesRow:
    return VerifyCodesRow(match_id="M", game_no=gn, map_verified=mv, match_has_restart=restart)


def test_report_no_mismatches() -> None:
    rep = verify_codes_report([_row(1, False), _row(1, True)])
    assert rep.mismatches == 0 and rep.mismatch_rate == 0.0
    assert not rep.clusters_on_restarts


def test_report_clusters_on_restarts() -> None:
    # Every mismatch is in a restart match -> the demoURLs-bug fingerprint.
    rep = verify_codes_report([_row(0, True, 1), _row(0, True, 2), _row(1, False, 3)])
    assert rep.mismatches == 2 and rep.mismatches_in_restart_matches == 2
    assert rep.clusters_on_restarts is True


def test_report_mismatch_in_clean_match_not_clustered() -> None:
    rep = verify_codes_report([_row(0, True), _row(0, False)])
    assert rep.mismatches == 2 and rep.mismatches_in_clean_matches == 1
    assert rep.clusters_on_restarts is False


def test_report_unchecked_excluded() -> None:
    rep = verify_codes_report([_row(None, True), _row(1, False)])
    assert rep.total == 2 and rep.checked == 1 and rep.mismatches == 0


# --- verify_codes_rows over ATTACH ------------------------------------------


@pytest.fixture()
def db(tmp_path: Path) -> Iterator[Database]:
    database = Database(str(tmp_path / "owscout.sqlite3"))
    yield database
    database.close()


def _faceit(path: Path) -> str:
    c = sqlite3.connect(str(path))
    c.executescript("""
        CREATE TABLE games(match_id TEXT, game_no INT, was_restarted INT DEFAULT 0);
        CREATE TABLE matches(id TEXT PRIMARY KEY, faction1_team_id TEXT, faction2_team_id TEXT);
        CREATE TABLE maps(guid TEXT, name TEXT, category TEXT);
        CREATE TABLE teams(id TEXT, name TEXT);
    """)
    # match RESTART has a restart shell; match CLEAN does not.
    c.executemany("INSERT INTO games VALUES(?,?,?)",
                  [("RESTART", 1, 1), ("RESTART", 2, 0), ("CLEAN", 1, 0)])
    c.commit(); c.close()
    return str(path)


def _ctx(match_id: str) -> CodeContext:
    return CodeContext(demo_code="X", match_id=match_id, game_no=2, map_guid=None,
                       map_name="Ilios", map_category=None, faction1_team_id="a",
                       faction1_team_name="A", faction2_team_id="b", faction2_team_name="B",
                       winner_faction=None, bans=[], players=[], already_captured=False)


def test_verify_codes_rows_flags_restart_matches(db: Database, tmp_path: Path) -> None:
    fp = _faceit(tmp_path / "faceit.sqlite3")
    # Capture one instance in the restart match, one in the clean match.
    r = db.upsert_map_instance_from_context(_ctx("RESTART"), side_a_faction="faction1")
    db.set_map_verified(r, 0)   # mismatch
    db.upsert_map_instance_from_context(_ctx("CLEAN"), side_a_faction="faction1")

    rows = db.verify_codes_rows(fp)
    by_match = {row.match_id: row for row in rows}
    assert by_match["RESTART"].match_has_restart is True
    assert by_match["RESTART"].map_verified == 0
    assert by_match["CLEAN"].match_has_restart is False
    rep = verify_codes_report(rows)
    assert rep.clusters_on_restarts is True

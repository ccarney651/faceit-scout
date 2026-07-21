"""The first-run progress label. Pure text formatting, testable off the GUI."""

from __future__ import annotations

import os
import sqlite3

from owscout.gui import _eta_text, _faceit_is_empty, _setup_hint


def test_setup_hint_walks_the_user_through_the_three_steps() -> None:
    assert _setup_hint(False, False).startswith("Step 1 of 3")   # not calibrated
    assert _setup_hint(True, False).startswith("Step 2 of 3")    # calibrated, no codes
    assert _setup_hint(True, True).startswith("Step 3 of 3")     # ready to capture


def test_setup_hint_is_ascii_safe() -> None:
    for cal in (True, False):
        for codes in (True, False):
            _setup_hint(cal, codes)   # must not raise building the string


def test_missing_faceit_db_reads_as_empty_without_creating_it(tmp_path) -> None:
    """Fresh machine: the check decides bootstrap. It must say 'empty' AND not
    create the file - a plain connect would, and an empty file then looks
    'present' to the snapshot-vs-crawl decision downstream."""
    missing = str(tmp_path / "faceit.sqlite3")
    assert _faceit_is_empty(missing) is True
    assert not os.path.exists(missing)


def test_populated_faceit_db_is_not_empty(tmp_path) -> None:
    p = str(tmp_path / "f.sqlite3")
    con = sqlite3.connect(p)
    con.execute("CREATE TABLE championships(id TEXT)")
    con.execute("INSERT INTO championships(id) VALUES ('c1')")
    con.commit()
    con.close()
    assert _faceit_is_empty(p) is False


def test_file_with_no_championships_reads_as_empty(tmp_path) -> None:
    p = str(tmp_path / "f.sqlite3")
    con = sqlite3.connect(p)
    con.execute("CREATE TABLE championships(id TEXT)")  # table but no rows
    con.commit()
    con.close()
    assert _faceit_is_empty(p) is True


def test_position_is_always_shown() -> None:
    assert _eta_text(1, 380, elapsed=2.0).startswith("match 1 of 380")


def test_no_estimate_until_the_sample_is_worth_quoting() -> None:
    """Early matches are warm-up + rate-limiter settling; a wild number reads
    as a broken tool, so nothing is promised yet."""
    assert _eta_text(3, 380, elapsed=6.0) == "match 3 of 380"


def test_estimate_appears_once_there_is_history() -> None:
    # 10 matches in 60s -> 370 left at 6s each -> ~37 min.
    assert _eta_text(10, 380, elapsed=60.0) == "match 10 of 380 - about 38 min left"


def test_the_last_stretch_avoids_a_silly_zero() -> None:
    assert _eta_text(378, 380, elapsed=1000.0) == "match 378 of 380 - under a minute left"


def test_final_match_drops_the_estimate() -> None:
    assert _eta_text(380, 380, elapsed=1000.0) == "match 380 of 380"


def test_label_stays_ascii() -> None:
    """cp1252 consoles and Tk both choke on stray unicode dashes/arrows."""
    for done in (1, 5, 100, 380):
        _eta_text(done, 380, elapsed=120.0).encode("ascii")

"""The first-run progress label. Pure text formatting, testable off the GUI."""

from __future__ import annotations

from owscout.gui import _eta_text


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

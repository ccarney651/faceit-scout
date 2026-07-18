"""Capture pipeline core (SPEC §7, §8.2, §8.3): game-time, temporal smoothing,
change-detection write scheduling, side assignment, player resolution.

All pure — no game, no OpenCV."""

from __future__ import annotations

import pytest

from owscout.capture import (
    CaptureSession,
    assign_sides,
    game_time_ms,
    resolve_player,
    should_write,
)
from owscout.match import SlotMatch, TemporalSmoother, modal_slot


def _matches(*guids: str | None, conf: float = 0.9) -> list[SlotMatch]:
    return [
        SlotMatch(slot_index=i, matched_role=None, state="alive",
                  hero_guid=g, hero_name=g, confidence=conf if g else 0.0,
                  resolved=g is not None, candidates=5)
        for i, g in enumerate(guids)
    ]


# --- game time ---------------------------------------------------------------


def test_game_time_scales_with_speed() -> None:
    assert game_time_ms(10.0, 1.0) == 10_000
    assert game_time_ms(10.0, 4.0) == 40_000   # 4x playback


def test_game_time_rejects_bad_speed() -> None:
    with pytest.raises(ValueError):
        game_time_ms(1.0, 0.0)


# --- modal_slot / TemporalSmoother -------------------------------------------


def test_modal_picks_majority() -> None:
    guid, conf = modal_slot([("A", 0.9), ("A", 0.7), ("B", 0.95)])
    assert guid == "A"
    assert conf == pytest.approx(0.8)  # mean of A's confidences


def test_modal_none_majority_stays_unresolved() -> None:
    assert modal_slot([(None, 0.0), (None, 0.0), ("A", 0.9)])[0] is None


def test_modal_tie_breaks_to_most_recent() -> None:
    assert modal_slot([("A", 0.9), ("B", 0.9)])[0] == "B"


def test_modal_empty() -> None:
    assert modal_slot([]) == (None, 0.0)


def test_smoother_window_and_current() -> None:
    sm = TemporalSmoother(num_slots=2, window=3)
    sm.push([("A", 0.9), ("X", 0.9)])
    sm.push([("A", 0.9), ("Y", 0.9)])
    sm.push([("B", 0.9), ("X", 0.9)])   # slot0 window [A,A,B] -> A; slot1 [X,Y,X] -> X
    cur = sm.current()
    assert cur[0][0] == "A" and cur[1][0] == "X"
    sm.push([("B", 0.9), ("X", 0.9)])   # window slides: slot0 [A,B,B] -> B
    assert sm.current()[0][0] == "B"


# --- should_write (change detection) -----------------------------------------


def test_first_write_always() -> None:
    assert should_write(("A",), None, 0, None, 30_000) is True


def test_no_write_when_same_within_interval() -> None:
    assert should_write(("A",), ("A",), 5_000, 0, 30_000) is False


def test_write_on_change() -> None:
    assert should_write(("B",), ("A",), 5_000, 0, 30_000) is True


def test_write_on_interval_elapsed() -> None:
    assert should_write(("A",), ("A",), 30_000, 0, 30_000) is True


# --- CaptureSession end to end -----------------------------------------------


def test_session_first_frame_writes() -> None:
    s = CaptureSession(num_slots=2, window=1)
    obs = s.observe("a", _matches("A", "B"), game_ts_ms=0)
    assert obs is not None
    assert obs.side == "a" and obs.slot_guids == ["A", "B"]
    assert obs.resolved and obs.comp_id is not None


def test_session_suppresses_identical_within_interval() -> None:
    s = CaptureSession(num_slots=2, window=1, write_interval_ms=30_000)
    assert s.observe("a", _matches("A", "B"), 0) is not None
    assert s.observe("a", _matches("A", "B"), 5_000) is None   # unchanged
    assert s.observe("a", _matches("A", "C"), 6_000) is not None  # swap -> write


def test_session_heartbeat_after_interval() -> None:
    s = CaptureSession(num_slots=2, window=1, write_interval_ms=30_000)
    s.observe("a", _matches("A", "B"), 0)
    assert s.observe("a", _matches("A", "B"), 30_000) is not None  # heartbeat


def test_session_smoothing_ignores_single_blip() -> None:
    s = CaptureSession(num_slots=1, window=5, write_interval_ms=999_999)
    # Establish "A" as the majority over several frames.
    s.observe("a", _matches("A"), 0)          # writes first
    s.observe("a", _matches("A"), 1_000)
    s.observe("a", _matches("A"), 2_000)
    # A one-frame mismatch to "B" is outvoted 3:1 -> smoothed comp stays "A".
    assert s.observe("a", _matches("B"), 3_000) is None
    assert s.observe("a", _matches("A"), 4_000) is None


def test_session_unresolved_has_no_comp_id() -> None:
    s = CaptureSession(num_slots=2, window=1)
    obs = s.observe("a", _matches("A", None), 0)
    assert obs is not None and not obs.resolved and obs.comp_id is None


def test_session_sides_are_independent() -> None:
    s = CaptureSession(num_slots=1, window=1)
    assert s.observe("a", _matches("A"), 0) is not None
    assert s.observe("b", _matches("Z"), 0) is not None  # side b first write


# --- side assignment (SPEC §8.2) ---------------------------------------------


def test_assign_sides_direct() -> None:
    assert assign_sides(
        ["Alice", "Bob"], ["Zed", "Yan"],
        ["Alice", "Bob"], ["Zed", "Yan"],
    ) == "faction1"


def test_assign_sides_swapped() -> None:
    assert assign_sides(
        ["Zed", "Yan"], ["Alice", "Bob"],
        ["Alice", "Bob"], ["Zed", "Yan"],
    ) == "faction2"


def test_assign_sides_ambiguous_returns_none() -> None:
    # Identical rosters give no orientation a lead.
    assert assign_sides(["A"], ["A"], ["A"], ["A"]) is None


# --- player resolution (SPEC §8.2) -------------------------------------------


def test_resolve_player_matches_close_name() -> None:
    roster = [("p1", "Neliozu"), ("p2", "TONASA")]
    assert resolve_player("neliozu", roster) == "p1"


def test_resolve_player_below_threshold_is_none() -> None:
    roster = [("p1", "Neliozu"), ("p2", "TONASA")]
    assert resolve_player("zxqwv", roster) is None


def test_palette_hint_names_the_dead_side() -> None:
    """The colorblind-UI signature: one side blind, the other healthy. The
    message must name the failing side and the actual cause - without it the
    failure reads as 'the tool is broken', not 'the palette differs'."""
    from owscout.capture import palette_mismatch_hint
    hint = palette_mismatch_hint(1, 10, 9, 10, snapshots=2)
    assert hint is not None and "LEFT" in hint and "color" in hint
    hint = palette_mismatch_hint(9, 10, 1, 10, snapshots=2)
    assert hint is not None and "RIGHT" in hint


def test_palette_hint_both_sides_dead() -> None:
    from owscout.capture import palette_mismatch_hint
    hint = palette_mismatch_hint(1, 10, 2, 10, snapshots=3)
    assert hint is not None and "either team" in hint


def test_palette_hint_stays_quiet_when_healthy_or_early() -> None:
    """A healthy capture, an ordinary mixed read, or a single bad frame (loading
    screen, kill cam) must not trigger a scary diagnosis."""
    from owscout.capture import palette_mismatch_hint
    assert palette_mismatch_hint(9, 10, 10, 10, snapshots=5) is None
    assert palette_mismatch_hint(6, 10, 5, 10, snapshots=5) is None   # meh, not dead
    assert palette_mismatch_hint(0, 5, 5, 5, snapshots=1) is None     # one frame
    assert palette_mismatch_hint(0, 0, 0, 0, snapshots=9) is None     # no slots


# --- auto side-detection (real OCR fixtures from 2026-07-18 probe) -----------

WASP = ["envii_ow", "mellun", "twobleed", "DazedReox", "hzl113"]
DYST = ["Javi44", "BuFayez2", "Maquade", "Aufy", "jamal1505"]
# Verbatim Windows-OCR output from aligned dxcam frames. Note WHITEBEARD: that
# player's battletag shares nothing with any faceit nickname on the roster.
READ_L = ["MELLUN", "RDY", "DAZEDREOX", "ENVII", "HZL"]
READ_R = ["AUFY", "#####", "WHITEBEARD", "BUFAYEZ", "JAMALI 505"]
# Verbatim output from a misaligned frame: pure noise, yet it cleared the OLD
# assign_sides margin - which is exactly why the confident variant exists.
GARBAGE_L = ["", "ili1i11i111r1'/,7", "", "naaanno", ""]
GARBAGE_R = ["", "", "anna", "", ""]


def test_confident_side_from_real_ocr_reads() -> None:
    from owscout.capture import confident_left_faction
    assert confident_left_faction(READ_L, READ_R, WASP, DYST) == "faction1"
    # Same frames, rosters swapped in the call: the verdict must flip with them.
    assert confident_left_faction(READ_L, READ_R, DYST, WASP) == "faction2"


def test_confident_side_survives_battletag_mismatch() -> None:
    """WHITEBEARD matches no faceit nickname; the contrast between rosters must
    carry the verdict without it - battletags are not required data."""
    from owscout.capture import confident_left_faction
    assert confident_left_faction(READ_L, READ_R, WASP, DYST) == "faction1"


def test_garbage_reads_are_refused_not_guessed() -> None:
    """The failure that motivated the strict gates: noise cleared the old 1.0
    margin and would have silently mirrored every side-dependent stat."""
    from owscout.capture import assign_sides, confident_left_faction
    assert assign_sides(GARBAGE_L, GARBAGE_R, WASP, DYST) is not None  # the trap
    assert confident_left_faction(GARBAGE_L, GARBAGE_R, WASP, DYST) is None


def test_empty_reads_are_refused() -> None:
    from owscout.capture import confident_left_faction
    assert confident_left_faction([""] * 5, [""] * 5, WASP, DYST) is None

"""The pure half of the refs-trainer contract: roster -> step plan -> .opy."""

from __future__ import annotations

import pytest

from owdb.refs import classify_marker, parse_step_index
from owdb.refs_trainer import (
    DONE_SENTINEL,
    decode_marker,
    encode_marker,
    hero_enum,
    partition_roster,
    plan_sequence,
    render_opy,
)

# --- name -> Hero enum ------------------------------------------------------


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("Ana", "ANA"),
        ("D.Va", "DVA"),
        ("DVa", "DVA"),           # faceit's dotless spelling
        ("Soldier: 76", "SOLDIER"),
        ("Soldier 76", "SOLDIER"),
        ("Lúcio", "LUCIO"),
        ("Lucio", "LUCIO"),       # accent dropped
        ("Torbjörn", "TORBJORN"),
        ("Wrecking Ball", "WRECKING_BALL"),
        ("Junker Queen", "JUNKER_QUEEN"),
        ("D.Mon", "DMON"),        # overpy 9.7.16 added the constant
    ],
)
def test_hero_enum_matches_across_spellings(name: str, expected: str) -> None:
    assert hero_enum(name) == expected


def test_hero_enum_unknown_is_none() -> None:
    assert hero_enum("Not A Hero") is None


# --- roster partition -----------------------------------------------------


def test_partition_splits_and_sorts_case_insensitively() -> None:
    mappable, unmapped = partition_roster(["winston", "Ana", "Nonhero", "ashe"])
    assert mappable == ["Ana", "ashe", "winston"]
    assert unmapped == ["Nonhero"]


def test_partition_dedupes() -> None:
    mappable, _ = partition_roster(["Ana", "Ana", "Ashe"])
    assert mappable == ["Ana", "Ashe"]


# --- plan_sequence ------------------------------------------------------


def test_plan_chunks_into_rows_of_team_size() -> None:
    names = ["Ana", "Ashe", "Bastion", "Brigitte", "Cassidy", "Echo", "Genji"]
    rows = plan_sequence(names, team_size=5)
    assert rows[0] == ["Ana", "Ashe", "Bastion", "Brigitte", "Cassidy"]
    assert len(rows) == 2


def test_plan_pads_last_row_by_repeating_final_hero() -> None:
    rows = plan_sequence(["Ana", "Ashe", "Bastion", "Brigitte", "Cassidy", "Echo"], 5)
    assert rows[1] == ["Echo", "Echo", "Echo", "Echo", "Echo"]
    assert all(len(r) == 5 for r in rows)


def test_plan_excludes_unmapped_heroes() -> None:
    rows = plan_sequence(["Ana", "Nonhero", "Ashe"], team_size=5)
    flat = {n for r in rows for n in r}
    assert "Nonhero" not in flat
    assert flat == {"Ana", "Ashe"}


def test_plan_empty_when_nothing_mappable() -> None:
    assert plan_sequence(["Nonhero", "Someone Else"]) == []


def test_plan_is_deterministic_regardless_of_input_order() -> None:
    a = plan_sequence(["Ana", "Ashe", "Bastion"])
    b = plan_sequence(["Bastion", "Ana", "Ashe"])
    assert a == b


# --- marker encode/decode (alive+dead counter contract) --------------------


@pytest.mark.parametrize(
    ("step", "state", "marker"),
    [
        (0, "alive", 0),
        (0, "dead", 1),
        (1, "alive", 2),
        (5, "dead", 11),
        (10, "alive", 20),
    ],
)
def test_encode_marker(step: int, state: str, marker: int) -> None:
    assert encode_marker(step, state) == marker


@pytest.mark.parametrize("marker", [0, 1, 2, 11, 20, 21])
def test_marker_round_trips(marker: int) -> None:
    step, state = decode_marker(marker)
    assert encode_marker(step, state) == marker


def test_decode_marker_sentinel_is_none() -> None:
    assert decode_marker(DONE_SENTINEL) is None


def test_decode_marker_even_is_alive_odd_is_dead() -> None:
    assert decode_marker(4) == (2, "alive")
    assert decode_marker(7) == (3, "dead")


# --- render_opy -------------------------------------------------------


def test_render_opy_bakes_the_sequence_and_bounds() -> None:
    rows = plan_sequence(["Ana", "Ashe", "Bastion", "Brigitte", "Cassidy", "Echo"], 5)
    src = render_opy(rows, hold=6.0, settle=2.0)
    assert "Hero.ANA" in src and "Hero.ECHO" in src
    assert "while step < 2:" in src
    assert f"shown = {DONE_SENTINEL}" in src
    assert "createDummy(SEQ[step][slot], Team.1, slot" in src


def test_render_opy_marks_alive_then_dead_per_step() -> None:
    rows = plan_sequence(["Ana", "Ashe"], 5)
    src = render_opy(rows)
    assert "shown = step * 2" in src          # alive marker
    assert "shown = step * 2 + 1" in src      # dead marker


def test_render_opy_kills_bots_for_the_dead_pass() -> None:
    src = render_opy(plan_sequence(["Ana", "Ashe"], 5))
    assert ".disableRespawn()" in src         # so the kill sticks through the hold
    assert "kill(getAllPlayers(), null)" in src


def test_render_opy_rejects_empty_plan() -> None:
    with pytest.raises(ValueError):
        render_opy([])


# --- parse_step_index (the OCR side of the contract) ------------------------


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("REFS 0", 0),
        ("REFS 7", 7),
        ("REFS 10", 10),
        (f"REFS {DONE_SENTINEL}", DONE_SENTINEL),
        ("REFS O", 0),          # O -> 0 is visually unambiguous, safe to repair
        ("REFS l", 1),
        ("R3FS 4", 4),          # OCR read the E as a 3
        ("  refs   3  ", 3),
        ("CONTROL POINT UNLOCKS IN REFS 2 6.4", 2),  # anchor past the objective text
        ("garbage 42 REFS 6", 6),                    # ignore the stray number
    ],
)
def test_parse_step_index(text: str, expected: int) -> None:
    assert parse_step_index(text) == expected


@pytest.mark.parametrize(
    "text",
    [
        "",
        "REFS",
        "totally unrelated",
        "REFS B",   # 6/B and 5/S flip too often — a miss beats a mislabel
        "REFS S",
    ],
)
def test_parse_step_index_none(text: str) -> None:
    assert parse_step_index(text) is None


# --- classify_marker (autolearn's per-frame decision) ---------------------------

NROWS = 11  # 53 heroes / 5


def test_classify_done_sentinel() -> None:
    assert classify_marker(DONE_SENTINEL, set(), NROWS) == ("done", None, [])


def test_classify_first_marker_is_the_alive_pass_of_step_0() -> None:
    assert classify_marker(0, set(), NROWS) == ("expected", (0, "alive"), [])


def test_classify_next_marker_after_alive_is_the_dead_pass_of_the_same_step() -> None:
    assert classify_marker(1, {0}, NROWS) == ("expected", (0, "dead"), [])


def test_classify_marker_behind_progress_waits() -> None:
    assert classify_marker(1, {0, 1, 2}, NROWS) == ("wait", None, [])


def test_classify_missing_read_waits() -> None:
    assert classify_marker(None, set(), NROWS) == ("wait", None, [])


def test_classify_forward_jump_reports_the_skipped_markers() -> None:
    kind, decoded, lost = classify_marker(4, {0, 1}, NROWS)
    assert kind == "ahead"
    assert decoded == (2, "alive")
    assert lost == [2, 3]


def test_classify_marker_past_the_last_dead_pass_waits() -> None:
    # 11 rows -> markers 0..21; 22 is off the end, not a real step.
    done = set(range(22))
    assert classify_marker(22, done, NROWS) == ("wait", None, [])

"""tools/audit_capture_sides.py -- the swap-detection logic.

The load-bearing case is the regression this module was written to fix: a side
with NO player tags at all (auto-detect only ran on one HUD half, which is
common) must contribute zero evidence, not read as "does not match its side"
and get flagged as a swap. Only tags that actively point at the OTHER declared
team are swap evidence.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any

TOOL = Path(__file__).resolve().parents[1] / "tools" / "audit_capture_sides.py"
_spec = importlib.util.spec_from_file_location("audit_capture_sides", TOOL)
assert _spec and _spec.loader
audit = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = audit
_spec.loader.exec_module(audit)

TEAM_A, TEAM_B, TEAM_C = "team-a-id", "team-b-id", "team-c-id"
ROSTER = {
    "pa1": TEAM_A, "pa2": TEAM_A, "pa3": TEAM_A,
    "pb1": TEAM_B, "pb2": TEAM_B, "pb3": TEAM_B,
    "pc1": TEAM_C,
}


def _map(side_a: str, side_b: str, obs: list[dict[str, Any]]) -> dict[str, Any]:
    return {"side_a_team_id": side_a, "side_b_team_id": side_b, "observations": obs}


def _obs(side: str, player_ids: list[str | None]) -> dict[str, Any]:
    return {"side": side, "pairs": [[f"hero{i}", pid] for i, pid in enumerate(player_ids)]}


def test_correctly_attributed_sides_are_ok() -> None:
    m = _map(TEAM_A, TEAM_B, [
        _obs("a", ["pa1", "pa2", "pa3"]),
        _obs("b", ["pb1", "pb2", "pb3"]),
    ])
    assert audit._audit_map(m, ROSTER)["verdict"] == "OK"


def test_genuinely_swapped_sides_are_flagged() -> None:
    """Both sides' tagged players belong to the OTHER declared team."""
    m = _map(TEAM_A, TEAM_B, [
        _obs("a", ["pb1", "pb2", "pb3"]),   # side "a" is actually Team B
        _obs("b", ["pa1", "pa2", "pa3"]),   # side "b" is actually Team A
    ])
    assert audit._audit_map(m, ROSTER)["verdict"] == "SWAPPED"


def test_one_untagged_side_does_not_read_as_a_swap() -> None:
    """Regression: side A has zero tags (auto-detect ran on B only). This is a
    real shape seen in data/captures/gcb.json and was originally mis-scored as
    SUSPECT before this side-blindness was distinguished from swap evidence."""
    m = _map(TEAM_A, TEAM_B, [
        _obs("a", [None, None, None, None, None]),   # never resolved to any player
        _obs("b", ["pb1", "pb2", "pb3"]),             # matches its declared team
    ])
    assert audit._audit_map(m, ROSTER)["verdict"] == "OK"


def test_one_untagged_side_with_the_other_swapped_still_flags() -> None:
    """One side silent, the other's tags point at the OTHER declared team --
    that lone side is still real evidence and must not be discarded just
    because its partner has none."""
    m = _map(TEAM_A, TEAM_B, [
        _obs("a", [None, None, None]),
        _obs("b", ["pa1", "pa2", "pa3"]),   # side "b" is actually Team A
    ])
    assert audit._audit_map(m, ROSTER)["verdict"] == "SWAPPED"


def test_no_tags_anywhere_is_untagged_not_ok_or_swapped() -> None:
    m = _map(TEAM_A, TEAM_B, [_obs("a", [None] * 5), _obs("b", [None] * 5)])
    assert audit._audit_map(m, ROSTER)["verdict"] == "UNTAGGED"


def test_below_minimum_tag_count_does_not_resolve() -> None:
    """One or two tags could be a single stray OCR hit; must not call a side
    off that alone, in either direction."""
    m = _map(TEAM_A, TEAM_B, [
        _obs("a", ["pb1"]),                  # only 1 tag, points at Team B
        _obs("b", ["pb1", "pb2", "pb3"]),     # 3 tags, cleanly Team B, matches
    ])
    assert audit._audit_map(m, ROSTER)["verdict"] == "OK"


def test_mixed_tags_below_majority_do_not_resolve() -> None:
    """A side whose tags split roughly evenly across two teams (bad OCR, a
    mid-map substitution) is not confident evidence either way."""
    m = _map(TEAM_A, TEAM_B, [
        _obs("a", ["pa1", "pa1", "pb1", "pb1"]),   # 50/50 -- below MAJORITY
        _obs("b", ["pb1", "pb2", "pb3"]),
    ])
    res = audit._audit_map(m, ROSTER)
    assert res["verdict"] == "OK"   # side a contributes nothing; side b matches


def test_tags_pointing_at_a_third_team_are_suspect() -> None:
    """Tags resolve confidently, but to neither team FACEIT recorded for this
    game -- a genuinely confusing case that should surface for a human, not be
    silently called either OK or SWAPPED."""
    m = _map(TEAM_A, TEAM_B, [
        _obs("a", ["pc1", "pc1", "pc1"]),
        _obs("b", ["pb1", "pb2", "pb3"]),
    ])
    assert audit._audit_map(m, ROSTER)["verdict"] == "SUSPECT"

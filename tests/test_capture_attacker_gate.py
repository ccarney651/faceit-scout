"""The browser capture app's Escort/Hybrid round-3+ attacker gate.

FEATURES.md documents the underlying rule: "Attack/defend is derived for
Escort/Hybrid -- red attacks round 1, teams flip each round -- but from round 3
the attacker is decided by time bank, not parity." The capture app previously
kept auto-flipping its own best guess on every round, silently baking a wrong
guess into round 3+ observations. These tests pin the fix: rounds 1-2 keep the
free parity flip, round 3+ starts UNCONFIRMED each round and the capture gate
(attackerGateOk) refuses to save anything until the operator confirms.

Extracts the two pure decision functions from the shipped index.html and
executes them under Node -- no DOM, no video, matching the "pure decision
helper" pattern already used for faceit_sync/_dashboard.py's own pure helpers
(tests/test_dashboard_logic.py).
"""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

APP = Path(__file__).resolve().parents[1] / "docs" / "capture" / "index.html"


def _pure_js() -> str:
    html = APP.read_text(encoding="utf-8")
    start = html.index("function nextAttackerState(")
    end = html.index("function nextRound(")
    assert end > start, "extraction anchors moved in index.html"
    return html[start:end]


def _run(body: str) -> object:
    node = shutil.which("node")
    if not node:
        pytest.skip("node not available to run the capture app's helpers")
    src = _pure_js() + "\nconsole.log(JSON.stringify((()=>{" + body + "})()));"
    proc = subprocess.run([node, "-e", src], capture_output=True, text=True)
    assert proc.returncode == 0, f"node failed:\n{proc.stderr}"
    return json.loads(proc.stdout)


# --- nextAttackerState -------------------------------------------------

def test_non_phased_map_never_gates() -> None:
    """Control/Flashpoint/Push have no attacker concept at all."""
    got = _run("return nextAttackerState(false, 'a', 5);")
    assert got == {"attacker": None, "confirmed": True}


def test_round_1_to_2_flips_with_no_confirmation_needed() -> None:
    """The settled rule: red (b) attacks R1, flips R2 -- free, no operator input."""
    got = _run("return nextAttackerState(true, 'b', 2);")
    assert got == {"attacker": "a", "confirmed": True}


def test_round_2_to_3_stops_guessing() -> None:
    """This is the regression: round 3 must NOT auto-flip parity-style -- it must
    start unconfirmed so the gate blocks capture until the operator says who."""
    got = _run("return nextAttackerState(true, 'a', 3);")
    assert got["confirmed"] is False
    # The prior value survives only as a UI hint, not an answer.
    assert got["attacker"] == "a"


def test_round_3_to_4_also_requires_a_fresh_confirmation() -> None:
    """Every round from 3 onward is independently time-bank based -- confirming
    round 3 must not silently carry over to round 4."""
    got = _run("return nextAttackerState(true, 'b', 4);")
    assert got["confirmed"] is False


# --- attackerGateOk ------------------------------------------------------

def test_gate_open_for_round_1_and_2() -> None:
    assert _run("return attackerGateOk({phased:true, round:1, attackerConfirmed:false});") is True
    assert _run("return attackerGateOk({phased:true, round:2, attackerConfirmed:false});") is True


def test_gate_closed_at_round_3_until_confirmed() -> None:
    assert _run("return attackerGateOk({phased:true, round:3, attackerConfirmed:false});") is False
    assert _run("return attackerGateOk({phased:true, round:3, attackerConfirmed:true});") is True


def test_gate_never_applies_to_non_phased_maps() -> None:
    """A Control map at 'round 5' (points) must never be gated by this rule."""
    assert _run("return attackerGateOk({phased:false, round:5, attackerConfirmed:false});") is True


def test_gate_tolerates_a_missing_session() -> None:
    """A null session must fail OPEN (not gated), not throw -- basic defensive
    hygiene for a small pure helper reused across several call sites."""
    assert _run("return attackerGateOk(null);") is True

"""Browser capture app: process-of-elimination name attribution.

Extracts the pure attribute()/simScore() region from index.html (same
pattern as test_capture_attacker_gate.py) and runs it under Node.
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
    start = html.index("const AUTO_SIDE_MARGIN=")
    end = html.index("function setDetectMsg(")
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


_ROSTER = ("[{id:'p1',name:'Alison'},{id:'p2',name:'Sivaartt'},"
           "{id:'p3',name:'Kroxz'},{id:'p4',name:'Zorrow'},{id:'p5',name:'Benislover'}]")


def test_four_strong_matches_leave_the_fifth_slot_to_elimination() -> None:
    # Slot 4's OCR read is garbage (no strong match), but only p5 is left unused.
    names = "['Alison','Sivaartt','Kroxz','Zorrow','garb1ed$$']"
    got = _run(f"return attribute({names},{_ROSTER});")
    assert got == ["p1", "p2", "p3", "p4", "p5"]


def test_two_open_slots_stay_unresolved_not_guessed() -> None:
    names = "['Alison','Sivaartt','Kroxz','garb1ed$$','n0ise!!']"
    got = _run(f"return attribute({names},{_ROSTER});")
    assert got == ["p1", "p2", "p3", None, None]


def test_all_five_strong_matches_need_no_elimination() -> None:
    names = "['Alison','Sivaartt','Kroxz','Zorrow','Benislover']"
    got = _run(f"return attribute({names},{_ROSTER});")
    assert got == ["p1", "p2", "p3", "p4", "p5"]

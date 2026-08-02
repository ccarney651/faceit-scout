"""Browser capture app: hero->player name attribution in live preview.

Extracts the pure playerName() helper from index.html (same pattern as
test_capture_attribution.py) and runs it under Node with a stubbed code/roster.
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
    start = html.index("function playerName(pid)")
    end = html.index("return pid; }", start)
    assert end > start, "extraction anchors moved in index.html"
    return html[start:end + len("return pid; }")]


_STUB = """
function selectedCode(){ return { match_id:'m1', t1:'t1', t2:'t2' }; }
const DATA={ rosters:{ m1:{
  t1:{ name:'Alpha', players:[
    {id:'p1',game_name:'Alison',nick:'ali'}, {id:'p2',game_name:'',nick:'Sivaartt'}] },
  t2:{ name:'Beta', players:[
    {id:'p3',game_name:'Kroxz',nick:'kr'}, {id:'p4',game_name:'Zorrow',nick:'zo'}] } } } };
"""


def _run(body: str) -> object:
    node = shutil.which("node")
    if not node:
        pytest.skip("node not available to run the capture app's helpers")
    src = _STUB + _pure_js() + "\nconsole.log(JSON.stringify((()=>{" + body + "})()));"
    proc = subprocess.run([node, "-e", src], capture_output=True, text=True)
    assert proc.returncode == 0, f"node failed:\n{proc.stderr}"
    return json.loads(proc.stdout)


def test_game_name_wins_over_nick() -> None:
    assert _run("return playerName('p1');") == "Alison"


def test_nick_fills_when_game_name_empty() -> None:
    assert _run("return playerName('p2');") == "Sivaartt"


def test_second_team_roster_looked_up() -> None:
    assert _run("return playerName('p3');") == "Kroxz"


def test_unknown_id_returns_the_id_itself() -> None:
    assert _run("return playerName('nope');") == "nope"


def test_falsy_id_returns_empty_string() -> None:
    assert _run("return playerName(null);") == ""

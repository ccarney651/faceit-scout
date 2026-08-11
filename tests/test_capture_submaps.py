"""Browser capture app: spent sub-map elimination on control maps.

An Overwatch Control match plays each sub-map at most once - a round never
revisits one - so a sub-map already captured in an earlier round is spent.
usedSubmaps() returns that spent set so the picker can dim them and the
operator eliminates as they go rather than re-reading the full list each
round.

Scoping matters in both directions and is what these tests pin: the round
IN PROGRESS must not mark its own sub-map spent (it's the active pick, not
a used-up one), while every earlier round's must be.
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
    start = html.index("function usedSubmaps(snaps, currentRound){")
    end = html.index("\n}", start) + len("\n}")
    assert end > start, "extraction anchors moved in index.html"
    return html[start:end]


def _run(body: str) -> object:
    node = shutil.which("node")
    if not node:
        pytest.skip("node not available to run the capture app's helpers")
    # Set is not JSON-serialisable; hand back a sorted array for comparison.
    src = _pure_js() + "\nconsole.log(JSON.stringify([...(()=>{" + body + "})()].sort()));"
    proc = subprocess.run([node, "-e", src], capture_output=True, text=True)
    assert proc.returncode == 0, f"node failed:\n{proc.stderr}"
    return json.loads(proc.stdout)


def test_no_snapshots_yet_means_nothing_is_spent() -> None:
    assert _run("return usedSubmaps([], 1);") == []


def test_an_earlier_rounds_submap_is_spent() -> None:
    snaps = "[{round:1,sub:'Gardens'},{round:1,sub:'Gardens'}]"
    assert _run(f"return usedSubmaps({snaps}, 2);") == ["Gardens"]


def test_the_round_in_progress_does_not_spend_its_own_submap() -> None:
    # Mid-round-1 with snapshots already taken: Gardens is the ACTIVE pick and
    # must stay undimmed, or the operator sees the map they're on struck out.
    snaps = "[{round:1,sub:'Gardens'}]"
    assert _run(f"return usedSubmaps({snaps}, 1);") == []


def test_each_completed_round_adds_its_own_submap() -> None:
    snaps = ("[{round:1,sub:'Gardens'},{round:1,sub:'Gardens'},"
             "{round:2,sub:'City Center'},{round:3,sub:'University'}]")
    assert _run(f"return usedSubmaps({snaps}, 3);") == ["City Center", "Gardens"]


def test_snapshots_with_no_submap_are_ignored() -> None:
    # Non-control maps carry sub:null on every snap; nothing should be spent.
    snaps = "[{round:1,sub:null},{round:2,sub:undefined},{round:2,sub:''}]"
    assert _run(f"return usedSubmaps({snaps}, 3);") == []


def test_a_missing_snaps_list_is_tolerated() -> None:
    # renderPipControls can run against a session before snaps is populated.
    assert _run("return usedSubmaps(undefined, 1);") == []
    assert _run("return usedSubmaps(null, 1);") == []

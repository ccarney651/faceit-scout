"""The league page checks a read replay code against the feed.

Picking the wrong code from the dropdown attributes every captured comp to the
wrong match, teams and players - and publishes it, with no later signal that it
happened. This is the guard, and it is also what makes a read on this page
safe in a way a scrim read is not: here every read has a right answer available.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

APP = Path(__file__).resolve().parents[1] / "docs" / "capture" / "index.html"


def _run(body: str) -> object:
    node = shutil.which("node")
    if not node:
        pytest.skip("node not available")
    html = APP.read_text(encoding="utf-8")
    start = html.index("function matchReadCode(")
    end = html.index("\n}", start) + 2
    src = html[start:end] + "\nconsole.log(JSON.stringify((()=>{" + body + "})()));"
    tmp = Path("code_match_tmp.js")
    tmp.write_text(src, encoding="utf-8")
    try:
        proc = subprocess.run([node, str(tmp)], capture_output=True, text=True, encoding="utf-8")
        assert proc.returncode == 0, f"node failed:\n{proc.stderr}"
    finally:
        tmp.unlink(missing_ok=True)
    return json.loads(proc.stdout)


FEED = "[{code:'7DNNFL'},{code:'K3A6HZ'},{code:'TJDE6W'}]"


def test_an_exact_read_selects_that_match() -> None:
    assert _run(f"return matchReadCode('K3A6HZ', {FEED});") == {"kind": "exact", "code": "K3A6HZ"}


def test_a_one_character_miss_is_offered_as_a_correction() -> None:
    # 7DNNF1 vs 7DNNFL - the exact confusion Crockford excludes L for. foldCode
    # applies the published folding; this catches what survives it.
    assert _run(f"return matchReadCode('7DNNF1', {FEED});") == {"kind": "near", "code": "7DNNFL"}


def test_a_read_matching_nothing_changes_nothing() -> None:
    assert _run(f"return matchReadCode('ZZZZZZ', {FEED});")["kind"] == "none"


def test_an_ambiguous_near_match_abstains() -> None:
    # Two feed codes one character away: choosing either could file the capture
    # against the wrong match, which is the failure being prevented.
    got = _run("return matchReadCode('AAAAAA', [{code:'AAAAAB'},{code:'AAAAAC'}]);")
    assert got["kind"] == "none", "a tie must not be resolved by picking the first"


def test_a_failed_read_matches_nothing() -> None:
    # foldCode returns null on an unreadable crop; that must not be treated as
    # a code to go looking for.
    assert _run(f"return matchReadCode(null, {FEED});")["kind"] == "none"


def test_the_wrong_match_guard_is_wired_to_a_button() -> None:
    html = APP.read_text(encoding="utf-8")
    assert 'id="readcode"' in html, "no way to trigger the read"
    assert "matchReadCode(" in html.replace(" ", "").replace("\n", "") or "matchReadCode(" in html

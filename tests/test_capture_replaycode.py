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


ENGINE = APP.parent / "engine" / "replaycode.js"


def _run(body: str) -> object:
    """Run a snippet against the SHIPPED engine module.

    matchReadCode used to be lifted out of index.html by string surgery. It moved
    into engine/replaycode.js on 2026-09-08, where node:test can reach it without
    a browser, so this loads the real module rather than a slice of a page.
    """
    node = shutil.which("node")
    if not node:
        pytest.skip("node not available")
    mod = json.dumps(str(ENGINE).replace("\\", "/"))
    src = ("const R = require(" + mod + ");\n"
           "const matchReadCode = R.matchReadCode;\n"
           "const checkAgainstSelected = R.checkAgainstSelected;\n"
           "console.log(JSON.stringify((()=>{" + body + "})()));")
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


def test_the_wrong_match_guard_runs_on_the_first_snapshot() -> None:
    """The guard stopped being a button on 2026-09-08.

    The codes are fed to the operator, so there was never anything to look UP -
    what is worth checking is that the replay actually on screen is the match
    they picked. Asking for that by hand means it gets skipped exactly when it
    matters, so it runs on a map's first snapshot instead.
    """
    html = APP.read_text(encoding="utf-8")
    assert 'id="readcode"' not in html, "the manual button should be gone"
    assert "ensureCodeChecked()" in html, "the guard is not wired to anything"
    assert 'src="engine/replaycode.js"' in html, "the engine module is not loaded"


def test_the_guard_runs_before_every_other_check() -> None:
    """Order matters, and the operator settled it on 2026-09-08.

    Side detection reads the HUD names against the SELECTED match's roster, so on
    the wrong replay it cannot succeed - it either fails, sending the operator
    after a calibration fault that does not exist, or half-matches and teaches
    the map wrong names. "It will always fail if it's a code from the wrong game
    entirely." Every other check is equally meaningless on the wrong match, so
    the code question goes first.
    """
    html = APP.read_text(encoding="utf-8")
    body = html[html.index("async function snapshot("):]
    first = body.index("ensureCodeChecked()")
    for later in ("ensureSideResolved()", "pick a sub-map first"):
        assert first < body.index(later), f"the code check must precede {later}"


def test_the_guard_state_resets_with_the_map() -> None:
    """A verdict is about the replay on screen now, so it cannot outlive the map."""
    flat = APP.read_text(encoding="utf-8").replace(" ", "")
    assert "codeChecked:false" in flat
    assert "codeTries:0" in flat

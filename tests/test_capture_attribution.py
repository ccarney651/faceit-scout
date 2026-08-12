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
    """attribute()'s dependencies - normName/simScore/affinity and the
    AUTO_SIDE_MARGIN/STRONG_NAME_SCORE/MIN_STRONG_NAMES constants - moved to
    docs/capture/engine/names.js in the engine extraction, so they're loaded
    from the module now. The rest of the region attribute() needs
    (confidentLeft, rosterNames, attribute itself, ...) is still sliced
    straight out of index.html, just starting from confidentLeft instead of
    the now-deleted AUTO_SIDE_MARGIN declaration.
    """
    engine = (APP.parent / "engine" / "names.js").read_text(encoding="utf-8")
    html = APP.read_text(encoding="utf-8")
    start = html.index("function confidentLeft(")
    end = html.index("function setDetectMsg(")
    assert end > start, "extraction anchors moved in index.html"
    return "\n".join([
        "var module={exports:{}};",
        engine,
        "const {normName,simScore,affinity,AUTO_SIDE_MARGIN,STRONG_NAME_SCORE,MIN_STRONG_NAMES}=module.exports;",
        html[start:end],
    ])


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


# --- both names per player (Battle.net + FACEIT) -------------------------------
# The HUD renders the Battle.net name, which differs from the FACEIT nick for
# ~78% of league players. The native path always matched against both; the
# browser had drifted to game_name only, so the nick was never consulted.

# Shaped as teamRoster() now emits: `names` holds every alias for that player.
_DUAL = ("[{id:'p1',names:['Dip','Dip_impact']},"
         "{id:'p2',names:['aes','PRDZII']},"
         "{id:'p3',names:['gogo','GOGOOGOOO']}]")


def test_a_hud_read_matches_the_battletag() -> None:
    got = _run(f"return attribute(['Dip','aes','gogo'],{_DUAL});")
    assert got == ["p1", "p2", "p3", None, None]


def test_a_hud_read_matches_the_faceit_nick_too() -> None:
    # If the HUD happens to show the FACEIT handle (or the operator is reading a
    # scoreboard rather than the play HUD), the nick must still resolve.
    got = _run(f"return attribute(['Dip_impact','PRDZII','GOGOOGOOO'],{_DUAL});")
    assert got == ["p1", "p2", "p3", None, None]


def test_matching_only_the_primary_name_would_have_missed_these() -> None:
    # Guard against a regression back to single-name matching: "PRDZII" scores
    # essentially nothing against the battletag "aes", so a primary-name-only
    # implementation cannot resolve it.
    only_primary = "[{id:'p2',name:'aes'}]"
    assert _run(f"return attribute(['PRDZII'],{only_primary});") == [None] * 5
    assert _run(f"return attribute(['PRDZII'],{_DUAL});")[0] == "p2"


def test_accents_are_folded_before_comparing() -> None:
    # tessedit_char_whitelist is plain ASCII, so OCR can only ever emit "Hev"
    # for a HUD showing "Hev" with a macron - the roster name must still match.
    roster = "[{id:'p1',names:['H\\u0113v']}]"
    assert _run(f"return attribute(['Hev'],{roster});")[0] == "p1"
    # and the same in reverse (accented read, plain roster entry)
    roster2 = "[{id:'p1',names:['Hev']}]"
    assert _run(f"return attribute(['H\\u0113v'],{roster2});")[0] == "p1"

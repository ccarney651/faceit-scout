"""Browser capture app: process-of-elimination name attribution.

Extracts the pure attribute()/simScore() region from index.html (same
pattern as test_capture_attacker_gate.py) and runs it under Node.

The region also holds attributeSide(), the chooser between the role-constrained
resolver and the name-only matcher. Its `sidesKnown` argument is a safety gate,
not a refinement - see the tests at the bottom of this file.
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


# --- attributeSide: the role constraint must not run against the wrong team ---

_ASSIGN = Path(__file__).resolve().parents[1] / "docs" / "capture" / "engine" / "assign.js"

# One coded game, one match, both teams' five with roles - the shape gameLineup()
# reads out of the feed. Team t2's tank is the trap: with the sides backwards,
# the role constraint would force team t1's slot onto it with no name evidence.
_FEED = """
global.DATA={ lineups:{ 'm1:1':{
  t1:{players:[{id:'a-tank',nick:'AyzoOW',game_name:'ayzo',role:'Tank'},
               {id:'a-dps1',nick:'d1',game_name:'d1',role:'Damage'},
               {id:'a-dps2',nick:'d2',game_name:'d2',role:'Damage'},
               {id:'a-sup1',nick:'s1',game_name:'s1',role:'Support'},
               {id:'a-sup2',nick:'s2',game_name:'s2',role:'Support'}]},
  t2:{players:[{id:'b-tank',nick:'CP3_ow',game_name:'Faisal',role:'Tank'},
               {id:'b-dps1',nick:'e1',game_name:'e1',role:'Damage'},
               {id:'b-dps2',nick:'e2',game_name:'e2',role:'Damage'},
               {id:'b-sup1',nick:'f1',game_name:'f1',role:'Support'},
               {id:'b-sup2',nick:'f2',game_name:'f2',role:'Support'}]} } },
  rosters:{}, hero_roles:{ 'hazard':'Tank', 'ashe':'Damage', 'sojourn':'Damage',
                           'ana':'Support', 'kiriko':'Support' } };
global.selectedCode=()=>({match_id:'m1', game_no:1, t1:'t1', t2:'t2'});
global.CUSTOM_HEROES={};
global.OWDBAssign=require(%(assign)s);
const COMP={a:[{guid:'hazard'},{guid:'ashe'},{guid:'sojourn'},{guid:'ana'},{guid:'kiriko'}]};
const BLANK=['','','','',''];
"""


def _run_sides(body: str) -> object:
    node = shutil.which("node")
    if not node:
        pytest.skip("node not available to run the capture app's helpers")
    feed = _FEED % {"assign": json.dumps(str(_ASSIGN))}
    src = (_pure_js() + "\n" + feed
           + "\nconsole.log(JSON.stringify((()=>{" + body + "})()));")
    script = Path(__file__).resolve().parent / "_tmp_attribute_side_check.js"
    script.write_text(src, encoding="utf-8")
    try:
        proc = subprocess.run([node, str(script)], capture_output=True, text=True, timeout=20)
    finally:
        script.unlink(missing_ok=True)
    assert proc.returncode == 0, f"node failed:\n{proc.stderr}"
    return json.loads(proc.stdout)


def test_with_the_sides_known_the_tank_is_forced_with_no_name_evidence() -> None:
    # Every read is empty. Only one player on t1 can be the tank, so the slot
    # resolves anyway - this is the whole point of the role constraint.
    got = _run_sides("return attributeSide(BLANK,'t1',COMP,'a',true);")
    assert got["ids"][0] == "a-tank"
    assert got["conf"][0] == "forced"


def test_with_the_sides_unknown_nothing_is_forced() -> None:
    # Same reads, sides unconfirmed: fall back to names only, which has no
    # evidence and therefore tags nothing. Abstaining is the correct answer.
    got = _run_sides("return attributeSide(BLANK,'t1',COMP,'a',false);")
    assert got["ids"] == [None] * 5


def test_the_gate_is_what_stops_a_confident_wrong_team_tag() -> None:
    # The failure this gate exists for (real capture, 2026-08-18): the page had
    # left/right backwards, so side 'a' was scored against the OTHER team. With
    # the sides believed known, the role constraint hands the slot t2's tank -
    # a confident, wrong attribution built on no name evidence at all.
    wrong = _run_sides("return attributeSide(BLANK,'t2',COMP,'a',true);")
    assert wrong["ids"][0] == "b-tank", "expected the unguarded behaviour to mis-tag"
    # Below the gate the same call cannot invent it.
    guarded = _run_sides("return attributeSide(BLANK,'t2',COMP,'a',false);")
    assert guarded["ids"] == [None] * 5


def test_an_omitted_sidesknown_argument_is_treated_as_not_known() -> None:
    # Callers must pass it. If one forgets, the safe reading is "unknown".
    got = _run_sides("return attributeSide(BLANK,'t1',COMP,'a');")
    assert got["ids"] == [None] * 5

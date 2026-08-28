"""Browser capture app (scrims): map picker, screenshot import, auto-side detection.

Extracts pure helpers from docs/capture/scrim.html and runs them under Node.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

APP = Path(__file__).resolve().parents[1] / "docs" / "capture" / "scrim.html"


def _extract(*anchors: tuple[str, str]) -> str:
    html = APP.read_text(encoding="utf-8")
    parts = []
    for start_anchor, end_anchor in anchors:
        start = html.index(start_anchor)
        end = html.index(end_anchor, start)
        assert end > start, f"extraction anchor {end_anchor!r} moved in scrim.html"
        parts.append(html[start:end])
    return "\n".join(parts)


def _pure_js() -> str:
    """Cluster A: the map list. Cluster C: the screenshot-import parser.

    The roster-similarity helpers (formerly cluster B) moved to
    docs/capture/engine/names.js in the engine extraction; they are loaded
    from the module now rather than sliced out of the page. Cluster A's end
    anchor used to be the deleted block's own `const AUTO_SIDE_MARGIN=`
    declaration; since that text no longer exists in scrim.html, Cluster A
    now runs straight through to `detectScrimSides` (the same span it
    covered before, just without a mid-anchor split).
    """
    engine = (APP.parent / "engine" / "names.js").read_text(encoding="utf-8")
    return "\n".join([
        engine,
        "const {normName,simScore,affinity,confidentOrientation}=module.exports;",
        _extract(
            ("const CONTROL_SUBMAPS=", "async function detectScrimSides()"),
            ("function bestMapMatch(text)", "// The screenshot importer's UI is gone"),
        ),
    ])


# Minimal browser stubs so the extracted script can load in Node without the
# HAS_CAPTURE guard trying to touch real DOM APIs.
_STUBS = """
var window = {isSecureContext: true};
var navigator = {mediaDevices: {getDisplayMedia: function() {}}};
var document = {getElementById: function() { return null; }};
var module = {exports: {}};
"""


def _run(body: str) -> object:
    node = shutil.which("node")
    if not node:
        pytest.skip("node not available to run the capture app's helpers")
    src = _STUBS + _pure_js() + "\nconsole.log(JSON.stringify((()=>{" + body + "})()));"
    tmp = Path("scrim_test_tmp.js")
    tmp.write_text(src, encoding="utf-8")
    try:
        proc = subprocess.run([node, str(tmp)], capture_output=True, text=True)
        assert proc.returncode == 0, f"node failed:\n{proc.stderr}"
    finally:
        tmp.unlink(missing_ok=True)
    return json.loads(proc.stdout)


# ---------------------------------------------------------------------------
# Map picker
# ---------------------------------------------------------------------------


def test_scrim_maps_include_all_request_modes() -> None:
    """The mode dropdown must expose every competitively-played mode.

    Clash is deliberately absent - it is no longer played competitively, so it
    is noise in a scrim picker.
    """
    maps = _run("return SCRIM_MAPS;")
    modes = {m["cat"] for m in maps}
    assert modes == {"Control", "Escort", "Hybrid", "Push", "Flashpoint"}


def test_picking_a_mode_filters_to_its_maps() -> None:
    """Changing the mode keeps only that mode's maps selectable."""
    maps = _run("return SCRIM_MAPS;")
    control = [m["name"] for m in maps if m["cat"] == "Control"]
    escort = [m["name"] for m in maps if m["cat"] == "Escort"]
    assert "Ilios" in control and "King's Row" not in control
    assert "Dorado" in escort and "Ilios" not in escort


# ---------------------------------------------------------------------------
# Screenshot session import
# ---------------------------------------------------------------------------


def test_parse_scrim_session_text_extracts_map_code_result_score() -> None:
    lines = [
        "Ilios ABCD12 VICTORY | 11-2",
        "Lijiang Tower EFGH34 DEFEAT | 2-3",
        "Nepal IJKL56 | 1-1",
    ]
    rows = _run(f"return parseScrimSessionText({json.dumps(chr(10).join(lines))});")
    assert len(rows) == 3
    assert rows[0] == {"map_name": "Ilios", "map_category": "Control", "code": "ABCD12", "score": {"us": 11, "them": 2}, "result": "win"}
    assert rows[1] == {"map_name": "Lijiang Tower", "map_category": "Control", "code": "EFGH34", "score": {"us": 2, "them": 3}, "result": "loss"}
    assert rows[2] == {"map_name": "Nepal", "map_category": "Control", "code": "IJKL56", "score": {"us": 1, "them": 1}, "result": "draw"}


def test_parse_scrim_session_text_handles_ocr_noise_and_aliases() -> None:
    rows = _run("return parseScrimSessionText('Lijiang ABCD12 WIN | 3-0\\nantarctica EFGH00 LOSS 0-2');")
    assert len(rows) == 2
    assert rows[0]["map_name"] == "Lijiang Tower"
    assert rows[1]["map_name"] == "Antarctic Peninsula"


def test_parse_scrim_session_text_ignores_ui_words_like_review() -> None:
    rows = _run("return parseScrimSessionText('Circuit Royal REVIEW 7DNNF1\\nKing\\'s Row 7ONNFL');")
    assert len(rows) == 2
    assert rows[0]["code"] == "7DNNF1"
    assert rows[1]["code"] == "7ONNFL"


def test_parse_scrim_session_text_finds_code_map_pairs_without_scores() -> None:
    rows = _run("return parseScrimSessionText('Ilios ABCD12 VICTORY\\nno score here');")
    assert len(rows) == 1
    assert rows[0] == {"map_name": "Ilios", "map_category": "Control", "code": "ABCD12", "score": {"us": 0, "them": 0}, "result": "win"}


def test_parse_scrim_session_text_handles_overwatch_replay_history() -> None:
    text = (
        "< AK52A9\n"
        "SURAVASA 1 HOUR AGO - 15:01\n"
        "PHNG\n"
        "C/A KING'S ROW 2 HOURS AGO - 18:37\n"
        ". < 1s77F6 I\n"
        "I'% RUNASAPI 2 2 HOURS AGO - 10:06\n"
        "< 7DNNF1\n"
        "HiX CIRCUIT ROYAL EN i 2 HOURS AGO - 20:18 EER\n"
        "< E39856\n"
        "$e OASIS - a 3 HOURS AGO - 20:18"
    )
    rows = _run(f"return parseScrimSessionText({json.dumps(text)});")
    assert len(rows) == 5
    names = [r["map_name"] for r in rows]
    assert "Suravasa" in names
    assert "King's Row" in names
    assert "Runasapi" in names
    assert "Circuit Royal" in names
    assert "Oasis" in names
    codes = {r["code"] for r in rows if r["code"]}
    assert codes == {"AK52A9", "1S77F6", "7DNNF1", "E39856"}
    assert any(r["code"] is None for r in rows)  # King's Row code wasn't OCR'd


def test_parse_scrim_session_text_pairs_separate_result_score_lines() -> None:
    """When Overwatch's result/score column is read as a separate line, pair it with the nearest map."""
    text = (
        "Suravasa AKS2A9\n"
        "VICTORY | 11-2\n"
        "King's Row 3FPHN6\n"
        "VICTORY | 3-1\n"
        "Runasapi 1S77F6\n"
        "DEFEAT | 0-1\n"
        "Circuit Royal 7DNNF1\n"
        "DRAW | 3-3\n"
        "Oasis E39856\n"
        "DEFEAT | 1-2"
    )
    rows = _run(f"return parseScrimSessionText({json.dumps(text)});")
    assert len(rows) == 5
    assert rows[0] == {"map_name": "Suravasa", "map_category": "Flashpoint", "code": "AKS2A9", "score": {"us": 11, "them": 2}, "result": "win"}
    assert rows[1] == {"map_name": "King's Row", "map_category": "Hybrid", "code": "3FPHN6", "score": {"us": 3, "them": 1}, "result": "win"}
    assert rows[2] == {"map_name": "Runasapi", "map_category": "Push", "code": "1S77F6", "score": {"us": 0, "them": 1}, "result": "loss"}
    assert rows[3] == {"map_name": "Circuit Royal", "map_category": "Escort", "code": "7DNNF1", "score": {"us": 3, "them": 3}, "result": "draw"}
    assert rows[4] == {"map_name": "Oasis", "map_category": "Control", "code": "E39856", "score": {"us": 1, "them": 2}, "result": "loss"}


# ---------------------------------------------------------------------------
# Auto-side recognition
# ---------------------------------------------------------------------------


def test_auto_side_detects_us_on_left_when_rosters_match() -> None:
    our = ["Alison", "Sivaartt", "Kroxz", "Zorrow", "Benislover"]
    their = ["One", "Two", "Three", "Four", "Five"]
    got = _run(f"return confidentOrientation({json.dumps(our)}, {json.dumps(their)}, {json.dumps(our)}, {json.dumps(their)});")
    assert got == "a"


def test_auto_side_detects_them_on_left_when_sides_are_swapped() -> None:
    our = ["Alison", "Sivaartt", "Kroxz", "Zorrow", "Benislover"]
    their = ["One", "Two", "Three", "Four", "Five"]
    got = _run(f"return confidentOrientation({json.dumps(their)}, {json.dumps(our)}, {json.dumps(our)}, {json.dumps(their)});")
    assert got == "b"


def test_auto_side_returns_null_when_not_confident() -> None:
    our = ["Alison", "Sivaartt", "Kroxz", "Zorrow", "Benislover"]
    their = ["One", "Two", "Three", "Four", "Five"]
    strangers = ["X", "Y", "Z", "W", "Q"]
    got = _run(f"return confidentOrientation({json.dumps(strangers)}, {json.dumps(strangers)}, {json.dumps(our)}, {json.dumps(their)});")
    assert got is None


# ---------------------------------------------------------------------------
# Static page hygiene
# ---------------------------------------------------------------------------


def test_scrim_pages_are_gated_and_fail_closed() -> None:
    """Both scrim pages are locked to the public, and unlock only by script.

    These pages carried an unconditional full-screen #scrimpaused overlay
    (commit f2881cf) that no script removed; phase 1 deleted both so the
    feature could be built. It is now finished enough to merge but not to
    open, so the overlay is back - with a gate in front of it.

    The direction matters. The overlay is STATIC MARKUP and the gate script
    only ever removes it, so anything that goes wrong - a syntax error, a CSP
    block, a browser with localStorage disabled - leaves the page locked. A
    gate that added the overlay instead would fail open, and shipping an
    unfinished capture tool to everyone is the failure worth avoiding.
    """
    viewer = APP.parents[1] / "scrims.html"
    assert viewer.exists(), "docs/scrims.html moved — update this guard"
    gates = []
    for page in (APP, viewer):
        html = page.read_text(encoding="utf-8")
        assert 'id="scrimpaused"' in html, f"{page.name} lost the lock overlay"
        assert "Scrims are paused" in html, f"{page.name} lost the lock copy"
        start = html.index("// ---- scrim lock ----")
        gates.append(html[start:html.index("</script>", start)])
        body = html.index("<body")
        assert html.index('id="scrimpaused"') > body, "the overlay must be in the body"

    assert gates[0] == gates[1], "the two pages' gates have drifted apart"
    gate = gates[0]
    assert "removeAttribute" in gate or "remove()" in gate, (
        "the gate must REMOVE the overlay, never add it - see this test's docstring"
    )
    assert "scrimpaused" in gate

    # A failure inside the gate must not take the lock with it.
    assert "try" in gate and "catch" in gate, "a throwing gate must leave the page locked"



def test_scrim_page_loads_the_session_engine_module() -> None:
    """The league-code block must be reachable from the page, not just exist."""
    html = APP.read_text(encoding="utf-8")
    assert 'src="engine/session.js"' in html


def test_league_code_block_is_wired_into_every_code_entry_point() -> None:
    """The block is only real if it is CALLED. Loading the module is not enough.

    engine/session.js is unit-tested in isolation, and the test above only proves
    the <script> tag exists. Neither notices if the call sites are deleted - and
    without them a league match saves as a private scrim, invisibly, which is the
    exact failure the block exists to prevent. These assertions are anchored to
    the calls themselves for that reason.
    """
    html = APP.read_text(encoding="utf-8").replace(" ", "")
    # The invariant rather than a count: the page's own start path and the
    # screenshot importer are gone, so there is one start path today and
    # counting them would only have to be edited again next time. Anything
    # that begins capturing a map must ask first.
    starts = html.count("activeScrimMap={map_name:")
    assert starts >= 1, "no map start path found at all"
    assert html.count("if(awaitrefuseIfLeagueCode(") >= starts, (
        "a code entry point no longer calls refuseIfLeagueCode"
    )


def test_league_code_block_treats_an_unloaded_feed_as_unverifiable() -> None:
    """A failed data.json load must not read as 'this is not a league match'.

    CODE_INDEX starts empty, and an empty index classifies every code as a
    non-league one. So swallowing the fetch error fails OPEN: the block silently
    stops blocking. refuseIfLeagueCode must gate on feed readiness before it
    trusts a classification.
    """
    html = APP.read_text(encoding="utf-8").replace(" ", "")
    assert "CODE_FEED='failed'" in html, "the feed failure path no longer records state"
    assert "if(CODE_FEED!=='ready')" in html, (
        "refuseIfLeagueCode no longer checks feed readiness before classifying"
    )


def test_a_feed_that_loads_with_no_codes_is_also_unverifiable() -> None:
    """Zero codes must not read as 'this code is not a league match'.

    A feed that loads cleanly but carries no codes looks identical to one with
    no match for this code, and the consequences are opposite. CI publishes a
    populated feed; a local checkout ships an empty one. During verification a
    real league code was waved straight through for exactly this reason, so
    'loaded' is not sufficient - it has to carry codes to be trusted.
    """
    html = APP.read_text(encoding="utf-8").replace(" ", "")
    assert "CODE_INDEX.codes.size?'ready':'empty'" in html, (
        "an empty codes feed is being treated as authoritative again"
    )


def test_scrim_html_inline_script_is_syntactically_valid() -> None:
    """The entire scrim.html inline script must pass node --check."""
    node = shutil.which("node")
    if not node:
        pytest.skip("node not available")
    html = APP.read_text(encoding="utf-8")
    scripts = []
    import re
    for m in re.finditer(r"<script[^>]*>(.*?)</script>", html, re.DOTALL):
        if "src=" in m.group(0).split(">")[0]:
            continue
        scripts.append(m.group(1))
    js = "\n".join(scripts)
    assert js, "no inline script found in scrim.html"
    check = Path("scrim_inline_check.js")
    check.write_text(js, encoding="utf-8")
    try:
        proc = subprocess.run([node, "--check", str(check)], capture_output=True, text=True)
        assert proc.returncode == 0, f"node --check failed on scrim.html:\n{proc.stderr}"
    finally:
        check.unlink(missing_ok=True)


def test_league_capture_html_inline_script_is_syntactically_valid() -> None:
    """docs/capture/index.html inline script must pass node --check.

    The League capture app is a sibling of scrim.html and gets hand-edited just
    as often — a single JS syntax error blanks the whole capture tool, and a
    bracket-balance check won't catch it.
    """
    node = shutil.which("node")
    if not node:
        pytest.skip("node not available")
    path = APP.parent / "index.html"
    html = path.read_text(encoding="utf-8")
    scripts = []
    import re
    for m in re.finditer(r"<script[^>]*>(.*?)</script>", html, re.DOTALL):
        if "src=" in m.group(0).split(">")[0]:
            continue
        scripts.append(m.group(1))
    js = "\n".join(scripts)
    assert js, "no inline script found in index.html"
    check = Path("league_capture_inline_check.js")
    check.write_text(js, encoding="utf-8")
    try:
        proc = subprocess.run([node, "--check", str(check)], capture_output=True, text=True)
        assert proc.returncode == 0, f"node --check failed on index.html:\n{proc.stderr}"
    finally:
        check.unlink(missing_ok=True)


def test_scrims_html_script_is_syntactically_valid() -> None:
    """docs/scrims.html inline script must pass node --check."""
    node = shutil.which("node")
    if not node:
        pytest.skip("node not available")
    path = APP.parents[1] / "scrims.html"
    html = path.read_text(encoding="utf-8")
    scripts = []
    import re
    for m in re.finditer(r"<script[^>]*>(.*?)</script>", html, re.DOTALL):
        if "src=" in m.group(0).split(">")[0]:
            continue
        scripts.append(m.group(1))
    js = "\n".join(scripts)
    assert js, "no inline script found in scrims.html"
    check = Path("scrims_inline_check.js")
    check.write_text(js, encoding="utf-8")
    try:
        proc = subprocess.run([node, "--check", str(check)], capture_output=True, text=True)
        assert proc.returncode == 0, f"node --check failed on scrims.html:\n{proc.stderr}"
    finally:
        check.unlink(missing_ok=True)


def test_ui_modal_collects_textarea_fields() -> None:
    """scrim.html's OCR-import fallback edits raw text in a <textarea> inside a
    collect:true modal and reads it back via fields.rawocr. A collect selector
    without `textarea` makes that field permanently undefined and silently
    breaks the 'edit the OCR text and re-parse' recovery path - which is how it
    broke once during the engine extraction.
    """
    util = (APP.parent / "engine" / "util.js").read_text(encoding="utf-8")
    # Anchored to the call itself, not to the file's prose: an earlier version
    # of this guard matched the explanatory comment, so reverting the real
    # querySelectorAll still passed.
    assert "querySelectorAll('input,select,textarea')" in util.replace(" ", "")
    # scrim.html's own OCR-edit textarea went with the screenshot importer, but
    # index.html still edits raw OCR text this way and the selector is shared,
    # so the guard stays anchored to the module.
    idx = (APP.parent / "index.html").read_text(encoding="utf-8")
    assert "collect:true" in idx, "nothing collects modal fields any more - is this guard still needed?"


def test_capturing_never_waits_on_team_names() -> None:
    """Opening the scrim tool means a scrim block is already in progress.

    The page used to refuse to start a map until a scrim had been created with
    at least one team name typed in - which the operator hit immediately as
    "clunky to set up". Team names are metadata (phase 2 resolves the opponent
    off the HUD anyway) and must never stand between someone and their first
    Snapshot. The design says as much: nothing here blocks capture.
    """
    html = APP.read_text(encoding="utf-8")
    assert "create / pick a scrim first" not in html, (
        "starting a map refuses again until a scrim is created by hand"
    )
    assert "enter Our team and Opponent first" not in html, (
        "importing or starting a session demands team names again"
    )
    assert "async function ensureScrim()" in html, (
        "ensureScrim() is what creates the block implicitly - it is gone"
    )
    # Every entry point into capture must go through it. One path today, but
    # tied to the count of start paths so a new one cannot skip it.
    flat = html.replace(" ", "")
    assert flat.count("awaitensureScrim();") >= flat.count("activeScrimMap={map_name:"), (
        "a capture entry point no longer creates the scrim block implicitly"
    )


def test_an_unnamed_scrim_block_is_not_labelled_as_a_team() -> None:
    """A block with no names must read as a date, not as 'us vs opponent'.

    Filling blanks with those placeholders makes an unnamed block
    indistinguishable from a scrim against a team genuinely called that, and
    the placeholder then gets stored on every map record.
    """
    html = APP.read_text(encoding="utf-8")
    assert "function scrimLabel(s)" in html
    assert "esc(scrimLabel(s))" in html, "the picker no longer uses scrimLabel"


def test_fix_reads_opens_the_panel_it_fills() -> None:
    """Filling a collapsed <details> looks identical to a dead button.

    #refpanel sits inside <details id="herocard">, which starts closed.
    fixReads() populated it correctly but never opened the section, so
    clicking "Fix current reads" appeared to do nothing - which is how the
    operator reported "teach it a miss" as broken on 2026-08-13. Pre-existing:
    no version of either page ever opened it.
    """
    for page in (APP, APP.parent / "index.html"):
        html = page.read_text(encoding="utf-8")
        assert 'id="herocard"' in html, f"{page.name}: the hero card moved"
        body = html[html.index("function fixReads("):][:600]
        assert "herocard" in body and ".open=true" in body.replace(" ", ""), (
            f"{page.name}: fixReads no longer opens the panel it fills"
        )


def test_hero_bans_are_optional_per_scrim() -> None:
    """Some teams scrim with hero bans and some do not.

    A ban control on a scrim that never bans is noise, so it is off by default
    and the setting lives on the scrim record rather than being global.
    """
    html = APP.read_text(encoding="utf-8")
    assert 'id="scbans"' in html, "no per-scrim bans toggle"
    # The control itself lives in the pop-out panel now - see
    # test_the_panel_offers_the_ban_picker_between_maps.
    assert "{id:'prow-bans'" in html, "no ban control"
    assert "uses_bans" in html, "the toggle is not persisted on the scrim"
    assert "function usesBans()" in html


def test_bans_are_recorded_per_map_not_per_scrim() -> None:
    """A block can start banning partway through, and "what shifted when this
    hero was banned" is a per-map question.

    The reset moved: it used to happen when a map STARTED, which was safe only
    while bans were entered mid-map. They are picked before Start now, so the
    reset happens when a map finishes instead - see
    test_starting_a_map_keeps_the_bans_chosen_for_it.
    """
    html = APP.read_text(encoding="utf-8").replace(" ", "")
    assert "...banState()" in html, "bans are not saved onto the map record"
    assert "clearBans();" in html, "MAP_BANS is never reset between maps"


# ---------------------------------------------------------------------------
# Hero bans: the markup is shared by the setup card and the capture overlay
# ---------------------------------------------------------------------------
# The overlay is a SEPARATE DOCUMENT (a popped-out window), so the ban chips
# cannot be built by a function that reaches for elements by id on the main
# page. banChipsHtml() is the pure half, rendered into whichever container the
# caller owns.


def _bans_js() -> str:
    """banChipsHtml plus the two helpers it closes over, which the page gets
    from engine/util.js and engine/refs.js and this test stubs."""
    return "\n".join([
        "function esc(s){return String(s==null?'':s)"
        ".replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;')"
        ".replace(/\"/g,'&quot;');}",
        "var HERO_NAMES={'0x01':'Sombra'};",
        "function heroName(g){return HERO_NAMES[g]||'';}",
        _extract(("function banChipsHtml(", "function renderBans()")),
    ])


def _run_bans(body: str) -> object:
    node = shutil.which("node")
    if not node:
        pytest.skip("node not available to run the capture app's helpers")
    src = _bans_js() + "\nconsole.log(JSON.stringify((()=>{" + body + "})()));"
    tmp = Path("scrim_bans_test_tmp.js")
    tmp.write_text(src, encoding="utf-8")
    try:
        proc = subprocess.run([node, str(tmp)], capture_output=True, text=True)
        assert proc.returncode == 0, f"node failed:\n{proc.stderr}"
    finally:
        tmp.unlink(missing_ok=True)
    return json.loads(proc.stdout)


def test_no_bans_renders_an_empty_state_not_an_empty_string() -> None:
    # An empty container would read as "the control is broken"; the operator
    # needs to see that nothing has been recorded yet.
    html = _run_bans("return banChipsHtml([]);")
    assert "none recorded" in html


def test_each_ban_renders_a_chip_with_a_remove_control() -> None:
    html = _run_bans("return banChipsHtml([{g:'0x01',n:'Sombra'},{g:'0x02',n:'Ana'}]);")
    assert html.count("banx") == 2, "one remove control per ban"
    assert 'data-i="0"' in html and 'data-i="1"' in html, "removal is by index"
    assert "Sombra" in html and "Ana" in html


def test_a_ban_falls_back_to_the_hero_catalogue_when_it_carries_no_name() -> None:
    html = _run_bans("return banChipsHtml([{g:'0x01'}]);")
    assert "Sombra" in html


def test_who_banned_it_is_shown_only_when_recorded() -> None:
    with_by = _run_bans("return banChipsHtml([{g:'0x01',n:'Sombra',by:'them'}]);")
    without = _run_bans("return banChipsHtml([{g:'0x01',n:'Sombra'}]);")
    assert "them" in with_by
    assert "faint" not in without, "no by-tag when nobody recorded who banned it"


def test_hero_names_are_escaped() -> None:
    # Learned hero names are operator-typed, and this markup is injected with
    # innerHTML into two documents.
    html = _run_bans("return banChipsHtml([{g:'x',n:'<img src=x onerror=1>'}]);")
    assert "<img" not in html and "&lt;img" in html


# The panel row itself. The operator asked for ban entry beside the map picker,
# because during a scrim they are looking at the panel, not the page.

_ROW_STUBS = """
var CALLS=[];
function esc(s){return String(s==null?'':s);}
function heroCatalog(){ return [{g:'0x01',n:'Sombra'},{g:'0x02',n:'Ana'}]; }
function heroName(g){ return ({'0x01':'Sombra','0x02':'Ana'})[g]||''; }
var MAP_BANS=[], session=null, SCRIM={uses_bans:false};
function usesBans(){ return !!SCRIM.uses_bans; }
function renderBans(){ CALLS.push('renderBans'); }
function renderBansInto(box){ box.__chips=true; }
function renderBanPickerInto(box,doc){ box.__picker=true; }
function el(tag){ return { tagName:tag, className:'', innerHTML:'', textContent:'', value:'',
  children:[], style:{}, appendChild:function(c){ this.children.push(c); return c; },
  querySelectorAll:function(){ return []; } }; }
var d={ createElement:el };
var mk=function(p,t,fn,cls){ var b=el('button'); b.textContent=t; b.onclick=fn; p.appendChild(b); return b; };
function descend(node, out){ out=out||[]; (node.children||[]).forEach(function(c){ out.push(c); descend(c,out); }); return out; }
"""


def _run_row(body: str) -> object:
    node = shutil.which("node")
    if not node:
        pytest.skip("node not available to run the capture app's helpers")
    row = _extract(("{id:'prow-bans'", "{id:'prow-atk'"))
    src = (_ROW_STUBS + "\nvar ROW=" + row.rstrip().rstrip(",") + ";\n"
           + "console.log(JSON.stringify((()=>{" + body + "})()));")
    tmp = Path("scrim_row_test_tmp.js")
    tmp.write_text(src, encoding="utf-8")
    try:
        proc = subprocess.run([node, str(tmp)], capture_output=True, text=True)
        assert proc.returncode == 0, f"node failed:\n{proc.stderr}"
    finally:
        tmp.unlink(missing_ok=True)
    return json.loads(proc.stdout)


def test_the_panel_has_no_ban_row_when_the_scrim_does_not_use_bans() -> None:
    # Most scrims do not ban. A control for something the block never does is
    # noise on a panel that sits on top of the game.
    kids = _run_row("""
      var row=el('div'); SCRIM.uses_bans=false; session=null;
      ROW.render(row,d,mk); return descend(row).length;""")
    assert kids == 0


def test_the_panel_offers_the_ban_picker_between_maps() -> None:
    # Inverted from what this row used to do. Bans are settled during draft -
    # before the map starts - so the pre-map screen is the only moment the
    # control is any use. It used to appear only once the map was running,
    # which is after the draft it was meant to record.
    got = _run_row("""
      var row=el('div'); SCRIM.uses_bans=true; session=null;
      ROW.render(row,d,mk);
      return !!row.__picker;""")
    assert got is True, "the pre-map panel must carry the ban picker"


def test_the_panel_hides_the_ban_picker_while_a_map_runs() -> None:
    # By then the draft is over, and the panel needs its space for the two
    # team read-outs.
    kids = _run_row("""
      var row=el('div'); SCRIM.uses_bans=true; session={};
      ROW.render(row,d,mk); return descend(row).length;""")
    assert kids == 0


def test_every_panel_row_has_somewhere_to_render() -> None:
    """A row in `controls` whose id is missing from `middleHtml` never renders.

    renderPipControls() looks each id up in the panel document and skips the
    ones it cannot find (`if (el) row.render(...)`), so the row is simply
    absent with no error anywhere. This was a real miss when the bans row was
    added.
    """
    import re
    html = APP.read_text(encoding="utf-8")
    declared = set(re.findall(r"\{id:'(prow-[a-z]+)'", html))
    # Two slots, not one: popout() concatenates middleHtml and finishHtml, and
    # scrim.html puts its Finish row in the second.
    slots = re.findall(r"(?:middleHtml|finishHtml):'([^']*)'", html)
    assert slots, "middleHtml/finishHtml moved in scrim.html"
    present = set(re.findall(r'id="(prow-[a-z]+)"', " ".join(slots)))
    assert declared, "no panel rows found - the controls list moved"
    assert declared <= present, (
        f"panel rows with nowhere to render: {sorted(declared - present)}"
    )


# ---------------------------------------------------------------------------
# Knowing which side is us
# ---------------------------------------------------------------------------
# ourSide() in engine/opponents.js matches the HUD against our own roster and
# returns null the moment that roster is empty. In the field it was ALWAYS
# empty: the scrim carried no "Our team", and the remembered-team store had no
# writer at all, so side detection could never fire. These cover the two ways
# we now know who we are.

_US_STUBS = """
var STORE={};
var localStorage={ getItem:function(k){ return k in STORE?STORE[k]:null; },
                   setItem:function(k,v){ STORE[k]=String(v); },
                   removeItem:function(k){ delete STORE[k]; } };
var FEED={ vertex:['GCB','KHALED','XYPHER','ASHBORN','NUT'] };
function faceitRoster(name){ return FEED[(name||'').trim().toLowerCase()]||[]; }
var activeScrim=null;
"""


def _run_us(body: str) -> object:
    node = shutil.which("node")
    if not node:
        pytest.skip("node not available to run the capture app's helpers")
    src = (_US_STUBS + _extract(("const OUR_TEAM_KEY=", "const ALIAS_KEY="))
           + "\nconsole.log(JSON.stringify((()=>{" + body + "})()));")
    tmp = Path("scrim_us_test_tmp.js")
    tmp.write_text(src, encoding="utf-8")
    try:
        proc = subprocess.run([node, str(tmp)], capture_output=True, text=True)
        assert proc.returncode == 0, f"node failed:\n{proc.stderr}"
    finally:
        tmp.unlink(missing_ok=True)
    return json.loads(proc.stdout)


def test_with_no_team_named_anywhere_we_admit_we_do_not_know_who_we_are() -> None:
    # The field failure. An empty roster must stay empty rather than become
    # some default - ourSide() then abstains and the operator sets it by hand.
    assert _run_us("return ourRosterNames();") == []


def test_the_scrims_own_team_field_is_enough_to_know_us() -> None:
    names = _run_us("activeScrim={team_us:'Vertex'}; return ourRosterNames();")
    assert "GCB" in names and len(names) == 5


def test_our_team_is_remembered_across_scrims() -> None:
    # Typing it into one scrim must be the last time it is typed. The next
    # scrim starts blank and must still resolve.
    names = _run_us("""
        rememberOurTeam('Vertex');
        activeScrim={team_us:''};
        return ourRosterNames();""")
    assert "GCB" in names


def test_names_learned_from_a_manual_side_pick_count_as_us() -> None:
    # The case the league feed cannot cover: a stand-in, a smurf, or a team
    # that is not in the league at all.
    names = _run_us("""
        rememberOurTeam('Vertex');
        learnOurRoster(['GCB','KHALED','StandInSmurf']);
        return ourRosterNames();""")
    assert "StandInSmurf" in names, "a learned name must widen who counts as us"
    assert "XYPHER" in names, "and must not replace the roster we already had"


def test_a_team_outside_the_league_can_still_be_learned() -> None:
    names = _run_us("""
        learnOurRoster(['GROKA','OTAKAW','JJUUZOU','CHEESEBURGER','OIDOPUAA']);
        return ourRosterNames();""")
    assert len(names) == 5, "no feed entry, but five confirmed names is still a roster"


def test_learning_accumulates_and_never_duplicates() -> None:
    names = _run_us("""
        learnOurRoster(['GCB','KHALED']);
        learnOurRoster(['KHALED','NEWSTANDIN']);
        return ourRosterNames();""")
    assert sorted(names) == ["GCB", "KHALED", "NEWSTANDIN"]


# Learning happens when a map is FINISHED, not when the side radio changes.
# On change would be worse than useless: a swap would teach it the opposing
# five as well, both sides would then match "us", and ourSide() - which
# refuses to guess when both overlap - would abstain forever.


def test_our_names_come_from_the_side_the_operator_marked_as_ours() -> None:
    snaps = ("[{aPlayers:['GCB','KHALED'],bPlayers:['GROKA','OTAKAW']}]")
    left_us = _run_us(f"return ourNamesFromSnaps({snaps},'us');")
    left_them = _run_us(f"return ourNamesFromSnaps({snaps},'them');")
    assert left_us == ["GCB", "KHALED"]
    assert left_them == ["GROKA", "OTAKAW"], "'them' on the left means we are on the right"


def test_nothing_is_learned_while_the_sides_are_unconfirmed() -> None:
    # Learning the wrong five is not a small error: both sides then match us
    # and ourSide() abstains forever after.
    snaps = "[{aPlayers:['GCB'],bPlayers:['GROKA']}]"
    assert _run_us(f"return ourNamesFromSnaps({snaps},'');") == []


def test_names_are_gathered_across_every_snapshot_of_the_map() -> None:
    # A substitution mid-map means the five are not the same in every snapshot.
    snaps = ("[{aPlayers:['GCB','KHALED']},{aPlayers:['GCB','SUBBED_IN']}]")
    assert _run_us(f"return ourNamesFromSnaps({snaps},'us');") == ["GCB", "KHALED", "SUBBED_IN"]


def test_unattributed_slots_are_skipped() -> None:
    snaps = "[{aPlayers:['GCB',null,'',undefined,'KHALED']}]"
    assert _run_us(f"return ourNamesFromSnaps({snaps},'us');") == ["GCB", "KHALED"]


def test_the_failure_message_says_we_do_not_know_who_you_are() -> None:
    # The old message ("pick the left team above, then Snapshot again") said
    # what to do but never what was wrong - and the wrong thing was almost
    # always that nothing had told the tool which team is ours.
    hint = _run_us("return sideFailureHint(false);")
    assert "Our team" in hint, "name the field that fixes it"
    assert "remember" in hint.lower(), "and say it only has to be done once"


def test_a_different_message_when_we_know_who_we_are_and_still_cannot_tell() -> None:
    # Different cause, different fix: the roster is known, so this is a bad
    # OCR read or a stand-in, and re-reading may well work.
    hint = _run_us("return sideFailureHint(true);")
    assert "Our team" not in hint
    assert hint != _run_us("return sideFailureHint(false);")


def test_a_new_scrim_starts_with_the_team_we_already_know_is_ours() -> None:
    # Typed once, never again: an auto-created scrim inherits the remembered
    # team so side detection works on its very first map.
    assert _run_us("rememberOurTeam('Vertex'); return newScrimTeamUs();") == "Vertex"


def test_a_new_scrim_is_blank_when_nothing_is_remembered_yet() -> None:
    assert _run_us("return newScrimTeamUs();") == ""


def test_the_form_prefills_our_team_for_a_brand_new_scrim() -> None:
    # Picking "+ new scrim…" clears the form. It must not clear the one field
    # we already know the answer to - that was the field-reported bug.
    assert _run_us("rememberOurTeam('Vertex'); return scrimFormTeamUs(null);") == "Vertex"
    assert _run_us("rememberOurTeam('Vertex'); return scrimFormTeamUs({});") == "Vertex"


def test_an_existing_scrims_own_team_is_never_overridden_by_the_remembered_one() -> None:
    # Scrims played as a different team, or an older scrim named before the
    # team was remembered, must keep what they were saved with.
    got = _run_us("rememberOurTeam('Vertex'); return scrimFormTeamUs({team_us:'Some Other Team'});")
    assert got == "Some Other Team"


def test_the_form_stays_blank_when_no_team_is_remembered() -> None:
    assert _run_us("return scrimFormTeamUs(null);") == ""


# ---------------------------------------------------------------------------
# Which teams the page knows about
# ---------------------------------------------------------------------------
# The page built its team list and roster lookup from `rosters` alone, which is
# per CODED MATCH: 19 teams against the 159 in `team_rosters`. That is why the
# autocomplete offered no Master-division teams, and why faceitRoster() could
# not find a team that had not played a coded match - including, in the field,
# the operator's own.

_FEED_FIXTURE = """{
  team_rosters:{
    t1:{name:'Vertex', players:[{game_name:'gcb'},{nick:'Xypher'}]},
    t2:{name:'Master Div Team', players:[{game_name:'someone'}]}
  },
  rosters:{ 'm1':{ t3:{name:'Coded Only', players:[{game_name:'coded'}]} } },
  codes:[{team_a:'Coded Only', team_b:'Named In Codes'}]
}"""


def _run_feed(body: str) -> object:
    node = shutil.which("node")
    if not node:
        pytest.skip("node not available to run the capture app's helpers")
    src = (_extract(("function indexLeagueTeams(", "async function loadTeamNames("))
           + "\nconsole.log(JSON.stringify((()=>{" + body + "})()));")
    tmp = Path("scrim_feed_test_tmp.js")
    tmp.write_text(src, encoding="utf-8")
    try:
        proc = subprocess.run([node, str(tmp)], capture_output=True, text=True)
        assert proc.returncode == 0, f"node failed:\n{proc.stderr}"
    finally:
        tmp.unlink(missing_ok=True)
    return json.loads(proc.stdout)


def test_every_team_in_the_league_is_offered_not_just_the_coded_ones() -> None:
    names = _run_feed(f"return indexLeagueTeams({_FEED_FIXTURE}).names;")
    assert "Master Div Team" in names, "a team with no coded match is still a real team"
    assert "Vertex" in names


def test_teams_reachable_only_through_a_coded_match_are_kept() -> None:
    # Older feeds carry no team_rosters at all; dropping this would trade one
    # regression for another.
    names = _run_feed(f"return indexLeagueTeams({_FEED_FIXTURE}).names;")
    assert "Coded Only" in names


def test_a_team_named_only_in_the_code_list_is_still_offered() -> None:
    names = _run_feed(f"return indexLeagueTeams({_FEED_FIXTURE}).names;")
    assert "Named In Codes" in names


def test_the_roster_lookup_finds_a_team_that_never_played_a_coded_match() -> None:
    # This is the side-detection half: ourSide() needs a roster for our team,
    # and ours had no coded match.
    roster = _run_feed(f"return indexLeagueTeams({_FEED_FIXTURE}).rosters['vertex'];")
    assert roster and [p.get("game_name") or p.get("nick") for p in roster["players"]] == ["gcb", "Xypher"]


def test_the_roster_lookup_is_case_insensitive() -> None:
    assert _run_feed(f"return !!indexLeagueTeams({_FEED_FIXTURE}).rosters['master div team'];")


def test_teams_are_listed_once_and_sorted() -> None:
    names = _run_feed(f"return indexLeagueTeams({_FEED_FIXTURE}).names;")
    assert names == sorted(set(names)), "duplicates or unsorted names in the picker"


# --- who is on which hero -------------------------------------------------
# The panel read the ten HUD names all along and then threw them away at the
# last step, printing a hardcoded em-dash in every Player cell. These cover the
# helper that decides what a slot says.

def _run_label(body: str) -> object:
    node = shutil.which("node")
    if not node:
        pytest.skip("node not available to run the capture app's helpers")
    engine = (APP.parent / "engine" / "opponents.js").read_text(encoding="utf-8")
    src = (engine + "\nvar OWDBOpponents=module.exports;\n" + _US_STUBS
           + _extract(("const OUR_TEAM_KEY=", "const ALIAS_KEY="))
           + "\nconsole.log(JSON.stringify((()=>{" + body + "})()));")
    tmp = Path("scrim_label_test_tmp.js")
    tmp.write_text(src, encoding="utf-8")
    try:
        # encoding= explicitly: the fixtures here carry the punctuation OCR
        # invents around a name plate, which the Windows default codepage
        # mangles on the way back out of node.
        proc = subprocess.run([node, str(tmp)], capture_output=True, text=True, encoding="utf-8")
        assert proc.returncode == 0, f"node failed:\n{proc.stderr}"
    finally:
        tmp.unlink(missing_ok=True)
    return json.loads(proc.stdout)


def test_a_slot_shows_the_name_that_was_read_for_it() -> None:
    # No roster in play at all: the read itself is the answer. Showing nothing
    # because we cannot vouch for it is how this cell ended up blank.
    assert _run_label("return slotPlayerLabel('SYNEX', []);") == "SYNEX"


def test_a_read_that_matches_a_roster_shows_the_rosters_spelling() -> None:
    # "i XYPHER |" is a real read - the stray glyphs are plate edges. It is
    # matched exactly the way identification matches it, so what the panel
    # shows agrees with who the tool decided we are playing.
    assert _run_label("return slotPlayerLabel('i XYPHER |', ['GCB','XYPHER']);") == "XYPHER"


def test_a_slot_nothing_could_be_read_for_stays_blank() -> None:
    # Blank means "no name", and must not be dressed up as one.
    assert _run_label("return slotPlayerLabel('', ['GCB']);") == ""
    assert _run_label("return slotPlayerLabel(null, ['GCB']);") == ""


def test_an_unrecognised_read_is_shown_as_read_not_dropped() -> None:
    # The opponent is usually a mix with no roster anywhere. Their names are
    # still the whole point of the column.
    assert _run_label("return slotPlayerLabel('§ ASHBORN |}', ['GCB']);") == "§ ASHBORN |}"


def test_the_panel_no_longer_hardcodes_an_em_dash_in_the_player_cell() -> None:
    # The bug itself: readComp populated session.players, saved it per
    # snapshot, paired it into the finished map - and printed a literal dash.
    row = _extract(("function readComp(bx)", "// refTemplate/addRef/learnCrop"))
    assert '<span class="cn pn">\u2014</span>' not in row, "the Player cell is hardcoded again"
    assert "slotPlayerLabel(" in row, "readComp must ask what the slot's player is called"


# --- the panel's ban picker ------------------------------------------------
# The dropdown was replaced by a role-grouped grid of portraits, in the panel,
# on the pre-map screen: bans are settled during draft, and the panel is where
# the operator already is.

_BANGRID_STUBS = """
function esc(s){ return (s==null?'':String(s)).replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c])); }
function heroPortrait(n){ return '<img alt="'+esc(n)+'">'; }
function heroName(g){ return ({r:'Reinhardt',g:'Genji',a:'Ana'})[g]||g; }
var HEROES=[{g:'r',n:'Reinhardt'},{g:'g',n:'Genji'},{g:'a',n:'Ana'}];
function heroCatalog(){ return HEROES; }
"""


def _run_bangrid(body: str) -> object:
    node = shutil.which("node")
    if not node:
        pytest.skip("node not available to run the capture app's helpers")
    engine = (APP.parent / "engine" / "heroes.js").read_text(encoding="utf-8")
    src = (engine + "\nvar OWDBHeroes=module.exports;\n" + _BANGRID_STUBS
           + _extract(("// ---------- hero bans ----------", "// scrimLabel():"))
           + "\nconsole.log(JSON.stringify((()=>{" + body + "})()));")
    tmp = Path("scrim_bans_test_tmp.js")
    tmp.write_text(src, encoding="utf-8")
    try:
        proc = subprocess.run([node, str(tmp)], capture_output=True, text=True, encoding="utf-8")
        assert proc.returncode == 0, f"node failed:\n{proc.stderr}"
    finally:
        tmp.unlink(missing_ok=True)
    return json.loads(proc.stdout)


def test_clicking_a_hero_bans_it() -> None:
    assert _run_bangrid("return withBanToggled([], 'r', 'Reinhardt', null);") == [
        {"g": "r", "n": "Reinhardt", "by": None}]


def test_clicking_a_banned_hero_again_unbans_it() -> None:
    # A grid of buttons has no "remove" affordance of its own, so the button
    # itself has to be the undo - otherwise a misclick is only fixable from
    # the chip row.
    assert _run_bangrid("""
        const one=withBanToggled([], 'r', 'Reinhardt', null);
        return withBanToggled(one, 'r', 'Reinhardt', null);""") == []


def test_a_ban_records_who_made_it() -> None:
    assert _run_bangrid("return withBanToggled([], 'g', 'Genji', 'them');")[0]["by"] == "them"


def test_the_grid_is_grouped_by_role_in_play_order() -> None:
    html = _run_bangrid("return banGridHtml(heroCatalog(), []);")
    assert html.index("Tank") < html.index("Damage") < html.index("Support")


def test_the_grid_marks_what_is_already_banned() -> None:
    # The panel is glanced at, not read. Which heroes are gone has to be
    # visible in the grid itself, not only in the chip list under it.
    html = _run_bangrid("return banGridHtml(heroCatalog(), [{g:'g',n:'Genji'}]);")
    banned = [ln for ln in html.split("<button") if 'data-g="g"' in ln]
    assert banned and "banned" in banned[0], "a banned hero must be marked in the grid"
    other = [ln for ln in html.split("<button") if 'data-g="r"' in ln]
    assert other and "banned" not in other[0]


def test_no_bans_this_map_is_a_fact_not_an_empty_list() -> None:
    # An empty ban list means "nobody recorded any". "We played this map with
    # no bans" is different evidence and the viewer counts it differently.
    assert _run_bangrid("MAP_BANS=[]; MAP_BANS_NONE=false; return banState();") == {"bans": [], "no_bans": False}
    assert _run_bangrid("setNoBans(); return banState();") == {"bans": [], "no_bans": True}


def test_banning_a_hero_cancels_no_bans() -> None:
    assert _run_bangrid("""
        setNoBans();
        MAP_BANS=withBanToggled(MAP_BANS,'r','Reinhardt',null); MAP_BANS_NONE=false;
        return banState();""") == {"bans": [{"g": "r", "n": "Reinhardt", "by": None}], "no_bans": False}


def test_starting_a_map_keeps_the_bans_chosen_for_it() -> None:
    # The whole point of moving the picker to the pre-map screen. All three
    # map-start paths used to clear MAP_BANS, which would have eaten the input
    # the moment Start was pressed.
    html = APP.read_text(encoding="utf-8")
    assigns = html.count("MAP_BANS=[]")
    assert assigns == 2, (
        "MAP_BANS is emptied somewhere other than setNoBans/clearBans - "
        "a map start path is eating the bans picked before it")


def test_a_ban_can_record_who_banned_it() -> None:
    # The by-us/by-them picker applies to the next hero clicked, so it is set
    # once for a whole draft rather than per ban.
    assert _run_bangrid("return withBanToggled([], 'g', 'Genji', 'us');")[0]["by"] == "us"


def test_the_panel_shows_the_ban_picker_not_a_dropdown() -> None:
    row = _extract(("{id:'prow-bans'", "{id:'prow-atk'"))
    assert "renderBanPickerInto(" in row, "the panel must render the shared picker"
    assert "<option" not in row, "the 53-entry dropdown is what the grid replaced"


def test_the_panel_can_close_out_a_scrim_only_between_maps() -> None:
    # Not a refusal with a toast: the button is simply not rendered while a
    # map is being captured, so there is nothing to decline.
    row = _extract(("{id:'prow-endscrim'", "{id:'prow-finish'"))
    compact = "".join(row.split())
    assert "if(session||!activeScrim||!SCRIM_MAP_COUNT)return;" in compact, (
        "finish-scrim must not render while a map is being captured")


def test_closing_a_scrims_capture_leaves_the_scrim_editable() -> None:
    # "Finish scrim capture" ends the capture session, it does not seal the
    # record - the scrim stays in the picker and can be added to later.
    src = _extract(("async function endScrimCapture()", "// scrimDate():"))
    assert "owdb_cap_scrim" in src, "closing capture must drop the active-scrim pointer"
    assert "idbPutScrim" not in src and "void" not in src, (
        "closing capture must not write a finished/void flag onto the scrim")


def test_every_hero_in_the_grid_is_named_under_its_portrait() -> None:
    # Portraits alone are recognisable for the heroes you play and guesswork
    # for the rest, and a ban is entered under time pressure during a draft.
    html = _run_bangrid("return banGridHtml([{g:'r',n:'Reinhardt'}], []);")
    assert ">Reinhardt<" in html, "the name must be text under the tile, not just alt text"


def test_a_hero_with_no_portrait_still_occupies_a_full_tile() -> None:
    # hero_icons.json is optional and can lag a new hero. Without a stand-in
    # for the image the tile would collapse to its name and break the grid.
    html = _run_bangrid("""
        heroPortrait=function(){ return ''; };
        return banGridHtml([{g:'x',n:'Nohero'}], []);""")
    assert ">Nohero<" in html
    assert "banph" in html, "a portrait-less hero needs a placeholder the size of a portrait"


def test_the_ban_grid_tiles_are_a_fixed_size() -> None:
    # The panel is resizable, and fractional columns made the portraits grow
    # with it - a hero select the size of the window is harder to scan, not
    # easier. Fixed tiles reflow into more columns instead of inflating.
    import re
    css = APP.read_text(encoding="utf-8").replace(" ", "")
    assert "repeat(6,1fr)" not in css, "ban tiles stretch with the panel again"
    cols = re.findall(r"grid-template-columns:repeat\(auto-fill,(\d+)px\)", css)
    assert len(cols) == 2, "both stylesheets must set a fixed tile width"


def test_the_panel_tiles_are_smaller_than_the_pages() -> None:
    # The panel sits on top of the game and is read at a glance between maps;
    # the page card has a whole browser window to spend. Same grid, denser
    # where space is scarce - which is why the parity check compares selector
    # sets rather than values.
    import re
    css = APP.read_text(encoding="utf-8").replace(" ", "")
    page, panel = re.findall(r"grid-template-columns:repeat\(auto-fill,(\d+)px\)", css)
    assert int(panel) < int(page), "the panel's ban tiles are no denser than the page's"


def test_the_ban_grid_is_styled_on_the_page_as_well_as_the_panel() -> None:
    # The panel builds its stylesheet in JS from the live palette; the page
    # card has no such thing, so rules written only into panelCss leave the
    # page's tiles wearing the default button padding.
    html = APP.read_text(encoding="utf-8")
    page_css = html[html.index("<style>"):html.index("</style>")]
    assert ".banbtn" in page_css, "the ban grid is unstyled on the page card"
    assert ".bangrid" in page_css


def test_the_page_and_panel_ban_stylesheets_stay_in_step() -> None:
    """These rules exist twice and must not drift.

    The panel is a separate document and builds its stylesheet in JS from the
    live palette; the page card is styled by the page's own <style>. There is
    no mechanism keeping them equal, so this is it. It is not theoretical: the
    tiles shipped once with no page-side rules at all, and a class named
    outside the `.ban` prefix went unstyled in a tool that selected on it.
    """
    import re
    html = APP.read_text(encoding="utf-8")
    page = html[html.index("<style>"):html.index("</style>")]
    start = html.index("panelCss:c=>")
    panel = html[start:html.index("middleHtml:", start)]
    selectors = lambda s: set(re.findall(r"\.ban[a-z]*", s))
    assert selectors(page) == selectors(panel), (
        f"ban styling differs between page and panel: "
        f"page-only {sorted(selectors(page) - selectors(panel))}, "
        f"panel-only {sorted(selectors(panel) - selectors(page))}"
    )


def test_every_ban_grid_class_shares_the_ban_prefix() -> None:
    # So a single prefix finds all of them - the parity check above, and any
    # tool that has to pull these rules out of the page, select on `.ban`.
    html = APP.read_text(encoding="utf-8")
    grid = _extract(("function banGridHtml(", "// The chip markup for a map's bans."))
    import re
    for cls in re.findall(r'class="([a-z ]+)"', grid):
        for one in cls.split():
            assert one.startswith("ban"), f"grid class {one!r} sits outside the .ban prefix"


# --- the pre-map screen shows nothing stale -------------------------------

_READOUT_STUBS = """
function box(){ return {style:{}, innerHTML:'x'}; }
var PAGE={outA:{innerHTML:'stale'}, outB:{innerHTML:'stale'}};
PAGE.outA.parentElement=box(); PAGE.outB.parentElement=box();
var document={ getElementById:function(id){ return PAGE[id]||null; } };
var target={ A:{innerHTML:'stale'}, B:{innerHTML:'stale'} };
target.A.parentElement=box(); target.B.parentElement=box();
"""


def _run_readouts(body: str) -> object:
    node = shutil.which("node")
    if not node:
        pytest.skip("node not available to run the capture app's helpers")
    src = (_READOUT_STUBS + _extract(("function setReadoutsVisible(", "function readComp(bx)"))
           + "\nconsole.log(JSON.stringify((()=>{" + body + "})()));")
    tmp = Path("scrim_readout_test_tmp.js")
    tmp.write_text(src, encoding="utf-8")
    try:
        proc = subprocess.run([node, str(tmp)], capture_output=True, text=True, encoding="utf-8")
        assert proc.returncode == 0, f"node failed:\n{proc.stderr}"
    finally:
        tmp.unlink(missing_ok=True)
    return json.loads(proc.stdout)


def test_between_maps_the_team_readouts_are_emptied() -> None:
    # They hold whatever the last snapshot painted, so on the pre-map screen
    # they showed the PREVIOUS map's comp underneath the ban grid - stale data
    # wearing the appearance of live data.
    got = _run_readouts("""
      setReadoutsVisible(false);
      return [target.A.innerHTML, target.B.innerHTML,
              PAGE.outA.innerHTML, PAGE.outB.innerHTML];""")
    assert got == ["", "", "", ""], "a finished map's comp is still on screen"


def test_between_maps_the_team_panels_are_hidden_not_just_blank() -> None:
    # An empty column under its heading is still furniture on a panel that
    # sits on top of the game.
    got = _run_readouts("""
      setReadoutsVisible(false);
      return [target.A.parentElement.style.display, PAGE.outA.parentElement.style.display];""")
    assert got == ["none", "none"]


def test_starting_a_map_brings_the_readouts_back() -> None:
    got = _run_readouts("""
      setReadoutsVisible(false); setReadoutsVisible(true);
      return [target.A.parentElement.style.display, PAGE.outB.parentElement.style.display];""")
    assert got == ["", ""]


def test_showing_the_readouts_does_not_wipe_what_they_hold() -> None:
    # It runs from updateBtns, which fires on every state change - including
    # mid-capture, where clearing the current comp would blank the panel the
    # operator is reading.
    got = _run_readouts("""
      target.A.innerHTML='live comp';
      setReadoutsVisible(true);
      return target.A.innerHTML;""")
    assert got == "live comp"


# --- the panel is the workflow, the page is setup -------------------------
# Everything done DURING a scrim moved to the pop-out panel: the operator is
# watching Overwatch, and a control on the page is a control that costs an
# alt-tab. The page keeps what is done before the game starts (share the
# screen, calibrate, name the scrim) and nothing else.

def test_the_page_cannot_start_a_map() -> None:
    # It could, and it bypassed the ban picker entirely: the page's "Start map"
    # ran before bans had anywhere to be entered on that surface.
    html = APP.read_text(encoding="utf-8")
    for gone in ('id="scstart"', 'id="scrimmode"', 'id="scrimmapbtns"',
                 'id="scrimmapidx"', 'id="scrimcode"'):
        assert gone not in html, f"{gone} still lets the page start a map"


def test_the_page_has_no_ban_controls() -> None:
    html = APP.read_text(encoding="utf-8")
    for gone in ('id="banrow"', 'id="banpicker"'):
        assert gone not in html, f"{gone} still puts bans on the page"


def test_the_page_has_no_screenshot_importer() -> None:
    html = APP.read_text(encoding="utf-8")
    for gone in ('id="scrimpscrbtn"', 'id="scrimpscr"', 'id="scrimqueue"',
                 'id="scrimaddhand"', 'id="scrimstartsession"'):
        assert gone not in html, f"{gone} is still on the page"


def test_the_replay_history_parser_survives_its_ui() -> None:
    # The button went, the parsing did not: the replay-code OCR reads the same
    # replay-history text off the screen, and would otherwise start from
    # nothing. Its tests above still cover it.
    html = APP.read_text(encoding="utf-8")
    assert "function parseScrimSessionText(" in html
    assert "function bestMapMatch(" in html


def test_a_map_can_still_be_given_a_replay_code_from_the_panel() -> None:
    # Removing the page's code field took away the only place a code could be
    # entered. Without this every map would be saved with none until the
    # code-OCR work lands, and there would be no way to add one afterwards.
    row = _extract(("{id:'prow-next'", "{id:'prow-main'"))
    assert "createElement('input')" in row, "the panel has nowhere to put a replay code"
    assert "startMapNamed(" in row


def test_the_panel_says_what_the_pre_map_screen_is_for() -> None:
    html = APP.read_text(encoding="utf-8")
    assert "no map running" not in html, "the panel still leads with what is NOT happening"
    tick = _extract(("tick:el=>", "controls:["))
    assert "bans" in tick.lower() and "map" in tick.lower(), (
        "the pre-map panel does not say what it is for"
    )


def test_a_scrim_with_no_maps_cannot_be_closed_out() -> None:
    # Closing out a scrim that captured nothing leaves an empty record and
    # loses the setup. The button is not offered until a map has been saved.
    row = _extract(("{id:'prow-endscrim'", "{id:'prow-finish'"))
    assert "SCRIM_MAP_COUNT" in row, "finish-scrim is offered before any map exists"
    src = _extract(("async function endScrimCapture()", "// scrimDate():"))
    assert "SCRIM_MAP_COUNT" in src, "the guard is only in the rendering, not the action"


# --- reading the replay code off the screen -------------------------------

def test_the_panel_can_read_the_replay_code_off_the_screen() -> None:
    row = _extract(("{id:'prow-next'", "{id:'prow-main'"))
    assert "readReplayCode(" in row, "the panel has no way to read the code"


def test_reading_the_code_restores_the_shared_workers_settings() -> None:
    # One worker is shared with readHudNames and readScoreboard. engine/refs.js
    # records that no whitelist is set globally because readScoreboard needs
    # full text - so a code-only whitelist left in place does not fail loudly,
    # it silently corrupts the next scoreboard read.
    src = _extract(("async function readReplayCode(", "// ---------- hero bans"))
    assert "tessedit_char_whitelist" in src
    assert src.count("setParameters") >= 2, "the whitelist is set but never restored"
    assert "tessedit_char_whitelist:''" in src.replace(" ", ""), (
        "the whitelist must be cleared again, not left set to the code alphabet"
    )


def test_an_unreadable_code_writes_nothing() -> None:
    src = _extract(("async function readReplayCode(", "// ---------- hero bans"))
    assert "foldCode(" in src, "the read is not put through the validation gate"


def test_no_code_is_recorded_without_the_operator_seeing_it() -> None:
    """Starting a map must not read a code by itself.

    A crop that clips a glyph can produce six valid Crockford characters that
    are the wrong code - TJDE6W read as 8TDE6W, measured in the sweep - and
    foldCode cannot catch that, because it is well-formed. The scrim page has
    no feed to check against, so the operator seeing the read in the panel
    field IS the check. Filling it during Start removes that.
    """
    src = _extract(("async function startMapNamed(", "// A sub-map captured in an EARLIER round"))
    assert "readReplayCode" not in src, (
        "starting a map reads a code the operator never saw"
    )


def test_the_code_is_read_at_several_geometries_not_just_contrasts() -> None:
    """The contrast ladder cannot see a crop in the wrong place.

    A shifted crop is shifted identically at every contrast level, so all
    three passes agree and the read rule accepts on agreement. Measured over
    twelve real frames, that let 54 well-formed six-character codes through
    once the calibration strip was off by more than about 2% - codes that
    belong to no game, attributing a whole map's comps to the wrong match.
    Reading at several strip geometries and requiring all of them to agree
    scored zero wrong on the same frames.

    Full numbers: tools/real_frame_eval/README.md.
    """
    src = _extract(("async function readReplayCode(", "// ---------- hero bans"))
    assert "PROBES" in src and "probeStrip(" in src, (
        "the read no longer varies the geometry - the contrast ladder alone "
        "cannot catch a mis-placed crop"
    )
    assert "answers.length" in src, "a probe that read nothing must not be treated as agreement"


def test_scrim_page_loads_the_ban_row_parser() -> None:
    """A script the page uses but never loads is invisible to pytest and fatal
    in the browser - the CSP has silently broken three scripts already."""
    page = (Path(__file__).resolve().parents[1]
            / "docs" / "capture" / "scrim.html").read_text(encoding="utf-8")
    assert "engine/banrow.js" in page, "banrow.js is used but never loaded"
    assert "OWDBBanRow" in page, "banrow.js is loaded but never called"


def test_scrim_page_reads_bans_through_the_deadline_wrapped_ocr() -> None:
    """ocrWorker()'s timeout only covers LOADING tesseract. A recognize() that
    stalls afterwards never returns and takes every other read down with it."""
    page = (Path(__file__).resolve().parents[1]
            / "docs" / "capture" / "scrim.html").read_text(encoding="utf-8")
    body = page[page.index("async function readBanRow"):]
    body = body[:body.index("\n}")]
    assert "ocrRead(" in body, "the ban read must go through ocrRead"
    assert ".recognize(" not in body, "call ocrRead, never recognize directly"

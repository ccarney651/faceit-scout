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
            ("function bestMapMatch(text)", "async function importSessionFromScreenshot(file)"),
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


def test_scrim_pages_are_not_paused() -> None:
    """Both pause overlays are gone and cannot silently come back.

    Two pages carried an unconditional full-screen #scrimpaused overlay that
    no script removed (commit f2881cf): docs/capture/scrim.html blocked
    capturing, docs/scrims.html blocked viewing. Phase 1 removes both; this
    test is what stops either reappearing. It covers both files because an
    earlier draft of this plan removed only the capture one, which would have
    shipped scrims you could record but not read.
    """
    viewer = APP.parents[1] / "scrims.html"
    assert viewer.exists(), "docs/scrims.html moved — update this guard"
    for page in (APP, viewer):
        html = page.read_text(encoding="utf-8")
        assert "scrimpaused" not in html, f"{page.name} still has the overlay"
        assert "Scrims are paused" not in html, f"{page.name} still has the copy"


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
    # Both entry points that can start a capture from a replay code.
    assert html.count("if(awaitrefuseIfLeagueCode(") >= 2, (
        "a code entry point no longer calls refuseIfLeagueCode"
    )
    # The scaffold must not queue league rows in the first place.
    assert "!r.league" in html, "scaffolded league rows are no longer filtered out"


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
    html = APP.read_text(encoding="utf-8")
    assert 'id="rawocr"' in html, "the textarea this guard exists for moved or was renamed"


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
    # Every entry point into capture must go through it.
    assert html.replace(" ", "").count("awaitensureScrim();") >= 3, (
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
    assert 'id="banrow"' in html, "no ban control"
    assert "uses_bans" in html, "the toggle is not persisted on the scrim"
    assert "function usesBans()" in html


def test_bans_are_recorded_per_map_not_per_scrim() -> None:
    """A block can start banning partway through, and "what shifted when this
    hero was banned" is a per-map question."""
    html = APP.read_text(encoding="utf-8").replace(" ", "")
    assert "bans:MAP_BANS.slice()" in html, "bans are not saved onto the map record"
    # Reset per map, or the second map inherits the first map's bans.
    assert html.count("MAP_BANS=[];") >= 2, "MAP_BANS is not reset when a map starts"


def test_a_ban_can_record_who_banned_it() -> None:
    """'They banned it' and 'it was banned on them' are different situations -
    averaging them hides both, which is why the league Scout page splits them."""
    html = APP.read_text(encoding="utf-8")
    assert 'id="banby"' in html
    for who in ('value="us"', 'value="them"'):
        assert who in html, f"ban attribution is missing {who}"


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
      var row=el('div'); SCRIM.uses_bans=false; session={};
      ROW.render(row,d,mk); return descend(row).length;""")
    assert kids == 0


def test_the_panel_has_no_ban_row_before_a_map_is_running() -> None:
    kids = _run_row("""
      var row=el('div'); SCRIM.uses_bans=true; session=null;
      ROW.render(row,d,mk); return descend(row).length;""")
    assert kids == 0, "bans are recorded per map, so there is nothing to ban against yet"


def test_the_ban_row_offers_every_hero_and_who_banned_it() -> None:
    tags = _run_row("""
      var row=el('div'); SCRIM.uses_bans=true; session={};
      ROW.render(row,d,mk);
      return descend(row).map(function(n){return n.tagName;});""")
    assert tags.count("select") == 2, "a hero picker and a by-us/by-them picker"


def test_the_ban_row_shows_the_bans_already_recorded() -> None:
    chips = _run_row("""
      var row=el('div'); SCRIM.uses_bans=true; session={};
      MAP_BANS=[{g:'0x01',n:'Sombra'}];
      ROW.render(row,d,mk);
      return descend(row).filter(function(n){return n.__chips;}).length;""")
    assert chips == 1, "the row must render the existing bans, not just an input"


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

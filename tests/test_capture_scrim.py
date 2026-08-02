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
    # Three non-overlapping regions that avoid the DOM-heavy top-level wiring
    # between them.  Cluster A gives the map list; Cluster B gives the roster
    # similarity helpers; Cluster C gives the screenshot-import parser.
    return _extract(
        ("const CONTROL_SUBMAPS=", "const AUTO_SIDE_MARGIN="),
        ("const AUTO_SIDE_MARGIN=", "async function detectScrimSides()"),
        ("function bestMapMatch(text)", "async function importSessionFromScreenshot(file)"),
    )


# Minimal browser stubs so the extracted script can load in Node without the
# HAS_CAPTURE guard trying to touch real DOM APIs.
_STUBS = """
var window = {isSecureContext: true};
var navigator = {mediaDevices: {getDisplayMedia: function() {}}};
var document = {getElementById: function() { return null; }};
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
    """The mode dropdown must expose Control, Escort, Hybrid, Push, Flashpoint, Clash."""
    maps = _run("return SCRIM_MAPS;")
    modes = {m["cat"] for m in maps}
    assert modes == {"Control", "Escort", "Hybrid", "Push", "Flashpoint", "Clash"}


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

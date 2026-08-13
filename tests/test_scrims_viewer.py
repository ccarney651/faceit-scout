"""docs/scrims.html — the private scrims viewer's analysis helpers.

Extracts the pure functions and runs them under Node, the same way
tests/test_capture_scrim.py does for the capture app. The viewer keeps its
analysis inline rather than in an engine module because its CSP allows only
inline scripts (`script-src 'unsafe-inline'`, no `'self'`), so there is nothing
to import.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

APP = Path(__file__).resolve().parents[1] / "docs" / "scrims.html"


def _pure_js() -> str:
    html = APP.read_text(encoding="utf-8")
    start = html.index("const SCRIM_MODES")
    end = html.index("// ---------- opponent registry ----------")
    return html[start:end]


def _run(body: str) -> object:
    node = shutil.which("node")
    if not node:
        pytest.skip("node not available to run the viewer's helpers")
    src = _pure_js() + "\nconsole.log(JSON.stringify((()=>{" + body + "})()));"
    proc = subprocess.run([node, "-e", src], capture_output=True, text=True)
    assert proc.returncode == 0, f"node failed:\n{proc.stderr}"
    return json.loads(proc.stdout)


def _scrims_and_maps() -> tuple[str, str]:
    scrims = json.dumps([
        {"id": "s1", "date": "2026-08-13"},
        {"id": "s2", "date": "2026-07-20"},
    ])
    maps = json.dumps([
        {"scrim_id": "s1", "map_category": "Control"},
        {"scrim_id": "s1", "map_category": "Control"},
        {"scrim_id": "s1", "map_category": "Hybrid"},
        {"scrim_id": "s2", "map_category": "Push"},
    ])
    return scrims, maps


def test_coverage_reports_every_mode_including_unplayed_ones() -> None:
    """The point is the mode you have NOT played, so modes are listed, not derived.

    Deriving them from the captured maps would hide exactly the gap this is for.
    """
    scrims, maps = _scrims_and_maps()
    cov = _run(f"return mapCoverage({scrims}, {maps}, '2026-08-14');")
    modes = {c["mode"] for c in cov}
    assert {"Control", "Escort", "Hybrid", "Push", "Flashpoint", "Clash"} <= modes
    by = {c["mode"]: c for c in cov}
    assert by["Escort"]["games"] == 0 and by["Escort"]["last"] is None
    assert by["Escort"]["days"] is None


def test_coverage_counts_games_and_dates_the_most_recent() -> None:
    scrims, maps = _scrims_and_maps()
    by = {c["mode"]: c for c in _run(f"return mapCoverage({scrims}, {maps}, '2026-08-14');")}
    assert by["Control"]["games"] == 2
    assert by["Control"]["last"] == "2026-08-13"
    assert by["Control"]["days"] == 1
    assert by["Push"]["days"] == 25, "Push was three and a half weeks ago"


def test_coverage_puts_the_least_practised_first() -> None:
    """The ordering is the recommendation: never-played, then longest since."""
    scrims, maps = _scrims_and_maps()
    cov = _run(f"return mapCoverage({scrims}, {maps}, '2026-08-14');")
    played = [c["mode"] for c in cov if c["games"]]
    assert cov[0]["games"] == 0, "an unplayed mode should lead"
    assert played.index("Push") < played.index("Control"), (
        "the stalest played mode should come before the freshest"
    )


def test_voided_maps_do_not_count_as_practice() -> None:
    """A restarted map was not practice; counting it claims coverage you skipped."""
    scrims = json.dumps([{"id": "s1", "date": "2026-08-13"}])
    maps = json.dumps([
        {"scrim_id": "s1", "map_category": "Push", "void": True},
        {"scrim_id": "s1", "map_category": "Control"},
    ])
    by = {c["mode"]: c for c in _run(f"return mapCoverage({scrims}, {maps}, '2026-08-14');")}
    assert by["Push"]["games"] == 0, "a voided map still counted as practice"
    assert by["Control"]["games"] == 1


def test_coverage_falls_back_to_created_at_when_a_scrim_has_no_date() -> None:
    """An auto-created block has no date field until it is named and saved."""
    scrims = json.dumps([{"id": "s1", "created_at": "2026-08-10T19:00:00Z"}])
    maps = json.dumps([{"scrim_id": "s1", "map_category": "Control"}])
    by = {c["mode"]: c for c in _run(f"return mapCoverage({scrims}, {maps}, '2026-08-14');")}
    assert by["Control"]["last"] == "2026-08-10"
    assert by["Control"]["days"] == 4


def test_an_unexpected_mode_still_appears() -> None:
    """A mode the list does not know about must not vanish from the log."""
    scrims = json.dumps([{"id": "s1", "date": "2026-08-13"}])
    maps = json.dumps([{"scrim_id": "s1", "map_category": "Brawl"}])
    by = {c["mode"]: c for c in _run(f"return mapCoverage({scrims}, {maps}, '2026-08-14');")}
    assert by["Brawl"]["games"] == 1


def test_viewer_resolves_opponents_through_the_registry() -> None:
    """Renaming a remembered group once must relabel every scrim against them.

    So the viewer has to read the registry rather than the name string frozen
    onto each scrim record when it was captured.
    """
    html = APP.read_text(encoding="utf-8")
    assert "async function loadOpponents()" in html
    assert "function opponentOf(s)" in html
    assert "await loadOpponents();" in html, "the registry is never loaded"
    # And the places that show an opponent must go through it.
    assert html.count("opponentLabelHtml(s)") >= 2, (
        "a scrim's opponent is still rendered from the frozen string"
    )
    assert "esc(s.opponent||'opponent')" not in html, (
        "an opponent is still rendered without consulting the registry"
    )

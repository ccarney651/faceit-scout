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
    assert {"Control", "Escort", "Hybrid", "Push", "Flashpoint"} <= modes
    assert "Clash" not in modes, "Clash is no longer played competitively"
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


DEMO = APP.parent / "scrims-demo.json"


def test_demo_fixture_uses_real_teams_and_real_hero_guids() -> None:
    """A demo of "Team A / Player 1" teaches nothing about whether this is worth using.

    Real FACEIT entrants and real hero GUIDs, so the sample looks like what the
    operator would actually see.
    """
    d = json.loads(DEMO.read_text(encoding="utf-8"))
    assert d["demo"] is True
    assert d["scrims"] and d["scrim_maps"]
    names = {s.get("team_us") for s in d["scrims"]} | {s.get("opponent") for s in d["scrims"]}
    names.discard(None)
    assert names, "no team names in the demo"
    assert not any(n.lower().startswith(("team a", "team b", "example")) for n in names), (
        f"placeholder team names in the demo: {names}"
    )
    guids = {g for m in d["scrim_maps"] for o in m["observations"] for g in o["heroes"]}
    assert guids, "the demo has no hero observations"
    assert all(g.startswith("0x") for g in guids), f"not real hero GUIDs: {sorted(guids)[:3]}"


def test_demo_says_plainly_that_the_results_are_invented() -> None:
    """It names real teams and real players, so the disclaimer is not decoration.

    Without it, someone could read the page as a record of games those teams
    actually played.
    """
    d = json.loads(DEMO.read_text(encoding="utf-8"))
    note = d["note"].lower()
    assert "never happened" in note or "invented" in note, d["note"]
    assert "real" in note, "it should say the teams themselves are real"
    html = APP.read_text(encoding="utf-8")
    assert "function demoBanner()" in html
    assert "DEMO?demoBanner():''" in html.replace(" ", ""), "the banner is never rendered"


def test_demo_never_writes_to_the_real_database() -> None:
    """Trying the demo must not leave invented scrims in someone's own data."""
    html = APP.read_text(encoding="utf-8")
    start = html.index("async function loadDemo()")
    end = html.index("async function loadData()")
    body = html[start:end]
    for forbidden in ("idbPutIn", "objectStore(", "readwrite"):
        assert forbidden not in body, f"loadDemo touches storage: {forbidden}"


def test_demo_dates_stay_recent_rather_than_ageing() -> None:
    """Committed absolute dates would read as "played 200 days ago" within a year."""
    d = json.loads(DEMO.read_text(encoding="utf-8"))
    assert any("@@MINUS" in str(s.get("date", "")) for s in d["scrims"]), (
        "demo dates are absolute and will rot"
    )
    html = APP.read_text(encoding="utf-8")
    assert "function demoDate(" in html, "nothing resolves the relative dates"


def test_demo_covers_the_cases_the_viewer_is_meant_to_show() -> None:
    """The sample has to exercise what makes the page worth looking at."""
    d = json.loads(DEMO.read_text(encoding="utf-8"))
    assert any(s.get("opponent_team_id") for s in d["scrims"]), "no league opponent"
    assert any(s.get("opponent_id") for s in d["scrims"]), "no remembered group"
    assert any(not s.get("opponent_team_id") and not s.get("opponent_id")
               for s in d["scrims"]), "no unidentified opponent"
    assert any(m.get("void") for m in d["scrim_maps"]), "no voided restart"
    modes = {m["map_category"] for m in d["scrim_maps"]}
    assert len(modes) >= 4, f"too few modes to make coverage meaningful: {modes}"


def test_coverage_breaks_a_mode_down_by_map() -> None:
    """A mode total hides that you have played Ilios twice and Nepal never.

    The per-map breakdown is the actionable half: "play Control more" is not a
    plan, "you have never scrimmed Nepal" is.
    """
    scrims = json.dumps([{"id": "s1", "date": "2026-08-13"}])
    maps = json.dumps([
        {"scrim_id": "s1", "map_category": "Control", "map_name": "Ilios"},
        {"scrim_id": "s1", "map_category": "Control", "map_name": "Ilios"},
        {"scrim_id": "s1", "map_category": "Control", "map_name": "Busan"},
    ])
    by = {c["mode"]: c for c in _run(f"return mapCoverage({scrims}, {maps}, '2026-08-14');")}
    ctrl = by["Control"]["maps"]
    assert ctrl["Ilios"] == 2
    assert ctrl["Busan"] == 1
    assert ctrl["Nepal"] == 0, "an unplayed map in the pool must still be listed"
    assert set(ctrl) >= {"Antarctic Peninsula", "Lijiang Tower", "Oasis", "Samoa"}


def test_clash_is_gone_from_the_pool() -> None:
    """No longer played competitively, so it is noise in every list."""
    html = APP.read_text(encoding="utf-8")
    start = html.index("const POOL = {")
    pool = html[start:html.index("};", start)]
    assert "Clash" not in pool
    assert "Anubis" not in pool and "Hanaoka" not in pool


def test_the_view_can_be_scoped_to_a_period() -> None:
    """A year of scrims can span two or three teams.

    Mixing them produces hero pools that belong to nobody, so the range is a
    first-class control rather than a nicety.
    """
    html = APP.read_text(encoding="utf-8")
    assert "function applyRange(data)" in html
    assert "function renderRangeBar()" in html
    assert "function wireRangeBar(" in html
    assert "Custom…" in html or "Custom" in html, "no custom range option"
    # It must filter the loaded data rather than re-read storage, or switching
    # range would be a round-trip to IndexedDB on every change.
    start = html.index("function applyRange(data)")
    body = html[start:start + 800]
    assert "idbGetAll" not in body, "applyRange re-reads storage instead of filtering"


def test_an_undated_scrim_is_never_hidden_by_a_range() -> None:
    """An auto-created block has no date until it is saved; losing it would look
    like data loss rather than filtering."""
    html = APP.read_text(encoding="utf-8")
    start = html.index("function applyRange(data)")
    body = html[start:start + 800]
    assert "if(!d) return true" in body.replace(" ", "").replace("if(!d)returntrue", "if(!d) return true") \
        or "if(!d) return true" in body, "undated scrims are not explicitly kept"

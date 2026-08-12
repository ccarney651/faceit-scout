"""The divergence report that guides engine extraction."""

from __future__ import annotations

from tools.capture_divergence import function_bodies, report


def test_report_finds_the_known_shared_surface() -> None:
    rep = report()
    # 104 shared names at the time of writing; the count only shrinks as
    # extraction proceeds, so assert the floor rather than an exact figure.
    assert len(rep["shared"]) >= 40
    assert "calMsg" in rep["diverged"], "calMsg differs by string encoding"
    # simScore was the worked example of real drift (index.html normalised
    # through _normName(); scrim.html only lowercased and trimmed). The names
    # engine extraction (docs/capture/engine/names.js) resolved the drift by
    # moving it out of both pages entirely, so it no longer appears as a
    # named function in either - and therefore can't be "shared" (let alone
    # "diverged") by this name-matching tool anymore.
    assert "simScore" not in rep["shared"], "simScore should have moved to engine/names.js"


def test_bodies_are_extracted_with_balanced_braces() -> None:
    bodies = function_bodies("index.html")
    body = bodies["calMsg"]
    assert body.startswith("{") and body.endswith("}")
    assert body.count("{") == body.count("}")

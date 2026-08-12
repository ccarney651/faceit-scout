"""The divergence report that guides engine extraction."""

from __future__ import annotations

from tools.capture_divergence import function_bodies, report


def test_report_finds_the_known_shared_surface() -> None:
    rep = report()
    # 104 shared names at the time of writing; the count only shrinks as
    # extraction proceeds, so assert the floor rather than an exact figure.
    assert len(rep["shared"]) >= 40
    assert "simScore" in rep["diverged"], "simScore drift is the worked example"
    assert "calMsg" in rep["diverged"], "calMsg differs by string encoding"


def test_bodies_are_extracted_with_balanced_braces() -> None:
    bodies = function_bodies("index.html")
    body = bodies["simScore"]
    assert body.startswith("{") and body.endswith("}")
    assert body.count("{") == body.count("}")

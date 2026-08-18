"""The divergence report that guides engine extraction."""

from __future__ import annotations

from tools.capture_divergence import function_bodies, report


def test_report_finds_the_known_shared_surface() -> None:
    rep = report()
    # 104 shared names at the time of writing; the count only shrinks as
    # extraction proceeds, so assert the floor rather than an exact figure.
    # Lowered 40 -> 30 when the overlay (popout/renderPipControls/pipColors/
    # pipPanelCss/setPopBtn/maybeAutoPop/gestureAutoPop/restylePipPanel) and
    # tour (tourHighlight/tourRender/tourOpen/tourDone/tourNext/tourPrev/
    # tourTick/maybeShowTour/isFirstVisit) clusters moved into
    # docs/capture/engine/overlay.js and engine/tour.js - the last extraction
    # in phase 0 (see tools/capture_divergence.py's own count: 34 shared
    # after this move).
    assert len(rep["shared"]) >= 30
    # simScore was the worked example of real drift (index.html normalised
    # through _normName(); scrim.html only lowercased and trimmed). The names
    # engine extraction (docs/capture/engine/names.js) resolved the drift by
    # moving it out of both pages entirely, so it no longer appears as a
    # named function in either - and therefore can't be "shared" (let alone
    # "diverged") by this name-matching tool anymore.
    assert "simScore" not in rep["shared"], "simScore should have moved to engine/names.js"
    # calMsg was the worked example of cosmetic (string-encoding-only) drift.
    # Calibration extraction (docs/capture/engine/calibration.js) moved it out
    # of both pages entirely along with the rest of the calibrate-preview
    # cluster, so - same as simScore above - it can no longer be "shared" or
    # "diverged" by this name-matching tool.
    assert "calMsg" not in rep["shared"], "calMsg should have moved to engine/calibration.js"
    # bestMatch and importRefs both showed up in this tool's diverged report
    # (bestMatch by one comment index.html carried and scrim.html didn't;
    # importRefs by an em-dash-escape-vs-literal drift, same pattern as
    # calMsg) - neither was a real behavioural difference, confirmed with
    # difflib.SequenceMatcher over the raw bodies before moving. Hero
    # recognition extraction (docs/capture/engine/refs.js) moved the whole
    # cluster out of both pages, so - same as simScore/calMsg above - these
    # can no longer be "shared" or "diverged" by this name-matching tool.
    assert "bestMatch" not in rep["shared"], "bestMatch should have moved to engine/refs.js"
    assert "importRefs" not in rep["shared"], "importRefs should have moved to engine/refs.js"
    # popout and renderPipControls were the worked example of real (not
    # cosmetic) drift for this task: index.html's control panel carries
    # controls scrim.html's doesn't, so the two pages differed by >1KB in
    # each. Overlay extraction (docs/capture/engine/overlay.js) moved the
    # whole cluster out of both pages, passing the control set in as data
    # (ctx.controls) instead of reconciling it into one branching function.
    assert "popout" not in rep["shared"], "popout should have moved to engine/overlay.js"
    assert "renderPipControls" not in rep["shared"], "renderPipControls should have moved to engine/overlay.js"
    # tourOpen/tourDone/maybeShowTour/isFirstVisit: tour extraction
    # (docs/capture/engine/tour.js) moved the tour MECHANISM out of both
    # pages; tourDefs (each page's own step copy) and updateGuide (a
    # separate always-visible stepper card) deliberately stayed behind, so
    # they still show up in this report.
    assert "tourOpen" not in rep["shared"], "tourOpen should have moved to engine/tour.js"
    assert "tourDone" not in rep["shared"], "tourDone should have moved to engine/tour.js"
    assert "maybeShowTour" not in rep["shared"], "maybeShowTour should have moved to engine/tour.js"
    assert "isFirstVisit" not in rep["shared"], "isFirstVisit should have moved to engine/tour.js"
    assert "tourDefs" in rep["shared"], "tourDefs is page copy and should NOT have moved"
    assert "updateGuide" in rep["shared"], "updateGuide is page copy and should NOT have moved"


def test_bodies_are_extracted_with_balanced_braces() -> None:
    # calMsg (the original worked example here) moved to
    # engine/calibration.js, then bestMatch (the second worked example) moved
    # to engine/refs.js; fixReads is still a named function in both pages
    # (it stayed page-side - see engine/refs.js's header for why) and serves
    # the same purpose: a real multi-brace function body to exercise the
    # balanced-brace scan.
    bodies = function_bodies("index.html")
    body = bodies["fixReads"]
    assert body.startswith("{") and body.endswith("}")
    assert body.count("{") == body.count("}")

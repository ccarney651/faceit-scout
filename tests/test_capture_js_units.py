"""Runs the capture app's JavaScript unit tests under pytest.

docs/capture/*.test.js and docs/capture/engine/*.test.js are node:test files.
Without this shim nothing executes them — scoreboard.test.js sat green and
unrun for months. pytest is the suite of record (AGENTS.md), so JS unit tests
have to be reachable from it.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

CAPTURE = Path(__file__).resolve().parents[1] / "docs" / "capture"


def test_capture_javascript_unit_tests_pass() -> None:
    node = shutil.which("node")
    if not node:
        pytest.skip("node not available to run the capture app's JS unit tests")

    suites = sorted(CAPTURE.rglob("*.test.js"))
    assert suites, "no *.test.js files found under docs/capture — did the runner move?"

    proc = subprocess.run(
        [node, "--test", *[str(p) for p in suites]],
        capture_output=True,
        text=True,
        cwd=CAPTURE,
    )
    assert proc.returncode == 0, (
        f"node --test failed:\n{proc.stdout}\n{proc.stderr}"
    )

"""ARCHITECTURE.md cites file paths constantly. This keeps them honest.

A wrong path in an architecture document is worse than a missing one: it sends
both the reader and any coding agent to a file that is not there. This test
fails the moment the document names something the repository does not have --
including when a later refactor renames a module out from under it.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DOC = REPO_ROOT / "ARCHITECTURE.md"

# Paths the document must be able to name even though they are generated at
# runtime and absent from a fresh clone.
RUNTIME_PATHS = {
    "crops/",
    "refs/",
    "calibration/",
    "screenshots/",
    "faceit.sqlite3",
    "owdb.sqlite3",
    "owdb_comps.json",
    "dashboard.html",
    "owdb_refs.zip",
    ".venv/Scripts/python.exe",
    # Present on a working machine, absent from a fresh clone: local tool state
    # and build byproducts. Section 2 names them, so they have to be nameable.
    "overwatch-hero-icons/",
    "faceit_sync.egg-info/",
    ".mypy_cache/",
    ".pytest_cache/",
    ".ruff_cache/",
    ".venv/",
}

_CODE_SPAN = re.compile(r"`([^`\n]+)`")
# Skip anything that is plainly not a literal path: command lines (whitespace),
# placeholders like <season>, globs, and URLs.
_NOT_A_PATH = re.compile(r"[<>*?\s]|^https?://")
_PATH_SUFFIXES = (
    ".md",
    ".py",
    ".json",
    ".toml",
    ".yml",
    ".yaml",
    ".cmd",
    ".html",
    ".js",
    ".css",
)


def _cited_paths(text: str) -> set[str]:
    """Repo-relative paths cited in inline code spans."""
    found: set[str] = set()
    for span in _CODE_SPAN.findall(text):
        if _NOT_A_PATH.search(span):
            continue
        if "/" not in span and not span.endswith(_PATH_SUFFIXES):
            continue
        if span in RUNTIME_PATHS or span.rstrip("/") + "/" in RUNTIME_PATHS:
            continue
        found.add(span)
    return found


def test_architecture_doc_exists() -> None:
    assert DOC.is_file(), "ARCHITECTURE.md is missing from the repository root"


def test_every_cited_path_exists() -> None:
    missing = sorted(
        path
        for path in _cited_paths(DOC.read_text(encoding="utf-8"))
        if not (REPO_ROOT / path).exists()
    )
    assert not missing, "ARCHITECTURE.md cites paths that do not exist:\n  " + "\n  ".join(missing)

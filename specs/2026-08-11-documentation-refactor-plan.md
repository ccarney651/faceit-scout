# Documentation Refactor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Produce `ARCHITECTURE.md` — one verified document explaining every part of OWDB and how the parts connect — plus a reconstructed `CHANGELOG.md`, an `AGENTS.md`/`CLAUDE.md` split, and removal of the repo's dead files.

**Architecture:** `ARCHITECTURE.md` sits at the repository root above the existing reference docs (`README.md`, `FEATURES.md`, `SPEC.md`), which are not rewritten. It is built section by section, each section verified against source code rather than paraphrased from existing docs. A new pytest test (`tests/test_docs_links.py`) mechanically verifies that every repo path the document cites actually exists, and is written **first** so every later section is written against a green check.

**Tech Stack:** Markdown; Python 3.12 + pytest for the link-checker test; git for the changelog reconstruction and cleanup.

## Global Constraints

- **Source of truth is the code.** Every factual claim in `ARCHITECTURE.md` must be verified by reading the referenced source file in this task. Do not paraphrase `CLAUDE.md`, `FEATURES.md`, or `SPEC.md` — `specs/BACKLOG.md` records that `FEATURES.md` is six features behind. Anything unconfirmable from source is omitted or explicitly marked unverified. Never guessed.
- **`ARCHITECTURE.md` lives at the repository root**, never under `docs/` — `docs/` is the GitHub Pages web root (`docs/CNAME`, `docs/.nojekyll`) and anything placed there is published to owdb.io.
- **No source code behaviour changes.** This change touches documentation, `.gitignore`, one new test file, and deletes dead files. Nothing else.
- **Do not modify** `README.md`, `FEATURES.md`, `SPEC.md`, `docs/index.html`, `docs/capture/*`, `docs/scrims.html`, or any file the live site renders.
- **Subsystem section template**, used verbatim for sections 3 through 8: `What it does` → `How it works` → `Files` → `How it connects` → `Gotchas`.
- **Retrieval rules** for the whole document: literal repo-relative paths in backticks (never "the export module"); every section opens with a one-line summary; no pronoun reaching back across a heading; unique stable headings with a linked table of contents; invariants stated imperatively with the failure mode attached.
- **Python is invoked as** `.venv/Scripts/python.exe` (Windows dev environment).
- **Verification commands:** `.venv/Scripts/python.exe -m pytest` (full suite), `.venv/Scripts/python.exe -m mypy faceit_sync` (must stay clean).
- **CI auto-commits to `origin/main` every few minutes.** Always `git fetch` before pushing, expect a merge, and resolve by keeping CI's data and reapplying your own diff on top.

---

## File Structure

**Created:**
- `ARCHITECTURE.md` — the deliverable; 14 sections, root level.
- `CHANGELOG.md` — reconstructed history, root level.
- `AGENTS.md` — canonical cross-agent instruction file, root level.
- `tests/test_docs_links.py` — mechanical link check for `ARCHITECTURE.md`.

**Modified:**
- `.gitignore` — add `.opencode/` and `dashboard_artifact.html`.
- `CLAUDE.md` — reduced to a pointer at `AGENTS.md`.

**Deleted:**
- `GUIDED`, `DISTRIBUTION.md`, `poc/` (tracked; `git rm`).
- `crops/` (tracked; `git rm --cached -r` only — files stay on disk).
- Untracked junk: eleven root `.log` files, `build/`, `dist/`, `owscout.sqlite3.bak-20260717-234643`, `owdb_refs.zip`, `dashboard_artifact.html`.

---

## Task 1: Repository cleanup

Removes the dead files first so every later task works in a quiet tree. Verified during planning: `git grep` finds **no inbound references** to `DISTRIBUTION.md`, `GUIDED`, or `poc/` outside `poc/` itself, so all three deletions are safe.

**Files:**
- Modify: `.gitignore`
- Delete (tracked): `GUIDED`, `DISTRIBUTION.md`, `poc/browser-capture.html`, `poc/build_browser_poc.py`
- Untrack only: `crops/` (1,530 files)

**Interfaces:**
- Consumes: nothing.
- Produces: a clean `git status`; no symbols.

- [ ] **Step 1: Re-confirm no inbound references before deleting**

```bash
git grep -n -I -E 'DISTRIBUTION\.md|GUIDED|poc/' -- . ':(exclude)crops'
```

Expected: only self-references inside `poc/build_browser_poc.py` and `poc/browser-capture.html`. If anything else appears, fix that reference before continuing.

- [ ] **Step 2: Delete untracked working-tree junk**

```bash
rm -f audit.log audit2.log auto-update.log build.log build2.log build3.log \
      build4.log build5.log import.log reingest.log server.log
rm -f owscout.sqlite3.bak-20260717-234643 owdb_refs.zip dashboard_artifact.html
rm -rf build/ dist/
```

Do **not** delete `dashboard.html` — it is the local preview build and is deliberately kept.

- [ ] **Step 3: Untrack `crops/`, delete the dead tracked files**

```bash
git rm -r --cached --quiet crops/
git rm -f GUIDED DISTRIBUTION.md
git rm -r -f poc/
```

`--cached` on `crops/` is deliberate: the 1,530 PNGs are regenerable runtime debug output already listed in `.gitignore`, and there is no upside to destroying local data.

- [ ] **Step 4: Add the two missing `.gitignore` rules**

Append to `.gitignore`:

```gitignore
# opencode agent workspace (plugins + its own node_modules)
.opencode/
```

And directly below the existing `dashboard.html` block, add:

```gitignore
dashboard_artifact.html
```

- [ ] **Step 5: Verify nothing broke**

```bash
.venv/Scripts/python.exe -m pytest
git status --short
```

Expected: full suite passes (no test imports `poc/` or reads `GUIDED`). `git status --short` shows only the intended deletions plus the `.gitignore` edit — no `crops/` entries, no `.opencode/` entries.

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -m "chore: remove dead files and untrack debug crops

Deletes GUIDED (documented the native GUI removed 2026-08-08),
DISTRIBUTION.md (a tombstone redirecting to FEATURES.md 2.7), and poc/
(superseded by the shipped docs/capture/). Untracks crops/ -- 1,530 debug
PNGs committed in 43c926a before the .gitignore rule landed; files stay on
disk since they are regenerable. Ignores .opencode/ and
dashboard_artifact.html.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## Task 2: The link-checker test and the `ARCHITECTURE.md` skeleton

Writes the test that keeps the document honest **before** writing the document, so every later section is added against a green check. This is the mechanism that enforces the accuracy requirement.

**Files:**
- Create: `tests/test_docs_links.py`
- Create: `ARCHITECTURE.md`

**Interfaces:**
- Consumes: nothing.
- Produces: `tests/test_docs_links.py` with `RUNTIME_PATHS: set[str]` (the allowlist later tasks extend if they cite a generated file) and `_cited_paths(text: str) -> set[str]`. `ARCHITECTURE.md` with all 14 section headings in place for later tasks to fill.

- [ ] **Step 1: Write the failing test**

Create `tests/test_docs_links.py`:

```python
"""ARCHITECTURE.md cites file paths constantly. This keeps them honest.

A wrong path in an architecture document is worse than a missing one: it
sends both the reader and any coding agent to a file that is not there.
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
}

_CODE_SPAN = re.compile(r"`([^`\n]+)`")
# Skip anything that is plainly not a literal path: command lines (whitespace),
# placeholders like <season>, globs, and URLs.
_NOT_A_PATH = re.compile(r"[<>*?\s]|^https?://")
_PATH_SUFFIXES = (".md", ".py", ".json", ".toml", ".yml", ".yaml", ".cmd", ".html", ".js", ".css")


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
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
.venv/Scripts/python.exe -m pytest tests/test_docs_links.py -v
```

Expected: `test_architecture_doc_exists` FAILS with "ARCHITECTURE.md is missing from the repository root".

- [ ] **Step 3: Create the `ARCHITECTURE.md` skeleton**

Create `ARCHITECTURE.md` containing: an H1 title, a one-paragraph statement of what the document is and who it is for, a table-of-contents list linking to each of the 14 anchors, and all 14 H2 headings with a one-line summary under each. Headings must be exactly:

```markdown
## 0. Orientation
## 1. The map
## 2. Repository tour
## 3. Ingest — `faceit_sync`
## 4. Dashboard build
## 5. Capture — the Python `owdb` package
## 6. Browser capture app
## 7. Scrims
## 8. Infrastructure and CI
## 9. Data contracts
## 10. Lifecycles and operations
## 11. Glossary
## 12. Invariants
## 13. Testing map
```

Under each heading, for now, write only the one-line summary sentence. Later tasks fill the bodies.

- [ ] **Step 4: Run the test to verify it passes**

```bash
.venv/Scripts/python.exe -m pytest tests/test_docs_links.py -v
```

Expected: both tests PASS.

- [ ] **Step 5: Commit**

```bash
git add tests/test_docs_links.py ARCHITECTURE.md
git commit -m "docs: add ARCHITECTURE.md skeleton and its link-checker test

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## Task 3: Sections 0-2 — orientation, the map, repository tour

The reader's entry point: what OWDB is, the artifact-flow diagram, and what every top-level path is for.

**Files:**
- Modify: `ARCHITECTURE.md` (sections 0, 1, 2)
- Read to verify: `pyproject.toml`, `faceit_sync/cli.py`, `owdb/cli.py`, `.github/workflows/update.yml`

**Interfaces:**
- Consumes: the skeleton from Task 2.
- Produces: section anchors `#0-orientation`, `#1-the-map`, `#2-repository-tour` for later cross-references.

- [ ] **Step 1: Inventory the repository**

```bash
git ls-files | awk -F/ '{print $1}' | sort -u
ls -A
```

Cross-check each entry against `.gitignore` so the tour can mark what is tracked versus generated.

- [ ] **Step 2: Verify the console entry points**

```bash
grep -A5 '\[project.scripts\]' pyproject.toml
```

Confirms the `faceit-sync` and `owdb` command names before documenting them.

- [ ] **Step 3: Write section 0 — Orientation**

One paragraph on what OWDB is (Overwatch 2 composition scouting for the FACEIT League: two Python packages feeding one website). Then a routing table with columns `I want to change…` / `Look at…` / `Section`, covering at minimum: ingest logic, the dashboard's look, the dashboard's data, the capture tool, scrims, the upload worker, CI scheduling, and hero reference images.

- [ ] **Step 4: Write section 1 — The map**

A fenced ASCII diagram of the full data flow, then a table below it with columns `Artifact` / `Written by` / `Read by` / `Committed?` covering at minimum: `faceit.sqlite3`, `owdb.sqlite3`, `docs/index.html`, `data/captures/s9/*.json`, `owdb_comps.json`, `docs/capture/data.json`, `docs/capture/refs.json`, and the browser IndexedDB store `owscout-capture`.

State explicitly, in prose, that there are two independent copies of `faceit.sqlite3` — the local one and the one CI keeps in its Actions cache — and that nothing reconciles them.

- [ ] **Step 5: Write section 2 — Repository tour**

A table with columns `Path` / `What it is` / `Status`, one row per top-level directory and per root file. `Status` is one of `live`, `reference`, `generated`, or `local-only`. Every path in the `Path` column must exist (the link-checker test enforces this).

- [ ] **Step 6: Run the link checker**

```bash
.venv/Scripts/python.exe -m pytest tests/test_docs_links.py -v
```

Expected: PASS. If a path is reported missing, the document is wrong — fix the document, not the test, unless the path is genuinely runtime-generated, in which case add it to `RUNTIME_PATHS` with a comment.

- [ ] **Step 7: Commit**

```bash
git add ARCHITECTURE.md tests/test_docs_links.py
git commit -m "docs: ARCHITECTURE.md sections 0-2 (orientation, map, repo tour)

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## Task 4: Section 3 — Ingest (`faceit_sync`)

How FACEIT match data gets into `faceit.sqlite3`, and the three data-quality hazards that motivate the project.

**Files:**
- Modify: `ARCHITECTURE.md` (section 3)
- Read to verify: `faceit_sync/sync.py`, `faceit_sync/client.py`, `faceit_sync/db.py`, `faceit_sync/models.py`, `faceit_sync/cli.py`
- Cross-check tests: `tests/test_sync.py`, `tests/test_idempotency.py`, `tests/test_restart.py`, `tests/test_history.py`, `tests/test_scheduled.py`, `tests/test_stats_null.py`

**Interfaces:**
- Consumes: section anchors from Task 3.
- Produces: anchor `#3-ingest--faceit_sync`.

- [ ] **Step 1: Read the ingest modules**

Read all five `faceit_sync` modules listed above in full. Note the actual function names for: the keyless transitive discovery walk, the per-match write transaction, and the finished-match skip with its replay-code backfill exceptions.

- [ ] **Step 2: Verify the stat-code mapping**

```bash
grep -n 'STAT_FIELD_MAP' -A 30 faceit_sync/models.py
```

Record the real codes and their meanings; do not copy them from `README.md`.

- [ ] **Step 3: Verify each hazard against its test**

Read `tests/test_restart.py` and `tests/test_stats_null.py` and confirm what behaviour each actually asserts before describing hazards A and B. Read `tests/test_history.py` for hazard C.

- [ ] **Step 4: Write section 3**

Follow the five-part template. `How it works` must cover: keyless transitive discovery from `matches.txt` seeds, why an API key is only needed for championship enumeration, the idempotency model (reference rows upsert; per-match child rows delete-and-reinsert atomically), the finished-match skip and its two backfill exceptions, and scheduled/upcoming fixtures being stored bare and upgraded on finish.

`Gotchas` must cover: the three data hazards with the reason each exists, the empirically-mapped opaque stat codes in `faceit_sync/models.py`, the stats endpoint path quirk, and the User-Agent rule (FACEIT's edge returns 403 for browser-like agents; the client sends a descriptive `faceit-sync/…` agent and must not impersonate a browser).

- [ ] **Step 5: Run the link checker and commit**

```bash
.venv/Scripts/python.exe -m pytest tests/test_docs_links.py -v
git add ARCHITECTURE.md
git commit -m "docs: ARCHITECTURE.md section 3 (faceit_sync ingest)

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## Task 5: Section 4 — Dashboard build

How `docs/index.html` is assembled, and why one JavaScript syntax error yields a completely blank page.

**Files:**
- Modify: `ARCHITECTURE.md` (section 4)
- Read to verify: `faceit_sync/_dashboard.py`, `faceit_sync/export.py`, `faceit_sync/dashboard/head.html`, `faceit_sync/dashboard/pure.js`, `faceit_sync/dashboard/app.js`, `faceit_sync/dashboard/boot.js`, `faceit_sync/hero_icons.py`, `faceit_sync/team_logos.py`
- Cross-check tests: `tests/test_export.py`, `tests/test_dashboard_logic.py`

**Interfaces:**
- Consumes: anchors from Tasks 3-4.
- Produces: anchor `#4-dashboard-build`.

- [ ] **Step 1: Read the build path**

Read `faceit_sync/_dashboard.py` in full and record the exact concatenation order of the four part files and the name of the data placeholder token in `faceit_sync/dashboard/head.html`.

- [ ] **Step 2: Verify the testability seam**

Read `tests/test_dashboard_logic.py` and record how it extracts the pure region of `faceit_sync/dashboard/pure.js` and executes it in node. This is the rule that decides where new dashboard logic belongs.

- [ ] **Step 3: Verify the self-containment constraint**

```bash
grep -n 'self_contained\|theme.css\|base64' faceit_sync/_dashboard.py
```

Confirm how `docs/theme.css` is inlined with base64-embedded fonts, and read `tests/test_export.py::test_export_html_is_self_contained_and_valid` for what "self-contained" is actually asserted to mean.

- [ ] **Step 4: Write section 4**

Follow the five-part template. `How it works` covers: plain concatenation at import time with no framework or build step, the four part files and their responsibilities, `bootApp(DATA)`, inline `var __OWDB_DATA__=…` versus `export --external-data`, and vanilla-JS DOM construction with hash routing per tab.

`Gotchas` must state, prominently: the dashboard body is entirely rendered in JavaScript from an inlined data blob, so a single JS syntax error produces a blank page that bracket-balance checks will not catch — always run `tests/test_export.py::test_dashboard_javascript_is_syntactically_valid` (which runs `node --check`) after editing any part file. Also cover: `docs/theme.css` as the shared token source and why `docs/index.html` cannot link it, and hero portraits silently degrading to text chips when the `faceit_sync/hero_icons.json` cache is absent.

- [ ] **Step 5: Run both checks and commit**

```bash
.venv/Scripts/python.exe -m pytest tests/test_docs_links.py tests/test_export.py -v
git add ARCHITECTURE.md
git commit -m "docs: ARCHITECTURE.md section 4 (dashboard build)

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## Task 6: Section 5 — Capture (Python `owdb`)

The original capture pipeline: screen capture and template matching turned into typed comp observations.

**Files:**
- Modify: `ARCHITECTURE.md` (section 5)
- Read to verify: `owdb/cli.py`, `owdb/db.py`, `owdb/calibrate.py`, `owdb/refs.py`, `owdb/capture.py`, `owdb/match.py`, `owdb/integrity.py`, `owdb/comps.py`, `owdb/scout.py`, `owdb/analysis.py`, `owdb/derive.py`, `owdb/context.py`, `owdb/contribute.py`, `owdb/maps.py`, `owdb/models.py`, `owdb/firstrun.py`, `owdb/faceit.py`, `owdb/errors.py`, `owdb/integrity.py`

**Interfaces:**
- Consumes: anchors from Tasks 3-5.
- Produces: anchor `#5-capture--the-python-owdb-package`.

- [ ] **Step 1: Enumerate the real subcommands**

```bash
grep -n 'add_parser' owdb/cli.py
```

Document the subcommands that actually exist, not the list in `CLAUDE.md`.

- [ ] **Step 2: Verify the read-only attach**

```bash
grep -n 'attach_faceit' -A 15 owdb/db.py
```

Confirm the `mode=ro` URI. This is the invariant that `owdb` never writes the faceit database.

- [ ] **Step 3: Verify the mypy exclusion**

```bash
grep -n 'exclude\|owdb' pyproject.toml
```

Record which modules are excluded from mypy and state the reason in the document: the capture/CV layer is thin IO wrapping, and the logic it wraps is typed and tested separately.

- [ ] **Step 4: Write section 5**

Follow the five-part template. `How it works` walks the pipeline in order — calibrate, build the reference library, capture a replay, match observations to players and heroes, run integrity checks, derive comps, produce scouting output — naming the module that owns each stage.

`Gotchas` covers: replay codes being invalidated by every Overwatch patch, and the wipe date living in **two** files that must stay in sync (`owdb/db.py` `_SEED_WIPES` and `tools/build_capture_data.py` `CODE_WIPE_DATE`), plus the pinned assertions in `owdb/tests/test_codes.py` and `owdb/tests/test_context.py`.

- [ ] **Step 5: Run checks and commit**

```bash
.venv/Scripts/python.exe -m pytest tests/test_docs_links.py -v
git add ARCHITECTURE.md
git commit -m "docs: ARCHITECTURE.md section 5 (owdb capture package)

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## Task 7: Sections 6-7 — Browser capture app and scrims

The only supported capture path, and the private local-first scrims side-channel that shares its browser storage.

**Files:**
- Modify: `ARCHITECTURE.md` (sections 6, 7)
- Read to verify: `docs/capture/index.html`, `docs/capture/scrim.html`, `docs/capture/scoreboard.js`, `docs/scrims.html`, `tools/build_capture_data.py`, `tools/build_capture_refs.py`
- Cross-check tests: `tests/test_capture_csp.py`, `tests/test_capture_scrim.py`, `tests/test_capture_observations.py`, `tests/test_capture_ocr_worker.py`, `tests/test_capture_attribution.py`

**Interfaces:**
- Consumes: anchors from Tasks 3-6.
- Produces: anchors `#6-browser-capture-app`, `#7-scrims`.

- [ ] **Step 1: Verify the IndexedDB contract**

```bash
grep -n "owscout-capture" docs/capture/index.html docs/capture/scrim.html docs/scrims.html
```

Record the database name, its schema version, and the object stores. Confirm from the source that `docs/scrims.html` opens it without bumping the version.

- [ ] **Step 2: Verify the CSP arrangement**

Read `tests/test_capture_csp.py` and the `<meta http-equiv="Content-Security-Policy">` tag in `docs/capture/index.html`. Note for the document that the policy lives in a meta tag, so `curl -I` shows nothing — this cost four debugging sessions when it silently blocked tesseract.js's blob worker.

- [ ] **Step 3: Write section 6 — Browser capture app**

Follow the five-part template. Cover: zero-install operation via `getDisplayMedia` plus tesseract.js OCR, that it is the **only** supported capture path, and the publish route from the browser to the upload Worker to `data/captures/<season>/<contributor>.json`.

- [ ] **Step 4: Write section 7 — Scrims**

Follow the five-part template. Cover: scrim data living only in the browser and never being published or merged; `docs/capture/` and `docs/` sharing an origin, which is what lets `docs/scrims.html` read the same IndexedDB read-only; the replay-code field hard-blocking known FACEIT league codes so league maps stay public; and hero guid resolution via `docs/capture/refs.json` plus the page's own role table.

State the invariant that the league dashboard never touches that IndexedDB, and that scrims must not be added into the dashboard build.

- [ ] **Step 5: Run checks and commit**

```bash
.venv/Scripts/python.exe -m pytest tests/test_docs_links.py -v
git add ARCHITECTURE.md
git commit -m "docs: ARCHITECTURE.md sections 6-7 (browser capture, scrims)

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## Task 8: Sections 8-9 — Infrastructure, CI, and data contracts

What runs outside this repository, and the exact shape of every file that crosses a subsystem boundary.

**Files:**
- Modify: `ARCHITECTURE.md` (sections 8, 9)
- Read to verify: `infra/upload-worker/worker.js`, `infra/upload-worker/wrangler.toml`, `infra/upload-worker/DISCORD_SETUP.md`, `.github/workflows/update.yml`, `data/captures/s9/ccarn.json`, `docs/capture/data.json`, `docs/capture/refs.json`

**Interfaces:**
- Consumes: anchors from Tasks 3-7.
- Produces: anchors `#8-infrastructure-and-ci`, `#9-data-contracts`.

- [ ] **Step 1: Read the CI workflow end to end**

Read `.github/workflows/update.yml` and record: the schedule, the `repository_dispatch` trigger, the Actions cache holding `faceit.sqlite3`, the export invocation and its flags, and what it commits.

- [ ] **Step 2: Read the Worker**

Read `infra/upload-worker/worker.js` and record its routes, the Durable Object used for scouting claims, the Discord auth flow, and `CURRENT_SEASON`. Note in the document that `wrangler deploy` is run by the human and bypasses git and GitHub Pages entirely.

- [ ] **Step 3: Sample the real data files**

```bash
.venv/Scripts/python.exe -c "import json;d=json.load(open('data/captures/s9/ccarn.json'));print(type(d));print(json.dumps(d if isinstance(d,dict) else d[0],indent=2)[:1500])"
```

Repeat for `docs/capture/data.json` and `docs/capture/refs.json`. Document the shapes observed, not the shapes assumed.

- [ ] **Step 4: Write section 8**

Follow the five-part template. Must state that `.github/workflows/update.yml` is the **only** writer of `docs/index.html`, and must explain the two-independent-copies problem: the local `faceit.sqlite3` and CI's cached copy both rebuild from the same API and nothing reconciles them, so a local `export` can regress CI's fresher data.

- [ ] **Step 5: Write section 9**

One subsection per artifact, each with a fenced JSON example trimmed to the illustrative fields, plus a note on who writes it and who reads it. Cover: `data/captures/<season>/<contributor>.json`, `owdb_comps.json`, `docs/capture/data.json`, `docs/capture/refs.json`, and the inlined dashboard data blob.

State the rule that `data/captures/` is committed while `owdb_comps.json` is generated at build and deliberately not committed, so analysis improvements apply retroactively — and that the CI merge resolves contested maps first-wins by commit date.

- [ ] **Step 6: Run checks and commit**

```bash
.venv/Scripts/python.exe -m pytest tests/test_docs_links.py -v
git add ARCHITECTURE.md
git commit -m "docs: ARCHITECTURE.md sections 8-9 (infra/CI, data contracts)

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## Task 9: Sections 10-13 — Lifecycles, glossary, invariants, testing map

The operational half: recurring procedures, the project's vocabulary, the rules that must not be broken, and how to prove nothing is broken.

**Files:**
- Modify: `ARCHITECTURE.md` (sections 10, 11, 12, 13)
- Read to verify: `specs/2026-08-10-season10-cutover-design.md`, `owdb/db.py`, `tools/build_capture_data.py`, `pyproject.toml`

**Interfaces:**
- Consumes: all anchors from Tasks 3-8.
- Produces: anchors `#10-lifecycles-and-operations`, `#11-glossary`, `#12-invariants`, `#13-testing-map`.

- [ ] **Step 1: Write section 10 — Lifecycles and operations**

Three numbered procedures. **Code wipe:** update `owdb/db.py` `_SEED_WIPES` and `tools/build_capture_data.py` `CODE_WIPE_DATE` together, plus the pinned assertions in `owdb/tests/test_codes.py` and `owdb/tests/test_context.py`. **Season cutover:** summarise and link `specs/2026-08-10-season10-cutover-design.md` — do not restate its detail, and note that it is deliberately deferred until Season 9 finishes. **Deploying each piece:** the site via CI, the Worker via human-run `wrangler deploy`, the capture app via GitHub Pages.

- [ ] **Step 2: Write section 11 — Glossary**

A two-column table. Minimum entries: replay code, code wipe, veto, comp, comp family, sub-role, swap, division, tier, region, season, observation, capture, contributor, curator, claim, scrim, and any term used in earlier sections that a newcomer would not know.

- [ ] **Step 3: Write section 12 — Invariants**

A numbered list. Each entry is one imperative sentence followed by the failure mode. Minimum set:

1. Never hand-edit `docs/index.html` — CI regenerates it from `faceit_sync/dashboard/head.html` on every run and the edit is lost.
2. Never run `faceit-sync export` locally to "just regenerate" the site — the local `faceit.sqlite3` may be stale and the export overwrites CI's fresher match data.
3. Always run `tests/test_export.py::test_dashboard_javascript_is_syntactically_valid` after editing any file under `faceit_sync/dashboard/` — a JS syntax error renders a blank page silently.
4. Never let the two code-wipe dates drift apart.
5. Never bump the IndexedDB schema version from `docs/scrims.html` — it is a read-only consumer of the capture app's store.
6. Never commit `owdb_comps.json` — a stale report would outlive the observations it came from.
7. Never change the client's User-Agent to impersonate a browser — FACEIT's edge returns 403.
8. Never add scrims into the dashboard build — the private side stays separate.
9. Always `git fetch` before pushing — CI auto-commits to `origin/main` every few minutes.

- [ ] **Step 4: Write section 13 — Testing map**

A table mapping each subsystem to its guarding test files, using the real filenames from `tests/` and `owdb/tests/`. Then the verification commands: the full suite, a single test, keyword selection, `mypy`, and the three tests that must always run after touching the dashboard.

- [ ] **Step 5: Run the full suite and commit**

```bash
.venv/Scripts/python.exe -m pytest
.venv/Scripts/python.exe -m mypy faceit_sync
git add ARCHITECTURE.md
git commit -m "docs: ARCHITECTURE.md sections 10-13 (ops, glossary, invariants, tests)

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## Task 10: `CHANGELOG.md`

Reconstructs the project's story from 429 human commits so the history stops living only in commit messages.

**Files:**
- Create: `CHANGELOG.md`

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces: `CHANGELOG.md`, referenced by `ARCHITECTURE.md` section 2 and `AGENTS.md`.

- [ ] **Step 1: Extract the human commit history**

```bash
git log --reverse --date=short --format='%ad|%h|%s' \
  | grep -v -E 'Auto-update dashboard|Merge remote-tracking' \
  > "$TMPDIR/owdb-history.txt"
```

Use the scratchpad directory for the temporary file. Expected: roughly 429 lines spanning 2026-07-09 to 2026-08-11.

- [ ] **Step 2: Write the file header**

`CHANGELOG.md` opens with the title, a line stating the format is based on Keep a Changelog, and an explicit note that entries are **date-based, not semantic versions**, because the project has no version tags and ships continuously to a live site.

Then a short maintenance note:

```markdown
> **Maintaining this:** add an entry when a change is user-visible on
> owdb.io, changes a data contract, or changes an operational procedure.
> Routine refactors, test-only changes, and the automated dashboard data
> refreshes do not need entries.
```

- [ ] **Step 3: Write the dated entries**

Reverse-chronological. One `## YYYY-MM-DD` heading per day that had human commits, with `### Added` / `### Changed` / `### Fixed` / `### Removed` subsections as applicable. Group related commits into a single readable entry rather than transcribing commit subjects one-to-one — the point is the story, not the log.

- [ ] **Step 4: Add the CI note**

Under a `## About the automated commits` heading at the bottom, state that `.github/workflows/update.yml` has produced 261 `Auto-update dashboard` and merge commits over this period, that they carry data refreshes rather than code changes, and that they are intentionally excluded from the entries above.

- [ ] **Step 5: Commit**

```bash
git add CHANGELOG.md
git commit -m "docs: add CHANGELOG.md reconstructed from git history

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## Task 11: `AGENTS.md` and the `CLAUDE.md` pointer

Gives every coding agent the same project context. Today only Claude Code loads `CLAUDE.md`; opencode, Codex, Cursor, and Amp read `AGENTS.md`, which does not exist.

**Files:**
- Create: `AGENTS.md`
- Modify: `CLAUDE.md` (replaced with a pointer)

**Interfaces:**
- Consumes: all `ARCHITECTURE.md` anchors from Tasks 3-9, and `CHANGELOG.md` from Task 10.
- Produces: nothing later tasks depend on.

- [ ] **Step 1: Create `AGENTS.md` from the current `CLAUDE.md` content**

Keep inline, because an agent needs them without a second file read: the commands section, the gotchas, the codebase conventions, and the roadmap and priorities.

Replace the architecture prose with a pointer block naming the specific anchors, for example:

```markdown
## Architecture

`ARCHITECTURE.md` is the full explanation — read it before deep work.
Fast paths:

- Ingest and the data hazards: `ARCHITECTURE.md` §3
- How `docs/index.html` is built: `ARCHITECTURE.md` §4
- The capture pipeline: `ARCHITECTURE.md` §5-6
- File formats crossing a boundary: `ARCHITECTURE.md` §9
- **Rules that must not be broken: `ARCHITECTURE.md` §12**
```

Restate the invariants list imperatively with failure modes, matching `ARCHITECTURE.md` section 12 exactly — the same nine rules, same wording, so the two files cannot drift into disagreement.

- [ ] **Step 2: Reduce `CLAUDE.md` to a pointer**

Replace the entire contents of `CLAUDE.md` with:

```markdown
# CLAUDE.md

**The canonical instructions for this repository live in `AGENTS.md`. Read it
first.** It is the cross-agent standard file, so Claude Code, opencode, Codex,
and Cursor all work from the same context.

`ARCHITECTURE.md` explains how every part of the project works and how the
parts connect. `CHANGELOG.md` records what changed and when.

Nothing else belongs in this file — anything Claude-Code-specific that is worth
keeping should be added here explicitly, and everything else goes in
`AGENTS.md`.
```

- [ ] **Step 3: Verify the split lost nothing**

```bash
git show HEAD:CLAUDE.md > "$TMPDIR/claude-md-before.md"
```

Read the saved copy against the new `AGENTS.md` section by section and confirm every instruction survived, either inline or as a pointer into `ARCHITECTURE.md`. Anything dropped must be dropped deliberately, not by accident.

- [ ] **Step 4: Run the full suite**

```bash
.venv/Scripts/python.exe -m pytest
.venv/Scripts/python.exe -m mypy faceit_sync
```

Expected: both clean.

- [ ] **Step 5: Commit**

```bash
git add AGENTS.md CLAUDE.md
git commit -m "docs: make AGENTS.md canonical, reduce CLAUDE.md to a pointer

opencode, Codex, and Cursor read AGENTS.md by convention and previously
started with no project context at all. One file now serves every agent.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## Task 12: Final verification and push

**Files:** none modified; verification only.

**Interfaces:**
- Consumes: everything.
- Produces: pushed `origin/main`.

- [ ] **Step 1: Full verification**

```bash
.venv/Scripts/python.exe -m pytest
.venv/Scripts/python.exe -m mypy faceit_sync
git status --short
```

Expected: suite passes, mypy clean, working tree clean.

- [ ] **Step 2: Confirm the document reads correctly end to end**

Read `ARCHITECTURE.md` start to finish in one pass. Check that the table of contents links resolve, that no section contradicts another, and that sections 12 and `AGENTS.md` state the same invariants in the same words.

- [ ] **Step 3: Fetch, merge CI's commits, push**

```bash
git fetch origin
git merge origin/main
```

CI commits to `origin/main` every few minutes, so expect a merge. Resolve any conflict by keeping CI's data and reapplying the documentation diff on top. Then:

```bash
.venv/Scripts/python.exe -m pytest
git push origin main
```

Re-run the suite after the merge before pushing — the merge can bring in changes that the documentation now describes incorrectly.

---

## Self-Review

**Spec coverage:** Deliverable 1 (`ARCHITECTURE.md`, 14 sections) → Tasks 2, 3, 4, 5, 6, 7, 8, 9. Deliverable 2 (cleanup) → Task 1. Deliverable 3 (`CHANGELOG.md`) → Task 10. Deliverable 4 (`AGENTS.md`/`CLAUDE.md`) → Task 11. Spec verification section → Tasks 2 and 12. Spec accuracy requirement → enforced by `tests/test_docs_links.py` (Task 2) and by the explicit read-and-verify step opening each of Tasks 4-9.

**Placeholder scan:** No TBD/TODO. Each section-writing step names its required content explicitly rather than saying "write the section". The link-checker test is given in full, working form.

**Type consistency:** `tests/test_docs_links.py` defines `RUNTIME_PATHS`, `_cited_paths`, `REPO_ROOT`, and `DOC` in Task 2; Tasks 3-9 reference only `RUNTIME_PATHS` and the two test names, all as defined. Section anchors produced by each task match the exact headings fixed in Task 2 Step 3.

**One gap found and closed:** the spec's cleanup list did not say what happens if a cited runtime-generated path is absent from a fresh clone; Task 2 resolves this with the `RUNTIME_PATHS` allowlist, and Task 3 Step 6 states the rule for extending it.

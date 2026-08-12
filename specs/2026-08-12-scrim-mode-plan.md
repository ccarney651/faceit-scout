# Scrim Mode — Phases 0 & 1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stop the two capture pages being hand-maintained forks of each other, then un-pause scrim capture with a session scaffolded from the Overwatch replay-history screenshot, guarded by a real league-code block.

**Architecture:** `docs/capture/index.html` and `docs/capture/scrim.html` currently duplicate 104 named functions, 44 of which have silently diverged. Phase 0 extracts the shared, low-divergence subsystems into UMD modules under `docs/capture/engine/`, following the existing `scoreboard.js` pattern, one module per commit, with the league flow unchanged at every step. Phase 1 then removes the pause overlay and builds session scaffolding on top of the already-tested `parseScrimSessionText()`.

**Tech Stack:** Vanilla browser JS (no build step, no bundler), UMD modules, IndexedDB, `node --test` for JS unit tests, pytest as the runner of record, Python 3 + mypy for `faceit_sync`.

## Global Constraints

- **Dev Python is the venv binary:** `.venv/Scripts/python.exe -m pytest`. Never bare `python`.
- **Never hand-edit `docs/index.html`.** CI regenerates it from `faceit_sync/dashboard/head.html`.
- **Never run `faceit-sync export` locally.** The local `faceit.sqlite3` is days behind CI's.
- **Never bump the IndexedDB schema version from `docs/scrims.html`.** It is a read-only consumer.
- **Never commit `owdb_comps.json`.**
- **Never put developer documentation in `docs/`.** That is the published web root; specs and plans go in `specs/`.
- **All work happens on branch `scrim-mode`, never on `main`.** CI auto-commits to `origin/main` every few minutes.
- **The capture pages' CSP lives in a `<meta>` tag,** not a header. Any new script file must be permitted by it — check it first when a script silently fails to load.
- **Branding is "OWDB".** The IndexedDB name `owscout-capture` is deliberately unchanged until the Season 10 cutover.
- **Every task ends green:** `.venv/Scripts/python.exe -m pytest` passes in full before the commit.

---

## File Structure

**Created:**

| File | Responsibility |
| --- | --- |
| `docs/capture/engine/util.js` | String escaping, CSS injection, base64, DOM-free helpers |
| `docs/capture/engine/idb.js` | IndexedDB open/read/write helpers |
| `docs/capture/engine/names.js` | Player-name normalisation, similarity, roster affinity |
| `docs/capture/engine/frames.js` | Screen share lifecycle, frame grab, greyscale canvases |
| `docs/capture/engine/calibration.js` | Box picking, auto-calibrate, calibration preview and overlay |
| `docs/capture/engine/refs.js` | Hero portrait recognition, learned refs, OCR worker |
| `docs/capture/engine/overlay.js` | Floating capture console (picture-in-picture panel) |
| `docs/capture/engine/tour.js` | First-visit guided tour |
| `docs/capture/engine/session.js` | Scrim session scaffold: league-code block, wipe check, row building |
| `tests/test_capture_js_units.py` | Runs `node --test` over `docs/capture/`, so JS unit tests execute in CI |
| `docs/capture/engine/names.test.js` | JS unit tests for `names.js` |
| `docs/capture/engine/session.test.js` | JS unit tests for `session.js` |

**Modified:** `docs/capture/index.html`, `docs/capture/scrim.html`, `ARCHITECTURE.md`, `AGENTS.md`, `CHANGELOG.md`.

**Deferred to phase 3, deliberately:** `docs/capture/engine/snapshot.js`. The snapshot/review/finish cluster is where divergence is worst — `renderReview` differs by 1959 characters, `snapshot` by 1139, and `finishMap` is 1530 characters in `index.html` against a **110-character stub** in `scrim.html`. Phase 3 rewrites the scrim finish flow anyway ("skip to the end of the map, confirm the final read"), so extracting it now would mean reconciling it twice. It stays forked until then.

### The module contract

Every engine module follows `docs/capture/scoreboard.js` exactly: an IIFE that assigns to `module.exports` under Node and to a global under the browser. DOM-coupled modules take a **context object** rather than reaching for globals, so page-specific behaviour is injected instead of branched on:

```js
// docs/capture/engine/<name>.js
(function (global) {
  'use strict';
  function make(ctx) { /* ctx = {doc, els, on, ...} */ }
  var Mod = { make: make /* + pure helpers */ };
  if (typeof module !== 'undefined' && module.exports) module.exports = Mod;
  else global.OWDBMod = Mod;
})(typeof self !== 'undefined' ? self : this);
```

Pure functions are exported directly (testable under Node with no stubs); stateful ones come from `make(ctx)`.

### The reconciliation rule

44 of the 104 shared functions have diverged. **Every extraction task must classify each function it moves** into exactly one of three buckets, and record the classification in the commit message:

| Bucket | Meaning | Action |
| --- | --- | --- |
| **Identical** | Bodies match after whitespace normalisation | Move as-is |
| **Cosmetic** | Differ only in string encoding or formatting — e.g. `calMsg` uses a literal `—` in `index.html` and `—` in `scrim.html` | Move either; prefer `index.html`'s |
| **Real drift** | Behaviour differs — e.g. `simScore` normalises via `_normName()` in `index.html` but only `toLowerCase().trim()` in `scrim.html` | **Take the superset, state why in the commit, and confirm existing tests still pass** |
| **By design** | Legitimately page-specific — e.g. `stopCapture` calls `releaseClaim()` in `index.html` (live-scouting claims) and must not in `scrim.html` | Inject via `ctx`; never branch on page identity inside the module |

To regenerate the classification at any time:

```bash
.venv/Scripts/python.exe tools/capture_divergence.py
```

(That tool is built in Task 2.)

---

# PHASE 0 — Extract the shared engine

## Task 1: Make JS unit tests actually run

`docs/capture/scoreboard.test.js` exists, contains 9 passing tests, and **is executed by nothing** — not pytest, not CI, and there is no root `package.json` script. Every module this plan creates would inherit that fate. Fix the runner before writing any module.

**Files:**
- Create: `tests/test_capture_js_units.py`
- Test: itself

**Interfaces:**
- Consumes: nothing
- Produces: a pytest test that runs `node --test docs/capture/`, so any `*.test.js` under `docs/capture/` (including `engine/`) executes in the suite of record. Later tasks rely on this and add only `.test.js` files.

- [ ] **Step 1: Write the test**

```python
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
```

- [ ] **Step 2: Run it and confirm it passes against the existing suite**

Run: `.venv/Scripts/python.exe -m pytest tests/test_capture_js_units.py -v`
Expected: PASS. This retroactively activates `scoreboard.test.js`'s 9 tests.

- [ ] **Step 3: Prove the runner actually fails on a broken test**

A runner that always passes is worse than none. Temporarily append to `docs/capture/scoreboard.test.js`:

```js
test('DELIBERATE FAILURE — remove me', () => { assert.equal(1, 2); });
```

Run: `.venv/Scripts/python.exe -m pytest tests/test_capture_js_units.py -v`
Expected: FAIL, with the failing test name visible in the captured output.

- [ ] **Step 4: Remove the deliberate failure and re-run**

Run: `.venv/Scripts/python.exe -m pytest tests/test_capture_js_units.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git checkout -b scrim-mode
git add tests/test_capture_js_units.py
git commit -m "Run the capture app's JS unit tests under pytest

scoreboard.test.js held 9 passing tests that nothing executed - not pytest,
not CI, and there is no root package.json script. Every engine module the
scrim work adds would have inherited that. pytest is the suite of record, so
JS unit tests now run from it."
```

---

## Task 2: Freeze the divergence report as a tool

Every later task needs to know which functions diverged and how. Reading it by eye is how drift gets re-introduced.

**Files:**
- Create: `tools/capture_divergence.py`
- Test: `tests/test_capture_divergence.py`

**Interfaces:**
- Consumes: nothing
- Produces: `classify(name) -> "identical" | "diverged"` and a `main()` printing the report. Later tasks run this to fill in their commit-message classification.

- [ ] **Step 1: Write the failing test**

```python
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
```

- [ ] **Step 2: Run it to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/test_capture_divergence.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'tools.capture_divergence'`

- [ ] **Step 3: Write the implementation**

```python
"""Compare the two capture pages' shared JavaScript functions.

docs/capture/index.html and scrim.html were forked, not shared: 104 named
functions exist in both and many have drifted. Engine extraction has to know
which, so it reconciles deliberately instead of silently picking one copy.

    .venv/Scripts/python.exe tools/capture_divergence.py
"""

from __future__ import annotations

import re
from pathlib import Path

CAPTURE = Path(__file__).resolve().parents[1] / "docs" / "capture"
FUNC = re.compile(r"(?:^|\s)(?:async\s+)?function\s+([A-Za-z0-9_]+)\s*\(")


def function_bodies(filename: str) -> dict[str, str]:
    """Map every top-level named function to its brace-balanced body."""
    src = (CAPTURE / filename).read_text(encoding="utf-8")
    out: dict[str, str] = {}
    for m in FUNC.finditer(src):
        start = src.index("{", m.end() - 1)
        depth, i = 0, start
        while i < len(src):
            if src[i] == "{":
                depth += 1
            elif src[i] == "}":
                depth -= 1
                if depth == 0:
                    break
            i += 1
        out[m.group(1)] = src[start : i + 1]
    return out


def _norm(body: str) -> str:
    return re.sub(r"\s+", " ", body).strip()


def report() -> dict[str, list[str]]:
    a, b = function_bodies("index.html"), function_bodies("scrim.html")
    shared = sorted(set(a) & set(b))
    return {
        "shared": shared,
        "identical": [n for n in shared if _norm(a[n]) == _norm(b[n])],
        "diverged": [n for n in shared if _norm(a[n]) != _norm(b[n])],
    }


def main() -> None:
    rep = report()
    print(f"shared: {len(rep['shared'])}  "
          f"identical: {len(rep['identical'])}  "
          f"diverged: {len(rep['diverged'])}")
    a, b = function_bodies("index.html"), function_bodies("scrim.html")
    print("\nDIVERGED (name, index chars, scrim chars):")
    for n in sorted(rep["diverged"], key=lambda n: -abs(len(a[n]) - len(b[n]))):
        print(f"  {n:24} {len(a[n]):6} {len(b[n]):6}  {len(b[n]) - len(a[n]):+6}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `.venv/Scripts/python.exe -m pytest tests/test_capture_divergence.py -v`
Expected: PASS

- [ ] **Step 5: Run the tool and read the report**

Run: `.venv/Scripts/python.exe tools/capture_divergence.py`
Expected: `shared: 104  identical: 60  diverged: 44`

- [ ] **Step 6: Commit**

```bash
git add tools/capture_divergence.py tests/test_capture_divergence.py
git commit -m "Add the capture-page divergence report

The two capture pages share 104 named functions and 44 have drifted. Engine
extraction needs that list mechanically, not by eye, so each move reconciles
deliberately rather than silently adopting whichever copy was pasted last."
```

---

## Task 3: Extract `names.js` — and fix the drift it exposes

Start here rather than with `util.js`: `names.js` is pure, already has pytest coverage through `test_capture_scrim.py`, and contains the **worked example of real drift**. `simScore` in `index.html` normalises through `_normName()`; in `scrim.html` it only does `toLowerCase().trim()`. The scrim page carries the weaker normaliser — and it is exactly the code that phase 2 points at battletag matching.

**Files:**
- Create: `docs/capture/engine/names.js`, `docs/capture/engine/names.test.js`
- Modify: `docs/capture/index.html`, `docs/capture/scrim.html`
- Test: `docs/capture/engine/names.test.js`, plus existing `tests/test_capture_scrim.py`

**Interfaces:**
- Consumes: nothing
- Produces: global `OWDBNames` / CommonJS export with:
  - `normName(s) -> string`
  - `simScore(a, b) -> number` (0–200 scale, unchanged)
  - `affinity(names, roster) -> number`
  - `confidentOrientation(leftNames, rightNames, aRoster, bRoster) -> 'a' | 'b' | null`
  - constants `AUTO_SIDE_MARGIN = 100`, `STRONG_NAME_SCORE = 75`, `MIN_STRONG_NAMES = 2`

- [ ] **Step 1: Write the failing JS test**

Create `docs/capture/engine/names.test.js`:

```js
const test = require('node:test');
const assert = require('node:assert');
const Names = require('./names.js');

test('normName folds case and trims', () => {
  assert.equal(Names.normName('  Kirbz  '), 'kirbz');
});

test('normName drops a battletag discriminator', () => {
  // The ready-up list renders the real battletag; stored game_name values
  // carry no discriminator, so both forms must compare equal.
  assert.equal(Names.normName('Kirbz#2183'), Names.normName('Kirbz'));
});

test('simScore is 200 for an exact match and 0 for empties', () => {
  assert.equal(Names.simScore('Kirbz', 'Kirbz'), 200);
  assert.equal(Names.simScore('', ''), 0);
});

test('simScore ignores case and surrounding whitespace', () => {
  assert.equal(Names.simScore(' KIRBZ ', 'kirbz'), 200);
});

test('simScore scores a one-character OCR miss below exact but well above zero', () => {
  const s = Names.simScore('Kirbz', 'Klrbz');
  assert.ok(s > 100 && s < 200, `expected partial score, got ${s}`);
});

test('affinity sums each name best match against the roster', () => {
  const roster = ['Kirbz', 'Vega'];
  assert.equal(Names.affinity(['Kirbz'], roster), 200);
  assert.equal(Names.affinity([], roster), 0);
});

test('confidentOrientation returns null when the sides are indistinguishable', () => {
  const r = ['One', 'Two'];
  assert.equal(Names.confidentOrientation(r, r, r, r), null);
});

test('confidentOrientation picks the direct orientation when the left side matches roster a', () => {
  const ours = ['Alison', 'Sivaartt', 'Kroxz', 'Zorrow', 'Benislover'];
  const theirs = ['One', 'Two', 'Three', 'Four', 'Five'];
  assert.equal(Names.confidentOrientation(ours, theirs, ours, theirs), 'a');
});

test('confidentOrientation detects a swap', () => {
  const ours = ['Alison', 'Sivaartt', 'Kroxz', 'Zorrow', 'Benislover'];
  const theirs = ['One', 'Two', 'Three', 'Four', 'Five'];
  assert.equal(Names.confidentOrientation(theirs, ours, ours, theirs), 'b');
});
```

- [ ] **Step 2: Run it to verify it fails**

Run: `cd docs/capture && node --test engine/names.test.js`
Expected: FAIL — `Cannot find module './names.js'`

- [ ] **Step 3: Create the module**

Create `docs/capture/engine/names.js`. Move `_normName`, `_matchTotal`, `simScore`, `affinity`, `confidentOrientation` and the three constants out of `index.html`, wrapped in the UMD shell from the module contract above.

**Reconciliation decisions for this task, to be restated in the commit message:**

| Function | Bucket | Decision |
| --- | --- | --- |
| `_matchTotal` | Identical | Move as-is |
| `affinity` | Identical | Move as-is |
| `confidentOrientation` | Identical | Move as-is |
| `simScore` | **Real drift** | Take `index.html`'s `_normName()` version. `scrim.html`'s `toLowerCase().trim()` is the older, weaker form, and phase 2 aims this function at battletag matching |
| `_normName` | Only in `index.html` | Move, and **extend it to strip a `#` discriminator** per the design's §4.2 normalisation rule |

`normName` must be exported (the tests above call it directly) and must: casefold, trim, and drop everything from the first `#` onward.

- [ ] **Step 4: Run the JS tests to verify they pass**

Run: `cd docs/capture && node --test engine/names.test.js`
Expected: PASS, 9 tests

- [ ] **Step 5: Wire both pages to the module**

In **both** `docs/capture/index.html` and `docs/capture/scrim.html`, add before the main inline script:

```html
<script src="engine/names.js"></script>
```

Then delete the moved function definitions from both pages' inline scripts and add, at the top of each inline script:

```js
const {normName, simScore, affinity, confidentOrientation,
       AUTO_SIDE_MARGIN, STRONG_NAME_SCORE, MIN_STRONG_NAMES} = OWDBNames;
```

- [ ] **Step 6: Update the pytest extraction anchors**

`tests/test_capture_scrim.py` slices `scrim.html` between literal anchors, and one of them is `const AUTO_SIDE_MARGIN=` — which this task deletes from the page. Change `_pure_js()` so the roster-similarity cluster is loaded from the module instead of scraped from the HTML:

```python
def _pure_js() -> str:
    """Cluster A: the map list. Cluster C: the screenshot-import parser.

    The roster-similarity helpers (formerly cluster B) moved to
    docs/capture/engine/names.js in the engine extraction; they are loaded
    from the module now rather than sliced out of the page.
    """
    engine = (APP.parent / "engine" / "names.js").read_text(encoding="utf-8")
    return "\n".join([
        engine,
        "const {normName,simScore,affinity,confidentOrientation}=module.exports;",
        _extract(
            ("const CONTROL_SUBMAPS=", "const AUTO_SIDE_MARGIN="),
            ("function bestMapMatch(text)", "async function importSessionFromScreenshot(file)"),
        ),
    ])
```

Add `var module={exports:{}};` to `_STUBS` so the UMD wrapper takes the CommonJS branch.

- [ ] **Step 7: Run the full suite**

Run: `.venv/Scripts/python.exe -m pytest`
Expected: PASS, including the three `test_auto_side_*` tests and the script-validity tests for all three pages.

- [ ] **Step 8: Verify both pages still load in a browser**

Build nothing — open the files directly. Confirm no console errors and that hero portraits still read on a calibrated screen share. The dashboard's blank-page failure mode applies here too: a JS error yields a dead page that a syntax check will not catch.

- [ ] **Step 9: Commit**

```bash
git add docs/capture/engine/names.js docs/capture/engine/names.test.js \
        docs/capture/index.html docs/capture/scrim.html tests/test_capture_scrim.py
git commit -m "Extract names.js from both capture pages

First engine module. Reconciliation: _matchTotal, affinity and
confidentOrientation were identical; simScore had really drifted - index.html
normalised through _normName() while scrim.html only lowercased and trimmed.
Took index.html's, since phase 2 aims this function at battletag matching and
the scrim page carried the weaker normaliser.

normName now also strips a # discriminator, so a ready-up battletag compares
equal to the stored game_name."
```

---

## Task 4: Extract `util.js`

**Files:**
- Create: `docs/capture/engine/util.js`
- Modify: `docs/capture/index.html`, `docs/capture/scrim.html`

**Interfaces:**
- Consumes: nothing
- Produces: global `OWDBUtil` with `esc(s)`, `css(text)`, `scl(n)`, `ico(name)`, `evp(e)`, `b64bytes(s)`, `bytesToB64(bytes)`, `isTyping(el)`, `toast(msg)`, `uiModal(opts)`, `uiConfirm(msg)`

- [ ] **Step 1: Confirm the divergence classification for this module's functions**

Run: `.venv/Scripts/python.exe tools/capture_divergence.py`
Expected: of this module's functions only `uiModal` appears in the diverged list, at +9 characters — a cosmetic difference. Everything else is identical. If the report disagrees, stop and reclassify before moving anything.

- [ ] **Step 2: Create the module**

Create `docs/capture/engine/util.js` with the UMD shell, moving `esc`, `css`, `scl`, `ico`, `evp`, `b64bytes`, `bytesToB64`, `isTyping`, `toast`, `uiModal`, `uiConfirm` from `index.html`. Take `index.html`'s `uiModal`.

`toast`, `uiModal` and `uiConfirm` touch the DOM but only through `document`, which both pages provide identically — they move as plain functions, not through `make(ctx)`.

- [ ] **Step 3: Wire both pages**

Add `<script src="engine/util.js"></script>` before the inline script in both pages, delete the moved definitions, and destructure at the top of each inline script:

```js
const {esc, css, scl, ico, evp, b64bytes, bytesToB64, isTyping,
       toast, uiModal, uiConfirm} = OWDBUtil;
```

- [ ] **Step 4: Run the full suite**

Run: `.venv/Scripts/python.exe -m pytest`
Expected: PASS

- [ ] **Step 5: Load both pages in a browser and confirm no console errors**

Specifically exercise a modal (the "Import…" button) and a toast, since those have no automated coverage.

- [ ] **Step 6: Commit**

```bash
git add docs/capture/engine/util.js docs/capture/index.html docs/capture/scrim.html
git commit -m "Extract util.js from both capture pages

Reconciliation: all identical except uiModal, which differed cosmetically
(+9 chars); took index.html's."
```

---

## Task 5: Extract `idb.js`

**Files:**
- Create: `docs/capture/engine/idb.js`
- Modify: `docs/capture/index.html`, `docs/capture/scrim.html`

**Interfaces:**
- Consumes: nothing
- Produces: global `OWDBIdb` with `open(version, stores)`, `getAll(store)`, `putIn(store, rec)`, `clear(store)`

- [ ] **Step 1: Read both copies of `idb` before moving anything**

Run: `.venv/Scripts/python.exe tools/capture_divergence.py`
Expected: `idb` diverged by +57 characters. This one is **not** cosmetic — the two pages own different object stores. `index.html` creates `maps`, `refs`, `heroes`; `scrim.html` additionally creates `scrims` and `scrim_maps`.

- [ ] **Step 2: Move `idb` with the store list injected**

This is the **by design** bucket. The module must not know which page it is on:

```js
// open(version, stores) — the caller owns its store list. scrim.html adds
// 'scrims' and 'scrim_maps' to the three the league page creates. The schema
// version is owned by the capture app; docs/scrims.html opens without a
// version and must never trigger an upgrade.
function open(version, stores) { /* ... */ }
```

Both pages then pass their own list. Keep the current schema version (4) unchanged — this task must not trigger an IndexedDB upgrade for anyone.

- [ ] **Step 3: Wire both pages and delete the moved definitions**

- [ ] **Step 4: Run the full suite**

Run: `.venv/Scripts/python.exe -m pytest`
Expected: PASS

- [ ] **Step 5: Verify no schema upgrade fires**

Open `docs/capture/index.html` in a browser with existing capture data, then `docs/capture/scrim.html`, then `docs/scrims.html`. Confirm in DevTools → Application → IndexedDB that `owscout-capture` is still at version 4 and existing records are intact. **A lost `refs` store costs a contributor every hero they have taught.**

- [ ] **Step 6: Commit**

```bash
git add docs/capture/engine/idb.js docs/capture/index.html docs/capture/scrim.html
git commit -m "Extract idb.js from both capture pages

The two copies differed by design, not drift: index.html creates maps/refs/
heroes, scrim.html adds scrims/scrim_maps. open() now takes the store list
from its caller instead of the module knowing which page it is on. Schema
version stays at 4 - this must not trigger an upgrade."
```

---

## Task 6: Extract `frames.js`

**Files:**
- Create: `docs/capture/engine/frames.js`
- Modify: `docs/capture/index.html`, `docs/capture/scrim.html`

**Interfaces:**
- Consumes: `OWDBUtil`
- Produces: global `OWDBFrames` with `make(ctx) -> {ensureWork, grabFrame, grayCanvas, cellGrayPadded, nameCanvas, detectContentRect, stopCapture, togglePreview, readyForCapture}` where `ctx = {doc, video, onStop}`

- [ ] **Step 1: Classify this module's functions**

Run: `.venv/Scripts/python.exe tools/capture_divergence.py`
Expected: only `stopCapture` diverges, at −16 characters. This is the **by design** worked example — `index.html` calls `releaseClaim()` (live-scouting claims, which scrims do not have) and `scrim.html` does not.

- [ ] **Step 2: Move the cluster, injecting the teardown hook**

`stopCapture` takes its page-specific teardown from `ctx.onStop`:

```js
// index.html passes onStop: releaseClaim
// scrim.html passes onStop: null — scrims have no live-scouting claims
function stopCapture() {
  clearCalPreview();
  if (ctx.video.srcObject) {
    ctx.video.srcObject.getTracks().forEach(function (t) { t.stop(); });
    ctx.video.srcObject = null;
  }
  if (ctx.onStop) ctx.onStop();
  drawOverlay();
  updateBtns();
  ctx.doc.getElementById('calhint').textContent =
    'Screen capture stopped. Click Share my screen to resume.';
}
```

- [ ] **Step 3: Wire both pages and delete the moved definitions**

- [ ] **Step 4: Run the full suite**

Run: `.venv/Scripts/python.exe -m pytest`
Expected: PASS

- [ ] **Step 5: Verify screen capture end-to-end in a browser**

Share a screen on both pages, confirm the preview renders and "Stop capture" tears down cleanly. On `index.html` confirm the live-scouting claim is still released on stop — that is the injected hook, and nothing automated covers it.

- [ ] **Step 6: Commit**

```bash
git add docs/capture/engine/frames.js docs/capture/index.html docs/capture/scrim.html
git commit -m "Extract frames.js from both capture pages

stopCapture was the by-design case: index.html releases its live-scouting
claim on teardown and scrim.html has no claims. The module takes an onStop
hook rather than branching on which page it is running in."
```

---

## Task 7: Extract `calibration.js`

**Files:**
- Create: `docs/capture/engine/calibration.js`
- Modify: `docs/capture/index.html`, `docs/capture/scrim.html`

**Interfaces:**
- Consumes: `OWDBUtil`, `OWDBFrames`
- Produces: global `OWDBCalibration` with `make(ctx) -> {autoCalibrate, boxesFromStrips, scoreBoxes, pickBox, commitCal, renderCalPreview, clearCalPreview, retryCal, enterFsCal, calMsg, calOk, drawOverlay, fitOverlay}`

- [ ] **Step 1: Classify this module's functions**

Run: `.venv/Scripts/python.exe tools/capture_divergence.py`
Expected diverging members: `autoCalibrate` (−273), `drawOverlay` (+185), `pickBox` (+178), `renderCalPreview` (+20), `calMsg` (+15).

`calMsg` is cosmetic (`—` versus `—`). The other four need reading before moving: `drawOverlay` and `pickBox` are **larger** in `scrim.html`, so the scrim page is ahead here and its version is the likely superset — the opposite of `simScore`. **Do not assume `index.html` always wins.** Read both, take the superset, and record which and why.

- [ ] **Step 2: Move the cluster**

Scoreboard and score-box calibration (`setSb`, `setSr` handlers) exist only on the scrim page. Move the generic box-picking machinery; leave the page's own button wiring in the page.

- [ ] **Step 3: Wire both pages and delete the moved definitions**

- [ ] **Step 4: Run the full suite**

Run: `.venv/Scripts/python.exe -m pytest`
Expected: PASS

- [ ] **Step 5: Verify calibration end-to-end in a browser**

On both pages: share a screen with a live comp visible, run Auto-calibrate, confirm the confidence preview appears and only commits on "Use these boxes", then confirm manual LEFT/RIGHT box dragging still works and fullscreen calibrate opens and exits.

- [ ] **Step 6: Commit**

```bash
git add docs/capture/engine/calibration.js docs/capture/index.html docs/capture/scrim.html
git commit -m "Extract calibration.js from both capture pages

Five members had drifted. calMsg was cosmetic. drawOverlay and pickBox were
LARGER on the scrim page - the scrim copy was ahead, so index.html is not
automatically the superset; each was read and the fuller version taken."
```

---

## Task 8: Extract `refs.js`

**Files:**
- Create: `docs/capture/engine/refs.js`
- Modify: `docs/capture/index.html`, `docs/capture/scrim.html`

**Interfaces:**
- Consumes: `OWDBUtil`, `OWDBIdb`, `OWDBFrames`
- Produces: global `OWDBRefs` with `make(ctx) -> {addRef, bestMatch, matchCrop, learnCrop, refTemplate, exportRefs, importRefs, clearLearnedRefs, heroCatalog, heroName, heroSlug, heroPortrait, onlyLostKnown, ocrWorker}`

- [ ] **Step 1: Classify this module's functions**

Run: `.venv/Scripts/python.exe tools/capture_divergence.py`
Expected diverging members: `ocrWorker` (−433), `onFixPick` (−272), `remapHero` (−178), `bestMatch` (−72), `fixReads` (−36), `importRefs` (+5).

`bestMatch` diverging is the serious one — it is the hero-recognition core, and a difference there means the two pages **recognise heroes differently today**. Read both carefully and record the behavioural difference in the commit message.

- [ ] **Step 2: Check the CSP before touching `ocrWorker`**

The capture pages' Content-Security-Policy lives in a `<meta>` tag and has silently broken tesseract's blob worker before — it cost four sessions once. Read the `<meta http-equiv="Content-Security-Policy">` tag in both pages **before** moving `ocrWorker`, and confirm the module's new path does not violate `script-src`.

- [ ] **Step 3: Move the cluster**

- [ ] **Step 4: Run the full suite**

Run: `.venv/Scripts/python.exe -m pytest`
Expected: PASS

- [ ] **Step 5: Verify hero recognition end-to-end in a browser**

On both pages with a calibrated share: confirm portraits read correctly, teach a deliberate miss under "Hero recognition", confirm it is learned and persists across a reload, then export and re-import learned refs. Confirm the learned-ref count is unchanged from before this task.

- [ ] **Step 6: Commit**

```bash
git add docs/capture/engine/refs.js docs/capture/index.html docs/capture/scrim.html
git commit -m "Extract refs.js from both capture pages

bestMatch had drifted, which means the two pages were recognising heroes
differently. Reconciled to one implementation so a recognition fix lands
once instead of being remembered twice."
```

---

## Task 9: Extract `overlay.js` and `tour.js`

Two small clusters, both self-contained, committed separately.

**Files:**
- Create: `docs/capture/engine/overlay.js`, `docs/capture/engine/tour.js`
- Modify: `docs/capture/index.html`, `docs/capture/scrim.html`

**Interfaces:**
- Consumes: `OWDBUtil`
- Produces: `OWDBOverlay.make(ctx) -> {popout, maybeAutoPop, gestureAutoPop, setPopBtn, pipColors, pipPanelCss, renderPipControls, restylePipPanel}`; `OWDBTour.make(ctx) -> {open, next, prev, render, tick, highlight, done, isFirstVisit, maybeShow}` where `ctx.steps` is the page's own step list

- [ ] **Step 1: Classify both clusters**

Run: `.venv/Scripts/python.exe tools/capture_divergence.py`
Expected overlay divergence: `popout` (−1348), `renderPipControls` (−1101), `pipPanelCss` (−600), `setPopBtn` (+15), `gestureAutoPop` (−6), `maybeAutoPop` (−5).
Expected tour divergence: `tourDefs` (−77), `isFirstVisit` (−66), `maybeShowTour` (−18), `tourDone` (+5), `updateGuide` (−273).

- [ ] **Step 2: Move the overlay cluster, keeping the control set injected**

The league overlay carries controls the scrim overlay does not — that is why `popout` and `renderPipControls` differ by more than a kilobyte each. **The control list is data, not code:** `ctx.controls` is an array the page supplies, and the module renders whatever it is given.

- [ ] **Step 3: Commit the overlay extraction**

```bash
git add docs/capture/engine/overlay.js docs/capture/index.html docs/capture/scrim.html
git commit -m "Extract overlay.js from both capture pages

popout and renderPipControls differed by >1KB each because the league overlay
carries controls the scrim one does not. The control set is now data the page
passes in, so the two overlays differ in configuration rather than in code."
```

- [ ] **Step 4: Move the tour cluster, keeping step definitions in the pages**

`tourDefs` is page-specific copy and **stays in each page**; only the tour mechanism moves. Note `updateGuide` is page copy too — leave it in the pages.

- [ ] **Step 5: Run the full suite**

Run: `.venv/Scripts/python.exe -m pytest`
Expected: PASS, including `test_capture_onboarding.py`

- [ ] **Step 6: Verify the tour in a browser**

Clear the first-visit marker in localStorage on both pages, reload, and confirm the tour opens, steps through, highlights the right elements, and can be skipped.

- [ ] **Step 7: Commit the tour extraction**

```bash
git add docs/capture/engine/tour.js docs/capture/index.html docs/capture/scrim.html
git commit -m "Extract tour.js from both capture pages

Only the mechanism moves; tourDefs and updateGuide are page copy and stay
in their pages."
```

---

## Task 10: Record phase 0 in the docs

**Files:**
- Modify: `ARCHITECTURE.md`, `AGENTS.md`, `CHANGELOG.md`

- [ ] **Step 1: Update `ARCHITECTURE.md` §5-7**

Document `docs/capture/engine/` as the shared engine, list each module's responsibility, state the module contract (UMD, `make(ctx)` for stateful modules), and record that `snapshot.js` remains forked until phase 3 and why.

- [ ] **Step 2: Add a gotcha to `AGENTS.md`**

> **The capture pages share an engine under `docs/capture/engine/`.** A fix to
> calibration, hero recognition, the overlay or name matching belongs in the
> module, not in a page. The snapshot/review/finish cluster is still forked
> between the two pages until phase 3 — check both when touching it.

- [ ] **Step 3: Add a `CHANGELOG.md` entry**

Phase 0 changes no behaviour, but it changes where code lives, which is an operational fact for anyone working in these files.

- [ ] **Step 4: Run the full suite and commit**

```bash
.venv/Scripts/python.exe -m pytest
git add ARCHITECTURE.md AGENTS.md CHANGELOG.md
git commit -m "Document the shared capture engine"
```

---

# PHASE 1 — Un-pause scrims, scaffold a session

## Task 11: Build the league-code block

**Build this before removing the pause overlay.** The page's help text already promises that league codes are blocked, and no code implements it. Un-pausing first would let a league map be recorded as a scrim and silently stay private instead of being published.

**Files:**
- Create: `docs/capture/engine/session.js`, `docs/capture/engine/session.test.js`
- Modify: `docs/capture/scrim.html`

**Interfaces:**
- Consumes: nothing
- Produces: global `OWDBSession` with:
  - `norm(code) -> string` — trimmed, upper-cased
  - `buildCodeIndex(data) -> {codes: Set<string>, byCode: Object, wipeDate: string|null}` from a parsed `data.json`
  - `classifyCode(code, index, played) -> {league: boolean, dead: boolean, division: string|null}`, where `played` is the session's ISO date (`YYYY-MM-DD`)

- [ ] **Step 1: Write the failing JS test**

Create `docs/capture/engine/session.test.js`:

```js
const test = require('node:test');
const assert = require('node:assert');
const Session = require('./session.js');

const DATA = {
  code_wipe_date: '2026-08-11',
  codes: [
    { code: 'E39856', map: 'Oasis', division: 'EMEA Master' },
    { code: 'ABCD12', map: 'Ilios', division: 'NA Expert' },
  ],
};

test('buildCodeIndex collects league codes and the wipe date', () => {
  const idx = Session.buildCodeIndex(DATA);
  assert.equal(idx.wipeDate, '2026-08-11');
  assert.ok(idx.codes.has('E39856'));
  assert.equal(idx.codes.size, 2);
});

test('buildCodeIndex tolerates a missing or empty feed', () => {
  const idx = Session.buildCodeIndex({});
  assert.equal(idx.wipeDate, null);
  assert.equal(idx.codes.size, 0);
});

test('a league code is flagged, with its division', () => {
  const idx = Session.buildCodeIndex(DATA);
  const got = Session.classifyCode('E39856', idx, '2026-08-12');
  assert.equal(got.league, true);
  assert.equal(got.division, 'EMEA Master');
});

test('code matching is case-insensitive and whitespace-tolerant', () => {
  const idx = Session.buildCodeIndex(DATA);
  assert.equal(Session.classifyCode(' e39856 ', idx, '2026-08-12').league, true);
});

test('a code that is not in the feed is not a league code', () => {
  const idx = Session.buildCodeIndex(DATA);
  assert.equal(Session.classifyCode('7DNNF1', idx, '2026-08-12').league, false);
});

test('a code captured before the last wipe is dead', () => {
  const idx = Session.buildCodeIndex(DATA);
  // The scrim was played on the 9th; the patch wiped codes on the 11th.
  assert.equal(Session.classifyCode('7DNNF1', idx, '2026-08-09').dead, true);
});

test('a code from after the last wipe is alive', () => {
  const idx = Session.buildCodeIndex(DATA);
  assert.equal(Session.classifyCode('7DNNF1', idx, '2026-08-12').dead, false);
});

test('with no known wipe date nothing is called dead', () => {
  const idx = Session.buildCodeIndex({});
  assert.equal(Session.classifyCode('7DNNF1', idx, '2026-08-09').dead, false);
});
```

- [ ] **Step 2: Run it to verify it fails**

Run: `cd docs/capture && node --test engine/session.test.js`
Expected: FAIL — `Cannot find module './session.js'`

- [ ] **Step 3: Write the implementation**

```js
// docs/capture/engine/session.js
// Scrim session scaffolding: the league-code block and the replay-code
// wipe check.
//
// The league-code block is a correctness guarantee, not a convenience. The
// scrim page's help text has always claimed league codes are blocked while no
// code implemented it; a league map recorded as a scrim would stay private in
// one person's browser instead of being published to the site.
//
// Replay codes are invalidated by every Overwatch patch (a "code wipe"). The
// date has one source - _SEED_WIPES in owdb/db.py - and reaches the browser as
// data.json's code_wipe_date.

(function (global) {
  'use strict';

  function norm(code) {
    return String(code == null ? '' : code).trim().toUpperCase();
  }

  function buildCodeIndex(data) {
    var d = data || {};
    var codes = new Set();
    var byCode = {};
    (d.codes || []).forEach(function (c) {
      if (!c || !c.code) return;
      var k = norm(c.code);
      codes.add(k);
      byCode[k] = c;
    });
    return { codes: codes, byCode: byCode, wipeDate: d.code_wipe_date || null };
  }

  // played: ISO date (YYYY-MM-DD) the map was played, i.e. the session date.
  function classifyCode(code, index, played) {
    var k = norm(code);
    var entry = index.byCode[k] || null;
    var dead = false;
    if (index.wipeDate && played) {
      dead = String(played) < String(index.wipeDate);
    }
    return {
      league: index.codes.has(k),
      dead: dead,
      division: entry ? (entry.division || null) : null,
    };
  }

  var Session = {
    norm: norm,
    buildCodeIndex: buildCodeIndex,
    classifyCode: classifyCode,
  };

  if (typeof module !== 'undefined' && module.exports) module.exports = Session;
  else global.OWDBSession = Session;
})(typeof self !== 'undefined' ? self : this);
```

- [ ] **Step 4: Run the JS tests to verify they pass**

Run: `cd docs/capture && node --test engine/session.test.js`
Expected: PASS, 8 tests

- [ ] **Step 5: Enforce the block at the point of save**

In `docs/capture/scrim.html`, load the module and keep the parsed feed rather than discarding it. `loadTeamNames()` already fetches `data.json` (line ~470) and throws away everything but rosters and team names — store it:

```js
let LEAGUE_DATA = null, CODE_INDEX = OWDBSession.buildCodeIndex({});
// inside loadTeamNames(), after `const d = await (await fetch('data.json'...)).json();`
LEAGUE_DATA = d;
CODE_INDEX = OWDBSession.buildCodeIndex(d);
```

Then, in the handler that saves a scrim map with a replay code, refuse a league code:

```js
const cls = OWDBSession.classifyCode(code, CODE_INDEX, scrimDate());
if (cls.league) {
  await uiModal({
    title: 'That is a league match',
    body: `Code <b>${esc(code)}</b> is a ${esc(cls.division || 'league')} match. `
        + `League maps belong in League capture so they get published — `
        + `recording it here would keep it private in this browser only.`,
    actions: [{label: 'Open League capture', href: 'index.html'}, {label: 'Cancel'}],
  });
  return;   // refuse the save
}
```

- [ ] **Step 6: Run the full suite**

Run: `.venv/Scripts/python.exe -m pytest`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add docs/capture/engine/session.js docs/capture/engine/session.test.js \
        docs/capture/scrim.html
git commit -m "Implement the league-code block

The scrim page's help text has claimed since it was written that league codes
are blocked, and nothing implemented it. A league map saved as a scrim would
stay private in one browser instead of being published. Built before
un-pausing, because un-pausing without it is the bug."
```

---

## Task 12: Scaffold a session from the replay-history screenshot

**Files:**
- Modify: `docs/capture/engine/session.js`, `docs/capture/engine/session.test.js`, `docs/capture/scrim.html`

**Interfaces:**
- Consumes: `parseScrimSessionText()` (already in `scrim.html`), `classifyCode`
- Produces: `Session.buildScaffold(rows, index, played) -> [{map_name, map_category, code, score, result, league, dead, division}]`

- [ ] **Step 1: Write the failing JS test**

Append to `docs/capture/engine/session.test.js`:

```js
test('buildScaffold annotates parsed rows with league and wipe status', () => {
  const idx = Session.buildCodeIndex(DATA);
  const rows = [
    { map_name: 'Suravasa', map_category: 'Flashpoint', code: 'AKS2A9',
      score: {us: 11, them: 2}, result: 'win' },
    { map_name: 'Oasis', map_category: 'Control', code: 'E39856',
      score: {us: 1, them: 2}, result: 'loss' },
  ];
  const out = Session.buildScaffold(rows, idx, '2026-08-12');
  assert.equal(out.length, 2);
  assert.equal(out[0].league, false);
  assert.equal(out[0].dead, false);
  assert.equal(out[1].league, true, 'the Oasis row is a league match');
  assert.equal(out[1].division, 'EMEA Master');
});

test('buildScaffold keeps rows that have no code at all', () => {
  const idx = Session.buildCodeIndex(DATA);
  const rows = [{ map_name: "King's Row", map_category: 'Hybrid', code: null,
                  score: {us: 3, them: 1}, result: 'win' }];
  const out = Session.buildScaffold(rows, idx, '2026-08-12');
  assert.equal(out.length, 1);
  assert.equal(out[0].code, null);
  assert.equal(out[0].league, false);
});

test('buildScaffold marks every row dead when the session predates the wipe', () => {
  const idx = Session.buildCodeIndex(DATA);
  const rows = [{ map_name: 'Suravasa', map_category: 'Flashpoint',
                  code: 'AKS2A9', score: {us: 11, them: 2}, result: 'win' }];
  const out = Session.buildScaffold(rows, idx, '2026-08-01');
  assert.equal(out[0].dead, true);
});
```

- [ ] **Step 2: Run it to verify it fails**

Run: `cd docs/capture && node --test engine/session.test.js`
Expected: FAIL — `Session.buildScaffold is not a function`

- [ ] **Step 3: Implement `buildScaffold`**

```js
  function buildScaffold(rows, index, played) {
    return (rows || []).map(function (r) {
      var cls = r.code ? classifyCode(r.code, index, played)
                       : { league: false, dead: false, division: null };
      return {
        map_name: r.map_name,
        map_category: r.map_category,
        code: r.code || null,
        score: r.score || { us: 0, them: 0 },
        result: r.result || null,
        league: cls.league,
        dead: cls.dead,
        division: cls.division,
      };
    });
  }
```

Add it to the exported `Session` object.

- [ ] **Step 4: Run the JS tests to verify they pass**

Run: `cd docs/capture && node --test engine/session.test.js`
Expected: PASS, 11 tests

- [ ] **Step 5: Render the review list in the page**

Wire the existing `#scrimpscrbtn` / paste handler so that after `parseScrimSessionText()` produces rows, `buildScaffold()` annotates them and a review list is rendered into `#scrimqueuelist` (the element already exists, inside the currently-hidden `#scrimqueue`). Add to `docs/capture/scrim.html`:

```js
// Render the scaffolded session for review. League rows are refused outright;
// dead-code rows are kept (the map was still played) but flagged as
// uncapturable, since the replay they would be captured from no longer exists.
function renderScaffold(rows){
  const wrap=document.getElementById('scrimqueue');
  const list=document.getElementById('scrimqueuelist');
  if(!rows.length){ wrap.style.display='none'; return; }
  wrap.style.display='';
  const wipe=CODE_INDEX.wipeDate;
  list.innerHTML=`<p class="status">${rows.length} map${rows.length===1?'':'s'} read`
    + (wipe?` — codes valid until the next patch (last wipe ${esc(wipe)})`:'')
    + `</p>`
    + rows.map((r,i)=>{
        const dis=r.league?'disabled':'';
        const on=r.league?'':'checked';
        const note=r.league
          ? `<span class="warn">league match${r.division?` (${esc(r.division)})`:''}
             — <a href="index.html">capture in League scout</a></span>`
          : r.dead
            ? `<span class="warn">code expired — replay unavailable</span>`
            : '';
        const sc=r.score?`${r.score.us}-${r.score.them}`:'';
        return `<label class="row" style="gap:8px">
          <input type="checkbox" data-i="${i}" ${on} ${dis}>
          <b>${esc(r.map_name)}</b>
          <span class="status">${esc(r.map_category||'')}</span>
          <code>${esc(r.code||'—')}</code>
          <span class="status">${esc(sc)}</span>
          <span class="status">${esc(r.result||'')}</span>
          ${note}
        </label>`;
      }).join('');
}
```

"Start session" then creates a `scrim_map` record per checked row. Keep "+ add a map by hand" always available, offering **every** map in `SCRIM_MAPS` — scrims are not restricted to a league map pool.

- [ ] **Step 5b: Verify the rendering against a real screenshot**

Paste a real Overwatch replay-history screenshot into the page. Confirm each row shows the map, code, score and result; that a league code (if the history contains one) is unchecked and disabled with its division named; and that the wipe-date line reads correctly.

- [ ] **Step 6: Run the full suite**

Run: `.venv/Scripts/python.exe -m pytest`
Expected: PASS, including the seven existing `parse_scrim_session_text` tests

- [ ] **Step 7: Commit**

```bash
git add docs/capture/engine/session.js docs/capture/engine/session.test.js \
        docs/capture/scrim.html
git commit -m "Scaffold a scrim session from the replay-history screenshot

The screenshot is the session manifest - the scrim equivalent of the FACEIT
match data the league flow gets free. It does not replace capture; it lists
the maps that will then be captured from their replays. League rows are
refused and expired codes are marked."
```

---

## Task 13: Remove the pause overlay

Last, not first. Everything that makes un-pausing safe is now in place.

**Files:**
- Modify: `docs/capture/scrim.html`
- Test: `tests/test_capture_scrim.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_capture_scrim.py`:

```python
def test_scrim_capture_is_not_paused() -> None:
    """The pause overlay is gone and cannot silently come back.

    docs/capture/scrim.html rendered an unconditional full-screen
    #scrimpaused overlay that no script removed (commit f2881cf). Phase 1
    removes it; this test is what stops it reappearing.
    """
    html = APP.read_text(encoding="utf-8")
    assert "scrimpaused" not in html
    assert "Scrims are paused" not in html


def test_scrim_page_loads_the_session_engine_module() -> None:
    """The league-code block must be reachable from the page, not just exist."""
    html = APP.read_text(encoding="utf-8")
    assert 'src="engine/session.js"' in html
```

- [ ] **Step 2: Run it to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/test_capture_scrim.py -k paused -v`
Expected: FAIL — `assert 'scrimpaused' not in html`

- [ ] **Step 3: Delete the overlay**

Remove the `<div id="scrimpaused">` block at `docs/capture/scrim.html:160-167` in full.

- [ ] **Step 4: Run the test to verify it passes**

Run: `.venv/Scripts/python.exe -m pytest tests/test_capture_scrim.py -k "paused or engine" -v`
Expected: PASS

- [ ] **Step 5: Run the full suite**

Run: `.venv/Scripts/python.exe -m pytest`
Expected: PASS

- [ ] **Step 6: Walk the whole flow in a browser**

This is the acceptance test for phase 1, and only a human can run it:

1. Open `docs/capture/scrim.html` — no overlay.
2. Paste a screenshot of a real Overwatch replay history. Confirm the maps, codes, scores and results are read, and that any league code in it is refused with its division named.
3. Create the session, add one map by hand, confirm every map is offered.
4. Share a screen, calibrate, start a map, take snapshots, save it.
5. Open `docs/scrims.html` and confirm the scrim appears.

- [ ] **Step 7: Commit**

```bash
git add docs/capture/scrim.html tests/test_capture_scrim.py
git commit -m "Un-pause scrim capture

Removes the unconditional #scrimpaused overlay from f2881cf. Removed last,
after the league-code block and the session scaffold, so un-pausing does not
open a window where a league map can be recorded as a private scrim. A test
now guards against the overlay returning."
```

---

## Task 14: Record phase 1 in the docs

**Files:**
- Modify: `ARCHITECTURE.md`, `AGENTS.md`, `CHANGELOG.md`

- [ ] **Step 1: Rewrite `ARCHITECTURE.md` §7**

Delete the "Current state: scrim capture is switched off in production" block. Replace the "advertised league-code block is not implemented" gotcha with a description of how it now works and where it lives. Update the WIP-feature list — screenshot import has graduated; auto side-detection, the scoreboard read and the score-box read remain, now scoped to phases 2 and 3.

- [ ] **Step 2: Update the `AGENTS.md` roadmap**

Priority 2 changes from "Ship scrim mode" to the remaining phases 2–6, with phases 0 and 1 marked delivered.

- [ ] **Step 3: Add the `CHANGELOG.md` entry**

Scrim capture being usable is visible on owdb.io and changes an operational procedure, so it qualifies on two counts.

- [ ] **Step 4: Run the full suite**

Run: `.venv/Scripts/python.exe -m pytest`
Expected: PASS

- [ ] **Step 5: Commit and open the PR**

```bash
git add ARCHITECTURE.md AGENTS.md CHANGELOG.md
git commit -m "Document scrim mode phases 0 and 1"
git fetch origin
git rebase origin/main    # CI commits to main constantly; expect to do this
.venv/Scripts/python.exe -m pytest
git push -u origin scrim-mode
```

---

## Verification checklist for the whole plan

- [ ] `.venv/Scripts/python.exe -m pytest` passes in full
- [ ] `.venv/Scripts/python.exe -m mypy faceit_sync` is clean
- [ ] `.venv/Scripts/python.exe tools/capture_divergence.py` shows the shared-function count reduced
- [ ] `docs/capture/index.html` still: shares a screen, auto-calibrates, reads portraits, teaches a miss, pops out the overlay, claims and releases a live-scouting claim, and uploads a capture
- [ ] `docs/capture/scrim.html` still does all of the above minus claims and upload, and additionally scaffolds a session and refuses a league code
- [ ] `docs/scrims.html` reads the IndexedDB without triggering an upgrade
- [ ] IndexedDB `owscout-capture` is still at version 4 with learned refs intact
- [ ] No developer documentation was added under `docs/`

## Out of scope

Phases 2–6 of `specs/2026-08-12-scrim-mode-design.md`, each of which gets its own plan: opponent identification and the roster search (2), the stats read and the workshop hero-glyph reference set (3), the viewer (4), sync and sharing (5), auto map detection (6). `docs/capture/engine/snapshot.js` is deliberately deferred to phase 3, as recorded in the File Structure section.

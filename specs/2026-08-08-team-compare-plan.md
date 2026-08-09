# Team Compare — implementation plan

**Date:** 2026-08-08

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Two-team side-by-side comparison on the dashboard: a radar across mixed FACEIT + capture axes, per-team map-pick/ban views, and a perspective toggle — per `specs/2026-08-08-team-compare-design.md`.

**Architecture:** Client-side only, entirely in the dashboard JS parts. Hoists the compare math (`compareAxes`, `radarPoints`) above `bootApp` in `faceit_sync/dashboard/pure.js` as data-parameterized pure functions; adds state + routing + `renderCompare()` in `faceit_sync/dashboard/app.js`; radar CSS in `faceit_sync/dashboard/head.html`. No Python changes, no new dependencies, no build step.

**Tech Stack:** Python 3.12 (the parts are concatenated at import by `faceit_sync/_dashboard.py`), vanilla JS, `node --check` for syntax, `pytest` for the pure-function tests, headless Edge for the visual pass.

## Global Constraints

- **After every edit to a dashboard part file** (`pure.js`/`app.js`/`head.html`), run `.venv/Scripts/python.exe -m pytest tests/test_export.py::test_dashboard_javascript_is_syntactically_valid` — one JS syntax error yields a completely blank live page.
- **Pure, testable logic goes in `pure.js` above `function bootApp(DATA){`**, same discipline as `codeLookup`/`codesFor`/`mapCoverage`. A function belongs there only if it has **zero** dependency on anything declared inside `bootApp` — no `esc`, `el`, `inc`, `MAP_CAT`, `CODE_WIPE`, `HERO_ROLE`, `D()`, or DOM. The `_pure_js()` harness executes every hoisted line in node, so any such reference throws immediately in the new tests.
- **`aggregate()` lives in `app.js`, not pure.js.** `compareAxes` must take already-computed `aggA`/`aggB`/`scoutA`/`scoutB` objects as parameters; the `app.js` wrapper builds them from `D().matches` + `DATA.owdb_comps`. Never call the wrapper from the tests — call `compareAxes` with explicit fixtures.
- **No new dependencies, no build step.** Reuse `codeLookup`, `codesFor`, `pill`, `winVar`, `table`, `barList`, `compRow`, `teamAvatar`, `esc`, `el`, and the existing CSS variables.
- **`mypy faceit_sync` / full `pytest`** run once at the end (Task 6), not per-task — these edits live in the JS part files, which mypy doesn't parse.
- **Division scope is enforced at the routing layer** (same-division only), not in pure math: `compareAxes` doesn't know about divisions.

---

### Task 1: Pure layer — `compareAxes` + `radarPoints` in `pure.js`, tests in `tests/test_dashboard_logic.py`

**Files:**
- Modify: `faceit_sync/dashboard/pure.js` (insert after `mapCoverage`, at end of file)
- Test: `tests/test_dashboard_logic.py` (append)

**Interfaces:**
- Produces:
  - `compareAxes(aggA, aggB, scoutA, scoutB)` → `Array<{id, label, a:{raw,val,n,ok}, b:{raw,val,n,ok}}>`. Axis table (cap, floor) as documented. Dropped entirely when neither side has a sample.
  - `radarPoints(vals, cx, cy, r)` → `[{x,y}]`, 12 o'clock start, clockwise. `null` vals skip the vertex (for dimmed/absent axes, the polygon bridges the gap — caller decides).
  - Named constants `COMPARE_CAPS` (the `{axis: cap}` map) and floor constants.
- Consumed by: Task 4's `renderCompare` and Task 5's tests.

- [x] **Step 1: Write the failing tests**

Append to `tests/test_dashboard_logic.py`:

```python
# --- team compare: radar math -------------------------------------------------
# compareAxes/radarPoints are pure (no DOM, no DATA), so they're declared above
# bootApp and directly testable. Aggregates come pre-computed from app.js's
# aggregate(); the pure layer only applies caps/floors and shapes the radar.

def test_compare_axes_caps_raw_values(tmp_path) -> None:
    ...

def test_compare_axes_dims_below_floor(tmp_path) -> None:
    ...

def test_compare_axes_drops_axis_missing_on_both_sides(tmp_path) -> None:
    ...

def test_compare_axes_one_sided_capture_dims_the_other(tmp_path) -> None:
    ...

def test_compare_team_eff_uses_qualified_players_only(tmp_path) -> None:
    ...

def test_radar_points_vertices(tmp_path) -> None:
    ...
```

- [x] **Step 2: Implement the pure functions in `pure.js`**

`compareAxes` walks the fixed axis table; for each axis extracts `raw`/`n` from the right spot in each side's agg/scout, computes `val=min(raw/cap,1)*100`, marks `ok` by floor, and skips the row if `raw` is missing on both sides. `radarPoints` does `x=cx+r*v/100*cos(θ)`, `y=cy-r*v/100*sin(θ)` for `θ = -π/2 + 2πk/N`, skipping `null` vals. Guard zero/negative radius.

- [x] **Step 3: Run the new tests + the JS syntax guard**

`.venv/Scripts/python.exe -m pytest tests/test_dashboard_logic.py tests/test_export.py::test_dashboard_javascript_is_syntactically_valid`

---

### Task 2: State + routing in `app.js`

**Files:** Modify: `faceit_sync/dashboard/app.js`

- [x] **Step 1: State.** Add next to `MATCH_ID` (`app.js:862`):
  `let COMPARE_A=null, COMPARE_B=null, COMPARE_PERSP='A';`
- [x] **Step 2: `hashDispatch` `compare=` branch.** Add before the `TABS.some` fallback (`:2772`). Parse `start.slice(8).split('|')`. Resolve the single-division view via team A (reuse the `scout=` loop shape `:2743-2755`); set `CURRENT_VIEW`, `recomputeDivision()`, `updateHeader()`, sync `#division`. Set `COMPARE_A=A`, `COMPARE_B=B` (or `null` if B isn't in `D().team_names`). `show('compare'); return;`
- [x] **Step 3: `show(id)` special-case.** Mirror `matchdetail` (`:2780-2786`): `navId = id==='compare' ? 'scout' : navId`; render `renderCompare()` when `id==='compare'`. (Refactor the existing `navId` ternary to also map `compare`→`scout`.)
- [x] **Step 4: `hashFor(id)`.** `if(id==='compare'&&COMPARE_A&&COMPARE_B) return 'compare='+encodeURIComponent(COMPARE_A+'|'+COMPARE_B);` before the scout branch.
- [x] **Step 5: `gotoCompare(a,b)` helper.** Set `COMPARE_A=a; COMPARE_B=b;` (validate both in `D().team_names`; null otherwise), `show('compare')`.

Run the JS syntax guard after each edit.

---

### Task 3: Scout page entry button

**Files:** Modify: `faceit_sync/dashboard/app.js` (`renderScout` control bar, `:1159-1174`)

- [x] **Step 1:** Add a "Compare…" button to the scout control bar next to the prep button (`:1171`). `onclick`: pick `SCOUT_TEAM` as A and the first other team in `D().team_names` as B, `gotoCompare(a,b)`.

Run the JS syntax guard.

---

### Task 4: `renderCompare()` + radar SVG + head.html CSS

**Files:** Modify: `faceit_sync/dashboard/app.js`, `faceit_sync/dashboard/head.html`

- [x] **Step 1: `renderCompare()` in `app.js`** (place near `renderPrepBody`/`renderScout`). Sections per design §4:
  - Header band: A/B names + record pills, swap button, two team selects, perspective radios, unresolved-B note.
  - Radar card: inline SVG octagon via small local helpers (`svgNS`, `svgPoly(points)`); per-axis value + `n` labels; dimmed for `ok:false`.
  - Maps/Bans/Comps/Players tables via existing helpers; Comps only when either side has captures.
  - Head-to-head list (matches where both `f1`/`f2` are A and B).
  - Perspective toggle re-renders section labels via a small `pers(us,them)` helper.
- [x] **Step 2: Radar axis inputs.** Build `aggA=aggregate(MATCHES_RECENT, COMPARE_A)` (and B), `scoutA=(DATA.owdb_comps||{})[COMPARE_A]` (and B), call `compareAxes`, then `radarPoints` per team.
- [x] **Step 3: head.html CSS.** `.compare-hd`, `.compare-grid` (two columns), `.radar` + axis/value/dim states, reusing `--line`/`--muted`/`--good`/`--bad`/`--accent`.

Run the JS syntax guard.

---

### Task 5: Pure tests detail (expand in Task 1)

Fixture aggregates: `{mapStats:{mapA:{games,wins}}, games, gwins, bans:{}, mapsPicked:{}, firstBanGames}` etc. Scout fixture: `{scout:{adapt:{families,swaps_per_map}, hero_pool:[...], games, rounds}}`. Assert JSON-returned rows via the existing `_run(body, tmp_path)` harness (spread Sets if any — none expected here).

- [x] Run `.venv/Scripts/python.exe -m pytest tests/test_dashboard_logic.py` green.
- [x] Run full `.venv/Scripts/python.exe -m pytest` green (Task 6).

---

### Task 6: Full verification

- [x] `.venv/Scripts/python.exe -m pytest` — full suite green.
- [x] `.venv/Scripts/python.exe -m mypy faceit_sync` — clean.
- [x] `pytest tests/test_export.py::test_dashboard_javascript_is_syntactically_valid` — green (blank-page guard).
- [x] Visual: `faceit-sync export --format html --out dashboard.html`, headless-Edge screenshots of the compare view, a `#compare=A|B` deep link, the perspective toggle, and a one-sided-capture pair.

### Task 7: Docs

- [x] `FEATURES.md` — add Team Compare (radar, mixed axes, perspective toggle, deep link).
- [x] `CLAUDE.md` — note compare in roadmap (P2 Team Compare resolved) if it's tracked there (not tracked — see notes).
- [x] `specs/BACKLOG.md` — mark P2 Team Compare resolved with a shipped note (date + what landed), mirroring the "Resolved" entries already in the file.

---

## Implementation notes (2026-08-08 — deviations found while executing)

1. **`compareAxes` gained a 5th/6th parameter** — `effA`/`effB` — in addition to
   the documented `(aggA, aggB, scoutA, scoutB)`. The Team Eff axis needs the
   roster Eff summary (mean + count of qualified players), which lives neither
   in `aggregate()`'s output nor in `owdb_comps`; the app wrapper computes it
   via `compareRoster()` + `teamEffSummary()` (mirroring `renderPlayers`' eff
   pass) and passes `{mean, n}` per side. Pure layer stays pure; only the
   signature grew.
2. **`heroes(a)` returns null (not 0) when `hero_pool` is undefined** — so a
   no-capture side drops the heropool axis entirely (with its capture-free
   counterpart), rather than rendering a confident 0.
3. **Two render bugs caught only by the headless-Edge DOM check** (the JS
   syntax test can't catch them):
   - `el(table(...))` → `table()` returns an ELEMENT, not HTML → dropped the
     `el()` wrapper (`card.appendChild(table(...))`).
   - `banLiftRows(..., DATA)` → the 5th arg is the `codeLookup(...)` Map, not
     `DATA` (`lookup.get is not a function`); fixed to
     `codeLookup(MATCHES_RECENT, team, CODE_WIPE)`.
   Lesson: this feature's render path is only provable by a browser DOM pass
   (trap-instrumented `--dump-dom`), not by `node --check` alone.
4. **Deep-link verification used `Redline|Vertex`** (both EMEA Master, both
   captured) and `Here4Views|Redline` (one-sided capture → comps block
   correctly skipped for the unscouted side, not shown as "no captured comps").
5. Screenshots are not verifiable with this model (cannot read images); DOM-text
   verification via instrumented `--dump-dom` is the working substitute.
6. CLAUDE.md roadmap does not track P2 backlog items, so only FEATURES.md and
   BACKLOG.md were updated in Task 7.
7. Full suite after all fixes: 467 passed; `mypy faceit_sync` clean.

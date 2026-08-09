# Power Rankings Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a "Power Rankings" table to the Overview tab: a from-scratch, Elo-style Series rating (orders the table) plus a supporting Map rating, with a per-match trend sparkline, computed entirely client-side from data already in the existing per-division payload.

**Architecture:** Two new pure functions in `faceit_sync/dashboard/pure.js` (`powerRankings`, `sparklinePoints`) — no DOM, no `DATA` global, directly unit-testable via the existing node-execution harness in `tests/test_dashboard_logic.py`. One rendering addition in `renderOverview()` in `faceit_sync/dashboard/app.js`, reusing the existing `table()`/`teamLink()`/`sectionH()` helpers. A few lines of CSS in `faceit_sync/dashboard/head.html`. No Python, DB, or export.py changes — the `matches` array already carried in the per-division payload (`m.f1`, `m.f2`, `m.winner`, `m.walkover`, `m.finished_at`, `m.games[].winner_faction`) is sufficient.

**Tech Stack:** Vanilla JS (no framework/build step — dashboard parts are concatenated at import time), pytest + node for the pure-logic tests.

## Global Constraints

- Regular-season matches only — same scope as the existing Standings table (`D().matches`), not `D().playoffs`.
- Series Elo (`K=32`) is the sort/rank order. Map Elo (`K=12`) is a secondary, non-sorting column, labelled "Map form."
- Both start at rating **1500**. No draws (every match/game has a winner).
- Walkover matches (`m.walkover === true`, no maps played) are excluded from both ratings — no competitive signal.
- Trend = per-match Series-rating history (one point per match played), not calendar weeks.
- Teams with zero counted (non-walkover) matches are omitted from the table entirely.
- Rows with `n < 5` matches are **provisional**: rank/rating rendered faint plus a `*`, never hidden.
- UI copy says "Rating" / "Power Rankings" — never the word "Elo" (a `<p class="note">` methodology line may mention it's Elo-style, matching how other tooltips on this page explain their math).
- Run `pytest tests/test_export.py::test_dashboard_javascript_is_syntactically_valid` after touching any dashboard part file.
- Run the full suite (`.venv/Scripts/python.exe -m pytest`) and `mypy faceit_sync` before considering this done (no Python was touched, but the full suite is cheap and this repo keeps it green).

---

### Task 1: Elo core — `powerRankings`

**Files:**
- Modify: `faceit_sync/dashboard/pure.js` (append new section at the end, after the existing helpers, following the same "why" comment style as `worstMaps`)
- Test: `tests/test_dashboard_logic.py` (append new section at the end)

**Interfaces:**
- Consumes: an array of match objects shaped exactly like the `matches` entries `export.py` already produces: `{finished_at, f1, f2, winner, walkover, games: [{winner_faction}, ...]}` (see `faceit_sync/export.py:453-462` for the authoritative shape — `winner`/`winner_faction` are `'faction1'`/`'faction2'` strings).
- Produces: `powerRankings(matches)` → array of `{name, rating, mapRating, n, history, provisional}` sorted by `rating` descending, where `history` is an array of `Math.round`ed Series ratings, one per match the team has played, in chronological order. Also exports the constants `SERIES_ELO_K`, `MAP_ELO_K`, `ELO_START`, `POWER_MIN_N` (top-level `const`s, referenced directly by `app.js` the same way `WORST_MIN_GAMES` already is at `app.js:1350`).

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_dashboard_logic.py`:

```python
# --- power rankings ---------------------------------------------------------
# Series Elo orders the table (K=32); Map Elo (K=12) is a supporting column
# only. Walkovers carry no maps and must not move either rating. Order of the
# input array must not matter — only chronology (finished_at) does.

def _match(f1, f2, winner, finished_at, game_winners, walkover=False):
    games = [{"winner_faction": w} for w in game_winners]
    return {
        "finished_at": finished_at, "f1": f1, "f2": f2,
        "winner": winner, "walkover": walkover, "games": games,
    }


def test_power_rankings_bo1_match_updates_both_ratings_exactly(tmp_path) -> None:
    # Single-game match keeps Series and Map Elo identical formulas with no
    # intermediate steps, so the exact post-match numbers are hand-checkable:
    # both start at 1500 (expected score 0.5 each way), A wins ->
    # ra = 1500 + K*(1-0.5), rb = 1500 + K*(0-0.5).
    m = [_match("A", "B", "faction1", "2026-01-01T00:00:00Z", ["faction1"])]
    got = _run(f"return powerRankings({json.dumps(m)});", tmp_path)
    by_name = {r["name"]: r for r in got}
    assert by_name["A"]["rating"] == 1516
    assert by_name["B"]["rating"] == 1484
    assert by_name["A"]["mapRating"] == 1506
    assert by_name["B"]["mapRating"] == 1494
    assert by_name["A"]["n"] == 1 and by_name["B"]["n"] == 1
    assert by_name["A"]["provisional"] is True   # n=1 < POWER_MIN_N


def test_power_rankings_orders_by_series_rating_descending(tmp_path) -> None:
    m = [_match("A", "B", "faction1", "2026-01-01T00:00:00Z", ["faction1"])]
    got = _run(f"return powerRankings({json.dumps(m)});", tmp_path)
    assert [r["name"] for r in got] == ["A", "B"]


def test_power_rankings_bo5_win_moves_both_ratings_in_the_winners_favor(tmp_path) -> None:
    m = [_match("A", "B", "faction1", "2026-01-01T00:00:00Z",
                ["faction1", "faction1", "faction2", "faction1"])]
    got = _run(f"return powerRankings({json.dumps(m)});", tmp_path)
    by_name = {r["name"]: r for r in got}
    assert by_name["A"]["rating"] > 1500 > by_name["B"]["rating"]
    assert by_name["A"]["mapRating"] > 1500 > by_name["B"]["mapRating"]


def test_power_rankings_excludes_walkovers(tmp_path) -> None:
    m = [_match("A", "B", "faction1", "2026-01-01T00:00:00Z", [], walkover=True)]
    got = _run(f"return powerRankings({json.dumps(m)});", tmp_path)
    assert got == []


def test_power_rankings_is_order_independent_of_input_array_order(tmp_path) -> None:
    m1 = _match("A", "B", "faction1", "2026-01-01T00:00:00Z", ["faction1"])
    m2 = _match("A", "B", "faction2", "2026-01-08T00:00:00Z", ["faction2"])
    forward = _run(f"return powerRankings({json.dumps([m1, m2])});", tmp_path)
    backward = _run(f"return powerRankings({json.dumps([m2, m1])});", tmp_path)
    assert forward == backward


def test_power_rankings_provisional_flag_boundary(tmp_path) -> None:
    # A plays 4 distinct opponents (n=4, below POWER_MIN_N=5) -> provisional.
    opponents = ["C", "D", "E", "F"]
    matches = [_match("A", opp, "faction1", f"2026-01-0{i+1}T00:00:00Z", ["faction1"])
               for i, opp in enumerate(opponents)]
    got = _run(f"return powerRankings({json.dumps(matches)});", tmp_path)
    a = next(r for r in got if r["name"] == "A")
    assert a["n"] == 4
    assert a["provisional"] is True

    matches.append(_match("A", "G", "faction1", "2026-01-05T00:00:00Z", ["faction1"]))
    got5 = _run(f"return powerRankings({json.dumps(matches)});", tmp_path)
    a5 = next(r for r in got5 if r["name"] == "A")
    assert a5["n"] == 5
    assert a5["provisional"] is False


def test_power_rankings_history_is_one_point_per_match_in_order(tmp_path) -> None:
    m1 = _match("A", "B", "faction1", "2026-01-01T00:00:00Z", ["faction1"])
    m2 = _match("A", "C", "faction2", "2026-01-08T00:00:00Z", ["faction2"])
    got = _run(f"return powerRankings({json.dumps([m1, m2])});", tmp_path)
    a = next(r for r in got if r["name"] == "A")
    assert len(a["history"]) == 2
    assert a["history"][0] == 1516          # after beating B (see bo1 test above)
    assert a["history"][1] < a["history"][0]  # then lost to C, rating dropped
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/Scripts/python.exe -m pytest tests/test_dashboard_logic.py -k power_rankings -v`
Expected: FAIL — `powerRankings is not defined` (node error surfaces as a non-zero return code, tripping the `assert proc.returncode == 0` in `_run`).

- [ ] **Step 3: Implement `powerRankings` in pure.js**

Append to the end of `faceit_sync/dashboard/pure.js`:

```js
// Power rankings — a from-scratch team rating computed from stored match/map
// results (NOT FACEIT's own per-player elo_snapshot on round_players). Series
// Elo is the thing the league itself decides standings by, so it orders the
// table; Map Elo updates far more often (games >> matches) and rides along as
// a faster-reacting secondary signal, never the sort key. Walkovers have no
// maps played and carry no competitive signal, so they're skipped entirely —
// same "zeroed rows aren't a real result" rule the rest of ingest follows.
const SERIES_ELO_K = 32, MAP_ELO_K = 12, ELO_START = 1500, POWER_MIN_N = 5;

function eloExpected(ra, rb) { return 1 / (1 + Math.pow(10, (rb - ra) / 400)); }
function eloNext(ra, rb, scoreA, k) { return ra + k * (scoreA - eloExpected(ra, rb)); }

function powerRankings(matches) {
  const teams = {};
  const team = (name) => teams[name] || (teams[name] = {
    rating: ELO_START, mapRating: ELO_START, n: 0, history: [],
  });

  const ordered = (matches || [])
    .filter(m => !m.walkover && m.f1 && m.f2)
    .slice()
    .sort((a, b) => String(a.finished_at || '').localeCompare(String(b.finished_at || '')));

  ordered.forEach(m => {
    const a = team(m.f1), b = team(m.f2);

    (m.games || []).forEach(g => {
      if (g.winner_faction !== 'faction1' && g.winner_faction !== 'faction2') return;
      const scoreA = g.winner_faction === 'faction1' ? 1 : 0;
      const ra = eloNext(a.mapRating, b.mapRating, scoreA, MAP_ELO_K);
      const rb = eloNext(b.mapRating, a.mapRating, 1 - scoreA, MAP_ELO_K);
      a.mapRating = ra; b.mapRating = rb;
    });

    const scoreA = m.winner === 'faction1' ? 1 : m.winner === 'faction2' ? 0 : null;
    if (scoreA == null) return;
    const ra = eloNext(a.rating, b.rating, scoreA, SERIES_ELO_K);
    const rb = eloNext(b.rating, a.rating, 1 - scoreA, SERIES_ELO_K);
    a.rating = ra; b.rating = rb; a.n += 1; b.n += 1;
    a.history.push(Math.round(ra)); b.history.push(Math.round(rb));
  });

  return Object.entries(teams)
    .filter(([, t]) => t.n > 0)
    .map(([name, t]) => ({
      name, rating: Math.round(t.rating), mapRating: Math.round(t.mapRating),
      n: t.n, history: t.history, provisional: t.n < POWER_MIN_N,
    }))
    .sort((a, b) => b.rating - a.rating);
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/Scripts/python.exe -m pytest tests/test_dashboard_logic.py -k power_rankings -v`
Expected: PASS (7 tests)

- [ ] **Step 5: Dashboard JS syntax check**

Run: `.venv/Scripts/python.exe -m pytest tests/test_export.py::test_dashboard_javascript_is_syntactically_valid -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add faceit_sync/dashboard/pure.js tests/test_dashboard_logic.py
git commit -m "Add powerRankings pure Elo core for the dashboard"
```

---

### Task 2: Sparkline helper — `sparklinePoints`

**Files:**
- Modify: `faceit_sync/dashboard/pure.js` (append after `powerRankings`)
- Test: `tests/test_dashboard_logic.py` (append after the power-rankings tests)

**Interfaces:**
- Consumes: `history` — the same array `powerRankings` returns per team (`number[]`).
- Produces: `sparklinePoints(history, w, h)` → a string of `"x,y"` pairs (space-separated) suitable for an SVG `<polyline points="...">`, normalized into a `0..w` × `0..h` box. `w`/`h` default to `60`/`20` when omitted. Consumed by Task 3's rendering code.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_dashboard_logic.py`:

```python
# --- sparkline points --------------------------------------------------------
# Turns a rating history into normalized SVG polyline points. A single-point
# history still has to render a visible flat line, not collapse to nothing —
# a team's first result shouldn't be an invisible sparkline.

def test_sparkline_empty_history_is_empty_string(tmp_path) -> None:
    assert _run("return sparklinePoints([], 60, 20);", tmp_path) == ""


def test_sparkline_single_point_is_a_flat_centered_line(tmp_path) -> None:
    assert _run("return sparklinePoints([1500], 60, 20);", tmp_path) == "0,10 60,10"


def test_sparkline_two_points_span_the_full_box(tmp_path) -> None:
    # Lower rating first -> higher on screen is lower y (SVG y grows downward),
    # so the rising [1500,1600] history must end at y=0 (top), not y=20.
    got = _run("return sparklinePoints([1500,1600], 60, 20);", tmp_path)
    assert got == "0.0,20.0 60.0,0.0"


def test_sparkline_flat_history_stays_centered(tmp_path) -> None:
    got = _run("return sparklinePoints([1500,1500,1500], 60, 20);", tmp_path)
    # equal values -> span defaults to 1 so it doesn't divide by zero; every
    # point should land at the same y.
    ys = [p.split(',')[1] for p in got.split(' ')]
    assert len(set(ys)) == 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/Scripts/python.exe -m pytest tests/test_dashboard_logic.py -k sparkline -v`
Expected: FAIL — `sparklinePoints is not defined`

- [ ] **Step 3: Implement `sparklinePoints` in pure.js**

Append to `faceit_sync/dashboard/pure.js`, directly after the `powerRankings` block:

```js
// history -> normalized "x,y x,y ..." for an SVG <polyline>. A one-point
// history still draws a flat line across the full width rather than a dot,
// so a team's very first tracked result isn't invisible in the table.
function sparklinePoints(history, w, h) {
  const w_ = w || 60, h_ = h || 20;
  if (!history || !history.length) return '';
  if (history.length === 1) return `0,${h_ / 2} ${w_},${h_ / 2}`;
  const min = Math.min(...history), max = Math.max(...history), span = (max - min) || 1;
  return history.map((v, i) => {
    const x = i / (history.length - 1) * w_;
    const y = h_ - ((v - min) / span) * h_;
    return `${x.toFixed(1)},${y.toFixed(1)}`;
  }).join(' ');
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/Scripts/python.exe -m pytest tests/test_dashboard_logic.py -k sparkline -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Dashboard JS syntax check**

Run: `.venv/Scripts/python.exe -m pytest tests/test_export.py::test_dashboard_javascript_is_syntactically_valid -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add faceit_sync/dashboard/pure.js tests/test_dashboard_logic.py
git commit -m "Add sparklinePoints pure helper for rating trend lines"
```

---

### Task 3: Render the Power Rankings card on Overview

**Files:**
- Modify: `faceit_sync/dashboard/app.js:1233` (insert immediately after the existing `<p class="note">Veto attribution recovered…</p>` line that closes the Standings block inside `renderOverview()`)
- Modify: `faceit_sync/dashboard/head.html` (append one CSS rule near `.pill`, `~head.html:420`)

**Interfaces:**
- Consumes: `powerRankings` and `sparklinePoints` from Task 1/2 (top-level functions, already in scope — `app.js` is concatenated after `pure.js` into the same `<script>` block, the same way `app.js:1350` already references `WORST_MIN_GAMES` from `pure.js` directly). Also consumes existing helpers already in `app.js`: `D()` (`app.js:17`), `table()` (`app.js:600`), `teamLink()` (`app.js:273`), `sectionH()` (`app.js:638`), `el()`/`esc()` (`app.js:49-50`).
- Produces: nothing consumed by later tasks — this is the last task.

- [ ] **Step 1: Add the CSS rule**

In `faceit_sync/dashboard/head.html`, add this line directly after the `.pill{...}` rule (`head.html:420`):

```css
.spark{display:block;vertical-align:middle}
```

- [ ] **Step 2: Insert the rendering block in `renderOverview()`**

In `faceit_sync/dashboard/app.js`, find this line (currently `app.js:1233`):

```js
  wrap.appendChild(el(`<p class="note">Veto attribution recovered from FACEIT's durable history feed for ${s.matches_with_attribution}/${s.matches} matches; only walkovers and disrupted vetos lack it.</p>`));
```

Insert immediately after it (still inside `renderOverview()`, before the `// Scout leaderboard` comment that follows):

```js
  // Power Rankings — a from-scratch Elo-style rating built from stored match
  // results (distinct from FACEIT's own per-player elo_snapshot). Series
  // rating orders the table since that's what the league itself decides
  // standings by; Map form is a faster-reacting secondary column, never the
  // sort key. Regular season only, same scope as Standings above.
  const pr = powerRankings(D().matches);
  if (pr.length) {
    wrap.appendChild(el(sectionH('Power Rankings')));
    wrap.appendChild(table(
      [{k: 'rank', label: '#', num: true},
       {k: 'name', label: 'Team', html: r => teamLink(r.name)},
       {k: 'rating', label: 'Rating', num: true,
        html: r => `<span class="${r.provisional ? 'faint' : ''}">${r.rating}</span>`},
       {k: 'mapRating', label: 'Map form', num: true},
       {k: 'history', label: 'Trend',
        html: r => `<svg viewBox="0 0 60 20" class="spark" width="60" height="20">` +
          `<polyline points="${sparklinePoints(r.history, 60, 20)}" fill="none" ` +
          `stroke="var(--accent)" stroke-width="2"/></svg>`},
       {k: 'n', label: 'n', num: true,
        html: r => r.provisional
          ? `${r.n} <span class="faint" title="Fewer than ${POWER_MIN_N} matches — rating is still settling">*</span>`
          : String(r.n)}],
      pr.map((r, i) => ({...r, rank: i + 1}))));
    wrap.appendChild(el(`<p class="note">Power Rankings is an Elo-style rating built from match results (not FACEIT's own per-player elo) — every finished match moves a team's Rating by up to K=${SERIES_ELO_K} based on the result and the opponent's strength, and every map moves a separate Map form rating (K=${MAP_ELO_K}), which reacts faster since there are more maps than matches. Trend plots Rating after each match, oldest to newest. Rows marked * have played fewer than ${POWER_MIN_N} matches and are still settling.</p>`));
  }
```

Note: `{k: 'history', ...}` and `{k: 'mapRating', ...}` reuse row properties that already exist on the objects `powerRankings` returns (`history`, `mapRating`) — no extra data plumbing needed. The `rank` and `n`-with-asterisk fields are the only ones synthesized for display.

- [ ] **Step 3: Dashboard JS syntax check**

Run: `.venv/Scripts/python.exe -m pytest tests/test_export.py::test_dashboard_javascript_is_syntactically_valid -v`
Expected: PASS — this is the only automated guard on `app.js`/`head.html` changes; there is no unit test for DOM rendering in this codebase (see `tests/test_dashboard_logic.py` module docstring — presentation is smoke-tested only).

- [ ] **Step 4: Full test suite and mypy**

Run: `.venv/Scripts/python.exe -m pytest`
Expected: PASS (all tests, including the two new test groups from Tasks 1–2)

Run: `.venv/Scripts/python.exe -m mypy faceit_sync`
Expected: clean (no Python was touched, but this must stay green per project convention)

- [ ] **Step 5: Visual check**

Build a local dashboard from whatever DB is available and screenshot the Overview tab, per the project's standard verification method (CLAUDE.md "Verifying the dashboard"):

```bash
.venv/Scripts/python.exe -m faceit_sync.cli export --format html --out dashboard.html
msedge --headless --screenshot=overview.png "file:///c:/Users/ccarn/faceit-sync/dashboard.html#overview"
```

Confirm: the Power Rankings card appears below Standings with a `#`/Team/Rating/Map form/Trend/n table, sparklines render as small visible line segments (not blank), any provisional rows show a faint rank/rating and a `*` next to `n`, and the methodology note reads correctly. Check both a light and dark OS theme if convenient — the CSS uses only existing `var(--accent)`/`var(--faint)` tokens, which are already theme-aware, but confirm the sparkline stroke is visible in both.

- [ ] **Step 6: Commit**

```bash
git add faceit_sync/dashboard/app.js faceit_sync/dashboard/head.html
git commit -m "Render Power Rankings card on the Overview tab"
```

---

## Plan Self-Review

**Spec coverage:**
- Series Elo (K=32) orders the table → Task 1 (`powerRankings`, sorted by `rating` desc).
- Map Elo (K=12) as a non-sorting secondary column → Task 1 (`mapRating` computed independently) + Task 3 (`mapRating` column, no special sort handling).
- Per-match trend sparkline, not calendar weeks → Task 1 (`history` = one push per match) + Task 2 (`sparklinePoints`) + Task 3 (rendered as `<polyline>`).
- Regular-season only → Task 3 calls `powerRankings(D().matches)`, the same source the existing Standings table uses; `D().playoffs` is never touched.
- Walkovers excluded → Task 1, filtered before sorting into chronological order.
- Teams with zero counted matches omitted → Task 1, `filter(([, t]) => t.n > 0)`.
- Provisional (`n < 5`) shown faint + `*`, never hidden → Task 3 rendering.
- "Rating," never "Elo," in UI copy → Task 3's column labels and note text; the word "Elo" appears only in code comments and the one explanatory methodology sentence, matching how Team Eff's tooltip explains its own math.
- Placement: new card below Standings on Overview, no new tab/route → Task 3 inserts directly into `renderOverview()`; `TABS` (`app.js:852-858`) is untouched.

**Placeholder scan:** none — every step has real code, real file paths/line anchors, and runnable commands.

**Type consistency:** `powerRankings` returns `{name, rating, mapRating, n, history, provisional}` in Task 1; Task 3's table columns reference exactly those five field names (`rank` and the asterisk-decorated `n` cell are the only synthesized additions, both scoped to the `pr.map((r,i)=>({...r, rank:i+1}))` call in Task 3, not returned by the pure layer). `sparklinePoints(history, w, h)` from Task 2 is called with `(r.history, 60, 20)` in Task 3, matching its signature. Constants `SERIES_ELO_K`/`MAP_ELO_K`/`POWER_MIN_N` are defined once in Task 1 and only ever read (never redefined) in Task 3.

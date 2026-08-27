# Season 10 readiness — implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the 7 September Season 10 boundary a non-event — the site flips
itself the moment S10 has data, says which season it is showing, covers the new
regions, and leaves Season 9 permanently readable at its own URL.

**Architecture:** Four independent changes, none of which depends on S10
existing. A fallback in `export_html` makes an explicit `--season` pin degrade to
the newest season that actually has matches, so the pin can be flipped to `s10`
today and takes effect by itself on the first ingested S10 match. The season the
page rendered becomes a payload field, which the shell reads for a label and a
season-state note. `REGIONS` grows to four entries. Season 9 is frozen as a
static export outside CI's regeneration path.

**Tech Stack:** Python 3.12 (`faceit_sync`, `owdb`), pytest, mypy (strict, over
`faceit_sync` only), vanilla ES5-flavoured JS in `faceit_sync/dashboard/`,
`node --check` as the JS syntax gate.

**Spec:** `specs/2026-08-10-season10-cutover-design.md`, especially §6 (status at
the end of Season 9) and the decisions recorded in §6.3–§6.4. Read it first; this
plan argues from it.

## Global Constraints

Copied verbatim from `AGENTS.md`; every task's requirements include these.

- **Never hand-edit `docs/index.html`.** CI regenerates it from
  `faceit_sync/dashboard/head.html` on every run. Fix the part file.
- **Never run `faceit-sync export` locally to "just regenerate" the site.** The
  local `faceit.sqlite3` is routinely days behind CI's cached copy. Task 4 is the
  one place this plan writes into `docs/`, and it builds from CI's published DB
  (`docs/faceit.sqlite3.gz`), never from the local file.
- **Always run the dashboard JS syntax test after editing anything under
  `faceit_sync/dashboard/`**:
  `pytest tests/test_export.py::test_dashboard_javascript_is_syntactically_valid`.
- **Never commit `owdb_comps.json`** (or `owdb_comps_s9.json`).
- **`mypy` must stay clean over `faceit_sync`**:
  `.venv/Scripts/python.exe -m mypy faceit_sync`.
- **`docs/theme.css` is the design system**; a page that restates one of its
  values is the bug. Corners come from `--r-sm/-md/-lg/-pill`; `--on-accent` is
  the ink for any saturated fill. `docs/theme.css` and
  `faceit_sync/dashboard/theme.css` must be copied in step.
- **Never put developer documentation in `docs/`** — it is the GitHub Pages web
  root.
- **`wrangler deploy` is run by the human.** Task 5 does not deploy anything.
- Dev environment is Windows; use `.venv/Scripts/python.exe` directly.

## Out of scope

Decided in conversation on 2026-08-27, recorded here so nobody re-opens them
mid-execution:

- **Relegation ingest** — skipped entirely, operator's call. S9 standings stay
  the record; S10 division membership becomes visible when S10 is crawled.
- **Intermediate tier** — seeded in week 1 of S10 instead of at the boundary,
  once its real team count is countable. Nothing in this plan.
- **The `owscout-capture` IndexedDB rename** — closed as won't-do. Task 3 step 6
  deletes the promise from `AGENTS.md`; there is no migration.
- **Cross-season player careers** — wanted, but it needs S9 in the live payload,
  which cuts against the season-scoped export. Its own design document, after
  the boundary.
- **`--external-data` page splitting** — still deferred; the Intermediate
  decision is what would have forced it.

---

### Task 1: Season fallback in the exporter

`export --season s10` against a DB with no S10 data currently prints "no data to
export yet", writes a **0-byte file** and exits 1. GitHub Actions runs `run:`
blocks under `bash -e`, so the job dies before the publish step: the live site is
not clobbered, but CI goes red on every run and owdb.io silently freezes. This
task makes the pin fall back to the newest season that does have matches, so the
pin can be flipped to `s10` at any time and the site switches itself on the first
S10 match.

An explicit pin always wins **when it has data**. The fallback only ever covers
the gap.

**Files:**
- Modify: `faceit_sync/export.py` (add `_newest_season`; the `want_season` filter
  inside `export_html`, currently around line 587)
- Test: `tests/test_export.py`

**Interfaces:**
- Consumes: `_season_of(name) -> str | None` and `_SEASON_RE` (already exist,
  `faceit_sync/export.py:532-545`).
- Produces: `_newest_season(names: Iterable[str | None]) -> str | None` — the
  highest-numbered season across the names given, `None` if none encodes one.
  Task 2 imports it for the payload field.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_export.py`. `test_season_filter_narrows_the_export` (line 520)
is the exact pattern to copy: the `db: Database` fixture from `conftest.py`, one
`championships` row per name, and `_insert_match` (line 295) to give each one a
finished match so it counts as a division with data. Factor that setup into a
local helper next to it, since three new tests need it:

```python
def _seed_divisions(db: Database, names: dict[str, str]) -> None:
    """One finished match per championship, so each name becomes a division with
    data. Keys are championship ids, values the FACEIT championship names."""
    c = db.conn
    c.execute("INSERT INTO maps(guid,name,category) VALUES('m1','Ilios','Control')")
    for tid, nm in [("t1", "Alpha"), ("t2", "Bravo")]:
        c.execute("INSERT INTO teams(id,name) VALUES(?,?)", (tid, nm))
    for cid, nm in names.items():
        c.execute("INSERT INTO championships(id,name,game,region) VALUES(?,?,?,'GLOBAL')",
                  (cid, nm, "ow2"))
        _insert_match(db, cid, f"m-{cid}", "FINISHED", "t1", "t2", "faction1", None,
                      "2026-07-20T20:00:00Z", 1, ["faction1", "faction1"])
    db.conn.commit()


def _payload(buf: io.StringIO) -> dict:
    """The inlined data blob, as the existing filter tests read it."""
    return json.loads(re.search(r"var __OWDB_DATA__=(\{.*\});", buf.getvalue())
                      .group(1).replace("<\\/", "</"))


def test_newest_season_picks_the_highest_number() -> None:
    from faceit_sync.export import _newest_season

    names = ["S9 EMEA Master Central - Regular Season",
             "S10 EMEA Master Central - Regular Season"]
    assert _newest_season(names) == "s10"
    # Lexically "s9" > "s10"; the compare must be numeric.
    assert _newest_season(reversed(names)) == "s10"
    assert _newest_season(["Winter Finale Cup", None]) is None
    assert _newest_season([]) is None


def test_pinned_season_with_no_data_falls_back_to_the_newest(db: Database) -> None:
    """The week either side of a season boundary: the pin names a season that
    exists as an intention but not yet as data. Falling back keeps the site live
    and lets it switch over by itself on the first ingested match."""
    _seed_divisions(db, {"s9m": "S9 EMEA Master Central - Regular Season"})

    buf = io.StringIO()
    n = export_html(db, buf, only_season="s10")
    assert n == 1, "expected the S9 division to render as the fallback"
    assert [v["label"] for v in _payload(buf)["views"]] == ["EMEA Master"]


def test_pinned_season_wins_whenever_it_has_data(db: Database) -> None:
    """The fallback must never override an explicit pin that CAN be satisfied."""
    _seed_divisions(db, {"s9m": "S9 EMEA Master Central - Regular Season",
                         "s10m": "S10 EMEA Master Central - Regular Season"})

    buf = io.StringIO()
    n = export_html(db, buf, only_season="s9")
    assert n == 1
    assert list(_payload(buf)["divisions"].keys()) == ["s9m"]
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
.venv/Scripts/python.exe -m pytest tests/test_export.py -k "newest_season or pinned_season" -v
```

Expected: FAIL — `ImportError: cannot import name '_newest_season'` on the first,
and the two `export_html` tests failing because a pinned-but-empty season
currently renders zero divisions.

- [ ] **Step 3: Add `_newest_season`**

In `faceit_sync/export.py`, directly below `_season_of` (which ends around line
545), so the two season helpers sit together:

```python
def _newest_season(names: Iterable[str | None]) -> str | None:
    """The highest-numbered season across these championship names.

    Compared numerically, not lexically: sorted as strings 's9' beats 's10',
    which would pin the site to the season that just ended for as long as both
    are in the database.
    """
    seasons = {s for s in (_season_of(n) for n in names) if s}
    return max(seasons, key=lambda s: int(s[1:]), default=None)
```

`Iterable` needs `from collections.abc import Iterable` at the top of the file if
it is not already imported — check the existing imports before adding a duplicate.

- [ ] **Step 4: Make the pin fall back**

In `export_html`, replace the season filter (currently the two lines
`if want_season:` / `rows = [r for r in rows if _season_of(r["name"]) == want_season]`):

```python
        if want_season:
            seasoned = [r for r in rows if _season_of(r["name"]) == want_season]
            if seasoned:
                rows = seasoned
            else:
                # The pinned season exists as an intention but not yet as data —
                # the days either side of a season boundary. Falling back to the
                # newest season that DOES have matches keeps the site live, and
                # switches it over by itself on the first ingested match of the
                # new season, with no second manual step at an hour nobody is
                # watching. Without this the export writes a 0-byte file and
                # exits 1, which under `bash -e` fails the whole CI job.
                fallback = _newest_season([r["name"] for r in rows])
                log.warning(
                    "season %s has no data yet - falling back to %s",
                    want_season, fallback or "(no season could be parsed)",
                )
                rows = [r for r in rows if _season_of(r["name"]) == fallback] \
                    if fallback else []
```

- [ ] **Step 5: Run the tests to verify they pass**

```bash
.venv/Scripts/python.exe -m pytest tests/test_export.py -k "newest_season or pinned_season" -v
```

Expected: 3 passed.

- [ ] **Step 6: Run the full gate**

```bash
.venv/Scripts/python.exe -m pytest
.venv/Scripts/python.exe -m mypy faceit_sync
```

Expected: all green, mypy clean. `export.py` is not a `faceit_sync/dashboard/`
part file, so the JS syntax test is not specifically implicated here — but it
runs as part of the suite above and must stay green.

- [ ] **Step 7: Commit**

```bash
git add faceit_sync/export.py tests/test_export.py
git commit -m "export: fall back to the newest season with data when the pin is empty"
```

---

### Task 2: The site says which season it is showing

With Task 1 in place the site can render a different season from the one the flag
names. That is only safe if the page stops being silent about it — a visitor must
be able to tell S9 from S10 without counting matches. The same element answers
the current off-season question, which the site does not address at all today:
the capture funnel is dead because every S9 code predates the 2026-08-18 wipe,
and nothing says so.

`#wipenote` in the hero card already hides itself when no codes are live
(`app.js:3415`), so today it renders nothing. This task gives that empty slot a
job.

**Files:**
- Modify: `faceit_sync/export.py` (payload `data` dict, around line 720)
- Modify: `faceit_sync/dashboard/head.html:560` (the brand block)
- Modify: `faceit_sync/dashboard/pure.js` (add `seasonNote`, beside
  `coverageState` around line 139)
- Modify: `faceit_sync/dashboard/app.js` (`renderWipeNote`, around line 3413; and
  `init`, around line 3420)
- Test: `tests/test_export.py` (payload), `tests/test_dashboard_logic.py`
  (the `pure.js` helpers — it runs them under node from pytest via `_run`)

**Interfaces:**
- Consumes: `_newest_season` from Task 1.
- Produces:
  - payload keys `season` (`"s10"` / `null`) and `next_season_start`
    (`"2026-09-07"`), read by `app.js` as `DATA.season` / `DATA.next_season_start`.
  - `seasonNote(season, liveCodes, nextStartISO, todayISO) -> string` in
    `pure.js` — the note's text, `''` when there is nothing to say.
  - `seasonLabel(season) -> string` in `pure.js` — `"s10"` → `"Season 10"`,
    `null` → `''`.

- [ ] **Step 1: Write the failing payload test**

In `tests/test_export.py`:

```python
def test_payload_names_the_season_it_rendered() -> None:
    """The page can render a season other than the pinned one (see the fallback
    in export_html), so the label must come from the data, not the flag."""
    db = _db_with_divisions(["S9 EMEA Master Central - Regular Season"])
    out = io.StringIO()
    export_html(db, out, only_season="s10")
    body = out.getvalue()
    assert '"season": "s9"' in body or '"season":"s9"' in body, \
        "payload must report the season actually rendered, not the pin"
```

- [ ] **Step 2: Run it to verify it fails**

```bash
.venv/Scripts/python.exe -m pytest tests/test_export.py -k payload_names_the_season -v
```

Expected: FAIL — there is no `season` key in the payload.

- [ ] **Step 3: Add the payload fields**

In `export_html`'s `data` dict (the one containing `"code_wipe": owdb_wipe`), add
next to `code_wipe`:

```python
        # The season actually rendered, which is NOT necessarily the pinned one:
        # export_html falls back when the pin has no data yet. The page labels
        # itself from this, so a fallback is visible rather than silent.
        "season": _newest_season(
            str(d["summary"]["championship"]) for d in divisions.values()
        ),
        # When the next FACEIT League season starts, so the page can say what
        # happens next while the current one is finished. One date, one place.
        "next_season_start": NEXT_SEASON_START,
```

And near `REGIONS`/`TIERS` at the top of the module's constants block (around
line 514):

```python
# When the next FACEIT League season's first matches are played. Shown on the
# page while the current season is over and the new one has no data yet; it
# stops being mentioned once the date has passed. Update it once per season —
# nothing derives from it, so a stale value degrades to silence, not a lie.
NEXT_SEASON_START = "2026-09-07"
```

- [ ] **Step 4: Run it to verify it passes**

```bash
.venv/Scripts/python.exe -m pytest tests/test_export.py -k payload_names_the_season -v
```

Expected: PASS.

- [ ] **Step 5: Write the failing `pure.js` tests**

`pure.js` is not tested from a JS runner — `tests/test_dashboard_logic.py` slices
everything above `bootApp(` out of the assembled template and executes it under
node from pytest, via its `_run(body, tmp_path)` helper. Add these there, in that
file's style:

```python
# --- season labelling ------------------------------------------------------
# The page can render a season other than the pinned one (export_html falls back
# when the pin has no data yet), so the label must be derived from the data. And
# between seasons there is nothing to capture at all: every code from the season
# that just ended predates the wipe that ended it, which is a thing the page has
# never said out loud.

def test_season_label_reads_as_prose(tmp_path) -> None:
    got = _run("return [seasonLabel('s10'), seasonLabel('s9'), seasonLabel(null)];",
               tmp_path)
    assert got == ["Season 10", "Season 9", ""]


def test_season_note_is_silent_while_codes_are_live(tmp_path) -> None:
    """The wipe note owns this slot whenever there is something to capture."""
    got = _run("return seasonNote('s9', 12, '2026-09-07', '2026-08-27');", tmp_path)
    assert got == ""


def test_season_note_explains_a_finished_season(tmp_path) -> None:
    got = _run("return seasonNote('s9', 0, '2026-09-07', '2026-08-27');", tmp_path)
    assert "Season 9" in got
    assert "Season 10" in got
    assert "7 September" in got


def test_season_note_stops_promising_a_date_once_it_passes(tmp_path) -> None:
    got = _run("return seasonNote('s9', 0, '2026-09-07', '2026-09-09');", tmp_path)
    assert "Season 10" in got
    assert "7 September" not in got,         "a date in the past must not be advertised as upcoming"


def test_season_note_is_silent_with_no_season_to_name(tmp_path) -> None:
    got = _run("return seasonNote(null, 0, '2026-09-07', '2026-08-27');", tmp_path)
    assert got == ""
```

- [ ] **Step 6: Run them to verify they fail**

```bash
.venv/Scripts/python.exe -m pytest tests/test_dashboard_logic.py -k season -v
```

Expected: FAIL — node exits non-zero with `seasonLabel is not defined`, surfaced
by `_run`'s `assert proc.returncode == 0`.

- [ ] **Step 7: Implement both helpers in `pure.js`**

Add beside `coverageState` (around line 139), which is the nearest neighbour in
both purpose and style:

```js
// 's10' -> 'Season 10'. The page renders the season it actually built from, so
// this reads the data rather than any flag.
function seasonLabel(season){
  const m=/^s(\d+)$/i.exec(String(season||''));
  return m ? `Season ${m[1]}` : '';
}

// The one line under the hero copy explaining the state of the season, for the
// weeks when there is nothing to capture. The wipe note owns this slot whenever
// live codes exist, so this returns '' in the normal case.
//
// Every S9 code predated the 2026-08-18 wipe, so between the end of one season
// and the first games of the next the funnel is dead and the page said nothing
// at all about why. A date already past is dropped rather than advertised.
function seasonNote(season, liveCodes, nextStartISO, todayISO){
  if(liveCodes) return '';
  const label=seasonLabel(season);
  if(!label) return '';
  const next=seasonLabel('s'+(parseInt(String(season).slice(1),10)+1));
  if(nextStartISO && todayISO && todayISO < nextStartISO){
    return `${label} has finished — every replay code from it was wiped by an `
      + `Overwatch patch, so there is nothing left to capture. `
      + `${next} starts ${longDate(nextStartISO)}.`;
  }
  return `${label} has finished. ${next} codes will appear here once matches `
    + `are played.`;
}

// '2026-09-07' -> '7 September'. Deliberately no year: the note only ever names
// a date inside the next few weeks.
function longDate(iso){
  const MONTHS=['January','February','March','April','May','June','July',
                'August','September','October','November','December'];
  const p=String(iso||'').split('-');
  if(p.length!==3) return '';
  return `${parseInt(p[2],10)} ${MONTHS[parseInt(p[1],10)-1]||''}`.trim();
}
```

If `pure.js` already has a long-date formatter, use it and delete `longDate` from
this snippet rather than shipping a second one — `grep -n "MONTHS\|toLocaleDate" faceit_sync/dashboard/pure.js`
before you add it.

- [ ] **Step 8: Run them to verify they pass**

```bash
.venv/Scripts/python.exe -m pytest tests/test_dashboard_logic.py -k season -v
```

Expected: 5 passed.

- [ ] **Step 9: Render the note and the label**

In `app.js`, replace the early return in the wipe-note renderer (around line
3415) so the slot falls through to the season note instead of hiding:

```js
  const el=document.getElementById('wipenote'); if(!el) return;
  const q=viewQueue();
  if(!CODE_WIPE || !q.length){
    // Nothing to capture. Rather than an empty slot, say why — between seasons
    // that is the single most useful sentence on the page.
    const note=seasonNote(DATA.season, q.length,
                          DATA.next_season_start, new Date().toISOString().slice(0,10));
    if(!note){ el.style.display='none'; return; }
    el.style.display='block';
    el.innerHTML=`<span style="color:var(--muted)">${esc(note)}</span>`;
    return;
  }
```

And in `init()` (around line 3420), after `recomputeDivision()`, set the label in
the brand block:

```js
  const slab=document.getElementById('seasonlab');
  if(slab) slab.textContent=seasonLabel(DATA.season);
```

- [ ] **Step 10: Add the label element to the shell**

In `faceit_sync/dashboard/head.html:560`, inside the `.brand` block, after the
existing `<span class="sub">FACEIT League</span>`:

```html
<span class="sub" id="seasonlab"></span>
```

Reuse the existing `.sub` class — do not add a new rule. A new colour or radius
here is exactly what `tests/test_ui_consistency.py` fails on.

- [ ] **Step 11: Run the JS syntax gate and the full suite**

```bash
.venv/Scripts/python.exe -m pytest tests/test_export.py::test_dashboard_javascript_is_syntactically_valid -v
.venv/Scripts/python.exe -m pytest
```

Expected: all green. A JS error here yields a completely blank page in
production, and the syntax test is the only thing standing between you and that.

- [ ] **Step 12: Look at it**

Build a throwaway copy from CI's DB (never `docs/index.html`) and screenshot it:

```bash
mkdir -p /tmp/s10check
gunzip -c docs/faceit.sqlite3.gz > /tmp/s10check/ci.sqlite3
.venv/Scripts/python.exe -m faceit_sync.cli --db /tmp/s10check/ci.sqlite3 \
  export --season s10 --format html --out /tmp/s10check/preview.html
```

Expected: it exports the S9 divisions (the fallback), the log carries
`season s10 has no data yet - falling back to s9`, the brand reads
"Season 9", and the hero note reads "Season 9 has finished … Season 10 starts
7 September." Screenshot with headless Edge using `--screenshot=FILE` — on
Windows `--dump-dom` produces no stdout.

- [ ] **Step 13: Commit**

```bash
git add faceit_sync/export.py faceit_sync/dashboard/head.html \
        faceit_sync/dashboard/pure.js faceit_sync/dashboard/app.js tests/
git commit -m "dashboard: label the season on the page and explain a finished one"
```

---

### Task 3: SA and OCE region support

The last piece of cutover code. It is inert until a SA or OCE championship exists
in the DB, which is exactly why it should land before anyone is under time
pressure. Four places in `faceit_sync` plus `tools/build_capture_data.py`'s own
copy of `REGIONS`, which is easy to miss and would leave the capture app's
division dropdown a region short.

`_region_of` already matches whole words, so `"S10 SA Master Central"` classifies
with no change, and the view builder is already generic over `REGIONS x TIERS`.

**Files:**
- Modify: `faceit_sync/export.py:514` (`REGIONS`), `:576` (`want_region`), `:567`
  (the `export_html` docstring)
- Modify: `faceit_sync/cli.py:235` (`--region` choices)
- Modify: `tools/build_capture_data.py:41` (its `REGIONS` copy)
- Modify: `AGENTS.md` (delete the IndexedDB rename promise — step 6)
- Test: `tests/test_export.py`, `tests/test_capture_feed.py`

**Interfaces:**
- Consumes: nothing from Tasks 1–2.
- Produces: `REGIONS == ("EMEA", "NA", "SA", "OCE")`, importable from
  `faceit_sync.export` — `cli.py` derives its `--region` choices from it rather
  than restating them.

- [ ] **Step 1: Write the failing tests**

```python
def test_sa_and_oce_are_supported_regions() -> None:
    from faceit_sync.export import REGIONS, _region_of

    assert REGIONS == ("EMEA", "NA", "SA", "OCE")
    assert _region_of("S10 SA Master Central - Regular Season") == "SA"
    assert _region_of("S10 OCE Master Central - Regular Season") == "OCE"
    # Whole-word matching, still: these must not classify.
    assert _region_of("S10 CANADA Master - Regular Season") is None


def test_single_division_region_gets_no_combined_view() -> None:
    """A 'Combined' view over one division is the same division twice."""
    db = _db_with_divisions(["S10 OCE Master Central - Regular Season",
                             "S10 EMEA Master Central - Regular Season",
                             "S10 EMEA Expert Central - Regular Season"])
    out = io.StringIO()
    export_html(db, out, only_season="s10")
    body = out.getvalue()
    assert "EMEA Combined" in body
    assert "OCE Combined" not in body


def test_region_filter_accepts_every_region_by_name() -> None:
    db = _db_with_divisions(["S10 SA Master Central - Regular Season",
                             "S10 EMEA Master Central - Regular Season"])
    out = io.StringIO()
    n = export_html(db, out, only_region="sa", only_season="s10")
    assert n == 1
    assert "SA Master" in out.getvalue()
```

And in `tests/test_capture_feed.py`, guarding the copy that is easy to forget:

```python
def test_capture_feed_regions_match_the_exporter() -> None:
    """tools/build_capture_data.py keeps its own REGIONS tuple; a region added
    to the site but not to the feed is a division missing from the capture
    app's dropdown, with nothing to say so."""
    import tools.build_capture_data as feed
    from faceit_sync.export import REGIONS

    assert tuple(feed.REGIONS) == REGIONS
```

- [ ] **Step 2: Run them to verify they fail**

```bash
.venv/Scripts/python.exe -m pytest tests/test_export.py -k "sa_and_oce or single_division_region or region_filter_accepts" -v
.venv/Scripts/python.exe -m pytest tests/test_capture_feed.py -k regions_match -v
```

Expected: FAIL — `REGIONS` is `("EMEA", "NA")`, and `only_region="sa"` currently
resolves to `None` (the prefix test only knows `e` and `n`), which silently
exports everything.

- [ ] **Step 3: Widen `REGIONS` and generalise the region filter**

`faceit_sync/export.py:514`:

```python
REGIONS: tuple[str, ...] = ("EMEA", "NA", "SA", "OCE")
```

Then replace the prefix hack in `export_html` (currently
`want_region = "EMEA" if w.startswith("e") else "NA" if w.startswith("n") else None`):

```python
    want_region: str | None = None
    if only_region:
        w = only_region.strip().lower()
        # Exact match on the region name, not a first-letter prefix: with SA and
        # OCE in play a prefix test is one new region away from resolving the
        # wrong one, and a wrong region exports silently rather than failing.
        want_region = next((r for r in REGIONS if r.lower() == w), None)
```

And update the `export_html` docstring, which currently says
`` ``only_region`` ('emea'/'na') ``:

```python
    ``only_region`` ('emea'/'na'/'sa'/'oce') restrict the dashboard; ...
```

- [ ] **Step 4: Derive the CLI choices from `REGIONS`**

`faceit_sync/cli.py:235` — replace the hardcoded tuple so the two can never
disagree:

```python
    e.add_argument("--region", choices=tuple(r.lower() for r in REGIONS), default=None,
                   help="restrict the HTML dashboard to one region (default: all)")
```

Add `REGIONS` to the existing `from faceit_sync.export import ...` line if it is
not already imported; do not add a second import statement.

- [ ] **Step 5: Move the capture feed's copy**

`tools/build_capture_data.py:41`:

```python
REGIONS = ("EMEA", "NA", "SA", "OCE")
```

Leave the existing comment that says it is kept in sync with
`faceit_sync.export.REGIONS` — the test added in step 1 is now what enforces it.

- [ ] **Step 6: Close the IndexedDB rename promise**

Still `AGENTS.md`, under Conventions. The name is invisible to users and renaming
orphans every contributor's learned refs and unsent captures; the decision on
2026-08-27 was to keep it permanently. Replace the "deliberately kept until the
Season 10 cutover …" sentence and the paragraph added after it with:

```markdown
  in code, CLI, and copy; the browser IndexedDB name `owscout-capture` is kept
  **permanently**. It is invisible to users — it appears in no UI, URL or
  document — and renaming it orphans every contributor's learned refs, unsent
  captures and scrim history for no gain. Decided 2026-08-27; do not re-open it
  at a season boundary.
```

- [ ] **Step 7: Run the tests to verify they pass**

```bash
.venv/Scripts/python.exe -m pytest tests/test_export.py -k "sa_and_oce or single_division_region or region_filter_accepts" -v
.venv/Scripts/python.exe -m pytest tests/test_capture_feed.py -k regions_match -v
```

Expected: 4 passed.

- [ ] **Step 8: Run the full gate**

```bash
.venv/Scripts/python.exe -m pytest
.venv/Scripts/python.exe -m mypy faceit_sync
```

Expected: all green. Watch for existing tests that assert the old two-region
tuple or the old `--region` choices — if one fails, it is asserting the old
world and should be updated, not worked around.

- [ ] **Step 9: Commit**

```bash
git add faceit_sync/export.py faceit_sync/cli.py tools/build_capture_data.py AGENTS.md tests/
git commit -m "export: support SA and OCE regions; close the IndexedDB rename as won't-do"
```

---

### Task 4: Freeze Season 9 at its own URL

S9 is final — last match 2026-08-17 — so this is built once and never rebuilt.
It is what makes every other decision here reversible: whatever the live site
does at the boundary, the complete S9 season stays readable.

Two traps. **Build from CI's DB, not the local one** (invariant 2 — the local
`faceit.sqlite3` is days behind). And the frozen page lands under `docs/`, where
two test suites glob every `*.html`; a frozen artefact can never be fixed in
response to a finding, so it must be excluded the same way `docs/index.html` is.

**Files:**
- Create: `docs/s9/index.html` (generated, committed once, never regenerated)
- Create: `docs/archive.html`
- Modify: `faceit_sync/dashboard/head.html` (footer link)
- Modify: `tests/test_ui_consistency.py:39` (`GENERATED`)
- Modify: `tests/test_page_csp_permits_own_scripts.py` (`GENERATED`)

**Interfaces:**
- Consumes: nothing. Deliberately independent of Tasks 1–3 — it can be done
  first if that suits.
- Produces: the URL `/s9/` and the index page `/archive.html`, which the shell
  footer links to.

- [ ] **Step 1: Exclude frozen archives from the page globs, test-first**

Both suites glob `docs/**/*.html` and exclude exactly `index.html`. Add the
failing expectation to `tests/test_ui_consistency.py`:

```python
def test_frozen_season_archives_are_excluded_from_page_checks() -> None:
    """A frozen archive is a generated export that can never be edited again —
    a finding against it could not be fixed even in principle. Same reasoning as
    docs/index.html, one step further along."""
    assert "s9/index.html" in GENERATED
```

- [ ] **Step 2: Run it to verify it fails**

```bash
.venv/Scripts/python.exe -m pytest tests/test_ui_consistency.py -k frozen_season -v
```

Expected: FAIL — `GENERATED` is `{"index.html"}`.

- [ ] **Step 3: Widen `GENERATED` in both suites**

Identically in `tests/test_ui_consistency.py:39` and
`tests/test_page_csp_permits_own_scripts.py`:

```python
# CI regenerates docs/index.html from faceit_sync/dashboard/head.html on every
# run, so a finding there would be reported against a file nobody edits. The
# dashboard is covered at its source instead. Frozen season archives
# (docs/s9/index.html, ...) are the same file one step further along: generated
# from the same template and then deliberately never rebuilt, so a finding
# against one could not be acted on even in principle.
GENERATED = {"index.html"} | {f"s{n}/index.html" for n in range(1, 30)}
```

- [ ] **Step 4: Run it to verify it passes**

```bash
.venv/Scripts/python.exe -m pytest tests/test_ui_consistency.py tests/test_page_csp_permits_own_scripts.py -v
```

Expected: all pass.

- [ ] **Step 5: Build the archive from CI's database**

Never from the local `faceit.sqlite3`.

```bash
mkdir -p /tmp/s9freeze
gunzip -c docs/faceit.sqlite3.gz > /tmp/s9freeze/ci.sqlite3
.venv/Scripts/python.exe -m owdb.cli --faceit-db /tmp/s9freeze/ci.sqlite3 \
  contribute merge --dir data/captures/s9 --out /tmp/s9freeze/owdb_comps.json
cp /tmp/s9freeze/owdb_comps.json ./owdb_comps.json
mkdir -p docs/s9
.venv/Scripts/python.exe -m faceit_sync.cli --db /tmp/s9freeze/ci.sqlite3 \
  export --season s9 --format html --out docs/s9/index.html
rm ./owdb_comps.json
```

`export` reads `owdb_comps.json` from the repo root, which is why it is copied in
and then removed. **Never commit it** (invariant 6) — confirm with `git status`
before staging that only `docs/s9/index.html` is new.

Expected: `wrote docs/s9/index.html (N division(s))` with N = 6, and a file of
roughly 8–9 MB. If N is smaller, the merge or the DB is wrong — stop and find out
why rather than committing a partial season.

- [ ] **Step 6: Write `docs/archive.html`**

A static index. It links `theme.css` and must read the palette key like every
other hand-authored page, or `tests/test_ui_consistency.py` fails it. The CSP is
copied from `docs/scrims.html` minus what this page does not use.

```html
<!doctype html>
<html lang="en" data-theme="dark">
<head>
<meta charset="utf-8">
<script>
// Apply the remembered palette before first paint (no flash). Shares the
// dashboard's owdb.palette localStorage key across the origin.
(function(){try{
  var p=localStorage.getItem('owdb.palette');
  if(['violet','ocean','forest','sunset','teal','overwatch'].indexOf(p)>=0) document.documentElement.setAttribute('data-palette',p);
  else document.documentElement.setAttribute('data-palette','original');
}catch(e){}})();
</script>
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>owdb &mdash; Past seasons</title>
<meta name="description" content="Frozen end-of-season snapshots of the owdb FACEIT League scouting site.">
<meta name="theme-color" content="#0d1015">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline' 'self'; img-src 'self' data:; connect-src 'none'; font-src 'self' data:; object-src 'none'; frame-src 'none'; base-uri 'self'; form-action 'none'">
<link rel="stylesheet" href="theme.css">
</head>
<body>
<div class="topbar"><div class="topbar-in"><div class="toprow">
  <div class="brand"><span class="prodname"><span class="wordmark"><span class="br">[</span><span class="ow">ow</span><span class="db">db</span><span class="br">]</span></span><span class="sub">Past seasons</span></span></div>
  <div class="sidebox"><div class="sidetoggle"><a href="./">Current season</a></div></div>
</div></div></div>
<main style="max-width:760px;margin:28px auto;padding:0 20px">
  <div class="card">
    <p class="eyebrow">Past seasons</p>
    <p class="note">Each past season is frozen exactly as it stood when the season
    ended, at its own address. Nothing in them changes again — the replay codes
    they link to were wiped by later Overwatch patches, and the rosters are the
    ones that played, not the ones that exist now.</p>
    <p><a class="btn" href="s9/">Season 9 &rarr;</a></p>
    <p class="faint">Season 9 ran to 17 August 2026: EMEA Master, Expert and
    Advanced; NA Master and Expert; regular seasons and playoffs.</p>
  </div>
</main>
<footer style="max-width:760px;margin:32px auto 20px;padding:16px 20px;border-top:1px solid var(--line);color:var(--faint);font-size:12px;line-height:1.6">
  <b style="color:var(--muted)">owdb</b> &mdash; community Overwatch 2 scouting for the FACEIT League.
  Not affiliated with, endorsed by, or sponsored by FACEIT or Blizzard Entertainment.
  Overwatch is a trademark of Blizzard Entertainment.
</footer>
</body>
</html>
```

If `tests/test_ui_consistency.py` reports that this page reads the palette key
but never sets `data-palette`, or vice versa, the bootstrap script above is the
thing it is talking about — both assertions are satisfied by it, so a failure
means it was altered.

- [ ] **Step 7: Link it from the live shell**

In `faceit_sync/dashboard/head.html:595`, extend the footer line:

```html
  Overwatch is a trademark of Blizzard Entertainment. <a href="archive.html" style="color:var(--muted)">Past seasons</a> <span id="footbuilt"></span>
```

- [ ] **Step 8: Run the full gate**

```bash
.venv/Scripts/python.exe -m pytest
.venv/Scripts/python.exe -m pytest tests/test_export.py::test_dashboard_javascript_is_syntactically_valid -v
```

Expected: all green, including the two page-glob suites now seeing
`docs/archive.html` for the first time.

- [ ] **Step 9: Check both pages in a browser**

```bash
.venv/Scripts/python.exe -m http.server 8000 --directory docs
```

Open `http://localhost:8000/archive.html` and `http://localhost:8000/s9/`.
Verify over `http://localhost:8000`, **never** `file://`. Confirm: the archive
page is themed (not unstyled), the palette picker choice made on another page
carries to it, `/s9/` loads a full working S9 dashboard with its divisions and
captured comps, and its replay codes render as "code wiped" rather than as live
chips.

- [ ] **Step 10: Commit**

```bash
git status                     # confirm owdb_comps.json is NOT staged
git add docs/s9/index.html docs/archive.html faceit_sync/dashboard/head.html tests/
git commit -m "docs: freeze Season 9 at /s9/ and add a past-seasons index"
```

---

### Task 5: Prepare the cutover commit (do not apply it yet)

With Task 1 in place the export pin is safe to flip early — it falls back until
S10 has data. The other two season constants are **not** guarded, and they must
move together with it: if CI merges `data/captures/s9` while the site renders
S10, every team's Season 9 comps attach to their Season 10 page by team id, which
is precisely the hazard season-scoped captures exist to prevent.

So this is one commit plus one human `wrangler deploy`, applied when S10 has
results. Writing it now means the boundary is a paste, not a design session.

**Files (when applied):**
- Modify: `.github/workflows/update.yml:136` and `:149`
- Modify: `infra/upload-worker/worker.js:35`

- [ ] **Step 1: Record the exact change in the design document**

Append to `specs/2026-08-10-season10-cutover-design.md` §6.4 group C, so the
runbook holds the literal diff rather than a description of one:

```markdown
The group C change in full — three lines, one commit, then a human deploy:

    .github/workflows/update.yml:136
    -  ... contribute merge --dir data/captures/s9 --out owdb_comps.json ...
    +  ... contribute merge --dir data/captures/s10 --out owdb_comps.json ...

    .github/workflows/update.yml:149
    -  faceit-sync --db faceit.sqlite3 export --season s9 --format html --out docs/index.html
    +  faceit-sync --db faceit.sqlite3 export --season s10 --format html --out docs/index.html

    infra/upload-worker/worker.js:35
    -  const CURRENT_SEASON = "s9";
    +  const CURRENT_SEASON = "s10";

Then `wrangler deploy` (human). The export line is the only one the fallback
protects; flipping it alone is safe at any time, flipping the merge line early
is not.
```

- [ ] **Step 2: Commit the runbook, not the change**

```bash
git add specs/2026-08-10-season10-cutover-design.md
git commit -m "spec: record the S10 cutover as a literal three-line diff"
```

- [ ] **Step 3: Verify nothing in `docs/` or CI moved**

```bash
git diff HEAD~1 --stat
```

Expected: one file changed, `specs/2026-08-10-season10-cutover-design.md`. If
`update.yml` or `worker.js` appear here, the cutover has been applied early —
revert them.

---

## Self-review

**Spec coverage.** §6.4 group A item 1 (freeze the archive, built from CI's DB) →
Task 4. Item 2 (SA/OCE region support, including `build_capture_data.py`'s copy)
→ Task 3. Item 3 (decide the IndexedDB rename) → Task 3 step 6. Item 4
(relegation) → out of scope by decision, recorded above. §6.2's "nothing says the
season is over" → Task 2. §6.3's cutover trigger → Tasks 1 and 5 together: the
fallback makes the trigger self-executing, and Task 5 keeps the two unguarded
constants moving with it. §6.4 group C → Task 5. Group B (seeding) is the
operator's, and needs S10 rooms that do not exist yet. §6.6's open questions are
listed as out of scope with their reasons.

**Type consistency.** `_newest_season` is defined in Task 1 and consumed in Task
2 with the same signature. `seasonLabel`/`seasonNote`/`longDate` are defined in
Task 2 step 7 and called in step 9 with matching arity. The payload keys `season`
and `next_season_start` are written in Task 2 step 3 and read in step 9 as
`DATA.season` / `DATA.next_season_start`. `REGIONS` is widened once in Task 3 and
consumed by `cli.py` and `build_capture_data.py` in the same task.

**Resolved before execution.** The two loose references in the first draft were
checked against the repo rather than left to the executor: the fixture pattern is
`test_season_filter_narrows_the_export` (`tests/test_export.py:520`), factored
into `_seed_divisions`/`_payload` in Task 1; and the `pure.js` helpers are tested
from `tests/test_dashboard_logic.py`, which executes them under node from pytest
via `_run` — there is no JS-native test runner in this repo.

**Remaining soft spot.** Task 4 step 5's expected division count (6) comes from
the CI DB as of 2026-08-24. Sanity-check it against what the export actually
prints rather than asserting it blindly; a smaller number means the merge or the
DB is wrong, and a partial season must not be frozen.

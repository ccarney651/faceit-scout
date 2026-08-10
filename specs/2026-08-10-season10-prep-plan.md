# Season 10 prep (safe-now subset) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Land the part of `specs/2026-08-10-season10-cutover-design.md` that's safe to ship today — season-aware export filtering, and migrating captures to a season-scoped layout — without waiting for Season 9 to finish and without changing what the live site currently shows.

**Architecture:** Season is parsed from the FACEIT championship name (`"S9 EMEA Advanced Central - Regular Season"`) exactly the way region/tier already are (`_region_of`/`_tier_of` in `faceit_sync/export.py`) — no schema change, no DB writes. Captures move from a flat `data/captures/*.json` layout to `data/captures/<season>/*.json`, with `s9` as the first season directory; both writers (the Cloudflare Worker for browser uploads, and the Python CLI's curator-fallback push) get a single season constant each so a future cutover is a one-line bump, not a migration.

**Tech Stack:** Python 3.12 (`faceit_sync`, `owdb`), pytest, Cloudflare Workers (vanilla JS, no framework), GitHub Actions.

## Global Constraints

- `faceit_sync` must stay `mypy --strict` clean (`CLAUDE.md`).
- Always run `pytest tests/test_export.py::test_dashboard_javascript_is_syntactically_valid` after touching anything that could affect the generated dashboard — not expected to apply to this plan (no `faceit_sync/dashboard/` part file changes), but the constraint is repo-wide.
- `wrangler deploy` is run by the human, never by Claude (`CLAUDE.md` gotcha). Task 5 below ends at a hard stop for exactly this reason.
- Don't touch `docs/index.html`'s live behavior — no `--season s10` anywhere yet (S10 doesn't exist in the DB), no `docs/s9/index.html`, no `docs/archive.html`. Those stay out of scope until Season 9 actually finishes.

---

### Task 1: `_season_of()` — parse season from a championship name

**Files:**
- Modify: `faceit_sync/export.py` (near `_region_of`/`_tier_of`, `export.py:496-524`)
- Test: `tests/test_export.py` (near `test_tier_and_region_classify_championship_names`, `test_export.py:275-303`)

**Interfaces:**
- Produces: `_season_of(name: str | None) -> str | None` — returns the lowercase season token (e.g. `"s9"`) or `None`. Consumed by Task 2.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_export.py`, right after `test_tier_and_region_classify_championship_names` (around line 289):

```python
def test_season_classifies_championship_names() -> None:
    """Season is embedded in the same championship-name string region/tier
    already parse ("S9 EMEA Advanced Central - Regular Season")."""
    from faceit_sync.export import _season_of

    assert _season_of("S9 EMEA Master Central - Regular Season") == "s9"
    assert _season_of("S9 NA Expert Central - Playoffs") == "s9"
    assert _season_of("S10 EMEA Master Central - Regular Season") == "s10"
    assert _season_of("Winter Finale Cup") is None
    assert _season_of(None) is None


def test_season_matches_whole_word_only() -> None:
    """A bare prefix/substring test would let 'S90 EMEA...' match 's9', or let
    a name merely containing 's9' mid-word false-match. Word-boundary regex,
    mirroring the _region_of guard just above."""
    from faceit_sync.export import _season_of

    assert _season_of("S90 EMEA Master Central - Regular Season") == "s90"
    assert _season_of("S9 EMEA Master Central - Regular Season") == "s9"
    assert _season_of("Class9 Something") is None
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/Scripts/python.exe -m pytest tests/test_export.py::test_season_classifies_championship_names tests/test_export.py::test_season_matches_whole_word_only -v`
Expected: FAIL with `ImportError: cannot import name '_season_of'`

- [ ] **Step 3: Implement `_season_of`**

In `faceit_sync/export.py`, add right after the `_region_of` function (after line 524, before `_is_playoff`):

```python
_SEASON_RE = re.compile(r"\bS(\d+)\b", re.IGNORECASE)


def _season_of(name: str | None) -> str | None:
    """The season a championship name encodes ('s9', 's10', ...), or None.

    Matched with a word boundary (mirrors ``_region_of``): a bare substring
    test would let "S90 EMEA..." match "s9", or a name merely containing
    "s9" mid-word false-match.
    """
    if not name:
        return None
    m = _SEASON_RE.search(name)
    return f"s{m.group(1)}" if m else None
```

Check the top of `faceit_sync/export.py` for an existing `import re` — add one if it's not already imported (region/tier parsing doesn't use regex today, so it's likely missing).

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv/Scripts/python.exe -m pytest tests/test_export.py::test_season_classifies_championship_names tests/test_export.py::test_season_matches_whole_word_only -v`
Expected: PASS

- [ ] **Step 5: mypy**

Run: `.venv/Scripts/python.exe -m mypy faceit_sync`
Expected: no new errors.

- [ ] **Step 6: Commit**

```bash
git add faceit_sync/export.py tests/test_export.py
git commit -m "Add _season_of() championship-name parsing"
```

---

### Task 2: `--season` export filter

**Files:**
- Modify: `faceit_sync/export.py` (`export_html` signature/body, `export.py:535-563`)
- Modify: `faceit_sync/cli.py` (`cmd_export`, `cli.py:114-136`; `export` subparser, `cli.py:228-241`)
- Test: `tests/test_export.py` (near `test_region_filter_still_narrows_the_export`, `test_export.py:344-363`)

**Interfaces:**
- Consumes: `_season_of()` from Task 1.
- Produces: `export_html(..., only_season: str | None = None, ...)` narrows the championship set. CLI `faceit-sync export --season s9`.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_export.py`, right after `test_region_filter_still_narrows_the_export` (around line 363):

```python
def test_season_filter_narrows_the_export(db: Database) -> None:
    """--season restricts the export to one season's championships — the
    mechanism the future S9/S10 cutover relies on."""
    c = db.conn
    c.execute("INSERT INTO maps(guid,name,category) VALUES('m1','Ilios','Control')")
    for tid, nm in [("t1", "Alpha"), ("t2", "Bravo")]:
        c.execute("INSERT INTO teams(id,name) VALUES(?,?)", (tid, nm))
    for cid, nm in [("s9m", "S9 EMEA Master Central - Regular Season"),
                    ("s10m", "S10 EMEA Master Central - Regular Season")]:
        c.execute("INSERT INTO championships(id,name,game,region) VALUES(?,?,?,'GLOBAL')",
                  (cid, nm, "ow2"))
        _insert_match(db, cid, f"m-{cid}", "FINISHED", "t1", "t2", "faction1", None,
                      "2026-07-20T20:00:00Z", 1, ["faction1", "faction1"])
    db.conn.commit()

    buf = io.StringIO()
    export_html(db, buf, only_season="s9")
    data = json.loads(re.search(r"var __OWDB_DATA__=(\{.*\});", buf.getvalue())
                      .group(1).replace("<\\/", "</"))
    assert [v["label"] for v in data["views"]] == ["EMEA Master"]
    assert list(data["divisions"].keys()) == ["s9m"]
```

This follows the same `db: Database` pytest-fixture pattern (from `tests/conftest.py:31`) that `test_region_filter_still_narrows_the_export` already uses — no manual `Database(...)` construction needed. `Database` and `_insert_match` are already imported/defined earlier in `tests/test_export.py` (the same ones `test_region_filter_still_narrows_the_export` uses).

- [ ] **Step 2: Run the test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/test_export.py::test_season_filter_narrows_the_export -v`
Expected: FAIL with `TypeError: export_html() got an unexpected keyword argument 'only_season'`

- [ ] **Step 3: Implement the filter in `export_html`**

In `faceit_sync/export.py`, update the signature and filtering block (around lines 535-563):

```python
def export_html(db: Database, out: TextIO, championship_id: str | None = None,
                only_tier: str | None = None, only_region: str | None = None,
                only_season: str | None = None,
                data_path: str | None = None) -> int:
    """Render the multi-division dashboard.

    With ``championship_id`` set, only that division is included; otherwise every
    championship in the database becomes a switchable division. ``only_tier``
    (master/expert/advanced/open), ``only_region`` ('emea'/'na') and
    ``only_season`` ('s9', 's10', ...) restrict the dashboard; the DB may hold
    several divisions across tiers, regions and (once a cutover has happened)
    seasons. Returns the number of divisions with data.
    """
    want_tier: str | None = None
    if only_tier:
        w = only_tier.strip().lower()
        want_tier = next((t for t in TIERS if t.lower() == w), None)
    want_region: str | None = None
    if only_region:
        w = only_region.strip().lower()
        want_region = "EMEA" if w.startswith("e") else "NA" if w.startswith("n") else None
    want_season: str | None = only_season.strip().lower() if only_season else None

    if championship_id:
        cids = [championship_id]
    else:
        rows = db.conn.execute("SELECT id, name FROM championships ORDER BY name").fetchall()
        if want_tier:
            rows = [r for r in rows if _tier_of(r["name"]) == want_tier]
        if want_region:
            rows = [r for r in rows if _region_of(r["name"]) == want_region]
        if want_season:
            rows = [r for r in rows if _season_of(r["name"]) == want_season]
        cids = [str(r["id"]) for r in rows]
```

(Only the `only_season`/`want_season` lines are new; everything else in that block is unchanged context to locate the edit.)

- [ ] **Step 4: Wire the CLI flag**

In `faceit_sync/cli.py`, add the argument next to `--region` in the `export` subparser (around line 234-235):

```python
    e.add_argument("--season", default=None,
                   help="restrict the HTML dashboard to one season, e.g. 's9' (default: all)")
```

And pass it through in `cmd_export` (around line 126-128, in the `export_html(...)` call):

```python
                n = export_html(db, out, championship_id=args.championship,
                                only_tier=args.tier, only_region=args.region,
                                only_season=args.season,
                                data_path=data_path)
```

- [ ] **Step 5: Run the test to verify it passes**

Run: `.venv/Scripts/python.exe -m pytest tests/test_export.py::test_season_filter_narrows_the_export -v`
Expected: PASS

- [ ] **Step 6: Run the full export test file + mypy**

Run: `.venv/Scripts/python.exe -m pytest tests/test_export.py -v` — expect all PASS.
Run: `.venv/Scripts/python.exe -m mypy faceit_sync` — expect no new errors.

- [ ] **Step 7: Commit**

```bash
git add faceit_sync/export.py faceit_sync/cli.py tests/test_export.py
git commit -m "Add --season export filter"
```

---

### Task 3: CI safety net — pin the live export to `--season s9`

**Files:**
- Modify: `.github/workflows/update.yml` (export step, `update.yml:139-144`)

**Interfaces:**
- Consumes: `--season` flag from Task 2.

**Why now, not at cutover:** This is a no-op today (S9 is the only season the DB holds), but once S10 championship IDs are added to `matches.txt` — which will happen before S9's playoffs are even done, per the design's overlap-period requirement — an un-pinned export would immediately start showing S10 divisions on the live site the moment they're ingested. Pinning now closes that gap before it can ever open.

- [ ] **Step 1: Edit the workflow**

In `.github/workflows/update.yml`, the export line currently reads (around line 144):

```yaml
          faceit-sync --db faceit.sqlite3 export --format html --out docs/index.html
```

Change it to:

```yaml
          # --season s9 pins the live site to Season 9 even once S10 championship
          # ids start appearing in the DB during the overlap period (S10 seeded
          # into matches.txt before S9's playoffs finish). Bump to s10 at the
          # actual cutover — see specs/2026-08-10-season10-cutover-design.md.
          faceit-sync --db faceit.sqlite3 export --season s9 --format html --out docs/index.html
```

- [ ] **Step 2: Sanity-check locally**

This can't be run as a GitHub Actions job locally, but confirm the CLI call itself works against the real local DB:

Run: `.venv/Scripts/faceit-sync.exe --db faceit.sqlite3 export --season s9 --format html --out /tmp/season-check.html`
Expected: `wrote /tmp/season-check.html (N division(s))` where N matches today's normal (unfiltered) division count, since every division currently in the DB is S9.

- [ ] **Step 3: Commit**

```bash
git add .github/workflows/update.yml
git commit -m "Pin the live export to --season s9 ahead of the S10 overlap period"
```

---

### Task 4: Season-scope `CONTRIB_DIR` (Python side)

**Files:**
- Modify: `owdb/contribute.py` (`CONTRIB_DIR`, `contribute.py:52`)
- Modify: `owdb/cli.py` (help text, `cli.py:1219`)

**Interfaces:**
- Produces: `owdb.contribute.CONTRIB_DIR == "data/captures/s9"`. Consumed by `cmd_contribute_export`'s default `--out`, `cmd_contribute_push`'s curator-fallback path, and `contribute merge`/`unscout`'s default `--dir` (all already read `CONTRIB_DIR` — no other code change needed, confirmed via `grep CONTRIB_DIR`).

This task changes a *default value only*; no capture files move yet (that's Task 6, which depends on Task 5's Worker deploy landing first).

- [ ] **Step 1: Change the constant**

In `owdb/contribute.py`, line 52:

```python
CONTRIB_DIR = "data/captures/s9"
```

- [ ] **Step 2: Update the CLI help text**

In `owdb/cli.py`, line 1219, the `contribute export` subparser's `--out` help currently hardcodes the old path:

```python
    ce.add_argument("--out", default=None, help="output path (default: data/captures/<name>.json)")
```

Change the string to reflect the new default:

```python
    ce.add_argument("--out", default=None, help="output path (default: data/captures/s9/<name>.json)")
```

- [ ] **Step 3: Run the owdb test suite**

Run: `.venv/Scripts/python.exe -m pytest owdb/tests -v`
Expected: all PASS. (Confirmed during planning: `owdb/tests/test_contribute.py`'s `push_contribution` tests pass an explicit literal `path=` argument and don't reference `CONTRIB_DIR`, so they're unaffected by this change.)

- [ ] **Step 4: Commit**

```bash
git add owdb/contribute.py owdb/cli.py
git commit -m "Season-scope CONTRIB_DIR to data/captures/s9"
```

---

### Task 5: Season-scope the upload Worker — code change + human deploy checkpoint

**Files:**
- Modify: `infra/upload-worker/worker.js` (write path `worker.js:198`, admin detail read path `worker.js:419`)

**Interfaces:**
- Produces: uploads land at `data/captures/${CURRENT_SEASON}/${claimKey}.json`.

**This task ends at a hard stop.** Per `CLAUDE.md`, `wrangler deploy` is run by the human, never by Claude. Task 6 (moving the existing flat capture files) must not start until this deploy is confirmed live — otherwise a capture uploaded in the gap between "Task 6's `git mv`" and "the Worker actually writing to the new path" would land in the old flat location and be silently missed by a CI merge step already pointed only at `data/captures/s9`. Deploying first closes that gap: once this is live, every new upload already lands under `s9/`, so Task 6's `git mv` only has to catch what's still flat.

- [ ] **Step 1: Add the season constant**

In `infra/upload-worker/worker.js`, add near the other top-level constants (after line 31, `const FORMAT = 1;`):

```javascript
// Bump at each season cutover — see specs/2026-08-10-season10-cutover-design.md
// for the full runbook. Every upload path below is keyed off this so a cutover
// is a one-line change, not a migration.
const CURRENT_SEASON = "s9";
```

- [ ] **Step 2: Season-scope the upload write path**

Change line 198 from:

```javascript
    const path = `data/captures/${claimKey}.json`;
```

to:

```javascript
    const path = `data/captures/${CURRENT_SEASON}/${claimKey}.json`;
```

- [ ] **Step 3: Season-scope the admin detail read path**

Change line 419 from:

```javascript
  const gh = await fetch(`https://api.github.com/repos/${env.REPO}/contents/data/captures/${encodeURIComponent(key)}.json`, {
```

to:

```javascript
  const gh = await fetch(`https://api.github.com/repos/${env.REPO}/contents/data/captures/${CURRENT_SEASON}/${encodeURIComponent(key)}.json`, {
```

(This is the admin panel's "view a contributor's file" endpoint — easy to miss since it's a second, independent hardcoded copy of the same path template used for uploads. Without this change, the admin panel would 404 looking up any contributor whose file already moved to `s9/`.)

- [ ] **Step 4: Update the file's own doc comment**

Line 13 currently reads:

```
 *  - a name writes exactly one file: data/captures/<name>.json
```

Change to:

```
 *  - a name writes exactly one file: data/captures/<season>/<name>.json
```

- [ ] **Step 5: Commit**

```bash
git add infra/upload-worker/worker.js
git commit -m "Season-scope the upload worker's capture write/read paths"
```

- [ ] **Step 6: HARD STOP — ask the user to deploy, and wait for confirmation**

Tell the user: "worker.js is committed. Please run `wrangler deploy` from `infra/upload-worker/` when ready, and let me know once it's live — Task 6 (moving the existing capture files) depends on the new path already being live, so new uploads never land in the old flat location." Do not proceed to Task 6 until they confirm.

---

### Task 6: Migrate existing capture files to `data/captures/s9/`

**Files:**
- Modify: `data/captures/*.json` → `data/captures/s9/*.json` (git mv)
- Modify: `.github/workflows/update.yml` (merge step, `update.yml:135`)

**Interfaces:**
- Consumes: Task 5's Worker deploy must be confirmed live first (see Task 5 Step 6).

**Known risk this task must verify, not just assume away:** `owdb.contribute.git_submission_order()` (`owdb/contribute.py:980-1023`) decides who owns a *contested* map (the same `match_id`/`game_no` captured by two contributors) by running `git log --diff-filter=A --name-only -- <paths>` against each file's *current* path and taking the oldest "Added" date. A `git mv` deletes the old path and adds the new one in the same commit — without rename detection in play, that commit is indistinguishable from "this file has never existed before now" for every moved file simultaneously, which would silently collapse all contested-map tie-breaks among today's contributors to a single instant (falling back to alphabetical-by-filename) instead of the real historical commit order. There's no existing test coverage of `git_submission_order` to catch this. Rather than touch that function's git-shelling logic (untested, and deliberately batched for performance — not something to risk changing under this task), this task verifies the actual before/after merge output directly and pins anything that changed using the existing `overrides.json` mechanism.

- [ ] **Step 1: Capture the baseline merge output (before moving anything)**

```bash
mkdir -p /tmp/season10-prep-check
.venv/Scripts/owdb.exe --faceit-db faceit.sqlite3 contribute merge \
  --dir data/captures --out /tmp/season10-prep-check/pre.json \
  --captured-out /tmp/season10-prep-check/pre-captured.json
```

- [ ] **Step 2: Move the files**

```bash
ls data/captures/*.json
mkdir -p data/captures/s9
git mv data/captures/*.json data/captures/s9/
```

Run the `ls` first and eyeball the list — it should be every contributor file that existed before Task 5's Worker deploy landed, plus possibly one or two more if a capture was uploaded in the gap between the deploy and now (those still land at the flat path if uploaded before the deploy, or at `data/captures/s9/` directly if uploaded after — the `git mv *.json` above only catches ones still sitting flat, which is exactly what's wanted).

- [ ] **Step 3: Capture the post-move merge output**

```bash
.venv/Scripts/owdb.exe --faceit-db faceit.sqlite3 contribute merge \
  --dir data/captures/s9 --out /tmp/season10-prep-check/post.json \
  --captured-out /tmp/season10-prep-check/post-captured.json
```

- [ ] **Step 4: Diff and resolve any reordering**

`merged_payload` stamps a fresh `payload["built_at"] = datetime.now(UTC)...`
on every call (`owdb/contribute.py:572`), so a raw `diff` between `pre.json`
and `post.json` will ALWAYS show at least that one field changing, even when
nothing else did — a guaranteed false positive. Strip it before comparing:

```bash
.venv/Scripts/python.exe - <<'PY'
import difflib
import json

with open("/tmp/season10-prep-check/pre.json", encoding="utf-8") as f:
    pre = json.load(f)
with open("/tmp/season10-prep-check/post.json", encoding="utf-8") as f:
    post = json.load(f)
pre.pop("built_at", None)
post.pop("built_at", None)

if pre == post:
    print("IDENTICAL (ignoring built_at) — no contested-map reordering.")
else:
    a = json.dumps(pre, indent=2, sort_keys=True).splitlines()
    b = json.dumps(post, indent=2, sort_keys=True).splitlines()
    print("\n".join(difflib.unified_diff(a, b, "pre", "post", lineterm="")))
PY
```

- If it prints **IDENTICAL**: no contested maps were affected — proceed to Step 5.
- If it prints a **diff**: for each map whose owning contributor changed, add an explicit entry to a new `data/captures/s9/overrides.json` pinning it back to the pre-move winner. The override format is documented in `owdb/contribute.py` around `OVERRIDES_FILE`/`load_overrides` (`contribute.py:279` onward) — read that code for the exact JSON shape before writing the file, since this plan is written without knowing in advance whether any map is actually contested. Re-run Step 3's command after adding overrides and re-run this diff, confirming it now prints IDENTICAL before proceeding.

- [ ] **Step 5: Update the CI merge step**

In `.github/workflows/update.yml`, line 135 currently reads:

```yaml
            owdb --faceit-db faceit.sqlite3 contribute merge --dir data/captures --out owdb_comps.json --captured-out docs/captured.json
```

Change `--dir data/captures` to `--dir data/captures/s9`:

```yaml
            owdb --faceit-db faceit.sqlite3 contribute merge --dir data/captures/s9 --out owdb_comps.json --captured-out docs/captured.json
```

Also check the comment above it (around line 128-133, "Scouting data arrives as RAW OBSERVATIONS, one file per contributor under data/captures/...") and update `data/captures/` to `data/captures/s9/` there too so the comment matches the real path.

- [ ] **Step 6: Full local rebuild sanity check**

```bash
.venv/Scripts/faceit-sync.exe --db faceit.sqlite3 export --season s9 --format html --out /tmp/season10-prep-check/dashboard.html
```

Expected: succeeds, same division count as Task 3's Step 2 check. (This doesn't exercise the capture merge — that's already verified in Steps 3-4 — it's just confirming the season filter and the rest of the pipeline still work together after the directory move.)

- [ ] **Step 7: Run the full test suite**

Run: `.venv/Scripts/python.exe -m pytest -v`
Expected: all PASS.

- [ ] **Step 8: Commit**

```bash
git add data/captures .github/workflows/update.yml
git commit -m "Migrate captures to data/captures/s9/"
```

(If Step 4 required adding `data/captures/s9/overrides.json`, that file is included in this `git add data/captures` already.)

---

### Task 7: Document the new convention and the future cutover runbook

**Files:**
- Modify: `CLAUDE.md`

**Interfaces:** None — documentation only, no code interfaces.

- [ ] **Step 1: Fix the Commands section example**

`CLAUDE.md`'s Commands section currently shows:

```
owdb ... contribute merge --dir data/captures --out owdb_comps.json  # merge captures
```

Change to:

```
owdb ... contribute merge --dir data/captures/s9 --out owdb_comps.json  # merge captures
```

- [ ] **Step 2: Update the data-flow fact about captures**

`CLAUDE.md`'s "Data-flow facts" list, point 3, currently reads:

```
3. **`data/captures/<contributor>.json` is committed; `owdb_comps.json` is
   generated at build and NOT committed** — the report is always recomputed from
   raw observations so analysis improvements apply retroactively. The CI merge
   does first-wins on contested maps by commit date.
```

Change the first line to:

```
3. **`data/captures/<season>/<contributor>.json` is committed; `owdb_comps.json`
   is generated at build and NOT committed** — the report is always recomputed
   from raw observations so analysis improvements apply retroactively. The CI
   merge does first-wins on contested maps by commit date.
```

- [ ] **Step 3: Add a Gotchas bullet for the season convention + cutover pointer**

In `CLAUDE.md`'s `## Gotchas` section, add a new bullet (alongside the existing "Replay codes are invalidated..." one), pointing at the design spec rather than duplicating its runbook:

```markdown
- **Captures are season-scoped** (`data/captures/<season>/`, currently `s9`).
  Both writers — the upload Worker (`infra/upload-worker/worker.js`
  `CURRENT_SEASON`) and the Python CLI's curator-fallback push
  (`owdb/contribute.py` `CONTRIB_DIR`) — key off a single per-season constant
  each. When Season 9 actually finishes, follow the cutover runbook in
  `specs/2026-08-10-season10-cutover-design.md` (archive export, bump both
  constants, add S10 to `matches.txt`, flip the live `--season` filter in
  `update.yml`) rather than improvising — the design doc has the full sequence
  and the reasoning behind it.
```

- [ ] **Step 4: Commit**

```bash
git add CLAUDE.md
git commit -m "Document season-scoped captures and point to the cutover runbook"
```

---

## Self-review notes (for whoever executes this plan)

- Tasks 1-4 have no ordering dependency on each other beyond needing Task 1 before Task 2 (both touch `export.py`/tests) — they could run in either order relative to Tasks 5-6.
- Tasks 5 → 6 have a **hard** ordering dependency with a human-in-the-loop checkpoint in between (Task 5 Step 6). Do not skip or reorder this.
- Task 7 should run last since it documents the end state of Tasks 1-6.
- If Task 6 Step 4 finds a contested map and needs an `overrides.json` entry, re-read `owdb/contribute.py`'s override-loading code before writing it — this plan intentionally does not guess at the exact JSON shape since it wasn't verified against a real contested-map case during planning.

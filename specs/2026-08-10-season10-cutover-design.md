# Season 10 cutover — design

**Date:** 2026-08-10
**Status:** approved, ready for implementation planning

## Goal

Define how the site, the ingest DB, and captures behave when FACEIT League
moves from Season 9 to Season 10 — without disrupting Season 9 while it's
still live, and without losing Season 9's data once it isn't.

The site stays on **GitHub Pages** — nothing about a season transition
requires new hosting; the DB, the Cloudflare Worker, and the capture app are
all already decoupled from where the static site is served.

## Background: what's already there

- **No season concept exists in the schema today.** Championships are keyed
  by FACEIT id only. The dashboard already tolerates divisions "coming and
  going" between seasons gracefully (a stored view preference is validated
  against current views and falls back rather than breaking — `FEATURES.md`
  lines 100-106), but nothing currently *scopes* the live export to one
  season — it ships every championship the DB holds.
- **Region and tier are already parsed from the championship name**
  (`_region_of` / `_tier_of` in `faceit_sync/export.py`), matched as whole
  words. Checking the live DB confirms FACEIT's own `championships.name`
  already carries the season too, e.g. `"S9 EMEA Advanced Central - Regular
  Season"`. Season is parseable with the exact same technique — no new
  tagging system needed, and no reason to touch the DB schema.
- **Code wipes are an existing, recurring mechanism** (`owdb/db.py`
  `_SEED_WIPES` / `LATEST_KNOWN_WIPE`, mirrored in `tools/build_capture_data.py`
  `CODE_WIPE_DATE`). A season boundary is, in practice, one more wipe entry —
  not new machinery. Once S10's wipe date is registered, the capture tool
  automatically stops offering S9 codes; no separate season filter needed
  there.
- **Contributions are NOT written by CI.** The browser capture app uploads
  go straight from the Cloudflare Worker to a committed file
  (`infra/upload-worker/worker.js:198`,
  `` const path = `data/captures/${claimKey}.json` ``) via the GitHub
  contents API. Any season-scoping of captures has to change the Worker,
  not just `owdb/contribute.py` (whose merge logic already just globs
  `*.json` in whatever `--dir` it's given — `contribution_files`,
  `owdb/contribute.py:970`).
- **Private scrims are out of scope.** `docs/scrims.html` reads only
  browser-local IndexedDB (`owscout-capture`), never committed, never
  merged into `data/captures/`. Nothing here touches it.

## Scope decisions

| Decision | Choice | Why |
|---|---|---|
| Hosting | Stay on GitHub Pages | No concrete driver for moving; a season transition doesn't touch hosting at all. |
| S9 data retention | Keep forever in the working `faceit.sqlite3`; never deleted | Rosters/comps go stale across a season, but the *raw match/stat data* stays cheap and valuable (all-time stats, cross-season elo) — SQLite handles it fine at this scale. Only the **export** is season-scoped, not the data. |
| S9 live-site visibility | Stays the sole live season (`docs/index.html`) until every S9 game finishes — no commingling with S10 divisions that start trickling into the DB during the overlap period | Explicit user requirement: rosters/teams change constantly between seasons, so a commingled or look-back selector is "kinda pointless" day-to-day. Cutover to S10-only is a deliberate, explicit action, not an auto-detected one, because playoffs of one season and the start of the next can overlap in the DB. |
| Archive shape | One frozen static export per past season, at its own path (`docs/s9/index.html`, ...), linked from a small static `docs/archive.html` index; never regenerated after creation | Cheapest correct option — a true point-in-time snapshot, no new season-switcher UI/JS logic in the live dashboard app. |
| Captures | Season-scoped directories: `data/captures/s9/`, `data/captures/s10/`, ... | A team's S9 comp must never silently feed S10 scouting — rosters and metas both change. Existing flat files get `git mv`'d into `data/captures/s9/` at cutover for a uniform scheme (no flat-file special case going forward). |
| Cutover mechanism | Manual, documented runbook (in `CLAUDE.md`), not an automated script | Quarterly cadence, and this is the *first* cutover ever run — automating an unrehearsed process guesses at the wrong abstraction. Revisit as a script only if manual execution proves error-prone after being run for real. |

## Changes

### 1. Season filtering (`faceit_sync/export.py`)

- Add `_season_of(name: str | None) -> str | None`, parsing the leading
  `S\d+` token from a championship name with the same word-boundary
  discipline as `_region_of`/`_tier_of` (must not let `S9` false-match
  inside `S90`, etc.).
- Add a `--season` flag to `faceit-sync export`, parity with the existing
  `--region`, narrowing the championship set before views are built.
- CI's live export in `.github/workflows/update.yml` passes an explicit
  `--season s10` once the cutover happens (not auto-latest-detected — see
  scope decision above).

### 2. Frozen archive

One-time, by hand, once S9 is fully finished:

1. `owdb contribute merge --dir data/captures/s9 --out owdb_comps_s9.json`
2. `faceit-sync export --season s9 --format html --out docs/s9/index.html`
3. Commit both. `docs/s9/**` is outside `update.yml`'s regeneration path, so
   it stays byte-frozen even as the live DB keeps accumulating S10+ data.
4. Add a `Season 9 →` line to a small static `docs/archive.html`. Add a
   permanent "Past seasons" link from `docs/index.html`'s shell to it (exact
   placement — footer vs. near the region selector — is an implementation
   detail, not a design decision).

### 3. Captures season-scoping

- `infra/upload-worker/worker.js`: add a `CURRENT_SEASON` constant near the
  top (same shape as the project's existing per-patch constants), change the
  write path to `` `data/captures/${CURRENT_SEASON}/${claimKey}.json` ``.
  Requires a `wrangler deploy` at cutover (run by the human, per existing
  convention — this repo never runs `wrangler deploy` from CI).
- `.github/workflows/update.yml`: the `owdb contribute merge --dir
  data/captures` step becomes `--dir data/captures/s10`.
- `owdb/contribute.py`: no code change — `contribution_files` already globs
  `*.json` in whatever directory it's handed.

### 4. The cutover runbook (documented in `CLAUDE.md`, executed once S9's
   last match finishes)

1. Register the S10 code-wipe date (existing procedure: `owdb/db.py`
   `_SEED_WIPES` + `tools/build_capture_data.py` `CODE_WIPE_DATE`, plus the
   pinned wipe-date test assertions).
2. `git mv data/captures/*.json data/captures/s9/`.
3. Add S10 championship IDs to `matches.txt`; comment out the S9 blocks
   (existing convention — see the `HELD` comment style already in the file).
4. Build the frozen archive (Section 2 above).
5. Update `update.yml`: live export gets `--season s10`; merge step's `--dir`
   becomes `data/captures/s10`.
6. Update `worker.js`'s `CURRENT_SEASON` constant; `wrangler deploy`.

## Testing

- Unit test `_season_of()` against real championship names (parity with the
  existing `_region_of`/`_tier_of` tests), including the word-boundary edge
  case (`S9` must not match `S90`/`S19`, etc.).
- `tests/test_export.py::test_dashboard_javascript_is_syntactically_valid`
  is unaffected in scope (this change lives in `export.py`/CLI, not a
  `faceit_sync/dashboard/` part file) but stays part of the standard gate
  for any future change that does touch a part file.
- The runbook itself isn't unit-testable, but step 4 (the archive export) is
  cheap to rehearse against a local `faceit.sqlite3` copy before ever
  touching the real CI-cached DB or the live Worker.

## Explicitly out of scope

- Any change to hosting (staying on GitHub Pages).
- Deleting or migrating rows out of `faceit.sqlite3`.
- A season switcher/dropdown inside the live dashboard app (`app.js`).
- Any change to `docs/scrims.html` or the browser-local scrim IndexedDB.
- Automating the cutover into a script (deferred until after it's been run
  by hand at least once).

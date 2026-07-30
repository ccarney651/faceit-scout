# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

**OW Scout** — Overwatch 2 composition scouting for the FACEIT League. Two Python
packages feed **one website** (`docs/index.html`):

- **`faceit_sync`** — incremental, idempotent ingest of FACEIT League match data
  into a local **SQLite** DB, exported as a self-contained HTML dashboard.
- **`owscout`** — reads hero comps off the observer HUD of in-client replays
  (screen capture + template matching) and turns them into per-team composition
  scouting shown on the same page. Windows-only capture stack.

`README.md` (faceit_sync ingest + data-quality hazards) and `FEATURES.md`
(every feature in both packages) are the authoritative long-form docs — read them
before deep work on ingest or capture.

## Commands

Dev environment is **Windows**; use the venv Python directly:

```bash
.venv/Scripts/python.exe -m pytest                 # full suite (tests/ + owscout/tests/)
.venv/Scripts/python.exe -m pytest tests/test_export.py::test_name   # one test
.venv/Scripts/python.exe -m pytest -k scheduled    # by keyword
.venv/Scripts/python.exe -m mypy faceit_sync       # strict; must stay clean
pip install -e ".[dev]"                            # install (add [capture] for owscout CV deps)
```

`faceit-sync` / `owscout` / `owscout-app` are the console entry points
(see `[project.scripts]`). Common flows:

```bash
faceit-sync fetch --matches-file matches.txt        # seed + keyless transitive ingest
faceit-sync fetch --championship <id>               # enumerate (needs FACEIT_API_KEY)
faceit-sync export --format html --out docs/index.html   # build the site (all regions)
faceit-sync export --format html --out docs/index.html --region na      # narrow to one region
owscout ... contribute merge --dir data/captures --out owscout_comps.json  # merge captures
```

### Verifying the dashboard

The dashboard's **entire body is rendered in JavaScript** from an inlined data
blob, so **one JS syntax error yields a completely blank page** that
bracket-balance checks won't catch. Always:
- Run `pytest tests/test_export.py::test_dashboard_javascript_is_syntactically_valid`
  (it runs `node --check` over the generated script) after editing `_dashboard.py`.
- For visual checks, build a local `.html` and screenshot with headless Edge
  (`msedge --headless --screenshot=FILE "file:///…#tab"`). On Windows use
  `--screenshot=FILE`, **not** `--dump-dom` (the GUI exe produces no stdout).

## Architecture (the parts that span multiple files)

```
FACEIT API ──fetch──► faceit.sqlite3 ──export──► docs/index.html   (the live site)
                            │                          ▲
                       (read-only ATTACH)              │ (captures merged at build)
                            ▼                          │
OW replay ──capture──► owscout.sqlite3 ──publish──► data/captures/<you>.json
```

**Data-flow facts that carry the operational risk:**

1. **`docs/index.html` is the live site and CI (`.github/workflows/update.yml`)
   is its only writer.** A local `dashboard.html` is an untracked preview built
   from *your* DB. Never hand-edit `docs/index.html` — regenerate via `export`.
2. **Two independent copies of `faceit.sqlite3`** — yours and the one CI keeps in
   its Actions cache. Both rebuild from the same API; nothing reconciles them.
3. **`data/captures/<contributor>.json` is committed; `owscout_comps.json` is
   generated at build and NOT committed** — the report is always recomputed from
   raw observations so analysis improvements apply retroactively. The CI merge
   does first-wins on contested maps by commit date.
4. **`owscout` never writes the faceit DB** — it `ATTACH`es it read-only
   (`mode=ro` URI, see `owscout/db.py::attach_faceit`) for cross-DB context.

**`faceit_sync` ingest** (`sync.py` orchestrates; `client.py` HTTP; `db.py` schema
+ idempotent writes; `models.py` typed records):
- **Keyless transitive discovery** from `matches.txt` seeds → championships →
  every match. An API key only unlocks championship enumeration.
- **Idempotent**: reference rows upsert; per-match child rows are deleted +
  re-inserted atomically, so re-ingest leaves counts unchanged.
- Finished matches are skipped on re-run (veto/results/stats are immutable) —
  **except** the narrow replay-code backfill cases (partial gap within
  `--backfill-days`, or ingested in the last 12h). Missing-on-all-games codes are
  permanent; do not rebuild a blanket backfill (measured, see README).
- **Scheduled/upcoming matches** (status `SCHEDULED`, from the keyless list as
  `created`) are stored as bare fixtures (teams/time/round, no games) and
  upgraded on FINISH. Export keeps standings/counts `FINISHED`-only and exposes a
  separate `upcoming` payload; a scheduled row would otherwise read as a walkover.
- **Data hazards A/B/C** (zeroed rows ≠ forfeit; restarts wipe veto attribution;
  live veto feed is ephemeral but `/history` is durable) are the point of the
  project — handled explicitly and each has a dedicated test. See README.
- Opaque FACEIT stat codes (`i8`, `i14`…) are mapped empirically in one place:
  `models.STAT_FIELD_MAP`. Correct them there if FACEIT changes them.

**The dashboard** (`faceit_sync/_dashboard.py`) is one large `HTML_TEMPLATE`
Python string; vanilla JS builds the DOM (`el()`/`esc()`, hash routing per tab).
The app boots via `bootApp(DATA)` — DATA is inlined as `var __OWSCOUT_DATA__=…`
by default, or fetched from a sibling `data.json` with `export --external-data`
(the seam for future access-gating). Hero portraits come from the committed
`faceit_sync/hero_icons.json` cache (a build without it silently renders text
chips; regenerate with `python -m faceit_sync.hero_icons <asset-dir>`).

**`owscout`** keeps IO/CV/GUI thin and the logic in typed, tested modules
(`gui.py` and the capture/CV stack are excluded from mypy for that reason;
everything they wrap is tested elsewhere). Its CLI (`owscout/cli.py`) has many
subcommands (`calibrate`, `refs`, `capture`, `scout`, `contribute`, `codes`,
`review`, `drafts`, `doctor`, …). SPEC.md is its design reference.

## Gotchas

- **Replay codes are invalidated by every OW patch ("code wipe").** The wipe date
  is duplicated in **two** places that must stay in sync: `owscout/db.py`
  `_SEED_WIPES` (drives `LATEST_KNOWN_WIPE` → `owscout_comps.json` → the site) and
  `tools/build_capture_data.py` `CODE_WIPE_DATE` (drives the capture tool). Update
  both when a patch lands, plus the pinned wipe-date assertions in
  `owscout/tests/test_codes.py` / `test_context.py`.
- **`setup.txt`** is intentionally-uncommitted working notes — leave it out of
  commits (stash it around `git pull --rebase` / `git push`).
- **Cloudflare Worker** (`infra/upload-worker/`, `wrangler.toml`) handles capture
  uploads + real-time scouting claims (a Durable Object). `wrangler deploy` is run
  by the human, not from here.
- FACEIT's edge blocks browser-like User-Agents (`Mozilla/5.0` → 403); the client
  sends a descriptive `faceit-sync/…` UA — don't change it to impersonate a browser.
- The stats endpoint is `…/stats/v1/stats/matches/{id}` (the documented `/time`
  segment 404s).

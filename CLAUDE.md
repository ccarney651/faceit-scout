# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

**OW Scout** — Overwatch 2 composition scouting for the FACEIT League. Two Python
packages feed **one website** (`docs/index.html`):

- **`faceit_sync`** — incremental, idempotent ingest of FACEIT League match data
  into a local **SQLite** DB, exported as a self-contained HTML dashboard.
- **`owscout`** — reads hero comps off the observer HUD of in-client replays
  (screen capture + template matching) and turns them into per-team composition
  scouting shown on the same page. Capture happens through the browser app at
  `docs/capture/` (zero-install, `getDisplayMedia` + tesseract.js) — **the only
  supported capture path.** A native Windows GUI once existed here
  (`owscout/gui.py`, `owscout_app.py`) but was removed in 2026-08-08 as dead
  code; its tested first-run helpers survive in `owscout/firstrun.py`.

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

`faceit-sync` / `owscout` are the console entry points (see `[project.scripts]`).
Common flows:

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
  (it runs `node --check` over the generated script) after editing any dashboard
  part file under `faceit_sync/dashboard/`.
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
                            ▲
               (browser IndexedDB "owscout-capture")
               docs/capture/ ──scrim──► private scrims (this browser only)
                                            │
                                            ▼ (same origin: /docs/)
                               docs/scrims.html  (Scrims page, via the top-bar toggle)
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
5. **Private scrims live only in the browser.** The capture app's scrim mode
   (`docs/capture/scrim.html`, IndexedDB `owscout-capture` v4, stores `scrims` +
   `scrim_maps`) is a local-first side-channel: never published to the worker,
   never merged into `data/captures/`, and — because `docs/capture/` and `docs/`
   share an origin — readable by the **Scrims page** (`docs/scrims.html`, the
   one scrims viewer, reached via the top-bar League/Scrims toggle), which opens
   the same DB read-only (it must NOT bump the capture app's schema version).
   The league dashboard itself never touches that IndexedDB. The replay code
   field in scrim mode is optional but **hard-blocks known FACEIT league codes**
   (it checks the capture app's `data.json` feed) and offers to switch over to
   League capture, so league maps stay public. Scrim records carry hero *guids*;
   `docs/scrims.html` resolves them via `capture/refs.json` + a small hero-role
   table of its own (hero names/roles are not part of the league data payload).

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

**The dashboard** is assembled by `faceit_sync/_dashboard.py` from four static
parts under `faceit_sync/dashboard/` — `head.html` (page shell + CSS + the
`// __DATA_INLINE__` data placeholder), `pure.js` (the tested pure decision
helpers), `app.js` (the `bootApp(DATA)` body), `boot.js` (data delivery) — via
plain concatenation at import, no framework or build step. Vanilla JS builds the
DOM (`el()`/`esc()`, hash routing per tab). The app boots via `bootApp(DATA)` —
DATA is inlined as `var __OWSCOUT_DATA__=…` by default, or fetched from a
sibling `data.json` with `export --external-data` (the seam for future
access-gating). Pure logic that must be unit-testable goes in `pure.js` above
`bootApp` (the `tests/test_dashboard_logic.py` harness executes that region in
node). Hero portraits come from the committed `faceit_sync/hero_icons.json`
cache (a build without it silently renders text chips; regenerate with
`python -m faceit_sync.hero_icons <asset-dir>`).

**`owscout`** keeps IO/CV thin and the logic in typed, tested modules (the
capture/CV stack is excluded from mypy for that reason; everything it wraps is
tested elsewhere). Its CLI (`owscout/cli.py`) has many
subcommands (`calibrate`, `refs`, `capture`, `scout`, `contribute`, `codes`,
`review`, `drafts`, `doctor`, …). SPEC.md is its design reference.

## Gotchas

- **Replay codes are invalidated by every OW patch ("code wipe").** The wipe date
  is duplicated in **two** places that must stay in sync: `owscout/db.py`
  `_SEED_WIPES` (drives `LATEST_KNOWN_WIPE` → `owscout_comps.json` → the site) and
  `tools/build_capture_data.py` `CODE_WIPE_DATE` (drives the capture tool). Update
  both when a patch lands, plus the pinned wipe-date assertions in
  `owscout/tests/test_codes.py` / `test_context.py`.
- **Cloudflare Worker** (`infra/upload-worker/`, `wrangler.toml`) handles capture
  uploads + real-time scouting claims (a Durable Object). `wrangler deploy` is run
  by the human, not from here.
- FACEIT's edge blocks browser-like User-Agents (`Mozilla/5.0` → 403); the client
  sends a descriptive `faceit-sync/…` UA — don't change it to impersonate a browser.
- The stats endpoint is `…/stats/v1/stats/matches/{id}` (the documented `/time`
  segment 404s).

## Roadmap & conventions

### Priorities (ordered)

1. **Unblock capture adoption** — the binding constraint. Coverage is thin everywhere
   except FACEIT Masters, and the tool is ~1 min/map so time isn't the problem. The
   three friction fixes this priority named are **delivered** (guided first-capture
   tour, auto-calibrate confidence preview, contributor impact card — all shipped
   together in the 2026-08-04 onboarding commit); the priority now is to **iterate on
   adoption** — watch where new scouts stall and remove the next friction.
2. **Ship scrim mode** — graduate WIP features (auto-side detection for scrims,
   scoreboard score read, screenshot import) from experimental badges. Bring scrim
   analytics to parity with league scouting (hero pools, swap detection, comp
   families). The two scrims implementations were **consolidated 2026-08-08**:
   `docs/scrims.html` (via the top-bar League/Scrims toggle) is the one viewer —
   the dashboard's phantom "Scrims tab" was a dead `HERO_BY_GUID` stub plus a
   `guid` payload field, both removed.
3. **OWCS expansion** — scrape from FACEIT where possible (OWCS uses FACEIT for
   some events); VOD-based capture from YouTube/Twitch for the rest; manual entry
   as fallback.
4. **Statistical capture recommendations** — **delivered** (the Overview panel
   ranking under-covered maps by unseen minutes shipped ahead of priorities 2 and 3).
   Iterate on adoption: the per-mode length estimates are hardcoded guesses, and
   coverage currently counts regular-season games only (playoff games are a known gap).

### Audience

Organised play first (FACEIT League, scrims, OWCS). Aspiration to serve all
audiences if the analytics are strong enough.

### Codebase conventions

- **Branding: "OWDB".** Rebranding in progress from "OW Scout". Chosen domain is
  **owdb.gg** (gaming-native, currently available) — register it when closer to
  shipping the final product. `owdb.com/.net/.org` are taken/expensive;
  `owdb.dev/.app/.io/.sh/.me` are available fallbacks.
- **Don't overengineer unless necessary for expandability.** The dashboard is
  modularized into concatenated static parts (`faceit_sync/dashboard/`); keep
  new features landing in the right part file rather than growing one string.
- The dead native GUI (`owscout/gui.py`, `owscout_app.py`, PyInstaller spec
  files, `Scout app.cmd`) was removed in 2026-08-08 — don't resurrect it.
- The two scrims implementations were consolidated in 2026-08-08 — the
  standalone `docs/scrims.html` page (reached via the top-bar League/Scrims
  toggle) is the single scrims viewer; the dashboard's "Scrims tab" vestige
  (an unused `HERO_BY_GUID` map and the `guid` field it read) was removed.
  Don't add scrims into the dashboard build — keep the private side separate.
- `docs/index.html` is the live site — never hand-edit, only regenerate via export.
- Always run the dashboard JS syntax test after touching a dashboard part file:
  `pytest tests/test_export.py::test_dashboard_javascript_is_syntactically_valid`

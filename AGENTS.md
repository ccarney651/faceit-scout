# AGENTS.md

Canonical instructions for coding agents working in this repository. Claude
Code, opencode, Codex, and Cursor all work from this file.

## What this is

**OWDB** — Overwatch 2 composition scouting for the FACEIT League. Two Python
packages feed **one website** (`docs/index.html`):

- **`faceit_sync`** — incremental, idempotent ingest of FACEIT League match data
  into a local SQLite database, exported as a self-contained HTML dashboard.
- **`owdb`** — reads hero comps off the observer HUD of in-client replays and
  turns them into per-team composition scouting on the same page. Capture happens
  through the browser app at `docs/capture/` — **the only supported capture
  path.**

## Read this first

**`ARCHITECTURE.md` explains every part of the project and how the parts
connect.** Read it before deep work. Fast paths:

| You need | Go to |
| --- | --- |
| Where anything lives | `ARCHITECTURE.md` §0-2 |
| Ingest and the three data hazards | `ARCHITECTURE.md` §3 |
| How `docs/index.html` is built | `ARCHITECTURE.md` §4 |
| The capture pipeline | `ARCHITECTURE.md` §5-6 |
| Scrims | `ARCHITECTURE.md` §7 |
| CI and the Cloudflare Worker | `ARCHITECTURE.md` §8 |
| File formats crossing a boundary | `ARCHITECTURE.md` §9 |
| Code wipes and season cutover | `ARCHITECTURE.md` §10 |
| Project vocabulary | `ARCHITECTURE.md` §11 |
| **Rules that must not be broken** | **`ARCHITECTURE.md` §12** |
| Which test guards what | `ARCHITECTURE.md` §13 |

Other documentation: `README.md` (ingest and data hazards, long-form),
`FEATURES.md` (feature-by-feature — known to lag the code), `SPEC.md` (the
original `owdb` design reference), `CHANGELOG.md` (what changed and when),
`specs/` (one design and plan document per feature, plus `specs/BACKLOG.md`).

## Commands

Dev environment is **Windows**; use the venv Python directly:

```bash
.venv/Scripts/python.exe -m pytest                 # full suite (tests/ + owdb/tests/)
.venv/Scripts/python.exe -m pytest tests/test_export.py::test_name   # one test
.venv/Scripts/python.exe -m pytest -k scheduled    # by keyword
.venv/Scripts/python.exe -m mypy faceit_sync       # strict; must stay clean
pip install -e ".[dev]"                            # install (add [capture] for owdb CV deps)
```

`faceit-sync` and `owdb` are the console entry points. Common flows:

```bash
faceit-sync fetch --matches-file matches.txt        # seed + keyless transitive ingest
faceit-sync fetch --championship <id>               # enumerate (needs FACEIT_API_KEY)
faceit-sync export --format html --out docs/index.html          # build the site
faceit-sync export --format html --out docs/index.html --region na
owdb ... contribute merge --dir data/captures/s9 --out owdb_comps.json
```

### Verifying the dashboard

The dashboard's **entire body is rendered in JavaScript** from an inlined data
blob, so **one JS syntax error yields a completely blank page** that
bracket-balance checks will not catch. Always:

- Run `pytest tests/test_export.py::test_dashboard_javascript_is_syntactically_valid`
  (it runs `node --check` over the generated script) after editing any part file
  under `faceit_sync/dashboard/`.
- For visual checks, build a local `.html` and screenshot with headless Edge.
  On Windows use `--screenshot=FILE`, **not** `--dump-dom` — the GUI executable
  produces no stdout.

## Invariants

These are the same rules as `ARCHITECTURE.md` §12, stated here so they are never
one file-read away. If the two lists ever disagree, `ARCHITECTURE.md` is
canonical and this copy is the bug.

1. **Never hand-edit `docs/index.html`.** CI regenerates it from
   `faceit_sync/dashboard/head.html` on every run; the edit disappears at the
   next build. Fix the part file.
2. **Never run `faceit-sync export` locally to "just regenerate" the site.** The
   local `faceit.sqlite3` is routinely days behind CI's cached copy, so
   committing a local export overwrites fresh data with stale data.
3. **Always run the dashboard JS syntax test after editing anything under
   `faceit_sync/dashboard/`.**
4. **Bump the code-wipe date only in `_SEED_WIPES` in `owdb/db.py`.** Everything
   downstream derives from it.
5. **Never bump the IndexedDB schema version from `docs/scrims.html`.** It is a
   read-only consumer of the capture app's store.
6. **Never commit `owdb_comps.json`.** A committed report would outlive the
   observations it came from and freeze the analysis that produced it.
7. **Never change the client User-Agent to impersonate a browser.** FACEIT's
   edge returns 403 for `Mozilla/5.0`-style agents.
8. **Never add scrims into the dashboard build.** The private side stays
   separate.
9. **Always `git fetch` before pushing.** CI auto-commits to `origin/main` every
   few minutes; expect a merge, and resolve by keeping CI's data and reapplying
   your diff on top.
10. **Never put developer documentation in `docs/`.** That is the GitHub Pages
    web root — anything there is published to owdb.io.
11. **`wrangler deploy` is run by the human.** A commit to
    `infra/upload-worker/worker.js` is not live until someone deploys it.

## Gotchas

- **Replay codes are invalidated by every Overwatch patch (a "code wipe").** The
  date has **one** source: `_SEED_WIPES` in `owdb/db.py`.
  `tools/build_capture_data.py` imports `LATEST_KNOWN_WIPE` rather than
  restating it. When a patch lands, add the entry and update the pinned
  assertions in `owdb/tests/test_context.py`. Fixture matches that must stay
  alive derive their dates from `LATEST_KNOWN_WIPE` — never hard-code one.
- **The capture pages' Content-Security-Policy lives in a `<meta>` tag**, so
  `curl -I` shows nothing. It has silently broken browser APIs before — check it
  first when something fails quietly in `docs/capture/`.
- **pytest cannot see through a real browser.** It checks syntax and shape, not
  behaviour against a live DOM, IndexedDB or CSP — a gap that has hidden live
  bugs more than once. `tools/verify_capture_browser.js` closes most of it
  (serve `docs/`, `npm install playwright-core`, then run it). Everything left
  after that needs a human with Overwatch open: screen share, calibration,
  portrait recognition, and the overlay over the game.
- **Both capture pages must open IndexedDB with the same store list**
  (`ALL_STORES` in `docs/capture/engine/idb.js`). Declaring only the stores a
  page uses looks right and breaks the other page — see `ARCHITECTURE.md` §7.
- **The capture pages share an engine under `docs/capture/engine/`.** A fix to
  calibration, hero recognition, the overlay or name matching belongs in the
  module, not in a page. The snapshot/review/finish cluster is still forked
  between the two pages until phase 3 — check both when touching it.
- **Player assignment abstains; do not "improve" it into guessing.** The floor in
  `docs/capture/engine/assign.js` is the only thing keeping the wrong-attribution
  rate at zero — removing it took the same resolver to 33.6% wrong once the OCR
  reads degraded. If you change either threshold, re-run `tools/assign_eval.py`
  and move the numbers in `ARCHITECTURE.md` with it.
- **`data.json`'s `lineups` is per game and `rosters` is per match on purpose.**
  27% of match-teams field more than five players once substitutes are counted,
  which destroys the exact five-over-five cover assignment relies on. Do not
  collapse the two.
- **`AUTO_STRIPS` is correct live; the frames in `screenshots/` do not match it.**
  Verified 2026-08-18: auto-calibrate reports 10/10 portraits confident against a
  live share. On those old replay-HUD screenshots it reaches only 4.83-5.48 where
  the measured strip scores 6.06-6.82, and the gap is strip *size* (~6% wider,
  ~14% taller) so no dx/dy sweep closes it. That is a property of the fixtures,
  not a bug: derive boxes from the pixels when evaluating against them (as
  `tools/real_frame_eval/gen_all.py` does) and do NOT change `AUTO_STRIPS`.
- **The HUD name crop must come from `nameRow()`, not from a fraction of the
  calibration box.** The box is fitted to the portraits; every fixed band under
  it that anyone has tried also contains the health bar or the portrait bottom,
  and tesseract reads the bar. Find the row once per SIDE across the five-slot
  strip — per slot it picks the hero portrait. Two per-slot attempts were built
  and reverted; `tools/real_frame_eval/README.md` records both so they are not
  tried a third time. Any change to the locator or its constants must be re-run
  through that harness (`rowfind_sweep.py`, then `rowfind_parity.py`, which
  proves the shipped JS still matches the Python the sweep uses) **before** it
  goes anywhere near a live capture.
- **Captures are season-scoped** (`data/captures/s9/`). Two writers key off a
  per-season constant each: `CURRENT_SEASON` in `infra/upload-worker/worker.js`
  and `CONTRIB_DIR` in `owdb/contribute.py`. At the cutover, follow
  `specs/2026-08-10-season10-cutover-design.md` rather than improvising.
- **`mypy` covers `faceit_sync` only.** `owdb` is not in the must-stay-clean
  contract and currently reports two errors in `owdb/contribute.py`. Its tests
  are its safety net.
- The stats endpoint is `…/stats/v1/stats/matches/{id}` — the documented `/time`
  segment 404s.

## Roadmap

### Priorities (ordered)

1. **Unblock capture adoption** — the binding constraint. Coverage is thin
   everywhere except FACEIT Masters, and the tool takes about a minute per map,
   so time is not the problem. The named friction fixes are **delivered**: the
   guided first-capture tour, auto-calibrate confidence preview, and contributor
   impact card (2026-08-04); the capture-funnel callout (2026-08-09);
   league-wide click-to-codes (2026-08-09); and **player attribution**
   (2026-08-18) — captures now say which FACEIT player is in which HUD slot,
   which had never worked. The priority remains to **iterate on adoption** —
   watch where new scouts stall and remove the next friction. Remaining P2
   items: NA Advanced seeding (one line in `matches.txt`), and
   `--external-data` page splitting only if page weight grows.

   Shipped WITHOUT scrim mode, deliberately: the release branched at the last
   commit of the shared-engine extraction (scrim mode phase 0), so the engine
   and the attribution work went live while everything scrim-facing stayed on
   `scrim-mode`. That seam is reusable — phase 0 is a pure refactor plus fixes,
   and nothing above it is.

2. **Scrim mode, phases 2–6.** Mind the split between what is BUILT and what is
   IN PRODUCTION, because they differ:

   - **Phase 0** (shared capture engine extraction) is built *and shipped* —
     merged to `main` on 2026-08-18 with the player-attribution work.
   - **Phase 1** (un-pause, session scaffold, league-code block, wipe-date
     check, manual add) is built on `scrim-mode` and **not shipped**. In
     production `docs/capture/scrim.html` still renders the unconditional
     `#scrimpaused` overlay that no script removes (commit `f2881cf`), so
     scrims remain switched off for everyone but this branch.
   - Also built here, unshipped: phase 2a (opponent identification, confirmed
     working in the field 2026-08-19) and phase 4's analysis half (the scrims
     viewer at parity with league Scout).
   - Also built here, unshipped: the **panel-first capture workflow** — the
     page no longer starts maps, takes bans or imports sessions; everything
     done during a scrim happens in the pop-out panel. And the **replay-code
     reader** (`engine/replaycode.js`), which is the one piece that touches
     `docs/capture/index.html` too, so it will ship with whatever merges next.

   What remains, per `specs/2026-08-12-scrim-mode-design.md`: the rest of
   opponent identification and roster search (2); the stats read plus a
   workshop hero-glyph reference set (3); the viewer's Players tab (4); sync
   and sharing (5); auto map detection (6). See `ARCHITECTURE.md` §7.

   **Auto map detection (6) is now cheaper than it was**: the code reader can
   already tell when the replay on screen is not the one being captured. It was
   deliberately left on-demand rather than polling — see
   `specs/2026-08-19-replay-code-ocr-design.md` §4.6 for what polling would
   cost and why it was declined.

3. **OWCS expansion** — scrape from FACEIT where possible; VOD-based capture
   from YouTube and Twitch for the rest; manual entry as fallback.
4. **Statistical capture recommendations** — **delivered**. Iterate: the
   per-mode length estimates are hardcoded guesses, and coverage counts
   regular-season games only (playoff games are a known gap).

### Audience

Organised play first (FACEIT League, scrims, OWCS). Aspiration to serve all
audiences if the analytics are strong enough.

## Conventions

- **Branding is "OWDB"**, on **owdb.io** (registered 2026-08-09), with the upload
  Worker on `upload.owdb.io`. The rename from "OW Scout" / `owscout` is complete
  in code, CLI, and copy; the browser IndexedDB name `owscout-capture` is
  deliberately kept until the Season 10 cutover, since renaming it would orphan
  every contributor's local data.
- **Do not overengineer unless expandability requires it.** The dashboard is
  modularised into concatenated static parts under `faceit_sync/dashboard/` —
  land new features in the right part file rather than growing one string.
- **Shared design tokens and primitives live in `docs/theme.css`** — colours,
  fonts, `.card`, `.btn`, the `.prodname` wordmark, `.sidetoggle`/`.sidebox`,
  `nav`, `.eyebrow`. `docs/scrims.html` and `docs/capture/*.html` link it
  directly; `docs/index.html` cannot (it must stay self-contained), so
  `faceit_sync/_dashboard.py` inlines the canonical copy at
  `faceit_sync/dashboard/theme.css` with fonts base64-embedded. Edit the shared
  set there and never re-add a per-page copy — that duplication is what caused
  the pre-redesign inconsistency. Everything page-specific stays per-page and
  re-themes automatically from these tokens.
- **The dead native GUI was removed on 2026-08-08** (`owdb/gui.py`,
  `owdb_app.py`, the PyInstaller specs, `Scout app.cmd`). Do not resurrect it.
- **`docs/scrims.html` is the single scrims viewer.** The two implementations
  were consolidated on 2026-08-08.
- **Feature work gets a design document then a plan**, both under `specs/`, named
  `YYYY-MM-DD-<topic>-design.md` and `-plan.md`.
- **Update `CHANGELOG.md`** when a change is visible on owdb.io, changes a data
  contract, or changes an operational procedure.

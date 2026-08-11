# OWDB — Architecture

This document explains what every part of OWDB is, how it works, and how the
parts feed each other. It is the map of the project: read it before deep work
anywhere in the repository, and read the section for a subsystem before changing
that subsystem.

It is written to be read start-to-finish once, and grepped thereafter. Every
file is named by its literal repo-relative path, every section opens with a
one-line summary, and every paragraph stands on its own — so landing in the
middle of this document, whether by scrolling or by search, still lands you in
context.

`README.md`, `FEATURES.md`, and `SPEC.md` remain the long-form references for
ingest, features, and the capture design respectively. This document sits above
them and says how everything connects.

## Contents

- [0. Orientation](#0-orientation)
- [1. The map](#1-the-map)
- [2. Repository tour](#2-repository-tour)
- [3. Ingest — `faceit_sync`](#3-ingest--faceit_sync)
- [4. Dashboard build](#4-dashboard-build)
- [5. Capture — the Python `owdb` package](#5-capture--the-python-owdb-package)
- [6. Browser capture app](#6-browser-capture-app)
- [7. Scrims](#7-scrims)
- [8. Infrastructure and CI](#8-infrastructure-and-ci)
- [9. Data contracts](#9-data-contracts)
- [10. Lifecycles and operations](#10-lifecycles-and-operations)
- [11. Glossary](#11-glossary)
- [12. Invariants](#12-invariants)
- [13. Testing map](#13-testing-map)

---

## 0. Orientation

What OWDB is, and where to look for the thing you want to change.

OWDB is composition scouting for Overwatch 2 in the FACEIT League. Two Python
packages feed one website. `faceit_sync` pulls match data — teams, results, map
vetoes, player stats, replay codes — from FACEIT's public API into a local
SQLite database, then exports that database as a self-contained HTML dashboard.
`owdb` solves the problem FACEIT's API does not: the API never says which heroes
were played. So OWDB reads hero compositions off the observer HUD of in-client
replays, turns them into stored observations, and merges everyone's
contributions into per-team scouting shown on the same page. Capture happens in
the browser at `docs/capture/`, which needs no installation.

The two halves meet in exactly one place — the export step — and are otherwise
independent.

**Where to look:**

| I want to change… | Look at… | Section |
| --- | --- | --- |
| How matches are fetched or stored | `faceit_sync/sync.py`, `faceit_sync/client.py`, `faceit_sync/db.py` | [3](#3-ingest--faceit_sync) |
| What the dashboard looks like | `faceit_sync/dashboard/head.html` (CSS), `docs/theme.css` (shared tokens) | [4](#4-dashboard-build) |
| What the dashboard shows or computes | `faceit_sync/dashboard/app.js` (rendering), `faceit_sync/dashboard/pure.js` (testable logic) | [4](#4-dashboard-build) |
| What data reaches the dashboard | `faceit_sync/export.py` | [4](#4-dashboard-build), [9](#9-data-contracts) |
| The capture tool people actually use | `docs/capture/index.html` | [6](#6-browser-capture-app) |
| The Python capture pipeline | `owdb/capture.py`, `owdb/match.py`, `owdb/comps.py` | [5](#5-capture--the-python-owdb-package) |
| Scrim recording or the scrims page | `docs/capture/scrim.html`, `docs/scrims.html` | [7](#7-scrims) |
| Uploads, login, or scouting claims | `infra/upload-worker/worker.js` | [8](#8-infrastructure-and-ci) |
| When and how the site rebuilds | `.github/workflows/update.yml` | [8](#8-infrastructure-and-ci) |
| Hero portraits on the dashboard | `faceit_sync/hero_icons.py`, `faceit_sync/hero_icons.json` | [4](#4-dashboard-build) |
| Hero templates used for HUD matching | `owdb/refs.py`, `tools/build_capture_refs.py` | [5](#5-capture--the-python-owdb-package) |
| Which matches are known about at all | `matches.txt` | [3](#3-ingest--faceit_sync) |

## 1. The map

Every artifact in the system, who writes it, and who reads it.

```
                     FACEIT public API
                            │
                    faceit-sync fetch
                            │
                            ▼
                    faceit.sqlite3  ────────────┐
                    (match data)                │ read-only ATTACH
                            │                   ▼
                            │            owdb.sqlite3
                            │            (HUD observations,
                            │             hero reference images)
                            │                   │
                            │                   │ owdb contribute publish
                            │                   ▼
                            │        data/captures/s9/<contributor>.json
                            │            (committed, one file each)
                            │                   │
                            │        owdb contribute merge  (at build time)
                            │                   ▼
                            │            owdb_comps.json
                            │            (derived, never committed)
                            │                   │
                            └───────┬───────────┘
                                    │ faceit-sync export
                                    ▼
                            docs/index.html   ← the live site, owdb.io


  BROWSER SIDE

    docs/capture/index.html ──uploads──► upload.owdb.io Worker
       (league capture)                        │
            │                                  └──► commits data/captures/s9/
            │ reads
            ▼
    docs/capture/data.json      ← built by tools/build_capture_data.py
    docs/capture/refs.json      ← built by tools/build_capture_refs.py

    docs/capture/scrim.html ──► IndexedDB "owscout-capture"  (never leaves the browser)
                                          │ same origin, read-only
                                          ▼
                                  docs/scrims.html
```

| Artifact | Written by | Read by | Committed? |
| --- | --- | --- | --- |
| `faceit.sqlite3` | `faceit-sync fetch` | `faceit-sync export`, `owdb` (read-only) | No — two independent copies exist |
| `owdb.sqlite3` | `owdb capture`, `owdb refs` | `owdb scout`, `owdb contribute` | No — local to each contributor |
| `data/captures/s9/` | the upload Worker, or `owdb contribute publish` | `owdb contribute merge` | **Yes** — this is the durable record |
| `owdb_comps.json` | `owdb contribute merge` at build time | `faceit-sync export` | **No** — deliberately regenerated |
| `docs/index.html` | `.github/workflows/update.yml` **only** | the public | Yes |
| `docs/captured.json` | `owdb contribute merge` | `docs/index.html` | Yes |
| `docs/capture/data.json` | `tools/build_capture_data.py` | `docs/capture/index.html` | Yes |
| `docs/capture/refs.json` | `tools/build_capture_refs.py` | `docs/capture/index.html`, `docs/scrims.html` | Yes — curator-committed |
| `docs/faceit.sqlite3.gz` | `.github/workflows/update.yml` | a fresh `owdb` install, to skip re-crawling | Yes |
| IndexedDB `owscout-capture` | `docs/capture/scrim.html` | `docs/scrims.html` | **Never leaves the browser** |

**Two independent copies of `faceit.sqlite3` exist.** One is on the contributor's
machine; the other lives in the GitHub Actions cache and is the one the live site
is built from. Both rebuild from the same FACEIT API and **nothing reconciles
them**. A local copy can be days stale while CI's is current, which is why
running `export` locally and committing the result silently destroys fresh data.
See [invariant 2](#12-invariants).

## 2. Repository tour

Every top-level directory and root file, and whether it is live, reference, generated, or local-only.

`live` means something depends on it at build or run time. `reference` means it
is documentation or seed data for humans. `generated` means a tool produces it
and it can be deleted safely. `local-only` means it exists on a working machine
and is not in git.

| Path | What it is | Status |
| --- | --- | --- |
| `faceit_sync/` | The ingest package and the dashboard builder. See [3](#3-ingest--faceit_sync) and [4](#4-dashboard-build). | live |
| `faceit_sync/dashboard/` | The four static parts concatenated into the dashboard, plus its fonts. | live |
| `owdb/` | The Python capture and analysis package, including its own test suite in `owdb/tests/`. | live |
| `docs/` | **The GitHub Pages web root.** Everything here is published to owdb.io. | live |
| `docs/capture/` | The browser capture app — the only supported capture path. | live |
| `data/captures/` | Committed contributor observations, one JSON file per person per season. | live |
| `tools/` | Build scripts that produce feeds for the capture app, plus the social-preview image generator. | live |
| `tools/scrim_code/` | OverPy source for the in-game Overwatch Workshop scrim helper. | live |
| `infra/upload-worker/` | The Cloudflare Worker source. Deployed by hand, not by CI. | live |
| `tests/` | Pytest suite for `faceit_sync`, the dashboard, and the browser capture app. | live |
| `.github/workflows/update.yml` | The only writer of the live site. | live |
| `matches.txt` | Seed list of match IDs and championship URLs that ingest starts from. | live |
| `pyproject.toml` | Packaging, dependencies, the `faceit-sync` and `owdb` entry points, mypy and pytest config. | live |
| `README.md` | Long-form reference: ingest, the schema, and the data-quality hazards. | reference |
| `FEATURES.md` | Long-form reference: every feature in both packages. Known to lag the code. | reference |
| `SPEC.md` | The original `owdb` design reference — design intent, not current state. | reference |
| `ARCHITECTURE.md` | This document. | reference |
| `specs/` | Design and implementation-plan documents, one pair per feature, plus `specs/BACKLOG.md`. | reference |
| `verify_accuracy.py` | Standalone audit script that re-derives dashboard numbers independently. | reference |
| `Dockerfile`, `docker-compose.yml` | Containerised ingest, for running the sync somewhere other than a desktop. | reference |
| `*.cmd` (7 files at root) | Double-clickable Windows launchers wrapping the two CLIs, for non-technical contributors. | reference |
| `.env.example` | The environment variables ingest and the Worker read. | reference |
| `faceit.sqlite3` | The local ingest database. | local-only |
| `owdb.sqlite3` | The local capture database, including the hero reference images. | local-only |
| `owdb_comps.json` | The merged scouting report, rebuilt at every site build. | generated |
| `dashboard.html` | A local dashboard preview built from *your* database. Not the live site. | generated |
| `refs/`, `calibration/`, `crops/`, `screenshots/` | Capture runtime output: exported templates, calibration state, and debug images. | generated |
| `overwatch-hero-icons/` | Downloaded hero art, used to regenerate `faceit_sync/hero_icons.json`. | local-only |
| `.venv/` | The Python virtual environment. All commands in this document invoke it directly. | local-only |
| `.claude/`, `.opencode/`, `.remember/`, `.superpowers/` | Coding-agent workspaces. | local-only |
| `.mypy_cache/`, `.pytest_cache/`, `.ruff_cache/`, `faceit_sync.egg-info/` | Tool caches and packaging metadata. | generated |

## 3. Ingest — `faceit_sync`

How FACEIT League match data gets into a local SQLite database, and the data-quality hazards that shape the design.

### What it does

`faceit-sync fetch` pulls every FACEIT League match it can reach — teams,
schedules, results, map vetoes, hero bans, per-player stats, and replay codes —
and stores them in a local SQLite file. It is incremental and idempotent: run it
as often as you like, and the second run changes nothing the first already got
right.

### How it works

**Three payloads per match.** `faceit_sync/client.py` fetches each match from
three separate endpoints and `faceit_sync/sync.py::extract_bundle` reconciles
them into one typed `MatchBundle`:

| Payload | Endpoint | Carries |
| --- | --- | --- |
| Match detail | `api.faceit.com/match/v2/match/{id}` | teams, rosters, results, the map and hero voting record, replay codes |
| Democracy | `api.faceit.com/democracy/v1/match/{id}` | **who** banned what and who picked which map |
| Stats | `api.faceit.com/stats/v1/stats/matches/{id}` | per-player per-game numbers |

Only championship enumeration needs a `FACEIT_API_KEY`; those three are keyless.

**Keyless transitive discovery** is the trick that makes an API key optional.
`SyncEngine.run` in `faceit_sync/sync.py` starts from the teams already known
for a championship — one seed match is enough — enumerates each team's matches,
and every match ingested reveals new opponents, which are then enumerated in
turn until the team graph is exhausted. In a connected schedule this reaches
every team and every match from any single seed. `matches.txt` holds those
seeds. `SyncEngine.run_all` crawls regular-season divisions **before** their
playoff siblings, because a bracket is seeded from the sibling division's
qualifiers and those teams must be discovered first.

**Idempotency** is deliberate and split by row type, documented at the top of
`faceit_sync/db.py`. Reference rows (championships, teams, players, heroes,
maps, matches) are written with `INSERT … ON CONFLICT DO UPDATE`. Per-match
child rows (games, map picks, hero bans, round players) are deleted and
re-inserted together inside one transaction by `Database.replace_children`. The
result is that re-running a sync never duplicates rows and leaves counts
unchanged.

**Finished matches are skipped on re-run**, because their veto, results, and
stats are immutable. `SyncEngine._skip_stored` makes that call, with two
exceptions computed once per run by `Database.matches_needing_backfill`:

1. a **partial gap** — some games in a match have replay codes and some do not,
   the only signature consistent with an incomplete publish; and
2. a **just-ingested match** — stored within the last 12 hours
   (`DEFAULT_BACKFILL_FRESH_HOURS`), where codes may genuinely not be up yet.

Everything else is left alone, and this is measured rather than assumed: across
676 real matches, 87 had no code on any game, only 4 had a partial gap, and
re-fetching all of them recovered **zero** codes. Replays were simply never
published for those matches. **A match missing codes on every game is missing
them permanently — it is not late.** Do not rebuild a blanket backfill.

**Upcoming matches are stored as bare fixtures.** A match in any of the
pre-finish states listed in `SCHEDULED_STATES` gets a row with teams, scheduled
time, and round, but no games. It is never skipped, and is upgraded to a full
ingest once it reaches `FINISHED`. Export keeps standings and counts
`FINISHED`-only and ships upcoming matches as a separate payload — a scheduled
row counted as a result would read as a walkover.

**Politeness.** `faceit_sync/client.py` holds one `requests.Session`, a global
rate limit defaulting to 4 requests per second, exponential backoff with jitter
on 429 (honouring `Retry-After`), and retries on 5xx.

### Files

| File | Responsibility |
| --- | --- |
| `faceit_sync/client.py` | HTTP only: endpoints, rate limiting, retries, pagination |
| `faceit_sync/sync.py` | Extraction, reconciliation, and orchestration — the hazards live here |
| `faceit_sync/db.py` | Schema, connection handling, idempotent write helpers |
| `faceit_sync/models.py` | Typed records and the stat-code mapping |
| `faceit_sync/cli.py` | The `faceit-sync` command surface |
| `matches.txt` | Seed list of match IDs and championship URLs |

### How it connects

Ingest writes `faceit.sqlite3` and nothing else. Two consumers read it:
`faceit_sync/export.py` builds the dashboard from it ([section 4](#4-dashboard-build)),
and the `owdb` package attaches it **read-only** for cross-referencing
([section 5](#5-capture--the-python-owdb-package)). Ingest itself never reads
capture data — the two halves meet only at export.

### Gotchas

**The three data hazards.** These are the reason the project exists rather than
being a thin API wrapper. Each is handled explicitly in `faceit_sync/sync.py`
and each has a dedicated test.

- **Hazard A — zeroed player rows are not forfeits.** A game played to
  completion whose stat capture failed (a team disconnecting at the end) returns
  rows with role `-` and all-zero stats. Writing those zeros would corrupt every
  average. Ingest writes `NULL` — never `0` — sets `stats_captured = False`, and
  takes the game outcome from `results[]` instead. Guarded by
  `tests/test_stats_null.py`.
- **Hazard B — an admin restart destroys that game's veto ticket.** A restarted
  game's democracy hero ticket comes back all-`open`. Ingest does not trust
  `sessions[]` (absent from every observed payload); it reconciles instead — a
  game present in `results[]` with an empty ticket was restarted, so the bans
  still come from the match payload but `banned_by_faction` is `NULL` and
  `was_restarted` is `True`. Guarded by `tests/test_restart.py`.
- **Hazard C — the democracy feed is ephemeral, roughly seven days.** When the
  whole payload 404s, no game in that match has veto attribution and the loss is
  permanent. This is why ingest must run often enough to catch matches while
  they are fresh. Guarded by `tests/test_history.py`.

**Veto slots are joined by ban-set equality, not by position.** A restarted game
leaves an `open` slot that shifts every later index, so positional alignment
between democracy slots and played games is unreliable. `_match_slot` joins on
the set of banned heroes instead. The same misalignment risk applies to
`demoURLs`: when the alignment cannot be trusted, ingest drops **all** replay
codes for that match rather than label a game with its neighbour's replay.

**The opaque stat codes are empirical.** FACEIT returns `i8`, `i9`, `i10`,
`i13`, `i14`, `i17` with no schema. `STAT_FIELD_MAP` in `faceit_sync/models.py`
maps them to eliminations, deaths, assists, damage, healing, and damage
mitigated, established by correlating each code against player role across real
matches. If FACEIT changes the schema, correct it there — it is the only place
the mapping exists.

**Never change the User-Agent to impersonate a browser.** FACEIT's edge returns
403 for `Mozilla/5.0`-style agents but accepts a descriptive one, so the client
sends `faceit-sync/…`. See `DEFAULT_USER_AGENT` in `faceit_sync/client.py`.

**The stats endpoint has no `/time` segment.** The documented
`/stats/time/matches/{id}` path 404s; the working path is
`/stats/v1/stats/matches/{id}`.

**One bad match must never abort a run.** Both `_ingest_and_tally` and the team
enumeration loop catch broadly and tally an error, so a single unreachable match
cannot block the daily update.

## 4. Dashboard build

How the live site at `docs/index.html` is assembled from static parts, and why a single JavaScript error blanks the page.

### What it does

`faceit-sync export --format html` turns the ingest database plus the merged
scouting report into one self-contained HTML file. No external fonts, scripts,
or images: it opens by double-clicking, works offline, works from `file://`, and
survives a strict CSP.

### How it works

**Assembly is plain concatenation at import time.** `faceit_sync/_dashboard.py`
reads four part files from `faceit_sync/dashboard/` in a fixed order and joins
them into the module-level `HTML_TEMPLATE`. There is no framework, no bundler,
and no build step — editing a part file *is* editing the page.

| Part | Lines | Responsibility |
| --- | --- | --- |
| `faceit_sync/dashboard/head.html` | 655 | Page shell, all CSS, the `__THEME_CSS__` and `// __DATA_INLINE__` markers |
| `faceit_sync/dashboard/pure.js` | 637 | Pure decision helpers — no DOM, no globals, unit-tested |
| `faceit_sync/dashboard/app.js` | 3248 | The `bootApp(DATA)` body: all rendering and interaction |
| `faceit_sync/dashboard/boot.js` | 14 | Data delivery, then closes the document |

**Two data-delivery modes**, both handled by `faceit_sync/dashboard/boot.js`.
By default `faceit_sync/export.py` inlines the whole payload as
`var __OWDB_DATA__={…}` and the page boots straight from it. With
`export --external-data`, the payload is written to a sibling `data.json` and
the page fetches it at runtime, leaving `docs/index.html` a static shell. That
fetch is deliberately the seam where future access-gating hooks in — serving
`data.json` from the authenticated Worker instead of from Pages.

**The pure/impure split is a testing boundary, not a style choice.** Everything
declared above `function bootApp(` can be executed by node without a DOM, and
`tests/test_dashboard_logic.py` does exactly that: it extracts the region of the
generated script ahead of `bootApp` and runs assertions against it. As the
comment at the top of `faceit_sync/dashboard/pure.js` puts it, every helper
there got a claim on the page wrong at some point, and the tests are the record
of the right answer. **New logic that can mislead a coach belongs in
`pure.js`**; new rendering belongs in `app.js`.

**The payload is escaped against HTML breakout.** `faceit_sync/export.py`
serialises with `ensure_ascii=True` and replaces every `<` with `<`, which
closes both the `</script>` and the `<!--` escape holes. JSON decoding reverses
it losslessly.

**Views and tabs.** Without `--championship`, every championship in the database
becomes a switchable division, grouped by region and tier; `--region`,
`--tier`, and `--season` narrow it. Playoff championships are split off and
attached to their matching regular-season division rather than becoming their
own view. The page has five tabs — Overview, Teams, Players, League meta,
Matches — with hash routing; Playoffs is a mode *inside* the Matches tab, not a
tab of its own.

### Files

| File | Responsibility |
| --- | --- |
| `faceit_sync/_dashboard.py` | Concatenates the parts, inlines the theme |
| `faceit_sync/export.py` | Builds the data payload and writes the file |
| `faceit_sync/dashboard/` | The four part files, plus `theme.css` and the fonts |
| `faceit_sync/hero_icons.py`, `faceit_sync/hero_icons.json` | Hero portrait cache |
| `faceit_sync/team_logos.py`, `faceit_sync/team_logos.json` | Team avatar cache |
| `faceit_sync/subroles.py` | Hero sub-role classification used by the page |
| `docs/theme.css` | The shared design tokens, mirrored from the dashboard copy |

### How it connects

Export reads `faceit.sqlite3` ([section 3](#3-ingest--faceit_sync)) and
`owdb_comps.json` ([section 5](#5-capture--the-python-owdb-package)) and writes
`docs/index.html`. `.github/workflows/update.yml` is the **only** thing that
should run it against the live file ([section 8](#8-infrastructure-and-ci)).

### Gotchas

**A single JavaScript syntax error blanks the entire page.** The dashboard's
whole body is rendered in JS from the inlined blob, so a broken script produces
a completely empty page — and bracket-balance checks will not catch it. **After
editing any file under `faceit_sync/dashboard/`, run
`tests/test_export.py::test_dashboard_javascript_is_syntactically_valid`**,
which runs `node --check` over the generated script.

**Never hand-edit `docs/index.html`.** It is a build artifact, regenerated by CI
from the part files on every run. An edit made there is lost at the next build.
Fix the part file instead.

**Never run `export` locally to "just regenerate" the live site.** The local
`faceit.sqlite3` is frequently days behind CI's cached copy, so exporting and
committing overwrites fresher match data with staler data. See
[invariant 2](#12-invariants).

**Shared styling lives in one file, copied twice.**
`faceit_sync/dashboard/theme.css` is canonical (bundled as package data, so a
non-editable install still has it); `docs/theme.css` is a tracked copy that
`docs/scrims.html` and `docs/capture/*.html` link directly.
`tests/test_export.py::test_dashboard_theme_assets_match_docs_copies` asserts the
two stay byte-identical. The dashboard cannot link the file — it must stay
self-contained — so `_inline_theme_css()` embeds it with the fonts converted to
base64 data URIs. Edit the shared tokens there; do not re-add a per-page copy.

**Hero portraits degrade silently.** `load_hero_icons()` returns an empty map
when `faceit_sync/hero_icons.json` is missing, and the page then renders comps
as text chips instead of icons — a quiet quality regression rather than an
error. Regenerate the cache with
`python -m faceit_sync.hero_icons <asset-dir>` if it goes missing.

## 5. Capture — the Python `owdb` package

How hero compositions are read off the Overwatch observer HUD and turned into typed, stored observations.

### What it does

FACEIT's API never says which heroes were played. `owdb` recovers that by
watching an in-client replay: it reads the observer HUD's hero portraits by
template matching, resolves each slot to a player and a hero, and stores the
result as timestamped observations in `owdb.sqlite3`. Those observations become
per-team composition scouting.

This is the original capture path and still the reference implementation of the
analysis. The path contributors actually use is the browser app
([section 6](#6-browser-capture-app)).

### How it works

The pipeline runs in stages, each owned by one module.

1. **Calibrate** — `owdb/calibrate.py`. The operator drags boxes over each
   team's hero-portrait strip and over two or three pieces of fixed HUD
   furniture. Each strip is subdivided into equal per-slot regions of interest.
   **Pixel coordinates live in the database, never in source.** The anchors let
   the runtime tell a live match view from a menu, killcam, or loading screen.
2. **Build the reference library** — `owdb/refs.py`. Reference portraits must be
   captured *from the client at the operator's exact resolution* — wiki and CDN
   art does not match in-game rendering. Each hero is stored in both visual
   states, alive and dead, with a perceptual hash. `owdb refs verify` reports
   gaps and near-collisions.
3. **Derive context from the replay code** — `owdb/context.py`. Six characters
   of replay code are enough: with `faceit.sqlite3` attached, the tool derives
   the match, game number, map, both teams, the winner, the bans, and all ten
   players with their roles, and reports whether that map was already captured.
4. **Capture** — `owdb/capture.py`. A one-to-two frames-per-second sampling loop
   grabs the screen through `dxcam`, falling back to `mss`. Screen capture is a
   **read only**; nothing is ever injected into the game process. Those libraries
   are heavy and Windows-specific, so they are imported lazily — importing the
   module, and therefore the CLI, must not require them until a real grab
   happens.
5. **Match** — `owdb/match.py`. **This is where the accuracy comes from.** Before
   matching a slot, the candidate set is reduced by the map's bans (a banned hero
   is impossible, not merely unlikely) and by the role expected for that slot,
   since the observer HUD orders slots by role. A tank slot becomes a 1-of-14
   decision instead of 1-of-52.
6. **Check integrity** — `owdb/integrity.py`. Two checks matter most. A slot that
   resolves to a *banned* hero is provably wrong, which makes it a better
   HUD-drift detector than an anchor similarity score — it is a logical
   impossibility rather than a threshold. And a map name OCR'd from the replay
   that disagrees with the stored map for that code exposes the `demoURLs`
   index-misalignment problem in ingest: `owdb` can see the map and
   `faceit_sync` cannot, which makes `owdb` a validator for it.
7. **Canonicalise comps** — `owdb/comps.py`. A comp is a *set* of heroes, not an
   ordered list, so `comp_id` is the SHA-1 of the sorted hero GUIDs and
   order-independence is structural rather than enforced.
8. **Interpret** — `owdb/analysis.py`. A comp is a **family**, not an exact
   lineup: two lineups are the same comp when they share four or more heroes, or
   exactly three including the same tank — in 5v5 the tank anchors a comp's
   identity. A mid-map change is then a FLEX swap (core intact) or a CORE swap (a
   genuinely different comp), and a core swap can be attributed to the enemy
   lineup at the moment it happened.
9. **Report** — `owdb/derive.py` and `owdb/scout.py`. The binding constraint here
   is sample depth — a median of roughly two games per team-map — so the rules
   are enforced in code: always report `n` beside a percentage, never render a
   bare percentage below the minimum sample size, and fall back from
   `(team, map)` to `(team, map category)` to `(team, all)` while stating which
   level was used.

**The testable-core pattern is used throughout.** Every module separates pure,
injectable logic from the IO shell that drives it, and only the pure half is
unit-tested — the frame grabs, OpenCV calls, and operator prompts are the
injected defaults, exercised only at runtime.

### Files

| File | Responsibility |
| --- | --- |
| `owdb/cli.py` | The `owdb` command surface — `calibrate`, `refs`, `capture`, `match`, `codes`, `review`, `drafts`, `doctor`, `heroes`, `scout`, `comps`, `contribute`, `export`, `code` |
| `owdb/db.py` | Schema, writes, and the read-only attach of the ingest database |
| `owdb/calibrate.py` | ROI and anchor capture |
| `owdb/refs.py` | The reference-portrait library |
| `owdb/capture.py` | Screen capture and the sampling pipeline |
| `owdb/match.py` | Constraint-reduced frame matching |
| `owdb/integrity.py` | The checks that stop the tool lying quietly |
| `owdb/comps.py` | Comp canonicalisation |
| `owdb/analysis.py` | Comp families and swap classification |
| `owdb/derive.py`, `owdb/scout.py` | Scouting statistics and per-team reports |
| `owdb/context.py` | Replay-code context derivation |
| `owdb/contribute.py` | Export, publish, and the multi-contributor merge |
| `owdb/firstrun.py` | First-run helpers, retained from the removed native GUI |
| `SPEC.md` | The original design reference these modules cite by section |

### How it connects

`owdb` reads `faceit.sqlite3` and writes `owdb.sqlite3`. `owdb contribute
export` and `owdb contribute push` turn local observations into a contributor
file under `data/captures/`; `owdb contribute merge` combines everyone's files
into `owdb_comps.json`, which `faceit_sync/export.py` reads at build time
([section 4](#4-dashboard-build)). The contribution formats are specified in
[section 9](#9-data-contracts).

**The unit of contribution is the raw observation, never a finished report.**
Two summaries cannot be merged, and a summary is frozen against the analysis
that produced it. Publishing observations instead means improvements to the
analysis apply retroactively to every past contribution — which is exactly why
`owdb_comps.json` is regenerated at every build and never committed.

### Gotchas

**`owdb` must never write the ingest database.** `Database.attach_faceit` in
`owdb/db.py` attaches it with a `mode=ro` URI, so read-only is enforced by
SQLite itself rather than by discipline — a write against `faceit.*` raises.
Cross-database joins work; cross-database foreign keys do not, so FACEIT keys
are plain validated columns.

**Replay codes are invalidated by every Overwatch patch — a "code wipe."** The
wipe date is duplicated in **two** places that must be updated together:
`_SEED_WIPES` in `owdb/db.py`, which drives the value that reaches the site, and
`CODE_WIPE_DATE` in `tools/build_capture_data.py`, which drives the capture
tool. The pinned assertions in `owdb/tests/test_codes.py` and
`owdb/tests/test_context.py` must be updated in the same change. The procedure
is in [section 10](#10-lifecycles-and-operations).

**Type checking does not cover this package.** The documented command is
`mypy faceit_sync`, and `owdb` is not part of the must-stay-clean contract — at
the time of writing `mypy owdb` reports two errors in `owdb/contribute.py`.
`pyproject.toml` adds `ignore_missing_imports` and `follow_imports = "skip"`
overrides for `cv2`, `dxcam`, `mss`, `numpy`, and `keyboard`, which ship no
usable stubs. The tests, not the type checker, are this package's safety net.

**The native Windows GUI is gone and must not come back.** `owdb/gui.py`,
`owdb_app.py`, the PyInstaller spec files, and the `Scout app.cmd` launcher were
removed in August 2026. Only the tested first-run helpers in
`owdb/firstrun.py` survive.

## 6. Browser capture app

The zero-install capture tool at `docs/capture/` — the only supported capture path.

## 7. Scrims

The private, browser-local side channel for scrim data, and the separate page that reads it.

## 8. Infrastructure and CI

What runs outside this repository: the Cloudflare Worker and the GitHub Actions workflow that is the sole writer of the live site.

## 9. Data contracts

The exact shape of every file that crosses a subsystem boundary.

## 10. Lifecycles and operations

The recurring procedures: code wipes, season cutover, and deploying each piece.

## 11. Glossary

The project's vocabulary, defined once.

## 12. Invariants

Rules that must not be broken, each with the failure mode it prevents.

## 13. Testing map

Which tests guard which subsystem, and the commands that prove nothing is broken.

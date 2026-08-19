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
| `CHANGELOG.md` | What changed and when, reconstructed back to the first commit. | reference |
| `AGENTS.md` | Canonical instructions for coding agents — every agent reads this one. | reference |
| `CLAUDE.md` | A pointer to `AGENTS.md`. | reference |
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
wipe date has **one** source: `_SEED_WIPES` in `owdb/db.py`, whose maximum is
`LATEST_KNOWN_WIPE`. Both consumers derive from it — the value that reaches the
site, and `CODE_WIPE_DATE` in `tools/build_capture_data.py`, which imports it
rather than restating it. The pinned assertions in `owdb/tests/test_context.py`
must be updated in the same change. The procedure is in
[section 10](#10-lifecycles-and-operations).

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

### What it does

`docs/capture/index.html` does in a browser tab what the Python package does on
a desktop: the scout shares their screen while an Overwatch replay plays, the
page reads the hero portraits and player names off the HUD, and the finished map
is uploaded as a contribution. It needs no install, no Python, and no
command line — which is the entire point, because capture adoption is the
project's binding constraint.

### How it works

**Screen capture is `getDisplayMedia`.** The page draws the shared stream to a
canvas and template-matches hero portraits against reference images the scout
has learned, held in the browser's own IndexedDB.

**Player names are read with OCR.** `tesseract.js` is loaded lazily from
jsDelivr on first use and runs in a worker. It is optional: when it fails to
load, capture continues without name attribution rather than breaking.

**The crop handed to tesseract is found, not assumed.** The calibration box is
fitted to the *portraits*, and the fixed band underneath it that the crop used
to assume (48-90% of cell height) straddles the portrait bottom, the name and
the health bar on a real frame - so the brightest thing in the crop was the
health bar and the reads came back as letter-soup. `engine/frames.js nameRow()`
now locates the name row **once per side, across the whole five-slot strip**,
and all five crops use it. Per slot it cannot be done: the hero portrait sits
inside the cell *above* the name and its art is transition-dense, and a long
name can out-score the health bar - the two obvious per-slot heuristics were
both tried and both picked the wrong band. Across the strip the five names
reinforce each other while portrait noise averages out. The row is the run of
rows with many horizontal light/dark transitions that does not fill the strip
(a full health bar fills ~0.55 of it, a name ~0.15-0.32) and sits in the
quietest surroundings, the names being drawn on a dark plate. Measured on real
frames: 15 of 90 slots read correctly before, 77 of 90 after, and every one of
the 90 resolves once the role constraint is applied - against 36 of 90 with two
*wrong* before. `tools/real_frame_eval/` has the numbers, the threshold sweep
(1800 box/resolution variants, all landing on the row) and a parity check that
runs the shipped JS over real pixels.

**Names are not how a slot is assigned to a player — role is.** Overwatch
tournament play is role-locked, and FACEIT records the role each player queued
for, per game: 8303 of 8356 team-games in the database are exactly 1 Tank /
2 Damage / 2 Support, and all 53 exceptions are a *missing* role rather than a
real 2-tank comp. So `engine/assign.js` reads the role off the hero recognised
in each slot and uses it to partition the candidates. A correctly-read comp
collapses from 120 permutations to 1 × 2 × 2 = 4 — and **the tank is determined
with no name evidence at all**. It is the same reduction `owdb/match.py` already
applies to hero matching, pointed at players instead.

Assignment is optimal within a role group rather than greedy, and it abstains
rather than guesses: a contested group must clear a lead over the runner-up, and
then either an absolute score floor or one slot matching decisively — a single
confident read settles its partner by elimination, and the group mean must not
veto that. **The floor is what makes this safe.**
Without it the identical resolver produced 33.6% *wrong* attributions once the
reads degraded to noise, because uniform noise reliably manufactures a score
lead between two candidates. `tools/assign_eval.py` measures all of this against
every real lineup with ground truth known by construction; re-run it when the
rosters grow.

**Its corruption model understates the win, and `tools/real_frame_eval/` shows
why.** Run against real tesseract output on real HUD frames — ground truth taken
from the replay code burnt into the frame — the name-only matcher resolves 85% of
slots and the role-constrained one 100%, neither ever wrong. The synthetic model
degrades every name a little; real OCR destroys whole names and leaves the rest
pristine. It returned `4.04` for a clean, legible `PROXY` in six frames of eight.
And a slot reading `JODAN` perfectly still matched nothing, because FACEIT's
stored `game_name` for that player says `Arclite` — **the battletag on a FACEIT
account can be stale against the live Battle.net name**, which is worth
remembering before trusting `game_name` as an identity key.

The name matcher survives as the fallback for a game with no `lineups` entry, so
a stale feed degrades to the old behaviour rather than to nothing. The
per-slot outcome is published as `player_conf` (`forced` / `matched` / `null`)
beside the raw read, so a later matcher can tell a role-determined tag from a
name-matched one.

**`docs/capture/index.html` and `docs/capture/scrim.html` share a JS engine
under `docs/capture/engine/`, not by copy-paste.** The two pages used to be
hand-maintained forks of one another: a 2026-08-12 audit
(`tools/capture_divergence.py`) found 104 top-level functions defined in both
files, 44 of them silently drifted apart. Seven modules were extracted so the
logic is owned once:

| Module | Owns |
| --- | --- |
| `engine/names.js` | Name normalisation, similarity scoring, roster affinity, `confidentOrientation`. The fold transliterates stroked Latin letters (`ø ł ħ ŧ …`) as well as decomposing accents — NFD leaves the stroked ones alone, so the roster kept a glyph an ASCII-restricted OCR could never emit |
| `engine/assign.js` | Role-constrained player assignment: which FACEIT player is in which HUD slot (league capture only) |
| `engine/util.js` | HTML/attr escaping, CSS injection, base64 helpers, toasts, modals, the `ICONS` table |
| `engine/idb.js` | IndexedDB open/read/write; `open(version, stores)` takes its store list from the caller rather than hard-coding one |
| `engine/frames.js` | Screen share, frame grab, greyscale canvases, HUD name-row location and name crops; `ctx.onStop` is the page-specific teardown hook |
| `engine/calibration.js` | Box picking, auto-calibrate, calibration preview, overlay drawing; `ctx.boxKeys` scopes which calibration boxes a page owns |
| `engine/refs.js` | Hero portrait recognition, learned references, the OCR worker |
| `engine/heroes.js` | Which role each hero plays, and `byRole()` for grouping a catalogue by it. The ONE copy of the role table — `docs/scrims.html` imports it too, which is that page's only external script |
| `engine/overlay.js`, `engine/tour.js` | The floating capture console, and the guided-tour mechanism — `tourDefs`/`updateGuide` stay page-side since the tour content itself is page-specific |

**The module contract is a UMD IIFE plus `make(ctx)` for anything stateful.**
Every module exports the same way `docs/capture/scoreboard.js` always has —
`module.exports = Mod` under Node, `global.OWDBxxx` (`OWDBNames`, `OWDBUtil`,
`OWDBIdb`, `OWDBFrames`, `OWDBCalibration`, `OWDBRefs`, `OWDBOverlay`,
`OWDBTour`) in the browser — so the same file runs under `node --test` and in
either page unmodified. A module that needs per-page state (DOM handles,
which boxes to draw, what happens on stop) takes a `make(ctx)` factory and
reads its behaviour from `ctx`; page differences are **injected, never
branched on inside the module**. `docs/capture/scoreboard.js` is the original
of this pattern — the engine modules generalise it.

**The snapshot/review/finish cluster is deliberately not extracted.**
`finishMap` and its neighbours stay forked, defined separately in each page,
until phase 3: `finishMap` is roughly 1,530 characters in `index.html`
against a roughly 110-character stub in `scrim.html`, and phase 3 rewrites the
scrim finish flow anyway, which would waste an extraction done now. Anyone
touching snapshot, review, or finish logic must check **both**
`docs/capture/index.html` and `docs/capture/scrim.html`.

**The app is fed by two committed JSON files rather than by crawling FACEIT.**
`docs/capture/data.json` carries the capturable replay codes and the rosters, and
is rebuilt by `tools/build_capture_data.py` on every CI run.
`docs/capture/refs.json` carries the curator's hero reference library and is
committed by hand via `tools/build_capture_refs.py`.

**Scouts do not collide, in real time.** Every open capture page holds one
WebSocket to a Durable Object claim room on the Worker. Claiming or releasing a
map is pushed to everyone instantly, and a dropped socket frees that scout's
claims immediately. If the socket cannot be established the page falls back to
HTTP polling, and if the endpoints are not deployed at all every claim call
degrades to a no-op — the page always works.

**Identity is a browser-local token.** A random 24-byte token is generated on
first use and kept in `localStorage`; the first upload under a display name
claims that name for that browser. Uploads go to `https://upload.owdb.io`, which
commits them into `data/captures/` ([section 8](#8-infrastructure-and-ci)).

### Files

| File | Responsibility |
| --- | --- |
| `docs/capture/index.html` | The league capture app — self-contained apart from theme and OCR |
| `docs/capture/scrim.html` | Scrim capture — see [section 7](#7-scrims) |
| `docs/capture/engine/` | The shared engine: `names.js`, `util.js`, `idb.js`, `frames.js`, `calibration.js`, `refs.js`, `overlay.js`, `tour.js`, `session.js`, `heroes.js`. `names.js`, `session.js`, `opponents.js`, `frames.js` and `heroes.js` have a co-located `*.test.js`; the rest are DOM- and browser-API-coupled and are covered from `tests/` instead |
| `docs/capture/scoreboard.js` | Scoreboard OCR parsing, with its own `docs/capture/scoreboard.test.js`; the original of the UMD `make(ctx)` pattern |
| `docs/capture/data.json` | Codes and rosters feed, rebuilt by CI |
| `docs/capture/refs.json` | Curator-committed hero reference library |
| `docs/capture/hero_icons.json` | Hero portrait art for the UI |
| `tools/build_capture_data.py` | Builds `docs/capture/data.json` from the ingest database |
| `tools/build_capture_refs.py` | Builds `docs/capture/refs.json` from a curator's local library |
| `tools/capture_divergence.py` | Reports which top-level functions still differ between the two pages — run it before touching shared code |

### How it connects

The app reads the two committed feeds, writes to browser IndexedDB while
working, and publishes finished maps to the Worker. The Worker commits them to
`data/captures/`, which triggers a CI rebuild of the site
([section 8](#8-infrastructure-and-ci)). The dashboard links into this app: every
replay-code chip opens it with that code pre-loaded, and every team name offers a
capture icon that pre-filters it to that team.

### Gotchas

**The Content-Security-Policy lives in a `<meta>` tag, not in a header.** A
`curl -I` against the page shows no CSP at all, which makes it invisible when
debugging. This cost four sessions once, when the policy silently blocked
`tesseract.js` from starting its blob worker. **When a browser API fails
silently on these pages, check the CSP meta tag first.** `tests/test_capture_csp.py`
now pins the four clauses that matter: `worker-src blob:`, `wasm-unsafe-eval`,
the `data:` connect source, and the jsDelivr origin the OCR library is loaded
from.

**`script-src` lacked `'self'` until commit `bc91c1f` (2026-08-12), and that
silently blocked every same-origin script.** `style-src`, `img-src`, and
`font-src` all carried `'self'`; `script-src` did not, so `<script
src="scoreboard.js">` never loaded in production — `window.Scoreboard` was
undefined on both pages the whole time, with no console error pointing at the
CSP. Adding `'self'` was a prerequisite for the engine extraction below, since
every `engine/*.js` file is loaded the same-origin way.

**The page is not an artifact and may use a CDN.** Unlike `docs/index.html`,
which must stay self-contained, this page links `docs/theme.css` directly and
pulls `tesseract.js` from jsDelivr.

**These pages are tested from Python.** The suite in `tests/` parses the HTML and
runs `node --check` over the inline scripts — see
`tests/test_capture_scrim.py::test_league_capture_html_inline_script_is_syntactically_valid`.
Editing a capture page without running those tests risks shipping a page that
does not parse. **`tests/test_capture_js_units.py` runs every
`docs/capture/**/*.test.js` file under `node --test`** — before this shim
existed, `scoreboard.test.js`'s 9 tests sat green in the repo but were never
actually executed by anything. Run `tools/capture_divergence.py` before
touching any function shared between the two pages; it reports which
top-level functions still differ so a fix does not silently apply to only one
page.

**Real drift the extraction fixed, as a sample of what "104 shared functions,
44 diverged" meant in practice:** `simScore` — the scrim page's name
normaliser was weaker than the league page's; `uiModal` — the scrim copy had
dropped the `textarea` case, which broke editing and re-parsing an OCR read
on that page only; `ocrWorker` — the scrim page never got the league page's
OCR load timeout, so a stuck load could hang forever on scrim capture but not
on league capture.

## 7. Scrims

The private, browser-local side channel for scrim data, and the separate page that reads it.

### What it does

Scrims are private practice matches, and their compositions must never become
public. Scrim mode records them into the browser and nowhere else: a scrim is
captured the same way a league map is, but the result stays in local storage and
is readable only by the person who recorded it.

### How it works

**Storage is one IndexedDB database, `owscout-capture`, at schema version 5.**
Both capture pages open it with an explicit version and **both create every
store**, from the single `ALL_STORES` map in `docs/capture/engine/idb.js`:
`maps` (league captures), `refs` (learned hero portraits), `heroes` (custom
heroes), `scrims` and `scrim_maps`.

**Each page must not declare only the stores it uses**, however natural that
looks. `onupgradeneeded` fires once per version, so whichever page opens the
database first would create its own stores and fix the version, leaving the
other page's stores uncreated and every transaction on them throwing
*"One of the specified object stores was not found"*. It is symmetric: league
page first kills scrim capture, scrim page first kills league capture. The bug
predates the engine extraction — `main` at `7e7bde2` fails identically — and was
survivable only while scrim capture was paused, since nobody reached the scrim
stores. Un-pausing scrims made the normal path (a new contributor opening the
league page first) a broken one.

Version 5 exists to heal databases created before that fix: a browser that only
ever opened one capture page sits at v4 with half the stores, and without a
version change `onupgradeneeded` would never fire again to add the rest. The
upgrade only ever **adds** stores, so existing records — learned hero refs above
all, which are hand-taught and irreplaceable — are untouched.

**`docs/scrims.html` is the one scrims viewer**, reached from the League/Scrims
toggle in the top bar. It works because `docs/capture/` and `docs/` are the same
origin, so the page can open the very same IndexedDB. It opens it **without a
version argument** — which is precisely how it reads the data without ever
triggering an upgrade.

**Scrim records store hero GUIDs, not names.** Hero names and roles are not part
of the league data payload, so `docs/scrims.html` resolves GUIDs by fetching
`docs/capture/refs.json` for names, then inferring each hero's role from its own
small `ROLE_MAP` table, because `refs.json` carries names only.

### Files

| File | Responsibility |
| --- | --- |
| `docs/capture/scrim.html` | Scrim capture |
| `docs/scrims.html` | The one scrims viewer; read-only consumer of the IndexedDB |
| `tools/scrim_code/` | OverPy source for the in-game Workshop scrim helper |
| `tests/test_capture_scrim.py` | Session-text parsing, map filtering, side detection, script validity |

### How it connects

It deliberately connects to almost nothing. Scrim data is **never** published to
the Worker, **never** merged into `data/captures/`, and **never** read by the
league dashboard. The only link is the same-origin IndexedDB read by
`docs/scrims.html`, and the only shared file is `docs/capture/refs.json` for
hero-name resolution.

### Gotchas

**Never bump the IndexedDB schema version from `docs/scrims.html`.** It is a
read-only consumer. Opening with a higher version would trigger an upgrade
transaction from a page that does not own the schema, and the capture app is the
only writer.

**Never add scrims into the dashboard build.** The two scrims implementations
were consolidated in August 2026 — the dashboard's vestigial "Scrims tab" was an
unused `HERO_BY_GUID` map plus the `guid` payload field it read, and both were
removed. `docs/scrims.html` is the single viewer, and the private side stays
separate.

**The league-code block lives in `docs/capture/engine/session.js`.**
`buildCodeIndex()` turns `docs/capture/data.json`'s `codes` array into a
lookup keyed by normalized code; `classifyCode()` checks an entered code
against that index and against `data.json`'s `code_wipe_date` to say whether
it's a live league code and, if so, which division. `docs/capture/scrim.html`
calls this at every point a code can start a scrim capture
(`refuseIfLeagueCode()`), and on a match shows a modal naming the division and
offering to jump to League capture instead of letting the save proceed. A
league map's replay code can no longer be recorded as a private scrim.

**Three features still carry `WIP` badges**: auto side-detection, the scoreboard
OCR read, and the score-box read. Side detection has since worked end to end in
the field (2026-08-19, all ten slots), but one confirmed run is not a track
record and the badge stays until it has several. The other two are scoped to
phase 3 of `specs/2026-08-12-scrim-mode-design.md`.

**The scrim workflow lives in the pop-out panel, not on the page.** The page is
setup — share the screen, calibrate, name the scrim — and pressing *Save scrim*
opens the panel. From there the whole loop closes without an alt-tab: choose the
map and its optional replay code, note the bans on a role-grouped hero grid,
capture, *Finish + save*, then either the next map or *Finish scrim capture*
(offered only between maps, and only once a map has been saved). The page has no
map, ban or import controls at all; anything it offered during a scrim was a
control that cost an alt-tab, and its own *Start map* predated the ban picker
and could begin a map with the draft unrecorded.

**Two functions are deliberately kept without a caller**:
`parseScrimSessionText()` in `scrim.html` and `buildScaffold()` in
`engine/session.js`. Both were the screenshot importer's, whose UI was removed
with the rest of the page's map controls — importing a whole replay history is
not something done mid-game. They read and league-annotate replay-history text,
which is exactly what the planned replay-code OCR needs, so they are reserved
rather than deleted. Their tests still run.

## 8. Infrastructure and CI

What runs outside this repository: the Cloudflare Worker and the GitHub Actions workflow that is the sole writer of the live site.

### What it does

Two pieces of infrastructure keep the site alive without anyone's computer being
on. A GitHub Actions workflow fetches new matches and rebuilds the site on a
schedule. A Cloudflare Worker accepts capture uploads, handles login, and
coordinates live scouting claims between scouts.

### How it works — the CI workflow

`.github/workflows/update.yml` is the **only writer of `docs/index.html`**. It
runs on four triggers: the daily schedule, a manual dispatch, a
`repository_dispatch` of type `refresh` (which is what the site's "Refresh now"
button fires through the Worker), and a push touching `data/captures/**`,
`faceit_sync/**`, `owdb/**`, `tools/**`, `docs/capture/**`, `refs.json`, or
`matches.txt`.

**The daily schedule is two crons with a gate**, because GitHub cron is UTC-only
while the target is 9pm London. Both `17 20 * * *` and `17 21 * * *` are
registered, and a `gate` job runs only the one where it is actually 21:00 in
London, skipping the shadow. Minute 17 is chosen because on-the-hour crons are
GitHub's most congested slot. The gate logs the computed London hour on every
run — that line is the only evidence the runner's timezone database resolves at
all.

**Fetching is skipped when it is not needed.** Only the schedule, a manual run,
and a refresh dispatch set `DO_FETCH=true`. A code or contribution push
re-exports from the cached database in seconds. A missing cache self-heals by
forcing a full fetch, since the seed list rebuilds every division through
transitive discovery.

**The database is carried between runs in the Actions cache**, keyed on the run
ID and restored by prefix. The checkout uses `fetch-depth: 0` on purpose:
`git_submission_order` in `owdb/contribute.py` decides who owns a contested map
by the commit that *added* their file, and a shallow clone cannot see it — every
file would look equally old and silently fall back to name order.

**The build order per run** is: fetch matches → backfill Battle.net game names →
merge `data/captures/s9/` into `owdb_comps.json` and `docs/captured.json` →
export `docs/index.html` pinned with `--season s9` → rebuild
`docs/capture/data.json` → publish a compacted, gzipped database snapshot to
`docs/faceit.sqlite3.gz` → commit and push if anything changed.

### How it works — the Cloudflare Worker

`infra/upload-worker/worker.js` is deployed to `upload.owdb.io`. Its routes:

| Route | Purpose |
| --- | --- |
| `/` (POST) | Accept a capture upload and commit it to `data/captures/s9/<name>.json` via the GitHub contents API |
| `/refresh` | Fire a `repository_dispatch` at the site repo — the "Refresh now" button |
| `/claims`, `/claim`, `/unclaim`, `/claims/ws` | Live scouting claims, held in the `ClaimRoom` Durable Object |
| `/auth/login`, `/auth/callback` | Discord OAuth login |
| `/admin/contributors`, `/admin/claims`, `/admin/contributor` | The admin roster panel |

`ClaimRoom` is a single global SQLite-backed Durable Object holding the claim
room and every scout's WebSocket, which keeps it on the Workers free plan.
Contributor display names are reserved in a KV namespace bound as `NAMES`.

### Files

| File | Responsibility |
| --- | --- |
| `.github/workflows/update.yml` | The scheduled build; the only writer of the live site |
| `infra/upload-worker/worker.js` | Uploads, refresh dispatch, auth, claims |
| `infra/upload-worker/wrangler.toml` | Routes, bindings, the `NAMES` KV namespace, the DO migration |
| `infra/upload-worker/DISCORD_SETUP.md` | How the Discord app is configured |

### How it connects

CI reads `matches.txt` and `data/captures/`, writes `docs/index.html`,
`docs/captured.json`, `docs/capture/data.json`, and `docs/faceit.sqlite3.gz`. The
Worker writes into `data/captures/`, which triggers CI. The capture app talks to
the Worker; the dashboard's refresh button reaches CI through it.

### Gotchas

**The Worker is deployed by hand, not by CI.** `wrangler deploy` is run by a
human and bypasses git and GitHub Pages entirely — so the Worker's live code can
differ from what is committed here, and a change committed to
`infra/upload-worker/worker.js` is **not live until someone deploys it**.

**Its secrets are separate from GitHub's.** `GITHUB_TOKEN`,
`DISCORD_CLIENT_ID`, `DISCORD_CLIENT_SECRET`, and `SESSION_SECRET` are set with
`wrangler secret put`. A valid, correctly-scoped GitHub PAT is not enough — if
the Worker's stored copy is stale, the refresh button returns 401 while
everything else looks fine.

**Two independent copies of `faceit.sqlite3` exist and nothing reconciles
them** — the local one and CI's cached one. See
[section 1](#1-the-map) and [invariant 2](#12-invariants).

**Season is pinned in the export flag.** CI passes `--season s9` so the live site
stays on Season 9 even once Season 10 championship IDs start appearing in the
database during the overlap. Changing it is part of the cutover, not a casual
edit — see [section 10](#10-lifecycles-and-operations).

**Fetch errors are tolerated; the export is not.** A stray unreachable match must
never block the daily update, so both fetch steps swallow errors and continue.

## 9. Data contracts

The exact shape of every file that crosses a subsystem boundary.

Shapes below were read from the live files, not from a specification.

### `data/captures/<season>/<contributor>.json` — the durable record

Written by the upload Worker or by `owdb contribute push`; read by
`owdb contribute merge`. **This is the one committed artifact that cannot be
regenerated** — everything else in the scouting pipeline is derived from it.

```json
{
  "format": 1,
  "contributor": "ccarn",
  "tool_version": "0.1.0",
  "heroes": {},
  "maps": [
    {
      "match_id": "1-4b63acd1-…", "game_no": 1, "demo_code": "GPJW93",
      "map_guid": "0x080000000000066D", "map_name": "Ilios",
      "map_category": "Control",
      "side_a_team_id": "db15d8f5-…", "side_a_team": "Wasp",
      "side_b_team_id": "d2ce5415-…", "side_b_team": "Dystopia",
      "winner_side": "a", "captured_at": "2026-07-18T12:49:01Z",
      "bans": ["0x02E00000000004E3"],
      "profile": {"w": 2560, "h": 1440, "hud_variant": "default"},
      "observations": [
        {"side": "a", "ts": 0, "sub_map": "Ruins", "round_no": 1,
         "phase": null, "heroes": ["0x02E0000000000516", "…"]}
      ]
    }
  ]
}
```

Every hero and map is a GUID, never a name — names change, GUIDs do not.
`observations` are raw samples with a timestamp, which is what makes the whole
scheme work: the report is recomputed from them at every build, so analysis
improvements apply retroactively.

**Contested maps resolve first-wins by commit date.** `git_submission_order` in
`owdb/contribute.py` orders contributor files by the commit that added each one,
because the contributing machine cannot be trusted to timestamp its own
submission. Files git knows nothing about sort last, by name.

### `owdb_comps.json` — the derived report

Written by `owdb contribute merge` at build time, read by
`faceit_sync/export.py`. **Never committed** — `.gitignore` excludes it, so a
stale report can never outlive the observations it came from or freeze the
analysis that produced it.

### `docs/captured.json` — coverage index

Written by the same merge step, read by the dashboard to show which maps are
already captured. A `format` and `generated_at` header over a flat list of
`"<match_id>:<game_no>"` strings.

```json
{"format": 1, "generated_at": "2026-08-11T01:41:39Z",
 "captured": ["1-00a16ee9-…:1", "…"]}
```

### `docs/capture/data.json` — the capture app's feed

Written by `tools/build_capture_data.py` on every CI run; read by
`docs/capture/index.html` and `docs/capture/scrim.html`. It exists so the capture
app never has to crawl FACEIT itself.

```json
{
  "built_at": "…", "code_wipe_date": "2026-08-11",
  "regions": ["EMEA", "NA"], "divisions": ["EMEA Master", "…"],
  "codes": [
    {"code": "2RYPJJ", "match_id": "1-57b84ab3-…", "game_no": 1,
     "map": "Antarctica", "map_category": "Control",
     "map_guid": "0x0800000000000CF2", "division": "NA Expert",
     "team_a": "…", "team_b": "…", "t1": "<uuid>", "t2": "<uuid>",
     "finished_at": "2026-08-11T01:41:39Z"}
  ],
  "rosters": {
    "<match_id>": {
      "<team_id>": {"name": "Qwiz Esports",
        "players": [{"id": "…", "nick": "qeezyow", "game_name": "qeezy"}]}
    }
  },
  "lineups": {
    "<match_id>:<game_no>": {
      "<team_id>": {"name": "Qwiz Esports",
        "players": [{"id": "…", "nick": "qeezyow", "game_name": "qeezy",
                     "role": "Tank"}]}
    }
  },
  "hero_roles": {"0x02E000000000007A": "Tank"}
}
```

`game_name` is the Battle.net name the Overwatch HUD actually shows, which is
why ingest backfills it separately — the FACEIT nickname often differs.

**`lineups` is keyed per game and `rosters` per match, and that is not
redundancy.** `rosters` groups by `(team, player)` across the whole match, so a
substitution inflates it — 610 of 2260 real match-teams (27%) carry more than
five players. Player assignment needs an *exact cover* of five over five slots;
hand it six and the damage group has three candidates for two slots, so the role
constraint stops constraining and a substitute who never played that game becomes
a candidate for it. Scrim opponent identification wants
the opposite — the accumulated squad, because a season's stand-ins are what still
identify a lineup when two players are on smurfs. Two consumers, two correct
shapes; neither should be bent to serve the other.

`role` is FACEIT's own per-game value (the `i16` stats field), stored as `null`
for a game whose stats never captured rather than guessed. `hero_roles` exists
because the browser otherwise has no role for a *built-in* hero at all — only
`CUSTOM_HEROES` carried one — and the slot's role is read off the recognised
hero.

### `docs/capture/refs.json` — the hero reference library

Written by `tools/build_capture_refs.py` from a curator's local library and
committed by hand; read by `docs/capture/index.html` and `docs/scrims.html`. It
carries the calibration geometry the references were captured at, then one
record per hero-state with a name, GUID, visual state, and the image data.

```json
{"w": 2560, "h": 1440, "left_fraction": 0.0, "top_fraction": 0.0,
 "refs": [{"n": "<name>", "g": "<hero guid>", "v": "<state>", "d": "<image>"}]}
```

`refs.json` carries **names only, not roles** — which is why `docs/scrims.html`
keeps its own hero-role table.

### The inlined dashboard payload

Written into `docs/index.html` by `faceit_sync/export.py` as
`var __OWDB_DATA__={…}`, or into a sibling `data.json` under `--external-data`.
It carries the divisions, rosters, maps, the merged comps, contributor lists,
inlined team avatars and hero icons, the code-wipe date, the refresh endpoint,
and a `built_at` timestamp so anyone can tell at a glance whether their
contribution has landed.

## 10. Lifecycles and operations

The recurring procedures: code wipes, season cutover, and deploying each piece.

### Registering a code wipe

Every Overwatch patch invalidates all existing replay codes. A game finished on
or before the latest wipe can never be replayed unless it was captured first,
which makes the wipe date the deadline the whole capture effort runs against.

**The wipe date has one source.** Add the new entry to `_SEED_WIPES` in
`owdb/db.py`; `LATEST_KNOWN_WIPE` is the maximum of that list and everything
downstream follows it, including `CODE_WIPE_DATE` in
`tools/build_capture_data.py`, which imports the value rather than restating it.

1. Append `("YYYY-MM-DD", "observed", "<why>")` to `_SEED_WIPES` in
   `owdb/db.py`.
2. Update the pinned assertions that name the previous date and the wipe count —
   `test_wipe_seeded_idempotently` in `owdb/tests/test_context.py`.
3. Run the suite. The capture tool stops offering pre-wipe codes automatically.

Fixtures whose matches must stay *alive* derive their dates from
`LATEST_KNOWN_WIPE` (`ALIVE_AT` in `owdb/tests/test_codes.py`, and the same
trick in `tests/test_capture_feed.py`), so a new wipe does not silently flip
them to dead. Keep new fixtures on that pattern rather than hard-coding a date.

Recorded wipes so far: 2026-07-14, 2026-07-28 and 2026-08-11.

### Season cutover

Season 10 cutover is **deliberately deferred until Season 9 finishes**, and the
safe-now subset (season-scoped captures and a season-filtered export) is already
shipped. The live site is pinned with `--season s9` in
`.github/workflows/update.yml`.

Do not improvise the cutover. The full sequence and the reasoning behind it —
archive export, bumping the season constants in both the Worker and
`owdb/contribute.py`, seeding Season 10 into `matches.txt`, flipping the live
`--season` filter — is in `specs/2026-08-10-season10-cutover-design.md`. A useful
property noted there: a season boundary is in practice one more wipe entry, so
once Season 10's wipe date is registered the capture tool stops offering Season 9
codes on its own.

### Deploying each piece

| Piece | How it goes live |
| --- | --- |
| The site (`docs/index.html`) | Automatically, by `.github/workflows/update.yml`. Never by hand. |
| The capture app (`docs/capture/`) | Commit to `main`; GitHub Pages serves it directly. |
| The scrims page (`docs/scrims.html`) | Same — commit and it is live. |
| The Cloudflare Worker | **A human runs `wrangler deploy`.** A commit alone changes nothing. |
| Worker secrets | `wrangler secret put <NAME>`, separately from GitHub's secrets. |

## 11. Glossary

The project's vocabulary, defined once.

| Term | Meaning |
| --- | --- |
| **Replay code** | Six characters that let the Overwatch client replay a specific game. The only way to see what heroes were played. |
| **Code wipe** | An Overwatch patch invalidating every existing replay code. The capture deadline. |
| **Veto / democracy** | The pre-match map and hero ban process. FACEIT calls the feed "democracy". |
| **Ban** | A hero removed from the pool for one game. Ingest stores which faction banned it when attribution survives. |
| **Comp** | The five heroes a team fields. Stored as a *set*, so slot order is irrelevant. |
| **Comp family** | A group of near-identical comps — four or more shared heroes, or exactly three including the same tank. |
| **FLEX swap** | A mid-map hero change that keeps the comp's core intact. |
| **CORE swap** | A mid-map change to a genuinely different comp. |
| **Sub-role** | A finer classification than Tank/Damage/Support — see `faceit_sync/subroles.py`. |
| **Region** | EMEA or NA. Parsed from the championship name. |
| **Tier** | Master, Expert, Advanced, or Open — the division's competitive level. |
| **Division** | A region-and-tier competition, e.g. "EMEA Master Central". |
| **Season** | A league season, e.g. `s9`. Parsed from the championship name. |
| **Faction** | FACEIT's name for a side in a match: `faction1` or `faction2`. |
| **Side** | The HUD's left/right, stored as `a` and `b`. Not the same as faction. |
| **Sub-map** | A stage within a Control map, e.g. Ilios's Ruins. |
| **Segment** | The unit scouting aggregates over: attack or defend on Escort/Hybrid, the sub-map on Control, else the whole map. |
| **Observation** | One timestamped sample of one side's five heroes. The raw unit of contribution. |
| **Capture** | One recorded map — a set of observations plus its context. |
| **Contributor** | Someone who captures maps. Owns one file under `data/captures/<season>/`. |
| **Curator** | The person who commits the shared hero reference library, `docs/capture/refs.json`. |
| **Claim** | A live lock on a map, so two scouts do not capture the same replay. |
| **Scrim** | A private practice match. Never published. |
| **GUID** | FACEIT's stable identifier for a hero or map, e.g. `0x02E0000000000516`. Used everywhere in preference to names. |
| **`game_name`** | A player's Battle.net name — what the Overwatch HUD shows. Often differs from their FACEIT nickname. |

## 12. Invariants

Rules that must not be broken, each with the failure mode it prevents.

1. **Never hand-edit `docs/index.html`.** `.github/workflows/update.yml`
   regenerates it from `faceit_sync/dashboard/head.html` on every run, so the
   edit disappears at the next build. Fix the part file instead.
2. **Never run `faceit-sync export` locally to "just regenerate" the site.** The
   local `faceit.sqlite3` is routinely days behind CI's cached copy, so
   exporting and committing overwrites fresh match data with stale data.
3. **Always run
   `tests/test_export.py::test_dashboard_javascript_is_syntactically_valid`
   after editing anything under `faceit_sync/dashboard/`.** The page is rendered
   entirely in JavaScript, so one syntax error yields a blank page — and
   bracket-balance checks will not catch it.
4. **Bump the code-wipe date only in `_SEED_WIPES` in `owdb/db.py`.** Everything
   downstream derives from it. Hand-editing a derived constant creates the
   disagreement the single source exists to prevent.
5. **Never bump the IndexedDB schema version from `docs/scrims.html`.** It is a
   read-only consumer opening the capture app's store; an upgrade transaction
   from a non-owner corrupts the contract between the two pages.
6. **Never commit `owdb_comps.json`.** A committed report would outlive the
   observations it came from and freeze the analysis that produced it, defeating
   the reason contributions are raw observations.
7. **Never change the client User-Agent to impersonate a browser.** FACEIT's
   edge returns 403 for `Mozilla/5.0`-style agents. Keep the descriptive
   `faceit-sync/…` string in `faceit_sync/client.py`.
8. **Never add scrims into the dashboard build.** Scrim data is private and
   browser-local; the dashboard must never touch that IndexedDB.
9. **Always `git fetch` before pushing.** CI auto-commits to `origin/main` every
   few minutes. Expect a merge, and resolve it by keeping CI's data and
   reapplying your own diff on top.
10. **Never put developer documentation in `docs/`.** That directory is the
    GitHub Pages web root, so anything added there is published to owdb.io.
11. **`wrangler deploy` is run by a human.** A change committed to
    `infra/upload-worker/worker.js` is not live until someone deploys it.

## 13. Testing map

Which tests guard which subsystem, and the commands that prove nothing is broken.

### Commands

```bash
.venv/Scripts/python.exe -m pytest                      # everything
.venv/Scripts/python.exe -m pytest tests/test_export.py # one file
.venv/Scripts/python.exe -m pytest -k scheduled         # by keyword
.venv/Scripts/python.exe -m mypy faceit_sync            # strict; must stay clean
```

`pyproject.toml` sets `testpaths = ["tests", "owdb/tests"]`, so a bare `pytest`
covers both suites.

**`mypy` covers `faceit_sync` only.** `owdb` is not part of the must-stay-clean
contract and currently reports two errors in `owdb/contribute.py`. The tests are
that package's safety net.

### Which tests guard what

| Subsystem | Tests |
| --- | --- |
| Ingest orchestration | `tests/test_sync.py`, `tests/test_idempotency.py`, `tests/test_pagination.py`, `tests/test_backoff.py` |
| Data hazard A — zeroed rows | `tests/test_stats_null.py` |
| Data hazard B — restarts | `tests/test_restart.py` |
| Data hazard C — ephemeral veto | `tests/test_history.py` |
| Replay-code alignment | `tests/test_demo_urls.py` |
| Scheduled fixtures | `tests/test_scheduled.py` |
| Playoffs | `tests/test_playoff_crawl.py` |
| Dashboard export and self-containment | `tests/test_export.py` |
| Dashboard pure logic | `tests/test_dashboard_logic.py` |
| Assets | `tests/test_team_logos.py`, `tests/test_snapshot_download.py` |
| Browser capture app | the `tests/test_capture_*.py` family — CSP, OCR, onboarding, attribution, observations, sub-maps, controls, filters, publish preview |
| Scrims | `tests/test_capture_scrim.py` |
| This document | `tests/test_docs_links.py` |
| Capture pipeline and analysis | `owdb/tests/` — matching, comps, swaps, integrity, refs, codes, context, contribute, scout, derive |

### The three that must always run after a dashboard change

```bash
.venv/Scripts/python.exe -m pytest \
  tests/test_export.py::test_dashboard_javascript_is_syntactically_valid \
  tests/test_export.py::test_export_html_is_self_contained_and_valid \
  tests/test_dashboard_logic.py
```

For a visual check, build a local preview and screenshot it with headless Edge —
on Windows use `--screenshot=FILE`, **not** `--dump-dom`, because the GUI
executable produces no stdout.

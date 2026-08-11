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

## 5. Capture — the Python `owdb` package

How hero compositions are read off the Overwatch observer HUD and turned into typed, stored observations.

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

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

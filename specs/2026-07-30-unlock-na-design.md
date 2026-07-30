# Unlock NA — design

**Date:** 2026-07-30
**Status:** approved, ready for implementation

> Spec location note: the superpowers default is `docs/superpowers/specs/`, but
> `docs/` is this repo's **published GitHub Pages root** (it holds `CNAME`).
> Internal specs live in `specs/` so they are never served from owscout.com.

## Goal

Ship the FACEIT League **NA** region on the site and make NA replays scoutable,
alongside the EMEA divisions already live.

## Background: nothing needs ingesting

NA is already in the database. `matches.txt` seeds NA Master and NA Expert, and
the keyless transitive crawler has ingested them for some time:

| Championship | matches |
|---|---|
| S9 EMEA Master Central | 108 |
| S9 EMEA Expert Central | 280 |
| S9 NA Master Central | 90 |
| S9 NA Expert Central | 315 |

(EMEA Advanced exists in CI's cached DB, not the local copy.)

This is therefore a **gating** change, not an ingest one. Three flags hide NA,
and most of the machinery behind them is already region-aware and dormant:

- `export.py` loops `for region in ("EMEA", "NA")` and mints a `"NA Combined"`
  view automatically.
- The dashboard's region `<select>` (`_dashboard.py:2729-2743`) derives its
  options from `VIEWS`, so it lights up as soon as a second region appears.
- The owscout GUI's region picker exists behind `LOCK_REGION`, whose own comment
  reads *"Set to None to restore the region picker (e.g. when NA is enabled)"*.

## Scope decisions

| Decision | Choice | Why |
|---|---|---|
| Reach | Site **and** capture tooling | NA divisions would otherwise render with permanently empty comp sections; unlocking capture lets data start accumulating. |
| NA tiers | Master + Expert | Already ingested. NA Advanced has no seed; adding one means a ~300-match rate-limited crawl. NA reading as 2 tiers vs EMEA's 3 is honest — that division simply isn't tracked yet. |
| Page weight | Accept, stay inlined | Measured below. |
| Landing view | Remember last division | An NA coach should pick their region once, not every visit. |

### Weight, measured

| build | raw | gzipped (what ships) |
|---|---|---|
| live today (EMEA M/E/A) | 4.67 MB | **631 KB** |
| local EMEA M/E | 2.39 MB | 380 KB |
| local + NA M/E | 4.65 MB | 657 KB |

The blob compresses ~7.1x and GitHub Pages serves gzip, so NA puts the live page
around **~950 KB on the wire**. That does not justify `--external-data` or a
per-region split. Keep it inlined; revisit only if a future season's data makes
the number move materially.

### Verified as needing no work

- **Player ranking pools.** `owscout/cli.py:572` keys per-game stats on
  `m.championship_id` — a UUID — so EMEA Master and NA Master are already
  distinct pools. The `rank_player_heroes` docstring's "champ keeps skill tiers
  apart" holds across regions for free.
- **Deep links.** `#scout=<Team>` / `#prep=<Team>` search every view for the
  division containing that team, so NA links resolve correctly. Checked for
  cross-region team-name collisions: exactly one, `"bye"`, a bracket placeholder.
- **Contributed `division` field.** Written by the capture app, displayed in its
  upload list, and read by nothing. Its format is free to change.

## Changes

### 1. The three flags

| File | Change |
|---|---|
| `.github/workflows/update.yml:143` | drop `--region emea` |
| `tools/build_capture_data.py:24` | `REGION = "EMEA"` -> both regions |
| `owscout/gui.py:35` | `LOCK_REGION = "EMEA"` -> `None` |

The comment above the export line is stale independently of this work — it says
the site ships "EMEA Master + Expert" when Advanced has been live for a while.
Correct it while editing.

Expected result: **EMEA** Master / Expert / Advanced / Combined and **NA** Master
/ Expert / Combined, EMEA first (the `("EMEA", "NA")` loop order).

### 2. Region-qualified divisions in the capture feed

The one place two regions genuinely collide. The browser capture app builds its
dropdown from `DATA.divisions` and filters `c.division === dv`
(`docs/capture/index.html:299,311`). With NA unlocked, a scout picking "Master"
would get EMEA and NA codes merged with nothing telling them apart.

Emit `division` as the qualified label — `"EMEA Master"`, `"NA Expert"` — and
build `divisions` from the same qualified strings. **The capture app needs no
changes**: same dropdown, same equality filter.

Two follow-ons:

- `_dashboard.py:1054` `captureUrl` passes `?division=<tier>`. It must pass the
  qualified label so the dashboard's "Capture this team" prompt still lands on
  the right filter. The region comes from the current view.
- Pre-existing `?division=Master` bookmarks fail the app's
  `.some(o => o.value === dv)` guard and fall back to `all` — a safe degradation,
  and the reason that guard is worth keeping.

### 3. Whole-word region matching

`export.py:474` classifies with a bare substring test:

```python
return "EMEA" if "EMEA" in u else "NA" if "NA" in u else None
```

Only the EMEA-first ordering saves this today. `owscout/db.py` already matches
whole words (`% NA %`) and carries a regression test
(`test_region_matches_whole_words_only`) written for exactly this hazard. Align
`_region_of` with that behaviour: `"S9 Open Nationals"` must classify as `None`,
not `NA`. Harmless while NA is hidden; load-bearing once a mis-classified
division would land in the wrong region's switcher.

### 4. Remember the last division

`_dashboard.py:562` sets `CURRENT_VIEW = VIEWS[0].id` with no persistence, so
every visitor lands on EMEA Master.

- `setDivision(id)` writes the id to `localStorage`.
- `init()` restores it **only if it still exists in `VIEWS`** — divisions change
  between seasons, and an unknown stored id must fall back to `VIEWS[0]` rather
  than blank the page.
- Deep links keep priority: `#scout=` / `#prep=` already reassign `CURRENT_VIEW`
  before `show()`, so no ordering change is needed beyond restoring before them.
- `localStorage` access is wrapped — it throws in some privacy modes, and this
  page renders its entire body in JS, so an uncaught throw is a blank page.

### 5. Documentation

`FEATURES.md`, `CLAUDE.md`, and the `build_capture_data.py` module docstring
("Scoped to EMEA, all tiers") all assert EMEA-only scope. Update each to state
EMEA + NA and which tiers per region.

## Testing

- **Mandatory after any `_dashboard.py` edit:**
  `pytest tests/test_export.py::test_dashboard_javascript_is_syntactically_valid`
  (`node --check` over the generated script). The page renders entirely in JS, so
  one syntax error yields a blank page that bracket-balance checks miss.
- New: `_region_of` whole-word cases, including the `None` case for a name
  containing "NA" as a substring.
- New: a two-region export asserting the switcher's view list and its
  EMEA-then-NA order. Must build its own fixture championships rather than read
  the working DB — the local copy has no EMEA Advanced, so a live-DB assertion
  would disagree with CI.
- New: `build_capture_data` emits qualified division labels for both regions.
- `pytest` full suite green; `mypy faceit_sync` clean.
- Visual: build a local preview, screenshot with headless Edge
  (`msedge --headless --screenshot=FILE "file:///...#overview"`), confirm the
  region dropdown appears, switches, and that the stored division survives a
  reload.

## Out of scope

- Seeding NA Advanced (one line in `matches.txt` whenever wanted).
- `--external-data` / per-region page splitting.
- A linkable `#div=<id>` hash.

## Risks

| Risk | Mitigation |
|---|---|
| First CI run after unlocking exports 7 views instead of 4 and is slower | Export is seconds; the slow part is the FACEIT fetch, which is unchanged (NA is already ingested). |
| A capture contributor's stale `?division=` bookmark stops filtering | Degrades to `all`, does not break. |
| NA divisions show empty comp/scout sections until someone captures them | Already the documented behaviour (FEATURES.md §5, "Known gaps"); FACEIT-derived data — standings, bans, maps, players, elo — is fully populated regardless. |

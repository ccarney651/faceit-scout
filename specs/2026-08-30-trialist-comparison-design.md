# Trialist comparison — design

**Date:** 2026-08-30
**Status:** design approved in conversation; spec awaiting operator review

## Goal

A local-only tool for judging trial candidates against each other. Search the
league's players by either name they go by, add them to a persistent trialist
pool, and read them as side-by-side columns in **separate tables per role**.

Built for a real need: the operator's team is trialling replacements for players
who cannot commit to the coming season.

## Scope decisions

| Decision | Choice | Why |
| --- | --- | --- |
| Where it lives | A local HTML file, never committed, never under `docs/` | A shortlist of who you are trialling leaks recruiting intent. `docs/` is the Pages web root (invariant 10). |
| Blizzard / ranked data | **Out of scope** | There are zero BattleTags in the data (measured: 0 of 1347 players have a `#` in `game_name`), and Blizzard has no official stats API. The candidate identity carries no field to join on, so this cannot be derived — only typed in. Deferred, not designed around. |
| Season scope | **All divisions in the DB**, not one season | The public site pins `--season s9` because it reports on the current season. Judging a trialist wants every map you have on them. |
| Region scope | **All regions**, searchable together | The DB holds EMEA and NA today (`REGIONS` allows SA/OCE). Candidates may come from anywhere; narrowing by default would hide them. |
| Composite score | **No** | One number hides which axis a player is good at, which is the entire question when comparing trialists. |
| Per-game role purity | **No** | Needs a payload addition. Dominant-role-per-team covers 1001 of 1187 players exactly; the flex badge (below) covers the rest. |

## What the data actually supports

Everything below was measured against `faceit.sqlite3` and `owdb_comps.json` on
2026-08-30. These numbers are the reason the page is shaped the way it is.

### Identity: two names, and the sheet uses the wrong one

A recruiter's shortlist is written in **in-game names**; FACEIT knows players by
**nickname**. They frequently differ. Of a real 24-name candidate sheet, matching
on `players.nickname` resolved **3**; matching on `players.game_name` resolved
**13**; a further 3 resolved by eye (`aziz` to `owaziz` / "Aziz1", `RDX` to
`llRDX` / "iRDX", `Galwyn` to nickname `Galwyn` / game name "StarWinks").

**Consequence:** search must cover `nickname` OR `game_name` and display both, or
the tool looks empty for people who are plainly in the data. There is no
automatic join to build here — 8 of the 24 have no candidate under either name,
because they do not play FACEIT League at all. The tool must say so rather than
render a blank.

### Sample sizes are thin and wildly uneven

Among the resolved candidates, maps played ranged from **8** (`styxywhixy`) to
**68** (`BroPla`). A win rate at n=8 next to one at n=68, printed the same way,
is a trap.

**Consequence:** every rate carries its `n`, and anything under its floor renders
as an em dash whose tooltip says why — the discipline the player pages already
enforce (n>=5 per mode, n>=3 per map).

### Hero pools are near-empty and actively misleading

Hero attribution comes from replay captures: **122 games, 128 players** in the
whole dataset. Of 14 resolved candidates, **4** had any hero attributed. One,
`monclermonk`, reads "Kiriko 14 of 14 games" — which is a capture-coverage
artifact, not evidence of a one-trick.

**Consequence:** hero pool is the last section, explicitly marked thin, and never
the basis of a comparison. The full-coverage substitute is FACEIT's per-game
`role`, which exists on every game of every player.

### Roles bucket cleanly, but not perfectly

Roles are `Tank` / `Damage` / `Support` (17639 / 17637 / 8811 rows; 63 null or
`'None'`). **1001 of 1187** players played exactly one role all season; median
role purity is **1.0**; only **103** fall below 90% purity. But the real flex
cases matter for a trial: `Warglabidoo` played 60 maps of Damage and 7 of Tank.

**Consequence:** dominant role decides the table, and a second role at >=10% of
maps puts the player in that table too, badged with the split.

### Tier and region make the headline numbers non-comparable

The candidate sheet spanned **three tiers** — Master (`monclermonk`, `graalistf`,
`7nexty`, `scraine`, `Javi44`), Expert (most), Advanced (`styxywhixy`) — and the
DB spans two regions. Elo is region-and-tier relative; `Eff` is z-scored against
same-role peers *within one division*.

**Consequence:** a `+0.9` Eff in Advanced is not a `+0.9` in Master. Every column
header names the player's region, tier and division, and the Eff row names the
peer group it was computed against. The tool does not attempt a cross-tier
normalisation — there is no defensible one.

## Architecture

### One command, one file

```
faceit-sync trials --out trials.html
```

A new `trials` subcommand mirroring `export`'s flags (`--db`, `--season`,
`--region`, `--tier`, `--out`), defaulting to every division in the DB and every
region. Output is a self-contained HTML file — openable from `file://`, nothing
to serve — written to `trials.html` and added to `.gitignore`.

### Components

**`faceit_sync/trials.py`** — the page builder. Two responsibilities, in this
order: build the search index, and render the shell around the payload. It owns
no analysis; see "reused math" below.

**`faceit_sync/cli.py`** — a thin `trials` subcommand. Argument parsing only.

**`faceit_sync/export.py`** — one contained refactor. `export_html()` currently
builds the data payload and renders the dashboard in a single ~240-line
function. Its payload half becomes:

```python
def build_dashboard_data(db, championship_id=None, only_tier=None,
                         only_region=None, only_season=None) -> dict:
```

`export_html()` then calls it and renders. Its signature and behaviour are
unchanged, and the existing export tests guard that. This exists so the trials
page and the site build their data through **one** code path and cannot drift.

### Reused math, not re-derived math

The page inlines `faceit_sync/dashboard/pure.js` **unchanged** and calls:

- `playerSeason(nick, divisions, comps, pergame)` — per player: team spells,
  divisions, per-mode record, per-map record, hero pool.
- `efficiencyRatings(...)` with `effGroupOf` — the Eff z-score, computed over the
  player's whole division cohort exactly as the Players tab computes it.
- `mergePlayerStats(...)` — stat merge across a player's teams.
- `playerRate(wins, games, floor)` — the floors.

No win rate, record or z-score is implemented a second time. An Eff is a
comparison, so it cannot be computed for one player alone; the cohort is built
from the division, not from the trialist pool.

### The search index

A flat array built once at generation time, one entry per player:

```json
{"nick": "Pixels99", "game": "pixels", "role": "Support",
 "region": "EMEA", "tier": "Expert", "div": "S9 EMEA Expert Central",
 "team": "FXHND", "maps": 64, "last": "2026-08-10"}
```

Matching is case-insensitive substring against `nick` **or** `game`, across all
regions at once. Results display both names, so `pix` returns
`Pixels99 · "pixels" · Support · EMEA Expert · 64 maps`.

A player appearing in several divisions (a regular season and its playoffs, or a
mid-season move) collapses to **one** search entry: `maps` is the sum across all
of them, and `team` / `role` / `region` / `tier` / `div` / `last` come from the
division they most recently played in. The search index is for *finding* a
player; their full multi-division chronology comes from `playerSeason()` at
render time and is not duplicated here.

An empty result set renders "No league player matches *<query>* under either
name" — not a blank list. This is the expected outcome for roughly a third of any
real shortlist.

### The trialist pool

The pool is the tool's one piece of state: an ordered list of nicks, persisted to
`localStorage` so it survives closing the file and regenerating it.

- **Add** — click a search result. Already-pooled players show as pooled in the
  results rather than adding twice.
- **Remove** — an `×` on the player's column header, and an `×` in a compact pool
  list above the tables so the pool is manageable without hunting across tables.
- **Clear pool** — one button, behind a confirm.

The pool is stored, and the tables are derived from it on every render. Nothing
else is persisted.

### Rendering: one table per role

Up to four tables — **Tank**, **Damage**, **Support**, and **Unassigned** for
players FACEIT recorded no role for — each rendered only when the pool puts
someone in it. In practice Unassigned is near-always absent: 63 of 44 150 game
rows carry a null or `'None'` role. Columns are players; rows are axes.

Placement: a player's dominant role decides their table; a second role played on
>=10% of their maps places them in that table as well, with a badge showing the
split (`Damage 60 · Tank 7`).

Shared rows, in order: team and division (with region and tier), last played,
maps, map win rate, elo, Eff (naming its peer group), K/D.

Role-specific rows, so no table is half empty:

| Table | Extra rows |
| --- | --- |
| Tank | mitigation/map, damage/map |
| Damage | damage/map, elims/map |
| Support | healing/map, damage/map |

Then per-mode win rates (5 modes, n>=5), per-map win rates behind a toggle
(n>=3), and hero pool last — shown only where captures exist and labelled as thin
evidence.

Every rate prints its `n` beside it. Below-floor cells are an em dash whose
`title` gives the floor and the sample.

## Error handling

| Situation | Behaviour |
| --- | --- |
| Search matches nothing | Explicit "no player under either name" message naming the query |
| Pooled player absent from the payload (regenerated with narrower filters) | Column renders with the name and a "not in this build's divisions" note; stays in the pool so a rebuild restores it |
| Player has no stat rows (all games zeroed by hazard A) | Stat rows show em dashes; maps and win rate still render |
| A pooled player has no role at all (`role` null/`'None'`) | Placed in an "Unassigned" table rather than dropped |
| `localStorage` unavailable | Pool degrades to session-only; a note says so |
| Empty pool | The page shows the search bar and a short "search for a player to begin" |

## Testing

Python (`pytest`):

- `build_dashboard_data` returns a payload identical to what `export_html`
  inlines, for the same arguments — the anti-drift guard.
- Search index carries both `nick` and `game`, and covers every region present.
- Role bucketing: single-role player lands in one table; the >=10% second role
  lands in two; a null-role player lands in Unassigned.
- The generated file is self-contained (no external references) and is written to
  the requested path.
- `--season` / `--region` / `--tier` narrow the index as `export` does.

JavaScript:

- `node --check` over the generated page's script. This repo's failure mode for a
  JS slip is a **completely blank page**, so this guard is not optional.

## Out of scope

Blizzard/ranked integration, a composite ranking score, per-game role purity,
and any publication of this page. The candidate-file idea explored during
brainstorming was dropped in favour of the search bar and pool.

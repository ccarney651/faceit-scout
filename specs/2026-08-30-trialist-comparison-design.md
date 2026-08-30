# Trialist comparison — design

**Date:** 2026-08-30
**Status:** design approved in conversation; spec awaiting operator review

## Goal

A local-only tool for judging trial candidates against each other. Search the
league's players by either name they go by, add them to a persistent trialist
pool, and read them as sortable rows in **separate tables per role**.

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
| Per-game role purity | **Yes** — corrected during implementation | The design assumed this needed a payload addition. It does not: `export.py:457` already ships `role` on every per-game roster entry, so the true split is computable. `teams[].roster[]`'s rollup is not used at all — see "Counting" below. |

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
enforce (the floors come from pure.js; see "Rendering" for the exact values).

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
rows carry a null or `'None'` role.

**Players are rows; metrics are columns.** The first build made players columns
and it was wrong: a fourth candidate pushed the table off-screen, and comparing
across a horizontal scrollbar is exactly what a comparison tool must not ask for.
Reading down a column is the whole job. Every header sorts (same column toggles
direction, a new column starts descending, missing values sort last in **both**
directions — a player under the Eff floor has not earned the top of the list),
and clicking a player expands a detail row carrying the modes, maps, hero pool
and team spells that are too long to sit in the table.

Placement: a player's dominant role decides their table; a second role played on
>=10% of their maps places them in that table as well, with a badge showing the
split (`Damage 60 · Tank 7`).

Columns, in order: player (with in-game name), team, division, maps, win %,
**team %**, **vs team**, elo, Eff, K/D, and one role-appropriate stat —
mitigation/map for Tank, damage/map for Damage, healing/map for Support.

### Splitting the DPS seats, by hand

The two DPS seats (Hitscan / Flex DPS) are assigned **manually**, with the choice
persisted per browser. Inferring them needs hero attribution, which reaches 128
players in the whole dataset — nowhere near enough to bucket a trialist by, and
`subroles.py` itself calls hero→seat "genuinely fuzzy at the edges".

`tablesWithSeats()` applies the seat by replacing `Damage` in the player's table
list and touching nothing else, so a flex player keeps the tank table their own
maps earned, and a stale seat on someone who has since changed role is ignored.
Unassigned players stay under plain `Damage`.

It is a **grouping, not a recomputation**. Eff's cohort is division-wide;
labels covering only the pool cannot build one, so no Eff moves when a seat is
set. The peer group beside each Eff remains the real one — which is already a
seat for the minority of players captures placed in one.

### Normalising for team quality

Measured across 1016 players with 10+ maps: a player's win rate is **82%**
explained by which team they were on (r=0.90); Eff is only **22%** (r=0.47).
Sorting candidates by win rate is close to sorting them by who had the best
team, so the table carries the team's own rate and the difference beside it.

Two normalisations were measured and **rejected**:

- **Strength of schedule.** Mean-opponent win rate spans only 47–57% within a
  division while team win rates span 35–96%. It is a round robin; everyone plays
  everyone. Adjusting for it would add noise, not signal.
- **Team-adjusted Eff** (Eff minus the player's own team mean). It removes the
  residual 22% and works for full-timers, but it asks "better than your
  teammates?" rather than "how good?", penalising a strong player on a strong
  team. Rejected as a headline number; Eff is left absolute.

### Weighting Eff by sample size

Eff is a mean of z-scores of per-**map** averages, so a short season is not only
less reliable — it is *wider*. Measured across 1123 players:

| maps | players | mean Eff | SD of Eff | share with \|Eff\|>1 |
|---|---|---|---|---|
| 5–14 | 199 | -0.117 | 0.679 | **12.6%** |
| 15–29 | 250 | -0.092 | 0.530 | 5.2% |
| 30–49 | 382 | +0.050 | 0.446 | 3.7% |
| 50+ | 292 | +0.093 | 0.356 | **1.0%** |

Note the means: low-sample Eff is **not** systematically higher —
`corr(maps, Eff)` is **+0.165**, i.e. faintly the other way. What low sample does
is widen the distribution, so a descending sort fills its top with whoever played
least. That is the thing worth fixing.

The `Eff·n` column applies the standard regression-to-the-mean shrink,
`eff × n/(n+k)`. Fitting observed variance = skill + noise/n gives skill 0.062
and noise 3.64, implying k=59 — strong enough to flatten nearly everyone. **k=15
is used instead**, because it already does the whole job: styxywhixy's +0.71 over
8 maps falls from 1st to 4th at k=15 and is still 4th at k=30 and k=59. Past 15
the ordering stops changing and only the numbers compress.

The shrink only scales toward zero: a sign never flips, and an Eff that was
absent stays absent. Raw Eff keeps its own column, so nothing is hidden — the
table just stops *ranking* on the noisier of the two.

**Known thinness this does not address:** the shrink weights the player's own
sample, not the size of the cohort they were scored against. `Javi44`'s +0.91 is
computed against **5** peers (the floor is 4), which is its own kind of thin.

`vs team` is honest about its own limit: **27% of players started every one of
their team's maps**, and for them the difference is *structurally* zero. Those
cells render a faint `0` titled "started every map — nothing to diverge from",
not a bold zero that looks like a measurement.

Then per-mode win rates, per-map win rates behind a toggle, and hero pool last —
shown only where captures exist and labelled as thin evidence. The floors are
`PLAYER_MODE_MIN` / `PLAYER_MAP_MIN` / `PLAYER_HERO_MIN` read from pure.js, which
are **5 / 5 / 3** — this document said "n>=3 per map" before implementation;
pure.js is the authority and it says 5.

Every rate prints its `n` beside it. Below-floor cells are an em dash whose
`title` gives the floor and the sample.

### Counting: never from `teams[].roster[]`

Maps and roles are counted from the per-game rosters, across `matches` **and**
`playoffs`. The `teams[].roster[]` rollup is per championship and playoffs are
their own championship, so its `games` silently stops at the group stage: it puts
Warglabidoo at 55 maps when he played 67. The roster is read only for the two
things per-game entries do not carry — the in-game name and elo.

### The flex caveat, and why the numbers are still shown

Stats and Eff are rolled up per player per division with **no role split**. For a
player's dominant role that is a fair label; in their *second* table it is not —
Warglabidoo's 7 Tank maps carry the averages of his 60 Damage ones, and his Eff
peer group is still Damage. Hiding the numbers would be worse (they are the only
ones there are), so instead every affected cell is tagged `all roles`, the column
header says `second role · 7 of 67 maps`, and the table carries a banner saying
so in words.

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

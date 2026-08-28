# OWDB — backlog

Compiled 2026-08-01; updated 2026-08-27 (end of Season 9 — newest section last). Everything the
project is tracking but is not (yet) a dated plan/design spec. Items move out
of here into `specs/<date>-<topic>-*` docs when they get scoped for
implementation.

Priority levels:
- **P1** — should be next; closes a known data gap or a directly-asked-for fix.
- **P2** — high-value but needs scoping first (owns a design doc).
- **P3** — idea-level; fun or future, not promised to anyone.

## Recently shipped — do not re-plan

The dated specs in this directory all correspond to merged work, verified live
on owdb.io 2026-08-01. Treat them as historical records, not pending work:

- **Swap-trigger baseline subtraction** (`owdb/scout.py::aggregate_swaps`,
  2026-08-01). Was a P1 known gap below; audit found it already had a *frontend*
  workaround (`SWAP_NOISE` in `_dashboard.py`, matchup-based, untested). Moved
  the real fix into the tested core — a candidate trigger hero must now clear
  its own baseline presence rate (all observations, not just swap moments), not
  just the >=half-occurrences threshold — and deleted the JS heuristic it
  replaces. Test: `test_swap_trigger_ignores_enemy_heroes_present_all_game`.

- **Unlock NA** (`specs/2026-07-30-unlock-na-design.md`) — live: region switcher
  shows EMEA + NA, NA divisions rendered, qualified `division` labels.
- **Overview/nav redesign** (`specs/2026-07-31-overview-ia-redesign-{design,plan}.md`)
  — live: 5-tab nav, hero orientation strip, Overview trimmed, Playoffs folded
  into Matches as a 3-mode toggle, Draft simulator relegated to Scout a team.
- **Click-to-codes** (`specs/2026-07-31-click-to-codes-{design,plan}.md`) — live:
  evidence rows across all 8 Scout-page sites resolve to replay codes
  (`codeslink`/`codespop` in the deployed page).

Shipped and verified live since the 2026-08-01 audit (all six carry tests; the
2026-08-07 audit re-verified them in the deployed `docs/index.html`):

- **Players → By seat grid layout fix** (`1ae09bb`, 2026-08-01) — was "in
  flight" below; exported long ago.
- **Capture onboarding** (`c104e86`, 2026-08-04) — guided first-capture tour
  (league + scrim apps), auto-calibrate confidence preview that only commits on
  "Use these boxes", contributor impact card above the scout leaderboard, WIP
  badges on the experimental OCR reads. These are exactly the three friction
  fixes roadmap priority 1 named. Tests: `test_capture_onboarding.py` +
  capture-app syntax guard.
- **Capture recommendations** (`93b0496`, 2026-08-04) — Overview panel ranking
  maps by unseen league minutes (games × per-mode length estimate), withheld
  when nothing is under-covered. Pure `mapCoverage()` + tests. Roadmap
  priority 4, shipped ahead of 2 and 3.
- **Playoff bracket crawl + layout** (`61e3552`, 2026-08-06) — a playoff
  championship's keyless crawl seeds from the sibling regular-season division's
  teams (`_related_division_teams`), so bracket matches are discoverable from
  the first run; bracket columns keyed by (group, round) via pure
  `playoffStageKey` (lower bracket + grand final land correctly).
- **Playoff match pages + scout CTA** (`a5c47ef`, 2026-08-06) — finished
  bracket entries are full match objects, so a scouted playoff game gets the
  same match page as a regular-season one; match detail pages carry a capture
  banner for their own live unscouted codes; finished playoff matches join the
  Played tab tagged.
- **Draft-sim explainability** (`6a401cc`, spec
  `2026-08-05-draft-sim-explainable-{design,plan}.md`) — every auto map/ban
  suggestion carries a plain-language "why" plus replay-code evidence; weak
  samples are labelled "a hint, not a pattern"; decision helpers moved to the
  tested pure layer.
- **Admin capture panel** (`6a4c61a`, 2026-08-06) — worker endpoints
  `/admin/claims` + `/admin/contributor`, gated server-side by `ADMIN_IDS`;
  the capture app shows live scout claims and per-contributor submitted-map
  detail.

---

## Current backlog (pre-existing)

### P1 — Known gaps (FEATURES.md §5)

- **"Teach it a miss" does not work — root cause still unknown.** Reported by
  the operator on 2026-08-13 and re-confirmed in-game on 2026-08-14 *after* a
  fix that turned out to be incomplete. Deprioritised by the operator ("I don't
  care about hero correction"), so this is a record, not a queued task.

  **What was fixed and is not the cause:** `#refpanel` sits inside
  `<details id="herocard">`, which starts collapsed, and `fixReads()` populated
  it without opening the section — so the button looked dead. Both pages now
  open it. That was a genuine bug and it is gone, but it was not the operator's
  symptom.

  **What is verified working**, so the search can skip it: `learnCrop()` returns
  a 3072-byte crop, `addRef()` stores the record in IndexedDB, the "N learned"
  counter increments, and the panel renders ten hero dropdowns. All checked in a
  real browser.

  **So the fault is downstream of storing a ref** — most likely that a learned
  template does not actually beat the built-in one on the next read. Start at
  `bestMatch()`/`matchCrop()` in `docs/capture/engine/refs.js` and at how
  `LOCAL_REFS`/`REFS` are ordered and scored, not at the UI. Note this cannot be
  reproduced headlessly: a synthetic frame teaches nothing meaningful, so it
  needs a live frame and the operator.

- **Map-name verification is stubbed.** The OCR hook returns `None`, so map
  mismatch reads "not checked". Open question: is the map name reliably on the
  observer HUD at all? If not, close as impossible rather than fake it. Not a
  desk task — needs a live in-client HUD check, not something resolvable by
  reading code.
- **Ref library live-frame validation is ongoing.** 88/104 hero+team refs have
  never faced a live frame. Not a code task — `refs coverage` tracks it and it
  shrinks with every capture. Keep `doctor`/`coverage` surfacing it.

### P2 — Deferred, explicitly out-of-scope in prior specs

- **League-wide click-to-codes.** The click-to-codes spec scoped itself to the
  8 evidence sites on Scout a team; League meta and Overview aggregates are
  league-wide and were deliberately excluded. Do the larger, less-targeted
  versions if asked for.

  **Resolved 2026-08-09.** Every replay-code chip (`rcChip`) on the dashboard
  now jumps into the capture tool with that code pre-loaded (`capture/?code=…`,
  `109acf6`; the tool auto-copies it, so pasting into OW2 → Watch still works),
  and every team-name link — standings, power rankings, match cards, match
  detail, playoff sides/projections, funnel chips, scout roster header,
  leaderboard — gains a small capture icon (`capBtn`) that opens the capture
  tool pre-filtered to that team (`capture/?team=…&division=REGION Tier`).
  Team names still click to Scout: the delegated `[data-scout]` handler ignores
  the capture icon's `<a>`. Verified by a Node runtime harness that boots the
  real assembled JS plus the `node --check` gate and the full pytest suite.
- **Aggressive capture-funnel callout.** "14 teams have zero captures" style
  coverage-gap nudge on Overview was deferred in the nav redesign; the
  orientation strip CTA was the agreed first step, and it's shipped.
- **`--external-data` page splitting.** Seam exists (sibling `data.json`,
  future access-gating). Spec says revisit only if page weight moves
  materially (~950 KB on the wire today, gzipped).
- **NA Advanced seeding.** One line in `matches.txt` whenever wanted; triggers
  a ~300-match rate-limited crawl.

### P3 — Future scope, already noted in the repo

- **Access gating / contribute-or-pay threshold.** CLAUDE.md flags the
  `--external-data` seam and FEATURES.md references "the future contribute-or-
  pay threshold" using the same league-wide leaderboard count. Not designed.
- **`#div=<id>` deep link.** Deferred in the unlock-NA spec.

### P3 — Scrim tracker (roadmap item)

The user's product-defining idea — *"infinitely more potential overall"* than
the FACEIT lens alone. Seed: SPEC §0's scrims pipeline (no FACEIT match →
`scrims` table → `map_instances.source_type='scrim'` → `owdb capture --scrim`
→ comp scouting for private games). The capture side is what exists; everything
past capture — tracking, dashboard, scrim-vs-scrim comparison — is open. Captured
as a roadmap item only, per user: *"if there's no detail there then just leave it
as a roadmap item."* Needs its own design doc before any implementation.

---

## Added 2026-08-01 — owscouter.com parity + product ideas

Audit note (2026-08-01): the codebase-side claims below (what data we already
store, what's already shipped) were re-verified directly against schema/tests
and hold up. The owscouter.com feature claims (MPI, scoreboard modal, map
drawer) could not be independently re-checked — the site renders client-side
and a plain fetch returns an empty shell — so they're carried forward on trust
in the original agent's live-browser audit, not re-confirmed here.

Sourced from a full audit of owscouter.com ("FACEIT Analytics & Insights").
The audit's headline: owscouter is FACEIT-data-only analytics; its two data
limits are exactly what OWDB already solves (it cannot get hero picks/comps,
and it cannot attribute bans). Parity items below close its *analytics* surface;
they are derivable from data we already store (`round_players` elo/stats,
`games` per-map scores, `matches` results) — no new collection needed.

### P2 — Power rankings

Derived from stored match results: Series Elo (K=32) + Map Elo (K=12),
weekly ratings, sparkline trajectories, ordered standings. Pure data math,
fits the testable-core rule. User verdict: *"99% of OW players don't care about
elo, but power rankings could be fun"* — frame it as rankings, not elo. Must
follow the sample-honesty rules (show `n`, weak evidence weakened).

### P2 — Team Compare

Two teams side-by-side on the dashboard: radar-style comparison across
dimensions, map-pick/ban views for each, perspective toggle. Rated the
stand-out parity item — **"especially with my hero tracking"**: because we have
captured comps, our compare can be deeper than owscouter's (which is FACEIT
stats only). Natural fit: an extension of the Scout a team page / draft
simulator rather than a new surface.

**Resolved 2026-08-08.** Shipped as a pseudo-tab reached via `#compare=<A>|<B>`
(or the Scout page's "Compare…" button; nav highlights Teams). Radar across
**8 mixed axes** — map win rate, map pool breadth, ban pressure, pick agency,
Team Eff (mean of qualified players' `eff.eff`, ≥3 peers) + 3 capture-only
dimensions (comp diversity, hero pool breadth, adaptability) that drop or dim
when a side has no captures. Same-division only; perspective toggle flips the
"you"/"them" tags and re-reads ban tables per team; per-team maps/bans/comps/
top-by-Eff cards + a head-to-head match list. Pure layer:
`compareAxes` / `radarPoints` / `COMPARE_CAPS` / `COMPARE_FLOORS` /
`HERO_POOL_MIN_PICK` in `faceit_sync/dashboard/pure.js`; routing + rendering
in `app.js` (`renderCompare`, `gotoCompare`, `COMPARE_A/B/PERSP`); radar CSS in
`head.html`; tests in `tests/test_dashboard_logic.py`. Design + plan:
`specs/2026-08-08-team-compare-{design,plan}.md`.

**Follow-up polish, same day.** Post-ship review found the per-team Maps table
wasn't actually grouping — `table()`'s group header only collapses *consecutive*
same-group rows, but the rows were sorted by games-played, so every map got its
own header. Fixed by sorting with the existing `mapCmp`/`byMode` convention
(already used on the Team detail page) before handing rows to `table()`. Also
found "Map pool breadth" saturating at 100 for most teams — its cap was a
hardcoded 10 maps, well under a real season's ~13, so any active team maxed it
out with no differentiation left. `compareAxes` now takes an optional `poolCap`
arg; `renderCompare` derives it from the division's actual distinct maps played
and falls back to the old constant only if unset (existing tests, which don't
pass one, are unaffected). Every axis got an `AXIS_HELP` hover explanation (axis
table `<td>` and radar spoke labels both), since none existed before. The
team-picker header was rebuilt from two bare `<select>`s into a proper vs-layout
(avatars, bold names, centered VS + swap) carrying a team-A/team-B color code
(accent/support) through the header dot, axis-table columns, radar polygons and
a top accent bar on each team card — one consistent visual thread instead of
color meaning only lived in the chart. Radar/axis-table proportions tuned twice
on user feedback (table columns in `head.html`: `.compare-radar-table`,
`.compare-radar-svg`, `.cmp-*`).

### P2 — Player efficiency rating (PER-style), role-relative

**Resolved 2026-08-08.** Shipped as the leaderboard's **Eff** column (Players →
Leaderboard). Per-map stat averages (dmg/heal/mit/kd) z-scored against the
division's other players in the same competitive role and averaged across the
stats that vary within the role; the component z's are shown under the composite
(d/h/m/k); nothing renders below the 5-map sample floor or inside a cohort under
4 peers; peer group = competitive role when scouted, else base role; the
team-strength confound is disclosed in the leaderboard footnote. Pure layer:
`efficiencyRatings` / `effZ` / `EFF_GROUP_MIN` in `faceit_sync/dashboard/pure.js`
(`rankPlayers` gained an `eff` key); peer-group assignment `effGroupOf` in
`app.js`; tests in `tests/test_dashboard_logic.py`. Vocabulary landed alongside:
the Players-tab toggle reads "By role" and user-facing copy says "same role",
never "seat" / "subrole". The timeline (elo/stat trajectory over the season)
remains a future, bundled item.

### P3 — Per-map scoreboard context

Map cards gain per-player stats **vs division average** and **vs their own
season average** (owscouter's scoreboard modal). All data exists in
`round_players`; it's compute + UI. "Kinda cool, not super important" — bundle
with the player index work if either gets scoped.

**Resolved 2026-08-24** by the player pages, which are the "player index work"
this entry was waiting on. `#player=<nick>` carries the per-division stat rows
against same-role peers (reusing `efficiencyRatings`' cohort), per-map and
per-mode records beside the team's own rate, and a per-map stat line on every
recent game. Design + plan:
`specs/2026-08-24-player-pages-{design,plan}.md`.

Two things were deliberately left out, with the measurement rather than a
shrug behind each:

- **Per-game elo trend.** `round_players.elo_snapshot` exists per game but is
  exported only as the player's latest value. Shipping it per game costs
  **+473 KB raw** on a 9.1 MB page for one trend line, and season form can
  already be sparklined from the per-game stats that do ship. Revisit if the
  page ever earns a form chart.
- **Career / multi-season pages.** The payload is one season by construction
  (CI exports `--season s9`), so this needs a decision about what a
  cross-season page compares, not just code.

One accepted limitation: a player is keyed by nickname, so someone who renames
mid-season becomes two pages. FACEIT publishes no nickname history, so the page
says so rather than being quietly wrong.

### P3 — Map drawer (reimagine, do not copy)

A draw-on-map strategy whiteboard is a fun idea but owscouter owns the shape
of it; do not clone it. If it ever ships, it should be OWDB's own take —
the obvious spin is tying markers to *real captured data* (mark a position,
attach the comps/comps that were run there, export a prep image) rather than a
blank whiteboard. Idea-level until that angle is defined.

---

## Added 2026-08-07 — audit of the Aug 4–6 wave

Findings from auditing the six shipped features above (full suite + mypy clean,
all verified live). Ordered.

### P2 — FEATURES.md is six features behind

**Resolved 2026-08-08.** FEATURES.md now documents all six: capture
recommendations panel + contributor impact card (§1.2 Overview), onboarding
tour / auto-calibrate preview / WIP badges (§2.3), playoff match pages + scout
CTA + Played-tab merge (§1.2 Matches), draft-sim explainers + `#simfull` (§1.2
+ §3), and the admin capture panel (its own section). CLAUDE.md's roadmap was
reworded in the same pass: priorities 1 and 4 read "delivered; iterate on
adoption". The Eff rating landed in the Players section alongside.

### P2 — Capture recommendations ignore playoff matches

`mapCoverage(D().matches, …)` reads regular-season games only, while
`scoutQueue`/`capSampleAll`/`MATCH_BY_ID` all union in `d.playoffs` and the
code itself calls a live playoff code "the freshest, highest-value capture
target on the site". Either feed playoffs into coverage too (one-line change,
matches the established pattern) or write down why they're excluded.

**Resolved 2026-08-08** — fed playoffs in. The Overview call site now passes
`(D().matches||[]).concat(D().playoffs||[])` to `mapCoverage`, the same union
`drawPlayed` uses; a captured playoff game still counts as covered, and a live
playoff code is what the "Scout →" link prefers. Tests:
`test_map_coverage_counts_finished_playoff_games_as_league_play` /
`test_map_coverage_counts_a_captured_playoff_game`. Combined views remain
playoff-free (no view merges `playoffs` anywhere, pre-existing).

### P2 — Consolidate the two scrims implementations

**Resolved 2026-08-08.** The audit found there was only ever one live viewer:
`docs/scrims.html` reads the `owscout-capture` IndexedDB from the shared origin;
the dashboard's "Scrims tab" was a phantom — a dead `HERO_BY_GUID` stub in
`app.js` (never read) plus a `guid` field in the `heroes`/`roster` export
payloads whose only documented consumer was that stub (`scrims.html` resolves
guids via `capture/refs.json` instead). Both were removed, and the docs
(CLAUDE.md diagram + fact 5, FEATURES.md, `_dashboard.py` docstring, capture
tour copy, this backlog) now describe the one real path: the Scrims page via
the top-bar League/Scrims toggle. The dashboard never touches the capture
IndexedDB — keep it that way.

### P2 — Dashboard modularization before the next major feature

CLAUDE.md convention: `_dashboard.py` is one ~3,700-line template string and
grew ~500 lines in a week (draft sim, playoffs, capture recs). The agreed
shape is a concatenation build step, no framework. Cheaper now than after the
next feature lands.

**Resolved 2026-08-08.** `HTML_TEMPLATE` is now assembled at import from four
static parts under `faceit_sync/dashboard/` (`head.html`, `pure.js`, `app.js`,
`boot.js`) by `_dashboard.py` — plain concatenation, no framework. New pure,
testable logic lands in `pure.js` (above `bootApp`); new page shell/CSS in
`head.html`; rendering in `app.js`; data delivery in `boot.js`. The parts ship
as package data (pyproject.toml). If `app.js` outgrows itself, split it the
same way the pure layer was hoisted.

### P3 — Playoff sibling pairing is a LIKE prefix

`_related_division_teams` matches `name LIKE base || '%'`; a future division
whose base name is a prefix of another's (e.g. "Master" vs "Master 2") would
cross-seed the crawl. Anchor the pairing (exact stage-suffix match) when a
second real pairing case appears.

### P3 — `MODE_MINUTES` are hardcoded guesses

Capture-recs playtime weights (Control 14, Escort/Hybrid 20, Push/Flashpoint
11) are estimates; only the proportions matter today. If the stats feed
exposes real game durations, derive them.

### P3 — Retire the dead native GUI

**Resolved 2026-08-08.** `owdb/gui.py`, `owdb_app.py`, the PyInstaller
specs and `Scout app.cmd` were deleted; the `owdb gui` subcommand, the
`owdb-app` console script and the `owdb.gui` mypy override are gone. Its
tested pure helpers were relocated to `owdb/firstrun.py` (tests moved to
`tests/test_firstrun.py`) rather than thrown away.

### P3 — OWDB rebrand mechanics

Domain is registered (owdb.io, 2026-08-09) and the site/capture/upload-worker all
point at it; a rename pass over user-visible strings (site title, capture app,
worker messages, docs) is still outstanding.

## Added 2026-08-10

### P2 — "Most wanted" codes should follow the selected division

Overview's "Most wanted" card (`app.js` `leagueQueue()` / `scoutQueue`,
~line 1214) lists live replay codes league-wide, ignoring the division switcher
the user has active. A scout working one division sees codes from every other
division mixed in. Scope it to the currently selected division (like the rest of
Overview already is), keeping the league-wide count as a separate signal.

### P3 — Draft simulator bugs (user report)

**Resolved 2026-08-10.** Reported while testing the draft simulator (known beta):

- **Top bar doesn't update "first pick & ban".** After simulating, the header
  still shows a stale team (user: "still says AR9 a different team") — the
  pick/ban attribution row isn't re-rendered. Root cause: the "First pick &
  ban" and "Format" (Bo3/5/7) buttons were built once into the static control
  bar and never rebuilt, so their cached team-name text and selected-highlight
  went stale on any team/first-pick/format change. Fixed by hoisting both into
  `renderFB()`/`renderBO()` closures called on every `draw()` (`app.js`
  `renderSim`), not just at initial mount.
- **Ban suggestion ignores role constraints.** The sim recommended the 2nd team
  ban Mauga when the 1st team should have banned D.Va — "can't ban the same
  role", so the two bans can't both be tanks. Fixed: once the first team's ban
  is resolved, `node()` adds every hero sharing its role (via the new
  `HEROES_BY_ROLE` lookup) to the second team's illegal set before resolving
  their ban — enforced for both the auto-suggestion and the manual hero picker.
- **Ban suggestion is map-agnostic.** It recommends the overall most-banned hero
  rather than the specific map's ban pattern ("obviously no one bans Mauga in
  Dorado"). Fixed: `banSuggest` (`pure.js`) now ranks by on-map ban count first
  and only falls back to the overall count as a tiebreaker (previously
  `onMap*2+all`, which let a big overall total outrank real on-map evidence).

`specs/2026-08-05-draft-sim-explainable-*.md` is the design reference for the
current (explainable) draft sim.

---

## Added 2026-08-27 — end of Season 9

S9 finished 2026-08-17. **Season 10 starts Monday 7 September 2026, 01:00
BST.** Full analysis and the cutover runbook live in
`specs/2026-08-10-season10-cutover-design.md` §6; the readiness work that
executed off it is `specs/2026-08-27-season10-readiness-plan.md`. Do not
re-derive any of this — those documents carry the evidence.

### Shipped 2026-08-27 — do not re-plan

- **Season fallback + season label.** A pinned season with no data used to write
  a 0-byte `index.html` and exit 1, which under CI's `bash -e` failed the whole
  job and froze the site silently. It now falls back to the newest season with
  data, so the pin can be flipped at any time and the site switches itself over
  on the first ingested S10 match. The page labels the season it actually
  rendered, so a fallback is visible rather than silent.
- **Season-state note.** Between seasons there is nothing to capture and the
  hero slot rendered empty, which reads as a broken site. It now explains the
  wipe, and names the next season's start date until that date passes.
- **SA and OCE regions.** Inert until such a championship exists. `--region` now
  matches region names exactly rather than by first letter, and the capture
  feed's separate `REGIONS` copy is test-pinned to the exporter's.
- **Season 9 frozen** at `docs/s9/`, indexed by `docs/archive.html`, linked from
  every page footer. Built from CI's DB, never the local one.
- **IndexedDB rename closed as won't-do.** `owscout-capture` is kept
  permanently; `AGENTS.md` records a decision, not a deadline.
- **Relegation ingest: skipped**, operator's decision. The window has closed
  regardless — 0 of the 4,456 coded S9 games finished after the 2026-08-18 wipe,
  so nothing in Season 9 is replayable any more.

### P1 — Cross-season player careers (design first)

**Wanted, and worth building BEFORE the cutover rather than after** — the one
item on this list whose value decays if it lands late. Player pages aggregate
whatever divisions are in the payload, so the moment the site becomes S10 every
player restarts from nothing and their S9 record exists only inside the frozen
archive, at a different URL. A new season is exactly when people look up who
moved where.

Needs a **design document, not a plan**: the honest implementation cuts against
the season-scoped export, and the obvious version (ship both seasons inline)
roughly doubles page weight — the same `--external-data` question the
Intermediate decision defers. Decide the two together.

### P2 — Operator-gated, around 7 September

- **S10 seed room URLs.** One FACEIT match room per division, collected by hand
  once rooms exist. There is no automated path: FACEIT's keyless
  `championships/v1/championships` refuses offset enumeration (verified
  2026-08-27). Seed NA Advanced, SA Master and OCE Master alongside the existing
  divisions.
- **The Intermediate call, in week 1 of S10.** Deferred from the boundary
  deliberately: Intermediate is new, nobody knows its team count, and at
  Advanced's size it adds ~2.6 MB/region while at Open's it adds ~6.1 MB — the
  difference between a 17 MB and a 24 MB page. Week 1 is when it becomes
  countable and there is still almost nothing to back-crawl.
- **Register the S10 code-wipe date** when the season-start patch lands
  (`_SEED_WIPES` only).
- **The cutover commit itself** — three lines, written out verbatim in the
  design's §6.4 group C, plus a human `wrangler deploy`. Only the export line is
  protected by the fallback; the merge dir and `CURRENT_SEASON` must move with
  it or Season 9 comps attach to Season 10 teams by team id.

### Shipped 2026-08-27 — `team_rosters` is scoped to the active season

Was a P2 open question here and in the cutover design §6.6. The feed now builds
`team_rosters` from the newest season that has data only, sharing
`faceit_sync.models.newest_season` with the exporter rather than parsing the
season a second time. The operator's call, and the reason it is the right one:
you only scrim teams that are active, so matching against last season's squad
writes a team that no longer plays into a private scrim log — worse than not
identifying at all.

Inert on today's database (S9 is the only season, so the emitted `data.json` is
byte-identical, verified by diffing the built feed rather than assumed) and
flips itself on the first ingested S10 match. `tools/roster_match_eval.py`
applies the same filter, so re-running it at cutover measures the pool that
actually ships. Worth re-running in week 1 of S10 in particular: the pool is
then only the teams that have played.

### P3 — `FACEIT_API_KEY`-backed championship discovery

Every season, seeding costs a manual hunt for one room URL per division. The
Data API's `organizers/{id}/championships` would list them directly; organizer
id `f0e8a591-08fd-4619-9d59-d97f0571842e`. Worth it only if manual seeding
actually hurts — CI needs no key today, and adding one is a new operational
dependency.

### Decision, not a task — open scrim mode for the off-season?

Both scrim pages ship locked behind `?unlock=scrimbeta`. **Asked and answered
2026-08-27: keep it locked for now**, revisit when phase 2 (opponent
identification / roster search) is complete.

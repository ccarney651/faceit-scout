# OW Scout — backlog

Compiled 2026-08-01; updated 2026-08-07 (post-playoffs audit). Everything the
project is tracking but is not (yet) a dated plan/design spec. Items move out
of here into `specs/<date>-<topic>-*` docs when they get scoped for
implementation.

Priority levels:
- **P1** — should be next; closes a known data gap or a directly-asked-for fix.
- **P2** — high-value but needs scoping first (owns a design doc).
- **P3** — idea-level; fun or future, not promised to anyone.

## Recently shipped — do not re-plan

The dated specs in this directory all correspond to merged work, verified live
on owscout.com 2026-08-01. Treat them as historical records, not pending work:

- **Swap-trigger baseline subtraction** (`owscout/scout.py::aggregate_swaps`,
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
`scrims` table → `map_instances.source_type='scrim'` → `owscout capture --scrim`
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
limits are exactly what OW Scout already solves (it cannot get hero picks/comps,
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

### P3 — Map drawer (reimagine, do not copy)

A draw-on-map strategy whiteboard is a fun idea but owscouter owns the shape
of it; do not clone it. If it ever ships, it should be OW Scout's own take —
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

**Resolved 2026-08-08.** `owscout/gui.py`, `owscout_app.py`, the PyInstaller
specs and `Scout app.cmd` were deleted; the `owscout gui` subcommand, the
`owscout-app` console script and the `owscout.gui` mypy override are gone. Its
tested pure helpers were relocated to `owscout/firstrun.py` (tests moved to
`tests/test_firstrun.py`) rather than thrown away.

### P3 — OWDB rebrand mechanics

Branding decision is made (owdb.gg, per CLAUDE.md) but untracked: register the
domain when closer to shipping, then a rename pass over user-visible strings
(site title, capture app, worker messages, docs).

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

### P2 — Player efficiency rating (PER-style), role-relative

Requested by a league player (boomed/SHKI, Discord, 2026-08-06): a PER-like
composite — damage/healing/mitigation averages + K:D — "role by role, meta
independent, relative to peers". Was P3 as "player performance index +
timeline" (owscouter's MPI); an explicit user request bumps it. All inputs
already sit in `round_players` at FULL league coverage (no capture needed),
and the Players leaderboard's 5-map sample floor is the natural base.

Vocabulary (decided 2026-08-07): user-facing copy calls the five buckets
**"Role"** — the values (Tank / Hitscan / Flex DPS / Main Support / Flex
Support) shown alongside self-disambiguate from the game's three roles, and
it's the word organised players already use. "Seat" never appears in UI
(Players-tab toggle relabelled "By seat" → "By role" 2026-08-07); in prose
that needs it, "competitive role". "Subrole" is off-limits — Blizzard shipped
official in-game Sub-Roles with the perk system — so the internal
`subroles.py` module name now collides with a real game mechanic: harmless
until we surface hero sub-roles, then rename to `seats.py`. Internal code
keeps `seat`/`seat_of` (short, grep-able, users never see it).

Design steers that keep it inside the repo's honesty rules:

- **Rank against peers in the same competitive role** (Tank / Hitscan /
  Flex DPS / Main Support / Flex Support — `subroles.py`), not the game's
  three roles — hero pick within a role swings stat lines more than skill
  does (Mercy vs Zen). Percentile or z-score within role+division is "meta
  independent" for free: a meta shift moves the whole peer group together.
- **Show the components.** The composite is a summary line over the existing
  per-map stats, never a bare opaque number (the repo rule). Components + `n`
  visible; below the sample floor, no rating renders at all.
- Per-map rates, not raw totals (map length confounds raw damage/healing).
- Disclose, don't solve: players on strong teams post better lines (more
  elims, fewer deaths) — the rating doesn't control for team strength.
- boomed's "chances:goals / takes:makes" note — OW's analog is elims:deaths,
  already shipped as K:D. The new value is cross-stat normalization, not
  another ratio.
- Timeline (elo/stat trajectory over the season) stays bundled as before.

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

The authoritative feature reference documents none of: the capture
recommendations panel, the contributor impact card, the onboarding tour /
auto-calibrate preview / WIP badges, playoff match pages + scout CTA + the
Played-tab merge, draft-sim explainers + legend + `#simfull`, or the admin
capture panel. Touch §1.2 (Tabs: Overview, Matches), §3 (scout page / draft
sim), §2.3 (capture onboarding), §2.8 (admin panel). Same pass: CLAUDE.md's
roadmap still describes priorities 1 and 4 as future work though their named
items shipped — reword to "delivered; iterate on adoption".

### P2 — Capture recommendations ignore playoff matches

`mapCoverage(D().matches, …)` reads regular-season games only, while
`scoutQueue`/`capSampleAll`/`MATCH_BY_ID` all union in `d.playoffs` and the
code itself calls a live playoff code "the freshest, highest-value capture
target on the site". Either feed playoffs into coverage too (one-line change,
matches the established pattern) or write down why they're excluded.

### P2 — Consolidate the two scrims implementations

Standalone `docs/scrims.html` vs the dashboard Scrims tab, both reading the
same IndexedDB store. CLAUDE.md flags the consolidation as part of roadmap
priority 2 (ship scrim mode); it has no other tracking home.

### P2 — Dashboard modularization before the next major feature

CLAUDE.md convention: `_dashboard.py` is one ~3,700-line template string and
grew ~500 lines in a week (draft sim, playoffs, capture recs). The agreed
shape is a concatenation build step, no framework. Cheaper now than after the
next feature lands.

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

`owscout/gui.py`, `owscout_app.py`, the PyInstaller specs and `.cmd` launchers
are slated for removal per CLAUDE.md. No one is pointed at them; deleting them
shrinks the repo and the test-import surface.

### P3 — OWDB rebrand mechanics

Branding decision is made (owdb.gg, per CLAUDE.md) but untracked: register the
domain when closer to shipping, then a rename pass over user-visible strings
(site title, capture app, worker messages, docs).

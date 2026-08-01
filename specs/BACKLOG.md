# OW Scout — backlog

Compiled 2026-08-01. Everything the project is tracking but is not (yet) a
dated plan/design spec. Items move out of here into `specs/<date>-<topic>-*`
docs when they get scoped for implementation.

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

## In flight (committed, not yet re-exported to the live site)

- **Players → By seat grid layout fix** (`faceit_sync/_dashboard.py`, commit
  `1ae09bb`, 2026-08-01). `.seatrow` CSS + the By-seat renderer: name/heroes/stats
  in fixed grid columns so rows stop staggering on variable-width content.
  Correction: the prior version of this doc called it "uncommitted" — it's on
  `main`, just ahead of the last CI export (`bced1e4`), so `docs/index.html`
  hasn't picked it up yet. Gate: JS-syntax test + headless-Edge screenshot.

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

### P3 — Player performance index + timeline

Composite per-player score (owscouter calls theirs MPI), radar vs same-role
peers, elo/stats trajectory over the season. Rated "kinda cool, not super
important". Design caution: an opaque composite index fights the repo's
"say what the number rests on" rule — if built, show components + sample floor,
never a bare opaque number.

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

# Overview & navigation redesign — design

**Date:** 2026-07-31
**Status:** approved, ready for implementation

## Goal

Two pieces of peer feedback on the live dashboard, both about first impressions:

- *"its very overwelming for a new viewer... more cleanly organized, with
  important info easy to see and more info clickable if people want"*
- The site's own contribute/capture funnel isn't converting — nobody published
  a capture the day this was raised, even though the callout already exists on
  Overview.

This is a client-side reorganization of `faceit_sync/_dashboard.py`'s
`bootApp` template: trim Overview to non-redundant content, consolidate the
tab bar, and promote the capture CTA to the first thing a visitor sees. No
data, schema, or export changes.

## Background: current structure

`TABS` (`_dashboard.py:1175-1183`) — 7 top-level tabs: Overview, Scout a team,
Players, Draft simulator, League meta, Playoffs, Matches.

`renderOverview()` (`_dashboard.py:1222-1310`) is a flat stack, rendered in
full every time, no collapsing:

1. Coverage tiles (maps played, teams, teams scouted, comps captured)
2. "Prep for a match" team-picker + Scout button
3. "Contribute" callout with a **Capture comps →** button (the existing funnel
   nudge — buried as the 3rd section, not the reason it's underperforming is
   unproven, but it's not prominent)
4. Scout leaderboard (per-contributor maps, if any captures exist)
5. Current ban meta + most-played maps (two cards)
6. Standings table
7. Rosters at a glance (every team's full roster, in a grid)

Sections 5 and 7 are duplicates of content shown elsewhere:

- Section 5 duplicates the **League meta** tab (`renderMeta`), which covers the
  same ban/map data at full depth.
- Section 7 duplicates per-team rosters already shown on **Scout a team**
  ("Current roster" card, `_dashboard.py:1482`) and **Players** (team view,
  `_dashboard.py:2233-2249`) — Overview is a third copy, rendered for every
  team at once, which is the single biggest chunk of vertical density on the
  page.

Hash routing (`_dashboard.py:2816-2898`): `hashFor(id)` special-cases only
`scout` (carries `SCOUT_TEAM`); every other tab is a bare id. `init()` falls
back to `'overview'` for any hash that doesn't match a `TABS` id
(`_dashboard.py:2898`) — so removing a tab id silently drops any bookmarked
link to it unless handled explicitly.

## Scope decisions

| Decision | Choice | Why |
|---|---|---|
| Reach | `_dashboard.py` only | Pure reorganization of already-exported data; nothing new to compute. |
| Orientation | Always-visible strip, not a dismissible modal | Cheap real estate; serves cold traffic *and* doubles as fast navigation for returning visitors. |
| Draft simulator | Moves under Scout a team, beta-labelled | It's a matchup-prep tool, not a destination; explicit user call ("relegate... to a beta tool reachable within scout pages"). |
| Playoffs | Folds into Matches via a toggle | Same schedule/bracket shape as Matches; mostly empty/projected until S9 playoffs post, not worth a dedicated top-level slot. |
| League meta | Stays a separate tab | Different audience (whole-league trends vs. one matchup) despite touching the same ban/map data as the cut Overview cards. |

## Changes

### 1. Orientation strip (new)

Added above the tab content, always rendered (part of the page shell, not
per-tab), one line of framing + two equal-weight CTAs:

```
owdb — FACEIT League scouting, built from real match data + fan-captured comps.
[ Scout a team → ]     [ Contribute a capture → ]
```

- "Scout a team" behaves like the existing Overview launcher: jump to
  `renderScout` (last-used team, or first team in the active division if none
  selected yet).
- "Contribute a capture →" replaces the current Overview "Contribute" card;
  same target (`location.href='capture/'`) as today's `cbtn`
  (`_dashboard.py:1252`).
- Lives in the page shell (near `#title`/`#subtitle`, `_dashboard.py:2826-2853`
  region), not inside `renderOverview`, so it's visible on every tab, not just
  Overview.

### 2. Overview trim

`renderOverview()` keeps: tiles, standings, scout leaderboard (moved after
standings — a trust signal, not orientation info a first-time visitor needs
immediately).

`renderOverview()` drops:

- The "Prep for a match" launcher card and "Contribute" callout — superseded
  by the orientation strip (§1), would otherwise be duplicated.
- The ban-meta / most-played-maps two-card row — duplicates League meta
  wholesale; Overview does not need a preview of a tab one click away.
- "Rosters at a glance" — duplicates Scout a team and Players; cut entirely,
  not shrunk.

Net: Overview goes from 7 stacked sections to 3 (tiles, standings, leaderboard)
plus the shell-level orientation strip.

### 3. Tab consolidation: `TABS` 7 → 5

```js
const TABS=[
 {id:'overview',label:'Overview',render:renderOverview},
 {id:'scout',label:'Scout a team',render:renderScout},
 {id:'players',label:'Players',render:renderPlayers},
 {id:'meta',label:'League meta',render:renderMeta},
 {id:'matches',label:'Matches',render:renderMatches},
];
```

**Playoffs → Matches toggle.** `renderMatches` gains a segment control at the
top: `Regular season | Playoffs`, next to (or replacing) the existing
Upcoming/Played mode toggle already in that function
(`_dashboard.py:2802-2810`, `MATCHES_MODE`). Default segment: Playoffs if the
active division has any `_is_playoff`-attached data (finished or scheduled),
else Regular season. The existing `renderPlayoffs` body (bracket rendering)
becomes a branch inside `renderMatches` rather than its own top-level
`render`.

**Draft simulator → Scout a team.** `renderScoutBody` gains a collapsed
"Draft simulator (beta)" section/button that expands the existing
`renderSim`-derived UI inline, pre-filled with the currently scouted team as
one side. No standalone `sim` tab in `TABS`.

### 4. Hash-routing backward compatibility

Two hash ids stop existing as tab ids but may be bookmarked/shared already
(the Discord screenshots reference this site being actively used):

- `#playoffs` → resolve to the `matches` tab with the Playoffs segment
  selected.
- `#sim` → resolve to the `scout` tab with the draft-simulator section
  expanded (no team to pre-fill from a bare `#sim` hash — none was carried
  before either).

Implementation: in `init()` (`_dashboard.py:2871-2898`), before the final
`TABS.some(...)` fallback, add explicit cases for `start==='playoffs'` and
`start==='sim'` that set the relevant UI state and call `show('matches')` /
`show('scout')` respectively, mirroring the existing `prep=`/`scout=`
handling pattern already in that function.

### 5. Documentation

`FEATURES.md` "### Tabs" section (lines 115-147) lists all 7 tabs with
descriptions. Update to 5 entries: fold the Playoffs description into Matches
(mention the toggle), fold Draft simulator's description into Scout a team
(mention it's a beta section, not a tab), and drop the now-cut Overview
content (ban meta, rosters-at-a-glance) from the Overview description.

## Testing

- **Mandatory after any `_dashboard.py` edit:**
  `pytest tests/test_export.py::test_dashboard_javascript_is_syntactically_valid`
  (`node --check` over the generated script) — the page renders entirely in
  JS, so one syntax error yields a blank page bracket-balance checks won't
  catch.
- New/updated: any existing test asserting `TABS` length or tab ids (check
  `tests/test_dashboard_logic.py`) updated for the 5-tab list.
- New: hash-routing test (or a documented manual check, since routing lives
  inside `bootApp`'s closure) confirming `#playoffs` and `#sim` still resolve
  without hitting the `'overview'` fallback.
- Visual: build a local preview, screenshot with headless Edge
  (`msedge --headless --screenshot=FILE "file:///.../dashboard.html#overview"`)
  — confirm the orientation strip renders, Overview shows 3 sections not 7,
  the nav bar shows 5 tabs, and the Matches tab's Playoffs/Regular-season
  toggle works.
- `pytest` full suite green; `mypy faceit_sync` clean — all the edits here are
  inside `HTML_TEMPLATE`'s JS string literal, which mypy doesn't parse, so this
  should be a no-op check, not a risk area.

## Out of scope

- Any change to what data is captured/exported (`export.py`, `db.py`,
  `models.py` untouched).
- The click-to-codes drill-down feature (separate spec, tracked separately).
- The role/slot vs. player-identity hero-swap-tracking bug (separate fix, not
  a design change).
- A more aggressive capture-funnel treatment (e.g. a live coverage-gap
  callout like "14 teams have zero captures") — deferred; the orientation
  strip's CTA is the agreed first step.
- Visual restyling of the CTA buttons/strip beyond using existing `.card`/
  `.btn` classes — no new design system work.

## Risks

| Risk | Mitigation |
|---|---|
| A bookmarked `#playoffs` or `#sim` link silently lands on Overview instead of the old content | §4 adds explicit redirect handling in `init()`, tested. |
| Cutting Overview's ban/map cards removes the *only* place a first-visit user sees current meta before finding League meta | Acceptable — the orientation strip's "Scout a team" CTA and the standings table are the priorities for a cold visitor; League meta is one tab click away, same as today. |
| Folding Playoffs into Matches makes the bracket harder to find once S9 playoffs actually post and get real traffic | The toggle defaults to Playoffs automatically once playoff data exists (§3), so it surfaces without an extra click at the moment it matters most. |

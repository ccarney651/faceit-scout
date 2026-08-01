# Match detail page — design

**Date:** 2026-08-01
**Status:** approved, ready for implementation

## Goal

Every match currently renders as a fully-expanded card — bans, per-segment
opening comps, and a rosters-toggle for *every* game in the series, stacked
vertically (`matchCard()`, `_dashboard.py:969`). On a Bo5 that's a long
scroll, and it's the only way to see a match: the same card is reused
verbatim in the Matches tab list and in the Scout-a-team sticky rail
(`_dashboard.py:2219`, `:2924`).

Split it in two: a compact "at a glance" row (teams, score, one pip per map)
that's cheap to scan in a list, and a dedicated match detail page — reached
by clicking the row — that shows one map's full data at a time via per-map
tabs, FACEIT-match-room style.

## Background: what's already there

- **Data per game** (`export.py:417-421`, mirrored in `models.Game`): `map`,
  `map_category`, `f1`/`f2` (per-map round score), `winner_faction`,
  `winner_team`, `attacking_first_faction`, `side_picked_by_faction`,
  `demo_code`, `was_restarted`. Bans (`bansOrdered`, `:952`), rosters
  (`rosterHTML`, `:940`), and opening comps (`compRow`/`segOrder`, `:818`/
  `:961`, fed by `DATA.owscout_pergame[matchId:gameNo]`) are all already
  computed — this is a re-layout, not a new data need.
- **Replay codes**: `rcChip` (`:888`) click-to-copy, `wipedTag`/`codeDead`
  (`:896`/`:701`) for post-wipe codes. Reused as-is.
- **`m.id`** is unique **within its division**, not globally — matches live
  in `DIVS[cid].matches` (`export.py`'s per-championship payload), and
  `VIEWS` (`_dashboard.py:631`) combine one or more divisions. There's
  existing precedent for resolving a cross-division link: the `#scout=`/
  `#prep=` hash handlers (`:3008-3026`) search `VIEWS` for the single-division
  view whose `team_names` contains the linked team, then switch
  `CURRENT_VIEW` to it. A match link needs the same move, keyed on match id
  instead of team name.
- **Hash routing**: `hashFor`/`show`/`init` (`:2944-3034`) already special-case
  non-tab hash states (`scout=`, `prep=`) that resolve to the real `scout`
  tab with extra state (`SCOUT_TEAM`, `SCOUT_PREP`) set first. This feature
  adds a third state (`match=<id>` → `MATCH_ID`) that resolves to a new
  pseudo-tab id, `matchdetail`, which isn't a nav button — same asymmetry
  `scout=`/`prep=` already have relative to the real `scout` tab.

## Design

### 1. Compact match card (replaces the top of today's `matchCard`)

One row: team names (win/lose styling unchanged, still individually
click-to-scout via `.tscout`/`data-scout`), series score, Bo/round/group tag,
date, walkover/forfeit tag — this part is close to the existing header row
(`:977-982`), kept as-is. Below it, one **pip per played map** instead of the
full game blocks:

```
Redline   2–1   Vertex Prime          Bo3 · R14 · G2
Aug 1                                  🎥 3/3 scouted
 [King's Row 3–1] [Circuit Royal 2–4] [Ilios —]
```

- Pip = map name + that map's round score (`g.f1`–`g.f2`), colored via the
  existing `wlw`/`wll` (`--good`/`--bad`) convention, anchored to **f1**
  (whichever team the card lists first) — win if `g.winner_faction===
  'faction1'`. Consistent within one card; matches how the header already
  reads left-to-right.
- Per-pip replay-code affordance (per your answer): a small `rcChip` (or
  `wipedTag` if `codeDead(m.finished_at)`) inside the pip. Needs a click-guard
  — clicking the pip navigates to the detail page, clicking the `.rc` chip
  inside it must not (mirror the existing guard at `:1023`:
  `if(e.target.closest('.rc')) return;`, same idea for `.tscout`).
- A single roll-up "N/M scouted" replaces the current per-game `scouted` tag
  (`CAPTURED.has(m.id+':'+g.game_no)`, `:989`) — count games where that's
  true over games with a map.
- Card click (anywhere except `.rc`/`.tscout`) → `openMatch(m.id)`.

This keeps `matchCard(m)` as the function name (no call-site changes at
`:2219`/`:2924`) — its body shrinks to just this row.

### 2. Match detail page

New render function, e.g. `renderMatchDetail(m)`. Layout:

```
‹ Matches
Redline  2–1  Vertex Prime         Bo3 · Round 14 · Group 2 · Aug 1

[ M1 King's Row ✓ ] [ M2 Circuit Royal ✓ ] [ M3 Ilios ]
──────────────────────────────────────────────────────
King's Row · Hybrid · 3–1
Attacking first: Vertex Prime · Side picked by: Redline
🎥 AB12-CD34 (or "code wiped")   ✓ scouted

Bans                [bansOrdered(g) — unchanged]

Opening comps       [compRow/segOrder box — unchanged, promoted to
                      full width now that it isn't sharing a card with
                      bans+rosters]

Box score           [rosterHTML(g)'s table, always visible — no more
                      hidden/toggle, since this page IS the detail view]
```

- Header repeats the compact card's summary line + a `‹ Matches` back link
  (`onclick=()=>show('matches')` — doesn't try to restore rail-vs-tab origin,
  simplest option and consistent with how `scout=`/`prep=` links already just
  land on the `scout` tab).
- Map tabs: one per game with a map (`m.games.filter(g=>g.map)`), labelled
  `M{game_no} {map}` with a small ✓ if `CAPTURED.has(...)`. Default = first
  map. Per your answer, tabs — not an accordion — so only one map's bans/
  comps/box-score render at a time.
- Per-map panel is close to today's `.game` block content (`:983-1021`)
  minus the rosters-toggle machinery (`hidden` class, `.rtog`, the
  `game-hd` click handler) — box score is just always rendered now.

### 3. Routing

- Module state: `let MATCH_ID=null;` alongside `SCOUT_TEAM`/`SCOUT_PREP`.
- Shared helper `divisionOfMatch(matchId)`:
  `for(const cid in DIVS) if((DIVS[cid].matches||[]).some(m=>m.id===matchId)) return cid;
  return null;` — used by both `openMatch` (below) and `init`'s `match=`
  branch, so the lookup logic exists once.
- `openMatch(matchId)`: `divisionOfMatch(matchId)` → the single-division
  `VIEWS` entry for that `cid` (same precedent as `:3019-3021`: *"the single
  division is the page people mean when they share a link"*) → switch
  `CURRENT_VIEW`, `recomputeDivision()`, `updateHeader()`, sync the
  `#division` select, set `MATCH_ID=matchId`, `show('matchdetail')`. If
  `divisionOfMatch` returns null, fall back to `show('matches')` (see Risks).
- `findMatch(matchId)`: simple, assumes `CURRENT_VIEW` is already correct
  (true by the time it's called, since `openMatch`/`init` always resolve the
  division first) — `D().matches.find(m=>m.id===matchId)`. Used by `show`'s
  render call, kept separate from `divisionOfMatch` since it doesn't need to
  search every division once the view is already right.
- `hashFor(id)`: add `if(id==='matchdetail'&&MATCH_ID) return 'match='+
  encodeURIComponent(MATCH_ID);` before the existing scout/prep branch.
- `show(id)`: `matchdetail` isn't in `TABS`, so its render call is special-
  cased (`id==='matchdetail' ? renderMatchDetail(findMatch(MATCH_ID)) :
  TABS.find(...).render()`); nav active-state highlights the `matches` button
  when `id==='matchdetail'` (it's conceptually a drill-in under Matches, no
  dedicated nav entry — same non-tab status as `scout=`/`prep=` relative to
  `scout`).
- `init()`: add a `start.startsWith('match=')` branch before the final
  `TABS.some(...)` fallback, mirroring the `prep=`/`scout=` blocks — resolve
  the division via `divisionOfMatch`, set state, `show('matchdetail')`,
  `return`; if unresolved, fall through to the existing default-tab logic.

### 4. Scout-a-team rail

No component change — it already calls `matchCard(m)` (`:2219`), which now
renders the compact row. Same `openMatch` on click. Net effect: the rail gets
shorter automatically.

## Testing

- **Mandatory:** `pytest tests/test_export.py::test_dashboard_javascript_is_syntactically_valid`
  after every `_dashboard.py` edit (`node --check` over the generated script —
  a JS syntax error blanks the whole page, per CLAUDE.md).
- Manual: build a local preview (`faceit-sync export --format html --out
  dashboard.html`), headless-Edge screenshot (`--screenshot=FILE`, not
  `--dump-dom`) of: Matches tab compact list, a match detail page on each map
  tab, the Scout-a-team rail, and a `#match=<id>` deep link opened directly
  (confirms the division-resolution path, not just the click path).
- If a pure, dependency-free helper falls out of this work (e.g. `findMatch`
  or the pip win/loss classifier), add it to `tests/test_dashboard_logic.py`
  via the existing `_pure_js()` node harness, same placement discipline as
  `defaultMatchesMode`/`pickDivision` (declared above `bootApp`). Everything
  DOM-dependent (the tabs, the click routing, the header) is verified the
  same way the rest of this file already is — `node --check` + manual visual
  check, not invented pytest coverage for code the harness can't reach.

## Risks

| Risk | Mitigation |
|---|---|
| A match's `m.id` isn't found in any division (stale link, bad data) | `openMatch`/`init`'s `match=` branch falls back to `show('matches')` if `findMatch` returns null — same "stored id no longer exists" fallback discipline already used for `pickDivision`. |
| Pip click-guard misses a case, card navigates when copying a code | Reuse the exact `closest('.rc')`/`closest('.tscout')` guard pattern already proven at `:1023` and in the `data-scout` delegated handler — not a new mechanism. |
| Detail page opened for a match whose division isn't the current view (rail click while a different division is active) | `openMatch` always switches `CURRENT_VIEW` to the match's own division first, same as `scout=`/`prep=` already do — the back link then lands on that division's Matches tab, which is correct since the rail can only ever link to a match already in view. |
| Removing the rosters-toggle changes the page's initial height a lot (box score always visible) | Intentional — this page's whole purpose is the detail; nothing left to progressively disclose within a single map's panel. |

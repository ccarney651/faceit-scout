# Click-to-codes — design

**Date:** 2026-07-31
**Status:** approved, ready for implementation

## Goal

Peer feedback (boomed, twice): evidence panels on the Scout page show aggregate
stats ("they ban X on this map 4x", "3 games where the opponent shared 3 of
your heroes") with no way to reach the specific replay code(s) behind the
number. *"being able to click on these with drop downs to codes of the
specific maps would be nice"* / *"bringing me to the code of that 1 game would
be piss broken"*. Let every evidence row on Scout a team resolve to its
backing replay code(s), one click away.

## Background: what's already there

- Every game with a code carries it as `g.demo_code`; `rcChip(code)`
  (`_dashboard.py:841`) is the existing click-to-copy affordance, wired via a
  delegated `document` click listener (`:849-854`) — the pattern this feature
  reuses, not reinvents.
- `aggregate()` (`:1030-1080`) already tracks **which games** back one row: for
  `a.banOpen[hero]`, `gk` is a `Set` of `"<match_id>:<game_no>"` keys built in
  the same pass that increments the count (`:1074`). Every other accumulator in
  the same function — `bans`, `firstBans`, `mapStats`, `counter`, `perMapPick`,
  `pickFirstBan` — tracks only the count, not the keys. This feature is mostly
  extending an established pattern, not inventing one.
- `a.replays` (`:1052`) is already a flat per-game list with everything a
  codes popover needs to display: `{when, mid, opp, map, cat, gno, code, won}`.
- Counter-scout's matchup rows (`scout.matchups`, owscout-generated) already
  carry `match_id`/`game_no` per row — confirmed by
  `test_matchups_carry_match_identity_for_recency_and_history`
  (`owscout/tests/test_scout.py:133`). These rows need no aggregation changes
  at all, just a lookup.
- `document.addEventListener('click', ...)` delegation already exists twice
  (`data-scout` links, `.rc` copy) — this feature adds a third delegated
  handler, not a new event-wiring pattern.
- `table()` (`:967`) is entirely string-based: `html:` column builders return
  HTML strings inserted via `innerHTML`, and re-sorting rebuilds `tbody`
  from scratch by re-calling every `html:` builder. Any per-row interactive
  content must be self-contained in the string (no external registry that
  could go stale across a re-sort).

## Scope

**In scope — the 8 evidence render sites on Scout a team** (`renderScoutBody`):

| # | Section | Accumulator | Grain |
|---|---|---|---|
| 1 | Ban tendencies | `t.bans` | per hero |
| 2 | First ban | `t.firstBans` | per hero |
| 3 | Maps — picks & win rate | `t.mapStats` | per map |
| 4 | Counter-bans | `t.counter` | per opponent-banned hero |
| 5 | When they ban a hero → what they open | `t.banOpen` | per hero (gk already tracked) |
| 6 | Signature setups | `t.pickFirstBan` | per map |
| 7 | Bans on maps they pick (Ban-by-map evidence) | `t.perMapPick` | per map |
| 8 | Counter-scout ("vs comps like yours") | `scout.matchups` | per game (no aggregation) |

**Out of scope** (explicit, so it isn't silently expected later):

- The "At a glance" summary cards (go-to comps / their bans / map pool / form)
  and the barList/signature-ban teasers elsewhere on the page that reuse
  `t.bans`/`t.mapStats` in compact form — same underlying data is fully
  explorable, with codes, in the dedicated sections above. Wiring the
  teasers too would duplicate the affordance for no new capability.
- League meta and Overview — those aggregates are **league-wide**, not
  team-scoped; "which games" is a much larger, less-targeted list and reads
  differently. Not requested; left for a future pass if wanted.
- The Matches tab already shows codes inline per game card — nothing to add
  there.
- `t.banHeroWin` — computed but never rendered (dead code per an existing
  comment at `:2016`); not touched.

## Design

### 1. Data layer — extend `aggregate()`'s gk tracking

Mirror `banOpen`'s existing pattern (`gk: Set()` alongside the count, updated
in the same increment) for every other accumulator that needs it:

- `a.bans[hero]` / `a.firstBans[hero]` (flat `{hero:count}`) → add parallel
  `a.bansGk[hero]`/`a.firstBansGk[hero]` (`{hero:Set()}`). Kept parallel
  rather than nested, because `bans`/`firstBans` feed `banLiftRows()`, a
  generic helper used by League meta and Overview too — changing its input
  shape would ripple beyond this feature's scope.
- `a.mapStats[map]` (already `{games,wins,picks}`) → add a `.gk` property
  directly, same object. Safe: every consumer destructures named fields, none
  enumerates the object's keys.
- `a.pickFirstBan[map]` (already `{games,wins,bans:{}}`) → add `.gk` directly,
  identical precedent to `banOpen`.
- `a.perMapPick[map]` is currently a flat `{hero:count}` with no wrapper —
  restructure to `{heroes:{...}, gk:Set()}`. One consumer
  (`banMapTable`, `:2087`) changes from `rank(pm[mp])` to `rank(pm[mp].heroes)`.
- `a.counter[oppHero]` — the Counter-bans table's row grain is "opponent
  banned X" (one row lists every reply the team made), so track ONE `gk` per
  opponent-banned-hero, not per reply pair: `a.counterGk[oppHero] = Set()`.

Every `gk.add(...)` call uses the same key format already established by
`banOpen`: `` `${m.id}:${g.game_no}` ``.

Two small shared helpers, placed near `rcChip` (pure enough to unit-test):

```js
// mid:gno -> {map,cat,code,opp,when,won} for every game with a replay code in
// the given matches. Built once per aggregate() call; also used directly by
// Counter-scout, whose rows (owscout matchups) carry match_id/game_no but
// aren't part of aggregate()'s accumulators at all.
function codeLookup(matches, team){
  const m=new Map();
  matches.forEach(mt=>mt.games.forEach(g=>{
    if(!g.demo_code) return;
    m.set(mt.id+':'+g.game_no, {map:g.map, cat:g.map_category, code:g.demo_code,
      opp:(team&&mt.f1===team)?mt.f2:mt.f1, when:mt.finished_at,
      won: team? g.winner_faction===(mt.f1===team?'faction1':'faction2') : null});
  }));
  return m;
}
// Resolve a Set/array of 'mid:gno' keys to their code rows via a lookup Map,
// newest first, silently dropping keys the lookup doesn't have (a code that
// wiped, or a lookup built for a narrower match window than the gk set).
function codesFor(gkSet, lookup){
  return [...gkSet].map(k=>lookup.get(k)).filter(Boolean)
    .sort((a,b)=>String(b.when||'').localeCompare(String(a.when||'')));
}
```

### 2. UI layer — one popover, one inline-chip rule, one delegated handler

```js
// Evidence-row codes cell: exactly one backing game -> the code chip inline,
// no click needed (the common thin-sample case, and what was explicitly
// asked for — "bring me straight to code"). More than one -> a small
// click-to-open link; the resolved rows travel in a data attribute (JSON,
// esc()-quoted) rather than an external registry, since table() rebuilds
// every row's HTML string from scratch on every re-sort and a registry
// indexed by insertion order would go stale across that rebuild.
function codesCell(rows){
  if(!rows.length) return '<span class="faint">—</span>';
  if(rows.length===1) return rcChip(rows[0].code);
  return `<span class="codeslink" data-codes="${esc(JSON.stringify(rows))}">${rows.length} codes ▾</span>`;
}
let _codesPop=null;
function closeCodesPopover(){
  if(!_codesPop) return;
  _codesPop.remove(); _codesPop=null;
  document.removeEventListener('click', _codesPopOutside, true);
}
function _codesPopOutside(e){ if(_codesPop && !_codesPop.contains(e.target) && !e.target.closest('.codeslink')) closeCodesPopover(); }
function openCodesPopover(anchor, rows){
  closeCodesPopover();
  const pop=el(`<div class="codespop"></div>`);
  rows.forEach(r=>pop.appendChild(el(
    `<div class="codesrow"><span>${esc(r.map)} <span class="faint">vs ${esc(r.opp||'—')} · ${dshort(r.when)}</span></span>${rcChip(r.code)}</div>`)));
  document.body.appendChild(pop);
  const rc=anchor.getBoundingClientRect();
  pop.style.left=Math.max(8,Math.min(rc.left, window.innerWidth-pop.offsetWidth-8))+'px';
  pop.style.top=(rc.bottom+4)+'px';
  _codesPop=pop;
  setTimeout(()=>document.addEventListener('click', _codesPopOutside, true), 0);
}
document.addEventListener('click', e=>{
  const t=e.target.closest('.codeslink'); if(!t) return;
  openCodesPopover(t, JSON.parse(t.dataset.codes));
});
```

CSS (near `.rc`'s existing rules):

```css
.codeslink{cursor:pointer;color:var(--accent);font-size:12px;text-decoration:underline dotted;text-underline-offset:2px}
.codeslink:hover{color:var(--fg)}
.codespop{position:fixed;z-index:50;background:var(--surface);border:1px solid var(--line2);
  border-radius:8px;padding:8px;box-shadow:0 8px 24px rgba(0,0,0,.35);max-width:280px;max-height:320px;overflow:auto}
.codesrow{display:flex;justify-content:space-between;align-items:center;gap:10px;padding:4px 0;
  border-top:1px solid var(--line);font-size:12px}
.codesrow:first-child{border-top:0}
```

### 3. Wiring the 8 sites

Each site adds one column (or extends an existing cell) via `codesCell(...)`.
`lookup` = `codeLookup(t.matches, t.team)` built once per `renderScoutBody`
call (reused by sites 1-7 via each row's `gk`; site 8 uses it directly per
matchup's own `match_id:game_no`, no `gk` involved).

| # | Change |
|---|---|
| 1, 2 | `banLiftRows()`'s output rows gain a `codes` field (`codesFor(bansGk[h]\|\|new Set(), lookup)`); the Ban tendencies / First ban tables add a "Codes" column. |
| 3 | Maps table adds a "Codes" column: `codesFor(v.gk, lookup)`. |
| 4 | Counter-bans table adds a "Codes" column: `codesFor(counterGk[opp]\|\|new Set(), lookup)`. |
| 5 | `boRows` (ban→opening) already has `v.gk` — add a "Codes" column, no accumulator change. |
| 6 | Signature setups (`pfb`) adds a "Codes" column: `codesFor(v.gk, lookup)`. |
| 7 | `banMapTable`'s rows add a "Codes" column: `codesFor(pm[mp].gk, lookup)`. |
| 8 | Counter-scout's matchup rows (`:1894-1899`) get an inline `rcChip` appended directly (each row is exactly one game — always the single-code inline case, never the popover). |

## Testing

- **Mandatory after any `_dashboard.py` edit:**
  `pytest tests/test_export.py::test_dashboard_javascript_is_syntactically_valid`.
- New pure-function tests (`tests/test_dashboard_logic.py`, via the existing
  `_pure_js()`/`_run()` node harness) for `codeLookup` and `codesFor` — both
  are declared above `bootApp` specifically so they're reachable by that
  harness, same placement discipline as `defaultMatchesMode`/`pickDivision`.
  Cases: a game with no `demo_code` is excluded from the lookup; `codesFor`
  sorts newest-first and silently drops a key missing from the lookup.
- `codesCell`'s inline-vs-popover branch is a one-line pure decision — cover
  it in the same test file (0 rows → em-dash, 1 row → `rcChip`-shaped output,
  2+ rows → `codeslink`-shaped output with valid embedded JSON).
- Everything downstream of these (the `aggregate()` accumulator wiring, the
  popover DOM/positioning, the delegated click handler) lives inside `bootApp`
  and is DOM-dependent — per this codebase's established practice (see the
  Overview/nav redesign plan, same day), that's verified via `node --check`
  plus a manual headless-Edge visual/interaction check, not invented pytest
  coverage for code the test harness can't reach.
- Manual check: build a local preview, screenshot `#scout=<team>` for a team
  with multi-game evidence rows; confirm each of the 8 sections shows a Codes
  column/chip, a single-code row shows the `.rc` chip inline, a multi-code row
  shows a `codeslink`, and (if a real browser/Playwright becomes available)
  clicking it opens the popover with the right codes and click-to-copy still
  works.

## Risks

| Risk | Mitigation |
|---|---|
| A `gk` set and its row's displayed count silently disagree (e.g. one code wiped/missing from `a.replays`) | `codesFor` just returns fewer rows than the count in that case — visibly "3 games, 2 codes shown" rather than a crash or a wrong number; acceptable, matches how `t.replays`-based coverage counters already handle missing codes elsewhere (`coverageState`). |
| JSON round-tripped through a `data-` attribute for larger rows-lists gets unwieldy | Each row list is at most a handful of games (typically 1-8), each entry a few short strings — well within reasonable attribute size; `esc()` already escapes `"` safely for double-quoted attributes. |
| Popover positioning goes off-screen on a narrow viewport | Clamped in `openCodesPopover` (`Math.min(rc.left, window.innerWidth-pop.offsetWidth-8)`); not pixel-perfect on every viewport but never fully off-screen. |
| Restructuring `perMapPick[map]` from flat to `{heroes,gk}` breaks a consumer I didn't find | Single known consumer (`banMapTable`); grep for `perMapPick` before landing the change to confirm no second site. |

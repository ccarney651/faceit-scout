# Team Compare — design

**Date:** 2026-08-08
**Status:** approved, ready for implementation

## Goal

A two-team, side-by-side comparison on the dashboard: a radar-style chart across
mixed FACEIT + capture-derived dimensions, plus per-team map-pick/ban views and
a perspective toggle. Because we hold captured comps, this compare is deeper than
owscouter's (which is FACEIT stats only): comp diversity, hero-pool breadth and
adaptability join map win rate, bans and efficiency on the same radar.

## Background: what's already there

- **Per-team aggregates are computed today.** `aggregate(matches, team)`
  (`faceit_sync/dashboard/app.js:662-718`) already returns `mapStats`
  (`{map:{games,wins,picks,gk}}`), `bans`, `mapsPicked`, `firstBans`,
  `firstBanGames`, `results` and more — keyed on team name, reading the
  active division's matches. Compare needs nothing new from FACEIT data.
- **Capture analytics are already per team.** `DATA.owscout_comps[team].scout`
  carries `overall` (comp families), `adapt` (`swaps_per_map`, `families`),
  `hero_pool` (`[{hero,role,rounds,pick_rate}]`), `games` (maps captured),
  `rounds`, `swaps` and `ban_response`.
- **Team Eff is already computed.** `rankPlayers` + `efficiencyRatings` produce
  `p.eff.eff` per player; compare averages the qualified players' Eff for the
  team axis.
- **Pseudo-tab routing has a proven pattern.** `#match=<id>` → `matchdetail`
  (`app.js:2756-2765`, `:2774-2789`) resolves a division, switches
  `CURRENT_VIEW`, sets state, then renders a non-nav `render*` function with a
  `hashFor` special-case and a nav-highlight override. `#compare=` follows the
  same shape with two team names.
- **No SVG/chart helper exists yet.** All "charts" are CSS bars (`barList`,
  `.track/.fill`) and sortable tables. The radar is the first inline SVG in the
  app — a small self-contained generator, no dependency.

## Scope decisions

| Decision | Choice | Why |
|---|---|---|
| Surface | Pseudo-tab via `#compare=<A>\|<B>` deep link | Same non-nav drill-in status as `matchdetail`; a clean slate for the two-column layout without adding a sixth nav button. |
| Reach | Scout page "Compare…" entry + the compare view's own selectors | The deep link is the canonical address; the Scout button is the discovery path. |
| Dimensions | Mixed: 5 FACEIT + 3 capture axes | This is the parity advantage — "especially with my hero tracking". Capture axes degrade gracefully to dimmed/absent when a team has no captures. |
| Division scope | Same-division only | Elo/Eff/ban baselines are division-scoped; a cross-division radar would compare incomparable cohorts. B in a different division → falls back to A's division with a note. |
| Sample window | Full season (no recency slider) | Matches coverage and the sim's full-season map picks; a window control is future work. |
| Radar normalization | Fixed caps per axis | Honest and stable: two weak teams both show small shapes rather than inflating to fill the chart. Caps are documented constants (the `MODE_MINUTES` precedent). |
| Team Eff axis | Mean of qualified players' `eff.eff` (≥5 maps each) | Reuses `LB_MIN_GAMES`; players under the floor are excluded so a 1-map cameo can't drag the mean. |

### Axes

All axes normalize to 0..100 via `min(raw/cap, 1)*100`. A per-team `ok:false`
(insufficient sample) dims that team's vertex and value text; an axis with no
sample on *either* side is dropped from the radar (with a note naming what's
missing — "no capture data for either team").

| Axis | Source (per team) | Cap | Floor (ok) |
|---|---|---|---|
| Map win rate | `agg.mapStats` Σwins / Σgames | 100 | ≥5 games |
| Map pool breadth | distinct maps with ≥1 game | 10 | ≥5 games |
| Ban pressure | bans per game (Σ`bans` / Σgames) | 2 | ≥5 games |
| Pick agency | `mapsPicked` share of games | 100 | ≥5 games |
| Team Eff | mean of roster `eff.eff` (qualified) | 2.0 (z-scale) | ≥3 qualified players |
| Comp diversity | `scout.adapt.families` | 12 | ≥3 captured maps |
| Hero pool breadth | distinct `hero_pool` heroes with pick_rate ≥ .05 | 15 | ≥20 captured rounds |
| Adaptability | `scout.adapt.swaps_per_map` | 3 | ≥3 captured maps |

## Design

### 1. Pure layer — `faceit_sync/dashboard/pure.js`

Hoisted above `bootApp` (the `test_dashboard_logic.py` `_pure_js()` seam):

- `compareAxes(aggA, aggB, scoutA, scoutB)` → array of axis rows
  `{id, label, a:{raw,val,n,ok}, b:{raw,val,n,ok}}`. Pure data math: takes the
  already-computed aggregates (FACEIT numbers from `aggregate()`, capture
  numbers from `owscout_comps`), applies caps/floors, drops all-missing axes.
- `radarPoints(axisVals, cx, cy, r)` → `[{x,y}]` polygon vertices for one team,
  starting at 12 o'clock, clockwise. Pure trig; the caller supplies `vals`
  (array of 0..100 numbers, or null to skip a vertex) and a target center/radius.
- Constants `COMPARE_CAPS` and the axis/floor table live beside the functions
  so tests pin them.

Inputs to `compareAxes` are explicit `agg`/`scout` objects (no `DATA`, no `D()`,
no `MAP_CAT`), so node tests construct fixtures directly — same discipline as
`simModelFrom(matches, team, limitGames)`.

### 2. State + routing — `faceit_sync/dashboard/app.js`

- Module state next to `MATCH_ID` (`app.js:862`):
  `let COMPARE_A=null, COMPARE_B=null, COMPARE_PERSP='A';`
  (`COMPARE_PERSP` = whose perspective the labels read from: `'A'` | `'B'`).
- `hashDispatch()` (`app.js:2725`): add a `compare=` branch before the
  `TABS.some` fallback (`:2772`). Format `compare=<A>|<B>` (both
  `encodeURIComponent`'d). Resolve the single-division view via team A (same
  loop as `scout=` at `:2743-2755`); if team B isn't in that division, leave
  `COMPARE_B` unresolved and let the render show a note. Set
  `CURRENT_VIEW`, `recomputeDivision()`, `updateHeader()`, sync the division
  select, `show('compare')`.
- `show(id)` (`:2774`): special-case `compare` like `matchdetail` — nav
  highlights the `scout` button (it's a drill-in under Teams). Render
  `renderCompare()`.
- `hashFor(id)` (`:2715`): `if(id==='compare'&&COMPARE_A&&COMPARE_B) return
  'compare='+encodeURIComponent(COMPARE_A+'|'+COMPARE_B);`.
- `gotoCompare(a,b)` helper: set both, `show('compare')` — used by the Scout
  entry button and the compare view's own team selectors.

### 3. Scout page entry — `app.js` `renderScout` (`:1157-1174`)

A "Compare…" button in the scout control bar. Click → `gotoCompare(SCOUT_TEAM,
<first other team in D().team_names>)`. This is the discovery path; the compare
view's own selectors are the primary picking surface once inside.

### 4. Compare view — `renderCompare()` in `app.js` + CSS in `head.html`

```
Redline            2–1  vs  1–2          Vertex Prime        [swap]
[Team select A]  [perspective toggle]  [Team select B]

            [ RADAR — octagon, two polygons, dimmed axes,
              per-axis value + n labels, legend ]

Maps            Bans            Comps*           Players
[mapStats table][banLift table] [families/pools] [Eff top list]
   └ per team     └ per team      └ per team       └ per team

Head to head   (matches where both appear, score + #match= link)
```

- **Header band**: A vs B names with record pills (`pill`/`winVar`, from
  `scoutData(A).results` and `scoutData(B).results`), a swap button, the two
  team selects, and the **perspective toggle** (radio "Prepping to play A" /
  "Prepping to play B"). The toggle re-renders the section labels so the
  prepped team reads as "you": e.g. bans become "Expect B to ban" vs "Expect A
  to ban" depending on `COMPARE_PERSP`.
- **Radar card**: inline SVG octagon. Two `<polygon>`s (team A fill + team B
  stroke), axis spokes + value lines, dimmed (reduced opacity) for `ok:false`,
  per-axis labels with value + `n`. Small SVG generator helpers in `app.js`
  (`svgPoly(points)`, etc.) — first SVG in the app, kept local and minimal.
- **Maps**: per-team table from `agg.mapStats` (map, games, win-rate pill, pick
  count), using the existing `table`/`pill`/`winVar` helpers.
- **Bans**: per-team `banLiftRows` vs the shared `divBanBaseline()` (reuses
  `app.js:151-164`), so each side reads "what they value MORE than the field".
- **Comps** (rendered only if either team has captures): per-team top families
  (`compRow`), hero-pool chips by role, `swaps_per_map` + `families` summary
  line — reusing `DATA.owscout_comps[team].scout`.
- **Players**: per-team top contributors by `eff` (falling back to elo), via
  `rankPlayers`/`efficiencyRatings`.
- **Head to head**: matches in `D().matches` where `f1`/`f2` are A and B, each
  with `pill` score + click → `#match=<id>`.

### 5. CSS — `head.html`

Radar layout classes: `.compare-grid` (two-column side-by-side), `.radar`
(+ axis/value text styles, dim state), `.compare-hd` (header band). Follow the
existing variable conventions (`--line`, `--muted`, `--good`, `--bad`, `--accent`).

## Testing

- **Mandatory after every `_dashboard.py`/part-file edit:**
  `pytest tests/test_export.py::test_dashboard_javascript_is_syntactically_valid`
  (`node --check` over the generated script). One syntax error blanks the page.
- New pure tests in `tests/test_dashboard_logic.py` (via the existing `_pure_js()`
  node harness, explicit fixture aggs/scouts):
  - cap-clamping (`raw > cap` → 100; `raw=0` → 0);
  - floor dimming (a team under the map floor gets `ok:false`; the other stays `ok`);
  - all-missing axis dropped (neither team has captures → no capture axes, note material);
  - one-sided capture sample (A captured, B not → capture axes present with B dimmed);
  - Team Eff = mean of qualified players only (unqualified excluded);
  - `radarPoints` vertex math (12 o'clock start, clockwise order, 0-radius center).
- Full `pytest` green; `mypy faceit_sync` clean (these edits live in the JS parts,
  which mypy doesn't parse — still run for the repo rule).
- Visual: build local `dashboard.html`, headless-Edge screenshot (`--screenshot=FILE`)
  of: the compare view, the `#compare=A|B` deep link opened directly, the
  perspective toggle, and a one-sided-capture pair (dimmed capture axes).

## Out of scope

- A recency window for the compare sample (full season only).
- Cross-division comparison.
- A compare link on match cards / the Matches tab (nice-to-have later).
- Player-level head-to-head matchup tiles.

## Risks

| Risk | Mitigation |
|---|---|
| Team names collide across regions in the `#compare=` link (e.g. "bye") | Same-division enforcement uses the single-division view (as `scout=` already does); an unresolved B shows a note rather than silently comparing wrong teams. |
| Radar reads as misleading when an axis has a tiny sample | Per-team `ok:false` dims the vertex + value; the axis label carries `n`; `worstMaps`-style "not enough games" copy is reused where relevant. |
| Team Eff drags a roster with one qualified player into a confident-looking mean | Mean requires ≥3 qualified players (each ≥5 maps), mirroring `EFF_GROUP_MIN`'s honesty floor. |
| The octagon mis-scales for a team with no captures | Axes missing on *both* sides are dropped entirely; a one-sided gap is visually dimmed, not stretched. |
| `compare=` URL with a stale/unresolvable team | Same fallback discipline as `scout=`/`match=`: unresolved teams render a note and the page still shows the division, never a blank. |

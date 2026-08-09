# Draft simulator — explainable & verifiable — design

**Date:** 2026-08-05
**Status:** proposed

## Goal

The draft simulator shows *what* it suggests (a pre-filled map and bans per game) but
not *why*, and its decision engine is unverifiable. Rewrite it around three
commitments, driven by the operator's ask ("ease of use, readability, easy to
understand; suggested bans/map picks explained as plainly as possible; data strong
and verifiable"):

1. **Every suggestion explains itself in plain language.** The auto-picked map and
   each suggested ban get a one-to-two-sentence reason, shown visibly (not
   hover-only), and re-explain themselves when the user changes a selection.
2. **The data behind every suggestion is strong and verifiable.** The suggestion
   engine moves into the tested pure-function layer (the same discipline as every
   other dashboard decision helper), every suggestion states what it rests on
   (counts, window, team-vs-division fallback), weak samples are flagged, and the
   backing games are one click away as replay codes.
3. **The interface is readable and self-explanatory.** Tooltip-only controls get
   visible microcopy; the dense wall-of-text intro becomes a compact legend; chip
   counts get defined.

## Background: what's already there

- `renderSim()` (`_dashboard.py:2998`) builds the whole sim. Its decision helpers —
  `simModel` (`:2956`), `divBanBaseline` (`:1015`), `divMaps` (`:2971`), `banSuggest`
  (`:2975`), and the `renderSim` closures `mapKey`/`cmpMap`/`allowedCatsFor`/
  `autoMap`/`autoBan`/`sigMark` (`:3040-3100`) — are all **below `bootApp` (line 866)**
  and depend on the `D()` global plus the bootApp-scoped `inc` helper (`:920`), so
  they sit outside the `_pure_js()` head that `tests/test_dashboard_logic.py`
  executes. The sim has **zero behavioural tests**.
- The **pure-head pattern is established**: `_pure_js()` (`tests/test_dashboard_logic.py:22`)
  runs everything above `bootApp` with node, and `codeLookup`/`codesFor`
  (`_dashboard.py:743`/`:757`) already live there, tested.
- **Click-to-codes infra already exists**: `codeLookup(matches, team, wipeDate)` →
  `Map<'mid:gno', {map,cat,code,opp,when,won,dead}>`, `codesFor(gkSet, lookup)`, and
  the bootApp-scoped renderer `codesCell(rows)` + `.codespop` popover (`:1156`) with
  its delegated `.codeslink` click handler. The sim only needs to feed it gk keys.
- The model already computes `ngames` (window transparency), per-map pick counts,
  per-map ban counts, and overall ban counts (`simModel`). It does **not** track the
  game keys (`mid:gno`) behind each count, so drilldown is impossible today.
- `banSuggest`'s ranking is `onMap*2 + all` (`:2977`) — opaque. `sigMark` (`:3096`)
  requires ≥3 bans and lift ≥2 vs the division ban share; it is a bootApp closure.
- Chips show raw counts (`Oasis 3×`, `2× here · 5 total`) whose meaning lives only in
  the wall-of-text intro (`:3028`) or hover tooltips. There is no fallback labelling
  (when the sim falls back to division tendencies it is invisible) and no
  sample-honesty (a "2× here" read off a 2-game window looks as strong as one off 15
  games).
- `D().matches` carries `id`, `finished_at`, per-game `map`, `game_no`, `demo_code`,
  `map_picked_by`, and `bans[{team,hero,order}]` — everything the drilldown needs.

## Scope

**In scope:**

1. Hoist the sim's decision engine into the pure head as data-parameterized
   functions (no `D()`, no `inc`): `simModelFrom`, `divBanBaseFrom`, `mapsFrom`,
   `banSuggest`, `mapCompare`, `allowedCatsFor`, `autoMap`, `autoBan`, `sigLift`.
2. New pure explainers that turn those numbers into plain sentences: `mapExplain`,
   `banExplain`, `modeExplain`, plus a thin-sample descriptor.
3. Focused-card explainer strips for map + both bans, wired to the current selection
   (auto or user-picked), each carrying its evidence as a click-to-codes cell.
4. UI copy: controls get visible microcopy, the intro wall-of-text becomes a compact
   legend, and the status/transparency line gains weak-sample warnings.
5. gk tracking in the model for the drilldown.
6. Behavioural tests for every pure helper.

**Out of scope** (explicit):

- The scenario-tree mechanics (branch/expand/focus/collapse) — unchanged; only copy
  touches them.
- The capture "drafts" review flow (`owdb drafts`, GUI review) — an unrelated
  feature that merely shares the word.
- New suggestion *features* (win-rate-aware map picks, comp-aware bans, per-game
  outcome reads) — future, not this pass.
- Removing the "beta" label — flagged as a decision at the end (see §7), not assumed.

## Design

### 1. Pure decision engine (hoisted above `bootApp`)

All functions take explicit data and return plain values; none touch `D()`, the DOM,
or `inc` (increments are inlined as local closures). Placed above `bootApp`, right
after `codesFor`, under a `/* draft simulator — pure decision helpers */` banner.

**Model builder** — same shape as today's `simModel` plus gk keys:

```js
function simModelFrom(matches, team, limitGames){
  const pick={}, banByMap={}, bansAll={}, gkPick={}, gkBanAll={}, gkBanMap={};
  const inc=(o,k)=>o[k]=(o[k]||0)+1;
  const add=(o,k,v)=>{(o[k]=o[k]||new Set()).add(v);};
  const games=[];
  (matches||[]).forEach(m=>{
    const side=m.f1===team?'faction1':(m.f2===team?'faction2':null); if(!side) return;
    (m.games||[]).forEach(g=>{ if(!g.map) return;
      games.push({g,mid:m.id,at:m.finished_at||'',gno:g.game_no||0}); });
  });
  games.sort((a,b)=>(a.at<b.at?1:a.at>b.at?-1:0)||(b.gno-a.gno));
  const use=(limitGames>0)?games.slice(0,limitGames):games;
  use.forEach(({g,mid})=>{
    const k=mid+':'+g.game_no;
    if(g.map_picked_by===team){ inc(pick,g.map); add(gkPick,g.map,k); }
    (g.bans||[]).filter(b=>b.team===team&&b.hero).forEach(b=>{
      (banByMap[g.map]=banByMap[g.map]||{}); inc(banByMap[g.map],b.hero);
      inc(bansAll,b.hero); add(gkBanAll,b.hero,k);
      (gkBanMap[g.map]=gkBanMap[g.map]||{}); add(gkBanMap[g.map],b.hero,k); });
  });
  return {team,pick,banByMap,bansAll,gkPick,gkBanAll,gkBanMap,ngames:use.length};
}
```

**Division baselines / maps** — parameterized versions of `divBanBaseline`/`divMaps`
(the share math from `:1015` verbatim, but over an explicit match list):

```js
function divBanBaseFrom(matches){
  const all={}, first={};
  (matches||[]).forEach(m=>(m.games||[]).forEach(g=>{
    if(!g.map) return;
    (g.bans||[]).forEach(b=>{ if(!b.hero) return;
      all[b.hero]=(all[b.hero]||0)+1; if(b.order===1) first[b.hero]=(first[b.hero]||0)+1; }); }));
  const shares=o=>{ const t=Object.values(o).reduce((a,b)=>a+b,0)||1; const s={};
    Object.entries(o).forEach(([h,n])=>s[h]=n/t); return s; };
  return {all:shares(all), first:shares(first)};
}
function mapsFrom(matches){
  const s={}; (matches||[]).forEach(m=>(m.games||[]).forEach(g=>{
    if(g.map&&!s[g.map]) s[g.map]=g.map_category||''; }));
  return s;
}
```
(`MAP_CAT` is bootApp-scoped (`:938`), so the pure `mapsFrom` reads only the data's
`g.map_category`; the bootApp `divMaps()` wrapper backfills gaps from `MAP_CAT`.)

**Suggestions.** `banSuggest` moves up essentially unchanged (it is already pure); its
ranking `onMap*2 + all` is pinned here so tests can assert ordering:

```js
// Ranked ban suggestions for a team on a map. Blend on-map ("in this situation")
// with overall tendency, weighting on-map so a hero they clearly target here
// leads — but a single on-map ban doesn't outrank a strong overall staple.
function banSuggest(model, map, illegal){
  const onMap=model.banByMap[map]||{}, all=model.bansAll||{}, keys=new Set([...Object.keys(onMap),...Object.keys(all)]);
  const score=x=>x.onMap*2+x.all;
  return [...keys].filter(h=>!illegal.has(h))
    .map(h=>({hero:h,onMap:onMap[h]||0,all:all[h]||0}))
    .sort((a,b)=>(score(b)-score(a))||(b.onMap-a.onMap)).slice(0,7);
}
```

**Signature lift** — the numeric core of today's `sigMark` closure, made pure:

```js
// Signature ban: a hero this team bans REPEATEDLY and well above the field.
// Requires a real sample (>=SIG_MIN bans) and a lift >=SIG_LIFT vs the division
// share. Returns {sig, bans, lift}; lift is null when the field has no baseline.
function sigLift(model, divBase, hero){
  const bans=model.bansAll[hero]||0;
  if(bans<SIG_MIN) return {sig:false, bans, lift:null};
  const tot=Object.values(model.bansAll).reduce((a,b)=>a+b,0)||1;
  const share=divBase.all[hero];
  const lift=share? (bans/tot)/share : null;
  return {sig: lift!=null && lift>=SIG_LIFT, bans, lift};
}
const SIG_MIN=3, SIG_LIFT=2, SIM_MIN_MAPS=6;
```

**Map ordering + auto picks** — the closure logic moves up unchanged:

```js
// allowedCatsFor(g1, used, pool): G1 is Control; afterwards any non-Control mode
// not yet played on this line, with a repeat allowed once all four are used.
function allowedCatsFor(g1, used, pool){
  const MODES=['Control','Escort','Flashpoint','Hybrid','Push'];
  if(g1) return ['Control'];
  const usedCats=new Set([...used].map(mp=>pool[mp]));
  const nc=MODES.filter(x=>x!=='Control'), fresh=nc.filter(x=>!usedCats.has(x));
  return fresh.length? fresh : nc;
}
// mapCompare(a, b, teamPicks, divPicks, divPlay): season team picks, then division
// picks, then raw division plays; ties break alphabetically.
function mapCompare(a, b, teamPicks, divPicks, divPlay){
  const ka=[teamPicks[a]||0,divPicks[a]||0,divPlay[a]||0];
  const kb=[teamPicks[b]||0,divPicks[b]||0,divPlay[b]||0];
  for(let i=0;i<3;i++){ if(kb[i]!==ka[i]) return kb[i]-ka[i]; } return a.localeCompare(b);
}
function autoMap(teamPicks, divPicks, divPlay, cats, used, pool){
  const avail=Object.keys(pool).filter(mp=>!used.has(mp)&&cats.includes(pool[mp]));
  avail.sort((a,b)=>mapCompare(a,b,teamPicks,divPicks,divPlay));
  return avail[0]||null;
}
function autoBan(model, map, illegal){
  const s=banSuggest(model, map, illegal); return s.length? s[0].hero : null;
}
```

The `renderSim` closure versions of these are deleted in favour of the hoisted ones
(thin bootApp wrappers keep the old names working — see §1 note below).

**Back-compat wrappers.** `simModel`/`divBanBaseline`/`divMaps` stay where they are
today (below `bootApp`) as one-line delegators to the pure functions with
`D().matches`, so the Scout page and League meta callers are untouched:
`simModel(team,n)=>simModelFrom(D().matches,team,n)`, etc. The hoisted functions are
the tested ones; the wrappers are untestable by construction (they read the global),
which is the established pattern.

### 2. Plain-language explainers (pure text)

Return `{text, thin}` plain strings (no HTML; the bootApp layer escapes with `esc`).
Each takes the numbers, not the model, so they are trivially unit-testable:

```js
// Why this map. teamPicks = this team's season pick count for `map`; divPicks =
// the division-wide pick count (the fallback); cat = the map's mode. `thin` means
// "a single data point" — zero-data/fallback reads carry their caveat in the text
// instead, so a fallback is never also labelled "a single case".
function mapExplain(teamName, map, cat, teamPicks, divPicks, isTopInCat){
  if(teamPicks>0) return {text:`${teamName} picked ${map} ${teamPicks}× this season`+
    (isTopInCat?` — their most-picked ${cat} map`:''), thin: teamPicks===1};
  if(divPicks>0) return {text:`no ${teamName} pick history on ${cat} — ${map} is the division's most-picked (${divPicks}× league-wide)`, thin:false};
  return {text:`no pick data on ${cat} — nothing to read yet`, thin:false};
}
// Why this ban. all/onMap = overall vs on-this-map ban counts; the isTop* flags
// must be computed against the current legal suggestion set so an override never
// claims to be "the most".
function banExplain(teamName, map, hero, all, onMap, isTopOverall, isTopOnMap, sig){
  if(all===0) return {text:`no ban history for ${hero} — an experimental pick`, thin:false};
  let t, saidHere=false;
  if(isTopOverall) t = `${teamName}'s most-banned hero overall — ${all}× this season`;
  else if(isTopOnMap){ t = `their most-banned hero on ${map} — ${onMap}× here${onMap<all?`, ${all}× this season`:''}`; saidHere=true; }
  else t = `banned ${all}× this season`;
  if(onMap>0 && !saidHere) t += `, ${onMap} of them on ${map}`;
  if(sig) t += ` — ★ signature, well above the division rate`;
  return {text:t, thin: all===1};
}
```
(`saidHere` avoids restating the on-map count when the lead already said "× here",
so a hero that is top overall AND top on-map still keeps its on-map evidence.)
// Why this mode (later games). leaguePct = share of league picks in this mode.
function modeExplain(teamName, cat, leaguePct, teamModePicks){
  return {text:`${cat} — the league's most-picked remaining type (${leaguePct}% of picks)`+
    (teamModePicks>0?`; ${teamName} picked ${cat} maps ${teamModePicks}× themselves`:''),
    thin:false};
}
```

**Thin-sample bar.** `SIM_MIN_MAPS=6` (a named constant near the pure helpers): when
either team's `ngames` is below it, the status line says the read is thin. Per-suggestion
thinness is the `thin` flag above (a count of exactly 1).

### 3. Focused-card explainer strips

The focused node gains one explainer line per decision, each narrating the **current
selection** (so an override re-explains itself):

- **Map row:** under the map buttons — `Why ${map}? ${mapExplain(...).text}` plus
  `codesCell(codesFor(gkPick[map], lookup))` when that map has picks.
- **Ban rows:** under each team's buttons — `Why ${hero}? ${banExplain(...).text}`
  plus `codesCell(codesFor(gkBanMap[map]?.[hero] ?? gkBanAll[hero], lookup))`.
- `isTopOverall`/`isTopOnMap`/`isTopInCat` are computed against the **current legal
  suggestion set** (the max count within it), so the "most-banned / most-picked"
  phrasing is literally true and an override is never mislabelled. The
  auto-selected values are the top of the blended ranking (`banSuggest`'s
  `onMap*2+all`), and their explainers then state whichever "most" claims hold.
- **Wiring:** the existing `setOv`/`onPick` handlers already re-`draw()` on every
  change and the explainer reads the resolved `map`/`b1`/`b2` (override-or-auto), so
  no new state is introduced.

### 4. Evidence drilldown

`renderSim` builds `lookup = codeLookup(D().matches, SIM_A, CODE_WIPE)` once per
`draw()` (Team A's perspective for opponent names; both teams' codes resolve because
the lookup is built over the same match list the models read). Each explainer's
codes cell uses the shipped `codesCell`/`.codespop`/delegated `.codeslink` handler
unchanged; wiped codes render the existing "code wiped" tag.

### 5. Readability & microcopy

- **Controls:** keep the six controls; add a visible one-line microcopy strip beneath
  them — "Team A picks Game 1 and bans first. The loser of each map picks the next
  one." — so the "First pick & ban" toggle and the tree's mechanics read without
  hovering.
- **Legend:** replace the `:3028` wall of text with a compact always-visible legend:
  - `3×` on a map chip = times that team has picked it this season.
  - `2× here · 5×` on a ban chip = bans on this map · this season (always both parts).
  - `★` = signature ban — repeated well above the division rate.
  - A team can't repeat its own ban down a line.
- **Status line:** keep the window transparency ("reads use … full-season record —
  Team A 15 maps · Team B 12 maps"), and when any team's `ngames < SIM_MIN_MAPS`
  append "— only N maps on record, so this read is a hint, not a pattern".
- **Chip counts:** ban chips move to the always-two-part `N× here · M×` format
  (dropping the bare/`total` variants) so the legend is literally true everywhere.

### 6. Tests (see the plan doc for the full list)

`tests/test_dashboard_logic.py` gains behavioural cases for every hoisted helper and
explainer, run through the existing `_run`/`_pure_js` node harness. DOM-scoped
renderers (the strips, legend, codeslinks inside cards) follow the codebase's
established verification: `node --check` + a headless-Edge screenshot pass, not
invented pytest coverage for code the harness can't reach.

### 7. Beta label — decision point

The sim is beta-labelled because its logic was untested and its suggestions
unexplained. This pass removes both objections. Graduating it out of beta is a
one-word change in `renderScoutBody` (`:2763`); flagged for the user, not assumed.

## Testing

- Mandatory after any `_dashboard.py` edit:
  `pytest tests/test_export.py::test_dashboard_javascript_is_syntactically_valid`.
- New `tests/test_dashboard_logic.py` cases (via `_run`/`_pure_js`), minimum set:
  - `simModelFrom`: newest-N windowing; team-side attribution; per-map vs overall
    ban counts; gk keys on picks/bans (map-scoped and overall); `ngames`.
  - `banSuggest`: on-map ranks above overall; capped at 7; illegal heroes excluded.
  - `sigLift`: <3 bans never sig; lift ≥2 threshold; missing field baseline → null lift.
  - `mapCompare`/`autoMap`: team picks beat division picks beat division plays;
    `used`/category respected; alphabetical tiebreak.
  - `allowedCatsFor`: G1 Control-only; fresh modes first; repeat only after all used.
  - `autoBan`: top suggestion, or `null` when the illegal set covers all.
  - `mapExplain`/`banExplain`/`modeExplain`: team-data vs fallback vs no-data
    phrasing; `thin` at count 1; signature mention; no false "most" after an override.
  - `divBanBaseFrom`: share sums to 1; zero-total guard doesn't NaN.
- Manual pass: build a local preview, screenshot `#scout=<team>` with the sim section
  expanded — one team with rich history, one with thin history. Confirm explainers
  render, chips read plainly, weak-data warnings appear, and codes popovers open from
  the focused card.

## Risks

| Risk | Mitigation |
|---|---|
| Hoisting the helpers above `bootApp` breaks an existing caller | Thin wrappers keep the old names (`simModel`/`divBanBaseline`/`divMaps`) delegating to the pure functions, so Scout page and League meta callers are untouched. |
| "most-picked" claims drift from the ranking after a user override | `isTop*` flags are computed from the *current* suggestion list and passed into the explainers, so an override is never mislabelled. |
| gk sets and displayed counts disagree (wiped/missing codes) | `codesFor` silently returns fewer rows — "3 bans, 2 codes shown", the mismatch the dashboard already tolerates. |
| Explainers make the focused card taller/busier | One short sentence per decision row, only in the focused card; mini nodes stay at today's density. |
| A hoisted function accidentally references `esc`/`inc`/`CODE_WIPE` | `_pure_js()` executes every hoisted line in node during tests — any bootApp-scoped reference throws immediately, catching a bad hoist before the UI ever runs. |

# Match Detail Page Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the fully-expanded match card (bans + comps + rosters for every map, stacked) with a compact "at a glance" card and a click-through match detail page with per-map tabs, per `specs/2026-08-01-match-detail-page-design.md`.

**Architecture:** Client-side only, entirely within `faceit_sync/_dashboard.py`'s `HTML_TEMPLATE` JS. Three pure helpers above `bootApp` (`divisionOfMatch`, `mapPipClass`, `scoutedCount`), a new routing state (`MATCH_ID`) and pseudo-tab (`matchdetail`) alongside the existing `scout=`/`prep=` hash pattern, a new `renderMatchDetail`/`gamePanel` pair that reuses today's bans/comps/rosters rendering verbatim, and a rewritten `matchCard` that shrinks to the compact summary + map pips.

**Tech Stack:** Python 3.12 (`faceit_sync/_dashboard.py`, a Python string), vanilla JS, `node --check` for syntax, `pytest` for the pure-function tests.

## Global Constraints

- **After every edit to `_dashboard.py`, run** `.venv/Scripts/python.exe -m pytest tests/test_export.py::test_dashboard_javascript_is_syntactically_valid` — one JS syntax error yields a completely blank live page.
- **Pure, testable logic goes above `function bootApp(DATA){`** (`_dashboard.py:630`), same discipline as `defaultMatchesMode`/`pickDivision`/`codeLookup`. A function belongs there only if it has zero dependency on anything declared inside `bootApp` (no `esc`, `el`, `rcChip`, `DIVS`/`VIEWS` as closed-over globals, or any DOM access) — pass everything it needs as parameters instead.
- **No new dependencies, no build step.** Reuse `el`, `esc`, `tag`, `rcChip`, `wipedTag`, `codeDead`, `bansOrdered`, `compRow`, `segOrder`, `rosterHTML`, `dshort`, existing CSS variables (`--surface`, `--surface2`, `--line`, `--line2`, `--good`, `--faint`, `--muted`, `--accent`).
- **`mypy faceit_sync` / full `pytest`** run once at the end (Task 4), not per-task — these edits are inside `HTML_TEMPLATE`'s string literal, which mypy doesn't parse.
- **Roster data has no hero/assists/mitigation fields** (`export.py:404-414`): only `nick`, `role`, `cap`, `e`, `d`, `dmg`, `heal`. Do not invent columns the data doesn't carry — the detail page's player panel reuses `rosterHTML(g)` exactly as it renders today, just always-visible instead of behind a toggle.
- **`m.id` is unique only within its division** (`DIVS[cid].matches`), not globally — every cross-division match lookup goes through `divisionOfMatch`, mirroring the existing team-lookup loop used by `gotoScout`/`#scout=`/`#prep=` (`_dashboard.py:1312-1319`, `:3019-3021`).

---

### Task 1: Pure helpers — `divisionOfMatch`, `mapPipClass`, `scoutedCount`

**Files:**
- Modify: `faceit_sync/_dashboard.py` (insert above `bootApp`, after `codesFor`)
- Test: `tests/test_dashboard_logic.py` (append)

**Interfaces:**
- Produces: `divisionOfMatch(divs, matchId)` → the owning division id (`string`) or `null`. `divs` is the `DIVS` shape: `{[cid]: {matches:[{id,...}]}}`.
- Produces: `mapPipClass(g)` → `'win'`, `'loss'`, or `''`. `g` is a game object with `winner_faction` (`'faction1'`/`'faction2'`/falsy). Win/loss is always relative to `faction1` (the left-listed team on a match card).
- Produces: `scoutedCount(m, capturedIds)` → `{done, total}`. `m` is a match with `.id` and `.games` (each `{game_no, map}`); `total` counts games with a truthy `map`; `done` counts how many of those have `` `${m.id}:${g.game_no}` `` in `capturedIds` (a `Set`).
- Consumed by: Task 2 (`divisionOfMatch`, via `openMatch`/`init`'s `match=` branch) and Task 3 (`mapPipClass`, `scoutedCount`, via the rewritten `matchCard`).

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_dashboard_logic.py`:

```python
# --- match detail page: pure helpers ---------------------------------------
# divisionOfMatch/mapPipClass/scoutedCount are pure data transforms (no DOM,
# no esc/el/CAPTURED), so they're declared above bootApp and directly
# testable here, same discipline as codeLookup/codesFor.

_DIVS = "{a:{matches:[{id:'m1'}]}, b:{matches:[{id:'m2'},{id:'m3'}]}}"


def test_division_of_match_finds_the_owning_division(tmp_path) -> None:
    assert _run(f"return divisionOfMatch({_DIVS},'m2');", tmp_path) == "b"


def test_division_of_match_returns_null_for_an_unknown_id(tmp_path) -> None:
    assert _run(f"return divisionOfMatch({_DIVS},'nope');", tmp_path) is None


def test_map_pip_class_is_win_when_faction1_won(tmp_path) -> None:
    got = _run("return mapPipClass({winner_faction:'faction1'});", tmp_path)
    assert got == "win"


def test_map_pip_class_is_loss_when_faction2_won(tmp_path) -> None:
    got = _run("return mapPipClass({winner_faction:'faction2'});", tmp_path)
    assert got == "loss"


def test_map_pip_class_is_empty_with_no_winner(tmp_path) -> None:
    got = _run("return mapPipClass({winner_faction:null});", tmp_path)
    assert got == ""


_SCOUT_MATCH = ("{id:'m1',games:[{game_no:1,map:'Ilios'},{game_no:2,map:'Oasis'},"
                "{game_no:3,map:null}]}")   # game 3: not played (series ended 2-0)


def test_scouted_count_only_counts_played_maps(tmp_path) -> None:
    got = _run(f"return scoutedCount({_SCOUT_MATCH}, new Set());", tmp_path)
    assert got == {"done": 0, "total": 2}


def test_scouted_count_counts_captured_games(tmp_path) -> None:
    got = _run(
        f"return scoutedCount({_SCOUT_MATCH}, new Set(['m1:1']));", tmp_path
    )
    assert got == {"done": 1, "total": 2}
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/Scripts/python.exe -m pytest tests/test_dashboard_logic.py -k "division_of_match or map_pip_class or scouted_count" -v`
Expected: FAIL — `divisionOfMatch is not defined` (node ReferenceError).

- [ ] **Step 3: Add the pure functions**

In `faceit_sync/_dashboard.py`, find:

```
// Resolve a Set/array of 'mid:gno' keys to their code rows via codeLookup's
// Map, newest first. A key with no match (a code that wiped, or a lookup
// built narrower than the gk set) is silently dropped, not guessed.
function codesFor(gkSet, lookup){
  return [...gkSet].map(k=>lookup.get(k)).filter(Boolean)
    .sort((a,b)=>String(b.when||'').localeCompare(String(a.when||'')));
}

// The whole app runs inside bootApp(DATA); DATA arrives either inlined above
```

Replace with:

```
// Resolve a Set/array of 'mid:gno' keys to their code rows via codeLookup's
// Map, newest first. A key with no match (a code that wiped, or a lookup
// built narrower than the gk set) is silently dropped, not guessed.
function codesFor(gkSet, lookup){
  return [...gkSet].map(k=>lookup.get(k)).filter(Boolean)
    .sort((a,b)=>String(b.when||'').localeCompare(String(a.when||'')));
}

// Match detail page: a match id is unique only within its own division
// (DIVS[cid].matches), so a cross-division link (the Scout-a-team rail, or a
// shared #match= URL) needs to find which division owns it before switching
// CURRENT_VIEW — the same move gotoScout already makes for a team name.
function divisionOfMatch(divs, matchId){
  for(const cid in divs){ if((divs[cid].matches||[]).some(m=>m.id===matchId)) return cid; }
  return null;
}
// The compact match card's per-map pip: win/loss is always read relative to
// faction1 (the team listed first on the card), so one card's pips read
// consistently even though "win" has no meaning without a fixed side.
function mapPipClass(g){
  if(g.winner_faction==='faction1') return 'win';
  if(g.winner_faction==='faction2') return 'loss';
  return '';
}
// Roll up per-game "scouted" (owscout has a captured comp for this game) into
// one N/total for the compact card, in place of a tag per map.
function scoutedCount(m, capturedIds){
  const played=(m.games||[]).filter(g=>g.map);
  const done=played.filter(g=>capturedIds.has(m.id+':'+g.game_no)).length;
  return {done, total:played.length};
}

// The whole app runs inside bootApp(DATA); DATA arrives either inlined above
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv/Scripts/python.exe -m pytest tests/test_dashboard_logic.py -k "division_of_match or map_pip_class or scouted_count" -v`
Expected: 7 passed.

- [ ] **Step 5: Run the JS-syntax gate**

Run: `.venv/Scripts/python.exe -m pytest tests/test_export.py::test_dashboard_javascript_is_syntactically_valid -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add faceit_sync/_dashboard.py tests/test_dashboard_logic.py
git commit -m "dashboard: add divisionOfMatch/mapPipClass/scoutedCount pure helpers"
```

---

### Task 2: Match detail page + routing

**Files:**
- Modify: `faceit_sync/_dashboard.py`

**Interfaces:**
- Consumes: `divisionOfMatch` (Task 1); `el`, `esc`, `tag`, `dshort`, `rcChip`, `wipedTag`, `codeDead`, `bansOrdered`, `compRow`, `segOrder`, `rosterHTML`, `CAPTURED`, `DATA.owscout_pergame`, `recomputeDivision`, `updateHeader` (all existing, `bootApp`-scoped).
- Produces: `let MATCH_ID` (module state). `findMatch(matchId)` → the match object in the *current* view, or `null`. `openMatch(matchId)` → switches to the owning division if needed and opens the detail page. `gamePanel(m, g)` → one map's full detail (`Element`). `renderMatchDetail(m)` → the whole page (`Element`). A `'matchdetail'` pseudo-tab id understood by `show`/`hashFor`/`init`.
- Consumed by: Task 3 (`matchCard`'s click handler calls `openMatch`).

Nothing links to `openMatch`/`'matchdetail'` yet after this task — it's reachable by hand-typing `#match=<id>` in the address bar (verified in Step 6) or from the browser console. Task 3 wires the actual click.

- [ ] **Step 1: Add `MATCH_ID` state**

Find:

```
let SCOUT_TEAM = null;   // set per division by recomputeDivision()
let SCOUT_PREP=false;       // scout tab: full detail vs the condensed prep sheet
const PLANNED={};           // counter-scout: team -> Set of planned hero names
```

Replace with:

```
let SCOUT_TEAM = null;   // set per division by recomputeDivision()
let SCOUT_PREP=false;       // scout tab: full detail vs the condensed prep sheet
let MATCH_ID=null;          // match detail page: which match, within the active division
const PLANNED={};           // counter-scout: team -> Set of planned hero names
```

- [ ] **Step 2: Add `findMatch` and `openMatch`**

Find the whole `gotoScout` function and the blank line after it:

```
function gotoScout(team){
  // If the team isn't in the active view (e.g. click from a combined view),
  // switch to the single division that knows it — same lookup the hash nav uses.
  if(!(D().team_names||[]).includes(team)){
    for(const v of VIEWS){
      if(v.divisions.length===1 && (DIVS[v.divisions[0]].team_names||[]).includes(team)){
        CURRENT_VIEW=v.id; recomputeDivision(); updateHeader();
        const dsel=document.getElementById('division'); if(dsel) dsel.value=v.id;
        break;
      }
    }
  }
  SCOUT_TEAM=team; show('scout');
}

function renderOverview(){
```

Replace with:

```
function gotoScout(team){
  // If the team isn't in the active view (e.g. click from a combined view),
  // switch to the single division that knows it — same lookup the hash nav uses.
  if(!(D().team_names||[]).includes(team)){
    for(const v of VIEWS){
      if(v.divisions.length===1 && (DIVS[v.divisions[0]].team_names||[]).includes(team)){
        CURRENT_VIEW=v.id; recomputeDivision(); updateHeader();
        const dsel=document.getElementById('division'); if(dsel) dsel.value=v.id;
        break;
      }
    }
  }
  SCOUT_TEAM=team; show('scout');
}

// A match id is only unique within its own division (see divisionOfMatch),
// so findMatch assumes CURRENT_VIEW is already correct — true by the time
// it's called, since openMatch/init's match= branch always resolve the
// division first.
function findMatch(matchId){ return (D().matches||[]).find(m=>m.id===matchId)||null; }
function openMatch(matchId){
  const cid=divisionOfMatch(DIVS, matchId);
  if(cid){
    const v=VIEWS.find(v=>v.divisions.length===1&&v.divisions[0]===cid);
    if(v){ CURRENT_VIEW=v.id; recomputeDivision(); updateHeader();
      const dsel=document.getElementById('division'); if(dsel) dsel.value=v.id; }
  }
  MATCH_ID=matchId; show('matchdetail');
}

function renderOverview(){
```

- [ ] **Step 3: Run the JS-syntax gate**

Run: `.venv/Scripts/python.exe -m pytest tests/test_export.py::test_dashboard_javascript_is_syntactically_valid -v`
Expected: PASS.

- [ ] **Step 4: Add `gamePanel` and `renderMatchDetail`**

Find (the end of the still-unmodified `matchCard`, and the start of `barList`):

```
    const ros=el(`<div class="hidden">${rosterHTML(g)}</div>`);
    gEl.appendChild(ros);
    const toggle=gEl.querySelector('.game-hd');
    toggle.onclick=(e)=>{ if(e.target.closest('.rc')) return;   // let replay-code copy
      const open=ros.classList.toggle('hidden')===false;
      gEl.querySelector('.rtog').textContent=open?'▾ rosters':'▸ rosters'; };
    c.appendChild(gEl);
  });
  return c;
}

// horizontal bar list. items:[{label(html), value, color?}]
```

Replace with:

```
    const ros=el(`<div class="hidden">${rosterHTML(g)}</div>`);
    gEl.appendChild(ros);
    const toggle=gEl.querySelector('.game-hd');
    toggle.onclick=(e)=>{ if(e.target.closest('.rc')) return;   // let replay-code copy
      const open=ros.classList.toggle('hidden')===false;
      gEl.querySelector('.rtog').textContent=open?'▾ rosters':'▸ rosters'; };
    c.appendChild(gEl);
  });
  return c;
}

// One map's full detail: header (map/score/side/code/scouted), bans, opening
// comps, and the roster/stat table — always visible (no toggle; this is
// already the detail view, nothing left to progressively disclose). Used by
// the match detail page's tabs (renderMatchDetail below). matchCard still has
// its own copy of this rendering for now — Task 3 removes it once the
// compact card no longer needs it, so this file is never left duplicating
// nothing (each task leaves a working, testable page).
function gamePanel(m,g){
  const gEl=el(`<div class="game"></div>`);
  gEl.appendChild(el(`<div class="game-hd"><span class="gno">M${g.game_no}</span>`+
    `<b>${esc(g.map)}</b> ${tag(g.map_category||'')} <span class="tnum">${esc(g.f1)}–${esc(g.f2)}</span>`+
    `<span class="muted">→ ${esc(g.winner_team||'?')}</span>`+
    (g.was_restarted?tag('veto disrupted','warn'):'')+
    (CAPTURED.has(m.id+':'+g.game_no)?tag('scouted','ok'):'')+
    `<span style="margin-left:auto;display:inline-flex;gap:10px;align-items:center">`+
      (g.demo_code?(codeDead(m.finished_at)?wipedTag:rcChip(g.demo_code))
        :'<span class="faint" style="font-size:11.5px">no replay</span>')+
      `</span></div>`));
  gEl.appendChild(el(`<div class="bans">${bansOrdered(g)}</div>`));
  const pg=(DATA.owscout_pergame||{})[m.id+':'+g.game_no];
  if(pg && Object.keys(pg).length){
    const teams=Object.keys(pg).sort((a,b)=>((a===m.f1?0:a===m.f2?1:2)-(b===m.f1?0:b===m.f2?1:2)));
    const order=segOrder(pg);
    const single=order.length===1 && order[0]==='map';
    const teamRow=(tn,c)=>`<div class="gcteam"><span class="gcname" title="${esc(tn)}">${esc(tn)}</span>`+
      `${c&&c.length?compRow(c):'<span class="faint">—</span>'}</div>`;
    const box=el(`<div class="gamecomps"></div>`);
    if(single){
      const seg=el(`<div class="gcseg"></div>`);
      teams.forEach(tn=>seg.appendChild(el(teamRow(tn,(pg[tn]||{}).map))));
      box.appendChild(seg);
    } else {
      order.forEach(sg=>{ const seg=el(`<div class="gcseg"></div>`);
        seg.appendChild(el(`<div class="gcseglab">${esc(sg)}</div>`));
        teams.forEach(tn=>seg.appendChild(el(teamRow(tn,(pg[tn]||{})[sg]))));
        box.appendChild(seg); });
    }
    gEl.appendChild(box);
  }
  gEl.appendChild(el(rosterHTML(g)));
  return gEl;
}
// The match detail page: header (teams/score/tags, same as the compact
// card's), a back link, a tab per played map, and the selected map's panel.
function renderMatchDetail(m){
  const wrap=el(`<div class="card match matchdetail"></div>`);
  if(!m){ wrap.appendChild(el(`<p class="note" style="padding:16px">Match not found.</p>`)); return wrap; }
  const back=el(`<a class="backlink" href="#matches">‹ Matches</a>`);
  back.onclick=(e)=>{ e.preventDefault(); show('matches'); };
  wrap.appendChild(back);
  const w1=m.winner==='faction1', w2=m.winner==='faction2';
  const teamName=(name,cls)=> name
    ? `<span class="${cls} tscout" data-scout="${esc(name)}" title="Scout ${esc(name)}">${esc(name)}</span>`
    : `<span class="${cls}">?</span>`;
  wrap.appendChild(el(`<div class="hd"><div class="teams">${teamName(m.f1,w1?'win':'lose')}`+
    `<span class="score">${esc(m.series)}</span>${teamName(m.f2,w2?'win':'lose')}</div>`+
    `<div>${m.walkover?tag('walkover','bad'):(m.forfeit?tag('forfeit','bad'):'')} `+
    `${m.finished_at?tag(dshort(m.finished_at)):''} ${tag('R'+m.round+' · G'+m.group)}</div></div>`));
  const games=m.games.filter(g=>g.map);
  if(!games.length){ wrap.appendChild(el(`<p class="note" style="padding:0 16px 16px">No maps played.</p>`)); return wrap; }
  const tabbar=el(`<div class="wsel maptabs"></div>`);
  const panel=el(`<div></div>`);
  let active=games[0].game_no;
  function draw(){
    [...tabbar.children].forEach(b=>b.classList.toggle('selA', +b.dataset.gno===active));
    panel.innerHTML=''; panel.appendChild(gamePanel(m, games.find(g=>g.game_no===active)));
  }
  games.forEach(g=>{
    const b=el(`<span class="wbtn" data-gno="${g.game_no}">M${g.game_no} ${esc(g.map)}${CAPTURED.has(m.id+':'+g.game_no)?' ✓':''}</span>`);
    b.onclick=()=>{ active=g.game_no; draw(); };
    tabbar.appendChild(b);
  });
  wrap.append(tabbar, panel);
  draw();
  return wrap;
}

// horizontal bar list. items:[{label(html), value, color?}]
```

- [ ] **Step 5: Wire `hashFor`, `show`, and `init`**

Find:

```
function hashFor(id){
  if(id==='scout'&&SCOUT_TEAM) return (SCOUT_PREP?'prep=':'scout=')+encodeURIComponent(SCOUT_TEAM);
  return id;
}
function show(id){
  document.querySelectorAll('nav button').forEach(b=>b.classList.toggle('active',b.dataset.id===id));
  const c=document.getElementById('content'); c.innerHTML=''; c.appendChild(TABS.find(t=>t.id===id).render());
  try{window.scrollTo(0,0)}catch(e){}
  const h=hashFor(id); if(location.hash!=='#'+h) location.hash=h;
}
```

Replace with:

```
function hashFor(id){
  if(id==='matchdetail'&&MATCH_ID) return 'match='+encodeURIComponent(MATCH_ID);
  if(id==='scout'&&SCOUT_TEAM) return (SCOUT_PREP?'prep=':'scout=')+encodeURIComponent(SCOUT_TEAM);
  return id;
}
function show(id){
  const navId = id==='matchdetail' ? 'matches' : id;   // no dedicated nav entry - it's a drill-in under Matches
  document.querySelectorAll('nav button').forEach(b=>b.classList.toggle('active',b.dataset.id===navId));
  const c=document.getElementById('content'); c.innerHTML='';
  if(id==='matchdetail'){
    const m=findMatch(MATCH_ID);
    if(!m){ show('matches'); return; }   // stale/unresolvable link - land on the list, not a blank page
    c.appendChild(renderMatchDetail(m));
  } else {
    c.appendChild(TABS.find(t=>t.id===id).render());
  }
  try{window.scrollTo(0,0)}catch(e){}
  const h=hashFor(id); if(location.hash!=='#'+h) location.hash=h;
}
```

Find:

```
  if(start.startsWith('scout=')){
    const team=start.slice(6);
    // Find the division that knows this team; a combined view would work too,
    // but the single division is the page people mean when they share a link.
    for(const v of VIEWS){
      if(v.divisions.length===1 && (DIVS[v.divisions[0]].team_names||[]).includes(team)){
        CURRENT_VIEW=v.id; recomputeDivision(); updateHeader();
        document.getElementById('division').value=v.id;
        break;
      }
    }
    if((D().team_names||[]).includes(team)){ SCOUT_TEAM=team; show('scout'); return; }
  }
  // 'playoffs' and 'sim' were their own tabs before this redesign; a link
  // bookmarked from before still needs to resolve to real content, not fall
  // through to Overview.
  if(start==='playoffs'){ MATCHES_MODE='playoffs'; MATCHES_MODE_SET=true; show('matches'); return; }
```

Replace with:

```
  if(start.startsWith('scout=')){
    const team=start.slice(6);
    // Find the division that knows this team; a combined view would work too,
    // but the single division is the page people mean when they share a link.
    for(const v of VIEWS){
      if(v.divisions.length===1 && (DIVS[v.divisions[0]].team_names||[]).includes(team)){
        CURRENT_VIEW=v.id; recomputeDivision(); updateHeader();
        document.getElementById('division').value=v.id;
        break;
      }
    }
    if((D().team_names||[]).includes(team)){ SCOUT_TEAM=team; show('scout'); return; }
  }
  if(start.startsWith('match=')){
    const mid=start.slice(6);
    const cid=divisionOfMatch(DIVS, mid);
    if(cid){
      const v=VIEWS.find(v=>v.divisions.length===1&&v.divisions[0]===cid);
      if(v){ CURRENT_VIEW=v.id; recomputeDivision(); updateHeader();
        document.getElementById('division').value=v.id; }
    }
    MATCH_ID=mid; show('matchdetail'); return;
  }
  // 'playoffs' and 'sim' were their own tabs before this redesign; a link
  // bookmarked from before still needs to resolve to real content, not fall
  // through to Overview.
  if(start==='playoffs'){ MATCHES_MODE='playoffs'; MATCHES_MODE_SET=true; show('matches'); return; }
```

- [ ] **Step 6: Add CSS for the detail page**

Find:

```
.rosters{display:grid;grid-template-columns:1fr 1fr;gap:14px;margin-top:10px}
@media (max-width:640px){.rosters{grid-template-columns:1fr}}
```

Replace with:

```
.rosters{display:grid;grid-template-columns:1fr 1fr;gap:14px;margin-top:10px}
@media (max-width:640px){.rosters{grid-template-columns:1fr}}
.backlink{display:block;padding:14px 16px 0;margin:0;color:var(--muted);text-decoration:none;font-size:13px}
.backlink:hover{color:var(--accent)}
.maptabs{padding:0 16px 12px}
```

- [ ] **Step 7: Run the JS-syntax gate**

Run: `.venv/Scripts/python.exe -m pytest tests/test_export.py::test_dashboard_javascript_is_syntactically_valid -v`
Expected: PASS.

- [ ] **Step 8: Manual check — the route works standalone**

```bash
.venv/Scripts/python.exe -m faceit_sync.cli export --format html --out dashboard.html
```

Open `dashboard.html` in a browser, go to the Matches tab, open the browser
console, and run:

```js
openMatch(document.querySelector('.match .tscout').dataset.scout && MATCHES_RECENT[0].id)
```

(simplest real check: just run `openMatch(MATCHES_RECENT[0].id)` in the
console). Confirm: the page shows the new detail layout (back link, header,
map tabs, bans/comps/rosters for the first map), clicking a different tab
switches maps, and the back link returns to the Matches tab. `matchCard` is
untouched by this task, so the Matches list itself still looks exactly as it
did before.

- [ ] **Step 9: Commit**

```bash
git add faceit_sync/_dashboard.py
git commit -m "dashboard: add match detail page (renderMatchDetail) + #match= routing"
```

---

### Task 3: Compact match card

**Files:**
- Modify: `faceit_sync/_dashboard.py`

**Interfaces:**
- Consumes: `mapPipClass`, `scoutedCount` (Task 1); `openMatch` (Task 2); `el`, `esc`, `tag`, `dshort`, `rcChip`, `wipedTag`, `codeDead`, `CAPTURED` (existing).
- Produces: `matchCard(m)` unchanged in name/signature — its two existing call sites (`_dashboard.py:2219`, `:2924`, the Scout-a-team rail and the Matches tab list) need no changes.

- [ ] **Step 1: Rewrite `matchCard`**

Find the complete current function:

```
function matchCard(m){
  const c=el(`<div class="card match"></div>`);
  const w1=m.winner==='faction1',w2=m.winner==='faction2';
  // Team names double as click-to-scout links (hover-only underline — a resting
  // dotted line under every name would clutter this dense list).
  const teamName=(name,cls)=> name
    ? `<span class="${cls} tscout" data-scout="${esc(name)}" title="Scout ${esc(name)}">${esc(name)}</span>`
    : `<span class="${cls}">?</span>`;
  c.appendChild(el(`<div class="hd"><div class="teams">${teamName(m.f1,w1?'win':'lose')}`+
    `<span class="score">${esc(m.series)}</span>${teamName(m.f2,w2?'win':'lose')}</div>`+
    `<div>${m.walkover?tag('walkover','bad'):(m.forfeit?tag('forfeit','bad'):'')} `+
    // When it was played: a comp read from a 6-week-old match is weaker evidence
    // than last week's, and nothing else on the card says how old it is.
    `${m.finished_at?tag(dshort(m.finished_at)):''} ${tag('R'+m.round+' · G'+m.group)}</div></div>`));
  m.games.filter(g=>g.map).forEach(g=>{
    const gEl=el(`<div class="game"></div>`);
    gEl.appendChild(el(`<div class="game-hd"><span class="gno">M${g.game_no}</span>`+
      `<b>${esc(g.map)}</b> ${tag(g.map_category||'')} <span class="tnum">${esc(g.f1)}–${esc(g.f2)}</span>`+
      `<span class="muted">→ ${esc(g.winner_team||'?')}</span>`+
      (g.was_restarted?tag('veto disrupted','warn'):'')+
      (CAPTURED.has(m.id+':'+g.game_no)?tag('scouted','ok'):'')+
      `<span style="margin-left:auto;display:inline-flex;gap:10px;align-items:center">`+
        (g.demo_code?(codeDead(m.finished_at)?wipedTag:rcChip(g.demo_code))
          :'<span class="faint" style="font-size:11.5px">no replay</span>')+
        `<span class="faint rtog">▸ rosters</span></span></div>`));
    gEl.appendChild(el(`<div class="bans">${bansOrdered(g)}</div>`));
    // Captured opening comps per segment: sub-map (Control), attack/defend
    // (Escort/Hybrid), or the whole map (Push/Flashpoint). Only when captured.
    const pg=(DATA.owscout_pergame||{})[m.id+':'+g.game_no];
    if(pg && Object.keys(pg).length){
      // Both teams' opening comps per segment. In the narrow rail they STACK
      // (team over team) so each comp gets the full width instead of two 5-hero
      // rows colliding side by side and overflowing.
      const teams=Object.keys(pg).sort((a,b)=>((a===m.f1?0:a===m.f2?1:2)-(b===m.f1?0:b===m.f2?1:2)));
      const order=segOrder(pg);
      const single=order.length===1 && order[0]==='map';
      const teamRow=(tn,c)=>`<div class="gcteam"><span class="gcname" title="${esc(tn)}">${esc(tn)}</span>`+
        `${c&&c.length?compRow(c):'<span class="faint">—</span>'}</div>`;
      const box=el(`<div class="gamecomps"></div>`);
      if(single){
        const seg=el(`<div class="gcseg"></div>`);
        teams.forEach(tn=>seg.appendChild(el(teamRow(tn,(pg[tn]||{}).map))));
        box.appendChild(seg);
      } else {
        order.forEach(sg=>{ const seg=el(`<div class="gcseg"></div>`);
          seg.appendChild(el(`<div class="gcseglab">${esc(sg)}</div>`));
          teams.forEach(tn=>seg.appendChild(el(teamRow(tn,(pg[tn]||{})[sg]))));
          box.appendChild(seg); });
      }
      gEl.appendChild(box);
    }
    const ros=el(`<div class="hidden">${rosterHTML(g)}</div>`);
    gEl.appendChild(ros);
    const toggle=gEl.querySelector('.game-hd');
    toggle.onclick=(e)=>{ if(e.target.closest('.rc')) return;   // let replay-code copy
      const open=ros.classList.toggle('hidden')===false;
      gEl.querySelector('.rtog').textContent=open?'▾ rosters':'▸ rosters'; };
    c.appendChild(gEl);
  });
  return c;
}
```

Replace with:

```
// The compact "at a glance" match card: header (teams/score/tags) + one pip
// per played map. Everything the old card used to expand inline (bans, per-
// segment comps, rosters) now lives on the match detail page - click the
// card (anywhere except a team name or a replay-code chip) to open it.
function matchCard(m){
  const c=el(`<div class="card match mrow"></div>`);
  const w1=m.winner==='faction1',w2=m.winner==='faction2';
  // Team names double as click-to-scout links (hover-only underline — a resting
  // dotted line under every name would clutter this dense list).
  const teamName=(name,cls)=> name
    ? `<span class="${cls} tscout" data-scout="${esc(name)}" title="Scout ${esc(name)}">${esc(name)}</span>`
    : `<span class="${cls}">?</span>`;
  c.appendChild(el(`<div class="hd"><div class="teams">${teamName(m.f1,w1?'win':'lose')}`+
    `<span class="score">${esc(m.series)}</span>${teamName(m.f2,w2?'win':'lose')}</div>`+
    `<div>${m.walkover?tag('walkover','bad'):(m.forfeit?tag('forfeit','bad'):'')} `+
    // When it was played: a comp read from a 6-week-old match is weaker evidence
    // than last week's, and nothing else on the card says how old it is.
    `${m.finished_at?tag(dshort(m.finished_at)):''} ${tag('R'+m.round+' · G'+m.group)}</div></div>`));
  const games=m.games.filter(g=>g.map);
  if(games.length){
    const pips=el(`<div class="mpips"></div>`);
    games.forEach(g=>{
      const codeBit=g.demo_code?(codeDead(m.finished_at)?wipedTag:rcChip(g.demo_code)):'';
      pips.appendChild(el(`<span class="mpip ${mapPipClass(g)}"><b>${esc(g.map)}</b> `+
        `<span class="tnum">${esc(g.f1)}–${esc(g.f2)}</span>${codeBit}</span>`));
    });
    c.appendChild(pips);
    const sc=scoutedCount(m, CAPTURED);
    if(sc.total) c.appendChild(el(`<p class="note mscouted">🎥 ${sc.done}/${sc.total} scouted</p>`));
  }
  // Whole-card click opens the detail page, except a team name (click-to-scout)
  // or a replay-code chip (click-to-copy) inside a pip — same guard pattern the
  // old per-game rosters toggle used for `.rc`.
  c.onclick=(e)=>{ if(e.target.closest('[data-scout]')||e.target.closest('.rc')) return; openMatch(m.id); };
  return c;
}
```

- [ ] **Step 2: Run the JS-syntax gate**

Run: `.venv/Scripts/python.exe -m pytest tests/test_export.py::test_dashboard_javascript_is_syntactically_valid -v`
Expected: PASS.

- [ ] **Step 3: Add CSS for the compact card's pips**

Find (the lines Task 2 Step 6 just added):

```
.backlink{display:block;padding:14px 16px 0;margin:0;color:var(--muted);text-decoration:none;font-size:13px}
.backlink:hover{color:var(--accent)}
.maptabs{padding:0 16px 12px}
```

Replace with:

```
.backlink{display:block;padding:14px 16px 0;margin:0;color:var(--muted);text-decoration:none;font-size:13px}
.backlink:hover{color:var(--accent)}
.maptabs{padding:0 16px 12px}
.mrow{cursor:pointer}
.mpips{display:flex;gap:8px;flex-wrap:wrap;padding:0 16px 12px}
.mpip{display:inline-flex;align-items:center;gap:6px;font-size:12.5px;padding:5px 9px;border-radius:7px;
  background:var(--surface2);border:1px solid var(--line2)}
.mpip.win{border-color:color-mix(in srgb,var(--good) 45%,var(--line2))}
.mpip.loss{color:var(--faint)}
.mscouted{padding:0 16px 12px;margin:0}
```

- [ ] **Step 4: Run the JS-syntax gate**

Run: `.venv/Scripts/python.exe -m pytest tests/test_export.py::test_dashboard_javascript_is_syntactically_valid -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add faceit_sync/_dashboard.py
git commit -m "dashboard: shrink matchCard to a compact at-a-glance row"
```

---

### Task 4: Full verification pass

**Files:** None modified — verification only.

- [ ] **Step 1: Full test suite**

Run: `.venv/Scripts/python.exe -m pytest`
Expected: all pass.

- [ ] **Step 2: Type check**

Run: `.venv/Scripts/python.exe -m mypy faceit_sync`
Expected: clean — all edits are inside the `HTML_TEMPLATE` string literal.

- [ ] **Step 3: Rebuild and visual/interaction check**

```bash
.venv/Scripts/python.exe -m faceit_sync.cli export --format html --out dashboard.html
```

Using headless Edge (`--screenshot=FILE`, **not** `--dump-dom` — see
CLAUDE.md), screenshot and confirm:

1. **Matches tab**: cards are now compact — team/score header + a row of map
   pips (map name, round score, win/loss color, a code chip where a replay
   exists) + an "N/M scouted" line. No bans/comps/rosters inline.
2. **A match detail page** (click a card, or navigate to
   `file:///…/dashboard.html#match=<a real match id from MATCHES_RECENT>`):
   back link, header matching the card's, a tab per played map, and the
   selected tab showing bans, opening comps (if captured), and the roster
   table — all always visible, no toggle.
3. Click a different map tab: content swaps to that map, others don't.
4. Click the back link: returns to the Matches tab.
5. **Scout-a-team rail** (`#scout=<team>`): the "Matches" sticky rail also
   shows the compact cards now, same click-through behavior.
6. Click a team name on a compact card: navigates to that team's Scout page
   (not the match detail page) — confirms the click-guard works.
7. Click a replay-code chip on a pip: copies the code (`rc.textContent`
   flashes "copied ✓"), does **not** navigate to the detail page.

- [ ] **Step 4: Clean up the local preview build**

```bash
rm -f dashboard.html
```

- [ ] **Step 5: Final commit (only if Step 3 surfaced fixes)**

If the visual pass required touch-ups, commit them now with a message
describing what it caught. Otherwise Tasks 1-3's commits are the complete
change set.

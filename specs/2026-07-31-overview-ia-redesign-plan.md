# Overview & Navigation Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reorganize the live dashboard's Overview tab and top-level navigation so a cold visitor gets oriented immediately and the capture/contribute funnel is prominent, per the design in `specs/2026-07-31-overview-ia-redesign-design.md`.

**Architecture:** Entirely a client-side edit to the single JS template string (`HTML_TEMPLATE`) in `faceit_sync/_dashboard.py` — no Python logic, schema, or export changes. Adds one new pure decision helper (testable per the existing `capSample`/`pickDivision` pattern), restructures `renderOverview`, adds a static "hero" strip to the page shell, folds the Playoffs tab into Matches via a mode toggle, and relegates the Draft simulator into a collapsible section on Scout a team.

**Tech Stack:** Python 3.12 (`faceit_sync/_dashboard.py`, a big Python string), vanilla JS (no framework, no build step), `node --check` for JS syntax validation, `pytest` for the pure-function tests.

## Global Constraints

- **`docs/index.html` is the live site; never hand-edit it.** All work happens in `faceit_sync/_dashboard.py`; the site rebuilds via `faceit-sync export` / CI.
- **After every edit to `_dashboard.py`, run** `.venv/Scripts/python.exe -m pytest tests/test_export.py::test_dashboard_javascript_is_syntactically_valid` — the page renders its entire body in JS, so one syntax error (a stray comma, a duplicate `const`) yields a blank page that bracket-balance checks won't catch. Treat this as the gate for every task in this plan, not just the last one.
- **Pure decision logic goes above `function bootApp(DATA){`** (currently line 571), in the same style as `capSample`/`capLabelText`/`coverageState`/`pickDivision` — these are the only parts of the dashboard `pytest` can exercise directly (via `tests/test_dashboard_logic.py`'s `_pure_js()`/`_run()` harness, which runs everything above `bootApp` through `node`). Anything that touches `D()`, `DATA`, or the DOM lives inside `bootApp` and is **not** reachable by that harness — for those, verification is `node --check` (syntax only) plus a manual headless-Edge screenshot, matching this codebase's documented approach (`CLAUDE.md` → "Verifying the dashboard"). Do not invent pytest coverage for DOM-only code; it isn't reachable and the attempt will just be dead code.
- **No new dependencies, no build step, no CSS framework.** Reuse existing CSS classes (`.card`, `.btn`, `.eyebrow`, `.opener`, `.wsel`, `.wbtn`, `.note`) rather than inventing new ones, matching the file's existing convention of composing from a small shared set.
- **`mypy faceit_sync` must stay clean**, though none of these edits touch typed Python code — they're all inside the `HTML_TEMPLATE` string literal, which mypy doesn't parse. Run it once at the end as a sanity check, not per-task.

---

### Task 1: Pure helper — `defaultMatchesMode`

**Files:**
- Modify: `faceit_sync/_dashboard.py:562-565` (insert after `pickDivision`, before `bootApp`)
- Test: `tests/test_dashboard_logic.py` (append new tests)

**Interfaces:**
- Produces: `defaultMatchesMode(playoffsList)` → `'playoffs' | 'played'`. Pure function, no globals. `playoffsList` is the same shape as `D().playoffs` — an array of match objects, each with a `status` field (`'FINISHED'` or a scheduled/other status). Task 3 calls this as `defaultMatchesMode(D().playoffs||[])`.

The Matches tab is getting a `Regular season | Playoffs` toggle (Task 3). Which one is selected by default needs to be a real decision, not a coin flip — and per this codebase's convention (see the module docstring in `tests/test_dashboard_logic.py`), any decision that could mislead a viewer belongs in a pure, directly-tested function, not buried inside a render function.

Rule: default to Playoffs only once real playoff matches exist for the active division (`playoffsList.length > 0`); otherwise default to the regular-season list, since an empty Playoffs view first is a worse landing than an empty toggle button.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_dashboard_logic.py`:

```python
# --- Matches tab default mode --------------------------------------------
# Landing a visitor on an empty "Playoffs" panel is a worse first screen than
# landing them on the (populated) regular-season list, so the toggle should
# only default to Playoffs once real playoff matches exist.

def test_default_matches_mode_is_played_when_no_playoff_matches(tmp_path) -> None:
    got = _run("return defaultMatchesMode([]);", tmp_path)
    assert got == "played"


def test_default_matches_mode_is_playoffs_once_any_playoff_match_exists(tmp_path) -> None:
    got = _run(
        "return defaultMatchesMode([{status:'SCHEDULED'}]);", tmp_path
    )
    assert got == "playoffs"


def test_default_matches_mode_is_playoffs_when_playoffs_are_finished(tmp_path) -> None:
    got = _run(
        "return defaultMatchesMode([{status:'FINISHED'}]);", tmp_path
    )
    assert got == "playoffs"
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/Scripts/python.exe -m pytest tests/test_dashboard_logic.py -k default_matches_mode -v`
Expected: FAIL — `defaultMatchesMode is not defined` (node ReferenceError surfaced as a non-zero exit in `_run`).

- [ ] **Step 3: Add the pure function**

In `faceit_sync/_dashboard.py`, find this exact block (currently lines 555-566):

```
// Which division to open on, given the one remembered from last visit. With more
// than one region live, always opening VIEWS[0] (EMEA Master) makes every NA
// visitor re-pick their region on every visit.
//
// A stored id is only honoured if it STILL EXISTS: divisions come and go between
// seasons, and this page renders its entire body off the active view, so a stale
// id must fall back to the first view rather than leave it dangling.
function pickDivision(storedId, views){
  if(!views || !views.length) return null;
  return views.some(v=>v.id===storedId) ? storedId : views[0].id;
}

// The whole app runs inside bootApp(DATA); DATA arrives either inlined above
```

Replace it with (adds the new function between `pickDivision` and the `bootApp` comment):

```
// Which division to open on, given the one remembered from last visit. With more
// than one region live, always opening VIEWS[0] (EMEA Master) makes every NA
// visitor re-pick their region on every visit.
//
// A stored id is only honoured if it STILL EXISTS: divisions come and go between
// seasons, and this page renders its entire body off the active view, so a stale
// id must fall back to the first view rather than leave it dangling.
function pickDivision(storedId, views){
  if(!views || !views.length) return null;
  return views.some(v=>v.id===storedId) ? storedId : views[0].id;
}

// Matches tab: which mode (Regular season vs Playoffs) opens by default.
// Landing on an empty Playoffs panel is worse than landing on the (populated)
// regular-season list, so only default to Playoffs once real playoff matches
// exist for the active division — finished or scheduled, any status counts.
function defaultMatchesMode(playoffsList){
  return (playoffsList && playoffsList.length) ? 'playoffs' : 'played';
}

// The whole app runs inside bootApp(DATA); DATA arrives either inlined above
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv/Scripts/python.exe -m pytest tests/test_dashboard_logic.py -k default_matches_mode -v`
Expected: 3 passed.

- [ ] **Step 5: Run the JS-syntax gate**

Run: `.venv/Scripts/python.exe -m pytest tests/test_export.py::test_dashboard_javascript_is_syntactically_valid -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add faceit_sync/_dashboard.py tests/test_dashboard_logic.py
git commit -m "dashboard: add defaultMatchesMode pure helper for the upcoming Playoffs/Matches merge"
```

---

### Task 2: Orientation strip + Overview trim

**Files:**
- Modify: `faceit_sync/_dashboard.py` (CSS block, HTML shell, `renderOverview`, `init()`)

**Interfaces:**
- Consumes: `gotoScout`/`show`/`D()` (existing, unchanged signatures), `location.href` navigation to `capture/` (existing pattern from the current Contribute callout).
- Produces: two new DOM ids, `heroScout` and `heroCapture`, wired in `init()`. Nothing downstream depends on new JS functions from this task.

This is one task because trimming Overview's launcher/contribute cards without the hero strip already in place would remove the only way a fresh visitor reaches Scout/Capture — the two changes must land together to keep the page working at every commit.

- [ ] **Step 1: Add the `.hero` CSS rule**

In `faceit_sync/_dashboard.py`, find:

```
.card{background:var(--surface);border:1px solid var(--line);border-radius:10px;padding:12px 14px;box-shadow:none}
```

Replace with:

```
.card{background:var(--surface);border:1px solid var(--line);border-radius:10px;padding:12px 14px;box-shadow:none}
.hero{max-width:min(1500px,96vw);margin:14px auto 0;display:flex;justify-content:space-between;align-items:center;gap:14px;flex-wrap:wrap}
```

- [ ] **Step 2: Add the hero strip markup to the page shell**

Find:

```
</div></div>
<main id="content"></main>
```

Replace with:

```
</div></div>
<div id="hero" class="card hero">
  <span class="note" style="margin:0;font-size:13px">OWDB — FACEIT League scouting, built from real match data + fan-captured comps.</span>
  <div style="display:flex;gap:8px;flex-wrap:wrap">
    <button class="btn" id="heroScout" type="button">Scout a team →</button>
    <button class="btn" id="heroCapture" type="button">Contribute a capture →</button>
  </div>
</div>
<main id="content"></main>
```

- [ ] **Step 3: Wire the hero buttons in `init()`**

Find (inside `function init()`):

```
  const nav=document.getElementById('nav');
  TABS.forEach(t=>{const b=el(`<button data-id="${t.id}">${esc(t.label)}</button>`);b.onclick=()=>show(t.id);nav.appendChild(b);});
  nav.appendChild(el(`<a class="navcap" href="capture/" title="Scout comps in your browser — no install, no exe">＋ Capture comps</a>`));
```

Replace with:

```
  const nav=document.getElementById('nav');
  TABS.forEach(t=>{const b=el(`<button data-id="${t.id}">${esc(t.label)}</button>`);b.onclick=()=>show(t.id);nav.appendChild(b);});
  nav.appendChild(el(`<a class="navcap" href="capture/" title="Scout comps in your browser — no install, no exe">＋ Capture comps</a>`));
  document.getElementById('heroScout').onclick=()=>{ if(!SCOUT_TEAM) SCOUT_TEAM=(D().team_names||[])[0]||null; show('scout'); };
  document.getElementById('heroCapture').onclick=()=>{ location.href='capture/'; };
```

- [ ] **Step 4: Trim `renderOverview`**

Find the full current function (`faceit_sync/_dashboard.py`, currently lines 1222-1310):

```
function renderOverview(){
  const s=D().summary, wrap=el(`<div></div>`);

  // Coverage-at-a-glance beats data-health diagnostics: how much of the league
  // is actually scouted is the thing a scout wants to see first.
  const ocs=DATA.owdb_comps||{}, tn=D().team_names;
  const teamsScouted=tn.filter(n=>(((ocs[n]||{}).scout)||{}).games).length;
  const capturedMaps=tn.reduce((a,n)=>a+((((ocs[n]||{}).scout)||{}).games||0),0);
  const tiles=[[nf(s.played_games),'Maps played',`${s.matches} matches`],
    [nf(s.teams),'Teams',`single round-robin`],
    [`${teamsScouted}/${tn.length}`,'Teams scouted',`have captured comps`],
    [nf(capturedMaps),'Comps captured',`maps with hero data`]];
  const g=el(`<div class="grid cols-auto"></div>`);
  tiles.forEach(([v,l,sub])=>g.appendChild(el(`<div class="card tile"><div class="n">${v}</div><div class="l">${l}</div><div class="sub">${sub}</div></div>`)));
  wrap.appendChild(g);

  // Scout launcher
  const launch=el(`<div class="card" style="margin-top:14px"></div>`);
  launch.appendChild(el(`<p class="eyebrow">Prep for a match</p>`));
  const row=el(`<div class="controls"></div>`);
  const sel=el(`<select style="min-width:200px"></select>`);
  D().team_names.forEach(n=>sel.appendChild(el(`<option>${esc(n)}</option>`)));
  const go=el(`<button class="btn">Scout this team →</button>`);
  go.onclick=()=>gotoScout(sel.value);
  row.append(sel,go); launch.appendChild(row);
  wrap.appendChild(launch);

  // Contribute callout: the browser capture tool lives at /capture/ — no install.
  const contrib=el(`<div class="card" style="margin-top:14px;display:flex;justify-content:space-between;align-items:center;gap:12px;flex-wrap:wrap"></div>`);
  contrib.appendChild(el(`<div><p class="eyebrow" style="margin:0 0 2px">Contribute</p><span class="note">Scout comps straight from your browser — no install, no exe. Every capture sharpens the data here.</span></div>`));
  const cbtn=el(`<button class="btn">Capture comps →</button>`); cbtn.onclick=()=>{location.href='capture/';}; contrib.appendChild(cbtn);
  wrap.appendChild(contrib);

  // Scout leaderboard — maps each contributor owns (first-wins credited), the
  // same count the future contribute-or-pay threshold will use. League-wide.
  const contribs=DATA.owdb_contributors||[];
  if(contribs.length){
    const lc=el(`<div class="card" style="margin-top:14px"></div>`);
    lc.appendChild(el(`<p class="eyebrow">Scout leaderboard</p>`));
    lc.appendChild(el(`<p class="note" style="margin:0 0 8px">Maps each scout has contributed this season — every capture sharpens the data here. 🙏</p>`));
    lc.appendChild(el(barList(contribs.slice(0,15).map(c=>({label:esc(c.name),value:c.maps})))));
    const total=contribs.reduce((x,c)=>x+(c.maps||0),0);
    lc.appendChild(el(`<p class="note" style="margin-top:8px">${contribs.length} scout${contribs.length===1?'':'s'} · ${nf(total)} maps captured league-wide.</p>`));
    wrap.appendChild(lc);
  }

  // current meta + standings
  const two=el(`<div class="grid cols-2" style="margin-top:20px"></div>`);
  const win=recent(MATCHES_RECENT,20), a=aggregate(win,null), {from,to}=dateRange(win);
  const banCard=el(`<div class="card"></div>`);
  banCard.appendChild(el(`<p class="eyebrow">Current ban meta · last ${win.length} matches</p>`));
  banCard.appendChild(el(barList(rank(a.bans).slice(0,8).map(([h,n])=>({label:heroChip(h),value:n,color:roleVar(HERO_ROLE[h])})))));
  banCard.appendChild(el(`<p class="note">${dshort(from)} → ${dshort(to)}. See <b>League meta</b> for windows.</p>`));
  const mapCard=el(`<div class="card"></div>`);
  mapCard.appendChild(el(`<p class="eyebrow">Most played maps · last ${win.length} matches</p>`));
  mapCard.appendChild(el(barList(rank(a.mapsPicked).slice(0,8).map(([m,n])=>({label:`${esc(m)} ${tag(MAP_CAT[m]||'')}`,value:n})))));
  two.append(banCard,mapCard); wrap.appendChild(two);

  wrap.appendChild(el(sectionH('Standings')));
  wrap.appendChild(table(
    [{k:'name',label:'Team',html:r=>teamLink(r.name)},{k:'matches',label:'Matches',num:true},{k:'wins',label:'Wins',num:true},
     {k:'win_pct',label:'Win %',num:true,html:r=>pill(r.win_pct+'%',winVar(r.win_pct))}],
    D().teams));
  wrap.appendChild(el(`<p class="note">Veto attribution recovered from FACEIT's durable history feed for ${s.matches_with_attribution}/${s.matches} matches; only walkovers and disrupted vetos lack it.</p>`));

  // Rosters at a glance: the current lineup per team (whoever played the latest
  // match), most-used first, with subs / departed players dimmed below. Straight
  // from FACEIT round_players, so it's there even for un-scouted teams.
  wrap.appendChild(el(sectionH('Rosters at a glance')));
  const prow=(p,dim)=>`<div class="pl"${dim?' style="opacity:.5"':''}>`+
    `<span class="dot bg-${esc(p.role||'')}" title="${esc(p.role||'—')}"></span>`+
    `<span>${esc(p.nick)}</span>`+
    `<span class="st">${p.games} map${p.games===1?'':'s'}</span></div>`;
  const rg=el(`<div class="grid cols-3"></div>`);
  D().teams.forEach(t=>{
    const ros=t.roster||[], cur=ros.filter(p=>p.current), sub=ros.filter(p=>!p.current);
    let body=cur.map(p=>prow(p,false)).join('');
    if(sub.length) body+=`<div class="subhd">also played this season</div>`+sub.map(p=>prow(p,true)).join('');
    const card=el(`<div class="card roster"></div>`);
    card.appendChild(el(`<h4 style="display:flex;justify-content:space-between;align-items:center;gap:8px">`+
      `<span class="tlink" data-scout="${esc(t.name)}" title="Scout ${esc(t.name)}" style="color:var(--fg);font-size:14px;font-weight:660">${esc(t.name)}</span>`+
      pill(t.win_pct+'%',winVar(t.win_pct))+`</h4>`));
    card.appendChild(el(`<div>${body||'<span class="faint">no roster data yet</span>'}</div>`));
    rg.appendChild(card);
  });
  wrap.appendChild(rg);
  wrap.appendChild(el(`<p class="note">Current lineup = players who appeared in the team's most recent match; “map” counts are games played this season. Roles and names are FACEIT's.</p>`));
  return wrap;
}
```

Replace it with the trimmed version (tiles → standings → leaderboard; the launcher, contribute callout, ban/map-meta duplication, and rosters-at-a-glance are cut per the design doc's §2):

```
function renderOverview(){
  const s=D().summary, wrap=el(`<div></div>`);

  // Coverage-at-a-glance beats data-health diagnostics: how much of the league
  // is actually scouted is the thing a scout wants to see first.
  const ocs=DATA.owdb_comps||{}, tn=D().team_names;
  const teamsScouted=tn.filter(n=>(((ocs[n]||{}).scout)||{}).games).length;
  const capturedMaps=tn.reduce((a,n)=>a+((((ocs[n]||{}).scout)||{}).games||0),0);
  const tiles=[[nf(s.played_games),'Maps played',`${s.matches} matches`],
    [nf(s.teams),'Teams',`single round-robin`],
    [`${teamsScouted}/${tn.length}`,'Teams scouted',`have captured comps`],
    [nf(capturedMaps),'Comps captured',`maps with hero data`]];
  const g=el(`<div class="grid cols-auto"></div>`);
  tiles.forEach(([v,l,sub])=>g.appendChild(el(`<div class="card tile"><div class="n">${v}</div><div class="l">${l}</div><div class="sub">${sub}</div></div>`)));
  wrap.appendChild(g);

  wrap.appendChild(el(sectionH('Standings')));
  wrap.appendChild(table(
    [{k:'name',label:'Team',html:r=>teamLink(r.name)},{k:'matches',label:'Matches',num:true},{k:'wins',label:'Wins',num:true},
     {k:'win_pct',label:'Win %',num:true,html:r=>pill(r.win_pct+'%',winVar(r.win_pct))}],
    D().teams));
  wrap.appendChild(el(`<p class="note">Veto attribution recovered from FACEIT's durable history feed for ${s.matches_with_attribution}/${s.matches} matches; only walkovers and disrupted vetos lack it.</p>`));

  // Scout leaderboard — maps each contributor owns (first-wins credited), the
  // same count the future contribute-or-pay threshold will use. League-wide.
  // Below standings, not above: a trust signal for a returning visitor, not
  // orientation info a cold visitor needs first (that's the hero strip above).
  const contribs=DATA.owdb_contributors||[];
  if(contribs.length){
    const lc=el(`<div class="card" style="margin-top:20px"></div>`);
    lc.appendChild(el(`<p class="eyebrow">Scout leaderboard</p>`));
    lc.appendChild(el(`<p class="note" style="margin:0 0 8px">Maps each scout has contributed this season — every capture sharpens the data here. 🙏</p>`));
    lc.appendChild(el(barList(contribs.slice(0,15).map(c=>({label:esc(c.name),value:c.maps})))));
    const total=contribs.reduce((x,c)=>x+(c.maps||0),0);
    lc.appendChild(el(`<p class="note" style="margin-top:8px">${contribs.length} scout${contribs.length===1?'':'s'} · ${nf(total)} maps captured league-wide.</p>`));
    wrap.appendChild(lc);
  }

  return wrap;
}
```

- [ ] **Step 5: Run the JS-syntax gate**

Run: `.venv/Scripts/python.exe -m pytest tests/test_export.py::test_dashboard_javascript_is_syntactically_valid -v`
Expected: PASS.

- [ ] **Step 6: Manual visual check**

```bash
.venv/Scripts/python.exe -m faceit_sync.cli export --format html --out dashboard.html
```

```bash
msedge --headless --screenshot=overview.png "file:///$(pwd)/dashboard.html#overview"
```

Read `overview.png` (via the Read tool) and confirm: the hero strip renders above the tab bar with both buttons, Overview shows only 3 sections (tiles, standings, leaderboard — no launcher/contribute/meta-duplication/rosters cards), and clicking "Scout a team →" / "Contribute a capture →" works (can't verify clicks from a static screenshot — confirm the buttons exist and are visibly styled as clickable; functional click-through is covered by Task 6's fuller pass).

- [ ] **Step 7: Commit**

```bash
git add faceit_sync/_dashboard.py
git commit -m "dashboard: add hero orientation strip, trim Overview to non-redundant sections"
```

---

### Task 3: Fold Playoffs into Matches

**Files:**
- Modify: `faceit_sync/_dashboard.py` (`TABS`, global state near `MATCHES_MODE`, `renderMatches`, `init()`)

**Interfaces:**
- Consumes: `defaultMatchesMode(playoffsList)` from Task 1, `renderPlayoffs()` (existing, unchanged — still returns a `<div>` wrap and handles its own "pick a single division" / "no bracket yet" states internally).
- Produces: `MATCHES_MODE_SET` (new global boolean), a third `modeBar` button, `drawPlayoffs()` (local to `renderMatches`). `TABS` drops its `playoffs` entry — nothing else in the file references `TABS` by exact length, but grep for `'playoffs'` after this task to confirm no dangling references remain (the `init()` hash-fallback handling added in Step 4 is the one intentional exception).

- [ ] **Step 1: Remove the `playoffs` tab and add the `MATCHES_MODE_SET` flag**

Find:

```
const TABS=[
 {id:'overview',label:'Overview',render:renderOverview},
 {id:'scout',label:'Scout a team',render:renderScout},
 {id:'players',label:'Players',render:renderPlayers},
 {id:'sim',label:'Draft simulator',render:renderSim},
 {id:'meta',label:'League meta',render:renderMeta},
 {id:'playoffs',label:'Playoffs',render:renderPlayoffs},
 {id:'matches',label:'Matches',render:renderMatches},
];
```

Replace with (still keeps `sim` for now — Task 4 removes it):

```
const TABS=[
 {id:'overview',label:'Overview',render:renderOverview},
 {id:'scout',label:'Scout a team',render:renderScout},
 {id:'players',label:'Players',render:renderPlayers},
 {id:'sim',label:'Draft simulator',render:renderSim},
 {id:'meta',label:'League meta',render:renderMeta},
 {id:'matches',label:'Matches',render:renderMatches},
];
```

Find:

```
let MATCHES_MODE='played';   // Matches tab: 'played' history vs 'upcoming' fixtures
```

Replace with:

```
let MATCHES_MODE='played';   // Matches tab: 'played' | 'upcoming' | 'playoffs'
let MATCHES_MODE_SET=false;  // whether the user (or a deep link) has explicitly chosen a mode this session — once true, defaultMatchesMode() no longer overrides it on re-render
```

- [ ] **Step 2: Add the third toggle button and the playoffs branch in `renderMatches`**

Find:

```
  // Played history vs upcoming fixtures. A full-season schedule can be large, so
  // upcoming lives in its own view (toggle) rather than stacked on the results.
  const up0=D().upcoming||[];
  const modeBar=el(`<div class="wsel" style="margin:0 2px 12px"></div>`);
  const mkMode=(m,lbl)=>{ const b=el(`<span class="wbtn">${lbl}</span>`); b.onclick=()=>{ MATCHES_MODE=m; draw(); }; return b; };
  modeBar.append(mkMode('played','Played'), mkMode('upcoming',`Upcoming${up0.length?' · '+up0.length:''}`));
```

Replace with:

```
  // Played history vs upcoming fixtures vs the playoff bracket. A full-season
  // schedule can be large, so each lives in its own view (toggle) rather than
  // stacked on the results. Default mode is a real decision (defaultMatchesMode,
  // declared above bootApp) so it's independently testable.
  const up0=D().upcoming||[];
  if(!MATCHES_MODE_SET){ MATCHES_MODE=defaultMatchesMode(D().playoffs||[]); MATCHES_MODE_SET=true; }
  const modeBar=el(`<div class="wsel" style="margin:0 2px 12px"></div>`);
  const mkMode=(m,lbl)=>{ const b=el(`<span class="wbtn">${lbl}</span>`); b.onclick=()=>{ MATCHES_MODE=m; MATCHES_MODE_SET=true; draw(); }; return b; };
  modeBar.append(mkMode('played','Played'), mkMode('upcoming',`Upcoming${up0.length?' · '+up0.length:''}`), mkMode('playoffs','Playoffs'));
```

Find:

```
  function drawPlayed(q){
    // MATCHES_RECENT is newest-first; reverse for oldest-first.
    let shown=MATCHES_RECENT.filter(m=>!q||hay(m).includes(q));
    if(sort.value==='old') shown=[...shown].reverse();
    if(!shown.length){ list.appendChild(el(`<p class="note">No played matches${q?' match your search':''}.</p>`)); return; }
    shown.forEach(m=>list.appendChild(matchCard(m)));
  }
  function draw(){
    const q=(search.value||'').trim().toLowerCase();
    const upMode=(MATCHES_MODE==='upcoming');
    [...modeBar.children].forEach((b,i)=>b.classList.toggle('selA',(i===0)!==upMode));
    note.style.display=upMode?'none':''; sort.style.display=upMode?'none':'';
    list.innerHTML='';
    if(upMode) drawUpcoming(q); else drawPlayed(q);
  }
```

Replace with:

```
  function drawPlayed(q){
    // MATCHES_RECENT is newest-first; reverse for oldest-first.
    let shown=MATCHES_RECENT.filter(m=>!q||hay(m).includes(q));
    if(sort.value==='old') shown=[...shown].reverse();
    if(!shown.length){ list.appendChild(el(`<p class="note">No played matches${q?' match your search':''}.</p>`)); return; }
    shown.forEach(m=>list.appendChild(matchCard(m)));
  }
  function drawPlayoffs(){
    list.appendChild(renderPlayoffs());
  }
  function draw(){
    const q=(search.value||'').trim().toLowerCase();
    const idx={played:0,upcoming:1,playoffs:2}[MATCHES_MODE]||0;
    [...modeBar.children].forEach((b,i)=>b.classList.toggle('selA',i===idx));
    const upMode=(MATCHES_MODE==='upcoming'), poMode=(MATCHES_MODE==='playoffs');
    note.style.display=(upMode||poMode)?'none':''; sort.style.display=(upMode||poMode)?'none':''; search.style.display=poMode?'none':'';
    list.innerHTML='';
    if(poMode) drawPlayoffs(); else if(upMode) drawUpcoming(q); else drawPlayed(q);
  }
```

- [ ] **Step 3: Verify `TABS` no longer references `renderPlayoffs` directly, and that `renderPlayoffs` itself is unchanged**

Run: `grep -n "id:'playoffs'" faceit_sync/_dashboard.py` (or the Grep tool) — expect no matches. `renderPlayoffs` (the function definition) must still exist untouched; only its caller changed from a `TABS` entry to `drawPlayoffs()`.

- [ ] **Step 4: Hash-routing backward compatibility for `#playoffs`**

Find (inside `function init()`):

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
  show(TABS.some(t=>t.id===start)?start:'overview');
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
  // 'playoffs' and 'sim' were their own tabs before this redesign; a link
  // bookmarked from before still needs to resolve to real content, not fall
  // through to Overview.
  if(start==='playoffs'){ MATCHES_MODE='playoffs'; MATCHES_MODE_SET=true; show('matches'); return; }
  show(TABS.some(t=>t.id===start)?start:'overview');
```

(The `#sim` case is added in Task 4, once the destination it redirects to exists.)

- [ ] **Step 5: Run the JS-syntax gate**

Run: `.venv/Scripts/python.exe -m pytest tests/test_export.py::test_dashboard_javascript_is_syntactically_valid -v`
Expected: PASS.

- [ ] **Step 6: Manual visual check**

Rebuild `dashboard.html` (same command as Task 2 Step 6) and screenshot both:
- `file:///.../dashboard.html#matches` — confirm three toggle buttons (Played / Upcoming / Playoffs) appear above the match list, and clicking each switches content without a page reload.
- `file:///.../dashboard.html#playoffs` — confirm it lands on the Matches tab with Playoffs selected (not a blank Overview).

- [ ] **Step 7: Commit**

```bash
git add faceit_sync/_dashboard.py
git commit -m "dashboard: fold Playoffs tab into Matches as a Regular season/Playoffs toggle"
```

---

### Task 4: Relegate Draft simulator into Scout a team

**Files:**
- Modify: `faceit_sync/_dashboard.py` (`TABS`, global state near `SIM_A`, `renderScoutBody`, `init()`)

**Interfaces:**
- Consumes: `renderSim()` (existing, unchanged — still builds and returns its own `<div>` off the module-level `SIM_A`/`SIM_B`/`SIM_TREE`/etc. state).
- Produces: `SCOUT_SIM_OPEN` (new global boolean, one-shot: read once per `renderScoutBody` call then reset to `false`). `TABS` drops its `sim` entry.

- [ ] **Step 1: Remove the `sim` tab and add the `SCOUT_SIM_OPEN` flag**

Find (this is the `TABS` array as left by Task 3):

```
const TABS=[
 {id:'overview',label:'Overview',render:renderOverview},
 {id:'scout',label:'Scout a team',render:renderScout},
 {id:'players',label:'Players',render:renderPlayers},
 {id:'sim',label:'Draft simulator',render:renderSim},
 {id:'meta',label:'League meta',render:renderMeta},
 {id:'matches',label:'Matches',render:renderMatches},
];
```

Replace with:

```
const TABS=[
 {id:'overview',label:'Overview',render:renderOverview},
 {id:'scout',label:'Scout a team',render:renderScout},
 {id:'players',label:'Players',render:renderPlayers},
 {id:'meta',label:'League meta',render:renderMeta},
 {id:'matches',label:'Matches',render:renderMatches},
];
```

Find:

```
let SIM_A=null, SIM_B=null, SIM_FIRST='A';  // draft simulator state
```

Replace with:

```
let SIM_A=null, SIM_B=null, SIM_FIRST='A';  // draft simulator state
let SCOUT_SIM_OPEN=false;   // one-shot: force the Scout page's beta draft-simulator section open (set by the #sim deep-link redirect in init(), consumed and reset on the next renderScoutBody)
```

- [ ] **Step 2: Add the collapsible beta section to `renderScoutBody`**

Find the end of the function:

```
  return root;
}

function scoutData(team,lim){
```

Replace with:

```
  // Draft simulator, relegated here from its own top-level tab: it's a
  // matchup-prep tool reached for while prepping a specific opponent, not a
  // destination on its own. Lazy-built on first open (or forced open once by
  // the #sim deep-link redirect in init()) since renderSim() does real work
  // aggregating each team's ban/pick history.
  {
    const openSim=SCOUT_SIM_OPEN; SCOUT_SIM_OPEN=false;
    const dsCard=el(`<details class="card" style="margin-top:14px"${openSim?' open':''}></details>`);
    dsCard.appendChild(el(`<summary style="cursor:pointer"><span class="eyebrow" style="display:inline;margin:0">Draft simulator</span> <span class="opener">beta</span></summary>`));
    const dsBody=el(`<div style="margin-top:10px"></div>`);
    dsCard.appendChild(dsBody);
    const buildSim=()=>{
      if(SIM_A!==t.team){ SIM_A=t.team; SIM_TREE={}; SIM_FOCUS=''; }
      dsBody.innerHTML=''; dsBody.appendChild(renderSim());
    };
    dsCard.addEventListener('toggle',()=>{ if(dsCard.open) buildSim(); });
    if(openSim) buildSim();
    root.appendChild(dsCard);
  }

  return root;
}

function scoutData(team,lim){
```

- [ ] **Step 3: Hash-routing backward compatibility for `#sim`**

Find (the line added in Task 3 Step 4):

```
  if(start==='playoffs'){ MATCHES_MODE='playoffs'; MATCHES_MODE_SET=true; show('matches'); return; }
  show(TABS.some(t=>t.id===start)?start:'overview');
```

Replace with:

```
  if(start==='playoffs'){ MATCHES_MODE='playoffs'; MATCHES_MODE_SET=true; show('matches'); return; }
  if(start==='sim'){ SCOUT_PREP=false; SCOUT_SIM_OPEN=true; show('scout'); return; }
  show(TABS.some(t=>t.id===start)?start:'overview');
```

(`SCOUT_PREP=false` matters because the beta section is only added to `renderScoutBody`, not the condensed `renderPrepBody` — without this a `#sim` link landing on a session where the prep sheet is active would show the condensed view with no simulator in it.)

- [ ] **Step 4: Run the JS-syntax gate**

Run: `.venv/Scripts/python.exe -m pytest tests/test_export.py::test_dashboard_javascript_is_syntactically_valid -v`
Expected: PASS.

- [ ] **Step 5: Manual visual check**

Rebuild and screenshot:
- `file:///.../dashboard.html#scout=<any real team name from your local DB>` — confirm a collapsed "Draft simulator [beta]" section appears near the bottom of the page, closed by default.
- `file:///.../dashboard.html#sim` — confirm it lands on Scout a team with the beta section already expanded and populated (not the old standalone simulator tab, not blank).

- [ ] **Step 6: Commit**

```bash
git add faceit_sync/_dashboard.py
git commit -m "dashboard: relegate Draft simulator from a top-level tab to a beta section on Scout a team"
```

---

### Task 5: Update FEATURES.md

**Files:**
- Modify: `FEATURES.md:115-147` ("### Tabs" section)

**Interfaces:** None — documentation only.

- [ ] **Step 1: Rewrite the Tabs section**

Find (`FEATURES.md`):

```
### Tabs

**Overview** — division summary, most-picked maps, ban leaders, data-quality
counters (walkovers, restarts, DC'd games, attribution coverage).

**Scout a team** — the main working view. Detailed in §3. The team picker is
labelled *Team*, not *Opponent*: pointed at your own side the same sheet is a
self-scout, showing what an opponent prepping you is looking at.

**Players** — every player on every roster, in three views. *By team* (rosters,
starters over subs, elo, top-3 captured heroes), *By seat* (grouped by inferred
subrole — Tank / Hitscan / Flex DPS / Main Support / Flex Support), and
*Leaderboard* — a sortable table of elo, maps, K/D and per-map damage / healing /
mitigation. The leaderboard runs purely off FACEIT's stat feed, so unlike hero
pools it is fully populated in **every** division, captured or not. Rate columns
carry a 5-map sample floor; counts and elo do not need one.

**Draft simulator** — a manual scenario planner. Pick two teams and walk a draft;
each team's real history drives the suggestions (map-pick frequency, per-map ban
counts, overall ban rates), with already-banned heroes excluded from the picker.

**League meta** — cross-division hero ban rates, ban-by-role split, map
popularity, attacking-first win rate per map (Escort/Hybrid only, since mirrored
modes have no attacking side), and **hero win rates** off the captured comps
joined to the match result — what actually wins, next to what gets banned. The
unit is the map (a hero on two sub-maps of one Control map played one map), each
team's lineup counts separately, and 8+ maps are needed to qualify.

**Playoffs** — the bracket, seeded from current standings until real playoff
matches exist.

**Matches** — every match card: per-map bans in draft order, replay codes inline
and click-to-copy, expandable rosters, newest/oldest sort, and the match date.
```

Replace with:

```
### Tabs

A hero strip above the tab bar ("Scout a team →" / "Contribute a capture →")
is always visible, on every tab — it's the fast path for both a first-time
visitor and a returning one, so Overview itself doesn't need to duplicate it.

**Overview** — coverage tiles (maps played, teams, teams scouted, comps
captured), standings, and the scout leaderboard (maps contributed per scout).
Deliberately does not repeat content that has its own tab (ban/map meta lives
in League meta; per-team rosters live on Scout a team and Players) — Overview
is orientation, not a preview of everything else.

**Scout a team** — the main working view. Detailed in §3. The team picker is
labelled *Team*, not *Opponent*: pointed at your own side the same sheet is a
self-scout, showing what an opponent prepping you is looking at. Includes a
collapsed **Draft simulator (beta)** section near the bottom — pick two teams
and walk a draft; each team's real history drives the suggestions (map-pick
frequency, per-map ban counts, overall ban rates), with already-banned heroes
excluded from the picker. Opens pre-filled with the currently scouted team.

**Players** — every player on every roster, in three views. *By team* (rosters,
starters over subs, elo, top-3 captured heroes), *By seat* (grouped by inferred
subrole — Tank / Hitscan / Flex DPS / Main Support / Flex Support), and
*Leaderboard* — a sortable table of elo, maps, K/D and per-map damage / healing /
mitigation. The leaderboard runs purely off FACEIT's stat feed, so unlike hero
pools it is fully populated in **every** division, captured or not. Rate columns
carry a 5-map sample floor; counts and elo do not need one.

**League meta** — cross-division hero ban rates, ban-by-role split, map
popularity, attacking-first win rate per map (Escort/Hybrid only, since mirrored
modes have no attacking side), and **hero win rates** off the captured comps
joined to the match result — what actually wins, next to what gets banned. The
unit is the map (a hero on two sub-maps of one Control map played one map), each
team's lineup counts separately, and 8+ maps are needed to qualify.

**Matches** — every match card: per-map bans in draft order, replay codes inline
and click-to-copy, expandable rosters, newest/oldest sort, and the match date. A
**Played / Upcoming / Playoffs** toggle switches the list; Playoffs shows the
bracket (seeded from current standings until real playoff matches exist) and
becomes the default view automatically once real playoff matches are ingested
for the active division.
```

- [ ] **Step 2: Commit**

```bash
git add FEATURES.md
git commit -m "docs: update FEATURES.md tabs section for the Overview/nav redesign"
```

---

### Task 6: Full verification pass

**Files:** None modified — verification only.

- [ ] **Step 1: Full test suite**

Run: `.venv/Scripts/python.exe -m pytest`
Expected: all tests pass (this includes `owdb/tests`, per `pyproject.toml`'s `testpaths`).

- [ ] **Step 2: Type check**

Run: `.venv/Scripts/python.exe -m mypy faceit_sync`
Expected: clean (no errors) — this plan touches only the `HTML_TEMPLATE` string literal, so this should be a no-op confirmation, not a place bugs are expected.

- [ ] **Step 3: Rebuild and full-tab screenshot pass**

```bash
.venv/Scripts/python.exe -m faceit_sync.cli export --format html --out dashboard.html
```

Screenshot each remaining tab and the two backward-compat redirects:

```bash
msedge --headless --screenshot=t_overview.png "file:///$(pwd)/dashboard.html#overview"
msedge --headless --screenshot=t_scout.png "file:///$(pwd)/dashboard.html#scout"
msedge --headless --screenshot=t_players.png "file:///$(pwd)/dashboard.html#players"
msedge --headless --screenshot=t_meta.png "file:///$(pwd)/dashboard.html#meta"
msedge --headless --screenshot=t_matches.png "file:///$(pwd)/dashboard.html#matches"
msedge --headless --screenshot=t_playoffs_redirect.png "file:///$(pwd)/dashboard.html#playoffs"
msedge --headless --screenshot=t_sim_redirect.png "file:///$(pwd)/dashboard.html#sim"
```

Read each PNG (via the Read tool) and confirm:
- The nav bar shows exactly 5 tabs (Overview, Scout a team, Players, League meta, Matches) — no Draft simulator, no Playoffs.
- The hero strip renders on every tab, not just Overview.
- Overview shows tiles → standings → leaderboard, nothing else.
- `#matches` shows the three-way toggle; `#playoffs` redirects into it with Playoffs selected and real/projected bracket content visible.
- `#scout` shows a collapsed "Draft simulator [beta]" section; `#sim` redirects into Scout a team with it already expanded.

- [ ] **Step 4: Clean up the local preview build**

```bash
rm -f dashboard.html t_*.png overview.png
```

(These are untracked local-preview artifacts per `CLAUDE.md` — never commit `dashboard.html`, only `docs/index.html` via CI.)

- [ ] **Step 5: Final commit (if Step 3 surfaced any fixes)**

If the visual pass required any touch-ups, commit them now with a message describing what the screenshot caught. If everything passed clean, there's nothing to commit for this task — Tasks 1-5's commits are the complete change set.

# Click-to-codes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let every evidence row on the Scout a team page resolve to its backing replay code(s), per `specs/2026-07-31-click-to-codes-design.md`.

**Architecture:** Client-side only, entirely within `faceit_sync/_dashboard.py`'s `HTML_TEMPLATE` JS. Extends `aggregate()`'s existing `gk`-tracking pattern (already used for one panel) to six more accumulators, adds two pure helpers (`codeLookup`, `codesFor`) above `bootApp` and one `bootApp`-scoped renderer (`codesCell`) plus a small popover, then wires all 8 evidence sites on `renderScoutBody`.

**Tech Stack:** Python 3.12 (`faceit_sync/_dashboard.py`, a Python string), vanilla JS, `node --check` for syntax, `pytest` for the pure-function tests.

## Global Constraints

- **After every edit to `_dashboard.py`, run** `.venv/Scripts/python.exe -m pytest tests/test_export.py::test_dashboard_javascript_is_syntactically_valid` — one JS syntax error yields a completely blank live page.
- **Pure, testable logic goes above `function bootApp(DATA){`** (`_dashboard.py:587`), same discipline as `defaultMatchesMode`/`pickDivision`. A function belongs there only if it has zero dependency on anything declared inside `bootApp` (no `esc`, `el`, `rcChip`, or any DOM access) — `codeLookup`/`codesFor` qualify; `codesCell` does not (it calls `rcChip`/`esc`, both `bootApp`-scoped) and stays inside, verified by `node --check` + manual visual check only, not pytest.
- **No new dependencies, no build step.** Reuse `rcChip`, `el`, `esc`, `table`, `drawer`, existing CSS variables (`--surface`, `--line`, `--line2`, `--accent`, `--fg`, `--faint`).
- **`mypy faceit_sync` / full `pytest`** run once at the end (Task 10), not per-task — these edits are inside `HTML_TEMPLATE`'s string literal, which mypy doesn't parse.
- **Every `gk` key is the string `` `${matchId}:${gameNo}` ``** — already the format `banOpen` and `a.replays`-adjacent code use; stay consistent so `codeLookup`'s keys always match.

---

### Task 1: Pure helpers — `codeLookup` and `codesFor`

**Files:**
- Modify: `faceit_sync/_dashboard.py` (insert above `bootApp`, after `defaultMatchesMode`)
- Test: `tests/test_dashboard_logic.py` (append)

**Interfaces:**
- Produces: `codeLookup(matches, team)` → `Map<'matchId:gameNo', {map,cat,code,opp,when,won}>`. `matches` is the dashboard's match array shape (`{id, f1, f2, finished_at, games:[{game_no, map, map_category, demo_code, winner_faction}]}`); `team` may be falsy (then `opp`/`won` are `null`).
- Produces: `codesFor(gkSet, lookup)` → `Array<{map,cat,code,opp,when,won}>`, newest-first, missing keys silently dropped. `gkSet` is any iterable of the same key strings (`Set` or `Array`).
- Consumed by: Task 2's `codesCell` and Tasks 3-9's wiring (all inside `bootApp`, calling these as ordinary in-scope functions since they're declared in the enclosing module scope).

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_dashboard_logic.py`:

```python
# --- click-to-codes: code lookup + resolution -----------------------------
# codeLookup/codesFor are pure data transforms (no DOM, no esc/el/rcChip), so
# they're declared above bootApp and directly testable here.

_ONE_MATCH = ("[{id:'m1',f1:'Alpha',f2:'Bravo',finished_at:'2026-07-20',"
              "games:[{game_no:1,map:'Ilios',map_category:'Control',"
              "demo_code:'ABC123',winner_faction:'faction1'},"
              "{game_no:2,map:'Circuit Royal',map_category:'Escort',"
              "demo_code:null,winner_faction:'faction2'}]}]")


def test_code_lookup_indexes_by_match_and_game(tmp_path) -> None:
    got = _run(f"return [...codeLookup({_ONE_MATCH},'Alpha').entries()]"
               ".map(([k])=>k);", tmp_path)
    assert got == ["m1:1"]   # game 2 has no demo_code -> excluded


def test_code_lookup_carries_opponent_and_result_for_the_given_team(tmp_path) -> None:
    got = _run(f"return codeLookup({_ONE_MATCH},'Alpha').get('m1:1');", tmp_path)
    assert got["opp"] == "Bravo" and got["won"] is True and got["code"] == "ABC123"
    assert got["map"] == "Ilios"


def test_code_lookup_flips_opponent_for_the_other_team(tmp_path) -> None:
    got = _run(f"return codeLookup({_ONE_MATCH},'Bravo').get('m1:1');", tmp_path)
    assert got["opp"] == "Alpha" and got["won"] is False


_LOOKUP = ("codeLookup(" + _ONE_MATCH + ",'Alpha')")


def test_codes_for_resolves_and_sorts_newest_first(tmp_path) -> None:
    two = ("[{id:'m2',f1:'Alpha',f2:'Charlie',finished_at:'2026-07-25',"
           "games:[{game_no:1,map:'Oasis',map_category:'Control',"
           "demo_code:'ZZZ999',winner_faction:'faction1'}]}]")
    got = _run(
        f"const lk=codeLookup([...{_ONE_MATCH},...{two}],'Alpha');"
        "return codesFor(['m1:1','m2:1'], lk).map(r=>r.code);", tmp_path)
    assert got == ["ZZZ999", "ABC123"]   # 07-25 before 07-20


def test_codes_for_silently_drops_an_unresolvable_key(tmp_path) -> None:
    got = _run(f"return codesFor(['m1:1','nope:9'], {_LOOKUP}).map(r=>r.code);", tmp_path)
    assert got == ["ABC123"]
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/Scripts/python.exe -m pytest tests/test_dashboard_logic.py -k "code_lookup or codes_for" -v`
Expected: FAIL — `codeLookup is not defined` (node ReferenceError).

- [ ] **Step 3: Add the pure functions**

In `faceit_sync/_dashboard.py`, find:

```
// Matches tab: which mode (Regular season vs Playoffs) opens by default.
// Landing on an empty Playoffs panel is worse than landing on the (populated)
// regular-season list, so only default to Playoffs once real playoff matches
// exist for the active division — finished or scheduled, any status counts.
function defaultMatchesMode(playoffsList){
  return (playoffsList && playoffsList.length) ? 'playoffs' : 'played';
}

// The whole app runs inside bootApp(DATA); DATA arrives either inlined above
```

Replace with:

```
// Matches tab: which mode (Regular season vs Playoffs) opens by default.
// Landing on an empty Playoffs panel is worse than landing on the (populated)
// regular-season list, so only default to Playoffs once real playoff matches
// exist for the active division — finished or scheduled, any status counts.
function defaultMatchesMode(playoffsList){
  return (playoffsList && playoffsList.length) ? 'playoffs' : 'played';
}

// Click-to-codes: mid:gno -> the replay-code context an evidence row's popover
// needs. `team` is whose perspective opp/won are read from (may be falsy).
function codeLookup(matches, team){
  const m=new Map();
  (matches||[]).forEach(mt=>(mt.games||[]).forEach(g=>{
    if(!g.demo_code) return;
    const won = team ? (g.winner_faction===(mt.f1===team?'faction1':'faction2')) : null;
    m.set(mt.id+':'+g.game_no, {map:g.map, cat:g.map_category, code:g.demo_code,
      opp:(team&&mt.f1===team)?mt.f2:mt.f1, when:mt.finished_at, won});
  }));
  return m;
}
// Resolve a Set/array of 'mid:gno' keys to their code rows via codeLookup's
// Map, newest first. A key with no match (a code that wiped, or a lookup
// built narrower than the gk set) is silently dropped, not guessed.
function codesFor(gkSet, lookup){
  return [...gkSet].map(k=>lookup.get(k)).filter(Boolean)
    .sort((a,b)=>String(b.when||'').localeCompare(String(a.when||'')));
}

// The whole app runs inside bootApp(DATA); DATA arrives either inlined above
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv/Scripts/python.exe -m pytest tests/test_dashboard_logic.py -k "code_lookup or codes_for" -v`
Expected: 5 passed.

- [ ] **Step 5: Run the JS-syntax gate**

Run: `.venv/Scripts/python.exe -m pytest tests/test_export.py::test_dashboard_javascript_is_syntactically_valid -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add faceit_sync/_dashboard.py tests/test_dashboard_logic.py
git commit -m "dashboard: add codeLookup/codesFor pure helpers for click-to-codes"
```

---

### Task 2: UI infra — `codesCell`, popover, delegated click handler, CSS

**Files:**
- Modify: `faceit_sync/_dashboard.py` (CSS block; near `rcChip`/its click handler, inside `bootApp`)

**Interfaces:**
- Consumes: `rcChip(code)`, `el(html)`, `esc(s)`, `dshort(iso)` (all existing, `bootApp`-scoped).
- Produces: `codesCell(rows)` → HTML string. `openCodesPopover(anchorEl, rows)` / `closeCodesPopover()`. A `document` click listener on `.codeslink`. All consumed by Tasks 3-9.

- [ ] **Step 1: Add the CSS**

Find:

```
.rc.copied{color:var(--good);border-color:var(--good)}
```

Replace with:

```
.rc.copied{color:var(--good);border-color:var(--good)}
.codeslink{cursor:pointer;color:var(--accent);font-size:12px;text-decoration:underline dotted;text-underline-offset:2px}
.codeslink:hover{color:var(--fg)}
.codespop{position:fixed;z-index:50;background:var(--surface);border:1px solid var(--line2);
  border-radius:8px;padding:8px;box-shadow:0 8px 24px rgba(0,0,0,.35);max-width:280px;max-height:320px;overflow:auto}
.codesrow{display:flex;justify-content:space-between;align-items:center;gap:10px;padding:4px 0;
  border-top:1px solid var(--line);font-size:12px}
.codesrow:first-child{border-top:0}
```

- [ ] **Step 2: Add `codesCell`, the popover, and its click handler**

Find:

```
function rcChip(code){ return `<code class="rc" data-rc="${esc(code)}" title="Copy replay code — paste in Overwatch → Watch">${esc(code)}</code>`; }
```

Replace with:

```
function rcChip(code){ return `<code class="rc" data-rc="${esc(code)}" title="Copy replay code — paste in Overwatch → Watch">${esc(code)}</code>`; }
// Evidence-row codes cell: exactly one backing game -> the code chip inline,
// no click needed (the common thin-sample case, and the explicit ask —
// "bring me straight to code"). More than one -> a small click-to-open link.
// The resolved rows travel in a data attribute (JSON, esc()-quoted) rather
// than an external registry, since table() rebuilds every row's HTML string
// from scratch on every re-sort and an insertion-order registry would go
// stale across that rebuild.
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

- [ ] **Step 3: Run the JS-syntax gate**

Run: `.venv/Scripts/python.exe -m pytest tests/test_export.py::test_dashboard_javascript_is_syntactically_valid -v`
Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add faceit_sync/_dashboard.py
git commit -m "dashboard: add codesCell + a small popover for click-to-codes"
```

---

### Task 3: Extend `aggregate()` with `gk` tracking

**Files:**
- Modify: `faceit_sync/_dashboard.py` (the `aggregate` function)

**Interfaces:**
- Produces: `a.bansGk`, `a.firstBansGk`, `a.counterGk` (new: `{key: Set<gk>}`); `a.mapStats[map].gk`, `a.pickFirstBan[map].gk` (new properties on existing per-map objects); `a.perMapPick[map]` **reshaped** from `{hero:count}` to `{heroes:{hero:count}, gk:Set}`. `a.banOpen[hero].gk` unchanged (already existed).
- Consumed by: Tasks 4-9 (each reads its own accumulator's new `gk`/`.gk` field) and the one existing consumer of the reshaped field, `banMapTable` (fixed in this same task, Step 3, so the app never sits in a broken intermediate state).

- [ ] **Step 1: Replace `aggregate()`**

Find the complete current function:

```
function aggregate(matches,team){
  const a={bans:{},banRoles:{},mapsPicked:{},perMapPick:{},counter:{},mapStats:{},
           firstBans:{},firstBanGames:0,pickFirstBan:{},banHeroWin:{},banOpen:{},games:0,gwins:0,results:[],replays:[]};
  matches.forEach(m=>{
    const side = team? (m.f1===team?'faction1':(m.f2===team?'faction2':null)) : 'x';
    if(team && !side) return;
    if(team){ const opp=m.f1===team?m.f2:m.f1; a.results.push({opp,won:m.winner===side,series:m.series,when:m.finished_at}); }
    m.games.forEach(g=>{
      if(!g.map) return; a.games++;
      if(team){
        const won=g.winner_faction===side; if(won)a.gwins++;
        const ms=a.mapStats[g.map]||(a.mapStats[g.map]={games:0,wins:0,picks:0}); ms.games++; if(won)ms.wins++;
        if(g.map_picked_by===team){ inc(a.mapsPicked,g.map); ms.picks++; }
        // map win rate conditioned on a hero being banned out this map (by either team).
        const seenB=new Set();
        g.bans.forEach(b=>{ if(!b.hero||seenB.has(b.hero))return; seenB.add(b.hero);
          const s=a.banHeroWin[b.hero]||(a.banHeroWin[b.hero]=
            {games:0,wins:0,them:{games:0,wins:0},opp:{games:0,wins:0}});
          s.games++; if(won)s.wins++;
          // Who removed the hero changes what the number means: their own ban is a
          // choice, the opponent's is something done TO them.
          const by=b.team===team?s.them:(b.team?s.opp:null);
          if(by){ by.games++; if(won)by.wins++; } });
        if(g.demo_code) a.replays.push({when:m.finished_at,mid:m.id,opp:(m.f1===team?m.f2:m.f1),
          map:g.map,cat:g.map_category,gno:g.game_no,code:g.demo_code,won});
        const mine=g.bans.find(b=>b.team===team), oc=g.bans.find(b=>b.team&&b.team!==team);
        if(mine){ inc(a.bans,mine.hero); if(mine.role)inc(a.banRoles,mine.role);
          if(g.map_picked_by===team){ (a.perMapPick[g.map]=a.perMapPick[g.map]||{}); inc(a.perMapPick[g.map],mine.hero); }
          if(mine.order===1){ a.firstBanGames++; inc(a.firstBans,mine.hero); }
          // their pick + they ban first: a self-chosen setup — surfaces repeated strats.
          if(g.map_picked_by===team && mine.order===1){
            const p=a.pickFirstBan[g.map]||(a.pickFirstBan[g.map]={games:0,wins:0,bans:{}});
            p.games++; if(won)p.wins++; inc(p.bans,mine.hero); }
          // counter-ban = the team's RESPONSE, i.e. only when the opponent
          // banned first (order 1) and this team banned second (order 2).
          if(oc && oc.order===1 && mine.order===2){ (a.counter[oc.hero]=a.counter[oc.hero]||{}); inc(a.counter[oc.hero],mine.hero); } }
        // Ban -> opening comp: pair each hero THIS team banned (FACEIT bans are
        // complete + team-attributed) with the comp they OPENED that game (their
        // captured first-segment). Reliable ban side; opening side fills in with
        // captures. Count each opening hero once per game so a hero's tally = the
        // number of "banned X" games it appeared in.
        const pg=(DATA.owscout_pergame||{})[m.id+':'+g.game_no];
        const myOpen=(pg&&team&&pg[team])?Object.values(pg[team])[0]:null;   // first segment = the opening comp
        if(myOpen&&myOpen.length){ const gk=m.id+':'+g.game_no;
          g.bans.filter(b=>b.team===team&&b.hero).forEach(b=>{
            const bo=a.banOpen[b.hero]||(a.banOpen[b.hero]={gk:new Set(),heroes:{}});
            if(!bo.gk.has(gk)){ bo.gk.add(gk); myOpen.forEach(h=>inc(bo.heroes,h)); } }); }
      } else { inc(a.mapsPicked,g.map); g.bans.forEach(b=>{ inc(a.bans,b.hero); if(b.role)inc(a.banRoles,b.role); }); }
    });
  });
  return a;
}
```

Replace with:

```
function aggregate(matches,team){
  const a={bans:{},bansGk:{},banRoles:{},mapsPicked:{},perMapPick:{},counter:{},counterGk:{},mapStats:{},
           firstBans:{},firstBansGk:{},firstBanGames:0,pickFirstBan:{},banHeroWin:{},banOpen:{},games:0,gwins:0,results:[],replays:[]};
  matches.forEach(m=>{
    const side = team? (m.f1===team?'faction1':(m.f2===team?'faction2':null)) : 'x';
    if(team && !side) return;
    if(team){ const opp=m.f1===team?m.f2:m.f1; a.results.push({opp,won:m.winner===side,series:m.series,when:m.finished_at}); }
    m.games.forEach(g=>{
      if(!g.map) return; a.games++;
      if(team){
        const won=g.winner_faction===side; if(won)a.gwins++;
        const gk=m.id+':'+g.game_no;
        const ms=a.mapStats[g.map]||(a.mapStats[g.map]={games:0,wins:0,picks:0,gk:new Set()}); ms.games++; if(won)ms.wins++; ms.gk.add(gk);
        if(g.map_picked_by===team){ inc(a.mapsPicked,g.map); ms.picks++; }
        // map win rate conditioned on a hero being banned out this map (by either team).
        const seenB=new Set();
        g.bans.forEach(b=>{ if(!b.hero||seenB.has(b.hero))return; seenB.add(b.hero);
          const s=a.banHeroWin[b.hero]||(a.banHeroWin[b.hero]=
            {games:0,wins:0,them:{games:0,wins:0},opp:{games:0,wins:0}});
          s.games++; if(won)s.wins++;
          // Who removed the hero changes what the number means: their own ban is a
          // choice, the opponent's is something done TO them.
          const by=b.team===team?s.them:(b.team?s.opp:null);
          if(by){ by.games++; if(won)by.wins++; } });
        if(g.demo_code) a.replays.push({when:m.finished_at,mid:m.id,opp:(m.f1===team?m.f2:m.f1),
          map:g.map,cat:g.map_category,gno:g.game_no,code:g.demo_code,won});
        const mine=g.bans.find(b=>b.team===team), oc=g.bans.find(b=>b.team&&b.team!==team);
        if(mine){ inc(a.bans,mine.hero); (a.bansGk[mine.hero]=a.bansGk[mine.hero]||new Set()).add(gk);
          if(mine.role)inc(a.banRoles,mine.role);
          if(g.map_picked_by===team){ const pm=a.perMapPick[g.map]=a.perMapPick[g.map]||{heroes:{},gk:new Set()};
            inc(pm.heroes,mine.hero); pm.gk.add(gk); }
          if(mine.order===1){ a.firstBanGames++; inc(a.firstBans,mine.hero);
            (a.firstBansGk[mine.hero]=a.firstBansGk[mine.hero]||new Set()).add(gk); }
          // their pick + they ban first: a self-chosen setup — surfaces repeated strats.
          if(g.map_picked_by===team && mine.order===1){
            const p=a.pickFirstBan[g.map]||(a.pickFirstBan[g.map]={games:0,wins:0,bans:{},gk:new Set()});
            p.games++; if(won)p.wins++; inc(p.bans,mine.hero); p.gk.add(gk); }
          // counter-ban = the team's RESPONSE, i.e. only when the opponent
          // banned first (order 1) and this team banned second (order 2).
          if(oc && oc.order===1 && mine.order===2){ (a.counter[oc.hero]=a.counter[oc.hero]||{}); inc(a.counter[oc.hero],mine.hero);
            (a.counterGk[oc.hero]=a.counterGk[oc.hero]||new Set()).add(gk); } }
        // Ban -> opening comp: pair each hero THIS team banned (FACEIT bans are
        // complete + team-attributed) with the comp they OPENED that game (their
        // captured first-segment). Reliable ban side; opening side fills in with
        // captures. Count each opening hero once per game so a hero's tally = the
        // number of "banned X" games it appeared in.
        const pg=(DATA.owscout_pergame||{})[m.id+':'+g.game_no];
        const myOpen=(pg&&team&&pg[team])?Object.values(pg[team])[0]:null;   // first segment = the opening comp
        if(myOpen&&myOpen.length){
          g.bans.filter(b=>b.team===team&&b.hero).forEach(b=>{
            const bo=a.banOpen[b.hero]||(a.banOpen[b.hero]={gk:new Set(),heroes:{}});
            if(!bo.gk.has(gk)){ bo.gk.add(gk); myOpen.forEach(h=>inc(bo.heroes,h)); } }); }
      } else { inc(a.mapsPicked,g.map); g.bans.forEach(b=>{ inc(a.bans,b.hero); if(b.role)inc(a.banRoles,b.role); }); }
    });
  });
  return a;
}
```

(Two behavioral non-changes worth noting for the reviewer: `gk` is now computed once per game unconditionally instead of only inside the `myOpen` branch — cheap string concat, no side effect, identical value. `perMapPick[g.map]`'s shape changed from a flat hero-count object to `{heroes,gk}` — Step 3 below fixes its one consumer in the same task.)

- [ ] **Step 2: Run the JS-syntax gate**

Run: `.venv/Scripts/python.exe -m pytest tests/test_export.py::test_dashboard_javascript_is_syntactically_valid -v`
Expected: PASS.

- [ ] **Step 3: Fix `perMapPick`'s one consumer (`banMapTable`)**

Find:

```
  const banMapTable=(pm)=>{
    // Ordered by ban count, not by mode: the top of this table is also the map
    // they pick most often, which is the thing worth seeing first.
    const rows=Object.keys(pm).map(mp=>({map:mp,cat:MAP_CAT[mp]||'',
      n:Object.values(pm[mp]).reduce((a,b)=>a+b,0),
      heroes:rank(pm[mp]).map(([h,c])=>`${heroChip(h)}<span class="faint"> ${c}</span>`).join(' ')}))
      .sort((a,b)=>b.n-a.n||mapCmp(a.map,b.map));
    return rows.length?table(
      [{k:'map',label:'Map',html:r=>`${esc(r.map)} <span class="faint">${esc(r.cat)}</span>`},
       {k:'n',label:'Bans',num:true},{k:'heroes',label:'Heroes banned',html:r=>r.heroes}],
      rows)
     :el(`<p class="note">No data in this window.</p>`);
  };
```

Replace with (grep confirmed a single consumer of `perMapPick`, `banMapTable` itself; adds the Codes column at the same time so this task never leaves the file in a broken state):

```
  const banMapTable=(pm)=>{
    // Ordered by ban count, not by mode: the top of this table is also the map
    // they pick most often, which is the thing worth seeing first.
    const rows=Object.keys(pm).map(mp=>({map:mp,cat:MAP_CAT[mp]||'',
      n:Object.values(pm[mp].heroes).reduce((a,b)=>a+b,0),
      heroes:rank(pm[mp].heroes).map(([h,c])=>`${heroChip(h)}<span class="faint"> ${c}</span>`).join(' '),
      codes:codesFor(pm[mp].gk, lookup)}))
      .sort((a,b)=>b.n-a.n||mapCmp(a.map,b.map));
    return rows.length?table(
      [{k:'map',label:'Map',html:r=>`${esc(r.map)} <span class="faint">${esc(r.cat)}</span>`},
       {k:'n',label:'Bans',num:true},{k:'heroes',label:'Heroes banned',html:r=>r.heroes},
       {k:'codes',label:'Codes',html:r=>codesCell(r.codes)}],
      rows)
     :el(`<p class="note">No data in this window.</p>`);
  };
```

This introduces a reference to `lookup`, which Task 4 Step 2 declares near the top of `renderScoutBody` (before this closure runs — `banMapTable` is only invoked later, at the existing `dv.body.appendChild(banMapTable(t.perMapPick));` call site, itself well after the top-of-function declaration point). Task 4 lands immediately after this task; the two together always leave a working file, but `node --check` alone (Step 4 below) cannot catch a missing declaration — it's a parse check, not an execution — so don't treat a green syntax check here as proof `lookup` already resolves; that's only true once Task 4 Step 2 lands.

- [ ] **Step 4: Run the JS-syntax gate again**

Run: `.venv/Scripts/python.exe -m pytest tests/test_export.py::test_dashboard_javascript_is_syntactically_valid -v`
Expected: PASS (syntax is valid even though `lookup` doesn't exist yet at runtime — Task 4 Step 1 adds its declaration next; `node --check` only parses, it doesn't execute).

- [ ] **Step 5: Commit**

```bash
git add faceit_sync/_dashboard.py
git commit -m "dashboard: extend aggregate() gk-tracking to bans/firstBans/mapStats/counter/perMapPick/pickFirstBan"
```

---

### Task 4: Declare `lookup`, wire sites 1-2 (Ban tendencies, First ban)

**Files:**
- Modify: `faceit_sync/_dashboard.py`

**Interfaces:**
- Produces: `lookup` (a `Map`, declared once near the top of `renderScoutBody` — Tasks 6-8 and Task 3 Step 3's `banMapTable` all reuse this same binding; must not be redeclared).
- Consumes: `codeLookup`, `banLiftRows`, `banLiftList`, `codesCell` (all now defined per Tasks 1-2).

- [ ] **Step 1: Update `banLiftRows`/`banLiftList` to carry and render codes**

Find:

```
function banLiftRows(counts, baseShare, minN){
  const tot=Object.values(counts).reduce((a,b)=>a+b,0)||1;
  return Object.entries(counts).map(([h,n])=>({hero:h, n, share:n/tot,
      base:baseShare[h]||0, lift: baseShare[h]? (n/tot)/baseShare[h] : null}))
    .filter(r=>r.n>=(minN||2))
    .sort((a,b)=>((b.lift==null?-1:b.lift)-(a.lift==null?-1:a.lift))||b.n-a.n);
}
function banLiftList(rows){
  if(!rows.length) return `<p class="note">Too few bans to read a tendency (needs 2+ of a hero).</p>`;
  return `<div>`+rows.slice(0,10).map(r=>{
    const lab=r.lift==null?'new':'×'+r.lift.toFixed(1);
    const col=r.lift==null?'var(--faint)':r.lift>=1.5?'var(--good)':r.lift<=0.6?'var(--bad)':'var(--mid)';
    return `<div class="crow"><span>${heroChip(r.hero)} <span class="faint">${r.n} ban${r.n===1?'':'s'} · ${Math.round(r.share*100)}% of theirs vs ${Math.round(r.base*100)}% field</span></span>`+
      `<span class="rec">${pill(lab,col)}</span></div>`;
  }).join('')+`</div>`;
}
```

Replace with:

```
function banLiftRows(counts, baseShare, minN, gkByHero, lookup){
  const tot=Object.values(counts).reduce((a,b)=>a+b,0)||1;
  return Object.entries(counts).map(([h,n])=>({hero:h, n, share:n/tot,
      base:baseShare[h]||0, lift: baseShare[h]? (n/tot)/baseShare[h] : null,
      codes: gkByHero ? codesFor(gkByHero[h]||new Set(), lookup) : null}))
    .filter(r=>r.n>=(minN||2))
    .sort((a,b)=>((b.lift==null?-1:b.lift)-(a.lift==null?-1:a.lift))||b.n-a.n);
}
function banLiftList(rows){
  if(!rows.length) return `<p class="note">Too few bans to read a tendency (needs 2+ of a hero).</p>`;
  return `<div>`+rows.slice(0,10).map(r=>{
    const lab=r.lift==null?'new':'×'+r.lift.toFixed(1);
    const col=r.lift==null?'var(--faint)':r.lift>=1.5?'var(--good)':r.lift<=0.6?'var(--bad)':'var(--mid)';
    return `<div class="crow"><span>${heroChip(r.hero)} <span class="faint">${r.n} ban${r.n===1?'':'s'} · ${Math.round(r.share*100)}% of theirs vs ${Math.round(r.base*100)}% field</span></span>`+
      `<span class="rec">${r.codes?codesCell(r.codes)+' ':''}${pill(lab,col)}</span></div>`;
  }).join('')+`</div>`;
}
```

`banLiftRows`'s one other caller (the signature-ban glance callout,
`banLiftRows(t.bans, bb.all, 3).filter(...)`) passes neither `gkByHero` nor
`lookup` — both stay `undefined`, `r.codes` stays `null`, `banLiftList` never
renders a codes cell for it. Unaffected by this change, matching the design
doc's explicit scope (that callout is out of scope).

- [ ] **Step 2: Declare `lookup` near the top of `renderScoutBody`**

`renderScoutBody` starts at `_dashboard.py:1420`; Counter-scout (Task 8) is
the first section that needs `lookup`, and it's much *earlier* in the
function's source order (around `:1829`) than the Ban tendencies section
(around `:1991`) where the aggregated-table wiring happens. `const` is not
hoisted in JS, so `lookup` must be declared before its first use in **source
order**, not merely before it in task-execution order — declare it right at
the top of the function instead.

Find:

```
  const root=el(`<div></div>`);
  const w=el(`<div class="scout-main"></div>`);
  const side=el(`<div class="scout-side"></div>`);
```

Replace with:

```
  const root=el(`<div></div>`);
  const w=el(`<div class="scout-main"></div>`);
  const side=el(`<div class="scout-side"></div>`);
  // Resolves every gk-tracked evidence row in this function to its replay
  // code(s); built from MATCHES_RECENT (unwindowed), not t.matches, so it
  // also covers Counter-scout's matchups below, which come from a separate,
  // unwindowed owscout source (see the design doc). Declared here, at the
  // top of the function, because Counter-scout (which needs it) renders
  // before the aggregated evidence tables do, and const isn't hoisted.
  const lookup=codeLookup(MATCHES_RECENT, t.team);
```

- [ ] **Step 3: Wire the Ban tendencies + First ban sections**

Find:

```
  // Preferred bans + Maps picks/win rate - the side-by-side pair, restored
  // by operator request after the reorg had split it across the clusters.
  const two=el(`<div class="grid cols-2" style="margin-top:16px;align-items:start"></div>`);
  const banC=el(`<div class="card"></div>`);
  const banBase=divBanBaseline();
  banC.appendChild(el(`<p class="eyebrow">Ban tendencies <span class="note" style="text-transform:none;letter-spacing:0">· lift vs the field, not raw counts</span></p>`));
  banC.appendChild(el(banLiftList(banLiftRows(t.bans, banBase.all))));
  if(t.firstBanGames){
    banC.appendChild(el(`<p class="eyebrow" style="margin-top:16px">First ban <span class="note" style="text-transform:none;letter-spacing:0">· when they draft first (${t.firstBanGames} maps) — the intentional one</span></p>`));
    banC.appendChild(el(banLiftList(banLiftRows(t.firstBans, banBase.first))));
  }
  two.appendChild(banC);
```

Replace with:

```
  // Preferred bans + Maps picks/win rate - the side-by-side pair, restored
  // by operator request after the reorg had split it across the clusters.
  const two=el(`<div class="grid cols-2" style="margin-top:16px;align-items:start"></div>`);
  const banC=el(`<div class="card"></div>`);
  const banBase=divBanBaseline();
  banC.appendChild(el(`<p class="eyebrow">Ban tendencies <span class="note" style="text-transform:none;letter-spacing:0">· lift vs the field, not raw counts</span></p>`));
  banC.appendChild(el(banLiftList(banLiftRows(t.bans, banBase.all, undefined, t.bansGk, lookup))));
  if(t.firstBanGames){
    banC.appendChild(el(`<p class="eyebrow" style="margin-top:16px">First ban <span class="note" style="text-transform:none;letter-spacing:0">· when they draft first (${t.firstBanGames} maps) — the intentional one</span></p>`));
    banC.appendChild(el(banLiftList(banLiftRows(t.firstBans, banBase.first, undefined, t.firstBansGk, lookup))));
  }
  two.appendChild(banC);
```

- [ ] **Step 4: Run the JS-syntax gate**

Run: `.venv/Scripts/python.exe -m pytest tests/test_export.py::test_dashboard_javascript_is_syntactically_valid -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add faceit_sync/_dashboard.py
git commit -m "dashboard: wire click-to-codes into Ban tendencies + First ban"
```

---

### Task 5: Wire site 3 (Maps — picks & win rate)

**Files:**
- Modify: `faceit_sync/_dashboard.py`

- [ ] **Step 1: Add the Codes column**

Find:

```
  const mapC=el(`<div class="card"></div>`);
  mapC.appendChild(el(`<p class="eyebrow">Maps — picks &amp; win rate</p>`));
  const mrows=Object.entries(t.mapStats).map(([m,v])=>({map:m,cat:MAP_CAT[m]||'',games:v.games,picks:v.picks,wins:v.wins,wr:pctOf(v.wins,v.games)})).sort((a,b)=>mapCmp(a.map,b.map));
  mapC.appendChild(mrows.length?table(
    [{k:'map',label:'Map'},
     {k:'picks',label:'Picked',num:true},{k:'games',label:'Played',num:true},
     {k:'wr',label:'Win %',num:true,html:r=>wrCell(r.wins,r.games)}], mrows, byMode)
   :el(`<p class="note">No maps in window.</p>`));
  two.appendChild(mapC);
```

Replace with:

```
  const mapC=el(`<div class="card"></div>`);
  mapC.appendChild(el(`<p class="eyebrow">Maps — picks &amp; win rate</p>`));
  const mrows=Object.entries(t.mapStats).map(([m,v])=>({map:m,cat:MAP_CAT[m]||'',games:v.games,picks:v.picks,wins:v.wins,wr:pctOf(v.wins,v.games),codes:codesFor(v.gk,lookup)})).sort((a,b)=>mapCmp(a.map,b.map));
  mapC.appendChild(mrows.length?table(
    [{k:'map',label:'Map'},
     {k:'picks',label:'Picked',num:true},{k:'games',label:'Played',num:true},
     {k:'wr',label:'Win %',num:true,html:r=>wrCell(r.wins,r.games)},
     {k:'codes',label:'Codes',html:r=>codesCell(r.codes)}], mrows, byMode)
   :el(`<p class="note">No maps in window.</p>`));
  two.appendChild(mapC);
```

- [ ] **Step 2: Run the JS-syntax gate**

Run: `.venv/Scripts/python.exe -m pytest tests/test_export.py::test_dashboard_javascript_is_syntactically_valid -v`
Expected: PASS.

- [ ] **Step 3: Commit**

```bash
git add faceit_sync/_dashboard.py
git commit -m "dashboard: wire click-to-codes into Maps picks & win rate"
```

---

### Task 6: Wire site 4 (Counter-bans) and site 5 (Ban→opening)

**Files:**
- Modify: `faceit_sync/_dashboard.py`

- [ ] **Step 1: Add the Codes column to Counter-bans**

Find:

```
      dv.body.appendChild(el(sectionH('Counter-bans',`<span class="note">opponent bans first → ${esc(t.team)}'s reply</span>`)));
  const cRows=rank(Object.fromEntries(Object.entries(t.counter).map(([k,v])=>[k,Object.values(v).reduce((x,y)=>x+y,0)])))
    .map(([opp,tot])=>({opp,tot,resp:rank(t.counter[opp]).map(([h,n])=>`${heroChip(h)}<span class="faint"> ${n}</span>`).join(' ')}));
      dv.body.appendChild(cRows.length?table(
    [{k:'opp',label:'Opponent banned first',html:r=>heroChip(r.opp)},{k:'tot',label:'×',num:true},
     {k:'resp',label:`${esc(t.team)} replied with`,html:r=>r.resp}], cRows)
   :el(`<p class="note">No counter-bans in this window (needs the opponent to have banned first with both bans attributed).</p>`));
```

Replace with:

```
      dv.body.appendChild(el(sectionH('Counter-bans',`<span class="note">opponent bans first → ${esc(t.team)}'s reply</span>`)));
  const cRows=rank(Object.fromEntries(Object.entries(t.counter).map(([k,v])=>[k,Object.values(v).reduce((x,y)=>x+y,0)])))
    .map(([opp,tot])=>({opp,tot,resp:rank(t.counter[opp]).map(([h,n])=>`${heroChip(h)}<span class="faint"> ${n}</span>`).join(' '),
      codes:codesFor(t.counterGk[opp]||new Set(),lookup)}));
      dv.body.appendChild(cRows.length?table(
    [{k:'opp',label:'Opponent banned first',html:r=>heroChip(r.opp)},{k:'tot',label:'×',num:true},
     {k:'resp',label:`${esc(t.team)} replied with`,html:r=>r.resp},
     {k:'codes',label:'Codes',html:r=>codesCell(r.codes)}], cRows)
   :el(`<p class="note">No counter-bans in this window (needs the opponent to have banned first with both bans attributed).</p>`));
```

- [ ] **Step 2: Add the Codes column to Ban→opening**

Find:

```
    const boRows=Object.entries(t.banOpen||{})
      .map(([ban,v])=>({ban, n:v.gk.size,
        opens:Object.entries(v.heroes).sort((x,y)=>y[1]-x[1]).filter(([h,c])=>c/v.gk.size>=0.6).slice(0,5)}))
      .filter(r=>r.n>=2 && r.opens.length).sort((x,y)=>y.n-x.n).slice(0,8);
    if(boRows.length){
      dv.body.appendChild(el(sectionH('When they ban a hero → what they open',`<span class="note">their ban paired with the comp they opened that game · captured games only</span>`)));
      dv.body.appendChild(table(
        [{k:'ban',label:'They ban',html:r=>heroChip(r.ban)},{k:'n',label:'Games',num:true},
         {k:'opens',label:'They open with',html:r=>r.opens.map(([h,c])=>`${heroChip(h)}${c<r.n?`<span class="faint"> ${c}/${r.n}</span>`:''}`).join(' ')}], boRows));
    }
```

Replace with:

```
    const boRows=Object.entries(t.banOpen||{})
      .map(([ban,v])=>({ban, n:v.gk.size,
        opens:Object.entries(v.heroes).sort((x,y)=>y[1]-x[1]).filter(([h,c])=>c/v.gk.size>=0.6).slice(0,5),
        codes:codesFor(v.gk,lookup)}))
      .filter(r=>r.n>=2 && r.opens.length).sort((x,y)=>y.n-x.n).slice(0,8);
    if(boRows.length){
      dv.body.appendChild(el(sectionH('When they ban a hero → what they open',`<span class="note">their ban paired with the comp they opened that game · captured games only</span>`)));
      dv.body.appendChild(table(
        [{k:'ban',label:'They ban',html:r=>heroChip(r.ban)},{k:'n',label:'Games',num:true},
         {k:'opens',label:'They open with',html:r=>r.opens.map(([h,c])=>`${heroChip(h)}${c<r.n?`<span class="faint"> ${c}/${r.n}</span>`:''}`).join(' ')},
         {k:'codes',label:'Codes',html:r=>codesCell(r.codes)}], boRows));
    }
```

- [ ] **Step 3: Run the JS-syntax gate**

Run: `.venv/Scripts/python.exe -m pytest tests/test_export.py::test_dashboard_javascript_is_syntactically_valid -v`
Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add faceit_sync/_dashboard.py
git commit -m "dashboard: wire click-to-codes into Counter-bans + Ban->opening"
```

---

### Task 7: Wire site 6 (Signature setups)

**Files:**
- Modify: `faceit_sync/_dashboard.py`

- [ ] **Step 1: Add the Codes column**

Find:

```
  const pfb=Object.entries(t.pickFirstBan).map(([m,v])=>({map:m,cat:MAP_CAT[m]||'',
      games:v.games,wr:pctOf(v.wins,v.games),comp:openOn(m),
      ban:rank(v.bans).slice(0,2).map(([h,n])=>`${heroChip(h)}<span class="faint"> ${n}</span>`).join(' ')}))
    .sort((a,b)=>mapCmp(a.map,b.map));
  w.appendChild(el(sectionH('Signature setups',`<span class="note">maps they pick &amp; ban first on · self-chosen drafts</span>`)));
  if(pfb.length){
    w.appendChild(el(`<p class="note" style="margin-top:0">Maps ${esc(t.team)} both picked and opened the ban on — a fully self-chosen draft. A map+first-ban they repeat is a rehearsed setup worth being ready for. (Win rate omitted — at ~2 games per map it is noise.)</p>`));
    w.appendChild(table(
      [{k:'map',label:'Map'},
       {k:'ban',label:'Their first ban',html:r=>r.ban},
       {k:'comp',label:'What they run there',html:r=>r.comp||`<span class="faint">not captured</span>`},
       {k:'games',label:'Maps',num:true}], pfb, byMode));
  } else {
    w.appendChild(el(`<p class="note">No maps in this window where they both picked and banned first.</p>`));
  }
```

Replace with:

```
  const pfb=Object.entries(t.pickFirstBan).map(([m,v])=>({map:m,cat:MAP_CAT[m]||'',
      games:v.games,wr:pctOf(v.wins,v.games),comp:openOn(m),
      ban:rank(v.bans).slice(0,2).map(([h,n])=>`${heroChip(h)}<span class="faint"> ${n}</span>`).join(' '),
      codes:codesFor(v.gk,lookup)}))
    .sort((a,b)=>mapCmp(a.map,b.map));
  w.appendChild(el(sectionH('Signature setups',`<span class="note">maps they pick &amp; ban first on · self-chosen drafts</span>`)));
  if(pfb.length){
    w.appendChild(el(`<p class="note" style="margin-top:0">Maps ${esc(t.team)} both picked and opened the ban on — a fully self-chosen draft. A map+first-ban they repeat is a rehearsed setup worth being ready for. (Win rate omitted — at ~2 games per map it is noise.)</p>`));
    w.appendChild(table(
      [{k:'map',label:'Map'},
       {k:'ban',label:'Their first ban',html:r=>r.ban},
       {k:'comp',label:'What they run there',html:r=>r.comp||`<span class="faint">not captured</span>`},
       {k:'games',label:'Maps',num:true},
       {k:'codes',label:'Codes',html:r=>codesCell(r.codes)}], pfb, byMode));
  } else {
    w.appendChild(el(`<p class="note">No maps in this window where they both picked and banned first.</p>`));
  }
```

- [ ] **Step 2: Run the JS-syntax gate**

Run: `.venv/Scripts/python.exe -m pytest tests/test_export.py::test_dashboard_javascript_is_syntactically_valid -v`
Expected: PASS.

- [ ] **Step 3: Commit**

```bash
git add faceit_sync/_dashboard.py
git commit -m "dashboard: wire click-to-codes into Signature setups"
```

---

### Task 8: Wire site 8 (Counter-scout matchup rows)

**Files:**
- Modify: `faceit_sync/_dashboard.py`

Note: site 7 (Ban-by-map evidence / `banMapTable`) was already wired in Task 3
Step 3 (bundled there since it was the one consumer of the `perMapPick`
reshape) — this task covers the remaining site, Counter-scout.

- [ ] **Step 1: Append an inline code chip to each matchup row**

Find:

```
          sim.slice(0,6).forEach(({m,ov})=>{
            resBox.appendChild(el(`<div class="crow${ov.length<2?' thin':''}">`+
              `<span class="csrow"><span class="wlsq ${m.won?'w':'l'}">${m.won?'W':'L'}</span>`+
              `<b>${esc(m.map)}</b><span class="faint">ran</span>${compRow(m.open||[])}</span>`+
              `<span class="rec">matched ${ov.length}/${signal.length}</span></div>`));
          });
```

Replace with:

```
          sim.slice(0,6).forEach(({m,ov})=>{
            // Counter-scout rows are already one game each (unlike the aggregated
            // tables above) - always the inline single-code case, never a popover.
            const cc=lookup.get(m.match_id+':'+m.game_no);
            resBox.appendChild(el(`<div class="crow${ov.length<2?' thin':''}">`+
              `<span class="csrow"><span class="wlsq ${m.won?'w':'l'}">${m.won?'W':'L'}</span>`+
              `<b>${esc(m.map)}</b><span class="faint">ran</span>${compRow(m.open||[])}</span>`+
              `<span class="rec">matched ${ov.length}/${signal.length}${cc?' '+rcChip(cc.code):''}</span></div>`));
          });
```

- [ ] **Step 2: Run the JS-syntax gate**

Run: `.venv/Scripts/python.exe -m pytest tests/test_export.py::test_dashboard_javascript_is_syntactically_valid -v`
Expected: PASS.

- [ ] **Step 3: Commit**

```bash
git add faceit_sync/_dashboard.py
git commit -m "dashboard: wire click-to-codes into Counter-scout matchup rows"
```

---

### Task 9: Full verification pass

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

Pick a real team from the local DB with enough captured/played history to
populate every section (check the Overview standings table for one with a
decent match count), then screenshot `#scout=<team>` at a generous height
(the page is long — see the Overview/nav redesign plan's crop technique if a
single screenshot doesn't capture everything). Confirm:

- Ban tendencies and First ban rows show either an inline `.rc` code chip
  (1 backing game) or a `N codes ▾` link (2+).
- Maps — picks & win rate, Counter-bans, Ban→opening, Signature setups, and
  Bans on maps they pick (Ban-by-map evidence, inside its drawer — expand it)
  all show a Codes column with the same inline-vs-link rule.
- Counter-scout's "Vs comps like yours" rows show an inline code chip
  appended to the `matched N/M` text when a code is available.
- If a real browser/Playwright is available: click a `codeslink`, confirm the
  popover opens near the row with map/opponent/date per game and a working
  `.rc` copy chip; click outside, confirm it closes; click another
  `codeslink` while one is open, confirm the first one closes (only one open
  at a time).

- [ ] **Step 4: Clean up the local preview build**

```bash
rm -f dashboard.html
```

- [ ] **Step 5: Final commit (only if Step 3 surfaced fixes)**

If the visual pass required touch-ups, commit them now with a message
describing what it caught. Otherwise Tasks 1-8's commits are the complete
change set.

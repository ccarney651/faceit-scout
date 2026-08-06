# Draft simulator — explainable & verifiable — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the draft simulator explain every suggestion in plain language, verify its decision engine in the tested pure-function layer, and let each suggestion's backing games resolve to replay codes — per `specs/2026-08-05-draft-sim-explainable-design.md`.

**Architecture:** Client-side only, entirely within `faceit_sync/_dashboard.py`'s `HTML_TEMPLATE` JS. Hoists the sim's decision engine (`simModelFrom`, `divBanBaseFrom`, `mapsFrom`, `banSuggest`, `sigLift`, `mapCompare`, `allowedCatsFor`, `autoMap`, `autoBan`) and three plain-text explainers (`mapExplain`, `banExplain`, `modeExplain`) above `bootApp` as data-parameterized pure functions, keeps the old names as thin bootApp wrappers, then rewires the focused sim card to show a selection-driven "why" strip per decision with click-to-codes evidence. The scenario-tree mechanics are untouched.

**Tech Stack:** Python 3.12 (`faceit_sync/_dashboard.py`, a Python string), vanilla JS, `node --check` for syntax, `pytest` for the pure-function tests, headless Edge for the visual pass.

## Global Constraints

- **After every edit to `_dashboard.py`, run** `.venv/Scripts/python.exe -m pytest tests/test_export.py::test_dashboard_javascript_is_syntactically_valid` — one JS syntax error yields a completely blank live page.
- **Pure, testable logic goes above `function bootApp(DATA){`** (`_dashboard.py:866`), same discipline as `codeLookup`/`codesFor`/`defaultMatchesMode`. A function belongs there only if it has **zero** dependency on anything declared inside `bootApp` — no `esc`, `el`, `inc`, `MAP_CAT`, `CODE_WIPE`, `HERO_ROLE`, `D()`, or DOM. The `_pure_js()` harness executes every hoisted line in node, so any such reference throws immediately in the new tests.
- **Old names stay as thin bootApp wrappers.** `simModel`, `divBanBaseline`, `divMaps` keep their callers (Scout page, League meta) working by delegating to the pure functions over `D().matches`. Never call the wrappers from the tests — call the pure functions with explicit fixtures.
- **Every gk key is the string `` `${matchId}:${gameNo}` ``** — the format `codeLookup` already keys on; stay consistent.
- **No new dependencies, no build step.** Reuse `codeLookup`, `codesFor`, `codesCell`, `.codespop`, `heroChip`, `esc`, `el`, and the existing CSS variables.
- **`mypy faceit_sync` / full `pytest`** run once at the end (Task 5), not per-task — these edits are inside `HTML_TEMPLATE`'s string literal, which mypy doesn't parse.
- **`MAP_CAT` is bootApp-scoped** (`:938`). Pure `mapsFrom` must read `g.map_category` only; the `divMaps()` wrapper enriches gaps from `MAP_CAT`.

## Implementation notes (2026-08-05 — deviations found while executing)

Recorded so the plan stays an accurate account of what actually landed:

- **`_run()` harness needed an explicit UTF-8 decode.** `subprocess.run(..., text=True)` decodes node's stdout with the Windows ANSI codepage, corrupting the explainers' `×`/`★`/`—` before the comparison. Fixed once in `tests/test_dashboard_logic.py:41` (`encoding="utf-8"`); all pre-existing tests are ASCII and unaffected.
- **The gk drilldown test must spread Sets in JS.** `JSON.stringify` turns a `Set` into `{}`, so `return simModelFrom(...)` mangles `gkPick`/`gkBanAll`/`gkBanMap`. The test body spreads first: `[...model.gkPick['Oasis']].sort()`.
- **`thin` means "a single data point", not "no data".** Zero-data reads (division fallback, "no ban history") carry their caveat in the text and return `thin:false`; appending "a single case, not a pattern" to "no Ragnarok pick history" read as a contradiction. The plan's explainer tests were updated to assert this.
- **`banExplain` uses a `saidHere` flag.** When a hero is top overall *and* top on-map (the common auto-suggestion), the on-map evidence must still be shown; the flag only suppresses it when the lead phrase already said "× here".
- **The map evidence cell reads the full-season model** (`modelFull(picker).gkPick`), because map picks are full-season in the sim while bans use the recent window.
- **`renderSim`'s local `MODES` became dead code** once `allowedCatsFor` moved up and was removed.

---

### Task 1: Pure decision engine + explainers, hoisted above `bootApp`

**Files:**
- Modify: `faceit_sync/_dashboard.py` (insert above `bootApp`, after `codesFor` at `:760`)
- Test: `tests/test_dashboard_logic.py` (append)

**Interfaces:**
- Produces: `simModelFrom(matches, team, limitGames)` → `{team, pick, banByMap, bansAll, gkPick, gkBanAll, gkBanMap, ngames}`; `divBanBaseFrom(matches)` → `{all, first}` share maps; `mapsFrom(matches)` → `{map: category}`; `banSuggest(model, map, illegal)` → `Array<{hero,onMap,all}>` (≤7, ranked `onMap*2+all`); `sigLift(model, divBase, hero)` → `{sig, bans, lift}`; `mapCompare(a,b,teamPicks,divPicks,divPlay)` → number; `allowedCatsFor(g1,used,pool)` → `string[]`; `autoMap(teamPicks,divPicks,divPlay,cats,used,pool)` → map|`null`; `autoBan(model,map,illegal)` → hero|`null`; `mapExplain(teamName,map,cat,teamPicks,divPicks,isTopInCat)` / `banExplain(teamName,map,hero,all,onMap,isTopOverall,isTopOnMap,sig)` / `modeExplain(teamName,cat,leaguePct,teamModePicks)` → `{text, thin}`. Plus named constants `SIG_MIN=3`, `SIG_LIFT=2`, `SIM_MIN_MAPS=6`.
- Consumed by: Task 2's wrappers and Task 3/4's renderSim wiring.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_dashboard_logic.py`:

```python
# --- draft simulator: pure decision engine + explainers ---------------------
# simModelFrom/divBanBaseFrom/mapsFrom/banSuggest/sigLift/mapCompare/autoMap/
# autoBan/allowedCatsFor and the explainers are pure (no DOM, no esc/inc/
# MAP_CAT/CODE_WIPE), so they're declared above bootApp and directly testable.

_ONE = ("[{id:'m1',f1:'Alpha',f2:'Bravo',finished_at:'2026-07-01',"
        "games:[{game_no:1,map:'Oasis',map_category:'Control',map_picked_by:'Alpha',"
        "bans:[{team:'Alpha',hero:'D.Va',order:1},{team:'Bravo',hero:'Kiriko',order:2}]},"
        "{game_no:2,map:'Runasapi',map_category:'Push',map_picked_by:'Bravo',"
        "bans:[{team:'Alpha',hero:'D.Va',order:2},{team:'Bravo',hero:'Kiriko',order:1}]}]}]")


def test_sim_model_counts_only_that_team_s_picks_and_bans(tmp_path) -> None:
    got = _run(f"return simModelFrom({_ONE},'Alpha',0);", tmp_path)
    assert got["pick"] == {"Oasis": 1}            # Bravo picked Runasapi, not Alpha
    assert got["bansAll"] == {"D.Va": 2}          # Kiriko is Bravo's ban
    assert got["banByMap"]["Oasis"] == {"D.Va": 1}
    assert got["ngames"] == 2


def test_sim_model_tracks_game_keys_for_drilldown(tmp_path) -> None:
    got = _run(f"return simModelFrom({_ONE},'Alpha',0);", tmp_path)
    assert sorted(got["gkPick"]["Oasis"]) == ["m1:1"]
    assert sorted(got["gkBanAll"]["D.Va"]) == ["m1:1", "m1:2"]
    assert sorted(got["gkBanMap"]["Oasis"]["D.Va"]) == ["m1:1"]


def test_sim_model_windows_to_the_newest_maps(tmp_path) -> None:
    three = ("[{id:'w1',f1:'Alpha',f2:'B',finished_at:'2026-07-01',"
             "games:[{game_no:1,map:'Oasis',map_category:'Control',map_picked_by:'Alpha',"
             "bans:[{team:'Alpha',hero:'D.Va',order:1}]}]},"
             "{id:'w2',f1:'Alpha',f2:'B',finished_at:'2026-07-02',"
             "games:[{game_no:1,map:'Ilios',map_category:'Control',map_picked_by:'Alpha',"
             "bans:[{team:'Alpha',hero:'D.Va',order:1}]}]},"
             "{id:'w3',f1:'Alpha',f2:'B',finished_at:'2026-07-03',"
             "games:[{game_no:1,map:'Nepal',map_category:'Control',map_picked_by:'Alpha',"
             "bans:[{team:'Alpha',hero:'Zarya',order:1}]}]}]")
    full = _run(f"return simModelFrom({three},'Alpha',0);", tmp_path)
    assert full["pick"] == {"Oasis": 1, "Ilios": 1, "Nepal": 1} and full["ngames"] == 3
    win = _run(f"return simModelFrom({three},'Alpha',2);", tmp_path)
    assert win["pick"] == {"Ilios": 1, "Nepal": 1} and win["ngames"] == 2  # newest two


_MODEL = ("{banByMap:{Oasis:{'D.Va':3,Zarya:1}},bansAll:{Zarya:10,'D.Va':3,Kiriko:2},"
          "pick:{},gkPick:{},gkBanAll:{},gkBanMap:{}}")


def test_ban_suggest_ranks_a_strong_overall_staple_above_one_on_map_ban(tmp_path) -> None:
    got = _run(f"return banSuggest({_MODEL},'Oasis',new Set()).map(s=>s.hero);", tmp_path)
    assert got == ["Zarya", "D.Va", "Kiriko"]   # 1*2+10 > 3*2+3 > 0+2


def test_ban_suggest_excludes_illegal_heroes_and_caps_at_seven(tmp_path) -> None:
    got = _run(f"return banSuggest({_MODEL},'Oasis',new Set(['Zarya'])).map(s=>s.hero);",
               tmp_path)
    assert got == ["D.Va", "Kiriko"]
    big = ("{banByMap:{Oasis:{}},bansAll:"
           "{A:8,B:7,C:6,D:5,E:4,F:3,G:2,H:1,I:0},pick:{},gkPick:{},gkBanAll:{},gkBanMap:{}}")
    assert len(_run(f"return banSuggest({big},'Oasis',new Set());", tmp_path)) == 7


def test_sig_lift_requires_a_real_sample_and_lift(tmp_path) -> None:
    model = "{banByMap:{},bansAll:{'D.Va':5,Zarya:1},pick:{},gkPick:{},gkBanAll:{},gkBanMap:{}}"
    base = "{all:{'D.Va':0.1},first:{}}"
    assert _run(f"return sigLift({model},{base},'D.Va').sig;", tmp_path) is True
    assert _run(f"return sigLift({model},{base},'Zarya').sig;", tmp_path) is False  # < SIG_MIN
    assert _run(f"return sigLift({model},{{all:{{}},first:{{}}}},'D.Va').lift;",
                tmp_path) is None  # no field baseline -> no lift, no sig


def test_map_compare_prefers_team_picks_then_division_picks_then_plays(tmp_path) -> None:
    assert _run("return mapCompare('Oasis','Ilios',{Oasis:2},{Oasis:5},{Oasis:5});",
                tmp_path) < 0   # team picks beat everything
    assert _run("return mapCompare('Ilios','Oasis',{}, {Oasis:5},{Oasis:5});",
                tmp_path) > 0   # division picks beat nothing
    assert _run("return mapCompare('Ilios','Oasis',{}, {}, {Oasis:3});",
                tmp_path) > 0   # raw plays are the last resort
    assert _run("return mapCompare('Ilios','Oasis',{}, {}, {});",
                tmp_path) < 0   # ties break alphabetically (Ilios < Oasis)


def test_auto_map_respects_used_and_category(tmp_path) -> None:
    pool = "{Oasis:'Control',Ilios:'Control',Nepal:'Control',Blizzard:'Push'}"
    got = _run("return autoMap({},{Oasis:5},{}, ['Control'], new Set(['Oasis']),"
               f"{pool});", tmp_path)
    assert got == "Ilios"


def test_allowed_cats_g1_is_control_and_repeats_only_after_all_used(tmp_path) -> None:
    pool = ("{Oasis:'Control',Blizzard:'Push',Midtown:'Escort',Runasapi:'Push',"
            "Antarctic:'Flashpoint',Numbani:'Hybrid'}")
    assert _run(f"return allowedCatsFor(true, new Set(), {pool});", tmp_path) == ["Control"]
    fresh = _run(f"return allowedCatsFor(false, new Set(['Oasis']), {pool});", tmp_path)
    assert len(fresh) == 4 and "Control" not in fresh          # all non-Control, all fresh
    all4 = _run("return allowedCatsFor(false, new Set(['Blizzard','Midtown','Runasapi',"
                f"'Antarctic','Numbani']), {pool});", tmp_path)
    assert len(all4) == 4                                      # every mode used -> repeats


def test_auto_ban_returns_null_when_everything_is_illegal(tmp_path) -> None:
    assert _run(f"return autoBan({_MODEL},'Oasis',new Set(['Zarya','D.Va','Kiriko']));",
                tmp_path) is None
    assert _run(f"return autoBan({_MODEL},'Oasis',new Set());", tmp_path) == "Zarya"


def test_map_explain_phrases_team_data_vs_division_fallback(tmp_path) -> None:
    assert _run("return mapExplain('Alpha','Oasis','Control',5,10,true).text;",
                tmp_path).startswith("Alpha picked Oasis 5×") 
    assert "most-picked Control" in _run(
        "return mapExplain('Alpha','Oasis','Control',5,10,true).text;", tmp_path)
    fall = _run("return mapExplain('Alpha','Oasis','Control',0,10,true);", tmp_path)
    assert "no Alpha pick history" in fall["text"] and "division's most-picked" in fall["text"]
    assert fall["thin"] is True
    none = _run("return mapExplain('Alpha','Oasis','Control',0,0,false);", tmp_path)
    assert "no pick data" in none["text"] and none["thin"] is True


def test_map_explain_flags_a_single_pick_as_thin(tmp_path) -> None:
    got = _run("return mapExplain('Alpha','Oasis','Control',1,10,false);", tmp_path)
    assert got["thin"] is True


def test_ban_explain_phrases_overall_on_map_and_signature(tmp_path) -> None:
    text = _run("return banExplain('Alpha','Oasis','D.Va',5,2,true,true,true).text;", tmp_path)
    assert "most-banned hero overall" in text and "2 of them on Oasis" in text
    assert "★ signature" in text
    assert _run("return banExplain('Alpha','Oasis','D.Va',5,2,true,true,true).thin;",
                tmp_path) is False


def test_ban_explain_phrases_an_on_map_only_top(tmp_path) -> None:
    text = _run("return banExplain('Alpha','Oasis','D.Va',4,3,false,true,false).text;",
                tmp_path)
    assert "most-banned hero on Oasis" in text and "3× here" in text and "4× this season" in text
    assert "most-banned hero overall" not in text      # overall leader is someone else


def test_ban_explain_never_claims_most_after_an_override(tmp_path) -> None:
    text = _run("return banExplain('Alpha','Oasis','Zarya',4,0,false,false,false).text;",
                tmp_path)
    assert "banned 4× this season" in text and "most-banned" not in text


def test_ban_explain_flags_no_history_and_single_case(tmp_path) -> None:
    assert "no ban history" in _run(
        "return banExplain('Alpha','Oasis','Zarya',0,0,false,false,false).text;", tmp_path)
    assert _run("return banExplain('Alpha','Oasis','Zarya',1,1,false,false,false).thin;",
                tmp_path) is True


def test_mode_explain_mentions_league_share_and_team_preference(tmp_path) -> None:
    text = _run("return modeExplain('Alpha','Escort',38,2).text;", tmp_path)
    assert "38% of picks" in text and "picked Escort maps 2×" in text


def test_div_ban_base_shares_sum_to_one_and_guard_zero_total(tmp_path) -> None:
    got = _run(f"return divBanBaseFrom({_ONE});", tmp_path)
    assert round(got["all"]["D.Va"] + got["all"]["Kiriko"], 9) == 1
    empty = _run("return divBanBaseFrom([{id:'m',f1:'A',f2:'B',games:"
                 "[{game_no:1,map:'Oasis',map_category:'Control',bans:[]}]}]);", tmp_path)
    assert empty["all"] == {}
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/Scripts/python.exe -m pytest tests/test_dashboard_logic.py -k "sim_model or ban_suggest or sig_lift or map_compare or auto_map or allowed_cats or auto_ban or map_explain or ban_explain or mode_explain or div_ban_base" -v`
Expected: FAIL — `simModelFrom is not defined` (node ReferenceError).

- [ ] **Step 3: Add the pure functions**

In `faceit_sync/_dashboard.py`, find:

```
function codesFor(gkSet, lookup){
  return [...gkSet].map(k=>lookup.get(k)).filter(Boolean)
    .sort((a,b)=>String(b.when||'').localeCompare(String(a.when||'')));
}
```

Replace with the same `codesFor` followed by the `/* draft simulator — pure decision helpers */` block. Use the plan's version of `mapsFrom` (data's `g.map_category` only — no `MAP_CAT`, which is bootApp-scoped) and the plan's `banExplain` thin rule (`all===1`):

```js
function codesFor(gkSet, lookup){
  return [...gkSet].map(k=>lookup.get(k)).filter(Boolean)
    .sort((a,b)=>String(b.when||'').localeCompare(String(a.when||'')));
}

/* draft simulator — pure decision helpers */
const SIG_MIN=3, SIG_LIFT=2, SIM_MIN_MAPS=6;
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
function banSuggest(model, map, illegal){
  const onMap=model.banByMap[map]||{}, all=model.bansAll||{}, keys=new Set([...Object.keys(onMap),...Object.keys(all)]);
  const score=x=>x.onMap*2+x.all;
  return [...keys].filter(h=>!illegal.has(h))
    .map(h=>({hero:h,onMap:onMap[h]||0,all:all[h]||0}))
    .sort((a,b)=>(score(b)-score(a))||(b.onMap-a.onMap)).slice(0,7);
}
function sigLift(model, divBase, hero){
  const bans=model.bansAll[hero]||0;
  if(bans<SIG_MIN) return {sig:false, bans, lift:null};
  const tot=Object.values(model.bansAll).reduce((a,b)=>a+b,0)||1;
  const share=divBase.all[hero];
  const lift=share? (bans/tot)/share : null;
  return {sig: lift!=null && lift>=SIG_LIFT, bans, lift};
}
function allowedCatsFor(g1, used, pool){
  const MODES=['Control','Escort','Flashpoint','Hybrid','Push'];
  if(g1) return ['Control'];
  const usedCats=new Set([...used].map(mp=>pool[mp]));
  const nc=MODES.filter(x=>x!=='Control'), fresh=nc.filter(x=>!usedCats.has(x));
  return fresh.length? fresh : nc;
}
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
function mapExplain(teamName, map, cat, teamPicks, divPicks, isTopInCat){
  if(teamPicks>0) return {text:`${teamName} picked ${map} ${teamPicks}× this season`+
    (isTopInCat?` — their most-picked ${cat} map`:''), thin: teamPicks===1};
  if(divPicks>0) return {text:`no ${teamName} pick history on ${cat} — ${map} is the division's most-picked (${divPicks}× league-wide)`, thin:true};
  return {text:`no pick data on ${cat} — nothing to read yet`, thin:true};
}
function banExplain(teamName, map, hero, all, onMap, isTopOverall, isTopOnMap, sig){
  if(all===0) return {text:`no ban history for ${hero} — an experimental pick`, thin:true};
  let t, saidHere=false;
  if(isTopOverall) t = `${teamName}'s most-banned hero overall — ${all}× this season`;
  else if(isTopOnMap){ t = `their most-banned hero on ${map} — ${onMap}× here${onMap<all?`, ${all}× this season`:''}`; saidHere=true; }
  else t = `banned ${all}× this season`;
  if(onMap>0 && !saidHere) t += `, ${onMap} of them on ${map}`;
  if(sig) t += ` — ★ signature, well above the division rate`;
  return {text:t, thin: all===1};
}
function modeExplain(teamName, cat, leaguePct, teamModePicks){
  return {text:`${cat} — the league's most-picked remaining type (${leaguePct}% of picks)`+
    (teamModePicks>0?`; ${teamName} picked ${cat} maps ${teamModePicks}× themselves`:''),
    thin:false};
}
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv/Scripts/python.exe -m pytest tests/test_dashboard_logic.py -k "sim_model or ban_suggest or sig_lift or map_compare or auto_map or allowed_cats or auto_ban or map_explain or ban_explain or mode_explain or div_ban_base" -v`
Expected: all 18 new tests pass. `banSuggest`/`mapExplain` etc. already execute against the head — the harness proves the hoist is clean.

- [ ] **Step 5: Run the JS-syntax gate**

Run: `.venv/Scripts/python.exe -m pytest tests/test_export.py::test_dashboard_javascript_is_syntactically_valid -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add faceit_sync/_dashboard.py tests/test_dashboard_logic.py
git commit -m "dashboard: hoist draft-sim decision engine + explainers into the tested pure layer"
```

---

### Task 2: Back-compat wrappers; strip the old closures out of `renderSim`

**Files:**
- Modify: `faceit_sync/_dashboard.py`

**Interfaces:**
- Consumes: all of Task 1's pure functions.
- Produces: thin bootApp wrappers `simModel`, `divMaps`, `divBanBaseline` (old names, same return shapes as today); `sigMark` reimplemented on `sigLift`; the old `renderSim` closures deleted.

- [ ] **Step 1: Rewrite `divBanBaseline` as a delegator**

Find (`:1015-1025`):

```
let DIV_BAN_BASE=null;
function divBanBaseline(){
  if(DIV_BAN_BASE) return DIV_BAN_BASE;
  const all={}, first={};
  D().matches.forEach(m=>m.games.forEach(g=>{ if(!g.map) return;
    (g.bans||[]).forEach(b=>{ if(!b.hero) return; inc(all,b.hero);
      if(b.order===1) inc(first,b.hero); }); }));
  const shares=(o)=>{ const t=Object.values(o).reduce((a,b)=>a+b,0)||1; const s={};
    Object.entries(o).forEach(([h,n])=>s[h]=n/t); return s; };
  DIV_BAN_BASE={all:shares(all), first:shares(first)};
  return DIV_BAN_BASE;
}
```

Replace with:

```
let DIV_BAN_BASE=null;
function divBanBaseline(){
  if(DIV_BAN_BASE) return DIV_BAN_BASE;
  DIV_BAN_BASE=divBanBaseFrom(D().matches);
  return DIV_BAN_BASE;
}
```

- [ ] **Step 2: Rewrite `simModel`/`divMaps` as delegators**

Find (`:2956-2971`):

```
function simModel(team, limitGames){
  const pick={}, banByMap={}, bansAll={};
  const games=[];
  D().matches.forEach(m=>{
    const side=m.f1===team?'faction1':(m.f2===team?'faction2':null); if(!side)return;
    m.games.forEach(g=>{ if(g.map) games.push({g,at:m.finished_at||'',gno:g.game_no||0}); });
  });
  games.sort((a,b)=> (a.at<b.at?1:a.at>b.at?-1:0) || (b.gno-a.gno));   // newest first
  const use = (limitGames>0)? games.slice(0,limitGames) : games;
  use.forEach(({g})=>{
    if(g.map_picked_by===team) inc(pick,g.map);
    g.bans.filter(b=>b.team===team&&b.hero).forEach(b=>{ (banByMap[g.map]=banByMap[g.map]||{}); inc(banByMap[g.map],b.hero); inc(bansAll,b.hero); });
  });
  return {team,pick,banByMap,bansAll,ngames:use.length};
}
function divMaps(){ const s={}; D().matches.forEach(m=>m.games.forEach(g=>{ if(g.map) s[g.map]=g.map_category||MAP_CAT[g.map]||''; })); return s; }
```

Replace with:

```
function simModel(team, limitGames){
  return simModelFrom(D().matches, team, limitGames);
}
function divMaps(){
  const s=mapsFrom(D().matches);
  Object.keys(MAP_CAT).forEach(k=>{ if(!s[k]) s[k]=MAP_CAT[k]; });
  return s;
}
```

- [ ] **Step 3: Delete the old closures from `renderSim`**

Inside `renderSim` (`:2998`), remove: the `mapKey`/`cmpMap` pair (`:3040-3042`), the `allowedCatsFor` closure (`:3079-3084`), the `autoMap` closure (`:3085-3089`), the `autoBan` const (`:3090`), `SIG_MIN` (`:3095`) and the `sigMark` closure (`:3096-3100`). The hoisted versions and `SIG_MIN`/`SIG_LIFT` (now module-scoped) take their place. Keep the `divPick`/`divPlay` data computation (`:3036`), the `divModePick`/`divModeTot`/`modeShare` data (`:3044-3046`), and `setOv`.

`renderSim`'s existing call sites then change signature:
- `cmpMap(a,b,mf)` → `mapCompare(a,b,mf.pick,divPick,divPlay)` (in `mapButtons`).
- `allowedCatsFor(g1,used)` → `allowedCatsFor(g1,used,pool)`.
- `autoMap(mf,cats,used)` → `autoMap(mf.pick,divPick,divPlay,cats,used,pool)`.
- `autoBan(model,map,illegal)` unchanged.
- `sigMark(model,hero)` → reimplemented as a tiny local wrapper over `sigLift` + the ★ HTML (keep the same return shape: `''` or the ★ `<span>`), using `divBanBaseline()` for the baseline and `SIG_MIN`/`SIG_LIFT` from module scope.

- [ ] **Step 4: Run the JS-syntax gate**

Run: `.venv/Scripts/python.exe -m pytest tests/test_export.py::test_dashboard_javascript_is_syntactically_valid -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add faceit_sync/_dashboard.py
git commit -m "dashboard: delegate simModel/divMaps/divBanBaseline to the pure engine; drop renderSim closures"
```

---

### Task 3: Focused-card explainer strips + replay-code evidence

**Files:**
- Modify: `faceit_sync/_dashboard.py`

**Interfaces:**
- Consumes: `mapExplain`/`banExplain`/`modeExplain`, `simModelFrom`, `banSuggest`, `sigLift`, `codeLookup`/`codesFor`/`codesCell`, `esc`, `heroChip`.
- Produces: in `draw()`, a `lookup` per draw and a selection-driven explainer line under the Map row and each Ban row of the focused node, each with a codes cell for the backing games.

- [ ] **Step 1: Build `lookup` once per `draw()`**

Near the top of `draw()` in `renderSim` (`:3103`), after the models are built (`:3106-3108`), add:

```
const lookup=codeLookup(D().matches, SIM_A, CODE_WIPE);
```

- [ ] **Step 2: Compute the explainer inputs per focused node**

Inside `node()`'s focused branch (`:3140`), after `b1`/`b2`/`map` resolve (`:3129-3135`), compute (the `isTop*` flags compare against the current **legal** suggestion set so every "most" claim is literally true):

```
const mfNow = modelOf(picker);
const selMap = map;
const mapWhy = selMap? mapExplain(nameOf(picker), selMap, pool[selMap], mfNow.pick[selMap]||0,
    divPick[selMap]||0, isTopMapInCat(mfNow, selMap)) : null;
const banWhy = (model, hero, ill)=>{
  const all = model.bansAll[hero]||0, onMap = (model.banByMap[selMap]||{})[hero]||0;
  const maxAll = Math.max(0, ...Object.entries(model.bansAll||{})
    .filter(([h])=>!ill.has(h)).map(([,n])=>n));
  const maxOnMap = Math.max(0, ...Object.entries(model.banByMap[selMap]||{})
    .filter(([h])=>!ill.has(h)).map(([,n])=>n));
  const isTopOverall = all>0 && all===maxAll;
  const isTopOnMap = onMap>0 && onMap===maxOnMap;
  const sig = sigLift(model, dbase, hero).sig;
  return banExplain(nameOf(model===A?'A':'B'), selMap, hero, all, onMap, isTopOverall, isTopOnMap, sig);
};
```

Where `isTopMapInCat` is defined once in `renderSim`, above `node`:

```
const isTopMapInCat = (mf, mp)=> (mf.pick[mp]||0)>0 && Object.keys(pool)
  .filter(x=>pool[x]===pool[mp]).every(x=> (mf.pick[mp]||0) >= (mf.pick[x]||0));
```

(`modelOf`/`nameOf`/`opp` already exist; `dbase` is `divBanBaseline()` from `:3003`.)

- [ ] **Step 3: Render the strips in the focused card**

Map row (`:3145-3164`): after the map/mode buttons append (map picks are full-season, so the evidence comes from `modelFull(picker)`):

```
if(mapWhy) card.appendChild(el(`<p class="whyline">Why <b>${esc(map)}</b>? ${esc(mapWhy.text)}${mapWhy.thin?` <span class="thin">— thin, treat as a hint</span>`:''}`+
  ` ${codesCell(codesFor(modelFull(picker).gkPick[map]||new Set(), lookup))}</p>`));
```

Ban rows (`:3165-3172`): after each `r1`/`r2` row append a line narrating `b1`/`b2` (bans use the recent-window model, matching the chip counts):

```
const whyRow = (hero, model, ill)=>{
  const e = hero? banWhy(model, hero, ill) : null;
  if(!e) return '';
  return `<p class="whyline">Why <b>${heroChip(hero)}</b>? ${esc(e.text)}${e.thin?` <span class="thin">— a single case, not a pattern</span>`:''}`+
    ` ${codesCell(codesFor(((model.gkBanMap[map]||{})[hero])||(model.gkBanAll[hero]||new Set()), lookup))}</p>`;
};
card.appendChild(el(whyRow(b1, modelOf(picker), ill1)));
card.appendChild(el(whyRow(b2, modelOf(other), ill2)));
```

(Backticks inside template literals are fine here — `_dashboard.py` already nests them; the plan's inline code is illustrative, the implementer should match the file's existing escaping.)

- [ ] **Step 4: Add the CSS**

Near the existing `/* scenario tree */` block (`:221`), add:

```
.whyline{font-size:12px;color:var(--muted);margin:4px 0 8px 95px;display:flex;align-items:center;gap:8px;flex-wrap:wrap}
.whyline .thin{color:var(--bad);font-weight:600}
```

(Adjust `95px` to align with the row label gutter if the focused card's layout needs it.)

- [ ] **Step 5: Run the JS-syntax gate**

Run: `.venv/Scripts/python.exe -m pytest tests/test_export.py::test_dashboard_javascript_is_syntactically_valid -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add faceit_sync/_dashboard.py
git commit -m "dashboard: draft sim focused card explains each pick + ban with replay-code evidence"
```

---

### Task 4: Readability — controls microcopy, legend, status line, chip counts

**Files:**
- Modify: `faceit_sync/_dashboard.py`

- [ ] **Step 1: Controls microcopy strip**

After the controls bar (`:3027`), before the old intro paragraph, insert:

```
wrap.appendChild(el(`<p class="note" style="margin:8px 2px 0"><b>${esc(SIM_FIRST==='A'?SIM_A:SIM_B)}</b> picks Game 1 and bans first. The loser of each map picks the next one.</p>`));
```

(The text should reflect `SIM_FIRST`; re-render on `draw()`.)

- [ ] **Step 2: Replace the wall-of-text intro with a compact legend**

Replace the `:3028` paragraph with:

```
wrap.appendChild(el(`<div class="simlegend">
  <div><span class="pp">3×</span> on a map chip = times that team has picked it this season</div>
  <div><span class="pp">2× here · 5×</span> on a ban chip = bans on this map · this season</div>
  <div><span class="pp">★</span> = signature ban — repeated well above the division rate</div>
  <div>A team can't repeat its own ban down a line</div>
</div>`));
```

With CSS:

```
.simlegend{margin:4px 2px 0;font-size:12px;color:var(--faint);display:flex;flex-direction:column;gap:3px}
```

- [ ] **Step 3: Standardize ban-chip counts**

In `banButtons` (`:3068`), the count becomes the always-two-part format:
`const cnt = s.onMap>0 ? `${s.onMap}× here · ${s.all}×` : `${s.all}× total`;`

- [ ] **Step 4: Weak-sample status line**

Extend the existing status line (`:3110-3112`) so that when `SIM_RECENT>0` and either model's `ngames < SIM_RECENT`, it appends ` — only ${n} of the last ${SIM_RECENT} games on record for ${team}, so this read is thin, not a pattern.`; and when `SIM_RECENT===0` and either `ngames < SIM_MIN_MAPS`, append ` — ${team} has only ${n} maps of history; treat this read as a hint.`

- [ ] **Step 5: Run the JS-syntax gate**

Run: `.venv/Scripts/python.exe -m pytest tests/test_export.py::test_dashboard_javascript_is_syntactically_valid -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add faceit_sync/_dashboard.py
git commit -m "dashboard: draft sim readability - controls microcopy, legend, thin-data warnings"
```

---

### Task 5: Full verification pass + beta-label decision

**Files:** None modified unless Step 3 surfaces fixes.

- [ ] **Step 1: Full test suite**

Run: `.venv/Scripts/python.exe -m pytest`
Expected: all pass (including the new draft-sim cases).

- [ ] **Step 2: Type check**

Run: `.venv/Scripts/python.exe -m mypy faceit_sync`
Expected: clean — all edits are inside the `HTML_TEMPLATE` string literal.

- [ ] **Step 3: Rebuild and visual/interaction check**

```bash
.venv/Scripts/python.exe -m faceit_sync.cli export --format html --out dashboard.html
```

Screenshot `#scout=<team>` with the sim section expanded for two teams — one with a rich ban/pick history, one with thin history (a team near the bottom of the standings). Confirm:

- The controls show the "picks Game 1 and bans first" microcopy and the legend renders.
- The focused card's Map row and both Ban rows show a plain-language "Why …?" line that narrates the auto-selected value; clicking a different map/ban chip updates that line (no false "most-picked" claims on an override).
- The "2× here · 5×" chip format renders; ★ appears on signature bans.
- The status line flags a thin read for the thin-history team.
- Codes links/cells appear in the Why lines and the `.codespop` popover opens with the right games (if a real browser/Playwright is available); wiped codes show the "code wiped" tag.
- The condensed (mini) nodes still render at today's density.

- [ ] **Step 4: Clean up the local preview build**

```bash
rm -f dashboard.html
```

- [ ] **Step 5: Beta-label decision (ask the user, don't assume)**

The design doc flags graduating the sim out of beta (drop the `beta` opener at `:2763`) now that its logic is tested and every suggestion is explained. Ask the operator; if yes, one-word edit + re-run the JS gate + commit.

- [ ] **Step 6: Final commit (only if Steps 3-5 surfaced fixes)**

If the visual pass required touch-ups or the beta label changed, commit them with a message describing what it caught. Otherwise Tasks 1-4's commits are the complete change set.

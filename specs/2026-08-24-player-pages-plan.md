# Player Pages Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** An individual page per player at `#player=<nick>` showing their season across every division — team timeline, mode and map win rates against their team's, per-map stat averages against same-role peers, and the hero pool captures have proved.

**Architecture:** All aggregation is client-side in `faceit_sync/dashboard/pure.js`, built from two low-level scans (`playerGames`, `teamRecords`) that five small derivation functions read. `playerSeason` composes them. Rendering is a non-nav pseudo-tab in `app.js`, reached by hash like `#match=` and `#compare=` already are. One export change adds `mit` to game rosters.

**Tech Stack:** Python 3 (`faceit_sync`), plain ES2020 JavaScript (the codebase already uses optional chaining) (no framework, no bundler — the dashboard is four concatenated static files), pytest driving node for the pure layer.

**Spec:** `specs/2026-08-24-player-pages-design.md`

## Global Constraints

Copied from the spec and from `AGENTS.md`. Every task's requirements implicitly include this section.

- **Dev environment is Windows; use the venv Python directly:** `.venv/Scripts/python.exe -m pytest`.
- **Never hand-edit `docs/index.html`.** It is a build artifact; CI regenerates it. Fix the part file under `faceit_sync/dashboard/`.
- **Never run `faceit-sync export` onto `docs/index.html`.** The local `faceit.sqlite3` runs days behind CI's; committing a local export overwrites fresh data with stale data. Build previews to a scratch path.
- **After editing anything under `faceit_sync/dashboard/`, run the three mandatory tests** (see Task 10). One JS syntax error blanks the entire page and bracket-balance checks do not catch it.
- **Pure/impure split:** everything executable without a DOM goes in `pure.js`, above `bootApp(`. Rendering goes in `app.js`. Logic that can mislead a coach belongs in `pure.js`.
- **`docs/theme.css` is the design system.** A page that restates a token's value is the bug. Radii come from `--r-sm/-md/-lg/-pill`; `--on-accent` is the ink for any saturated fill. A selector defined in both data pages fails `tests/test_ui_consistency.py`.
- **Never put developer documentation in `docs/`** — it is the GitHub Pages web root. Specs live in `specs/`.
- **Match sources go through `leagueMatches(matches, playoffs)`**, never `div.matches` directly, or playoff games silently vanish. `leagueMatches` returns **newest first**.
- **Floors:** `PLAYER_MODE_MIN = PLAYER_MAP_MIN = PLAYER_HERO_MIN = 5`. A rate under its floor is `null`, never a number.
- **Commit message style:** an imperative sentence, no `feat:`/`fix:` prefix (`git log` shows "Scout a team's playoff run, not just its regular season"). End commit messages with the `Co-Authored-By` trailer.
- **Do not commit `owdb_comps.json`** and do not commit a seeded `docs/capture/data.json`.
- **Work on a branch.** `main` is the default branch and CI auto-commits to it; `git fetch` before pushing.

---

## File Structure

| File | Change | Responsibility |
| --- | --- | --- |
| `faceit_sync/export.py` | Modify `:442-453` | Add `mit` to the per-game roster rows |
| `faceit_sync/dashboard/pure.js` | Append | `playerGames`, `teamRecords`, `playerSpells`, `playerMapRecord`, `playerHeroPool`, `playerDivisions`, `mergePlayerStats`, `playerSeason`, the three floor constants |
| `faceit_sync/dashboard/app.js` | Modify | `PLAYER_NICK` state, `gotoPlayer`, the `[data-player]` delegate, `hashFor`/`hashDispatch`/`show` cases, `renderPlayer`, player links in three existing views |
| `faceit_sync/dashboard/head.html` | Modify | One new CSS component: the team-swap timeline strip |
| `tests/test_dashboard_logic.py` | Append | Behavioural tests for every pure function above |
| `tests/test_export.py` | Append | Assert game rosters carry `mit` |
| `CHANGELOG.md`, `ARCHITECTURE.md`, `specs/BACKLOG.md`, `FEATURES.md` | Modify | Task 10 |

---

## Task 1: Ship mitigation on per-game rosters

Per-game roster rows carry `e / d / dmg / heal` but not `mit`, so a Tank's per-map table would omit the stat their season card leads with. Cost measured at +512 KB raw (~60 KB gzipped) on a 9.14 MB page.

**Files:**
- Modify: `faceit_sync/export.py:442-453`
- Test: `tests/test_export.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `matches[].games[].rosters[].players[].mit` — an integer or `null` — in the inlined payload. Tasks 2 and 9 read it.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_export.py`. There is **no** `_exported_payload` helper in
that file — the convention is the `db` fixture plus `_insert_match`, an in-memory
`export_html`, and a regex slice. Copy it exactly:

```python
def test_game_rosters_carry_mitigation(db: Database) -> None:
    """A Tank's per-map stat line needs mitigation; the season card already shows
    it, so a per-game table without it reads as a missing number rather than an
    absent column."""
    c = db.conn
    c.execute("INSERT INTO maps(guid,name,category) VALUES('m1','Ilios','Control')")
    for tid, nm in [("t1", "Alpha"), ("t2", "Bravo")]:
        c.execute("INSERT INTO teams(id,name) VALUES(?,?)", (tid, nm))
    c.execute("INSERT INTO championships(id,name,game,region) VALUES(?,?,?,'GLOBAL')",
              ("em", "S9 EMEA Master Central - Regular Season", "ow2"))
    _insert_match(db, "em", "m1", "FINISHED", "t1", "t2", "faction1", None,
                  "2026-07-20T20:00:00Z", 1, ["faction1"])
    c.execute("INSERT INTO players(id,nickname,game_name) VALUES('p1','Blip','Blip#1')")
    c.execute(
        "INSERT INTO round_players(match_id,game_no,team_id,player_id,role,elo_snapshot,"
        "stats_captured,eliminations,deaths,assists,damage,healing,damage_mitigated) "
        "VALUES('m1',1,'t1','p1','Tank',2000,1,20,5,3,8000,0,9000)")
    db.conn.commit()

    buf = io.StringIO()
    export_html(db, buf)
    data = json.loads(re.search(r"var __OWDB_DATA__=(\{.*\});", buf.getvalue())
                      .group(1).replace("<\\/", "</"))
    rows = [p for div in data["divisions"].values()
            for m in div["matches"] for g in m["games"]
            for r in g["rosters"] for p in r["players"]]
    assert rows, "fixture exported no per-game roster rows"
    assert all("mit" in p for p in rows)
    assert rows[0]["mit"] == 9000
```

- [ ] **Step 2: Run test to verify it fails**

```bash
.venv/Scripts/python.exe -m pytest tests/test_export.py::test_game_rosters_carry_mitigation -v
```

Expected: FAIL — `assert all("mit" in p for p in rows)` is False.

- [ ] **Step 3: Add the column**

In `faceit_sync/export.py`, the per-game roster query at `:443-449`. Add `rp.damage_mitigated` to the SELECT and `mit` to the emitted dict:

```python
            for rp in rows("""SELECT rp.team_id, COALESCE(p.nickname, rp.player_id) nick,
                                     rp.role, rp.stats_captured cap, rp.eliminations e,
                                     rp.deaths d, rp.damage dmg, rp.healing heal,
                                     rp.damage_mitigated mit
                              FROM round_players rp LEFT JOIN players p ON p.id=rp.player_id
                              WHERE rp.match_id=? AND rp.game_no=?""", m["id"], gno):
                tname = tid_name.get(rp["team_id"]) or "?"
                by_team.setdefault(tname, []).append({
                    "nick": rp["nick"], "role": rp["role"], "cap": bool(rp["cap"]),
                    "e": rp["e"], "d": rp["d"], "dmg": rp["dmg"], "heal": rp["heal"],
                    "mit": rp["mit"],
                })
```

`damage_mitigated` is NULL for zeroed rows (data hazard A), and `null` is the correct value there — do not coalesce it to 0, which would claim a measurement that was never taken.

- [ ] **Step 4: Run the tests**

```bash
.venv/Scripts/python.exe -m pytest tests/test_export.py -v
.venv/Scripts/python.exe -m mypy faceit_sync
```

Expected: all PASS, mypy clean.

- [ ] **Step 5: Commit**

```bash
git add faceit_sync/export.py tests/test_export.py
git commit -m "Ship mitigation on per-game rosters, not just season averages"
```

---

## Task 2: Scan a player's games and every team's record

The two low-level scans everything else derives from. Keeping them separate means the games are walked once and the derivations are each testable against a hand-built list.

**Files:**
- Modify: `faceit_sync/dashboard/pure.js` (append, above `bootApp`)
- Test: `tests/test_dashboard_logic.py`

**Interfaces:**
- Consumes: `leagueMatches(matches, playoffs)` — already in `pure.js:181`, returns newest first.
- Produces:
  - `PLAYER_MODE_MIN`, `PLAYER_MAP_MIN`, `PLAYER_HERO_MIN` — all `5`.
  - `playerRate(wins, games, floor) -> number|null`
  - `playerGames(nick, divisions, pergame) -> [{cid, division, matchId, at, team, opponent, map, mode, won, stats:{e,d,dmg,heal,mit}, hero}]`, newest first.
  - `teamRecords(divisions) -> {"<cid>|<team>": {mode:{[m]:{games,wins}}, map:{[m]:{games,wins}}}}`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_dashboard_logic.py`. First the shared fixture builder — put it at module level near the other helpers:

```python
# --- player pages ----------------------------------------------------------
# A player's season is assembled from two scans. The fixture builds divisions
# out of one-game matches, because every claim under test is per game: which
# team a player was on, whether that game was won, and when it happened.

_PLAYER_FIX = """
const stat=(n)=>({e:n,d:5,dmg:1000*n,heal:0,mit:100*n});
// one match, one game, `nick` on `team` (omit nick for a game they sat out)
const mk=(id,at,team,opp,map,cat,won,nick)=>({
  id:id, finished_at:at, f1:team, f2:opp, winner_team:(won?team:opp),
  games:[{game_no:1, map:map, map_category:cat, winner_team:(won?team:opp),
    rosters:[
      {team:team, players:(nick?[{nick:nick,role:'Tank',...stat(20)}]:[])},
      {team:opp,  players:[]}]}]});
const div=(label,teams,matches,playoffs)=>({
  summary:{championship:label}, teams:teams, matches:matches,
  playoffs:(playoffs||[])});
"""


def _prun(body: str, tmp_path) -> object:
    """Run a player-page test body with the fixture builders in scope."""
    return _run(_PLAYER_FIX + body, tmp_path)
```

Then the tests:

```python
def test_player_games_include_playoff_games(tmp_path) -> None:
    """Team-facing reads once stopped at the group stage (fixed 2026-08-20).
    A player page reading div.matches directly would reintroduce exactly that."""
    got = _prun("""
      const DIVS={m1:div('EMEA Master',[],
        [mk('M1','2026-07-01T00:00:00Z','Alpha','Zeta','Ilios','Control',true,'Blip')],
        [{id:'P1',status:'FINISHED',finished_at:'2026-07-25T00:00:00Z',
          f1:'Alpha',f2:'Zeta',winner_team:'Alpha',
          games:[{game_no:1,map:'Ilios',map_category:'Control',winner_team:'Alpha',
            rosters:[{team:'Alpha',players:[{nick:'Blip',role:'Tank',e:20,d:5,dmg:20000,heal:0,mit:2000}]},
                     {team:'Zeta',players:[]}]}]}])};
      return playerGames('Blip', DIVS, {}).map(g=>g.matchId);
    """, tmp_path)
    assert got == ["P1", "M1"]          # newest first, playoff game present


def test_player_games_skip_walkovers_and_other_players(tmp_path) -> None:
    got = _prun("""
      const DIVS={m1:div('EMEA Master',[],[
        mk('M1','2026-07-01T00:00:00Z','Alpha','Zeta','Ilios','Control',true,'Blip'),
        mk('M2','2026-07-02T00:00:00Z','Alpha','Zeta','Nepal','Control',true,'Other'),
        {id:'M3',finished_at:'2026-07-03T00:00:00Z',f1:'Alpha',f2:'Zeta',
         winner_team:'Alpha',games:[{game_no:1,map:null,map_category:null,
           winner_team:'Alpha',rosters:[]}]}
      ],[])};
      return playerGames('Blip', DIVS, {}).map(g=>g.map);
    """, tmp_path)
    assert got == ["Ilios"]


def test_player_games_carry_opponent_result_and_hero(tmp_path) -> None:
    got = _prun("""
      const DIVS={m1:div('EMEA Master',[],
        [mk('M1','2026-07-01T00:00:00Z','Alpha','Zeta','Ilios','Control',false,'Blip')],[])};
      return playerGames('Blip', DIVS, {'M1:1':{Blip:'Winston'}})[0];
    """, tmp_path)
    assert got["team"] == "Alpha"
    assert got["opponent"] == "Zeta"
    assert got["won"] is False
    assert got["hero"] == "Winston"
    assert got["mode"] == "Control"
    assert got["division"] == "EMEA Master"
    assert got["stats"]["mit"] == 2000


def test_player_games_hero_is_null_without_attribution(tmp_path) -> None:
    """10.8% of players have any attributed game. A missing hero is the normal
    case, not an error, and must not become the string 'undefined'."""
    got = _prun("""
      const DIVS={m1:div('EMEA Master',[],
        [mk('M1','2026-07-01T00:00:00Z','Alpha','Zeta','Ilios','Control',true,'Blip')],[])};
      return playerGames('Blip', DIVS, {})[0].hero;
    """, tmp_path)
    assert got is None


def test_team_records_count_every_game_not_just_the_players(tmp_path) -> None:
    """teamWr's whole purpose is to be the team's record, including games the
    player sat out - otherwise it is the player's own number twice over."""
    got = _prun("""
      const DIVS={m1:div('EMEA Master',[],[
        mk('M1','2026-07-01T00:00:00Z','Alpha','Zeta','Ilios','Control',true,'Blip'),
        mk('M2','2026-07-02T00:00:00Z','Alpha','Zeta','Ilios','Control',false,null)
      ],[])};
      const r=teamRecords(DIVS);
      return {alpha:r['m1|Alpha'].map.Ilios, zeta:r['m1|Zeta'].mode.Control};
    """, tmp_path)
    assert got["alpha"] == {"games": 2, "wins": 1}
    assert got["zeta"] == {"games": 2, "wins": 1}
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
.venv/Scripts/python.exe -m pytest tests/test_dashboard_logic.py -k player -v
```

Expected: FAIL — node reports `playerGames is not defined`.

- [ ] **Step 3: Implement the scans**

Append to `faceit_sync/dashboard/pure.js`:

```js
// ---- Player pages ---------------------------------------------------------
// A player's season, across every division in the payload. Season-scoped on
// purpose: the payload is exported --season, so "every division" IS the season,
// and it is the only scope in which a mid-season team or division move can be
// shown as one player rather than two.
//
// Every rate here refuses under a floor. Measured 2026-08-24: the median player
// has 38 maps but only 3 per map and 8 per mode, and only 10.8% have any
// captured hero attribution at all. A 3-game win rate reads to a coach as a
// fact, so the pure layer returns null and lets the page say why.
const PLAYER_MODE_MIN=5, PLAYER_MAP_MIN=5, PLAYER_HERO_MIN=5;

function playerRate(wins, games, floor){
  return games>=floor ? Math.round(100*wins/games) : null;
}
function _pbump(t, k, won){
  if(k==null) return;
  const c=t[k]||(t[k]={games:0,wins:0}); c.games++; if(won) c.wins++;
}

// Every game this player appeared in, newest first, flattened across divisions.
// Playoff games come through leagueMatches — reading div.matches directly is the
// bug fixed on 2026-08-20, where team reads silently stopped at the group stage.
function playerGames(nick, divisions, pergame){
  const out=[];
  if(!nick||!divisions) return out;
  Object.keys(divisions).forEach(cid=>{
    const div=divisions[cid]||{};
    const label=(div.summary&&div.summary.championship)||cid;
    leagueMatches(div.matches, div.playoffs).forEach(m=>{
      (m.games||[]).forEach(g=>{
        if(!g.map) return;                       // walkover or unplayed slot
        (g.rosters||[]).forEach(r=>{
          const team=r&&r.team;
          if(!team||team==='?') return;
          const me=(r.players||[]).find(p=>p&&p.nick===nick);
          if(!me) return;
          const at=m.finished_at||'';
          out.push({cid:cid, division:label, matchId:m.id, at:at, team:team,
                    opponent:(m.f1===team?m.f2:m.f1)||null,
                    map:g.map, mode:g.map_category||'Other',
                    won:g.winner_team===team,
                    stats:{e:me.e, d:me.d, dmg:me.dmg, heal:me.heal,
                           mit:(me.mit==null?null:me.mit)},
                    hero:((pergame||{})[m.id+':'+g.game_no]||{})[nick]||null});
        });
      });
    });
  });
  return out.sort((a,b)=>(b.at||'').localeCompare(a.at||''));
}

// Every team's own map and mode record, keyed "<cid>|<team>". This is what a
// player's rate is shown against: they play with the same four teammates, so
// their map record is largely the team's, and only the gap is a player signal.
// It counts games the player sat out, which is the entire point.
function teamRecords(divisions){
  const out={};
  if(!divisions) return out;
  Object.keys(divisions).forEach(cid=>{
    const div=divisions[cid]||{};
    leagueMatches(div.matches, div.playoffs).forEach(m=>{
      (m.games||[]).forEach(g=>{
        if(!g.map) return;
        (g.rosters||[]).forEach(r=>{
          const team=r&&r.team;
          if(!team||team==='?') return;
          const k=cid+'|'+team, won=g.winner_team===team;
          const rec=out[k]||(out[k]={mode:{},map:{}});
          _pbump(rec.mode, g.map_category||'Other', won);
          _pbump(rec.map, g.map, won);
        });
      });
    });
  });
  return out;
}
```

- [ ] **Step 4: Run the tests**

```bash
.venv/Scripts/python.exe -m pytest tests/test_dashboard_logic.py -k player -v
.venv/Scripts/python.exe -m pytest tests/test_export.py::test_dashboard_javascript_is_syntactically_valid -v
```

Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add faceit_sync/dashboard/pure.js tests/test_dashboard_logic.py
git commit -m "Scan a player's games and every team's record"
```

---

## Task 3: Build the team timeline from game chronology

Derives the spells a player had, in order, so a mid-season swap reads as "Alpha until 2026-07-02, Beta since 2026-07-20" rather than one blurred "current team".

**Files:**
- Modify: `faceit_sync/dashboard/pure.js`
- Test: `tests/test_dashboard_logic.py`

**Interfaces:**
- Consumes: `playerGames(...)` output from Task 2.
- Produces: `playerSpells(games) -> {spells:[{cid, division, team, games, firstSeen, lastSeen}], current:{team, division, cid}|null}`. `spells` is oldest-first; `current` is the spell with the latest `lastSeen`.

- [ ] **Step 1: Write the failing tests**

```python
def test_player_spells_are_chronological_across_a_mid_season_swap(tmp_path) -> None:
    got = _prun("""
      const DIVS={m1:div('EMEA Master',[],[
        mk('M1','2026-07-01T00:00:00Z','Alpha','Zeta','Ilios','Control',true,'Blip'),
        mk('M2','2026-07-02T00:00:00Z','Alpha','Zeta','Nepal','Control',true,'Blip'),
        mk('M3','2026-07-20T00:00:00Z','Beta','Zeta','Ilios','Control',true,'Blip')
      ],[])};
      return playerSpells(playerGames('Blip', DIVS, {}));
    """, tmp_path)
    assert [s["team"] for s in got["spells"]] == ["Alpha", "Beta"]
    assert got["spells"][0]["games"] == 2
    assert got["spells"][0]["firstSeen"] == "2026-07-01T00:00:00Z"
    assert got["spells"][0]["lastSeen"] == "2026-07-02T00:00:00Z"
    assert got["current"]["team"] == "Beta"


def test_player_spells_span_divisions(tmp_path) -> None:
    """17 of 1187 players moved division mid-season. The earlier division is a
    spell, not a separate player."""
    got = _prun("""
      const DIVS={
        m1:div('EMEA Master',[],[mk('M2','2026-07-20T00:00:00Z','Beta','Zeta','Ilios','Control',true,'Blip')],[]),
        m2:div('EMEA Expert',[],[mk('M1','2026-06-10T00:00:00Z','Gamma','Delta','Numbani','Hybrid',true,'Blip')],[])};
      return playerSpells(playerGames('Blip', DIVS, {})).spells
               .map(s=>s.division+'/'+s.team);
    """, tmp_path)
    assert got == ["EMEA Expert/Gamma", "EMEA Master/Beta"]


def test_player_spells_are_empty_for_an_unknown_nick(tmp_path) -> None:
    got = _prun("""
      const DIVS={m1:div('EMEA Master',[],
        [mk('M1','2026-07-01T00:00:00Z','Alpha','Zeta','Ilios','Control',true,'Blip')],[])};
      return playerSpells(playerGames('Nobody', DIVS, {}));
    """, tmp_path)
    assert got["spells"] == []
    assert got["current"] is None
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
.venv/Scripts/python.exe -m pytest tests/test_dashboard_logic.py -k spells -v
```

Expected: FAIL — `playerSpells is not defined`.

- [ ] **Step 3: Implement**

Append to `pure.js`:

```js
// The teams a player actually played for, in order, with real first/last dates.
// Derived from game chronology rather than roster[].last_seen, which knows only
// the final date per (team, player) and so cannot date the start of a spell.
function playerSpells(games){
  const by={};
  (games||[]).forEach(g=>{
    const k=g.cid+'|'+g.team;
    const s=by[k]||(by[k]={cid:g.cid, division:g.division, team:g.team,
                           games:0, firstSeen:'', lastSeen:''});
    s.games++;
    const at=g.at||'';
    if(at){
      if(!s.firstSeen||at<s.firstSeen) s.firstSeen=at;
      if(at>s.lastSeen) s.lastSeen=at;
    }
  });
  const spells=Object.keys(by).map(k=>by[k]).sort((a,b)=>
    (a.firstSeen||'').localeCompare(b.firstSeen||'') || a.team.localeCompare(b.team));
  let cur=null;
  spells.forEach(s=>{ if(!cur||(s.lastSeen||'')>(cur.lastSeen||'')) cur=s; });
  return {spells:spells,
          current:cur?{team:cur.team, division:cur.division, cid:cur.cid}:null};
}
```

- [ ] **Step 4: Run the tests**

```bash
.venv/Scripts/python.exe -m pytest tests/test_dashboard_logic.py -k player -v
```

Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add faceit_sync/dashboard/pure.js tests/test_dashboard_logic.py
git commit -m "Read a player's team timeline off the games, not the roster row"
```

---

## Task 4: Mode and map win rates, shown against the team's

Mode is the headline grain (median 8 games) and map the drill-down (median 3). Every row carries its `n` and the record of the teams the player played it for.

**Files:**
- Modify: `faceit_sync/dashboard/pure.js`
- Test: `tests/test_dashboard_logic.py`

**Interfaces:**
- Consumes: `playerGames(...)` (Task 2), `teamRecords(...)` (Task 2), `playerRate`, `PLAYER_MODE_MIN`, `PLAYER_MAP_MIN`.
- Produces: `playerMapRecord(games, records) -> {modes:[row], maps:[row]}` where a row is `{mode|map, mode (on map rows), games, wins, wr:number|null, teamGames, teamWr:number|null}`. Both lists are sorted by `games` descending, then name.

- [ ] **Step 1: Write the failing tests**

```python
def test_player_map_record_refuses_below_the_floor_and_fires_at_it(tmp_path) -> None:
    """Median per-map sample is 3 games. The floor is the feature: null under,
    a number at, never a confident-looking figure from four games."""
    got = _prun("""
      const ms=[]; for(let i=0;i<4;i++)
        ms.push(mk('K'+i,'2026-07-0'+(i+1)+'T00:00:00Z','Alpha','Zeta','Kings Row','Hybrid',true,'Blip'));
      for(let i=0;i<5;i++)
        ms.push(mk('I'+i,'2026-07-1'+i+'T00:00:00Z','Alpha','Zeta','Ilios','Control',i<3,'Blip'));
      const DIVS={m1:div('EMEA Master',[],ms,[])};
      const r=playerMapRecord(playerGames('Blip',DIVS,{}), teamRecords(DIVS));
      const by={}; r.maps.forEach(m=>by[m.map]=m);
      return {kings:by['Kings Row'], ilios:by['Ilios']};
    """, tmp_path)
    assert got["kings"]["games"] == 4 and got["kings"]["wr"] is None
    assert got["ilios"]["games"] == 5 and got["ilios"]["wr"] == 60


def test_player_mode_record_aggregates_maps_into_modes(tmp_path) -> None:
    """Mode is the headline grain precisely because it clears the floor where
    the individual maps do not."""
    got = _prun("""
      const ms=[];
      ['Ilios','Nepal','Oasis'].forEach((mp,i)=>{
        ms.push(mk('A'+i,'2026-07-0'+(i+1)+'T00:00:00Z','Alpha','Zeta',mp,'Control',true,'Blip'));
        ms.push(mk('B'+i,'2026-07-1'+i+'T00:00:00Z','Alpha','Zeta',mp,'Control',false,'Blip'));
      });
      const DIVS={m1:div('EMEA Master',[],ms,[])};
      const r=playerMapRecord(playerGames('Blip',DIVS,{}), teamRecords(DIVS));
      return {modes:r.modes, mapWr:r.maps.map(m=>m.wr)};
    """, tmp_path)
    assert got["modes"][0] == {"mode": "Control", "games": 6, "wins": 3, "wr": 50,
                               "teamGames": 6, "teamWr": 50}
    assert got["mapWr"] == [None, None, None]      # 2 games each, all under the floor


def test_player_map_record_shows_the_teams_rate_including_games_they_missed(tmp_path) -> None:
    """A sub's divergence from their team is the one genuinely player-specific
    read here, and it only exists if teamWr counts the games they sat out."""
    got = _prun("""
      const ms=[];
      for(let i=0;i<5;i++)
        ms.push(mk('P'+i,'2026-07-0'+(i+1)+'T00:00:00Z','Alpha','Zeta','Ilios','Control',true,'Blip'));
      for(let i=0;i<5;i++)
        ms.push(mk('S'+i,'2026-07-1'+i+'T00:00:00Z','Alpha','Zeta','Ilios','Control',false,null));
      const DIVS={m1:div('EMEA Master',[],ms,[])};
      const r=playerMapRecord(playerGames('Blip',DIVS,{}), teamRecords(DIVS));
      return r.maps[0];
    """, tmp_path)
    assert got["games"] == 5 and got["wr"] == 100
    assert got["teamGames"] == 10 and got["teamWr"] == 50


def test_player_map_record_pools_the_teams_of_a_swapped_player(tmp_path) -> None:
    got = _prun("""
      const ms=[
        mk('M1','2026-07-01T00:00:00Z','Alpha','Zeta','Ilios','Control',true,'Blip'),
        mk('M2','2026-07-20T00:00:00Z','Beta','Zeta','Ilios','Control',false,'Blip')];
      const DIVS={m1:div('EMEA Master',[],ms,[])};
      const r=playerMapRecord(playerGames('Blip',DIVS,{}), teamRecords(DIVS));
      return r.maps[0].teamGames;
    """, tmp_path)
    assert got == 2      # Alpha's one game plus Beta's one, not Zeta's two
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
.venv/Scripts/python.exe -m pytest tests/test_dashboard_logic.py -k map_record -v
```

Expected: FAIL — `playerMapRecord is not defined`.

- [ ] **Step 3: Implement**

Append to `pure.js`:

```js
// A player's record by mode and by map, each row carrying the record of the
// teams they played it for. Mode is the headline grain (median 8 games) and map
// the drill-down (median 3) — which is why both floors exist and why the team's
// rate sits in the same row: a player's map record is largely their team's.
function playerMapRecord(games, records){
  const pMode={}, pMap={}, srcMode={}, srcMap={}, mapMode={};
  (games||[]).forEach(g=>{
    const tk=g.cid+'|'+g.team;
    _pbump(pMode, g.mode, g.won);
    _pbump(pMap, g.map, g.won);
    (srcMode[g.mode]||(srcMode[g.mode]={}))[tk]=1;
    (srcMap[g.map]||(srcMap[g.map]={}))[tk]=1;
    mapMode[g.map]=g.mode;
  });
  const teamSide=(src, key, kind)=>{
    let n=0, w=0;
    Object.keys(src[key]||{}).forEach(tk=>{
      const c=((records||{})[tk]||{})[kind];
      const e=c&&c[key];
      if(e){ n+=e.games; w+=e.wins; }
    });
    return {teamGames:n, teamWr:n?Math.round(100*w/n):null};
  };
  const modes=Object.keys(pMode).map(k=>Object.assign(
    {mode:k, games:pMode[k].games, wins:pMode[k].wins,
     wr:playerRate(pMode[k].wins, pMode[k].games, PLAYER_MODE_MIN)},
    teamSide(srcMode, k, 'mode')));
  const maps=Object.keys(pMap).map(k=>Object.assign(
    {map:k, mode:mapMode[k]||'Other', games:pMap[k].games, wins:pMap[k].wins,
     wr:playerRate(pMap[k].wins, pMap[k].games, PLAYER_MAP_MIN)},
    teamSide(srcMap, k, 'map')));
  const bySize=(a,b)=>b.games-a.games||String(a.map||a.mode).localeCompare(String(b.map||b.mode));
  return {modes:modes.sort(bySize), maps:maps.sort(bySize)};
}
```

- [ ] **Step 4: Run the tests**

```bash
.venv/Scripts/python.exe -m pytest tests/test_dashboard_logic.py -k player -v
```

Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add faceit_sync/dashboard/pure.js tests/test_dashboard_logic.py
git commit -m "Rate a player's maps and modes against their own team's record"
```

---

## Task 5: Hero pool, with win rate behind a hard floor

Two sources, deliberately: pool share comes from capture pools (factual at any sample), win rate from per-game attribution joined to results (blank below 5 games on that hero). "Pool share but no win rate" is the expected row at today's coverage.

**Files:**
- Modify: `faceit_sync/dashboard/pure.js`
- Test: `tests/test_dashboard_logic.py`

**Interfaces:**
- Consumes: `playerGames(...)` (Task 2), `playerRate`, `PLAYER_HERO_MIN`.
- Produces: `playerHeroPool(nick, games, comps) -> [{hero, rounds, share:number|null, games, wins, wr:number|null}]`, sorted by `rounds` desc, then `games` desc, then hero name. `comps` is `DATA.owdb_comps` (team-keyed).

- [ ] **Step 1: Write the failing tests**

```python
def test_player_hero_pool_reports_share_without_a_win_rate(tmp_path) -> None:
    """The expected row at today's coverage: 10.8% of players have any
    attribution at all and the median is 8 games across every hero they play."""
    got = _prun("""
      const DIVS={m1:div('EMEA Master',[],
        [mk('M1','2026-07-01T00:00:00Z','Alpha','Zeta','Ilios','Control',true,'Blip')],[])};
      const comps={Alpha:{scout:{players:[{player:'Blip',heroes:[
        {hero:'Winston',rounds:30},{hero:'D.Va',rounds:10}]}]}}};
      return playerHeroPool('Blip', playerGames('Blip',DIVS,{'M1:1':{Blip:'Winston'}}), comps);
    """, tmp_path)
    assert [h["hero"] for h in got] == ["Winston", "D.Va"]
    assert got[0]["share"] == 75 and got[0]["games"] == 1 and got[0]["wr"] is None
    assert got[1]["share"] == 25 and got[1]["games"] == 0


def test_player_hero_win_rate_appears_at_the_floor(tmp_path) -> None:
    got = _prun("""
      const ms=[]; for(let i=0;i<5;i++)
        ms.push(mk('M'+i,'2026-07-0'+(i+1)+'T00:00:00Z','Alpha','Zeta','Ilios','Control',i<4,'Blip'));
      const DIVS={m1:div('EMEA Master',[],ms,[])};
      const pg={}; for(let i=0;i<5;i++) pg['M'+i+':1']={Blip:'Winston'};
      const comps={Alpha:{scout:{players:[{player:'Blip',heroes:[{hero:'Winston',rounds:50}]}]}}};
      return playerHeroPool('Blip', playerGames('Blip',DIVS,pg), comps)[0];
    """, tmp_path)
    assert got["games"] == 5 and got["wins"] == 4 and got["wr"] == 80


def test_player_hero_pool_ignores_pools_from_teams_they_never_played_for(tmp_path) -> None:
    """Pools are matched by nick inside a team. A same-nick entry under a team
    the player never played for is not their pool."""
    got = _prun("""
      const DIVS={m1:div('EMEA Master',[],
        [mk('M1','2026-07-01T00:00:00Z','Alpha','Zeta','Ilios','Control',true,'Blip')],[])};
      const comps={
        Alpha:{scout:{players:[{player:'Blip',heroes:[{hero:'Winston',rounds:10}]}]}},
        Zeta: {scout:{players:[{player:'Blip',heroes:[{hero:'Sigma',rounds:99}]}]}}};
      return playerHeroPool('Blip', playerGames('Blip',DIVS,{}), comps).map(h=>h.hero);
    """, tmp_path)
    assert got == ["Winston"]


def test_player_hero_pool_is_empty_without_captures(tmp_path) -> None:
    """89% of players. Empty, not an error, and not a zero-length share."""
    got = _prun("""
      const DIVS={m1:div('EMEA Master',[],
        [mk('M1','2026-07-01T00:00:00Z','Alpha','Zeta','Ilios','Control',true,'Blip')],[])};
      return playerHeroPool('Blip', playerGames('Blip',DIVS,{}), {});
    """, tmp_path)
    assert got == []
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
.venv/Scripts/python.exe -m pytest tests/test_dashboard_logic.py -k hero_pool -v
```

Expected: FAIL — `playerHeroPool is not defined`.

- [ ] **Step 3: Implement**

Append to `pure.js`:

```js
// A player's heroes, from two sources that must not be conflated. `rounds` and
// `share` come from the capture pools and are factual at any sample size;
// `games`/`wins`/`wr` come from per-game attribution joined to the result, and
// the win rate refuses below PLAYER_HERO_MIN. A hero with a share and no win
// rate is the EXPECTED row — 10.8% of players have any attribution at all.
// Pools are read only from the teams the player actually played for: a pool is
// matched by nick inside a team, so a same-nick entry elsewhere is not theirs.
function playerHeroPool(nick, games, comps){
  const mine={}, tally={};
  (games||[]).forEach(g=>{
    mine[g.team]=1;
    if(g.hero) _pbump(tally, g.hero, g.won);
  });
  const pool={};
  Object.keys(comps||{}).forEach(team=>{
    if(!mine[team]) return;
    const ps=(((comps[team]||{}).scout)||{}).players||[];
    ps.forEach(p=>{
      if(!p||p.player!==nick) return;
      (p.heroes||[]).forEach(h=>{
        if(!h||!h.hero) return;
        pool[h.hero]=(pool[h.hero]||0)+(h.rounds||0);
      });
    });
  });
  const total=Object.keys(pool).reduce((a,h)=>a+pool[h],0);
  const names={};
  Object.keys(pool).forEach(h=>{ names[h]=1; });
  Object.keys(tally).forEach(h=>{ names[h]=1; });
  return Object.keys(names).map(h=>{
    const rounds=pool[h]||0, c=tally[h]||{games:0,wins:0};
    return {hero:h, rounds:rounds, share:total?Math.round(100*rounds/total):null,
            games:c.games, wins:c.wins,
            wr:playerRate(c.wins, c.games, PLAYER_HERO_MIN)};
  }).sort((a,b)=>b.rounds-a.rounds||b.games-a.games||a.hero.localeCompare(b.hero));
}
```

- [ ] **Step 4: Run the tests**

```bash
.venv/Scripts/python.exe -m pytest tests/test_dashboard_logic.py -k player -v
```

Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add faceit_sync/dashboard/pure.js tests/test_dashboard_logic.py
git commit -m "Show a player's hero pool always, their hero win rate only above the floor"
```

---

## Task 6: Per-division stat rows, never blended

A Master dmg average and an Advanced one are different units. A player who crossed divisions gets one row each — the same refusal `efficiencyRatings` already makes by z-scoring inside a division.

**Files:**
- Modify: `faceit_sync/dashboard/pure.js`
- Test: `tests/test_dashboard_logic.py`

**Interfaces:**
- Consumes: nothing from earlier tasks — reads `divisions` directly (`div.teams[].roster[]`).
- Produces:
  - `mergePlayerStats(rows) -> {games, elims, deaths, dmg, heal, mit, kd}|null` where `rows` are `roster[].stats` objects.
  - `playerDivisions(nick, divisions) -> [{cid, division, teams:[name], role, gameName, elo, lastSeen, games, stats}]`, sorted by `games` desc.

- [ ] **Step 1: Write the failing tests**

```python
def test_merge_player_stats_reweights_by_sample_and_recomputes_kd(tmp_path) -> None:
    """k/d is a ratio of season totals, never a mean of two ratios - averaging
    ratios lets a two-map row outvote a forty-map one."""
    got = _prun("""
      return mergePlayerStats([
        {games:10, elims:20, deaths:10, dmg:1000, heal:0, mit:500, kd:2},
        {games:30, elims:10, deaths:5,  dmg:2000, heal:0, mit:100, kd:2}]);
    """, tmp_path)
    assert got["games"] == 40
    assert got["elims"] == 12.5          # (20*10 + 10*30) / 40
    assert got["deaths"] == 6.25
    assert got["dmg"] == 1750
    assert got["kd"] == 2.0


def test_merge_player_stats_is_null_without_a_sample(tmp_path) -> None:
    """Zeroed rows (data hazard A) are stored NULL, so a player can have maps
    played and no stat sample at all."""
    got = _prun("return mergePlayerStats([null, {games:0}]);", tmp_path)
    assert got is None


def test_player_divisions_keeps_a_cross_division_player_in_two_rows(tmp_path) -> None:
    got = _prun("""
      const row=(nick,g,seen,elo,st)=>({nick:nick,game_name:'Blip#1',games:g,
        last_seen:seen, elo:elo, role:'Tank', current:true, stats:st});
      const DIVS={
        m1:div('EMEA Master',[{name:'Beta',roster:[
              row('Blip',10,'2026-07-20T00:00:00Z',2100,{games:10,elims:10,deaths:5,dmg:6000,heal:0,mit:7000,kd:2})]}],[],[]),
        m2:div('EMEA Expert',[{name:'Gamma',roster:[
              row('Blip',4,'2026-06-10T00:00:00Z',1900,{games:4,elims:20,deaths:5,dmg:9000,heal:0,mit:8000,kd:4})]}],[],[])};
      return playerDivisions('Blip', DIVS);
    """, tmp_path)
    assert [d["division"] for d in got] == ["EMEA Master", "EMEA Expert"]
    assert got[0]["stats"]["dmg"] == 6000 and got[1]["stats"]["dmg"] == 9000
    assert got[0]["elo"] == 2100


def test_player_divisions_merges_two_teams_inside_one_division(tmp_path) -> None:
    """A mid-season swap inside one division leaves two roster rows. They are
    one division row - and elo comes from the most recent of them."""
    got = _prun("""
      const row=(g,seen,elo,st)=>({nick:'Blip',game_name:'Blip#1',games:g,
        last_seen:seen, elo:elo, role:'Tank', current:true, stats:st});
      const DIVS={m1:div('EMEA Master',[
        {name:'Alpha',roster:[row(2,'2026-07-02T00:00:00Z',2000,{games:2,elims:20,deaths:5,dmg:8000,heal:0,mit:9000,kd:4})]},
        {name:'Beta', roster:[row(2,'2026-07-20T00:00:00Z',2100,{games:2,elims:10,deaths:5,dmg:6000,heal:0,mit:7000,kd:2})]}],[],[])};
      return playerDivisions('Blip', DIVS)[0];
    """, tmp_path)
    assert got["teams"] == ["Alpha", "Beta"]
    assert got["games"] == 4
    assert got["elo"] == 2100                 # the later roster row
    assert got["stats"]["games"] == 4
    assert got["stats"]["dmg"] == 7000        # (8000*2 + 6000*2) / 4
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
.venv/Scripts/python.exe -m pytest tests/test_dashboard_logic.py -k "merge_player_stats or player_divisions" -v
```

Expected: FAIL — `mergePlayerStats is not defined`.

- [ ] **Step 3: Implement**

Append to `pure.js`:

```js
// Merge per-map stat averages from several roster rows: a player who changed
// team inside one division has one row per team. Means are re-weighted by each
// row's own stat sample, and k/d is recomputed from the recovered totals rather
// than averaged as a ratio of ratios — which would let a two-map row outvote a
// forty-map one.
function mergePlayerStats(rows){
  const ok=(rows||[]).filter(r=>r&&r.games);
  if(!ok.length) return null;
  const n=ok.reduce((a,r)=>a+r.games,0);
  const w=k=>ok.reduce((a,r)=>a+(r[k]||0)*r.games,0)/n;
  const elims=w('elims'), deaths=w('deaths');
  return {games:n,
          elims:Math.round(elims*10)/10, deaths:Math.round(deaths*10)/10,
          dmg:Math.round(w('dmg')), heal:Math.round(w('heal')), mit:Math.round(w('mit')),
          kd:deaths>0?Math.round(100*elims/deaths)/100:null};
}

// One row per division a player appears in — never a blend. A Master damage
// average and an Advanced one are different units, and the whole site refuses
// that comparison already (efficiencyRatings z-scores inside a division).
function playerDivisions(nick, divisions){
  const out=[];
  if(!nick||!divisions) return out;
  Object.keys(divisions).forEach(cid=>{
    const div=divisions[cid]||{};
    const found=[];
    (div.teams||[]).forEach(t=>{
      (t.roster||[]).forEach(p=>{ if(p&&p.nick===nick) found.push({team:t.name, row:p}); });
    });
    if(!found.length) return;
    found.sort((a,b)=>(a.row.last_seen||'').localeCompare(b.row.last_seen||''));
    const last=found[found.length-1].row;
    out.push({cid:cid,
      division:(div.summary&&div.summary.championship)||cid,
      teams:found.map(f=>f.team),
      role:last.role||null,
      gameName:last.game_name||null,
      elo:(last.elo==null?null:last.elo),
      lastSeen:last.last_seen||'',
      games:found.reduce((a,f)=>a+(f.row.games||0),0),
      stats:mergePlayerStats(found.map(f=>f.row.stats))});
  });
  return out.sort((a,b)=>b.games-a.games||a.division.localeCompare(b.division));
}
```

- [ ] **Step 4: Run the tests**

```bash
.venv/Scripts/python.exe -m pytest tests/test_dashboard_logic.py -k player -v
```

Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add faceit_sync/dashboard/pure.js tests/test_dashboard_logic.py
git commit -m "Give a cross-division player one stat row per division"
```

---

## Task 7: Compose the season

The thin function the page calls. It walks the games once and hands the result to the four derivations.

**Files:**
- Modify: `faceit_sync/dashboard/pure.js`
- Test: `tests/test_dashboard_logic.py`

**Interfaces:**
- Consumes: everything from Tasks 2-6.
- Produces: `playerSeason(nick, divisions, comps, pergame) -> {found, nick, gameName, teams, current, divisions, modes, maps, recent, heroes}`. `recent` is `playerGames`' output in full, newest first — the view slices it.

- [ ] **Step 1: Write the failing tests**

```python
def test_player_season_composes_the_whole_page(tmp_path) -> None:
    got = _prun("""
      const row=(g,seen,elo,st)=>({nick:'Blip',game_name:'Blip#1',games:g,
        last_seen:seen, elo:elo, role:'Tank', current:true, stats:st});
      const st={games:2,elims:20,deaths:5,dmg:8000,heal:0,mit:9000,kd:4};
      const DIVS={m1:div('EMEA Master',
        [{name:'Alpha',roster:[row(2,'2026-07-02T00:00:00Z',2000,st)]}],
        [mk('M1','2026-07-01T00:00:00Z','Alpha','Zeta','Ilios','Control',true,'Blip'),
         mk('M2','2026-07-02T00:00:00Z','Alpha','Zeta','Nepal','Control',false,'Blip')],[])};
      const comps={Alpha:{scout:{players:[{player:'Blip',heroes:[{hero:'Winston',rounds:20}]}]}}};
      return playerSeason('Blip', DIVS, comps, {'M1:1':{Blip:'Winston'}});
    """, tmp_path)
    assert got["found"] is True
    assert got["gameName"] == "Blip#1"
    assert got["current"]["team"] == "Alpha"
    assert [t["team"] for t in got["teams"]] == ["Alpha"]
    assert got["modes"][0]["mode"] == "Control" and got["modes"][0]["games"] == 2
    assert got["modes"][0]["wr"] is None                 # 2 games, under the floor
    assert [g["matchId"] for g in got["recent"]] == ["M2", "M1"]
    assert got["heroes"][0]["hero"] == "Winston"
    assert got["divisions"][0]["division"] == "EMEA Master"


def test_player_season_is_found_from_a_roster_row_alone(tmp_path) -> None:
    """A player on a roster whose games all fell to walkovers still has a page
    - with an empty record, not a 'no such player' dead end."""
    got = _prun("""
      const DIVS={m1:div('EMEA Master',
        [{name:'Alpha',roster:[{nick:'Blip',game_name:'Blip#1',games:0,
          last_seen:'2026-07-02T00:00:00Z',elo:2000,role:'Tank',current:true,stats:null}]}],
        [],[])};
      return playerSeason('Blip', DIVS, {}, {});
    """, tmp_path)
    assert got["found"] is True
    assert got["recent"] == [] and got["maps"] == []
    assert got["divisions"][0]["stats"] is None


def test_player_season_reports_an_unknown_nick_as_not_found(tmp_path) -> None:
    got = _prun("""
      const DIVS={m1:div('EMEA Master',[],
        [mk('M1','2026-07-01T00:00:00Z','Alpha','Zeta','Ilios','Control',true,'Blip')],[])};
      return playerSeason('Nobody', DIVS, {}, {});
    """, tmp_path)
    assert got["found"] is False
    assert got["current"] is None and got["teams"] == []
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
.venv/Scripts/python.exe -m pytest tests/test_dashboard_logic.py -k player_season -v
```

Expected: FAIL — `playerSeason is not defined`.

- [ ] **Step 3: Implement**

Append to `pure.js`:

```js
// A player's whole season, ready to render. `found` is true if they appear on
// any roster OR in any game: a player whose matches were all walkovers still has
// a page, with an empty record rather than a dead end.
function playerSeason(nick, divisions, comps, pergame){
  const games=playerGames(nick, divisions, pergame);
  const spells=playerSpells(games);
  const record=playerMapRecord(games, teamRecords(divisions));
  const divs=playerDivisions(nick, divisions);
  return {found:!!(games.length||divs.length),
          nick:nick,
          gameName:(divs[0]&&divs[0].gameName)||null,
          teams:spells.spells,
          current:spells.current,
          divisions:divs,
          modes:record.modes,
          maps:record.maps,
          recent:games,
          heroes:playerHeroPool(nick, games, comps)};
}
```

- [ ] **Step 4: Run the tests**

```bash
.venv/Scripts/python.exe -m pytest tests/test_dashboard_logic.py -v
.venv/Scripts/python.exe -m pytest tests/test_export.py::test_dashboard_javascript_is_syntactically_valid -v
```

Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add faceit_sync/dashboard/pure.js tests/test_dashboard_logic.py
git commit -m "Compose a player's season from the games and the rosters"
```

---

## Task 8: Route to a player, and link to them from everywhere

`#player=<nick>` as a non-nav drill-in, plus the click delegate and the three places player names already appear.

**Files:**
- Modify: `faceit_sync/dashboard/app.js` — `hashFor` (`:3097`), `hashDispatch` (`:3107`), `show` (`:3174`), the delegate near `:325`, and the three views listed below.

**Interfaces:**
- Consumes: `playerSeason(...)` from Task 7 (called by `renderPlayer`, built in Task 9).
- Produces: `PLAYER_NICK` (module state), `gotoPlayer(nick)`, `playerLink(nick, extra)`, and the `playerdetail` screen id. Task 9 implements `renderPlayer()`.

- [ ] **Step 1: Add a temporary stub so routing is testable before the view exists**

In `app.js`, beside the other `render*` functions:

```js
function renderPlayer(){ return el(`<div></div>`); }   // Task 9 fills this in
```

- [ ] **Step 2: Add the state, the link helper and the delegate**

Beside `let SCOUT_TEAM = null;` (`app.js:941`):

```js
let PLAYER_NICK = null;   // #player=<nick>: the drill-in's subject
```

Beside `teamLink` (`app.js:324`):

```js
// A player name anywhere on the site is a link to their page. Season-scoped, so
// no division has to be resolved first — the page finds them wherever they are.
function playerLink(nick, extra){
  return nick
    ? `<span class="tlink" data-player="${esc(nick)}" title="${esc(nick)}'s season">${esc(nick)}</span>${extra||''}`
    : '<span class="faint">—</span>';
}
```

Beside the `[data-scout]` delegate (`app.js:325-328`), a sibling. Guard it against `[data-scout]` so a player chip nested inside a team link never fires both:

```js
document.addEventListener('click',e=>{ const t=e.target.closest('[data-player]');
  if(t&&t.dataset.player&&!e.target.closest('a')&&!e.target.closest('[data-scout]')){
    e.preventDefault(); gotoPlayer(t.dataset.player); } });
```

- [ ] **Step 3: Add `gotoPlayer` and the three routing cases**

Beside `gotoScout` (`app.js:993`):

```js
// The player's own primary division (most maps) becomes the active view, so the
// header, the division select and any subsequent tab click stay coherent. The
// page itself still spans every division they played in.
function gotoPlayer(nick){
  const rows=playerDivisions(nick, DIVS);
  if(rows.length){
    const v=VIEWS.find(v=>v.divisions.length===1&&v.divisions[0]===rows[0].cid);
    if(v){ CURRENT_VIEW=v.id; recomputeDivision(); updateHeader();
           document.getElementById('division').value=v.id; }
  }
  PLAYER_NICK=nick; show('playerdetail');
}
```

In `hashFor` (`app.js:3097`), beside the other drill-in cases:

```js
  if(id==='playerdetail'&&PLAYER_NICK) return 'player='+encodeURIComponent(PLAYER_NICK);
```

In `hashDispatch` (`app.js:3107`), before the final `show(...)` fallthrough:

```js
  if(start.startsWith('player=')){
    const nick=start.slice(7);
    // An unresolvable nick lands on the Players tab, never a blank page — the
    // same way a stale #match= id lands on the match list.
    if(!playerDivisions(nick, DIVS).length && !playerGames(nick, DIVS, {}).length){
      show('players'); return;
    }
    gotoPlayer(nick); return;
  }
```

In `show` (`app.js:3174`), extend the `navId` remap and add the render branch:

```js
  const navId = (id==='matchdetail'?'matches':(id==='compare'?'scout':(id==='playerdetail'?'players':id)));
```

```js
  } else if(id==='playerdetail'){
    c.appendChild(renderPlayer());
  } else {
```

- [ ] **Step 4: Turn the three existing player lists into links**

No new UI — the names that are already rendered gain `data-player`:

1. **Players tab, team view** — the `mkRow` name cell in `drawTeam` (`app.js:~2420`).
2. **Players tab, seat and leaderboard views** — the name cell in each (`app.js:~2446` and `~2505`).
3. **Team roster cards on the Scout page** — the roster rows around `app.js:1597-1610`.
4. **Match detail per-map scoreboards** — the player rows built around `app.js:406`.

In each, wrap the existing escaped nick in `playerLink(...)` rather than adding a button. Keep every surrounding class and title attribute exactly as it is; the only change is that the name becomes clickable.

- [ ] **Step 5: Verify the script still parses and the routing test suite passes**

```bash
.venv/Scripts/python.exe -m pytest tests/test_export.py::test_dashboard_javascript_is_syntactically_valid -v
.venv/Scripts/python.exe -m pytest tests/test_dashboard_logic.py -v
```

Expected: PASS. A failure here means the page would render completely blank in production — do not proceed past it.

- [ ] **Step 6: Commit**

```bash
git add faceit_sync/dashboard/app.js
git commit -m "Route to a player page, and link every player name to it"
```

---

## Task 9: Render the player page

**Files:**
- Modify: `faceit_sync/dashboard/app.js` — replace the Task 8 stub.
- Modify: `faceit_sync/dashboard/head.html` — one new CSS component.
- Modify: `docs/theme.css` — **no.** The timeline strip is dashboard-only; a selector defined in both data pages fails `tests/test_ui_consistency.py`.

**Interfaces:**
- Consumes: `playerSeason`, `playerDivisions`, `PLAYER_MODE_MIN`, `PLAYER_MAP_MIN`, `PLAYER_HERO_MIN` (Tasks 2-7); the existing `efficiencyRatings`, `effGroupOf`, `playerCaptures`, `heroIcon`, `teamAvatar`, `table`, `mapCmp`, `byMode`, `pill`, `winVar`, `sectionH`, `captureDivisionUrl`, `el`, `esc`, `nf`, `dshort`.
- Produces: the rendered page. Nothing downstream consumes it.

- [ ] **Step 1: Add the one new CSS component**

In `faceit_sync/dashboard/head.html`, beside the other page-specific rules. Tokens only — no literal colours, no literal radii:

```css
.ptl{display:flex;flex-wrap:wrap;align-items:stretch;gap:8px;margin:10px 0}
.ptl .sp{flex:1 1 180px;min-width:0;background:var(--surface2);
  border:1px solid var(--line);border-left:3px solid var(--accent);
  border-radius:var(--r-sm);padding:8px 10px}
.ptl .sp .t{font-weight:660;font-size:13px;display:flex;align-items:center;gap:7px}
.ptl .sp .d{color:var(--muted);font-size:11.5px;margin-top:3px;font-variant-numeric:tabular-nums}
.ptl .sp.now{border-left-color:var(--good)}
@media (max-width:640px){ .ptl{flex-direction:column} }
```

- [ ] **Step 2: Replace the stub with the view**

In `app.js`, replace `function renderPlayer(){ return el(`<div></div>`); }` with the full view. Build it section by section in the order below; each section appends to `wrap` and returns early only where noted.

```js
// ---- Player page (#player=<nick>) -----------------------------------------
// A player's season across every division. Every rate carries its n; anything
// under its floor renders as an em dash with a title saying why, the same
// treatment Eff already gets. A player's map record is largely their team's, so
// the team's rate sits in the same row rather than in a footnote.
function playerRateCell(wr, n, floor, label){
  return wr==null
    ? `<span class="faint" title="${esc(label)} needs ${floor}+ games; ${n} so far">—</span>`
    : `${pill(wr+'%', winVar(wr))} <span class="faint">${n}g</span>`;
}
function renderPlayer(){
  const wrap=el(`<div></div>`);
  wrap.appendChild(el(`<a class="backlink" href="#players">‹ Players</a>`));
  const S=playerSeason(PLAYER_NICK, DIVS, DATA.owdb_comps||{}, DATA.owdb_pergame_players||{});
  if(!S.found){
    wrap.appendChild(el(`<p class="note" style="margin-top:14px">No player named ${esc(PLAYER_NICK||'')} in this season's data.</p>`));
    return wrap;
  }
  // 1. Identity. No player avatar exists in the schema; the team carries it.
  const cur=S.current;
  wrap.appendChild(el(sectionH(S.nick,
    `<span class="note">${S.gameName?esc(S.gameName)+' · ':''}`+
    `${cur?`<span class="tlink" data-scout="${esc(cur.team)}" title="Scout ${esc(cur.team)}">${esc(cur.team)}</span> · ${esc(cur.division)}`:'no current team'}</span>`)));

  // 2. Headline tiles.
  const totG=S.maps.reduce((a,m)=>a+m.games,0), totW=S.maps.reduce((a,m)=>a+m.wins,0);
  const d0=S.divisions[0]||{};
  const eff=playerEffFor(S.nick, d0.cid);         // see step 3
  const tiles=el(`<div class="grid cols-4"></div>`);
  const tile=(n,l,sub)=>el(`<div class="tile"><div class="n">${n}</div><div class="l">${esc(l)}</div>${sub?`<div class="sub">${sub}</div>`:''}</div>`);
  tiles.append(
    tile(totG, 'maps played', S.divisions.length>1?esc(S.divisions.length+' divisions'):''),
    tile(totG?Math.round(100*totW/totG)+'%':'—', 'map win rate', totG?`${totW}-${totG-totW}`:''),
    tile(eff&&eff.eff!=null?(eff.eff>0?'+':'')+eff.eff.toFixed(2):'—', 'Eff',
         eff&&eff.eff!=null?esc((eff.group||'')+' · '+eff.groupN+' peers'):'not enough peers'),
    tile(d0.elo==null?'—':d0.elo, 'elo', d0.lastSeen?esc(dshort(d0.lastSeen)):''));
  wrap.appendChild(tiles);

  // 3. Team timeline — only when there is actually a story to tell.
  if(S.teams.length>1){
    const tl=el(`<div class="ptl"></div>`);
    S.teams.forEach((s,i)=>{
      const now=cur&&s.team===cur.team&&s.cid===cur.cid;
      tl.appendChild(el(`<div class="sp${now?' now':''}">`+
        `<div class="t">${teamAvatar(s.team,20)}<span class="tlink" data-scout="${esc(s.team)}">${esc(s.team)}</span></div>`+
        `<div class="d">${esc(s.division)} · ${s.games} map${s.games===1?'':'s'}<br>`+
        `${esc(dshort(s.firstSeen))} → ${now?'now':esc(dshort(s.lastSeen))}</div></div>`));
    });
    wrap.append(el(sectionH('Season timeline',
      `<span class="note">${S.teams.length} spells · dates are first and last map played</span>`)), tl);
  }
  // 4-7 follow, appended to wrap in order.
  return wrap;
}
```

- [ ] **Step 3: Add the Eff lookup, reusing the existing rating**

Beside `effGroupOf` (`app.js:2368`). Do **not** write a second efficiency calculation — build the same per-division player list `renderPlayers` builds and read this player's entry out of it:

```js
// This player's Eff inside one division, computed exactly the way the Players
// tab computes it: the whole division's cohort, z-scored per role. Building the
// cohort is the point — an Eff is a comparison, so it cannot be computed for one
// player alone.
function playerEffFor(nick, cid){
  const div=cid?DIVS[cid]:null;
  if(!div) return null;
  const cap=playerCaptures();
  const list=[];
  (div.teams||[]).forEach(t=>{ (t.roster||[]).forEach(p=>{
    list.push({nick:p.nick, team:t.name, role:p.role||'', stats:p.stats||null,
               cap:cap[t.name+'|'+p.nick]||null}); }); });
  const effs=efficiencyRatings(list.map(p=>({group:effGroupOf(p), stats:p.stats})));
  const i=list.findIndex(p=>p.nick===nick);
  return i>=0?effs[i]:null;
}
```

`playerCaptures()` (`app.js:2345`) reads `D().team_names`, so `gotoPlayer` must have set the view to the player's primary division before `renderPlayer` runs — it does (Task 8, Step 3).

- [ ] **Step 4: Add sections 4-7**

Insert before `return wrap;`:

```js
  // 4. Season stats, one row per division — never blended across tiers.
  wrap.appendChild(el(sectionH('Season stats',
    `<span class="note">per-map averages from FACEIT · one row per division, because a Master average and an Advanced one are different units</span>`)));
  wrap.appendChild(table([
    {k:'division',label:'Division'},
    {k:'teams',label:'Team(s)',html:r=>r.teams.map(t=>`<span class="tlink" data-scout="${esc(t)}">${esc(t)}</span>`).join(' → ')},
    {k:'role',label:'Role',html:r=>esc(r.role||'—')},
    {k:'games',label:'Maps',num:true},
    {k:'kd',label:'K/D',num:true,html:r=>r.stats&&r.stats.kd!=null?r.stats.kd:'—'},
    {k:'dmg',label:'Damage',num:true,html:r=>r.stats?nf(r.stats.dmg):'—'},
    {k:'heal',label:'Healing',num:true,html:r=>r.stats?nf(r.stats.heal):'—'},
    {k:'mit',label:'Mitigated',num:true,html:r=>r.stats?nf(r.stats.mit):'—'},
    {k:'elo',label:'Elo',num:true,html:r=>r.elo==null?'—':r.elo}
  ], S.divisions));

  // 5. Modes, then maps. Sort BEFORE table() — its group header only collapses
  // consecutive same-group rows, which is the bug Team Compare shipped.
  wrap.appendChild(el(sectionH('Modes & maps',
    `<span class="note">their record, beside their teams' own · mode needs ${PLAYER_MODE_MIN}+ games, map needs ${PLAYER_MAP_MIN}+</span>`)));
  const bars=el(`<div class="card"></div>`);
  S.modes.forEach(m=>{
    bars.appendChild(el(`<div class="barrow">`+
      `<span class="lab">${esc(m.mode)}</span>`+
      `<span class="track"><span class="fill" style="width:${m.games?Math.round(100*m.wins/m.games):0}%"></span></span>`+
      `<span class="barval">${m.wr==null?`<span class="faint" title="needs ${PLAYER_MODE_MIN}+ games; ${m.games} so far">—</span>`:m.wr+'%'}</span>`+
      `</div>`));
  });
  wrap.appendChild(bars);
  wrap.appendChild(table([
    {k:'map',label:'Map'},
    {k:'games',label:'Maps',num:true},
    {k:'wr',label:'Their %',num:true,html:r=>playerRateCell(r.wr,r.games,PLAYER_MAP_MIN,'A map win rate')},
    {k:'teamWr',label:"Team %",num:true,html:r=>r.teamWr==null?'—':`${r.teamWr}% <span class="faint">${r.teamGames}g</span>`}
  ], S.maps.slice().sort((a,b)=>mapCmp(a.map,b.map)), byMode));
  wrap.appendChild(el(`<p class="note">A player plays with the same four teammates, so their map record is largely their team's — the useful read is where the two columns diverge, which is where someone was subbed in or out.</p>`));

  // 6. Hero pool. Present whenever captures exist; the win column only above the floor.
  if(S.heroes.length){
    wrap.appendChild(el(sectionH('Hero pool',
      `<span class="note">share of their captured rounds · win rate needs ${PLAYER_HERO_MIN}+ captured games on that hero</span>`)));
    const hb=el(`<div class="card"></div>`);
    S.heroes.forEach(h=>{
      hb.appendChild(el(`<div class="barrow">`+
        `<span class="lab">${heroIcon(h.hero)}${esc(h.hero)}</span>`+
        `<span class="track"><span class="fill" style="width:${h.share||0}%"></span></span>`+
        `<span class="barval">${h.share==null?'—':h.share+'%'} · ${playerRateCell(h.wr,h.games,PLAYER_HERO_MIN,'A hero win rate')}</span>`+
        `</div>`));
    });
    wrap.appendChild(hb);
  } else {
    wrap.appendChild(el(sectionH('Hero pool',
      `<span class="note">no captured games for this player yet</span>`)));
    wrap.appendChild(el(`<p class="note">Hero pools come from captured replays. <a href="${captureDivisionUrl()}">Capture a map</a> and this fills in.</p>`));
  }

  // 7. Recent maps. The pure layer returns every game; the view decides how many fit.
  wrap.appendChild(el(sectionH('Recent maps',
    `<span class="note">their last ${Math.min(10,S.recent.length)} maps</span>`)));
  wrap.appendChild(table([
    {k:'at',label:'Date',html:r=>esc(dshort(r.at))},
    {k:'opponent',label:'Opponent',html:r=>r.opponent?`<span class="tlink" data-scout="${esc(r.opponent)}">${esc(r.opponent)}</span>`:'—'},
    {k:'map',label:'Map',html:r=>esc(r.map)},
    {k:'hero',label:'Hero',html:r=>r.hero?heroIcon(r.hero)+esc(r.hero):'<span class="faint">—</span>'},
    {k:'won',label:'Result',html:r=>pill(r.won?'W':'L', r.won?'var(--good)':'var(--bad)')},
    {k:'stats',label:'Line',html:r=>esc(`${r.stats.e??'—'}/${r.stats.d??'—'} · ${nf(r.stats.dmg||0)} dmg`)}
  ], S.recent.slice(0,10)));

  // The spec's one accepted limitation, said out loud. FACEIT gives no nickname
  // history, so a player who renamed mid-season becomes two pages and there is
  // no way to detect it from the data we hold. Stating it beats being quietly
  // wrong about a season that looks half as long as it was.
  wrap.appendChild(el(`<p class="note">A player is identified by their FACEIT nickname. Someone who changed nickname mid-season appears here as two players — FACEIT does not publish nickname history, so this cannot be stitched back together.</p>`));
```

- [ ] **Step 5: Verify the script parses, then look at it**

```bash
.venv/Scripts/python.exe -m pytest \
  tests/test_export.py::test_dashboard_javascript_is_syntactically_valid \
  tests/test_export.py::test_export_html_is_self_contained_and_valid \
  tests/test_ui_consistency.py \
  tests/test_dashboard_logic.py -v
```

Expected: all PASS. `test_ui_consistency.py` fails if the new CSS restates a token value or duplicates a selector across the data pages.

Then build a preview **to a scratch path** and look at it. Never export onto `docs/index.html`:

```bash
.venv/Scripts/python.exe -m faceit_sync.cli --db faceit.sqlite3 export \
  --season s9 --format html --out "$TMP/player-preview.html"
```

Open it, navigate to `#player=<some nick from the data>`, and check: light and
dark, 640px width, a player with captures and one without, and a player who
changed team mid-season.

Horizontal overflow needs no new CSS — `table()` already wraps every table in
`<div class="scroll">` (`app.js:665`), which is the container the shared mobile
pass scrolls. Confirm it rather than adding a second rule.

To find a swapped player to test with:

```bash
.venv/Scripts/python.exe -c "
import sqlite3
db=sqlite3.connect('faceit.sqlite3')
for nick,n in db.execute('''
  SELECT p.nickname, COUNT(DISTINCT rp.team_id) n
  FROM round_players rp JOIN players p ON p.id=rp.player_id
  GROUP BY rp.player_id HAVING n>1 ORDER BY n DESC LIMIT 5'''):
    print(nick, n)
"
```

- [ ] **Step 6: Commit**

```bash
git add faceit_sync/dashboard/app.js faceit_sync/dashboard/head.html
git commit -m "Give every player a page of their season"
```

---

## Task 10: Update the documentation

Required, not optional: this is visible on owdb.io and it changes a data contract.

**Files:**
- Modify: `CHANGELOG.md`, `ARCHITECTURE.md`, `specs/BACKLOG.md`, `FEATURES.md`

- [ ] **Step 1: `CHANGELOG.md`**

Add an entry in the file's existing format covering both halves: the player page at `#player=<nick>`, and the payload change (`matches[].games[].rosters[].players[].mit`). Note the floors — a reader should learn from the changelog that hero win rate is deliberately blank for most players.

- [ ] **Step 2: `ARCHITECTURE.md` §4**

The "Views and tabs" paragraph currently ends: *"Playoffs is a mode inside the Matches tab, not a tab of its own."* Add the fourth drill-in beside `#match=`, `#scout=`/`#prep=` and `#compare=`:

> A fourth drill-in, `#player=<nick>`, hangs off the Players tab. Unlike the others it is **season-scoped rather than division-scoped** — it aggregates every division in the payload, which is what lets a mid-season team or division move read as one player. It sets the active view to the player's primary division so the header stays coherent.

- [ ] **Step 3: `ARCHITECTURE.md` §9**

In "The inlined dashboard payload", record that per-game roster rows carry `mit` alongside `e / d / dmg / heal`, and that it is `null` for zeroed rows (hazard A) rather than 0.

- [ ] **Step 4: `ARCHITECTURE.md` §13**

Only if a new test file was created. This plan adds cases to existing files, so the table needs no new row — verify that is still true before skipping the step.

- [ ] **Step 5: `specs/BACKLOG.md`**

Two edits:
- The P3 *per-map scoreboard context* entry (around line 238) says to "bundle with the player index work if either gets scoped." The player page delivers the per-map stat context, so mark it resolved with the date and a pointer to `specs/2026-08-24-player-pages-design.md`.
- Add a line recording what was deliberately deferred and its measured cost: per-game elo trend, +473 KB raw.

- [ ] **Step 6: `FEATURES.md`**

Add the player page entry. The file is known to lag the code; adding the entry is what stops the gap widening.

- [ ] **Step 7: Verify the docs still link correctly**

```bash
.venv/Scripts/python.exe -m pytest tests/test_docs_links.py -v
```

Expected: PASS.

- [ ] **Step 8: Full suite, then commit**

```bash
.venv/Scripts/python.exe -m pytest
.venv/Scripts/python.exe -m mypy faceit_sync
```

Expected: everything green, mypy clean.

```bash
git add CHANGELOG.md ARCHITECTURE.md specs/BACKLOG.md FEATURES.md
git commit -m "Document the player pages and the mitigation payload change"
```

---

## Done

The branch is ready to review. It is **not** ready to merge until someone has looked at a real preview build — `pytest` cannot see through a browser, and the one thing it cannot catch here is a page that renders but reads wrong.

Before pushing: `git fetch`. CI auto-commits to `origin/main` every few minutes; expect a merge, and resolve by keeping CI's data and reapplying the diff on top.

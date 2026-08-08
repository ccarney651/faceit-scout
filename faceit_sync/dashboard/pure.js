/* ---------- pure decision helpers ----------
   Declared ahead of bootApp (no DOM, no DATA) so tests/test_dashboard_logic.py
   can execute them for real. Every one of these got a claim on the page wrong
   at some point; the tests are the record of what the right answer is. */

// The date range a capture sample actually covers, and whether all of it
// predates the latest replay-code wipe. A wipe IS a patch, so a wholly pre-wipe
// sample is pre-patch comp data and must never be labelled as newer than it is.
function capSample(dates, wipe){
  const ds=(dates||[]).filter(Boolean).map(d=>String(d).slice(0,10)).sort();
  if(!ds.length) return null;
  const to=ds[ds.length-1];
  return {n:ds.length, from:ds[0], to, stale: !!(wipe && to<=wipe)};
}
// fmt lets the caller localise the dates (the page passes dshort); the default
// keeps the helper pure and testable on raw ISO days.
function capLabelText(sample, wipe, fmt){
  if(!sample) return '';
  const f=fmt||(s=>s);
  const range = sample.from===sample.to ? f(sample.from)
              : f(sample.from)+' → '+f(sample.to);
  return sample.stale
    ? `captured ${range} — all before the ${f(wipe)} patch`
    : `captured ${range}`;
}

// Maps worth targeting: only where a team is genuinely weaker than its own
// baseline. Sorting by win rate alone hands a coach the opponent's best maps as
// "their worst" the moment that opponent is undefeated, so a map must sit a
// clear margin BELOW their own average to count, and single games never do.
const WORST_MIN_GAMES=2, WORST_MARGIN=10;
function worstMaps(mapStats, opts){
  const o=opts||{}, minGames=o.minGames||WORST_MIN_GAMES,
        margin=(o.margin==null?WORST_MARGIN:o.margin), limit=o.limit||4;
  const rows=Object.entries(mapStats||{})
    .filter(([,v])=>(v&&v.games||0)>=minGames)
    .map(([m,v])=>({m, g:v.games, wr:Math.round(100*v.wins/v.games)}));
  if(!rows.length) return {rows:[], baseline:null};
  const g=rows.reduce((a,r)=>a+r.g,0), w=rows.reduce((a,r)=>a+r.wr*r.g/100,0);
  const baseline=Math.round(100*w/g);
  return {baseline, rows: rows.filter(r=>r.wr<=baseline-margin)
                               .sort((a,b)=>a.wr-b.wr||b.g-a.g).slice(0,limit)};
}

// Hero win rates off the captured comps joined to the match result. Ban counts
// say what the league respects; this says what actually wins on the same sample.
// The unit is the MAP: a hero who appears on two sub-maps of one Control map has
// played one map, and each team's lineup is counted separately.
function heroWinRates(pergame, winnerOf, opts){
  const minMaps=(opts&&opts.minMaps)||5, tally={};
  Object.entries(pergame||{}).forEach(([key,teams])=>{
    const won=(winnerOf||{})[key];
    if(!won) return;                     // no result on record -> not evidence
    Object.entries(teams||{}).forEach(([team,submaps])=>{
      const heroes=new Set();
      Object.values(submaps||{}).forEach(l=>(l||[]).forEach(h=>heroes.add(h)));
      heroes.forEach(h=>{
        const t=tally[h]||(tally[h]={maps:0,wins:0});
        t.maps++; if(team===won) t.wins++;
      });
    });
  });
  return Object.entries(tally)
    .map(([hero,t])=>({hero, maps:t.maps, wins:t.wins,
                       wr:Math.round(100*t.wins/t.maps)}))
    .filter(r=>r.maps>=minMaps)
    .sort((a,b)=>b.wr-a.wr||b.maps-a.maps||a.hero.localeCompare(b.hero));
}

// Rank players for the leaderboard. Rate columns (k/d, damage…) need a sample
// floor or a one-map cameo tops the table; elo is a rating FACEIT reports per
// game, so it stands on its own even when the stat rows were zeroed (hazard A).
// A player missing the sorted stat always sorts last, never above a real number.
const LB_MIN_GAMES=5;
function rankPlayers(players, opts){
  const o=opts||{}, key=o.key||'elo';
  const minGames=(o.minGames==null?LB_MIN_GAMES:o.minGames);
  const role=(o.role&&o.role!=='All')?o.role:null;
  const count=(key==='elo'||key==='maps');   // counts/ratings, not per-map rates
  const val=p=> key==='elo' ? p.elo
              : key==='maps' ? (p.maps==null?null:p.maps)
              : key==='eff' ? (p.eff&&p.eff.eff!=null?p.eff.eff:null)
              : (p.stats?p.stats[key]:null);
  return (players||[])
    .filter(p=>!role||p.role===role)
    .filter(p=> count ? true : (p.stats?(p.stats.games||0)>=minGames:true))
    .sort((a,b)=>{
      const av=val(a), bv=val(b);
      if(av==null&&bv==null) return String(a.nick).localeCompare(String(b.nick));
      if(av==null) return 1;
      if(bv==null) return -1;
      return bv-av || String(a.nick).localeCompare(String(b.nick));
    });
}

// Efficiency rating (PER-style). Each player's per-map stat averages are
// z-scored against the division's other players in the same role, then averaged
// across the stats that actually vary within that role. A component with no
// variance inside the cohort (a Tank cohort's healing) drops out by itself
// rather than being weighted by hand. The composite is a summary line over those
// real numbers, never a bare opaque figure — every component z is carried
// alongside it — and a role with fewer than EFF_GROUP_MIN peers produces no
// rating at all: a z-score against two other players is not a number to lean on.
const EFF_GROUP_MIN=4;
function effZ(mean,sd,v){ if(v==null) return null; if(!(sd>1e-9)) return null; return (v-mean)/sd; }
function efficiencyRatings(players){
  const KEYS=['dmg','heal','mit','kd'];
  const mem=(players||[]).map(p=>p||{});
  const out=mem.map(()=>({group:null, n:0, eff:null, comps:{}, groupN:0}));
  const cohorts={};
  mem.forEach((p,i)=>{ if(p.group==null) return; (cohorts[p.group]=(cohorts[p.group]||[])).push(i); });
  Object.keys(cohorts).forEach(g=>{
    const ids=cohorts[g].filter(i=>{ const s=mem[i].stats; return s&&(s.games||0)>=LB_MIN_GAMES; });
    const groupN=ids.length;
    ids.forEach(i=>{ out[i].group=g; out[i].groupN=groupN; out[i].n=mem[i].stats.games; });
    if(groupN<EFF_GROUP_MIN) return;   // too few peers to mean anything
    const zs={};
    KEYS.forEach(k=>{
      const vals=ids.map(i=>mem[i].stats[k]).filter(v=>v!=null);
      if(!vals.length) return;   // nobody reports this stat: not part of the rating
      const mean=vals.reduce((a,b)=>a+b,0)/vals.length;
      const sd=Math.sqrt(vals.reduce((a,b)=>a+(b-mean)*(b-mean),0)/vals.length);
      ids.forEach(i=>{ const v=mem[i].stats[k];
        const z=(sd>1e-9&&v!=null)?(v-mean)/sd:null;   // sd≈0: no signal within this role
        if(z!=null){ (zs[i]=zs[i]||{})[k]=z; } });
    });
    ids.forEach(i=>{
      const parts=Object.keys(zs[i]||{});
      if(parts.length) out[i].eff=parts.reduce((a,k)=>a+zs[i][k],0)/parts.length;
      KEYS.forEach(k=>{ const z=zs[i]&&zs[i][k]; if(z!=null) out[i].comps[k]={z}; });
    });
  });
  return out;
}

// What a team's scouting-coverage row should say. `scoutable` counts games whose
// replay code still works (or that were captured before it died), so it can be
// zero — and 0-of-0 is "nothing left to scout", never "fully scouted".
function coverageState(total, scoutable, done, wipe){
  if(!total) return null;
  const lost=total-scoutable;
  if(!scoutable) return {kind:'wiped', lost,
    text:`Nothing left to scout — all ${lost} replay code${lost===1?'':'s'} `+
         `were wiped on ${wipe}.`};
  if(done>=scoutable) return {kind:'full', lost,
    text:'Fully scouted - every replay-coded game is captured.'};
  return {kind:'partial', lost, text:''};
}

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

// Playoffs bracket: which column a real FACEIT match belongs in. Playoff
// championships are double-elimination; FACEIT's `group` is the bracket leg
// (1 = upper, 2 = lower) and `round` is the stage within it, so the column is
// derived from BOTH — using `group` alone would collapse every upper-bracket
// round into one column. The bracket's columns are upper rounds (4/2/1), then
// lower rounds (2/2/1/1), then the grand final. A match whose leg is unknown,
// or whose round exceeds its leg's configured span, is the grand final — FACEIT
// numbers it inside group 1/2 on the real brackets, so a bare (group, round)
// lookup would otherwise land it in the wrong stage column.
function playoffStageKey(m, ubRounds, lbRounds){
  const g=m.group!=null?m.group:0, r=Math.max(0,(m.round!=null?m.round:0)-1);
  const gfCol=ubRounds+lbRounds;
  if(g===2) return r<lbRounds ? ubRounds+r : gfCol;   // lower bracket, else grand final
  if(g===1) return r<ubRounds ? r : gfCol;            // upper bracket, else grand final
  return gfCol;                                       // unknown leg -> grand final
}

// Click-to-codes: mid:gno -> the replay-code context an evidence row's popover
// needs. `team` is whose perspective opp/won are read from (may be falsy).
// `wipeDate` (CODE_WIPE) marks a game `dead` when it finished on/before the
// wipe - a plain string param, not a read of the bootApp-scoped CODE_WIPE
// global, so this stays a pure function callers can pass any date into.
function codeLookup(matches, team, wipeDate){
  const m=new Map();
  (matches||[]).forEach(mt=>(mt.games||[]).forEach(g=>{
    if(!g.demo_code) return;
    const won = team ? (g.winner_faction===(mt.f1===team?'faction1':'faction2')) : null;
    const dead = !!(wipeDate && mt.finished_at && String(mt.finished_at).slice(0,10)<=wipeDate);
    m.set(mt.id+':'+g.game_no, {map:g.map, cat:g.map_category, code:g.demo_code,
      opp:(team&&mt.f1===team)?mt.f2:mt.f1, when:mt.finished_at, won, dead});
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
  if(divPicks>0) return {text:`no ${teamName} pick history on ${cat} — ${map} is the division's most-picked (${divPicks}× league-wide)`, thin:false};
  return {text:`no pick data on ${cat} — nothing to read yet`, thin:false};
}
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
function modeExplain(teamName, cat, leaguePct, teamModePicks){
  return {text:`${cat} — the league's most-picked remaining type (${leaguePct}% of picks)`+
    (teamModePicks>0?`; ${teamName} picked ${cat} maps ${teamModePicks}× themselves`:''),
    thin:false};
}

// Match detail page: a match id is unique only within its own division
// (DIVS[cid].matches), so a cross-division link (the Scout-a-team rail, or a
// shared #match= URL) needs to find which division owns it before switching
// CURRENT_VIEW — the same move gotoScout already makes for a team name.
function divisionOfMatch(divs, matchId){
  for(const cid in divs){
    if((divs[cid].matches||[]).some(m=>m.id===matchId)) return cid;
    if((divs[cid].playoffs||[]).some(m=>m.id===matchId)) return cid;
  }
  return null;
}
// The compact match card's per-map pip: win/loss is always read relative to
// faction1 (the team listed first on the card), so one card's pips read
// consistently even though "win" has no meaning without a fixed side.
function mapPipClass(g){
  if(g.winner_faction==='faction1') return 'f1win';
  if(g.winner_faction==='faction2') return 'f2win';
  return '';
}
// Roll up per-game "scouted" (owscout has a captured comp for this game) into
// one N/total for the compact card, in place of a tag per map.
function scoutedCount(m, capturedIds){
  const played=(m.games||[]).filter(g=>g.map);
  const done=played.filter(g=>capturedIds.has(m.id+':'+g.game_no)).length;
  return {done, total:played.length};
}

// League-wide capture queue: every played game that (a) has a replay code, (b)
// no one has captured yet, and (c) can still be scouted — a code is dead only
// once a patch wiped it AND the game was never captured. Newest first. This one
// list powers the nav badge, the Overview "Most wanted" card and the wipe line,
// so it must agree with what the capture tool's feed can actually offer.
function scoutQueue(divs, captured, wipe){
  const out=[];
  for(const cid in divs){
    const d=divs[cid];
    // Finished matches + the playoff bracket both feed the queue — a live playoff
    // code is the freshest, highest-value capture target on the site.
    const lists=[[d.matches||[], ''],[d.playoffs||[], ' · playoffs']];
    lists.forEach(([ms,label])=>ms.forEach(m=>(m.games||[]).forEach(g=>{
      if(!g.demo_code||!g.map) return;
      const key=m.id+':'+g.game_no;
      if(captured.has(key)) return;
      if(wipe && m.finished_at && String(m.finished_at).slice(0,10)<=wipe) return;
      out.push({mid:m.id, gno:g.game_no, code:g.demo_code, map:g.map, f1:m.f1, f2:m.f2,
        when:m.finished_at||'', div:((d.summary&&d.summary.championship)||cid)+label});
    })));
  }
  return out.sort((a,b)=>String(b.when).localeCompare(String(a.when)));
}
// Within ONE match, the games still worth scouting: coded, not captured, and
// with a live code (finished after the latest wipe). Pre-wipe codes are dead
// unless someone already captured them, which this excludes.
function matchLiveTodo(m, captured, wipe){
  return (m.games||[]).filter(g=>g.demo_code&&g.map&&!captured.has(m.id+':'+g.game_no)&&
    !(wipe&&m.finished_at&&String(m.finished_at).slice(0,10)<=wipe));
}

// ---- capture recommendations (Phase 4) ------------------------------------
// Average per-game length by mode, minutes. Used to turn game counts into an
// ESTIMATE of league playtime — the panel labels it as such; the logic only
// needs the proportion right. Control is a BO3 (~14), escort/hybrid run a full
// game (~20), the push-style modes are short (~11).
const MODE_MINUTES={Control:14,Escort:20,Hybrid:20,Push:11,Flashpoint:11,Clash:10};
// A map is "under-covered" until half its league play is captured, and maps
// played fewer than this many times sit below the noise floor (one game on a
// map is not a coverage gap).
const MAP_MIN_GAMES=3, MAP_COVER_TARGET=0.5;
// Which maps most need captures, per division. For every map: how much it's
// been played, how much of that is captured, and how many games still have a
// live replay code. A wiped-and-unseen game can never be fixed, so a map only
// becomes recommendable when it has a live code left to capture. Rows are
// ranked by unseen playtime (games uncaptured × typical length) — the maps
// where the most league minutes are still unobserved. `liveCode` is the newest
// capturable code on the map, for a straight "Scout →" deep link.
function mapCoverage(matches, captured, wipe){
  const agg={};
  (matches||[]).forEach(m=>(m.games||[]).forEach(g=>{
    if(!g.map) return;
    const key=m.id+':'+g.game_no;
    const e=agg[g.map]||(agg[g.map]={map:g.map, mode:g.map_category||'', played:0, captured:0, live:0, liveCode:null});
    e.played++;
    const dead=!!(wipe&&m.finished_at&&String(m.finished_at).slice(0,10)<=wipe);
    if(captured.has(key)){ e.captured++; return; }
    if(g.demo_code&&!dead){
      e.live++;
      // Newest capturable code on the map, for the "Scout →" link — freshest
      // replay is least likely to have been captured since the last build.
      const w=m.finished_at||'';
      if(!e.liveWhen || String(w).localeCompare(e.liveWhen)>0){ e.liveWhen=w; e.liveCode=g.demo_code; }
    }
  }));
  const out=[];
  for(const e of Object.values(agg)){
    const mp=MODE_MINUTES[e.mode]||12;
    e.minutes=e.played*mp;
    e.unseen=e.played-e.captured;
    e.unseenMin=e.unseen*mp;
    e.pct=e.played?Math.round(100*e.captured/e.played):0;
    e.needed=Math.max(0, Math.ceil(e.played*MAP_COVER_TARGET)-e.captured);
    delete e.liveWhen;
    if(e.played>=MAP_MIN_GAMES && e.needed>0 && e.live>0) out.push(e);
  }
  return out.sort((a,b)=> b.unseenMin-a.unseenMin || b.played-a.played);
}


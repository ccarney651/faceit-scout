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

// Every league match a division has actually PLAYED: the regular season plus the
// playoff bracket's finished matches, newest first. Playoff entries carry the
// full match shape (games, maps, bans, rosters, replay codes), so a team read
// built on this list - scouting coverage, comps, ban tendencies, replay-code
// lookup - counts a team's bracket run instead of stopping at the group stage.
// That run is both its most recent form and its most capturable replays.
// Unplayed bracket slots are dropped: they hold no games, and a TBD slot has no
// team to attribute anything to.
//
// Deliberately NOT the list behind standings, power rankings, or the division
// summary counts - a playoff result must never move a regular-season table.
function leagueMatches(matches, playoffs){
  return [...(matches||[]), ...(playoffs||[]).filter(m=>m && m.status==='FINISHED')]
    .sort((a,b)=>{const x=a.finished_at||'',y=b.finished_at||'';return x===y?0:(x<y?1:-1);});
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
// Ordinal label for a placement, and the range label for a tied tier
// ("3rd", "5th–13th").
function ordinal(n){
  const s=['th','st','nd','rd'], v=n%100;
  return n+(s[(v-20)%10]||s[v]||s[0]);
}
function placeRangeLabel(start, size){
  return size<=1 ? ordinal(start) : ordinal(start)+'–'+ordinal(start+size-1);
}
// Final playoff standings, filled in bottom-up as lower-bracket rounds and the
// grand final resolve. FACEIT keeps the bracket topology "clean" even when a
// division's qualifier count isn't a power of 2 (Advanced seeds 24 teams into
// a 32-slot bracket) by auto-generating placeholder matches against a pseudo
// team literally named 'bye' at every round that needs one — pre-FINISHED,
// with no real loser. So a round can be fully resolved (all its real matches
// exist and are FINISHED) yet eliminate nobody (an all-bye round); that must
// NOT be confused with "this round hasn't been scheduled yet" (no match rows
// at all), which is where placement has to stop — later rounds can't be
// numbered correctly until every earlier round's real elimination count is
// known, since the tier boundaries are counted from the bottom (`remaining`)
// rather than read off theoretical bracket-shape math.
function playoffPlacements(matches, n, ubRounds, lbRounds){
  const gfCol=ubRounds+lbRounds;
  const byStage=new Map();
  (matches||[]).forEach(m=>{
    if(!m||!m.f1||!m.f2) return;
    const k=playoffStageKey(m, ubRounds, lbRounds);
    if(!byStage.has(k)) byStage.set(k, []);
    byStage.get(k).push(m);
  });
  const loserOf=(m)=> m.winner_team===m.f1 ? m.f2 : m.f1;
  const tiers=[];
  let remaining=n;
  for(let i=0;i<lbRounds;i++){
    const stage=byStage.get(ubRounds+i)||[];
    if(!stage.length) break;                                   // round not reached yet
    if(stage.some(m=>m.status!=='FINISHED'||!m.winner_team)) break;  // round in progress
    const losers=stage.filter(m=>m.f1!=='bye'&&m.f2!=='bye').map(loserOf);
    if(losers.length){
      tiers.push({start:remaining-losers.length+1, size:losers.length, teams:losers});
      remaining-=losers.length;
    }
  }
  const gf=(byStage.get(gfCol)||[])[0];
  if(gf && gf.status==='FINISHED' && gf.winner_team){
    tiers.push({start:2, size:1, teams:[loserOf(gf)]});
    tiers.push({start:1, size:1, teams:[gf.winner_team]});
  }
  return tiers.sort((a,b)=>a.start-b.start);
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
  const pick={}, banByMap={}, bansAll={}, gkPick={}, gkBanAll={}, gkBanMap={}, counter={}, gkCounter={};
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
    // Counter-ban: this team's reply (order 2) to the opponent's ban (order 1),
    // regardless of map — once we already know exactly what the opponent just
    // took away, this is a stronger signal than "their ban history" in general.
    const mine=(g.bans||[]).find(b=>b.team===team&&b.order===2);
    const opp=(g.bans||[]).find(b=>b.team&&b.team!==team&&b.order===1);
    if(mine&&opp&&mine.hero&&opp.hero){
      (counter[opp.hero]=counter[opp.hero]||{}); inc(counter[opp.hero],mine.hero);
      add(gkCounter,opp.hero,k);
    }
  });
  return {team,pick,banByMap,bansAll,gkPick,gkBanAll,gkBanMap,counter,gkCounter,ngames:use.length};
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
// Ranked ban suggestions for a team on a map. When vsBan is given (this is
// the SECOND ban of the map, replying to the opponent's already-known first
// ban), that team's historical reply to vsBan specifically — regardless of
// map — outranks everything else: it's a stronger, more specific signal than
// "their ban history" once we already know exactly what was just taken away.
// Below that, on-map bans (this exact map) outrank overall bans elsewhere —
// a hero this team has never banned on THIS map shouldn't beat one they
// have, no matter how big its overall count is. Overall count only breaks
// ties (including the all-zero-on-map case, where it's the only signal left).
function banSuggest(model, map, illegal, vsBan){
  const onMap=model.banByMap[map]||{}, all=model.bansAll||{};
  const counter=(vsBan && model.counter && model.counter[vsBan]) || {};
  const keys=new Set([...Object.keys(onMap),...Object.keys(all),...Object.keys(counter)]);
  return [...keys].filter(h=>!illegal.has(h))
    .map(h=>({hero:h,onMap:onMap[h]||0,all:all[h]||0,counter:counter[h]||0}))
    .sort((a,b)=>(b.counter-a.counter)||(b.onMap-a.onMap)||(b.all-a.all)||a.hero.localeCompare(b.hero)).slice(0,7);
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
function autoBan(model, map, illegal, vsBan){
  const s=banSuggest(model, map, illegal, vsBan); return s.length? s[0].hero : null;
}
function mapExplain(teamName, map, cat, teamPicks, divPicks, isTopInCat){
  if(teamPicks>0) return {text:`${teamName} picked ${map} ${teamPicks}× this season`+
    (isTopInCat?` — their most-picked ${cat} map`:''), thin: teamPicks===1};
  if(divPicks>0) return {text:`no ${teamName} pick history on ${cat} — ${map} is the division's most-picked (${divPicks}× league-wide)`, thin:false};
  return {text:`no pick data on ${cat} — nothing to read yet`, thin:false};
}
// counter (optional): {vsBan, n} — this hero is the team's actual historical
// reply, n× this season on any map, when the opponent opened by banning
// vsBan. Takes priority over the overall/on-map reasoning below it: knowing
// exactly what a team does after seeing THIS ban beats a general tendency.
function banExplain(teamName, map, hero, all, onMap, isTopOverall, isTopOnMap, sig, counter){
  if(all===0 && !(counter&&counter.n)) return {text:`no ban history for ${hero} — an experimental pick`, thin:false};
  let t, saidHere=false;
  if(counter && counter.n){
    t = `${teamName}'s most common reply when the opponent opens by banning ${counter.vsBan} — ${counter.n}× this season, any map`;
    saidHere = true;
  }
  else if(isTopOverall) t = `${teamName}'s most-banned hero overall — ${all}× this season`;
  else if(isTopOnMap){ t = `their most-banned hero on ${map} — ${onMap}× here${onMap<all?`, ${all}× this season`:''}`; saidHere=true; }
  else t = `banned ${all}× this season`;
  if(onMap>0 && !saidHere) t += `, ${onMap} of them on ${map}`;
  if(sig) t += ` — ★ signature, well above the division rate`;
  return {text:t, thin: counter&&counter.n ? counter.n===1 : all===1};
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
// Roll up per-game "scouted" (owdb has a captured comp for this game) into
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
// Teams in a view with no captured comps at all — the Overview capture-funnel
// callout. A team counts as "scouted" once it has any captured game
// (`scout.games`), so a missing/empty entry means zero captures.
function zeroCaptureTeams(teamNames, owdbComps){
  const ocs=owdbComps||{};
  return teamNames.filter(n=>!(((ocs[n]||{}).scout)||{}).games);
}
// Teams that can actually be captured FOR: have at least one game with a live
// (post-wipe), uncaptured replay code. Same code-liveness rules as scoutQueue/
// matchLiveTodo. The funnel must only nudge scouts toward teams a capture can
// help — a team that never played, or whose only codes were wiped before anyone
// captured them, offers no replay to run.
function capturableTeams(matches, captured, wipe){
  const out=new Set();
  matches.forEach(m=>(m.games||[]).forEach(g=>{
    if(!g.demo_code||!g.map) return;
    const key=m.id+':'+g.game_no;
    if(captured.has(key)) return;
    if(wipe&&m.finished_at&&String(m.finished_at).slice(0,10)<=wipe) return;
    if(m.f1) out.add(m.f1);
    if(m.f2) out.add(m.f2);
  }));
  return out;
}

// ---- capture recommendations (Phase 4) ------------------------------------
// Average per-game length by mode, minutes. Used to turn game counts into an
// ESTIMATE of league playtime — the panel labels it as such; the logic only
// needs the proportion right. Control is a BO3 (~14), escort/hybrid run a full
// game (~20), the push-style modes are short (~11).
// Clash is absent: it is no longer played competitively, so it never appears
// in league data and would only pad the mode lists.
//
// These stay flat per mode ON PURPOSE, and the alternative was measured rather
// than assumed (2026-08-20). Per-game scores ARE in the data, so each game could
// be weighted by its own length: Control and Flashpoint score in rounds, and an
// escort/hybrid total above 3 means extra rounds were played. Doing that moves
// per-game estimates by up to 3x - and changes the panel by nothing. Across all
// five divisions the ranking moved 0-2 positions and the top three rows, the only
// ones a scout acts on, were identical every time.
//
// The reason is structural, not a property of this season: the panel aggregates
// to MAPS, and every map carries dozens of games, so game-level length averages
// out before it reaches a row. Measured per-map mean length varies 0.3% (Control)
// to 10.9% (Escort) while the games inside vary 3x. A map's rank is driven by how
// often it is PLAYED and how little of it is captured, not by how long its games
// run. Reach for real per-game weighting only if the panel ever ranks something
// with few games behind it - a single match, a single team's play - where one
// long game is no longer averaged away.
const MODE_MINUTES={Control:14,Escort:20,Hybrid:20,Push:11,Flashpoint:11};
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

// ---- team compare (Phase 5) -----------------------------------------------
// Two-team radar. The compare view hands this pre-computed per-team sources
// (aggregate()'s output + the owdb_comps.scout object), and the pure layer
// only normalizes: caps raw values to 0..100, applies per-axis sample floors
// (below a floor the number is honest to show dimmed, never confident), and
// drops an axis neither team has any sample for. Fixed caps keep two weak teams
// reading as two small shapes instead of inflating to fill the chart.
const COMPARE_CAPS={mapwr:100, pool:10, banpress:2, pick:100, eff:0.5, families:12, heropool:15, swaps:3};
const COMPARE_FLOORS={mapwr:5, pool:5, banpress:5, pick:5, eff:3, families:3, heropool:20, swaps:3};
const HERO_POOL_MIN_PICK=0.05;
function compareAxes(aggA, aggB, scoutA, scoutB, effA, effB, poolCap){
  const A=aggA||{}, B=aggB||{}, SA=(scoutA&&scoutA.scout)||{}, SB=(scoutB&&scoutB.scout)||{};
  const ga=A.games||0, gb=B.games||0;
  const sum=o=>Object.values(o||{}).reduce((x,y)=>x+y,0);
  const mg=a=>{let g=0,w=0; Object.values(a.mapStats||{}).forEach(v=>{g+=v.games;w+=v.wins;}); return {g,w};};
  const maps=a=>Object.keys(a.mapStats||{}).filter(m=>(a.mapStats[m].games||0)>0).length;
  const heroes=a=>{ if(!a.hero_pool) return null; let c=0; (a.hero_pool||[]).forEach(h=>{ if((h.pick_rate||0)>=HERO_POOL_MIN_PICK) c++; }); return c;};
  const effN=e=>(e&&e.n)||0, effMean=e=>(e&&e.mean!=null)?e.mean:null;
  const adapt=a=>a.adapt||{};
  const row=(id,label,ra,rb,na,nb,cap,floor,sym)=>(
    (ra==null&&rb==null) ? null : {id,label,
      a:{raw:ra, val:(ra==null?null:sym?Math.max(0,Math.min(100,50+(ra/cap)*50)):Math.min(ra/cap,1)*100), n:na||0, ok:!!(ra!=null&&na>=floor)},
      b:{raw:rb, val:(rb==null?null:sym?Math.max(0,Math.min(100,50+(rb/cap)*50)):Math.min(rb/cap,1)*100), n:nb||0, ok:!!(rb!=null&&nb>=floor)}});
  const mA=mg(A), mB=mg(B);
  // Pool cap is the division's actual active map count when the caller knows it
  // (a fixed 10 undercounts most seasons, so real teams saturate this axis at
  // 100 with nothing left to differentiate them — see COMPARE_CAPS' comment).
  const poolCapVal = poolCap>0 ? poolCap : COMPARE_CAPS.pool;
  return [
    row('mapwr','Map win rate', mA.g?100*mA.w/mA.g:null, mB.g?100*mB.w/mB.g:null, mA.g, mB.g, COMPARE_CAPS.mapwr, COMPARE_FLOORS.mapwr),
    row('pool','Map pool breadth', maps(A), maps(B), ga, gb, poolCapVal, COMPARE_FLOORS.pool),
    row('banpress','Ban pressure', ga?sum(A.bans)/ga:null, gb?sum(B.bans)/gb:null, ga, gb, COMPARE_CAPS.banpress, COMPARE_FLOORS.banpress),
    row('pick','Pick agency', ga?100*sum(A.mapsPicked)/ga:null, gb?100*sum(B.mapsPicked)/gb:null, ga, gb, COMPARE_CAPS.pick, COMPARE_FLOORS.pick),
    row('eff','Team Eff', effMean(effA), effMean(effB), effN(effA), effN(effB), COMPARE_CAPS.eff, COMPARE_FLOORS.eff, true),
    row('families','Comp diversity', adapt(SA).families!=null?adapt(SA).families:null, adapt(SB).families!=null?adapt(SB).families:null, SA.games||0, SB.games||0, COMPARE_CAPS.families, COMPARE_FLOORS.families),
    row('heropool','Hero pool breadth', heroes(SA), heroes(SB), SA.rounds||0, SB.rounds||0, COMPARE_CAPS.heropool, COMPARE_FLOORS.heropool),
    row('swaps','Adaptability', adapt(SA).swaps_per_map!=null?adapt(SA).swaps_per_map:null, adapt(SB).swaps_per_map!=null?adapt(SB).swaps_per_map:null, SA.games||0, SB.games||0, COMPARE_CAPS.swaps, COMPARE_FLOORS.swaps),
  ].filter(Boolean);
}
// Radar polygon vertices for one team, 12 o'clock, clockwise. Values are 0..100;
// a null value (no data on that axis) is returned as null so the caller can
// bridge the gap in the polygon. Radius 0 or fewer yields no shape at all.
function radarPoints(vals, cx, cy, r){
  if(!(r>0)||!vals||!vals.length) return [];
  return vals.map((v,i)=>{
    if(v==null) return null;
    const t=-Math.PI/2+2*Math.PI*i/vals.length;
    const rr=r*Math.min(100,Math.max(0,v))/100;
    return {x:cx+rr*Math.cos(t), y:cy+rr*Math.sin(t)};
  });
}


// Power rankings — a from-scratch team rating computed from stored match/map
// results (NOT FACEIT's own per-player elo_snapshot on round_players). Series
// Elo is the thing the league itself decides standings by, so it orders the
// table; Map Elo updates far more often (games >> matches) and rides along as
// a faster-reacting secondary signal, never the sort key. A walkover (forfeit
// or no-show, no real map played) still counts as a Series result -- FACEIT's
// own standings count it as a loss, and excluding it entirely made a team that
// defaulted most of its season read as an unproven middling team instead of
// what it actually is. Map form stays blind to it either way: a walkover's
// game rows are synthetic scoring artifacts (fixed score, no real map), never
// a real per-map outcome, so they never touch Map Elo.
const SERIES_ELO_K = 32, MAP_ELO_K = 12, ELO_START = 1500, POWER_MIN_N = 5;

function eloExpected(ra, rb) { return 1 / (1 + Math.pow(10, (rb - ra) / 400)); }
function eloNext(ra, rb, scoreA, k) { return ra + k * (scoreA - eloExpected(ra, rb)); }

function powerRankings(matches) {
  const teams = Object.create(null);
  const team = (name) => teams[name] || (teams[name] = {
    rating: ELO_START, mapRating: ELO_START, n: 0, history: [],
  });

  const ordered = (matches || [])
    .filter(m => m.f1 && m.f2)
    .slice()
    .sort((a, b) => String(a.finished_at || '').localeCompare(String(b.finished_at || '')));

  ordered.forEach(m => {
    const a = team(m.f1), b = team(m.f2);

    if (!m.walkover) {
      (m.games || []).forEach(g => {
        if (g.winner_faction !== 'faction1' && g.winner_faction !== 'faction2') return;
        const scoreA = g.winner_faction === 'faction1' ? 1 : 0;
        const ra = eloNext(a.mapRating, b.mapRating, scoreA, MAP_ELO_K);
        const rb = eloNext(b.mapRating, a.mapRating, 1 - scoreA, MAP_ELO_K);
        a.mapRating = ra; b.mapRating = rb;
      });
    }

    const scoreA = m.winner === 'faction1' ? 1 : m.winner === 'faction2' ? 0 : null;
    if (scoreA == null) return;
    const ra = eloNext(a.rating, b.rating, scoreA, SERIES_ELO_K);
    const rb = eloNext(b.rating, a.rating, 1 - scoreA, SERIES_ELO_K);
    a.rating = ra; b.rating = rb; a.n += 1; b.n += 1;
    a.history.push(Math.round(ra)); b.history.push(Math.round(rb));
  });

  return Object.entries(teams)
    .filter(([, t]) => t.n > 0)
    .map(([name, t]) => ({
      name, rating: Math.round(t.rating), mapRating: Math.round(t.mapRating),
      n: t.n, history: t.history, provisional: t.n < POWER_MIN_N,
    }))
    .sort((a, b) => b.rating - a.rating);
}

// history -> normalized "x,y x,y ..." for an SVG <polyline>. A one-point
// history still draws a flat line across the full width rather than a dot,
// so a team's very first tracked result isn't invisible in the table.
function sparklinePoints(history, w, h) {
  const w_ = w || 60, h_ = h || 20;
  if (!history || !history.length) return '';
  if (history.length === 1) return `0,${h_ / 2} ${w_},${h_ / 2}`;
  const min = Math.min(...history), max = Math.max(...history), span = (max - min) || 1;
  return history.map((v, i) => {
    const x = i / (history.length - 1) * w_;
    const y = h_ - ((v - min) / span) * h_;
    return `${x.toFixed(1)},${y.toFixed(1)}`;
  }).join(' ');
}

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

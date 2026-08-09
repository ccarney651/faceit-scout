// The whole app runs inside bootApp(DATA); DATA arrives either inlined above
// (single-file/offline builds) or fetched from data.json (the shell build). This
// split is what lets next-season gating be a config change — point the fetch at
// the authenticated Worker — rather than a rewrite.
function bootApp(DATA){
const DIVS = DATA.divisions, VIEWS = DATA.views;   // real divisions + combined views
(()=>{ const fb=document.getElementById('footbuilt'); if(fb&&DATA.built_at) fb.textContent='· data updated '+String(DATA.built_at).slice(0,10); })();
// Remembered division (decision in pickDivision above; this is just the IO).
// localStorage throws in some privacy modes and on file:// origins, so both ends
// are guarded — an uncaught throw here would render a blank page.
const DIV_KEY='owdb.division';
const readDivision=()=>{ try{ return localStorage.getItem(DIV_KEY); }catch(e){ return null; } };
const rememberDivision=(id)=>{ try{ localStorage.setItem(DIV_KEY,id); }catch(e){} };
let CURRENT_VIEW = pickDivision(readDivision(), VIEWS);
const viewOf = (id)=> VIEWS.find(v=>v.id===id);
const _vcache = {};
function D(){                                       // active view's data (single or merged)
  const v=viewOf(CURRENT_VIEW);
  if(v.divisions.length===1) return DIVS[v.divisions[0]];
  return _vcache[v.id] || (_vcache[v.id]=mergeDivisions(v));
}
// Merge several divisions into one combined view (matches/teams/meta), no data
// duplication in the file — computed on demand, cached.
function mergeDivisions(v){
  const ds=v.divisions.map(cid=>DIVS[cid]);
  const matches=[].concat(...ds.map(d=>d.matches));
  const upcoming=[].concat(...ds.map(d=>d.upcoming||[]));
  const teams=[].concat(...ds.map(d=>d.teams));
  const team_names=[...new Set([].concat(...ds.map(d=>d.team_names)))].sort();
  const sum={championship:v.label, region:v.region};
  ['matches','played_games','teams','players','walkovers','matches_with_attribution','restarted_games','dc_games']
    .forEach(k=> sum[k]=ds.reduce((a,d)=>a+(d.summary[k]||0),0));
  const fr=ds.map(d=>d.summary.date_from).filter(Boolean).sort();
  const to=ds.map(d=>d.summary.date_to).filter(Boolean).sort();
  sum.date_from=fr[0]||''; sum.date_to=to[to.length-1]||'';
  const mergePanel=(get)=>{ const bm={};
    ds.forEach(d=>((get(d)||{}).by_map||[]).forEach(m=>{
      const e=bm[m.name]||(bm[m.name]={name:m.name,category:m.category,games:0,atk_first_wins:0});
      e.games+=m.games; e.atk_first_wins+=m.atk_first_wins; }));
    return {by_map:Object.values(bm).sort((a,b)=>b.games-a.games),
      total_games:ds.reduce((a,d)=>a+((get(d)||{}).total_games||0),0),
      atk_first_wins:ds.reduce((a,d)=>a+((get(d)||{}).atk_first_wins||0),0)}; };
  return {summary:sum, teams, team_names, matches, upcoming,
    attacking_first:mergePanel(d=>d.attacking_first),
    attacking_first_extra:mergePanel(d=>d.attacking_first_extra)};
}

/* ---------- tiny DOM + format helpers ---------- */
const el = (h)=>{const t=document.createElement('template');t.innerHTML=h.trim();return t.content.firstChild;};
const esc = (s)=> (s==null?'':String(s)).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const nf = (n)=> (n==null?'—':Number(n).toLocaleString('en-US'));
const pctOf = (a,b)=> b? Math.round(100*a/b) : 0;
const dshort = (s)=> s? String(s).slice(0,10) : '?';
// Kickoff time in the viewer's local zone, from a UTC ISO string.
const _DAYS=['Sun','Mon','Tue','Wed','Thu','Fri','Sat'], _MON=['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
function fmtWhen(iso){ if(!iso) return ''; const d=new Date(iso); if(isNaN(d)) return esc(iso);
  const p=n=>String(n).padStart(2,'0');
  return `${_DAYS[d.getDay()]} ${d.getDate()} ${_MON[d.getMonth()]} · ${p(d.getHours())}:${p(d.getMinutes())}`; }
const inc = (o,k,by=1)=>{ o[k]=(o[k]||0)+by; };
const rank = (o)=> Object.entries(o).sort((a,b)=>b[1]-a[1]);   // NB: not `top` (window.top is reserved)
// Small team logo in match headers / team pages. Empty when the faceit ingest has
// no avatar for this team (newly-created teams, or older seasons without logos).
const teamAvatar = (name, size)=>{
  const url=(DATA.team_avatars||{})[name];
  if(!url) return '';
  size = size || 20;
  return `<img class="tlogo" src="${esc(url)}" alt="" style="width:${size}px;height:${size}px" loading="lazy">`;
};

const HERO_ROLE={}; DATA.heroes.forEach(h=>HERO_ROLE[h.name]=h.role);
// Full roster (all heroes, incl. never-banned ones) for the draft simulator's hero picker.
const ROSTER = (DATA.roster&&DATA.roster.length)? DATA.roster : DATA.heroes;
ROSTER.forEach(h=>{ if(!HERO_ROLE[h.name]) HERO_ROLE[h.name]=h.role; });
const MAP_CAT={}; DATA.maps.forEach(m=>MAP_CAT[m.name]=m.category);
// Competitive seats (Tank / Hitscan / Flex DPS / Main Support / Flex Support).
// Unclassified heroes have no seat and fall back to base role everywhere.
const HERO_SEAT={}; (DATA.heroes||[]).forEach(h=>{ if(h.subrole) HERO_SEAT[h.name]=h.subrole; });
const SEATS=DATA.seat_order||['Tank','Hitscan','Flex DPS','Main Support','Flex Support'];
// Games whose comps have been captured by owdb ("match_id:game_no").
const CAPTURED=new Set(DATA.owdb_captured||[]);
// OW wipes invalidate replay codes each patch: a game finished on or before this
// date can never be replayed, so it is only "scoutable" if already captured.
const CODE_WIPE=DATA.code_wipe||null;
const codeDead=(when)=>!!(CODE_WIPE&&when&&String(when).slice(0,10)<=CODE_WIPE);
// League-wide queue of still-scoutable games (see scoutQueue above), computed
// once per page load — matches don't change mid-session, and every consumer
// (nav badge, Most wanted, wipe line) wants the same stable number.
let _leagueQueue;
const leagueQueue=()=> _leagueQueue!==undefined ? _leagueQueue
  : (_leagueQueue=scoutQueue(DIVS, CAPTURED, CODE_WIPE));
// Capture sections append the sample's REAL date range to their subtitle. The
// old label read "captures since <wipe date>", which claimed the comps were
// post-patch when in practice the whole sample usually predates the wipe that
// killed its codes - the one direction of error that misleads a coach.
let _capSampleAll;
function capSampleAll(){
  if(_capSampleAll!==undefined) return _capSampleAll;
  const when={};
  Object.values(DIVS).forEach(d=>[(d.matches||[]),(d.playoffs||[])].forEach(ms=>ms.forEach(m=>{when[m.id]=m.finished_at||'';})));
  const dates=[...CAPTURED].map(k=>when[k.slice(0,k.lastIndexOf(':'))]);
  return (_capSampleAll=capSample(dates,CODE_WIPE));
}
const capSince=()=>{
  const t=capLabelText(capSampleAll(),CODE_WIPE,dshort);
  return t?` <span class="faint" title="Comps come from captured replays. Replay codes reset every patch, so a game can only be scouted while its code lives.">· ${t}</span>`:'';
};
// Map lists everywhere read as a mode block at a time (all Control together, etc),
// and within a mode the maps the league actually plays come first.
const MODE_ORDER=['Control','Escort','Hybrid','Flashpoint','Push','Clash'];
const MAP_POP={};
Object.values(DIVS).forEach(d=>d.matches.forEach(m=>m.games.forEach(g=>{
  if(g.map) MAP_POP[g.map]=(MAP_POP[g.map]||0)+1; })));
// match_id -> match, so a captured comp (which carries only match_id/game_no) can
// be dated by the real match date — capture order is not match order.
const MATCH_BY_ID={};
Object.values(DIVS).forEach(d=>[(d.matches||[]),(d.playoffs||[])].forEach(ms=>ms.forEach(m=>{ MATCH_BY_ID[m.id]=m; })));
const matchWhen=(mid)=> (MATCH_BY_ID[mid]&&MATCH_BY_ID[mid].finished_at)||'';
function modeRank(mp){ const i=MODE_ORDER.indexOf(MAP_CAT[mp]||''); return i<0?MODE_ORDER.length:i; }
function mapCmp(a,b){ return modeRank(a)-modeRank(b) || (MAP_POP[b]||0)-(MAP_POP[a]||0)
                          || a.localeCompare(b); }
function sortMaps(names){ return names.slice().sort(mapCmp); }
const roleVar = (r)=> ({Tank:'var(--tank)',Damage:'var(--damage)',Support:'var(--support)'}[r]||'var(--accent)');
const winVar = (p)=> p>=58?'var(--good)': p>=42?'var(--mid)':'var(--bad)';
// A win-rate cell that never lies at low n (SPEC 10.0): a coloured % only at
// n>=3, else the raw fraction, so a 2-0 can't masquerade as a confident 100%.
function wrCell(wins,games){
  if(!games) return '<span class="faint">—</span>';
  return games>=3 ? pill(pctOf(wins,games)+'%',winVar(pctOf(wins,games)))
                  : `<span class="faint">${wins}/${games}</span>`;
}

/* recency: matches newest-first (recency is measured in matches ≈ how a season is counted).
   Recomputed whenever the active division changes. */
let MATCHES_RECENT=[];
let MATCHES_MODE='played';   // Matches tab: 'played' | 'upcoming' | 'playoffs'
let MATCHES_MODE_SET=false;  // whether the user (or a deep link) has explicitly chosen a mode this session — once true, defaultMatchesMode() no longer overrides it on re-render
function recomputeDivision(){
  MATCHES_RECENT=[...D().matches].sort((a,b)=>{const x=a.finished_at||'',y=b.finished_at||'';return x===y?0:(x<y?1:-1);});
  SCOUT_TEAM=D().team_names[0]||null; SCOUT_N=null;
  const tn=D().team_names;
  SIM_A=tn[0]||null; SIM_B=tn[1]||tn[0]||null; SIM_FIRST='A'; SIM_TREE={};
  DIV_BAN_BASE=null;                        // ban-lift baseline is per division
}
const recent=(arr,lim)=> (lim && lim<arr.length)? arr.slice(0,lim) : arr;
const dateRange=(ms)=>{const w=ms.map(m=>m.finished_at).filter(Boolean).sort();return {from:w[0]||'',to:w[w.length-1]||''};};

// Ban lift: a team's ban rate vs the division's, so the read is "what do they
// value MORE than the field" instead of restating the meta everyone bans. Share-
// based (fraction of ban budget spent on a hero) keeps it comparable across teams.
let DIV_BAN_BASE=null;
function divBanBaseline(){
  if(DIV_BAN_BASE) return DIV_BAN_BASE;
  DIV_BAN_BASE=divBanBaseFrom(D().matches);
  return DIV_BAN_BASE;
}
// A team's ban counts -> lift rows vs a baseline share map. Drops n<minN (a lone
// ban makes any lift meaningless), sorts by lift then count.
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
    const lab=r.lift==null?'new':r.lift>=1.5?'more than most':r.lift<=0.6?'less than most':'typical';
    const col=r.lift==null?'var(--faint)':r.lift>=1.5?'var(--good)':r.lift<=0.6?'var(--bad)':'var(--mid)';
    const liftTitle=r.lift==null?'no field baseline to compare yet':`bans this ${r.lift.toFixed(1)}x more often than the division average`;
    return `<div class="crow"><span>${heroChip(r.hero)} <span class="faint">${r.n} ban${r.n===1?'':'s'} · ${Math.round(r.share*100)}% of theirs vs ${Math.round(r.base*100)}% field</span></span>`+
      `<span class="rec">${r.codes?codesCell(r.codes)+' ':''}<span title="${esc(liftTitle)}">${pill(lab,col)}</span></span></div>`;
  }).join('')+`</div>`;
}

/* ---------- reusable renderers ---------- */
const HERO_ICON=DATA.hero_icons||{};
function heroSlug(n){ return String(n).toLowerCase().replace(/[^a-z0-9]/g,''); }
function heroChip(name){ const r=HERO_ROLE[name], src=HERO_ICON[heroSlug(name)];
  if(src) return `<span class="chip ico"><img class="hicon sm r-${esc(r||'')}" src="${src}" alt="">${esc(name)}</span>`;
  return `<span class="chip"><span class="dot bg-${esc(r||'')}"></span>${esc(name)}</span>`; }
// Icon-only, for dense comp rows where five portraits ARE the information.
function heroIcon(name){ const r=HERO_ROLE[name], src=HERO_ICON[heroSlug(name)];
  return src?`<img class="hicon r-${esc(r||'')}" src="${src}" alt="${esc(name)}" title="${esc(name)}">`
            :heroChip(name); }
function heroIconSmall(name){ const r=HERO_ROLE[name], src=HERO_ICON[heroSlug(name)];
  return src?`<img class="hicon sm r-${esc(r||'')}" src="${src}" alt="${esc(name)}" title="${esc(name)}">`
            :heroChip(name); }
function heroIconMedium(name){ const r=HERO_ROLE[name], src=HERO_ICON[heroSlug(name)];
  return src?`<img class="hicon md r-${esc(r||'')}" src="${src}" alt="${esc(name)}" title="${esc(name)}">`
            :heroChip(name); }
// Comps read best in role order: tank, damage, damage, support, support.
// NB: ROLE_ORDER is declared further down (an array); don't redeclare it.
function roleRank(h){ const i=['Tank','Damage','Support'].indexOf(HERO_ROLE[h]); return i<0?9:i; }
// Seat order makes a comp read as a LINEUP: Tank, Hitscan, Flex, MS, FS. An
// unclassified hero slots after its base role's seats rather than being guessed.
function seatRank(h){
  const s=SEATS.indexOf(HERO_SEAT[h]); if(s>=0) return s*2;
  return roleRank(h)*3+1;   // between the seats of its base role
}
function byRole(heroes){ return heroes.slice().sort((a,b)=>
  seatRank(a)-seatRank(b) || String(a).localeCompare(b)); }
// A comp reads as a LINEUP, not five loose faces: role-order the portraits and
// put a gap between role groups (tank | dps dps | sup sup) so the 1-2-2 shape is
// scannable at a glance.
function compRow(heroes){
  const s=byRole(heroes); let out='';
  s.forEach((h,i)=>{ if(i>0 && HERO_ROLE[h]!==HERO_ROLE[s[i-1]]) out+='<i class="rgap"></i>';
    out+=heroIcon(h); });
  return `<span class="comp">${out}</span>`;
}
// A comp change is only interesting in the heroes that moved - repeating the four
// unchanged portraits buries the one that matters. null = no change at all.
function compDelta(from,to){
  const a=new Set(from), b=new Set(to);
  const out=from.filter(h=>!b.has(h)), inn=to.filter(h=>!a.has(h));
  return (out.length||inn.length)?{out,in:inn}:null;
}
function deltaHtml(d){ return `${compRow(d.out)}<span class="arr">&rarr;</span>${compRow(d.in)}`; }

// Comp-family identity, ported from analysis.same_comp: two lineups are the same
// comp when they share >=4 heroes, or exactly 3 including the same tank. Lets a
// one-hero flex fold into the same comp when we ask "what did they run here".
function tankOf(hs){ return hs.find(h=>HERO_ROLE[h]==='Tank')||null; }
function sameCompJS(a,b){
  const sb=new Set(b); let shared=0; a.forEach(h=>{ if(sb.has(h)) shared++; });
  if(shared>=4) return true;
  if(shared===3){ const t=tankOf(a); return !!t&&sb.has(t)&&tankOf(b)===t; }
  return false;
}
// The representative comp across a set of games (the "average" of the last N):
// cluster by family, the biggest cluster wins, ties broken toward the most recent
// game. `games` is newest-first, each {heroes,won}. Returns {heroes,n,of,wins,losses}.
function modalComp(games){
  if(!games.length) return null;
  const used=new Array(games.length).fill(false), clusters=[];
  for(let i=0;i<games.length;i++){ if(used[i])continue;
    const c=[i]; used[i]=true;
    for(let j=i+1;j<games.length;j++){
      if(!used[j]&&sameCompJS(games[i].heroes,games[j].heroes)){ c.push(j); used[j]=true; } }
    clusters.push(c); }
  clusters.sort((x,y)=> y.length-x.length || x[0]-y[0]);  // size, then most-recent anchor
  const best=clusters[0], wins=best.filter(k=>games[k].won).length;
  return {heroes:games[best[0]].heroes, n:best.length, of:games.length,
          wins, losses:best.length-wins};
}
// A team's captured games on one map, newest match first, each carrying the
// opponent and the opening comp — the raw material for "last 3" + full history.
function mapHistory(scout, mp){
  return (scout.matchups||[]).filter(m=>m.map===mp)
    .map(m=>({heroes:m.open||[], won:m.won, opp:m.opp, when:matchWhen(m.match_id)}))
    .sort((a,b)=> (b.when||'').localeCompare(a.when||''));
}

function swapLine(s){
  // One arrow only: the enemy lineup is the TRIGGER (context), the single arrow
  // is the actual out->in swap. A second arrow after "vs" read as a swap too.
  // Baseline subtraction (heroes present in ~every enemy lineup, not just at
  // the swap) already happened server-side in aggregate_swaps - s.vs is
  // pre-filtered to actual triggers.
  const vs=s.vs||[];
  const trig=vs.length
    ? `<span class="faint">vs</span>${compRow(vs.slice(0,5))}<span class="faint swapsep">&middot;</span>`
    : '';
  return `<div class="crow${s.count<=1?' thin':''}">`+
    `<span class="swapline">${trig}${deltaHtml({out:s.out,in:s.in})}</span>`+
    `<span class="rec">${s.count}x · ${s.kind==='core'?'comp change':'flex'}</span></div>`;
}
function pill(text,color){ return `<span class="pill" style="background:color-mix(in srgb,${color} 16%,transparent);color:${color}">${esc(text)}</span>`; }
function tag(text,cls=''){ return `<span class="tag ${cls}">${esc(text)}</span>`; }
// A team name rendered as a click-to-scout link (jumps to that team's scout
// page); the capture icon beside it jumps straight into the capture tool,
// pre-filtered to this team.
function teamLink(name,extra){ return name?`<span class="tlink" data-scout="${esc(name)}" title="Scout ${esc(name)}" style="display:flex;align-items:center;gap:8px">${teamAvatar(name,24)}${esc(name)}${capBtn(name)}</span>${extra||''}`:'<span class="faint">—</span>'; }
document.addEventListener('click',e=>{ const t=e.target.closest('[data-scout]');
  // An <a> inside the team link (the capture icon) navigates on its own — don't
  // hijack it into the Scout page.
  if(t&&t.dataset.scout&&!e.target.closest('a')){ e.preventDefault(); gotoScout(t.dataset.scout); } });
// Playoff bracket nodes: a finished match card opens its detail page. Guarded
// the same way matchCard's own onclick is — a team name (data-scout) or replay
// chip inside the card wins, and a plain click opens the match.
document.addEventListener('click',e=>{ const t=e.target.closest('[data-match]');
  if(t&&t.dataset.match&&!e.target.closest('[data-scout]')&&!e.target.closest('.rc')&&!e.target.closest('a')){ e.preventDefault(); openMatch(t.dataset.match); } });
// Overwatch replay code — click to jump into the capture tool with this code
// pre-loaded (the tool copies it, so pasting into OW2 → Watch → Replays still works).
function rcChip(code){ return `<code class="rc" data-rc="${esc(code)}" title="Open this replay in the capture tool — the code is copied for Overwatch">${esc(code)}</code>`; }
// Evidence-row codes cell: exactly one backing game -> the code chip inline,
// no click needed (the common thin-sample case, and the explicit ask —
// "bring me straight to code"). More than one -> a small click-to-open link.
// The resolved rows travel in a data attribute (JSON, esc()-quoted) rather
// than an external registry, since table() rebuilds every row's HTML string
// from scratch on every re-sort and an insertion-order registry would go
// stale across that rebuild.
const wipedTag='<span class="faint" style="font-size:11.5px" title="This replay code predates the last OW patch\'s code wipe and no longer loads in-game.">code wiped</span>';
function codesCell(rows){
  if(!rows.length) return '<span class="faint">—</span>';
  if(rows.length===1) return rows[0].dead ? wipedTag : rcChip(rows[0].code);
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
    `<div class="codesrow"><span>${esc(r.map)} <span class="faint">vs ${esc(r.opp||'—')} · ${dshort(r.when)}</span></span>${r.dead?wipedTag:rcChip(r.code)}</div>`)));
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
document.addEventListener('click',e=>{
  const rc=e.target.closest('.rc'); if(!rc||!rc.dataset.rc) return;
  // Jump into the capture tool with this code pre-loaded (it auto-copies the
  // code for pasting into Overwatch). A code chip can sit inside a match-history
  // <a> row — stop that anchor's default from also firing.
  e.preventDefault();
  location.href=captureCodeUrl(rc.dataset.rc);
});

/* ---------- shared match card (used by Matches tab and Scout page) ---------- */
// Per-map stat tables, one per team: Player | E | Dmg | Heal | D. The hero next
// to a name is that player's primary hero ON THIS MAP when the capture carried
// per-player attribution (owdb's per_game_players), else their season
// most-played hero (owdb_comps), else nothing but the name.
function rosterHTML(m,g){
  const pgHeroes=(DATA.owdb_pergame_players||{})[m.id+':'+g.game_no]||{};
  const seasonHero=(team,nick)=>{ const ps=(((DATA.owdb_comps||{})[team]||{}).scout||{}).players||[];
    const p=ps.find(x=>x.player===nick); return p&&p.heroes&&p.heroes[0]?p.heroes[0].hero:null; };
  const portrait=(hero)=>{ if(!hero) return '';
    const r=HERO_ROLE[hero], src=HERO_ICON[heroSlug(hero)];
    return src?`<img class="hicon r-${esc(r||'')}" src="${src}" alt="" title="${esc(hero)}">`
              :`<span class="dot bg-${esc(r||'')}" title="${esc(hero)}"></span>`; };
  const wrap=el(`<div class="rosters"></div>`);
  (g.rosters||[]).forEach(rt=>{
    const box=el(`<div class="roster"><h4>${esc(rt.team)}</h4></div>`);
    const table=el(`<table><thead><tr>`+
      `<th class="pname" data-k="nick" data-num="0">Player<span class="sar"></span></th>`+
      `<th class="num" data-k="e" data-num="1">E<span class="sar"></span></th>`+
      `<th class="num" data-k="dmg" data-num="1">Dmg<span class="sar"></span></th>`+
      `<th class="num" data-k="heal" data-num="1">Heal<span class="sar"></span></th>`+
      `<th class="num" data-k="d" data-num="1">D<span class="sar"></span></th></tr></thead>`+
      `<tbody></tbody></table>`);
    const tbody=table.querySelector('tbody');
    let rows=rt.players.map(p=>{
      const hero=pgHeroes[p.nick]||seasonHero(rt.team,p.nick);
      return {hero,nick:p.nick,e:p.e||0,dmg:p.dmg||0,heal:p.heal||0,d:p.d||0,cap:!!p.cap};
    });
    const render=()=>{
      tbody.innerHTML='';
      if(!rows.length){ tbody.innerHTML=`<tr><td class="faint" colspan="5">—</td></tr>`; return; }
      rows.forEach(r=>{
        if(!r.cap){
          tbody.insertAdjacentHTML('beforeend',`<tr><td class="pname">${portrait(r.hero)}<span>${esc(r.nick)}</span></td>`+
            `<td class="num faint" colspan="4">stats not captured (DC)</td></tr>`);
        } else {
          tbody.insertAdjacentHTML('beforeend',`<tr><td class="pname">${portrait(r.hero)}<span>${esc(r.nick)}</span></td>`+
            `<td class="num">${nf(r.e)}</td><td class="num">${nf(r.dmg)}</td>`+
            `<td class="num">${nf(r.heal)}</td><td class="num">${nf(r.d)}</td></tr>`);
        }
      });
    };
    const asc={};
    table.querySelectorAll('th').forEach(th=>th.onclick=()=>{
      const k=th.dataset.k, num=th.dataset.num==='1';
      asc[k]=!asc[k];
      rows=[...rows].sort((a,b)=>{
        if(a.cap!==b.cap) return a.cap?-1:1;
        let x=a[k],y=b[k];
        if(num){ x=+x||0; y=+y||0; return asc[k]?x-y:y-x; }
        return asc[k]?String(x).localeCompare(String(y)):String(y).localeCompare(String(x));
      });
      table.querySelectorAll('th').forEach(t=>{t.classList.remove('sorted');t.querySelector('.sar').textContent='';});
      th.classList.add('sorted'); th.querySelector('.sar').textContent=asc[k]?'▲':'▼';
      render();
    });
    render();
    box.appendChild(table);
    wrap.appendChild(box);
  });
  return wrap;
}
// Bans in draft order: 1st ban, 2nd ban — with the team that banned it.
function bansOrdered(g){
  const ord=[...g.bans].sort((a,b)=>(a.order||9)-(b.order||9));
  return ord.map(b=>`<span class="banstep"><span class="ord">${b.order||'?'}</span> `+
    `<b>${b.team?esc(b.team):'<span class=\'faint\'>?</span>'}</b> banned ${heroChip(b.hero)}</span>`).join('');
}
// One full match card: header (teams/score), then each map with bans + toggleable rosters.
// Canonical segment order for a game's per-team opening comps: attack/defend for
// Escort/Hybrid, a single 'map' for Push/Flashpoint, else control sub-maps in
// play order. Both teams share the same segments, so we can grid them.
function segOrder(pg){
  const all=new Set();
  Object.values(pg).forEach(segs=>Object.keys(segs).forEach(s=>all.add(s)));
  if(all.has('attack')||all.has('defend')) return ['attack','defend'].filter(s=>all.has(s));
  if(all.has('map')) return ['map'];
  const order=[]; Object.values(pg).forEach(segs=>Object.keys(segs).forEach(s=>{ if(!order.includes(s)) order.push(s); }));
  return order;
}
// The compact "at a glance" match card: header (teams/score/tags) + one pip
// per played map. Everything the old card used to expand inline (bans, per-
// segment comps, rosters) now lives on the match detail page - click the
// card (anywhere except a team name or a replay-code chip) to open it.
function matchCard(m, opts={}){
  const c=el(`<div class="card match mrow"></div>`);
  const w1=m.winner==='faction1',w2=m.winner==='faction2';
  // Team names double as click-to-scout links (hover-only underline — a resting
  // dotted line under every name would clutter this dense list).
  const teamName=(name,cls)=> name
    ? `<span class="${cls} tscout" data-scout="${esc(name)}" title="Scout ${esc(name)}">${teamAvatar(name)}${esc(name)}${capBtn(name)}</span>`
    : `<span class="${cls}">?</span>`;
  c.appendChild(el(`<div class="hd"><div class="teams">${teamName(m.f1,w1?'win':'lose')}`+
    `<span class="score">${esc(m.series)}</span>${teamName(m.f2,w2?'win':'lose')}</div>`+
    `<div class="tags">${m.walkover?tag('walkover','bad'):(m.forfeit?tag('forfeit','bad'):'')} `+
    `${m.playoff?tag('playoff','playoff'):''} `+
    // When it was played: a comp read from a 6-week-old match is weaker evidence
    // than last week's, and nothing else on the card says how old it is.
    `${m.finished_at?tag(dshort(m.finished_at)):''} ${tag('R'+m.round+' · G'+m.group)}</div></div>`));
  const games=m.games.filter(g=>g.map);
  if(games.length){
    // Stripped-down comp preview in each map bar (Matches tab only). The grid is
    // 5 columns so the map, each team's comp, and the code line up across every map
    // in the series. A full-width ban line below mirrors the match detail page.
    const compBit=(g)=>{
      if(!opts.showComps) return '';
      const pg=(DATA.owdb_pergame||{})[m.id+':'+g.game_no];
      if(!pg) return '';
      const order=segOrder(pg), seg=order[0];
      if(!seg) return '';
      const f1c=(pg[m.f1]||{})[seg], f2c=(pg[m.f2]||{})[seg];
      if(!f1c && !f2c) return '';
      return `<span class="mscomp f1">${compRow(f1c||[])}</span><span class="msvs">vs</span><span class="mscomp f2">${compRow(f2c||[])}</span>`;
    };
    const bansLine=(g)=>{
      if(!opts.showComps || !g.bans || !g.bans.length) return '';
      return `<div class="msbansline"><div class="bans">${bansOrdered(g)}</div></div>`;
    };
    const score=el(`<div class="mscores"></div>`);
    games.forEach(g=>{
      const codeBit=g.demo_code?(codeDead(m.finished_at)?wipedTag:rcChip(g.demo_code)):'';
      const cbit=compBit(g), bline=bansLine(g);
      const cls=mapPipClass(g);
      if(opts.showComps){
        score.appendChild(el(`<div class="msline ${cls}"><div class="msrow"><span class="msmap">${esc(g.map)} <span class="msnum">${esc(g.f1)}–${esc(g.f2)}</span></span>${cbit}<span class="msright">${codeBit}</span></div>${bline}</div>`));
      } else {
        score.appendChild(el(`<div class="msline ${cls}"><div class="msrow rail"><span class="msmap">${esc(g.map)} <span class="msnum">${esc(g.f1)}–${esc(g.f2)}</span></span><span class="msright">${codeBit}</span></div></div>`));
      }
    });
    c.appendChild(score);
    const sc=scoutedCount(m, CAPTURED);
    const live=matchLiveTodo(m, CAPTURED, CODE_WIPE);
    if(sc.total) c.appendChild(el(`<p class="note mscouted"${live.length?' style="display:flex;align-items:center;gap:8px"':''}>`+
      `🎥 ${sc.done}/${sc.total} scouted`+
      (live.length?` <a class="btn" href="${captureCodeUrl(live[live.length-1].demo_code)}" title="Open this match's newest unscouted replay in the capture tool" style="text-decoration:none;padding:3px 10px;font-size:11.5px;margin-left:auto;white-space:nowrap">Scout →</a>`:'')+`</p>`));
  }
  // Whole-card click opens the detail page, except a team name (click-to-scout)
  // or a replay-code chip (click-to-copy) or a Scout button (deep-link) inside a
  // pip — same guard pattern the old per-game rosters toggle used for `.rc`.
  c.onclick=(e)=>{ if(e.target.closest('[data-scout]')||e.target.closest('.rc')||e.target.closest('a')) return; openMatch(m.id); };
  return c;
}

// One map's full detail: header (map/score/side/code/scouted), bans, opening
// comps, and the roster/stat table — always visible (no toggle; this is
// already the detail view, nothing left to progressively disclose). Used by
// the match detail page's tabs (renderMatchDetail below); matchCard is now a
// compact summary and no longer renders this itself.
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
  const pg=(DATA.owdb_pergame||{})[m.id+':'+g.game_no];
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
  gEl.appendChild(rosterHTML(m,g));
  return gEl;
}
// All-maps-at-a-glance series overview (owdber-style): small cards side by
// side, each showing one map's score, winner, and capture status. Clicking a
// card selects that map's panel below.
function seriesOverview(m,games,onSelect){
  const wrap=el(`<div class="seriesov"></div>`);
  games.forEach((g,i)=>{
    const cls=mapPipClass(g);
    const cap=CAPTURED.has(m.id+':'+g.game_no);
    const card=el(`<div class="gcard ${cls}" data-gno="${g.game_no}">`+
      `<div class="ghead"><span class="gno">M${g.game_no}</span><span class="gmap">${esc(g.map)}</span>`+
      `<span class="gcat">${esc(g.map_category||'')}</span></div>`+
      `<span class="gsc">${esc(g.f1)}–${esc(g.f2)}</span>`+
      `<span class="gwin">${g.winner_team?esc(g.winner_team):'—'}</span>`+
      `<div class="gmeta">${cap?'<span class="gcap" title="captured">✓ captured</span>':'<span></span>'}`+
      `<span class="muted">${g.demo_code?(codeDead(m.finished_at)?'wiped':'replay'):'no replay'}</span></div>`+
      `</div>`);
    card.onclick=()=>onSelect(g.game_no);
    wrap.appendChild(card);
  });
  return wrap;
}
// The match detail page: header (teams/score/tags, same as the compact
// card's), a back link, a horizontal strip of map cards, and the selected map's panel.
function renderMatchDetail(m){
  const wrap=el(`<div class="card match matchdetail"></div>`);
  if(!m){ wrap.appendChild(el(`<p class="note" style="padding:16px">Match not found.</p>`)); return wrap; }
  const back=el(`<a class="backlink" href="#matches">‹ Matches</a>`);
  back.onclick=(e)=>{ e.preventDefault(); show('matches'); };
  wrap.appendChild(back);
  const w1=m.winner==='faction1', w2=m.winner==='faction2';
  const _teamName=(name,cls)=> name
    ? `<span class="${cls} tscout" data-scout="${esc(name)}" title="Scout ${esc(name)}">${teamAvatar(name)}${esc(name)}${capBtn(name)}</span>`
    : `<span class="${cls}">?</span>`;
  wrap.appendChild(el(`<div class="hd"><div class="teams">${_teamName(m.f1,w1?'win':'lose')}`+
    `<span class="score">${esc(m.series)}</span>${_teamName(m.f2,w2?'win':'lose')}</div>`+
    `<div class="tags">${m.walkover?tag('walkover','bad'):(m.forfeit?tag('forfeit','bad'):'')} `+
    `${m.playoff?tag('playoff','playoff'):''} `+
    `${m.finished_at?tag(dshort(m.finished_at)):''} ${tag('R'+m.round+' · G'+m.group)}</div></div>`));
  // Scout push: the live replay codes in THIS match that nobody has captured yet.
  // The detail page doubles as a capture queue — the one place where the specific
  // game, teams and map are already in front of the scout. Nothing renders when
  // every code is captured (or wiped and uncapturable).
  const todo=matchLiveTodo(m, CAPTURED, CODE_WIPE);
  if(todo.length){
    const sc=scoutedCount(m, CAPTURED);
    const maps=[...new Set(todo.map(g=>g.map))].join(', ');
    wrap.appendChild(el(`<div class="scoutcta">`+
      `<span class="sct"><b>${sc.done}/${sc.total} scouted</b> — `+
      `${esc(maps)} still open to capture — replay codes stop working at the next patch. About a minute per map in the capture tool.</span>`+
      `<a class="btn" href="${captureCodeUrl(todo[todo.length-1].demo_code)}" title="Open this match's newest unscouted replay in the capture tool" style="text-decoration:none;padding:4px 12px;font-size:12px;white-space:nowrap">Scout ${esc(todo[todo.length-1].demo_code)} →</a></div>`));
  }
  const games=m.games.filter(g=>g.map);
  if(!games.length){ wrap.appendChild(el(`<p class="note" style="padding:0 16px 16px">No maps played.</p>`)); return wrap; }
  const panel=el(`<div></div>`);
  let active=games[0].game_no;
  const ov=seriesOverview(m,games,gno=>{ active=gno; draw(); });
  function draw(){
    [...ov.children].forEach(c=>c.classList.toggle('selA', +c.dataset.gno===active));
    panel.innerHTML=''; panel.appendChild(gamePanel(m, games.find(g=>g.game_no===active)));
  }
  wrap.appendChild(ov);
  wrap.appendChild(panel);
  draw();
  return wrap;
}

// horizontal bar list. items:[{label(html), value, color?}]
function barList(items){
  if(!items.length) return `<p class="note">No data in this window.</p>`;
  const max=Math.max(1,...items.map(i=>i.value));
  return `<div>`+items.map(i=>{
    const w=Math.max(2,Math.round(100*i.value/max));
    const you=i.you?' you':'';
    return `<div class="barrow${you}"><div class="lab">${i.label}${i.you?`<span class="youdot">you</span>`:''}</div>`+
      `<div class="track"><div class="fill" style="width:${w}%;background:${i.color||'var(--accent)'}"></div></div>`+
      `<div class="barval">${i.value}</div></div>`;
  }).join('')+`</div>`;
}

// sortable table. cols:[{k,label,num?,html?}]
// `group` (optional): row -> group name. In the table's natural order the rows are
// broken into labelled blocks — a map list reads as one mode at a time, not as 13
// undifferentiated rows. Sorting by a column drops the grouping, since comparing
// across every map is the whole point of clicking a header.
function table(cols,rows,group){
  const head=`<tr>`+cols.map((c,i)=>`<th class="${c.num?'num':''}" data-i="${i}">${esc(c.label)}<span class="sar"></span></th>`).join('')+`</tr>`;
  // `tag` labels the row inline; used only once the grouping headers are gone, so
  // a sorted map table still tells you which mode each map is.
  const tr=(r,tag)=>`<tr>`+cols.map((c,i)=>`<td class="${c.num?'num':''}">`+
    `${c.html?c.html(r):esc(r[c.k])}`+
    `${i===0&&tag?` <span class="faint">${esc(tag)}</span>`:''}</td>`).join('')+`</tr>`;
  const body=(rs,grp)=>{
    if(!grp) return rs.map(r=>tr(r,group?group(r):null)).join('');
    let last=null;
    return rs.map(r=>{
      const g=grp(r), h=g===last?'':`<tr class="grp"><td colspan="${cols.length}">${esc(g)}</td></tr>`;
      last=g; return h+tr(r,null);
    }).join('');
  };
  const box=el(`<div class="scroll"><table><thead>${head}</thead><tbody>${body(rows,group)}</tbody></table></div>`);
  const asc={};
  box.querySelectorAll('th').forEach(th=>th.onclick=()=>{
    const i=+th.dataset.i,c=cols[i];asc[i]=!asc[i];
    const s=[...rows].sort((a,b)=>{let x=a[c.k],y=b[c.k];if(c.num){x=+x||0;y=+y||0;return asc[i]?x-y:y-x;}return asc[i]?String(x).localeCompare(String(y)):String(y).localeCompare(String(x));});
    box.querySelectorAll('th').forEach(t=>{t.classList.remove('sorted');t.querySelector('.sar').textContent='';});
    th.classList.add('sorted'); th.querySelector('.sar').textContent = asc[i]?'▲':'▼';
    box.querySelector('tbody').innerHTML=body(s,null);
  });
  return box;
}
// The mode of a row's map — the grouping key for every map table.
const byMode=r=>MAP_CAT[r.map]||r.cat||'Other';

// Decision clusters + evidence drawers: answers stay open, receipts fold.
const cluster=(id,label)=>el(`<div class="cluster-h" id="${id}">${label}</div>`);
function drawer(title, hint){
  const d=el(`<details class="mapblk"><summary><span>${title}</span>`+
    `<span class="rec faint">${hint}</span></summary>`+
    `<div class="mapbody" style="display:block"></div></details>`);
  return {root:d, body:d.querySelector('.mapbody')};
}

function sectionH(title,right=''){ return `<div class="section-h"><h2>${esc(title)}</h2>${right}</div>`; }

// Recency control: a slider + number box (synced) over 1..total matches.
// onChange gets the limit (a number, or null for "all"). Returns the group node.
// `total` = matches actually available (drives the "all"/label logic); `sliderMax`
// = how far the control can go (defaults to total; Scout sets a floor of 15).
function makeRecency(total, currentN, onChange, sliderMax){
  sliderMax = sliderMax || total;
  const g=el(`<span class="recency"></span>`);
  const slider=el(`<input type="range" min="1" step="1" aria-label="recent matches">`);
  const num=el(`<input type="number" min="1" step="1" aria-label="recent matches">`);
  const lab=el(`<span class="winlab"></span>`);
  slider.max=num.max=sliderMax;
  const upd=(v,fire)=>{ const n=Math.max(1,Math.min(sliderMax,parseInt(v,10)||sliderMax));
    slider.value=num.value=n; lab.textContent = n>=total ? `all ${total} matches` : `last ${n} of ${total}`;
    if(fire) onChange(n>=total?null:n); };
  slider.oninput=()=>upd(slider.value,true);
  num.oninput=()=>upd(num.value,true);
  g.append(slider,num,lab); upd(currentN,false);
  return g;
}

/* ---------- aggregation over a set of matches ---------- */
// team=null → league-wide; else that team's own bans/picks/counters + map win rates.
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
        const pg=(DATA.owdb_pergame||{})[m.id+':'+g.game_no];
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

/* ============================================================ PLAYOFFS */
// Qualifier count per tier (FACEIT League S8 EMEA; update when S9 formats post).
// Every division is double elimination, Ft5, Grand Final Ft7. 24 (Advanced) seeds
// into a 32-slot bracket, so the top 8 draw byes automatically — no special case.
const PLAYOFF_QUALIFIERS={Master:8,Expert:16,Advanced:24,Open:32};
const tierOf=(name)=>['Master','Expert','Advanced','Open'].find(t=>(name||'').includes(t))||null;
const regionOf=(name)=>['EMEA','NA'].find(r=>String(name||'').toUpperCase().replace(/-/g,' ').split(/\s+/).includes(r))||null;
// Deep-link into the browser capture tool, pre-filtered to a team (+ its division).
// The division must be REGION-QUALIFIED ("EMEA Master") to match the labels
// tools/build_capture_data.py emits — a bare tier merges both regions there.
const captureUrl=(team)=>{ const c=String((D().summary||{}).championship||''), t=tierOf(c), r=regionOf(c);
  const d=(r&&t)?r+' '+t:''; return 'capture/?team='+encodeURIComponent(team)+(d?'&division='+encodeURIComponent(d):''); };
// Deep-link into the capture tool by replay code alone. A code is unique across
// the whole feed (unlike a match id, which is only unique within its division),
// so the capture page can locate it without a team/division hint.
const captureCodeUrl=(code)=>'capture/?code='+encodeURIComponent(code);
// Compact capture icon for team-name links: one click into the capture tool,
// pre-filtered to this team. The name itself still opens the Scout page.
const capBtn=(team)=>`<a class="capbtn" href="${captureUrl(team)}" title="Capture ${esc(team)} →" aria-label="Capture ${esc(team)}">`+
  `<svg viewBox="0 0 16 16" width="13" height="13" aria-hidden="true"><circle cx="8" cy="8" r="5.2" fill="none" stroke="currentColor" stroke-width="1.5"/><circle cx="8" cy="8" r="2.6" fill="currentColor"/></svg></a>`;
const nextPow2=(n)=>{let k=1;while(k<n)k*=2;return k;};
// Standard bracket seed order so 1 & 2 can only meet in the final:
// seeds(4)=[1,4,2,3]; seeds(8)=[1,8,4,5,2,7,3,6].
function seedOrder(k){let s=[1];while(s.length<k){const m=s.length*2+1,t=[];for(const x of s)t.push(x,m-x);s=t;}return s;}
const ubRoundName=(m)=> m===1?'Final':m===2?'Semifinals':m===4?'Quarterfinals':'Round of '+(2*m);

function renderPlayoffs(){
  const wrap=el(`<div class="stack"></div>`);
  const tier=tierOf(String((D().summary||{}).championship||''));
  if(!tier){
    wrap.appendChild(el(`<div class="card"><p class="eyebrow">Playoffs</p>`+
      `<p class="note">Pick a single division (Master / Expert / Advanced / Open) from the switcher above — a Combined view has no single bracket.</p></div>`));
    return wrap;
  }
  const N=PLAYOFF_QUALIFIERS[tier]||8, teams=D().teams||[], k=nextPow2(N);
  const ubRounds=Math.round(Math.log2(k)), lbRounds=2*(ubRounds-1), order=seedOrder(k);
  const po=D().playoffs||[];   // real bracket matches (finished + scheduled), attached from the playoff championship (empty until it exists)
  const done=po.filter(m=>m.status==='FINISHED').length, up=po.length-done;

  // One tree merges both sources: real matches sit in their bracket stage and the
  // empty slots are the standings-based projection (dashed). Nodes reuse the
  // Matches → Played card language, compressed to the series level — winner gets a
  // good-colored edge, losers dim, upcoming slots show kickoff instead of a score.
  const side=(n,cls)=> n
    ? `<span class="pside ${cls} tscout" data-scout="${esc(n)}" title="Scout ${esc(n)}">${teamAvatar(n,16)}<span class="pn">${esc(n)}</span>${capBtn(n)}</span>`
    : `<span class="pside tbd">TBD</span>`;
  const node=(m)=>{
    const fin=m.status==='FINISHED';
    const w1=fin&&m.winner_team&&m.winner_team===m.f1, w2=fin&&m.winner_team&&m.winner_team===m.f2;
    const cls=fin?(w1?' f1win':w2?' f2win':''):' soon';
    // A finished node opens the full match page (per-map scores, comps, bans) —
    // the same detail view a regular-season match gets. Upcoming/TBD slots stay
    // inert. Clicking a team name inside still goes to that team's scout page.
    const open=fin&&m.id?` data-match="${esc(m.id)}"`:'';
    return `<div class="pcard${cls}"${open}><div class="pteams">`+
      side(m.f1, fin?(w1?'':'lose'):'')+
      `<span class="pscore${fin?'':' vs'}">${fin?esc(m.series||'—'):'vs'}</span>`+
      side(m.f2, fin?(w2?'':'lose'):'')+
      `</div><div class="pfoot"><span class="pbo">Bo${m.best_of||5}</span>`+
      (m.forfeit?'<span class="tag bad" style="margin-left:4px">FF</span>':'')+
      `<span class="pwhen">${fin?dshort(m.finished_at):(m.scheduled_at?fmtWhen(m.scheduled_at):'time TBD')}</span>`+
      `</div></div>`;
  };
  const projSide=(seed)=>{
    if(seed==null||seed>N) return null;
    const t=teams[seed-1];
    return t?{seed,name:t.name}:null;
  };
  const proj=(p)=> p
    ? `<span class="pside proj tscout" data-scout="${esc(p.name)}" title="Scout ${esc(p.name)}">${teamAvatar(p.name,16)}<span class="pn">${esc(p.name)}</span>${capBtn(p.name)}</span>`
    : `<span class="pside tbd">TBD</span>`;
  const blank=(a,b,bo)=>`<div class="pcard proj"><div class="pteams">${proj(a)}<span class="pscore vs">vs</span>${proj(b)}</div>`+
    `<div class="pfoot"><span class="pbo">Bo${bo||5}</span><span class="pwhen">—</span></div></div>`;

  // Real matches bucketed by bracket column (see playoffStageKey): each column
  // consumes its own stage so a partially played round never bleeds into the
  // next one.
  const stageKey=(m)=> playoffStageKey(m, ubRounds, lbRounds);
  const pool=po.slice().sort((a,b)=> (stageKey(a)-stageKey(b)) || String(a.finished_at||a.scheduled_at||'').localeCompare(String(b.finished_at||b.scheduled_at||'')));
  // Bucket by stage-key VALUE, not insertion position — a round with no real
  // match yet must not shift later matches into the wrong column.
  const byStage=new Map();
  pool.forEach(m=>{ const g=stageKey(m); if(!byStage.has(g)) byStage.set(g,[]); byStage.get(g).push(m); });
  const fill=(i,cnt,seeds,bo)=>{
    const ms=byStage.get(i)||[], pairs=seeds||[];
    let out='';
    for(let j=0;j<cnt;j++){
      const m=ms[j];
      if(m) out+=node(m);
      else out+=(pairs[j]?blank(projSide(pairs[j][0]),projSide(pairs[j][1]),bo):blank(null,null,bo));
    }
    return out;
  };

  const seedPairs=[]; for(let i=0;i<k/2;i++) seedPairs.push([order[2*i],order[2*i+1]]);
  const ubSizes=[]; for(let m=k/2;m>=1;m/=2) ubSizes.push(m);
  const lbSizes=[]; for(let j=1;j<=lbRounds;j++) lbSizes.push(Math.pow(2,(ubRounds-1)-Math.ceil(j/2)));
  const col=(title,inner)=>{const c=el(`<div class="br-col"></div>`);c.appendChild(el(`<h4>${esc(title)}</h4>`));c.appendChild(el(`<div class="br-col-body">${inner}</div>`));return c;};
  const flow=()=>{const b=el(`<div class="bracket"><div class="br-flow"></div></div>`);return[b,b.querySelector('.br-flow')];};

  const brCard=el(`<div class="card"></div>`);
  brCard.appendChild(el(`<p class="eyebrow">${esc(tier)} playoffs — bracket</p>`));
  brCard.appendChild(el(`<p style="margin:2px 0 0;font-size:14px">Top <b>${N}</b> · double elimination · Ft5 <span class="faint">(Grand Final Ft7)</span></p>`));
  brCard.appendChild(el(`<p class="note">${po.length?`${done} played${up?` · ${up} upcoming`:''} — blank slots are the standings-based projection.`:'Seeded by current standings (win %). Bracket slots fill in once playoffs begin — no playoff matches exist yet.'} S9 playoffs run <b>Aug 3–16</b>.</p>`));

  brCard.appendChild(el(`<p class="note" style="margin:0 0 4px"><b>Upper bracket</b></p>`));
  const [ub,ubFlow]=flow();
  ubSizes.forEach((s,i)=>{ ubFlow.appendChild(col(ubRoundName(s), fill(i, s, i===0?seedPairs:null))); });
  brCard.appendChild(ub);

  brCard.appendChild(el(`<p class="note mt14"><b>Lower bracket</b> <span class="faint">— filled by upper-bracket losers</span></p>`));
  const [lb,lbFlow]=flow();
  lbSizes.forEach((s,i)=>{ lbFlow.appendChild(col('LB round '+(i+1), fill(ubSizes.length+i, s, null))); });
  brCard.appendChild(lb);

  brCard.appendChild(el(`<p class="note mt14"><b>Grand Final</b></p>`));
  const [gf,gfFlow]=flow();
  gfFlow.appendChild(col('Grand Final (Ft7)', fill(ubSizes.length+lbSizes.length, 1, null, 7)));
  brCard.appendChild(gf);

  wrap.appendChild(brCard);

  // Projected seeds
  const seedCard=el(`<div class="card"></div>`);
  seedCard.appendChild(el(`<p class="eyebrow">Projected seeds (top ${N})</p>`));
  const sg=el(`<div class="crowgrid"></div>`);
  for(let i=0;i<N;i++){const t=teams[i];
    sg.appendChild(el(`<div class="crow">`+
      `<span style="min-width:0;flex:1;overflow:hidden;text-overflow:ellipsis"><span class="br-seed">${i+1}</span> ${t?esc(t.name):'<span class="faint">— not enough teams yet —</span>'}</span>`+
      `<span class="rec">${t?t.win_pct+'%':''}</span></div>`));
  }
  seedCard.appendChild(sg); wrap.appendChild(seedCard);
  return wrap;
}

/* ============================================================= VIEWS */
const TABS=[
 {id:'overview',label:'Overview',render:renderOverview},
 {id:'scout',label:'Teams',render:renderScout},
 {id:'players',label:'Players',render:renderPlayers},
 {id:'meta',label:'League meta',render:renderMeta},
  {id:'matches',label:'Matches',render:renderMatches},
];

let SCOUT_TEAM = null;   // set per division by recomputeDivision()
let SCOUT_PREP=false;       // scout tab: full detail vs the condensed prep sheet
let MATCH_ID=null;          // match detail page: which match, within the active division
let COMPARE_A=null, COMPARE_B=null; // team compare page: the two teams being compared
const PLANNED={};           // counter-scout: team -> Set of planned hero names
let SCOUT_N=null, META_N=40;   // recent-match counts; null = all
let PLAYERS_ROLE='All';         // Leaderboard role filter: All | Tank | Damage | Support
let PLAYERS_VIEW='team';        // Players tab mode: 'team' | 'role' | 'rank'
let PLAYERS_SORT='eff';         // Leaderboard sort column (see LB_COLS); Eff default, like By role
let PLAYERS_ROLE_SORT='eff';    // By role view: sort column shared by every role card (see LB_COLS)
let PLAYERS_SEAT=null;          // By role view: which role table is shown (one at a time; null = first)
// Leaderboard columns, in table order. `rate` marks a per-map average, which
// needs a sample floor to be meaningful; counts and elo do not.
// Hero win rate needs a real sample before it means anything; at ~140 captured
// maps a league-wide floor of 8 keeps the table honest without emptying it.
const HERO_WR_MIN=8;
const LB_COLS=[{k:'maps',label:'Maps'},{k:'elo',label:'Elo'},
  {k:'kd',label:'K/D',rate:1},{k:'dmg',label:'Dmg/map',rate:1},
  {k:'heal',label:'Heal/map',rate:1},{k:'mit',label:'Mit/map',rate:1},
  {k:'eff',label:'Eff',rate:1}];
// Stat columns/cells shared by the By-role tables and the leaderboard, so a
// player reads identically in both views. The leading identity columns (rank,
// team, role) differ per view; everything from Maps rightward is one definition.
const EFF_HELP=`Eff compares each player\u2019s per-map stats against the division\u2019s other players in the same role: a z-score (+1 = one standard deviation above the role average), averaged across the stats that vary within that role. Needs ${LB_MIN_GAMES}+ maps and ${EFF_GROUP_MIN}+ same-role peers to show.`;
function statColTh(active){ return LB_COLS.map(c=>`<th class="num" data-k="${c.k}" style="cursor:pointer" title="${c.k==='eff'?esc(EFF_HELP):''}">${esc(c.label)}${c.k===active?' ▾':''}</th>`).join(''); }
function statCells(p){ const s=p.stats;
  return `<td class="num">${p.maps||0}</td>`+
    `<td class="num">${p.elo!=null?p.elo:'<span class="faint">—</span>'}</td>`+
    `<td class="num">${s?s.kd:'<span class="faint">—</span>'}</td>`+
    `<td class="num">${s?nf(s.dmg):'<span class="faint">—</span>'}</td>`+
    `<td class="num">${s?nf(s.heal):'<span class="faint">—</span>'}</td>`+
    `<td class="num">${s?nf(s.mit):'<span class="faint">—</span>'}</td>`+
    `${p.eff&&p.eff.eff!=null?effCell(p):'<td class="num"><span class="faint">—</span></td>'}`; }
// Efficiency cell: the composite z in bold, with the per-component z's on a
// faint line underneath (d/h/m/k = damage, healing, mitigation, K/D; – = that
// stat does not vary within the role, so it is not part of this rating).
function effCell(p){
  const e=p.eff; if(!e||e.eff==null) return null;
  const comp=(k)=>{ const z=e.comps[k]&&e.comps[k].z; return z==null?'–':`${(z>0?'+':'')+z.toFixed(1)}`; };
  return `<td class="num" title="${esc(e.group||'')} role · ${e.groupN} same-role players · ${e.n} maps">`+
    `<b>${(e.eff>0?'+':'')+e.eff.toFixed(1)}</b>`+
    ` <span class="faint" style="font-size:11px">d${comp('dmg')} h${comp('heal')} m${comp('mit')} k${comp('kd')}</span></td>`;
}
let SIM_A=null, SIM_B=null, SIM_FIRST='A';  // draft simulator state
let SCOUT_SIM_OPEN=false;   // one-shot: force the Scout page's beta draft-simulator section open (set by the #sim deep-link redirect in init(), consumed and reset on the next renderScoutBody)
let SIM_TREE={};    // scenario tree: path-of-winners string ('','A','AB'…) -> {map,b1,b2} overrides
let SIM_BO=3;       // wins needed: 2 = Bo3, 3 = Bo5 (default), 4 = Bo7 (playoff)
let SIM_RECENT=0;   // ban window: use each team's most recent N maps for BANS (0 = full season, default — a short window is too sparse to read ban tendencies)
let SIM_OPEN=new Set();   // scenario tree: which branches (child paths) are expanded
let SIM_FOCUS='';         // scenario tree: the one node shown full-size (others condense)
let SIM_OPEN_ALL=false;   // one-shot: #simfull deep link renders the whole tree expanded (consumed on first sim draw)

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

// Team compare shares the scout page's same-division discipline: a team only
// resolves against the division that knows it, so the compare radar never mixes
// elo/ban baselines from two different championships.
function gotoCompare(a,b){
  const names=D().team_names||[];
  if(!names.includes(a)){
    for(const v of VIEWS){
      if(v.divisions.length===1 && (DIVS[v.divisions[0]].team_names||[]).includes(a)){
        CURRENT_VIEW=v.id; recomputeDivision(); updateHeader();
        const dsel=document.getElementById('division'); if(dsel) dsel.value=v.id;
        break;
      }
    }
  }
  COMPARE_A=names.includes(a)?a:null;
  COMPARE_B=names.includes(b)?b:null;
  show('compare');
}

// -----------------------------------------------------------------------------
// Team compare (#compare=A|B): a radar across mixed FACEIT + capture axes, then
// per-team maps/bans/comps/players side-by-side. The pure math (compareAxes,
// radarPoints) lives in pure.js; this is only the DOM.
// -----------------------------------------------------------------------------
// The efficiency pass is identical to the Players tab's: every known player
// z-scored against their same-role cohort, then we keep the qualified ones
// (eff!=null) per team for the Team Eff axis.
function compareRoster(){
  const players=[];
  D().teams.forEach(t=>(t.roster||[]).forEach(p=>{
    players.push({nick:p.nick, team:t.name, role:p.role||'', maps:p.games||0,
      elo:(p.elo==null?null:p.elo), stats:p.stats||null});
  }));
  const effs=efficiencyRatings(players.map(p=>({group:effGroupOf(p),stats:p.stats})));
  players.forEach((p,i)=>{ p.eff=effs[i]; });
  return players;
}
function teamEffSummary(players, team){
  const q=players.filter(p=>p.team===team && p.eff && p.eff.eff!=null);
  return q.length ? {mean: q.reduce((s,p)=>s+p.eff.eff,0)/q.length, n:q.length} : {mean:null, n:0};
}
// Octagon: rings at 25/50/75/100, spokes, axis labels at each vertex, then each
// team's polygon. Null values (no data on an axis) bridge the gap in the polygon.
function compareRadarSvg(rows, av, bv){
  const cx=200, cy=170, r=120, lr=r+18;
  const ring=(p)=>radarPoints(rows.map(()=>p), cx, cy, r)
    .map(pt=>`${pt.x.toFixed(1)},${pt.y.toFixed(1)}`).join(' ');
  const tips=radarPoints(rows.map(()=>100), cx, cy, r);
  let s=`<svg viewBox="0 0 400 390" class="radar" role="img" aria-label="team compare radar">`;
  [25,50,75,100].forEach(p=> s+=`<polygon points="${ring(p)}" class="rring"/>`);
  rows.forEach((_,i)=>{ s+=`<line x1="${cx}" y1="${cy}" x2="${tips[i].x.toFixed(1)}" y2="${tips[i].y.toFixed(1)}" class="rspeak"/>`; });
  // Axis labels at each spoke tip, anchored by angle quadrant.
  rows.forEach((row,i)=>{
    const t=-Math.PI/2+2*Math.PI*i/rows.length;
    const lx=cx+lr*Math.cos(t), ly=cy+lr*Math.sin(t);
    const cos=Math.cos(t);
    const anchor=cos>0.3?'start':cos<-0.3?'end':'middle';
    const dy=Math.sin(t)<-0.3?-4:Math.sin(t)>0.3?12:4;
    s+=`<text x="${lx.toFixed(1)}" y="${(ly+dy).toFixed(1)}" text-anchor="${anchor}" class="rlabel"><title>${esc(AXIS_HELP[row.id]||'')}</title>${esc(row.label)}</text>`;
  });
  const poly=(vals,cls)=>`<polygon points="${radarPoints(vals, cx, cy, r)
    .filter(Boolean).map(pt=>`${pt.x.toFixed(1)},${pt.y.toFixed(1)}`).join(' ')}" class="${cls}"/>`;
  s+=poly(av,'rpoly rpoly-a')+poly(bv,'rpoly rpoly-b');
  // Color legend: two dots with team names, stacked below the octagon (names
  // can be long, so side-by-side risks the labels overlapping).
  const ly1=cy+r+46, ly2=ly1+20;
  s+=`<circle cx="${cx-30}" cy="${ly1}" r="5" fill="var(--accent)"/>`;
  s+=`<text x="${cx-18}" y="${ly1+4}" class="rlabel" text-anchor="start">${esc(COMPARE_A)}</text>`;
  s+=`<circle cx="${cx-30}" cy="${ly2}" r="5" fill="var(--support)"/>`;
  s+=`<text x="${cx-18}" y="${ly2+4}" class="rlabel" text-anchor="start">${esc(COMPARE_B)}</text>`;
  s+=`</svg>`;
  return s;
}
// What each axis actually measures — hover the axis name in the table.
const AXIS_HELP={
  mapwr:'Win rate across every map played this season.',
  pool:'Share of this division’s active map pool the team has played at least once. Most teams reach the top of this one by mid-season — it says they’ve seen the whole pool, not that they’re good on it.',
  banpress:'Bans thrown per game, capped at 2 — how often this team spends a veto instead of leaving the pool open.',
  pick:'Share of games where this team named the map, rather than playing whatever was left after bans.',
  eff:'Team-average Eff: each qualified player’s stats as a z-score against same-role peers this season, then averaged. +1 reads as one standard deviation above the average player in that role.',
  families:'Distinct comp families seen across this team’s captured maps — higher means less predictable drafting.',
  heropool:`Heroes played on at least ${Math.round(HERO_POOL_MIN_PICK*100)}% of this team’s captured rounds — their real, usable pool rather than one-off picks.`,
  swaps:'Confirmed mid-map hero swaps per map, from captured comps — how often this team reacts instead of setting a comp and holding it.',
};
// Honest readout under the SVG: each axis, both team values, dimmed below a
// sample floor. The SVG polygons show the shape; this table says the numbers.
function compareAxisTable(rows){
  const cell=(s)=> s.raw==null
    ? `<span class="faint">—</span>`
    : `<span class="${s.ok?'':'faint'}">${Math.round(s.val)} <span class="faint">(${s.n})</span></span>`;
  return `<table class="table cmpaxis"><tr><th>Axis</th><th class="num side-a">${esc(COMPARE_A)}</th><th class="num side-b">${esc(COMPARE_B)}</th></tr>`+
    rows.map(r=>`<tr><td><span class="axhelp" title="${esc(AXIS_HELP[r.id]||'')}">${esc(r.label)}</span></td><td class="num">${cell(r.a)}</td><td class="num">${cell(r.b)}</td></tr>`).join('')+`</table>`;
}
// One team's half of the side-by-side: maps, bans, comps, players.
function teamCompareCard(team, opp, agg, scout, effSummary, roster){
  const card=el(`<div class="card"></div>`);
  // Build header directly instead of via sectionH — teamAvatar returns HTML
  // that sectionH would escape, turning the <img> into raw visible tags.
  card.appendChild(el(`<div class="section-h"><h2>${teamAvatar(team,24)} ${esc(team)}</h2></div>`));
  const rec=agg.results||[];
  const w=rec.filter(r=>r.won).length;
  card.appendChild(el(`<p class="note" style="margin:2px 0 10px">${rec.length} matches · ${w}–${rec.length-w} `+
    `${effSummary.mean!=null?`· Team Eff ${effSummary.mean>0?'+':''}${effSummary.mean.toFixed(2)} <span class="faint">(${effSummary.n} qualified)</span>`:'<span class="faint">· Team Eff: no qualified players</span>'}</p>`));
  // Maps
  const ms=Object.entries(agg.mapStats||{}).map(([map,v])=>({map, games:v.games, wins:v.wins, picked:v.picks||0}))
    .sort((a,b)=>mapCmp(a.map,b.map));
  card.appendChild(el(`<h4>Maps</h4>`));
  if(ms.length){
    card.appendChild(table(
      [{k:'map',label:'Map'},{k:'games',label:'G',num:1},{k:'wins',label:'W',num:1},{k:'picked',label:'Pick',num:1},
       {k:'wr',label:'WR',num:1,html:r=>wrCell(r.wins,r.games)}],
      ms, byMode));
  } else {
    card.appendChild(el(`<p class="note">No maps played this season.</p>`));
  }
  // Bans — lift vs the shared division baseline: "what they ban MORE than the field."
  card.appendChild(el(`<h4>Bans vs division avg</h4>`));
  card.appendChild(el(banLiftList(banLiftRows(agg.bans, divBanBaseline().all, 2, agg.bansGk, codeLookup(MATCHES_RECENT, team, CODE_WIPE)))));
  // Comps (capture analytics)
  if(scout && scout.scout){
    const s=scout.scout;
    const fams=(s.overall||[]).slice(0,3);
    card.appendChild(el(`<h4>Captured comps <span class="faint">${s.games||0} maps · ${s.rounds||0} rounds</span></h4>`));
    if(fams.length){
      card.appendChild(el(`<div>`+fams.map(f=>`<div class="crow"><span>${compRow(f.heroes)}</span>`+
        `<span class="rec">${wrCell(f.wins,f.wins+f.losses)}${f.samples?` <span class="faint">${f.samples}</span>`:''}</span></div>`).join('')+`</div>`));
    } else {
      card.appendChild(el(`<p class="note">No captured comps for this team.</p>`));
    }
    const hp=(s.hero_pool||[]).filter(h=>(h.pick_rate||0)>=HERO_POOL_MIN_PICK).sort((a,b)=>b.rounds-a.rounds);
    if(hp.length) card.appendChild(el(`<p class="crow"><span>${hp.map(h=>heroIconSmall(h.hero)).join('')}</span>`+
      `<span class="rec">pool ${hp.length}</span></p>`));
  }
  // Players — top by Eff (unrated sorts last, so this reads honestly).
  const mine=roster.filter(p=>p.team===team);
  const top=rankPlayers(mine,{key:'eff'}).slice(0,5);
  card.appendChild(el(`<h4>Top by Eff</h4>`));
  card.appendChild(el(`<div>`+top.map(p=>`<div class="crow"><span>${esc(p.nick)}</span>`+
    `<span class="rec">${p.eff&&p.eff.eff!=null
      ? `${(p.eff.eff>0?'+':'')+p.eff.eff.toFixed(1)} <span class="faint">· ${p.maps}m</span>`
      : `<span class="faint">${p.elo!=null?p.elo+' elo':'no rating'}</span>`}</span></div>`).join('')+`</div>`));
  return card;
}
function renderCompare(){
  const wrap=el(`<div></div>`);
  const back=el(`<a class="backlink" href="#scout">‹ Teams</a>`);
  back.onclick=(e)=>{ e.preventDefault(); show('scout'); };
  wrap.appendChild(back);
  const names=D().team_names||[];
  if(names.length<2){ wrap.appendChild(el(`<p class="note" style="padding:16px">Not enough teams in this division to compare yet.</p>`)); return wrap; }
  if(!COMPARE_A||!names.includes(COMPARE_A)) COMPARE_A=names[0];
  if(!COMPARE_B||!names.includes(COMPARE_B)) COMPARE_B=names.find(n=>n!==COMPARE_A)||names[0];

  const hd=el(`<div class="card compare-hd"></div>`);
  wrap.appendChild(hd);
  const body=el(`<div></div>`);
  wrap.appendChild(body);
  // The header rebuilds with the team state so a swap updates the select
  // options, the perspective toggle labels and the stale-B note together.
  function draw(){
    const b=COMPARE_B||names.find(n=>n!==COMPARE_A)||null;
    const mkSel=(cur,on)=>{
      const s=el(`<select class="cmp-select">${names.map(n=>`<option ${n===cur?'selected':''}>${esc(n)}</option>`).join('')}</select>`);
      s.onchange=()=>on(s.value); return s;
    };
    const selA=mkSel(COMPARE_A, v=>{ COMPARE_A=v; if(COMPARE_B===v)COMPARE_B=names.find(n=>n!==v)||null; draw(); });
    const selB=mkSel(b, v=>{ COMPARE_B=v; if(COMPARE_A===v)COMPARE_A=names.find(n=>n!==v)||null; draw(); });
    const swapBtn=el(`<button class="btn" type="button" style="padding:4px 10px" title="Swap the two teams">⇄</button>`);
    swapBtn.onclick=()=>{ const t=COMPARE_A; COMPARE_A=COMPARE_B; COMPARE_B=t; draw(); };
    const side=(name, dotVar, sel)=>{
      const av=teamAvatar(name,44);
      const d=el(`<div class="cmp-side"></div>`);
      if(av) d.appendChild(el(`<div class="cmp-avatar">${av}</div>`));
      d.appendChild(el(`<div class="cmp-name"><span class="cmp-dot" style="background:var(${dotVar})"></span><b>${esc(name)}</b></div>`));
      d.appendChild(sel);
      return d;
    };
    const mid=el(`<div class="cmp-vs-mid"><span class="cmp-vs-label">VS</span></div>`);
    mid.appendChild(swapBtn);
    const row=el(`<div class="cmp-vs-row"></div>`);
    row.append(side(COMPARE_A,'--accent',selA), mid, side(b||'—','--support',selB));
    hd.replaceChildren(row);
    const note=b&&!names.includes(b)
      ? el(`<p class="note" style="padding:0 4px 10px;text-align:center">${esc(b)} isn't in this division — only same-division comparisons are shown.</p>`)
      : null;
    if(note) hd.appendChild(note);
    if(!b){ body.innerHTML=''; return; }
    const roster=compareRoster();
    const aggA=aggregate(D().matches, COMPARE_A), aggB=aggregate(D().matches, b);
    const scoutA=(DATA.owdb_comps||{})[COMPARE_A]||null, scoutB=(DATA.owdb_comps||{})[b]||null;
    const effA=teamEffSummary(roster, COMPARE_A), effB=teamEffSummary(roster, b);
    // Real active map count for this division, not the axis's fallback cap —
    // most seasons run well past 10 maps, which otherwise saturates every team.
    const poolCap=new Set(D().matches.flatMap(m=>(m.games||[]).map(g=>g.map).filter(Boolean))).size;
    const rows=compareAxes(aggA, aggB, scoutA, scoutB, effA, effB, poolCap);
    // Radar card: axis table on the left, SVG + legend on the right.
    const radar=el(`<div class="card"></div>`);
    radar.appendChild(el(sectionH('Radar', `<span class="note">fixed caps — a strong league reads near the edge, a weak one near the middle</span>`)));
    const radarInner=el(`<div class="compare-radar-row"></div>`);
    const radarTable=el(`<div class="compare-radar-table">${compareAxisTable(rows)}</div>`);
    const radarSvg=el(`<div class="compare-radar-svg">${compareRadarSvg(rows, rows.map(r=>r.a.val), rows.map(r=>r.b.val))}</div>`);
    radarInner.append(radarTable, radarSvg);
    radar.appendChild(radarInner);
    const grid=el(`<div class="grid cols-2 compare-grid"></div>`);
    const cardA=teamCompareCard(COMPARE_A, b, aggA, scoutA, effA, roster); cardA.classList.add('side-a');
    const cardB=teamCompareCard(b, COMPARE_A, aggB, scoutB, effB, roster); cardB.classList.add('side-b');
    grid.append(cardA, cardB);
    // Head to head: matches where these two faced each other.
    const h2h=D().matches.filter(m=>(m.f1===COMPARE_A&&m.f2===b)||(m.f1===b&&m.f2===COMPARE_A));
    const h2=el(`<div class="card"></div>`);
    h2.appendChild(el(sectionH('Head to head', `<span class="note">${h2h.length} meeting${h2h.length===1?'':'s'} this season</span>`)));
    if(h2h.length){
      h2.appendChild(el(`<div>`+h2h.map(m=>{
        return `<div class="crow"><span>${dshort(m.finished_at)} · <b>${esc(m.f1)}</b> <span class="score">${esc(m.series)}</span> <b>${esc(m.f2)}</b>`+
          ` <span class="faint">${esc(m.winner_team)} won</span></span><span class="rec"><span class="tlink" data-match="${esc(m.id)}" style="cursor:pointer">details →</span></span></div>`;
      }).join('')+`</div>`));
    } else {
      h2.appendChild(el(`<p class="note">These two haven't met in ${esc(D().summary.championship||'this division')} this season.</p>`));
    }
    body.replaceChildren(radar, grid, h2);
  }
  draw();
  return wrap;
}

// A match id is only unique within its own division (see divisionOfMatch),
// so findMatch assumes CURRENT_VIEW is already correct — true by the time
// it's called, since openMatch/init's match= branch always resolves the
// division first. Playoff bracket matches live alongside the regular-season
// list (same division), so both are searched.
function findMatch(matchId){ return (D().matches||[]).find(m=>m.id===matchId)||(D().playoffs||[]).find(m=>m.id===matchId)||null; }
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

  // Capture funnel — teams in this view nobody has scouted yet. Aggressive by
  // design: their comp/bans/hero-pool panels are blank until someone captures a
  // game, so the callout names them and hands over a concrete one-minute task.
  // Only teams with a live replay actually available are listed — a team that
  // never played, or whose only codes were wiped before capture, has nothing a
  // scout could run.
  const capturable=capturableTeams((D().matches||[]).concat(D().playoffs||[]), CAPTURED, CODE_WIPE);
  const cap=zeroCaptureTeams(tn, ocs).filter(n=>capturable.has(n));
  const capCount=tn.filter(n=>capturable.has(n)).length;
  if(cap.length){
    const zcd=el(`<div class="card mt20 funnel"></div>`);
    zcd.appendChild(el(`<p class="eyebrow">Capture funnel · ${cap.length} of ${capCount} teams here have zero captures</p>`));
    zcd.appendChild(el(`<p class="note" style="margin:0 0 6px">These teams have live replays waiting right now but no captured comps yet — their scouting panels stay blank until a scout runs one. About a minute per map, and a capture outlives the next code wipe.</p>`));
    const zrow=el(`<div class="crowgrid" style="margin-bottom:10px"></div>`);
    cap.slice(0,8).forEach(n=>zrow.appendChild(el(`<div class="crow"><span class="chip tlink" data-scout="${esc(n)}" title="Scout ${esc(n)}">${esc(n)}${capBtn(n)}</span></div>`)));
    if(cap.length>8) zrow.appendChild(el(`<div class="crow"><span class="note" style="margin:0">…and ${cap.length-8} more.</span></div>`));
    zcd.appendChild(zrow);
    // Point at a live code involving one of these teams when one exists; the
    // funnel then hands over an exact replay instead of a generic call to action.
    const zt=leagueQueue().find(r=>cap.includes(r.f1)||cap.includes(r.f2));
    zcd.appendChild(el(zt
      ? `<a class="btn" href="${captureCodeUrl(zt.code)}" title="Open a live replay of ${esc(zt.f1)} vs ${esc(zt.f2)} on ${esc(zt.map)} in the capture tool" style="text-decoration:none;padding:4px 12px;font-size:12.5px;white-space:nowrap">Scout a zero-capture team's live replay →</a>`
      : `<a class="btn" href="capture/" title="Open the capture tool" style="text-decoration:none;padding:4px 12px;font-size:12.5px;white-space:nowrap">Open the capture tool →</a>`));
    wrap.appendChild(zcd);
  }

  // Most wanted — the live replay codes no one has captured yet, newest first.
  // A concrete one-minute task for a cold visitor, with the leaderboard below as
  // proof it's a real community effort. Hidden when nothing is scoutable.
  const qq=leagueQueue();
  if(qq.length){
    const mw=el(`<div class="card mt20"></div>`);
    mw.appendChild(el(`<p class="eyebrow">Most wanted · ${qq.length} live replay code${qq.length===1?'':'s'} waiting</p>`));
    mw.appendChild(el(`<p class="note" style="margin:0 0 6px">Each code stops working at the next patch${CODE_WIPE?` (last wipe: <b>${esc(CODE_WIPE)}</b>)`:''}, so a capture is a one-time window — about a minute per map in the capture tool.</p>`));
    qq.slice(0,5).forEach(r=>{
      const row=el(`<div class="crow"></div>`);
      row.appendChild(el(`<span style="min-width:0;flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap"><b>${esc(r.f1)}</b> <span class="faint">vs</span> <b>${esc(r.f2)}</b> <span class="faint">· ${esc(r.map)} · ${dshort(r.when)}</span>${r.div?` <span class="faint">· ${esc(r.div)}</span>`:''}</span>`));
      row.appendChild(el(`<span class="rec"><a class="btn" href="${captureCodeUrl(r.code)}" title="Open this replay in the capture tool" style="text-decoration:none;padding:3px 10px;font-size:12px;white-space:nowrap">Scout ${esc(r.code)} →</a></span>`));
      mw.appendChild(row);
    });
    if(qq.length>5) mw.appendChild(el(`<p class="note" style="margin-top:6px">…and ${qq.length-5} more. <a href="capture/" style="color:var(--accent);font-weight:600;text-decoration:none">Open the capture tool →</a></p>`));
    wrap.appendChild(mw);
  }

  // Capture recommendations — the strategic sibling of "Most wanted". That card
  // lists fresh codes; this one says which MAPS are under-covered relative to
  // how much they're played, so a scout works the maps that most need data.
  // Playtime is an estimate (games × typical mode length); a map is listed
  // until at least half its league play is captured and it still has a live
  // code left to capture. Finished playoff games count as league play here too
  // (the same union the queue uses) — a live playoff code is the freshest
  // capture target on the site.
  const recs=mapCoverage((D().matches||[]).concat(D().playoffs||[]), CAPTURED, CODE_WIPE);
  if(recs.length){
    const rc=el(`<div class="card mt20"></div>`);
    rc.appendChild(el(`<p class="eyebrow">Capture recommendations · ${recs.length} map${recs.length===1?'':'s'} under-covered</p>`));
    rc.appendChild(el(`<p class="note" style="margin:0 0 6px">Coverage of each map's league play. Playtime is an <b>estimate</b> (games × typical game length for the mode). The more a map is played, the more captures it needs to read reliably — capture until at least half its play is covered.</p>`));
    recs.slice(0,8).forEach(r=>{
      const row=el(`<div class="crow"></div>`);
      row.appendChild(el(`<span style="min-width:0;flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap"><b>${esc(r.map)}</b> <span class="faint">${esc(r.mode||'')}</span> <span class="faint">· ${r.captured}/${r.played} captured (${r.pct}%) · ~${nf(r.unseenMin)} min unseen</span></span>`));
      row.appendChild(el(`<span style="flex:none"><span class="track" style="display:inline-block;width:110px;height:7px;vertical-align:middle"><span class="fill" style="display:block;width:${Math.min(100,r.pct)}%;background:${r.pct>=50?'var(--good)':'var(--mid)'}"></span></span></span>`));
      row.appendChild(el(`<span class="rec"><a class="btn" href="${captureCodeUrl(r.liveCode)}" title="Open a live replay on ${esc(r.map)} in the capture tool" style="text-decoration:none;padding:3px 10px;font-size:12px;white-space:nowrap">Scout →</a></span>`));
      rc.appendChild(row);
    });
    if(recs.length>8) rc.appendChild(el(`<p class="note" style="margin-top:6px">…and ${recs.length-8} more map${recs.length-8===1?'':'s'} under-covered.</p>`));
    wrap.appendChild(rc);
  }

  wrap.appendChild(el(sectionH('Standings')));
  wrap.appendChild(table(
    [{k:'name',label:'Team',html:r=>teamLink(r.name)},{k:'matches',label:'Matches',num:true},
     {k:'wins',label:'Wins',num:true},{k:'win_pct',label:'Match %',num:true,html:r=>pill(r.win_pct+'%',winVar(r.win_pct))},
     {k:'games',label:'Maps',num:true},{k:'game_wins',label:'Map wins',num:true},
     {k:'map_win_pct',label:'Map %',num:true,html:r=>pill(r.map_win_pct+'%',winVar(r.map_win_pct))}],
    D().teams));
  wrap.appendChild(el(`<p class="note">Veto attribution recovered from FACEIT's durable history feed for ${s.matches_with_attribution}/${s.matches} matches; only walkovers and disrupted vetos lack it.</p>`));

  // Power Rankings — a from-scratch Elo-style rating built from stored match
  // results (distinct from FACEIT's own per-player elo_snapshot). Series
  // rating orders the table since that's what the league itself decides
  // standings by; Map form is a faster-reacting secondary column, never the
  // sort key. Regular season only, same scope as Standings above.
  const pr = powerRankings(D().matches);
  if (pr.length) {
    wrap.appendChild(el(sectionH('Power Rankings')));
    wrap.appendChild(table(
      [{k: 'rank', label: '#', num: true,
        html: r => `<span class="${r.provisional ? 'faint' : ''}">${r.rank}</span>`},
       {k: 'name', label: 'Team', html: r => teamLink(r.name)},
       {k: 'rating', label: 'Rating', num: true,
        html: r => `<span class="${r.provisional ? 'faint' : ''}">${r.rating}</span>`},
       {k: 'mapRating', label: 'Map form', num: true},
       {k: 'history', label: 'Trend',
        html: r => `<svg viewBox="0 0 60 20" class="spark" width="60" height="20">` +
          `<polyline points="${sparklinePoints(r.history, 60, 20)}" fill="none" ` +
          `stroke="var(--accent)" stroke-width="2"/></svg>`},
       {k: 'n', label: 'n', num: true,
        html: r => r.provisional
          ? `${r.n} <span class="faint" title="Fewer than ${POWER_MIN_N} matches — rating is still settling">*</span>`
          : String(r.n)}],
      pr.map((r, i) => ({...r, rank: i + 1}))));
    const combinedCaveat = viewOf(CURRENT_VIEW).divisions.length > 1
      ? ' This is a combined view spanning multiple tiers that never play each other — ratings are only meaningfully comparable within a tier.'
      : '';
    wrap.appendChild(el(`<p class="note">Power Rankings is an Elo-style rating built from match results (not FACEIT's own per-player elo) — every finished match moves a team's Rating by up to K=${SERIES_ELO_K} based on the result and the opponent's strength, and every map moves a separate Map form rating (K=${MAP_ELO_K}), which reacts faster since there are more maps than matches. A forfeited or defaulted match still counts toward Rating, same as any other result, but never toward Map form since no maps were actually played. Trend plots Rating after each match, oldest to newest. Rows marked * have played fewer than ${POWER_MIN_N} matches and are still settling.${combinedCaveat}</p>`));
  }

  // Scout leaderboard — maps each contributor owns (first-wins credited). League-wide.
  const contribs=DATA.owdb_contributors||[];
  const meName=((localStorage.getItem('owdb_name')||'').trim()||'').toLowerCase();
  const meIdx=meName?contribs.findIndex(c=>String(c.name||'').toLowerCase()===meName):-1;

  // Personalised contributor impact card — the scout's own profile, shown when
  // their browser name matches a contributor. A clear reward signal that makes
  // the capture-leaderboard loop tangible for a returning contributor.
  if(meIdx>=0 && contribs.length){
    const me=contribs[meIdx];
    const rankStr=meIdx===0?'🥇':meIdx===1?'🥈':meIdx===2?'🥉':'#'+(meIdx+1);
    const pct=CAPTURED.size?Math.round(100*me.maps/CAPTURED.size):0;
    const ci=el(`<div class="card mt20 profcard"></div>`);
    ci.appendChild(el(`<div class="profile">
      <span class="prank">${rankStr}</span>
      <div class="pinfo">
        <span class="pname">${esc(me.name)}</span>
        <span class="pstat">Rank ${meIdx+1} of ${contribs.length} scouts · <b>${nf(me.maps)}</b> maps contributed${pct>0?` · ${pct}% of captured maps`:''}</span>
      </div>
      <div class="pcta">
        <a class="btn" href="capture/">Capture another →</a>
      </div>
    </div>`));
    wrap.appendChild(ci);
  }

  if(contribs.length){
    const lc=el(`<div class="card mt20"></div>`);
    lc.appendChild(el(`<p class="eyebrow">Scout leaderboard</p>`));
    lc.appendChild(el(`<p class="note" style="margin:0 0 8px">Maps each scout has contributed this season — every capture sharpens the data here. 🙏</p>`));
    lc.appendChild(el(barList(contribs.slice(0,15).map((c,i)=>{
      const nm=String(c.name||'');
      const medals=['🥇','🥈','🥉'];
      const medal=i<3?`<span class="medal">${medals[i]}</span>`:'';
      const you=!!meName && nm.toLowerCase()===meName;
      return {label:`${medal}${you?`<span class="you">${esc(nm)}</span>`:esc(nm)}`,value:c.maps,you};
    }))));
    const total=contribs.reduce((x,c)=>x+(c.maps||0),0);
    lc.appendChild(el(`<p class="note" style="margin-top:8px">${contribs.length} scout${contribs.length===1?'':'s'} · ${nf(total)} maps captured league-wide.</p>`));
    wrap.appendChild(lc);
  }

  return wrap;
}

function scoutData(team,lim){
  const mine=MATCHES_RECENT.filter(m=>m.f1===team||m.f2===team);
  const used=recent(mine,lim), a=aggregate(used,team), {from,to}=dateRange(used);
  return {team,used:used.length,total:mine.length,from,to,matches:used,...a};
}

const teamTotalMatches=(team)=> MATCHES_RECENT.filter(m=>m.f1===team||m.f2===team).length;


/* ================================= PREP SHEET (the night-before one-pager) */
// Everything a team decides before a match, on one screen: what to ban, what
// they'll ban, where the map draft goes, and what comp walks out of spawn.
// Deliberately terse - the full scout page is one click away.
function renderPrepBody(t){
  const w=el(`<div></div>`);
  const wins=t.results.filter(r=>r.won).length;
  const oc=(DATA.owdb_comps||{})[t.team], sc=oc&&oc.scout;
  const ad=sc&&sc.adapt;
  w.appendChild(el(`<div class="card" style="display:flex;gap:14px;flex-wrap:wrap;align-items:baseline">`+
    `<span style="font-size:18px;font-weight:680">${esc(t.team)} - prep sheet</span>`+
    `<span>${pill(`${wins}/${t.results.length} matches`,winVar(pctOf(wins,t.results.length)))} `+
    `${pill(`${t.gwins}/${t.games} maps`,winVar(pctOf(t.gwins,t.games)))}</span>`+
    (ad?`<span class="note" style="margin:0">${ad.swaps_per_map} swaps/map · ${ad.families} famil${ad.families===1?'y':'ies'}`+
        (ad.loss_followups?` · changed comp after a loss ${ad.changed_after_loss}/${ad.loss_followups}`:'')+`</span>`:'')
    +`</div>`));

  const grid=el(`<div class="grid cols-2 mt10" style="align-items:start"></div>`);

  // What to take away from THEM: their most-relied-on heroes.
  const banC=el(`<div class="card"></div>`);
  banC.appendChild(el(`<p class="eyebrow">Ban candidates - what they rely on</p>`));
  const pool=(sc&&sc.hero_pool||[]).slice(0,5);
  if(pool.length){
    pool.forEach(h=>banC.appendChild(el(`<div class="crow"><span>${heroChip(h.hero)}</span>`+
      `<span class="rec">${Math.round((h.pick_rate||0)*100)}% of rounds</span></div>`)));
  } else {
    banC.appendChild(el(`<p class="note">No captured comps yet - see their bans below for hints.</p>`));
  }
  grid.appendChild(banC);

  // What YOU will likely lose: their ban habits.
  const theirC=el(`<div class="card"></div>`);
  theirC.appendChild(el(`<p class="eyebrow">Expect them to ban</p>`));
  rank(t.bans).slice(0,4).forEach(([h,n])=>theirC.appendChild(
    el(`<div class="crow"><span>${heroChip(h)}</span><span class="rec">${n}x</span></div>`)));
  if(t.firstBanGames){
    theirC.appendChild(el(`<p class="eyebrow" style="margin-top:10px">Their first ban (drafting first)</p>`));
    rank(t.firstBans).slice(0,2).forEach(([h,n])=>theirC.appendChild(
      el(`<div class="crow"><span>${heroChip(h)}</span><span class="rec">${n}x</span></div>`)));
  }
  grid.appendChild(theirC);

  // Map draft: what they'll bring, and where they're weak.
  const pick=el(`<div class="card"></div>`);
  pick.appendChild(el(`<p class="eyebrow">Expect them to pick</p>`));
  Object.entries(t.mapStats).filter(([,v])=>v.picks>0)
    .map(([m,v])=>({m,p:v.picks,wr:pctOf(v.wins,v.games)}))
    .sort((a,b)=>b.p-a.p).slice(0,4)
    .forEach(r=>pick.appendChild(el(`<div class="crow"><span>${esc(r.m)} <span class="faint">${esc(MAP_CAT[r.m]||'')}</span></span>`+
      `<span class="rec">${r.p}x · ${pill(r.wr+'%',winVar(r.wr))}</span></div>`)));
  grid.appendChild(pick);

  const weak=el(`<div class="card"></div>`);
  const ws=worstMaps(t.mapStats);
  weak.appendChild(el(`<p class="eyebrow">Target these maps - their worst`+
    (ws.baseline!=null?` <span class="note">vs their ${ws.baseline}% overall</span>`:'')+`</p>`));
  if(!ws.rows.length){
    // A dominant (or too-thin) record has no weak map. Saying so beats handing
    // the coach four maps the opponent has never lost on.
    weak.appendChild(el(ws.baseline==null
      ? `<p class="note">Not enough games per map yet <span class="faint">(needs ${WORST_MIN_GAMES}+ on a map)</span>.</p>`
      : `<p class="note">No clear weak map - they hold ${ws.baseline}% across their pool. Draft to your own strengths instead.</p>`));
  }
  ws.rows.forEach(r=>weak.appendChild(el(`<div class="crow"><span>${esc(r.m)} <span class="faint">${esc(MAP_CAT[r.m]||'')}</span></span>`+
    `<span class="rec">${r.g} games · ${pill(r.wr+'%',winVar(r.wr))}</span></div>`)));
  grid.appendChild(weak);
  w.appendChild(grid);

  // What walks out of spawn, and how bans move it.
  if(sc){
    const comps=(sc.overall||[]).slice(0,2);
    if(comps.length){
      w.appendChild(el(sectionH('Their comps',`<span class="note">${sc.games} map${sc.games===1?'':'s'} captured</span>`)));
      const card=el(`<div class="card"></div>`);
      comps.forEach(c=>card.appendChild(el(`<div class="crow"><span>${compRow(c.heroes)}</span>`+
        `<span class="rec">${c.maps} map${c.maps===1?'':'s'} · ${c.wins}W-${c.losses}L</span></div>`)));
      w.appendChild(card);
    }
    const br=(sc.ban_response||[]).slice(0,2);
    if(br.length){
      const card=el(`<div class="card mt10"></div>`);
      card.appendChild(el(`<p class="eyebrow">If a key hero is banned</p>`));
      br.forEach(b=>{
        const open=(b.opens||[])[0];
        if(open) card.appendChild(el(`<div class="crow"><span><b>${esc(b.banned)}</b> banned &rarr; ${compRow(open.heroes)}</span>`+
          `<span class="rec">${b.games} game${b.games===1?'':'s'}</span></div>`));
      });
      w.appendChild(card);
    }
  }
  return w;
}

function renderScout(){
  const wrap=el(`<div></div>`);
  const bar=el(`<div class="card controls"></div>`);
  // "Team", not "Opponent": the same sheet read about your own side is a
  // self-scout - what you are predictable on, and what an opponent prepping you
  // is looking at right now. Only the label ever stopped that being obvious.
  bar.appendChild(el(`<label>Team</label>`));
  const sel=el(`<select style="min-width:190px"></select>`);
  D().team_names.forEach(n=>sel.appendChild(el(`<option ${n===SCOUT_TEAM?'selected':''}>${esc(n)}</option>`)));
  bar.appendChild(sel);
  bar.appendChild(el(`<span class="note" style="margin:0">opponent — or your own team, to see what they see</span>`));
  bar.appendChild(el(`<label>Recent matches</label>`));
  const holder=el(`<span style="display:inline-flex"></span>`);
  bar.appendChild(holder);
  const prepBtn=el(`<button class="btn" type="button" style="margin-left:auto;padding:4px 12px"></button>`);
  bar.appendChild(prepBtn);
  const cmpBtn=el(`<button class="btn" type="button" style="padding:4px 12px" title="Two-team radar across maps, bans, eff and capture analytics">Compare…</button>`);
  bar.appendChild(cmpBtn);
  const body=el(`<div></div>`);
  wrap.append(bar,body);

  function renderBody(){
    prepBtn.textContent=SCOUT_PREP?'Full detail':'Prep sheet';
    body.innerHTML='';
    const data=scoutData(SCOUT_TEAM, SCOUT_N);
    body.appendChild(SCOUT_PREP?renderPrepBody(data):renderScoutBody(data));
  }
  prepBtn.onclick=()=>{ SCOUT_PREP=!SCOUT_PREP; location.hash=hashFor('scout'); renderBody(); };
  cmpBtn.onclick=()=>{
    const other=D().team_names.find(n=>n!==SCOUT_TEAM)||null;
    if(other) gotoCompare(SCOUT_TEAM, other);
  };
  function rebuild(){                       // per-team total → rebuild the control
    const total=Math.max(1,teamTotalMatches(SCOUT_TEAM));
    const smax=Math.max(15,total);          // let the window reach a full season
    if(SCOUT_N!=null && SCOUT_N>smax) SCOUT_N=null;
    holder.replaceChildren(makeRecency(total, SCOUT_N==null?smax:SCOUT_N, n=>{ SCOUT_N=n; renderBody(); }, smax));
    renderBody();
  }
  sel.onchange=()=>{ SCOUT_TEAM=sel.value; SCOUT_N=null;
    location.hash=hashFor('scout'); rebuild(); };
  rebuild(); return wrap;
}

function renderScoutBody(t){
  // Layout: a full-width top band (header, glance, coverage) over a two-column
  // body — the deep analysis in `w` (main column), the match receipts in a
  // sticky rail. `w` stays the analysis container so that body is untouched.
  const root=el(`<div></div>`);
  const w=el(`<div class="scout-main"></div>`);
  const side=el(`<div class="scout-side"></div>`);
  // Resolves every gk-tracked evidence row in this function to its replay
  // code(s); built from MATCHES_RECENT (unwindowed), not t.matches, so it
  // also covers Counter-scout's matchups below, which come from a separate,
  // unwindowed owdb source (see the design doc). Declared here, at the
  // top of the function, because Counter-scout (which needs it) renders
  // before the aggregated evidence tables do, and const isn't hoisted.
  // CODE_WIPE marks pre-wipe entries `dead` so codesCell/the popover can
  // label them "code wiped" instead of offering a copy chip that won't load.
  const lookup=codeLookup(MATCHES_RECENT, t.team, CODE_WIPE);
  const matchW=t.results.filter(r=>r.won).length;
  const form=t.results.slice(0,7).map(r=>`<b class="${r.won?'w':'l'}" title="${esc(r.opp)} ${esc(r.series)}">${r.won?'W':'L'}</b>`).join('');
  const head=el(`<div class="card" style="display:flex;gap:18px;flex-wrap:wrap;align-items:center;justify-content:space-between"></div>`);
  const _tav=teamAvatar(t.team,56);
  head.appendChild(el(`<div style="display:flex;align-items:center;gap:14px">${_tav?`<div style="display:flex;align-items:center;justify-content:center;width:64px;height:64px">${_tav}</div>`:''}`+
    `<div><div style="font-size:18px;font-weight:680">${esc(t.team)}</div>`+
    `<div class="note" style="margin-top:2px">${t.used<t.total?`last ${t.used} of ${t.total} matches`:`all ${t.total} matches`} · ${dshort(t.from)} → ${dshort(t.to)}</div></div></div>`));
  const _hsc=((DATA.owdb_comps||{})[t.team]||{}).scout, capMaps=(_hsc&&_hsc.games)||0;
  // Coverage is all-time (captures aren't windowed), so its denominator must be
  // all-time maps played too - windowing it (t.games) could show capMaps > total.
  const _allMaps=MATCHES_RECENT.filter(m=>m.f1===t.team||m.f2===t.team)
    .reduce((s,m)=>s+m.games.filter(g=>g.map).length,0);
  head.appendChild(el(`<div style="text-align:right"><div><span title="matches won / played">${pill(`${matchW}/${t.results.length} matches`,winVar(pctOf(matchW,t.results.length)))}</span> <span title="maps won / played">${pill(`${t.gwins}/${t.games} maps`,winVar(pctOf(t.gwins,t.games)))}</span> <span title="maps with captured comps (scouted)">${pill(`${capMaps}/${_allMaps} scouted`,capMaps?'var(--accent)':'var(--faint)')}</span></div>`+
    `<div class="wl" style="margin-top:6px;justify-content:flex-end">${form||'<span class="faint">no maps</span>'}</div></div>`));
  root.appendChild(head);

  // Current roster tile: who you're actually scouting. Current lineup (played
  // the latest match) first, subs / departed dimmed below. From FACEIT round_players.
  {
    const ros=((D().teams.find(x=>x.name===t.team)||{}).roster)||[];
    const cur=ros.filter(p=>p.current), sub=ros.filter(p=>!p.current);
    // Most-played hero per player, from the same HUD-attributed pools "Player
    // pools" below uses (scout.players[].heroes is share-sorted, so [0] is it).
    const topHeroByPlayer={};
    (((DATA.owdb_comps||{})[t.team]||{}).scout||{}).players?.forEach(p=>{
      if(p.heroes&&p.heroes[0]) topHeroByPlayer[p.player]=p.heroes[0].hero; });
    const prow=(p,dim)=>{
      const th=topHeroByPlayer[p.nick];
      const av=faceitAvg(p), role=roleOf(p.role);
      return `<div class="seatrow" style="grid-template-columns:1fr 40px auto${dim?';opacity:.5':''}" title="${p.games} maps this season${av?' · '+av.games+' maps with stats':''}">`+
      `<span class="nm"><b>${esc(p.nick)}</b><span class="tm">${esc(role||'—')}${p.elo!=null?` · ${p.elo} elo`:''}</span></span>`+
      `<span class="hs">${th?heroIconMedium(th):''}</span>`+
      `<span class="rec">${p.games} map${p.games===1?'':'s'}${av?` · ${av.games}m`:` ${p.stats?'<span class="faint"> · '+p.stats.kd+' k/d</span>':''}`}</span></div>`; };
    const rc=el(`<div class="card roster"></div>`);
    rc.appendChild(el(`<p class="eyebrow">Current roster</p>`));
    if(ros.length){
      const grid=el(`<div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(260px,1fr));gap:0 16px"></div>`);
      cur.forEach(p=>grid.appendChild(el(prow(p,false))));
      if(sub.length){
        grid.appendChild(el(`<div class="subhd" style="grid-column:1/-1">also played this season</div>`));
        sub.forEach(p=>grid.appendChild(el(prow(p,true))));
      }
      rc.appendChild(grid);
    } else rc.appendChild(el(`<p class="note" style="margin:2px 0 0">No roster data yet.</p>`));
    root.appendChild(rc);
  }

  // ---- At a glance: the prep headline before any scrolling. Four panels —
  // go-to comps, their bans, map pool, form/tempo. Degrades to the FACEIT-derived
  // bans/maps when no comps have been captured for this team yet.
  {
    const scoutG=((DATA.owdb_comps||{})[t.team]||{}).scout;
    const g=el(`<div class="card glance"></div>`);
    g.appendChild(el(`<p class="eyebrow">At a glance</p>`));
    const cols=el(`<div class="glance-grid"></div>`);

    const c1=el(`<div class="glance-col"></div>`);
    c1.appendChild(el(`<p class="eyebrow">Go-to comps</p>`));
    const tops=((scoutG&&scoutG.overall)||[]).slice(0,2);
    if(tops.length) tops.forEach(c=>c1.appendChild(el(
      `<div class="crow${c.maps<=1?' thin':''}"><span>${compRow(c.heroes)}</span>`+
      `<span class="rec">${c.maps>=3?`${c.wins}W-${c.losses}L`:`${c.maps} map${c.maps===1?'':'s'}`}</span></div>`)));
    else c1.appendChild(el(`<p class="note" style="margin:2px 0 0">No comps captured yet.</p>`));
    cols.appendChild(c1);

    const c2=el(`<div class="glance-col"></div>`);
    c2.appendChild(el(`<p class="eyebrow">Their bans</p>`));
    // Recount from the drafts so the opening ban + field comparison line up with
    // the shown counts (these two reads were folded in from the old Tendencies card).
    const tBan={}, tBanWin={}, tFirst={}; let tBanTot=0, tFirstG=0;
    t.matches.forEach(m=>{ const side=m.f1===t.team?'faction1':(m.f2===t.team?'faction2':null);
      m.games.forEach(gm=>{ if(!gm.map) return; const won=!!(side&&gm.winner_faction===side);
      const mine=(gm.bans||[]).filter(b=>b.hero&&b.team===t.team).sort((a,b)=>(a.order||9)-(b.order||9));
      if(mine.length){ inc(tFirst,mine[0].hero); tFirstG++; }
      mine.forEach(b=>{ inc(tBan,b.hero); tBanTot++;
        const w=tBanWin[b.hero]||(tBanWin[b.hero]={games:0,wins:0}); w.games++; if(won)w.wins++; }); }); });
    const fBan={}; let fBanTot=0;
    D().matches.forEach(m=>m.games.forEach(gm=>{ if(!gm.map) return;
      (gm.bans||[]).forEach(b=>{ if(b.hero){ inc(fBan,b.hero); fBanTot++; } }); }));
    const feb=rank(tFirst)[0], opener=(feb&&tFirstG>=3&&feb[1]>=2)?feb[0]:null;
    let tb=rank(tBan).slice(0,4);
    if(opener && !tb.some(([h])=>h===opener)) tb=[[opener,tBan[opener]||0],...tb].slice(0,4);
    if(tb.length) tb.forEach(([h,n])=>{
      const ts=tBanTot?n/tBanTot:0, fs=fBanTot?(fBan[h]||0)/fBanTot:0;
      const over=n>=2 && ts>=fs*1.6 && (ts-fs)>=0.05;   // a real team-specific tell, not the meta
      const w=tBanWin[h]||{games:0,wins:0};
      c2.appendChild(el(`<div class="crow"><span>${heroChip(h)}${opener===h?` <span class="opener" title="their most common first ban">1st ban</span>`:''}</span>`+
        `<span class="rec"><span title="banned ${n} time${n===1?'':'s'} in this window">${n}x</span>`+
        ` · <span class="faint" title="how often the league bans ${esc(h)}, for comparison">league ${Math.round(fs*100)}%</span>`+
        ` · <span title="their win rate in games where they banned ${esc(h)}">won ${wrCell(w.wins,w.games)}</span>`+
        `${over?`<span class="bvs" title="A ban that's distinctive to ${esc(t.team)} — they ban it in ${Math.round(ts*100)}% of their games, vs ${Math.round(fs*100)}% for most teams">signature</span>`:''}</span></div>`));
    });
    else c2.appendChild(el(`<p class="note" style="margin:2px 0 0">No bans in window.</p>`));
    cols.appendChild(c2);

    const c3=el(`<div class="glance-col"></div>`);
    c3.appendChild(el(`<p class="eyebrow">Map pool</p>`));
    const mp=Object.entries(t.mapStats).filter(([,v])=>v.picks>0)
      .map(([m,v])=>({m,picks:v.picks,wins:v.wins,games:v.games}))
      .sort((a,b)=>b.picks-a.picks).slice(0,4);
    if(mp.length) mp.forEach(r=>c3.appendChild(el(
      `<div class="crow"><span>${esc(r.m)} <span class="faint">${esc(MAP_CAT[r.m]||'')}</span></span>`+
      `<span class="rec">${r.games} played · ${r.picks}x picked · <span title="their win rate on ${esc(r.m)}">won ${wrCell(r.wins,r.games)}</span></span></div>`)));
    else c3.appendChild(el(`<p class="note" style="margin:2px 0 0">No picked maps in window.</p>`));
    cols.appendChild(c3);

    const c4=el(`<div class="glance-col"></div>`);
    c4.appendChild(el(`<p class="eyebrow">Form &amp; tempo</p>`));
    c4.appendChild(el(`<div class="wl" style="margin:2px 0 7px">${form||'<span class="faint">no maps</span>'}</div>`));
    if(scoutG&&scoutG.adapt){
      const ad=scoutG.adapt;
      const bits=[`<b>${ad.swaps_per_map}</b> hero swaps mid-map`,
                  `<b>${ad.families}</b> different comp${ad.families===1?'':'s'}`];
      if(ad.loss_followups>0) bits.push(`reworked their comp after <b>${ad.changed_after_loss}</b> of <b>${ad.loss_followups}</b> losses`);
      c4.appendChild(el(`<p class="note" style="margin:0;font-size:12.5px">${bits.join(' · ')}</p>`));
      c4.appendChild(el(`<p class="note" style="margin:4px 0 0;font-size:11.5px">${ad.families<=2?'<b>Predictable</b> — runs the same few comps, easy to prep for.':'<b>Varied</b> — mixes comps, so be ready to adapt in-game.'}</p>`));
    } else {
      c4.appendChild(el(`<p class="note" style="margin:0;font-size:12px">No captured comps for a tempo read.</p>`));
    }
    cols.appendChild(c4);

    g.appendChild(cols);
    root.appendChild(g);
  }

  // The short version — plain counts, like the League meta tab: what this team
  // bans most and plays most, no jargon. (Requested: a simple by-the-numbers read
  // that doesn't need decoding.)
  {
    const sc=((DATA.owdb_comps||{})[t.team]||{}).scout;
    const banRows=rank(t.bans).slice(0,8).map(([h,n])=>({label:heroChip(h),value:n,color:roleVar(HERO_ROLE[h])}));
    const pool=((sc&&sc.hero_pool)||[]).slice().sort((a,b)=>(b.rounds||0)-(a.rounds||0)).slice(0,8);
    const playRows=pool.map(h=>({label:heroChip(h.hero),value:h.rounds||0,color:roleVar(h.role||HERO_ROLE[h.hero])}));
    if(banRows.length||playRows.length){
      const two=el(`<div class="grid cols-2 mt14"></div>`);
      const bc=el(`<div class="card"></div>`);
      bc.appendChild(el(`<p class="eyebrow">Most-banned heroes</p>`));
      bc.appendChild(el(`<p class="note" style="margin:0 0 8px">How many times ${esc(t.team)} banned each hero${capSince()}.</p>`));
      bc.appendChild(el(banRows.length?barList(banRows):`<p class="note">No bans in window.</p>`));
      const pc=el(`<div class="card"></div>`);
      pc.appendChild(el(`<p class="eyebrow">Most-played heroes</p>`));
      pc.appendChild(el(`<p class="note" style="margin:0 0 8px">Rounds played across their captured comps.</p>`));
      pc.appendChild(el(playRows.length?barList(playRows):`<p class="note">No captured comps yet — scout some to fill this in.</p>`));
      two.append(bc,pc); root.appendChild(two);
    }
  }

  // Scouting coverage - the capture work-list. Every replay-coded game either
  // has captured comps or is still to scout; the pending codes are click-to-copy
  // chips, so "what do I scout next for this team" is answered right here.
  if(t.replays.length){
    // A pre-wipe game is only in scope if someone captured it before the wipe;
    // otherwise its code is dead and no amount of scouting can recover it.
    const scoutable=t.replays.filter(r=>CAPTURED.has(r.mid+':'+r.gno)||!codeDead(r.when));
    const lost=t.replays.length-scoutable.length;
    const done=scoutable.filter(r=>CAPTURED.has(r.mid+':'+r.gno));
    const todo=scoutable.filter(r=>!CAPTURED.has(r.mid+':'+r.gno))
      .sort((a,b)=>(b.when||'').localeCompare(a.when||''));
    const cst=coverageState(t.replays.length,scoutable.length,done.length,CODE_WIPE);
    const cov=el(`<div class="card mt10"></div>`);
    cov.appendChild(el(`<p class="eyebrow">Scouting coverage · ${done.length} of ${scoutable.length} scoutable games captured`+
      (lost?` <span class="faint">· ${lost} lost to the ${esc(CODE_WIPE)} code wipe</span>`:'')+`</p>`));
    if(cst&&cst.kind==='wiped'){
      cov.appendChild(el(`<p class="note" style="margin:0">${esc(cst.text)}</p>`));
    } else if(todo.length){
      const row=el(`<div style="display:flex;flex-wrap:wrap;gap:6px;align-items:center"></div>`);
      row.appendChild(el(`<span class="note" style="margin:0">to scout:</span>`));
      todo.slice(0,8).forEach(r=>{
        const chip=el(`<span class="opt" style="cursor:default">${rcChip(r.code)}<span class="pp">${esc(r.map)} · ${dshort(r.when)}</span></span>`);
        row.appendChild(chip);
      });
      if(todo.length>8) row.appendChild(el(`<span class="faint">+${todo.length-8} more</span>`));
      row.appendChild(el(`<a class="btn" href="${captureUrl(t.team)}" style="text-decoration:none;padding:4px 10px;font-size:12px;margin-left:auto;white-space:nowrap">Capture →</a>`));
      cov.appendChild(row);
    } else {
      cov.appendChild(el(`<p class="note" style="margin:0">${esc((cst||{}).text||'')}</p>`));
    }
    root.appendChild(cov);
  }

  // Adaptability now lives in the glance band above. Sticky jump bar heads the
  // main column; Matches moved to the rail, so it drops out of the jump links.
  w.appendChild(el(`<nav class="minibar">`+
    `<a href="#sc-run">What they run</a><a href="#sc-ban">Ban decision</a>`+
    `<a href="#sc-map">Map decision</a></nav>`));

  // ---- Scouting from captured replays (owdb) -------------------------
  // Three sections: what they play (Common comps + Hero pool), where they play
  // it (Map scouting, collapsible), and how they react (Common swaps).
  const oc=(DATA.owdb_comps||{})[t.team];
  const scout=oc&&oc.scout;
  const nGames=(scout&&scout.games)||0;
  // Honest degrade: don't let the hero sections silently vanish for an uncaptured
  // team - say so, and point at the rail so they get scouted.
  if(!scout){
    const ns=el(`<div class="card mt10" style="display:flex;justify-content:space-between;align-items:center;gap:12px;flex-wrap:wrap"></div>`);
    ns.appendChild(el(`<div><p class="eyebrow" style="margin:0 0 2px">Not scouted yet</p>`+
      `<span class="note">No captured comps for ${esc(t.team)} <b>(0 of ${t.games} maps played)</b>. Everything below is FACEIT draft data only.</span></div>`));
    const cb=el(`<a class="btn" href="${captureUrl(t.team)}" style="text-decoration:none;white-space:nowrap">Capture ${esc(t.team)} →</a>`);
    ns.appendChild(cb); w.appendChild(ns);
  }

  // Scouting tells: a scannable TL;DR of the team's strongest, data-backed
  // tendencies. Each line names its evidence; none fires on a single game. Built
  // entirely from signals already computed (ban-lift, ban-response, signatures).
  {
    const tells=[];
    const bb=divBanBaseline();
    const sigBan=banLiftRows(t.bans, bb.all, 3).filter(r=>r.lift&&r.lift>=1.5)[0];
    if(sigBan) tells.push(`<span class="then">ban</span> bans ${heroChip(sigBan.hero)} far more than most teams `+
      `<span class="faint" title="${sigBan.lift.toFixed(1)}× as often as the average team">${sigBan.n} bans</span>`);
    const br=((scout&&scout.ban_response)||[]).filter(b=>b.games>=2 && (b.opens||[]).length)[0];
    if(br) tells.push(`<span class="then">when ${esc(br.banned)} banned</span> opens ${compRow(br.opens[0].heroes)} `+
      `<span class="faint">${br.games} games</span>`);
    const sig=Object.entries(t.pickFirstBan).map(([m,v])=>({m,v}))
      .filter(x=>x.v.games>=2).sort((a,b)=>b.v.games-a.v.games)[0];
    if(sig){ const tb=rank(sig.v.bans)[0];
      tells.push(`<span class="then">map</span> on ${esc(sig.m)} they pick &amp; open the ban`+
        (tb?` on ${heroChip(tb[0])}`:'')+` <span class="faint">${sig.v.games}x, self-chosen</span>`); }
    if(tells.length){
      const card=el(`<div class="card mt10"><p class="eyebrow">Scouting tells</p></div>`);
      tells.forEach(tx=>card.appendChild(el(`<div class="crow" style="border:none;padding:4px 2px"><span class="swapline">${tx}</span></div>`)));
      w.appendChild(card);
    }
  }
  // n=1 is an anecdote, not a pattern - show it, but visibly weaker.
  const thin=n=>n<=1?' thin':'';
  // Below 3 maps a W-L is an anecdote that READS like a rate (Redline and
  // Peps ran the identical comp 0-4 vs 2-0) - so thin rows show frequency
  // only, and records appear once there is something behind them.
  const rec=c=>c.maps>=3?`${c.maps} maps · ${c.wins}W-${c.losses}L`
                        :`${c.maps} map${c.maps===1?'':'s'}`;
  // Bans that accompany a comp fill the row's dead middle: the draft context the
  // comp lives in (heroes banned out in a majority of the games they ran it).
  const banHtml=c=>(c.bans&&c.bans.length)
    ? `<span class="cbans"><span class="bl">bans</span>${c.bans.slice(0,4).map(h=>heroIcon(h)).join('')}</span>` : '';
  const compLine=c=>`<div class="crow${thin(c.maps)}"><span>${compRow(c.heroes)}</span>`+
                    `${banHtml(c)}<span class="rec">${rec(c)} · ${codesCell(codesFor(c.game_keys||[],lookup))}</span></div>`;
  if(scout) w.appendChild(cluster('sc-run','What they run'));
  if(scout){
    // 1. Common comps - the 3-5 they actually run most.
    const top=(scout.overall||[]).slice(0,5);
    if(top.length){
      w.appendChild(el(sectionH('Common comps',
        `<span class="note">most-played compositions · ${nGames} map${nGames===1?'':'s'} captured${capSince()}</span>`)));
      const card=el(`<div class="card"></div>`);
      top.forEach(c=>card.appendChild(el(compLine(c))));
      w.appendChild(card);
    }

    // 2. Hero pool, split by role - counted in ROUNDS, not maps: a hero played
    // every round is a staple, one played for a single point is not, and counting
    // maps flattens both to "1 map".
    const pool=scout.hero_pool||[];
    const nRounds=scout.rounds||0;
    if(pool.length){
      w.appendChild(el(sectionH('Hero pool',
        `<span class="note">rounds played · ${nRounds} round${nRounds===1?'':'s'} captured${capSince()}</span>`)));
      const grid=el(`<div class="grid cols-3"></div>`);
      ['Tank','Damage','Support'].forEach(role=>{
        const rows=pool.filter(h=>(h.role||HERO_ROLE[h.hero])===role).slice(0,8);
        const card=el(`<div class="card"></div>`);
        card.appendChild(el(`<p class="eyebrow role-${role}">${role}</p>`));
        if(!rows.length){ card.appendChild(el(`<p class="note">None captured.</p>`)); }
        rows.forEach(h=>{
          const pct=Math.round((h.pick_rate||0)*100);
          card.appendChild(el(`<div class="crow"><span>${heroChip(h.hero)}</span>`+
            `<span class="rec">${pct}% · ${h.rounds}/${nRounds}</span></div>`));
        });
        grid.appendChild(card);
      });
      w.appendChild(grid);
    }

    // 2b. Player pools - who plays what, when captures carry OCR attribution.
    // Absent for captures made before attribution existed; grows from here.
    const ppools=scout.players||[];
    if(ppools.length){
      w.appendChild(el(sectionH('Player pools',
        `<span class="note">who plays what, from HUD attribution · % = share of this player's captured rounds · hover for their averages${capSince()}</span>`)));
      const pgrid=el(`<div class="grid cols-3"></div>`);
      ppools.forEach(p=>{
        const card=el(`<div class="card"></div>`);
        card.appendChild(el(`<p class="eyebrow">${esc(p.player)} <span class="note">${p.rounds} rounds seen</span></p>`));
        p.heroes.slice(0,5).forEach(h=>{
          // Factual pool only: the hero, its share of this player's rounds, and
          // their raw averages on hover. No skill rank — see the Players tab note.
          const st=h.stats?` title="${h.games}g avg · ${h.stats.kd!=null?h.stats.kd+' k/d · ':''}${nf(h.stats.damage)} dmg · ${h.stats.elims} elim · ${h.stats.deaths} deaths · ${nf(h.stats.healing)} heal · ${nf(h.stats.mitigation)} mit"`:'';
          card.appendChild(el(
            `<div class="crow"${st}><span>${heroChip(h.hero)}</span>`+
            `<span class="rec">${Math.round((h.share||0)*100)}% · ${h.rounds}r</span></div>`));
        });
        pgrid.appendChild(card);
      });
      w.appendChild(pgrid);
    }

    // 3. Map scouting - collapsible per map; segments are attack/defend on
    // Escort+Hybrid, sub-maps on Control, one generic block otherwise.
    const maps=scout.maps||{};
    const mapNames=sortMaps(Object.keys(maps));
    if(mapNames.length){
      w.appendChild(el(sectionH('Map scouting',`<span class="note">click a map for captured detail${capSince()}</span>`)));
      let lastMode=null;
      mapNames.forEach(mp=>{
        // One mode at a time, with a heading where the mode changes.
        const mode=MAP_CAT[mp]||'Other';
        if(mode!==lastMode){ lastMode=mode; w.appendChild(el(`<p class="modeh">${esc(mode)}</p>`)); }
        const entry=maps[mp]||{}, segs=entry.segments||{};
        // Complete per-map record + opponents + this team's bans, straight from
        // FACEIT (every game on the map, not only captured ones). The captured
        // comps below supply the "what"; FACEIT supplies the "who / when / result".
        const fh=[], mapBans={};
        t.matches.forEach(m=>m.games.forEach(g=>{ if(g.map!==mp) return;
          const us=m.f1===t.team;
          fh.push({mid:m.id, opp:us?m.f2:m.f1, won:g.winner_team===t.team, when:m.finished_at,
                   score:us?`${g.f1}-${g.f2}`:`${g.f2}-${g.f1}`, pick:g.map_picked_by===t.team,
                   code:g.demo_code||null, dead:codeDead(m.finished_at)});
          (g.bans||[]).filter(b=>b.hero&&b.team===t.team).forEach(b=>{ mapBans[b.hero]=(mapBans[b.hero]||0)+1; }); }));
        fh.sort((a,b)=>(b.when||'').localeCompare(a.when||''));
        const fw=fh.filter(x=>x.won).length;
        const d=el(`<details class="mapblk"><summary><span>${esc(mp)}</span>`+
          `<span class="rec">${fh.length?`${fw}W-${fh.length-fw}L`:'&mdash;'}</span></summary>`+
          `<div class="mapbody"><div class="mapcol opens"></div>`+
          `<div class="mapcol swaps"></div></div></details>`);
        const body=d.querySelector('.mapcol.opens');
        // Recency first: the comp from the last 3 games on this map predicts what
        // they'll run better than an all-time cluster, and the history says who
        // they ran each comp against. Ordered by real match date, not capture time.
        const hist=mapHistory(scout, mp);
        if(hist.length){
          const last3=hist.slice(0,3), mod=modalComp(last3);
          body.appendChild(el(`<p class="seg">last 3 games</p>`));
          if(mod){
            const lab=mod.of>=3?`${mod.n} of last ${mod.of}`:`${mod.of} game${mod.of===1?'':'s'}`;
            const w3=last3.filter(g=>g.won).length;
            body.appendChild(el(`<div class="crow${thin(mod.of)}"><span>${compRow(mod.heroes)}</span>`+
              `<span class="rec">${lab} · ${w3}W-${last3.length-w3}L</span></div>`));
          }
          // Signature: heroes they bring on this map no matter which comp - the
          // non-negotiables, distinct from the "current comp" modal above.
          const sigc={}; hist.forEach(g=>(g.heroes||[]).forEach(h=>sigc[h]=(sigc[h]||0)+1));
          const sig=Object.entries(sigc).filter(([,n])=>hist.length>=3 && n/hist.length>=0.6)
            .sort((a,b)=>b[1]-a[1]).map(([h])=>h);
          if(sig.length) body.appendChild(el(`<p class="sighint"><span class="sigk">always here</span>`+
            `${sig.map(h=>heroChip(h)).join('')} <span class="faint">in most of ${hist.length} games</span></p>`));
        }
        // Their bans on THIS map (FACEIT drafts, complete) - a map-specific ban
        // tell that the "at a glance" panel's all-map bans can't show.
        const topMB=rank(mapBans).slice(0,5);
        if(topMB.length) body.appendChild(el(`<p class="sighint"><span class="sigk sigk-ban">bans here</span>`+
          topMB.map(([h,n])=>`<span class="mbchip">${heroChip(h)}<span class="faint">${n}&times;</span></span>`).join('')+`</p>`));
        // Real opponents on this map from FACEIT: names, dates, map score, who
        // picked it, and the result - the "who did they play" the captures lack.
        if(fh.length){
          const hd=el(`<details class="hist"><summary>history &middot; ${fh.length} game${fh.length===1?'':'s'} &middot; ${fw}W-${fh.length-fw}L</summary></details>`);
          fh.forEach(x=>hd.appendChild(el(
            `<a class="crow hrow" href="#match=${esc(x.mid)}"${x.mid?` title="Open match ${esc(x.mid)}"`:''}>`+
            `<span>${x.pick?`<span class="pickpill" title="they picked this map">pick</span> `:''}<span class="faint">vs</span> ${esc(x.opp||'?')}</span>`+
            `<span class="rec">${x.when?dshort(x.when)+' &middot; ':''}<span class="faint">${esc(x.score)}</span> ${x.won?'<b class="wlw">W</b>':'<b class="wll">L</b>'}`+
            `${x.code?(x.dead?' '+wipedTag:' '+rcChip(x.code)):''}</span></a>`)));
          body.appendChild(hd);
        }
        Object.keys(segs).forEach(seg=>{
          const both=segs[seg]||{};
          // "all captured" heads the single-geometry block so it reads distinctly
          // from the "last 3 games" above it; phased/control maps use their seg name.
          // A per-segment record makes attack-vs-defend (and each sub-map) legible
          // at a glance; shown only when the segment holds more than one comp, so
          // it doesn't just echo a lone comp row.
          let sgw=0,sgl=0,sgm=0; (both.open||[]).forEach(c=>{sgw+=c.wins;sgl+=c.losses;sgm+=c.maps;});
          const segRec=((both.open||[]).length>1)
            ? ` <span class="segrec">${sgm>=3?`${sgm} maps &middot; ${sgw}W-${sgl}L`:`${sgm} map${sgm===1?'':'s'}`}</span>` : '';
          // Escort/Hybrid segments are the attack and defend halves - badge them so
          // the asymmetry reads at a glance; sub-maps/single blocks keep their name.
          const segTitle=/^attack$/i.test(seg)?`<span class="side atk">&#9650; attack</span>`
                        :/^defend$/i.test(seg)?`<span class="side def">&#9660; defend</span>`
                        :(seg==='all'?'all captured':esc(seg));
          body.appendChild(el(`<p class="seg" style="margin-top:12px">${segTitle}${segRec}</p>`));
          (both.open||[]).slice(0,3).forEach(c=>body.appendChild(el(compLine(c))));
          // Only show "settled" when they actually changed off the opener - and
          // only the heroes that changed, since the rest is the row above it.
          const o=(both.open||[])[0], s=(both.settled||[])[0];
          const dl=o&&s?compDelta(o.heroes,s.heroes):null;
          if(dl){
            body.appendChild(el(`<div class="crow${thin(s.maps)}"><span class="swapline">`+
              `<span class="then">then</span>${deltaHtml(dl)}</span>`+
              `<span class="rec">${rec(s)}</span></div>`));
          }
        });
        const sw=d.querySelector('.mapcol.swaps');
        const mswaps=(entry.swaps||[]).slice(0,6);
        sw.appendChild(el(`<p class="seg">swaps here</p>`));
        if(mswaps.length){ mswaps.forEach(s=>sw.appendChild(el(swapLine(s)))); }
        else { sw.appendChild(el(`<p class="note">No mid-map swaps captured.</p>`)); }
        w.appendChild(d);
      });
    }

    // 4. Common swaps - lead with the trigger: what makes them counter-swap.
    const swaps=(scout.swaps||[]).slice(0,8);
    if(swaps.length){
      w.appendChild(el(sectionH('Common swaps',`<span class="note">what makes them change heroes${capSince()}</span>`)));
      const card=el(`<div class="card"></div>`);
      swaps.forEach(s=>card.appendChild(el(swapLine(s))));
      w.appendChild(card);
    }


  }



    // 6. Counter-scout - the question every other section can't answer: given
    // OUR planned comp, what has THIS team actually done against comps like it?
    if(scout){
      const mus=scout.matchups||[];
      w.appendChild(el(sectionH('Counter-scout',
        `<span class="note">pick your planned comp - see how they played against comps like it</span>`)));
      const csCard=el(`<div class="card"></div>`);
      const plan=PLANNED[t.team]=(PLANNED[t.team]||new Set());
      const pickRow=el(`<div style="display:flex;flex-wrap:wrap;gap:6px;align-items:center"></div>`);
      const resBox=el(`<div style="margin-top:10px"></div>`);

      // Heroes present in nearly every captured lineup carry no signal - with
      // Kiriko in 100% of rounds, "they swapped vs Kiriko" is noise, and the
      // scoring must ignore her rather than let her match everything.
      const prevalence={};
      mus.forEach(m=>new Set(m.vs).forEach(h=>prevalence[h]=(prevalence[h]||0)+1));
      const ubiquitous=new Set(Object.entries(prevalence)
        .filter(([,n])=>mus.length>=4&&n/mus.length>=0.9).map(([h])=>h));

      const redraw=()=>{
        pickRow.innerHTML='';
        [...plan].sort((a,b)=>roleRank(a)-roleRank(b)||a.localeCompare(b)).forEach(h=>{
          const chip=el(`<span class="opt">${heroChip(h)}<span class="pp">x</span></span>`);
          chip.onclick=()=>{ plan.delete(h); redraw(); };
          pickRow.appendChild(chip);
        });
        if(plan.size<5){
          pickRow.appendChild(heroSelect('', new Set(plan), (name)=>{
            if(name){ plan.add(name); redraw(); } }));
        }
        if(plan.size){
          const clr=el(`<button class="sortbtn" type="button">clear</button>`);
          clr.onclick=()=>{ plan.clear(); redraw(); };
          pickRow.appendChild(clr);
        }

        resBox.innerHTML='';
        if(!plan.size){
          resBox.appendChild(el(`<p class="note">Pick the heroes you intend to run (partial comps work too).</p>`));
          return;
        }
        const signal=[...plan].filter(h=>!ubiquitous.has(h));
        if(signal.length<plan.size){
          resBox.appendChild(el(`<p class="note">${[...plan].filter(h=>ubiquitous.has(h)).map(esc).join(', ')} ignored for matching - they appear in ~every captured game.</p>`));
        }
        // A. Their games against comps overlapping yours, with THEIR result.
        // Thin data degrades gracefully: step the overlap requirement down until
        // something matches, and SAY which tier is being shown - a weak match
        // labelled as weak beats an empty section.
        const scored=mus.map(m=>({m,ov:signal.filter(h=>(m.vs||[]).includes(h))}));
        let need=Math.min(signal.length,3), sim=[];
        for(; need>=1; need--){
          sim=scored.filter(x=>x.ov.length>=need).sort((a,b)=>b.ov.length-a.ov.length);
          if(sim.length) break;
        }
        const q=need>=3?`${need} of your heroes`:need===2?'2 of your heroes':'1 of your heroes';
        resBox.appendChild(el(`<p class="eyebrow" style="margin-bottom:3px">Vs comps like yours (${sim.length})</p>`));
        if(sim.length){
          const wins=sim.filter(x=>x.m.won).length, losses=sim.length-wins;
          // A stated W-L record needs a real, tight sample. A lone loosely-matched
          // game gets shown as-is, never summarised into a fake "0W-1L" trend.
          const solid=need>=3 && sim.length>=3;
          resBox.appendChild(el(solid
            ? `<p class="note" style="margin-top:0">They went <b class="${wins>=losses?'wlw':'wll'}">${wins}W-${losses}L</b> when the opponent shared ${q}.</p>`
            : `<p class="note" style="margin-top:0">Only ${sim.length} game${sim.length>1?'s':''} where the opponent shared ${q} — too thin to call a record, but here's what they did:</p>`));
          sim.slice(0,6).forEach(({m,ov})=>{
            // Counter-scout rows are already one game each (unlike the aggregated
            // tables above) - always the inline single-code case, never a popover.
            const cc=lookup.get(m.match_id+':'+m.game_no);
            const ccTag=cc?(cc.dead?' '+wipedTag:' '+rcChip(cc.code)):'';
            resBox.appendChild(el(`<div class="crow${ov.length<2?' thin':''}">`+
              `<span class="csrow"><span class="wlsq ${m.won?'w':'l'}">${m.won?'W':'L'}</span>`+
              `<b>${esc(m.map)}</b><span class="faint">ran</span>${compRow(m.open||[])}</span>`+
              `<span class="rec">matched ${ov.length}/${signal.length}${ccTag}</span></div>`));
          });
        } else {
          resBox.appendChild(el(`<p class="note">No captured game where they faced any of those heroes yet.</p>`));
        }

        // B. Swaps they made when facing your planned heroes.
        const sw=(scout.swaps||[]).map(x=>({x,ov:(x.vs||[]).filter(h=>signal.includes(h))}))
          .filter(y=>y.ov.length)
          .sort((a,b)=>b.ov.length-a.ov.length||b.x.count-a.x.count);
        if(sw.length){
          resBox.appendChild(el(`<p class="eyebrow" style="margin-top:10px">Swaps they made against those heroes</p>`));
          sw.slice(0,5).forEach(({x})=>resBox.appendChild(el(swapLine(x))));
        }
      };
      redraw();
      csCard.append(pickRow,resBox);
      w.appendChild(csCard);
    }


  // ==== BAN DECISION: the planner answers; the drawer holds the receipts.
  w.appendChild(cluster('sc-ban','Ban decision'));
    // 7. Ban planner - "what should we ban" as an answer, not homework. A ban's
    // cost to them = how much they lean on the hero x how weak their same-seat
    // backup is, cross-checked against what actually happened when it was
    // banned before. Every component is SHOWN - the verdict is a summary of
    // visible evidence, not a black-box score.
    if(scout && (scout.hero_pool||[]).length){
      const pool=scout.hero_pool;
      const bySeat={};
      pool.forEach(h=>{ const st=HERO_SEAT[h.hero]||h.role||'?';
        (bySeat[st]=bySeat[st]||[]).push(h); });
      Object.values(bySeat).forEach(a=>a.sort((x,y)=>y.rounds-x.rounds));
      const brByHero={}; (scout.ban_response||[]).forEach(b=>brByHero[b.banned]=b);

      // Division-wide (meta) pick rate per hero = rounds featuring it / all captured
      // rounds across every team. Lets the planner separate a team's SIGNATURE hero
      // (they run it far more than the field) from a MUST-PLAY meta staple everyone
      // runs — banning a staple hurts both sides equally, so it's a wash, not a
      // targeted ban. A ban only disrupts THEM specifically when it's distinctive.
      const metaRate=(()=>{ const tot={}; let allR=0;
        Object.values(DATA.owdb_comps||{}).forEach(oc=>{ const sc=oc&&oc.scout; if(!sc||!sc.hero_pool) return;
          const r=sc.rounds||0; if(!r) return; allR+=r;
          sc.hero_pool.forEach(x=>{ tot[x.hero]=(tot[x.hero]||0)+((x.pick_rate||0)*r); }); });
        const out={}; if(allR) for(const k in tot) out[k]=tot[k]/allR; return out; })();

      const rows=pool.filter(h=>(h.pick_rate||0)>=0.25).map(h=>{
        const seat=HERO_SEAT[h.hero]||h.role||'?';
        const backup=(bySeat[seat]||[]).find(x=>x.hero!==h.hero)||null;
        const br=brByHero[h.hero];
        let banned=null;
        if(br){
          let w=0,l=0; (br.opens||[]).forEach(o=>{w+=o.wins;l+=o.losses;});
          banned={games:br.games,w,l};
        }
        const share=h.pick_rate||0, bshare=backup?(backup.pick_rate||0):0;
        const meta=metaRate[h.hero]||0;
        const lift= meta>0 ? share/meta : (share>0?99:1);   // how much MORE than the field they run it
        const staple= meta>=0.5;                            // run by ~half+ of the division = must-play
        // A ban is worth it only if they lean on it DISTINCTIVELY (far above the
        // field) and the seat has no practiced fallback. A must-play staple they
        // don't run more than anyone else is a wash — banning denies it to us too.
        let verdict;
        if(staple && lift<1.3)                          verdict=['meta','var(--faint)'];
        else if(share>=0.5 && bshare<0.3 && lift>=1.3)  verdict=['expensive','var(--good)'];
        else if(bshare>=share*0.7)                      verdict=['cheap','var(--bad)'];
        else                                            verdict=['moderate','var(--mid)'];
        return {h,seat,backup,banned,share,meta,lift,verdict};
      }).sort((a,b)=>{
        const rank=v=>v==='expensive'?0:v==='moderate'?1:v==='meta'?2:3;
        return rank(a.verdict[0])-rank(b.verdict[0])||b.lift-a.lift||b.share-a.share;
      });

      if(rows.length){
        w.appendChild(el(sectionH('Ban planner',
          `<span class="note">bans that hurt THEM specifically — heroes they run far more than the field, with a weak fallback. Meta staples everyone runs rank last (banning them is a wash).</span>`)));
        const card=el(`<div class="card"></div>`);
        rows.slice(0,8).forEach(({h,seat,backup,banned,share,meta,verdict})=>{
          const parts=[`${Math.round(share*100)}% of their rounds <span class="faint">· league ${Math.round(meta*100)}%</span>`,
                       `<span class="faint">${esc(seat)}</span>`];
          parts.push(backup
            ?`backup: ${heroIcon(backup.hero)} ${esc(backup.hero)} <span class="faint">${Math.round((backup.pick_rate||0)*100)}%</span>`
            :`<b>no captured backup in seat</b>`);
          if(banned) parts.push(`when banned: <b>${banned.w}W-${banned.l}L</b> <span class="faint">(${banned.games}g)</span>`);
          card.appendChild(el(`<div class="crow"><span>${heroChip(h.hero)} <span class="faint">·</span> ${parts.join(' <span class="faint">·</span> ')}</span>`+
            `<span class="rec">${pill('ban: '+verdict[0],verdict[1])}</span></div>`));
        });
        card.appendChild(el(`<p class="note" style="margin:8px 0 0">"expensive" = they run it far more than the division AND have no practiced fallback, so banning disrupts them specifically. "meta" = everyone runs it, so banning is a wash. Verdicts summarise the shown numbers — check them on thin data.</p>`));
        w.appendChild(card);
      }
    }

  // Preferred bans + Maps picks/win rate - the side-by-side pair, restored
  // by operator request after the reorg had split it across the clusters.
  const two=el(`<div class="grid cols-2 mt14" style="align-items:start"></div>`);
  const banC=el(`<div class="card"></div>`);
  const banBase=divBanBaseline();
  banC.appendChild(el(`<p class="eyebrow">Ban tendencies <span class="note">· compared to the league average, not raw counts</span></p>`));
  banC.appendChild(el(banLiftList(banLiftRows(t.bans, banBase.all, undefined, t.bansGk, lookup))));
  if(t.firstBanGames){
    banC.appendChild(el(`<p class="eyebrow" style="margin-top:16px">First ban <span class="note">· when they draft first (${t.firstBanGames} maps) — the intentional one</span></p>`));
    banC.appendChild(el(banLiftList(banLiftRows(t.firstBans, banBase.first, undefined, t.firstBansGk, lookup))));
  }
  two.appendChild(banC);
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
  w.appendChild(two);

  {
    const dv=drawer('Ban evidence','counter-bans · ban response');
  // "Win rate by banned hero" was removed here: conditioned on team strength it
  // does not survive out-of-sample (negative correlation), and the sort floated
  // the noisiest small samples to the top. Ban tendency now reads as lift, above.

  // Counter-bans — genuine responses only: the opponent banned first, this team
  // banned second in reply. (Cases where this team banned first are excluded.)
      dv.body.appendChild(el(sectionH('Counter-bans',`<span class="note">opponent bans first → ${esc(t.team)}'s reply</span>`)));
  const cRows=rank(Object.fromEntries(Object.entries(t.counter).map(([k,v])=>[k,Object.values(v).reduce((x,y)=>x+y,0)])))
    .map(([opp,tot])=>({opp,tot,resp:rank(t.counter[opp]).map(([h,n])=>`${heroChip(h)}<span class="faint"> ${n}</span>`).join(' '),
      codes:codesFor(t.counterGk[opp]||new Set(),lookup)}));
      dv.body.appendChild(cRows.length?table(
    [{k:'opp',label:'Opponent banned first',html:r=>heroChip(r.opp)},{k:'tot',label:'×',num:true},
     {k:'resp',label:`${esc(t.team)} replied with`,html:r=>r.resp},
     {k:'codes',label:'Codes',html:r=>codesCell(r.codes)}], cRows)
   :el(`<p class="note">No counter-bans in this window (needs the opponent to have banned first with both bans attributed).</p>`));

    // Ban -> opening: when THIS team bans a hero (FACEIT, complete), the heroes
    // they open with in those games. A hero shown in most of the "banned X" games
    // is the tell ("bans Sigma -> opens Ramattra"). Needs captured openings, so it
    // fills in as more of their games are scouted.
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
    w.appendChild(dv.root);
  }

  // ==== MAP DECISION ====
  w.appendChild(cluster('sc-map','Map decision'));
  // Signature setups — maps THEY pick AND ban first on (a fully self-chosen draft).
  // A high win% on a repeated map+ban tells you it's a rehearsed strat to be ready for.
  // Their captured opening comp on that map, when owdb has one: the map + first
  // ban says what they chose, this says what they actually ran inside it.
  const scoutMaps=(scout&&scout.maps)||{};
  const openOn=mp=>{
    const segs=(scoutMaps[mp]||{}).segments||{};
    const best=Object.values(segs).map(b=>(b.open||[])[0]).filter(Boolean)
      .sort((a,b)=>b.maps-a.maps)[0];
    return best?`<span style="display:inline-flex;align-items:center;flex-wrap:wrap;gap:2px 8px;white-space:normal">${compRow(best.heroes)}<span class="faint">${rec(best)}</span></span>`:'';
  };
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

  // Matches — full match cards for this team (same view as searching them on the
  // Matches tab): per-map bans in draft order, replay codes inline, toggleable rosters.
  {
    const dv=drawer('Ban-by-map evidence','what they ban on maps they pick');
  // Bans on maps they PICKED only. The all-maps version was dropped: on a map the
  // opponent picked, the ban is a reaction, so it diluted the signal this shows.
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
      dv.body.appendChild(el(sectionH('Bans on maps they pick',`<span class="note">what ${esc(t.team)} bans on maps they chose</span>`)));
      dv.body.appendChild(banMapTable(t.perMapPick));
    w.appendChild(dv.root);
  }

  // ==== MATCHES: a sticky right rail, not a bottom drawer — the receipts stay
  // in view while you read the analysis, and the list scrolls inside the rail.
  side.appendChild(el(sectionH('Matches',
    `<span class="note">${t.matches.length} match${t.matches.length===1?'':'es'} · click a map for rosters · codes inline</span>`)));
  if(t.matches.length){
    const mbox=el(`<div class="scrollbox rail"></div>`);
    t.matches.forEach(m=>mbox.appendChild(matchCard(m)));
    side.appendChild(mbox);
  } else {
    side.appendChild(el(`<p class="note">No matches in this window.</p>`));
  }

  // Upcoming fixtures for this team — who they play next and when. Not windowed
  // (these are future matches); pulled from the division's scheduled matches.
  const tUp=(D().upcoming||[]).filter(u=>u.f1===t.team||u.f2===t.team)
    .sort((a,b)=>String(a.scheduled_at||'').localeCompare(String(b.scheduled_at||'')));
  if(tUp.length){
    side.appendChild(el(sectionH('Upcoming',`<span class="note">${tUp.length} scheduled</span>`)));
    const ub=el(`<div class="uprows"></div>`);
    tUp.forEach(u=>{ const opp=(u.f1===t.team)?u.f2:u.f1;
      ub.appendChild(el(`<div class="uprow"><span class="uptime">${u.scheduled_at?esc(fmtWhen(u.scheduled_at)):'time TBD'}</span>`+
        `<span class="upteams"><span class="upvs">vs</span>${opp?teamLink(opp):'<span class="faint">TBD</span>'}</span>`+
        `<span class="uptag">${u.round?('Round '+u.round):''}</span></div>`));
    });
    side.appendChild(ub);
  }

  const layout=el(`<div class="scoutgrid"></div>`);
  layout.append(w, side);
  root.appendChild(layout);

  // Draft simulator, relegated here from its own top-level tab: it's a
  // matchup-prep tool reached for while prepping a specific opponent, not a
  // destination on its own. Lazy-built on first open (or forced open once by
  // the #sim deep-link redirect in init()) since renderSim() does real work
  // aggregating each team's ban/pick history.
  {
    const openSim=SCOUT_SIM_OPEN; SCOUT_SIM_OPEN=false;
    const dsCard=el(`<details class="card mt14"${openSim?' open':''}></details>`);
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
    // The #sim deep link forces this section open; show() then scrolls the page
    // to the top, so land the reader on the sim itself after that settles.
    if(openSim){ setTimeout(()=>{ try{ dsCard.scrollIntoView({block:'start',behavior:'smooth'}); }catch(e){} }, 150); }
  }

  return root;
}

/* ================================================= DRAFT SIMULATOR (manual scenario planner) */
// Per-team history over the active division: map-pick counts, per-map ban counts, overall ban counts.
/* ============================================================= PLAYERS */
// League-wide player leaderboards from owdb's merge-time ranks (division/tier-
// scoped, role-weighted, deaths heavy). Two modes: "By hero" (rank within one
// hero) and "By role" (aggregate a player across the heroes of a competitive seat
// — Tank / Hitscan / Flex DPS / Main Support / Flex Support).
// ---- Players tab: a league player DIRECTORY (not a ranking — captured samples
// are too small and scoreboard stats too crude to rank fairly). Roster, role and
// team come from FACEIT (covers everyone); top heroes + averages come from
// captures (present once a player is scouted, blank otherwise).
function playerCaptures(){ const ocs=DATA.owdb_comps||{}, out={};
  D().team_names.forEach(team=>{ (((ocs[team]||{}).scout||{}).players||[]).forEach(p=>{
    out[team+'|'+p.player]={rounds:p.rounds||0, heroes:(p.heroes||[]).slice()}; }); });
  return out; }
function topHeroes(cap,n){ return cap&&cap.heroes&&cap.heroes.length
  ? cap.heroes.slice().sort((a,b)=>(b.rounds||0)-(a.rounds||0)).slice(0,n||3) : []; }
const roleOf=r=>/tank/i.test(r||'')?'Tank':/support/i.test(r||'')?'Support':/dam|dps/i.test(r||'')?'Damage':null;
// A player's competitive SEAT, inferred from the heroes they've been captured on:
// tally rounds per seat among the two seats their FACEIT role allows and take the
// most-played. Tanks are one seat. A player with no captures returns null (can't
// be seated → listed by role at the foot); a scouted player whose captured heroes
// are all unclassified falls back to their role's primary seat.
const ROLE_SEATS={Damage:['Hitscan','Flex DPS'],Support:['Main Support','Flex Support']};
function seatOfPlayer(p){ const role=roleOf(p.role); if(!role) return null;
  const hs=(p.cap&&p.cap.heroes)||[]; if(!hs.length) return null;   // unscouted (any role) → listed by role at the foot
  if(role==='Tank') return 'Tank';                                  // tanks are one seat
  const allowed=ROLE_SEATS[role]; if(!allowed) return null;
  const tally={}; hs.forEach(h=>{ const s=HERO_SEAT[h.hero]; if(s&&allowed.indexOf(s)>=0) tally[s]=(tally[s]||0)+(h.rounds||0); });
  return Object.keys(tally).sort((a,b)=>tally[b]-tally[a])[0]||allowed[0]; }
// The peer group efficiency is compared against: a player's competitive role
// when captures place them in one, else their base role. Every player gets a
// group, so the rating stays full-coverage; the competitive role is simply the
// finer signal where it exists (see seatOfPlayer).
function effGroupOf(p){ const seat=seatOfPlayer(p); if(seat) return seat; return roleOf(p.role)||null; }
// The exported roster stats (per-map averages off FACEIT's feed) in the shape
// playerStatLine speaks. This replaced an equivalent computed from CAPTURED
// heroes only: the seat is what needs a capture, the numbers never did, and the
// season feed covers every player of every match.
function faceitAvg(p){ const s=p&&p.stats; if(!s) return null;
  return {games:s.games, kd:s.kd, elims:s.elims, deaths:s.deaths,
          damage:s.dmg, healing:s.heal, mitigation:s.mit}; }
function playerStatLine(role,s){ if(!s) return ''; const kd=s.kd!=null?`${s.kd} k/d`:'';
  if(role==='Support') return `${nf(s.healing)} heal · ${s.deaths} d${kd?' · '+kd:''}`;
  if(role==='Tank')    return `${kd?kd+' · ':''}${s.deaths} d · ${nf(s.damage)} dmg`;
  return `${kd?kd+' · ':''}${nf(s.damage)} dmg · ${s.deaths} d`; }
function renderPlayers(){
  const wrap=el(`<div></div>`);
  const cap=playerCaptures();
  // Every known player from the FACEIT rosters, captured heroes/stats joined by nick.
  // elo + per-map stat averages ride on the roster rows: FACEIT reports them for
  // every player of every match, so they are present at full league coverage -
  // unlike hero pools, which only exist where someone captured the replay.
  const players=[];
  D().teams.forEach(t=>{ (t.roster||[]).forEach(p=>{
    players.push({nick:p.nick, team:t.name, role:p.role||'', maps:p.games||0, current:!!p.current,
      elo:(p.elo==null?null:p.elo), stats:p.stats||null,
      cap:cap[t.name+'|'+p.nick]||null}); }); });
  // Efficiency rating: per-map stats z-scored against the division's same-role
  // players (pure layer). One pass over every known player, captured or not.
  const effs=efficiencyRatings(players.map(p=>({group:effGroupOf(p),stats:p.stats})));
  players.forEach((p,i)=>{ p.eff=effs[i]; });
  if(!players.length){
    wrap.appendChild(el(`<p class="note" style="margin-top:14px">No roster data yet.</p>`));
    return wrap;
  }
  wrap.appendChild(el(sectionH('Players',
    `<span class="note">every known player in ${esc(D().summary.championship||'the division')} · roles, teams, elo &amp; per-map stats from FACEIT (every division) · hero pools from captured games</span>`)));
  const modebar=el(`<div class="wsel" style="margin:2px 2px 12px"></div>`);
  const body=el(`<div></div>`);
  wrap.append(modebar, body);

  const icons=(c)=>{ const hs=topHeroes(c,3); return hs.length
    ? `<span title="${hs.map(x=>esc(x.hero)+' ('+(x.rounds||0)+'r)').join(', ')}">${hs.map(x=>heroIcon(x.hero)).join('')}</span>`
    : `<span class="faint" style="font-size:11px">not scouted</span>`; };

  // Team view: each roster (main 5 first, subs dimmed) with each player's top 3 heroes.
  function drawTeam(){
    body.innerHTML='';
    const grid=el(`<div class="grid cols-3"></div>`);
    D().teams.forEach(t=>{
      const ros=t.roster||[];
      const card=el(`<div class="card roster"></div>`);
      card.appendChild(el(`<h4 style="display:flex;justify-content:space-between;align-items:center;gap:8px">`+
        `<span class="tlink" data-scout="${esc(t.name)}" title="Scout ${esc(t.name)}" style="display:flex;align-items:center;gap:8px;color:var(--fg);font-size:14px;font-weight:660">${teamAvatar(t.name,28)}${esc(t.name)}${capBtn(t.name)}</span>${pill(t.win_pct+'%',winVar(t.win_pct))}</h4>`));
      const curP=ros.filter(p=>p.current), subP=ros.filter(p=>!p.current);
      const mkRow=(p,dim)=>{ const av=faceitAvg(p), hs=topHeroes(cap[t.name+'|'+p.nick],3), role=roleOf(p.role);
        return el(`<div class="seatrow"${dim?' style="opacity:.55"':''} title="${p.games} maps this season${av?' · '+av.kd+' k/d · '+nf(av.damage)+' dmg · '+av.deaths+' d · '+nf(av.healing)+' heal':''}">`+
          `<span class="nm"><b>${esc(p.nick)}</b><span class="tm">${role?`<span class="dot bg-${esc(role||'')}" style="display:inline-block;vertical-align:middle;margin-right:4px"></span>${esc(role)}`:'—'}${p.elo!=null?` · ${p.elo} elo`:''}</span></span>`+
          `<span class="hs">${hs.map(x=>heroIcon(x.hero)).join('')}</span>`+
          `<span class="rec">${av?playerStatLine(role,av)+` <span class="faint">· ${av.games}m</span>`:''}</span></div>`); };
      curP.forEach(p=>card.appendChild(mkRow(p,false)));
      if(subP.length){ card.appendChild(el(`<div class="subhd">subs / also played</div>`)); subP.forEach(p=>card.appendChild(mkRow(p,true))); }
      if(!ros.length) card.appendChild(el(`<span class="faint">no roster data yet</span>`));
      grid.appendChild(card);
    });
    body.appendChild(grid);
  }
  // Seat view: every player grouped by competitive seat (Tank / Hitscan / Flex
  // DPS / Main Support / Flex Support), with top 3 heroes + their average stats on
  // captured games. A player's seat is inferred from the heroes they've been
  // captured on (see seatOfPlayer); un-captured players can't be seated, so
  // they're listed by role at the foot.
  // Role view: one card per competitive role, each a sortable table. Clicking a
  // metric header sorts EVERY role card by that column (one shared sort state);
  // Eff is the default. Rate metrics respect the sample floor - a player below it
  // sorts last rather than topping the table off a one-map cameo. Columns and
  // cells come from the same statColTh/statCells helpers the leaderboard uses.
  function drawRole(){
    body.innerHTML='';
    const bySeat={}; SEATS.forEach(s=>bySeat[s]=[]);
    const unseated={Tank:[],Damage:[],Support:[]};
    players.forEach(p=>{ const role=roleOf(p.role); if(!role) return;
      const seat=seatOfPlayer(p);
      if(seat&&bySeat[seat]) bySeat[seat].push(p); else unseated[role].push(p); });
    // One role at a time keeps a 9-column table from crowding five of them onto
    // the screen; the switcher picks which one.
    const bar=el(`<div class="modebar" style="margin:0 0 10px"></div>`);
    SEATS.forEach(s=>{
      const b=el(`<span class="wbtn" data-v="${esc(s)}">${esc(s)}</span>`);
      b.classList.toggle('selA', (PLAYERS_SEAT||SEATS[0])===s);
      b.onclick=()=>{ PLAYERS_SEAT=s; drawRole(); }; bar.appendChild(b);
    });
    body.appendChild(bar);
    const seats=[PLAYERS_SEAT||SEATS[0]];
    const val=(p,k)=> k==='maps' ? (p.maps==null?null:p.maps)
      : k==='elo' ? (p.elo==null?null:p.elo)
      : k==='eff' ? (p.eff&&p.eff.eff!=null?p.eff.eff:null)
      : (p.stats&&(p.stats.games||0)>=LB_MIN_GAMES ? p.stats[k] : null);
    const byKey=(a,b)=>{ const av=val(a,PLAYERS_ROLE_SORT), bv=val(b,PLAYERS_ROLE_SORT);
      if(av==null&&bv==null) return String(a.nick).localeCompare(String(b.nick));
      if(av==null) return 1; if(bv==null) return -1;
      return bv-av || String(a.nick).localeCompare(String(b.nick)); };
    let any=false;
    seats.forEach(seat=>{
      const pool=(bySeat[seat]||[]).slice(); if(!pool.length) return; any=true;
      const baseRole = seat==='Tank'?'Tank' : /Support/.test(seat)?'Support':'Damage';
      const list=pool.sort(byKey);
      const col=(LB_COLS.find(c=>c.k===PLAYERS_ROLE_SORT)||{}).label||PLAYERS_ROLE_SORT;
      const card=el(`<div class="card" style="margin-bottom:12px"></div>`);
      card.appendChild(el(`<p class="eyebrow role-${baseRole}">${esc(seat)} <span class="note">${list.length} player${list.length===1?'':'s'} · sorted by <b>${esc(col)}</b></span></p>`));
      const tb=el(`<table class="compact"><thead><tr><th>Player</th><th>Top heroes</th>${statColTh(PLAYERS_ROLE_SORT)}</tr></thead><tbody></tbody></table>`);
      const tb2=tb.querySelector('tbody');
      list.forEach(p=>{ const hs=topHeroes(p.cap,3);
        tb2.appendChild(el(`<tr>`+
          `<td><b>${esc(p.nick)}</b><span class="tm" style="display:block;font-size:11px">${esc(p.team)}</span></td>`+
          `<td class="num">${hs.length?hs.map(x=>heroIconSmall(x.hero)).join(''):'<span class="faint">—</span>'}</td>`+
          statCells(p)+`</tr>`)); });
      tb.querySelectorAll('th[data-k]').forEach(th=>{ th.onclick=()=>{ PLAYERS_ROLE_SORT=th.dataset.k; drawRole(); }; });
      card.appendChild(tb); body.appendChild(card);
    });
    if(!any) body.appendChild(el(`<p class="note">No players with a known role yet.</p>`));
    const un=[]; const foot=(lbl,arr)=>{ if(arr.length) un.push(lbl+': '+arr.sort((a,b)=>b.maps-a.maps).map(p=>esc(p.nick)).join(', ')); };
    foot('Tank',unseated.Tank); foot('DPS',unseated.Damage); foot('Support',unseated.Support);
    if(un.length) body.appendChild(el(`<p class="note" style="margin-top:10px">Not scouted yet <span class="faint">(role shows once a player is captured)</span> — ${un.join(' · ')}</p>`));
  }
  // Leaderboard: pure FACEIT signal (elo + per-map averages), so unlike the hero
  // pools it is fully populated in every division, captured or not. Rate columns
  // carry a sample floor; counts and elo do not (see rankPlayers).
  function drawRanks(){
    body.innerHTML='';
    const col=LB_COLS.find(c=>c.k===PLAYERS_SORT)||LB_COLS[0];
    const ctl=el(`<div class="card controls" style="margin:0 0 10px"></div>`);
    const rsel=el(`<select>`+
      ['All','Tank','Damage','Support'].map(r=>`<option${r===PLAYERS_ROLE?' selected':''}>${r}</option>`).join('')+
      `</select>`);
    rsel.onchange=()=>{ PLAYERS_ROLE=rsel.value; drawRanks(); };
    ctl.append(el(`<label>Role</label>`), rsel,
      el(`<span class="note" style="margin:0">sorted by <b>${esc(col.label)}</b> · click a column to re-sort`+
         `${col.rate?` · needs ${LB_MIN_GAMES}+ maps`:''}</span>`));
    body.appendChild(ctl);
    const rows=rankPlayers(players,{key:PLAYERS_SORT,role:PLAYERS_ROLE});
    if(!rows.length){ body.appendChild(el(`<p class="note">No players with that stat yet.</p>`)); return; }
    const box=el(`<div class="scroll"></div>`);
    const tb=el(`<table class="compact"><thead><tr><th>#</th><th>Player</th><th>Team</th><th>Role</th><th>Top heroes</th>${statColTh(PLAYERS_SORT)}</tr></thead><tbody></tbody></table>`);
    const body2=tb.querySelector('tbody');
    rows.forEach((p,i)=>{
      const hs=topHeroes(p.cap,3);
      body2.appendChild(el(`<tr>`+
        `<td class="num faint">${i+1}</td>`+
        `<td><b>${esc(p.nick)}</b>${p.current?'':' <span class="faint" style="font-size:11px">sub</span>'}</td>`+
        `<td><span class="tlink" data-scout="${esc(p.team)}" style="display:flex;align-items:center;gap:6px">${teamAvatar(p.team,20)}${esc(p.team)}${capBtn(p.team)}</span></td>`+
        `<td><span class="dot bg-${esc(p.role||'')}"></span> <span class="faint">${esc(p.role||'—')}</span></td>`+
        `<td class="num">${hs.length?hs.map(x=>heroIconSmall(x.hero)).join(''):'<span class="faint">—</span>'}</td>`+
        statCells(p)+`</tr>`));
    });
    tb.querySelectorAll('th[data-k]').forEach(th=>{
      th.onclick=()=>{ PLAYERS_SORT=th.dataset.k; drawRanks(); }; });
    box.appendChild(tb); body.appendChild(box);   // [data-scout] clicks: global handler
    body.appendChild(el(`<p class="note" style="margin-top:8px">Elo is FACEIT's rating at the player's most recent map. `+
      `Averages are per map played across the whole season — they do not depend on anyone scouting the game. `+
      `Eff compares each player's per-map stats against the division's other players in the same role `+
      `(+1 = one standard deviation above the role average), averaged across the stats that vary within `+
      `that role — the d/h/m/k breakdown under the number. The peer group is their competitive role when `+
      `captured games place them in one, otherwise their base role. Strong teams post better lines: Eff does `+
      `not control for team strength.</p>`));
  }
  const draw=()=>{ [...modebar.children].forEach(b=>b.classList.toggle('selA', b.dataset.v===PLAYERS_VIEW));
    if(PLAYERS_VIEW==='role') drawRole(); else if(PLAYERS_VIEW==='rank') drawRanks(); else drawTeam(); };
  [['team','By team'],['role','By role'],['rank','Leaderboard']].forEach(([v,label])=>{
    const b=el(`<span class="wbtn" data-v="${v}">${esc(label)}</span>`);
    b.onclick=()=>{ PLAYERS_VIEW=v; draw(); }; modebar.appendChild(b);
  });
  draw();
  return wrap;
}

// Map-pick and ban tendencies for a team. limitGames>0 windows to that many of
// the team's MOST RECENT maps (newest match first, then latest map in it) so a
// shifting meta isn't buried under stale games; 0/undefined uses the full season.
// The math lives in the tested pure layer (simModelFrom above bootApp); this is
// just the bootApp-scoped data adapter.
function simModel(team, limitGames){
  return simModelFrom(D().matches, team, limitGames);
}
function divMaps(){
  const s=mapsFrom(D().matches);
  Object.keys(MAP_CAT).forEach(k=>{ if(!s[k]) s[k]=MAP_CAT[k]; });
  return s;
}
const ROLE_ORDER=['Tank','Damage','Support'];
// Full-roster hero picker (grouped by role), excluding heroes already banned by this team.
function heroSelect(current, illegal, onPick){
  const s=el(`<select class="herosel" style="min-width:148px;margin-left:4px"><option value="">+ any hero…</option></select>`);
  const groups={}; ROSTER.forEach(h=>{ const r=HERO_SEAT[h.name]||h.role||'Other'; (groups[r]=groups[r]||[]).push(h.name); });
  const order=[...SEATS.filter(r=>groups[r]), ...ROLE_ORDER.filter(r=>groups[r]),
               ...Object.keys(groups).filter(r=>!SEATS.includes(r)&&!ROLE_ORDER.includes(r)).sort()];
  order.forEach(r=>{ const og=el(`<optgroup label="${esc(r)}"></optgroup>`);
    groups[r].sort((a,b)=>a.localeCompare(b)).forEach(name=>{
      if(illegal.has(name)&&name!==current) return;
      og.appendChild(el(`<option ${name===current?'selected':''}>${esc(name)}</option>`)); });
    if(og.children.length) s.appendChild(og); });
  s.onchange=()=>onPick(s.value||null);
  return s;
}

function renderSim(){
  const wrap=el(`<div></div>`), tn=D().team_names, pool=divMaps();
  if(SIM_A==null){ SIM_A=tn[0]; SIM_B=tn[1]||tn[0]; }
  const nameOf=ab=>ab==='A'?SIM_A:SIM_B, opp=ab=>ab==='A'?'B':'A';
  const dbase=divBanBaseline();

  const ctl=el(`<div class="card controls" style="flex-wrap:wrap;gap:12px 16px"></div>`);
  const mkSel=(val,on)=>{ const s=el(`<select style="min-width:170px"></select>`); tn.forEach(n=>s.appendChild(el(`<option ${n===val?'selected':''}>${esc(n)}</option>`))); s.onchange=()=>on(s.value); return s; };
  ctl.appendChild(el(`<label>Team A</label>`));
  ctl.appendChild(mkSel(SIM_A,v=>{SIM_A=v;SIM_TREE={};SIM_FOCUS='';draw();}));
  ctl.appendChild(el(`<span class="faint" style="font-weight:800">vs</span>`));
  ctl.appendChild(el(`<label>Team B</label>`));
  ctl.appendChild(mkSel(SIM_B,v=>{SIM_B=v;SIM_TREE={};SIM_FOCUS='';draw();}));
  ctl.appendChild(el(`<label title="This team picks the Game 1 map and takes the first ban.">First pick &amp; ban</label>`));
  const fb=el(`<div class="wsel"></div>`);
  const fbBtn=ab=>{ const b=el(`<span class="wbtn ${SIM_FIRST===ab?(ab==='A'?'selA':'selB'):''}">${esc(nameOf(ab))}</span>`); b.onclick=()=>{SIM_FIRST=ab;SIM_TREE={};SIM_FOCUS='';draw();}; return b; };
  fb.append(fbBtn('A'),fbBtn('B')); ctl.appendChild(fb);
  ctl.appendChild(el(`<label title="Wins needed to take the series. Bo5 is the FACEIT default; playoff finals can be Bo7.">Format</label>`));
  const bo=el(`<div class="wsel"></div>`);
  [['Bo3',2],['Bo5',3],['Bo7',4]].forEach(([lbl,t])=>{ const b=el(`<span class="wbtn ${SIM_BO===t?'selA':''}" title="${lbl==='Bo7'?'Best of 7 — playoff finals':lbl==='Bo5'?'Best of 5 — regular default':'Best of 3'}">${lbl}</span>`); b.onclick=()=>{SIM_BO=t;SIM_FOCUS='';draw();}; bo.append(b); });
  ctl.appendChild(bo);
  ctl.appendChild(el(`<label title="How far back to read each team's BANS. Full season is most reliable; narrow it only to catch a very recent meta shift (a short window is sparse). Map picks always use the full season.">Ban window</label>`));
  const rw=el(`<select style="min-width:132px" title="How far back to read each team's bans."></select>`);
  [['Full season',0],['Last 12 games',12],['Last 6 games',6]].forEach(([lbl,v])=>rw.appendChild(el(`<option value="${v}" ${SIM_RECENT===v?'selected':''}>${lbl}</option>`)));
  rw.onchange=()=>{SIM_RECENT=+rw.value;draw();};
  ctl.appendChild(rw);
  const reset=el(`<span class="wbtn" style="margin-left:auto">↺ Reset edits</span>`); reset.onclick=()=>{SIM_TREE={};draw();};
  ctl.appendChild(reset);
  wrap.appendChild(ctl);
  // Compact legend — defines the chip counts and the ★ so the tree reads without
  // a wall of prose. (The procedural line "who picks Game 1" lives in draw(),
  // under the controls, so it reflects the First pick & ban toggle.)
  wrap.appendChild(el(`<div class="simlegend">
    <div><span class="pp">3×</span> on a map chip = times that team has picked it this season</div>
    <div><span class="pp">2× here · 5×</span> on a ban chip = bans on this map · this season</div>
    <div><span class="pp">★</span> = signature ban — repeated well above the division rate</div>
    <div>A team can't repeat its own ban down a line</div>
  </div>`));
  const body=el(`<div></div>`); wrap.appendChild(body);

  // Division map tendencies — the fallback when a team has no pick history for a
  // mode (common on G1 Control in a short window). Every game IS map-picked by a
  // team (the loser of the previous map; G1 by the first-pick team), so an empty
  // team window means "we don't know THEIR preference", not "nobody picks here".
  const divPick={}, divPlay={};
  D().matches.forEach(m=>m.games.forEach(g=>{ if(!g.map)return; inc(divPlay,g.map); if(g.map_picked_by) inc(divPick,g.map); }));
  // Map picks are a stable, season-long tendency (maps don't get buffed/nerfed
  // like heroes), so we rank and count them over the WHOLE season — the recent
  // window governs bans only. Season picks, then division picks, then raw plays.
  // League-wide type popularity (how often each non-Control mode is the pick).
  const divModePick={}; let divModeTot=0;
  Object.keys(divPick).forEach(mp=>{ const c=pool[mp]; if(c&&c!=='Control'){ divModePick[c]=(divModePick[c]||0)+divPick[mp]; divModeTot+=divPick[mp]; } });
  const modeShare=cat=>divModeTot? Math.round(100*(divModePick[cat]||0)/divModeTot) : 0;
  // Map choices as buttons (one per available map in a mode), each labelled with
  // how many times the picking team has chosen it this season. Selected highlighted.
  function mapButtons(cat, used, mf, current, onPick){
    const wrap=el(`<div class="mbtns"></div>`);
    Object.keys(pool).filter(mp=>pool[mp]===cat&&(!used.has(mp)||mp===current))
      .sort((a,b)=>mapCompare(a,b,mf.pick,divPick,divPlay))
      .forEach(mp=>{ const n=mf.pick[mp]||0;
        const o=el(`<span class="opt${mp===current?' sel':''}">${esc(mp)} <span class="pp">${n}×</span></span>`);
        o.onclick=()=>onPick(mp); wrap.appendChild(o); });
    return wrap;
  }
  // Ban choices as buttons — the team's most-banned heroes (recent window), each
  // with its ban count and ★ signature; a compact "any hero" dropdown covers the
  // long tail so the giant list isn't the primary interface.
  function banButtons(model, map, illegal, current, onPick){
    const wrap=el(`<div class="mbtns"></div>`);
    const sugg=banSuggest(model, map, illegal), shown=new Set();
    sugg.forEach(s=>{ shown.add(s.hero);
      const sig=sigMark(model,s.hero);
      // On-map count (their bans in this same situation) leads when present; the
      // total is their overall tendency. Both feed the "commonly banned here" read.
      // Format is defined in the sim legend: "N× here · M×" = this map · this season.
      const cnt = s.onMap>0 ? `${s.onMap}× here · ${s.all}×` : `${s.all}× total`;
      const o=el(`<span class="opt${s.hero===current?' sel':''}" title="${esc(s.hero)} — banned ${s.all}× overall${s.onMap?`, ${s.onMap}× on ${esc(map)}`:''}">${heroChip(s.hero)}<span class="pp">${cnt}</span>${sig}</span>`);
      o.onclick=()=>onPick(s.hero); wrap.appendChild(o); });
    if(current && !shown.has(current))
      wrap.appendChild(el(`<span class="opt sel">${heroChip(current)}<span class="pp">manual</span></span>`));
    wrap.appendChild(heroSelect(null, illegal, h=>{ if(h) onPick(h); }));
    return wrap;
  }
  // Signature ban: the pure sigLift decision rendered as the ★ mark on a chip.
  function sigMark(model,hero){ if(!hero)return '';
    const s=sigLift(model,dbase,hero);
    return s.sig?`<span class="pp" style="color:var(--good)" title="Signature ban — ${s.bans}× banned, well above the division rate">★</span>`:''; }
  function setOv(path,patch){ SIM_TREE[path]=Object.assign({},SIM_TREE[path],patch); draw(); }
  // True when a map is this team's most-picked within its mode — backs the
  // explainer's "most-picked [mode]" claim so it's only ever said when true.
  const isTopMapInCat = (mf, mp)=> (mf.pick[mp]||0)>0 && Object.keys(pool)
    .filter(x=>pool[x]===pool[mp]).every(x=> (mf.pick[mp]||0) >= (mf.pick[x]||0));

  function draw(){
    body.innerHTML='';
    if(SIM_A===SIM_B){ body.appendChild(el(`<p class="note" style="margin-top:14px">Pick two different teams.</p>`)); return; }
    const A=simModel(SIM_A,SIM_RECENT), B=simModel(SIM_B,SIM_RECENT), modelOf=ab=>ab==='A'?A:B, target=SIM_BO;
    // #simfull deep link: render the whole tree expanded on first draw. allOpen()
    // is declared below in this same scope, so this consumes it before the nodes
    // are drawn and never re-runs (the flag is one-shot).
    if(SIM_OPEN_ALL){ SIM_OPEN=allOpen(); SIM_FOCUS=''; SIM_OPEN_ALL=false; }
    // Full-season models back the suggestion when the recent window is silent.
    const Af=simModel(SIM_A,0), Bf=simModel(SIM_B,0), modelFull=ab=>ab==='A'?Af:Bf;
    // Evidence for the "why" strips: every gk key the models tracked resolves
    // against this lookup (built over the same match list the models read).
    const lookup=codeLookup(D().matches, SIM_A, CODE_WIPE);
    // Transparent about the window: show how many recent maps actually informed each side.
    let status = SIM_RECENT>0
      ? `<b>Ban</b> reads use the most recent ${SIM_RECENT} maps — <b>${esc(SIM_A)}</b> ${A.ngames} · <b>${esc(SIM_B)}</b> ${B.ngames}. Map picks stay full-season.`
      : `Reads use each team's <b>full-season</b> record — <b>${esc(SIM_A)}</b> ${A.ngames} maps · <b>${esc(SIM_B)}</b> ${B.ngames}.`;
    // Weak-sample honesty: below the window (or below SIM_MIN_MAPS on full-season)
    // the bans read is a hint, not a pattern — say so instead of letting a small
    // n look as strong as a big one.
    const under = m => m.ngames < (SIM_RECENT>0? SIM_RECENT : SIM_MIN_MAPS);
    if(under(A)||under(B)){
      const bits=[];
      if(under(A)) bits.push(SIM_RECENT>0
        ? `only <b>${A.ngames}</b> of the last ${SIM_RECENT} games on record for <b>${esc(SIM_A)}</b>`
        : `<b>${esc(SIM_A)}</b> has only ${A.ngames} map${A.ngames===1?'':'s'} of history`);
      if(under(B)) bits.push(SIM_RECENT>0
        ? `only <b>${B.ngames}</b> of the last ${SIM_RECENT} games on record for <b>${esc(SIM_B)}</b>`
        : `<b>${esc(SIM_B)}</b> has only ${B.ngames} map${B.ngames===1?'':'s'} of history`);
      status += ` ${bits.join(' · ')} — this read is a <b>hint</b>, not a pattern.`;
    }
    body.appendChild(el(`<p class="note" style="margin:8px 2px 0"><b>${esc(nameOf(SIM_FIRST))}</b> picks Game 1 and bans first. The loser of each map picks the next one.</p>`));
    body.appendChild(el(`<p class="note" style="margin:4px 2px 0">${status}</p>`));

    // Recursively draw the draft at `path` (string of prior winners) plus its two branches.
    // used = maps already taken on this line; banned = {A:Set,B:Set} of each team's earlier bans.
    function node(path, used, banned){
      const k=path.length;
      const sa=[...path].filter(c=>c==='A').length, sb=k-sa;
      const picker = k===0? SIM_FIRST : opp(path[k-1]);
      const other = opp(picker);
      const ov = SIM_TREE[path]||{};
      const g1 = (k===0);
      const mw=modelOf(picker), mf=modelFull(picker);

      // Resolve the map + both bans first — the compact view needs them too, and
      // they feed the child branches (one map per mode; no repeat bans down a line).
      const allowedCats=allowedCatsFor(g1,used,pool);
      const map = (ov.map && !used.has(ov.map) && allowedCats.includes(pool[ov.map])) ? ov.map : autoMap(mf.pick,divPick,divPlay,allowedCats,used,pool);
      const ill1=banned[picker], ill2=banned[other];
      let b1=null,b2=null;
      if(map){
        b1 = (ov.b1 && !ill1.has(ov.b1)) ? ov.b1 : autoBan(modelOf(picker),map,ill1);
        b2 = (ov.b2 && !ill2.has(ov.b2)) ? ov.b2 : autoBan(modelOf(other),map,ill2);
      }

      const focused = (path===SIM_FOCUS);
      const stn=el(`<div class="stnode"></div>`);

      if(focused){
        // Full, editable card — the game you're actively planning.
        const card=el(`<div class="snode focus${g1?' g1':''}"></div>`); stn.appendChild(card);
        card.appendChild(el(`<div class="snhd"><span class="gno">M${k+1}</span> <b>${esc(nameOf(picker))}</b> pick &amp; ban first`+
          `<span class="simscore faint" style="margin-left:auto">series ${sa}–${sb}${g1?' · G1 Control':''}</span></div>`));
        // Plain-language "why" for whatever is currently selected (auto or user-
        // overridden). isTop* claims are measured against the legal suggestion set
        // so an override is never mislabelled as "the most".
        const mfNow = modelOf(picker);
        const selMap = map;
        const mapWhy = selMap? mapExplain(nameOf(picker), selMap, pool[selMap],
          mfNow.pick[selMap]||0, divPick[selMap]||0, isTopMapInCat(mfNow, selMap)) : null;
        const banWhy = (model, hero, ill)=>{
          const all = model.bansAll[hero]||0, onMap = (model.banByMap[selMap]||{})[hero]||0;
          const maxAll = Math.max(0, ...Object.entries(model.bansAll||{})
            .filter(([h])=>!ill.has(h)).map(([,n])=>n));
          const maxOnMap = Math.max(0, ...Object.entries(model.banByMap[selMap]||{})
            .filter(([h])=>!ill.has(h)).map(([,n])=>n));
          const isTopOverall = all>0 && all===maxAll;
          const isTopOnMap = onMap>0 && onMap===maxOnMap;
          const sig = sigLift(model, dbase, hero).sig;
          return banExplain(nameOf(model===A?'A':'B'), selMap, hero, all, onMap,
            isTopOverall, isTopOnMap, sig);
        };
        if(g1){
          // Game 1 is always Control: pick straight from the three maps, each
          // labelled with how many times this team has chosen it.
          const mrow=el(`<div class="snrow"><span class="rl2">Map · Control</span></div>`);
          mrow.appendChild(mapButtons('Control', used, mf, map, mp=>setOv(path,{map:mp,b1:null,b2:null})));
          card.appendChild(mrow);
        } else {
          // Later games: choose the map TYPE first (with league popularity), then
          // the specific map from that type's buttons.
          const curCat = map? pool[map] : allowedCats[0];
          const trow=el(`<div class="snrow"><span class="rl2">Map type</span></div>`);
          const tsel=el(`<select class="herosel" style="min-width:170px" title="How often teams pick each type"></select>`);
          allowedCats.forEach(cat=>tsel.appendChild(el(`<option value="${esc(cat)}" ${cat===curCat?'selected':''}>${esc(cat)} · ${modeShare(cat)}% of picks</option>`)));
          tsel.onchange=()=>{ const top=autoMap(mf.pick,divPick,divPlay,[tsel.value],used,pool); if(top) setOv(path,{map:top,b1:null,b2:null}); };
          trow.appendChild(tsel);
          card.appendChild(trow);
          const mrow=el(`<div class="snrow"><span class="rl2">Map</span></div>`);
          mrow.appendChild(mapButtons(curCat, used, mf, map, mp=>setOv(path,{map:mp,b1:null,b2:null})));
          card.appendChild(mrow);
        }
        // Why this map? Map picks are full-season, so the evidence comes from the
        // full-season model; games with no replay code simply show no codes cell.
        if(mapWhy){
          const ev=codesFor(modelFull(picker).gkPick[selMap]||new Set(), lookup);
          card.appendChild(el(`<p class="whyline">Why <b>${esc(selMap)}</b>? ${esc(mapWhy.text)}${mapWhy.thin?` <span class="thin">— a single case, not a pattern</span>`:''}${ev.length?' '+codesCell(ev):''}</p>`));
        }
        if(map){
          const r1=el(`<div class="snrow"><span class="rl2">${esc(nameOf(picker))} ban</span></div>`);
          r1.appendChild(banButtons(modelOf(picker), map, ill1, b1, h=>setOv(path,{b1:h})));
          card.appendChild(r1);
          const r2=el(`<div class="snrow"><span class="rl2">${esc(nameOf(other))} ban</span></div>`);
          r2.appendChild(banButtons(modelOf(other), map, ill2, b2, h=>setOv(path,{b2:h})));
          card.appendChild(r2);
        }
        // Why each ban? Bans use the recent-window model (matching the chip counts);
        // evidence prefers the on-map set, falling back to the overall set.
        const whyRow = (hero, model, ill)=>{
          const e = hero? banWhy(model, hero, ill) : null;
          if(!e) return '';
          const ev=codesFor(((model.gkBanMap[selMap]||{})[hero])||(model.gkBanAll[hero]||new Set()), lookup);
          return `<p class="whyline">Why <b>${heroChip(hero)}</b>? ${esc(e.text)}${e.thin?` <span class="thin">— a single case, not a pattern</span>`:''}${ev.length?' '+codesCell(ev):''}</p>`;
        };
        card.appendChild(el(whyRow(b1, modelOf(picker), ill1)));
        card.appendChild(el(whyRow(b2, modelOf(other), ill2)));
      } else {
        // Condensed — one glance-able row. Click to bring it into focus.
        const mini=el(`<div class="snode mini" title="Click to edit this game"></div>`);
        mini.innerHTML=`<span class="gno">M${k+1}</span> <b>${esc(nameOf(picker))}</b>`+
          `<span class="mmap">${esc(map||'—')}</span>`+(map?` <span class="tag">${esc(pool[map]||'')}</span>`:'')+
          (map?`<span class="mbans">${heroChip(b1)}${heroChip(b2)}</span>`:'')+
          `<span class="faint mini-x" style="margin-left:auto">${sa}–${sb} · edit ✎</span>`;
        mini.onclick=()=>{ SIM_FOCUS=path; draw(); };
        stn.appendChild(mini);
      }

      // Win/lose fork. Expanding drills into that line AND focuses the new game;
      // collapsing hands focus back to this node. Bans made here carry into both.
      if(map){
        const childUsed=new Set(used); childUsed.add(map);
        const nb={A:new Set(banned.A),B:new Set(banned.B)};
        if(b1) nb[picker].add(b1);
        if(b2) nb[other].add(b2);
        ['A','B'].forEach(w=>{
          const cp=path+w, nsa=sa+(w==='A'?1:0), nsb=sb+(w==='B'?1:0), cls=w==='A'?'awin':'bwin';
          const br=el(`<div class="sbranch"></div>`); stn.appendChild(br);
          if(nsa>=target||nsb>=target){
            br.appendChild(el(`<div class="sterm ${cls}">🏆 ${esc(nameOf(w))} win the series ${Math.max(nsa,nsb)}–${Math.min(nsa,nsb)}</div>`));
          } else {
            const open=SIM_OPEN.has(cp);
            const tog=el(`<button type="button" class="btgl ${cls}${open?' open':''}"><span class="cv">${open?'▾':'▸'}</span> ${esc(nameOf(w))} win · ${nsa}–${nsb}</button>`);
            tog.onclick=()=>{ if(open){ SIM_OPEN.delete(cp); if(SIM_FOCUS.startsWith(cp)) SIM_FOCUS=path; } else { SIM_OPEN.add(cp); SIM_FOCUS=cp; } draw(); };
            br.appendChild(tog);
            if(open){ const kids=el(`<div class="skids"></div>`); kids.appendChild(node(cp, childUsed, nb)); br.appendChild(kids); }
          }
        });
      }
      return stn;
    }

    // Expand-all / collapse-all: every openable branch is a binary string of
    // winners whose A- and B-counts are both still below target.
    function allOpen(){ const out=new Set(), q=['']; while(q.length){ const p=q.shift();
      const a=[...p].filter(c=>c==='A').length, b=p.length-a;
      ['A','B'].forEach(w=>{ const cp=p+w, na=a+(w==='A'?1:0), nb=b+(w==='B'?1:0);
        if(na<target&&nb<target){ out.add(cp); q.push(cp); } }); } return out; }
    // Keep focus on a reachable node: every step of its path must be an open
    // branch (root '' is always shown). Trims a stale focus after collapses.
    { let f=''; for(const ch of SIM_FOCUS){ const nx=f+ch; if(SIM_OPEN.has(nx)) f=nx; else break; } SIM_FOCUS=f; }

    // Expand-all / collapse-all: every openable branch is a binary string of
    // winners whose A- and B-counts are both still below target.
    function allOpen(){ const out=new Set(), q=['']; while(q.length){ const p=q.shift();
      const a=[...p].filter(c=>c==='A').length, b=p.length-a;
      ['A','B'].forEach(w=>{ const cp=p+w, na=a+(w==='A'?1:0), nb=b+(w==='B'?1:0);
        if(na<target&&nb<target){ out.add(cp); q.push(cp); } }); } return out; }
    const hdr=el(`<div style="display:flex;align-items:center;gap:10px;margin:12px 2px 2px"><span class="eyebrow" style="margin:0">Series scenarios · Bo${target*2-1}</span><span style="margin-left:auto;display:flex;gap:6px"></span></div>`);
    const acts=hdr.lastChild;
    const bExp=el(`<span class="wbtn" style="font-size:11.5px;padding:4px 10px">Expand all</span>`); bExp.onclick=()=>{SIM_OPEN=allOpen();draw();};
    const bCol=el(`<span class="wbtn" style="font-size:11.5px;padding:4px 10px">Collapse all</span>`); bCol.onclick=()=>{SIM_OPEN=new Set();SIM_FOCUS='';draw();};
    acts.append(bExp,bCol); body.appendChild(hdr);

    const tree=el(`<div class="stree"></div>`);
    tree.appendChild(node('', new Set(), {A:new Set(),B:new Set()}));
    body.appendChild(tree);
  }
  draw();
  return wrap;
}

function renderMeta(){
  const wrap=el(`<div></div>`);
  const bar=el(`<div class="card controls"></div>`);
  bar.appendChild(el(`<label>Recent matches</label>`));
  const metaTotal=Math.max(1,MATCHES_RECENT.length);
  if(META_N!=null && META_N>metaTotal) META_N=null;
  bar.appendChild(makeRecency(metaTotal, META_N==null?metaTotal:META_N, n=>{META_N=n;draw();}));
  bar.appendChild(el(`<span class="note">a nerfed hero fades from recent windows</span>`));
  const body=el(`<div></div>`); wrap.append(bar,body);
  function draw(){
    const ms=recent(MATCHES_RECENT,META_N), a=aggregate(ms,null), {from,to}=dateRange(ms);
    body.innerHTML='';
    const v=el(`<div></div>`);
    v.appendChild(el(`<p class="note">${ms.length<MATCHES_RECENT.length?`last ${ms.length} of ${MATCHES_RECENT.length}`:`all ${ms.length}`} matches · ${dshort(from)} → ${dshort(to)}</p>`));
    const two=el(`<div class="grid cols-2 mt8"></div>`);
    const bc=el(`<div class="card"></div>`); bc.appendChild(el(`<p class="eyebrow">Most banned</p>`));
    bc.appendChild(el(barList(rank(a.bans).slice(0,16).map(([h,n])=>({label:heroChip(h),value:n,color:roleVar(HERO_ROLE[h])})))));
    const rc=el(`<div class="card"></div>`); rc.appendChild(el(`<p class="eyebrow">Bans by role</p>`));
    rc.appendChild(el(barList(rank(a.banRoles).map(([r,n])=>({label:`<span class="role-${esc(r)}">${esc(r)}</span>`,value:n,color:roleVar(r)})))));
    rc.appendChild(el(`<p class="eyebrow" style="margin-top:18px">Most played maps</p>`));
    rc.appendChild(el(barList(rank(a.mapsPicked).slice(0,10).map(([m,n])=>({label:`${esc(m)} ${tag(MAP_CAT[m]||'')}`,value:n})))));
    two.append(bc,rc); v.appendChild(two);
    body.appendChild(v);
  }
  draw();

  // Most-played comps across the league (captured openings). Aggregated by exact
  // 5-hero identity across every team; capture-gated, so honest when thin.
  {
    // Replay codes/map identity for this aggregate come from team_scout's
    // per-team `overall` families (scout.overall[].game_keys, same source
    // Scout a team's Common comps uses) - matched to the derive.py comp stats
    // above by the same sorted-hero-set key. Two different aggregation
    // pipelines over the same captures; a key that doesn't match just means
    // no map breakdown for that row, not a crash.
    const lookupLM=codeLookup(MATCHES_RECENT, null);
    const agg={};
    D().team_names.forEach(team=>{
      const ovByKey={};
      (((DATA.owdb_comps||{})[team]||{}).scout||{}).overall?.forEach(f=>{
        ovByKey[[...f.heroes].sort().join(',')]=f; });
      (((DATA.owdb_comps||{})[team]||{}).comps||[]).forEach(c=>{
        const key=[...c.heroes].sort().join(',');
        const a=agg[key]||(agg[key]={heroes:c.heroes,maps:0,games:0,wins:0,teams:new Set(),gks:new Set()});
        a.maps+=c.maps||0; a.games+=c.games||0; a.wins+=c.wins||0; a.teams.add(team);
        const fam=ovByKey[key];
        if(fam&&fam.game_keys) fam.game_keys.forEach(k=>a.gks.add(k));
      });
    });
    const rows=Object.values(agg).sort((a,b)=>b.maps-a.maps).slice(0,12);
    wrap.appendChild(el(sectionH('Most-played comps',`<span class="note">captured openings across the league · win% shown at 3+ maps${capSince()}</span>`)));
    if(rows.length){
      const card=el(`<div class="card"></div>`);
      rows.forEach(r=>{
        const codes=codesFor([...r.gks],lookupLM);
        const mapTally={};
        codes.forEach(c=>{ if(c.map) mapTally[c.map]=(mapTally[c.map]||0)+1; });
        const mapBreak=Object.entries(mapTally).sort((a,b)=>b[1]-a[1]).map(([m,n])=>`${esc(m)} ${n}×`).join(' · ');
        card.appendChild(el(`<div class="crow${r.maps<=1?' thin':''}"><span>${compRow(r.heroes)}</span>`+
          `<span class="rec">${r.maps} map${r.maps===1?'':'s'} · ${r.teams.size} team${r.teams.size===1?'':'s'}`+
          `${r.maps>=3?` · won ${Math.round(100*r.wins/(r.games||1))}%`:''} · ${codesCell(codes)}</span></div>`));
        if(mapBreak) card.appendChild(el(`<p class="note" style="margin:0 0 8px;padding-left:2px">played on: ${mapBreak}</p>`));
      });
      wrap.appendChild(card);
    } else {
      wrap.appendChild(el(`<p class="note">No comps captured yet — this fills in as games are scouted.</p>`));
    }
  }

  // What actually wins, next to what gets banned. Same captured sample as the
  // comps above, joined to the match result - so it carries the same caveats and
  // a hard sample floor (a hero seen 4 times has no win rate worth printing).
  {
    // Only this view's matches carry a winner, which scopes the whole table to
    // the selected division without filtering the league-wide capture blob.
    const winnerOf={};
    D().matches.forEach(m=>(m.games||[]).forEach(g=>{
      if(g.winner_team) winnerOf[m.id+':'+g.game_no]=g.winner_team;
    }));
    const rows=heroWinRates(DATA.owdb_pergame||{},winnerOf,{minMaps:HERO_WR_MIN});
    wrap.appendChild(el(sectionH('Hero win rates',
      `<span class="note">map win rate across captured maps · ${HERO_WR_MIN}+ maps to qualify · counted once per map a hero appears on${capSince()}</span>`)));
    if(rows.length){
      const card=el(`<div class="card"></div>`);
      rows.slice(0,18).forEach(r=>card.appendChild(el(`<div class="crow">`+
        `<span>${heroChip(r.hero)}</span>`+
        `<span class="rec">${r.wins}/${r.maps} · ${pill(r.wr+'%',winVar(r.wr))}</span></div>`)));
      wrap.appendChild(card);
    } else {
      wrap.appendChild(el(`<p class="note">Not enough captured maps yet — no hero in this division clears ${HERO_WR_MIN} maps.</p>`));
    }
  }

  // Current map pool, grouped by mode the way FACEIT lays out the veto pool.
  const MODE_ORDER=['Control','Escort','Flashpoint','Hybrid','Push','Clash'];
  const pool={};
  D().matches.forEach(m=>m.games.forEach(g=>{
    if(!g.map) return;
    const cat=MAP_CAT[g.map]||g.map_category||'—';
    (pool[cat]=pool[cat]||{}); const e=pool[cat][g.map]||(pool[cat][g.map]={picks:0,plays:0});
    e.plays++; if(g.map_picked_by) e.picks++;
  }));
  const cats=Object.keys(pool).sort((a,b)=>{const i=MODE_ORDER.indexOf(a),j=MODE_ORDER.indexOf(b);return (i<0?99:i)-(j<0?99:j)||a.localeCompare(b);});
  const poolPicks=cats.reduce((s,c)=>s+Object.values(pool[c]).reduce((x,e)=>x+e.picks,0),0);
  wrap.appendChild(el(sectionH('Map pool — picks by mode',`<span class="note">${cats.reduce((s,c)=>s+Object.keys(pool[c]).length,0)} maps · ${poolPicks} picks · all season</span>`)));
  const pg=el(`<div class="grid poolgrid"></div>`);
  cats.forEach(c=>{
    const maps=Object.entries(pool[c]).map(([m,e])=>({map:m,picks:e.picks,plays:e.plays})).sort((a,b)=>b.picks-a.picks||b.plays-a.plays);
    const tot=maps.reduce((s,m)=>s+m.picks,0);
    const card=el(`<div class="card"></div>`);
    card.appendChild(el(`<p class="eyebrow">${esc(c)} <span class="note">${tot} pick${tot===1?'':'s'}</span></p>`));
    card.appendChild(el(`<div>`+maps.map(m=>
      `<div class="poolrow"><span class="pm">${esc(m.map)}</span>`+
      `<span class="pr"><span class="pk">${m.picks}</span><span class="pp">${m.plays} played</span></span></div>`).join('')+`</div>`));
    pg.appendChild(card);
  });
  wrap.appendChild(pg);

  // Attacking-first advantage, by the DECIDING attack/defend cycle (round 1
  // normally, round 3 when it went long). Two panels: all games, and the long
  // games only. Mirrored modes (Control/Flashpoint/Push) have no attacker.
  const afPanel=(af,title,note)=>{
    wrap.appendChild(el(sectionH(title,`<span class="note">${note}</span>`)));
    if(!af||!af.total_games){ wrap.appendChild(el(`<p class="note" style="margin-top:0">No decidable games yet — extra-round games need a scouting capture to know the round-3 attacker.</p>`)); return; }
    wrap.appendChild(el(`<p class="note" style="margin-top:0">The team that attacked first in the deciding cycle won <b>${af.atk_first_wins}/${af.total_games}</b> = <b>${pctOf(af.atk_first_wins,af.total_games)}%</b>.</p>`));
    wrap.appendChild(table(
      [{k:'name',label:'Map'},{k:'games',label:'Maps',num:true},
       {k:'wr',label:'Atk-first win %',num:true,html:r=>pill(r.wr+'%',winVar(r.wr))}],
      af.by_map.map(m=>({...m,map:m.name,wr:pctOf(m.atk_first_wins,m.games)}))
        .sort((a,b)=>mapCmp(a.map,b.map)), byMode));
  };
  afPanel(D().attacking_first,'Attacking-first advantage',
    'Escort &amp; Hybrid · deciding attack/defend cycle · uncaptured extra-round games excluded');
  afPanel(D().attacking_first_extra,'Attacking-first — extra rounds only',
    'Escort &amp; Hybrid games that went to rounds 3/4 · round-3 attacker, from scouting captures'+capSince());
  return wrap;
}

function renderMatches(){
  const wrap=el(`<div></div>`);
  const bar=el(`<div class="card controls"></div>`);
  // Region + Division filters (FACEIT-style). They drive the shared division
  // view, so the rest of the page follows and the header switcher stays in sync.
  const suffix=(v)=> v.region? v.label.slice(v.region.length+1) : v.label;   // "Master"/"Combined"
  const regions=[...new Set(VIEWS.map(v=>v.region).filter(Boolean))];
  const curRegion=(viewOf(CURRENT_VIEW).region)||regions[0];
  const regSel=el(`<select title="Region"></select>`);
  regions.forEach(r=>regSel.appendChild(el(`<option${r===curRegion?' selected':''}>${esc(r)}</option>`)));
  const divSel=el(`<select title="Division"></select>`);
  const fillDivs=()=>{ divSel.innerHTML='';
    VIEWS.filter(v=>v.region===regSel.value).forEach(v=>
      divSel.appendChild(el(`<option value="${v.id}"${v.id===CURRENT_VIEW?' selected':''}>${esc(suffix(v))}</option>`))); };
  fillDivs();
  regSel.onchange=()=>{ const f=VIEWS.find(v=>v.region===regSel.value); if(f) setDivision(f.id); };
  divSel.onchange=()=>setDivision(divSel.value);
  if(regions.length) bar.appendChild(regSel);
  if(VIEWS.length>1) bar.appendChild(divSel);
  const search=el(`<input placeholder="search team, player, hero, or map…" style="flex:1;min-width:200px">`);
  const sort=el(`<select title="Sort by date"><option value="new">Newest first</option><option value="old">Oldest first</option></select>`);
  bar.append(search,sort);
  // Played history vs upcoming fixtures vs the playoff bracket. A full-season
  // schedule can be large, so each lives in its own view (toggle) rather than
  // stacked on the results. Default mode is a real decision (defaultMatchesMode,
  // declared above bootApp) so it's independently testable.
  const up0=D().upcoming||[];
  if(!MATCHES_MODE_SET){ MATCHES_MODE=defaultMatchesMode(D().playoffs||[]); MATCHES_MODE_SET=true; }
  const modeBar=el(`<div class="wsel" style="margin:12px 2px 12px"></div>`);
  const mkMode=(m,lbl)=>{ const b=el(`<span class="wbtn">${lbl}</span>`); b.onclick=()=>{ MATCHES_MODE=m; MATCHES_MODE_SET=true; draw(); }; return b; };
  modeBar.append(mkMode('played','Played'), mkMode('upcoming',`Upcoming${up0.length?' · '+up0.length:''}`), mkMode('playoffs','Playoffs'));
  // In a single round-robin every team has faced the same opponents, so a team's
  // full match list reads as their "book" against a field you already know -
  // search a team to see exactly how they drafted vs each opponent you also play.
  const note=el(`<p class="note" style="margin:0 2px 10px">Single round-robin — everyone plays the same 15 opponents. Search a team, player, hero, or map to read their book against the field.</p>`);
  const list=el(`<div></div>`); wrap.append(bar,modeBar,note,list);
  const hay=(m)=>[m.f1,m.f2,...m.games.flatMap(g=>{
    const pg=(DATA.owdb_pergame||{})[m.id+':'+g.game_no];
    const compHeroes=pg?Object.values(pg).flatMap(segs=>Object.values(segs).flat()):[];
    return [g.map,...g.bans.map(b=>b.hero),...compHeroes,...(g.rosters||[]).flatMap(r=>r.players.map(p=>p.nick))];
  })].filter(Boolean).join(' ').toLowerCase();
  function drawUpcoming(q){
    let up=(D().upcoming||[]);
    if(q) up=up.filter(u=>((u.f1||'')+' '+(u.f2||'')).toLowerCase().includes(q));
    if(!up.length){ list.appendChild(el(`<p class="note">No upcoming fixtures${q?' match your search':''}.</p>`)); return; }
    // A season schedule reads best grouped by round.
    const byR={}; up.forEach(u=>{ const r=u.round||0; (byR[r]=byR[r]||[]).push(u); });
    Object.keys(byR).map(Number).sort((a,b)=>a-b).forEach(r=>{
      list.appendChild(el(`<p class="eyebrow" style="margin:12px 2px 6px">Round ${r||'—'} · ${byR[r].length}</p>`));
      const rows=el(`<div class="uprows"></div>`);
      byR[r].sort((a,b)=>String(a.scheduled_at||'').localeCompare(String(b.scheduled_at||''))).forEach(u=>{
        const f1=u.f1?teamLink(u.f1):'<span class="faint">TBD</span>';
        const f2=u.f2?teamLink(u.f2):'<span class="faint">TBD</span>';
        rows.appendChild(el(`<div class="uprow"><span class="uptime">${u.scheduled_at?fmtWhen(u.scheduled_at):'time TBD'}</span>`+
          `<span class="upteams">${f1}<span class="upvs">vs</span>${f2}</span>`+
          `<span class="uptag">${u.best_of?('Bo'+u.best_of):''}</span></div>`));
      });
      list.appendChild(rows);
    });
  }
  function drawPlayed(q){
    // MATCHES_RECENT is newest-first (regular season). Finished playoff matches
    // join the list tagged — the Played tab reads as one full season history,
    // and their cards deep-link to the same match pages as the bracket.
    let shown=MATCHES_RECENT.concat((D().playoffs||[]).filter(m=>m.status==='FINISHED'))
      .sort((a,b)=>{const x=a.finished_at||'',y=b.finished_at||'';return x===y?0:(x<y?1:-1);})
      .filter(m=>!q||hay(m).includes(q));
    if(sort.value==='old') shown=[...shown].reverse();
    if(!shown.length){ list.appendChild(el(`<p class="note">No played matches${q?' match your search':''}.</p>`)); return; }
    const grid=el(`<div class="matches-grid"></div>`);
    shown.forEach(m=>grid.appendChild(matchCard(m,{showComps:true})));
    list.appendChild(grid);
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
  search.oninput=draw; sort.onchange=draw; draw(); return wrap;
}

/* ---------- shell ---------- */
// The scout tab's hash carries the team, so a prep link pasted in Discord lands
// a teammate directly on the right page: site/#scout=Redline
function hashFor(id){
  if(id==='matchdetail'&&MATCH_ID) return 'match='+encodeURIComponent(MATCH_ID);
  if(id==='compare'&&COMPARE_A&&COMPARE_B) return 'compare='+encodeURIComponent(COMPARE_A+'|'+COMPARE_B);
  if(id==='scout'&&SCOUT_TEAM) return (SCOUT_PREP?'prep=':'scout=')+encodeURIComponent(SCOUT_TEAM);
  return id;
}
// Browser back/forward: the hash is the source of truth for which screen we're
// on. show() renders + syncs the hash; hashchange drives the reverse direction
// (back/forward buttons, edited or pasted URLs). HANDLED_HASH keeps show()'s own
// hash write from re-rendering itself in a loop.
let HANDLED_HASH='';
function hashDispatch(){
  const h=location.hash||'#overview';
  if(h===HANDLED_HASH) return;
  HANDLED_HASH=h;
  const start=decodeURIComponent(h.slice(1));
  if(start.startsWith('prep=')||start.startsWith('scout=')){
    SCOUT_PREP=start.startsWith('prep=');
  }
  if(start.startsWith('prep=')){
    const team=start.slice(5);
    for(const v of VIEWS){
      if(v.divisions.length===1 && (DIVS[v.divisions[0]].team_names||[]).includes(team)){
        CURRENT_VIEW=v.id; recomputeDivision(); updateHeader();
        document.getElementById('division').value=v.id; break;
      }
    }
    if((D().team_names||[]).includes(team)){ SCOUT_TEAM=team; show('scout'); return; }
  }
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
  if(start.startsWith('compare=')){
    // Two team names, '|'-separated. Same-division scope: B resolving against a
    // different division (or a stale name) is a note on the page, never a guess.
    const parts=start.slice(8).split('|');
    const a=parts[0]||'', b=parts[1]||'';
    for(const v of VIEWS){
      if(v.divisions.length===1 && (DIVS[v.divisions[0]].team_names||[]).includes(a)){
        CURRENT_VIEW=v.id; recomputeDivision(); updateHeader();
        document.getElementById('division').value=v.id;
        break;
      }
    }
    COMPARE_A=(D().team_names||[]).includes(a)?a:null;
    COMPARE_B=(D().team_names||[]).includes(b)?b:null;
    if(!COMPARE_A&&!COMPARE_B){ show(TABS.some(t=>t.id===start)?start:'overview'); return; }
    show('compare'); return;
  }
  // 'playoffs' and 'sim' were their own tabs before this redesign; a link
  // bookmarked from before still needs to resolve to real content, not fall
  // through to Overview.
  if(start==='playoffs'){ MATCHES_MODE='playoffs'; MATCHES_MODE_SET=true; show('matches'); return; }
  if(start==='sim'){ SCOUT_PREP=false; SCOUT_SIM_OPEN=true; show('scout'); return; }
  if(start==='simfull'){ SCOUT_PREP=false; SCOUT_SIM_OPEN=true; SIM_OPEN_ALL=true; show('scout'); return; }
  show(TABS.some(t=>t.id===start)?start:'overview');
}
function show(id){
  const navId = (id==='matchdetail'?'matches':(id==='compare'?'scout':id));   // drill-ins: no nav entry of their own - they hang off Matches / Teams
  document.querySelectorAll('nav button').forEach(b=>b.classList.toggle('active',b.dataset.id===navId));
  const heroScout=document.getElementById('heroScout');
  if(heroScout) heroScout.classList.toggle('hidden', navId==='scout');   // already scouting on this tab - the button would just re-open it
  const c=document.getElementById('content'); c.innerHTML='';
  if(id==='matchdetail'){
    const m=findMatch(MATCH_ID);
    if(!m){ show('matches'); return; }   // stale/unresolvable link - land on the list, not a blank page
    c.appendChild(renderMatchDetail(m));
  } else if(id==='compare'){
    c.appendChild(renderCompare());
  } else {
    c.appendChild(TABS.find(t=>t.id===id).render());
  }
  try{window.scrollTo(0,0)}catch(e){}
  const h=hashFor(id); if(location.hash!=='#'+h){ HANDLED_HASH='#'+h; location.hash=h; }
}
function updateHeader(){
  const s=D().summary;
  document.getElementById('title').textContent=s.championship;
  const sub=document.getElementById('subtitle');
  sub.textContent=`${s.matches} matches · ${s.played_games} maps · ${dshort(s.date_from)} → ${dshort(s.date_to)}`+(DATA.built_at?` · built ${dshort(DATA.built_at)}`:'');
  // On-demand refresh: the page is static, so the button asks the upload worker
  // to start a rebuild - which pulls new FACEIT matches, re-merges every
  // contribution and republishes. ~2 minutes, then reload.
  if(DATA.refresh_endpoint && !document.getElementById('refreshbtn')){
    const b=el(`<button class="sortbtn" id="refreshbtn" type="button" style="margin-left:10px">Fetch new matches</button>`);
    b.onclick=async()=>{
      b.disabled=true; const was=b.textContent; b.textContent='starting…';
      try{
        const r=await fetch(DATA.refresh_endpoint,{method:'POST'});
        const j=await r.json().catch(()=>({}));
        if(r.ok){
          b.textContent='building - reload in ~2 min';
        } else {
          b.textContent=j.error||'could not start';
          setTimeout(()=>{b.textContent=was;b.disabled=false;}, 6000);
        }
      }catch(e){
        b.textContent='offline'; setTimeout(()=>{b.textContent=was;b.disabled=false;},6000);
      }
    };
    sub.appendChild(b);
  }
}
function setDivision(id){
  CURRENT_VIEW=id; rememberDivision(id); recomputeDivision(); updateHeader();
  const dsel=document.getElementById('division'); if(dsel) dsel.value=id;   // keep header in sync
  const cur=document.querySelector('nav button.active');
  show(cur?cur.dataset.id:'overview');
}
// Wipe-urgency line under the hero: replay codes die at each patch, so the live
// queue is a countdown, not a static number. Hidden when there's nothing left to
// scout or the feed has no wipe date on record.
function updateWipeNote(){
  const el=document.getElementById('wipenote'); if(!el) return;
  const q=leagueQueue();
  if(!CODE_WIPE || !q.length){ el.style.display='none'; return; }
  el.style.display='block';
  el.innerHTML=`<span style="color:var(--mid)">Replay codes wiped <b>${esc(CODE_WIPE)}</b> — ${q.length} live replay code${q.length===1?'':'s'} still need a capture before the next patch.</span> `+
    `<a href="capture/" style="color:var(--accent);font-weight:700;text-decoration:none">Pick one →</a>`;
}
function init(){
  recomputeDivision();
  const dsel=document.getElementById('division');
  VIEWS.forEach(v=>dsel.appendChild(el(`<option value="${v.id}">${esc(v.label)}</option>`)));
  dsel.value=CURRENT_VIEW;
  if(VIEWS.length>1) dsel.classList.remove('hidden');
  dsel.onchange=()=>setDivision(dsel.value);
  updateHeader();
  const nav=document.getElementById('nav');
  TABS.forEach(t=>{const b=el(`<button data-id="${t.id}">${esc(t.label)}</button>`);b.onclick=()=>show(t.id);nav.appendChild(b);});
  const ncl=document.getElementById('navcapcount');
  if(ncl){ const nq=leagueQueue().length; if(nq) ncl.textContent='· '+nq+' left'; }
  updateWipeNote();
  document.getElementById('heroScout').onclick=()=>{ if(!SCOUT_TEAM) SCOUT_TEAM=(D().team_names||[])[0]||null; show('scout'); };
  document.getElementById('heroCapture').onclick=()=>{ location.href='capture/'; };
  hashDispatch();
}
window.addEventListener('hashchange',hashDispatch);
init();
}

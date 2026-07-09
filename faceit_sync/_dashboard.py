"""Self-contained HTML dashboard template.

``export_html`` substitutes ``__TITLE__`` and ``__DATA__`` (a JSON blob) into this
template. No external resources (fonts, scripts, images) — it opens by
double-clicking, works offline, and is safe under a strict CSP.

Design: a refined, information-first scouting tool. Cool slate neutrals with a
single indigo accent; Overwatch role colours (Tank/Damage/Support) as the only
categorical hues; a green→amber→red scale reserved for win rates. Four views:
Overview (league at a glance) → Scout (opponent drill-down) → Meta (league-wide
ban/map trends) → Matches (searchable, per-game bans + rosters).
"""

HTML_TEMPLATE = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>__TITLE__ &mdash; scouting</title>
<style>
:root{
  --bg:#f5f7fa; --surface:#ffffff; --surface2:#eef1f6; --fg:#171a20; --muted:#5c6674;
  --faint:#8b95a4; --line:#e3e8f0; --line2:#d6dce6;
  --accent:#4f46e5; --accent-weak:rgba(79,70,229,.12);
  --tank:#3f80c4; --damage:#d5563f; --support:#33a06a;
  --good:#1f9d61; --mid:#b8860b; --bad:#cf4b36;
  --shadow:0 1px 2px rgba(16,24,40,.06),0 1px 3px rgba(16,24,40,.05);
}
@media (prefers-color-scheme: dark){
  :root{--bg:#0d1015;--surface:#161a21;--surface2:#1d232c;--fg:#e7ebf2;--muted:#98a2b2;
    --faint:#6b7686;--line:#252c37;--line2:#313a48;--accent:#8087ff;--accent-weak:rgba(128,135,255,.16);
    --tank:#5a9bd8;--damage:#e9694f;--support:#46b57c;--good:#34b877;--mid:#d3a02a;--bad:#e5624a;
    --shadow:0 1px 2px rgba(0,0,0,.3);}
}
:root[data-theme="dark"]{--bg:#0d1015;--surface:#161a21;--surface2:#1d232c;--fg:#e7ebf2;--muted:#98a2b2;
  --faint:#6b7686;--line:#252c37;--line2:#313a48;--accent:#8087ff;--accent-weak:rgba(128,135,255,.16);
  --tank:#5a9bd8;--damage:#e9694f;--support:#46b57c;--good:#34b877;--mid:#d3a02a;--bad:#e5624a;
  --shadow:0 1px 2px rgba(0,0,0,.3);}
:root[data-theme="light"]{--bg:#f5f7fa;--surface:#ffffff;--surface2:#eef1f6;--fg:#171a20;--muted:#5c6674;
  --faint:#8b95a4;--line:#e3e8f0;--line2:#d6dce6;--accent:#4f46e5;--accent-weak:rgba(79,70,229,.12);
  --tank:#3f80c4;--damage:#d5563f;--support:#33a06a;--good:#1f9d61;--mid:#b8860b;--bad:#cf4b36;
  --shadow:0 1px 2px rgba(16,24,40,.06),0 1px 3px rgba(16,24,40,.05);}

*{box-sizing:border-box}
html{-webkit-text-size-adjust:100%}
body{margin:0;background:var(--bg);color:var(--fg);font-variant-numeric:tabular-nums;
  font-family:ui-sans-serif,system-ui,-apple-system,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;
  font-size:14px;line-height:1.5;-webkit-font-smoothing:antialiased}
.tnum{font-variant-numeric:tabular-nums}

/* ---- app shell ---- */
.topbar{position:sticky;top:0;z-index:20;background:color-mix(in srgb,var(--bg) 88%,transparent);
  backdrop-filter:saturate(1.4) blur(8px);border-bottom:1px solid var(--line)}
.topbar-in{max-width:1060px;margin:0 auto;padding:12px 18px 0}
.brand{display:flex;align-items:baseline;gap:10px;flex-wrap:wrap}
.brand h1{margin:0;font-size:17px;font-weight:650;letter-spacing:-.01em}
.brand .meta{color:var(--muted);font-size:12.5px}
nav{display:flex;gap:2px;margin-top:10px}
nav button{border:0;background:transparent;color:var(--muted);padding:9px 14px;border-radius:8px 8px 0 0;
  cursor:pointer;font-size:13.5px;font-weight:600;border-bottom:2px solid transparent;margin-bottom:-1px}
nav button:hover{color:var(--fg)}
nav button.active{color:var(--accent);border-bottom-color:var(--accent)}
nav button:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
main{max-width:1060px;margin:0 auto;padding:20px 18px 72px}

/* ---- primitives ---- */
.eyebrow{font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:.07em;color:var(--faint);margin:0 0 8px}
.card{background:var(--surface);border:1px solid var(--line);border-radius:14px;padding:18px;box-shadow:var(--shadow)}
.grid{display:grid;gap:14px}
.cols-2{grid-template-columns:1fr 1fr}
.cols-auto{grid-template-columns:repeat(auto-fit,minmax(150px,1fr))}
@media (max-width:720px){.cols-2{grid-template-columns:1fr}}
.section-h{display:flex;align-items:center;justify-content:space-between;gap:12px;margin:26px 2px 10px}
.section-h h2{margin:0;font-size:14.5px;font-weight:650}
.note{color:var(--muted);font-size:12.5px;margin:8px 2px 0}
.tile .n{font-size:27px;font-weight:680;letter-spacing:-.02em}
.tile .l{color:var(--muted);font-size:12px;margin-top:1px}
.tile .sub{color:var(--faint);font-size:11.5px;margin-top:3px}

/* controls */
select,input,.btn{font:inherit;color:var(--fg);background:var(--surface);border:1px solid var(--line2);
  border-radius:9px;padding:8px 11px}
select:focus,input:focus{outline:2px solid var(--accent);outline-offset:1px;border-color:var(--accent)}
.controls{display:flex;gap:14px;align-items:center;flex-wrap:wrap}
.controls label{color:var(--muted);font-size:12px;font-weight:600}
.btn{cursor:pointer;font-weight:600;background:var(--accent);color:#fff;border-color:transparent}
.btn:hover{filter:brightness(1.06)}

/* tables */
table{width:100%;border-collapse:collapse}
th,td{text-align:left;padding:8px 11px;border-bottom:1px solid var(--line);white-space:nowrap;font-size:13.5px}
thead th{color:var(--faint);font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:.04em;
  cursor:pointer;user-select:none;position:sticky;top:0}
th.num,td.num{text-align:right}
tbody tr:hover{background:var(--surface2)}
.scroll{overflow-x:auto;border-radius:10px}

/* bars */
.barrow{display:grid;grid-template-columns:1fr 46%;align-items:center;gap:12px;padding:4px 2px}
.barrow .lab{font-size:13px;display:flex;align-items:center;gap:7px;min-width:0}
.barrow .lab .name{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.track{position:relative;height:10px;background:var(--surface2);border-radius:6px;overflow:hidden}
.fill{position:absolute;inset:0 auto 0 0;border-radius:6px;background:var(--accent)}
.barval{position:absolute;right:8px;top:-5px;font-size:12px;color:var(--muted)}
.barwrap{position:relative}

/* chips / badges */
.chip{display:inline-flex;align-items:center;gap:5px;font-size:11.5px;font-weight:600;padding:2px 8px;
  border-radius:20px;background:var(--surface2);color:var(--muted);border:1px solid var(--line)}
.dot{width:7px;height:7px;border-radius:50%;flex:none}
.role-Tank{color:var(--tank)} .role-Damage{color:var(--damage)} .role-Support{color:var(--support)}
.bg-Tank{background:var(--tank)} .bg-Damage{background:var(--damage)} .bg-Support{background:var(--support)}
.pill{display:inline-block;font-size:12px;font-weight:650;padding:1px 8px;border-radius:7px}
.tag{display:inline-block;font-size:10.5px;font-weight:700;text-transform:uppercase;letter-spacing:.03em;
  padding:1px 6px;border-radius:5px;background:var(--surface2);color:var(--faint)}
.tag.warn{background:color-mix(in srgb,var(--mid) 20%,transparent);color:var(--mid)}
.tag.bad{background:color-mix(in srgb,var(--bad) 18%,transparent);color:var(--bad)}
.wl{display:inline-flex;gap:3px}
.wl b{width:16px;height:16px;border-radius:4px;font-size:10px;font-weight:700;color:#fff;
  display:inline-flex;align-items:center;justify-content:center}
.w{background:var(--good)} .l{background:var(--bad)}

/* matches */
.match{margin-bottom:12px;padding:0;overflow:hidden}
.match .hd{display:flex;justify-content:space-between;align-items:center;gap:10px;flex-wrap:wrap;
  padding:14px 16px;border-bottom:1px solid var(--line)}
.match .teams{font-size:15px;font-weight:600}
.match .teams .win{color:var(--fg)} .match .teams .lose{color:var(--muted)}
.match .score{font-weight:750;font-size:15px;margin:0 8px}
.game{padding:10px 16px;border-bottom:1px solid var(--line);font-size:13px}
.game:last-child{border-bottom:0}
.game-hd{display:flex;align-items:center;gap:10px;flex-wrap:wrap;cursor:pointer}
.game-hd .gno{font-weight:700;color:var(--faint);width:22px}
.bans{display:flex;gap:6px;flex-wrap:wrap;align-items:center;margin-top:6px}
.rosters{display:grid;grid-template-columns:1fr 1fr;gap:14px;margin-top:10px}
@media (max-width:640px){.rosters{grid-template-columns:1fr}}
.roster h4{margin:0 0 6px;font-size:12px;color:var(--muted);font-weight:650}
.roster .pl{display:grid;grid-template-columns:14px 1fr auto;gap:8px;align-items:center;padding:3px 0;
  border-top:1px solid var(--line);font-size:12.5px}
.roster .pl .st{color:var(--faint);font-size:11.5px;font-variant-numeric:tabular-nums}
.muted{color:var(--muted)} .faint{color:var(--faint)}
.hidden{display:none}
</style>
</head>
<body>
<div class="topbar"><div class="topbar-in">
  <div class="brand"><h1 id="title"></h1><span class="meta" id="subtitle"></span></div>
  <nav id="nav"></nav>
</div></div>
<main id="content"></main>
<script>
const DATA = __DATA__;

/* ---------- tiny DOM + format helpers ---------- */
const el = (h)=>{const t=document.createElement('template');t.innerHTML=h.trim();return t.content.firstChild;};
const esc = (s)=> (s==null?'':String(s)).replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
const nf = (n)=> (n==null?'—':Number(n).toLocaleString('en-US'));
const pctOf = (a,b)=> b? Math.round(100*a/b) : 0;
const dshort = (s)=> s? String(s).slice(0,10) : '?';
const inc = (o,k,by=1)=>{ o[k]=(o[k]||0)+by; };
const rank = (o)=> Object.entries(o).sort((a,b)=>b[1]-a[1]);   // NB: not `top` (window.top is reserved)

const HERO_ROLE={}; DATA.heroes.forEach(h=>HERO_ROLE[h.name]=h.role);
const MAP_CAT={}; DATA.maps.forEach(m=>MAP_CAT[m.name]=m.category);
const roleVar = (r)=> ({Tank:'var(--tank)',Damage:'var(--damage)',Support:'var(--support)'}[r]||'var(--accent)');
const winVar = (p)=> p>=58?'var(--good)': p>=42?'var(--mid)':'var(--bad)';

/* recency: matches newest-first (recency is measured in matches ≈ how a season is counted) */
const MATCHES_RECENT=[...DATA.matches].sort((a,b)=>{const x=a.finished_at||'',y=b.finished_at||'';return x===y?0:(x<y?1:-1);});
const recent=(arr,lim)=> (lim && lim<arr.length)? arr.slice(0,lim) : arr;
const dateRange=(ms)=>{const w=ms.map(m=>m.finished_at).filter(Boolean).sort();return {from:w[0]||'',to:w[w.length-1]||''};};

/* ---------- reusable renderers ---------- */
function heroChip(name){ const r=HERO_ROLE[name]; return `<span class="chip"><span class="dot bg-${esc(r||'')}"></span>${esc(name)}</span>`; }
function pill(text,color){ return `<span class="pill" style="background:color-mix(in srgb,${color} 16%,transparent);color:${color}">${esc(text)}</span>`; }
function tag(text,cls=''){ return `<span class="tag ${cls}">${esc(text)}</span>`; }

// horizontal bar list. items:[{label(html), value, color?}]
function barList(items){
  if(!items.length) return `<p class="note">No data in this window.</p>`;
  const max=Math.max(1,...items.map(i=>i.value));
  return `<div>`+items.map(i=>{
    const w=Math.max(2,Math.round(100*i.value/max));
    return `<div class="barrow"><div class="lab">${i.label}</div>`+
      `<div class="barwrap"><div class="track"><div class="fill" style="width:${w}%;background:${i.color||'var(--accent)'}"></div></div>`+
      `<span class="barval">${i.value}</span></div></div>`;
  }).join('')+`</div>`;
}

// sortable table. cols:[{k,label,num?,html?}]
function table(cols,rows){
  const head=`<tr>`+cols.map((c,i)=>`<th class="${c.num?'num':''}" data-i="${i}">${esc(c.label)}</th>`).join('')+`</tr>`;
  const body=(rs)=>rs.map(r=>`<tr>`+cols.map(c=>`<td class="${c.num?'num':''}">${c.html?c.html(r):esc(r[c.k])}</td>`).join('')+`</tr>`).join('');
  const box=el(`<div class="scroll"><table><thead>${head}</thead><tbody>${body(rows)}</tbody></table></div>`);
  const asc={};
  box.querySelectorAll('th').forEach(th=>th.onclick=()=>{
    const i=+th.dataset.i,c=cols[i];asc[i]=!asc[i];
    const s=[...rows].sort((a,b)=>{let x=a[c.k],y=b[c.k];if(c.num){x=+x||0;y=+y||0;return asc[i]?x-y:y-x;}return asc[i]?String(x).localeCompare(String(y)):String(y).localeCompare(String(x));});
    box.querySelector('tbody').innerHTML=body(s);
  });
  return box;
}

function sectionH(title,right=''){ return `<div class="section-h"><h2>${esc(title)}</h2>${right}</div>`; }

// window <select>
function windowSelect(current,onchange,opts){
  const s=el(`<select></select>`);
  opts.forEach(([v,l])=>s.appendChild(el(`<option value="${v}" ${v===current?'selected':''}>${esc(l)}</option>`)));
  s.onchange=()=>onchange(s.value); return s;
}

/* ---------- aggregation over a set of matches ---------- */
// team=null → league-wide; else that team's own bans/picks/counters + map win rates.
function aggregate(matches,team){
  const a={bans:{},banRoles:{},mapsPicked:{},perMap:{},counter:{},mapStats:{},games:0,gwins:0,results:[]};
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
        const mine=g.bans.find(b=>b.team===team), oc=g.bans.find(b=>b.team&&b.team!==team);
        if(mine){ inc(a.bans,mine.hero); if(mine.role)inc(a.banRoles,mine.role);
          (a.perMap[g.map]=a.perMap[g.map]||{}); inc(a.perMap[g.map],mine.hero);
          if(oc){ (a.counter[oc.hero]=a.counter[oc.hero]||{}); inc(a.counter[oc.hero],mine.hero); } }
      } else { inc(a.mapsPicked,g.map); g.bans.forEach(b=>{ inc(a.bans,b.hero); if(b.role)inc(a.banRoles,b.role); }); }
    });
  });
  return a;
}

/* ============================================================= VIEWS */
const TABS=[
 {id:'overview',label:'Overview',render:renderOverview},
 {id:'scout',label:'Scout a team',render:renderScout},
 {id:'meta',label:'League meta',render:renderMeta},
 {id:'matches',label:'Matches',render:renderMatches},
];

let SCOUT_TEAM = DATA.team_names[0]||null;
let SCOUT_WIN='all', META_WIN='20';

function gotoScout(team){ SCOUT_TEAM=team; show('scout'); }

function renderOverview(){
  const s=DATA.summary, wrap=el(`<div></div>`);

  const tiles=[['played_games','Games played',`${s.matches} matches`],
    ['teams','Teams',`${s.walkovers} walkovers`],
    ['matches_with_attribution','Matches w/ veto data',`of ${s.matches} — ${pctOf(s.matches_with_attribution,s.matches)}%`],
    ['dc_games','Games w/ a DC',`stats stored as NULL`]];
  const g=el(`<div class="grid cols-auto"></div>`);
  tiles.forEach(([k,l,sub])=>g.appendChild(el(`<div class="card tile"><div class="n">${nf(s[k])}</div><div class="l">${l}</div><div class="sub">${sub}</div></div>`)));
  wrap.appendChild(g);

  // Scout launcher
  const launch=el(`<div class="card" style="margin-top:14px"></div>`);
  launch.appendChild(el(`<p class="eyebrow">Prep for a match</p>`));
  const row=el(`<div class="controls"></div>`);
  const sel=el(`<select style="min-width:200px"></select>`);
  DATA.team_names.forEach(n=>sel.appendChild(el(`<option>${esc(n)}</option>`)));
  const go=el(`<button class="btn">Scout this team →</button>`);
  go.onclick=()=>gotoScout(sel.value);
  row.append(sel,go); launch.appendChild(row);
  wrap.appendChild(launch);

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
    [{k:'name',label:'Team'},{k:'matches',label:'Matches',num:true},{k:'wins',label:'Wins',num:true},
     {k:'win_pct',label:'Win %',num:true,html:r=>pill(r.win_pct+'%',winVar(r.win_pct))}],
    DATA.teams));
  wrap.appendChild(el(`<p class="note">Veto attribution recovered from FACEIT's durable history feed for ${s.matches_with_attribution}/${s.matches} matches; only walkovers and disrupted vetos lack it.</p>`));
  return wrap;
}

function scoutData(team,lim){
  const mine=MATCHES_RECENT.filter(m=>m.f1===team||m.f2===team);
  const used=recent(mine,lim), a=aggregate(used,team), {from,to}=dateRange(used);
  return {team,used:used.length,total:mine.length,from,to,...a};
}

function renderScout(){
  const wrap=el(`<div></div>`);
  const bar=el(`<div class="card controls"></div>`);
  bar.appendChild(el(`<label>Opponent</label>`));
  const sel=el(`<select style="min-width:190px"></select>`);
  DATA.team_names.forEach(n=>sel.appendChild(el(`<option ${n===SCOUT_TEAM?'selected':''}>${esc(n)}</option>`)));
  sel.onchange=()=>{SCOUT_TEAM=sel.value;draw();};
  bar.appendChild(sel);
  bar.appendChild(el(`<label>Form</label>`));
  bar.appendChild(windowSelect(SCOUT_WIN,v=>{SCOUT_WIN=v;draw();},[['all','All matches'],['15','Last 15'],['10','Last 10'],['5','Last 5']]));
  const body=el(`<div></div>`);
  wrap.append(bar,body);
  function draw(){
    const lim=SCOUT_WIN==='all'?null:parseInt(SCOUT_WIN,10);
    const t=scoutData(SCOUT_TEAM,lim); body.innerHTML=''; body.appendChild(renderScoutBody(t));
  }
  draw(); return wrap;
}

function renderScoutBody(t){
  const w=el(`<div></div>`);
  const matchW=t.results.filter(r=>r.won).length;
  const form=t.results.slice(0,7).map(r=>`<b class="${r.won?'w':'l'}" title="${esc(r.opp)} ${esc(r.series)}">${r.won?'W':'L'}</b>`).join('');
  const head=el(`<div class="card" style="display:flex;gap:18px;flex-wrap:wrap;align-items:center;justify-content:space-between"></div>`);
  head.appendChild(el(`<div><div style="font-size:18px;font-weight:680">${esc(t.team)}</div>`+
    `<div class="note" style="margin-top:2px">${t.used<t.total?`last ${t.used} of ${t.total} matches`:`all ${t.total} matches`} · ${dshort(t.from)} → ${dshort(t.to)}</div></div>`));
  head.appendChild(el(`<div style="text-align:right"><div>${pill(`${matchW}/${t.results.length} matches`,winVar(pctOf(matchW,t.results.length)))} ${pill(`${t.gwins}/${t.games} games`,winVar(pctOf(t.gwins,t.games)))}</div>`+
    `<div class="wl" style="margin-top:6px;justify-content:flex-end">${form||'<span class="faint">no games</span>'}</div></div>`));
  w.appendChild(head);

  // Preferred bans + Map picks/win rates (the two most-used, side by side)
  const two=el(`<div class="grid cols-2" style="margin-top:16px"></div>`);
  const banC=el(`<div class="card"></div>`);
  banC.appendChild(el(`<p class="eyebrow">Preferred bans</p>`));
  banC.appendChild(el(barList(rank(t.bans).slice(0,12).map(([h,n])=>({label:heroChip(h),value:n,color:roleVar(HERO_ROLE[h])})))));
  two.appendChild(banC);
  const mapC=el(`<div class="card"></div>`);
  mapC.appendChild(el(`<p class="eyebrow">Maps — picks &amp; win rate</p>`));
  const mrows=Object.entries(t.mapStats).map(([m,v])=>({map:m,cat:MAP_CAT[m]||'',games:v.games,picks:v.picks,wr:pctOf(v.wins,v.games)})).sort((a,b)=>b.games-a.games);
  mapC.appendChild(mrows.length?table(
    [{k:'map',label:'Map',html:r=>`${esc(r.map)} <span class="faint">${esc(r.cat)}</span>`},
     {k:'picks',label:'Picked',num:true},{k:'games',label:'Played',num:true},
     {k:'wr',label:'Win %',num:true,html:r=>pill(r.wr+'%',winVar(r.wr))}], mrows)
   :el(`<p class="note">No maps in window.</p>`));
  two.appendChild(mapC);
  w.appendChild(two);

  // Counter-bans (full width — a key prep table)
  w.appendChild(el(sectionH('Counter-bans',`<span class="note">when the opponent banned X, ${esc(t.team)} banned…</span>`)));
  const cRows=rank(Object.fromEntries(Object.entries(t.counter).map(([k,v])=>[k,Object.values(v).reduce((x,y)=>x+y,0)])))
    .map(([opp,tot])=>({opp,tot,resp:rank(t.counter[opp]).map(([h,n])=>`${heroChip(h)}<span class="faint"> ${n}</span>`).join(' ')}));
  w.appendChild(cRows.length?table(
    [{k:'opp',label:'Opponent banned',html:r=>heroChip(r.opp)},{k:'tot',label:'×',num:true},
     {k:'resp',label:`${esc(t.team)} responded with`,html:r=>r.resp}], cRows)
   :el(`<p class="note">No paired bans yet (needs both teams' bans attributed).</p>`));

  // Bans by map
  w.appendChild(el(sectionH('Bans by map')));
  const bmRows=Object.keys(t.perMap).sort().map(mp=>({map:mp,n:Object.values(t.perMap[mp]).reduce((a,b)=>a+b,0),
    heroes:rank(t.perMap[mp]).map(([h,c])=>`${heroChip(h)}<span class="faint"> ${c}</span>`).join(' ')}));
  w.appendChild(bmRows.length?table(
    [{k:'map',label:'Map'},{k:'n',label:'Bans',num:true},{k:'heroes',label:'Heroes banned',html:r=>r.heroes}], bmRows)
   :el(`<p class="note">No data.</p>`));
  return w;
}

function renderMeta(){
  const wrap=el(`<div></div>`);
  const bar=el(`<div class="card controls"></div>`);
  bar.appendChild(el(`<label>Recency</label>`));
  bar.appendChild(windowSelect(META_WIN,v=>{META_WIN=v;draw();},[['all','All matches'],['40','Last 40'],['20','Last 20'],['10','Last 10'],['5','Last 5']]));
  bar.appendChild(el(`<span class="note">a nerfed hero fades from recent windows</span>`));
  const body=el(`<div></div>`); wrap.append(bar,body);
  function draw(){
    const lim=META_WIN==='all'?null:parseInt(META_WIN,10);
    const ms=recent(MATCHES_RECENT,lim), a=aggregate(ms,null), {from,to}=dateRange(ms);
    body.innerHTML='';
    const v=el(`<div></div>`);
    v.appendChild(el(`<p class="note">${ms.length<MATCHES_RECENT.length?`last ${ms.length} of ${MATCHES_RECENT.length}`:`all ${ms.length}`} matches · ${dshort(from)} → ${dshort(to)}</p>`));
    const two=el(`<div class="grid cols-2" style="margin-top:8px"></div>`);
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
  // attacking-first (all season)
  const af=DATA.attacking_first;
  wrap.appendChild(el(sectionH('Attacking-first advantage',`<span class="note">Escort &amp; Hybrid only · all season</span>`)));
  wrap.appendChild(el(`<p class="note" style="margin-top:0">Mirrored modes (Control/Flashpoint/Push) excluded. Overall the first-attacking team won <b>${af.atk_first_wins}/${af.total_games}</b> = <b>${pctOf(af.atk_first_wins,af.total_games)}%</b>.</p>`));
  wrap.appendChild(table(
    [{k:'name',label:'Map'},{k:'category',label:'Mode'},{k:'games',label:'Games',num:true},
     {k:'wr',label:'Atk-first win %',num:true,html:r=>pill(r.wr+'%',winVar(r.wr))}],
    af.by_map.map(m=>({...m,wr:pctOf(m.atk_first_wins,m.games)}))));
  return wrap;
}

function renderMatches(){
  const wrap=el(`<div></div>`);
  const search=el(`<input placeholder="search team, hero, or map…" style="width:100%;margin-bottom:12px;font-size:15px;padding:11px 13px">`);
  const list=el(`<div></div>`); wrap.append(search,list);
  const hay=(m)=>[m.f1,m.f2,...m.games.flatMap(g=>[g.map,...g.bans.map(b=>b.hero),...(g.rosters||[]).flatMap(r=>r.players.map(p=>p.nick))])].filter(Boolean).join(' ').toLowerCase();

  function rosterHTML(g){
    return `<div class="rosters">`+(g.rosters||[]).map(rt=>{
      const pls=rt.players.map(p=>{
        const st=p.cap? `<span class="st">${nf(p.e)}e · ${nf(p.dmg)} dmg · ${nf(p.heal)} heal</span>`
                       : `<span class="st faint">stats not captured (DC)</span>`;
        return `<div class="pl"><span class="dot bg-${esc(p.role||'')}" title="${esc(p.role||'—')}"></span>`+
               `<span>${esc(p.nick)}</span>${st}</div>`;
      }).join('');
      return `<div class="roster"><h4>${esc(rt.team)}</h4>${pls||'<span class="faint">—</span>'}</div>`;
    }).join('')+`</div>`;
  }
  function banSide(g,fac,name){
    const bs=g.bans.filter(b=>b.faction===fac);
    return `<span class="faint">${esc(name||fac)}:</span> ${bs.map(b=>heroChip(b.hero)).join(' ')||'—'}`;
  }
  function draw(q){
    q=(q||'').trim().toLowerCase(); list.innerHTML='';
    const shown=DATA.matches.filter(m=>!q||hay(m).includes(q));
    if(!shown.length){ list.appendChild(el(`<p class="note">No matches.</p>`)); return; }
    shown.forEach(m=>{
      const c=el(`<div class="card match"></div>`);
      const w1=m.winner==='faction1',w2=m.winner==='faction2';
      c.appendChild(el(`<div class="hd"><div class="teams"><span class="${w1?'win':'lose'}">${esc(m.f1||'?')}</span>`+
        `<span class="score">${esc(m.series)}</span><span class="${w2?'win':'lose'}">${esc(m.f2||'?')}</span></div>`+
        `<div>${m.walkover?tag('walkover','bad'):(m.forfeit?tag('forfeit','bad'):'')} ${tag('R'+m.round+' · G'+m.group)}</div></div>`));
      m.games.filter(g=>g.map).forEach(g=>{
        const gEl=el(`<div class="game"></div>`);
        const un=g.bans.filter(b=>!b.faction);
        gEl.appendChild(el(`<div class="game-hd"><span class="gno">G${g.game_no}</span>`+
          `<b>${esc(g.map)}</b> ${tag(g.map_category||'')} <span class="tnum">${esc(g.f1)}–${esc(g.f2)}</span>`+
          `<span class="muted">→ ${esc(g.winner_team||'?')}</span>`+
          (g.was_restarted?tag('veto disrupted','warn'):'')+
          `<span class="faint" style="margin-left:auto">▸ rosters</span></div>`));
        gEl.appendChild(el(`<div class="bans">${banSide(g,'faction1',m.f1)} &nbsp; ${banSide(g,'faction2',m.f2)}`+
          (un.length?` <span class="faint">(unattributed: ${un.map(b=>esc(b.hero)).join(', ')})</span>`:'')+`</div>`));
        const ros=el(`<div class="hidden">${rosterHTML(g)}</div>`);
        gEl.appendChild(ros);
        const toggle=gEl.querySelector('.game-hd');
        toggle.onclick=()=>{ const open=ros.classList.toggle('hidden')===false;
          toggle.querySelector('span:last-child').textContent=open?'▾ rosters':'▸ rosters'; };
        c.appendChild(gEl);
      });
      list.appendChild(c);
    });
  }
  search.oninput=()=>draw(search.value); draw(''); return wrap;
}

/* ---------- shell ---------- */
function show(id){
  document.querySelectorAll('nav button').forEach(b=>b.classList.toggle('active',b.dataset.id===id));
  const c=document.getElementById('content'); c.innerHTML=''; c.appendChild(TABS.find(t=>t.id===id).render());
  try{window.scrollTo(0,0)}catch(e){} if(location.hash!=='#'+id) location.hash=id;
}
function init(){
  document.getElementById('title').textContent=DATA.summary.championship;
  document.getElementById('subtitle').textContent=`${DATA.summary.matches} matches · ${DATA.summary.played_games} games · ${dshort(DATA.summary.date_from)} → ${dshort(DATA.summary.date_to)}`;
  const nav=document.getElementById('nav');
  TABS.forEach(t=>{const b=el(`<button data-id="${t.id}">${esc(t.label)}</button>`);b.onclick=()=>show(t.id);nav.appendChild(b);});
  const start=(location.hash||'#overview').slice(1);
  show(TABS.some(t=>t.id===start)?start:'overview');
}
init();
</script>
</body>
</html>
"""

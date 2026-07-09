"""Self-contained HTML dashboard template.

``export_html`` substitutes ``__TITLE__`` and ``__DATA__`` (a JSON blob) into this
template. No external resources — opens by double-clicking, works offline.
"""

HTML_TEMPLATE = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>__TITLE__ &mdash; faceit-sync</title>
<style>
:root{
  --bg:#f6f7f9; --card:#fff; --fg:#14171a; --muted:#5b6570; --line:#e3e7ec;
  --accent:#4c7ef3; --good:#2e9e6b; --warn:#c9922b; --bad:#d0503a;
  --tank:#6c8ebf; --damage:#d0503a; --support:#2e9e6b;
}
@media (prefers-color-scheme: dark){
  :root{--bg:#0f1216;--card:#171b21;--fg:#e7ecf2;--muted:#93a0ad;--line:#262c34;--accent:#5b8bff;}
}
/* An explicit viewer theme toggle must win over the OS preference, both ways. */
:root[data-theme="dark"]{--bg:#0f1216;--card:#171b21;--fg:#e7ecf2;--muted:#93a0ad;--line:#262c34;--accent:#5b8bff;}
:root[data-theme="light"]{--bg:#f6f7f9;--card:#fff;--fg:#14171a;--muted:#5b6570;--line:#e3e7ec;--accent:#4c7ef3;}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--fg);
  font:15px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif}
header{padding:22px 20px 6px}
h1{margin:0;font-size:20px} .sub{color:var(--muted);font-size:13px;margin-top:3px}
nav{display:flex;gap:4px;flex-wrap:wrap;padding:10px 16px;position:sticky;top:0;
  background:var(--bg);border-bottom:1px solid var(--line);z-index:5}
nav button{border:0;background:transparent;color:var(--muted);padding:8px 14px;border-radius:8px;
  cursor:pointer;font-size:14px;font-weight:600}
nav button.active{background:var(--card);color:var(--fg);box-shadow:0 1px 3px rgba(0,0,0,.08)}
main{max-width:1000px;margin:0 auto;padding:18px 16px 60px}
.grid{display:grid;gap:12px;grid-template-columns:repeat(auto-fit,minmax(150px,1fr))}
.card{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:16px}
.tile .n{font-size:26px;font-weight:700} .tile .l{color:var(--muted);font-size:12px;margin-top:2px}
h2{font-size:15px;margin:22px 2px 8px;color:var(--muted);text-transform:uppercase;letter-spacing:.04em}
table{width:100%;border-collapse:collapse;font-size:14px}
th,td{text-align:left;padding:7px 10px;border-bottom:1px solid var(--line);white-space:nowrap}
th{color:var(--muted);font-size:12px;cursor:pointer;user-select:none}
td.num,th.num{text-align:right;font-variant-numeric:tabular-nums}
tbody tr:hover{background:rgba(127,127,127,.06)}
.bar{height:9px;border-radius:5px;background:var(--accent);display:inline-block;vertical-align:middle}
.role-Tank{color:var(--tank)} .role-Damage{color:var(--damage)} .role-Support{color:var(--support)}
.badge{display:inline-block;font-size:11px;padding:1px 7px;border-radius:20px;background:rgba(127,127,127,.15);color:var(--muted)}
.badge.ff{background:rgba(208,80,58,.15);color:var(--bad)}
.badge.rs{background:rgba(201,146,43,.18);color:var(--warn)}
.match{margin-bottom:10px}
.match .hd{display:flex;justify-content:space-between;align-items:center;gap:10px;flex-wrap:wrap}
.win{font-weight:700}
.note{color:var(--muted);font-size:12.5px;margin:6px 2px 0}
.scroll{overflow-x:auto}
@media (max-width:560px){.tile .n{font-size:22px}}
</style>
</head>
<body>
<header>
  <h1 id="title"></h1>
  <div class="sub" id="subtitle"></div>
</header>
<nav id="nav"></nav>
<main id="content"></main>
<script>
const DATA = __DATA__;
const $ = (h)=>{const t=document.createElement('template');t.innerHTML=h.trim();return t.content.firstChild;};
const esc = (s)=> (s==null?'':String(s)).replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
const pct = (a,b)=> b? (100*a/b).toFixed(1)+'%':'—';
const roleSpan = (r)=> r?`<span class="role-${esc(r)}">${esc(r)}</span>`:'—';

function bars(items, labelFn, valKey, colorFn){
  const max = Math.max(1, ...items.map(i=>i[valKey]));
  return `<table><tbody>`+items.map(i=>{
    const w = Math.round(100*i[valKey]/max);
    const col = colorFn? colorFn(i):'var(--accent)';
    return `<tr><td>${labelFn(i)}</td>`+
      `<td style="width:55%"><span class="bar" style="width:${w}%;background:${col}"></span></td>`+
      `<td class="num">${i[valKey]}</td></tr>`;
  }).join('')+`</tbody></table>`;
}

function sortable(headers, rows){
  const thead = `<tr>`+headers.map((h,i)=>`<th class="${h.num?'num':''}" data-i="${i}">${esc(h.label)}</th>`).join('')+`</tr>`;
  const body = (rs)=> rs.map(r=>`<tr>`+headers.map(h=>
      `<td class="${h.num?'num':''}">${h.html?h.html(r):esc(r[h.k])}</td>`).join('')+`</tr>`).join('');
  const tbl = $(`<div class="scroll"><table><thead>${thead}</thead><tbody>${body(rows)}</tbody></table></div>`);
  const asc = {};
  tbl.querySelectorAll('th').forEach(th=>th.onclick=()=>{
    const i=+th.dataset.i, h=headers[i]; asc[i]=!asc[i];
    const sorted=[...rows].sort((a,b)=>{
      let x=a[h.k],y=b[h.k];
      if(h.num){x=+x||0;y=+y||0;return asc[i]?x-y:y-x;}
      return asc[i]? String(x).localeCompare(String(y)):String(y).localeCompare(String(x));
    });
    tbl.querySelector('tbody').innerHTML=body(sorted);
  });
  return tbl;
}

const roleColor = (i)=> ({Tank:'var(--tank)',Damage:'var(--damage)',Support:'var(--support)'}[i.role]||'var(--accent)');
const inc = (o,k)=>{ o[k]=(o[k]||0)+1; };
// NB: do not name this `top` — `window.top` is a read-only browser global and
// `const top` at script scope throws "Identifier 'top' has already been declared".
const rank = (o)=> Object.entries(o).sort((a,b)=>b[1]-a[1]);

// Lookups so aggregated (name-keyed) tallies can recover role / map category.
const HERO_ROLE = {}; DATA.heroes.forEach(h=>HERO_ROLE[h.name]=h.role);
const MAP_CAT = {}; DATA.maps.forEach(m=>MAP_CAT[m.name]=m.category);

let SELECTED_TEAM = DATA.team_names[0] || null;
let WIN_TEAM='all', WIN_BANS='all', WIN_MAPS='all';   // recency windows (in matches)
const dateShort = (s)=> s? String(s).slice(0,10) : '?';

// All matches newest-first (by finish date) — recency is measured in matches,
// which is how a season is counted (~15 per team before playoffs).
const MATCHES_RECENT = [...DATA.matches].sort((a,b)=>{
  const wa=a.finished_at||'', wb=b.finished_at||'';
  return wa===wb? 0 : (wa<wb? 1 : -1);
});
const recent = (arr, limit)=> (limit && limit<arr.length)? arr.slice(0,limit) : arr;
const dateRange = (ms)=>{ const w=ms.map(m=>m.finished_at).filter(Boolean).sort();
  return {from:w[0]||'', to:w[w.length-1]||''}; };

// Tally bans/maps over a set of matches. With `team`, restrict to that team's own
// bans/picks and build counter-bans; without, aggregate league-wide.
function aggregate(matches, team){
  const a={bans:{}, banRoles:{}, maps:{}, perMap:{}, counter:{}, games:0, gwins:0};
  matches.forEach(m=>{
    const side = team? (m.f1===team?'faction1':(m.f2===team?'faction2':null)) : 'x';
    if(team && !side) return;
    m.games.forEach(g=>{
      if(!g.map) return;
      a.games++;
      if(team){
        if(g.winner_faction===side) a.gwins++;
        if(g.map_picked_by===team) inc(a.maps, g.map);
        const mine=g.bans.find(b=>b.team===team);
        const opp =g.bans.find(b=>b.team && b.team!==team);
        if(mine){ inc(a.bans,mine.hero); if(mine.role) inc(a.banRoles,mine.role);
          (a.perMap[g.map]=a.perMap[g.map]||{}); inc(a.perMap[g.map],mine.hero);
          if(opp){ (a.counter[opp.hero]=a.counter[opp.hero]||{}); inc(a.counter[opp.hero],mine.hero); } }
      } else {
        inc(a.maps, g.map);
        g.bans.forEach(b=>{ inc(a.bans,b.hero); if(b.role) inc(a.banRoles,b.role); });
      }
    });
  });
  return a;
}

function teamTrends(team, limit){
  const mine = MATCHES_RECENT.filter(m=>m.f1===team||m.f2===team);
  const used = recent(mine, limit);
  const {from,to}=dateRange(used);
  return {team, matchesUsed:used.length, matchesTotal:mine.length, from, to, ...aggregate(used, team)};
}

// Window <select> builder shared by the team/hero/map tabs.
function windowSelect(opts, current, onchange){
  const style='font-size:14px;padding:6px 8px;border-radius:8px;background:var(--bg);color:var(--fg);border:1px solid var(--line)';
  const s=$(`<select style="${style}"></select>`);
  opts.forEach(([v,l])=>s.appendChild($(`<option value="${v}" ${v===current?'selected':''}>${l}</option>`)));
  s.onchange=()=>onchange(s.value);
  return s;
}
function windowNote(used, total, noun){
  return used<total? `last <b>${used}</b> of ${total} ${noun}` : `all <b>${total}</b> ${noun}`;
}

function heroChips(pairs){ // pairs: [ [hero,count], ... ]
  return pairs.map(([h,n])=>`<span class="badge role-${esc(HERO_ROLE[h]||'')}" style="margin:1px">${esc(h)} ${n}</span>`).join(' ');
}

function renderTeam(t){
  const w=$(`<div></div>`);
  w.appendChild($(`<div class="card"><b>${esc(t.team)}</b> &middot; ${windowNote(t.matchesUsed,t.matchesTotal,'matches')} &middot; `+
    `game win rate ${t.gwins}/${t.games} (${pct(t.gwins,t.games)}) &middot; `+
    `<span class="note">${esc(dateShort(t.from))} → ${esc(dateShort(t.to))}</span></div>`));

  w.appendChild($(`<h2>Preferred bans</h2>`));
  const banItems = rank(t.bans).slice(0,20).map(([h,n])=>({name:h,role:HERO_ROLE[h],n}));
  w.appendChild(banItems.length? $(bars(banItems, i=>`${esc(i.name)} <span class="badge">${esc(i.role||'')}</span>`,'n',roleColor))
                               : $(`<p class="note">No attributed bans.</p>`));

  w.appendChild($(`<h2>Preferred maps (picked)</h2>`));
  const mapItems = rank(t.maps).map(([m,n])=>({name:m,n}));
  w.appendChild(mapItems.length? $(bars(mapItems, i=>esc(i.name),'n'))
                               : $(`<p class="note">No attributed map picks.</p>`));

  w.appendChild($(`<h2>Bans by map</h2>`));
  const mapRows = Object.keys(t.perMap).sort().map(mp=>({
    map:mp, games:Object.values(t.perMap[mp]).reduce((a,b)=>a+b,0),
    bans:heroChips(rank(t.perMap[mp]))}));
  w.appendChild(mapRows.length? sortable([
    {k:'map',label:'Map'},{k:'games',label:'Bans',num:true},{k:'bans',label:'Heroes banned',html:r=>r.bans},
  ], mapRows) : $(`<p class="note">No data.</p>`));

  w.appendChild($(`<h2>Counter-bans <span class="note">(when the opponent banned X this game, ${esc(t.team)} banned…)</span></h2>`));
  const cRows = rank(Object.fromEntries(Object.entries(t.counter).map(([k,v])=>[k,Object.values(v).reduce((a,b)=>a+b,0)])))
    .map(([opp,tot])=>({opp, tot, resp:heroChips(rank(t.counter[opp]))}));
  w.appendChild(cRows.length? sortable([
    {k:'opp',label:'Opponent banned',html:r=>`<span class="badge role-${esc(HERO_ROLE[r.opp]||'')}">${esc(r.opp)}</span>`},
    {k:'tot',label:'Times',num:true},
    {k:'resp',label:`${esc(t.team)} responded with`,html:r=>r.resp},
  ], cRows) : $(`<p class="note">No paired bans (needs both teams' bans attributed).</p>`));
  return w;
}

const TABS = [
  {id:'overview', label:'Overview', render:()=>{
    const s=DATA.summary;
    const tiles=[['matches','Matches'],['played_games','Games played'],['teams','Teams'],
      ['players','Players'],['walkovers','Walkovers (no games)'],['matches_with_attribution','Matches w/ veto attribution'],
      ['restarted_games','Restarted games'],['dc_games','Games w/ a DC (stats NULL)']];
    const g=$(`<div class="grid"></div>`);
    tiles.forEach(([k,l])=>g.appendChild($(`<div class="card tile"><div class="n">${s[k]==null?0:s[k]}</div><div class="l">${l}</div></div>`)));
    const wrap=$(`<div></div>`); wrap.appendChild(g);
    wrap.appendChild($(`<p class="note">Veto attribution present for <b>${s.matches_with_attribution}/${s.matches}</b> matches &mdash; `+
      `recovered from FACEIT's durable veto-history feed. Only walkovers and genuinely disrupted vetos (restarts / paused vetos) lack it.</p>`));
    wrap.appendChild($(`<p class="note">Data range: ${esc(s.date_from)} &rarr; ${esc(s.date_to)}. Region: ${esc(s.region||'—')}.</p>`));
    return wrap;
  }},
  {id:'teams', label:'Teams', render:()=>{
    const wrap=$(`<div></div>`);
    wrap.appendChild($(`<p class="note">Click a column header to sort — e.g. Wins or Win %.</p>`));
    wrap.appendChild(sortable([
      {k:'name',label:'Team'},
      {k:'matches',label:'Matches',num:true},
      {k:'wins',label:'Wins',num:true},
      {k:'win_pct',label:'Win %',num:true,html:r=>r.win_pct+'%'},
    ], DATA.teams));
    return wrap;
  }},
  {id:'team', label:'Team trends', render:()=>{
    const wrap=$(`<div></div>`);
    const bar=$(`<div class="card" style="display:flex;gap:14px;align-items:center;flex-wrap:wrap"></div>`);
    const body=$(`<div></div>`);
    const draw=()=>{
      const lim = WIN_TEAM==='all'? null : parseInt(WIN_TEAM,10);
      body.innerHTML=''; body.appendChild(renderTeam(teamTrends(SELECTED_TEAM, lim)));
    };
    bar.appendChild($(`<label style="color:var(--muted);font-size:13px">Team</label>`));
    const sel=$(`<select style="font-size:14px;padding:6px 8px;border-radius:8px;background:var(--bg);color:var(--fg);border:1px solid var(--line)"></select>`);
    DATA.team_names.forEach(n=>sel.appendChild($(`<option ${n===SELECTED_TEAM?'selected':''}>${esc(n)}</option>`)));
    sel.onchange=()=>{ SELECTED_TEAM=sel.value; draw(); };
    bar.appendChild(sel);
    bar.appendChild($(`<label style="color:var(--muted);font-size:13px">Recent</label>`));
    bar.appendChild(windowSelect(
      [['all','All matches'],['15','Last 15'],['10','Last 10'],['5','Last 5']],
      WIN_TEAM, v=>{ WIN_TEAM=v; draw(); }));
    wrap.appendChild(bar); wrap.appendChild(body); draw();
    return wrap;
  }},
  {id:'heroes', label:'Hero bans', render:()=>{
    const wrap=$(`<div></div>`);
    const bar=$(`<div class="card" style="display:flex;gap:12px;align-items:center;flex-wrap:wrap"></div>`);
    const body=$(`<div></div>`);
    const draw=()=>{
      const lim = WIN_BANS==='all'? null : parseInt(WIN_BANS,10);
      const ms = recent(MATCHES_RECENT, lim), a = aggregate(ms, null), {from,to}=dateRange(ms);
      const totalBans = Object.values(a.bans).reduce((x,y)=>x+y,0);
      body.innerHTML='';
      const v=$(`<div></div>`);
      v.appendChild($(`<p class="note">${windowNote(ms.length,MATCHES_RECENT.length,'matches')} &middot; ${totalBans} bans &middot; ${esc(dateShort(from))} → ${esc(dateShort(to))}</p>`));
      v.appendChild($(`<h2>Most banned</h2>`));
      const items = rank(a.bans).slice(0,20).map(([h,n])=>({name:h,role:HERO_ROLE[h],n}));
      v.appendChild(items.length? $(bars(items, i=>`${esc(i.name)} <span class="badge">${esc(i.role||'')}</span>`,'n',roleColor)) : $(`<p class="note">No bans in this window.</p>`));
      v.appendChild($(`<h2>Bans by role</h2>`));
      v.appendChild($(bars(rank(a.banRoles).map(([r,n])=>({role:r,n})), i=>roleSpan(i.role),'n',roleColor)));
      body.appendChild(v);
    };
    bar.appendChild($(`<label style="color:var(--muted);font-size:13px">Recent</label>`));
    bar.appendChild(windowSelect([['all','All matches'],['40','Last 40'],['20','Last 20'],['10','Last 10'],['5','Last 5']], WIN_BANS, v=>{WIN_BANS=v;draw();}));
    bar.appendChild($(`<span class="note">how the league's ban meta shifts — a nerfed hero fades from recent windows</span>`));
    wrap.appendChild(bar); wrap.appendChild(body); draw();
    return wrap;
  }},
  {id:'maps', label:'Maps', render:()=>{
    const wrap=$(`<div></div>`);
    const bar=$(`<div class="card" style="display:flex;gap:12px;align-items:center;flex-wrap:wrap"></div>`);
    const body=$(`<div></div>`);
    const draw=()=>{
      const lim = WIN_MAPS==='all'? null : parseInt(WIN_MAPS,10);
      const ms = recent(MATCHES_RECENT, lim), a = aggregate(ms, null), {from,to}=dateRange(ms);
      body.innerHTML='';
      const v=$(`<div></div>`);
      v.appendChild($(`<p class="note">${windowNote(ms.length,MATCHES_RECENT.length,'matches')} &middot; ${esc(dateShort(from))} → ${esc(dateShort(to))}</p>`));
      v.appendChild($(`<h2>Map usage</h2>`));
      const items = rank(a.maps).map(([m,n])=>({name:m,cat:MAP_CAT[m],n}));
      v.appendChild($(bars(items, i=>`${esc(i.name)} <span class="badge">${esc(i.cat||'')}</span>`,'n')));
      body.appendChild(v);
    };
    bar.appendChild($(`<label style="color:var(--muted);font-size:13px">Recent</label>`));
    bar.appendChild(windowSelect([['all','All matches'],['40','Last 40'],['20','Last 20'],['10','Last 10'],['5','Last 5']], WIN_MAPS, v=>{WIN_MAPS=v;draw();}));
    wrap.appendChild(bar); wrap.appendChild(body);
    draw();
    // Attacking-first advantage is a balance question, not a meta-timing one, so
    // it stays all-season.
    const af=DATA.attacking_first;
    wrap.appendChild($(`<h2>Attacking-first advantage (Escort &amp; Hybrid only, all season)</h2>`));
    wrap.appendChild($(`<p class="note">Only asymmetric modes &mdash; Control/Flashpoint/Push are mirrored, so attack order is meaningless there. Overall: attacker-first won <b>${af.atk_first_wins}/${af.total_games}</b> = <b>${pct(af.atk_first_wins,af.total_games)}</b>.</p>`));
    wrap.appendChild(sortable([
      {k:'name',label:'Map'},{k:'category',label:'Mode'},
      {k:'games',label:'Games',num:true},
      {k:'wr',label:'Atk-first win%',num:true,html:r=>r.wr.toFixed(0)+'%'},
    ], af.by_map.map(m=>({...m, wr:m.games?(100*m.atk_first_wins/m.games):0}))));
    return wrap;
  }},
  {id:'matches', label:'Matches', render:()=>{
    const wrap=$(`<div></div>`);
    const search=$(`<input placeholder="search team, hero, or map…" `+
      `style="width:100%;font-size:15px;padding:10px 12px;border-radius:10px;margin-bottom:10px;`+
      `background:var(--card);color:var(--fg);border:1px solid var(--line)">`);
    const list=$(`<div></div>`);
    wrap.appendChild(search); wrap.appendChild(list);

    const heroChip=(b)=> b.team
      ? `<span class="badge role-${esc(b.role||'')}" title="${esc(b.team)}">${esc(b.hero)}</span>`
      : `<span class="badge">${esc(b.hero)}<span class="note"> ?</span></span>`;

    const haystack=(m)=>[m.f1,m.f2,...m.games.flatMap(g=>[g.map,...g.bans.map(b=>b.hero)])]
      .filter(Boolean).join(' ').toLowerCase();

    function draw(q){
      q=(q||'').trim().toLowerCase();
      list.innerHTML='';
      const shown=DATA.matches.filter(m=>!q || haystack(m).includes(q));
      if(!shown.length){ list.appendChild($(`<p class="note">No matches.</p>`)); return; }
      shown.forEach(m=>{
        const c=$(`<div class="card match"></div>`);
        const w1=m.winner==='faction1', w2=m.winner==='faction2';
        c.appendChild($(`<div class="hd">`+
          `<div><span class="${w1?'win':''}">${esc(m.f1||'?')}</span>`+
            `<b> ${esc(m.series)} </b><span class="${w2?'win':''}">${esc(m.f2||'?')}</span></div>`+
          `<div>${m.walkover?'<span class="badge ff">walkover</span> ':(m.forfeit?'<span class="badge ff">forfeit</span> ':'')}`+
            `<span class="badge">R${esc(m.round)} G${esc(m.group)}</span></div></div>`));
        m.games.filter(g=>g.map).forEach(g=>{
          const f1b=g.bans.filter(b=>b.faction==='faction1'), f2b=g.bans.filter(b=>b.faction==='faction2');
          const un=g.bans.filter(b=>!b.faction);
          const line=$(`<div style="border-top:1px solid var(--line);padding:6px 2px;font-size:13.5px"></div>`);
          line.innerHTML =
            `<b>G${g.game_no}</b> ${esc(g.map)} <span class="badge">${esc(g.map_category||'')}</span> `+
            `<span class="win">${esc(g.f1)}-${esc(g.f2)}</span> → ${esc(g.winner_team||'?')}`+
            (g.was_restarted?' <span class="badge rs">restart</span>':'')+
            (g.map_picked_by?` <span class="note">· map: ${esc(g.map_picked_by)}</span>`:'')+
            `<div style="margin-top:4px">`+
              `<span class="note">${esc(m.f1||'F1')} ban:</span> ${f1b.map(heroChip).join(' ')||'—'} `+
              `&nbsp;&nbsp;<span class="note">${esc(m.f2||'F2')} ban:</span> ${f2b.map(heroChip).join(' ')||'—'}`+
              (un.length?` <span class="note">(unattributed: ${un.map(b=>esc(b.hero)).join(', ')})</span>`:'')+
            `</div>`;
          c.appendChild(line);
        });
        list.appendChild(c);
      });
    }
    search.oninput=()=>draw(search.value);
    draw('');
    return wrap;
  }},
];

function show(id){
  document.querySelectorAll('nav button').forEach(b=>b.classList.toggle('active',b.dataset.id===id));
  const c=document.getElementById('content'); c.innerHTML='';
  c.appendChild(TABS.find(t=>t.id===id).render());
  location.hash=id;
}
function init(){
  document.getElementById('title').textContent=DATA.summary.championship;
  document.getElementById('subtitle').textContent=
    `${DATA.summary.matches} matches · ${DATA.summary.played_games} games · generated by faceit-sync`;
  const nav=document.getElementById('nav');
  TABS.forEach(t=>{const b=$(`<button data-id="${t.id}">${t.label}</button>`);b.onclick=()=>show(t.id);nav.appendChild(b);});
  const start=(location.hash||'#overview').slice(1);
  show(TABS.some(t=>t.id===start)?start:'overview');
}
init();
</script>
</body>
</html>
"""

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
<title>OW Scout &mdash; FACEIT League</title>
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
.prodname{display:block;font-size:11px;font-weight:800;letter-spacing:.14em;color:var(--accent);margin-bottom:2px}
.prodname span{color:var(--faint);font-weight:600;letter-spacing:.08em}
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
.eyebrow{font-size:10.5px;font-weight:700;text-transform:uppercase;letter-spacing:.07em;color:var(--faint);margin:0 0 6px}
.card{background:var(--surface);border:1px solid var(--line);border-radius:10px;padding:12px 14px;box-shadow:none}
.grid{display:grid;gap:10px}
.cols-2{grid-template-columns:1fr 1fr}
.cols-3{grid-template-columns:1fr 1fr 1fr}
.poolgrid{grid-template-columns:repeat(auto-fill,minmax(240px,1fr))}
.cols-auto{grid-template-columns:repeat(auto-fit,minmax(150px,1fr))}
@media (max-width:720px){.cols-2,.cols-3{grid-template-columns:1fr}}
@media (max-width:980px) and (min-width:721px){.cols-3{grid-template-columns:1fr 1fr}}
.section-h{display:flex;align-items:baseline;justify-content:space-between;gap:12px;
  margin:22px 2px 8px;padding-bottom:6px;border-bottom:1px solid var(--line)}
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
input[type=range]{appearance:auto;-webkit-appearance:auto;border:none;padding:0;margin:0;background:transparent;
  box-shadow:none;accent-color:var(--accent);width:150px;height:18px;cursor:pointer;vertical-align:middle}
input[type=range]:focus{outline:none;border-color:transparent;box-shadow:none}
input[type=range]:focus-visible{outline:2px solid var(--accent);outline-offset:5px;border-radius:3px}
input[type=number]{width:56px;text-align:center;padding:7px 6px}
.recency{display:inline-flex;align-items:center;gap:10px}
.winlab{color:var(--muted);font-size:12.5px;font-weight:600;white-space:nowrap}
.btn{cursor:pointer;font-weight:600;background:var(--accent);color:#fff;border-color:transparent}
.btn:hover{filter:brightness(1.06)}

/* tables */
table{width:100%;border-collapse:collapse}
th,td{text-align:left;padding:8px 11px;border-bottom:1px solid var(--line);white-space:nowrap;font-size:13.5px}
thead th{color:var(--faint);font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:.04em;
  cursor:pointer;user-select:none;position:sticky;top:0;background:var(--surface);white-space:nowrap}
thead th:hover{color:var(--fg)}
thead th.sorted{color:var(--fg)}
thead th .sar{margin-left:4px;font-size:8px;color:var(--accent);vertical-align:middle}
th.num,td.num{text-align:right;font-variant-numeric:tabular-nums}
tbody tr:hover{background:var(--surface2)}
/* Mode separator inside a map table: a visible break, not just a repeated tag. */
tbody tr.grp td{padding:14px 11px 5px;border-bottom:1px solid var(--line);
  font-size:10.5px;font-weight:700;text-transform:uppercase;letter-spacing:.08em;
  color:var(--muted);background:var(--surface2)}
tbody tr.grp:first-child td{padding-top:6px}
tbody tr.grp:hover{background:var(--surface2)}
/* Block table: several rows describe ONE subject (a hero, both ban cases). The
   rows inside a block run together; only the block boundary gets a rule. */
table.blocks td{border-bottom:none;padding-top:5px;padding-bottom:5px}
table.blocks tr.blk td{border-top:1px solid var(--line);padding-top:11px}
table.blocks tr.blk:first-child td{border-top:none}
table.blocks thead th{cursor:default}
table.blocks thead th:hover{color:var(--faint)}
/* A long list that must not push the rest of the page down. Tall enough to show
   a few entries, capped so the sections below stay reachable. */
.scrollbox{max-height:min(60vh,560px);overflow-y:auto;overscroll-behavior:contain;
  border:1px solid var(--line);border-radius:10px;padding:10px;background:var(--bg)}
.scrollbox>*+*{margin-top:8px}
.ctlrow{display:flex;gap:8px;align-items:center;margin:0 0 8px}
.sortbtn{font:inherit;font-size:12.5px;font-weight:600;cursor:pointer;color:var(--fg);
  background:var(--surface2);border:1px solid var(--line2);border-radius:8px;padding:4px 10px}
.sortbtn:hover{border-color:var(--accent);color:var(--accent)}
.scroll{overflow-x:auto;border:1px solid var(--line);border-radius:12px}
.scroll table{font-size:13.5px}

/* bars */
.barrow{display:grid;grid-template-columns:minmax(110px,1.1fr) minmax(70px,2fr) 40px;align-items:center;gap:11px;padding:5px 2px}
.barrow+.barrow{border-top:1px solid color-mix(in srgb,var(--line) 55%,transparent)}
.barrow .lab{font-size:13px;display:flex;align-items:center;gap:7px;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.track{height:9px;background:var(--surface2);border-radius:6px;overflow:hidden}
.fill{height:100%;border-radius:6px;background:var(--accent);min-width:3px;transition:width .2s ease}
.barval{text-align:right;font-size:12.5px;font-weight:650;color:var(--muted);font-variant-numeric:tabular-nums}
.poolrow{display:flex;align-items:center;justify-content:space-between;gap:10px;padding:6px 2px;font-size:13px}
.poolrow+.poolrow{border-top:1px solid color-mix(in srgb,var(--line) 55%,transparent)}
.poolrow .pm{font-weight:600;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.poolrow .pr{flex:none;white-space:nowrap;font-variant-numeric:tabular-nums;text-align:right}
.poolrow .pk{font-weight:700}
.poolrow .pp{color:var(--faint);font-size:11px;margin-left:7px}
/* draft simulator */
.probbar{display:flex;height:38px;border-radius:10px;overflow:hidden;font-weight:750;font-size:13.5px;box-shadow:inset 0 0 0 1px var(--line)}
.probbar>span{display:flex;align-items:center;padding:0 13px;white-space:nowrap;transition:flex-basis .35s ease}
.probbar .pa{background:var(--accent);color:#fff}
.probbar .pb{background:color-mix(in srgb,var(--bad) 78%,#000 0%);color:#fff;justify-content:flex-end}
.simblock{border:1px solid var(--line);border-radius:12px;padding:12px 14px;margin-top:10px;background:var(--surface);position:relative}
.simblock .bh{font-weight:680;font-size:13.5px;margin-bottom:6px;display:flex;gap:8px;align-items:center;flex-wrap:wrap}
.simrow{display:flex;gap:6px;flex-wrap:wrap;align-items:center;margin:7px 0}
.simrow .rl{font-size:10.5px;text-transform:uppercase;letter-spacing:.06em;color:var(--faint);min-width:82px;flex:none}
.modelbl{font-size:10px;text-transform:uppercase;letter-spacing:.06em;color:var(--faint);min-width:74px;flex:none;font-weight:700}
.opt{border:1px solid var(--line2);background:var(--surface2);border-radius:8px;padding:4px 9px;font-size:12.5px;cursor:pointer;display:inline-flex;gap:6px;align-items:center;user-select:none;line-height:1.5}
.opt:hover{border-color:var(--accent)}
.opt.sel{background:var(--accent-weak);border-color:var(--accent);font-weight:650}
.opt .pp{color:var(--faint);font-size:11px;font-variant-numeric:tabular-nums}
.opt.sel .pp{color:var(--accent)}
.opt.dim{opacity:.55}
.wsel{display:flex;gap:6px;flex-wrap:wrap;align-items:center}
.wbtn{border:1px solid var(--line2);border-radius:8px;padding:5px 12px;font-size:12.5px;cursor:pointer;font-weight:650}
.wbtn:hover{border-color:var(--accent)}
.wbtn.selA{background:var(--accent);color:#fff;border-color:var(--accent)}
.wbtn.selB{background:color-mix(in srgb,var(--bad) 82%,#000);color:#fff;border-color:transparent}
.simnext{font-size:11.5px;color:var(--faint);margin-top:8px}
.simscore{font-variant-numeric:tabular-nums;font-weight:750}

/* chips / badges */
.chip{display:inline-flex;align-items:center;gap:5px;font-size:11.5px;font-weight:600;padding:2px 8px;
  border-radius:20px;background:var(--surface2);color:var(--muted);border:1px solid var(--line)}
.dot{width:7px;height:7px;border-radius:50%;flex:none}
/* Hero portraits. A comp reads as five faces, not five words. The role colour
   survives as a ring so role composition is still scannable at a glance. */
.hicon{width:28px;height:28px;border-radius:7px;flex:none;display:inline-block;vertical-align:middle;
  object-fit:cover;background:var(--surface2);box-shadow:0 0 0 1.5px var(--line2)}
.hicon.r-Tank{box-shadow:0 0 0 1.5px var(--tank)}
.hicon.r-Damage{box-shadow:0 0 0 1.5px var(--damage)}
.hicon.r-Support{box-shadow:0 0 0 1.5px var(--support)}
.hicon.sm{width:18px;height:18px;border-radius:5px;box-shadow:none;margin:-1px 1px -1px -3px}
.chip.ico{padding-left:4px;gap:4px}
.comp{display:inline-flex;align-items:center;gap:4px}
.comp .hicon+.hicon{margin-left:0}
/* A row of icons + a right-aligned record; the workhorse of the scouting page. */
.crow{display:flex;align-items:center;justify-content:space-between;gap:12px;padding:7px 2px}
.crow+.crow{border-top:1px solid color-mix(in srgb,var(--line) 55%,transparent)}
.crow .rec{flex:none;white-space:nowrap;font-variant-numeric:tabular-nums;color:var(--muted);font-size:12.5px}
.crow.thin{opacity:.55}                      /* n=1: present, but visibly weak evidence */
details.mapblk{border:1px solid var(--line);border-radius:10px;background:var(--surface);margin-bottom:8px}
details.mapblk>summary{cursor:pointer;list-style:none;padding:10px 12px;display:flex;
  align-items:center;justify-content:space-between;gap:10px;font-weight:650}
details.mapblk>summary::-webkit-details-marker{display:none}
details.mapblk>summary::after{content:'be';color:var(--muted);transition:transform .15s}
details.mapblk[open]>summary::after{transform:rotate(180deg)}
details.mapblk>summary:hover{background:var(--surface2);border-radius:10px}
/* Two columns inside a map: openers on the left, the swaps seen there on the
   right (the right half was dead space before). Collapses on narrow screens. */
.mapbody{padding:2px 12px 12px;display:grid;grid-template-columns:1fr 1fr;gap:0 22px}
.mapcol.swaps{border-left:1px solid var(--line);padding-left:20px}
@media(max-width:820px){.mapbody{grid-template-columns:1fr}
  .mapcol.swaps{border-left:none;padding-left:0;border-top:1px solid var(--line);margin-top:10px}}
.seg{font-size:11px;font-weight:700;letter-spacing:.06em;text-transform:uppercase;
  color:var(--muted);margin:10px 0 2px}
/* Mode heading over a run of map blocks - the same break the tables get. */
.modeh{font-size:10.5px;font-weight:700;letter-spacing:.08em;text-transform:uppercase;
  color:var(--muted);margin:16px 0 6px;padding-bottom:4px;border-bottom:1px solid var(--line)}
.modeh:first-of-type{margin-top:8px}
/* A sub-map / phase separator is a heading; "then" is a note ON a row, so it must
   not read as one - it is inline, lighter, and lower-case. */
.then{font-size:10.5px;font-weight:700;text-transform:uppercase;letter-spacing:.04em;
  color:var(--faint);background:var(--surface2);border-radius:4px;padding:1px 5px;margin-right:6px}
.swapline{display:flex;align-items:center;gap:6px;flex-wrap:wrap}
.arr{color:var(--faint)}
.role-Tank{color:var(--tank)} .role-Damage{color:var(--damage)} .role-Support{color:var(--support)}
.bg-Tank{background:var(--tank)} .bg-Damage{background:var(--damage)} .bg-Support{background:var(--support)}
.pill{display:inline-block;font-size:12px;font-weight:650;padding:1px 8px;border-radius:7px}
.tag{display:inline-block;font-size:10.5px;font-weight:700;text-transform:uppercase;letter-spacing:.03em;
  padding:1px 6px;border-radius:5px;background:var(--surface2);color:var(--faint)}
.tag.warn{background:color-mix(in srgb,var(--mid) 20%,transparent);color:var(--mid)}
.tag.ok{background:color-mix(in srgb,var(--good) 18%,transparent);color:var(--good)}
.tag.bad{background:color-mix(in srgb,var(--bad) 18%,transparent);color:var(--bad)}
.wl{display:inline-flex;gap:3px}
.wl b{width:16px;height:16px;border-radius:4px;font-size:10px;font-weight:700;color:#fff;
  display:inline-flex;align-items:center;justify-content:center}
.wl .w{background:var(--good)} .wl .l{background:var(--bad)}

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
.bans{display:flex;gap:6px 4px;flex-wrap:wrap;align-items:center;margin-top:7px}
.banstep{display:inline-flex;align-items:center;gap:5px;margin-right:16px}
.ord{width:17px;height:17px;border-radius:50%;background:var(--accent-weak);color:var(--accent);
  font-size:10.5px;font-weight:700;display:inline-flex;align-items:center;justify-content:center;flex:none}
.rosters{display:grid;grid-template-columns:1fr 1fr;gap:14px;margin-top:10px}
@media (max-width:640px){.rosters{grid-template-columns:1fr}}
/* ---- mobile pass: prep links get opened from Discord on phones ---- */
@media (max-width:640px){
  main{padding:12px 10px 48px}               /* reclaim edge gutters */
  .topbar-in{padding:10px 10px 0}
  nav{overflow-x:auto;-webkit-overflow-scrolling:touch;scrollbar-width:none}
  nav::-webkit-scrollbar{display:none}
  nav button{white-space:nowrap;padding:9px 10px;font-size:13px}
  .card{padding:10px}
  .controls{flex-wrap:wrap;row-gap:8px}
  .game-hd{flex-wrap:wrap;row-gap:4px}       /* map + score + code stack cleanly */
  .game-hd>span[style*="margin-left:auto"]{margin-left:0!important;width:100%}
  th,td{padding:6px 7px;font-size:12.5px}
  .crow{gap:8px}
  .crow .rec{font-size:11.5px}
}
.roster h4{margin:0 0 6px;font-size:12px;color:var(--muted);font-weight:650}
.roster .pl{display:grid;grid-template-columns:14px 1fr auto;gap:8px;align-items:center;padding:3px 0;
  border-top:1px solid var(--line);font-size:12.5px}
.roster .pl .st{color:var(--faint);font-size:11.5px;font-variant-numeric:tabular-nums}
.muted{color:var(--muted)} .faint{color:var(--faint)}
.rc{font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;font-size:11.5px;font-weight:600;
  background:var(--surface2);color:var(--fg);padding:1.5px 7px;border-radius:6px;cursor:pointer;
  border:1px solid var(--line2);letter-spacing:.03em}
.rc:hover{border-color:var(--accent);color:var(--accent)}
.rc.copied{color:var(--good);border-color:var(--good)}
.hidden{display:none}
</style>
</head>
<body>
<div class="topbar"><div class="topbar-in">
  <div class="brand"><span class="prodname">OW SCOUT <span>FACEIT League</span></span>
    <h1 id="title"></h1>
    <select id="division" class="hidden" aria-label="Division"></select>
    <span class="meta" id="subtitle"></span></div>
  <nav id="nav"></nav>
</div></div>
<main id="content"></main>
<script>
const DATA = __DATA__;
const DIVS = DATA.divisions, VIEWS = DATA.views;   // real divisions + combined views
let CURRENT_VIEW = VIEWS[0].id;
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
  const teams=[].concat(...ds.map(d=>d.teams));
  const team_names=[...new Set([].concat(...ds.map(d=>d.team_names)))].sort();
  const sum={championship:v.label, region:v.region};
  ['matches','played_games','teams','players','walkovers','matches_with_attribution','restarted_games','dc_games']
    .forEach(k=> sum[k]=ds.reduce((a,d)=>a+(d.summary[k]||0),0));
  const fr=ds.map(d=>d.summary.date_from).filter(Boolean).sort();
  const to=ds.map(d=>d.summary.date_to).filter(Boolean).sort();
  sum.date_from=fr[0]||''; sum.date_to=to[to.length-1]||'';
  const bm={};
  ds.forEach(d=>d.attacking_first.by_map.forEach(m=>{
    const e=bm[m.name]||(bm[m.name]={name:m.name,category:m.category,games:0,atk_first_wins:0});
    e.games+=m.games; e.atk_first_wins+=m.atk_first_wins; }));
  const af={by_map:Object.values(bm).sort((a,b)=>b.games-a.games),
    total_games:ds.reduce((a,d)=>a+d.attacking_first.total_games,0),
    atk_first_wins:ds.reduce((a,d)=>a+d.attacking_first.atk_first_wins,0)};
  return {summary:sum, teams, team_names, matches, attacking_first:af};
}

/* ---------- tiny DOM + format helpers ---------- */
const el = (h)=>{const t=document.createElement('template');t.innerHTML=h.trim();return t.content.firstChild;};
const esc = (s)=> (s==null?'':String(s)).replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
const nf = (n)=> (n==null?'—':Number(n).toLocaleString('en-US'));
const pctOf = (a,b)=> b? Math.round(100*a/b) : 0;
const dshort = (s)=> s? String(s).slice(0,10) : '?';
const inc = (o,k,by=1)=>{ o[k]=(o[k]||0)+by; };
const rank = (o)=> Object.entries(o).sort((a,b)=>b[1]-a[1]);   // NB: not `top` (window.top is reserved)

const HERO_ROLE={}; DATA.heroes.forEach(h=>HERO_ROLE[h.name]=h.role);
// Full roster (all heroes, incl. never-banned ones) for the draft simulator's hero picker.
const ROSTER = (DATA.roster&&DATA.roster.length)? DATA.roster : DATA.heroes;
ROSTER.forEach(h=>{ if(!HERO_ROLE[h.name]) HERO_ROLE[h.name]=h.role; });
const MAP_CAT={}; DATA.maps.forEach(m=>MAP_CAT[m.name]=m.category);
// Competitive seats (Tank / Hitscan / Flex DPS / Main Support / Flex Support).
// Unclassified heroes have no seat and fall back to base role everywhere.
const HERO_SEAT={}; (DATA.heroes||[]).forEach(h=>{ if(h.subrole) HERO_SEAT[h.name]=h.subrole; });
const SEATS=DATA.seat_order||['Tank','Hitscan','Flex DPS','Main Support','Flex Support'];
// Games whose comps have been captured by owscout ("match_id:game_no").
const CAPTURED=new Set(DATA.owscout_captured||[]);
// OW wipes invalidate replay codes each patch: a game finished on or before this
// date can never be replayed, so it is only "scoutable" if already captured.
const CODE_WIPE=DATA.code_wipe||null;
const codeDead=(when)=>!!(CODE_WIPE&&when&&String(when).slice(0,10)<=CODE_WIPE);
// Map lists everywhere read as a mode block at a time (all Control together, etc),
// and within a mode the maps the league actually plays come first.
const MODE_ORDER=['Control','Escort','Hybrid','Flashpoint','Push','Clash'];
const MAP_POP={};
Object.values(DIVS).forEach(d=>d.matches.forEach(m=>m.games.forEach(g=>{
  if(g.map) MAP_POP[g.map]=(MAP_POP[g.map]||0)+1; })));
function modeRank(mp){ const i=MODE_ORDER.indexOf(MAP_CAT[mp]||''); return i<0?MODE_ORDER.length:i; }
function mapCmp(a,b){ return modeRank(a)-modeRank(b) || (MAP_POP[b]||0)-(MAP_POP[a]||0)
                          || a.localeCompare(b); }
function sortMaps(names){ return names.slice().sort(mapCmp); }
const roleVar = (r)=> ({Tank:'var(--tank)',Damage:'var(--damage)',Support:'var(--support)'}[r]||'var(--accent)');
const winVar = (p)=> p>=58?'var(--good)': p>=42?'var(--mid)':'var(--bad)';

/* recency: matches newest-first (recency is measured in matches ≈ how a season is counted).
   Recomputed whenever the active division changes. */
let MATCHES_RECENT=[];
function recomputeDivision(){
  MATCHES_RECENT=[...D().matches].sort((a,b)=>{const x=a.finished_at||'',y=b.finished_at||'';return x===y?0:(x<y?1:-1);});
  SCOUT_TEAM=D().team_names[0]||null; SCOUT_N=null;
  const tn=D().team_names;
  SIM_A=tn[0]||null; SIM_B=tn[1]||tn[0]||null; SIM_FIRST='A'; SIM_PATH=[];
}
const recent=(arr,lim)=> (lim && lim<arr.length)? arr.slice(0,lim) : arr;
const dateRange=(ms)=>{const w=ms.map(m=>m.finished_at).filter(Boolean).sort();return {from:w[0]||'',to:w[w.length-1]||''};};

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
function compRow(heroes){ return `<span class="comp">${byRole(heroes).map(h=>heroIcon(h)).join('')}</span>`; }
// A comp change is only interesting in the heroes that moved - repeating the four
// unchanged portraits buries the one that matters. null = no change at all.
function compDelta(from,to){
  const a=new Set(from), b=new Set(to);
  const out=from.filter(h=>!b.has(h)), inn=to.filter(h=>!a.has(h));
  return (out.length||inn.length)?{out,in:inn}:null;
}
function deltaHtml(d){ return `${compRow(d.out)}<span class="arr">&rarr;</span>${compRow(d.in)}`; }
function swapLine(s){
  const trig=(s.vs&&s.vs.length)
    ? `<span class="faint">vs</span>${compRow(s.vs.slice(0,3))}<span class="arr">&rarr;</span>`
    : '';
  return `<div class="crow${s.count<=1?' thin':''}">`+
    `<span class="swapline">${trig}${deltaHtml({out:s.out,in:s.in})}</span>`+
    `<span class="rec">${s.count}x · ${s.kind==='core'?'comp change':'flex'}</span></div>`;
}
function pill(text,color){ return `<span class="pill" style="background:color-mix(in srgb,${color} 16%,transparent);color:${color}">${esc(text)}</span>`; }
function tag(text,cls=''){ return `<span class="tag ${cls}">${esc(text)}</span>`; }
// Overwatch replay code — click to copy (paste into OW2 → Watch → Replays).
function rcChip(code){ return `<code class="rc" data-rc="${esc(code)}" title="Copy replay code — paste in Overwatch → Watch">${esc(code)}</code>`; }
function copyText(t){
  if(navigator.clipboard && window.isSecureContext) return navigator.clipboard.writeText(t);
  return new Promise((res,rej)=>{ try{ const ta=document.createElement('textarea');
    ta.value=t; ta.style.position='fixed'; ta.style.top='-999px'; document.body.appendChild(ta);
    ta.focus(); ta.select(); const ok=document.execCommand('copy'); document.body.removeChild(ta);
    ok?res():rej(); }catch(err){ rej(err); } });
}
document.addEventListener('click',e=>{
  const rc=e.target.closest('.rc'); if(!rc||!rc.dataset.rc) return;
  const o=rc.textContent;
  copyText(rc.dataset.rc).then(()=>{ rc.textContent='copied ✓'; rc.classList.add('copied');
    setTimeout(()=>{rc.textContent=o; rc.classList.remove('copied');},900); },()=>{});
});

/* ---------- shared match card (used by Matches tab and Scout page) ---------- */
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
// Bans in draft order: 1st ban, 2nd ban — with the team that banned it.
function bansOrdered(g){
  const ord=[...g.bans].sort((a,b)=>(a.order||9)-(b.order||9));
  return ord.map(b=>`<span class="banstep"><span class="ord">${b.order||'?'}</span> `+
    `<b>${b.team?esc(b.team):'<span class=\'faint\'>?</span>'}</b> banned ${heroChip(b.hero)}</span>`).join('');
}
// One full match card: header (teams/score), then each map with bans + toggleable rosters.
function matchCard(m){
  const c=el(`<div class="card match"></div>`);
  const w1=m.winner==='faction1',w2=m.winner==='faction2';
  c.appendChild(el(`<div class="hd"><div class="teams"><span class="${w1?'win':'lose'}">${esc(m.f1||'?')}</span>`+
    `<span class="score">${esc(m.series)}</span><span class="${w2?'win':'lose'}">${esc(m.f2||'?')}</span></div>`+
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
        (g.demo_code?(codeDead(m.finished_at)&&!CAPTURED.has(m.id+':'+g.game_no)
            ?'<span class="faint" style="font-size:11.5px">code wiped</span>'
            :rcChip(g.demo_code))
          :'<span class="faint" style="font-size:11.5px">no replay</span>')+
        `<span class="faint rtog">▸ rosters</span></span></div>`));
    gEl.appendChild(el(`<div class="bans">${bansOrdered(g)}</div>`));
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
function barList(items){
  if(!items.length) return `<p class="note">No data in this window.</p>`;
  const max=Math.max(1,...items.map(i=>i.value));
  return `<div>`+items.map(i=>{
    const w=Math.max(2,Math.round(100*i.value/max));
    return `<div class="barrow"><div class="lab">${i.label}</div>`+
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
  const a={bans:{},banRoles:{},mapsPicked:{},perMapPick:{},counter:{},mapStats:{},
           firstBans:{},firstBanGames:0,pickFirstBan:{},banHeroWin:{},games:0,gwins:0,results:[],replays:[]};
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
      } else { inc(a.mapsPicked,g.map); g.bans.forEach(b=>{ inc(a.bans,b.hero); if(b.role)inc(a.banRoles,b.role); }); }
    });
  });
  return a;
}

/* ============================================================= VIEWS */
const TABS=[
 {id:'overview',label:'Overview',render:renderOverview},
 {id:'scout',label:'Scout a team',render:renderScout},
 {id:'versus',label:'Team vs team',render:renderVersus},
 {id:'sim',label:'Draft simulator',render:renderSim},
 {id:'meta',label:'League meta',render:renderMeta},
 {id:'matches',label:'Matches',render:renderMatches},
];

let SCOUT_TEAM = null;   // set per division by recomputeDivision()
let VS_A=null, VS_B=null;   // team-vs-team selections (any team vs any team)
let SCOUT_PREP=false;       // scout tab: full detail vs the condensed prep sheet
const PLANNED={};           // counter-scout: team -> Set of planned hero names
let SCOUT_N=null, META_N=40;   // recent-match counts; null = all
let SIM_A=null, SIM_B=null, SIM_FIRST='A', SIM_PATH=[];  // draft simulator state

function gotoScout(team){ SCOUT_TEAM=team; show('scout'); }

function renderOverview(){
  const s=D().summary, wrap=el(`<div></div>`);

  const tiles=[['played_games','Maps played',`${s.matches} matches`],
    ['teams','Teams',`${s.walkovers} walkovers`],
    ['matches_with_attribution','Matches w/ veto data',`of ${s.matches} — ${pctOf(s.matches_with_attribution,s.matches)}%`],
    ['dc_games','Maps w/ a DC',`stats stored as NULL`]];
  const g=el(`<div class="grid cols-auto"></div>`);
  tiles.forEach(([k,l,sub])=>g.appendChild(el(`<div class="card tile"><div class="n">${nf(s[k])}</div><div class="l">${l}</div><div class="sub">${sub}</div></div>`)));
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
    D().teams));
  wrap.appendChild(el(`<p class="note">Veto attribution recovered from FACEIT's durable history feed for ${s.matches_with_attribution}/${s.matches} matches; only walkovers and disrupted vetos lack it.</p>`));
  return wrap;
}

function scoutData(team,lim){
  const mine=MATCHES_RECENT.filter(m=>m.f1===team||m.f2===team);
  const used=recent(mine,lim), a=aggregate(used,team), {from,to}=dateRange(used);
  return {team,used:used.length,total:mine.length,from,to,matches:used,...a};
}

const teamTotalMatches=(team)=> MATCHES_RECENT.filter(m=>m.f1===team||m.f2===team).length;


/* =============================================== TEAM vs TEAM (matchup prep) */
function renderVersus(){
  const names=D().team_names;
  if(names.length<2) return el(`<p class="note">Need at least two teams.</p>`);
  if(!VS_A||!names.includes(VS_A)) VS_A=names[0];
  if(!VS_B||!names.includes(VS_B)||VS_B===VS_A) VS_B=names.find(n=>n!==VS_A);

  const wrap=el(`<div></div>`);
  const bar=el(`<div class="card controls"></div>`);
  const mkSel=(val)=>{ const sel=el(`<select style="min-width:170px"></select>`);
    names.forEach(n=>sel.appendChild(el(`<option ${n===val?'selected':''}>${esc(n)}</option>`)));
    return sel; };
  const selA=mkSel(VS_A), selB=mkSel(VS_B);
  const swap=el(`<button class="btn" type="button" style="padding:4px 10px">&harr;</button>`);
  bar.append(selA, swap, selB);
  const body=el(`<div></div>`);
  wrap.append(bar, body);

  function draw(){
    location.hash=hashFor('versus');
    body.innerHTML='';
    const A=scoutData(VS_A,null), B=scoutData(VS_B,null);

    // Head-to-head history first: the only DIRECT evidence in the matchup.
    const h2h=MATCHES_RECENT.filter(m=>(m.f1===VS_A&&m.f2===VS_B)||(m.f1===VS_B&&m.f2===VS_A));
    let wa=0, wb=0;
    h2h.forEach(m=>{ const w=m.winner==='faction1'?m.f1:(m.winner==='faction2'?m.f2:null);
      if(w===VS_A)wa++; else if(w===VS_B)wb++; });
    body.appendChild(el(sectionH('Head to head',
      h2h.length?`<span class="note">${esc(VS_A)} ${wa} - ${wb} ${esc(VS_B)} · ${h2h.length} match${h2h.length===1?'':'es'}</span>`
                :`<span class="note">never played each other in this window</span>`)));
    h2h.slice(0,4).forEach(m=>body.appendChild(matchCard(m)));

    // The two teams side by side; collapses to one column on narrow screens.
    const cols=el(`<div class="grid cols-2" style="margin-top:14px;align-items:start"></div>`);
    [[A,VS_A],[B,VS_B]].forEach(([t,name])=>{
      const c=el(`<div class="card"></div>`);
      const wins=t.results.filter(r=>r.won).length;
      c.appendChild(el(`<div style="font-size:16px;font-weight:680;margin-bottom:2px">${esc(name)}</div>`+
        `<p class="note" style="margin:0 0 8px">${pill(`${wins}/${t.results.length} matches`,winVar(pctOf(wins,t.results.length)))} ${pill(`${t.gwins}/${t.games} maps`,winVar(pctOf(t.gwins,t.games)))}</p>`));
      c.appendChild(el(`<p class="eyebrow">Top bans</p>`));
      c.appendChild(el(barList(rank(t.bans).slice(0,6).map(([h,n])=>({label:heroChip(h),value:n,color:roleVar(HERO_ROLE[h])})))));
      c.appendChild(el(`<p class="eyebrow" style="margin-top:12px">Most-picked maps</p>`));
      const mp=Object.entries(t.mapStats).filter(([,v])=>v.picks>0)
        .map(([m,v])=>({map:m,picks:v.picks,wr:pctOf(v.wins,v.games)}))
        .sort((a,b)=>b.picks-a.picks).slice(0,5);
      if(!mp.length) c.appendChild(el(`<p class="note">No picked maps in window.</p>`));
      mp.forEach(r=>c.appendChild(el(`<div class="crow"><span>${esc(r.map)} <span class="faint">${esc(MAP_CAT[r.map]||'')}</span></span>`+
        `<span class="rec">${r.picks}x picked · ${pill(r.wr+'%',winVar(r.wr))}</span></div>`)));
      const oc=(DATA.owscout_comps||{})[name], sc=oc&&oc.scout;
      if(sc&&(sc.overall||[]).length){
        const top=sc.overall[0];
        c.appendChild(el(`<p class="eyebrow" style="margin-top:12px">Captured comp (${sc.games} map${sc.games===1?'':'s'})</p>`));
        c.appendChild(el(`<div class="crow"><span>${compRow(top.heroes)}</span>`+
          `<span class="rec">${top.wins}W-${top.losses}L</span></div>`));
      }
      cols.appendChild(c);
    });
    body.appendChild(cols);

    // Seat by seat: where the matchup is actually contested. Needs captured
    // hero pools; a team without captures shows a gap, not a guess.
    const poolOf=(name)=>{ const oc=(DATA.owscout_comps||{})[name];
      return ((oc&&oc.scout&&oc.scout.hero_pool)||[]); };
    const pa=poolOf(VS_A), pb=poolOf(VS_B);
    if(pa.length||pb.length){
      body.appendChild(el(sectionH('Seat by seat',`<span class="note">each team's captured pool per competitive seat</span>`)));
      const seatCard=el(`<div class="card"></div>`);
      SEATS.forEach(seat=>{
        const pick=(pool)=>pool.filter(h=>(HERO_SEAT[h.hero]||'')===seat)
          .sort((x,y)=>y.rounds-x.rounds).slice(0,3);
        const A=pick(pa), B=pick(pb);
        if(!A.length&&!B.length) return;
        const row=el(`<div class="crow" style="align-items:flex-start"><span style="min-width:110px" class="seg">${esc(seat)}</span>`+
          `<span style="flex:1">${A.map(h=>heroChip(h.hero)).join(' ')||'<span class="faint">no captures</span>'}</span>`+
          `<span style="flex:1;text-align:right">${B.map(h=>heroChip(h.hero)).join(' ')||'<span class="faint">no captures</span>'}</span></div>`);
        seatCard.appendChild(row);
      });
      body.appendChild(seatCard);
    }

    // The veto battleground: maps BOTH teams pick, with each side's win rate.
    const contested=Object.keys(A.mapStats).filter(m=>
      (A.mapStats[m]||{}).picks>0 && (B.mapStats[m]||{}).picks>0)
      .map(m=>({map:m,cat:MAP_CAT[m]||'',
        awr:pctOf(A.mapStats[m].wins,A.mapStats[m].games),
        bwr:pctOf(B.mapStats[m].wins,B.mapStats[m].games)}))
      .sort((a,b)=>mapCmp(a.map,b.map));
    body.appendChild(el(sectionH('Contested maps',`<span class="note">maps both teams pick - the veto battleground</span>`)));
    body.appendChild(contested.length?table(
      [{k:'map',label:'Map'},
       {k:'awr',label:esc(VS_A)+' win %',num:true,html:r=>pill(r.awr+'%',winVar(r.awr))},
       {k:'bwr',label:esc(VS_B)+' win %',num:true,html:r=>pill(r.bwr+'%',winVar(r.bwr))}],
      contested, byMode)
      :el(`<p class="note">No overlap in picked maps.</p>`));

    // Heroes BOTH teams ban often: gone either way, plan around their absence.
    const topA=new Set(rank(A.bans).slice(0,8).map(([h])=>h));
    const both=rank(B.bans).slice(0,8).map(([h])=>h).filter(h=>topA.has(h));
    if(both.length){
      body.appendChild(el(sectionH('Banned either way',`<span class="note">in both teams' top bans - plan around their absence</span>`)));
      const rowEl=el(`<div class="card" style="display:flex;flex-wrap:wrap;gap:6px"></div>`);
      both.forEach(h=>rowEl.appendChild(el(`<span class="opt" style="cursor:default">${heroChip(h)}</span>`)));
      body.appendChild(rowEl);
    }
  }
  selA.onchange=()=>{ VS_A=selA.value;
    if(VS_B===VS_A){ VS_B=names.find(n=>n!==VS_A); selB.value=VS_B; } draw(); };
  selB.onchange=()=>{ VS_B=selB.value;
    if(VS_A===VS_B){ VS_A=names.find(n=>n!==VS_B); selA.value=VS_A; } draw(); };
  swap.onclick=()=>{ [VS_A,VS_B]=[VS_B,VS_A]; selA.value=VS_A; selB.value=VS_B; draw(); };
  draw();
  return wrap;
}


/* ================================= PREP SHEET (the night-before one-pager) */
// Everything a team decides before a match, on one screen: what to ban, what
// they'll ban, where the map draft goes, and what comp walks out of spawn.
// Deliberately terse - the full scout page is one click away.
function renderPrepBody(t){
  const w=el(`<div></div>`);
  const wins=t.results.filter(r=>r.won).length;
  const oc=(DATA.owscout_comps||{})[t.team], sc=oc&&oc.scout;
  w.appendChild(el(`<div class="card" style="display:flex;gap:14px;flex-wrap:wrap;align-items:baseline">`+
    `<span style="font-size:18px;font-weight:680">${esc(t.team)} - prep sheet</span>`+
    `<span>${pill(`${wins}/${t.results.length} matches`,winVar(pctOf(wins,t.results.length)))} `+
    `${pill(`${t.gwins}/${t.games} maps`,winVar(pctOf(t.gwins,t.games)))}</span></div>`));

  const grid=el(`<div class="grid cols-2" style="margin-top:10px;align-items:start"></div>`);

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
  weak.appendChild(el(`<p class="eyebrow">Target these maps - their worst</p>`));
  const worst=Object.entries(t.mapStats).filter(([,v])=>v.games>=2)
    .map(([m,v])=>({m,g:v.games,wr:pctOf(v.wins,v.games)}))
    .sort((a,b)=>a.wr-b.wr).slice(0,4);
  if(!worst.length) weak.appendChild(el(`<p class="note">Not enough games per map yet.</p>`));
  worst.forEach(r=>weak.appendChild(el(`<div class="crow"><span>${esc(r.m)} <span class="faint">${esc(MAP_CAT[r.m]||'')}</span></span>`+
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
      const card=el(`<div class="card" style="margin-top:10px"></div>`);
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
  bar.appendChild(el(`<label>Opponent</label>`));
  const sel=el(`<select style="min-width:190px"></select>`);
  D().team_names.forEach(n=>sel.appendChild(el(`<option ${n===SCOUT_TEAM?'selected':''}>${esc(n)}</option>`)));
  bar.appendChild(sel);
  bar.appendChild(el(`<label>Recent matches</label>`));
  const holder=el(`<span style="display:inline-flex"></span>`);
  bar.appendChild(holder);
  const prepBtn=el(`<button class="btn" type="button" style="margin-left:auto;padding:4px 12px"></button>`);
  bar.appendChild(prepBtn);
  const body=el(`<div></div>`);
  wrap.append(bar,body);

  function renderBody(){
    prepBtn.textContent=SCOUT_PREP?'Full detail':'Prep sheet';
    body.innerHTML='';
    const data=scoutData(SCOUT_TEAM, SCOUT_N);
    body.appendChild(SCOUT_PREP?renderPrepBody(data):renderScoutBody(data));
  }
  prepBtn.onclick=()=>{ SCOUT_PREP=!SCOUT_PREP; location.hash=hashFor('scout'); renderBody(); };
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
  const w=el(`<div></div>`);
  const matchW=t.results.filter(r=>r.won).length;
  const form=t.results.slice(0,7).map(r=>`<b class="${r.won?'w':'l'}" title="${esc(r.opp)} ${esc(r.series)}">${r.won?'W':'L'}</b>`).join('');
  const head=el(`<div class="card" style="display:flex;gap:18px;flex-wrap:wrap;align-items:center;justify-content:space-between"></div>`);
  head.appendChild(el(`<div><div style="font-size:18px;font-weight:680">${esc(t.team)}</div>`+
    `<div class="note" style="margin-top:2px">${t.used<t.total?`last ${t.used} of ${t.total} matches`:`all ${t.total} matches`} · ${dshort(t.from)} → ${dshort(t.to)}</div></div>`));
  head.appendChild(el(`<div style="text-align:right"><div>${pill(`${matchW}/${t.results.length} matches`,winVar(pctOf(matchW,t.results.length)))} ${pill(`${t.gwins}/${t.games} maps`,winVar(pctOf(t.gwins,t.games)))}</div>`+
    `<div class="wl" style="margin-top:6px;justify-content:flex-end">${form||'<span class="faint">no maps</span>'}</div></div>`));
  w.appendChild(head);

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
    const cov=el(`<div class="card" style="margin-top:10px"></div>`);
    cov.appendChild(el(`<p class="eyebrow">Scouting coverage · ${done.length} of ${scoutable.length} scoutable games captured`+
      (lost?` <span class="faint" style="text-transform:none;letter-spacing:0">· ${lost} lost to the ${esc(CODE_WIPE)} code wipe</span>`:'')+`</p>`));
    if(todo.length){
      const row=el(`<div style="display:flex;flex-wrap:wrap;gap:6px;align-items:center"></div>`);
      row.appendChild(el(`<span class="note" style="margin:0">to scout:</span>`));
      todo.slice(0,8).forEach(r=>{
        const chip=el(`<span class="opt" style="cursor:default">${rcChip(r.code)}<span class="pp">${esc(r.map)} · ${dshort(r.when)}</span></span>`);
        row.appendChild(chip);
      });
      if(todo.length>8) row.appendChild(el(`<span class="faint">+${todo.length-8} more</span>`));
      cov.appendChild(row);
    } else {
      cov.appendChild(el(`<p class="note" style="margin:0">Fully scouted - every replay-coded game is captured.</p>`));
    }
    w.appendChild(cov);
  }

  // ---- Scouting from captured replays (owscout) -------------------------
  // Three sections: what they play (Common comps + Hero pool), where they play
  // it (Map scouting, collapsible), and how they react (Common swaps).
  const oc=(DATA.owscout_comps||{})[t.team];
  const scout=oc&&oc.scout;
  const nGames=(scout&&scout.games)||0;
  // n=1 is an anecdote, not a pattern - show it, but visibly weaker.
  const thin=n=>n<=1?' thin':'';
  const rec=c=>`${c.maps} map${c.maps===1?'':'s'} · ${c.wins}W-${c.losses}L`;
  const compLine=c=>`<div class="crow${thin(c.maps)}"><span>${compRow(c.heroes)}</span>`+
                    `<span class="rec">${rec(c)}</span></div>`;

  if(scout){
    // 1. Common comps - the 3-5 they actually run most.
    const top=(scout.overall||[]).slice(0,5);
    if(top.length){
      w.appendChild(el(sectionH('Common comps',
        `<span class="note">most-played compositions · ${nGames} map${nGames===1?'':'s'} captured</span>`)));
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
        `<span class="note">rounds played · ${nRounds} round${nRounds===1?'':'s'} captured</span>`)));
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
        `<span class="note">read from the HUD name bars · unmatched battletags stay anonymous</span>`)));
      const pgrid=el(`<div class="grid cols-3"></div>`);
      ppools.forEach(p=>{
        const card=el(`<div class="card"></div>`);
        card.appendChild(el(`<p class="eyebrow">${esc(p.player)} <span class="note" style="text-transform:none;letter-spacing:0">${p.rounds} rounds seen</span></p>`));
        p.heroes.slice(0,5).forEach(h=>card.appendChild(el(
          `<div class="crow"><span>${heroChip(h.hero)}</span>`+
          `<span class="rec">${Math.round((h.share||0)*100)}% · ${h.rounds}</span></div>`)));
        pgrid.appendChild(card);
      });
      w.appendChild(pgrid);
    }

    // 3. Map scouting - collapsible per map; segments are attack/defend on
    // Escort+Hybrid, sub-maps on Control, one generic block otherwise.
    const maps=scout.maps||{};
    const mapNames=sortMaps(Object.keys(maps));
    if(mapNames.length){
      w.appendChild(el(sectionH('Map scouting',`<span class="note">click a map for captured detail</span>`)));
      let lastMode=null;
      mapNames.forEach(mp=>{
        // One mode at a time, with a heading where the mode changes.
        const mode=MAP_CAT[mp]||'Other';
        if(mode!==lastMode){ lastMode=mode; w.appendChild(el(`<p class="modeh">${esc(mode)}</p>`)); }
        const entry=maps[mp]||{}, segs=entry.segments||{};
        let mw=0, ml=0;
        Object.values(segs).forEach(b=>(b.open||[]).forEach(c=>{mw+=c.wins; ml+=c.losses;}));
        const d=el(`<details class="mapblk"><summary><span>${esc(mp)}</span>`+
          `<span class="rec">${mw}W-${ml}L</span></summary>`+
          `<div class="mapbody"><div class="mapcol opens"></div>`+
          `<div class="mapcol swaps"></div></div></details>`);
        const body=d.querySelector('.mapcol.opens');
        Object.keys(segs).forEach(seg=>{
          const both=segs[seg]||{};
          if(seg!=='all') body.appendChild(el(`<p class="seg">${esc(seg)}</p>`));
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
      w.appendChild(el(sectionH('Common swaps',`<span class="note">what makes them change heroes</span>`)));
      const card=el(`<div class="card"></div>`);
      swaps.forEach(s=>card.appendChild(el(swapLine(s))));
      w.appendChild(card);
    }

    // 5. Ban response - how their opener shifts when a hero is banned.
    const banresp=(scout.ban_response||[]).slice(0,6);
    if(banresp.length){
      w.appendChild(el(sectionH('When a hero is banned',`<span class="note">how their opening comp shifts</span>`)));
      const card=el(`<div class="card"></div>`);
      banresp.forEach(b=>{
        card.appendChild(el(`<p class="seg">${esc(b.banned)} banned · ${b.games} game${b.games===1?'':'s'}</p>`));
        (b.opens||[]).slice(0,2).forEach(c=>card.appendChild(el(compLine(c))));
      });
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
        const scored=mus.map(m=>({m,ov:signal.filter(h=>m.vs.includes(h))}));
        let need=Math.min(signal.length,3), sim=[];
        for(; need>=1; need--){
          sim=scored.filter(x=>x.ov.length>=need).sort((a,b)=>b.ov.length-a.ov.length);
          if(sim.length) break;
        }
        const tier=need>=3?'':need===2?' · loose match (2 of your heroes)'
                                      :' · weak match (1 of your heroes)';
        resBox.appendChild(el(`<p class="eyebrow">Games vs comps like yours (${sim.length})${tier?`<span style="text-transform:none;letter-spacing:0;color:var(--mid)">${tier}</span>`:''}</p>`));
        if(sim.length){
          const wins=sim.filter(x=>x.m.won).length;
          resBox.appendChild(el(`<p class="note" style="margin-top:0">They went <b>${wins}W-${sim.length-wins}L</b> in those games.</p>`));
          sim.slice(0,6).forEach(({m,ov})=>{
            resBox.appendChild(el(`<div class="crow"><span>${esc(m.map)}: opened ${compRow(m.open)} <span class="faint">vs ${ov.map(h=>heroIcon(h)).join('')}${ov.length<m.vs.length?'…':''}</span></span>`+
              `<span class="rec">${m.won?'they won':'they lost'}</span></div>`));
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

  // Preferred bans + Map picks/win rates (the two most-used, side by side)
  const two=el(`<div class="grid cols-2" style="margin-top:16px"></div>`);
  const banC=el(`<div class="card"></div>`);
  banC.appendChild(el(`<p class="eyebrow">Preferred bans</p>`));
  banC.appendChild(el(barList(rank(t.bans).slice(0,12).map(([h,n])=>({label:heroChip(h),value:n,color:roleVar(HERO_ROLE[h])})))));
  if(t.firstBanGames){
    banC.appendChild(el(`<p class="eyebrow" style="margin-top:16px">First ban <span class="note">(when they draft first — ${t.firstBanGames} maps)</span></p>`));
    banC.appendChild(el(barList(rank(t.firstBans).slice(0,6).map(([h,n])=>({label:heroChip(h),value:n,color:roleVar(HERO_ROLE[h])})))));
  }
  two.appendChild(banC);
  const mapC=el(`<div class="card"></div>`);
  mapC.appendChild(el(`<p class="eyebrow">Maps — picks &amp; win rate</p>`));
  const mrows=Object.entries(t.mapStats).map(([m,v])=>({map:m,cat:MAP_CAT[m]||'',games:v.games,picks:v.picks,wr:pctOf(v.wins,v.games)})).sort((a,b)=>mapCmp(a.map,b.map));
  mapC.appendChild(mrows.length?table(
    [{k:'map',label:'Map'},
     {k:'picks',label:'Picked',num:true},{k:'games',label:'Played',num:true},
     {k:'wr',label:'Win %',num:true,html:r=>pill(r.wr+'%',winVar(r.wr))}], mrows, byMode)
   :el(`<p class="note">No maps in window.</p>`));
  two.appendChild(mapC);
  w.appendChild(two);

  // Signature setups — maps THEY pick AND ban first on (a fully self-chosen draft).
  // A high win% on a repeated map+ban tells you it's a rehearsed strat to be ready for.
  // Their captured opening comp on that map, when owscout has one: the map + first
  // ban says what they chose, this says what they actually ran inside it.
  const scoutMaps=(scout&&scout.maps)||{};
  const openOn=mp=>{
    const segs=(scoutMaps[mp]||{}).segments||{};
    const best=Object.values(segs).map(b=>(b.open||[])[0]).filter(Boolean)
      .sort((a,b)=>b.maps-a.maps)[0];
    return best?`${compRow(best.heroes)}<span class="faint"> ${rec(best)}</span>`:'';
  };
  const pfb=Object.entries(t.pickFirstBan).map(([m,v])=>({map:m,cat:MAP_CAT[m]||'',
      games:v.games,wr:pctOf(v.wins,v.games),comp:openOn(m),
      ban:rank(v.bans).slice(0,2).map(([h,n])=>`${heroChip(h)}<span class="faint"> ${n}</span>`).join(' ')}))
    .sort((a,b)=>mapCmp(a.map,b.map));
  const pfbG=pfb.reduce((s,r)=>s+r.games,0), pfbW=pfb.reduce((s,r)=>s+Math.round(r.wr*r.games/100),0);
  w.appendChild(el(sectionH('Signature setups',`<span class="note">maps they pick &amp; ban first on · self-chosen drafts</span>`)));
  if(pfb.length){
    w.appendChild(el(`<p class="note" style="margin-top:0">On maps ${esc(t.team)} both picked and opened the ban on, they won <b>${pfbW}/${pfbG}</b> = <b>${pctOf(pfbW,pfbG)}%</b>. A repeated map with a strong win rate is likely a rehearsed strat.</p>`));
    w.appendChild(table(
      [{k:'map',label:'Map'},
       {k:'ban',label:'Their first ban',html:r=>r.ban},
       {k:'comp',label:'What they run there',html:r=>r.comp||`<span class="faint">not captured</span>`},
       {k:'games',label:'Maps',num:true},
       {k:'wr',label:'Win %',num:true,html:r=>pill(r.wr+'%',winVar(r.wr))}], pfb, byMode));
  } else {
    w.appendChild(el(`<p class="note">No maps in this window where they both picked and banned first.</p>`));
  }

  // Matches — full match cards for this team (same view as searching them on the
  // Matches tab): per-map bans in draft order, replay codes inline, toggleable rosters.
  // Kept in its own scrolling box: the match list grows without bound and pushed
  // every analysis section below it off the screen.
  w.appendChild(el(sectionH('Matches',`<span class="note">${t.matches.length} match${t.matches.length===1?'':'es'} · scrolls · click a map for rosters · replay codes inline</span>`)));
  if(t.matches.length){
    const mbox=el(`<div class="scrollbox"></div>`);
    t.matches.forEach(m=>mbox.appendChild(matchCard(m)));
    w.appendChild(mbox);
  } else {
    w.appendChild(el(`<p class="note">No matches in this window.</p>`));
  }

  // Map win rate conditioned on a hero being banned out (by either team).
  // One row per (hero, who banned it): banning a hero yourself and having it taken
  // from you are different situations, and averaging them together hides both.
  // One BLOCK per hero holding both cases, so the portrait is drawn once and the
  // two numbers you are actually comparing sit directly above each other.
  const bhw=Object.entries(t.banHeroWin).map(([h,v])=>({
      hero:h, tot:v.games, wr:pctOf(v.wins,v.games),
      rows:[['them',`${t.team} banned it`],['opp','Opponent banned it']]
        .map(([k,label])=>({label,...v[k],wr:pctOf(v[k].wins,v[k].games)}))
        .filter(r=>r.games)}))
    .filter(b=>b.rows.length);
  const bhwSort=el(`<button class="sortbtn" type="button">Win % high &rarr; low</button>`);
  w.appendChild(el(sectionH('Win rate by banned hero',
    `<span class="note">map win % when this hero is banned out · split by who banned it</span>`)));
  if(bhw.length){
    w.appendChild(el(`<p class="note" style="margin-top:0">How ${esc(t.team)} does on maps where a given hero is banned (removed for both teams), split by whether they banned it or the opponent did. Low map counts are noisy — check <b>Maps</b> before trusting a row.</p>`));
    const bar=el(`<div class="ctlrow"></div>`); bar.appendChild(bhwSort); w.appendChild(bar);
    const box=el(`<div class="scroll"><table class="blocks"><thead><tr>`+
      `<th>Banned hero</th><th>Banned by</th><th class="num">Maps</th>`+
      `<th class="num">Won</th><th class="num">Win %</th></tr></thead><tbody></tbody></table></div>`);
    let desc=true;
    const draw=()=>{
      const list=[...bhw].sort((a,b)=>(desc?b.wr-a.wr:a.wr-b.wr)||b.tot-a.tot
                                       ||a.hero.localeCompare(b.hero));
      box.querySelector('tbody').innerHTML=list.map(b=>b.rows.map((r,i)=>
        `<tr class="${i===0?'blk':''}">`+
        `<td>${i===0?heroChip(b.hero):''}</td>`+
        `<td><span class="faint">${esc(r.label)}</span></td>`+
        `<td class="num">${r.games}</td><td class="num">${r.wins}</td>`+
        `<td class="num">${pill(r.wr+'%',winVar(r.wr))}</td></tr>`).join('')).join('');
    };
    bhwSort.onclick=()=>{ desc=!desc;
      bhwSort.innerHTML=desc?'Win % high &rarr; low':'Win % low &rarr; high'; draw(); };
    draw();
    w.appendChild(box);
  } else {
    w.appendChild(el(`<p class="note">No bans in this window.</p>`));
  }

  // Counter-bans — genuine responses only: the opponent banned first, this team
  // banned second in reply. (Cases where this team banned first are excluded.)
  w.appendChild(el(sectionH('Counter-bans',`<span class="note">opponent bans first → ${esc(t.team)}'s reply</span>`)));
  const cRows=rank(Object.fromEntries(Object.entries(t.counter).map(([k,v])=>[k,Object.values(v).reduce((x,y)=>x+y,0)])))
    .map(([opp,tot])=>({opp,tot,resp:rank(t.counter[opp]).map(([h,n])=>`${heroChip(h)}<span class="faint"> ${n}</span>`).join(' ')}));
  w.appendChild(cRows.length?table(
    [{k:'opp',label:'Opponent banned first',html:r=>heroChip(r.opp)},{k:'tot',label:'×',num:true},
     {k:'resp',label:`${esc(t.team)} replied with`,html:r=>r.resp}], cRows)
   :el(`<p class="note">No counter-bans in this window (needs the opponent to have banned first with both bans attributed).</p>`));

  // Bans on maps they PICKED only. The all-maps version was dropped: on a map the
  // opponent picked, the ban is a reaction, so it diluted the signal this shows.
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
  w.appendChild(el(sectionH('Bans on maps they pick',`<span class="note">what ${esc(t.team)} bans on maps they chose</span>`)));
  w.appendChild(banMapTable(t.perMapPick));
  return w;
}

/* ================================================= DRAFT SIMULATOR (manual scenario planner) */
// Per-team history over the active division: map-pick counts, per-map ban counts, overall ban counts.
function simModel(team){
  const pick={}, banByMap={}, bansAll={};
  D().matches.forEach(m=>{
    const side=m.f1===team?'faction1':(m.f2===team?'faction2':null); if(!side)return;
    m.games.forEach(g=>{ if(!g.map)return;
      if(g.map_picked_by===team) inc(pick,g.map);
      g.bans.filter(b=>b.team===team&&b.hero).forEach(b=>{ (banByMap[g.map]=banByMap[g.map]||{}); inc(banByMap[g.map],b.hero); inc(bansAll,b.hero); });
    });
  });
  return {team,pick,banByMap,bansAll};
}
function divMaps(){ const s={}; D().matches.forEach(m=>m.games.forEach(g=>{ if(g.map) s[g.map]=g.map_category||MAP_CAT[g.map]||''; })); return s; }
// Ranked ban suggestions for a team on a map: on-map history first, then overall; skip illegal heroes.
function banSuggest(model, map, illegal){
  const onMap=model.banByMap[map]||{}, all=model.bansAll||{}, keys=new Set([...Object.keys(onMap),...Object.keys(all)]);
  return [...keys].filter(h=>!illegal.has(h))
    .map(h=>({hero:h,onMap:onMap[h]||0,all:all[h]||0}))
    .sort((a,b)=>(b.onMap-a.onMap)||(b.all-a.all)).slice(0,7);
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
  const nameOf=ab=>ab==='A'?SIM_A:SIM_B;

  const ctl=el(`<div class="card controls" style="flex-wrap:wrap;gap:12px 16px"></div>`);
  const mkSel=(val,on)=>{ const s=el(`<select style="min-width:170px"></select>`); tn.forEach(n=>s.appendChild(el(`<option ${n===val?'selected':''}>${esc(n)}</option>`))); s.onchange=()=>on(s.value); return s; };
  ctl.appendChild(el(`<label>Team A</label>`));
  ctl.appendChild(mkSel(SIM_A,v=>{SIM_A=v;SIM_PATH=[];draw();}));
  ctl.appendChild(el(`<span class="faint" style="font-weight:800">vs</span>`));
  ctl.appendChild(el(`<label>Team B</label>`));
  ctl.appendChild(mkSel(SIM_B,v=>{SIM_B=v;SIM_PATH=[];draw();}));
  ctl.appendChild(el(`<label title="This team picks the Game 1 map and takes the first ban.">First pick &amp; ban</label>`));
  const fb=el(`<div class="wsel"></div>`);
  const fbBtn=ab=>{ const b=el(`<span class="wbtn ${SIM_FIRST===ab?(ab==='A'?'selA':'selB'):''}">${esc(nameOf(ab))}</span>`); b.onclick=()=>{SIM_FIRST=ab;SIM_PATH=[];draw();}; return b; };
  fb.append(fbBtn('A'),fbBtn('B')); ctl.appendChild(fb);
  const reset=el(`<span class="wbtn" style="margin-left:auto">↺ Reset draft</span>`); reset.onclick=()=>{SIM_PATH=[];draw();};
  ctl.appendChild(reset);
  wrap.appendChild(ctl);
  wrap.appendChild(el(`<p class="note" style="margin:2px 2px 0">Plan a Bo5 draft by hand. Each map, the team on the clock <b>picks the map</b> and <b>bans first</b>, then the other team bans. Click a suggested hero (from that team's history) or choose <b>any hero</b> from the dropdown — e.g. ban a pocket pick so the enemy can't take it. Mark who wins each map to continue (the loser picks next). A team can't repeat its own bans across the series; used heroes drop out of its list automatically.</p>`));
  const body=el(`<div></div>`); wrap.appendChild(body);

  function draw(){
    body.innerHTML='';
    if(SIM_A===SIM_B){ body.appendChild(el(`<p class="note" style="margin-top:14px">Pick two different teams.</p>`)); return; }
    const A=simModel(SIM_A), B=simModel(SIM_B), modelOf=ab=>ab==='A'?A:B;
    const ledgerCard=el(`<div class="card" style="margin-top:10px"></div>`); body.appendChild(ledgerCard);
    const tree=el(`<div></div>`); body.appendChild(tree);

    const banned={A:[],B:[]};                         // {hero,game,map} per team, built as we walk
    const setOf=ab=>new Set(banned[ab].map(x=>x.hero));
    let sa=0,sb=0; const used=new Set();
    for(let i=0;i<5 && sa<3 && sb<3;i++){
      const picker = i===0? SIM_FIRST : (SIM_PATH[i-1].winner==='A'?'B':'A');
      const other = picker==='A'?'B':'A';
      const node = SIM_PATH[i]||(SIM_PATH[i]={map:null,b1:null,b2:null,winner:null});
      const blk=el(`<div class="simblock"></div>`);
      blk.appendChild(el(`<div class="bh"><span class="gno">M${i+1}</span> <b>${esc(nameOf(picker))}</b> picks &amp; bans first <span class="simscore faint" style="margin-left:auto">series ${sa}–${sb}</span></div>`));
      // map pick — grouped by mode. Game 1 is always Control; later maps are never Control.
      const pk=modelOf(picker), g1=(i===0);
      const MODES=['Control','Escort','Flashpoint','Hybrid','Push'];
      const allowed=g1?['Control']:MODES.filter(x=>x!=='Control');
      const mrow=el(`<div class="simrow" style="align-items:flex-start"></div>`);
      mrow.appendChild(el(`<span class="rl">Map pick${g1?'<br><span style="text-transform:none;letter-spacing:0;font-weight:400">G1 = Control</span>':''}</span>`));
      const groups=el(`<div style="display:flex;flex-direction:column;gap:7px;flex:1;min-width:0"></div>`);
      allowed.forEach(cat=>{
        const maps=Object.keys(pool).filter(mp=>!used.has(mp)&&pool[mp]===cat)
          .map(mp=>({map:mp,n:pk.pick[mp]||0})).sort((a,b)=>b.n-a.n||a.map.localeCompare(b.map));
        if(!maps.length) return;
        const grow=el(`<div style="display:flex;gap:6px;flex-wrap:wrap;align-items:center"></div>`);
        grow.appendChild(el(`<span class="modelbl">${esc(cat)}</span>`));
        maps.forEach(d=>{ const o=el(`<span class="opt ${node.map===d.map?'sel':''} ${d.n<1?'dim':''}">${esc(d.map)}${d.n?` <span class="pp">picked ${d.n}×</span>`:''}</span>`);
          o.onclick=()=>setMap(i,d.map); grow.appendChild(o); });
        groups.appendChild(grow);
      });
      mrow.appendChild(groups); blk.appendChild(mrow);
      if(node.map){
        used.add(node.map);
        // two ban rows: picker bans first, then the other team.
        [['b1',picker],['b2',other]].forEach(([key,tab])=>{
          const illegal=setOf(tab);
          if(node[key] && illegal.has(node[key])) node[key]=null;      // heal an illegal repeat after an edit
          const row=el(`<div class="simrow"><span class="rl">${esc(nameOf(tab))} ban</span></div>`);
          const sugg=banSuggest(modelOf(tab), node.map, illegal);
          sugg.forEach(s2=>{ const o=el(`<span class="opt ${node[key]===s2.hero?'sel':''} ${(s2.onMap+s2.all)<2?'dim':''}">${heroChip(s2.hero)}<span class="pp">${s2.onMap?s2.onMap+'× here':s2.all+'× total'}</span></span>`);
            o.onclick=()=>{node[key]=s2.hero;draw();}; row.appendChild(o); });
          row.appendChild(heroSelect(node[key], illegal, h=>{node[key]=h;draw();}));
          if(node[key] && !sugg.some(x=>x.hero===node[key]))
            row.appendChild(el(`<span class="opt sel">${heroChip(node[key])}<span class="pp">manual</span></span>`));
          blk.appendChild(row);
        });
        if(node.b1) banned[picker].push({hero:node.b1,game:i+1,map:node.map});
        if(node.b2) banned[other].push({hero:node.b2,game:i+1,map:node.map});
        // map winner (drives who picks next)
        const wr=el(`<div class="simrow"><span class="rl">Map winner</span></div>`);
        const wa=el(`<span class="wbtn ${node.winner==='A'?'selA':''}">${esc(SIM_A)}</span>`); wa.onclick=()=>setWinner(i,'A');
        const wb=el(`<span class="wbtn ${node.winner==='B'?'selB':''}">${esc(SIM_B)}</span>`); wb.onclick=()=>setWinner(i,'B');
        wr.append(wa,wb); blk.appendChild(wr);
        if(node.winner){ if(node.winner==='A')sa++; else sb++;
          blk.appendChild(el(`<div class="simnext">↳ ${esc(nameOf(node.winner==='A'?'B':'A'))} lost — they pick next${(sa>=3||sb>=3)?' · series decided':''}.</div>`)); }
      }
      tree.appendChild(blk);
      if(!node.map || !node.winner) break;
    }
    // series ban ledger (populated after the walk)
    ledgerCard.appendChild(el(`<p class="eyebrow">Series ban ledger <span class="note" style="text-transform:none;letter-spacing:0">· a team can't repeat its own bans (opponents may)</span></p>`));
    const grid=el(`<div class="grid cols-2" style="margin-top:6px"></div>`);
    ['A','B'].forEach(ab=>{ const col=el(`<div></div>`);
      col.appendChild(el(`<div style="font-weight:680;font-size:13px;margin-bottom:5px">${esc(nameOf(ab))} <span class="faint" style="font-weight:400">· ${banned[ab].length} banned</span></div>`));
      if(banned[ab].length){ const chips=el(`<div style="display:flex;flex-wrap:wrap;gap:5px"></div>`);
        banned[ab].forEach(x=>chips.appendChild(el(`<span class="opt" style="cursor:default">${heroChip(x.hero)}<span class="pp">M${x.game}</span></span>`)));
        col.appendChild(chips);
      } else col.appendChild(el(`<span class="faint" style="font-size:12.5px">no bans yet</span>`));
      grid.appendChild(col); });
    ledgerCard.appendChild(grid);
    if(sa>=3||sb>=3) body.appendChild(el(`<div class="card" style="margin-top:10px"><b>Series result (your scenario):</b> ${esc(sa>sb?SIM_A:SIM_B)} win ${Math.max(sa,sb)}–${Math.min(sa,sb)}.</div>`));
  }
  function setMap(i,map){ SIM_PATH.length=i; SIM_PATH[i]={map,b1:null,b2:null,winner:null}; draw(); }
  function setWinner(i,ab){ SIM_PATH.length=i+1; SIM_PATH[i].winner=ab; draw(); }
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
    card.appendChild(el(`<p class="eyebrow">${esc(c)} <span class="note" style="text-transform:none;letter-spacing:0">${tot} pick${tot===1?'':'s'}</span></p>`));
    card.appendChild(el(`<div>`+maps.map(m=>
      `<div class="poolrow"><span class="pm">${esc(m.map)}</span>`+
      `<span class="pr"><span class="pk">${m.picks}</span><span class="pp">${m.plays} played</span></span></div>`).join('')+`</div>`));
    pg.appendChild(card);
  });
  wrap.appendChild(pg);

  // attacking-first (all season)
  const af=D().attacking_first;
  wrap.appendChild(el(sectionH('Attacking-first advantage',`<span class="note">Escort &amp; Hybrid only · all season</span>`)));
  wrap.appendChild(el(`<p class="note" style="margin-top:0">Mirrored modes (Control/Flashpoint/Push) excluded. Overall the first-attacking team won <b>${af.atk_first_wins}/${af.total_games}</b> = <b>${pctOf(af.atk_first_wins,af.total_games)}%</b>.</p>`));
  wrap.appendChild(table(
    [{k:'name',label:'Map'},{k:'games',label:'Maps',num:true},
     {k:'wr',label:'Atk-first win %',num:true,html:r=>pill(r.wr+'%',winVar(r.wr))}],
    af.by_map.map(m=>({...m,map:m.name,wr:pctOf(m.atk_first_wins,m.games)}))
      .sort((a,b)=>mapCmp(a.map,b.map)), byMode));
  return wrap;
}

function renderMatches(){
  const wrap=el(`<div></div>`);
  const bar=el(`<div style="display:flex;gap:10px;margin-bottom:12px;align-items:center;flex-wrap:wrap"></div>`);
  const search=el(`<input placeholder="search team, hero, or map…" style="flex:1;min-width:200px;font-size:15px;padding:11px 13px">`);
  const sort=el(`<select title="Sort by date" style="font-size:15px;padding:11px 13px"><option value="new">Newest first</option><option value="old">Oldest first</option></select>`);
  bar.append(search,sort);
  const list=el(`<div></div>`); wrap.append(bar,list);
  const hay=(m)=>[m.f1,m.f2,...m.games.flatMap(g=>[g.map,...g.bans.map(b=>b.hero),...(g.rosters||[]).flatMap(r=>r.players.map(p=>p.nick))])].filter(Boolean).join(' ').toLowerCase();
  function draw(){
    const q=(search.value||'').trim().toLowerCase(); list.innerHTML='';
    // MATCHES_RECENT is newest-first; reverse for oldest-first.
    let shown=MATCHES_RECENT.filter(m=>!q||hay(m).includes(q));
    if(sort.value==='old') shown=[...shown].reverse();
    if(!shown.length){ list.appendChild(el(`<p class="note">No matches.</p>`)); return; }
    shown.forEach(m=>list.appendChild(matchCard(m)));
  }
  search.oninput=draw; sort.onchange=draw; draw(); return wrap;
}

/* ---------- shell ---------- */
// The scout tab's hash carries the team, so a prep link pasted in Discord lands
// a teammate directly on the right page: site/#scout=Redline
function hashFor(id){
  if(id==='scout'&&SCOUT_TEAM) return (SCOUT_PREP?'prep=':'scout=')+encodeURIComponent(SCOUT_TEAM);
  if(id==='versus'&&VS_A&&VS_B) return 'vs='+encodeURIComponent(VS_A)+'~'+encodeURIComponent(VS_B);
  return id;
}
function show(id){
  document.querySelectorAll('nav button').forEach(b=>b.classList.toggle('active',b.dataset.id===id));
  const c=document.getElementById('content'); c.innerHTML=''; c.appendChild(TABS.find(t=>t.id===id).render());
  try{window.scrollTo(0,0)}catch(e){}
  const h=hashFor(id); if(location.hash!=='#'+h) location.hash=h;
}
function updateHeader(){
  const s=D().summary;
  document.getElementById('title').textContent=s.championship;
  document.getElementById('subtitle').textContent=`${s.matches} matches · ${s.played_games} maps · ${dshort(s.date_from)} → ${dshort(s.date_to)}`+(DATA.built_at?` · built ${dshort(DATA.built_at)}`:'');
}
function setDivision(id){
  CURRENT_VIEW=id; recomputeDivision(); updateHeader();
  const cur=document.querySelector('nav button.active');
  show(cur?cur.dataset.id:'overview');
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
  const start=decodeURIComponent((location.hash||'#overview').slice(1));
  if(start.startsWith('vs=')){
    const parts=start.slice(3).split('~');
    const a=parts[0], b=parts[1];
    for(const v of VIEWS){
      if(v.divisions.length===1){
        const tn=DIVS[v.divisions[0]].team_names||[];
        if(tn.includes(a)&&tn.includes(b)){
          CURRENT_VIEW=v.id; recomputeDivision(); updateHeader();
          document.getElementById('division').value=v.id; break;
        }
      }
    }
    const tn=D().team_names||[];
    if(tn.includes(a)&&tn.includes(b)){ VS_A=a; VS_B=b; show('versus'); return; }
  }
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
  show(TABS.some(t=>t.id===start)?start:'overview');
}
init();
</script>
</body>
</html>
"""

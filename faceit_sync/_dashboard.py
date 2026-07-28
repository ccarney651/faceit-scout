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
.topbar-in{max-width:min(1500px,96vw);margin:0 auto;padding:12px 18px 0}
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
nav .navcap{margin-left:auto;align-self:center;background:var(--accent-weak);color:var(--accent);text-decoration:none;padding:7px 13px;border-radius:8px;font-size:13px;font-weight:700;border:1px solid var(--accent);white-space:nowrap}
nav .navcap:hover{background:var(--accent);color:#fff}
nav button:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
main{max-width:min(1500px,96vw);margin:0 auto;padding:20px 18px 72px}

/* ---- primitives ---- */
.eyebrow{font-size:10.5px;font-weight:700;text-transform:uppercase;letter-spacing:.07em;color:var(--faint);margin:0 0 6px}
.opener{font-size:9.5px;font-weight:700;text-transform:uppercase;letter-spacing:.03em;color:var(--accent);border:1px solid color-mix(in srgb,var(--accent) 45%,var(--line));border-radius:4px;padding:0 4px;margin-left:3px;vertical-align:middle}
.bvs{display:block;font-size:10.5px;font-weight:400;line-height:1.2;color:var(--faint)}
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
.comp{display:inline-flex;align-items:center;gap:4px;flex-wrap:nowrap}
/* Spacer between role groups inside a comp, so tank | dps dps | sup sup reads as a shape. */
.comp .rgap{flex:0 0 9px}
.swapsep{margin:0 3px}
/* Bans accompanying a comp: smaller, slightly desaturated (they're OUT of play). */
.cbans{display:inline-flex;align-items:center;gap:3px;opacity:.9;margin:0 auto}
.cbans .bl{font-size:10px;text-transform:uppercase;letter-spacing:.05em;color:var(--faint);margin-right:2px}
.cbans .hicon{width:19px;height:19px;filter:grayscale(.4)}
.comp .hicon+.hicon{margin-left:0}
/* A row of icons + a right-aligned record; the workhorse of the scouting page. */
.crow{display:flex;align-items:center;justify-content:space-between;gap:12px;padding:7px 2px}
.crow+.crow{border-top:1px solid color-mix(in srgb,var(--line) 55%,transparent)}
.crow .rec{flex:none;white-space:nowrap;font-variant-numeric:tabular-nums;color:var(--muted);font-size:12.5px}
.crow.thin{opacity:.55}                      /* n=1: present, but visibly weak evidence */
.csrow{display:flex;align-items:center;gap:8px;flex-wrap:wrap;min-width:0}
.wlsq{display:inline-flex;align-items:center;justify-content:center;width:19px;height:19px;border-radius:5px;font-weight:800;font-size:11px;flex:none}
.wlsq.w{background:color-mix(in srgb,var(--good) 20%,transparent);color:var(--good)}
.wlsq.l{background:color-mix(in srgb,var(--bad) 20%,transparent);color:var(--bad)}
details.mapblk{border:1px solid var(--line);border-radius:10px;background:var(--surface);margin-bottom:8px}
details.mapblk>summary{cursor:pointer;list-style:none;padding:10px 12px;display:flex;
  align-items:center;justify-content:space-between;gap:10px;font-weight:650}
details.mapblk>summary::-webkit-details-marker{display:none}
details.mapblk>summary::after{content:'▾';color:var(--muted);transition:transform .15s}
details.mapblk[open]>summary::after{transform:rotate(180deg)}
details.mapblk>summary:hover{background:var(--surface2);border-radius:10px}
/* Per-map comp history: a light inline expander under the "last 3" headline. */
details.hist{margin:1px 0 4px}
details.hist>summary{cursor:pointer;list-style:none;color:var(--muted);font-size:11.5px;
  font-weight:650;padding:3px 0;user-select:none}
details.hist>summary::-webkit-details-marker{display:none}
details.hist>summary::before{content:'\25B8 ';color:var(--faint)}
details.hist[open]>summary::before{content:'\25BE '}
b.wlw{color:var(--good)} b.wll{color:var(--bad)}
/* Two columns inside a map: openers on the left, the swaps seen there on the
   right (the right half was dead space before). Collapses on narrow screens. */
.mapbody{padding:2px 12px 12px;display:grid;grid-template-columns:1fr 1fr;gap:0 22px}
.mapcol.swaps{border-left:1px solid var(--line);padding-left:20px}
@media(max-width:820px){.mapbody{grid-template-columns:1fr}
  .mapcol.swaps{border-left:none;padding-left:0;border-top:1px solid var(--line);margin-top:10px}}
.seg{font-size:11px;font-weight:700;letter-spacing:.06em;text-transform:uppercase;
  color:var(--muted);margin:10px 0 2px}
.segrec{font-weight:400;text-transform:none;letter-spacing:0;color:var(--faint);font-size:11px;margin-left:7px}
.sighint{margin:9px 0 2px;font-size:13px;display:flex;align-items:center;gap:6px;flex-wrap:wrap}
.sighint .sigk{font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:.05em;color:var(--accent);border:1px solid color-mix(in srgb,var(--accent) 40%,var(--line));border-radius:4px;padding:1px 5px}
.sighint .sigk-ban{color:var(--bad);border-color:color-mix(in srgb,var(--bad) 40%,var(--line))}
.mbchip{display:inline-flex;align-items:center;gap:3px}
.pickpill{font-size:9.5px;font-weight:700;text-transform:uppercase;letter-spacing:.04em;color:var(--accent);border:1px solid color-mix(in srgb,var(--accent) 40%,var(--line));border-radius:4px;padding:0 4px;margin-right:2px}
.side{display:inline-flex;align-items:center;gap:3px;font-size:10.5px;font-weight:700;text-transform:uppercase;letter-spacing:.05em;padding:1px 7px;border-radius:4px}
.side.atk{color:var(--damage);background:color-mix(in srgb,var(--damage) 15%,transparent)}
.side.def{color:var(--tank);background:color-mix(in srgb,var(--tank) 15%,transparent)}
/* Mode heading over a run of map blocks - the same break the tables get. */
.modeh{font-size:10.5px;font-weight:700;letter-spacing:.08em;text-transform:uppercase;
  color:var(--muted);margin:16px 0 6px;padding-bottom:4px;border-bottom:1px solid var(--line)}
.modeh:first-of-type{margin-top:8px}
/* Decision clusters: loud dividers so the page reads as four questions. */
.cluster-h{margin-top:28px;padding-top:12px;border-top:2px solid var(--line);scroll-margin-top:46px;
  font-size:12px;font-weight:800;letter-spacing:.13em;text-transform:uppercase;
  color:var(--accent)}
.minibar{position:sticky;top:0;z-index:30;display:flex;gap:16px;margin-top:12px;
  padding:8px 2px;background:var(--bg);border-bottom:1px solid var(--line)}
.minibar a{color:var(--muted);text-decoration:none;font-size:12.5px;font-weight:650}
.minibar a:hover{color:var(--accent)}
/* Scout tab body: deep analysis (main) beside a sticky Matches rail. */
.scoutgrid{display:grid;grid-template-columns:minmax(0,2.4fr) minmax(300px,1fr);
  gap:0 20px;align-items:start;margin-top:12px}
.scout-side{position:sticky;top:88px;align-self:start}
.scout-side .scrollbox.rail{max-height:calc(100vh - 108px)}
/* Match cards are full-width by nature; in the narrow rail force single-column
   rosters and a slightly tighter type so nothing overflows. */
.scout-side .rosters{grid-template-columns:1fr}
.scout-side .match{font-size:12.5px}
@media(max-width:900px){
  .scoutgrid{grid-template-columns:1fr}
  .scout-side{position:static}
  .scout-side .scrollbox.rail{max-height:min(60vh,560px)}
}
/* At-a-glance band: four self-wrapping summary panels. */
.glance{margin-top:10px}
.glance-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:16px 34px}
.glance-col>.eyebrow{margin-top:0}
.glance-col .crow{padding:8px 0}
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
/* Per-game opening comps on a match card: an aligned grid so both teams' comps
   line up per segment. Columns = segment label + one per team; width is bounded
   by the two comp columns (segments add rows, not columns), so it fits the rail. */
/* Both teams stacked (team over team) per segment, so each comp gets the full
   rail width instead of two 5-hero rows colliding. Comps may wrap, never scroll. */
.gamecomps{margin-top:9px;display:flex;flex-direction:column;gap:11px}
.gcseg{display:flex;flex-direction:column;gap:7px}
.gcseg .gcseglab{font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:.04em;
  color:var(--faint);white-space:nowrap}
/* Team name ABOVE its comp, so all 5 heroes get the full rail width and stay on
   one row instead of the 5th wrapping. */
.gcteam{display:flex;flex-direction:column;gap:3px;min-width:0}
.gcname{font-size:11px;font-weight:650;color:var(--muted);max-width:100%;
  white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.gamecomps .comp{flex-wrap:nowrap}
.banstep{display:inline-flex;align-items:center;gap:5px;margin-right:16px}
.ord{width:17px;height:17px;border-radius:50%;background:var(--accent-weak);color:var(--accent);
  font-size:10.5px;font-weight:700;display:inline-flex;align-items:center;justify-content:center;flex:none}
.rosters{display:grid;grid-template-columns:1fr 1fr;gap:14px;margin-top:10px}
@media (max-width:640px){.rosters{grid-template-columns:1fr}}
/* ---- mobile pass: prep links get opened from Discord on phones ---- */
@media (max-width:640px){
  main{padding:12px 10px 48px;overflow-x:clip}  /* reclaim gutters; clip (not hidden) keeps sticky working */
  .topbar-in{padding:10px 10px 0}
  nav{overflow-x:auto;-webkit-overflow-scrolling:touch;scrollbar-width:none}
  nav::-webkit-scrollbar{display:none}
  nav button{white-space:nowrap;padding:9px 10px;font-size:13px}
  .card{padding:10px}
  /* Let flex/grid children shrink below their content width so nothing pushes the
     page wider than the phone viewport (min-width:auto is the usual culprit). */
  .controls{flex-wrap:wrap;row-gap:8px;min-width:0}
  .controls>*{min-width:0;max-width:100%}
  .controls select{min-width:0!important}
  .recency{flex-wrap:wrap;gap:6px 10px}
  input[type=range]{width:100%;max-width:220px;min-width:0}
  .scoutgrid,.scoutgrid>*,.glance-col{min-width:0}
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
.roster .subhd{margin:8px 0 2px;font-size:10px;text-transform:uppercase;letter-spacing:.05em;color:var(--faint)}
/* ---- playoffs bracket ---- */
.bracket{overflow-x:auto;padding-bottom:6px}
.br-flow{display:flex;gap:16px;align-items:stretch;min-width:min-content}
.br-col{display:flex;flex-direction:column;min-width:160px}
.br-col h4{margin:0 0 6px;font-size:10.5px;text-transform:uppercase;letter-spacing:.04em;color:var(--muted);white-space:nowrap}
.br-col-body{display:flex;flex-direction:column;justify-content:space-around;gap:10px;flex:1}
.br-match{border:1px solid var(--line);border-radius:7px;overflow:hidden;background:var(--surface2)}
.br-team{display:flex;align-items:center;gap:7px;padding:5px 8px;font-size:12.5px;border-top:1px solid var(--line);white-space:nowrap}
.br-team:first-child{border-top:0}
.br-seed{color:var(--faint);font-variant-numeric:tabular-nums;min-width:15px;font-size:11px;text-align:right}
.br-nm{overflow:hidden;text-overflow:ellipsis}
.br-wp{margin-left:auto;color:var(--faint);font-size:11px;font-variant-numeric:tabular-nums}
.br-team.tbd,.br-team.bye{color:var(--faint)}
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
// __DATA_INLINE__
// The whole app runs inside bootApp(DATA); DATA arrives either inlined above
// (single-file/offline builds) or fetched from data.json (the shell build). This
// split is what lets next-season gating be a config change — point the fetch at
// the authenticated Worker — rather than a rewrite.
function bootApp(DATA){
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
  const mergePanel=(get)=>{ const bm={};
    ds.forEach(d=>((get(d)||{}).by_map||[]).forEach(m=>{
      const e=bm[m.name]||(bm[m.name]={name:m.name,category:m.category,games:0,atk_first_wins:0});
      e.games+=m.games; e.atk_first_wins+=m.atk_first_wins; }));
    return {by_map:Object.values(bm).sort((a,b)=>b.games-a.games),
      total_games:ds.reduce((a,d)=>a+((get(d)||{}).total_games||0),0),
      atk_first_wins:ds.reduce((a,d)=>a+((get(d)||{}).atk_first_wins||0),0)}; };
  return {summary:sum, teams, team_names, matches,
    attacking_first:mergePanel(d=>d.attacking_first),
    attacking_first_extra:mergePanel(d=>d.attacking_first_extra)};
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
// Every capture-based stat can only see games since the last replay-code wipe
// (codes reset each patch), so capture sections append this to their subtitle.
const capSince=()=> CODE_WIPE
  ? ` <span class="faint" title="Replay codes reset each patch, so captured data only covers games since the last code wipe">· captures since ${dshort(CODE_WIPE)}</span>`
  : '';
// Map lists everywhere read as a mode block at a time (all Control together, etc),
// and within a mode the maps the league actually plays come first.
const MODE_ORDER=['Control','Escort','Hybrid','Flashpoint','Push','Clash'];
const MAP_POP={};
Object.values(DIVS).forEach(d=>d.matches.forEach(m=>m.games.forEach(g=>{
  if(g.map) MAP_POP[g.map]=(MAP_POP[g.map]||0)+1; })));
// match_id -> match, so a captured comp (which carries only match_id/game_no) can
// be dated by the real match date — capture order is not match order.
const MATCH_BY_ID={};
Object.values(DIVS).forEach(d=>d.matches.forEach(m=>{ MATCH_BY_ID[m.id]=m; }));
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
function recomputeDivision(){
  MATCHES_RECENT=[...D().matches].sort((a,b)=>{const x=a.finished_at||'',y=b.finished_at||'';return x===y?0:(x<y?1:-1);});
  SCOUT_TEAM=D().team_names[0]||null; SCOUT_N=null;
  const tn=D().team_names;
  SIM_A=tn[0]||null; SIM_B=tn[1]||tn[0]||null; SIM_FIRST='A'; SIM_PATH=[];
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
  const all={}, first={};
  D().matches.forEach(m=>m.games.forEach(g=>{ if(!g.map) return;
    (g.bans||[]).forEach(b=>{ if(!b.hero) return; inc(all,b.hero);
      if(b.order===1) inc(first,b.hero); }); }));
  const shares=(o)=>{ const t=Object.values(o).reduce((a,b)=>a+b,0)||1; const s={};
    Object.entries(o).forEach(([h,n])=>s[h]=n/t); return s; };
  DIV_BAN_BASE={all:shares(all), first:shares(first)};
  return DIV_BAN_BASE;
}
// A team's ban counts -> lift rows vs a baseline share map. Drops n<minN (a lone
// ban makes any lift meaningless), sorts by lift then count.
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

let SWAP_NOISE=new Set();   // per-team: heroes in ~every enemy lineup (set by renderScoutBody)
function swapLine(s){
  // One arrow only: the enemy lineup is the TRIGGER (context), the single arrow
  // is the actual out->in swap. A second arrow after "vs" read as a swap too.
  const vs=(s.vs||[]).filter(h=>!SWAP_NOISE.has(h));
  const trig=vs.length
    ? `<span class="faint">vs</span>${compRow(vs.slice(0,5))}<span class="faint swapsep">&middot;</span>`
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
    // Captured opening comps per segment: sub-map (Control), attack/defend
    // (Escort/Hybrid), or the whole map (Push/Flashpoint). Only when captured.
    const pg=(DATA.owscout_pergame||{})[m.id+':'+g.game_no];
    if(pg && Object.keys(pg).length){
      // Both teams' opening comps per segment. In the narrow rail they STACK
      // (team over team) so each comp gets the full width instead of two 5-hero
      // rows colliding side by side and overflowing.
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

/* ============================================================ PLAYOFFS */
// Qualifier count per tier (FACEIT League S8 EMEA; update when S9 formats post).
// Every division is double elimination, Ft3, Grand Final Ft4. 24 (Advanced) seeds
// into a 32-slot bracket, so the top 8 draw byes automatically — no special case.
const PLAYOFF_QUALIFIERS={Master:8,Expert:16,Advanced:24,Open:32};
const tierOf=(name)=>['Master','Expert','Advanced','Open'].find(t=>(name||'').includes(t))||null;
// Deep-link into the browser capture tool, pre-filtered to a team (+ its tier).
const captureUrl=(team)=>{ const t=tierOf(String((D().summary||{}).championship||''))||''; return 'capture/?team='+encodeURIComponent(team)+(t?'&division='+encodeURIComponent(t):''); };
const nextPow2=(n)=>{let k=1;while(k<n)k*=2;return k;};
// Standard bracket seed order so 1 & 2 can only meet in the final:
// seeds(4)=[1,4,2,3]; seeds(8)=[1,8,4,5,2,7,3,6].
function seedOrder(k){let s=[1];while(s.length<k){const m=s.length*2+1,t=[];for(const x of s)t.push(x,m-x);s=t;}return s;}
const ubRoundName=(m)=> m===1?'Final':m===2?'Semifinals':m===4?'Quarterfinals':'Round of '+(2*m);

function renderPlayoffs(){
  const wrap=el(`<div></div>`);
  const tier=tierOf(String((D().summary||{}).championship||''));
  if(!tier){
    wrap.appendChild(el(`<div class="card"><p class="eyebrow">Playoffs</p>`+
      `<p class="note">Pick a single division (Master / Expert / Advanced / Open) from the switcher above — a Combined view has no single bracket.</p></div>`));
    return wrap;
  }
  const N=PLAYOFF_QUALIFIERS[tier]||8, teams=D().teams||[], k=nextPow2(N);
  const ubRounds=Math.round(Math.log2(k)), order=seedOrder(k);
  const po=D().playoffs||[];   // real played series, attached from the playoff championship (empty until it exists)

  // Real results (once the playoff championship is ingested): each played series,
  // grouped by bracket round, winner highlighted. Shown above the projection.
  if(po.length){
    const rc=el(`<div class="card"></div>`);
    rc.appendChild(el(`<p class="eyebrow">${esc(tier)} playoffs — results</p>`));
    rc.appendChild(el(`<p class="note" style="margin:2px 0 8px">${po.length} series played · double elimination · Ft3 <span class="faint">(Grand Final Ft4)</span></p>`));
    const byRound={}; po.forEach(m=>{const r=m.round||0;(byRound[r]=byRound[r]||[]).push(m);});
    Object.keys(byRound).map(Number).sort((a,b)=>a-b).forEach(rd=>{
      rc.appendChild(el(`<p class="note" style="margin:8px 0 2px"><b>Round ${rd||'—'}</b></p>`));
      byRound[rd].sort((a,b)=>String(a.finished_at||'').localeCompare(String(b.finished_at||''))).forEach(m=>{
        const w1=m.winner_team&&m.winner_team===m.f1, w2=m.winner_team&&m.winner_team===m.f2;
        rc.appendChild(el(`<div style="display:flex;justify-content:space-between;align-items:center;gap:8px;padding:3px 0;border-top:1px solid var(--line);font-size:12.5px">`+
          `<span style="flex:1;overflow:hidden;text-overflow:ellipsis"><b style="color:${w1?'var(--good)':'var(--fg)'}">${esc(m.f1||'TBD')}</b> <span class="faint">vs</span> <b style="color:${w2?'var(--good)':'var(--fg)'}">${esc(m.f2||'TBD')}</b>${m.forfeit?' <span class="faint">(FF)</span>':''}</span>`+
          `<span class="st">${esc(m.series||'')}</span></div>`));
      });
    });
    wrap.appendChild(rc);
  }

  const hd=el(`<div class="card"${po.length?' style="margin-top:14px"':''}></div>`);
  hd.appendChild(el(`<p class="eyebrow">${esc(tier)} playoffs — projected</p>`));
  hd.appendChild(el(`<p style="margin:2px 0 0;font-size:14px">Top <b>${N}</b> · double elimination · Ft3 <span class="faint">(Grand Final Ft4)</span></p>`));
  hd.appendChild(el(`<p class="note" style="margin-top:6px">${po.length?'Real results are shown above; the seeds and bracket below are the standings-based projection.':'Seeded by current standings (win %). Bracket slots fill in once playoffs begin — no playoff matches have been played yet.'} Format from FACEIT League S8; will re-confirm when S9 brackets are posted.</p>`));
  wrap.appendChild(hd);

  // Projected seeds
  const seedCard=el(`<div class="card" style="margin-top:14px"></div>`);
  seedCard.appendChild(el(`<p class="eyebrow">Projected seeds (top ${N})</p>`));
  const sg=el(`<div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(210px,1fr));gap:1px 20px"></div>`);
  for(let i=0;i<N;i++){const t=teams[i];
    sg.appendChild(el(`<div style="display:flex;align-items:center;gap:8px;padding:3px 0;border-top:1px solid var(--line);font-size:12.5px">`+
      `<span class="br-seed">${i+1}</span>`+
      `<span style="flex:1;overflow:hidden;text-overflow:ellipsis">${t?esc(t.name):'<span class="faint">— not enough teams yet —</span>'}</span>`+
      `<span class="st">${t?t.win_pct+'%':''}</span></div>`));
  }
  seedCard.appendChild(sg); wrap.appendChild(seedCard);

  // Bracket
  const teamCell=(seed)=>{
    if(seed==null) return `<div class="br-team tbd">TBD</div>`;
    if(seed>N) return `<div class="br-team bye"><span class="br-seed">${seed}</span>— bye —</div>`;
    const t=teams[seed-1];
    return t? `<div class="br-team"><span class="br-seed">${seed}</span><span class="br-nm">${esc(t.name)}</span><span class="br-wp">${t.win_pct}%</span></div>`
            : `<div class="br-team tbd"><span class="br-seed">${seed}</span>—</div>`;
  };
  const tbd=`<div class="br-match"><div class="br-team tbd">TBD</div><div class="br-team tbd">TBD</div></div>`;
  const col=(title,inner)=>{const c=el(`<div class="br-col"></div>`);c.appendChild(el(`<h4>${esc(title)}</h4>`));c.appendChild(el(`<div class="br-col-body">${inner}</div>`));return c;};
  const flow=()=>{const b=el(`<div class="bracket"><div class="br-flow"></div></div>`);return[b,b.querySelector('.br-flow')];};

  const brCard=el(`<div class="card" style="margin-top:14px"></div>`);
  brCard.appendChild(el(`<p class="eyebrow">Bracket</p>`));

  brCard.appendChild(el(`<p class="note" style="margin:0 0 4px"><b>Upper bracket</b></p>`));
  const [ub,ubFlow]=flow();
  let r1=''; for(let i=0;i<k/2;i++) r1+=`<div class="br-match">${teamCell(order[2*i])}${teamCell(order[2*i+1])}</div>`;
  ubFlow.appendChild(col(ubRoundName(k/2), r1));
  for(let m=k/4;m>=1;m/=2){ let inner=''; for(let i=0;i<m;i++) inner+=tbd; ubFlow.appendChild(col(ubRoundName(m), inner)); }
  brCard.appendChild(ub);

  brCard.appendChild(el(`<p class="note" style="margin:14px 0 4px"><b>Lower bracket</b> <span class="faint">— filled by upper-bracket losers</span></p>`));
  const [lb,lbFlow]=flow();
  const lbRounds=2*(ubRounds-1);
  for(let j=1;j<=lbRounds;j++){ const cnt=Math.pow(2,(ubRounds-1)-Math.ceil(j/2)); let inner=''; for(let i=0;i<cnt;i++) inner+=tbd; lbFlow.appendChild(col('LB round '+j, inner)); }
  brCard.appendChild(lb);

  brCard.appendChild(el(`<p class="note" style="margin:14px 0 4px"><b>Grand Final</b></p>`));
  const [gf,gfFlow]=flow(); gfFlow.appendChild(col('Grand Final (Ft4)', tbd)); brCard.appendChild(gf);

  wrap.appendChild(brCard);
  return wrap;
}

/* ============================================================= VIEWS */
const TABS=[
 {id:'overview',label:'Overview',render:renderOverview},
 {id:'scout',label:'Scout a team',render:renderScout},
 {id:'players',label:'Players',render:renderPlayers},
 {id:'sim',label:'Draft simulator',render:renderSim},
 {id:'meta',label:'League meta',render:renderMeta},
 {id:'playoffs',label:'Playoffs',render:renderPlayoffs},
 {id:'matches',label:'Matches',render:renderMatches},
];

let SCOUT_TEAM = null;   // set per division by recomputeDivision()
let SCOUT_PREP=false;       // scout tab: full detail vs the condensed prep sheet
const PLANNED={};           // counter-scout: team -> Set of planned hero names
let SCOUT_N=null, META_N=40;   // recent-match counts; null = all
let PLAYERS_ROLE='All';        // Players tab: By hero role filter
let PLAYERS_VIEW='hero';        // Players tab mode: 'hero' | 'role'
let SIM_A=null, SIM_B=null, SIM_FIRST='A', SIM_PATH=[];  // draft simulator state

function gotoScout(team){ SCOUT_TEAM=team; show('scout'); }

function renderOverview(){
  const s=D().summary, wrap=el(`<div></div>`);

  // Coverage-at-a-glance beats data-health diagnostics: how much of the league
  // is actually scouted is the thing a scout wants to see first.
  const ocs=DATA.owscout_comps||{}, tn=D().team_names;
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
  const contribs=DATA.owscout_contributors||[];
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
    [{k:'name',label:'Team'},{k:'matches',label:'Matches',num:true},{k:'wins',label:'Wins',num:true},
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
      `<span style="color:var(--fg);font-size:14px;font-weight:660">${esc(t.name)}</span>`+
      pill(t.win_pct+'%',winVar(t.win_pct))+`</h4>`));
    card.appendChild(el(`<div>${body||'<span class="faint">no roster data yet</span>'}</div>`));
    rg.appendChild(card);
  });
  wrap.appendChild(rg);
  wrap.appendChild(el(`<p class="note">Current lineup = players who appeared in the team's most recent match; “map” counts are games played this season. Roles and names are FACEIT's.</p>`));
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
  const oc=(DATA.owscout_comps||{})[t.team], sc=oc&&oc.scout;
  const ad=sc&&sc.adapt;
  w.appendChild(el(`<div class="card" style="display:flex;gap:14px;flex-wrap:wrap;align-items:baseline">`+
    `<span style="font-size:18px;font-weight:680">${esc(t.team)} - prep sheet</span>`+
    `<span>${pill(`${wins}/${t.results.length} matches`,winVar(pctOf(wins,t.results.length)))} `+
    `${pill(`${t.gwins}/${t.games} maps`,winVar(pctOf(t.gwins,t.games)))}</span>`+
    (ad?`<span class="note" style="margin:0">${ad.swaps_per_map} swaps/map · ${ad.families} famil${ad.families===1?'y':'ies'}`+
        (ad.loss_followups?` · changed comp after a loss ${ad.changed_after_loss}/${ad.loss_followups}`:'')+`</span>`:'')
    +`</div>`));

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
  // Layout: a full-width top band (header, glance, coverage) over a two-column
  // body — the deep analysis in `w` (main column), the match receipts in a
  // sticky rail. `w` stays the analysis container so that body is untouched.
  const root=el(`<div></div>`);
  const w=el(`<div class="scout-main"></div>`);
  const side=el(`<div class="scout-side"></div>`);
  const matchW=t.results.filter(r=>r.won).length;
  const form=t.results.slice(0,7).map(r=>`<b class="${r.won?'w':'l'}" title="${esc(r.opp)} ${esc(r.series)}">${r.won?'W':'L'}</b>`).join('');
  const head=el(`<div class="card" style="display:flex;gap:18px;flex-wrap:wrap;align-items:center;justify-content:space-between"></div>`);
  head.appendChild(el(`<div><div style="font-size:18px;font-weight:680">${esc(t.team)}</div>`+
    `<div class="note" style="margin-top:2px">${t.used<t.total?`last ${t.used} of ${t.total} matches`:`all ${t.total} matches`} · ${dshort(t.from)} → ${dshort(t.to)}</div></div>`));
  const _hsc=((DATA.owscout_comps||{})[t.team]||{}).scout, capMaps=(_hsc&&_hsc.games)||0;
  // Coverage is all-time (captures aren't windowed), so its denominator must be
  // all-time maps played too - windowing it (t.games) could show capMaps > total.
  const _allMaps=MATCHES_RECENT.filter(m=>m.f1===t.team||m.f2===t.team)
    .reduce((s,m)=>s+m.games.filter(g=>g.map).length,0);
  head.appendChild(el(`<div style="text-align:right"><div>${pill(`${matchW}/${t.results.length} matches`,winVar(pctOf(matchW,t.results.length)))} ${pill(`${t.gwins}/${t.games} maps`,winVar(pctOf(t.gwins,t.games)))} ${pill(`comps ${capMaps}/${_allMaps} maps`,capMaps?'var(--accent)':'var(--faint)')}</div>`+
    `<div class="wl" style="margin-top:6px;justify-content:flex-end">${form||'<span class="faint">no maps</span>'}</div></div>`));
  root.appendChild(head);

  // Current roster tile: who you're actually scouting. Current lineup (played
  // the latest match) first, subs / departed dimmed below. From FACEIT round_players.
  {
    const ros=((D().teams.find(x=>x.name===t.team)||{}).roster)||[];
    const cur=ros.filter(p=>p.current), sub=ros.filter(p=>!p.current);
    const prow=(p,dim)=>`<div class="pl"${dim?' style="opacity:.5"':''}>`+
      `<span class="dot bg-${esc(p.role||'')}" title="${esc(p.role||'—')}"></span>`+
      `<span>${esc(p.nick)}</span><span class="st">${p.games} map${p.games===1?'':'s'}</span></div>`;
    const rc=el(`<div class="card roster"></div>`);
    rc.appendChild(el(`<p class="eyebrow">Current roster</p>`));
    if(ros.length){
      const grid=el(`<div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(200px,1fr));gap:0 20px"></div>`);
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
    const scoutG=((DATA.owscout_comps||{})[t.team]||{}).scout;
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
    const tBan={}, tFirst={}; let tBanTot=0, tFirstG=0;
    t.matches.forEach(m=>m.games.forEach(gm=>{ if(!gm.map) return;
      const mine=(gm.bans||[]).filter(b=>b.hero&&b.team===t.team).sort((a,b)=>(a.order||9)-(b.order||9));
      if(mine.length){ inc(tFirst,mine[0].hero); tFirstG++; }
      mine.forEach(b=>{ inc(tBan,b.hero); tBanTot++; }); }));
    const fBan={}; let fBanTot=0;
    D().matches.forEach(m=>m.games.forEach(gm=>{ if(!gm.map) return;
      (gm.bans||[]).forEach(b=>{ if(b.hero){ inc(fBan,b.hero); fBanTot++; } }); }));
    const feb=rank(tFirst)[0], opener=(feb&&tFirstG>=3&&feb[1]>=2)?feb[0]:null;
    let tb=rank(tBan).slice(0,4);
    if(opener && !tb.some(([h])=>h===opener)) tb=[[opener,tBan[opener]||0],...tb].slice(0,4);
    if(tb.length) tb.forEach(([h,n])=>{
      const ts=tBanTot?n/tBanTot:0, fs=fBanTot?(fBan[h]||0)/fBanTot:0;
      const over=n>=2 && ts>=fs*1.6 && (ts-fs)>=0.05;   // a real team-specific tell, not the meta
      c2.appendChild(el(`<div class="crow"><span>${heroChip(h)}${opener===h?` <span class="opener" title="their most common first ban">1st ban</span>`:''}</span>`+
        `<span class="rec">${n}x${over?`<span class="bvs" title="${esc(t.team)} bans this in ${Math.round(ts*100)}% of their games; the league average is ${Math.round(fs*100)}%">▲ ${Math.round(ts*100)}% vs ${Math.round(fs*100)}% league</span>`:''}</span></div>`));
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
      `<span class="rec">${r.picks}x · ${wrCell(r.wins,r.games)}</span></div>`)));
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
    const sc=((DATA.owscout_comps||{})[t.team]||{}).scout;
    const banRows=rank(t.bans).slice(0,8).map(([h,n])=>({label:heroChip(h),value:n,color:roleVar(HERO_ROLE[h])}));
    const pool=((sc&&sc.hero_pool)||[]).slice().sort((a,b)=>(b.rounds||0)-(a.rounds||0)).slice(0,8);
    const playRows=pool.map(h=>({label:heroChip(h.hero),value:h.rounds||0,color:roleVar(h.role||HERO_ROLE[h.hero])}));
    if(banRows.length||playRows.length){
      const two=el(`<div class="grid cols-2" style="margin-top:14px"></div>`);
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
      row.appendChild(el(`<a class="btn" href="${captureUrl(t.team)}" style="text-decoration:none;padding:4px 10px;font-size:12px;margin-left:auto;white-space:nowrap">Capture →</a>`));
      cov.appendChild(row);
    } else {
      cov.appendChild(el(`<p class="note" style="margin:0">Fully scouted - every replay-coded game is captured.</p>`));
    }
    root.appendChild(cov);
  }

  // Adaptability now lives in the glance band above. Sticky jump bar heads the
  // main column; Matches moved to the rail, so it drops out of the jump links.
  w.appendChild(el(`<nav class="minibar">`+
    `<a href="#sc-run">What they run</a><a href="#sc-ban">Ban decision</a>`+
    `<a href="#sc-map">Map decision</a></nav>`));

  // ---- Scouting from captured replays (owscout) -------------------------
  // Three sections: what they play (Common comps + Hero pool), where they play
  // it (Map scouting, collapsible), and how they react (Common swaps).
  const oc=(DATA.owscout_comps||{})[t.team];
  const scout=oc&&oc.scout;
  const nGames=(scout&&scout.games)||0;
  // Honest degrade: don't let the hero sections silently vanish for an uncaptured
  // team - say so, and point at the rail so they get scouted.
  if(!scout){
    const ns=el(`<div class="card" style="margin-top:10px;display:flex;justify-content:space-between;align-items:center;gap:12px;flex-wrap:wrap"></div>`);
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
    if(sigBan) tells.push(`<span class="then">ban</span> bans ${heroChip(sigBan.hero)} far more than most `+
      `<span class="faint">${sigBan.lift.toFixed(1)}× the league average · ${sigBan.n} bans</span>`);
    const br=((scout&&scout.ban_response)||[]).filter(b=>b.games>=2 && (b.opens||[]).length)[0];
    if(br) tells.push(`<span class="then">when ${esc(br.banned)} banned</span> opens ${compRow(br.opens[0].heroes)} `+
      `<span class="faint">${br.games} games</span>`);
    const sig=Object.entries(t.pickFirstBan).map(([m,v])=>({m,v}))
      .filter(x=>x.v.games>=2).sort((a,b)=>b.v.games-a.v.games)[0];
    if(sig){ const tb=rank(sig.v.bans)[0];
      tells.push(`<span class="then">map</span> on ${esc(sig.m)} they pick &amp; open the ban`+
        (tb?` on ${heroChip(tb[0])}`:'')+` <span class="faint">${sig.v.games}x, self-chosen</span>`); }
    if(tells.length){
      const card=el(`<div class="card" style="margin-top:10px"><p class="eyebrow">Scouting tells</p></div>`);
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
                    `${banHtml(c)}<span class="rec">${rec(c)}</span></div>`;

  // Ubiquitous heroes carry no trigger signal - computed once per team, used
  // by every swap row this page renders.
  SWAP_NOISE=new Set();
  if(scout){
    const mus=scout.matchups||[]; const prev={};
    mus.forEach(m=>new Set(m.vs).forEach(h=>prev[h]=(prev[h]||0)+1));
    if(mus.length>=4) Object.entries(prev).forEach(([h,n])=>{ if(n/mus.length>=0.9) SWAP_NOISE.add(h); });
  }
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
        `<span class="note">HUD-attributed · #rank = this hero vs the field's other players of it${capSince()}</span>`)));
      const pgrid=el(`<div class="grid cols-3"></div>`);
      ppools.forEach(p=>{
        const card=el(`<div class="card"></div>`);
        card.appendChild(el(`<p class="eyebrow">${esc(p.player)} <span class="note" style="text-transform:none;letter-spacing:0">${p.rounds} rounds seen</span></p>`));
        p.heroes.slice(0,5).forEach(h=>{
          // Per-hero rank vs everyone who plays it (role-weighted): green=top
          // third, amber=middle, red=bottom. Low-sample ranks aren't shown as a
          // confident pill - just a faint "low data" note - so a 1-game hero
          // doesn't flash "#1". Hover shows the per-game averages.
          const rk=h.rank?(h.low_data
              ?`<span class="faint" style="font-size:11px">low data</span>`
              :pill('#'+h.rank+'/'+h.of,h.pct>=67?'var(--good)':h.pct>=34?'var(--mid)':'var(--bad)')):'';
          const st=h.stats?` title="${h.games}g avg · ${h.stats.kd!=null?h.stats.kd+' k/d · ':''}${nf(h.stats.damage)} dmg · ${h.stats.elims} elim · ${h.stats.deaths} deaths · ${nf(h.stats.healing)} heal · ${nf(h.stats.mitigation)} mit"`:'';
          card.appendChild(el(
            `<div class="crow"${st}><span>${heroChip(h.hero)} ${rk}</span>`+
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
          fh.push({opp:us?m.f2:m.f1, won:g.winner_team===t.team, when:m.finished_at,
                   score:us?`${g.f1}-${g.f2}`:`${g.f2}-${g.f1}`, pick:g.map_picked_by===t.team});
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
            `<div class="crow"><span>${x.pick?`<span class="pickpill" title="they picked this map">pick</span> `:''}<span class="faint">vs</span> ${esc(x.opp||'?')}</span>`+
            `<span class="rec">${x.when?dshort(x.when)+' &middot; ':''}<span class="faint">${esc(x.score)}</span> ${x.won?'<b class="wlw">W</b>':'<b class="wll">L</b>'}</span></div>`)));
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
            resBox.appendChild(el(`<div class="crow${ov.length<2?' thin':''}">`+
              `<span class="csrow"><span class="wlsq ${m.won?'w':'l'}">${m.won?'W':'L'}</span>`+
              `<b>${esc(m.map)}</b><span class="faint">ran</span>${compRow(m.open||[])}</span>`+
              `<span class="rec">matched ${ov.length}/${signal.length}</span></div>`));
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

      const rows=pool.filter(h=>(h.pick_rate||0)>=0.25).map(h=>{
        const seat=HERO_SEAT[h.hero]||h.role||'?';
        const backup=(bySeat[seat]||[]).find(x=>x.hero!==h.hero)||null;
        const br=brByHero[h.hero];
        let banned=null;
        if(br){
          let w=0,l=0; (br.opens||[]).forEach(o=>{w+=o.wins;l+=o.losses;});
          banned={games:br.games,w,l};
        }
        // Transparent verdict: they lean on it AND the same seat has no strong
        // captured backup -> expensive. Backup nearly as played -> cheap.
        const share=h.pick_rate||0, bshare=backup?(backup.pick_rate||0):0;
        const verdict=(share>=0.6&&bshare<0.3)?['expensive','var(--good)']
                     :(bshare>=share*0.7)?['cheap','var(--bad)']
                     :['moderate','var(--mid)'];
        return {h,seat,backup,banned,share,verdict};
      }).sort((a,b)=>{
        const rank=v=>v==='expensive'?0:v==='moderate'?1:2;
        return rank(a.verdict[0])-rank(b.verdict[0])||b.share-a.share;
      });

      if(rows.length){
        w.appendChild(el(sectionH('Ban planner',
          `<span class="note">what a ban would cost them - lean + same-seat backup + history</span>`)));
        const card=el(`<div class="card"></div>`);
        rows.slice(0,8).forEach(({h,seat,backup,banned,share,verdict})=>{
          const parts=[`${Math.round(share*100)}% of rounds`,
                       `<span class="faint">${esc(seat)}</span>`];
          parts.push(backup
            ?`backup: ${heroIcon(backup.hero)} ${esc(backup.hero)} <span class="faint">${Math.round((backup.pick_rate||0)*100)}%</span>`
            :`<b>no captured backup in seat</b>`);
          if(banned) parts.push(`when banned: <b>${banned.w}W-${banned.l}L</b> <span class="faint">(${banned.games}g)</span>`);
          card.appendChild(el(`<div class="crow"><span>${heroChip(h.hero)} <span class="faint">·</span> ${parts.join(' <span class="faint">·</span> ')}</span>`+
            `<span class="rec">${pill('ban: '+verdict[0],verdict[1])}</span></div>`));
        });
        card.appendChild(el(`<p class="note" style="margin:8px 0 0">"expensive" = they lean on it and the seat has no practiced fallback. Verdicts summarise the shown numbers - check the components on thin data.</p>`));
        w.appendChild(card);
      }
    }

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
  const mapC=el(`<div class="card"></div>`);
  mapC.appendChild(el(`<p class="eyebrow">Maps — picks &amp; win rate</p>`));
  const mrows=Object.entries(t.mapStats).map(([m,v])=>({map:m,cat:MAP_CAT[m]||'',games:v.games,picks:v.picks,wins:v.wins,wr:pctOf(v.wins,v.games)})).sort((a,b)=>mapCmp(a.map,b.map));
  mapC.appendChild(mrows.length?table(
    [{k:'map',label:'Map'},
     {k:'picks',label:'Picked',num:true},{k:'games',label:'Played',num:true},
     {k:'wr',label:'Win %',num:true,html:r=>wrCell(r.wins,r.games)}], mrows, byMode)
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
    .map(([opp,tot])=>({opp,tot,resp:rank(t.counter[opp]).map(([h,n])=>`${heroChip(h)}<span class="faint"> ${n}</span>`).join(' ')}));
      dv.body.appendChild(cRows.length?table(
    [{k:'opp',label:'Opponent banned first',html:r=>heroChip(r.opp)},{k:'tot',label:'×',num:true},
     {k:'resp',label:`${esc(t.team)} replied with`,html:r=>r.resp}], cRows)
   :el(`<p class="note">No counter-bans in this window (needs the opponent to have banned first with both bans attributed).</p>`));

    // Ban -> opening: when THIS team bans a hero (FACEIT, complete), the heroes
    // they open with in those games. A hero shown in most of the "banned X" games
    // is the tell ("bans Sigma -> opens Ramattra"). Needs captured openings, so it
    // fills in as more of their games are scouted.
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
    w.appendChild(dv.root);
  }

  // ==== MAP DECISION ====
  w.appendChild(cluster('sc-map','Map decision'));
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
      n:Object.values(pm[mp]).reduce((a,b)=>a+b,0),
      heroes:rank(pm[mp]).map(([h,c])=>`${heroChip(h)}<span class="faint"> ${c}</span>`).join(' ')}))
      .sort((a,b)=>b.n-a.n||mapCmp(a.map,b.map));
    return rows.length?table(
      [{k:'map',label:'Map',html:r=>`${esc(r.map)} <span class="faint">${esc(r.cat)}</span>`},
       {k:'n',label:'Bans',num:true},{k:'heroes',label:'Heroes banned',html:r=>r.heroes}],
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

  const layout=el(`<div class="scoutgrid"></div>`);
  layout.append(w, side);
  root.appendChild(layout);
  return root;
}

/* ================================================= DRAFT SIMULATOR (manual scenario planner) */
// Per-team history over the active division: map-pick counts, per-map ban counts, overall ban counts.
/* ============================================================= PLAYERS */
// League-wide player leaderboards from owscout's merge-time ranks (division/tier-
// scoped, role-weighted, deaths heavy). Two modes: "By hero" (rank within one
// hero) and "By role" (aggregate a player across the heroes of a competitive seat
// — Tank / Hitscan / Flex DPS / Main Support / Flex Support).
const PLAYER_STAT_FIELDS=['damage','elims','deaths','healing','mitigation'];
// Aggregate each player's per-hero composite across the heroes of a seat, weighted
// by games, then rank within the seat. Confident (>=2 seat games) vs low-data.
function seatLeaderboards(){
  const ocs=DATA.owscout_comps||{}, byPlayer={};
  D().team_names.forEach(team=>{
    (((ocs[team]||{}).scout||{}).players||[]).forEach(p=>{
      (p.heroes||[]).forEach(h=>{
        if(h.comp==null||!h.games) return;
        const seat=HERO_SEAT[h.hero]; if(!seat) return;
        const key=team+'|'+p.player;
        const pe=byPlayer[key]||(byPlayer[key]={player:p.player,team,seats:{}});
        const e=pe.seats[seat]||(pe.seats[seat]={g:0,cw:0,heroes:{},
          st:{damage:0,elims:0,deaths:0,healing:0,mitigation:0}});
        e.g+=h.games; e.cw+=h.comp*h.games;
        PLAYER_STAT_FIELDS.forEach(k=>e.st[k]+=((h.stats&&h.stats[k])||0)*h.games);
        e.heroes[h.hero]=(e.heroes[h.hero]||0)+h.games;
      });
    });
  });
  // Each player appears ONLY on their primary (most-played) seat, so a hitscan
  // main doesn't also clutter the Flex DPS board.
  const bySeat={};
  Object.values(byPlayer).forEach(pe=>{
    const seats=Object.entries(pe.seats).sort((a,b)=>b[1].g-a[1].g);
    if(!seats.length) return;
    const seat=seats[0][0], e=seats[0][1];
    (bySeat[seat]=bySeat[seat]||[]).push(Object.assign({player:pe.player,team:pe.team},e));
  });
  const rankGrp=arr=>{ arr.sort((a,b)=>b.idx-a.idx);
    arr.forEach((r,i)=>{ r.rank=i+1; r.of=arr.length;
      r.pct=arr.length>1?Math.round(100*(arr.length-1-i)/(arr.length-1)):100; }); return arr; };
  const out={};
  SEATS.forEach(seat=>{
    const players=bySeat[seat]; if(!players) return;
    const list=players.map(e=>{ const kd=e.st.elims/Math.max(e.st.deaths,0.5);
      return {player:e.player,team:e.team,games:e.g,idx:e.cw/e.g,low:e.g<2,
        stats:{damage:Math.round(e.st.damage/e.g),healing:Math.round(e.st.healing/e.g),
          mitigation:Math.round(e.st.mitigation/e.g),
          elims:Math.round(e.st.elims/e.g*10)/10,deaths:Math.round(e.st.deaths/e.g*10)/10,
          kd:Math.round(kd*100)/100},
        heroes:Object.entries(e.heroes).sort((a,b)=>b[1]-a[1]).map(x=>x[0])}; });
    out[seat]={conf:rankGrp(list.filter(r=>!r.low)),low:rankGrp(list.filter(r=>r.low))};
  });
  return out;
}
function renderPlayers(){
  const wrap=el(`<div></div>`);
  const ocs=DATA.owscout_comps||{}, byHero={};
  D().team_names.forEach(team=>{
    (((ocs[team]||{}).scout||{}).players||[]).forEach(p=>{
      (p.heroes||[]).forEach(h=>{ if(h.rank==null) return;
        (byHero[h.hero]=byHero[h.hero]||[]).push({player:p.player, team, ...h}); });
    });
  });
  if(!Object.keys(byHero).length){
    wrap.appendChild(el(`<p class="note" style="margin-top:14px">No ranked players yet. Player rankings appear once a division has <b>enough captured games</b> — capture more to fill this in.</p>`));
    return wrap;
  }
  wrap.appendChild(el(sectionH('Players',
    `<span class="note">ranked within ${esc(D().summary.championship||'the division')} · by k/d, deaths, then output (role-weighted) · By role lists each player on their main seat only · hover for per-game stats${capSince()}</span>`)));
  const modebar=el(`<div class="wsel" style="margin:2px 2px 10px"></div>`);   // By hero | By role
  const bar=el(`<div class="wsel" style="margin:2px 2px 12px"></div>`);       // hero-role sub-filter
  const body=el(`<div></div>`);
  wrap.append(modebar, bar, body);

  // Stats shown in the blend's priority order per role: tank k/d>deaths>dmg,
  // dps k/d>dmg>deaths, support heal>deaths>k/d.
  const statLine=(base,s)=>{
    const kd=s.kd!=null?`${s.kd} k/d`:'';
    if(base==='Support') return `${nf(s.healing)} heal · ${s.deaths} d${kd?' · '+kd:''}`;
    if(base==='Tank')    return `${kd?kd+' · ':''}${s.deaths} d · ${nf(s.damage)} dmg`;
    return `${kd?kd+' · ':''}${nf(s.damage)} dmg · ${s.deaths} d`;
  };
  const rowHtml=(base,r,extra)=>{
    const lo=r.low_data||r.low, s=r.stats||{};
    const col=lo?'var(--faint)':(r.pct>=67?'var(--good)':r.pct>=34?'var(--mid)':'var(--bad)');
    return `<div class="crow${lo?' thin':''}" title="${r.games} game${r.games===1?'':'s'} avg · ${s.kd!=null?s.kd+' k/d · ':''}${nf(s.damage)} dmg · ${s.elims} elim · ${s.deaths} deaths · ${nf(s.healing)} heal · ${nf(s.mitigation)} mit">`+
      `<span>${pill('#'+r.rank,col)} <b>${esc(r.player)}</b> <span class="faint">${esc(r.team)}</span>${extra||''}</span>`+
      `<span class="rec">${statLine(base,s)}${lo?` <span class="faint">· ${r.games}g</span>`:''}</span></div>`;
  };
  const makeCard=(titleHtml,conf,low,base,extraFn)=>{
    const card=el(`<div class="card"></div>`);
    card.appendChild(el(`<p class="eyebrow">${titleHtml}</p>`));
    conf.forEach(r=>card.appendChild(el(rowHtml(base,r,extraFn&&extraFn(r)))));
    if(low.length){
      card.appendChild(el(`<p class="seg" style="margin-top:8px;color:var(--faint)">not enough data</p>`));
      low.forEach(r=>card.appendChild(el(rowHtml(base,r,extraFn&&extraFn(r)))));
    }
    return card;
  };

  function drawHero(){
    body.innerHTML=''; bar.style.display='';
    [...bar.children].forEach(b=>b.classList.toggle('selA', b.textContent===PLAYERS_ROLE));
    const heroes=Object.keys(byHero).filter(h=>PLAYERS_ROLE==='All'||HERO_ROLE[h]===PLAYERS_ROLE)
      .sort((a,b)=>byHero[b].length-byHero[a].length||a.localeCompare(b));
    if(!heroes.length){ body.appendChild(el(`<p class="note">No ranked ${esc(PLAYERS_ROLE)} players yet.</p>`)); return; }
    const grid=el(`<div class="grid cols-2"></div>`);
    heroes.forEach(hero=>{
      const all=byHero[hero], base=HERO_ROLE[hero];
      const conf=all.filter(r=>!r.low_data).sort((a,b)=>a.rank-b.rank);
      const low =all.filter(r=> r.low_data).sort((a,b)=>a.rank-b.rank);
      grid.appendChild(makeCard(`${heroChip(hero)} <span class="note" style="text-transform:none;letter-spacing:0">${all.length} player${all.length===1?'':'s'} on this hero</span>`, conf, low, base));
    });
    body.appendChild(grid);
  }
  function drawRole(){
    body.innerHTML=''; bar.style.display='none';
    const seats=seatLeaderboards();
    const grid=el(`<div class="grid cols-2"></div>`); let any=false;
    SEATS.forEach(seat=>{
      const sd=seats[seat]; if(!sd||(!sd.conf.length&&!sd.low.length)) return; any=true;
      const base=/Support/.test(seat)?'Support':(seat==='Tank'?'Tank':'Damage');
      const heroesOf=r=> r.heroes&&r.heroes.length?` <span class="faint" style="font-size:11px">${r.heroes.slice(0,3).map(esc).join(', ')}</span>`:'';
      grid.appendChild(makeCard(`${esc(seat)} <span class="note" style="text-transform:none;letter-spacing:0">${sd.conf.length+sd.low.length} players</span>`, sd.conf, sd.low, base, heroesOf));
    });
    body.appendChild(any?grid:el(`<p class="note">No ranked players in any seat yet.</p>`));
  }
  const draw=()=>{ [...modebar.children].forEach(b=>b.classList.toggle('selA', b.dataset.v===PLAYERS_VIEW));
    if(PLAYERS_VIEW==='role') drawRole(); else drawHero(); };

  [['hero','By hero'],['role','By role']].forEach(([v,label])=>{
    const b=el(`<span class="wbtn" data-v="${v}">${esc(label)}</span>`);
    b.onclick=()=>{ PLAYERS_VIEW=v; draw(); }; modebar.appendChild(b);
  });
  ['All','Tank','Damage','Support'].forEach(role=>{
    const b=el(`<span class="wbtn">${role}</span>`);
    b.onclick=()=>{ PLAYERS_ROLE=role; drawHero(); }; bar.appendChild(b);
  });
  draw();
  return wrap;
}

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
  wrap.appendChild(el(`<p class="note" style="margin:2px 2px 0">Plan a Bo5 draft by hand. Each map, the team on the clock <b>picks the map</b> and <b>bans first</b>, then the other team bans. Click a suggested hero (from that team's history) or choose <b>any hero</b> from the dropdown — e.g. ban a pocket pick so the enemy can't take it. Mark who wins each map to continue (the loser picks next). A team can't repeat its own bans across the series; used heroes drop out of its list automatically. <b>★</b> marks a signature ban — one this team bans well above the division rate.</p>`));
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
          // Signature marker: a hero this team bans well above the division rate
          // is a rehearsed, intentional ban — worth pre-empting.
          const tm=modelOf(tab), teamTot=Object.values(tm.bansAll).reduce((a,b)=>a+b,0)||1, dbase=divBanBaseline();
          sugg.forEach(s2=>{
            const lift=dbase.all[s2.hero]?(s2.all/teamTot)/dbase.all[s2.hero]:0;
            const sig=lift>=1.5?` <span class="pp" style="color:var(--good)">★×${lift.toFixed(1)}</span>`:'';
            const o=el(`<span class="opt ${node[key]===s2.hero?'sel':''} ${(s2.onMap+s2.all)<2?'dim':''}">${heroChip(s2.hero)}<span class="pp">${s2.onMap?s2.onMap+'× here':s2.all+'× total'}</span>${sig}</span>`);
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

  // Most-played comps across the league (captured openings). Aggregated by exact
  // 5-hero identity across every team; capture-gated, so honest when thin.
  {
    const agg={};
    D().team_names.forEach(team=>{
      (((DATA.owscout_comps||{})[team]||{}).comps||[]).forEach(c=>{
        const key=[...c.heroes].sort().join(',');
        const a=agg[key]||(agg[key]={heroes:c.heroes,maps:0,games:0,wins:0,teams:new Set()});
        a.maps+=c.maps||0; a.games+=c.games||0; a.wins+=c.wins||0; a.teams.add(team);
      });
    });
    const rows=Object.values(agg).sort((a,b)=>b.maps-a.maps).slice(0,12);
    wrap.appendChild(el(sectionH('Most-played comps',`<span class="note">captured openings across the league · win% shown at 3+ maps${capSince()}</span>`)));
    if(rows.length){
      const card=el(`<div class="card"></div>`);
      rows.forEach(r=>card.appendChild(el(`<div class="crow${r.maps<=1?' thin':''}"><span>${compRow(r.heroes)}</span>`+
        `<span class="rec">${r.maps} map${r.maps===1?'':'s'} · ${r.teams.size} team${r.teams.size===1?'':'s'}`+
        `${r.maps>=3?` · ${Math.round(100*r.wins/(r.games||1))}%`:''}</span></div>`)));
      wrap.appendChild(card);
    } else {
      wrap.appendChild(el(`<p class="note">No comps captured yet — this fills in as games are scouted.</p>`));
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
    card.appendChild(el(`<p class="eyebrow">${esc(c)} <span class="note" style="text-transform:none;letter-spacing:0">${tot} pick${tot===1?'':'s'}</span></p>`));
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
  const bar=el(`<div style="display:flex;gap:10px;margin-bottom:12px;align-items:center;flex-wrap:wrap"></div>`);
  // Region + Division filters (FACEIT-style). They drive the shared division
  // view, so the rest of the page follows and the header switcher stays in sync.
  const suffix=(v)=> v.region? v.label.slice(v.region.length+1) : v.label;   // "Master"/"Combined"
  const regions=[...new Set(VIEWS.map(v=>v.region).filter(Boolean))];
  const curRegion=(viewOf(CURRENT_VIEW).region)||regions[0];
  const regSel=el(`<select title="Region" style="font-size:15px;padding:11px 13px"></select>`);
  regions.forEach(r=>regSel.appendChild(el(`<option${r===curRegion?' selected':''}>${esc(r)}</option>`)));
  const divSel=el(`<select title="Division" style="font-size:15px;padding:11px 13px"></select>`);
  const fillDivs=()=>{ divSel.innerHTML='';
    VIEWS.filter(v=>v.region===regSel.value).forEach(v=>
      divSel.appendChild(el(`<option value="${v.id}"${v.id===CURRENT_VIEW?' selected':''}>${esc(suffix(v))}</option>`))); };
  fillDivs();
  regSel.onchange=()=>{ const f=VIEWS.find(v=>v.region===regSel.value); if(f) setDivision(f.id); };
  divSel.onchange=()=>setDivision(divSel.value);
  if(regions.length) bar.appendChild(regSel);
  if(VIEWS.length>1) bar.appendChild(divSel);
  const search=el(`<input placeholder="search team, hero, or map…" style="flex:1;min-width:200px;font-size:15px;padding:11px 13px">`);
  const sort=el(`<select title="Sort by date" style="font-size:15px;padding:11px 13px"><option value="new">Newest first</option><option value="old">Oldest first</option></select>`);
  bar.append(search,sort);
  // In a single round-robin every team has faced the same opponents, so a team's
  // full match list reads as their "book" against a field you already know -
  // search a team to see exactly how they drafted vs each opponent you also play.
  const note=el(`<p class="note" style="margin:0 2px 10px">Single round-robin — everyone plays the same 15 opponents. Search a team to read their book against the field.</p>`);
  const list=el(`<div></div>`); wrap.append(bar,note,list);
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
  CURRENT_VIEW=id; recomputeDivision(); updateHeader();
  const dsel=document.getElementById('division'); if(dsel) dsel.value=id;   // keep header in sync
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
  nav.appendChild(el(`<a class="navcap" href="capture/" title="Scout comps in your browser — no install, no exe">＋ Capture comps</a>`));
  const start=decodeURIComponent((location.hash||'#overview').slice(1));
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
}
// Data delivery: an inlined blob when present (offline / single-file builds),
// otherwise fetch the sibling data.json (the shell build). Next season this fetch
// is the single place gating hooks in.
(function(){
  if(typeof __OWSCOUT_DATA__!=='undefined' && __OWSCOUT_DATA__) return bootApp(__OWSCOUT_DATA__);
  fetch('data.json',{cache:'no-store'})
    .then(function(r){ if(!r.ok) throw new Error('HTTP '+r.status); return r.json(); })
    .then(bootApp)
    .catch(function(err){ var c=document.getElementById('content');
      if(c) c.innerHTML='<p class="note" style="padding:24px">Could not load scouting data ('+err+'). Refresh to retry.</p>'; });
})();
</script>
</body>
</html>
"""

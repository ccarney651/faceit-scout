"""Generate a standalone, self-contained browser-capture POC page.

Viability spike for "can OW Scout run in a browser instead of a signed .exe?".
It bakes the operator's active HUD ref library (profile 4, 52 blue + 52 red face
crops) into one HTML file so recognition runs fully client-side — no opencv.js,
no server, no network. Open the output in a browser, share the Overwatch screen,
drag two boxes over the portrait strips, and hit Read comp.

    .venv/Scripts/python poc/build_browser_poc.py
    -> poc/browser-capture.html   (open it in Chrome/Edge; see the header note)

Matching mirrors the desktop: grayscale face_subrect crops, TM_CCOEFF_NORMED
(mean-subtracted normalized cross-correlation) with a small shift search for
alignment tolerance, per-team refs (left=variant a, right=variant b).
"""
from __future__ import annotations

import base64
import json
import os
import sqlite3

import cv2

OWSCOUT_DB = "owscout.sqlite3"
FACEIT_DB = "faceit.sqlite3"
PROFILE_ID = 4          # the operator's active 2560x1440 HUD library
REF_W, REF_H = 64, 36   # common match size (refs are ~77x44; keep ~1.75 aspect)
LEFT_FRACTION = 0.42    # face_subrect: drop the left 42% (ult overlay)
TOP_FRACTION = 0.45     # keep the top 45% (above the name bar)
OUT = os.path.join("poc", "browser-capture.html")


def hero_names() -> dict[str, str]:
    names: dict[str, str] = {}
    with sqlite3.connect(FACEIT_DB) as f:
        for guid, name in f.execute("SELECT guid, name FROM heroes"):
            names[guid] = name
    # custom heroes live in the owscout DB
    try:
        with sqlite3.connect(OWSCOUT_DB) as o:
            for guid, name in o.execute("SELECT guid, name FROM custom_heroes"):
                names[guid] = name
    except sqlite3.Error:
        pass
    return names


def build_refs() -> list[dict[str, str]]:
    names = hero_names()
    refs: list[dict[str, str]] = []
    with sqlite3.connect(OWSCOUT_DB) as c:
        rows = c.execute(
            "SELECT hero_guid, variant, image_path FROM hero_refs "
            "WHERE profile_id=? AND state='alive'",
            (PROFILE_ID,),
        ).fetchall()
    for guid, variant, path in rows:
        if not path or not os.path.exists(path):
            continue
        img = cv2.imread(path, cv2.IMREAD_GRAYSCALE)
        if img is None:
            continue
        small = cv2.resize(img, (REF_W, REF_H), interpolation=cv2.INTER_AREA)
        refs.append({
            "n": names.get(guid, guid[:6]),
            "v": variant,
            "d": base64.b64encode(small.tobytes()).decode("ascii"),
        })
    return refs


HTML = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>OW Scout — browser capture POC</title>
<style>
  :root{color-scheme:dark}
  body{margin:0;background:#0d1015;color:#e7ebf2;font:14px/1.5 system-ui,Segoe UI,sans-serif}
  header{padding:14px 18px;border-bottom:1px solid #252c37}
  h1{font-size:17px;margin:0 0 4px}
  .sub{color:#98a2b2;font-size:12.5px;max-width:900px}
  main{padding:16px 18px;display:grid;gap:14px}
  .bar{display:flex;gap:8px;flex-wrap:wrap;align-items:center}
  button{background:#8087ff;color:#0b1020;border:0;border-radius:7px;padding:9px 13px;font-weight:650;cursor:pointer}
  button.ghost{background:#1d232c;color:#e7ebf2;border:1px solid #313a48}
  button:disabled{opacity:.45;cursor:default}
  .stage{position:relative;display:inline-block;max-width:100%;border:1px solid #252c37;border-radius:8px;overflow:hidden;background:#000}
  video{display:block;max-width:100%;height:auto}
  canvas.ov{position:absolute;left:0;top:0;cursor:crosshair}
  .status{color:#98a2b2;font-size:12.5px}
  .grid{display:grid;grid-template-columns:1fr 1fr;gap:14px;max-width:760px}
  .team{border:1px solid #252c37;border-radius:8px;padding:10px 12px;background:#161a21}
  .team h3{margin:0 0 8px;font-size:12px;letter-spacing:.04em;text-transform:uppercase;color:#98a2b2}
  .slot{display:flex;justify-content:space-between;gap:8px;padding:4px 0;border-top:1px solid #252c37;font-size:13.5px}
  .slot:first-of-type{border-top:0}
  .sc{font-variant-numeric:tabular-nums;font-size:12px}
  .hi{color:#34b877}.mid{color:#d3a02a}.lo{color:#e5624a}
  code{background:#1d232c;padding:1px 5px;border-radius:4px}
  .warn{color:#e5624a}
</style></head><body>
<header>
  <h1>OW Scout — browser capture viability POC</h1>
  <div class="sub">Proves whether hero recognition can run entirely in a browser (no install, no signed exe). Everything is baked into this one file — the ref library, the matcher — and nothing leaves your machine. Run Overwatch <b>borderless/windowed</b> (exclusive fullscreen can't be captured), share the screen, drag the two boxes over the 5 blue and 5 red portraits once, then Read comp.
  <br><span class="warn" id="ctxwarn"></span></div>
</header>
<main>
  <div class="bar">
    <button id="share">1 · Share my screen</button>
    <button id="setL" class="ghost" disabled>2a · Set LEFT box (blue)</button>
    <button id="setR" class="ghost" disabled>2b · Set RIGHT box (red)</button>
    <button id="read" disabled>3 · Read comp</button>
    <label class="status"><input type="checkbox" id="auto"> auto every 2s</label>
    <button id="pop" class="ghost">Pop out overlay ⇱</button>
    <button id="clear" class="ghost">reset boxes</button>
  </div>
  <div class="status" id="hint">Click “Share my screen” and pick your Overwatch window/screen.</div>
  <div class="stage" id="stage">
    <video id="vid" autoplay muted playsinline></video>
    <canvas id="ov" class="ov"></canvas>
  </div>
  <div class="status" id="meta"></div>
  <div class="grid">
    <div class="team"><h3>Left / blue (variant a)</h3><div id="outA"></div></div>
    <div class="team"><h3>Right / red (variant b)</h3><div id="outB"></div></div>
  </div>
</main>
<script>
const REFS_RAW = __REFS__;
const REF_W=__RW__, REF_H=__RH__, LF=__LF__, TF=__TF__, PAD=2;

// secure-context check (getDisplayMedia needs https/localhost/file with flags)
if(!window.isSecureContext || !navigator.mediaDevices || !navigator.mediaDevices.getDisplayMedia){
  document.getElementById('ctxwarn').textContent =
    "This page isn't in a secure context, so screen capture may be blocked. If “Share” fails, serve it locally:  python -m http.server  then open http://localhost:8000/poc/browser-capture.html";
}

function b64bytes(s){const bin=atob(s);const u=new Uint8Array(bin.length);for(let i=0;i<bin.length;i++)u[i]=bin.charCodeAt(i);return u;}
const REFS = REFS_RAW.map(r=>{
  const px=b64bytes(r.d); let m=0; for(let i=0;i<px.length;i++)m+=px[i]; m/=px.length;
  const c=new Float32Array(px.length); let ss=0; for(let i=0;i<px.length;i++){c[i]=px[i]-m; ss+=c[i]*c[i];}
  return {n:r.n, v:r.v, c, norm:Math.sqrt(ss)||1};
});

const vid=document.getElementById('vid'), ov=document.getElementById('ov'), octx=ov.getContext('2d');
let boxes=JSON.parse(localStorage.getItem('owscout_poc_boxes')||'{}');   // {a:{x,y,w,h}, b:{...}} in VIDEO px
let drawMode=null, dragStart=null, dragCur=null, autoTimer=null;
// Where reads render — the main page, or a popped-out floating always-on-top
// window (Document Picture-in-Picture) that sits over Overwatch so no alt-tab.
let target={A:document.getElementById('outA'), B:document.getElementById('outB'), meta:document.getElementById('meta')};

function scale(){ return vid.videoWidth ? vid.clientWidth/vid.videoWidth : 1; }
function fitOverlay(){ ov.width=vid.clientWidth; ov.height=vid.clientHeight; drawOverlay(); }
window.addEventListener('resize', fitOverlay);

function drawOverlay(){
  octx.clearRect(0,0,ov.width,ov.height); const s=scale();
  for(const side of ['a','b']){ const b=boxes[side]; if(!b) continue;
    octx.strokeStyle = side==='a' ? '#5a9bd8' : '#e9694f'; octx.lineWidth=2;
    octx.strokeRect(b.x*s, b.y*s, b.w*s, b.h*s);
    octx.setLineDash([3,3]); octx.lineWidth=1;
    for(let i=1;i<5;i++){ const x=(b.x+i*b.w/5)*s; octx.beginPath(); octx.moveTo(x,b.y*s); octx.lineTo(x,(b.y+b.h)*s); octx.stroke(); }
    octx.setLineDash([]);
  }
  if(dragStart&&dragCur){ octx.strokeStyle='#8087ff'; octx.lineWidth=2;
    octx.strokeRect(Math.min(dragStart.x,dragCur.x),Math.min(dragStart.y,dragCur.y),Math.abs(dragCur.x-dragStart.x),Math.abs(dragCur.y-dragStart.y)); }
}
function evPos(e){ const r=ov.getBoundingClientRect(); return {x:e.clientX-r.left, y:e.clientY-r.top}; }
ov.addEventListener('mousedown',e=>{ if(!drawMode)return; dragStart=evPos(e); dragCur=dragStart; });
ov.addEventListener('mousemove',e=>{ if(!drawMode||!dragStart)return; dragCur=evPos(e); drawOverlay(); });
ov.addEventListener('mouseup',e=>{ if(!drawMode||!dragStart)return; const p=evPos(e); const s=scale();
  const x=Math.min(dragStart.x,p.x)/s, y=Math.min(dragStart.y,p.y)/s, w=Math.abs(p.x-dragStart.x)/s, h=Math.abs(p.y-dragStart.y)/s;
  if(w>10&&h>10){ boxes[drawMode]={x,y,w,h}; localStorage.setItem('owscout_poc_boxes',JSON.stringify(boxes)); }
  drawMode=null; dragStart=null; dragCur=null; document.getElementById('hint').textContent='Box saved. Set the other, or Read comp.'; drawOverlay(); updateButtons();
});

async function share(){
  try{
    const stream=await navigator.mediaDevices.getDisplayMedia({video:{frameRate:5},audio:false});
    vid.srcObject=stream;
    await vid.play().catch(()=>{});
    vid.onloadedmetadata=()=>{ fitOverlay(); document.getElementById('meta').textContent=`capturing ${vid.videoWidth}x${vid.videoHeight}`; };
    setTimeout(fitOverlay,300);
    document.getElementById('hint').textContent='Screen shared. Now set the two boxes over the portrait strips.';
    updateButtons();
  }catch(err){ document.getElementById('hint').innerHTML='<span class="warn">Share failed: '+err+'</span>'; }
}
function updateButtons(){
  const ready=!!vid.srcObject;
  document.getElementById('setL').disabled=!ready;
  document.getElementById('setR').disabled=!ready;
  document.getElementById('read').disabled=!(ready&&boxes.a&&boxes.b);
}

// --- matching ---
const work=document.createElement('canvas'); work.width=REF_W+2*PAD; work.height=REF_H+2*PAD;
const wctx=work.getContext('2d',{willReadFrequently:true});
function cellGrayPadded(frame, cell){
  const fx=cell.x+cell.w*LF, fy=cell.y, fw=cell.w*(1-LF), fh=cell.h*TF;
  wctx.drawImage(frame, fx, fy, fw, fh, 0,0, work.width, work.height);
  const d=wctx.getImageData(0,0,work.width,work.height).data;
  const g=new Float32Array(work.width*work.height);
  for(let i=0,j=0;i<d.length;i+=4,j++) g[j]=0.299*d[i]+0.587*d[i+1]+0.114*d[i+2];
  return g;
}
function bestMatch(gpad, variant){
  const W=REF_W+2*PAD; let best={score:-2,name:'?'};
  for(let dy=0;dy<=2*PAD;dy+=PAD){ for(let dx=0;dx<=2*PAD;dx+=PAD){
    const cand=new Float32Array(REF_W*REF_H); let m=0;
    for(let y=0;y<REF_H;y++){ const src=(y+dy)*W+dx; for(let x=0;x<REF_W;x++){ const v=gpad[src+x]; cand[y*REF_W+x]=v; m+=v; } }
    m/=cand.length; let ss=0; for(let i=0;i<cand.length;i++){cand[i]-=m; ss+=cand[i]*cand[i];} const cn=Math.sqrt(ss)||1;
    for(const r of REFS){ if(r.v!==variant) continue; let dot=0; const rc=r.c; for(let i=0;i<cand.length;i++) dot+=rc[i]*cand[i];
      const s=dot/(r.norm*cn); if(s>best.score) best={score:s,name:r.n}; }
  }}
  return best;
}
function grabFrame(){ const c=document.createElement('canvas'); c.width=vid.videoWidth; c.height=vid.videoHeight; c.getContext('2d').drawImage(vid,0,0); return c; }
function slotClass(s){ return s>=0.75?'hi':s>=0.55?'mid':'lo'; }
function read(){
  if(!boxes.a||!boxes.b) return;
  const t0=performance.now(); const frame=grabFrame();
  for(const side of ['a','b']){ const b=boxes[side]; const host=(side==='a'?target.A:target.B); host.innerHTML='';
    for(let i=0;i<5;i++){ const cell={x:b.x+i*b.w/5,y:b.y,w:b.w/5,h:b.h};
      const r=bestMatch(cellGrayPadded(frame,cell), side);
      const row=document.createElement('div'); row.className='slot';
      row.innerHTML=`<span>${r.score>=0.5?r.name:'??'}</span><span class="sc ${slotClass(r.score)}">${r.score.toFixed(2)}</span>`;
      host.appendChild(row);
    } }
  target.meta.textContent=`${vid.videoWidth}x${vid.videoHeight} · ${(performance.now()-t0).toFixed(0)} ms · updated ${new Date().toLocaleTimeString()}`;
}

document.getElementById('share').onclick=share;
document.getElementById('setL').onclick=()=>{drawMode='a';document.getElementById('hint').textContent='Drag a box over the 5 BLUE (left) portraits.';};
document.getElementById('setR').onclick=()=>{drawMode='b';document.getElementById('hint').textContent='Drag a box over the 5 RED (right) portraits.';};
document.getElementById('read').onclick=read;
document.getElementById('clear').onclick=()=>{boxes={};localStorage.removeItem('owscout_poc_boxes');drawOverlay();updateButtons();document.getElementById('outA').innerHTML='';document.getElementById('outB').innerHTML='';};
document.getElementById('auto').onchange=e=>{ if(e.target.checked){ autoTimer=setInterval(()=>{ if(boxes.a&&boxes.b&&vid.srcObject) read(); },1500);} else clearInterval(autoTimer); };

// Pop out a floating, always-on-top window (Document Picture-in-Picture) that
// sits over Overwatch in borderless — the browser's answer to an in-game overlay.
// Kicks on continuous auto-read so the comp updates with zero alt-tab.
async function popout(){
  if(!('documentPictureInPicture' in window)){ alert('Floating overlay needs Chrome/Edge 116+ (Document Picture-in-Picture). Firefox has capture but not this.'); return; }
  try{
    const w=await documentPictureInPicture.requestWindow({width:300,height:300});
    w.document.body.style.cssText='margin:0;background:#0d1015;color:#e7ebf2;font:13px system-ui,Segoe UI,sans-serif';
    const st=w.document.createElement('style');
    st.textContent='#pmeta{color:#98a2b2;font-size:11px;padding:5px 10px}.pteam{padding:5px 10px}.pteam h3{margin:0 0 4px;font-size:10.5px;color:#98a2b2;text-transform:uppercase;letter-spacing:.04em}.slot{display:flex;justify-content:space-between;gap:8px;padding:2px 0;border-top:1px solid #252c37}.slot:first-of-type{border-top:0}.sc{font-variant-numeric:tabular-nums;font-size:11px}.hi{color:#34b877}.mid{color:#d3a02a}.lo{color:#e5624a}';
    w.document.head.appendChild(st);
    w.document.body.innerHTML='<div id="pmeta">live</div><div class="pteam"><h3>Left / blue</h3><div id="poutA"></div></div><div class="pteam"><h3>Right / red</h3><div id="poutB"></div></div>';
    target={A:w.document.getElementById('poutA'), B:w.document.getElementById('poutB'), meta:w.document.getElementById('pmeta')};
    if(!document.getElementById('auto').checked){ document.getElementById('auto').checked=true; document.getElementById('auto').dispatchEvent(new Event('change')); }
    if(boxes.a&&boxes.b&&vid.srcObject) read();
    w.addEventListener('pagehide',()=>{ target={A:document.getElementById('outA'),B:document.getElementById('outB'),meta:document.getElementById('meta')}; });
  }catch(err){ alert('Pop-out failed: '+err); }
}
document.getElementById('pop').onclick=popout;
updateButtons();
</script></body></html>
"""


def main() -> None:
    refs = build_refs()
    if not refs:
        raise SystemExit("no profile-4 refs found — is owscout.sqlite3 present with a trained library?")
    html = (HTML
            .replace("__REFS__", json.dumps(refs))
            .replace("__RW__", str(REF_W)).replace("__RH__", str(REF_H))
            .replace("__LF__", str(LEFT_FRACTION)).replace("__TF__", str(TOP_FRACTION)))
    with open(OUT, "w", encoding="utf-8") as fh:
        fh.write(html)
    n_a = sum(1 for r in refs if r["v"] == "a")
    n_b = sum(1 for r in refs if r["v"] == "b")
    print(f"wrote {OUT}  ({len(refs)} refs: {n_a} blue + {n_b} red, {os.path.getsize(OUT)//1024} KB)")


if __name__ == "__main__":
    main()

"""Browser capture app: renderCaptured() must not crash building the publish
impact preview.

renderCaptured() called `nf(fresh.length)` at the "N unsent maps will publish
comp data for M teams" preview, but `nf` (a number formatter borrowed from
the dashboard's app.js, where it IS defined) was never actually defined
anywhere in docs/capture/index.html - a ReferenceError on every real
Finish + save once there was at least one unpublished captured map with a
named team on either side (i.e. basically always). Because the crash landed
after `#capcount` is set but before the visible list is rebuilt, and
`finishMap()` awaits renderCaptured() with no try/catch, the practical
symptoms were: Finish + save appearing to do nothing (the success toast /
session reset / auto-fetch-next never ran), and the just-saved map being
stuck in IndexedDB - counted, but never rendered, so its delete button
never existed either.
"""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

APP = Path(__file__).resolve().parents[1] / "docs" / "capture" / "index.html"


def _extract(start: str, end: str) -> str:
    html = APP.read_text(encoding="utf-8")
    s = html.index(start)
    e = html.index(end, s) + len(end)
    assert e > s, "extraction anchors moved in index.html"
    return html[s:e]


_ESC = ("function esc(s){return String(s==null?'':s).replace(/[&<>\"']/g,"
        "c=>({'&':'&amp;','<':'&lt;','>':'&gt;','\"':'&quot;',\"'\":'&#39;'}[c]));}")
# Extracted (not hardcoded) so a regression that removes/renames nf() in the
# app is caught here rather than papered over by a test-side stand-in.
_NF = _extract("const nf=(n)=>", "'en-US'));")
_EL = _extract("function el(html){", "return t.content.firstChild; }")
_CAPROW = _extract("function capRow(r, done){", "el.appendChild(rev); return el; }")
_RENDER_CAPTURED = _extract(
    "async function renderCaptured(){",
    "if(done.length){ const d=document.createElement('details'); d.className='pubdone';\n"
    "    d.innerHTML=`<summary class=\"status\">✓ ${done.length} uploaded"
    " — kept so they stay in your published set (re-sent each publish;"
    " editing one re-queues it)</summary>`;\n"
    "    const box=document.createElement('div'); done.forEach(r=>box.appendChild(capRow(r,true)));"
    " d.appendChild(box); host.appendChild(d); } }",
)

_HARNESS = r"""
function fakeEl(){
  return { _children: [], className: '', textContent: '', innerHTML: '', style: {},
    appendChild(c){ this._children.push(c); return c; },
    querySelector(){ return fakeEl(); } };
}
const elements = {};
global.document = {
  getElementById(id){ if(!elements[id]) elements[id]=fakeEl(); return elements[id]; },
  createElement(){ return fakeEl(); },
};
global.savedKeys = new Set();
global.renderWelcome = async ()=>{};
global.idbDel = async ()=>{};
global.syncCodeOptions = ()=>true;
global.refreshCodes = ()=>{};
global.renderReview = ()=>{};
"""

# A fully-populated record exactly as produced by finishMap() for a real map.
_REC = """({
  id:'m1:1', code:'ABCD1', match_id:'m1', game_no:1,
  division:'EMEA Master', map_name:'Circuit Royal', map_category:'Escort', map_guid:'g1',
  side_a_team_id:'t1', side_a_team:'Team A', side_b_team_id:'t2', side_b_team:'Team B',
  winner_side:null, profile:{w:1920,h:1080,hud_variant:'browser'},
  captured_at:new Date().toISOString(), bans:[],
  observations:[{side:'a',ts:0,sub_map:null,round_no:1,phase:'attack',heroes:['g1'],pairs:[['g1',null]]}],
  crops:null,
})"""


def _run() -> dict:
    node = shutil.which("node")
    if not node:
        pytest.skip("node not available to run the capture app's helpers")
    src = (_HARNESS + "\nglobal.idbAll=async()=>[" + _REC + "];\n"
           + _ESC + "\n" + _NF + "\n" + _EL + "\n" + _CAPROW + "\n" + _RENDER_CAPTURED
           + """
renderCaptured().then(()=>{
  console.log(JSON.stringify({
    ok:true,
    capcount: document.getElementById('capcount').textContent,
    children: document.getElementById('caplist')._children.length,
    pubpreview: document.getElementById('pubpreview').innerHTML,
  }));
}).catch(e=>{ console.log(JSON.stringify({ok:false, error:e.message})); });
""")
    proc = subprocess.run([node, "-e", src], capture_output=True, text=True)
    assert proc.returncode == 0, f"node failed:\n{proc.stderr}"
    return json.loads(proc.stdout)


def test_render_captured_does_not_crash_with_an_unpublished_map() -> None:
    out = _run()
    assert out["ok"], out.get("error")
    assert out["capcount"] == 1
    assert out["children"] == 1, (
        "capcount updated but the visible list never got rebuilt - "
        "this is the 'saved but hidden' symptom"
    )


def test_publish_preview_names_the_unsent_map_and_teams() -> None:
    out = _run()
    assert out["ok"], out.get("error")
    assert "Team A" in out["pubpreview"]
    assert "Team B" in out["pubpreview"]


def test_nf_helper_exists_and_formats_numbers() -> None:
    # Direct regression pin for the missing helper itself (borrowed from the
    # dashboard's app.js, where nf already exists and is tested).
    html = APP.read_text(encoding="utf-8")
    assert "const nf=" in html or "function nf(" in html, (
        "nf() is not defined in docs/capture/index.html - renderCaptured()'s "
        "publish preview calls nf(fresh.length) and will throw ReferenceError"
    )

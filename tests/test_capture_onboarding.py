"""Browser capture app onboarding: auto-calibrate preview + first-capture tour.

Extracts the pure state-machine helpers from docs/capture/index.html and runs
them under Node, exactly like the other capture-app tests. Two things this
session changed are pinned here so a future edit can't silently regress them:

- ``autoCalibrate`` now PREVIEWS a placement (confidence + candidate boxes) and
  only commits when the scout clicks "Use these boxes" (``commitCal``). The old
  behaviour committed on sweep; these tests pin the new transition order.
- The guided tour opens at the first incomplete step, walks prev/next, and only
  marks itself done when completed or explicitly dismissed.

The calibrate-preview state machine (autoCalibrate/commitCal/retryCal/
clearCalPreview) later moved into docs/capture/engine/calibration.js (shared
with scrim.html; see tools/capture_divergence.py and that module's own
docstring). This test now loads the REAL module via OWDBCalibration.make(),
same as a page would, instead of splicing extracted function text into the
script - boxesFromStrips/scoreBoxes/calOk/renderCalPreview/drawOverlay/
commitCal/retryCal/clearCalPreview are now internal closures of one make()
instance, so they can no longer be overridden with global stubs the way they
could when they were free-standing page functions. `pendingCal` is instance-
private too (see calibration.js), so these checks now observe only what a
page can observe: DOM state (calhint/calpreview), the persisted `boxes`
global, and the free variables the module still calls out to (readComp,
detectContentRect, selfTest, updateBtns, setStageHint).

The tour mechanism (tourHighlight/tourRender/tourOpen/tourDone/tourNext/
tourPrev/tourTick/maybeShowTour/isFirstVisit) later moved into
docs/capture/engine/tour.js (shared with scrim.html). This test now loads
the REAL module via OWDBTour.make(), same as a page would, instead of
splicing extracted function text into the script - only `tourDefs` (page
copy, not moved) is still extracted from index.html by anchor, and fed in
as `ctx.steps`. `tourManualAt` is instance-private now (see tour.js), so the
"ticker advances past the completed Share step" check below drives that
through a mocked `Date.now()` (simulating the 2.5s manual-nav grace period
elapsing) instead of reaching into module state that's no longer reachable.
`tourIdx` stays a real global here because index.html's own fullscreenchange
handler reads it directly - see tour.js's header.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

APP = Path(__file__).resolve().parents[1] / "docs" / "capture" / "index.html"
ENGINE_CALIBRATION = Path(__file__).resolve().parents[1] / "docs" / "capture" / "engine" / "calibration.js"
ENGINE_TOUR = Path(__file__).resolve().parents[1] / "docs" / "capture" / "engine" / "tour.js"


def _extract(start: str, end: str) -> str:
    html = APP.read_text(encoding="utf-8")
    s = html.index(start)
    e = html.index(end)
    assert e > s, f"extraction anchors moved in index.html: {start!r} / {end!r}"
    return html[s:e]


# A cacheable fake element: every getElementById/querySelector returns a stable
# object with classList/style/innerHTML, so the extracted code can read back the
# side effects it set (panel display, hints, tour titles).
_FAKE_DOM = r"""
function fakeEl(id){ return {
  id, innerHTML:'', textContent:'', style:{}, _cls:new Set(),
  classList:{ add:c=>fakeEl.cache(id)._cls.add(c), remove:c=>fakeEl.cache(id)._cls.delete(c), contains:c=>fakeEl.cache(id)._cls.has(c) },
  querySelector:(sel)=>fakeEl.cache(id+'|'+sel),
  querySelectorAll:()=>[],
  appendChild(){},
  getContext(){ return { getImageData:()=>({data:new Uint8Array(4)}), drawImage(){}, clearRect(){}, strokeRect(){}, beginPath(){}, moveTo(){}, lineTo(){}, stroke(){}, setLineDash(){} }; }
}; }
fakeEl.cache=(id)=>{ if(!fakeEl._c) fakeEl._c={}; if(!fakeEl._c[id]) fakeEl._c[id]=fakeEl(id); return fakeEl._c[id]; };
const el=(id)=>fakeEl.cache(id);
global.document={ getElementById:el, querySelectorAll:()=>[], createElement:()=>fakeEl('created'), addEventListener(){} };
global.localStorage={ _d:{}, getItem(k){ return this._d[k]!==undefined?this._d[k]:null; }, setItem(k,v){ this._d[k]=String(v); }, removeItem(k){ delete this._d[k]; } };
global.getComputedStyle=()=>({ getPropertyValue:()=>'#8087ff' });
global.requestAnimationFrame=()=>0;
"""

# ---------------------------------------------------------------------------
# Calibrate preview state machine
# ---------------------------------------------------------------------------

_CAL_STUBS = _FAKE_DOM + r"""
global.vid={ videoWidth:1920, videoHeight:1080, srcObject:{}, clientWidth:640, clientHeight:360 };
global.boxes={};
global.drawMode=null; global.dragS=null; global.dragC=null;
global.REFS=[];   // empty: skips the sweep, so scoreBoxes (real, needs
                   // ensureWork/cellGrayPadded/bestMatch) never actually runs here.
global.detectContentRect=()=>({x:0,y:0,w:1920,h:1080});
// calOk/renderCalPreview/drawOverlay/commitCal/retryCal/clearCalPreview are
// now internal to the calibration.js instance below, so they can't be
// stubbed - only the free variables the module still calls out to can be.
// readComp backs calOk's "N/10 confident" read; mirror the old calOk stub's
// 9-of-10 result whenever both boxes are present.
global.readComp=(bx)=>{ if(!bx||!bx.a||!bx.b) return null;
  return { a:[{score:0.9},{score:0.9},{score:0.9},{score:0.9},{score:0.9}],
           b:[{score:0.9},{score:0.9},{score:0.9},{score:0.9},{score:0.1}] }; };
global.updateBtns=()=>{ global._update=1; };
global.selfTest=()=>{ global._selftest=1; };
global.setStageHint=()=>{};
global.ov={ width:640, height:360 };
let _strokeRectCalls=0;
global.octx={ strokeStyle:'', lineWidth:0, clearRect(){}, strokeRect(){ _strokeRectCalls++; },
  beginPath(){}, moveTo(){}, lineTo(){}, stroke(){}, setLineDash(){} };
global.css=()=>'#8087ff';
global.scl=()=>1;
"""

_WIRE_CAL = r"""
var module = { exports: {} };
"""

_CAL_BODY = r"""
const results=[];
const check=(name,cond)=>{ results.push({name, ok:!!cond}); };

// boxKeys mirrors index.html's real wiring: this page owns only the two
// portrait boxes, NOT scoreboard/score_readout (scrim.html-only).
const cal=OWDBCalibration.make({ doc:global.document, video:global.vid, ov:global.ov, octx:global.octx, boxKeys:['a','b'] });
const {autoCalibrate, commitCal, retryCal, clearCalPreview, drawOverlay}=cal;

autoCalibrate();
check('preview panel shown', el('calpreview').style.display==='block');
check('hint shows the confidence', el('calhint').innerHTML.indexOf('9/10')>=0);
check('overlay redrawn with candidate boxes', _strokeRectCalls>0);
check('boxes NOT committed by autoCalibrate', global.boxes.a===undefined);

commitCal();
check('boxes committed after confirm', !!global.boxes.a && !!global.boxes.b);
check('boxes persisted', (global.localStorage.getItem('owdb_cap_boxes')||'').indexOf('x')>=0);
check('panel hidden after commit', el('calpreview').style.display==='none');
check('self-test runs after commit', global._selftest===1);

// pendingCal is instance-private now (see calibration.js) - observe that it
// was cleared indirectly: a second commitCal() with no fresh autoCalibrate()
// has nothing pending, so it must be a no-op (boxes unchanged).
const boxesAfterFirstCommit=JSON.stringify(global.boxes);
commitCal();
check('pendingCal cleared after commit (second commit is a no-op)', JSON.stringify(global.boxes)===boxesAfterFirstCommit);

global.vid.srcObject=null;
el('calpreview').style.display='block';
retryCal();
check('retryCal clears preview when no video', el('calpreview').style.display==='none');

el('calpreview').style.display='block';
clearCalPreview();
check('clearCalPreview hides the preview panel', el('calpreview').style.display==='none');

global.vid.videoWidth=0; global.vid.srcObject=null;
const boxesBeforeGuard=JSON.stringify(global.boxes);
autoCalibrate();
check('autoCalibrate guards no-video', el('calhint').innerHTML.indexOf('Share your screen first')>=0);
commitCal();
check('guarded autoCalibrate created no pending candidate', JSON.stringify(global.boxes)===boxesBeforeGuard);

// Regression guard (fix round 1): both pages read the SAME localStorage key
// ('owdb_cap_boxes'), so a scoreboard/score_readout box left behind by a
// scrim.html calibration session in the same browser can still show up in
// this page's `boxes`. ctx.boxKeys=['a','b'] (this page's real wiring) must
// stop drawOverlay from rendering a key it does not own, even though the
// key is present in `boxes`.
global.vid.videoWidth=1920; global.vid.srcObject={};
global.boxes.a={x:1,y:2,w:100,h:20}; global.boxes.b={x:3,y:4,w:100,h:20};
global.boxes.scoreboard={x:5,y:6,w:10,h:10};   // simulated scrim.html leakage
_strokeRectCalls=0;
drawOverlay();
check('drawOverlay does not render a box key this page does not own', _strokeRectCalls===2);
delete global.boxes.scoreboard;

console.log(JSON.stringify(results));
"""


def test_auto_calibrate_previews_before_committing() -> None:
    node = shutil.which("node")
    if not node:
        pytest.skip("node not available to run the capture app's helpers")
    calibration_src = ENGINE_CALIBRATION.read_text(encoding="utf-8")
    src = (
        _CAL_STUBS + "\n" + _WIRE_CAL + "\n" + calibration_src
        + "\nconst OWDBCalibration = module.exports;\n"
        + _CAL_BODY
    )
    proc = subprocess.run([node, "-e", src], capture_output=True, text=True)
    assert proc.returncode == 0, f"node failed:\n{proc.stderr}"
    results = json.loads(proc.stdout)
    failed = [r["name"] for r in results if not r["ok"]]
    assert not failed, f"calibrate-preview checks failed: {failed}"


# ---------------------------------------------------------------------------
# Guided first-capture tour
# ---------------------------------------------------------------------------

# tourDefs is page copy (not moved into tour.js) - extract just that function
# from index.html, same anchor style as before, but now stopping at the
# comment this extraction left right after it instead of the old inline
# mechanism functions (which no longer exist in the page).
_TOUR_DEFS = _extract("function tourDefs(){", "// Mechanism now lives in engine/tour.js")

_TOUR_STUBS = _FAKE_DOM + r"""
global.HAS_CAPTURE=true;
global.vid={ srcObject:null };
global.boxes={};
global.session=null;
global.selectedCode=()=>null;
global.ico=()=>'';
global.toast=()=>{};
global.tourIdx=-1;   // real global on the page (fullscreenchange reads it) - see tour.js header
"""

_WIRE_TOUR = r"""
var module = { exports: {} };
"""

_TOUR_BODY = r"""
const results=[];
const check=(name,cond)=>{ results.push({name, ok:!!cond}); };
const title=()=>el('tour|.tour-title').textContent;

""" + _TOUR_DEFS + r"""

// Real wiring: same ctx shape index.html builds (see that page's own
// OWDBTour.make call) - a saved 'owdb_name' means a returning, already-
// published scout, both for isFirstVisit and for skipping the tour.
const tourInst = OWDBTour.make({ doc: global.document, steps: tourDefs(), tourKey: 'owdb_tour_done',
  firstVisitExtra: () => !(global.localStorage.getItem('owdb_name')||'').trim(),
  skipIf: () => !!(global.localStorage.getItem('owdb_name')||'').trim() });
const { open, next, prev, done, tick, maybeShow } = tourInst;

check('tour has 6 steps', tourDefs().length===6);

open();
check('fresh user opens at Welcome', title().indexOf('capture your first replay')>=0);
check('tour visible + open class', el('tour').style.display==='block' && el('tour')._cls.has('open'));
check('prev arrow hidden on step 1', el('tour|#tourPrev').style.visibility==='hidden');

next();
check('Next -> Share screen', title().indexOf('Share your screen')>=0);
prev();
check('Prev -> back to Welcome', title().indexOf('capture your first replay')>=0);
prev();
check('Prev clamped at first step', title().indexOf('capture your first replay')>=0);

done();   // the Skip / ✕ buttons both call done
check('skipping marks the tour done', global.localStorage.getItem('owdb_tour_done')==='1');
check('tour hidden after skip', el('tour').style.display==='none');

// A returning scout who already published (has a name) is never toured.
global.localStorage.removeItem('owdb_tour_done');
global.localStorage.setItem('owdb_name','ccarn');
maybeShow();
check('returning scout never toured', el('tour').style.display==='none');
global.localStorage.removeItem('owdb_name');

// Calibrated-but-not-published: after clicking Start the ticker walks past the
// completed Share step on its own (one advance per tick — grace notwithstanding).
// tourManualAt (the debounce timestamp) is instance-private in tour.js now, so
// this drives the SAME real behaviour through a mocked Date.now() instead of
// reaching into module state - if the grace period stopped elapsing (or
// tick() stopped checking it), this would go red exactly like the old
// direct-reset version did.
global.localStorage.removeItem('owdb_tour_done');
global.boxes={a:{},b:{}}; global.vid.srcObject={};
open();
next();          // click Start on Welcome
const realNow=Date.now;
Date.now=()=>realNow()+3000;   // simulate >2.5s passing so the manual-nav grace elapses
tick();
Date.now=realNow;
check('ticker advances past completed Share step', title().indexOf('Auto-calibrate')>=0);

console.log(JSON.stringify(results));
"""


def test_tour_opens_resumes_and_dismisses() -> None:
    node = shutil.which("node")
    if not node:
        pytest.skip("node not available to run the capture app's helpers")
    tour_src = ENGINE_TOUR.read_text(encoding="utf-8")
    src = (
        _TOUR_STUBS + "\n" + _WIRE_TOUR + "\n" + tour_src
        + "\nconst OWDBTour = module.exports;\n"
        + _TOUR_BODY
    )
    proc = subprocess.run([node, "-e", src], capture_output=True, text=True)
    assert proc.returncode == 0, f"node failed:\n{proc.stderr}"
    results = json.loads(proc.stdout)
    failed = [r["name"] for r in results if not r["ok"]]
    assert not failed, f"tour checks failed: {failed}"

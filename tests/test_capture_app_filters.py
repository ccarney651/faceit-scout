"""The browser capture app's region/division picker (docs/capture/index.html).

This exists because of a real regression. `tools/build_capture_data.py` started
emitting region-qualified divisions ("EMEA Master") when NA was unlocked, while
the app still rendered a hardcoded ``Region: EMEA`` label beside a Division
dropdown fed straight from that list — so it read "Region EMEA / Division NA
Master", and the two controls contradicted each other.

The app is a single static HTML file with no build step, so the functions are
extracted from it and executed under Node against a stub DOM. Compiling the
SHIPPED source is the point: a transcribed copy would drift from it silently,
which is exactly how the bug got out.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

APP = Path(__file__).resolve().parents[1] / "docs" / "capture" / "index.html"

# Enough of a feed to cover the collision: two regions, a tier in one that the
# other does not have, and a championship carrying no region at all.
FEED = {
    "regions": ["EMEA", "NA"],
    "divisions": ["EMEA Master", "EMEA Expert", "EMEA Advanced", "NA Master", "NA Expert"],
    "codes": [
        {"code": "EM1", "division": "EMEA Master"},
        {"code": "EE1", "division": "EMEA Expert"},
        {"code": "EA1", "division": "EMEA Advanced"},
        {"code": "NM1", "division": "NA Master"},
        {"code": "NE1", "division": "NA Expert"},
        {"code": "NE2", "division": "NA Expert"},
    ],
}

# Stub DOM covering only what the picker functions touch, plus the harness that
# pulls them out of the app. Kept in one place so the tests below read as checks.
HARNESS = r"""
const fs=require('fs');
// Via env, not argv: `node -e` shifts argv (there is no script path), which is
// easy to get subtly wrong.
const html=fs.readFileSync(process.env.CAPTURE_APP,'utf8');
const DATA=JSON.parse(process.env.CAPTURE_FEED);
function makeSelect(){ return { _opts:[], value:'',
  get options(){ return this._opts; },
  set innerHTML(h){
    this._opts=[...h.matchAll(/<option(?:\s+value="([^"]*)")?[^>]*>([^<]*)<\/option>/g)]
      .map(m=>({value:m[1]!==undefined?m[1]:m[2], text:m[2]}));
    const sel=[...h.matchAll(/<option[^>]*\sselected[^>]*>([^<]*)</g)].map(m=>m[1]);
    if(sel.length) this.value=sel[0];
    else if(!this._opts.some(o=>o.value===this.value)) this.value=this._opts.length?this._opts[0].value:'';
  } }; }
const els={reg:makeSelect(), div:makeSelect()};
const document={getElementById:id=>els[id]};
// One contiguous block in the app, ending just before codeKey().
const a=html.indexOf('function splitDiv('), b=html.indexOf('function codeKey(');
if(a<0||b<0||b<a) throw new Error('extraction anchors moved in index.html');
const names=['splitDiv','buildRegions','buildDivisions','wantedDivision','inRegion','divFilter'];
for(const n of names) if(!new RegExp('function '+n+'\\(').test(html.slice(a,b)))
  throw new Error('missing '+n);
// Compiled in its own scope so the extracted declarations cannot collide with
// this harness's bindings. Input is the repo's own committed file.
const F=new Function('DATA','document',html.slice(a,b)+'\nreturn {'+names.join(',')+'};')(DATA,document);
const out={};
%s
console.log(JSON.stringify(out));
"""


def _run(body: str) -> dict:
    node = shutil.which("node")
    if not node:
        pytest.skip("node not available to run the capture app's helpers")
    proc = subprocess.run(
        [node, "-e", HARNESS % body], capture_output=True, text=True,
        env={**os.environ, "CAPTURE_APP": str(APP), "CAPTURE_FEED": json.dumps(FEED)})
    assert proc.returncode == 0, f"node failed:\n{proc.stderr}"
    return json.loads(proc.stdout)


def test_region_and_division_split_out_of_the_qualified_label() -> None:
    got = _run("""
      out.master=F.splitDiv('EMEA Master');
      out.naexp=F.splitDiv('NA Expert');
      out.cup=F.splitDiv('Winter Invitational');
    """)
    assert got["master"] == {"region": "EMEA", "tier": "Master"}
    assert got["naexp"] == {"region": "NA", "tier": "Expert"}
    # No region in the name -> no region, rather than a guess.
    assert got["cup"] == {"region": None, "tier": "Winter Invitational"}


def test_division_list_offers_only_the_selected_regions_tiers() -> None:
    """NA has no Advanced division. Offering it would produce an always-empty
    filter that looks like missing data."""
    got = _run("""
      F.buildRegions(); out.regions=els.reg.options.map(o=>o.value);
      F.buildDivisions(); out.emea=els.div.options.map(o=>o.value);
      els.reg.value='NA'; F.buildDivisions(); out.na=els.div.options.map(o=>o.value);
    """)
    assert got["regions"] == ["EMEA", "NA"]
    assert got["emea"] == ["all", "Master", "Expert", "Advanced"]
    assert got["na"] == ["all", "Master", "Expert"]


def test_switching_region_clears_a_tier_the_new_region_lacks() -> None:
    """EMEA Advanced -> NA must not leave 'Advanced' selected; that would filter
    every code away and read as "no replays available"."""
    got = _run("""
      F.buildRegions(); F.buildDivisions(); els.div.value='Advanced';
      els.reg.value='NA'; F.buildDivisions();
      out.div=els.div.value;
      out.n=F.divFilter(DATA.codes).length;
    """)
    assert got["div"] == "all"
    assert got["n"] == 3          # every NA code, not zero


def test_a_tier_never_mixes_the_two_regions() -> None:
    """The regression this file exists for: picking Master must not merge EMEA
    Master and NA Master into one list."""
    got = _run("""
      F.buildRegions(); F.buildDivisions(); els.div.value='Master';
      out.emea=[...new Set(F.divFilter(DATA.codes).map(c=>c.division))];
      els.reg.value='NA'; F.buildDivisions(); els.div.value='Master';
      out.na=[...new Set(F.divFilter(DATA.codes).map(c=>c.division))];
    """)
    assert got["emea"] == ["EMEA Master"]
    assert got["na"] == ["NA Master"]


def test_all_within_a_region_stays_inside_that_region() -> None:
    """'all' means every tier of the CHOSEN region, never every region."""
    got = _run("""
      F.buildRegions(); F.buildDivisions(); els.div.value='all';
      out.want=F.wantedDivision();
      out.emea=[...new Set(F.divFilter(DATA.codes).map(c=>F.splitDiv(c.division).region))];
      els.reg.value='NA'; F.buildDivisions();
      out.na=[...new Set(F.divFilter(DATA.codes).map(c=>F.splitDiv(c.division).region))];
    """)
    assert got["want"] is None
    assert got["emea"] == ["EMEA"]
    assert got["na"] == ["NA"]

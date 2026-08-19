"""Parity between the two implementations of the comp analysis.

The dashboard computes its aggregations in Python at export time; `scrims.html`
must compute in the browser at read time, because scrim data is local and
private and never reaches a build step. So the same analysis genuinely exists
twice, and the design (`specs/2026-08-12-scrim-mode-design.md` §8.1) is explicit
that the fix is not to share the implementation but to **stop the two from
drifting**: define each aggregation once, implement it in both, and assert they
agree over a shared fixture.

This is that assertion. The JS half was hand-ported from `owdb/analysis.py`,
which is exactly the kind of port that rots silently — a threshold nudged on one
side and the scrim page quietly starts disagreeing with the Scout pages about
what a comp even is.

WHAT IS NOT PARITY-TESTED, and why:

* `aggregate_swaps`. The league pipeline confirms a swap through **player
  identity** (`confirmed_swap_events`), so a substitution is never misreported
  as a tactical swap. Scrim capture cannot do that yet — HUD name reading is
  unreliable, design phase 2b — so the JS uses a hero-set difference. The two
  take different inputs and are deliberately different functions; asserting they
  agree would either be vacuous or force the scrim side to fake player data.
  The trigger-selection rule they DO share (majority threshold with baseline
  subtraction) is covered in tests/test_scrims_viewer.py.

* `cluster_comps` win/loss counting. Python builds one instance per game, so
  wins-per-instance and wins-per-map are the same number. The JS builds one
  instance per *segment* — a comp opened on both halves of an Escort map is two
  samples — so it counts W-L over distinct maps instead, or one won map would
  report 2-0. The fixture below therefore feeds one instance per map, the
  granularity where the two are directly comparable, and the segment rule has
  its own test in tests/test_scrims_viewer.py.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from owdb.analysis import CompInstance, classify_transition, cluster_comps, same_comp

APP = Path(__file__).resolve().parents[1] / "docs" / "scrims.html"

# Roles are case-insensitive on both sides; the viewer stores them capitalised
# and Python lowercases before comparing, so this exercises that too.
ROLES = {
    "T1": "Tank", "T2": "Tank",
    "D1": "Damage", "D2": "Damage", "D3": "Damage", "D4": "Damage",
    "S1": "Support", "S2": "Support", "S3": "Support", "S4": "Support",
}

# Lineups chosen for the boundaries of the comp-family relation, not for realism:
# exactly-4 shared, exactly-3 with the same tank, exactly-3 with a different
# tank, tank-only overlap, and a tankless lineup that has no anchor at all.
L = {
    "base":        ["T1", "D1", "D2", "S1", "S2"],
    "one_off":     ["T1", "D1", "D2", "S1", "S3"],   # 4 shared with base
    "three_tank":  ["T1", "D1", "D2", "S3", "S4"],   # 3 shared, same tank
    "three_swap":  ["T2", "D1", "D2", "S3", "S4"],   # 3 shared, tank differs
    "tank_only":   ["T1", "D3", "D4", "S3", "S4"],   # 1 shared
    "other_tank":  ["T2", "D3", "D4", "S3", "S4"],
    "tankless":    ["D1", "D2", "D3", "S1", "S2"],   # no tank to anchor on
    "two_tanks":   ["T1", "T2", "D1", "S1", "S2"],   # off-meta, but capturable
}
NAMES = sorted(L)


def _pure_js() -> str:
    html = APP.read_text(encoding="utf-8")
    start = html.index("const SCRIM_MODES")
    end = html.index("// ---------- opponent registry ----------")
    return html[start:end]


def _js(body: str) -> object:
    node = shutil.which("node")
    if not node:
        pytest.skip("node not available to run the viewer's analysis")
    src = _pure_js() + "\nconsole.log(JSON.stringify((()=>{" + body + "})()));"
    proc = subprocess.run([node, "-e", src], capture_output=True, text=True)
    assert proc.returncode == 0, f"node failed:\n{proc.stderr}"
    return json.loads(proc.stdout)


R = json.dumps(ROLES)
LJ = json.dumps(L)


def test_the_same_comp_relation_agrees_over_every_pair() -> None:
    """The relation the whole analysis rests on. If these two ever disagree, the
    scrim page and the Scout pages mean different things by "the same comp"."""
    got = _js(f"""
      const L = {LJ}, names = {json.dumps(NAMES)}, out = {{}};
      for(const a of names) for(const b of names)
        out[a+'|'+b] = sameComp(L[a].slice().sort(), L[b].slice().sort(), {R});
      return out;
    """)
    want = {
        f"{a}|{b}": same_comp(sorted(L[a]), sorted(L[b]), ROLES)
        for a in NAMES for b in NAMES
    }
    disagree = {k: (want[k], got[k]) for k in want if want[k] != got[k]}
    assert not disagree, f"python vs js (expected, got): {disagree}"


def test_the_relation_is_actually_exercised_by_the_fixture() -> None:
    """A fixture where every pair answers the same way would make the test above
    pass while proving nothing."""
    vals = {same_comp(sorted(L[a]), sorted(L[b]), ROLES) for a in NAMES for b in NAMES}
    assert vals == {True, False}, "the fixture does not span both outcomes"


def test_swap_classification_agrees() -> None:
    """flex (still the same comp) vs core (a genuinely different one) is the
    distinction that makes a swap worth reading, so both sides must draw it in
    the same place."""
    pairs = [(a, b) for a in NAMES for b in NAMES if a != b]
    got = _js(f"""
      const L = {LJ}, pairs = {json.dumps(pairs)}, out = {{}};
      for(const [a,b] of pairs){{
        const prev = L[a].slice().sort(), curr = L[b].slice().sort();
        out[a+'|'+b] = sameComp(prev, curr, {R}) ? 'flex' : 'core';
      }}
      return out;
    """)
    want = {
        f"{a}|{b}": classify_transition(sorted(L[a]), sorted(L[b]), ROLES).kind
        for a, b in pairs
    }
    disagree = {k: (want[k], got[k]) for k in want if want[k] != got[k]}
    assert not disagree, f"python vs js (expected, got): {disagree}"


# One instance per map, so the two implementations' W-L counting coincides (see
# the module docstring). Frequencies are uneven on purpose: clustering is greedy
# and anchored on the most-played lineup, so a fixture with flat frequencies
# would never exercise the anchoring order.
INSTANCES: list[tuple[str, bool, str]] = [
    ("base", True, "m1"), ("base", True, "m2"), ("base", False, "m3"),
    ("one_off", True, "m4"), ("one_off", False, "m5"),
    ("three_tank", False, "m6"),
    ("three_swap", True, "m7"), ("three_swap", True, "m8"),
    ("tank_only", False, "m9"),
    ("other_tank", True, "m10"),
    ("tankless", False, "m11"), ("tankless", True, "m12"),
    ("two_tanks", True, "m13"),
]


def _js_families() -> list[dict]:
    js_insts = json.dumps([
        {"heroes": sorted(L[name]), "mapKey": key, "result": "win" if won else "loss"}
        for name, won, key in INSTANCES
    ])
    return _js(f"return clusterComps({js_insts}, {R});")


def _py_families() -> list:
    return cluster_comps(
        [CompInstance(heroes=tuple(sorted(L[n])), won=w, map_key=k)
         for n, w, k in INSTANCES],
        ROLES,
    )


def test_clustering_produces_the_same_families_in_the_same_order() -> None:
    """Greedy clustering means the ORDER matters: the most-frequent lineup
    anchors a family and absorbs what matches it, so a different anchoring order
    produces different families from identical data."""
    js, py = _js_families(), _py_families()
    assert [f["heroes"] for f in js] == [f.heroes for f in py]


def test_clustering_agrees_on_membership_and_counts() -> None:
    js, py = _js_families(), _py_families()
    assert len(js) == len(py), f"{len(js)} families in js, {len(py)} in python"
    for j, p in zip(js, py, strict=True):
        assert j["heroes"] == p.heroes
        assert sorted(tuple(v) for v in j["variants"]) == sorted(p.variants), (
            f"different lineups folded into {p.heroes}"
        )
        assert j["samples"] == p.samples, f"samples differ for {p.heroes}"
        assert j["maps"] == p.maps, f"map count differs for {p.heroes}"
        assert (j["wins"], j["losses"]) == (p.wins, p.losses), (
            f"record differs for {p.heroes}"
        )


def test_the_fixture_actually_folds_lineups_together() -> None:
    """If every lineup were its own family, the parity above would only be
    checking that neither side clusters at all."""
    py = _py_families()
    assert any(len(f.variants) > 1 for f in py), "no family absorbed a variant"
    assert len(py) > 1, "everything collapsed into one family"

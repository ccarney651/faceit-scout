"""Browser capture app: the published per-observation shape.

`ingame_names` carries the raw OCR HUD read behind each slot. Without it a
capture is frozen at whatever this build's attribute() could resolve (~73% of
slots; the rest publish as a permanent null), because the text that failed to
match is discarded at capture time. Storing it makes a future battletag ->
FACEIT matcher re-runnable over already-published captures.

The rule these tests exist to pin is ALIGNMENT: empty hero slots are dropped
from the published arrays, so `heroes`, `pairs` and `ingame_names` must be
appended under the same skip or index i stops meaning the same slot in each -
which would silently attribute a hero to the wrong player's name.
"""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

APP = Path(__file__).resolve().parents[1] / "docs" / "capture" / "index.html"


def _pure_js() -> str:
    html = APP.read_text(encoding="utf-8")
    start = html.index(
        "function buildObservations(snaps, players, playersRaw, phased, playersConf){")
    end = html.index("\n}", start) + len("\n}")
    assert end > start, "extraction anchors moved in index.html"
    return html[start:end]


def _run(body: str) -> object:
    node = shutil.which("node")
    if not node:
        pytest.skip("node not available to run the capture app's helpers")
    src = _pure_js() + "\nconsole.log(JSON.stringify((()=>{" + body + "})()));"
    proc = subprocess.run([node, "-e", src], capture_output=True, text=True)
    assert proc.returncode == 0, f"node failed:\n{proc.stderr}"
    return json.loads(proc.stdout)


# One snapshot, five heroes a side, nothing missing.
_FULL = ("[{round:1,sub:null,attacker:'a',ts:0,"
         "a:['ga1','ga2','ga3','ga4','ga5'],b:['gb1','gb2','gb3','gb4','gb5']}]")
_PLAYERS = "{a:['p1','p2','p3','p4','p5'],b:['q1','q2','q3','q4','q5']}"
_RAW = ("{a:['Dip','aes','gogo','zorrow','beni'],"
        "b:['Rx','Ty','Uz','Vw','Xq']}")


def test_raw_hud_reads_are_published_alongside_the_ids() -> None:
    got = _run(f"return buildObservations({_FULL},{_PLAYERS},{_RAW},false);")
    assert got[0]["ingame_names"] == ["Dip", "aes", "gogo", "zorrow", "beni"]
    assert got[1]["ingame_names"] == ["Rx", "Ty", "Uz", "Vw", "Xq"]


def test_a_slot_the_matcher_could_not_resolve_still_keeps_its_read() -> None:
    # This is the whole point: id is null (attribute() gave up) but the text
    # that produced that null survives, so a better matcher can retry offline.
    players = "{a:['p1',null,'p3','p4','p5'],b:[]}"
    got = _run(f"return buildObservations({_FULL},{players},{_RAW},false);")
    assert got[0]["pairs"][1] == ["ga2", None]
    assert got[0]["ingame_names"][1] == "aes"


def test_empty_hero_slots_are_dropped_from_all_three_arrays_together() -> None:
    # Slots 1 and 3 have no hero read. Dropping them from `heroes`/`pairs` but
    # not `ingame_names` would shift every later name onto the wrong hero.
    snaps = ("[{round:1,sub:null,attacker:'a',ts:0,"
             "a:['ga1',null,'ga3',null,'ga5'],b:[]}]")
    got = _run(f"return buildObservations({snaps},{_PLAYERS},{_RAW},false);")
    obs = got[0]
    assert obs["heroes"] == ["ga1", "ga3", "ga5"]
    assert obs["pairs"] == [["ga1", "p1"], ["ga3", "p3"], ["ga5", "p5"]]
    assert obs["ingame_names"] == ["Dip", "gogo", "beni"]
    assert len(obs["heroes"]) == len(obs["pairs"]) == len(obs["ingame_names"])


def test_no_ocr_reads_at_all_publishes_nulls_not_a_short_array() -> None:
    # Sides set by hand, auto-detect never run. The array must still be
    # slot-aligned so consumers can index it without a length check.
    got = _run(f"return buildObservations({_FULL},{_PLAYERS},null,false);")
    assert got[0]["ingame_names"] == [None] * 5


def test_an_empty_read_is_normalised_to_null() -> None:
    # OCR returns '' for an unreadable cell; publishing the empty string would
    # make "we read nothing" indistinguishable from a real one-character name.
    raw = "{a:['Dip','','gogo','',''],b:[]}"
    got = _run(f"return buildObservations({_FULL},{_PLAYERS},{raw},false);")
    assert got[0]["ingame_names"] == ["Dip", None, "gogo", None, None]


def test_pairs_keep_their_two_tuple_arity() -> None:
    # owdb/contribute.py and tools/audit_capture_sides.py read pair[1] as the
    # player id positionally - the raw name goes in a parallel array, never as
    # a third element, or every existing consumer misreads it.
    got = _run(f"return buildObservations({_FULL},{_PLAYERS},{_RAW},false);")
    assert all(len(p) == 2 for o in got for p in o["pairs"])


def test_player_conf_follows_the_same_skip_as_every_other_array() -> None:
    """`player_conf` records HOW a slot was assigned ('forced' from the role
    constraint alone, 'matched' on name evidence, null = abstained). It is a
    fourth parallel array, so it must be dropped under the same skip as the rest
    or a 'forced' tag lands on the wrong hero."""
    gappy = ("[{round:1,sub:null,attacker:'a',ts:0,"
             "a:['ga1',null,'ga3',null,'ga5'],b:['gb1','gb2','gb3','gb4','gb5']}]")
    conf = ("{a:['forced',null,'matched',null,'matched'],"
            "b:[null,null,null,null,null]}")
    obs = _run(f"return buildObservations({gappy},{_PLAYERS},{_RAW},false,{conf})")[0]
    assert obs["player_conf"] == ["forced", "matched", "matched"]
    assert len(obs["heroes"]) == len(obs["pairs"]) == len(obs["ingame_names"]) \
        == len(obs["player_conf"])


def test_a_capture_with_no_confidence_data_still_publishes_nulls() -> None:
    """An older session object (or the greedy fallback path) passes nothing."""
    got = _run(f"return buildObservations({_FULL},{_PLAYERS},{_RAW},false);")
    assert got[0]["player_conf"] == [None] * 5


def test_the_rest_of_the_observation_shape_is_unchanged() -> None:
    got = _run(f"return buildObservations({_FULL},{_PLAYERS},{_RAW},true);")
    assert set(got[0]) == {"side", "ts", "sub_map", "round_no", "phase",
                           "heroes", "pairs", "ingame_names", "player_conf"}
    assert (got[0]["side"], got[0]["phase"]) == ("a", "attack")
    assert (got[1]["side"], got[1]["phase"]) == ("b", "defend")
    # Unphased maps (Control/Push) carry no attack/defend at all.
    unphased = _run(f"return buildObservations({_FULL},{_PLAYERS},{_RAW},false);")
    assert unphased[0]["phase"] is None

"""detectStrips locates the portrait strips from the HUD's own structure.

WHY THIS EXISTS. Auto-calibrate used to place the boxes at fixed fractions of
the frame, measured once off a 1440p capture. That cannot survive a change of
display mode: the HUD scales with the game's CONTENT height, and a title bar
takes 29px of it away, so borderless tiles are ~7% larger than windowed ones on
the same monitor. Measured 2026-09-07 over four configurations of one replay,
the fixed-fraction sweep read 10/10 on the configuration it was fitted to and
4-6/10 on the other three.

detectStrips keys on the one thing common to all of them: five team-coloured
tiles at a constant pitch. The pitch IS the scale, so nothing about the frame's
resolution, aspect or display mode has to be assumed.

These tests drive the REAL docs/capture/engine/calibration.js through node over
synthetic pixels. Synthetic because screenshots/ is gitignored and a fresh clone
has no frames; the real frames are measured separately by
tools/real_frame_eval/strip_detect_parity.py, which feeds the same function the
same kind of byte array (10/10 on all six real capture frames as of 2026-09-07).
"""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

ENGINE_CALIBRATION = (
    Path(__file__).resolve().parents[1] / "docs" / "capture" / "engine" / "calibration.js"
)

# A synthetic observer HUD: five team-coloured tiles per side at a fixed pitch,
# on a desaturated background the colour tests ignore. The decoy bar is the
# centre objective bar, which is the same blue as the left team and is what
# broke an earlier attempt that measured the band's horizontal EXTENT instead of
# its run STARTS (it blew the width out to 945-1199 against a true 659).
_HARNESS = r"""
var module = { exports: {} };
%(SRC)s
const Mod = module.exports;
const cal = Mod.make({
  doc: { getElementById: () => null, createElement: () => ({ getContext: () => ({}) }) },
  video: { videoWidth: 0, videoHeight: 0 },
  ov: { width: 0, height: 0 }, octx: {}, boxKeys: ['a', 'b'],
});

function frame(opts) {
  const W = opts.W, H = opts.H;
  const d = new Uint8ClampedArray(W * H * 4);
  for (let i = 0; i < W * H; i++) {            // flat, desaturated background
    d[i*4] = 60; d[i*4+1] = 62; d[i*4+2] = 64; d[i*4+3] = 255;
  }
  const paint = (x0, x1, y0, y1, c) => {
    for (let y = y0; y <= y1; y++) {
      for (let x = Math.max(0, x0); x <= Math.min(W - 1, x1); x++) {
        const i = (y * W + x) * 4;
        d[i] = c[0]; d[i+1] = c[1]; d[i+2] = c[2];
      }
    }
  };
  const BLUE = opts.ca || [40, 120, 220], RED = opts.cb || [220, 60, 60];
  const tw = Math.round(opts.pitch * 0.53);
  for (let k = 0; k < 5; k++) {
    if (opts.left !== false) {
      const x = Math.round(opts.ax + k * opts.pitch);
      paint(x, x + tw, opts.y0, opts.y1, BLUE);
    }
    if (opts.right !== false) {
      const x = Math.round(opts.bx + k * opts.pitch);
      paint(x, x + tw, opts.y0, opts.y1, RED);
    }
  }
  if (opts.decoy) paint(opts.decoy[0], opts.decoy[1], opts.y0, opts.y1, BLUE);
  return { data: d, W: W, H: H };
}

const cases = JSON.parse(process.argv[2]);
const out = {};
for (const [name, opts] of Object.entries(cases)) {
  const f = frame(opts);
  out[name] = {
    fixed: cal.detectStrips(f.data, f.W, f.H),
    swept: cal.detectStripsByHue(f.data, f.W, f.H),
  };
}
console.log(JSON.stringify(out));
"""

# 1440p borderless geometry, measured: band rows 98..147, pitch 141.5, left
# strip starting at x=53. `windowed` is the same HUD one display mode away -
# the case the fixed-fraction sweep could not reach.
CASES = {
    "borderless": dict(W=2560, H=432, y0=98, y1=147, pitch=141.5, ax=56, bx=1804,
                       decoy=[1000, 1270]),
    "windowed": dict(W=2560, H=432, y0=120, y1=167, pitch=132.5, ax=132, bx=1772,
                     decoy=[1010, 1280]),
    "smaller_display": dict(W=1920, H=324, y0=74, y1=110, pitch=106.0, ax=42, bx=1353),
    "no_band": dict(W=2560, H=432, y0=0, y1=0, pitch=141.5, ax=56, bx=1804,
                    left=False, right=False),
    "one_side_only": dict(W=2560, H=432, y0=98, y1=147, pitch=141.5, ax=56, bx=1804,
                          right=False),
    # OW's accessibility options recolour the team and enemy UI. The structure
    # is identical; only the hue moves.
    "purple_gold": dict(W=2560, H=432, y0=98, y1=147, pitch=141.5, ax=56, bx=1804,
                        decoy=[1000, 1270], ca=[150, 70, 230], cb=[230, 180, 40]),
    "green_teal": dict(W=2560, H=432, y0=120, y1=167, pitch=132.5, ax=132, bx=1772,
                       ca=[60, 200, 70], cb=[230, 90, 200]),
    # The palette the operator was actually running on 2026-09-08: orange (hue
    # bin 1, 15 deg) against lime (bin 4, 60 deg). FORTY-FIVE degrees apart,
    # and both warm - the case that broke the first cut of the sweep, which
    # demanded 60 degrees and threw the true pair away unscored.
    "operator_orange_lime": dict(W=2560, H=432, y0=98, y1=147, pitch=141.5,
                                 ax=56, bx=1804, decoy=[1000, 1270],
                                 ca=[230, 92, 46], cb=[230, 230, 46]),
    # Tighter than any palette OW offers, as a margin check: measured, the
    # sweep still resolves teams 10 degrees apart.
    "near_identical_hues": dict(W=2560, H=432, y0=98, y1=147, pitch=141.5,
                                ax=56, bx=1804,
                                ca=[230, 130, 46], cb=[230, 176, 46]),
}


@pytest.fixture(scope="module")
def raw() -> dict:
    node = shutil.which("node")
    if not node:
        pytest.skip("node not available to run the capture app's helpers")
    src = _HARNESS % {"SRC": ENGINE_CALIBRATION.read_text(encoding="utf-8")}
    script = Path(__file__).resolve().parent / "_tmp_strip_detect_check.js"
    script.write_text(src, encoding="utf-8")
    try:
        proc = subprocess.run([node, str(script), json.dumps(CASES)],
                              capture_output=True, text=True)
    finally:
        script.unlink(missing_ok=True)
    assert proc.returncode == 0, f"node failed:\n{proc.stderr}"
    return json.loads(proc.stdout)


@pytest.fixture(scope="module")
def detected(raw: dict) -> dict:
    """Stage 1 - the default blue/red palette."""
    return {k: v["fixed"] for k, v in raw.items()}


@pytest.fixture(scope="module")
def swept(raw: dict) -> dict:
    """Stage 2 - team colours swept, best palette first."""
    return {k: v["swept"] for k, v in raw.items()}


def test_finds_the_band_and_pitch(detected: dict) -> None:
    d = detected["borderless"]
    assert d is not None
    assert d["pitch"] == pytest.approx(141.5, abs=1.0)
    assert d["bandTop"] == 98


def test_strip_width_is_five_tiles(detected: dict) -> None:
    """w comes from the measured pitch, not from a table - this is the whole
    point: the fixed fractions could translate a box but never resize it."""
    d = detected["borderless"]
    assert d["a"]["w"] == pytest.approx(5 * d["pitch"], abs=0.01)
    assert d["b"]["w"] == pytest.approx(5 * d["pitch"], abs=0.01)


def test_lands_on_the_tiles(detected: dict) -> None:
    d = detected["borderless"]
    assert d["a"]["x"] == pytest.approx(53.3, abs=3)
    assert d["b"]["x"] == pytest.approx(1801.3, abs=3)
    assert d["a"]["y"] == 98


def test_the_centre_objective_bar_is_not_mistaken_for_a_tile(detected: dict) -> None:
    """The decoy is the same blue and sits in the same rows as the left strip.
    Only the five evenly spaced runs may win."""
    d = detected["borderless"]
    assert d["a"]["x"] + d["a"]["w"] < 1000


def test_tracks_a_change_of_display_mode(detected: dict) -> None:
    """Same monitor, same resolution, 7% smaller HUD - borderless vs windowed.
    A fixed fraction reads one of these and misses the other."""
    bl, win = detected["borderless"], detected["windowed"]
    assert win["pitch"] < bl["pitch"]
    assert win["pitch"] == pytest.approx(132.5, abs=1.0)
    assert win["bandTop"] == 120
    assert win["a"]["x"] == pytest.approx(129.5, abs=3)


def test_scales_to_a_different_resolution(detected: dict) -> None:
    d = detected["smaller_display"]
    assert d is not None
    assert d["pitch"] == pytest.approx(106.0, abs=1.0)
    assert d["a"]["w"] == pytest.approx(530, abs=6)


def test_strip_height_follows_width(detected: dict) -> None:
    """h is w times the strip's own aspect ratio, so it resizes with the HUD."""
    for name in ("borderless", "windowed", "smaller_display"):
        d = detected[name]
        for side in ("a", "b"):
            assert d[side]["h"] == pytest.approx(d[side]["w"] * (0.147 if side == "a" else 0.154),
                                                 rel=0.02)


def test_refuses_when_there_is_no_band(detected: dict) -> None:
    """Honest failure matters more than a number: the old sweep reported
    '9/10 portraits confident' over a placement where every row was wrong."""
    assert detected["no_band"] is None


def test_refuses_when_only_one_team_is_visible(detected: dict) -> None:
    """The band is the rows where BOTH halves carry team colour. A one-sided
    test called the band 18px too tall on a real frame, which is four times the
    matcher's tolerance."""
    assert detected["one_side_only"] is None


# --------------------------------------------------------- custom palettes


def test_a_recoloured_hud_defeats_the_fixed_palette(detected: dict) -> None:
    """The premise of stage 2: keying on blue and red finds nothing at all for
    a player running OW's accessibility colours."""
    assert detected["purple_gold"] is None
    assert detected["green_teal"] is None


def test_the_sweep_finds_a_recoloured_hud(swept: dict) -> None:
    got = swept["purple_gold"]
    assert got, "no palette proposed for a purple/gold HUD"
    top = got[0]
    assert top["pitch"] == pytest.approx(141.5, abs=1.0)
    assert top["bandTop"] == 98
    assert top["a"]["x"] == pytest.approx(53.3, abs=3)
    assert top["b"]["x"] == pytest.approx(1801.3, abs=3)


def test_the_sweep_handles_a_second_palette_and_pitch(swept: dict) -> None:
    got = swept["green_teal"]
    assert got, "no palette proposed for a green/magenta HUD"
    top = got[0]
    assert top["pitch"] == pytest.approx(132.5, abs=1.0)
    assert top["bandTop"] == 120
    assert top["a"]["x"] == pytest.approx(129.5, abs=3)


def test_the_sweep_still_reads_the_default_palette(swept: dict) -> None:
    """Stage 2 is a fallback, not a replacement - but it must not be blind to
    the colours stage 1 handles, or a partial stage-1 read could not improve."""
    got = swept["borderless"]
    assert got
    assert got[0]["pitch"] == pytest.approx(141.5, abs=1.0)


def test_the_sweep_refuses_a_frame_with_no_band(swept: dict) -> None:
    assert swept["no_band"] == []


def test_the_palette_the_operator_was_running(swept: dict) -> None:
    """Regression for 2026-09-08: orange vs lime, 45 degrees apart. Both warm,
    both close, and the first cut of the sweep required 60 degrees of
    separation - so it discarded the true palette before scoring it and
    auto-calibrate fell through to the sweep and read 2/10 in the field."""
    got = swept["operator_orange_lime"]
    assert got, "no palette proposed for orange vs lime"
    top = got[0]
    assert top["pitch"] == pytest.approx(141.5, abs=1.0)
    assert top["bandTop"] == 98
    assert top["a"]["x"] == pytest.approx(53.3, abs=3)
    assert top["b"]["x"] == pytest.approx(1801.3, abs=3)


def test_resolves_teams_only_ten_degrees_apart(swept: dict) -> None:
    """Margin over anything OW can be set to. Two hue windows need only be
    non-overlapping, which is two bins - 30 degrees - so this is the floor."""
    got = swept["near_identical_hues"]
    assert got
    assert got[0]["a"]["x"] == pytest.approx(53.3, abs=3)
    assert got[0]["b"]["x"] == pytest.approx(1801.3, abs=3)


def test_a_fragmented_band_is_still_one_band(swept: dict) -> None:
    """A tile is team-coloured at its header and name plate but not across the
    portrait art in between, so the band's row profile dips mid-tile. Measured
    on the operator's frame, the real band at 98..147 arrived as three runs of
    13, 12 and 10 rows, and taking the longest run alone picked a structure
    ABOVE the tiles instead."""
    for name in ("operator_orange_lime", "purple_gold", "borderless"):
        got = swept[name]
        assert got, f"{name}: nothing proposed"
        assert got[0]["bandTop"] in (98, 120), f"{name}: band {got[0]['bandTop']}"


# --------------------------------------------------- OW's own colour presets
#
# The thirteen colours OW offers for ENEMY UI COLOR and FRIENDLY UI COLOR, read
# off the settings screen 2026-09-08. (GROUP and ALERT offer two more, LAWN
# GREEN and TANGERINE, which cannot be a team colour and so cannot appear as a
# portrait strip.) RGB is estimated from the swatches - the detector keys on
# hue, so an estimate is enough to establish which PAIRS are tight, which is
# the only thing this matrix is for.
OW_PRESETS = {
    "YELLOW": [255, 255, 0], "LIME GREEN": [170, 255, 0], "NEON BLUE": [0, 255, 255],
    "AQUA": [60, 60, 255], "TAWNY": [200, 70, 0], "ORANGE": [230, 120, 0],
    "MAGENTA": [240, 0, 220], "BLUE": [0, 170, 255], "RED": [250, 40, 60],
    "GOLD": [255, 200, 0], "GREEN": [0, 180, 120], "PINK": [255, 120, 190],
    "PURPLE": [140, 0, 140],
}

# Measured: these two differ in BRIGHTNESS, not hue - about 5 degrees apart -
# so a hue sweep cannot separate them and stage 2 proposes nothing. A player
# who set them could not tell their own team from the enemy either, which is
# the entire point of the setting, so this is documented rather than fixed.
# It fails honestly: no proposal, and the preview says so.
KNOWN_UNRESOLVABLE = {("MAGENTA", "PURPLE"), ("PURPLE", "MAGENTA")}


@pytest.fixture(scope="module")
def preset_matrix() -> dict:
    """Every friendly x enemy pair of OW's presets, through the real module."""
    node = shutil.which("node")
    if not node:
        pytest.skip("node not available to run the capture app's helpers")
    cases = {}
    for left, ca in OW_PRESETS.items():
        for right, cb in OW_PRESETS.items():
            if left == right:
                continue
            cases[f"{left}|{right}"] = dict(
                W=2560, H=432, y0=98, y1=147, pitch=141.5, ax=56, bx=1804,
                ca=ca, cb=cb)
    src = _HARNESS % {"SRC": ENGINE_CALIBRATION.read_text(encoding="utf-8")}
    script = Path(__file__).resolve().parent / "_tmp_preset_matrix_check.js"
    script.write_text(src, encoding="utf-8")
    try:
        proc = subprocess.run([node, str(script), json.dumps(cases)],
                              capture_output=True, text=True)
    finally:
        script.unlink(missing_ok=True)
    assert proc.returncode == 0, f"node failed:\n{proc.stderr}"
    return json.loads(proc.stdout)


def test_every_ow_preset_pair_resolves(preset_matrix: dict) -> None:
    """The palette a contributor is actually able to select must not be a
    silent failure. 154 of the 156 selectable pairs resolve; the two that do
    not are named above and refuse rather than guess."""
    broken = []
    for key, got in preset_matrix.items():
        left, right = key.split("|")
        swept = got["swept"]
        ok = bool(swept) and abs(swept[0]["a"]["x"] - 53.3) < 5             and abs(swept[0]["b"]["x"] - 1801.3) < 5             and abs(swept[0]["pitch"] - 141.5) < 2
        if ok == ((left, right) in KNOWN_UNRESOLVABLE):
            broken.append((left, right, "resolved unexpectedly" if ok else "failed"))
    assert not broken, f"preset pairs changed behaviour: {broken}"


def test_the_default_palette_is_in_the_matrix(preset_matrix: dict) -> None:
    """BLUE friendly against RED enemy is what almost everyone runs, and it
    must resolve through stage 2 as well as through stage 1 - a partial stage-1
    read falls through to the sweep."""
    got = preset_matrix["BLUE|RED"]["swept"]
    assert got and got[0]["a"]["x"] == pytest.approx(53.3, abs=5)


def test_swapped_defaults_resolve_on_a_clean_background(preset_matrix: dict) -> None:
    """DOES NOT PROVE INVERSION WORKS IN THE FIELD - and it does not.

    Tested live 2026-09-08 with friendly RED and enemy BLUE, the right strip
    read 5/5 but the LEFT was misplaced: nothing on two configurations, and
    horizontally offset on borderless direct capture. This synthetic case
    passes because its background is flat grey; the real left half is full of
    map and HUD red, which is what the detector then has to tell the tiles
    apart from.

    What it does pin: the pairing itself carries no assumption about which
    colour sits on which side. If that ever regresses, this goes red - so it
    earns its place, as long as nobody reads it as coverage of inversion.

    The gap is known and accepted (operator's call, 2026-09-08): inverting the
    defaults is a deliberate, rare setting, and it fails HONESTLY - the preview
    reported 6/10 rather than claiming a good placement.
    """
    got = preset_matrix["RED|BLUE"]["swept"]
    assert got and got[0]["a"]["x"] == pytest.approx(53.3, abs=5)


def test_the_sweep_proposes_distinct_placements(swept: dict) -> None:
    """Every shortlist slot must be worth something.

    Adjacent hue windows overlap by a bin, so a team colour near a boundary is
    caught by two of them and proposes the SAME boxes twice. That is free to
    generate and expensive to carry: the shortlist is capped, and a duplicate
    costs a slot that a real alternative needed.

    Measured on the operator's neon-blue/magenta frame of 2026-09-08 - a team
    colour against a map of nearly that colour - twenty-four slots held about
    twelve distinct placements, and the correct one came twenty-first. It only
    just survived the cap. Deduping on geometry, the same frame proposes nine
    placements and the right one leads on score.
    """
    for name in ("borderless", "operator_orange_lime", "purple_gold"):
        got = swept[name]
        seen = []
        for g in got:
            key = (round(g["bandTop"] / 4), round(g["pitch"]), round(g["a"]["x"] / 4),
                   round(g["b"]["x"] / 4))
            assert key not in seen, f"{name}: duplicate placement proposed twice"
            seen.append(key)

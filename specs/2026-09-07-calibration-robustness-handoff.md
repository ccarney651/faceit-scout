# Handoff — make auto-calibration robust across resolutions, scales and aspect ratios

**Written:** 2026-09-07, end of a long debugging session.
**Status:** problem fully diagnosed, no solution designed. This is a brief, not a plan.
**Urgency:** the FACEIT season's first games were played today and the operator wants
to scout immediately. A known-good workaround exists (below) so this is not
blocking tonight, but the tool is intended to open publicly within days and the
capture funnel starts with auto-calibrate.

---

## The task

Design a way for the browser capture tool to locate the **two five-hero portrait
strips** in an Overwatch spectator/replay frame that works across resolutions,
UI scales, aspect ratios, display modes (windowed / borderless) and capture
modes (whole screen / single window) — without a per-user calibration ritual.

Think about approaches first. Do not start editing `engine/calibration.js`
before agreeing a direction with the operator.

---

## What exists today, and exactly why it is fragile

`docs/capture/engine/calibration.js` → `autoCalibrate()`:

1. `detectContentRect()` trims **near-black** borders (threshold 24, scanning at
   most 20% in from each edge) to guess the game area `R`.
2. `AUTO_STRIPS` — four hardcoded fractions per strip, hand-measured off one
   1440p capture years ago:
   ```
   a (left):  x 0.0506  y 0.0832  w 0.2579  h 0.0675
   b (right): x 0.6912  y 0.0818  w 0.2573  h 0.0705
   ```
   Vertical fractions are projected against `R.w * 9/16` rather than `R.h`, so
   they are aspect-independent (a no-op at 16:9, a correction elsewhere).
3. A brute-force search nudges each strip **independently**: coarse grid
   ±0.02 x / ±0.08 y at 0.005, then the top two candidates refined at 0.001.
   Each candidate cuts the box into five cells, shrinks each to 64×36 greyscale,
   and correlates against 53 stored hero portraits per side (`refs.json`).
   Ranked by **distinct heroes** (OW2 is role locked, so five cells on a side
   must be five different heroes — noise cannot fake that).

**It can translate the box. It cannot resize it.** `w` and `h` come straight
from the table. That is the core limitation.

### The measured root cause

Four frames were captured from the same machine, same replay, one per
configuration (all in `screenshots/`, see below). The portrait band's true
position was measured by detecting the saturated blue/red tiles:

```
config                              frame        band rows     band height
SCREEN + windowed                 2560x1440      120..195          76
SCREEN + borderless               2560x1440       98..179          82
OW window + borderless            2560x1440       98..179          82
OW window + windowed              2570x1385      120..195          76

AUTO_STRIPS predicts                              119..217          97
```

Two independent errors:

- **The vertical fraction is simply wrong.** The true value is about **0.068**,
  not 0.0832. Windowed configurations work *by coincidence*: the title bar
  pushes the game content down by roughly the amount the bad fraction is short
  by, and the two cancel. Remove the title bar (borderless) and the
  compensation disappears — the box lands 21px low and reads nothing.
  ```
  borderless   0 + 0.068 × 1440 =  98   ✓ observed
  windowed    29 + 0.068 × 1335 = 120   ✓ observed
  AUTO_STRIPS      0.0832 × 1440 = 120   ✓ observed, wrong reasoning
  ```
- **The HUD scales with the game's content height, which differs by mode.**
  Borderless tiles are ~8% larger than windowed ones on the same monitor.
  The search cannot correct that at all.

Both errors compound, which is why no amount of re-ranking or finer stepping
fixed it — and several attempts were made.

### Why the search cannot compensate

The window in which a strip matches at all is about **four pixels wide**,
measured by sliding one strip a pixel at a time against the real references:

```
LEFT   +8px distinct=1   +10px distinct=3   +12px distinct=4   +14px distinct=1
RIGHT  -4px distinct=0    +0px distinct=5    +4px distinct=4
```

The correlation is that sensitive to alignment because each cell is downscaled
to 64×36 before matching. `bestMatch(gp, side, fast)` slides ±2 padded pixels
when `fast=false` (nine offsets, ~9× cost); the sweep uses `fast=true`
(centre only) for speed.

---

## Hard-won facts — do not rediscover these

- **Off-frame crops score as *perfect* matches.** A box hanging off the frame
  yields uniform black; centred and L2-normalised that correlates strongly with
  almost any reference. A candidate at `y=-27.9` scored **10/10 confident**.
  `withinFrame()` now rejects those. Any new search must keep that guard.
- **Flat in-frame crops score ~0.57 uniformly** — just above the 0.55
  confidence threshold. A placement on the white team banners returned the same
  hero ten times and was reported to the operator as "9/10 portraits
  confident". `MIN_RMS = 12` rejects crops below 12 RMS; real portrait cells
  never measured below 25.8. This does **not** catch textured non-portrait
  regions, which is why distinct-hero ranking carries the weight.
- **Ranking by confident-cell count selects for noise.** Ten barely-passing
  cells outrank nine strong ones. Measured over the frame set, scored honestly
  by distinct heroes: rank-by-ok **4.50**, rank-by-sum **5.74**,
  rank-by-distinct **6.16**, per-strip rank-by-distinct **6.71**.
- **Beware circular evaluation.** An earlier version of the eval scored frames
  by confident-cell count *while the search optimised confident-cell count*,
  and cheerfully reported 8.22/10 over a tool that was reading white banners.
  Score by something the search does not optimise.
- **`detectContentRect()` is weak.** It only trims near-black. On the
  borderless frames it wrongly trimmed 64px off the bottom; on a window capture
  it does not find the title bar at all (dark-mode title bars sit at ~32
  luminance, just above the threshold of 24). A better content-rect finder may
  be most of the solution on its own.
- **Colour detection of the tiles works vertically and failed horizontally.**
  A blue/red saturation mask locates the band's top row **exactly** in all four
  configurations (98 / 120). Finding the horizontal extent the same way failed:
  a naive threshold blows the width out to 945–1199 against a true 659 because
  the centre objective bar is the same blue, and keying on the five tiles'
  periodicity detected cleanly on only 3 of 36 frames — the portrait art itself
  is not blue, so each tile is two disjoint blue runs.
- **Horizontal has never been the problem.** `dx ≈ 0` in every configuration
  measured. Do not spend effort there.
- **Geometry fitted off screenshots does not transfer.** A previous feature
  scored 12/12 offline and read nothing live because it was fitted to a box the
  tool never actually produces. Always validate against a frame exported from a
  live session (`grabFrame().toBlob(...)`), not a screenshot of the browser.
  See the `calibration-relative-geometry` note.

---

## Ideas not yet explored

Offered as starting points, not as a shortlist. The operator's own question was
"surely there is a more robust way to locate that specific area of the screen" —
and they are right.

- **Find the game content rect properly**, then apply corrected fractions. If
  `content_top` and `content_height` were known, one fraction (~0.068) would
  work everywhere. This may be simpler and more general than detecting the
  HUD itself. Note the HUD scales with content height, so the rect gives scale
  for free.
- **Scale-space search** — add a size dimension to the existing sweep. Known to
  work in at least one case: the borderless right strip reaches 5/5 at scale
  1.075, versus 0 at scale 1.0. Cheap to try, but multiplies an already
  expensive search.
- **Detect the strips structurally** rather than by colour — five equal tiles at
  a fixed pitch is a strong periodic signal. Autocorrelation along the band, or
  finding the name-plate row (a continuous dark bar under the tiles, unlike the
  tiles themselves), may succeed where the colour mask failed.
- **Multi-scale template matching** on HUD chrome that does not vary by hero —
  the tile frame, the ult-charge pip bar, the team banner edge.
- **Two-stage: detect once, then track.** Locating the HUD costs more than a
  per-frame read can afford, but calibration happens once per session.
- **Ask the workshop mode.** `tools/scrim_code/scrim_owdb.opy` already draws
  green capture markers around the scoreboard for exactly this reason
  (`Scoreboard.findMarkerBox`). It could draw markers around the portrait bar
  too. **Only viable for scrims** — league replays are stock Overwatch — so it
  cannot be the whole answer, but it could be a high-confidence path for scrims
  and a fallback elsewhere. Note the marker detector currently returns `null` on
  real frames and is itself unproven; see "Still open" below.

---

## Tools you have

**`tools/real_frame_eval/calibrate_eval.py`** replicates the real pipeline
offline in Python/numpy — `boxesFromStrips`, `cellGrayPadded`, `bestMatch`,
`withinFrame` — and scores every frame in `screenshots/`. Run it before and
after any change:

```
.venv/Scripts/python.exe tools/real_frame_eval/calibrate_eval.py
```

**`screenshots/` is gitignored**, so the frames are local to the operator's
machine and a fresh clone has none. Ask for them. The set as of tonight:

| file | what it is |
| --- | --- |
| `cfg-SCREEN-windowed.png` | 2560×1440, **the only configuration that works** (10/10) |
| `cfg-SCREEN-BORDERLESS.png` | 2560×1440, fails (0/10 at base) |
| `cfgOWDIRECT-BORDERLESSWINDOW.png` | 2560×1440, fails |
| `cfgOWDIRECT-WINDOWED.png` | 2570×1385, partial (3/10 at base) |
| `frame.png`, `frame(1).png` | earlier window captures, 2570×1393 |
| `abox.png` / `bbox.png`, `a2.png` / `b2.png` | single-strip crops, useful for matcher work |

These four configurations with known-correct answers are the real asset: a
solution must handle all of them. **They are all from one machine** — a second
contributor's capture would be worth more than any amount of further analysis,
and the operator can only get that from a real user.

To export a frame from a live session (this is the *captured* frame, not a
screenshot of the browser):

```js
grabFrame().toBlob(b => { const a = document.createElement('a');
  a.href = URL.createObjectURL(b); a.download = 'frame.png'; a.click(); });
```

---

## Constraints

- Browser JavaScript, no build step, no new dependencies. Classic `<script>`
  tags, free-variable convention — read the header of `engine/calibration.js`.
- `engine/calibration.js` is **shared by `docs/capture/index.html` (league) and
  `docs/capture/scrim.html` (scrims)**. Run
  `.venv/Scripts/python.exe tools/capture_divergence.py` before and after; it
  must not regress (currently `shared: 38  identical: 15  diverged: 23`).
- Auto-calibrate is one button press but must feel responsive. An earlier
  version called `calOk()` per candidate — a full-frame `grabFrame()` plus ten
  DOM rows plus nine-offset matching — roughly a hundredfold blowup, and the
  operator reported the page freezing. Budget is a short pause, not seconds.
- Verify with `.venv/Scripts/python.exe -m pytest` (867 tests) and
  `node tools/verify_capture_browser.js` (137 checks, needs
  `python -m http.server 8000 --directory docs` running).
- Hero references live in `docs/capture/refs.json`: 53 heroes × 2 variants
  (`a` = blue/left, `b` = red/right), 64×36 greyscale, `left_fraction` 0.42 and
  `top_fraction` 0.45 governing the sub-crop within each cell.

---

## Success criteria

1. All four configuration frames calibrate correctly, measured by **distinct
   heroes per side** (5 + 5 = 10 is perfect).
2. No hardcoded assumption that the HUD sits at a fixed fraction of the frame.
3. Degrades honestly: when it cannot find the strips it must **say so** rather
   than report high confidence over garbage. The current failure mode reported
   "9/10 portraits confident" while every row was wrong, which is worse than
   admitting defeat.
4. Manual box-setting remains as the fallback and keeps working.

---

## The workaround, so nothing is blocked

**Share the entire screen with Overwatch in windowed mode.** Verified 10/10 on
the operator's own frame, at the base position with no search. Boxes persist in
`localStorage['owdb_cap_boxes']`, so calibrating once is enough — but switching
display mode changes the geometry and requires recalibration.

---

## Still open, unrelated to calibration

Do not lose these; they matter more to the product than calibration polish.

- **`autoBoardBox()` returns `null` on real frames** even with the workshop's
  green capture markers enabled and confirmed present in the lobby settings.
  `Scoreboard.findMarkerBox()` has never succeeded in the field.
- **The board read silently does nothing** when there is neither a marker box
  nor a hand-set SCOREBOARD box — `readScoreboard()` returns null and
  `captureBoardRead()` treats that as "not configured". For a public tool this
  should say so once; the operator's preference was a passive banner rather than
  a modal, but it was never built.
- **The per-round scoreboard read has never run successfully end to end.** It is
  committed, unit-tested and covered by browser checks, but has never been
  exercised against a real slot-ordered board. See
  `specs/2026-09-06-scrim-board-reads-design.md`.

# Real-frame evaluation of HUD name reading

`tools/assign_eval.py` measures the resolver against **synthetic** OCR corruption.
This harness measures the whole path — crop, tesseract, match — against **real
tesseract output on real HUD frames**, and it exists because the synthetic model
turned out to be wrong in two important ways:

- it models uniform per-character noise, and real OCR fails per *name* — one read
  is pristine, the next is unrecognisable garbage from a crop that is perfectly
  legible by eye;
- it assumes the crop handed to tesseract contains the name. For a long time it
  did not.

Ground truth is free when a frame shows its replay code: the code resolves in
`faceit.sqlite3` to a match and game, and that gives the exact five-player,
role-tagged lineup per team. The HUD *slot order* is not in the database and was
read off the frames by eye; it lives in `gen_truth.py`.

## What is in `screenshots/`

**`screenshots/` is gitignored** (56MB of PNGs), so these fixtures live on the
operator's machine only and a fresh clone cannot run this harness. Keep that in
mind before treating the numbers below as reproducible by anyone else.

Nine 2557×1438 frames, four replay codes, two distinct lineups:

| Frames | Code(s) | Match |
| --- | --- | --- |
| `200028`, `231525`, `231549`, `231604`, `231629`, `231639`, `231647`, `231657` | `K3A6HZ`, `TJDE6W`, `H6R64B` | Frost Tails vs ELMT Sunrise, games 1–3 — same ten players throughout |
| `image.png` | `GPJW93` | Wasp vs Dystopia — an independent lineup |

Three of the twenty players are cases no name lookup can solve on its own, which
is the whole argument for the role constraint:

- `JODAN` on the HUD, `Arclite` in `players.game_name` — **FACEIT's stored
  battletag is stale against the live Battle.net name**.
- `HZL` on the HUD, `PatataTime` stored.
- `ØØØØØ` on the HUD, five `ø` stored — the stroked-Latin case `engine/names.js`
  now transliterates.

## Result: the crop was the bottleneck (2026-08-18)

Ninety slots (nine frames × ten), real tesseract, three crop geometries. `row`
is the shipped `engine/frames.js nameRow()` locator; `shipped` is the fixed
48–90%-of-cell-height band it replaced.

```
variant     meanSim  read-alone-correct   assigned: correct  wrong  abstain
shipped       34.2    15/90                    36/90      2       52
row           92.4    77/90                    90/90      0        0
rowtight      91.0    73/90                    90/90      0        0
```

`shipped` is the geometry that had been running in production: on a real frame
the 48–90% band straddles the portrait bottom, the name **and** the health bar, and the bar
is the brightest thing in it. It also produced two *wrong* attributions — the
only wrong ones anywhere in this harness.

`rowtight` additionally trims each crop's x to the glyph run. It is no better
than `row` and has an extra failure mode, so it was not shipped; the code is kept
in `crop_variants.py` as the measurement that justified leaving it out.

With the crop fixed, the two hard cases from the earlier run remain visible and
still resolve: tesseract returns `404f` / `40.41` / `0Qf` for a clean, legible
`PROXY` in three frames, and `JODAN` reads perfectly and matches nothing. Both
are recovered by elimination inside the role group.

Confirmed live the same day: code `3DQNHD` on Oasis tagged 10/10 with none wrong
and none abstained, where the same code managed 6/10 with four abstentions before
the fix.

## The locator, and the two attempts that failed first

All five of a team's names share one row, so the row is found **once per side
across the whole five-slot strip**. Per slot it cannot be done reliably:

- *"Find the bar, take the band above it"* assumes the bar always out-scores the
  name. A long, dense name inverts that.
- *"Take the topmost strong band"* assumes nothing strong sits above the name.
  The hero portrait is inside the cell, above the name, and its art is
  transition-dense — 8 of 10 crops came back as hero portraits.

Across the strip the five names reinforce each other while per-hero portrait
noise averages out. The row is the run of rows that have many horizontal
light/dark transitions, do not fill the strip (a full health bar fills ~0.55 of
it, a name ~0.15–0.32), and sit in the quietest surroundings — the HUD draws the
names on a dark plate, and nothing else in the band has empty rows above and
below it.

Robustness, from `rowfind_sweep.py`: nine frames × four capture resolutions
(2557/1920/1600/1280 wide) × twenty-five perturbed calibration boxes = **1800/1800
land on the name row**. It holds for a box top off by ±25px and a box height off
by 0.8–1.25×; it fails only once the search band no longer contains the row at
all.

## Running it

Needs `tesseract.js` (not a project dependency — the capture page loads it from a
CDN at runtime). It drops a ~5MB `eng.traineddata` in the repo root on first run;
delete it afterwards.

    npm install --no-save tesseract.js

Crop quality end to end (writes into a scratch dir of your choosing):

    .venv/Scripts/python.exe tools/real_frame_eval/gen_truth.py  /tmp/truth.json
    .venv/Scripts/python.exe tools/real_frame_eval/gen_all.py    /tmp/strips
    node tools/real_frame_eval/ocr_all.js        /tmp/strips /tmp/reads.json
    node tools/real_frame_eval/score_variants.js /tmp/reads.json /tmp/truth.json

The locator on its own, no OCR — sweep the thresholds, then check the **shipped
JS** agrees with the prototype on the very same pixels:

    .venv/Scripts/python.exe tools/real_frame_eval/rowfind_sweep.py
    .venv/Scripts/python.exe tools/real_frame_eval/rowfind_parity.py /tmp/bands

| File | Does |
| --- | --- |
| `rowfind_proto.py` | Python mirror of `findNameRow`, for fast threshold sweeps |
| `rowfind_sweep.py` | The frames × resolutions × perturbed-boxes grid |
| `rowfind_parity.js/.py` | Runs the real `engine/frames.js` over dumped real bands and asserts it matches the prototype and lands on the row |
| `crop_variants.py`, `gen_all.py` | Render the three crop geometries, mirroring `nameCanvas()`'s 6× upscale and contrast stretch |
| `ocr_all.js` | Real tesseract, configured exactly as the capture page configures it (psm 7 + the gamertag whitelist) |
| `gen_truth.py` | Lineups from `faceit.sqlite3` + the HUD slot order |
| `score_variants.js` | Scores OCR quality and end-to-end attribution per variant |
| `crop_names.py`, `ocr_strips.js`, `compare_real.js` | The original single-frame matcher comparison (old greedy vs `assign.js`), kept as the record of that result |

`rowfind_proto.py` is a mirror and mirrors drift — `rowfind_parity.py` is what
keeps it honest, so run it after touching either copy. It allows one row of slack
because `np.percentile` interpolates where the JS reads a 256-bin histogram.

## Checking it in a real browser

`browser_check.html` runs the shipped engine over all nine frames in an actual
browser — auto-calibration, `nameRow()`, `nameCanvas()` — which the node and
Python harnesses cannot do, having no canvas. Serve the **repo root** so the
frames and `/docs/capture/` are same-origin (a cross-origin frame taints the
canvas and `getImageData` throws):

    .venv/Scripts/python.exe -m http.server 8000 --bind 127.0.0.1

then open `http://127.0.0.1:8000/tools/real_frame_eval/browser_check.html`, or
headlessly:

    msedge --headless=new --disable-gpu --virtual-time-budget=60000 --dump-dom "http://127.0.0.1:8000/tools/real_frame_eval/browser_check.html"

It confirms `nameRow()` returns `{y:154, h:22}` on all eighteen (frame, side)
pairs — identical to node and to the Python prototype — and that the crop canvas
comes back the right size and not blank.

## The fixtures do not match live HUD geometry — the product does

Found while building the browser check, and **settled**: `AUTO_STRIPS` is right
for a live capture and wrong for these frames. On 2026-08-18 auto-calibrate
reported *"10/10 portraits confident"* against a live share, so nothing here is a
reason to touch it. What follows is a caveat about the fixtures, not a bug.

On these frames the shipped placement is wrong, by the product's own portrait
matcher (sum of ten cells' best match; higher is better):

```
  AUTO_STRIPS base placement          2.56 - 3.35
  after autoCalibrate's dx/dy sweep   4.83 - 5.48
  the measured portrait strip         6.06 - 6.82   (best on all nine frames)
```

The base strips land about half a cell right and low; `autoCalibrate` then drives
`dy` to the sweep's extreme (`-8`, i.e. -115px) chasing the deficit and puts the
box at y≈5, nowhere near the portraits at y≈97.

**Translation is not the problem — size is.** Sweeping dx/dy far past the shipped
±0.02/±0.08 bounds tops out at 4.28, still well under the measured box's 6.82,
because `boxesFromStrips` can only translate. The strip fractions themselves are
off: `AUTO_STRIPS` says 0.2579 × 0.0675 of the frame where these frames want
≈0.2738 × 0.0772 — about 6% wider and 14% taller. Widening the sweep would not
help.

So these frames are not a stand-in for a live capture as far as *calibration*
goes — they are from a replay/spectator HUD and evidently predate a layout change
or come from a different UI scale. That is why `gen_all.py` derives its boxes
from the pixels instead of using `AUTO_STRIPS`, and why the perturbation sweep
matters. **Do not "fix" `AUTO_STRIPS` from these fixtures** — it is correct for
the thing it is actually used on.

## Caveats

- **Slot roles are supplied from ground truth**, so the attribution numbers
  assume hero recognition is correct. They do not test the recognise→role step.
- Two lineups, nine frames. 90 slots, but not 90 independent situations.
- The calibration boxes in `gen_all.py` are *derived* (portraits at y=97..147 are
  the top 45% of a 111px cell; cells are 140px from x=57 and x=1800), not taken
  from a real `roi_profiles` row — the stored profiles do not line up with these
  frames. The perturbation sweep is what covers the resulting uncertainty. The
  derivation is not guesswork: it scores higher than any placement
  auto-calibration can reach, on every frame, by the product's own matcher (see
  above).
- The whole crop result assumes calibration put the box on the portraits. It says
  nothing about what happens when calibration is grossly wrong — then the crop is
  meaningless, but so is hero recognition, and the page already says so.

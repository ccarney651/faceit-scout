# Handoff — nameplate OCR's dark-plate assumption breaks on a bright plate (2026-09-15)

Root-caused, not fixed. Reproduced twice on real captured data with a precise
mechanism, in shared code (`docs/capture/engine/frames.js`), so the fix
matters to the live capture pages' name OCR too, not just the replay bot.

Branch: `capture-read-guards`. Repo root: `C:\Users\ccarn\faceit-sync`.

---

## 1. How this was found

The operator was reviewing the 2026-09-15 390-map run
(`tools/replay_bot/out/replay-bot-2026-09-15-full.review.json`) and flagged a
map (`2RNA0B`, Samoa, SNK vs Green bean alliance) where every slot on one side
showed `attribution-abstained` despite the portrait-strip crop shown in the
review page looking completely legible — sharp portraits, crisp "4%/5%/4%/
12%/6%" ult text, bold player names plainly readable by eye.

That portrait-strip crop is **not** what OCR reads from, though — it is
`calib.FROZEN.boxes[side]` (plus 12px of display padding, `review_out.js`'s
`PAD_Y`), rendered whole for the human reviewer. `attribute.js`'s actual OCR
input is a much narrower **name row**, independently located by
`nameplate.js`'s `nameRow()`, which is a thin wrapper around
`docs/capture/engine/frames.js`'s `findNameRow()` (required directly,
unmodified — the same module the two live capture pages use). That function
is where the bug is.

## 2. Established (all of this is settled — do not re-litigate)

- **Not a crop-geometry offset.** Re-deriving `nameRow()`'s search band
  against the *true* `calib.FROZEN.boxes[side]` (not the padded review-display
  crop — see §3 for why that distinction matters) puts the 0.48–0.85 band
  exactly where the name text visually sits, confirmed by rendering the band
  boundaries over the real frame (§4).
- **Not OCR/tesseract misconfiguration.** Running the exact same
  `tessedit_char_whitelist` tesseract.js call `run.js` uses, directly against
  a correctly-cropped name-cell image, reads `SQUISHYSQUID`, `SHOCK`,
  `IPEECHEETOES`, `SHOGATTSU`, `ANGELOLAGUSA` perfectly — the five real roster
  names. OCR and its config are not the problem.
- **Not the same bug the 2026-09-15 `sample.quiesceMs` fix (700→1300,
  `CHANGELOG.md`) targets.** That fix is for a frame caught mid-transition
  after a seek. Every frame examined here is fully settled and static — the
  scoreboard numbers, health bars and portraits are all fully drawn. This is a
  measurement bug on good data, not a timing bug.
- **The raw OCR strings are already kept for exactly this kind of question.**
  `m.attribution.reads` (screen-side keyed, `{a:[...5], b:[...5]}`) rides in
  the review artifact — `attribute.js`'s own comment already documents an
  earlier, different instance of "OCR'd clean but still abstained" found
  2026-09-11 (PROXY/EDEN). Read that field before guessing at a map's
  abstain cause.

## 3. The mechanism

`findNameRow(rgba, w, h)` in `docs/capture/engine/frames.js:79` scores each
row of the search band by:

```js
score[y] = fill[y] <= NAME_FILL_MAX ? tr[y] : 0;   // NAME_FILL_MAX = 0.42
```

`fill[y]` is the fraction of that row's pixels brighter than a threshold `T`
(the 88th luminance percentile of the whole band, clamped to [120, 230]).
`tr[y]` is the row's light/dark transition density (how "texty" it looks).
The comment justifying `NAME_FILL_MAX` is explicit about its assumption:

> the HUD draws the names on a dark plate and nothing else in the band has
> empty rows above and below it

**That assumption is false for a bright or team-colour-tinted plate.** A
light-blue or saturated-red name-plate background is itself well above the
88th-percentile brightness threshold, so `fill[y]` for the row containing the
actual name text is inflated by the *background*, not just the glyphs — and
once `fill[y] > 0.42`, `score[y]` is forced to zero regardless of how
text-like `tr[y]` looks. Reproduced two distinct ways on the 2026-09-15
390-map run:

- **Total miss** (`BM1S86`, side a; `CENQKX`, side a; light-blue-tinted
  plates): every row across the true name-text height scores `fill` 0.50–0.65,
  permanently over the 0.42 ceiling. `findNameRow` returns `null` for the
  *entire side* — all 5 slots get blank OCR reads (`reads.a = ['','','','','']`).
- **Fragmented match** (`2RNA0B`, side b; red-tinted plate): most of the true
  text-row band scores fine (fill 0.27–0.41), but two interior rows spike to
  0.44–0.45 and get zeroed, splitting one ~13-row run into fragments. The
  run-selection logic picks the wrong (much shorter, ~5px) fragment, so
  `nameCrop()` hands tesseract a one-pixel sliver of glyph *tops* instead of
  the glyphs — garbage in, garbage out (`"42420sBBEaEBOrahoaeBOBEb"` etc.).

Both outcomes present identically downstream: `assign()` gets nothing useful
to match against, every slot abstains, `attribution-abstained` fires. The two
are indistinguishable from the review page or from `resolve.js`'s flags alone
— you have to look at `m.attribution.reads` to tell "abstained because OCR
read blank" from "abstained because OCR read garbage" from the pre-existing
2026-09-11 "abstained despite a clean read" case (assign.js ambiguity, not
this bug at all).

## 4. How to reproduce / verify a candidate map

No live client needed — this is pure offline pixel analysis against a saved
review artifact and its crop PNGs (`out/<session>/crops/<code>-r<N>-<side>.png`).

1. Find a suspect: any map/side in a `.review.json` where
   `m.attribution.reads[side]` has ≥3 of 5 entries that are empty or not
   plausible names.
2. Load `out/<session>/crops/<code>-r1-<side>.png` — this is
   `calib.FROZEN.boxes[side]` **plus `PAD_Y=12` px of padding top and bottom**
   (`review_out.js`'s `writeStrip`). Don't feed this straight into
   `nameplate.js`'s functions as if it *were* the box — rebase first:
   `box = { x: 0, y: PAD_Y, w: img.width, h: calib.FROZEN.boxes[side].h }`.
   (First pass at this got tripped up by exactly that — a naive test that
   skips the rebase gets a *more forgiving* result than production, because
   the extra 24px of height gives `findNameRow` more room than it really has.)
3. `Nameplate.nameRow(img, box)` — `null`, or a suspiciously short `h`
   (production text rows run ~13-20px; anything under ~10px is the fragment
   bug), confirms it.
4. To see *why*: recompute `fill[y]` per row by hand over the same band (see
   the commands run this session, not reproduced verbatim here — straightforward
   from `findNameRow`'s own source) and look for text rows sitting above 0.42.

## 5. Recommended direction (not decided — operator's call)

Options, roughly in order of invasiveness:

- **A. Raise or drop `NAME_FILL_MAX`.** Cheapest, but it is exactly the kind
  of single global constant that got the matcher into trouble before (see the
  ±2→±14 search radius fix, same day) — a plate bright enough to need a higher
  ceiling might also make a genuine health-bar row cross it, reintroducing the
  original "brightest thing in the crop is the health bar" failure this
  heuristic was built to fix (§6.2 `ARCHITECTURE.md`). Needs the same kind of
  corpus sweep that settled the search radius, not a guess — `tools/`
  currently has no harness for this the way `match_search_sweep.js` exists for
  the matcher; one would need to be built first.
- **B. Make the fill ceiling relative, not absolute.** Compare each row's
  `fill` against the *band's own* background fill (sampled from quiet rows
  above/below, which `quiet()` already computes for a different purpose) rather
  than a fixed 0.42 — would naturally adapt to a bright plate's baseline
  instead of assuming a dark one. More robust, more code, more risk of
  regressing the dark-plate case the current measurements (77/90, §6
  `ARCHITECTURE.md`) already validate.
- **C. Detect the plate's own background brightness first and pick a ceiling
  from a small table** — same spirit as the auto-calibrate cascade's
  "team-colour sweep for custom palettes" (§6.2), which already exists for a
  *different* fitting problem in the same file family. Reuse of an existing
  pattern rather than a new one.

Whichever is chosen, this is shared code
(`docs/capture/engine/frames.js` → both `docs/capture/index.html` and
`docs/capture/scrim.html`'s live name OCR, and `tools/replay_bot/nameplate.js`
mirroring it unmodified for the bot) — same caution as the matcher radius
item in `PLANS.md`: `tools/verify_capture_browser.js` does not exercise name
OCR either, so a change here also ships with no automated browser coverage
unless that's added alongside it.

## 6. What this does and does not explain

Of the 390-map run's 99 flagged maps, only **25 maps** (one or both sides)
show the heavy-garbage/all-blank OCR signature this bug produces. The
remaining `attribution-abstained` flags are very likely the *other*,
pre-existing, still-unexplained failure mode `attribute.js`'s own comment
already documents from 2026-09-11: OCR reads a clean, correct name and
`assign()` still won't commit to a slot (a role-constraint or scoring issue
in `docs/capture/engine/assign.js`, not `nameplate.js`). Don't assume fixing
this bug clears the whole `attribution-abstained` bucket — check
`m.attribution.reads` per map before attributing a fix's impact.

## 7. State of the batch this was found in

- `capture-read-guards`, uncommitted at handoff time: `resolve.js` playtime-based
  round resolution + `needsReview()` auto-review gate, `timing.js`
  `sample.quiesceMs` 700→1300 (folding in and clearing a stale
  `state/console_timing.json` override that had silently pinned it to 1000
  since 2026-09-11), matcher ±14 search (already committed separately,
  `d3ac0bf`, also cherry-picked to `main` as `936978c`).
- The 2026-09-15 full run captured 390 of 545 live codes before a
  two-consecutive-load-timeout circuit-breaker stop (client likely lost
  session state — display sleep/lock, not a bot bug). 155 codes remain,
  listed at `tools/replay_bot/state/full-run-remaining.txt`, ready to resume
  with `node run.js --codes "$(cat state/full-run-remaining.txt)"` once the
  client is confirmed responsive again.
- Review server was running at `http://localhost:51900/` against
  `out/replay-bot-2026-09-15-full.review.json` (390 maps, 340 auto-reviewed,
  50 still flagged) at handoff time.

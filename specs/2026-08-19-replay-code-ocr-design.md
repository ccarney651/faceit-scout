# Reading the replay code off the screen — design

**Date:** 2026-08-19
**Scope:** both capture pages — `docs/capture/index.html` (league) and
`docs/capture/scrim.html` (scrims), via one shared engine module.
**Status:** awaiting review.

## 1. The problem

A capture is filed against a **replay code**, and the code is entered by hand.

On the **league** page the operator picks one from a `<select>` of six-character
strings that all look alike (`syncCodeOptions()`). Picking the wrong one is easy
and nothing detects it: every comp captured is then attributed to the wrong
match, the wrong teams and the wrong players, and unlike a scrim that record is
published. There is no later signal that it happened — the capture looks
perfectly well-formed.

On the **scrim** page the code is optional metadata, typed into the panel's
next-map field. It is what lets someone find the replay again later. In practice
it gets skipped, because typing six random characters mid-scrim is exactly the
kind of friction the panel-first workflow exists to remove.

Meanwhile the code is **on the screen the whole time**, in the same place, in
both cases.

## 2. Where it is

The code sits on the top HUD banner row, immediately right of the TEAM 1 banner
and left of the objective/score box. Two frames, deliberately different in
resolution and window mode:

| Frame | Mode | Code |
| --- | --- | --- |
| `Screenshot 2026-08-18 234927.png` | windowed, 2559×1439 desktop | `D9X9N2` |
| `Screenshot 2026-07-15 231525.png` | fullscreen, 2557×1438 | `TJDE6W` |

In both, the code's position **relative to the TEAM 1 hero-portrait strip** is
the same: just past that strip's right edge, roughly three-quarters of a
strip-height above its top, about an eighth of a strip-width wide.

That strip is `boxes.a` — already calibrated, already fitted to the actual HUD by
`autoCalibrate()`. **The crop is therefore anchored to `boxes.a`, not to screen
fractions.** This is the same lesson the HUD name row taught (see
`specs/2026-08-16-player-assignment-design.md` §3): a band expressed as a
fraction of the screen straddled the wrong thing as soon as the window mode
changed, and the fix was to locate it against something already fitted.

The offsets quoted above are **eyeballed from two frames** and are not the
shipping values. They are fixed by a sweep over the full frame set (§6).

## 3. The alphabet is Crockford Base32

Measured over every replay code in `docs/faceit.sqlite3.gz` (`games.demo_code`):

```
4328 codes, all exactly 6 characters
alphabet observed: 0123456789ABCDEFGHJKMNPQRSTVWXYZ   (32 symbols)
never appears:     I  L  O  U
each of the 32 appears 750-850 times
```

Zero occurrences of four specific characters across 25,968 draws, while the other
32 are near-uniform, rules out a 36-character alphabet outright.

That set is **exactly [Crockford Base32](https://www.crockford.com/base32.html)**
— the ten digits plus A–Z excluding I, L, O and U. 32 symbols at 6 characters is
30 bits, which is what an ID space is designed around. The exclusions are
documented, with reasons that are precisely our problem:

| Excluded | Crockford's stated reason |
| --- | --- |
| `I` | can be confused with `1` |
| `L` | can be confused with `1` |
| `O` | can be confused with `0` |
| `U` | accidental obscenity |

And the spec prescribes the decoding rule directly: *"i and l will be treated as
1 and o will be treated as 0"*, with both cases accepted.

**This is why the folding rules below are not heuristics.** An earlier draft of
this design also folded `U`→`V` by inference. That is dropped: Crockford excludes
`U` for a reason that has nothing to do with visual ambiguity and says nothing
about decoding it, so there is no principled target to fold it to. A `U` in a
read is an unresolved character (§4.3).

Independent corroboration, ten codes from a third-party replay site
([OWReplays](https://owreplays.tv/)): `TKTNNJ`, `8ZHH4N`, `BS0JB2`, `08K58S`,
`73EGH8`, `HFVD7S`, `QD1255`, `1T8FNF`, `G90HXD`, `J1RYFB` — no I, L, O or U in
60 characters. No public Blizzard documentation of the format was found.

## 4. Design

### 4.1 `engine/replaycode.js` — the shared core

DOM-free, testable under `node:test`, with a co-located `replaycode.test.js`.

```
ALPHABET        the 32 Crockford symbols
codeBox(boxA)   -> {x,y,w,h}   the crop, relative to the calibrated strip
foldCode(raw)   -> 'D9X9N2' | null
```

`foldCode` is the whole validation gate and is pure:

1. uppercase (Crockford accepts either case; Tesseract may return either)
2. strip everything that is not a letter or digit — the crop carries plate edges,
   and the name-crop work showed OCR wraps a legible string in invented
   punctuation
3. fold `I`→`1`, `L`→`1`, `O`→`0` — the published decoder rule
4. require **exactly six** characters, all in the alphabet
5. anything else returns `null`

### 4.2 The read

Crop from the live frame → upscale and hard contrast → Tesseract → `foldCode`.

The contrast treatment is the one that took HUD name reads from 15/90 to 77/90
(`engine/frames.js`); the code sits on a similar semi-transparent plate and has
the same problem.

Tesseract runs at `tessedit_pageseg_mode: 7` (one line) with
`tessedit_char_whitelist` set to the 32 symbols. **Both parameters must be set
and restored per call.** There is one shared worker
(`ocrWorker()` in `engine/refs.js`) and its header records why no whitelist is
set globally: `readScoreboard()` needs full text, and a code-only whitelist would
break it. Reads must not overlap — the module serialises on the existing worker
promise rather than adding a second worker.

### 4.3 When it is unsure, it says nothing

`foldCode` returning `null` means no read. Nothing is written, no field changes,
and the operator is told the read failed rather than being handed a guess.

**The failure this must not have is a plausible wrong code in a saved record** —
that is indistinguishable from a correct one and silently misattributes a whole
map. A refused read costs one retry.

### 4.4 League page: snap to the feed

The league page knows every valid code for the division, so the read is checked
rather than trusted:

| Read | Behaviour |
| --- | --- |
| exact match in the feed | select that match |
| within edit distance 1 of exactly one feed code | offer it as a correction, named |
| ambiguous, or no match | say so; change nothing |

This is the wrong-match guard, and it is also why the league page is where the
locator's accuracy is *provable*: every read has a right answer available.

### 4.5 Scrim page: fill the field

A *Read code* button beside the panel's next-map code field fills it on success.
There is no candidate list to check against, so the read stands on `foldCode`
alone.

`refuseIfLeagueCode()` keeps first refusal, unchanged: a read that turns out to
be a live league code is blocked from being filed as a private scrim exactly as a
typed one is.

### 4.6 Trigger — on demand only

A button on each page, plus one read when a scrim map starts if the field is
empty. No polling.

Continuous polling was considered and rejected by the operator. It would have
enabled a fourth consumer — noticing mid-capture that the code changed, catching
a forgotten *Finish* — at the cost of steady OCR load and turn-taking against the
name and scoreboard reads on the single shared worker. **That consumer is
therefore out of scope**, and the design should not be read as leaving room for
it: adding it later means revisiting §4.2's serialisation.

## 5. Where it plugs in

| Site | Page | Action |
| --- | --- | --- |
| *Read code* button, panel next-map row | scrim | fill the code field |
| `startMapNamed()` | scrim | one read if the field is empty |
| *Read code* button, beside the code picker | league | select or correct the match |

## 6. Verification, before it ships

The frame set already has hand-verified ground truth in
`tools/real_frame_eval/gen_truth.py`, which maps frame stems to codes because the
name-attribution eval needed the code to resolve each frame's lineup:

| Code | Frames |
| --- | --- |
| `K3A6HZ` | `200028` |
| `TJDE6W` | `231525`, `231549`, `231604` |
| `H6R64B` | `231629`, `231639`, `231647`, `231657` |
| `GPJW93` | `image` |
| `D9X9N2` | the three 2026-08-18 frames (read by eye; to be added to the table) |

Twelve frames, five distinct codes, two window modes, several resolutions. Note
the codes themselves are *evidence about the frames*, so this table is truth for
this work in a way it was only incidental for the last one.

Three proofs, matching what the name crop had to produce:

1. **Offline eval** — read every frame, compare against the truth table. Reported
   as reads-correct and, separately, wrong-reads, which must be zero.
2. **Offset sweep** — the §2 offsets swept with `boxes.a` perturbed and stretched,
   as `rowfind_sweep.py` did for the name band, so the shipping numbers are fitted
   rather than eyeballed.
3. **Parity check** — the shipped JS run over the same real pixels as the Python
   prototype, so the sweeping tool cannot drift from what ships
   (`rowfind_parity.py`/`.js` is the precedent).

**Gate: zero wrong reads across the frame set.** A low read rate is a nuisance
the operator absorbs by retrying or typing; a wrong read is a corrupted record.

## 7. Out of scope

- **Continuous polling and mid-capture map-change detection** — §4.6.
- **Reading anything else off the banner row** (team names, score, timer). The
  score box already has its own WIP read.
- **Backfilling codes onto already-captured maps.** Nothing stores a frame after
  the fact, so there is nothing to re-read.
- **`parseScrimSessionText()` / `buildScaffold()`** stay as they are. They were
  kept through the panel migration for this work, but they parse a *replay-history
  list*, which is a different screen from the in-replay banner this reads. They
  are not touched here and do not become reachable again.

## 8. Risks

- **The §2 offsets may not hold across HUD variants** the frame set does not
  cover — a different aspect ratio, or a HUD scale setting. The sweep measures
  robustness within the set; it cannot speak for what is not in it. The on-demand
  trigger limits the blast radius: a failed read is visible immediately.
- **`boxes.a` must be calibrated** for the crop to exist at all. Both pages
  already gate capture on calibration, so this adds no new precondition, but the
  button must say that rather than failing opaquely.
- **Edit-distance 1 on six characters is a wide net** when a division has many
  codes. §4.4 requires a *unique* near match and abstains otherwise; the eval
  should report how often distance-1 is ambiguous in a real feed.

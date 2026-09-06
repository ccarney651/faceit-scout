# Scoreboard capture — design

**Date:** 2026-09-06
**Status:** design, agreed with the operator in conversation; not yet planned or built.
**Supersedes:** §5.1–5.4 of `specs/2026-08-12-scrim-mode-design.md` (phase 3),
which assumed a hero-glyph reference set was required. It is not.

## Goal

Per-player stats for a scrim map, read off the workshop spectator scoreboard at
moments the operator chooses, without a hero-glyph reference set and without
guessing which player a row belongs to.

## 1. The decision that removes the hard part

Phase 3's cost was concentrated in one place: the scoreboard row identifies its
player by `heroIcon(hero)`, an image OCR cannot read, so §5.1 concluded that a
reference set of workshop hero glyphs had to be built.

It does not, because **the row's sort order already carries the identity**.
`scrim_owdb.opy` offers three grouping styles, and the third makes the board
positional:

| Grouping Style | Sort key | Row order |
| --- | --- | --- |
| Group by role, sort by team *(the default)* | `role + 0.1×team` | role blocks, teams interleaved |
| Group by team, sort by role | `0.1×role + team` | team blocks, role-ordered |
| **Group by team, sort by slot** | `0.1×slot + team` | **Team 1 slots 0-4, then Team 2 slots 0-4** |

Under the third, row *i* is slot *i*, and the spectator portrait bar is in slot
order too — so `row → slot → player → hero` resolves positionally. The portrait
bar read the tool already performs supplies the player and the hero; the
scoreboard supplies the stats; position joins them.

**This is a workshop SETTING, not the code.** It is changed in the lobby, needs
no recompile and no re-upload, and the share code stays as it is.

### What that costs: it only works from the next lobby onwards

A replay reproduces the match as recorded. The grouping style is fixed at play
time, so **every existing replay code renders the role-grouped board** and
nothing done now can change that. The operator's decision, 2026-09-06, is that
**future scrims only is fine** — so the role-grouped layout is explicitly out of
scope for per-player attribution.

An attempt was made to avoid even that constraint: the row icon is the same
portrait art as the spectator bar, in the same frame, with the player's name
printed under it, so matching row icon against bar portrait should identify the
row with no reference set at all. Measured against a real frame it scores
**6/10 within the row's own team, 4/10 against all ten** — the row icons are
alpha-blended over the game world while the bar portraits sit on a solid panel,
so the same art gives different pixels. Recorded here so it is not re-attempted
casually; it is improvable (mask to the opaque interior, hue over luminance,
1-of-2 within a role pair) but it is not free, and the setting change is.

## 2. What already exists

- `docs/capture/scoreboard.js` — a pure parser for the **role-grouped** layout:
  legend rows by their `ACC`/`DB`/`HD` marker, entry rows as six values,
  `Match Time`, and a best-effort team split. 200 lines, unit-tested, and its
  header documents the row format.
- `docs/capture/engine/banrow.js` — the `BANS :` / `MAP :` rows, textually
  anchored.
- The portrait-bar comp read, which already yields player → hero per slot.

The new work is a slot-ordered layout path, the trigger model, and the record.

## 3. Decisions

| Decision | Choice | Why |
| --- | --- | --- |
| When a read happens | On **Next round** and on **Finish map**, never on a timer | In a replay the operator controls time. The authoritative frame is the one they scrubbed to, not whatever a 5-second timer caught. |
| A failed read | **Blocks** the advance, with an explicit **Skip** button | Operator's call. The board is gone once the round ends, so a silent failure is unrecoverable; making them look at it while they can still scrub back is the point. |
| Stat semantics | The board **accumulates over the map**; a round's stats are the delta between consecutive reads | Confirmed by the operator. It is why reading at the exact boundary is load-bearing rather than tidy. |
| Where deltas are computed | **At analysis time, not at capture time.** The record stores raw cumulative reads | Same rule the contribution merge already follows: store observations, derive reports, so an improvement to the arithmetic applies retroactively to every capture already taken. |
| A skipped read | Recorded, and the next successful read carries `rounds_covered: n` | A skip does not lose the stats, only the boundary. The next delta legitimately spans two rounds and the record must say so rather than attribute it all to one. |
| Layout | Detected from the read itself, never from a stored setting | Three stacked legends followed by ten rows is a different shape from three interleaved blocks. A setting the operator can change mid-session and the tool cannot see is a desync waiting to happen. |
| A role-grouped board | Read, stored, and attributed to **team and role** only — never guessed to a player | Team-level and comp-level analysis is unaffected; per-player is what the layout cannot support. Honest partial data beats a coin-flip. |

## 4. The read

One crop, one OCR pass, four facts. The workshop draws all of it as one block at
`HudPosition.LEFT`: `BANS`, `MAP`, the legends, the ten rows, and `MATCH TIME`.
`readBanRow()` already OCRs a generous fixed region of the left column — the
same read serves the board, so this is one pass, not two.

**The row names its own player (added 2026-09-06, after the design's first
draft).** Small and Medium now render `{icon} {name}: {stats}`; Large already
carried the name as its subheader. This was out of scope while it implied a
re-upload of its own, and stopped being so the moment the operator decided to
re-publish the mode from their main account — the marginal cost of carrying it
in that build is nothing.

It does not replace the slot ordering, it insures it: identity is then read
rather than inferred, so a lobby where somebody left the grouping style on a
role-grouped preset still attributes to the right player. **The colon is
load-bearing.** Overwatch permits an all-digits name, and the existing parser
identifies the stats by skipping leading non-numeric tokens — which would take
`1337` for a final-blow count. Splitting on the first colon is what makes a
numeric name safe.

**Shape validation, adapted from §5.2 to the slot layout.** A read is accepted
only if: ten entry rows; five of one team colour then five of the other; each
row six numeric fields, at most one bearing `%`; a `MATCH TIME` line present;
and the portrait bar independently reading 1-2-2 per team. The role of a row is
taken from the hero the portrait bar gives for that slot, **not** from a legend —
in the slot layout the three legends sit together at the top and no longer label
their block.

**`MATCH TIME` is the read's timestamp**, and two reads that share one are the
same moment: the second is rejected rather than stored as a zero delta.

**Occlusion is its own failure, not a misread.** Overwatch's replay events panel
covers exactly the left column — verified in a real frame, where it hid the whole
block behind `JAVI / ALL EVENTS / ROUND 1`. Detect it by its own text and by the
absence of the `MATCH TIME` anchor, and say *"the replay events panel is covering
the board — close it and read again"*. Moving the block is not an escape: the
kill feed owns the top-right and the objective UI owns the centre.

## 5. The record

Stored per map, alongside the existing comps and bans:

```
board_reads: [
  { round: 1, match_time: "3:41", rounds_covered: 1, layout: "slot",
    rows: [ { slot: 0, team: "a", k, d, dd, dt, x, uu }, ... ten ... ],
    raw: "<the OCR text>" },
  ...
]
```

`x` is the role-specific sixth column, stored unlabelled: what it means follows
from the slot's hero, which the comp read already knows, and labelling it at
capture time would bake today's inference into tomorrow's data. `raw` is kept
for the same reason every other read keeps it — a parser improvement can be
re-run against it.

The first read of a map establishes the baseline. It is normally zero (a map
starts at zero and the operator's own frame confirms it), but a capture that
joins mid-map has a non-zero one, so `from_start: false` marks it rather than
pretending the first delta is a round.

## 6. Testing

- Pure-parser unit tests for the slot layout, mirroring the existing
  role-grouped ones: ten rows, the five/five colour split, a `%` in the wrong
  column, a missing `MATCH TIME`, and the events-panel text as an occlusion case.
- Delta arithmetic tested directly: consecutive reads, a skipped round, a
  mid-map baseline, and a repeated `MATCH TIME`.
- The browser verifier gains a check that a blocked advance stays blocked until
  Skip is pressed.
- **What none of it proves** is the OCR read against a real replay of a
  slot-ordered board, which needs a scrim played after the setting is changed.
  That is the same gate the ban row is still waiting on, and it cannot be closed
  at a desk.

## 7. Out of scope

- The hero-glyph reference set, and per-player attribution on role-grouped
  replays — the operator's decision, §1.
- ~~Any change to `scrim_owdb.opy`.~~ **Reversed the same day.** The operator
  is re-publishing the mode from their main account, so a build was happening
  anyway: the row now carries the player's name (see §4), the ban chord became
  hold-to-confirm, the row text moved out of the HUD string onto a timer, and
  slot ordering became the default. `scrim_owdb.txt` is rebuilt and ready to
  paste; the share code it produces is new, because a workshop code cannot
  change owner.
- Phase 4's Players tab, which consumes this and is its own piece of work.

---

## 8. What the workshop HUD will and will not do (measured 2026-09-06)

Five rebuilds went into finding these. They are properties of the renderer, not
opinions about layout, and every one of them was learned by measuring a real
spectator frame after a design built on the opposite assumption failed.

- **Every line is CENTRE-aligned.** In one frame six lines' left edges spanned
  67 pixels while their centres all landed within three of each other. Columns
  therefore only line up when every row is the same LENGTH.
- **Runs of spaces are collapsed at render time.** The compiled output carries
  the literal `"      "` strings, so the mode sends them and the game discards
  them. Only a visible character can hold a column open, which means zero
  padding, which reads worse than the raggedness it fixes.
- **A name cannot be padded at all.** There is no runtime string length (`len()`
  compiles to Count Of, which counts array elements) and no substring or slice
  action. Numbers can be padded because their magnitude is knowable; names
  cannot.
- **`hudSubtext` is LARGER than `hudSubheader`.** The Size setting maps Small to
  hudSubheader and Medium to hudSubtext, which says so plainly. Pinning the
  column key to hudSubtext to make it "one size down" made it the biggest thing
  on the board.
- **The Size setting barely changes glyph height.** Line height measured 15px on
  Small and 15px again after switching to Medium. Large (`hudText`) is the only
  untested size lever, and glyph size remains the likeliest cause of the digits
  that weld together.
- **`+` is not concatenation.** In the Workshop it compiles to Add, so a string
  operand coerces to 0 and every pad silently evaluates to nothing. String
  building is `format()`, and only `format()`.

### 8.1 Colour is luminance, and one team colour had none

The claim that "colour was what separated the lines that read from the lines
that did not" was overstated when it was first made, and the operator was right
to challenge it. Measured properly - per row, across five frames, with the team
classified from the pixels and the background luminance controlled:

| rows | text luminance | background | contrast | numbers recovered |
| --- | --- | --- | --- | --- |
| team red | 53.8 | 78.4 | 24.6 | 3.40 / 6 |
| team blue | 155.8 | 80.5 | 75.3 | 4.55 / 6 |
| white | 249.2 | 133.5 | 115.7 | 5.39 / 6 |

The dose-response is clean, so colour is real. But blue had three times red's
contrast and still landed only 30% of rows fully correct, and white at the best
contrast of all still averages 5.39 of 6 - so colour was never the whole story.
The residue is adjacent numbers welding into one token (`0017100169`), which is
a glyph-size problem.

On a dark map the same measurement is brutal: team red came back at **6.4** of
contrast - the text darker than the background behind it - recovering 2.75
numbers per row against blue's 5.00 in the same frame. `rgb(250,5,30)` is a dark
colour wearing a bright one's name. It went to `rgb(255,135,140)` at luminance
161, matching blue's 160, so both sides are equally readable. That lift worked
and overshot — at blue 140 it reads as pink — and it is now `rgb(255,90,75)`
at luminance 124 — **and 8.3 shows the rule below inverts on a bright map, so
read the two together; neither is general on its own.**

**The rule this leaves behind:** spend hue where the parser does not look (the
column key, which is recognised only in order to be skipped) and keep luminance
high everywhere it does (the rows, BANS, MAP, MATCH TIME).

### 8.2 The ban read depended on a colon, and OCR eats colons

A frame whose gold `BANS` heading OCR'd perfectly - label, both hero names, the
accent folded - still failed with "could not find the BANS row on screen".
`findRow` required a colon, and the read had lost it. The module's own header
calls the label a textual anchor and explains that the crop therefore need not
be precise; the code did not honour that. There is now a colon-free search
behind the exact one, anchored on the first WORD so `BANSHEE` cannot stand in
for `BANS`. The frame's verbatim OCR is a test.


### 8.3 On a bright map the board is not read at all, and the fix is capture-side

Every measurement in 8.1 was taken on dark maps, where the background luminance
sat at 78–133. Two Busan frames on 2026-09-06 (`151426`, a white lighthouse
interior; `151437`, open sky) put the background at **200–255**, above every
text colour on the board, and the shipped read collapses:

```
                          values      complete rows
shipped crop (colour)     27 / 96        0 / 16
```

Zero complete rows. The failure mode is specific and worth naming: the bullet
separator `•` and the digit `0` both come back as `©`, and the tokenizer treats
`©` as a separator, so **every zero on the board is deleted rather than
misread**. `ASHE • 2 • 0 • 419 • 48 • 46% • 0` arrives as
`ASHE © 2 © © © 419 © 48 o 4% © ©`. A row that loses values positionally is
exactly the case `fields` exists to refuse, so nothing wrong was stored — the
board simply went unread.

**This is not a colour problem and cannot be fixed with one.** No text colour is
simultaneously darker than a white building and lighter than a dark map. It is a
preprocessing problem, and preprocessing is the half of this the tool controls.

Seventeen variants, both frames, scored on the same 96 values:

| variant | values | complete rows |
| --- | --- | --- |
| **saturation channel** (`255 − 1.6·(max−min)`) | **66 / 96** | **7 / 16** |
| adaptive local saturation, r=6 | 49 / 96 | 4 / 16 |
| grayscale luminance | 35 / 96 | 2 / 16 |
| shipped raw crop | 27 / 96 | 0 / 16 |
| global luminance threshold | 8–28 / 96 | 0–3 / 16 |

The saturation channel wins because the board is saturated and most map pixels
are not, which holds whichever side of the text the background's *luminance*
falls on. On `151426` it reads seven of eight rows perfectly, TEAM 2 included.

Two things it does not fix, both measured rather than assumed:

- **A character whitelist makes it worse, every time** — 59/96 against 66/96,
  and worse in fourteen of sixteen pairings. It was tried because `©` for `0`
  looks like exactly the error a whitelist should forbid. Tesseract does not
  substitute the nearest allowed glyph; denied its first choice it degrades the
  whole line. Do not re-try this.
- **`151437` (open sky) still fails for TEAM 1 only** — 0–3 of 6 per blue row
  while the red rows get 4–5. The sky is saturated cyan, so team blue is
  competing with a background of its own hue in the very channel that rescues
  everything else. If one team colour is to move next, the evidence points at
  **blue**, not red.

#### 8.1's rule inverts on a bright map, which is why no colour can fix this

Colours were scored by recolouring the real TEAM 2 rows in place — the real
font, the real background, the real dark outline, only the glyph colour changed
— so a colour costs an offline run instead of an in-game round trip
(`alpha = (P−B)·(T−B)/|T−B|²`, recomposite with the candidate; pixels off the
B→T line are left alone, which keeps the outline and the blue rows out of it).

A luminance ladder on these two bright frames, against 8.1's dark-map numbers:

| text luminance | raw crop | saturation pass | dark map (8.1) |
| --- | --- | --- | --- |
| 54 — `rgb(250,5,30)`, the original | **18 / 48** | 28 / 48 | **2.75 / 6 — worst** |
| 97 | 14 / 48 | 29 / 48 | |
| 124 — `rgb(255,90,75)`, shipped | 15 / 48 | 29 / 48 | |
| 161 — `rgb(255,135,140)`, previous | **18 / 48** | **30 / 48** | **5.00 / 6 — best** |
| 196 | 8 / 48 | 25 / 48 | |
| 228 | 7 / 48 | 18 / 48 | |

**The order is inverted.** The colour 8.1 measured as unreadable is joint-best
here, and the brightest are the worst, because on a white map the board needs to
be *darker* than its background rather than brighter. Both measurements say the
same thing — contrast, not colour — and they disagree about the sign because the
maps do.

So **8.1's rule ("keep luminance high everywhere the parser looks") is not
general; it is the dark-map half of a rule whose other half is its opposite.**
No fixed value satisfies both, which is the argument for moving the fix to the
capture side: the preprocessing change is worth 27 → 66 of 96 on these same
frames, larger than the entire luminance range above.

A caution against over-reading this table, recorded because it is the mistake
that was made here first: an earlier sweep of eight *reds* spanning pink to deep
red scored 12–18/48 raw and 28–33/48 saturated and was written up as "hue does
not matter to OCR". It does not show that. Those eight all sat at luminance
97–161 — a band that is flat in the table above — so it measured hue at roughly
fixed brightness, on frames where every candidate was on the same side of the
background, and generalised it to colour. Within a flat band, hue is free; that
is the whole of what was demonstrated.

What luminance 124 buys is the middle of both readable bands rather than the
optimum of either: 54 is the failure on a dark map, 196+ the failure on a light
one, and 69–161 is indistinguishable here. That is what leaves the pink-versus-
red call free to be made on how it looks to the operator, which is how it was
made.

#### What this changes

`readScoreboard()` in `scrim.html` hands `scoreCanvas()`'s raw colour crop
straight to tesseract. The measured change is to read the saturation channel
instead — or, following the replay-code precedent in
`tools/real_frame_eval/README.md`, both, since neither wins on every frame.
Unlike the code reader this cannot demand agreement between passes to accept a
value; the board is ten rows and they fail independently, so the merge rule is
the open question and it is not answered here.

Not yet done. Two frames, one map, one lineup — enough to show the shipped path
fails on a bright map and that the fix is capture-side, not enough to fix the
capture path against.

### 8.4 The correction: the map moves more than the colour does

8.3 was measured on two Busan frames and its conclusion — that the shipped read
collapses — was stated as though it were about the board. It is about *Busan*.
Three real frames, real white rows, no recolouring, all through the shipped
capture path with no preprocessing changes:

| frame | background | values | complete rows | names | teams / time / bans |
| --- | --- | --- | --- | --- | --- |
| Nepal `154354` | flat dark surfaces | **45 / 48** | **6 / 8** | 8/8 | all correct |
| Blizzard World `143627` | lantern-lit roof, high detail | 18 / 48 | 0 / 8 | 8/8 | none |
| Busan `151426`/`151437` | white interior, bright sky | *(team colour: 27/96)* | 0 / 16 | — | partial |

**Nepal is the best result anything has produced on this board**, and it is the
plain shipped path — no saturation pass, no whitelist, no ladder. The two
misses are both `O`-for-`0` in the trailing ULT column, a glyph confusion.

So the colour work in 8.1–8.3 was chasing the wrong variable. Same colour, same
font, same code, same resolution, a 2.5× spread from **background alone** —
because the HUD draws this text on no plate, straight over the world. Every
colour ranking measured so far has reversed itself on the next frame set, and
this is why.

**The methodological error is worth naming, because it was made twice.** Both
team-colour experiments were measured against whatever frames arrived next, and
each new frame set came from a different map. A colour was credited or blamed
for a difference the map had caused. The rule that follows: **hold the map fixed
or do not attribute the difference to the colour.** Two frames of one map is not
a measurement of a colour, and neither is one frame of each of two maps.

There is a second error here specific to how 8.3 was produced: real frames with
real white rows already existed (`143627`, and later `154354`) and were not
used. White was *simulated* by recolouring coloured rows, and the simulation was
then reported as the verdict on white. The simulation is faithful as far as it
goes, but a real frame was available and is the better evidence.

**Conclusion: keep the rows white.** The remaining problem is Busan-shaped and
capture-side — a bright or busy background, which no text colour fixes — and
that is where 8.3's preprocessing work belongs.

### 8.5 The column key was being read as a DPS legend

Found while scoring the Blizzard World frame. The mode draws one column key,
`PLAYER • K • D • DMG • TKN • ACC/BLK/HEAL • ULT`. It contains the token `ACC`,
which is the DPS legend's marker, and `legendRole()` asked only for the marker,
four-plus tokens and no digits — so the key satisfied it.

`isColumnHeader()` exists to catch exactly this line, but `parse()` tested it
*after* `legendRole()`, so it never ran. Two fixes, because the first is not
enough:

1. **Order.** `isColumnHeader` now runs first. That covers an intact key.
2. **`legendRole` was too loose.** On this frame `ULT` OCR'd as `ALeuT`, so the
   header test failed while `ACC` survived and fired the legend test anyway. A
   legend must now also carry `DD`, `DT` or `UU` — the key says `DMG`/`TKN`/`ULT`
   and shares only `K` and `D`, so the two separate cleanly. A legend that loses
   all three to OCR is not recognised, and the board reports no role rather than
   the wrong one.

The damage it did: on a frame whose `TEAM` headers did not survive, that single
miscount set `layout: 'role'`, which suppressed the five/five team split and
tagged all five surviving rows `dps` with `team: null`. Confidently wrong, which
is the one outcome §3 says this parser exists to avoid. It now returns
`layout: null` with every role `null`. Nepal is unchanged. Four regression tests,
verbatim from the frames; 30/30 pass.

### 8.6 The controlled experiment, and what it overturns

8.4 ended by saying that no colour measurement means anything unless the map is
held fixed. This is that experiment, and it required nothing from the game but
patience: **one board, paused, screenshotted eight times from eight camera
angles.** The text is byte-identical in all eight — same stats, same
`MATCH TIME: 3:02` — so the background is the only variable there is.

Colosseo, ten bots plus the operator, 2026-09-06. Background medians span the
whole usable range:

| frame | background | luminance | saturation |
| --- | --- | --- | --- |
| `202453` | black | 0 | 0 |
| `202412` | dark interior, flat | 16 | 4 |
| `202431` | dark, strongly saturated | 79 | 106 |
| `202447` | mid, saturated | 111 | 76 |
| `202418` | mid-bright stone | 155 | 36 |
| `202425` | bright saturated sky | 185 | 126 |
| `202507` | bright, unsaturated / white | 187 | 10 |
| `202439` | bright saturated | 193 | 76 |

Truth, harness and scoring live in `tools/real_frame_eval/`
(`scoreboard_truth.json`, `scoreboard_crop.py`, `scoreboard_eval.js`), so unlike
every measurement in 8.1–8.3 this one is reproducible by anyone with the frames.

#### 8.3's recommendation is withdrawn

**The saturation channel does not work on the board we ship, and cannot.** It
separates board from map by assuming the board is the saturated thing on screen.
That was true when the rows were team-coloured. The rows are white now, and
white is the least saturated colour there is, so the channel erases precisely
the text it was introduced to rescue. On `202412` its output is complete and
damning:

```
BANS : NONE
MAP : COLOSSEO
PLAYER * K * D * DMG ¢ TKN * ACC/BLK/HEAL « ULT
TEAM 1
TEAM 2
```

Four chrome lines, which are orange and survive; **zero of ten rows.** Across
all eight frames it scored 80/480 values against the shipped path's 109.

This is not a new mistake, it is 8.4's mistake again: 8.3 measured a preprocessor
against frames whose rows were coloured and reported the result as a property of
the preprocessor. The rule holds in both directions — hold the board fixed too.

#### What actually works: local contrast on luminance

The rows are white, i.e. maximum luminance, and the failure case is a *bright*
background. So the question worth asking a pixel is not "are you bright" but
**"are you brighter than what immediately surrounds you"** — which is the one
question a global threshold cannot answer on text drawn over an uncontrolled
world.

Luminance minus its own local mean (box blur r=12), gain 6, inverted to
dark-on-light:

| frame | shipped raw | **localg6** |
| --- | --- | --- |
| `202412` | 30 / 60 | **48 / 60** |
| `202418` | 0 | **12** |
| `202425` | 0 | **24** |
| `202431` | 42 | **54** |
| `202439` | 5 | **18** |
| `202447` | 14 | **17** |
| `202453` | 18 | **53** |
| `202507` | 0 | **60 / 60 — every value, every name, every team** |
| **total values** | **109 / 480** | **286 / 480** |
| **complete rows** | 16 / 80 | **45 / 80** |
| **names** | 19 / 80 | **45 / 80** |
| **match time** | 7 / 8 | **8 / 8** |

**2.6x, no frame regresses, and three frames go from completely unreadable to
readable.** `202507` — a white background, the case 8.3 correctly identified as
hopeless for any text colour — goes from nothing to a perfect read.

Three controls establish *why* it wins rather than just that it does:

- **`gray`** (plain luminance, 82/480) — the win is not merely dropping colour.
- **`lumhi`** (hard global bright threshold, 118/480, and **5/80 teams**) — the
  win is locality, not a bias toward bright pixels. A global bright cut also
  erases the coloured TEAM headers entirely, which is what the teams column says.
- **`tophat`** (morphological white top-hat, 86/480) — locality helps; this
  particular morphology does not, at r=11.

Both parameters are measured. Radius at fixed gain (6/12/20) gave 236/239/235 —
flat, so it need only be roughly glyph-scale. Gain at fixed radius (4/6/8/12)
gave 239/**286**/225/160, a real peak: below it faint strokes never reach ink,
above it background texture does. **In `scoreCanvas()` the radius scales with
crop width**, because a glyph is only ~12px on a 2560-wide capture and a fixed
radius would be wrong at any other resolution.

#### What it does not fix

The pass optimises for the white rows, which is the data. **The orange chrome
comes out worse** — `BANS`, `MAP`, the column key and the TEAM headers are all
mid-luminance colour, and they degrade (`ANS : NONI NE`, `LAYER ) ® DIG TIN`).
That is the right trade, but it means the board's own labels are no longer
something the parser can lean on, which is what makes 8.7 necessary.

Residual failures at value level are glyph confusions rather than contrast:
`O` for `0` is the most common by far, and a lost separator welds two values
into one (`138 • 0` → `1380`), which is the dangerous kind because it is silent.

### 8.7 One surviving TEAM header was worse than none

Found by the same frames. On `202431` the OCR is otherwise near-perfect, but
`TEAM 2` came back as `BAM 2`. The consequence was that **all ten rows reported
`team: 'a'`** — five of them confidently wrong.

The cause is that `parse()` already had the right idea and applied it too
timidly. A ten-row team-grouped board is five and five in slot order, and the
parser knew that, but only used it to fill a `null`. Here `TEAM 1` *had* read,
so `currentTeam` was still `'a'` when rows six to ten were parsed and every one
of them inherited it. Nothing was null, so the fallback declined to act.

**Position now overrides the headers outright when there are ten entries.** That
cannot disagree with headers that both survived — where they are right they say
exactly this — and where they are not, position is the more reliable of the two,
because it does not depend on OCR recovering coloured text, which is the first
thing OCR loses. Ten rows only: a nine-player lobby has no five/five to appeal
to, and there the headers are all there is.

This matters more after 8.6, not less. The local-contrast pass deliberately
trades the coloured chrome for the white rows, so the headers are now *expected*
to read poorly and the parser must not depend on them.

Two regression tests, one for the half-read board and one asserting the override
agrees with a fully-read one; 32/32 pass.

### 8.8 The scorer was measuring the wrong thing, and the round-letter zero

Two corrections and one fix, all from the same eight frames.

#### The harness understated the read, because it joined by name

`scoreboard_eval.js` originally paired a parsed row to its truth row by fuzzy
NAME match, and discarded any row whose name OCR'd too badly to pair. **That is
not how the tool joins.** Section 1 is explicit: row *i* is slot *i*, the
spectator portrait bar is in slot order too, and the join needs no name at all.
A row whose name came back as garbage is not lost in production; only its label
is, and the label was never load-bearing.

The harness now reports both. The name-matched score stays, because it is the
right diagnostic for name OCR specifically. The **positional** score is the one
that describes production, and it is reported only for frames that yielded
exactly ten rows — with nine, nobody knows *which* is missing, so every row below
the gap would attach to the wrong player and the frame has to be refused rather
than guessed at. Refusing is the correct behaviour, so the metric counts it.

#### A zero in the kills column is a round LETTER, and not always the same one

The single most common OCR error on this board, by a wide margin. Across the
eight frames a `0` comes back as `O`, `Q`, `QO` or `OQ`, and the two-character
welds are the expensive ones:

```
BASTION » 1 «QO » 585 ¢« 276 » 37% + 0     row DROPPED - one number banked,
                                            then QO, then under the 4-column
                                            minimum
REAPER  * OQ « 3 « 701 = 915 + 13% « 0     row SHIFTED - k reads 3, truth is 0
```

`zeroise()` rewrites these, and three details each cost something:

- **It anchors on the stats TAIL, not on the first digit.** A row whose first
  stat is a zero puts the offending letter before every digit on the line, so a
  digit anchor cannot see the value most likely to be a zero.
- **It replaces the WHOLE token.** Overwriting the first character of `QO`
  leaves `0O`, which is still not a number and still loses the row. The
  remainder is blanked to a space, which tokenize treats as the separator that
  should have been there.
- **It is restricted to O and Q.** `co` and `ce` appear on the same lines and
  are misread *separators*; turning one into a zero invents a column.

Deliberately not extended to `l`/`I` for 1 or `S` for 5. Those occur INSIDE
multi-digit numbers, where a substitution invents a plausible stat instead of
failing loudly. A round letter alone in a numeric column is certainly wrong; a
letter inside a number is only probably wrong, and this parser errs toward
silence.

#### Where that leaves the read

| | frames accepted | values | complete rows |
| --- | --- | --- | --- |
| raw crop, before any of this | 2 / 8 | 88% | 11 / 20 |
| **local contrast + zeroise** | **7 / 8** | **90%** | **53 / 70** |

**The preprocessing did not make individual reads much more accurate — it made
three and a half times as many frames readable at all.** Per-frame accuracy on
an accepted frame was already 88%; what changed is how often the board is
legible enough to accept.

The one frame still refused is `202418`, which yields eight rows. Its background
is mid-bright stone at high detail and the losses are two rows destroyed by
background texture welding into the glyphs, not a systematic error with a rule
behind it. Frames from a second map are worth more now than further tuning
against this one.

#### What is no longer worth doing

- **Splitting fields on word bounding boxes.** This was the planned next step,
  to defend against a lost `•` welding two values together. After `zeroise`
  there are **zero** rows with fewer than six fields across all eight frames -
  the missing fields were the dropped round letters all along, not lost
  separators. The problem it was going to solve does not currently exist.
- **A two-pass merge of raw and local contrast.** Measured at +10 values and
  +1 row for double the OCR cost. Section 8.3 left the merge rule as an open
  question; the answer is that it is not worth asking.

## 9. Locating the board: capture markers

The crop is not forgiving. Section 8.8's read assumes the box is the board's
true extent, and it is worth stating what happens when it is not — same frames,
same preprocessing, margin added on all four sides:

| box | frames accepted | values |
| --- | --- | --- |
| true extent | **7 / 8** | **343 / 480** |
| +10% | 4 / 8 | 300 |
| +25% | 5 / 8 | 298 |
| +50% | 4 / 8 | 194 |

**"Roughly the right area" is not good enough**, and `boxes.scoreboard` is drawn
by hand — so every capture currently depends on a host dragging an accurate
rectangle over a HUD element. That is the weakest link in the path.

Three ways to remove it were considered:

- **Fixed fractional offsets from `boxes.a`**, as `code_box()` already does for
  the replay code. Free and retroactive, but the board's height is not fixed —
  it moves with the Size setting and with how many lines are drawn — and the
  table above says the slack needed to cover that is expensive.
- **Self-locating**: profile the ink and crop to its bounding box, the way
  `rowfind_proto` finds the name rows. Free, retroactive, adapts to any layout.
  Rejected in favour of the third only because the operator does not need the
  retroactivity and preferred the simpler detector.
- **An in-game marker** — chosen. Costs a workshop change and a re-upload, and
  only works from the next lobby onwards, both of which the operator accepted
  explicitly.

### What the markers are, and why each choice

Two bars of 56 `●`, drawn at sort 0.1 and 4.5, spectator-and-replay only, behind
`5. Spectator Scoreboard > Draw Capture Markers` (default on).

- **Green `rgb(40,205,60)`** — the only colour in the mode's palette that nothing
  draws on the spectator view during a game. Blue and red are the TEAM headers,
  orange is the chrome, white is the rows; this green is used solely by the
  ready-up list, which is setup-only. No new colour, nothing to collide with,
  and it reads as part of a deliberate palette rather than a debug artifact.
- **A run of dots, not a hue** — this is what keeps green safe. Foliage is green;
  foliage is also textured, and nothing on an Overwatch map draws a
  56-character uniform horizontal bar. **The detector must key on the RUN, not
  the colour alone.** U+25CF specifically because the ready-up list already
  renders it in this mode, so it is known to exist in the font rather than a
  guess that costs an in-game test to disprove.
- **56 wide** — every HUD line is centre-aligned, so a bar wider than the widest
  line bounds the board horizontally as well as vertically, and two bars are a
  whole box. The widest line is the column key at 47 characters. Overshooting
  costs a little background either side, which the local-contrast pass handles;
  undershooting would clip the key and the longest rows.

The tool crops **strictly between** the two bars, so the markers never enter the
image handed to OCR and cannot contribute junk lines of their own.

### Not yet built

The detector. It needs frames that HAVE markers, which do not exist until the
mode is rebuilt and uploaded, so the order is: ship the workshop change, capture
two or three spectator frames, then tune the locator against them. Until that
exists the manual box remains the only path, and it stays as the fallback for a
host who switches the markers off.

### 9.1 Dots were ugly; a progress bar is a line

The first build drew each marker as 56 `●` of hud text. It worked exactly as
designed - solid, green, comfortably wider than the widest board line - and it
looked like debug output smeared across the spectator view, which is a view
humans actually watch. Rejected on sight, correctly.

**`progressBarHud` draws a real filled rectangle**, and its `text` parameter is
documented as "can be blank", so value 100 with no label is a clean line and
nothing else. The mode already used it for the ready and ban hold bars, so it
was proven in this code before it was used here.

Screen-space is the constraint that makes this the only alternative. The
Workshop's other drawing actions - `createIcon`, `createEffect`,
`createInWorldText`, and the in-world progress bar - all place things in the
WORLD, so they move with the camera. A spectator camera moves freely, so
anything world-anchored is useless as a screen-space marker. Hud text and
progress-bar hud text are the whole of what can be pinned to the screen.

The change also made the detector's job easier rather than harder: a solid bar
is one uniform block with straight edges, where 56 dots are 56 small blobs
separated by background.

**One thing it gives up.** A text bar bounded the board horizontally by being
wider than the widest line. A progress bar is a fixed HUD width, so it cannot be
relied on for that. The detector therefore takes only the vertical bounds from
the bars - which is the hard half - and finds the left and right edges by
profiling ink inside that band, which is easy once the rows are known to be rows.

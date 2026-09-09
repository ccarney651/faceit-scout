# Capturing hero references from a workshop lobby — an idea, not a plan

**Status: recorded, not designed and not built.** Written down on 2026-09-10 so
it is not lost. Nothing here has been measured.

## The problem it would solve

The HUD matcher recognises heroes by comparing a portrait crop against a library
of reference crops — 53 heroes × 2 side variants = 106, in
`docs/capture/refs.json`, generated from `owdb.sqlite3`'s `hero_refs`.

Every one of those references was grabbed **by hand, in-game, from whatever
frame happened to be available**. That has three costs:

1. **A bad reference is invisible.** D.Mon's side-A reference was wrong, and the
   matcher read D.Mon as Mei 32 times, Moira 7 and Brigitte twice across the
   retained frames — every appearance, on three of five league maps. Nothing in
   the output said so; the cell simply carried a plausible hero at a mediocre
   score. It was found by a person looking at `verify_sheet.js` output.
2. **A new hero is a chore.** Overwatch adds them steadily — this corpus already
   contains Mizuki, Shion, Vendetta, Jetpack Cat, Anran, Freja, Hazard, Juno,
   Wuyang, Sierra, Domina and D.Mon. Each needs the operator in-game, and
   `AGENTS.md` lists the four places a new hero must be registered.
3. **Colourblind modes are completely uncovered, and this is the real reason.**
   References are stored *per side* precisely because the team-coloured plate
   behind a portrait changes what the crop looks like. Colourblind mode changes
   exactly that colour. If an operator runs one, every reference is subtly wrong
   for them and **nothing would report it** — the same shape as the D.Mon fault,
   across the whole library at once. No frame in the corpus was captured in a
   colourblind mode, so we do not know how large the effect is.

## The idea

The operator's suggestion: a **workshop mode plus a driving tool** that puts ten
bots on screen and cycles every hero through every slot on both teams, while the
bot captures frames. One run yields the full library, consistently lit and
consistently cropped. Re-run it per colourblind mode for the variants.

The workshop half is the operator's — `tools/scrim_code/` already holds workshop
code for this project, and the HUD limits are recorded in memory and AGENTS.md.
The capture half is `grab.js` plus a chunk driver, both of which exist.

## The caveat that must be tested first

**This project already learned that a workshop lobby is not a league replay.**
`frames/README.md` says of the bootstrap frame:

> a **workshop lobby**, not a league replay — placeholder entity names, and an
> unrepresentative hero spread. Fine for validating crop geometry; poor for
> judging matcher confidence.

So references captured in a workshop may not match how a portrait looks in a
real game — different skins, different ult-charge states, different plate
rendering. A library that is beautifully consistent and subtly wrong would be
worse than the hand-grabbed one, and would fail the same silent way.

**That is testable rather than assumable, and the corpus to test it now
exists.** Capture a workshop library, then score it against the ~150 retained
real-game sample frames with the existing tooling:

- `corpus_sweep.js` for the detector readings
- `score.js` for accuracy against owreplays' event streams, where a key exists
- the bad-reference sweep — a cell unsure on its own side and confident on the
  other — which found D.Mon and nothing else

If workshop-captured references score at least as well as the current library on
real frames, the tool is trustworthy and adding a hero becomes a five-minute
job. If they do not, we have learned that cheaply and kept the hand-grabbed ones.

## What would need deciding

- Whether a workshop bot's portrait is pixel-comparable to a real player's.
- How ult charge, health state and skins affect the crop, and whether the
  reference should be captured in a specific state.
- Whether every colourblind mode needs its own full library, or whether a
  transform of the existing one is enough.
- Where per-mode libraries would live — `hero_refs` has a UNIQUE constraint on
  `(hero_guid, profile_id, state, variant)`, so a mode would likely be a new
  profile rather than a new variant.

## Why it is not urgent

The audit that found D.Mon found **one** bad reference out of 106, and that
signature is now swept automatically. The library is not rotten. This is about
making the *next* hero cheap and closing the colourblind blind spot, not about
repairing what is there.

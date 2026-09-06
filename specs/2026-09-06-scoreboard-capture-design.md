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
no recompile and no re-upload, and `B4GM8` stays as it is.

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

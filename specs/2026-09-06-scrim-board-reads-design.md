# Scrim board reads — design

**Date:** 2026-09-06
**Status:** design, agreed with the operator in conversation; not yet planned or built.
**Amends:** `specs/2026-09-06-scoreboard-capture-design.md`. That document decided
*what* the read is and *why* the slot ordering makes it possible. This one covers
the capture flow around it, and **supersedes its §1 on one point**: the join is
name-first, position-fallback, not the other way round (§3 below).

## Goal

Per-player stats for every round of a scrim map, read off the workshop spectator
scoreboard at the boundaries the operator crosses anyway, and stored so that a
later improvement to the arithmetic applies to captures already taken.

The user-visible flow this serves, in the operator's own words: open the site,
pick Scrims, pick Capture, be told to use the right workshop code, share the
screen, calibrate, capture round by round, finish each map with its stats read,
and save the scrim ready for analysis.

## 1. What was verified on 2026-09-06, and what was not

The 2026-09-06 capture design asserted the slot ordering. It is now confirmed
from source rather than assumed, because the whole positional half of the join
rests on it.

**The sort key** (`scrim_owdb.opy`, "Scoreboard: Build Row Text"):

```
Scoreboard_Sort = (getSlot() if GroupMode == 0 else <role>) * 0.1
                  + (2 if team == Team.1 else 3)
```

`GroupMode 0` is `"Group by team, sort by slot"`, and it is option 0 — the
default. It is present in the built `scrim_owdb.txt`, so the live share code has
it. The key therefore resolves to:

| team | slots 0-4 | sort values | rows |
| --- | --- | --- | --- |
| Team 1 | 0,1,2,3,4 | 2.0 2.1 2.2 2.3 2.4 | 1-5 |
| Team 2 | 0,1,2,3,4 | 3.0 3.1 3.2 3.3 3.4 | 6-10 |

So **row *i* is slot *i*, Team 1's block first**. `getSlot()` is the per-team
slot (0-4 in a team mode), not a global 0-9, which is exactly the shape the join
wants.

**The parser already handles the live row format.** The built row is
`NAME • K • D • DMG • TKN • X • ULT` — name first, bullet-separated, **no
colon**. The earlier design made the colon load-bearing for numeric-name safety;
that is no longer true and no longer needed, because `scoreboard.js` anchors on
the K/D pair rather than on punctuation. Run against the live format it returns
ten rows, a five/five team split, six fields each, `x` stored unlabelled, and
correct names — including an all-digits `1337` and a digit-suffixed `TANK 1`.
No parser change is required for the name.

**What is NOT verified, and cannot be from this repository:** that the spectator
*portrait bar* renders left-to-right in slot order. That is Overwatch's own HUD,
not the workshop's. It needs one in-game confirmation, and it is a gate on the
positional fallback only — not on the primary join, which is why §3 inverts them.

**What is known to be unreliable:** which screen strip is which team.
`boxes.a` is "the left five portraits", a screen position; Team 1 is a game
concept. A spectator changing POV in a replay can flip the mapping, which is why
the capture page already carries side radios and a *Swap teams* button. Nothing
should treat left-equals-Team-1 as a fact.

## 2. The record

`board_reads` replaces the single `scoreboard` blob on the scrim map record:

```
board_reads: [
  { round: 1, match_time: "3:41", rounds_covered: 1, from_start: true,
    layout: "slot",
    rows: [ { slot: 0, team: "a", player: "LEXRR", joined_by: "name",
              k, d, dd, dt, x, uu }, ... ten ... ],
    raw: "<the OCR text>" },
  ...
]
```

Every read is stored **raw and cumulative**. The board accumulates over the map,
so a round's stats are the delta between consecutive reads — and that
subtraction happens **at analysis time, never at capture time**. This is the
rule the contribution merge already follows: store observations, derive reports,
so an improvement to the arithmetic applies retroactively to every capture
already taken.

`x` stays unlabelled. What the sixth column means follows from the slot's hero,
which the comp read already knows, and labelling it at capture time would bake
today's inference into tomorrow's data.

`joined_by` records `"name"` or `"slot"` per row, so a later audit can tell an
identified row from an inferred one without re-running anything.

`from_start` marks whether the first read of a map is a true zero baseline. It
normally is; a capture that joins mid-map has a non-zero one, and saying so beats
pretending the first delta is a round.

`rounds_covered` is how a skip is absorbed: a skipped read loses the boundary,
not the stats, and the next successful read legitimately spans two rounds. The
record says so rather than attributing it all to one.

`round` is the round the read **closes**, not the one it opens — so the Finish
map read carries the final round's number, and a map of three rounds yields
reads numbered 1, 2, 3. There is no separate baseline read: §4's two triggers
are the only ones, and the first read of a map is round 1's cumulative total,
which is round 1's stats outright with nothing to subtract.

`from_start` is a flag on that first read, not a read of its own. It is true
when the capture session began at round 1, and false when the operator joined a
map already in progress — in which case the first read's values include rounds
nobody observed, and no delta from it is attributable to a single round.

## 3. The join: name first, position second

The 2026-09-06 design made slot position primary and the row's name insurance.
The measurement in §1 inverts that, because the name now parses reliably and the
position rests on an unverified HUD assumption plus a team-to-strip mapping known
to be flippable.

Per row, in order:

1. **By name.** Match the row's name against the portrait bar's player names for
   that read, fuzzily — both sides are OCR. On a match, `joined_by: "name"`.
2. **By slot position.** Row *i* to slot *i* within its team's block.
   `joined_by: "slot"`.
3. **Neither.** The row is stored with `player: null`. It still carries team and
   its stats, which is enough for team-level and comp-level analysis.

**Step 2 needs a Team-1-to-strip mapping, and none exists today.** The board
knows `TEAM 1` and `TEAM 2`; the capture page knows *us* and *them* and which
strip is on the left; nothing maps between them. `banrow.js` hit the same wall
and resolved it by refusing to attribute a ban to a side at all.

The mapping is **derived from step 1, not configured**: if any row in the
`TEAM 1` block name-matches a player in the left strip, Team 1 is the left strip
for this read, and the unmatched rows in that block fall back positionally
against it. Conflicting evidence, or none, means step 2 is unavailable and those
rows go to step 3.

This is why the join order matters beyond the individual row: the name matches
bootstrap the positional fallback for the rows that had none. A read where no
name matches at all yields team-level stats only — which is the honest outcome,
not a degraded one.

A **role-grouped** board (`layout: "role"`) attributes to team and role only,
never to a player. Honest partial data beats a coin-flip, and every replay
recorded before the current share code renders that layout — nothing done now
changes those.

Layout is detected from the read itself, never from a stored setting. A setting
the operator can change mid-session and the tool cannot see is a desync waiting
to happen.

## 4. When a read happens

On **Next round** and on **Finish map**, never on a timer. In a replay the
operator controls time, so the authoritative frame is the one they scrubbed to,
not whatever a five-second timer caught.

`MATCH TIME` is the read's identity. Two reads sharing one are the same moment:
the second is **rejected** rather than stored as a zero delta.

## 5. Occlusion is its own failure, not a misread

Overwatch's replay events panel covers exactly the left column — verified in a
real frame where it hid the whole block behind `JAVI / ALL EVENTS / ROUND 1`.
Detect it by its own text and by the absence of the `MATCH TIME` anchor, and say:

> the replay events panel is covering the board — close it and read again

Distinct from "the board did not parse", because the remedy is different and the
operator can only act on the one they are told. Moving the block is not an
escape: the kill feed owns the top-right and the objective UI owns the centre.

## 6. Blocking, and the friction it costs

A failed read **blocks** the advance, with an explicit **Skip**. The board is
gone once the round ends, so a silent failure is unrecoverable; making the
operator look at it while they can still scrub back is the entire point.

**Only failures interrupt.** The operator has already reported that the tool's
pop-ups are too frequent, and a confirmation on every successful read would be
one per round per map. A clean read updates a passive indicator and the advance
proceeds untouched — the operator notices the mechanism only when something is
actually wrong.

## 7. The workshop code, said where an operator will read it

`B44BZ` and the fact that bans and stats work **only** in a lobby running this
code are currently documented in `tools/scrim_code/README.md` and
`ARCHITECTURE.md`, and nowhere in the product. In a stock ScrimTime lobby the
*Read bans* button abstains with "could not read the ban row", which reads as a
tool bug rather than as the wrong lobby. ScrimTime Lite has no spectator
scoreboard at all, so it can never support the stats read either.

The capture page states this before capture starts: the code to host on, that
bans are auto-read only in that lobby, and that scoreboard stats are impossible
in any other.

**It must not be confusable with the league-code block.** That existing warning
(`refuseIfLeagueCode()`, `CODE_FEED`, `LEAGUE_CHECK_ACK`) is about FACEIT
*replay* codes and exists to stop a league match being recorded as a private
scrim. Same word, opposite meaning, opposite remedy. The two need visibly
different language — "workshop code" and "replay code" — wherever either appears.

## 8. Testing

- Pure-parser units for the slot layout: ten rows, the five/five colour split, a
  `%` in the wrong column, a missing `MATCH TIME`, and the events-panel text as
  an occlusion case.
- The name-first join directly: a clean name match, a fuzzy one, an unmatched
  name falling back to position, and a role-grouped board refusing to attribute.
- Delta arithmetic directly: consecutive reads, a skipped round, a mid-map
  baseline, and a repeated `MATCH TIME`. The delta function ships here with its
  tests even though nothing displays its output yet — it is what makes the
  stored reads meaningful, and writing it against the record while the record is
  fresh is cheaper than reconstructing the intent later. The UI that consumes it
  is phase 4's Players tab.
- The browser verifier gains a check that a blocked advance stays blocked until
  Skip is pressed, and that a clean read does not interrupt.

**What none of it proves** is the OCR read against a real replay of a
slot-ordered board, which needs a scrim played on the current share code. That is
the same gate the ban row is still waiting on, and it cannot be closed at a desk.

## 9. Out of scope

- **Windowed mode.** The operator has captured in windowed mode for the entire
  history of the project. No calibration work is needed; the page's
  borderless-only wording is stale and is corrected as copy, not as code.
- **Calibration changes**, including making auto-calibrate verify the board.
- Per-player attribution on replays recorded before the current share code.
- The hero-glyph reference set — settled in the 2026-09-06 design, still refused.
- Phase 4's Players tab, which consumes this and is its own piece of work.
- Site-wide login. The operator wants one eventually — league contribution
  tracking, and possibly sharing selected scrim data with teammates — but not
  now, and scrim capture needs no account: the data never leaves the browser.

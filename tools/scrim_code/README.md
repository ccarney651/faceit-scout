# OWDB Scrim workshop code

A **lean custom-game code** for Overwatch 2 scrims, built for the OWDB project
(`docs/`). It is a **stripped derivative of Scrimtime (DKEEH) v1.73** by Caldoran,
re-authored via the OverPy decompiler so teams can keep the Scrimtime experience
they already know at a lower server cost.

## Why strip Scrimtime instead of writing from scratch

- Feature-parity with the industry standard — teams already know the ready-up,
  add-time, defender-teleport and scoreboard UX.
- The **spectator scoreboard layout is preserved**, which is exactly what the
  OWDB capture tool will OCR in the scrim-tracker feature (Phase 2+).
- Bloat removed (see below) cuts the compiled size to **about 40%** and removes
  the per-event processing that drives server load. Measured 2026-09-06:
  `scrim_owdb.txt` is 56,823 bytes against `dkeeh_raw.txt`'s 141,746 — 40.1%,
  across 51 rules versus 81. (The 2026-08-27 figure of 50,446 bytes / 35 rules
  predates the hero-ban feature, which added rules of its own.)

  **"FPS" is the wrong word for what this buys, and it matters.** Workshop
  rules execute on Blizzard's game server, not on any player's PC, so no
  amount of script tuning moves a client's framerate directly. What server
  load actually produces is tick starvation — hitching, rubber-banding, the
  anti-crash slow-motion, heroes going missing from hero select, and at the
  limit "the server closed due to excessive workshop load". That is the thing
  being bought. Note also that once a round starts, every text this mode draws
  is spectator-and-replay-only (`null` audience + `SpecVisibility.ALWAYS`), so
  the ten people actually playing render nothing extra either way.

### What was stripped

| Removed | Why |
|---|---|
| Log Generator (~20 event-driven rules: kills, damage, healing, abilities, ults, hero-swap tracking…) | The biggest FPS cost; OWDB reads the screen, not a log. |
| Multi-language UI (40×7 language strings + Change Language keybind) | Enormous string budget, unused in this team. |
| Debug mode (5 rules + settings) | Dev-only. |
| Legacy scoreboard presets (Legacy Standard, Legacy OWL/OWC) | Only the Standard preset is kept; fewer HUD texts. |
| Disabled mode presets (Control 6v6, Balanced Overwatch variants) | Dead settings. |

### Kept (feature set)

- **Setup phase** — ready-up toggle, hold-to-force-team-ready, add setup time,
  defender teleport between objective and spawn.
- **Map completion** — Assault/Escort/Hybrid full-attack guarantee, Control ends
  after 3 rounds, Flashpoint after 5 captures.
- **Spectator scoreboard** (Standard preset, Small/Medium/Large, all grouping
  styles) — created with `SpecVisibility.ALWAYS`, so it renders for spectators
  **and in replays**; that is what the capture tool reads.
- **Hero bans** (added for OWDB, not in Scrimtime) — one per team during setup,
  enforced with `setAllowedHeroes`, the two forced to different roles, and the
  map blocked from starting with exactly one. Drawn on the spectator view as
  text so the capture tool can read it. Toggle under `1. Hero Bans`.
- **Capture markers** — two green bars above and below the board, so the OWDB
  capture tool can locate it without a human dragging a crop box over it. Toggle
  under `5. Spectator Scoreboard > Draw Capture Markers`, default on. They are
  **progress bars at 100% with no label**, not text: a first version drew a row
  of 56 dots, which worked and looked like debug output smeared across a view
  humans watch. Green because it is the only palette colour nothing else draws
  in-game.
- **Match time display** + host-spectator scoreboard toggle (Z+Q).
- The in-game **Settings panel** (ready up / setup phase / map completion /
  scoreboard / keybinds) with Scrimtime's original tunables.

## Build

Requires Node + npm (OverPy is an npm package).

```bash
npm install
npm run build        # scrim_owdb.opy -> scrim_owdb.txt (paste-ready)
npm run decompile:dkeeh   # regenerate dkeeh.opy from a fresh dkeeh_raw.txt export
```

`scrim_owdb.txt` is the file you paste into Overwatch. The `.opy` source is
the versioned, patchable form — edit that, then rebuild.

## Server load

The mode was tuned for server load on 2026-09-06. Every change below is
verified byte-identical in emitted strings, HUD positions, colours and
`SpecVisibility` against the previous compile — the capture parsers see exactly
what they saw before — and the condition *sets* are unchanged, only their
order. Compiled size fell 58,293 → 56,823 bytes.

| Change | What it removes |
|---|---|
| Scoreboard sort order moved into `Scoreboard_Sort`, a player variable built on the row timer | `SORT_ORDER` re-evaluation used to re-resolve two `Array Contains` scans over the hero lists, per player, for as long as the board existed. Now it resolves one variable. |
| The three `Create Player Entries` rules collapsed from an If/Else pair to one `Create HUD Text` each | Group mode is read once on the timer instead of at every creation; 6 HUD-create actions became 3. |
| The row timer's period spread to 0.200–0.245 s per player instead of a flat 0.25 s | Ten `Ongoing - Each Player` loops on an identical period landed on the same server frame, and peaks hurt more than steady load. Every period is ≤ the old one, so the spread costs no freshness. (This briefly ran at 0.90–0.99 s and was put back — see the measurement below.) |
| Constant settings promoted to the first condition (`Scoreboard_Size`, `Scoreboard_EnableScoreboard`, the gamemode tests) | Conditions short-circuit on the first false one. Two of the three size rules now stop at condition one and stay stopped. |
| `getMatchTime() <= 5` demoted below the ban test in the lone-ban rule | Match time changes continuously; a lone ban changes on a keypress and is usually false. |
| Four literal-string HUD texts dropped from `VISIBILITY_AND_STRING` to `VISIBILITY` | They re-derived a string that cannot change. Visibility still re-evaluates, because `getAllPlayers()` is genuinely dynamic. |
| The player's name folded into `Scoreboard_Row` on the timer, instead of being joined on at the hud text | The ten row texts re-evaluate their string continuously. Joining the name there meant re-resolving a `Custom String` concatenation per player, forever, to attach a name that never changes. The hud text's string is now a bare variable read. |

### What the load actually measured, 2026-09-06

**The honest result: this mode's cost could not be detected against ten bots.**
That is worth recording carefully, because the obvious experiment gives a
convincing wrong answer the first time you run it.

Using `5. Spectator Scoreboard > Enable Spectator Scoreboard` as an on/off lever
with 10 bots on one map:

| Run | Scoreboard off | Scoreboard on |
|---|---|---|
| First | ~121 peak | ~190 peak |
| Second, same map, same bots, same heroes, same difficulty | ~190 peak, ~110 avg | the same, if anything slightly lower |

The first run looks like a clean 69-point result for the scoreboard. The second
run shows what it really was: **the OFF baseline moved from 121 to 190 by
itself.** The whole apparent effect was run-to-run variance.

Why this measurement is so noisy:

- **`Server Load Peak` is a two-second rolling window**, not a high-water mark,
  so it reports whatever the worst two seconds happened to contain. A teamfight
  and a walk-out of spawn are completely different numbers.
- **Bot AI and bot combat dominate.** Abilities, damage events, healing and
  projectiles cost far more than a workshop script reading stats.
- **Server capacity varies by time of day** — the workshop.codes guide notes
  modes that were stable in the morning crashing in the evening.
- The **replay/killcam snapshot system** spikes load every few seconds on its
  own, unrelated to anything in the script.

**So the on/off experiment is a dead end.** What finally worked was a
*sensitivity test*: instead of removing the scoreboard, amplify it and see if
the amplification shows up. Same map, same bots, one build with the row loop's
wait cranked from ~0.945 s to `0.016` — about 60x the rebuild rate:

| | Normal | Amplified 60x | Δ |
|---|---|---|---|
| mean | 51 | 68 | **+17** |
| med | 46 | 63 | **+17** |
| worst1% | 125 | 142 | **+17** |
| best1% | 31 | 45 | +14 |
| max | 169 | 154 | noise |

A near-uniform shift of the whole distribution, which is the signature of a
constant added load rather than a new tail. Four statistics agreeing within
three points is not variance — `mean` reproduced to 1.3% across two earlier
runs, and here it moved 33%.

**The row loop costs about 0.28 load per rebuild-per-second-per-player.**

| Row loop period | Rebuilds/s/player | Cost |
|---|---|---|
| 0.016 s (amplified) | 62.5 | ~17 |
| 0.20–0.245 s (shipped) | ~4.5 | **~1.3** |

Against a mean of 51 that is **about 2.5% of the mode's load**, which is why
neither on/off run could see it. It is real, it is tiny, and it is now priced.

**What follows from this.** Every optimisation above is strictly less work than
what it replaced and verified not to change behaviour, so all of it stays. But
the mode was never the bottleneck — the load is bots, abilities, damage events
and the engine — and **nobody should trade features or freshness for load here
without pricing the trade first.** That already happened once: the row period
was raised to ~1 s for a full second of staleness, the measurement above showed
it bought back about one load unit, and it was put straight back to 0.25 s.

The amplified build is the tool for pricing the next one. Rebuild it by copying
the source, changing that one `wait`, and compiling to a separate file.

### Measuring server load

`6. Debug > Display Server Load` draws three lines, top right, off by default:

```
49 cur / 58 avg / 67 peak server load     <- Overwatch's own values
max 255 / mean 76 / 0% over 200 / n 572   <- accumulated for this map
best1% 31 / med 70 / worst1% 168          <- the distribution
```

**Line one is nearly useless on its own, and that is Overwatch's fault, not
yours.** Every value it exposes is a *two-second window* — `getPeakServerLoad()`
is "the highest CPU load … over the last two seconds", not a high-water mark,
and the average covers the same two seconds. So it tells you what just happened
and then forgets, the numbers move faster than you can read them, and two runs
of the same build look nothing alike. Lines two and three exist because of that.

Read them like an FPS benchmark, because the problem is the same shape — nobody
quotes average framerate alone, since a run that averages 120 with vicious
stutter and a run that sits flat at 120 are the same number and a completely
different experience.

| Field | What it is |
|---|---|
| `mean` | True average over the whole map. **The stable one — compare builds on this.** |
| `med` | Median. More honest than the mean, which a few 255s drag upward. |
| `worst1%` | 99th percentile: load exceeded 1% of the time. The direct analogue of an FPS "1% low", except higher is worse. |
| `best1%` | 1st percentile — the floor the mode idles at. |
| `% over 200` | Share of the map spent above 200. One 255 spike and a mode living at 255 are indistinguishable on line one and are completely different problems. |
| `n` | Sample count. Also tells you if you hit the 1200-sample cap. |
| `max` | High-water mark. **Expect 255 always** — it latches onto the single worst 2 s window, usually match start or a replay-system spike. Nearly useless; kept only to answer "did it ever hit the ceiling". |

Percentiles come from real samples through `Sorted Array`, taken at 1 Hz and
re-sorted every fifth sample. Both rates are deliberately slow: an instrument
that shifts what it measures is worse than no instrument. The trade is that 1 Hz
sampling cannot see a 200 ms spike — which is what `max` is for, since it reads
the 2 s peak every 0.5 s and cannot miss one. Read the two together.

Stats reset at the start of each map, so each map is an independent measurement.

**Measure, do not trust the table above.** Compare a full map against the
previous build, on `mean` and `worst1%`. The
magnitude is genuinely unknown from the source alone: the Workshop evaluates
sporadically-changing values on change rather than polling them every frame, so
how much any of this saves depends on engine behaviour that is not documented.
What is certain is that each change strictly reduces work and none can increase
it.

Two things were considered and **rejected**, so they do not get re-litigated:

- *Caching the hero role for the row's BLK/HEAL/ACC branch.* Computing the
  cached role costs the same two array scans it saves — a wash. Worse, the
  row's classification and the sort's classification disagree on a `null` hero
  (the row falls through to accuracy, the sort to 3), so merging them would
  have been a real behaviour change.
- *Pre-formatting the match-time string.* It is one text, not ten, and it would
  mean restructuring a working timer for a gain too small to measure.

## The share code

**`B44BZ`** — minted 2026-09-06 **from the main account `gcb`**. Hosts should
load this rather than pasting the script; it is the only way bans and the
spectator scoreboard reach a scrim somebody else is hosting.

**`B4GM8` is dead — do not hand it to anyone.** It was the 2026-08-28 code and
it lives on the alt account `ragecomic`, so it can only ever be updated from an
account the team does not normally use. Re-rolling on `gcb` moved publishing to
the account that actually ships the code, which is worth the one-time cost of
retiring the old five characters. Anyone still holding `B4GM8` is on a version
that will never be updated again.

Two things about the new one that are easy to get wrong:

- **Always pick "update an existing code", never "upload a new one."** It keeps
  the code stable for the team, it does not consume the create-code rate limit,
  and it counts as activity against expiry. Re-rolling is what retires a code;
  do it deliberately or not at all.
- **Publish from `gcb`.** Updating a code appears to require the account that
  published it, which is exactly why the alt-account arrangement was a problem
  worth spending a re-roll to escape. Do not upload this mode from any other
  account.

**The create-code rate limit is about ten codes.** Measured 2026-08-28 while
rerolling for a memorable one: after roughly ten creations Overwatch returns
"Reached limit for creating game settings code. Please try again later." The
cooldown is not published and was not waited out, so it is unknown. Blizzard
assigns the code randomly - it cannot be chosen - so rerolling is the only
lever, and it is a budget of about ten. Decide what you will accept before
spending it.

That budget has now been spent twice, on `ragecomic` (2026-08-28) and on `gcb`
(2026-09-06). It appears to be per-account, since the second re-roll succeeded
on a fresh account, but nobody has established whether it resets with time. Treat
another re-roll on `gcb` as expensive until someone knows.

**Codes expire six months after creation** unless imported or uploaded to often
enough. `B44BZ` was minted 2026-09-06, so it lapses around **2027-03-06** unless
the team keeps using it. Regular use is what keeps it alive; a code that only
gets loaded occasionally will quietly die, probably mid-season.

## Import in Overwatch

**Do not look for an "Import Code" button — that is a different mechanism.**
Overwatch has two, and they are not interchangeable:

- **Import** takes a short *share code* (`DKEEH`, `0PP1T`) and downloads a
  published mode. It cannot take a script.
- **Copy / Paste** moves the whole settings blob, workshop rules included,
  through your operating system's clipboard. That is how a script gets in.

To load `scrim_owdb.txt`:

1. Open `scrim_owdb.txt` in a text editor and copy all of it (Ctrl+A, Ctrl+C).
   **Do this first** — see step 4.
2. Custom Game > Create > **Settings** (top right).
3. Stay on the **Settings** screen. The button row is in the **Summary panel on
   the right**; do NOT go into the Workshop sub-screen, which has no paste
   control at all.
4. Click the orange **Paste** button beside Copy. It only appears when the
   clipboard already holds valid workshop text, so an empty clipboard shows
   nothing and looks like a missing feature.

Pasting replaces **all** lobby settings, not only the rules. Use a fresh lobby.

Pasting also fails outright if the Overwatch client language is not English —
`scrim_owdb.txt` is compiled `en-US`. Going the other way, a mode is exported
with the **Copy** button in the same place, which is how `dkeeh_raw.txt` was
obtained. A share code is minted separately via **Copy Settings** in the Custom
Game menu.

## Controls (default keybinds)

| Action | Input |
|---|---|
| Ready up / unready | Interact + Reload |
| Ban a hero (during setup) | Interact + Melee, while playing that hero |
| Clear your team's ban (during setup) | Interact + Crouch |
| Force team ready (hold) | Interact + Reload, hold 3 s |
| Add setup time | Interact + Ultimate (+30 s, cap 90 s) |
| Defender teleport | Interact + Jump |
| Host: toggle scoreboard | Ultimate + Ability 1 (Z+Q) |

Rebindable in the workshop Settings panel under **7. Keybinds**.

## Recommended lobby settings for scrim conventions

The workshop logic handles ready-up and map-completion bookkeeping; the actual
**flow** (how many points / rounds are played) is governed by lobby settings,
which is how teams run scrims today:

- **Control / Flashpoint** — teams play out *every* point even after a 3-0/2-0
  (scrim convention). In the lobby settings set the mode to keep the map going
  (e.g. disable early-end conditions) so the full best-of-5 is played; the
  workshop's "End Control After Three Rounds" setting controls whether the code
  force-ends it (turn **off** to play all points).
- **Hybrid / Escort** — both teams get a **full attack** regardless of distance.
  Leave the standard two-round flow; the map-completion rules ensure round 2 is
  fully attacked. If both teams full-cap and agree to "play it out" (one extra
  attack turn each), run the extra turns as a rematch round — the code's ready-up
  handles each new round.
- **Push** — normal match flow; nothing special.
- **Partial practice** (single sub-map of Control, one attack/defense, etc.) —
  just play that slice; the scoreboard and capture tool read whatever was played.

## In-game validation checklist (must be done by a human)

These cannot be verified outside the game:

1. **Setup phase** — ready-up toggle lights the ○/● list; both-teams-ready starts
   the countdown; hold-to-force-team-ready works; adding setup time increments
   the timer and respects the max.
2. **Defender teleport** — spawn↔objective teleport works on each map type
   (Escort/Hybrid/Control/Flashpoint); Push correctly excludes it.
3. **Map completion** — attacker-fail case sets the attacking score so round 2 is
   fully attacked; Control ends at 3 rounds, Flashpoint at 5.
4. **Scoreboard** — appears top-left for a **spectator**, and is present in the
   **replay** of the scrim; matches stats visually; host toggle hides/shows it.
   After the 2026-09-06 load pass, check specifically that **rows still sort
   correctly in both grouping styles**, including after a mid-round hero swap
   in "group by team, sort by role" — the sort order is a variable now, and it
   refreshes on the row timer rather than continuously.
5. **Server load** — turn on `6. Debug > Display Server Load` and watch cur /
   avg / peak through a full map. Peaks matter more than the average. Compare
   against Scrimtime (DKEEH) if that is the reason for using this code. This
   is not a framerate test: see the note under "Why strip Scrimtime" for why
   the two are different things.

## Licence note

Scrimtime (DKEEH) is **not open source**. This stripped copy is for this team's
own private scrims. Do **not** publish a stripped share code publicly as if it
were original work. If public publication ever becomes a goal, the clean base is
**Scrimmie** (open-source, CC BY-NC-SA, includes LogTime).

## Relationship to OWDB

- `tools/scrim_code/` = the workshop code only.
- The **capture** side (reading the scoreboard off-screen) lives in `owdb/`
  and `docs/capture/` and is developed separately — see `FEATURES.md`.
- `dkeeh_raw.txt` (original export) and `dkeeh.opy` (its decompilation) are kept
  as reference so the strip can be re-derived when DKEEH updates.

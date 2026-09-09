# Replay bot — design

An unattended harness that loads FACEIT replay codes into an Overwatch client,
sweeps each replay, and reads hero compositions off the HUD — replacing the
operator who currently has to sit in-game and scrub by hand.

> **Status, 2026-09-09: built and running.** This is the design as it was
> written. Where the build disagreed with it, the build won and
> `ARCHITECTURE.md` section 14 is the as-built account; section 11 below
> records which of these questions the building of it answered.

## 0. Why this exists

Capture today needs a person. They share their screen to `docs/capture/index.html`,
load a replay, scrub to each round boundary and confirm the read. That is the
only reason scouting coverage is bounded by operator time rather than by how
many matches were played.

Everything else about a match already arrives from FACEIT. `docs/capture/data.json`
currently carries **255 live codes**, each already joined to its map, division,
both team ids and `finished_at`. Bans and the scoreboard come from FACEIT too.

**The client is needed for exactly one fact FACEIT does not expose: which heroes
each team actually played.** That is the whole scope of this document.

## 1. Decisions

| Decision | Choice |
|---|---|
| Stack | Node harness, native window grab, engine modules reused unmodified |
| Frames | Retained as PNGs after each run |
| Seek strategy | One uniform sweep; round boundaries derived afterwards |
| Sample interval | ~30s, configurable |
| Frame source | Window grab of the Overwatch client, which must run Borderless Windowed |
| Calibration | One-time frozen constant + per-run smoke check |
| Provenance | Segregated contributor file, `tool_version: "replay-bot-0.1"` |
| Host | Bare-metal Windows on a spare machine — **not** a VM, **not** gcbserv |
| Account | A dedicated burner Battle.net account |

### 1.1 Terms of service

Driving the game client with synthetic input is **prohibited by the Blizzard
EULA**, which defines a Bot as software "not expressly authorized by Blizzard,
that allows the automated control of a Game or part of a Game, or any other
feature of the Platform". There is no carve-out for spectator or replay mode.

The operator has accepted this risk on a disposable account. This is recorded
here so nobody later mistakes it for an oversight. Two consequences bind the
design:

- All game-touching code is isolated in one module (§3, `driver.js`), so the
  ToS-relevant surface is a single file — swappable if authorization is ever
  obtained, and pointable at recorded frames for offline work.
- The rig runs on hardware whose loss is acceptable, and shares nothing with a
  primary account.

## 2. Scope

**In:** load a code, sweep the replay, identify the five heroes per side at each
sample, segment into rounds, write per-round comps as a contribution file.

**Out, because FACEIT already provides it:** the map, the code itself, bans,
the scoreboard, team identity, match outcome.

**Out, because there is no second party to distrust:** the upload Worker,
Discord auth, scouting claims, contributor identity, verified-wins ownership,
the guided tour, the pop-out overlay, and the screenshot-import walkthrough.
Every one of those exists to make a *stranger's* contribution trustworthy. A
single-operator rig on one machine needs none of it.

**Deliberately kept despite the above:** the read-shape guard (a frame yielding
other than ten rows is refused, never guessed at) and the calibration smoke
check (§5). These are correctness gates, not anti-tamper, and unattended
operation makes them matter more rather than less.

## 3. Components

A new Node package following the repo's testable-core pattern: logic pure and
exhaustively tested, I/O thin and mockable.

| Module | Purpose | Pure |
|---|---|---|
| `queue.js` | Read `data.json`, drop codes past the wipe date, skip completed work, order by `finished_at` | yes |
| `segment.js` | Observations to round boundaries and comps | yes |
| `emit.js` | Segmented rounds to contribution JSON | yes |
| `sweep.js` | Walk one replay's timeline, collect observations | thin |
| `shim.js` | A `{doc}` handle so engine modules run under Node | no |
| `grab.js` | Overwatch window to bitmap | no |
| `driver.js` | The only module that touches the game | no |
| `run.js` | CLI entry; wires the above | no |

`segment.js` and `emit.js` hold the real logic and have zero I/O, so the
interesting behaviour is unit-testable without a game, a GPU, or a screenshot.

### 3.1 Why the engine is reused rather than reimplemented

The capture engine already dependency-injects its DOM handle. `refs.js`
documents its context as `{doc, ocrLoadTimeoutMs}` and `frames.js` only ever
calls `ctx.doc.createElement('canvas')` — never a global `document`. And
`matchCrop()` runs the matcher over a 64x36 greyscale buffer as pure
`Float32Array` arithmetic, needing no canvas at all.

So `shim.js` supplies a minimal `doc` backed by a Node canvas implementation,
and `calibration.js`, `frames.js` and `refs.js` are consumed **byte-identical to
what the operator's browser runs**. The bot cannot drift from the human path,
because it is the same path. This also keeps it out of scope for
`tools/capture_divergence.py`.

## 4. The sweep

Per code:

1. `driver.openCode(code)`; wait for the replay to load.
2. Smoke-check calibration (§5). On failure, abort this code and write nothing.
3. Sweep: from t=0, step ~30s. At each stop `grab.capture()`, then
   - read `matchTime` and both scores via `boardreads`,
   - crop the ten portrait cells at the frozen geometry,
   - `matchCrop()` each cell,
   - append `{t, clock, score_a, score_b, heroes_a[5], heroes_b[5], confidence[]}`.
4. Terminate on N consecutive frames yielding no valid HUD read, or a hard cap.
5. `driver.close()`. Retain every PNG.

### 4.0 The scrubber already knows where the rounds are

**Supersedes the uniform sweep below, 2026-09-08.** The replay bar draws
between-round breaks in a different colour from play time, so a map's round
structure is sitting in the UI and does not need inferring at all.

Measured on the rig against a 17:42 three-round Control replay, the bar spans
x=73..2449 and shows exactly two coloured runs. Decoded:

| | Time | Length |
|---|---|---|
| Round 1 | 0:00 – 6:46 | 406s |
| break | 6:46 – 8:46 | 120s |
| Round 2 | 8:46 – 12:23 | 217s |
| break | 12:23 – 13:25 | 62s |
| Round 3 | 13:25 – 17:42 | 257s |

Breaks are found by **colour, not brightness**: the bar's luminance is polluted
by event ticks and the playhead, which are bright white, while the blue
channel's lead over red is clean. Runs narrower than `minRunPx` are discarded,
since the playhead knob is a few pixels of blue and taking it for a boundary
would cut a round in half.

Sampling is then **3 points per play segment** where a map has rounds, and
**5 across the single segment** where it does not (Push, Flashpoint). Points sit
strictly inside a segment, never on its edges, because a round's first and last
instants are setup and aftermath where portraits are absent or mid-transition.

That takes the measured Control replay from roughly 35 uniform samples to **9**,
and every one lands in live play. The scrubber's printed duration also settles
§11's open question about how the sweep knows when to stop.

### 4.1 Round boundaries are derived, not sought

Seeking *to* round starts would require knowing where they are, and the replay
timeline does not expose them — that path is a search loop against an oracle
that does not exist.

Instead the sweep is uniform and `segment.js` recovers boundaries afterwards
from the score changes and clock resets already visible in each observation.
This is strictly simpler, has no failure mode where the search diverges, and
yields the periodic intra-round samples as a side effect rather than as extra
work.

`map_category` is already present in `data.json`, so segmentation specialises:
Control is first-to-N with a resetting clock, while Escort and Hybrid advance
by checkpoint and need their own rule.

### 4.1b One machine, two team colours

The capture page supports recoloured teams and sweeps for them during
calibration. The bot never meets that case: one rig, fixed settings, default
colours, so the left strip is always the blue `a` variant and the right always
red `b`. `refs.json`'s 106 refs are exactly 53 heroes × those two variants, and
no custom-colour branch is needed anywhere in the bot.

### 4.1c The sweep's redundancy is spent on voting

A slot is sampled many times per round, which an operator snapshotting once per
round never gets. `vote.js` resolves each slot by agreement across those frames,
and `segment.js` reports it as the round's `voted` comp beside `opening`.

This cannot be replaced by a confidence threshold. Measured on the bootstrap
frame, correct reads on the red plate ran as low as **0.805** — so any cut-off
strict enough to reject a bad read would reject good ones too. Agreement across
frames separates noise from signal where a single number cannot.

A slot split badly enough to be a real hero swap rather than noise is flagged
`contested` instead of being resolved silently, because "this read was noisy"
and "they swapped mid-round" are different facts and only the caller knows which
one matters.

### 4.2 Comps are sets, and pools are not comps

`owdb/comps.py` defines `comp_id_for()` as the sha1 of the *sorted* hero guids,
so a comp is order-independent by construction and the bot never has to get
slot assignment right — only membership.

**The trap:** `canonical_comp()` collapses duplicates into a set and counts
roles over whatever it is given. Feeding it the union of every hero seen across
a round would manufacture a seven-hero "comp" with nonsense role counts that
hashes to an id no real comp shares.

Therefore:

- **the per-round opening comp** — the five heroes at the first observation
  after a boundary — is the canonical comp, and the only thing passed to
  `canonical_comp()`;
- **the hero pool** — the union across the round — travels as separate
  metadata, useful for scouting but never hashed as a comp.

## 5. Calibration

HUD geometry in this codebase is expressed as *fractions of the calibration
box*. On 2026-08-19 a replay-code crop was fitted against a hand-measured strip
of `(57, 97, 700, 111)`, scored 12/12 offline with zero wrong reads, and then
read nothing whatsoever on the first live capture. The box `auto-calibrate`
actually produces was `(129.536, 119.808, 660.224, 97.2)` — a different
rectangle entirely, against which the unmodified fractions worked.

The lesson is about **provenance, not frequency**. The reference rectangle must
be one `auto-calibrate` genuinely emitted; it does not have to be recomputed
often, or ever.

The rig is one machine at one resolution with fixed settings, so:

- **Bootstrap, once.** Run `auto-calibrate` against a share of **the Overwatch
  window**, not the whole display, and not a hand-measured screenshot. Record
  the emitted `boxes.a` and the frame dimensions, and freeze both as constants.

  The window is what makes this transfer. The bot grabs the client window so it
  can run behind other work — a full-screen grab would make the rig
  single-purpose, corrupted by any overlay or notification, which defeats the
  point of a background job. `getDisplayMedia` can share a window as readily as
  a display, so the bootstrap and the bot see the same rectangle in the same
  coordinates. Overwatch must therefore run **Borderless Windowed**; exclusive
  fullscreen is not reliably window-capturable.
- **Per run, cheaply.** Assert the frame matches the frozen dimensions and that
  the frozen crop still contains HUD-shaped content. This is a smoke check of a
  few lines, not a calibration.

The smoke check earns its place for one specific reason: **the bot's schedule is
pinned to the thing most likely to invalidate its geometry.** Codes die on patch
(§7), so the bot necessarily runs shortly after patches — exactly when HUD scale
or layout may have shifted. The operator's setup will not change between runs;
Blizzard's will. A check that fails loudly beats a silent run that writes
hundreds of maps of confident wrong comps.

Frozen geometry and the dimensions it was fitted at are recorded per map in the
existing `profile: {w, h, hud_variant}` field, so if a patch does move the HUD,
captures either side of it are distinguishable after the fact.

## 6. Output

The bot writes the established contribution schema — `format`, `contributor`,
`tool_version`, `maps[]` — with each map carrying `match_id`, `game_no`,
`demo_code`, `map_guid`, `map_name`, `map_category`, `side_a_team_id`,
`side_a_team`, `side_b_team_id`, `side_b_team`, `captured_at`, and `profile`.

### 6.1 The payload is observations, not comps

**Corrected 2026-09-08 against the real schema.** An earlier draft of this
section assumed the bot would ship per-round comps. It does not. `maps[]`
carries an `observations[]` array, and `owdb` derives comps from it downstream —
so the bot's job ends at reporting what it saw.

Each observation is **one side at one sample**, per `owdb/contribute.py`:

```
{side, ts, sub_map, round_no, phase, heroes: [guid…], pairs: [[guid, player_id|null]…]}
```

Three consequences:

- **`heroes` are hero GUIDs**, not display names — `"0x02E00000000001EC"`, with
  operator-added heroes as `"custom:d_mon"`. `refs.js` `bestMatch()` already
  returns the guid alongside the name, so the bot carries the guid and never
  round-trips through a name.
- **One sample yields two observation records**, one per side. The sweep's
  internal representation holds both sides together because round detection
  needs the whole scoreline; `emit.js` splits them.
- **Segmentation's shipped output is `round_no`**, stamped onto each
  observation. The opening-comp and hero-pool distinction of §4.2 remains the
  bot's own analysis — worth keeping for the accuracy comparison in §9 — but it
  is not what the contribution carries.

### 6.2 Honest degradation

Three fields the browser path fills that the bot initially cannot:

| Field | Bot behaviour | Why |
|---|---|---|
| `pairs` | `[]` | Player attribution needs name OCR the bot does not yet run. The merge already defaults this to empty, so it is a supported absence rather than a malformed record. |
| `sub_map` | `null` | Control sub-maps would need reading, and `CONTROL_SUBMAPS` is forked across four files. Deferred rather than forked a fifth time. |
| `phase` | `null` | Attack/defend is derivable downstream from `round_no`. |

These are absences the schema already tolerates, not invented values. The bot
must never guess one of them — a wrong `sub_map` is worse than no `sub_map`.

Two things mark it as machine-produced:

- `tool_version: "replay-bot-0.1"`, distinct from `browser-0.2`;
- its **own contributor file**, separate from any human's.

Segregation is what makes the bot auditable. Merge can prefer human reads on
conflict, report bot-only coverage separately, or ignore the bot wholesale — and
crucially, running the bot over maps an operator already captured by hand yields
a measured accuracy number before any of it is trusted.

## 7. Codes expire, so ordering is load-bearing

Observed wipes sit at 2026-07-14 and 2026-07-28, and `data.json` currently
carries `code_wipe_date: 2026-08-18` — a shelf life of roughly two to four
weeks, tracking the game's patch cadence. A code that outlives its wipe is not
late, it is **permanently unreplayable**.

Consequences:

- `queue.js` orders by `finished_at` and drops anything already wiped, rather
  than treating order as cosmetic.
- The bot is scheduled against patch cadence, not run casually. At roughly two
  to five minutes per code, 255 codes is somewhere between an overnight run and
  a full day of client time — comfortably inside a patch window, but only if the
  window is not missed.
- A missed window is unrecoverable data loss, which is the strongest practical
  argument for the whole harness: a human cannot hand-scrub 255 maps in a
  fortnight, and a bot can do it overnight.

## 8. Where it runs

**Bare-metal Windows on a spare machine.**

gcbserv was considered and rejected. It has a single GTX 1080 Ti, and VFIO
passthrough is exclusive — no consumer GeForce shares between host and guest —
so handing it to a VM means unbinding it from the pinned 535.309 driver and
taking Jellyfin's NVENC transcoding down with it. Its 16GB would also be
carrying an 8GB game plus a Windows guest on top of eighteen containers, and its
6-core Ryzen 2600 is already serving them.

The decisive objection is not capacity, though. **Virtualisation is a louder
anti-cheat signal than synthetic input.** Accepting ToS risk on a burner is a
considered trade; adding VM detection on top raises the risk while also being
the harder build. The workload is a replay viewer at minimum settings, which is
trivial for any modern GPU, so there is nothing to gain.

gcbserv can still own the queue and hold results over the network. It should not
run the client.

## 9. Testing

- **Pure units.** `queue.js`, `segment.js` and `emit.js` get `node:test`
  coverage over synthetic observation lists, matching the existing suite's
  conventions. Segmentation is tested per `map_category`.
- **Golden frames.** Retained PNGs become a regression corpus: the same frames
  in must yield the same comps out, forever. This is the payoff for retention —
  the matcher can be improved and re-run without spending another night of
  client time.
- **Measured accuracy.** The bot is run over maps already captured by an
  operator, and the comps compared. Segregated provenance is what makes this
  computable, and it gates trust.
- **Sparse-versus-dense.** A dense sweep of a small sample, compared against the
  30s cadence, quantifies how many hero swaps the interval misses — turning the
  sample rate into a measured choice rather than a guess.

## 10. Risks

| Risk | Handling |
|---|---|
| Native grab geometry differs from `getDisplayMedia` | Bootstrap calibration on the bot's own path (§5); never transfer the browser's box |
| A patch moves the HUD mid-campaign | Smoke check fails loudly; `profile` dates every capture |
| Hero absent from `refs.json` | Only an operator in-game can add refs, so the bot flags low-confidence matches rather than guessing |
| Codes expire mid-run | Queue ordered by `finished_at`; wiped codes dropped up front |
| Hero swaps between samples | Inherent to sampling; quantified by the sparse-versus-dense test |
| Account ban | Accepted; burner account, disposable hardware, no VM |

## 11. Open items

**Settled by building it (2026-09-09).** Kept here with their answers, because
what a design got wrong is worth as much as what it got right.

- ~~**Termination condition.**~~ There is nothing to terminate. The scrubber
  states the map's duration and its round structure, so the sample plan is
  finite before the first seek — "N consecutive invalid frames plus a hard cap"
  was a solution to a problem that only exists if you sweep blindly. What
  replaced it is a set of refusals: a frame at the wrong size, a missing
  playhead, an events panel that will not open, a seek that will not land.
- ~~**Sample interval.**~~ Not an interval at all. Samples are placed 3 per
  round or 5 across a single segment, read off the bar, then snapped to the grid
  that seeking can actually reach. The grid is whatever the client's skip
  interval is — **measured** per session by timing playback, since the setting
  silently reverts at every client restart.
- ~~**Escort and Hybrid segmentation.**~~ No mode-specific rule was needed.
  Breaks are drawn on the scrubber for every mode, so Escort reads its two
  halves the same way Control reads its three rounds. Verified on Watchpoint:
  Gibraltar, Circuit Royal and Havana. The one adjustment was dropping play
  segments under 30s, which are the assemble phase rather than a round.
- ~~**Input mechanism.**~~ `keybd_event` through a long-lived PowerShell host,
  with the client foregrounded — nothing reaches an unfocused window. Seek and
  spectate are the client's own bindings (`B`, `X`, `Z`, `N`, `K`, `SPACE`), and
  the menus around a replay are recorded rather than bound, since they have no
  keyboard route at all.

**Still open.**

- **Side b's calibration box.** It reads about 0.11 lower than side a, at the
  same 1px offset on two independent maps, so it is geometry rather than a map.
  Wants a bootstrap re-run for side b, not a hand-edited number.
- **Chunk playback speed.** `open-import` spends ~4.2s replaying waits the
  operator made while menus animated. `probe_chunk.js` measures what the client
  will keep up with; it has not been run yet, so `--chunk-speed` defaults to 1.
- **Real league maps.** Everything so far was measured on quick-play and
  competitive replays from a public code site. A FACEIT map is longer and has
  more rounds, so sample counts and per-map time will differ — worth re-timing
  on the first post-patch match rather than extrapolating.
- **Sparse-versus-dense accuracy.** §9's test is still unrun: nobody has yet
  quantified how many hero swaps the sampling misses.
- **Six-versus-six.** The frozen geometry divides each side's box into five
  portraits. A 6v6 replay reads garbage, and nothing currently detects that it
  is one.

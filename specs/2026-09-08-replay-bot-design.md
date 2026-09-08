# Replay bot — design

An unattended harness that loads FACEIT replay codes into an Overwatch client,
sweeps each replay, and reads hero compositions off the HUD — replacing the
operator who currently has to sit in-game and scrub by hand.

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

- **Bootstrap, once.** Run `auto-calibrate` on the bot's own grab path — not on
  a screenshot, and not on the browser path, since a native window grab may
  differ in dimensions and origin from `getDisplayMedia`. Record the emitted
  `boxes.a` and the frame dimensions. Freeze both as constants.
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

- **Termination condition.** "N consecutive invalid frames, plus a hard cap" is
  a reasonable default but has not been validated against a real replay's end
  screen. Worth settling in a first spike.
- **Sample interval.** 30s is a starting guess; §9's sparse-versus-dense test
  replaces it with a number.
- **Escort and Hybrid segmentation.** Control's resetting clock makes boundaries
  obvious. Checkpoint-based modes need their rule written against real
  observations.
- **Input mechanism.** Every spectate control is rebindable in-game, so the
  driver should bind seek and spectate to unambiguous keys rather than hunting
  UI pixels. The specific automation library is left to implementation.

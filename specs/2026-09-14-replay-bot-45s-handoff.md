# Handoff: replay bot on 45s cadence (next session)

Session 2026-09-14 shipped the 30s-grid + change-detection work from
`specs/2026-09-14-replay-bot-30s-capture-design.md` and live-tested it. The
operator has now decided to switch the cadence from 30s to **45s** — the client's
time-skip slider goes 5–60s, so 45s is a selectable grid. This file is the
complete context for that next session. Read it before touching anything.

## 0. Repository state — read first

- Branch: **`capture-read-guards`** (102 ahead / 7 behind `origin/main`;
  `tools/replay_bot/` does not exist on `main`). Do not merge or push anything
  unless the operator asks.
- The working tree has a **large pre-existing uncommitted state that is NOT
  ours and must NOT be touched**: `specs/` deletions, edits to `AGENTS.md`,
  `ARCHITECTURE.md`, `CHANGELOG.md`, `faceit_sync/*`, `owdb/*`,
  `tools/scrim_code/*`, `docs/*`, and staged `PLANS.md`. The operator's own
  replay-bot edits (`attribute.js`, `chunks/open-import.json`, `codestack.js`,
  `frames/README.md`, `resolve.js` earlier state, `review/page.html`,
  `timing.js`) are also theirs — leave them alone.
- Files our session wrote (yours to edit, still uncommitted):
  `timeline.js`, `phases.js`, `capture.js`, `gui.js`, `run.js` (comments only),
  `prune_frames.js`, `corpus_sweep.js`, `timeline.test.js`, `phases.test.js`,
  `capture.offline.test.js`, `resolve.test.js`, plus this design doc
  `specs/2026-09-14-replay-bot-30s-capture-design.md` (keep) and this handoff.
- Do not commit unless the operator asks. CI auto-commits to `origin/main` on
  its own schedule; if you ever push, `git fetch` first (AGENTS.md invariant 9).

## 1. What is already shipped (this session, all verified)

All work from the 30s design doc is **implemented and live-tested**. 428 tests
pass (`node --test` from inside `tools/replay_bot/`; repo-root discovery does
not work). The pipeline now:

- **`timeline.js`** — `planGrid(segs, {stepS})` replaces `plan()`/`samplesFor()`
  (both deleted). Grid points: first reachable inside each play segment
  (`ceil(from/step)*step`), then every `+step` while `< to`, `hi` clamped below
  `to` (never samples a round's closing edge), nearest-reachable-midpoint
  fallback for a segment shorter than one grid interval, cross-segment dedupe.
  **`INTERVALS = [5,10,20,30,60]` and both `planGrid` and `stepSecondsFrom`
  refuse any step not in it.** This is the one constant the 45s change touches.
- **`phases.js`** — `sampleAt` flipped to read-before-keep: read HUD on the
  settle's frame, one-second-look retry (`grabTo('t'+t+'-again')`) if
  `worstOf < LOW_SCORE (0.6)`, then a keep decision via the exported
  `shouldKeep(read, prev, prevPrev, firstOfRound)`. Keeps when: any slot guid
  changed, any score `< 0.6`, the previous read was contested
  (`prev.guid !== prevPrev.guid`), it is a round's first sample, or there is no
  previous read. Unkept samples return `framePath: null` (skips the ~210ms PNG
  encode). `readStructure` calls `planGrid` and returns
  `{segments, per: plan.length, plan}`.
- **`capture.js`** — the sample loop tracks `prevRead`/`prevPrevRead`/
  `roundSeen`, attaches a short-segment fallback point to the nearest play
  segment, resets baselines at each round's first sample, and passes
  `{prev, prevPrev, firstOfRound}` into `sampleAt`. All visits' reads go into
  `samples[]` regardless of keep — `resolve.js`/`emit.js` consume the denser
  reads unchanged.
- **`run.js` attribution fall-forward** — attribution runs once per map but now
  tries the **first up-to-4 kept sample frames** (the first sample's frame can
  be a round-intro transition with no name rows drawn — happened live on
  Nepal). It keeps whichever attempt resolves the most slots (stops early at
  ≥8/10) and logs `attribution: first sample's names were not readable, using
  sample at Ns (X/10 slots)` when it moves past the first. Verified 10/10 on
  both maps after the fix.
- **`resolve.js` swap-duration rule** — `segmentSlot` now needs **2 consecutive
  reads** before a new guid becomes its own segment (the operator's "don't count
  swaps under 1min = two reads on 30s" rule; read-count based, so it scales
  automatically to ~90s on a 45s grid). A single differing read is absorbed into
  the interrupted run (its score stays in that segment's `reads[]`; the raw vote
  still sees the differing guid). Accepted trade (documented in resolve.js): a
  fast multi-hop swap with one read per hero collapses into the preceding
  segment but surfaces as `contested`/`low-support` with `alt_guid`.
- **`gui.js` / `run.js`** — `set-interval` chunk described as 30s.
- **`prune_frames.js`** — README wording updated: sample frames are now one per
  COMP CHANGE (change-detection kept set), not one per grid point. Policy code
  unchanged.
- **`corpus_sweep.js`** — new `--retention` flag reports change-detection
  kept/total across readable HUD frames (flags a map where the detector flips
  every sample).

Tests: `timeline.test.js` rewritten around `planGrid`; `phases.test.js` and
`capture.offline.test.js` gained retention tests; `resolve.test.js` rewritten
for the 2-in-a-row rule. Full suite: 428 pass, 0 fail.

## 2. Live-test results (2026-09-14, four maps)

- Captured live: **Z3ZHME** (Nepal Control, correct 30s grid), **SMBB9Y**
  (Aatlis Flashpoint, operator's accidental 20s grid), **7Y1X6R** (Nepal, 30s),
  **KH6ZNX** (Samoa, 30s). Artifacts: `tools/replay_bot/out/replay-bot-2026-09-14.{json,review.json}`.
- **Change-detection retention works**: on both grids, every sub-0.6 visit was
  kept and every confident+unchanged visit was dropped (e.g. SMBB9Y 34 visits →
  29 kept, 28 of them low-score-driven).
- **Attribution**: pre-fix maps partial (Z3ZHME 3/10), post-fix maps **10/10**.
- **Red-side Lucio reads badly — this is the b-box geometry, not Lucio.** On the
  same KH6ZNX frame, side-a Lucio reads 0.851 and side-b Lucio 0.533; a +4px
  RIGHT shift of the whole b strip recovers Lucio to 0.805 and the whole b side
  to ~0.83 mean (a-side parity). Both maps today agreed on +4px; the 09-12
  session wanted −1px (sign is session/window-dependent). The bot uses frozen
  `calib.FROZEN.boxes` — **no per-map strip re-detection** (that only exists in
  the live `docs/capture/engine/calibration.js`), and hand-editing FROZEN is
  forbidden (`calib.js:21`; AGENTS.md). Open offer, still undecided: wire the
  live engine's structure detection (five team-coloured tiles at constant
  pitch) into the bot per map, FROZEN as fallback, with tests. The sanctioned
  manual fix is re-running the side-b bootstrap (operator action).
- **Swap rule confirmed**: SMBB9Y's t620 Brig read (single sample, Goose never
  left Moira) is now absorbed, not a segment.
- Gameday sizing: a full playday is ~34–37 matches ≈ ~124–137 maps with codes
  (measured from `docs/capture/data.json`, 424 codes total). At 30s that is
  ~3.8h; at 45s ~3.0h; at 60s ~2.3h. ~3.6–3.9s per visit, ~20–25s fixed per map.

## 3. THE TASK: switch the cadence to 45s

The operator: "lets try 45s intervals then." The client's time-skip slider is
5–60s, so 45s is a selectable grid (confirmed by the operator, who re-recorded
the `set-interval` chunk to 30s earlier today in the same Options menu).

### 3.1 Code changes (small)

1. **`timeline.js`**: add `45` to `INTERVALS` → `[5,10,20,30,45,60]`. `planGrid`
   and `stepSecondsFrom` both consult `INTERVALS`; the planGrid refusal message
   joins `INTERVALS` so it self-updates. Check `stepSecondsFrom`'s tolerance
   logic accepts a measured ~45s rate once 45 is in the list.
2. **`timeline.test.js`**: the refusal test asserts the message
   `/5\/10\/20\/30\/60/` — update for 45. Optionally add a planGrid case at
   step 45 (grid points strictly inside a segment, on the 45s grid).
3. **`gui.js`**: change the `set-interval` description from 30s to 45s.
4. **`run.js`**: update the comment around the interval-chunk/`--step` logic
   (it currently says 30s).
5. No changes needed in `phases.js`, `capture.js`, `resolve.js`, `emit.js`, or
   `owdb/contribute.py`. `--step 45` flows through `captureMap` → `planGrid`
   already. Storage stays cadence-independent under change-detection.

### 3.2 Operator actions (the rig, NOT code)

6. **Re-record `chunks/set-interval.json` to 45s** — same flow as the 30s
   re-record: `node tools/replay_bot/gui.js` → http://127.0.0.1:8787 →
   Record → alt-tab to Overwatch, Options → Time Skip Interval → 45s → back →
   F10 ends → Play to check → `node probe_chunk.js set-interval` to verify.
   The chunk is raw absolute-coordinate mouse events and CANNOT be hand-edited
   to 45s; the slider position differs per value, only re-recording works.
   The chunk cannot be imported twice in one session.
7. **Confirm the slider's snap values** and tell the next session, so
   `INTERVALS` matches reality rather than just containing 45. If the slider is
   continuous or has other steps (e.g. 15, 25), align `INTERVALS` to the full
   selectable set.

### 3.3 The grid == skip-interval invariant (why this matters)

Seeking is keypresses on the client's skip interval (`calibrateBar` measures
`stepPx` from one forward press; `stepS` is the seconds that press covers).
`planGrid` grids on `stepS`, and even the drag path converts seconds→pixels
through the same scale. **A 45s grid only exists if the client is actually at
45s.** `--step 45` against a client still at 30s/60s silently mis-scales every
target (design doc §2.2). Until the chunk is re-recorded, the operator can set
45s manually in Options and run `--step 45` (or `--interval-chunk missing`) for
a live check.

### 3.4 Verification

- `node --test` from inside `tools/replay_bot/` — full suite must stay green
  (was 428/428 before this change).
- One live map with the chunk at 45s: expect frame timestamps (`cap-t<N>-*.png`
  in `frames/`) on multiples of 45, the `every 45s inside play -> N grabs` log
  line, and unchanged reads logging `unchanged - not kept`.

## 4. Environment facts (recurring gotchas)

- Windows PowerShell 5.1; tests run from inside `tools/replay_bot/` with
  `node --test` (repo-root discovery does not work).
- `node_modules` (with `@napi-rs/canvas` + `tesseract.js`) lives in
  `tools/replay_bot/`. If packages are missing, install as ONE command:
  `npm install --no-save @napi-rs/canvas tesseract.js` (a `--no-save` install
  prunes any other `--no-save` package).
- `@napi-rs/canvas` is not resolvable from the repo root — run node scripts
  with `workdir=tools/replay_bot` and `$env:NODE_PATH` pointing at that
  `node_modules` when a script needs it.
- The feed gates runs: `run.js` refuses a `docs/capture/data.json` not built
  today unless `--stale-ok`. Rebuild with:
  `$env:PYTHONPATH="C:\Users\ccarn\faceit-sync"; .venv/Scripts/python.exe tools/build_capture_data.py`
  (PYTHONPATH needed; faceit_sync is not installed in the venv).
- Live servers this session: recorder/gui on http://127.0.0.1:8787 (operator's
  rig), review page on http://localhost:8790/ (started by shell; may or may not
  still be running — `node tools/replay_bot/review/server.js replay-bot-2026-09-14 --port 8790`).
- Diagnostic temp scripts from this session live in
  `C:\Users\ccarn\AppData\Local\Temp\opencode\` (`sweep_b.js`, `sweep_kh.js`,
  `check_retention.js`, `diag_*.js`, `pick_matches.py`, `list_live_codes.py`).

## 5. Open questions carried forward

1. **The exact first-sample offset** (design §2.3/§6.1): "sample ~15s after
   round start" can't be hit exactly on an absolute grid — the first sample
   lands 0–45s in depending on round start. Draft recommendation: accept the
   scatter (no per-round drag). Operator still to decide.
2. **b-box geometry**: per-map structure-based strip detection offer is still
   open (durable fix; the alternative is an operator bootstrap re-run each
   time the offset drifts).
3. **Slider snap increments** — needed to finalise `INTERVALS` (see §3.2 item 7).
# Replay-bot 30s cadence + change-detection retention — design

## 0. Why this exists

One night of unattended scouting writes ~5.1 GB of `frames/` (298 maps, 6.1
samples/map at 2.81 MB average per 2560x1440 sample PNG), and the sample
schedule is a fixed 3–5 points per play segment (`samplesFor()` in
`timeline.js`), placed by fractions of the segment, not by time. Two problems
follow:

- **Storage scales with maps, not with what changed.** A stable round keeps
  every one of its grid samples even though the comps did not move; a round
  with a mid-round swap keeps roughly the same number and hopes a grid point
  happened to sit on the swap. Neither is tuned to the match.
- **Swap timing is coarse.** `specs/2026-09-12-replay-bot-segment-observations-
  design.md` explicitly deferred the sampling-density question: its
  segmentation gets *better* as density does, but today a ~10-minute round
  carries three reads, so a swap's moment is only known to the nearest third
  of the round.

The operator has decided the direction (2026-09-14): **sample on a 30-second
cadence, and keep a frame only when the read differs from the previous one** —
the same retention rule the live `docs/capture/` app uses, stated verbatim:
*"same concept as the live manual capture, where if the current read is the
same as the previous, then it isn't stored."* Optimising the capture *process*
itself (grab speed, seek speed) is explicitly deferred to a later date; this
design only changes *when* we sample and *whether we store* the result.

## 1. Scope

**In:**

- `timeline.js` — cadence-based sampling replaces `samplesFor()`/`plan()`'s
  per-segment fractions with a time grid.
- `phases.js` — `sampleAt()` reads before it keeps, and `keepAs` fires only on
  change (or on a read that is not confidently identical).
- The `set-interval` chunk / `run.js`'s session step — the client's skip
  interval must be 30s for the grid to be reachable.
- `prune_frames.js` retention docs — the flat-dir prune policy now needs to
  know sample frames are *sparse*, not one-per-grid-point.

**Out:**

- Overtime detection (research-only; see §6).
- Any change to `resolve.js`, `emit.js`, `owdb/contribute.py`, or the segment
  schema — the 2026-09-12 design is unchanged; it consumes whatever samples
  exist.
- Any change to the capture pipeline's per-sample cost (grab encode, seek
  timing, host process). Deferred by the operator.
- The live `docs/capture/` app's change-detection implementation — this design
  is for the replay bot; the live app already does this and is not changing.

## 2. The sampling cadence

### 2.1 Decision: 30s grid

Replacing `samplesFor()`'s "3 or 5 points per segment, placed at fractions
i/(n+1)" with a **time grid**: one sample every 30 seconds inside each play
segment, plus a first sample as early into the round as the grid allows.

Measured against the real 09-12 session (279 maps with round data, 510 rounds;
median round 309s, mean 359s, 63 rounds over 600s):

| cadence | visits/map | wall time/map | per 298 maps |
| --- | --- | --- | --- |
| today (3–5/segment) | 6.1 | 44s | ~3.6h |
| 60s grid | 11.1 | 64s | ~5.3h |
| **30s grid** | **21.4** | **104s** | **~8.7h** |
| 15s grid | 40.2 | 178s | ~14.8h |

The visit cost is the binding constraint: ~3.9s per visit (seek + settle +
grab + read), plus ~20s fixed overhead per map. At 30s that is a full
overnight job (~8.7h for 298 maps) — the operator chose 30s over 60s knowing
the time, on the grounds that finer sampling is what makes swaps visible and
that the pipeline speedup is a separate, later problem.

### 2.2 Why the grid must match the skip interval

Seeking is keypresses, not pixels: `driver.seekTo()` jumps to start and presses
REPLAY FORWARD in fixed `stepS` steps, and `plan()` snaps every target to that
grid (`timeline.js` §on `plan`). A target that is not a multiple of `stepS` is
not reachable. So:

- The client's time-skip interval must be **30s** for a 30s grid to exist.
  Today the `set-interval` chunk records the options trip to **60s**
  (`gui.js`: "options -> time skip interval -> 60s"), and `INTERVALS` in
  `timeline.js` already includes `30`.
- `capture.js`'s `STEP_S = 20` default and the `--step` CLI override are
  *fallbacks only* — the measured `stepS` comes from `calibrateBar` + the
  `set-interval` chunk. The design therefore changes the **recorded chunk**
  (`tools/replay_bot/recorder.js` output, re-recorded once) rather than the
  constant. `probe_chunk.js` exists precisely because `set-interval` cannot be
  imported twice in a session.

### 2.3 What replaces `samplesFor()`/`plan()`

`timeline.js`'s `plan(segs, n, opts)` becomes `planGrid(segs, opts)` with
`opts.stepS` the only cadence input. For each play segment:

1. The first reachable grid point inside it (`ceil(from/step)*step`), clamped
   to `to - step` so a round is never sampled in its closing second — the
   existing "avoid segment edges" rule.
2. Every subsequent grid point at `+step` while `< to`.

Dedupe across segments and drop duplicates, as today. A segment shorter than
one grid interval keeps the existing nearest-reachable-midpoint fallback (the
`lo > hi` branch in today's `plan()`). `samplesFor()` is deleted; `readStructure`
calls `planGrid` with `stepS` it already has. The log line
(`per + ' samples per round -> …'`) becomes a per-map grid count.

**Open question for the operator** — the "15s into the round" first sample.
The verbatim requirement was *"a capture 15 after the start of a round, then
the next capture is at 1min"*. On an absolute grid, the first sample after a
round start lands anywhere from `0` to `step` seconds in (a round starting at
0:52 on a 30s grid gives 1:00 → 8s in; one starting at 0:58 gives 1:30 → 32s
in), because the grid is anchored to the map, not the round. Getting exactly
15s-in for every round needs either a per-round grid offset (unreachable by
keypresses, since the origin is fixed) or a drag (`seekDrag`) for that one
sample. Draft position: take the first *reachable* grid point and accept the
0–30s scatter — a drag per round is mouse work against a measured-invested
principle — but this is the one place the design defers to the operator. See
§6.

## 3. Change-detection retention

### 3.1 Read first, then decide to keep

Today `sampleAt()` (phases.js:405) does `keepAs('t'+t, ready.path)` **then**
`readHud()`. Change-detection requires the opposite order, and the flip is
free:

1. `read = await readHud(io, matcher, ready.path)` — the settle's frame is
   already in `io.lastFrame()`, a PNG or BMP path the loadImage path already
   handles.
2. Compare `read` to the previous sample's `read` for this map.
3. `keepAs` only if the comparison says *changed* (below).
4. The `framePath` returned is `null` when nothing was kept.

Skipping `keepAs` also skips its ~210ms PNG encode on unchanged frames — the
"same read, no encode" saving. The one-second-look retry (`worstOf < LOW_SCORE`
→ second grab) runs *before* the keep decision, so a mid-transition read that
recovers on retry is compared on the retry's values, and the retry's frame is
what gets kept if the comparison fires.

### 3.2 What counts as "changed"

Pure hero-set equality is too strict for the flag path. A frame that reads
*differently* — even if the diff is wrong — is exactly the frame a flagged slot
needs as evidence. So a keep fires when **any** of:

- any slot's `guid` differs from the previous sample's (`read.a[i].guid !==
  prev.a[i].guid`, same for `b`) — the hero set moved;
- any slot's best score is `< LOW_SCORE` (0.6) on this sample — the read is not
  confidently identical, and the frame may be the transition evidence;
- the slot was `contested` in the previous sample (the `vote.js`/`resolve.js`
  sense — a genuine split in progress needs every frame it can get).

The **first sample of each round** is always kept unconditionally: it is the
round's baseline comp, and `review_out.js` derives every `crops/…-a.png` /
`…-b.png` portrait strip from the round's **first** sample frame, so it cannot
be dropped. "First sample of a round" is known from `segments` (the round
boundaries `readStructure` already produced).

### 3.3 What resolve.js sees

`captureMap()`'s `samples[]` is unchanged in shape and in *content*: every
visit's read goes into the array regardless of whether the frame was kept.
`resolve.js` votes across all reads (`samples[].a/b`), and `emit.js`/segments
run exactly as the 2026-09-12 design specifies — the reads are denser (30s
grid), so vote `support` gets more evidence and `segmentSlot`'s min-run
threshold (`SEGMENT_MIN_RUN = 2`) stops absorbing real swaps. The only
difference downstream is `framePath` being `null` for unkept samples, and the
only consumer of `framePath` is the review page's frame gallery.

### 3.4 The review gallery

`review/server.js` and `review_out.js` show per-round portrait strips built
from a round's first sample, plus per-sample gallery strips only when a
mid-round swap is detected. With change-detection, the per-sample gallery is
*smaller and better targeted*: the gallery only ever contains frames the read
said were different, which is the set the operator needs when a slot is
flagged. No code change here — the artifacts are computed from `samples[]` and
`segments[]`, both of which still exist.

## 4. Storage maths

All measured, not estimated (09-12 session; 2.81 MB average sample PNG):

| | today (3–5/segment) | 30s grid + change-detection |
| --- | --- | --- |
| stored frames/map | 6.1 (all visits) | ~4.3 (only changes) |
| MB/map | 17.2 | ~12.0 |
| per 298 maps | ~5.1 GB | ~3.5 GB |
| visits/map (reads) | 6.1 | 21.4 |

The stored count under change-detection is bounded by **distinct comp states**
(a property of the match — the `2.5 stored/round` figure above comes from real
rounds), not by grid density. Going 60s→30s adds at most 5–15% stored frames
(the swaps that revert within one interval), while adding ~10 reads/map of
resolution evidence. Storage is *cadence-independent*; this is the core of the
decision. Baseline today is actually *more* storage than 30s+change-detection
would produce, at a third of the resolution.

`prune_frames.js` needs one doc correction: today its sample regex is
`/^cap-t\d+-\d+\.png$/` and it keeps all of a session's samples. Under
change-detection the sample frames for a session are the sparse kept set —
which is exactly the recovery value, so the policy (keep newest session's
samples, drop debris) is unchanged; only the README's description of what a
sample frame is moves from "one per grid point" to "one per comp change".

## 5. Explicit non-changes

- **`resolve.js` / `emit.js` / `owdb/contribute.py` / segment schema**: the
  2026-09-12 design is untouched and re-benefits.
- **`capture.js` per-sample cost**: grab, seek, settle timings all stay.
- **`docs/capture/` live app**: already change-detects; not in scope.
- **The flat-frames directory layout**: retained; the ability to map a frame
  back to per-slot flags is *not* being built (that was the point of the
  prune-frames rewrite — see its header). Change-detection makes the kept set
  smaller, which is the same goal approached at the source.

## 6. Open questions

1. **The exact 15s-in-round first sample** — §2.3. Reachable-grid-scatter
   (draft recommendation) vs one drag per round. Needs the operator.
2. **Overtime detection** — verbatim: *"a combination of timegating to
   indicate when an overtime is POSSIBLE (changes wildly depending on map and
   gamemode), then OCR'ing when those timegates are met. we can do some
   research on this later."* Research only; nothing in this design precludes it
   (a 30s grid already samples overtime denser than today).
3. **Cadence vs wall-clock for very long maps** — 63 of 510 rounds ran over
   600s (17:42 Control etc.); 30s grid on those is ~20+ visits/round. Accepting
   the time, or capping visits per round as a safety valve, is a tuning call.

## 7. Testing

- `timeline.test.js` — new cases for `planGrid`: grid points strictly inside a
  segment; dedupe across segments; short-segment fallback; `stepS` mismatch
  refusal (same refusal `stepSecondsFrom` already has).
- `phases.test.js` / `sampleAt` — read-before-keep order; unkept frame returns
  `framePath: null`; one-second-look retry still fires before the keep
  decision; "first sample of round always kept" honored.
- `capture.offline.test.js` — corpus frames re-run under the new retention:
  stored count per map = distinct comp states, not visit count (the corpus has
  known stable and known-swap maps; assert the stable one stores ~1/round).
- `corpus.test.js` / `corpus_sweep.js` — unchanged, but the sweep now also
  reports the change-detection kept-count per frame set, so a map where the
  detector flips every sample is visible in the output before it costs a
  session.
- `resolve.test.js` — unchanged (reads are denser, API identical).
- `prune_frames.js` docs — sample regex still matches kept frames.

## 8. Rollout

1. Re-record the `set-interval` chunk to 30s (`recorder.js`; verify with
   `probe_chunk.js` that it replays at the recorded speed — the chunk cannot be
   imported twice in one session).
2. Land `timeline.js` + `phases.js` + tests.
3. One live map, `--step 30`, compare the kept-set against the pre-change
   behaviour on the same replay; check `resolve` flags still surface the same
   slots.
4. Update `prune_frames.js` README wording; confirm the prune policy (keep
   newest session's samples, drop debris + scratch) still matches.
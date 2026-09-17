# OWDB — Plans

Everything that is **not** built yet: the backlog plus open design decisions,
triaged by priority. P1 should be next (closes a known data gap or a
directly-asked-for fix), P2 is high-value but needs scoping first (owns a design
doc), P3 is idea-level — fun or future, not promised to anyone. A scoped
feature gets its own design document before it is built; built work appears
here only as the "Recently shipped" list, so nobody re-plans it.

## Current season

Season state, the S10 calendar, the cutover and the ordered priorities live in
`AGENTS.md` § Roadmap — read that for what is true today. What is unique to
planning:

- **The Season Finals championship classification decision is still open, and
  has until November.** New in S10 (EMEA/NA, 9–15 Nov, 12 teams: top 4 of Master
  plus top 2 of each lower division). `is_playoff_name` matches only
  `playoff`/`knockout`, so today a `… - Season Finals` championship exports as
  its own division with its own standings table. Widening the matcher is the
  easy half; the hard half is that the Finals are cross-tier, and the
  playoff-attachment model keys on a single region+tier division — there is no
  existing slot to attach them to. Decide it before seeding a Finals room, not
  after. See the full item under Ingest, seasons and cutover.

## Priorities

`AGENTS.md` § Roadmap is the ordered list; the item detail behind it lives in
this file.

1. **Unblock capture adoption** — friction fixes delivered; iterate on adoption.
2. **Scrim mode, phases 2–6** — the open items are under Scrim mode below.
3. **OWCS expansion** — design approved, gated on OWTICS permission; see OWCS
   expansion below.
4. **Statistical capture recommendations** — delivered.

## Recently shipped — do not re-plan

One line each; a shipped item is history, not a queued task. If an item is not
listed here it is still open.

### Dashboard and analytics

- Swap-trigger baseline subtraction — 2026-08-01.
- Unlock NA (region switcher, NA divisions) — 2026-07-30.
- Overview/nav redesign (5-tab nav, Playoffs as a Matches mode) — 2026-07-31.
- Click-to-codes, then league-wide (`capture/?code=…`, `capBtn` team links) —
  2026-07-31 / 2026-08-09.
- Capture onboarding (tour, auto-calibrate preview, impact card) — 2026-08-04.
- Capture recommendations panel — 2026-08-04; playoff games fed in — 2026-08-08.
- Playoff bracket crawl + match pages + scout CTA — 2026-08-06.
- Draft-sim explainability — 2026-08-05; its bugs (stale header, role-locked
  bans, map-agnostic ban suggestion) — 2026-08-10.
- Admin capture panel — 2026-08-06.
- Capture-funnel callout (orientation-strip CTA) — 2026-08-09.
- Team Compare (`#compare=<A>|<B>`) — 2026-08-08.
- Player efficiency rating (Eff column, role-relative) — 2026-08-08.
- Player pages / per-map scoreboard context — 2026-08-24.
- Scrims implementations consolidated into `docs/scrims.html` — 2026-08-08.
- Dashboard modularised into `faceit_sync/dashboard/` parts — 2026-08-08.
- Dead native GUI retired — 2026-08-08.
- OWDB rebrand (site, capture, worker, docs) — 2026-08-09.

### Seasons and cutover

- Season fallback + label, season-state note, SA/OCE regions, S9 frozen at
  `docs/s9/`, IndexedDB rename closed as won't-do, relegation skipped —
  2026-08-27.
- `team_rosters` scoped to the active season — 2026-08-27.
- S10 seed URLs, all ten divisions, in `matches.txt` — 2026-09-05.
- Intermediate seeded in EMEA/NA; `TIERS` gained `Intermediate` — 2026-09-05.
- Cutover: `resolve-season` single pin; `CURRENT_SEASON`/`CONTRIB_DIR` → `s10` —
  2026-09-05.
- S10 code-wipe date registered (`("2026-09-07", …)`, day-early like the
  previous entry) — landed with the 2026-09-08 patch.

### Scrim mode and capture

- Scrim mode phases 0, 1, 2a and phase 4's analysis half — 2026-08-19.
- Hero bans (workshop ban phase + `banrow.js` read-back) — 2026-08-28.
- Spectator scoreboard read (`scoreCanvas`, marker-detected crop) — 2026-09-06.
- Share-code account question resolved: `B4GM8` (published from `ragecomic`)
  re-rolled as `B44BZ` on `gcb` — 2026-09-06.

### Replay bot

- Segment observations: `segmentSlot`, `emit.fromRounds()` from segments, a
  correction collapses segments, `owdb/contribute.py` weights hero-pool/primary
  hero by segment duration — 2026-09-12.
- Low-support made segment-aware (single differing read starts a segment) —
  2026-09-12.
- Mid-UI-transition screenshots: `sample.quiesceMs` 500 → 700ms — 2026-09-12.
- Per-code retry cap (`FAIL_RETRY_CAP`, review Failures panel + retry) for the
  finite feed/queue path — 2026-09-12.
- Frames pruned after a successful upload — 2026-09-12.
- `findNameRow`'s dark-plate assumption (bright/team-colour plates blanked or
  fragmented the name row) replaced with a local-relative fill ceiling,
  floored at the old 0.42 so dark plates are unaffected — 2026-09-15. Shared
  `docs/capture/engine/frames.js`, so live capture's name OCR gets the fix
  too. `tools/replay_bot/nameplate_fill_sweep.js` is the harness; 3 real
  fixtures in `docs/capture/engine/fixtures/` back `frames.test.js`.
- Name-crop contrast replaced with a percentile stretch (`frames.js`'s new
  `applyNameContrast`, shared by `nameCanvas()` and `nameplate.js`'s
  `nameCrop()`) — 2026-09-15. The old fixed formula clipped a bright plate's
  glyph and background together to flat white; the new one adapts to
  whatever range the crop actually has, and measured BETTER than the old
  formula even on already-good dark-plate crops (84/100 vs 79/100 confident
  matches), not just neutral. `tools/replay_bot/nameplate_contrast_sweep.js`
  is the harness. Did not fully solve bright-plate OCR on its own — the next
  fix (below) turned out to matter far more.
- `run.js`'s OCR worker switched from tesseract's default page-segmentation
  mode (PSM 3, full page layout) to PSM 8 ("single word") — 2026-09-15. A
  name crop is always one word; PSM 3 regularly found no text region at all
  on it, returning empty at zero confidence on images that read perfectly by
  eye. The single biggest lever of the three name-OCR fixes: nearly TRIPLED
  confident matches on known-hard bright-plate crops (11/75 → 31/75 in a
  sample) and sharply improved already-good crops too (53/75 → 65/75).
  Together, all three fixes recovered 616+ previously-abstained slots across
  106+ maps when `tools/replay_bot/reprocess_attribution.js` re-ran the fixed
  OCR against already-captured maps — on the active `2026-09-15-full` batch
  the review queue fell from 99 flagged maps to 27 of 390, and further as
  Doctrine's registration (below) resolved more role-group cascades.
- The review page stops offering an already-claimed player as a manual-
  correction candidate for a different slot (`claimedElsewhere()`, reads
  `effSlot()` so it reflects both an automatic confident match and a prior
  manual correction uniformly) — 2026-09-15.
- Doctrine (support) registered as an operator-added hero (`custom:doctrine`)
  from a real replay capture rather than the normal live-client `refs learn`
  flow — 2026-09-15. Also fixed a real gap it surfaced: an operator-added
  hero's role never reached `hero_roles` in `docs/capture/data.json`
  (`tools/build_capture_data.py` only ever queried FACEIT's own `heroes`
  table), which abstains the hero's WHOLE role group via `assign.js`'s
  exact-cover check, not just its own slot. Only a red-team portrait ref
  exists so far — `match.test.js` tracks the missing blue-team one as a
  known, deliberate gap rather than silently weakening that test.
- A map can be excluded from a contribution without deleting it
  (`status: 'excluded'` + `exclude_reason`/`prior_status`, `finalize()`
  drops it, the review page shows it dimmed with a Restore button) —
  2026-09-15. Used to pull 252 maps (every region) finished
  2026-09-12T19:00Z–2026-09-15T19:00Z from the active batch, since Doctrine's
  portrait ref was unverified/absent for that whole window and there is no
  way to rule out a silent misread map by map. None had reached the live
  site. Their codes are queued at
  `tools/replay_bot/state/doctrine-window-recapture.txt` for a re-run.
- The review page's "Loop every live code" path (the unattended overnight
  one) now always passes `--fail-streak-cap 8` instead of `run.js`'s
  attended-run default of 2 — 2026-09-15. The tight default is what killed
  the original 545-code overnight run after two back-to-back timeouts that
  turned out to be the client losing its session state, not a stuck client.
- `resolve.js` flags `cross-role-swap`: a confirmed segment-to-segment swap
  between two known, different roles within one round, which FACEIT's role
  lock makes physically impossible — 2026-09-17.
- `resolve.js` drops takeover-screen samples (>=6 of 10 slots reading
  `ABSENT_GUID` at once) before they reach the vote or segment chain,
  flagging the round `takeover-frame` — 2026-09-17.
- `T.planGrid`'s short-segment fallback takes two quarter-point samples
  instead of one middle sample, so a round too short for the normal grid
  step can still catch a real mid-round swap — 2026-09-17.
- A dead-but-present player no longer reads as a leaver: `calib.deathMarker`/
  `crop.cellDeath` detect the death-elimination X (a death desaturates the
  ult badge too, unlike a real disconnect), `phases.js` reads `DEAD_GUID`
  instead of `ABSENT_GUID`, and `resolve.js` drops it entirely rather than
  treating it as evidence — 2026-09-17.

## Capture app and ref library

- **P1 (record, not queued) — "Teach it a miss" does not work; root cause still
  unknown.** Reported by the operator 2026-08-13, re-confirmed in game
  2026-08-14 after a fix that turned out to be incomplete. Deprioritised by the
  operator ("I don't care about hero correction"), so this is a record. What is
  verified working and can be skipped: the `#refpanel` collapse bug (fixed —
  it was not the symptom), `learnCrop()` returning a 3072-byte crop, `addRef()`
  storing in IndexedDB, the "N learned" counter, the ten hero dropdowns
  rendering. The fault is downstream of storing a ref — most likely a learned
  template does not beat the built-in on the next read. Start at
  `bestMatch()`/`matchCrop()` in `docs/capture/engine/refs.js` and how
  `LOCAL_REFS`/`REFS` are ordered and scored, not at the UI. Cannot be
  reproduced headlessly: it needs a live frame and the operator.
- **P3 — Map-name verification: answered for scrims, closed as impossible for
  league.** The map name is not reliably on the observer HUD — but the scrim
  workshop code can put it there and does (`MAP   : SAMOA`, confirmed in game
  2026-08-27), so a scrim's map is verified against the HUD instead of trusting
  the operator's panel selection. League captures have no such row and no
  workshop code of ours; close that half as impossible rather than faking it.
- **P3 — Ref library live-frame validation is ongoing.** Refs that have never
  faced a live frame shrink with every capture; keep `doctor`/`coverage`
  surfacing the gap rather than hiding it.
- **P2 — The two capture pages still read hero portraits on the old ±2 search.**
  The replay bot's matcher was widened to ±14 on 2026-09-15 and its reads
  improved measurably (low-score 24.7% → 2.9%; see `ARCHITECTURE.md` §6), but
  `docs/capture/index.html` and `docs/capture/scrim.html` still call
  `bestMatch(cellGrayPadded(frame, cell), side)` — the `radius == null` legacy
  window. They cannot just pass the radius: `cellGrayPadded()` pads with a
  **scaled copy** of the crop, so a wider window there changes the candidate's
  scale rather than its offset, and `calibration.js`'s fast centre-only probe
  depends on that buffer. Giving them the alignment search means a new
  edge-clamped cell wrapper in the shared engine (the page-side equivalent of
  `matchCrop`). Deliberately left alone on the operator's call (2026-09-15)
  because `tools/verify_capture_browser.js` does **not** exercise the hero read
  at all, so the change would land on live capture with no automated coverage.
  Do it only alongside a browser check that actually performs a read.
- **P3 — A residual handful of bright-plate glyphs stay unreadable even
  after all three name-OCR fixes (2026-09-15: fill ceiling, contrast
  stretch, PSM 8 — see Recently shipped, replay bot).** What looked at
  first like a font-rendering problem (a hollow/outlined glyph style on one
  plate variant) turned out to be mostly a tesseract page-segmentation
  problem instead — PSM 8 alone recovered most of what the "outline" theory
  predicted would need morphology to fix. What is left after all three is a
  much smaller, not-yet-characterised tail; no working theory for it yet.
  Low priority: the operator finished reviewing the active batch 2026-09-15
  (99 flagged maps at the start of the day down to 12 maps carrying a
  surviving non-`contested` flag they chose to accept anyway — 5
  `attribution-abstained`, 7 `low-support` — everything else clean or
  excluded, see the 252-map exclude entry above).

## Replay bot

The replay bot lives on `tools/replay_bot/` and its full account is in
`ARCHITECTURE.md` §14. Open items:

- **P3 — Per-code retry-and-requeue for the code-stack loop.**
  **DECIDED 2026-09-14 — implemented in `run.js`.** The finite feed/queue path
  has a per-code retry cap (`FAIL_RETRY_CAP = 3`, sits *alongside* the
  two-consecutive-failure abort — 2026-09-12). The `--code-stack` loop is
  explicitly skipped from the attempt ledger (a code-stack code is meant to be
  imported again), so `CodeStack.rotate()` still cycles every code regardless of
  outcome and the whole-run abort still applies there. The operator chose: keep
  the circuit breaker and add a per-code cap **alongside** it; the cap lives in
  `run.js` next to `FAIL_RETRY_CAP`; only **post-import failures** count
  (import/environmental failures never entered the ring, so they are safe to
  retry next rotation); retirement is **log-and-skip for the run** — the code is
  rotated to the bottom and skipped, not deleted, and the run stops if every
  code retires. The loop's failure table is in-memory and scoped to the run
  (`pullLoopCode`/`countLoopFailure` in `run.js`); nothing touches
  `state/attempts.json`. One-shot-per-code still holds for a finite
  `--codes`/live-feed run.
- **P3 — No reference for the "no hero picked yet" portrait state.** Before a
  player locks in, their slot shows a generic placeholder — a plain silhouette
  with a "?" icon, 0% ult — instead of real hero art. The ref library has no
  template for it, so a frame caught in that window is matched against the
  closest-looking real hero and lands as a normal-looking but wrong
  low-score/low-support read rather than something the operator can spot as a
  capture-timing issue. Relevant to round 1's opening seconds (at the edge of
  `ASSEMBLE_GRACE_S`'s 10s grace) and to a fresh respawn after a mid-round swap.
  Needs its own ref entry (or entries — the placeholder likely renders
  identically on both sides) so "no pick yet" is recognised as its own outcome.
- **P3 — Echo copying a hero reads as that hero.** Echo's ult copies any other
  hero; while copied she gets that hero's portrait, identical in shape but
  heavily blue-tinted. A capture frame mid-copy reads as the copied hero, not
  Echo, because there is no "Echo-as-X" template. Needs Echo-as-X refs or a
  blue-tint detector that overrides the match.
- **P3 — Replay-bot accuracy: three unexplained findings (2026-09-11
  brainstorm) — PARTIALLY EXPLAINED 2026-09-16, needs re-measuring.** The
  aggregate side-b deficit (mean 0.760 vs side a 0.820 over 1410 slot-reads)
  was not partitioned between these three at the time:
  - **Side-b tile misalignment.** Still open as stated — native (`PrintWindow`)
    vs browser (`getDisplayMedia`) capture still hasn't been cross-validated
    pixel-for-pixel for a within-session offset. Not the same axis as the
    finding below (that's live-match vs replay-viewer *content*, not a frame
    offset within one capture), so don't assume this is closed too.
  - **Ref-library confusion pairs — likely explained, not a template problem.**
    This list named **Cassidy↔Pharah** specifically. 2026-09-16 found
    `refs.json` had been (and, via a since-fixed `build_capture_refs.py`
    default, kept getting) built from a live-spectate ROI profile instead of
    the replay-viewer one `tools/replay_bot` actually reads against — proven
    directly: the same Cassidy portrait from the two sources scores as low as
    0.28 cosine similarity against ITSELF, with an exhaustive ±15px
    realignment only recovering it to 0.40. Rebuilding from the correct
    profile took Cassidy from the worst hero in the library (mean 0.471) to
    0.861, and **Pharah moved too** (0.573 → 0.868) — strong circumstantial
    evidence this "confusion pair" was the same source-mismatch bug, not
    64×36 running out of resolution. Action: re-run the full pairwise cosine
    similarity sweep against the current `refs.json` — if Cassidy↔Pharah and
    the other pairs have closed up, this line item is source contamination,
    closed; if a real margin remains, template distinctiveness is still live
    and worth its own investigation.
  - **Transient visual noise corrupting crops.** Still open, unmeasured
    against current `refs.json` — a red damage-vignette wash and
    elimination/respawn overlays would depress scores by a different
    mechanism than either finding above and wouldn't be fixed by the
    2026-09-16 rebuild.
  A whole-round low-score red flag (distinct from the per-sample flag) is
  still worth considering, since temporal voting is blind to a problem
  consistent across all of a round's samples. `tools/replay_bot/
  match_accuracy_sweep.js` (added 2026-09-16) is the standing tool for
  re-measuring any of this against the live corpus going forward — it isn't
  pairwise, so a confusion-pair re-check still needs its own script.
- **P3 — refs_trainer replay-save verification.** Research (2026-09-11)
  concluded the replay-save trigger is "in progress AND ends"; the trainer's
  `Set Match Time(0)` loop during Setup/Assembling may keep a match from ever
  entering "in progress", so no save fires. Unconfirmed: whether spectator-only
  participation is excluded, and whether `Declare Match Draw`/`Declare Player
  Victory` count as a qualifying end. Empirical test: run the updated trainer
  but let one round reach a natural, un-reset end, or read `Is Game In
  Progress` on a debug HUD.
- **P2 — Recapture the four 2026-09-16 sessions despite reprocessing already
  fixing most of them.** `reprocess_hero_match.js` recovered ~1,020 bad
  slots across the sessions affected by the refs.json regression (see
  CHANGELOG), but it works from whichever crops were saved at capture time —
  a round the ORIGINAL run read as stable only kept one sample's crop, so a
  genuine swap that fooled the broken matcher into never flagging it as
  contested has no second sample to recover from. The operator wants these
  recaptured live anyway despite this being a narrow, unquantified gap — do
  that before spending further effort trying to bound how many rounds it
  actually affects.
- **P3 — `tools/assign_eval.py`'s corruption model doesn't exercise the
  2026-09-16 cross-role rescue at all.** It's a separate Python port of
  `assign()` (`role_constrained()`), corrupts OCR *names* only, and its
  ground truth always hands the resolver the correct role per slot — the
  rescue pass only ever runs when a role-count mismatch happens, which this
  harness has no way to simulate. AGENTS.md's "re-run assign_eval.py on any
  threshold change" doesn't strictly apply (FLOOR/MARGIN are untouched), but
  the harness is silent on whether the rescue pass could ever reintroduce
  wrong-assignment risk. The JS unit tests added the same night (including a
  contested-claim case proving it still abstains when two slots or players
  compete for the same decisive match) are the real coverage for now; porting
  a role-mismatch model into the Python harness would be the more rigorous
  version.
- **P3 — Archive-to-media-server blocked on a server-side permission.**
  `tools/replay_bot/archive_session.ps1` (2026-09-16) moves a session's
  `out/<session>/` data to the mapped `Z:\` share once reviewed, verifying
  the copy before deleting the local copy — written and logic-tested, but
  `Z:\backups` only grants write to the share's root Samba user/group, not
  the one this machine's connection maps to (`Z:\polybot` does grant it,
  confirming the share itself is reachable and writable, just not there).
  Needs the operator to create a writable folder for this on the server
  (mirroring `polybot`'s permissions) before this can run for real. Also
  relieved an acute local disk crisis the same night: `tools/replay_bot/
  frames/` (23GB of retained HUD frames) was moved to `D:\faceit-sync-data\
  replay_bot_frames` with a directory junction left at the original path, no
  code changes needed — C: 12.5GB free → 35GB.
- **Watch — single-read segments.** The low-support fix trades a flag for
  coverage: a lone misread that used to be absorbed into a running segment now
  becomes its own segment and is no longer flagged. Watch the next full review
  for stray misreads silently going uncorrected; if they show up, treat
  `reads.length === 1` segments with more suspicion than multi-read ones.
- **P3 — TypeSafe/Jev as replay-bot's decision loop (idea-level, not
  designed).** TypeSafe AI's Jev (`api.typesafe.ai`) returns a typed judgment
  — a choice, a yes/no probability, or a score — from text/state in ~150ms,
  cheaply enough to call on every decision point. It does not see images or
  take actions; a public demo of it playing DOOM works by feeding it the
  game's already-structured internal state and letting separate code turn its
  typed answers into inputs. Replay-bot already has that same shape: it
  already derives structured state from screenshots (OCR text, panel
  visibility, playhead position, confidence flags) and already executes
  actions via automation — only the "what do we do next" step is currently
  hand-tuned heuristics (`segmentSlot`'s swap-confirmation rule,
  `timing.js`'s `quiesceMs`, `vote.js`'s support threshold). The idea is Jev
  as that decision step, sitting on top of state the pipeline already
  computes — not a vision or UI-automation capability, which it does not
  have. Evidence so far (2026-09-16, four rounds / ~60 calls, prototype
  scripts under `tools/replay_bot/PROTOTYPE_typesafe_*.js`, uncommitted, not
  wired into anything): team-name-to-FACEIT-roster resolution validated well
  — 45/45 correct across increasingly adversarial cases, and confidence
  cleanly separated every wrong answer from every hard-but-correct one.
  Player-name attribution (the closer analogue to `assign.js`'s job) did
  **not** carry the same margin — fabricated lookalikes produced confident
  wrong answers overlapping genuinely-correct confidence scores, so it can't
  be gated the same way without more work. TypeSafe came out of stealth the
  same day this was evaluated, with no track record, so any real integration
  should stay optional and trivially removable, never load-bearing. Nothing
  decided; needs its own scoping pass (and per-heuristic validation, not a
  blanket swap) before it becomes a real plan.

  **2026-09-17 — shadow-mode test of the actual idea above (screen-state ->
  Jev decides the next capture-loop action), not just name matching.**
  Three rounds against the 14 hand-labelled real frames in `corpus.js`
  (never a live client, never a replay code), feeding Jev the SAME raw
  numeric signals the deterministic code uses (`Crop.hudTint`,
  `panelRowFraction`, `playheadX`) rather than the already-thresholded
  booleans - scripts `tools/replay_bot/PROTOTYPE_typesafe_shadow_mode{,_v2,_v3}.js`
  (uncommitted). Findings, most to least important:
  - **Jev matched the deterministic threshold almost perfectly on clean
    geometric signals** (events-panel-open: 14/14 every round; playhead-
    visible: 13/14, and that one "miss" is a corpus label that contradicts
    its own written description - likely stale, not a real disagreement).
  - **It was measurably worse on the noisier tint-difference signal** ("is a
    replay actually on screen") out of the box - 10/14, specifically wrong
    on exactly the adversarial menu/list-screen frames the corpus exists to
    test, always erring toward "yes, proceed" (the costly direction for a
    live loop).
  - **Prompt iteration mostly fixed it.** Telling Jev to treat borderline
    tint as weak evidence and cross-check the other signals raised that
    judgment to 13/14. Collapsing three independent yes/no questions into
    ONE compound Choice over a named screen-state vocabulary (closer to how
    a human reads the whole picture at once) did better on the metric that
    actually matters - which action to take next - than either the
    3-question version or the reworded version alone. Combining both ideas,
    plus explicitly framing "a real plate needs BOTH sides confidently
    positive together, never just one" (closed a specific false positive on
    an ESC-menu frame where one side's tint read positive by UI-chrome
    coincidence), reached 13/14 on the state judgment and 12/14 on the
    resulting action - the best of four attempts.
  - **Real architectural gotcha:** questions asked in parallel over the same
    state in one call CANNOT see each other's answers (confirmed against
    TypeSafe's own docs). Rewording only the "is a replay on screen"
    question fixed that question but did NOT fix the sibling "what action
    next" question asked alongside it in the same call - it kept reasoning
    from the old framing. If one judgment should inform another, either
    reword both, chain two sequential calls, or collapse them into one
    compound decision (which is what ended up working best here anyway).
  - **Confidence-gating is not a universal safety net.** It cleanly
    separated the menu-screen false positives (wrong answers 0.51-0.77,
    right answers 0.81-0.95+) in every round - consistent with the
    team-name-matching finding above. But the one frame that stayed wrong
    across all three prompt iterations (a genuine near-threshold
    mid-transition frame, tint reading just under the real cutoff) got
    MORE confident with each rewording (0.77 -> 0.66 -> 0.92), ending
    *inside* the confidence range of genuinely correct answers for that
    same state. A confidence gate would have caught every OTHER failure
    mode tested tonight and missed this one. Treat confidence as a strong
    signal, not a guarantee, especially near a measurement's own noise
    floor.
  - Side finding, not yet fixed: `corpus.js`'s `loading` witness has
    `playhead: true` even though its own hand-written description never
    mentions a playhead and both Jev and the deterministic code
    independently agree it should be `false` - worth a one-line correction
    next time someone is in that file.
  Still idea-level. Confirms the underlying decision-loop idea has real
  legs on structural signals and can be pushed a long way on noisier ones
  with better prompting, but also confirms it needs per-signal validation
  (exactly like the team/player-name split above) rather than a blanket
  "Jev drives the loop" swap - and needs a plan for the one failure mode
  prompting couldn't reach before anything here touches a live run.

  **2026-09-17, rounds 8-9 — first LIVE test, real client, real keys, a
  throwaway/practice account with reusable codes (user's explicit choice,
  see [[typesafe-vendor-caution]] - this is the user's call, not a default).**
  Script: `tools/replay_bot/PROTOTYPE_typesafe_live_nav.js` (uncommitted).
  Deliberately narrow scope: only the "get an already-open replay to a
  fully-ready state" job (press N / press K / wait / stop), reusing the
  real `capture.js`/`driver.js`/`phases.js` path, not fakeio. Safety rails:
  hard action cap, stuck-detection, and a `not_a_replay`/`uncertain_escalate`
  call is never followed by any recovery attempt (ESC/menu clicks) - a
  human looks instead, since blind recovery is exactly the failure shape
  that cost real codes historically (screen.js's header).
  - **Found a real, NEW bug in the existing deterministic code, not in
    Jev.** With the replay actually playing, `Crop.playheadX` read a false
    knob from moving game scenery (64px wide, fixed position) for 8 straight
    frames. Re-tested with the replay genuinely paused (confirmed via
    `phases.ensurePaused`, `pressed:false`) - the false knob persisted at a
    DIFFERENT width/position (68px) - proving it is not a motion artifact
    but static scenery, and that its width/position varies run to run
    because the replay's actual paused position differs. This is the same
    failure SHAPE as the historical XTK7MM/4TNEAJ incidents, just landing
    inside the 33-100px width band those were tightened around instead of
    outside it. **Root cause: production has apparently never exercised
    `playheadX` against arbitrary mid-match paused footage as a starting
    screen** - only controlled screens (GET READY, menus) - so this class
    of false positive had no chance to surface before. Worth a maintenance
    look independent of anything to do with Jev.
  - Jev's read of the false signal was textbook correct given its input
    (controls read as up, panel is shut, press K) - K against genuinely-down
    controls is a real no-op, confirmed on screen: nothing moved, 8 times.
  - **Two real script bugs found and fixed live:** (1) the first
    stuck-detection used exact equality on live signal readings, which
    never matches even a genuinely static screen (real captures have grab
    noise) - it silently never fired, and the hard action cap was the only
    thing that stopped the run both times. Fixed with a numeric-tolerance
    comparison. (2) The deeper fix: added CAUSAL feedback - after every
    keypress, compare signals before/after and tell Jev on the next call
    whether that specific action demonstrably changed anything ("had NO
    observable effect - the reading that suggested it was needed may
    itself be wrong"). This is the same principle production's own
    `mediaVisible()` uses (verify by observing a caused change, not by
    reading a static frame) - a static false positive cannot fake a change
    it never causes. Result: confidence on the repeated wrong call dropped
    sharply (0.94 -> 0.56) and the (now-fixed) stuck-detector cut the run
    off after 2 steps instead of 8. It did NOT fully self-correct to a
    different action, though - it hedged confidence rather than switching.
  - **The fix that actually worked, and the lesson behind it (flagged by
    the user, not found by me first):** `STATE_TO_KEYPRESS`'s mapping was
    already a fixed rule, not a Jev decision - the ONLY thing Jev was
    asked to infer was "are controls already up", which is exactly the one
    thing driver.js's real `ensureEventsViewer` does NOT treat as an
    inference at all ("N is pressed EVERY TIME because that is what the
    client needs" - its own comment, unconditional, no classification
    first). Asking Jev to classify a state production never bothers
    classifying was the actual design flaw, not a prompting problem. Fix:
    press N unconditionally as a fixed first step (matching production
    exactly, no Jev call involved), THEN hand the rest of the decision
    (does the panel need K, is it done, is something wrong) to Jev - the
    parts that were genuinely reliable all night (panel-open detection:
    100% across every round, shadow and live). Result: a clean, fully
    correct, fully autonomous 2-action run (N, then Jev-chosen K) that
    reached the ready state correctly, with a REAL knob this time (40px,
    inside the documented genuine-control range) confirming the
    distinction holds.
  - **General lesson for any future Jev-as-decision-maker work:** don't
    hand Jev a judgment call that the deterministic system already treats
    as a fixed rule. Reserve its judgment for the places that are
    genuinely ambiguous (which this session's testing has now mapped
    fairly precisely - see the punch list below).

  **2026-09-17, round 10 — the toggle-wrong-direction case, live, item 1
  below, RESOLVED CLEAN.** Set up cold: replay already fully ready (controls
  up, events panel open) before the script ever ran, so its unconditional
  first N press was guaranteed to hide controls that were already up - the
  actual historical XTK7MM/4TNEAJ failure shape, deliberately engineered
  instead of stumbled into. Full autonomous 3-action recovery, no human
  intervention: **step 1** - after the wrong-direction N, signals read
  `knob:null, rows:0` (tints still confident) - Jev correctly called
  `replay_controls_down` (NOT fooled into thinking controls were still up)
  and pressed N again, at **confidence 0.70** - below the 0.75-0.80 gate
  [[typesafe-capture-loop-shadow-mode]] established as reliable, on a call
  that was in fact correct. **step 2** - causal feedback correctly reported
  "N WAS followed by a real change"; signals now `knob:present, rows:0` -
  a second-order effect neither planned nor asked about: the events panel
  had ALSO visually dropped when controls went down, confirming driver.js's
  own comment that the panel only renders while controls are up. Jev called
  `replay_panel_shut` (0.93) and pressed K. **step 3** - `rows:0.587`,
  knob present - `replay_panel_open` (0.93) - DONE. So the recovery needed
  one MORE step than the direct N-undo (N, then N-again, then K to redraw
  the panel), and Jev/causal-feedback handled the whole chain unprompted,
  matching driver.js's documented dance end to end. **Confirms the
  confidence-gate caveat from shadow-mode is not a one-off**: this is a
  second real instance (after the mid-seek frame) of a correct call landing
  below the established gate threshold - a naive gate would have escalated
  a call that needed no escalation. Treat 0.70-0.80 as a genuine grey zone
  for this signal family, not a hard cutoff.

  **Next tests, for a fresh session dedicated to this (this list is meant
  to stand alone - read this whole PLANS.md entry plus
  [[typesafe-capture-loop-shadow-mode]] and [[typesafe-live-navigation-testing]]
  memory files for full context before starting):**
  1. ~~The toggle-wrong-direction case~~ DONE above (round 10).
  2. ~~A genuine `not_a_replay` scene, live~~ DONE (round 10, same session).
     Pressed ESC to back the live client out to its menu, then ran the
     script cold. Signals read clearly asymmetric (`L:29.3, R:-31.3` - one
     side positive, one negative, exactly the "not a real plate" pattern
     the corpus/prompt work targeted) - Jev called `not_a_replay` at 0.88
     and the script stopped with no recovery action, as designed.
     **But found a real design gap while doing it:** the script's
     unconditional-N-first step (the round-9 fix for the toggle case,
     above) fires BEFORE any screen classification at all - it pressed N
     blindly into the ESC menu before Jev ever saw a signal. Harmless this
     time (the menu doesn't appear to bind N), but it is exactly the
     "blind key into an unknown screen" risk the whole `not_a_replay`
     safety rail exists to prevent, and this is the first time the script
     was ever run starting from a confirmed non-replay screen. Fix before
     going further: read + classify first; only do the unconditional-N
     step once the screen is already confirmed to be a replay (a `pause`
     first only helps if you're already looking at the right thing).
     **FIXED same session**: `PROTOTYPE_typesafe_live_nav.js` now reads +
     classifies BEFORE any key is sent; a `not_a_replay`/`uncertain_escalate`
     result there stops the script with zero keys sent, ever. Re-ran against
     the same ESC-menu state cold: stopped correctly (`not_a_replay`, 0.86)
     with no key sent at all, confirmed by the log. **Residual, not fixed
     (out of scope tonight):** `phases.ensurePaused` - real, pre-existing
     production code, unchanged, called even before the new pre-check -
     detected motion in the ESC menu itself (likely a menu fade/animation)
     and pressed SPACE blindly, same category of "act before classifying"
     gap, just upstream of anything Jev touches. Harmless observed effect
     (the very next read still correctly reached `not_a_replay`), but
     production's own screen.js invariants apparently assume this is only
     ever called already-inside a replay - worth a maintenance look
     independent of the Jev work, not urgent tonight.
  3. **Characterize the newly-found `playheadX` scenery false positive
     properly**, independent of Jev: pause the replay at several different
     random points and log raw `Crop.playheadX` readings at each, to learn
     whether this is rare or common, and whether a tighter guard (not just
     width) could catch it in the deterministic code directly - this is a
     real production bug now, found via live Jev testing but not actually
     about Jev.
     **PARTIALLY DONE (round 10, same session), inconclusive.** New script
     `tools/replay_bot/playheadx_scenery_sweep.js` (uncommitted): forces
     controls down ONCE from a known-up state (no toggle ambiguity, no Jev
     call at all), then seeks to 6 spread-out positions (15/60/150/300/
     480/700s) and logs raw `Crop.playheadX` at each - confirmed by
     `panelRowFraction`+`hudTint` genuinely differing per sample that the
     seeks landed on different scenery, not the same frame six times.
     **Result: 0/6 false positives** on this map/replay code - a real
     negative result, not a null test, but only six samples on one replay.
     Could not cross-check against the ORIGINAL round-8/9 false-positive
     frame: `makeLiveIo`'s frame filenames are a plain per-process counter
     (`livenav-read-0.bmp`, `-1.bmp`, ...) with no run id, so every session
     tonight silently overwrote the previous one's frames at the same
     index - the actual evidence frames are gone. Minor tooling gap worth
     fixing before the next characterization attempt: stamp frame
     filenames with a run id (timestamp or pid) so evidence survives past
     the next invocation. Real conclusion needs either more samples, more
     maps/replay codes, or deliberately trying to reproduce the original
     session's exact conditions rather than an arbitrary spread.
  4. ~~Retry the one shadow-mode failure that resisted 3 prompt-engineering
     rounds (`mid-seek`) live~~ DONE (round 10, same session), with a real
     nuance. New script `tools/replay_bot/PROTOTYPE_typesafe_midseek_probe.js`
     (uncommitted): from the ready state, press one forward-seek key, read a
     frame deliberately EARLY (before the real settle-wait finishes) at two
     different delays, and classify it both blind and with a plain factual
     causal note ("a seek was just issued, weak signals are expected").
     **Trial 1 (150ms delay) - full blackout, the harder case:** tints
     collapsed completely (`L:0, R:0`), rows also 0 (the panel blanks
     mid-transition too, same coupling round 10's toggle-recovery test
     found for controls), knob present but at a shifted transient position.
     Both blind (0.82) AND hinted (0.99) correctly called
     `mid_transition_wait`, not `not_a_replay` - the round-7 prompt fix
     (explicit `mid_transition_wait` vocabulary entry) held up live even
     against a MORE extreme signal collapse than the offline corpus frame
     ever showed, and the causal hint pushed an already-correct call to
     near-certain. Settled ground truth confirmed `replay_panel_open` (0.96).
     **Trial 2 (350ms delay) - partial recovery, closer to the original
     offline case:** tints had already substantially recovered (`L:93.9,
     R:65.1` - actually overshooting baseline, likely a brief redraw flash),
     rows unaffected, knob shifted again. Both blind (0.90) and hinted
     (0.52) correctly called `replay_panel_open` - but **the causal hint
     dropped confidence by 38 points on a call that was already right**,
     the mirror image of trial 1's boost. **Real finding: the causal note
     is not a uniform confidence booster - it makes Jev generically more
     hedging/skeptical, which helped when the underlying signal genuinely
     was still ambiguous (trial 1) and only added unwarranted doubt when it
     wasn't (trial 2).** Caveat as originally written after trials 1-2:
     neither is a strict apples-to-apples retry of the specific offline
     corpus frame (persistent WEAK tint just under the real cutoff, not a
     full 0 or an overshoot).
     **Trial 3 (220ms delay) closed that gap and gives the cleanest answer
     to the original question.** Tints read weak AND wrong-signed on both
     sides together (`L:-14.0, R:-6.9`) - the actual close analogue to the
     resistant offline frame's borderline-weak profile, not a full collapse
     or a recovery overshoot. Blind classification got the right answer
     (`mid_transition_wait`) but at only **0.25 confidence** - exactly the
     kind of correct-but-unusable-confidence call a gate would have to
     escalate. **With the causal hint, confidence rose to 0.88 on the SAME
     correct answer** - a real, clean instance of causal feedback doing
     precisely what 3 rounds of offline reword-only prompting could not:
     turning a correct call nobody could safely act on into one that is.
     Combined with trial 2's finding (the hint can also unhelpfully lower
     confidence when the signal was never actually ambiguous), the fair
     summary is: the causal note's job is recalibration toward whatever the
     evidence actually supports, not a one-directional confidence boost -
     and on the case this test was built to retry, that recalibration
     landed on the right side.
  5. **Extend scope past "get ready" into seeking/sampling** - the more
     complex, higher-stakes decision territory (choosing a seek target,
     verifying a landed position, deciding whether a read is trustworthy
     enough to keep) that this session never touched live at all.
  6. ~~Measure live latency/cost at this scale for real~~ DONE (round 10,
     same session). Instrumented `PROTOTYPE_typesafe_live_nav.js` with real
     wall-clock timing around every Jev API call and the whole run. A full
     3-action ready-recovery run: **4491ms total, 4 API calls summing to
     1448ms (32% of total run time)** - individual call latencies
     706/230/247/265ms (the first call runs colder than the rest). For
     comparison, `timing.js`'s OWN fixed budget for just the deterministic
     post-N playhead poll (`media.tries * waitMs`) is up to 2500ms, before
     any grab/settle cost - so the API overhead is a minority of the
     per-step cost even before counting the grab+settle time both
     approaches pay identically. Real answer to "could this be faster":
     grab/settle dominates either way; Jev's added latency is real but not
     the bottleneck.
  7. ~~Test an already-open-panel cold start~~ DONE (round 10, same
     session) - and it FAILED the first time, revealing a genuine
     inefficiency the fix above's latency run exposed directly: cold-
     starting the script against an ALREADY fully-ready screen (pre-check
     correctly read `replay_panel_open` immediately) still ran the
     unconditional-N step anyway, blindly undoing and redoing state that
     needed no change - 3 extra actions and ~3.7s wasted on a screen with
     nothing to do. **Fixed same session:** the pre-check now short-circuits
     on `replay_panel_open` specifically and stops with ZERO keys sent.
     Safe to special-case, unlike the round-9 mistake this echoes: that one
     asked Jev to infer the narrow "are controls up" fact production treats
     as a fixed rule, where this shortcuts on the compound "fully done"
     classification that has read 100% reliably across every round tonight,
     shadow and live. Verified idempotent across two consecutive cold runs
     against the same ready screen: both stopped in ~1.6s total (one API
     call, ~620-640ms) with no key ever sent.
  `TYPESAFE_API_KEY` for continuing any of this is in
  `tools/replay_bot/state/typesafe_key.json` (gitignored, see
  [[typesafe-capture-loop-shadow-mode]] for why it isn't in memory itself).

  **2026-09-17, round 10 extension - user-directed, into a NEW screen
  family: the replay list / import flow, before a replay is even open.**
  New script `tools/replay_bot/PROTOTYPE_typesafe_import_probe.js`
  (uncommitted). Scoping first (see [[typesafe-live-navigation-testing]]
  for the full reasoning): `phases.js`'s seeking/sampling code turned out
  to be already fully deterministic with no exposed ambiguity worth
  testing, but `clientstate.js`'s import-success check is genuinely crude -
  `CS.waitFor(io, true, ...)` polls one boolean and throws a single generic
  "timed out" with no distinction between an invalid code, the client's
  10-most-recent-import limit, a slow network, or a chunk started from the
  wrong screen. That gap, plus classifying which of the client's PRE-replay
  screens is on screen (replay list / ESC menu / some other front-end menu
  / actually already in a replay), was the target. One real import was
  performed (a code from the existing rotating pool in
  `state/console_codes.json`, the same mechanism `run.js`/the console
  already use - not a fresh league code), navigated with `run.js`'s own
  real pre-import sequence copied verbatim (`clearEscMenu`, back out of the
  replay list, `leave-replay` if needed, then the `open-import` chunk) -
  never reinvented. Jev rode along OBSERVATIONALLY throughout: the real
  decision (did it load) stayed keyed on the same `CS.inReplay` boolean
  production trusts; Jev's read gated nothing.
  - **Real import: SUCCESS, loaded in 5.2s, 4 poll ticks.** The poll
    sequence is the cleanest demonstration yet of confidence tracking the
    genuine ambiguity of a live transition: `other_menu` (0.69) ->
    `other_menu` (0.86, tint just starting to move) -> `other_menu` (0.31,
    tint now positive both sides but weak/still resolving - the one
    genuinely uncertain moment) -> `in_replay` (0.96, resolved, matching
    the exact tick `CS.inReplay` flipped true). It never confidently
    misclassified the transition; low confidence showed up exactly where
    the screen was genuinely still changing.
  - **The in-replay ESC-menu round-trip after import classified perfectly**
    (`in_replay` 0.87 -> `esc_menu` 0.82, `dist_to_esc_menu` a confident 3.7
    - deep in the known range - -> back to `in_replay` 0.87), extending
    tonight's earlier toggle-recovery finding to a screen family never
    tested before.
  - **Real, independent-of-Jev finding: the FIRST read, of the screen the
    user was actually already sitting on, came back wrong** (`other_menu`
    0.44, when the ground truth was plainly `replay_list`). Root cause
    traced to the reference fingerprint itself, not Jev: `dist_to_replay_list`
    read 24.7 - well outside screen.js's own documented real-match range
    (0.6-5.3) and past its SAME=18 decision threshold - so even the
    EXISTING deterministic check would have called this screen "not a
    match" too. `screens/replay-history.json`'s own `"what"` field says it
    was recorded showing the **"IMPORTED (n)"** filtered sub-view; the user
    was on the default **"RECENT (16)", Mode: ALL** sub-view - a materially
    different layout the reference was never tuned against. This is a real,
    previously-undiscovered blind spot in the existing fixed-rule system
    (which sub-tab of the replay list counts as "the replay list"), found
    via this testing but not actually a Jev problem - Jev's low confidence
    (0.44) was in fact the honest, appropriate response to input that was
    genuinely out of the calibrated range. Worth either a second reference
    fingerprint (for the RECENT/ALL view) or documenting that the existing
    one only reliably covers the IMPORTED filter - `run.js`'s own use of
    `replayHistoryUp` only ever runs right after `open-import`, which
    likely always lands on the IMPORTED filter, so production itself may
    never actually hit this gap - but a human (or an agent) starting from
    the default view, as tonight did, will.
  - One clean idea not yet tried: give this vocabulary an explicit
    `loading`/`mid_transition` bucket (as the in-replay vocabulary has) -
    the 0.31-confidence poll tick above was real signal correctly read as
    uncertain, but labelled `other_menu`, which undersells what was
    actually happening (an import resolving, not a wrong screen).

  **2026-09-17, round 10 - further user-directed extension: the import
  ERROR dialogs specifically (duplicate code, expired code) - and a real
  methodology problem found and fixed mid-test.** The user asked to
  re-import the SAME code just imported (should trigger the client's "this
  replay was already imported" warning) and then import a known-expired
  code. **First obstacle, flagged by the user before any test ran:**
  `chunks/open-import.json`'s LAST recorded event is a blind click at
  (1340,833) - tuned as the "VIEW REPLAY" button on a successful import -
  and on a duplicate/expired code, an error dialog's "OK"/"CANCEL" button
  sits at close to that same position, so playing the chunk to completion
  auto-dismisses the very dialog this test wanted to see, before this
  script or Jev ever gets a look at it. **Fix:** new script
  `PROTOTYPE_typesafe_dialog_probe.js` plays only the chunk's first 4
  events via `R.playEvents` on a slice of the raw chunk (click IMPORT,
  click the field, paste the code, click SUBMIT) - never the 5th blind
  click - then stops, waits, and grabs a frame untouched. That frame is
  read two ways: Jev's numeric classification, AND an actual saved PNG
  Claude looks at directly - real visual ground truth, not a guess.
  - **Duplicate-code test (re-importing MTJC8C, just imported minutes
    earlier):** the saved frame showed, verbatim, "THAT REPLAY ALREADY
    EXISTS IN YOUR LIST." with an OK button - exactly the dialog the user
    predicted. `CS.inReplay` correctly read false; Jev called
    `dialog_or_unrecognised` (0.81). Dismissed cleanly via the chunk's own
    known final-click coordinates (reused deliberately, once confirmed via
    the image what they actually hit) - landed back on the exact same
    replay-list sub-view as before, confirmed both by `replayHistoryUp`
    reading false again (the SAME known sub-view blind spot from earlier
    tonight, not a new bug) and by a direct visual check.
  - **First expired-code attempt (`M810YF`, the earliest NA code in the
    live feed, 2026-09-09) was WRONG - user caught it live ("that code
    wasnt old enough").** The saved frame showed "MATCH LOADED." with
    DONE/VIEW - it had actually succeeded. Useful negative result anyway:
    since this was the OLDEST code the entire feed had, replay codes
    evidently outlive at least ~8 days, which the original assumption
    ("first round of NA" = expired) didn't account for.
  - **Root-caused a genuinely dead code via git history, not guessing
    twice:** found commit `73172fe` ("a region-aware wipe-date correction
    for NA"), which documents that NA's own 2026-09-08 patch restart
    landed MID-DAY, so every NA game finished that day is dead - already
    empirically confirmed in production by every attempted code from the
    8th failing with a load timeout. Pulled a genuine 2026-09-08 NA code
    (`WJ4906`) out of a pre-fix git snapshot of `docs/capture/data.json`
    (commit `fff348a`, before the regional correction removed these from
    the live feed). **Result: "LOAD FAILED: INCOMPATIBLE VERSION." with a
    CANCEL button** - a genuine third dialog, confirming the historical
    root cause exactly (an old-patch replay, not just an unimported one).
    `CS.inReplay` false; Jev: `dialog_or_unrecognised` (0.77).
  - **The real, clean finding across all three dialogs (duplicate/success/
    version-incompatible): their raw numeric signals were nearly
    indistinguishable from EACH OTHER** (dist_to_replay_list 114.3-114.5,
    dist_to_esc_menu 29.4-29.7, tints ~10-11/-10 to -11 every time) despite
    being three semantically different outcomes. This pipeline's signals
    are coarse/structural (a 32x18 fingerprint distance, a HUD-tint
    reading) - they can reliably say "something unusual is here, not a
    normal menu or an open replay," which Jev did correctly all three
    times, but they fundamentally cannot distinguish WHICH dialog it is
    from each other without either OCR of the actual banner text or a
    dedicated reference fingerprint per dialog type. Not a Jev shortcoming -
    a real ceiling on what this particular signal set can ever resolve.

  **2026-09-17, round 10, final extension - the first batch run: chaining
  every validated piece into an unattended loop over 10 real codes.** User-
  directed, explicitly scoped to import + reach-ready ONLY (no seeking, no
  sampling - that part of the pipeline stays fully deterministic and
  untouched, per punch-list item 5's conclusion above; a future idea,
  flagged but NOT built - teaching Jev to recognise "between rounds" or
  "still in setup" from the HUD, to protect real captures from landing
  mid-transition). New script `PROTOTYPE_typesafe_batch_run.js`
  (uncommitted): for each of N codes pulled from the rotating pool
  (`codestack.rotate`), leave any open replay, run `run.js`'s real
  pre-import sequence verbatim, play the FULL `open-import` chunk (unlike
  the dialog probe, this script only needs pass/fail, not a dialog's exact
  text, so the blind final click is fine here), poll with the same
  ground-truth-plus-Jev-observer pattern as the single-code import probe,
  and on success hand off to the round-9/10 "get ready" loop (pre-check
  shortcut, unconditional N, causal feedback, tolerance-based stuck
  detection, hard action cap) - all of it copied from already-validated
  scripts, nothing reinvented. Errors are logged and skipped, per the
  user's explicit instruction - never a guessed recovery.
  - **First run: 10/10 imported, 9/10 reached fully ready, 132.6s total (62
    Jev calls, 18.8s/14% of total time - consistent with the latency
    finding earlier tonight).** The one failure (`S11CRK`) is a genuine,
    valuable bug, not noise: right after import, tints read notably weak
    (19.6/25.7 vs the usual 40-55 elsewhere) with no panel/knob yet: this
    is EXACTLY the documented gap in `timing.js`'s own comment - "the
    replay has rendered but N/K do not land yet" (the same class of issue
    that cost two real codes historically, XTK7MM/4TNEAJ). Pressing N
    produced literally zero observable change; pressing K also produced
    zero observable change; Jev correctly recognised two genuinely-stuck
    actions and escalated rather than guessing a third time - the safety
    design worked exactly as intended. But the root cause was this batch
    script skipping `TIMING.load.settleMs` (500ms), the exact pause
    `run.js`'s real pipeline always takes between "import detected" and
    "start pressing keys" - because this was the FIRST time tonight the
    import phase and the ready phase were ever chained back-to-back
    without a human pause in between, and it surfaced the seam immediately.
  - **Fix: added the missing `io.sleep(TIMING.load.settleMs)` pause.
    Re-ran the full 10 codes: every code that got a chance to run reached
    ready (6/6) - `uncertain_escalate` never recurred.** The other 4 slots
    in that second run hit something unrelated: a real Windows-level
    "could not foreground Overwatch" refusal (`input.js`'s existing
    foreground guard, first seen in rounds 8-9, doing exactly its job -
    refusing to send blind keystrokes rather than guessing). Root cause is
    almost certainly OS focus-lock contention from Claude's own terminal
    activity between the two batch runs, not a Jev or pipeline bug.
    **Confirmed zero codes wasted by it**: `rotate()` is only called AFTER
    the pre-import sequence fully succeeds, so all 4 refusals happened
    before ever pulling a code, and the stack's position after both runs
    (16 codes advanced total) matches exactly. Worth remembering for any
    future longer unattended run: avoid heavy concurrent terminal/tool
    activity on the same machine while one is in progress, since it can
    intermittently starve the game window of OS-level foreground focus.
  - **Overall: this is the first time tonight's individually-validated
    Jev-driven pieces ran as a real chained sequence rather than isolated
    probes, and doing so immediately found one real, fixable seam bug
    (missing settle pause) while validating the whole chain end to end
    otherwise.** Genuinely promising result for treating this as more than
    a one-off experiment, though still entirely in throwaway prototype
    scripts, not wired into `run.js` itself.

  **2026-09-17, round 10, closing test - can Jev actually tell WHICH
  post-import outcome occurred (match imported, already imported,
  incompatible version) well enough to decide whether to continue, the
  way a human watching the screen would?** User-directed. Checked the
  premise against the live TypeSafe docs first (`state.md`, `api.md`, via
  the `typesafe-ai` skill): Jev has NO vision/image input at all, state is
  text/JSON only - confirming the assumption from the very first research
  entry above. The earlier finding that the three dialogs' NUMERIC signals
  (fingerprint distance, HUD tint) read almost identically to each other
  still stands - but rather than treat that as a ceiling, added a new
  signal: OCR of the dialog's own banner text, via a second `tesseract.js`
  worker (the pipeline already OCRs nameplates elsewhere) tuned for a
  sentence instead of a single word - PSM 7 ("single text line") and a
  wider whitelist, against a crop found by actually inspecting a saved
  frame first (`y:500-750`, full width) rather than guessing coordinates.
  New script `PROTOTYPE_typesafe_dialog_ocr_probe.js`, extending the
  dialog probe: plays only the chunk's first 4 events (never the blind
  5th click) so the result is inspected before anything auto-dismisses it,
  same discipline as before. Frames now save with the code AND a timestamp
  in the name, fixing the earlier tooling gap (two of the first three
  dialog-probe frames had been silently overwritten by later runs using
  the same bare counter, and were unrecoverable when this test needed them
  again).
  - **All three outcomes, OCR'd cleanly and classified correctly:**
    "MATCH LOADED." -> `match_imported` (0.88); "THAT REPLAY ALREADY EXISTS
    IN YOUR LIST." -> `already_imported` (0.99); "LORD FAILED: INCOMPATIBLE
    VERSION." (one-letter OCR noise, LOAD misread as LORD - a plausible
    O/A confusion on a stylised italic font) -> `incompatible_version`
    (0.97), Jev correctly unfazed by the typo since the rest of the
    sentence was unambiguous. This directly answers the user's question:
    yes, with OCR added as a signal, Jev can reliably tell these three
    outcomes apart - the numeric-only ceiling found earlier tonight was a
    signal-set gap, not a hard limit on the approach.
  - **Also caught a real bug in the TEST HARNESS itself, not Jev, not
    OCR:** the first duplicate-import attempt produced garbled OCR ("B L
    FAS") and Jev correctly called `unrecognized` (0.59) rather than
    guessing - and the saved frame showed why: this script never dismisses
    the dialog it finds, so running it twice back to back (fresh import,
    then immediately re-importing the same code to test the duplicate
    case) left the FIRST "MATCH LOADED" dialog still open when the second
    invocation's blind clicks landed - and the second click (meant for
    "SUBMIT") happened to land on that leftover dialog's "VIEW" button
    instead, actually opening the replay (confirmed by the saved frame:
    a real spectating view of Suravasa). Same exact failure SHAPE as every
    "blind click into an unconfirmed screen" risk flagged all night, just
    surfacing through the test tooling's own back-to-back invocation
    pattern rather than through Jev or production. Fixed by properly
    leaving the replay and re-testing from a clean state, which then
    produced the clean `already_imported` (0.99) result above.
  - **User's stated end goal, not yet built:** if this also learns to
    recognise "between rounds" / "still in setup" from the HUD, this
    becomes a genuine way to dynamically drive a capture the way a human
    watching the screen would - deciding what to do next from what is
    actually on screen (view/dismiss/skip after import; wait for a real
    round to start before sampling) rather than fixed waits and
    thresholds. Only the import-outcome half is validated so far; the
    round-boundary/setup-phase half is a new, separate signal that has not
    been attempted yet.

  **2026-09-17, continued - first concrete probe of the round-boundary/
  setup-phase HUD badge itself (OCR, not Jev yet).** Picking up mid-way:
  a prior pass in the same session had captured candidate frames
  (`tools/replay_bot/frames/cap-transition-*.png`,
  `cap-roundcomplete-*.png`, via `_tmp_find_transition.js` /
  `_tmp_capture_roundcomplete.js`, both uncommitted) of a small fixed-
  position HUD badge (top-center, ~x:1080-1330,y:30-100 @2560x1440) that
  shows GET READY / an objective-status line / OVERTIME, plus a first,
  unfinished attempt at OCR-reading it (`_tmp_ocr_upscale.js`, 4x scale)
  whose result was unknown at handoff time. Ran it: **bad** - "READ",
  "EE REAL", "REAL", confidence 32-64, one empty read. Root-caused by
  actually rendering the crop to a PNG and looking at it
  (`_tmp_crop_check.js`) rather than re-guessing coordinates: the
  hardcoded crop (`x:1080,y:30,w:200,h:60`) was too narrow and
  mis-positioned - it truncated the text instead of framing it.
  - **Fix: a wider, correctly-centered crop reads cleanly.**
    `{x:950,y:25,w:500,h:70}` at 3x scale, PSM 7, letters+space
    whitelist (`_tmp_ocr_upscale2.js`) got **96% confidence, exact text**
    on both "GET READY" and "DEFEND OBJECTIVE A" - the plain bold
    sans-serif HUD badge font is highly OCR-friendly once actually
    framed, consistent with [[ocr-readability-facts]] (contrast drives
    accuracy; this text has plenty of it against the blurred background).
    Not universal, though: two other frames of the same "GET READY" text
    (`cap-transition-24-41`, `cap-transition-332-57`) came back garbled
    even at the corrected crop - re-rendering those specific crops showed
    the text was visually just as clean as the ones that worked, so this
    looks like Tesseract-side flakiness on this exact style/size rather
    than a framing problem; needs more samples before trusting a single
    read, same lesson as every other OCR signal in this codebase.
  - **OVERTIME does not OCR at all, structurally, not just a tuning gap.**
    Re-cropped and visually inspected it directly
    (`cropcheck-roundcomplete-*.png`): it is rendered in a slanted,
    glowing, particle-effect italic display font, categorically different
    from the plain sans-serif GET READY/objective text - 0% confidence,
    pure garbage, on every crop/scale tried. This is very unlikely to
    become OCR-readable through crop/contrast/PSM tuning the way the
    scoreboard text was; it needs a different signal entirely, most
    likely a tint/color read (an orange-glow presence check) in the same
    spirit as the pipeline's existing `hudTint`, not more OCR work.
  - **The frames named "roundcomplete" are mislabeled - real finding, not
    yet corrected.** All four (`cap-roundcomplete-288/293/296/300`) show
    OVERTIME + "DEFEND OBJECTIVE A", not an actual "ROUND N COMPLETE"
    banner. The original seek target (t≈293s, "user-confirmed") was
    apparently a guess at the OVERTIME period, not the true round-
    complete screen. **The actual ROUND N COMPLETE banner has still not
    been located or captured** - finding it needs either scrubbing the
    timeline visually for the real transition, or re-running
    `_tmp_find_transition.js` (which seeks to every non-`play` segment
    `P.readStructure` finds) and checking ALL of its output frames, not
    just the ones a human guessed were relevant.
  - **Live client drifted mid-session** (unrelated to the OCR work
    above): a later structure-rescan hit `calibrateBar`'s "one press
    moved 0px" guard, and a follow-up grab showed the replay had ended up
    *playing* (unpaused, panel closed, badge cycling on its own) rather
    than in the paused/panel-open state earlier scripts left it in.
    Re-paused cleanly via `P.ensurePaused` and left it there - a safe
    stopping point, not a bug in anything tested tonight, most likely the
    same OS-level focus contention the round-10 batch-run entry above
    already documented ("avoid heavy concurrent terminal/tool activity on
    the same machine while one is in progress"). Codes are cheap/reusable
    ([[typesafe-live-navigation-testing]]) so nothing was at risk, but
    worth remembering before the next live session: don't run other
    node/tool commands back-to-back with scripts that expect the OW
    window to stay both focused and paused.
  - **Next, for whoever picks this up:** (1) actually find and capture
    the real ROUND N COMPLETE banner - scan every `readStructure`
    non-play segment, not a guessed timestamp; (2) get 4-5 more samples
    of "GET READY" at the corrected crop to learn whether the Tesseract
    flakiness above is rare or common before trusting a single OCR read
    in a live loop; (3) only then decide whether OVERTIME needs a tint
    signal built, or whether the badge's OCR text alone (GET READY /
    objective line / round-complete banner) is enough coverage for the
    user's stated "between rounds" goal without needing OVERTIME
    specifically.

  **2026-09-17, continued - user-directed: does any of this measurably beat
  the CURRENT workflow, not just work in isolated probes?** Every Jev call
  all session had been purely observational - ground truth (`CS.inReplay`,
  fixed timeouts) drove every real decision, Jev only got compared against
  it afterward. This test changes that: new script
  `PROTOTYPE_typesafe_trap_run.js` (uncommitted), built on the validated
  `PROTOTYPE_typesafe_batch_run.js` import+ready loop, but the import phase
  now uses the validated OCR+Jev fine dialog classification
  (`PROTOTYPE_typesafe_dialog_ocr_probe.js`'s vocabulary, extended with an
  `invalid_or_not_found` bucket for a never-tried case) to actually DECIDE
  when to stop polling and what to click, instead of blindly polling
  `CS.inReplay` for the full `TIMING.load.timeoutMs` (90s) the way the
  current deterministic path does on every failure (documented gap: "a
  single generic 'timed out' with no distinction"). A 10-code run, 3
  codes deliberately engineered as traps: a repeat import (same code
  reused two slots later, guaranteed still inside the client's last-10
  ring), the known-dead `WJ4906` (pre-patch NA code, root-caused
  earlier this session), and `ZZZZZZ` - a syntactically valid but
  never-real code, deliberately left unresearched going in so its actual
  failure mode would be a genuine test, not a rehearsed one.
  - **Result: 7/10 valid codes imported and reached ready (100% of the
    non-trap codes), all 3 traps correctly diagnosed with a SPECIFIC,
    correct label, in ~7.3s each** (`already_imported`,
    `incompatible_version`, and - the real test - `invalid_or_not_found`
    for `ZZZZZZ`, 0.92 confidence, OCR correctly read a FOURTH dialog type
    never seen before tonight: "LORD FAILED: REPLAY NOT FOUND." (LOAD→LORD
    is the same recurring O/A italic-font misread as the earlier
    INCOMPATIBLE VERSION case, and Jev was correctly unfazed by it again).
    **This is the real finding: the vocabulary generalized correctly to a
    genuinely novel dialog it was never tuned against**, not just the
    three known ones - evidence this approach isn't overfit.
  - **Concrete, measurable comparison against the current workflow:**
    diagnosis accuracy 3/3 specific-and-correct vs the current path's 0/3
    (it cannot distinguish causes at all, only "timed out"); time-to-skip
    ~7.3s vs a blind 90s wait per trap - **248.1s saved across 3 traps in
    this one run**, with zero regression on the 7 genuine codes (still
    ~10-12s each to ready, matching every earlier batch-run timing
    tonight). Total run: 135.7s for all 10 codes, 31 Jev calls, 14.0s
    total API time (~10% of run time, consistent with the latency finding
    earlier tonight).
  - **This is the first time tonight Jev's read has actually DRIVEN a real
    action (which button to click, whether to keep waiting) rather than
    riding along observationally** - still an uncommitted prototype
    script, not wired into `run.js`, but the first result in this whole
    thread with a real before/after number behind "does this help,"
    not just "is this accurate."
  - Not yet tested: a trap that looks like a dialog but ISN'T one (a
    genuinely slow-loading real code, to check the `still_loading` bucket
    doesn't misfire into a false early skip) - this run's real codes all
    resolved in one tick (9.7-11.7s) via `match_imported`, so the
    slow-but-genuine path was never actually exercised.

  **2026-09-17, continued - scoping "seeking and sampling" properly before
  testing anything there, user-directed.** Re-checked `phases.js` closely
  (not just re-quoting round 10's conclusion): every spot that looks like a
  judgment call already has a fixed rule with an explicit documented reason
  for rejecting a confidence-based approach - `shouldKeep`'s frame-storage
  rule and `vote.js`'s slot-resolution rule both exist specifically so a
  real hero swap can never be quietly averaged away, and `vote.js`'s own
  comment states the premise directly: "a confidence score cannot do this
  job... correct reads ran as low as 0.805." Confirms round 10's finding
  was not a shallow pass.
  - **One real, never-tested candidate did turn up: `sampleAt`'s low-score
    retry (`phases.js` lines ~466-478).** Below `LOW_SCORE` (0.6), it grabs
    ONE retry frame and keeps whichever scored better - a fixed, un-
    reasoned coin flip with no signal about WHY the frame looked bad
    (motion blur vs. genuine ambiguity vs. VFX/killcam occlusion).
  - **Tested this against 67 REAL historical retry pairs already sitting in
    `frames/` (offline, no live client, shadow-mode discipline) before
    building anything live.** Re-ran the actual production matcher
    (`P.readHud`/`P.worstOf`) on each original+retry pair. **Result: low
    leverage, not worth pursuing further.** Retry improved the worst score
    32/67 times, made it WORSE 33/67 (the current logic already guards
    against adopting a worse retry, so this isn't a bug - but it does show
    the retry is close to a coin flip, not a reliable fix), and only
    **3/67 (4.5%) stayed genuinely unresolved** (both reads under
    LOW_SCORE) - the one cohort Jev could theoretically help with. With
    only ~70 retries total across 7300+ kept samples (under 1% trigger
    rate) and 95% of those already resolved by the existing coin-flip
    retry, there just isn't enough headroom left here to matter, even with
    a large relative improvement. Closing this out rather than forcing a
    live test on a near-empty gap.
  - **Incidental finding, unrelated to Jev, not yet fixed:** 3 of the 67
    pairs threw during this analysis (`worstOf` returned `null`, not a
    number) - traced to `worstOf`'s min-reduction not guarding against an
    ABSENT_GUID cell's `score: null` (a disconnected player's empty slot).
    `null < worst` and `x < null` both coerce through 0 in JS, so a null
    score can silently corrupt the "worst" value depending on iteration
    order. Likely rare in practice (needs a disconnected player AND a
    genuinely low score in the same frame) and not something tonight's
    testing was built to chase, but worth a maintenance look independent of
    everything else in this entry.
  - **The bigger, more important conclusion this scoping exercise surfaced:
    hero identification itself (`Match`/the template matcher `sampleAt`
    calls) is fundamentally outside Jev's reach, not just low-priority.**
    Jev has no vision - every place it has helped tonight (screen state,
    dialog text) worked because a NUMERIC or OCR proxy for "what's on
    screen" already existed to hand it. Hero portrait matching has no such
    proxy short of the match score itself, which this test just showed
    carries little exploitable signal beyond what the fixed retry already
    uses. **This means the actual scouting PAYLOAD - identifying who's
    playing what - has no realistic Jev path**, distinct from and more
    fundamental than the earlier, already-documented player-NAME-
    attribution weakness (text-based, a different pipeline, and at least
    theoretically reachable since it's OCR+text matching, not raw vision).
    Relevant directly to the user's standing question about a full
    start-to-finish scouting simulation: the layer Jev has actually earned
    trust on (navigation, screen/dialog state) is the plumbing around the
    capture, not the extraction itself - see the assessment given directly
    in conversation this session for the fuller reasoning.

  **2026-09-17, continued - user-directed: one more real attempt at
  player-name attribution before settling for "plumbing only."** New script
  `PROTOTYPE_typesafe_player_match_v2.js` (uncommitted): grounds Jev in
  `assign.js`'s own real `Names.simScore` (the exact 0-100 number
  FLOOR/MARGIN already gate on) instead of bare OCR text - the "numeric
  proxy + text" shape that worked for dialog classification. Same 12-case
  real-near-duplicate fixture as the original round-4 test, plus 9
  fabricated lookalikes (5 new, against the same pool). **Result: worse,
  not better.** Real-match accuracy held (12/12) but false positives went
  to 9/9 (up from round 4's 4/4-of-4) - grounding in the real similarity
  score gave Jev something to point to as evidence for a mediocre match,
  exactly the risk flagged before running (that metric already reads 61.5
  for "Yoshiii" against the wrong candidate "yoshem", well past FLOOR=45).
  Confidence still technically didn't overlap (0.85 highest false positive
  vs 0.93 lowest correct) but the margin collapsed to ~8 points, nowhere
  near the wide gaps that made every other Jev signal tonight trustworthy.
  **Closes player-name attribution firmly - see
  [[typesafe-team-match-experiment]] for the full writeup.** Confirmed
  scope for whatever comes next: Jev stays confined to plumbing
  (navigation, dialog diagnosis); `assign.js`'s existing deterministic
  FLOOR/MARGIN path stays untouched for actually naming players.

  **2026-09-17, closing entry - the first real, full, start-to-finish
  scouting run, live, 3 real codes.** New script
  `PROTOTYPE_typesafe_scouting_run.js` (uncommitted): Jev diagnoses the
  import (validated `trap_run.js` logic, OCR+Jev dialog classification)
  and stops there - everything past "a replay is open" is real,
  unmodified production code called exactly as `run.js` calls it:
  `capture.js`'s `captureMap`, `attribute.js`'s `attributeMap`
  (`assign.js` underneath, untouched), `resolve.js`, `emit.js`. Used 3
  real, already-captured league codes (user-approved reuse) so
  attribution had genuine roster data to check against, not a simulation.
  - **First live attempt found a real architecture bug in the new glue
    code, not in Jev or production:** it also ran the validated Jev
    "get ready" loop before handing off to `captureMap` - but
    `captureMap`'s own first phase (`openEventsViewer`) ALREADY does that
    exact job itself, unconditionally, by design
    (`driver.js`'s `ensureEventsViewer` always presses N first, no
    classification, matching the round-9 lesson: "N is pressed EVERY TIME
    because that is what the client needs"). Chaining a Jev-driven ready
    step in front of that collided with it - pressing N into an
    already-open panel toggled it back down, and 2 of 3 maps opened the
    panel and then immediately lost it. User caught this live by watching
    the client ("opened, then immediately closed") before the run even
    finished. **Fix: removed the Jev ready step entirely.** Jev's
    plumbing role for a real capture is import diagnosis ONLY -
    `captureMap` already owns "get an open replay to ready," deterministically,
    better than the redundant Jev copy of the same job.
  - **Second bug, same root-cause category (dropped a real production
    step):** the script never played the `set-interval` chunk `run.js`
    always plays once per session, so the client measured whatever
    interval it defaulted to (20s) instead of being set to the
    session's real 45s - caught by the user from watching the client,
    not from the log. Fixed by wiring in the same `afterViewer` chunk
    call `run.js` uses, verbatim.
  - **Third run (fresh codes, since the first two were now inside the
    client's own 10-import ring and correctly, quickly - 0.99 confidence,
    ~7s each - diagnosed as `already_imported` rather than hanging):
    3/3 maps captured clean.** 48 total samples (9/15/24 per map), 0
    missed. Session step measured at 45s and reused for maps 2-3, exactly
    as intended. 10/10 player slots attributed on every map via the real,
    untouched `assign.js` FLOOR/MARGIN path - including a genuine
    team-side swap correctly detected on map 3 (`orientation: swapped`).
    Jev's total footprint for the whole run: 3 calls, 1.9s, all on import
    diagnosis - once the redundant ready step was gone there was nothing
    else for it to do, which is the right shape for "plumbing only."
  - **Answers the user's original standing question with a real result,
    not just a plan:** a full scouting run with Jev confined to plumbing
    works, today, on real codes with real rosters. The two bugs found
    were both integration mistakes in brand-new glue code (redundant
    state-driving, a dropped production step), not weaknesses in Jev's
    judgment or in the underlying deterministic pipeline - both caught
    fast because the user was watching the live client throughout, not
    from logs alone.

  **2026-09-17, further closing entry - real flag-triage head-to-head
  against a human, then a second, DIFFERENT-shaped player-attribution
  test that reversed the earlier verdict.** User asked to test Jev as an
  advisory triage layer over `resolve.js`'s existing `contested`/
  `low-support` flags (never auto-committing) - the idea floated
  earlier this session as the one candidate that fit the pattern proven
  to work (discrete classification, a real signal, a real gap) without
  the pattern proven NOT to work (open-ended name similarity).
  - **Test 1 (blind, real map, real human): 11/11 agreement.** Picked
    ZRDBGR (Samoa, unreviewed, 11 contested/low-support hero slots) from
    real production review data. New script
    `PROTOTYPE_typesafe_flag_triage.js` (uncommitted) fed Jev ONLY the
    structured evidence `resolve.js` already computes (reads, segments,
    support, teammates - no images) and asked, per flagged slot: genuine
    swap or noise. Result kept unread until the user finished reviewing
    the SAME map in the real review UI (`review/server.js`, pointed at
    the right session) and clicked Save. **Every one of Jev's 11 calls
    was `noise_not_swap`, and the user's saved corrections made ZERO
    hero-level changes** - full agreement, confidence 0.77-0.97,
    correctly attributing each flag to a null/dropped sample rather than
    real disagreement.
  - **But the user's real find wasn't hero identity at all - it was
    player ATTRIBUTION**, a question this test never asked. Two slots
    (round1+round2, side a, slots 3-4) had a player (Thpt) temporarily
    absent from the single early frame production's `attributeMap()`
    tries, which misattributed slot 3 to Thpt (whose name rendered
    there in that one frame) and left slot 4 unattributed. The user
    caught the real assignment (slot 3 = PARK, slot 4 = Thpt) by
    watching Thpt reconnect across later frames - real visual ground
    truth a numbers-only test can't reach.
  - **This matters because player-name attribution had already failed
    Jev TWICE tonight** (round 4 bare OCR text, and re-grounding in
    `assign.js`'s own `Names.simScore` - both failed on fabricated-
    lookalike false positives, see [[typesafe-team-match-experiment]]).
    Worth checking whether THIS shape of the problem is actually
    different before writing it off a third time.
  - **Test 2: it IS a different shape, and it worked - 6/6 against real
    saved ground truth, three real maps.** New script
    `PROTOTYPE_typesafe_player_triage.js` (uncommitted). The key
    reframe: not "does this OCR string look similar to that candidate
    name" (open-ended lookalike matching - the shape that failed twice),
    but "given MULTIPLE independent OCR reads of the same slot across a
    round, does a consistent signal emerge" - the same reconcile-noisy-
    repeated-observations shape that worked cleanly for hero triage.
    Production's real `attributeMap()` only OCRs ONE frame per map; this
    reuses the exact same real OCR pipeline (`nameplate.js`'s
    `nameRow`/`nameCrop`, identical PSM 8 tesseract settings) across
    EVERY saved multi-sample gallery crop for a flagged round/side -
    real crops already on disk (`review_out.js` only saves these when a
    hero swap co-occurred in that round, a lucky-but-real overlap).
    Hand-verified the coordinate math against ZRDBGR first: OCR off one
    single gallery crop alone already read "PARK" (96 conf) and "THPT"
    (90 conf) in exactly the two corrected slots, before Jev was
    involved at all - the multi-frame evidence genuinely contains what
    the single-frame production path missed.
  - **Result: 6/6 slots (2 per map x 3 maps - ZRDBGR live-reviewed this
    session, TM965Y and V0GJ69 already `status: reviewed` with real
    corrections from prior sessions, no need to interrupt the user's
    workflow for those two) matched the real saved correction, at
    0.99-1.00 confidence every time**, correctly ignoring garbled reads
    ("RQE", "s1", "l7") in favor of the consistent signal elsewhere in
    each slot's timeline (e.g. ZRDBGR slot 4: `["s1","THPT","THPT",
    "THPT","THPT"]` -> correctly picked Thpt).
  - **Real, load-bearing caveat, not yet resolved:** the multi-sample
    gallery this depends on only exists today as a side effect of a
    HERO swap happening to co-occur in the same round (`review_out.js`'s
    actual save condition) - it is not currently saved for every round,
    so this can't yet run on an arbitrary abstained slot without a
    production change (saving one multi-sample gallery per round
    unconditionally, or having captureMap run attribution across more
    than its current first-4-frames fallback).
  - **CORRECTED AT SCALE, same night - the 6/6 did NOT hold up and the
    real number is worse than it looks.** User asked to scale the test
    across every real map with the right data on disk. New script
    `PROTOTYPE_typesafe_player_triage_scale.js` (uncommitted) found 17
    real, already-reviewed maps (scanned every `out/*.review.json`, not
    hand-picked) with a gallery covering an abstained slot, and scored
    EVERY abstained slot in each (44 total), not just the ones a human
    had already corrected - the 6 cases from the first test were a
    biased sample (every one was a slot a human had already manually
    fixed, meaning a legible, roster-matching name definitely existed
    somewhere in it). **Result: 21/44 (48%) matched overall, but of the
    33 slots where Jev committed to a specific player, only 10 were
    correct - 23 were false positives (70% wrong when it commits).**
    Root cause, clean and consistent across the failures: Jev's "none"
    correctly fires on genuinely noisy/inconsistent evidence (AY0H66:
    4/4 correct abstains on wildly garbled reads) but does NOT fire when
    the evidence is CLEAN and CONSISTENT but simply belongs to nobody on
    the given roster (a substitute, a smurf, a name variant) - e.g.
    XSCC99 slot 0 read "SWIFFLE" identically 3/3 times, and Jev
    force-matched it to a real roster player at 1.00 confidence rather
    than recognising it matched nobody. **This is the exact same failure
    shape as the very first player-name test of the whole night** (round
    4's fabricated lookalikes) reappearing in a new form - a clean read
    is not the same as a CORRECT read, and Jev's "none" option needs
    "matches nobody in the list" framed as explicitly as "illegible,"
    which this test's prompt did not do.
  - **Standing verdict, corrected:** the reconcile-repeated-observations
    idea is real but narrower than first reported - useful ONLY as a
    supplement when a name is already suspected legible somewhere in a
    multi-frame timeline (which a human or a simScore pre-filter would
    still need to establish), not as a general abstained-slot resolver.
    Not worth pursuing further without a fundamentally different framing
    of the "none" criterion, and even that is speculative given
    simScore-grounding already backfired once tonight in the single-shot
    version of this same problem. Filed alongside, not replacing, the
    firm "player-name attribution stays on the deterministic path"
    conclusion above.

  **2026-09-17, correction to the correction - the 70% false-positive
  number was measuring a bug in the TEST's ground truth, not in Jev.**
  User asked directly whether the captures themselves might be flawed.
  They weren't (crop dimensions matched `calib.FROZEN` exactly across
  all three capture sessions, and a direct look at a "false positive"
  crop showed clean, correctly-legible names) - but the question was
  right to ask and led to finding a real methodology flaw: the scale
  test's ground truth assumed "no saved correction on an abstained slot"
  meant "a human confirmed nobody matches." Often it just means the name
  was ALREADY fine and nobody needed to touch it - `attribution-
  abstained` fires from `assign.js`'s FLOOR/MARGIN/role-constraint logic
  for reasons that have nothing to do with whether the OCR name was
  legible (XSCC99 slot 0: production's own ORIGINAL single-frame OCR
  already read "SWIFFLE" correctly - a real roster player - yet stayed
  abstained, almost certainly a role-constraint issue, not a naming one).
  - **Re-checked all 23 "false positives" against production's own
    original single-frame OCR read, using the real `Names.simScore`:
    14/23 strongly or exactly matched (>=70) what production itself had
    already read** - these are almost certainly mislabeled ground truth,
    not real Jev errors. Only 9/23 have no supporting match in the
    original read and remain genuinely uncertain.
  - **Corrected picture: 21 confirmed + 14 likely-correct-but-mislabeled
    = 35/44 plausibly right, 9/44 genuinely unverified** - a completely
    different result from "70% wrong when it commits." Two of the 9
    (A57Q7D's abstained slots reading "PROXY" and "TWERKNATION" in Jev's
    multi-frame evidence) are named in an unrelated historical memory
    entry as real, chronically hard-to-OCR players on this exact roster
    - suggestive, not proof, that Jev recovered real signal there too.
  - **Important epistemic caveat, stated plainly:** the recovered 35/44
    is CLAUDE's inference (agreement with production's own OCR), not
    human-verified the way the original 6/6 and the true "none" cases
    were. The honest next step is pulling the remaining ~9 genuinely-
    uncertain cases into the real review page for actual eyes-on-frame
    verification before trusting this number further - not yet done.

  **2026-09-17 - the ~9 remaining cases got real human verification: 8/8
  correct, and the ninth surfaced a real, separate production bug.**
  User reviewed the last uncertain slots (a filtered copy of the review
  artifact, `out/player-triage-verify.review.json`, built so 5 relevant
  maps didn't have to be hunted out of a 300-map session file) and saved
  real corrections. **All 8 checkable cases (Proxy, TWERKNATION, H4DE5,
  trentino, haipydragon, mesogood, pepper, catmintǃ) matched Jev's pick
  exactly.** Corrected final tally: 29/44 now fully human-or-original-
  ground-truth confirmed, up to 43/44 counting the still-inferred
  (simScore-matched-to-production's-own-OCR) 14. One real exception -
  not a Jev accuracy failure, a genuinely different problem:

  **P2 (not yet scoped) - a leaver mid-round shifts every slot to their
  right, and nothing in the pipeline defends against it.** Found live on
  Nepal (DFC8JM): user reported "the player on the leftmost slot left
  the game which made every other player shift one slot to the left."
  This is NOT the same failure as the already-tested "player absent at
  round start, reconnects later" case (ZRDBGR) - it is a genuine,
  mid-round RENUMBERING of every slot downstream of the leaver, and nothing
  currently detects it:
  - `resolve.js`'s `segmentSlot()` tracks each slot INDEX as if it is one
    continuous player for the whole round - a leftward shift reads as
    that slot's hero suddenly, permanently changing after the 2-read
    confirmation threshold, indistinguishable from the SAME player
    picking a new hero mid-round.
  - This is not only a player-attribution problem. It is a HERO-
    CONTINUITY problem baked into the same mechanism driving a chunk of
    this whole night's "contested"/multi-segment flags - a shift would
    manufacture a fake swap signal for every slot right of the leaver,
    not just corrupt one name. Worth checking whether any of tonight's
    OTHER "genuine swap" hero-triage cases (the 11-slot ZRDBGR test, or
    the wider corpus) were actually this, not a real swap.
  - `ABSENT_GUID` (phases.js) only models "this one slot is empty" - it
    has no concept of "everyone past an empty slot just renumbered."
  - **Not scoped or investigated further tonight** - parked here per
    the user's explicit call. Whoever picks this up next should start
    by measuring how common leaver-mid-round actually is across the
    corpus (a rare edge case changes the priority a lot) before
    designing a fix - matching this whole session's own discipline of
    measuring before assuming.

  **FIXED 2026-09-17** - `specs/2026-09-17-replay-bot-disconnect-identity-
  {design,plan}.md`. `phases.readNames` now reads all 10 name crops per
  sample (not once per map); `attribute.js`'s `attributeFromSamples` runs
  once a map's samples are all collected, establishes each side's canonical
  `player_id -> slot` map from every sample's name-matches (the MODE across
  the whole map, not one frame), and re-keys every sample's hero-cell array
  from visual position into canonical slot order before `resolve.rounds()`
  ever sees it - the leaver's own slot now reads `ABSENT_GUID`, and whoever
  shifted into their pixel territory is recovered back into their own slot,
  for shifts of 1-4 slots depending on which of the 5 original positions
  disconnected. Identity evidence only ever ADDS a correction: a slot whose
  name is illegible for reasons unrelated to any disconnect still keeps its
  hero read, only attribution (`player_id`) stays unresolved for it - the
  regression an earlier draft of the design would have introduced. `resolve.
  js`/`emit.js`/`owdb/contribute.py` are untouched; only `run.js`'s
  attribution call site and `capture.captureMap`'s per-sample loop changed.

  **2026-09-17 - the real overnight run (Jev-on-plumbing, full default
  queue) is live, and surfaced one more real, unrelated production
  finding within the first handful of maps: `measureRate` can return a
  wildly nonsensical implied press duration.** One map (4YR9CR, Nepal)
  failed calibration with "a press measured 743.6s, which is not near
  any of 5/10/20/30/45/60s." Client was left clean afterward (still
  inside the replay, no stuck menu - a normal restart recovered it), so
  this was not a stuck-client problem, but the number itself implies
  `phases.js`'s `measureRate` measured almost no playhead movement over
  its 6s playing window - i.e. it likely believed the replay was
  PLAYING when it was not, the same category of toggle-state confusion
  ("SPACE is a toggle, so whether it is already playing is measured, not
  assumed") already flagged live earlier tonight in the
  `playheadX`/get-ready toggle work - see
  [[typesafe-live-navigation-testing]]. Possibly the same underlying
  root cause surfacing in a different code path (calibration instead of
  navigation). Not investigated further tonight (the overnight run needs
  to keep moving) - worth a look alongside the leaver/slot-shift item
  above, and worth checking whether `measureRate` has a sanity floor on
  its own result the way `T.stepSecondsFrom` already gates the derived
  step (it clearly caught THIS bad value - the guard worked - but the
  root cause of the bad input measurement itself is still open).

**2026-09-17, closing entry - a real, deep human review of 30 flagged maps
from tonight's overnight run surfaced six genuine production findings,
independent of anything to do with Jev.** User reviewed all 30 flagged
maps by eye (crops, per-sample galleries) via the real review page and
found the following - ranked roughly by severity/leverage, not by the
order found:

1. **P1 - Dead-but-present players get wrongly marked ABSENT.** The
   dominant real bug in this corpus: of 4 genuine hero-guid corrections
   made across all 266 maps, 3 were exactly this (H6EW1N, 3H3DYA, 1AA7HP
   - all `was_guid: "ABSENT"` corrected to a real hero). User's own
   words: "It seems to be most sensitive when the player is dead" - a
   readable portrait with a death/kill-cam overlay is apparently
   triggering the same "no card present" signal `ABSENT_GUID` uses for a
   genuinely disconnected player (`calib.cellPresent`/`Crop.cellTint` in
   crop.js - worth checking whether the death-state overlay shifts the
   cell's brightness/tint below whatever threshold that check uses).
   Real counterexample confirmed working correctly: W Macro vs AR9
   (Esperança) - one genuinely disconnected player correctly read
   ABSENT there. So the mechanism is right in the disconnect case and
   wrong in the death case - these need to be distinguished, not merged.
   **FIXED 2026-09-17 (the death case specifically).** The 2026-09-16 fix
   (badge-only tint) turned out to only cover a DIFFERENT bug (a warm
   portrait dragging a whole-slot average) - a real death desaturates the
   badge too, so `cellPresent` still can't tell it from a disconnect on
   tint alone. `calib.deathMarker()`/`crop.cellDeath()` look for the red
   elimination X a death draws and a disconnect never does (operator:
   "the X means a player is dead"); `phases.js` reads `DEAD_GUID` instead
   of `ABSENT_GUID` when it's present, and `resolve.js` drops a
   `DEAD_GUID` read entirely rather than treating it as evidence either
   way. See CHANGELOG. Found via two more real examples in the SAME
   overnight batch while re-opening the maps the retroactive audit
   flagged (below): `P1PXQK` (`!DANUIL`/Reaper, ABSENT at the very first
   sample of a round, present the whole round) and a `H5Q9WE` frame
   showing three simultaneous deaths (NBHD/RAMI/SANTY, X present, no
   desaturation - confirms the X alone is the reliable signal, not
   desaturation).

2. **P1 - No validation that a mid-round hero "swap" is role-legal.**
   The clearest, cheapest-to-fix bug found: a slot's segments went
   Ramattra (Tank) -> Zenyatta (Support) within one continuous round -
   physically impossible under FACEIT's role lock (the same constraint
   `assign.js`'s whole design already leans on: "8303 of 8356 team-games
   are exactly 1 Tank/2 Damage/2 Support"). `segmentSlot()`/`resolve.js`
   currently has zero role-continuity awareness across a slot's own
   segment chain - it only tracks hero-guid continuity, never checks
   whether consecutive segments are even role-compatible. Since
   `hero_roles` (guid -> role) is already loaded and used elsewhere in
   this exact pipeline (`slotRolesFor` in attribute.js), a same-slot
   segment-to-segment role check is nearly free to add and would catch
   an entire class of misreads automatically - any segment transition
   between roles is either a genuine role-locked-comp exception (rare,
   measured at 53/8356 team-games, all missing-role not real 2-tank) or
   a misread of one of the two segments, worth flagging either way.
   **FIXED 2026-09-17** — `resolve.js` now flags `cross-role-swap` on any
   confirmed segment-to-segment transition between two known, different
   roles; silent when either guid's role is unknown. See CHANGELOG.

3. **P2 - Post-round/VS-takeover screens corrupting samples.** Two
   confirmed real examples (Sheffield Larp Central vs Chud Maximus,
   Nepal R2's final ~9:00 sample; Qwiz Esports vs VQ Ragnarok, Nepal R3's
   final sample) where the fixed sampling grid landed on the post-round
   VS screen instead of real gameplay, corrupting that read (visible
   directly in the crop galleries as a black/red takeover frame instead
   of a HUD). **This directly validates the "between rounds / still in
   setup" HUD detector idea explored earlier tonight** (GET READY /
   OVERTIME / VS-screen OCR, see this same P3 entry above) - which was
   de-prioritized at the time on the theory that `readStructure`'s
   segment boundaries already excluded these moments. That theory was
   wrong, or at least incomplete: real captures show it does not
   reliably exclude the POST-round takeover specifically (only the
   pre-round GET READY setup segment was verified excluded). Worth
   reopening with this concrete evidence in hand rather than the earlier
   inconclusive reasoning.
   **FIXED 2026-09-17** — rather than reopening the OCR/pixel HUD detector
   idea (needs a live frame to calibrate, and risks making Jev/TypeSafe
   load-bearing per [[typesafe-vendor-caution]]), `resolve.js` reuses the
   per-cell `ABSENT_GUID` presence signal it already computes: a sample
   where >=6 of 10 slots read ABSENT is a takeover screen, not ten
   leavers, and is dropped from the round before it reaches the vote or
   segment chain (flagged `takeover-frame`). See CHANGELOG.

4. **P2 - Short rounds can starve the sample grid.** User's proposed
   fix, concrete and cheap: when a round is too short for even one full
   step of the fixed 45s grid, split it in half and sample once ~15s in
   and once ~15s before it ends, rather than relying on
   `T.planGrid`'s fixed-step grid (which already has a short-segment
   fallback - a single nearest-reachable-instant sample - but that is
   ONE sample, not two, for a round that may still have a real mid-round
   swap in it). Likely the same underlying cause behind finding #6 below
   (a real multi-hop swap only partially detected) - too few samples to
   catch every segment, not a matcher accuracy problem.
   **FIXED 2026-09-17** — `T.planGrid`'s short-segment fallback now takes
   two independently-snapped quarter-point samples (`from + span/4`,
   `to - span/4`) instead of one middle sample, collapsing back to one via
   the existing whole-plan dedupe when the segment is too short even for
   that. See CHANGELOG.

5. **P3 - A single-unattributed-teammate elimination rule.** If exactly
   one of a side's 5 slots is unattributed AND exactly one roster player
   is unmatched anywhere else on that side, it is safe to attribute the
   remaining slot to the remaining player by elimination - a cheap,
   deterministic completion rule `assign.js`/`attribute.js` does not
   currently apply (each slot is scored independently within its role
   group; nothing currently does a final side-wide elimination pass).

6. **Already known, freshly reconfirmed - UI-settle timing on a scrub is
   not constant.** User: "these captures with the white background...
   only happen for a split second while the UI is settling after a
   scrub, but its not a constant time from scrub -> settle." This is
   exactly [[replay-scrubbing-timing-variance]] (already-documented,
   pre-existing finding) - not new, but this session gave it a fresh,
   concrete example (player 'fat': a real Lifeweaver -> Lucio -> Jetpack
   Cat swap where only "Lucio" was ever detected, likely because a
   settle-timing miss plus too-sparse sampling (#4 above) both fed the
   same slot at once).

**Jev's role in this entry: none, by design, and that is itself worth
noting.** The overnight flag-triage run (49 contested/low-support slots,
same approach as the earlier 11/11 ZRDBGR result) said `noise_not_swap`
on all 49, and nothing the user found contradicts that - but ALSO
nothing confirms it: every real bug found tonight (the ABSENT
mislabeling, the impossible role-swap, the post-round-screen corruption)
lives in a DIFFERENT flag category than what was tested
(`attribution-abstained`, `player-absent`, `low-score`, or no flag at
all). Test scope and real-bug location simply never overlapped tonight.
Script: `PROTOTYPE_typesafe_flag_triage_overnight.js` (uncommitted).

**None of this was fixed tonight** - the session has run long enough
(a full overnight capture plus a deep manual review) that these are
being recorded, not actioned, pending the user's own prioritization call
next session.

**2026-09-17, next session - items 1/2/3/4 above fixed (`cross-role-swap`,
`takeover-frame`, the two-sample short-round fallback; see CHANGELOG and
Replay bot "Recently shipped" below), then a full retroactive audit run
against every captured session AND the actual live published file.**
`tools/replay_bot/retroactive_flag_audit.js` (uncommitted) re-checks every
`out/*.review.json` on disk for `cross-role-swap` (exact, from stored
segments - free, no recapture needed) and `takeover-frame` (real pixel
re-check against saved per-sample crop images, only possible for rounds that
happened to save a multi-sample gallery under the OLD swap-only condition).
**Findings:**
- **40 cross-role-swap hits across the corpus, of which 2 were already
  human-corrected in the file they were found in, and 6 (all the same real
  match, `DFC8JM`) are CONFIRMED still wrong in the actual live
  `data/captures/s10/replay-bot.json` right now** - verified directly
  against that file's own published `observations` sequence, not inferred.
  `DFC8JM` is the already-known leaver/slot-shift bug (P2 above), so this is
  corroborating evidence of its real footprint, not a new bug.
- **A real regression risk, not previously known:** several matches
  (`TM965Y`, `WZM1EY`, `1X922Y`, `SJA0RF`, `1MWR2Y`, `4FG0WJ`, `P5J3TR`,
  `SMBB9Y`, `FGT3P2`, `JHRK4E`, `XSCC99`) show this exact misread,
  uncorrected, in a NEWER local recapture of a match that is ALREADY live
  from an OLDER, already-human-corrected capture of the same match+game.
  Naively re-uploading one of these newer local sessions as-is would
  overwrite the currently-correct live data with the older, uncorrected
  misread (`data/captures/` uploads replace the whole contributor file, see
  AGENTS.md). Any future publish needs to build the merged set from the
  BEST available capture of each match, not just the newest session.
- **takeover-frame: zero real hits found, but coverage is partial.** 1039 of
  1587 total rounds had a saved gallery to pixel-check for real; 548 (35%)
  never saved one (no swap was ever suspected in them under the old rule),
  so this flag's true prevalence in the already-captured corpus is
  genuinely unknown for those, not "probably fine."
- **Applied (`--apply`, `--live-check`):** 14 map-rows across 6 session
  files flipped from `reviewed` back to `unreviewed` (skipping any slot a
  human had already corrected), each file backed up first
  (`.review.json.bak-<timestamp>`, the existing convention). Nothing
  uploaded, nothing pushed - purely local review-queue state, fully
  reversible from the backups.

**2026-09-17, same session - individual segment correction, reported by the
operator while working the re-opened maps above.** "I cant currently correct
individual swaps within slots that have multiple swaps over the course of
the round. If a slot reads hero a, then b, then c, but only read b was
wrong, i can currently only correct the WHOLE read at once." **FIXED** - see
CHANGELOG. A correction can now carry an optional `segment_from_t`
targeting one specific segment; `applyCorrections` (review/server.js)
replaces or drops only that segment, leaving its siblings and the
round-level fields alone, and the review page's segment rows are
individually clickable to do it. TDD, `tools/replay_bot/review/server.test.js`.

**2026-09-17, next session - the disconnect slot-shift fix validated live,
twice.** After committing `attributeFromSamples` (see the goal memory /
`specs/2026-09-17-replay-bot-disconnect-identity-{design,plan}.md`), ran it
against two real live captures:
- A normal map (MTNN40) with no disconnect: 17 samples, 0 missed, all 10
  slots attributed (`conf: 'matched'` both sides), 3 rounds resolved clean,
  zero flags.
- **H5Q9WE re-captured live (the exact map the design doc's pixel inspection
  was done on)** — and it disconnected again mid-capture. Side a slot 3
  (Tracer) resolved to `Tracer -> ABSENT -> Tracer` (correctly attributed
  gap, reconnect recognised as the same player); side a slot 4 (D.Mon, the
  slot that visually compacted into position 3's pixels during the gap)
  resolved to a single unbroken `D.Mon` segment with no gap and no false
  swap. This is the exact bug pattern from the design doc, corrected live,
  for real, on the map that originally surfaced it.

- **P3 - a crashed capture's `state/attempts.json` entry is invisible to its
  own recovery UI.** Found live while re-running the smoke check above: a
  `run.js` process killed mid-capture (e.g. a tool/shell timeout) writes
  `status: 'opened'` before it starts, and never gets to overwrite that with
  a real outcome. `isDoneEntry` (run.js) correctly treats `'opened'` as done
  (deliberate - see its own comment, "an opened orphan from a crash"), so
  the code is excluded from the normal pending queue - fine so far. But
  `review/server.js`'s `failureList()` only ever lists entries with
  `status === 'failed'`, so an `'opened'` orphan never appears in the review
  page's Failures panel either, and its Retry button (`POST /failures/retry`,
  `delete attempts[key]`) can never reach it - there is no UI path back for
  it at all, only a hand-edit of `state/attempts.json` (mirroring what Retry
  already does). A small fix: `failureList()` should also surface a
  `status: 'opened'` entry (perhaps its own category, distinct from a real
  failure) so the existing Retry button can clear it like any other.

Phases 0–2a and phase 4's analysis half shipped 2026-08-19; both pages ship
locked behind `?unlock=scrimbeta`. The phase list below is open per
`AGENTS.md` § Roadmap priority 2; the items after it carry the detail:

- Phase 2 (rest): opponent identification and roster search.
- Phase 3: the stats read plus a workshop hero-glyph reference set.
- Phase 4: the viewer's Players tab.
- Phase 5: sync and sharing.
- Phase 6: auto map detection (cheaper than it was — the code reader already
  tells when the replay on screen is not the one being captured; deliberately
  on-demand, not polling).

- **P1 — "Read bans" has never faced a real replay.** Every part of the
  workshop half is verified in game; the capture half has only seen synthetic
  strings. It needs one captured scrim. Three outcomes to tell apart when it
  finally runs: both heroes filled (path works); abstaining (the reason
  matters — "could not find the BANS row" is a crop/OCR problem, "no hero
  matches X" is a name that did not resolve, "expected two bans, read N" is a
  garbled row); returning WRONG heroes should be impossible by construction
  (exact-after-normalisation, no fuzzy fallback) — if it happens, an assumption
  is wrong and it is urgent. Capture `LAST_BAN_READ.raw` before reloading.
- **P1 — Get the team's hosts onto the share code `B44BZ`.** Bans and the
  spectator scoreboard only exist in lobbies running our workshop code; scrims
  are hosted on a mix of ScrimTime, ScrimTime Lite and ours. Lite has no
  spectator scoreboard at all, so phase 3's stats read can never work there.
  Anyone still holding the old `B4GM8` needs the new five characters — that
  code is retired and will never be updated. Adoption is also maintenance:
  codes expire ~6 months after creation unless used (B44BZ lapses around
  2027-03-06 otherwise).
- **P2 — Verify the scoreboard read in a live capture.** Everything about the
  read is verified against still frames; `scoreCanvas()` and `autoBoardBox()`
  have never seen live screen-share video. First live check: `boxSource` must
  report `'markers'`. `'manual'` means the marker detector did not find the
  rules — either the host has not reloaded `B44BZ` or the markers are switched
  off in "5. Spectator Scoreboard".
- **P2 — Frames from a second map.** Preprocessing parameters (blur radius 12,
  gain 6) were tuned on eight frames of one map, the marker detector on two of
  another. The family choice (local contrast over saturation) is not in doubt;
  the specific numbers could be map-shaped. Cheap insurance: a few spectator
  frames from a different map with their truth added to `scoreboard_truth.json`.
- **P3 — Remaining in-game ban-phase checks.** `setAllowedHeroes` force-swapping
  a player already on the banned hero has only been exercised in a near-empty
  lobby. The R3 start guard has not been tested in both `ReadyUp_CaptainMode`
  modes (0 and 1) — it is a forked guard in two rules with differing wording.
  The setup timer expiring with exactly one ban set has never been triggered.
- **Record — unlocking scrim mode.** Asked and answered 2026-08-27: keep both
  pages locked, revisit when phase 2 (opponent identification / roster search)
  is complete. Never unlock one page without the other (invariant 12), and the
  gate must fail closed (invariant 13).
- **P3 — Scrim tracker (product idea).** The user's product-defining idea —
  "infinitely more potential overall" than the FACEIT lens. Capture is the part
  that exists; everything past it — tracking, dashboard, scrim-vs-scrim
  comparison — is open. Needs its own design doc before any implementation.

## Dashboard and analytics

- **P2 — Power rankings.** Derived from stored match results: Series Elo (K=32)
  + Map Elo (K=12), weekly ratings, sparkline trajectories, ordered standings.
  Pure data math, fits the testable-core rule. Frame it as rankings, not elo
  ("99% of OW players don't care about elo, but power rankings could be fun").
  Must follow the sample-honesty rules (show `n`, weak evidence weakened).
- **P2 — `--external-data` page splitting.** The seam exists (sibling
  `data.json`, future access-gating). The design decision says revisit only if
  page weight moves materially — and S10 measured at ~15.7 MB with splitting still
  unnecessary (see `AGENTS.md`), so it stays parked until a real trigger.
- **P3 — Access gating / contribute-or-pay threshold.** The same seam and the
  league-wide leaderboard count; not designed.
- **P3 — `#div=<id>` deep link.** Deferred since the unlock-NA work.
- **P3 — Map drawer (reimagine, do not copy).** owscouter owns the shape of a
  draw-on-map strategy whiteboard; if OWDB ever ships one it should be its own
  take — markers tied to *real captured data* (mark a position, attach the
  comps run there, export a prep image) rather than a blank whiteboard.
  Idea-level until that angle is defined.

## Ingest, seasons and cutover

- **P1 — Cross-season player careers (design first).** Player pages aggregate
  whatever divisions are in the payload, so the moment the site becomes S10
  every player restarts from nothing and their S9 record lives only in the
  frozen archive at a different URL — and a new season is exactly when people
  look up who moved where, so the value decays if this lands late. Needs a
  **design document, not a plan**: the honest implementation cuts against the
  season-scoped export, and the obvious version (ship both seasons inline)
  roughly doubles page weight — the same `--external-data` question. Decide the
  two together.
- **P2 — Decide what a "Season Finals" championship is (open; has until
  November).** See Current season. Widening `is_playoff_name` is the easy half;
  the cross-tier attachment shape is a design question with no existing model
  to hang off. Not urgent — nothing to crawl until November.
- **P3 — Playoff sibling pairing is a LIKE prefix.** `_related_division_teams`
  matches `name LIKE base || '%'`; a future division whose base name is a
  prefix of another's ("Master" vs "Master 2") would cross-seed the crawl.
  Anchor the pairing (exact stage-suffix match) when a second real pairing case
  appears.
- **P3 — `FACEIT_API_KEY`-backed championship discovery.** Every season,
  seeding costs a manual hunt for one room URL per division. The Data API's
  `organizers/{id}/championships` (organizer id
  `f0e8a591-08fd-4619-9d59-d97f0571842e`) would list them directly. Worth it
  only if manual seeding actually hurts — CI needs no key today, and adding one
  is a new operational dependency.
- **Record — `wrangler deploy` is still owed (operator).** The repo Worker says
  `s10`; the deployed copy is not live until someone deploys it (invariant 11,
  tracked in `AGENTS.md` § Roadmap "three things owed"). Not a planning item —
  listed here so the cutover checklist stays in one place.

## Working-tree health

- **P3 — Debloat the local working tree (partly done this session).** Not a
  repo-health problem — `.git` is 458M but that is historic `docs/index.html`
  revisions, not images, and every tracked image totals 128K. The bloat is
  gitignored/untracked scratch, measured on the operator's rig 2026-09-12.
  **Done this session:** `tools/replay_bot/out/` pruned to one reviewed
  artifact (`replay-bot-2026-09-12`), `node_modules` deleted, and the
  `screenshots/`, `refs_diag/` and `--help/` scratch cleared. **Retained
  deliberately:** `tools/replay_bot/frames/` (4.8G) — kept per that directory's
  own note, "a better matcher can re-read a map later with no client time and no
  code" — and `calibration/` (33M). **Partly answered:** `frames/` now prunes
  after a successful upload (2026-09-12), but there is still no age/count-based
  policy for a session that is never uploaded, and nothing retires an old,
  already reviewed-and-uploaded session from `out/`. **Still open:** the
  `--help/` folder was an accidental `mkdir` — something took `--help` as a
  literal directory-name argument instead of parsing it as a flag, and that bug
  may still exist even though the folder is gone. Worth a deliberate pass on an
  age- or count-based prune.

## OWCS expansion

- **P2 — OWCS ingest (design approved, gated on permission).** An
  unauthenticated GraphQL API (`api.owtics.gg`, full introspection, no key)
  has everything except comps: hero bans at ~100% coverage for 2025–26 OWCS
  (bans did not exist before 2025 — 2024's 0/183 is correct), map names and
  per-map scores, push/capture progress, teams, rosters, standings and
  brackets. `replayCode` is null on all 860 map results sampled; there is no
  player stats (OWTV, the only source, is excluded by its terms of service).
  So VOD capture is still required, but for one job instead of five. Phase 1 —
  an `owcs_sync` package ingesting OWTICS into a sibling `owcs.sqlite3`, with
  OWCS pages (bans, maps, standings) fed from a separately-fetched `owcs.json`
  rather than inlining another ~10 MB into the page; names are never
  fuzzy-matched across sources (an explicit curated alias table, zero rows on
  day one, instead); FACEIT and OWCS statistics never mix. Phase 1 is **blocked
  on asking OWTICS directly via their Discord** — they publish no terms of
  service, so silence is not permission; frame it as a contributor, and make
  attribution a design requirement, not a footer nicety. Phase 2 — VOD comps
  into `map_instances(source_type='owcs')` — is unblocked by phase 1 and does
  no broadcast geometry work. Phase 3 (automated VOD retrieval) is explicitly
  deferred. **Highest-leverage uncertainty: if OWTICS ever populates
  `replayCode`, phase 2 collapses into "capture the replay with the existing
  tool"** — re-check periodically; it costs one message to ask. This supersedes
  the older "scrape from FACEIT where possible" framing.
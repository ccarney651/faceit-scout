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
  brainstorm).** The aggregate side-b deficit (mean 0.760 vs side a 0.820 over
  1410 slot-reads) is not yet partitioned between these:
  - **Side-b tile misalignment.** The crop sometimes lands a full tile-width
    (~141px) off on side b, consistently for a whole match (correct on some
    replays, wrong on others) — a per-session/per-sample issue, not the frozen
    calibration constant, which re-measures accurate. Rule out first: whether
    the review artifact's exported frame matches the frame `match.js` actually
    scored; then window position/focus drift across an overnight session.
    Native (`PrintWindow`) vs browser (`getDisplayMedia`) capture have never
    been cross-validated pixel-for-pixel.
  - **Ref-library confusion pairs.** Full pairwise cosine similarity found
    Cassidy↔Pharah mutual (margin 0.11–0.17), Vendetta↔Brigitte dangerously
    tight (0.04), D.Va↔Wuyang and Mei↔Anran (~0.30). A template-distinctiveness
    problem, independent of geometry — 64×36 grayscale may be too little
    resolution, or the crop may be catching the wrong silhouette detail.
  - **Transient visual noise corrupting crops.** A red damage-vignette wash
    across the whole strip plus elimination/respawn overlays directly on
    portraits; a 2-ref static library cannot match through it. Frequency across
    the corpus unknown.
  A whole-round low-score red flag (distinct from today's per-sample flag) is
  worth considering, since temporal voting is blind to a problem consistent
  across all of a round's samples. The evidence (`refs_diag/`) was cleared this
  session.
- **P3 — refs_trainer replay-save verification.** Research (2026-09-11)
  concluded the replay-save trigger is "in progress AND ends"; the trainer's
  `Set Match Time(0)` loop during Setup/Assembling may keep a match from ever
  entering "in progress", so no save fires. Unconfirmed: whether spectator-only
  participation is excluded, and whether `Declare Match Draw`/`Declare Player
  Victory` count as a qualifying end. Empirical test: run the updated trainer
  but let one round reach a natural, un-reset end, or read `Is Game In
  Progress` on a debug HUD.
- **Watch — single-read segments.** The low-support fix trades a flag for
  coverage: a lone misread that used to be absorbed into a running segment now
  becomes its own segment and is no longer flagged. Watch the next full review
  for stray misreads silently going uncorrected; if they show up, treat
  `reads.length === 1` segments with more suspicion than multi-read ones.

## Scrim mode, phases 2–6

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
# Changelog

The notable changes to OWDB, newest first. Format follows
[Keep a Changelog](https://keepachangelog.com/); the section headings are
Added / Changed / Fixed / Removed.

**Entries are dated, not versioned.** The project has no version tags and ships
continuously to a live site, so a version number would be fiction. A date is the
honest unit.

> **Maintaining this:** add an entry when a change is visible to someone using
> owdb.io, changes a data contract, or changes an operational procedure. Routine
> refactors, test-only changes, and the automated dashboard data refreshes do
> not need entries.

Entries before 2026-08-11 were reconstructed from git history.

---

## 2026-08-18

### Fixed
- **The HUD name crop was pointed at the wrong part of the screen.** Calibration
  fits its box to the hero *portraits*, and the name crop assumed the name sat at
  a fixed 48-90% of that box's height. On a real frame that band straddles the
  portrait bottom, the name and the health bar - and the bar, being a solid
  bright block, is the brightest thing in it. Reads came back as letter-soup or
  empty, which is the likeliest reason `comp_slots.player_id` was 0 of 1620
  historically.

  The name row is now *located* in the frame, once per side across the whole
  five-slot strip, and all five crops use it. It cannot be done per slot: the
  hero portrait sits inside the cell above the name and its art is dense enough
  to look like text, and a long name can out-score the health bar. Across the
  strip the five names reinforce each other while portrait noise averages out.

  Measured with real tesseract on nine real HUD frames, ground truth taken from
  the replay code burnt into each frame (`tools/real_frame_eval/`):

  | | reads correct on their own | slots attributed | wrong |
  | --- | --- | --- | --- |
  | before | 15/90 | 36/90 | 2 |
  | after | 77/90 | **90/90** | 0 |

  The thirteen reads that are still wrong on their own are recovered by the role
  constraint, including three frames where tesseract returns `404f` for a clean,
  legible `PROXY`.

- **Player attribution could tag the wrong team.** The role constraint is only
  meaningful once it is known which team is on which side; with the sides
  unconfirmed the capture page could confidently attribute a slot to the other
  team's player. Attribution now reaches the role constraint only when the sides
  are known - from the read itself or from the operator locking them - and falls
  back to name-only matching otherwise, which cannot invent a tag.

### Confirmed live
- **2026-08-18, code `3DQNHD`, Oasis, Sheffield TD vs The best in the west: 10/10
  players tagged, none wrong, none abstained.** The same code read 6/10 with four
  abstentions before the crop fix. This is the roster the design was written
  against — `ÄL7ÖTĦÌ` and `Mź7w` were previously unmatchable by name — and both
  resolved. Sides were locked by the operator, so the role constraint was active.

  Eight slots matched on name evidence and two were forced by role, and between
  them the raw reads exercised every part of the design:

  - `"AYZO"` and `"FAISAL"` came back **forced** — Hazard and Mauga are tanks, one
    candidate each, settled with no name evidence. Both reads were independently
    clean, so the constraint's answer can be checked against them, and agrees.
  - One read was destroyed: `"1.7-1'4"` for `GRank`, on a crop legible by eye. It
    still resolved, because its support partner read `"ZAK"` decisively and the
    pair is an exact cover — the single-decisive-read clause, in the field.
  - `"MZ7W"` and `"AL7OTHI"` matched `Mź7w` and `ÄL7ÖTĦÌ`, which is the stroked-
    Latin transliteration doing exactly what it was added for.

### Notes
- One map, one snapshot. It does not tell us where the abstention floor bites,
  because nothing came close to it.
- The locator was swept over nine frames at four capture resolutions with the
  calibration box shifted by up to +/-25px and stretched 0.8-1.25x: 1800 of 1800
  variants land on the name row. A parity check runs the shipped JS over those
  same real pixels, so the Python prototype used for sweeping cannot drift away
  from what ships.

---

## 2026-08-16

### Added
- **League capture now assigns players by role, not by reading their name.**
  Overwatch tournament play is role-locked and FACEIT records each player's role
  per game, so the hero recognised in a slot says which players can possibly be
  standing in it. A correctly-read comp goes from 120 possible assignments to
  four, and the tank is settled with no name evidence at all. Measured against
  every real lineup with ground truth known by construction
  (`tools/assign_eval.py`): at 30% character error, slots tagged goes from 63.5%
  to 98.9%; at 50%, from 23.5% to 86.0%. With the names contributing *nothing* it
  still tags the tank correctly on every map.

  This matters most for the teams it used to fail on completely — a roster like
  `ÄL7ÖTĦÌ` / `Mź7w` was close to unattributable before, and is now resolved from
  one or two usable reads.

  Checked against real frames, not just the model: across eight real HUD frames
  with ground truth taken from the replay code in the frame, the old matcher
  resolved 68 of 80 slots and the new one 80 of 80, neither ever wrong
  (`tools/real_frame_eval/`). Two of those recoveries are worth naming — tesseract
  returned `4.04` for a perfectly legible `PROXY` in six frames of eight, and one
  slot that reads `JODAN` flawlessly can never be name-matched at all, because
  FACEIT's stored battletag for that player says `Arclite`.

  It abstains rather than guesses. A contested pair must clear a lead over the
  runner-up, and then either an absolute score floor or one slot matching
  decisively; slots that fail are left for the operator. The floor is
  load-bearing: without it the same resolver invented 33.6% wrong attributions
  once the reads went to noise.

- **`data.json` carries `lineups` (per game, with roles) and `hero_roles`.**
  `rosters` stays as it is — it is per *match*, and 27% of match-teams field more
  than five players once substitutes are counted, which is exactly what breaks the
  five-over-five cover the assignment depends on. Scrim opponent identification
  still reads `rosters`, where the accumulated squad is the right answer.

- **Captures publish `player_conf` per slot** (`forced` / `matched` / `null`)
  beside the raw HUD read, so a role-determined tag can be told apart from a
  name-matched one, and a future matcher can re-resolve old captures offline.

### Fixed
- **Names using stroked Latin letters could never match, even with a flawless
  OCR read.** The fold decomposed accents but left `ø ł đ ħ ŧ ŋ …` untouched,
  because those have no canonical decomposition — so the roster held a glyph an
  ASCII-restricted OCR is incapable of emitting. `ŚŁØŴ` scored 50 against a bar
  of 75 while the OCR was reading a perfectly correct `slow`. Affects 10 of 1304
  league players.

### Notes
- Scrims are deliberately unchanged: the per-game role data this relies on exists
  only for a coded league match. See `specs/2026-08-16-player-assignment-design.md`.
- The percentage curves come from a synthetic OCR-corruption model, which ranks
  the thresholds but does not predict field accuracy — real tesseract errors are
  systematic, not uniform noise. The real-frame check in `tools/real_frame_eval/`
  is the stronger evidence, but it is one match and one lineup, and it assumes
  hero recognition is correct. The thresholds stay provisional until more real
  capture sessions have been measured.

---

## 2026-08-14 (later)

### Fixed
- **The floating capture panel never said which team was on which side.** It is
  the only UI visible while Overwatch is in front, and its two read-out columns
  were labelled "Left" and "Right" — true, and useless, since which team is on
  the left is the one thing the operator needs from it. Both capture pages now
  name those columns after the teams actually on those sides, and the scrim
  panel gained the map-and-teams info line the league panel already had, with
  unconfirmed sides flagged rather than shown as fact.

### Added
- **The next map can be started from the floating panel.** A scrim is a series
  of maps, and having to alt-tab back to the page between every one of them was
  the most jarring part of the flow. The panel now carries a mode and map
  picker whenever no map is running, so the whole loop — pick, capture, finish,
  pick the next — closes without leaving it.
- **Scrim panel parity with the league one:** re-detect sides, copy the workshop
  code, spent sub-maps dimmed out, and Finish moved to its own pinned row away
  from the buttons pressed every round.

---

## 2026-08-14

### Added
- **The scrims viewer does the analysis the league Scout pages do.** Until now
  it counted hero appearances and stopped, which is a capture archive rather
  than a scouting tool. It now shows **comp families** (two lineups are the same
  comp if they share ≥4 heroes, or exactly 3 including the same tank) with a
  W-L record counted over distinct maps; a **hero pool counted in rounds, not
  maps**, split Tank/Damage/Support, because "played every round" and "played
  for one point" are the same "1 map" and completely different reads; **per-map
  openers broken down by segment** — sub-map on Control, attack/defend on Escort
  and Hybrid, whole map on the mirrored modes; and **recurring swaps led by
  their trigger**, with baseline subtraction so an enemy hero who is always on
  the field is not reported as having caused anything. Same semantics as
  `owdb/analysis.py`, reimplemented inline because this page has no build step.
- **A Bans tab, for the teams that scrim with them.** Preferred bans split by
  who made them, the record on maps with a given hero banned out, and how each
  side's opening comp shifts under a ban. The tab only appears once some map has
  actually recorded bans — a team that scrims without them is not shown an empty
  page asking why they have no ban profile. Scrim capture does not record draft
  *order*, so these are preferred bans and the page says so; there is no "first
  ban" section, because that would be inventing something never captured.
- **The demo (`scrims.html?demo=1`) exercises all of it.** Its observations now
  carry the fields the capture page actually writes, so segments, swaps and
  round denominators appear in the sample rather than reading as empty panels,
  and two of its four blocks use bans so both kinds of scrim are shown.

### Fixed
- **A misread portrait could invent a comp nobody played.** Two shapes the OCR
  emits on a bad frame were being analysed as real lineups: the same hero read
  into two slots (impossible with the hero limit always on) and a six-hero side
  (impossible in 5v5). The duplicate was worse than cosmetic — it let one shared
  hero count twice toward the four-hero comp-family bar, folding two different
  comps into one. Lineups are now deduplicated, a read of more than five is
  dropped as unusable, and a short read still counts, since three heroes read is
  three heroes that were genuinely on the field.
- **Ten heroes had no role in the scrims viewer, and three more were misspelled
  out of existence.** Its hand-kept hero→role table used display spellings —
  `D.Va`, `Soldier: 76`, `Lifeweaver` — that `refs.json` never writes, so those
  heroes matched nothing; the 2026 additions (Anran, Domina, Emre, Freja,
  Jetpack Cat, Mizuki, Shion, Sierra, Vendetta, Wuyang) were absent outright.
  Every one of them fell into an "Other" bucket in any role split. The table is
  now derived from `faceit_sync/subroles.py`, and a test fails if the copy ever
  disagrees with it again.
- **Section headings inside viewer cards rendered as plain body text** — the
  `.eyebrow` class was used throughout but never defined.

---

## 2026-08-13

### Changed
- **`docs/capture/index.html` and `docs/capture/scrim.html` now share a JS
  engine instead of being hand-maintained forks.** The two pages had drifted:
  104 top-level functions existed in both, 44 of them silently different.
  Seven modules — `names.js`, `util.js`, `idb.js`, `frames.js`,
  `calibration.js`, `refs.js`, `overlay.js`, `tour.js` — moved to
  `docs/capture/engine/`, cutting the shared-but-forked count to 34. No
  user-visible behaviour changed; where the code lives did. The
  snapshot/review/finish cluster (`finishMap` and neighbours) stays forked
  until phase 3 rewrites the scrim finish flow. See `ARCHITECTURE.md` §6.
- `tools/capture_divergence.py` reports which functions still differ between
  the two pages, and `tests/test_capture_js_units.py` now runs every
  `docs/capture/**/*.test.js` under `node --test` via pytest —
  `scoreboard.test.js`'s 9 tests were previously never executed by anything.

### Fixed
- **The capture pages' CSP was silently blocking every same-origin script.**
  `script-src` lacked `'self'` while `style-src`/`img-src`/`font-src` all had
  it, so `<script src="scoreboard.js">` had never loaded in production.
  Commit `bc91c1f` adds `'self'`, which is also a prerequisite for the shared
  engine above.
- Real drift caught during the extraction: `simScore` (the scrim page had a
  weaker name normaliser), `uiModal` (the scrim copy had dropped the
  `textarea` case, breaking OCR edit-and-reparse on that page), and
  `ocrWorker` (the scrim page lacked the league page's OCR load timeout, so
  its OCR could hang forever).

## 2026-08-11

### Changed
- **Registered the 2026-08-11 patch code wipe.** Every replay code from before
  the patch is dead; the site and the capture tool now count those maps as lost
  to the wipe rather than offering them. Test fixtures that need a live code now
  derive their match dates from `LATEST_KNOWN_WIPE` instead of hard-coding one,
  so future wipes no longer silently flip them to dead.

### Added
- `ARCHITECTURE.md` — one document explaining every part of the project and how
  the parts connect, with `tests/test_docs_links.py` verifying that every repo
  path it cites actually exists.
- Raw OCR HUD reads are now published with each capture, so a misattribution can
  be traced back to what the tool actually saw.
- Sub-map elimination: spent Control sub-maps are dimmed and struck through, and
  player attribution now matches both the Battle.net name and the FACEIT
  nickname.

### Fixed
- **OCR was silently broken by our own Content-Security-Policy**, which blocked
  `tesseract.js` from starting its blob worker. Four sessions of
  false leads — a local bundle, a CDN fallback, a worker probe — were reverted
  once the real cause was found. `tests/test_capture_csp.py` now pins the
  clauses that matter.
- A single OCR load failure no longer permanently blocks side detection.
- The social-preview screenshot server binds to loopback instead of every
  interface.

### Removed
- 1,530 debug crop images untracked from git, the retired `build/` and `dist/`
  PyInstaller output, and the dead `GUIDED`, `DISTRIBUTION.md`, and `poc/` files.

## 2026-08-10

### Added
- **The OWDB visual redesign**: a shared `docs/theme.css` carrying every design
  token and primitive, self-hosted Space Grotesk and Inter, five colour palettes,
  a warm-paper light mode, and a manual Light/Auto/Dark toggle. The dashboard
  inlines the stylesheet (with fonts base64-embedded) so it stays a single file;
  the capture pages and scrims page link it directly.
- Season 10 groundwork: `_season_of()` championship-name parsing, a `--season`
  export filter, season-scoped capture directories, and a full cutover design
  document. The live site is pinned to `--season s9` ahead of the overlap period.
- A final-standings section on the Playoffs bracket, and a counter-ban reply
  signal in the draft simulator.
- Capture entry points now scope to the selected division.

### Fixed
- The capture app's OCR side-detection could hang forever; it now warms up
  before first use, grabs a frame before loading, and retries on a fresh frame.
- A crash in the publish-impact preview, Finish-button clipping in the pop-out
  panel, several draft-simulator bugs, and dark-theme accent contrast.
- A non-editable install was broken because `theme.css` and the fonts lived
  outside the package; they were relocated into `faceit_sync/`.

## 2026-08-09

### Added
- **Power Rankings** on the Overview tab — a pure Elo core with sparkline rating
  trends, provisional-row shading, and forfeits counted as series results.
- **League-wide click-to-codes**: every replay-code chip opens the capture tool
  with that code loaded, and every team name gains a capture icon that
  pre-filters the tool to that team.
- The capture-funnel callout on Overview now lists only teams that actually have
  a live, uncaptured replay to scout.

### Changed
- **Rebranded to owdb.io.** The site and the upload Worker moved off owscout.com,
  and the `owscout` package and CLI were renamed to `owdb`. The browser
  IndexedDB name `owscout-capture` was deliberately left alone until the Season
  10 cutover.
- Scrim capture was paused behind a full-screen notice while the flow is
  finished, and the capture app moved to a control-panel-only flow.

### Fixed
- A Discord login redirect crash, and a ref-bundle idempotency regression.

## 2026-08-08

### Added
- **Team Compare** — a two-team radar with a side-by-side map table.
- An efficiency rating for players, and playoff games folded into coverage.

### Changed
- The dashboard was modularised from one large string into four static part
  files under `faceit_sync/dashboard/`.
- The two scrims implementations were consolidated: `docs/scrims.html` is the one
  viewer.

### Removed
- The retired native Windows GUI — `gui.py`, the app entry point, the PyInstaller
  specs, and its launcher — along with the dashboard's phantom Scrims tab.

## 2026-08-06 – 2026-08-07

### Added
- An explainable draft simulator: map and ban suggestions carry their reasoning
  and replay-code evidence.
- Full match pages for scouted playoff games, plus an admin capture panel showing
  live scouts and per-contributor map detail.

### Fixed
- The playoff bracket crawl is now seeded from the regular-season division, and
  the bracket column layout was corrected.

## 2026-08-04 – 2026-08-05

### Added
- **Capture onboarding**: a guided first-capture tour, an auto-calibrate
  confidence preview, and a contributor impact panel — the three friction fixes
  that adoption was blocked on.
- The capture recommendations panel, ranking under-covered maps by unseen minutes.

## 2026-08-01 – 2026-08-02

### Added
- A dedicated match detail page with `#match=` routing, and compact at-a-glance
  match cards.
- **Private Scrims**: scrim capture, the scrims viewer, the in-game Workshop
  helper, and a unified League/Scrims navigation. Screenshot-session import,
  auto side-detection, and the scoreboard score read all shipped behind WIP
  markers.
- Inlined team logos and per-game player-to-hero mapping.

### Changed
- Wiped replay codes are marked everywhere click-to-codes appears, with a
  tooltip explaining what "code wiped" means.

## 2026-07-31

### Added
- **NA unlocked** — the site is no longer EMEA-only.
- **Click-to-codes** across the Scout tab: ban tendencies, first bans, map picks,
  counter-bans, signature setups, and counter-scout matchups all became clickable
  routes to the underlying replays.
- Hero swaps are now confirmed via player identity rather than hero sets alone.

### Changed
- The Overview and navigation redesign: the Playoffs tab folded into Matches as a
  toggle, and the draft simulator was relegated from a top-level tab to a beta
  section.

## 2026-07-28 – 2026-07-30

### Added
- The **draft simulator**: a branching win/lose scenario tree with map selection
  as buttons, bans as counted buttons, and reliable ban reads.
- Scheduled and upcoming fixtures are ingested and shown across divisions, and
  the playoff bracket is built from real ingested matches.
- A social card, favicon, meta tags, and the CNAME for the custom domain.

### Changed
- The Players tab was rebuilt as a directory rather than a ranking — a
  credibility fix — with a "By seat" view over five sub-roles.
- CI rebuilds on code changes and skips the FACEIT fetch on push runs.
- Registered the 2026-07-28 patch code wipe.

## 2026-07-26 – 2026-07-27

### Added
- **The browser capture app.** From a viability proof of concept to a shipped
  tool in two days: screen capture, a Document Picture-in-Picture overlay,
  rounds and sub-maps, publishing to the site, auto-calibration, undo history,
  hero-recognition teaching, pre-publish review, and **live scouting claims over
  a Durable Object WebSocket** so two scouts never collide on the same map.
- A Discord login scaffold and an admin contributor roster on the Worker.
- The Playoffs tab, FACEIT-style region and division filters, and rosters
  at a glance.

### Changed
- The whole system became tier-generic, and the Expert division was un-parked.

### Fixed
- A Worker account-hijack hole found in a bugfix sweep, CORS preflight returning
  a body on 204, and mobile overflow.

## 2026-07-24 – 2026-07-25

### Added
- Role and seat player leaderboards, attacker-advantage panels, and per-game
  opening comps on every match card.

### Changed
- Win-rate honesty at low sample counts, with low-data players ranked separately
  and capture coverage made prominent.

## 2026-07-21 – 2026-07-22

### Added
- Auto-calibration that derives the ROI boxes from HUD proportions, with a
  self-test that flags misaligned boxes immediately.
- A draggable, position-remembering capture overlay, and a guided testers' build.
- Player attribution now matches the HUD's Battle.net name, not just the FACEIT
  nickname.

### Fixed
- Variable shadowing that broke every upload.

## 2026-07-19 – 2026-07-20

### Added
- **Open-access uploads** — no keys, no accounts, nothing to configure — and
  one-press publishing straight to the site repository.
- Shared "already scouted" awareness across contributors, and a "Fetch new
  matches" button for on-demand rebuilds.
- Competitive seats (Tank, Hitscan, Flex DPS, Main Support, Flex Support) with
  full 51-hero coverage, the ban planner, and counter-scout.
- A fresh install now downloads the database snapshot from the site instead of a
  30-minute crawl.

### Changed
- The nightly build moved to 9pm UK time, made DST-proof with a two-cron gate.

## 2026-07-18

The single largest day in the project's history — 60 commits.

### Added
- **The scouting interpretation layer**: comp identity and swap analysis,
  comp-family clustering, per-team scouting reports, mid-map swap analysis, and
  ban-response reads.
- The **multi-contributor exchange format** and its first-wins merge, with the
  published report derived from contributions at build time rather than
  committed — the decision that lets analysis improvements apply retroactively.
- Attack/defend phase derivation, control-map sub-map tagging, dead-state hero
  references, and alignment-tolerant matching that lifted mean match confidence
  from 0.72 to 0.88.
- A capture draft/review/finalize gate, in-review hero correction, and a
  shareable reference library.

### Fixed
- A blank dashboard caused by a duplicate `ROLE_ORDER` declaration — which is
  why the JavaScript syntax test exists.
- The replay-code backfill was narrowed to the cases that can actually gain a
  code.

## 2026-07-16 – 2026-07-17

### Added
- **`owscout`** — Overwatch 2 composition extraction from replays, integrated
  into the dashboard.
- HUD reference learning, per-team blue/red reference variants, single-portrait
  learn mode, and a desktop GUI.

## 2026-07-09 – 2026-07-10

### Added
- **The initial release**: the FACEIT OW2 scouting tool and its auto-updating
  dashboard, with daily updates moved to GitHub Actions so they run whether or
  not a PC is on.
- Multi-division and combined views, rule-based ban ordering, per-game rosters,
  copyable replay codes, and the League meta map pool.

---

## About the automated commits

`.github/workflows/update.yml` has produced roughly 260 `Auto-update dashboard`
and merge commits over this period. They carry refreshed match data rather than
code changes and are intentionally excluded from the entries above.

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

## 2026-08-13

### Changed
- **Scrim capture is un-paused.** The unconditional `#scrimpaused` overlay
  added in `f2881cf` is gone from both `docs/capture/scrim.html` (blocked
  capturing) and `docs/scrims.html` (blocked viewing) — removing only one
  would have shipped scrims you could record but not read. Un-pausing was
  gated on the league-code block: `docs/capture/scrim.html` now refuses to
  start a scrim capture on a code it recognises as a live league match,
  naming the division, via `classifyCode`/`buildCodeIndex` in
  `docs/capture/engine/session.js` checked against `docs/capture/data.json`'s
  codes. This finishes phases 0-1 of `specs/2026-08-12-scrim-mode-design.md`;
  see `ARCHITECTURE.md` §7. This changes the operational procedure for
  recording scrims — the capture and viewer pages are usable again instead of
  redirecting to League capture.
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

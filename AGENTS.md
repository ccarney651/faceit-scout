# AGENTS.md

Canonical instructions for coding agents working in this repository. Claude
Code, opencode, Codex, and Cursor all work from this file.

## What this is

**OWDB** — Overwatch 2 composition scouting for the FACEIT League. Two Python
packages feed **one website** (`docs/index.html`):

- **`faceit_sync`** — incremental, idempotent ingest of FACEIT League match data
  into a local SQLite database, exported as a self-contained HTML dashboard.
- **`owdb`** — reads hero comps off the observer HUD of in-client replays and
  turns them into per-team composition scouting on the same page. Capture happens
  through the browser app at `docs/capture/` — **the only supported capture
  path.**

## Read this first

**`ARCHITECTURE.md` explains every part of the project and how the parts
connect.** Read it before deep work. Fast paths:

| You need | Go to |
| --- | --- |
| Where anything lives | `ARCHITECTURE.md` §0-2 |
| Ingest and the three data hazards | `ARCHITECTURE.md` §3 |
| How `docs/index.html` is built | `ARCHITECTURE.md` §4 |
| The capture pipeline | `ARCHITECTURE.md` §5-6 |
| Scrims | `ARCHITECTURE.md` §7 |
| CI and the Cloudflare Worker | `ARCHITECTURE.md` §8 |
| File formats crossing a boundary | `ARCHITECTURE.md` §9 |
| Code wipes and season cutover | `ARCHITECTURE.md` §10 |
| Project vocabulary | `ARCHITECTURE.md` §11 |
| **Rules that must not be broken** | **`ARCHITECTURE.md` §12** |
| Which test guards what | `ARCHITECTURE.md` §13 |

Other documentation: `README.md` (ingest and data hazards, long-form),
`FEATURES.md` (feature-by-feature — known to lag the code), `SPEC.md` (the
original `owdb` design reference), `CHANGELOG.md` (what changed and when),
`specs/` (one design and plan document per feature, plus `specs/BACKLOG.md`).

## Commands

Dev environment is **Windows**; use the venv Python directly:

```bash
.venv/Scripts/python.exe -m pytest                 # full suite (tests/ + owdb/tests/)
.venv/Scripts/python.exe -m pytest tests/test_export.py::test_name   # one test
.venv/Scripts/python.exe -m pytest -k scheduled    # by keyword
.venv/Scripts/python.exe -m mypy faceit_sync       # strict; must stay clean
pip install -e ".[dev]"                            # install (add [capture] for owdb CV deps)
```

`faceit-sync` and `owdb` are the console entry points. Common flows:

```bash
faceit-sync fetch --matches-file matches.txt        # seed + keyless transitive ingest
faceit-sync fetch --championship <id>               # enumerate (needs FACEIT_API_KEY)
faceit-sync export --format html --out docs/index.html          # build the site
faceit-sync export --format html --out docs/index.html --region na
faceit-sync resolve-season --season s10          # the season CI would publish today
owdb ... contribute merge --dir data/captures/s10 --out owdb_comps.json
faceit-sync trials --out trials.html                 # local trialist comparison (never commit it)
```

### Verifying the dashboard

The dashboard's **entire body is rendered in JavaScript** from an inlined data
blob, so **one JS syntax error yields a completely blank page** that
bracket-balance checks will not catch. Always:

- Run `pytest tests/test_export.py::test_dashboard_javascript_is_syntactically_valid`
  (it runs `node --check` over the generated script) after editing any part file
  under `faceit_sync/dashboard/`.
- For visual checks, build a local `.html` and screenshot with headless Edge.
  On Windows use `--screenshot=FILE`, **not** `--dump-dom` — the GUI executable
  produces no stdout.

## Invariants

These are the same rules as `ARCHITECTURE.md` §12, stated here so they are never
one file-read away. If the two lists ever disagree, `ARCHITECTURE.md` is
canonical and this copy is the bug.

1. **Never hand-edit `docs/index.html`.** CI regenerates it from
   `faceit_sync/dashboard/head.html` on every run; the edit disappears at the
   next build. Fix the part file.
2. **Never run `faceit-sync export` locally to "just regenerate" the site.** The
   local `faceit.sqlite3` is routinely days behind CI's cached copy, so
   committing a local export overwrites fresh data with stale data.
3. **Always run the dashboard JS syntax test after editing anything under
   `faceit_sync/dashboard/`.**
4. **Bump the code-wipe date only in `_SEED_WIPES` in `owdb/db.py`.** Everything
   downstream derives from it.
5. **Never bump the IndexedDB schema version from `docs/scrims.html`.** It is a
   read-only consumer of the capture app's store.
6. **Never commit `owdb_comps.json`.** A committed report would outlive the
   observations it came from and freeze the analysis that produced it.
7. **Never change the client User-Agent to impersonate a browser.** FACEIT's
   edge returns 403 for `Mozilla/5.0`-style agents.
8. **Never add scrims into the dashboard build.** The private side stays
   separate.
9. **Always `git fetch` before pushing.** CI auto-commits to `origin/main` every
   few minutes; expect a merge, and resolve by keeping CI's data and reapplying
   your diff on top.
10. **Never put developer documentation in `docs/`.** That is the GitHub Pages
    web root — anything there is published to owdb.io.
11. **`wrangler deploy` is run by the human.** A commit to
    `infra/upload-worker/worker.js` is not live until someone deploys it.
12. **Never unlock one scrim page without the other.** `docs/capture/scrim.html`
    records scrims, `docs/scrims.html` reads them; either alone is half a
    feature.
13. **The scrim lock must fail closed.** The overlay is static markup and the
    gate only removes it, so any failure leaves the page locked.
14. **Never commit or publish the trials page.** `faceit-sync trials` writes a
    private page naming who you are trialling. `/trials.html` is gitignored
    (root-anchored: `faceit_sync/dashboard/trials.html` is its shell and *is*
    tracked), and it must never be written under `docs/`.
15. **Never trust a replay code read through a hand-dragged calibration box.**
    Past ~±2% of strip error the read returns a well-formed *wrong* code, not a
    failure. The probes in `engine/replaycode.js` refuse there now; the
    sensitivity itself remains.

## Gotchas

- **Replay codes are invalidated by every Overwatch patch (a "code wipe").** The
  date has **one** source: `_SEED_WIPES` in `owdb/db.py`.
  `tools/build_capture_data.py` imports `LATEST_KNOWN_WIPE` rather than
  restating it. When a patch lands, add the entry and update the pinned
  assertions in `owdb/tests/test_context.py`. Fixture matches that must stay
  alive derive their dates from `LATEST_KNOWN_WIPE` — never hard-code one.
- **The capture pages' Content-Security-Policy lives in a `<meta>` tag**, so
  `curl -I` shows nothing. It has silently broken browser APIs *three* times:
  tesseract's `blob:` worker, `scoreboard.js` (never loaded in production for
  months), and `heroes.js` on `docs/scrims.html`, which took the entire viewer
  down. `tests/test_page_csp_permits_own_scripts.py` now checks every page under
  `docs/` against its own policy, so a new script on an old page is caught the
  day it lands — but only for `<script src>`. Workers, styles and connections are
  still on you; check the policy first when something fails quietly.
- **Every OCR read goes through `ocrRead()`.** `ocrWorker()`'s timeout only covers
  *loading* tesseract; a `recognize()` that stalls afterwards never returns, and
  because tesseract runs one job at a time per worker it takes every other read
  down with it. `ocrRead` races a deadline and discards the wedged worker. Do not
  call `w.recognize()` directly — a test fails if you do.
- **The replay-code crop is only as right as the calibration strip, and the
  contrast ladder cannot tell you when it isn't.** `codeBox()` is fractions of
  `boxes.a`. Measured over twelve real frames: past roughly ±2% of strip error the
  read does not fail, it returns a well-formed six-character code belonging to
  another game — 54 times. A mis-placed crop is mis-placed *identically* at every
  contrast level, so all three passes agree and agreement is what the rule accepts
  on. The fix is a second geometry, not a fourth contrast: `PROBES` in
  `engine/replaycode.js` reads at five crop positions and takes the code only when
  all five agree. If you touch the offsets or the probes, re-run
  `tools/real_frame_eval/code_strip_tolerance.py` **and**
  `code_strip_guard_check.py` — the latter exists because the first probe set was
  only ever tested against errors on the axis it probed, which flattered it.
- **pytest cannot see through a real browser.** It checks syntax and shape, not
  behaviour against a live DOM, IndexedDB or CSP — a gap that has hidden live
  bugs more than once, most recently a CSP that blocked `docs/scrims.html`'s only
  external script and left the whole viewer blank. `tools/verify_capture_browser.js`
  closes most of it: serve `docs/`, `npm install --no-save playwright-core
  tesseract.js` (both, in one command — separate `--no-save` installs prune each
  other), then run it. 129 checks. Everything left needs a human with Overwatch
  open: screen share, calibration, portrait recognition, the overlay over the
  game.
- **`docs/theme.css` is the design system; a page that restates one of its
  values is the bug.** Colour, type and corner radii are tokens, and the pages
  had drifted by writing the answers down instead of reading them: `#fff` on
  `background:var(--accent)` (correct in the light palette, 1.93:1 on Teal),
  `#0b1020` where `var(--on-accent)` belongs, twelve different corner radii, and
  forty-two rules copied byte-for-byte into both data pages. Rules:
  `--on-accent` is the ink for **any** saturated fill (accent, `--good`,
  `--mid`), which is why it is a near-black in every dark palette; corners come
  from `--r-sm/-md/-lg/-pill`; a rule both data pages want goes in `theme.css`,
  and a name that means two things gets two names. `tests/test_ui_consistency.py`
  fails each of these, and it reads `faceit_sync/dashboard/head.html` rather than
  the generated `docs/index.html`. **`docs/theme.css` and
  `faceit_sync/dashboard/theme.css` must be copied in step** — nothing reconciles
  them at build time, and `tests/test_export.py` fails if they differ.
- **Both capture pages must open IndexedDB with the same store list**
  (`ALL_STORES` in `docs/capture/engine/idb.js`). Declaring only the stores a
  page uses looks right and breaks the other page — see `ARCHITECTURE.md` §7.
- **The capture pages share an engine under `docs/capture/engine/`.** A fix to
  calibration, hero recognition, the overlay or name matching belongs in the
  module, not in a page. The snapshot/review/finish cluster is still forked
  between the two pages until phase 3 — check both when touching it.
- **Player assignment abstains; do not "improve" it into guessing.** The floor in
  `docs/capture/engine/assign.js` is the only thing keeping the wrong-attribution
  rate at zero — removing it took the same resolver to 33.6% wrong once the OCR
  reads degraded. If you change either threshold, re-run `tools/assign_eval.py`
  and move the numbers in `ARCHITECTURE.md` with it.
- **`data.json`'s `lineups` is per game and `rosters` is per match on purpose.**
  27% of match-teams field more than five players once substitutes are counted,
  which destroys the exact five-over-five cover assignment relies on. Do not
  collapse the two.
- **`AUTO_STRIPS` is correct live; the frames in `screenshots/` do not match it.**
  Verified 2026-08-18: auto-calibrate reports 10/10 portraits confident against a
  live share. On those old replay-HUD screenshots it reaches only 4.83-5.48 where
  the measured strip scores 6.06-6.82, and the gap is strip *size* (~6% wider,
  ~14% taller) so no dx/dy sweep closes it. That is a property of the fixtures,
  not a bug: derive boxes from the pixels when evaluating against them (as
  `tools/real_frame_eval/gen_all.py` does) and do NOT change `AUTO_STRIPS`.
- **The HUD name crop must come from `nameRow()`, not from a fraction of the
  calibration box.** The box is fitted to the portraits; every fixed band under
  it that anyone has tried also contains the health bar or the portrait bottom,
  and tesseract reads the bar. Find the row once per SIDE across the five-slot
  strip — per slot it picks the hero portrait. Two per-slot attempts were built
  and reverted; `tools/real_frame_eval/README.md` records both so they are not
  tried a third time. Any change to the locator or its constants must be re-run
  through that harness (`rowfind_sweep.py`, then `rowfind_parity.py`, which
  proves the shipped JS still matches the Python the sweep uses) **before** it
  goes anywhere near a live capture.
- **Captures are season-scoped** (`data/captures/s10/`). Two writers key off a
  per-season constant each: `CURRENT_SEASON` in `infra/upload-worker/worker.js`
  and `CONTRIB_DIR` in `owdb/contribute.py`; both say `s10` since 2026-09-05, and
  the Worker's copy is not live until someone deploys it. The *reader* no longer
  needs keeping in step by hand — CI merges whichever season directory matches
  the season it is publishing (`faceit-sync resolve-season`). At a cutover,
  follow `specs/2026-08-10-season10-cutover-design.md` rather than improvising —
  **start at its §6**, then §7 for what actually shipped.
- **The S10 coverage is seeded and measured (2026-09-05).** Ten divisions:
  EMEA and NA Master/Expert/Advanced/**Intermediate**, plus SA Master and OCE
  Master. Open stays out and is the reason the page fits at all. The team counts
  are measured, not estimated — page through
  `api.faceit.com/championships/v1/championship/{id}/subscription?limit=20&offset=N`
  (keyless; `limit` over 20 returns 400, and no total is included, so page until
  a short page comes back):

  | | Master | Expert | Advanced | Intermediate |
  | --- | --- | --- | --- | --- |
  | EMEA | 16 | 27 | 43 | 46 |
  | NA | 16 | 31 | 52 | 56 |
  | SA | 10 | — | — | — |
  | OCE | 8 | — | — | — |

  That is ~2,540 matches with playoffs, ~9,140 games, **~15.7 MB** of
  `docs/index.html` — against ~10.3 MB for the same scope without Intermediate.
  `--external-data` splitting stays unnecessary. Size any future division with
  the validated formulas rather than re-estimating: Master is `n(n-1)/2` exactly,
  every other tier is 7.43 matches/team, Open is 3.16, 3.6 games a match, 1.76 KB
  of page per game. Full working: design §7.1.
- **The S10 caps are ceilings, not counts.** Master 16, Expert 32, Advanced 48,
  Intermediate 128, Open uncapped (EMEA/NA only; SA and OCE run Master + Open).
  Only Master fills its cap. Expert came in hardest under it — 41 → 27 in EMEA
  and 49 → 31 in NA — and Intermediate arrived Advanced-sized at 46/56 rather
  than anywhere near 128, which is the whole reason seeding it was affordable.
  Also new in S10 and not yet modelled anywhere: a **Season Finals** bracket per
  region (EMEA/NA, 9–15 November, 12 teams — top 4 of Master plus top 2 of each
  lower division), which is a fifth thing after Playoffs that a season can end
  in, and **no OWCS promotion/relegation** this season. Move-ups apply
  2026-11-17. Source: <https://www.faceit.com/en/news/faceit-league-season-10>
  (it 403s a plain fetch — curl it with a browser User-Agent and read the
  `__NEXT_DATA__` blob).
- **One S10 championship name still will not classify.** Both classifiers live
  in `faceit_sync/models.py` / `faceit_sync/export.py` and key off the
  championship *name* — there is no stage or tier column anywhere. `TIERS` gained
  `Intermediate` on 2026-09-05, so that half is fixed. What remains:
  - **"Season Finals" reads as a regular-season division.** `is_playoff_name`
    matches only `playoff`/`knockout`, and `_PLAYOFF_STAGE_SUFFIX` strips only
    `- Regular Season | Playoffs | Playoff Stage | Knockout Stage`. A
    `… - Season Finals` championship therefore misses the playoff split, is
    exported as its own division with its own standings table, and is *not*
    attached to any division's Playoffs tab. It is also cross-tier by design
    (top 4 Master + top 2 of each lower division), so even once classified it
    has no single region+tier division to attach to — the current
    playoff-attachment model does not have a shape for it. Decide that before
    seeding a Season Finals room, not after.
- **S10 division membership is not a function of S9 standings.** The Open
  Qualifiers (20–23 August 2026) placed teams directly into Expert and Advanced,
  on top of the usual move-ups. Anything that reasons "team X was in S9
  Advanced, so it starts S10 in Advanced" is wrong for an unknown number of
  teams; the S10 crawl is the only source for who is where.
- **There are TWO map lists and they are deliberately different.** Changing one
  is almost always wrong on its own:
  - `SCRIM_MAPS` in `docs/capture/scrim.html` — **every playable map in the
    game.** Scrims get booked on anything, and it also backs `bestMapMatch()`,
    so a map missing here is a map the replay-history OCR cannot read at all.
    Add new maps here the season they ship, whether or not the league pools
    them. Nobody did: Neon Junction was missing since its release this year, and
    Aatlis since June 2025 — over a year.
  - `POOL` in `docs/scrims.html` — **the current FACEIT season's pool**, which
    since S10 is a restricted subset (14 of 30). It seeds the practice-coverage
    panel's "never played" rows, so it must be the maps you can actually be drawn
    on. Refresh it every season from the season announcement. Dropping a map
    loses no history: `mapCoverage()` adds any played map it sees, so an
    off-pool map you did scrim still shows with its count.

  Control maps additionally need `CONTROL_SUBMAPS`, which is forked in four
  places — `owdb/maps.py` (canonical), `docs/capture/scrim.html`,
  `docs/capture/index.html` and `tools/build_scrim_demo.py`.
- **`mypy` covers `faceit_sync` only.** `owdb` is not in the must-stay-clean
  contract and currently reports two errors in `owdb/contribute.py`. Its tests
  are its safety net.
- The stats endpoint is `…/stats/v1/stats/matches/{id}` — the documented `/time`
  segment 404s.

## Roadmap

### Season state (2026-09-01)

**Season 9 is over** — last match 2026-08-17 — and **Season 10 starts Monday
7 September 2026, 01:00 BST** (confirmed by FACEIT's own announcement, so
`NEXT_SEASON_START` is right). The league feed is empty until S10 games are
played: all 4,456 coded S9 games predate the 2026-08-18 wipe, so nothing in S9
is replayable and `docs/capture/data.json` carries `codes: 0`. CI's daily runs
are healthy; a quiet commit log is no-change runs, not a break.

**The S10 calendar is now published.** Times are as FACEIT stated them; the
league runs on UTC and the announcement mixes UTC with unqualified local times,
so treat anything without an explicit zone as approximate to the hour.

| When | What | Why it matters here |
| --- | --- | --- |
| 2026-09-02 18:00 | Registration closes | Roster-addition cooldowns start applying from here |
| 2026-09-03 15:00 | Unpaid-team clear | Teams below 5 paid passes are **irreversibly removed** — team lists before this are provisional |
| **2026-09-03 15:30** | **Brackets generated** | **The operator gate.** Round 1 only; round 2 the next day, the rest as normal |
| 2026-09-07 | Season start (day 1) | `NEXT_SEASON_START`; D.Mon is legal from this day |
| week of 2026-09-21 | 3 playdays (lower divisions) | Denser than a normal week |
| week of 2026-09-28 | 3 playdays (lower divisions **and** Master) | Master's only 3-playday week |
| 2026-10-12 | **Roster lock** | After this the active-season roster is final — see the roster note below |
| 2026-11-09 23:00 UTC → 2026-11-15 22:55 UTC | Season Finals | Rounds play 11/12/13 Nov, final 15 Nov |
| 2026-11-17 | Move-ups and move-downs applied | S11 division membership resolves here |

**Seed collection unblocks on 3 September, not on the 7th.** Bracket generation
is what creates the S10 match rooms, so the hand-collected seed URLs
(`matches.txt`) can be gathered four days before the first game. Everything
`specs/BACKLOG.md` files under "around 7 September" is really "after 2026-09-03
15:30". Two caveats: only round 1 exists on the day, and a division's bracket
may lag the announced time — FACEIT says generation is slow and posts a separate
notice when every division is done. Wait for that notice before concluding a
division is missing.

**Bracket generation is also when Intermediate becomes countable.** The deferred
Intermediate call was scheduled for "week 1 of S10" on the grounds that nobody
knew its team count; the bracket publishes it on 3 September, and the cap (128)
is the ceiling regardless. The decision can be made a fortnight earlier than
planned.

**Roster churn in S10 is bounded, which the active-season roster pool can rely
on.** Once the season begins a team gets **two** roster-addition slots with a
**7-day cooldown**, in every division, and the roster is **locked outright on
12 October**. So `team_rosters` drifts slowly and stops drifting entirely
mid-season — a roster read after 12 October is final, not a snapshot.

**S10 match data is not comparable to S9 on disconnects.** FACEIT removed
pause-on-disconnect: a match no longer auto-pauses when someone drops, and each
team instead gets a single manual tech pause per map, for technical issues only.
The practical effect on the data is that a DC is now more likely to be *played
through* than restarted, so S10 should show relatively more `dc_games`
(`round_players.stats_captured=0`) and fewer `was_restarted` games than S9 for
the same underlying rate of disconnects. Neither is displayed on the site
today — `dc_games` is carried in the payload and never rendered, and
`was_restarted` only drives the per-game "veto disrupted" tag — so nothing is
broken by this. Do not put an S9-vs-S10 trend line on either without saying so.

The rest of the S10 rulebook is near-identical to S9's, so nothing else in the
ingest assumptions moves. FACEIT promised a per-playday key-dates article the
day after the season-start post; if precise playday dates ever matter, that
article — not this table — is the source.

The readiness work is **done** (2026-08-27, `specs/2026-08-27-season10-readiness-plan.md`):
Season 9 is frozen at `docs/s9/` behind `docs/archive.html`, SA/OCE are
supported regions, the page labels the season it rendered and explains a
finished one, and a pinned season with no data now falls back to the newest
season that has some — so `--season` can be flipped at any time and the site
switches itself over on the first ingested S10 match.

**The cutover has landed except the seeds (2026-09-05).** The pipeline no longer
carries a season pin in two places that a human has to keep equal. CI asks
`faceit-sync resolve-season --season s10` for the season it is publishing — the
pin once S10 has matches, the newest season that does until then — and uses that
one answer for BOTH the export and the `data/captures/<season>/` directory it
merges. The site therefore still shows Season 9 today and switches itself over,
page and captured comps together, on the first S10 match that is actually
PLAYED — a seeded-but-unplayed season does not count, or the site would empty
itself the day the rooms were added. Landed with
it: `CURRENT_SEASON` in `infra/upload-worker/worker.js` and `CONTRIB_DIR` in
`owdb/contribute.py` moved to `s10`, and `Intermediate` joined `TIERS` (inert
until such a division is seeded, but without it one would fall out of its
region's switcher silently).

**Three things are still owed, and all three are the operator's:**

1. **`wrangler deploy`** — invariant 11. Until it runs, the live Worker still
   writes uploads to `data/captures/s9/`. That is harmless while no replay code
   in the league is live, and wrong from the first S10 playday: an S10 capture
   landing in `s9/` merges into the Season 9 page. Deploy before 7 September.
2. ~~**The S10 seed URLs.**~~ **Done 2026-09-05** — all ten divisions are in
   `matches.txt` and the S9 blocks are commented out. Scope grew by the
   operator's decision to seed **Intermediate** in both regions: measured at 46
   (EMEA) and 56 (NA) teams against a 128 cap, so the whole S10 ingest sizes at
   ~15.7 MB of `docs/index.html`, against ~10.3 MB without it. Nothing crawls
   until the first playday on 7 September: every seeded room is still SCHEDULED.
3. **The S10 code-wipe date**, once the season-start patch lands — `_SEED_WIPES`
   only (invariant 4). `LATEST_KNOWN_WIPE` is still 2026-08-18. **The patch is
   Tuesday 2026-09-08**, so the entry is `("2026-09-07", ...)`: dated a day early
   on purpose, the same as the 2026-08-18 entry, so games played after the patch
   on the 8th stay scoutable. **Do not register it before the patch lands** —
   `codeDead()` is `finished_at[:10] <= wipe`, so an early entry hides every
   still-live code from the 7th and closes the only capture window Season 10's
   first playday has.

Open items: `specs/BACKLOG.md` § "Added 2026-08-27". The Season Finals shape
(cross-tier, no division to attach to) is still undecided and still has until
November.

### Priorities (ordered)

1. **Unblock capture adoption** — the binding constraint. Coverage is thin
   everywhere except FACEIT Masters, and the tool takes about a minute per map,
   so time is not the problem. The named friction fixes are **delivered**: the
   guided first-capture tour, auto-calibrate confidence preview, and contributor
   impact card (2026-08-04); the capture-funnel callout (2026-08-09);
   league-wide click-to-codes (2026-08-09); and **player attribution**
   (2026-08-18) — captures now say which FACEIT player is in which HUD slot,
   which had never worked. The priority remains to **iterate on adoption** —
   watch where new scouts stall and remove the next friction. Remaining P2
   items: NA Advanced seeding (one line in `matches.txt`), and
   `--external-data` page splitting only if page weight grows.

   The 2026-08-18 release shipped without scrim mode deliberately, branching at
   the last commit of the shared-engine extraction so the engine and the
   attribution work went live while everything scrim-facing stayed behind. Scrim
   mode has since merged (2026-08-19) and ships locked; see priority 2. That
   seam is still worth remembering — phase 0 was a pure refactor plus fixes, and
   splitting a release along one is cheaper than it looks.

2. **Scrim mode, phases 2–6.** Phases 0, 1, 2a and phase 4's analysis half are
   **shipped to `main`** (2026-08-19) — the branch is merged and deleted. What
   went live: the shared capture engine, the un-paused session scaffold, the
   league-code block, opponent identification, the panel-first capture workflow,
   the hero-grid ban picker, player names against heroes, the replay-code reader,
   and the scrims viewer at parity with league Scout. All were confirmed live by
   the operator against a real scrim captured end to end, which was the merge
   gate.

   **Both scrim pages ship LOCKED.** The feature is finished enough to merge and
   not to open, so `#scrimpaused` is back on `docs/capture/scrim.html` and
   `docs/scrims.html` with a gate in front of it: static overlay, a script that
   only ever removes it, `?unlock=scrimbeta` to open (persists per browser),
   `?lock=1` to close. There is deliberately no localhost exemption — see
   invariants 12 and 13. Opening it to the public is a decision, not a cleanup
   task.

   What remains, per `specs/2026-08-12-scrim-mode-design.md`: the rest of
   opponent identification and roster search (2); the stats read plus a workshop
   hero-glyph reference set (3); the viewer's Players tab (4); sync and sharing
   (5); auto map detection (6). See `ARCHITECTURE.md` §7.

   **Hero bans shipped 2026-08-28**, outside those phases:
   `tools/scrim_code/scrim_owdb.opy` runs a ban phase in setup and draws the
   result as text on the spectator view; `docs/capture/engine/banrow.js` reads
   it back. Design: `specs/2026-08-27-scrim-hero-bans-design.md`. Its §6.1
   records two Overwatch behaviours that each cost an in-game test cycle and are
   invisible from compiled output — `destroyAllHudTexts()` erasing anything
   created by a condition that never transitions again, and `getAllPlayers()`
   with `SpecVisibility.NEVER` rendering for nobody at all. Read it before
   touching workshop HUD code.

   **The scoreboard read shipped 2026-09-06, and it is measured, not guessed.**
   Three rules, each of which cost a wrong turn to learn:

   - **Hold the map fixed, and the board too, or the number means nothing.**
     Every colour ranking taken before this reversed itself on the next frame
     set, because each was measured on a different map. The experiment that
     works is ONE PAUSED BOARD shot from several camera angles, so the text is
     identical and the background is the only variable. Re-run it with
     `python tools/real_frame_eval/scoreboard_crop.py scoreboard_crops` then
     `node tools/real_frame_eval/scoreboard_eval.js scoreboard_crops`.
   - **Read the POSITIONAL score, not the name-matched one.** Rows join to
     players by slot, so a row whose name OCR'd badly is not lost in production.
     The harness reports both; only frames yielding exactly ten rows are scored,
     because at nine nobody knows which is missing.
   - **The saturation channel in design §8.3 is WITHDRAWN.** It assumes the
     board is the saturated thing on screen — true of team-coloured rows, false
     of white ones, so it erases them. What ships is local contrast on
     luminance. Do not reinstate it, and do not re-try a character whitelist
     either (§8.3 measured it worse in fourteen of sixteen pairings).

   **The board carries its own crop box.** Two green rules bracket it and
   `Scoreboard.findMarkerBox()` finds them, because the crop is not forgiving —
   the true extent gets 7 of 8 frames accepted, a 50% margin gets 4. Hosts must
   reload `B44BZ` to get the markers; the hand-drawn box remains the fallback.
   When debugging a live capture, check `boxSource` on the read: `'markers'`
   means the detector worked, `'manual'` means it silently fell back.

   **Bans and the spectator scoreboard only exist in lobbies running our
   workshop code.** Scrims are hosted on a mix of ScrimTime, ScrimTime Lite and
   ours, and Lite has no scoreboard — so a Lite-hosted scrim can never support
   the phase 3 stats read. The share code `B44BZ` is what moves hosts onto ours;
   see `tools/scrim_code/README.md`.

   **Auto map detection (6) is now cheaper than it was**: the code reader can
   already tell when the replay on screen is not the one being captured. It was
   deliberately left on-demand rather than polling — see
   `specs/2026-08-19-replay-code-ocr-design.md` §4.6 for what polling would cost
   and why it was declined.

   **Not covered anywhere: aspect ratios other than 16:9.** `AUTO_STRIPS`
   expresses the HUD as fractions of the frame, and auto-calibrate's sweep
   searches translation only, so it cannot correct a scale error. The failure is
   loud rather than silent — calibration scores low and says so, naming 16:9 —
   but the operator is then told to drag the boxes by hand, which is exactly the
   case the replay-code reader is least safe in. No non-16:9 HUD frame exists in
   `screenshots/`; the operator has only 16:9 monitors, so this needs a
   screenshot from someone else before anything can be claimed.

3. **OWCS expansion** — scrape from FACEIT where possible; VOD-based capture
   from YouTube and Twitch for the rest; manual entry as fallback.
4. **Statistical capture recommendations** — **delivered, and both known gaps
   are now closed (2026-08-20).**

   *Playoff games* were missing from every team-facing read, not just the
   coverage counts: team scouting was built from the regular season alone, so a
   team's comps, ban tendencies, replay-code links and coverage row stopped at
   the group stage. `leagueMatches()` now supplies the full played history
   (regular season + finished bracket) to those reads, and a Combined view
   merges `playoffs` at all. Standings, power rankings and League meta stay
   regular-season by design — see the comment on `leagueMatches` in `pure.js`.

   *The per-mode length estimates* stay hardcoded, deliberately, now with a
   measurement behind them instead of a shrug. Weighting each game by its own
   score (rounds for Control/Flashpoint, extra rounds for escort/hybrid totals
   above 3) shifts per-game estimates up to 3x and moves the panel 0-2 positions,
   with an identical top three in all five divisions: the panel aggregates to
   maps, and dozens of games per map average the variation away. Full reasoning
   sits on `MODE_MINUTES`. Revisit only if a panel ever ranks something with few
   games behind it.

### Audience

Organised play first (FACEIT League, scrims, OWCS). Aspiration to serve all
audiences if the analytics are strong enough.

## Conventions

- **Branding is "OWDB"**, on **owdb.io** (registered 2026-08-09), with the upload
  Worker on `upload.owdb.io`. The rename from "OW Scout" / `owscout` is complete
  in code, CLI, and copy; the browser IndexedDB name `owscout-capture` is
  kept **permanently**. It is invisible to users — it appears in no UI, URL or
  document — and renaming it orphans every contributor's learned refs, unsent
  captures and scrim history for no gain. The old promise to revisit it at the
  Season 10 cutover was closed as won't-do on 2026-08-27; do not re-open it at a
  season boundary.
- **Do not overengineer unless expandability requires it.** The dashboard is
  modularised into concatenated static parts under `faceit_sync/dashboard/` —
  land new features in the right part file rather than growing one string.
- **Shared design tokens, primitives and page furniture live in
  `docs/theme.css`** — colours, fonts and the `--r-sm/-md/-lg/-pill` radius
  scale; `.card`, `.btn`, the `.prodname` wordmark, `.sidetoggle`/`.sidebox`,
  `nav`, `.eyebrow`; and the shell/table/chip/tile/bar layer both data pages
  share. `docs/scrims.html` and `docs/capture/*.html` link it directly;
  `docs/index.html` cannot (it must stay self-contained), so
  `faceit_sync/_dashboard.py` inlines the canonical copy at
  `faceit_sync/dashboard/theme.css` with fonts base64-embedded. Edit the shared
  set there and never re-add a per-page copy — that duplication is what caused
  the pre-redesign inconsistency, and it caused the 2026-08-20 drift too. Only
  genuinely page-specific components stay per-page; they re-theme automatically
  from these tokens. See the design-system gotcha above for what a test enforces.
- **The dead native GUI was removed on 2026-08-08** (`owdb/gui.py`,
  `owdb_app.py`, the PyInstaller specs, `Scout app.cmd`). Do not resurrect it.
- **`docs/scrims.html` is the single scrims viewer.** The two implementations
  were consolidated on 2026-08-08.
- **Feature work gets a design document then a plan**, both under `specs/`, named
  `YYYY-MM-DD-<topic>-design.md` and `-plan.md`.
- **Update `CHANGELOG.md`** when a change is visible on owdb.io, changes a data
  contract, or changes an operational procedure.

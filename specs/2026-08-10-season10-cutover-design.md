# Season 10 cutover — design

**Date:** 2026-08-10
**Status:** all code shipped; what remains is blocked on S10 seeds.
See **§6 — Status at the end of Season 9 (2026-08-27)** before acting on
anything below. §6.4 group A is complete as of 2026-08-27 (frozen archive,
SA/OCE regions, the season fallback and label, and two decisions closed);
groups B and C wait on S10 rooms and S10 results respectively.

## Goal

Define how the site, the ingest DB, and captures behave when FACEIT League
moves from Season 9 to Season 10 — without disrupting Season 9 while it's
still live, and without losing Season 9's data once it isn't.

The site stays on **GitHub Pages** — nothing about a season transition
requires new hosting; the DB, the Cloudflare Worker, and the capture app are
all already decoupled from where the static site is served.

## Background: what's already there

- **No season concept exists in the schema today.** Championships are keyed
  by FACEIT id only. The dashboard already tolerates divisions "coming and
  going" between seasons gracefully (a stored view preference is validated
  against current views and falls back rather than breaking — `FEATURES.md`
  lines 100-106), but nothing currently *scopes* the live export to one
  season — it ships every championship the DB holds.
- **Region and tier are already parsed from the championship name**
  (`_region_of` / `_tier_of` in `faceit_sync/export.py`), matched as whole
  words. Checking the live DB confirms FACEIT's own `championships.name`
  already carries the season too, e.g. `"S9 EMEA Advanced Central - Regular
  Season"`. Season is parseable with the exact same technique — no new
  tagging system needed, and no reason to touch the DB schema.
- **Code wipes are an existing, recurring mechanism** (`owdb/db.py`
  `_SEED_WIPES` / `LATEST_KNOWN_WIPE`, mirrored in `tools/build_capture_data.py`
  `CODE_WIPE_DATE`). A season boundary is, in practice, one more wipe entry —
  not new machinery. Once S10's wipe date is registered, the capture tool
  automatically stops offering S9 codes; no separate season filter needed
  there.
- **Contributions are NOT written by CI.** The browser capture app uploads
  go straight from the Cloudflare Worker to a committed file
  (`infra/upload-worker/worker.js:198`,
  `` const path = `data/captures/${claimKey}.json` ``) via the GitHub
  contents API. Any season-scoping of captures has to change the Worker,
  not just `owdb/contribute.py` (whose merge logic already just globs
  `*.json` in whatever `--dir` it's given — `contribution_files`,
  `owdb/contribute.py:970`).
- **Private scrims are out of scope.** `docs/scrims.html` reads only
  browser-local IndexedDB (`owscout-capture`), never committed, never
  merged into `data/captures/`. Nothing here touches it.

## Scope decisions

| Decision | Choice | Why |
|---|---|---|
| Hosting | Stay on GitHub Pages | No concrete driver for moving; a season transition doesn't touch hosting at all. |
| S9 data retention | Keep forever in the working `faceit.sqlite3`; never deleted | Rosters/comps go stale across a season, but the *raw match/stat data* stays cheap and valuable (all-time stats, cross-season elo) — SQLite handles it fine at this scale. Only the **export** is season-scoped, not the data. |
| S9 live-site visibility | Stays the sole live season (`docs/index.html`) until every S9 game finishes — no commingling with S10 divisions that start trickling into the DB during the overlap period | Explicit user requirement: rosters/teams change constantly between seasons, so a commingled or look-back selector is "kinda pointless" day-to-day. Cutover to S10-only is a deliberate, explicit action, not an auto-detected one, because playoffs of one season and the start of the next can overlap in the DB. |
| Archive shape | One frozen static export per past season, at its own path (`docs/s9/index.html`, ...), linked from a small static `docs/archive.html` index; never regenerated after creation | Cheapest correct option — a true point-in-time snapshot, no new season-switcher UI/JS logic in the live dashboard app. |
| Captures | Season-scoped directories: `data/captures/s9/`, `data/captures/s10/`, ... | A team's S9 comp must never silently feed S10 scouting — rosters and metas both change. Existing flat files get `git mv`'d into `data/captures/s9/` at cutover for a uniform scheme (no flat-file special case going forward). |
| Cutover mechanism | Manual, documented runbook (this document; §6.4 is the current sequence), not an automated script | Quarterly cadence, and this is the *first* cutover ever run — automating an unrehearsed process guesses at the wrong abstraction. Revisit as a script only if manual execution proves error-prone after being run for real. |
| Coverage at cutover (added 2026-08-20) | Expand to EMEA + NA **Master/Expert/Advanced**, plus **SA Master** and **OCE Master** | The season boundary is the only free moment to change coverage: `matches.txt` is being rewritten anyway (runbook step 3), and seeding a division mid-season means back-crawling a live schedule. Operator's chosen scope. |
| Open and Intermediate | **Not ingested** | Open is 129 teams in EMEA alone and the lowest scouting value in the league; S10's new Intermediate sits between Advanced and Open and inherits that. Excluding both is what keeps the page under 12 MB — see the sizing section. |

## Changes

### 1. Season filtering (`faceit_sync/export.py`)

- Add `_season_of(name: str | None) -> str | None`, parsing the leading
  `S\d+` token from a championship name with the same word-boundary
  discipline as `_region_of`/`_tier_of` (must not let `S9` false-match
  inside `S90`, etc.).
- Add a `--season` flag to `faceit-sync export`, parity with the existing
  `--region`, narrowing the championship set before views are built.
- CI's live export in `.github/workflows/update.yml` passes an explicit
  `--season s10` once the cutover happens (not auto-latest-detected — see
  scope decision above).

### 2. Frozen archive

One-time, by hand, once S9 is fully finished — which it now is. **Build it from
CI's DB, not the local one: see the correction in §6.4 step 1.**

1. `owdb contribute merge --dir data/captures/s9 --out owdb_comps_s9.json`
2. `faceit-sync export --season s9 --format html --out docs/s9/index.html`
3. Commit both. `docs/s9/**` is outside `update.yml`'s regeneration path, so
   it stays byte-frozen even as the live DB keeps accumulating S10+ data.
4. Add a `Season 9 →` line to a small static `docs/archive.html`. Add a
   permanent "Past seasons" link from `docs/index.html`'s shell to it (exact
   placement — footer vs. near the region selector — is an implementation
   detail, not a design decision).

### 3. Captures season-scoping

- `infra/upload-worker/worker.js`: add a `CURRENT_SEASON` constant near the
  top (same shape as the project's existing per-patch constants), change the
  write path to `` `data/captures/${CURRENT_SEASON}/${claimKey}.json` ``.
  Requires a `wrangler deploy` at cutover (run by the human, per existing
  convention — this repo never runs `wrangler deploy` from CI).
- `.github/workflows/update.yml`: the `owdb contribute merge --dir
  data/captures` step becomes `--dir data/captures/s10`.
- `owdb/contribute.py`: no code change — `contribution_files` already globs
  `*.json` in whatever directory it's handed.

### 4. The cutover runbook (superseded — see §6.4)

> Kept for the rationale behind each step. The order below assumed the cutover
> fires when S9's last match finishes; §6.3 shows why the real trigger is S10
> having data, and §6.4 regroups these steps by what gates them.

1. Register the S10 code-wipe date (existing procedure: `owdb/db.py`
   `_SEED_WIPES` + `tools/build_capture_data.py` `CODE_WIPE_DATE`, plus the
   pinned wipe-date test assertions).
2. `git mv data/captures/*.json data/captures/s9/`.
3. Add S10 championship IDs to `matches.txt`; comment out the S9 blocks
   (existing convention — see the `HELD` comment style already in the file).
   This is where coverage changes — see Section 5. Seed **NA Advanced,
   SA Master and OCE Master** alongside the existing divisions, one room URL
   each. Do NOT seed Open or Intermediate.
3a. Verify the region code change from Section 5 is already merged (it is
   inert until these seeds land, so it should have shipped well before now).
   After the first crawl, confirm SA and OCE appear in the region switcher and
   that neither gets a spurious "Combined" view.
4. Build the frozen archive (Section 2 above).
5. Update `update.yml`: live export gets `--season s10`; merge step's `--dir`
   becomes `data/captures/s10`.
6. Update `worker.js`'s `CURRENT_SEASON` constant; `wrangler deploy`.


### 5. Coverage expansion (added 2026-08-20)

The cutover is when coverage changes, because it is the only moment when it is
cheap. `matches.txt` is already being rewritten at step 3, and seeding a
division mid-season means back-crawling a schedule that is still moving.

**Target scope:** EMEA Master/Expert/Advanced, NA Master/Expert/Advanced,
SA Master, OCE Master.

**Only three divisions are actually missing** — EMEA M/E/A and NA M/E are
already ingested:

| division | regular | playoffs | matches | games | basis |
|---|---|---|---|---|---|
| NA Advanced | 342 | 62 | 404 | 1,454 | ~46 teams — the one real estimate here |
| SA Master | 66 | 10 | 76 | 274 | 12 teams, exact: round robin is n(n-1)/2 |
| OCE Master | 28 | 6 | 34 | 122 | 8 teams, exact |
| | | | **514** | **1,850** | |

Measured against S9: 1,404 → 1,918 matches, 5,054 → 6,904 games, 167 → ~233
teams. **1.37x**, and `docs/index.html` goes 8.7 MB → **11.9 MB**. That is
comfortable; `--external-data` page splitting stays unnecessary. It would not
be if Open were included, which is the main reason it is not.

**Sizing formulas, validated against the live DB** — use these rather than
re-estimating:

- **Master is a single round robin**: `n(n-1)/2` matches, exact. 16 teams
  predicts 120, and both EMEA and NA Master measure exactly 120.
- **Every other tier is Swiss**, but the format label does not predict cost:
  Expert and Advanced both measure **7.43 matches per team**, the same as
  round-robin Master. Rounds played drives it, not format.
- **Open is the exception at 3.16 matches/team** (measured, EMEA Open: 110
  teams / 348 matches), and only ~85% of registered teams play at all.
- **3.6 games per match**, stable everywhere. **~1.76 KB of `index.html` per
  game** — the page is almost entirely inlined match data.

**Region support is a code change, and it should land BEFORE cutover day.**
Adding SA and OCE touches four places: the `REGIONS` tuple
(`faceit_sync/export.py`), the `--region` choices (`faceit_sync/cli.py`), the
`want_region` prefix test in `export.py` (currently `startswith("e")` /
`startswith("n")`, which needs generalizing rather than extending), and the
docstring listing valid regions. `_region_of` already matches whole words, so
`"S10 SA Master Central"` classifies with no change, and the view builder is
already generic over `REGIONS x TIERS`. The "Combined" view correctly does not
appear for a region with a single division.

Landing this early is deliberate: the change is **inert until a SA or OCE
championship exists in the DB**, so it can be written, tested and merged
without waiting, which takes it off the cutover-day critical path.

**The blocker is seeds, not code.** Each new division needs one FACEIT match
room URL to bootstrap the keyless crawler. Those must be collected by the
operator once S10 rooms exist; nothing can be seeded before then.

**Expect Advanced to shrink.** Intermediate sits between Advanced and Open, so
it will siphon teams out of the bottom of Advanced. The same scope will capture
fewer teams in S10 than it would have in S9 — treat the NA Advanced estimate
above as an upper bound.

## Testing

- Unit test `_season_of()` against real championship names (parity with the
  existing `_region_of`/`_tier_of` tests), including the word-boundary edge
  case (`S9` must not match `S90`/`S19`, etc.).
- `tests/test_export.py::test_dashboard_javascript_is_syntactically_valid`
  is unaffected in scope (this change lives in `export.py`/CLI, not a
  `faceit_sync/dashboard/` part file) but stays part of the standard gate
  for any future change that does touch a part file.
- The runbook itself isn't unit-testable, but step 4 (the archive export) is
  cheap to rehearse against a local `faceit.sqlite3` copy before ever
  touching the real CI-cached DB or the live Worker.

## Explicitly out of scope

- Any change to hosting (staying on GitHub Pages).
- Deleting or migrating rows out of `faceit.sqlite3`.
- A season switcher/dropdown inside the live dashboard app (`app.js`).
- Any change to `docs/scrims.html` or the browser-local scrim IndexedDB.
- Automating the cutover into a script (deferred until after it's been run
  by hand at least once).

---

## 6. Status at the end of Season 9 (added 2026-08-27)

S9 finished on **2026-08-17** (last ingested match: NA Expert Playoffs,
`2026-08-17T02:23:34Z`), and the operator reports relegation has since been
played. This section records what of the design above is actually live, what the
ten days since have changed, and the order the rest should happen in. It
supersedes the earlier sections where they disagree.

### 6.1 What is already shipped

Verified against the working tree, the CI-published DB (`docs/faceit.sqlite3.gz`)
and the commit history on 2026-08-27:

| Section | State |
|---|---|
| §1 season filtering | **Live.** `_season_of` + `--season` exist, with word-boundary tests in `tests/test_export.py`. CI pins the live export to `--season s9`, not `s10` — deliberately, see §6.3. |
| §2 frozen archive | **Shipped 2026-08-27.** `docs/s9/index.html` (5 divisions, 274 captured comps) and `docs/archive.html`, linked from every page footer. Built from CI's DB, per the correction in §6.4. |
| §3 capture season-scoping | **Live and deployed.** `CURRENT_SEASON = "s9"` in `worker.js`; the merge step reads `data/captures/s9`; the `git mv` happened in `705aa77`; contributions since (`2caffc1`) land under `data/captures/s9/`, which is the proof the Worker was actually deployed. |
| §4 runbook | **Moved.** It is this document, not `CLAUDE.md` — the 2026-08-11 documentation refactor emptied `CLAUDE.md`, and `AGENTS.md` now points here. Resequenced in §6.4. |
| §5 coverage expansion (SA/OCE regions) | **Code shipped 2026-08-27**, seeds outstanding. `REGIONS` is `("EMEA", "NA", "SA", "OCE")`, `--region` matches region names exactly instead of by first letter, and `tools/build_capture_data.py`'s separate copy is pinned to the exporter's by a test. Inert until a SA/OCE championship exists, so what remains is seeds (group B), not code. |
| §6.3 day-one flip | **Shipped 2026-08-27.** A pinned season with no data falls back to the newest season that has some, so the export pin can be flipped at any time. The page now labels the season it actually rendered, so a fallback is visible rather than silent. |

### 6.2 The site is in an off-season trough, and it degrades correctly

Worth knowing before anyone reads the live site as broken:

- **There is not one live replay code in the league.** Every S9 game finished on
  or before 2026-08-17; `LATEST_KNOWN_WIPE` is 2026-08-18. The CI-built
  `docs/capture/data.json` says so exactly — `codes: 0`, `divisions: []`, built
  `2026-08-24T00:45:32Z`. The capture app's league side has nothing to offer
  until S10 games are played, and no work can change that: a code nobody
  captured before the wipe is gone permanently.
- **The dashboard handles it.** `coverageState()` returns the `wiped` state and
  the page reads "Nothing left to scout — all N replay codes were wiped on
  2026-08-18"; Most wanted and the capture funnel withhold themselves rather than
  render empty. No fix needed. What is *not* said anywhere is that the season is
  over — a visitor sees a full site with a dead capture funnel and no
  explanation. A one-line season-state note is the cheapest item on this list.
- **CI is healthy.** Daily scheduled runs succeeded through 2026-08-27; the quiet
  commit log since 2026-08-24 is no-change runs, not a broken pipeline.

### 6.3 The cutover trigger is S10 data, not the end of S9

The original design says the cutover happens "once S9's last match finishes".
That is now demonstrably the wrong trigger. S9 finished ten days ago and no S10
championship exists in the DB, so flipping the live export to `--season s10`
today would publish an **empty site**: no standings, no power rankings, no player
pages, no meta.

**Decision:** the live export stays `--season s9` until S10 has enough played
matches to be worth showing, and the *archive* is what makes S9 permanent in the
meantime. The trigger for the export flip is "S10 divisions have real results in
the DB", not "S9 ended". The two events are weeks apart and only the second is a
cutover.

This does not weaken the no-commingling rule: `--season s9` keeps S10 rows out of
the live site automatically as they start arriving, which is exactly the overlap
case the flag was built for.

### 6.4 Resequenced runbook

Replaces §4's single ordered list. Same steps, grouped by what actually gates
them.

**A. Unblocked today — ALL DONE 2026-08-27.** Kept for the reasoning; the plan
that executed them is `specs/2026-08-27-season10-readiness-plan.md`.

1. ~~**Build the frozen S9 archive**~~ (§2) — **done.** `docs/s9/index.html`
   (5 divisions) and `docs/archive.html`, linked from every page footer.
   **The correction that mattered:** it must NOT be built from the local
   `faceit.sqlite3` — that copy is routinely days behind and invariant 2 forbids
   exporting from it. The recipe, for the next season:
   `gunzip -c docs/faceit.sqlite3.gz > s9.sqlite3`, merge
   `owdb contribute merge --dir data/captures/s9 --out owdb_comps.json` against
   it, then `faceit-sync --db s9.sqlite3 export --season s9 --format html --out
   docs/s9/index.html`. Commit `docs/s9/**`; never `owdb_comps.json`
   (invariant 6). Both page-glob test suites exclude `s<n>/index.html` for the
   same reason they exclude `docs/index.html`.
2. ~~**Land the SA/OCE region change**~~ (§5) — **done**, including
   `tools/build_capture_data.py`'s own `REGIONS` copy, now pinned to the
   exporter's by a test. `--region` also stopped matching on a first-letter
   prefix, which with four regions was one addition away from silently resolving
   the wrong one.
3. ~~**Decide the IndexedDB rename**~~ — **closed as won't-do.** The name is
   invisible to users and renaming orphans every contributor's learned refs,
   unsent captures and scrim history. `AGENTS.md` now records a decision rather
   than a deadline; do not re-open it at a season boundary.
4. ~~**Answer the relegation question**~~ (§6.5) — **decided: skip entirely.**
   Operator's call. S9 standings stay the record and S10 division membership
   becomes visible once S10 is crawled. Note for the record that the window has
   since closed either way: 0 of the 4,456 coded S9 games finished after the
   2026-08-18 wipe, so nothing in S9 is replayable any more.

Added by the same pass, not in the original plan: **the day-one flip guard**
(§6.3). The operator's decision was to flip the site to S10 on day one, and
testing that against CI's DB showed it wrote a 0-byte file and exited 1, failing
the whole CI job under `bash -e`. The pin now falls back to the newest season
with data, and the page labels the season it actually rendered.

Added by a later pass (2026-08-31), also not in the original plan: **the map
pool.** S10 is the first season FACEIT restricts one — 14 of the game's 30 maps
— which the cutover had not anticipated at all, because through S9 the league
pool and the game pool were the same list. Done in the same pass:
`POOL` in `docs/scrims.html` is now the S10 pool, so practice coverage measures
you against maps you can actually be drawn on; `SCRIM_MAPS` in
`docs/capture/scrim.html` stays every playable map and gained **Aatlis** and
**Neon Junction**, which had never been added at all. See `AGENTS.md` for why
the two lists differ. **`POOL` is now per-season maintenance** — refresh it from
the season announcement at every future cutover, alongside the code-wipe date.

The same announcement carries three things this design predates and does not
model: a new **Intermediate** division (capped 128, EMEA/NA), **new caps on the
tiers already in scope** (Expert 32, down from 41 EMEA / 49 NA; Advanced 48, up
from ~45 — net a shrink, so §5's coverage estimate is now high rather than low),
and a **Season Finals**
bracket per region on 9–15 November. S10 also has **no OWCS connection** — no
promotion or relegation to OWCS at the end of the season — so the cross-league
relegation championship that §6.5 is chasing has no S10 equivalent. That does
not close §6.5: its subject is the *S9* relegation matches, whose codes are
still the only live ones in the league. FACEIT-internal move-ups continue, and
apply 2026-11-17.

Added by a further pass (2026-09-01), when FACEIT published the season calendar
and the S10 rulebook changelog. **Group B's gate now has a date: 2026-09-03
15:30**, when the brackets are generated and the S10 match rooms first exist —
four days before the 7 September season start this design assumed. Round 1 only
is generated then, round 2 the following day, and FACEIT posts a separate notice
once every division is done, so an absent division on the day is normal. The
unpaid-team clear at 15:00 the same day removes ineligible teams irreversibly:
seeds collected before it are provisional. The rest of the calendar
(registration close 2026-09-02 18:00, roster lock 2026-10-12, Season Finals
2026-11-09 23:00 UTC → 2026-11-15 22:55 UTC with rounds on 11/12/13 November and
the final on the 15th) is tabulated in `AGENTS.md` § Season state; this design
does not restate it.

Three consequences for the model in this document:

1. **Intermediate's team count is published on 3 September**, by the bracket —
   so §6's "decide in week 1" can be decided at the gate instead. `TIERS` in
   `faceit_sync/export.py` still has no `Intermediate` entry, so even a seeded
   Intermediate division would fall out of the region switcher into the
   unclassified-name fallback. That entry is the prerequisite, and it is inert
   until such a championship exists.
2. **A "Season Finals" championship has no shape in this design.** It is not
   matched by `is_playoff_name` (`playoff`/`knockout` only), so it would export
   as a standalone division with its own standings; and because it is
   cross-tier by construction — top 4 of Master plus top 2 of each of Expert,
   Advanced, Intermediate and Open — it has no single region+tier division for
   the playoff-attachment step in §6 to hang it on. Widening the matcher is not
   sufficient. Nothing exists to crawl before November, so this is a design
   question with two months of slack, not a cutover blocker.
3. **S9 standings do not determine S10 division membership.** The Open
   Qualifiers (20–23 August 2026) placed teams straight into Expert and
   Advanced. §6's decision to skip the relegation ingest stands — S9 standings
   remain the S9 record — but they cannot be used to *predict* the S10 division
   lists. The crawl is the only source.

Two rule changes with no code consequence, recorded so nobody re-derives them:
in-season roster additions are capped at two slots with a 7-day cooldown across
all divisions (which bounds `team_rosters` drift until the 12 October lock), and
pause-on-disconnect is gone in favour of one manual tech pause per team per map
(which shifts disconnects from restarts toward played-through games, making
`dc_games` and `was_restarted` non-comparable across the S9→S10 boundary).

**B. Gated on S10 rooms existing (operator collects seeds).**

5. Add S10 championship IDs to `matches.txt`, comment out the S9 blocks, and seed
   NA Advanced, SA Master and OCE Master — one room URL each. There is no way to
   automate this discovery: FACEIT's keyless `championships/v1/championships`
   refuses offset enumeration (`"Only s2s calls are allowed to get championships
   by offset"`, verified 2026-08-27), so the seed URLs are collected by hand — or
   by adding a `FACEIT_API_KEY`-backed `organizers/{id}/championships` lookup,
   the only path that removes the manual step. The FACEIT League organizer id is
   `f0e8a591-08fd-4619-9d59-d97f0571842e`.
6. Register the S10 code-wipe date when the season-start patch lands (existing
   procedure — `_SEED_WIPES` only).

**C. Gated on S10 having real results.**

7. `update.yml`: live export becomes `--season s10`; merge `--dir` becomes
   `data/captures/s10`.
8. `worker.js`: `CURRENT_SEASON = "s10"`, then the human runs `wrangler deploy`.
   Treat 7 and 8 as one change — a Worker writing to `s10/` while CI still merges
   `s9/` silently drops every contribution.
9. After the first crawl, confirm SA and OCE appear in the region switcher and
   that neither gets a spurious "Combined" view.

**The group C change in full** — three lines, one commit, then a human deploy:

```
.github/workflows/update.yml:136
-  ... contribute merge --dir data/captures/s9 --out owdb_comps.json ...
+  ... contribute merge --dir data/captures/s10 --out owdb_comps.json ...

.github/workflows/update.yml:149
-  faceit-sync --db faceit.sqlite3 export --season s9 ... --out docs/index.html
+  faceit-sync --db faceit.sqlite3 export --season s10 ... --out docs/index.html

infra/upload-worker/worker.js:35
-  const CURRENT_SEASON = "s9";
+  const CURRENT_SEASON = "s10";
```

Then `wrangler deploy`, by the human.

**Only the export line is protected by the fallback** (shipped 2026-08-27): a
pinned season with no data falls back to the newest season that has some, so
flipping that line alone is safe at any time and the site switches itself over
on the first ingested S10 match. The merge line is *not* protected and must not
move early — teams persist across seasons by FACEIT team id, so merging
`data/captures/s9` while the site renders S10 attaches every team's Season 9
comps to their Season 10 page, which is the exact hazard season-scoped captures
exist to prevent. Move the merge line and `CURRENT_SEASON` together, when the
site is actually showing S10.

### 6.5 Relegation matches are not ingested, and their codes are alive

**New gap, found 2026-08-27.** The keyless crawler enumerates
`iter_team_championship_matches(championship_id, team_id)` — it is scoped to a
championship it was already handed. A relegation/promotion championship is a
*separate* FACEIT championship, so nothing in the current seed set can reach it,
and none is in the DB: the ten ingested S9 championships are six regular seasons
and four playoff brackets, with no match later than 2026-08-17.

This matters more than an ordinary gap, for two reasons:

- **Those codes are the only live replay codes in the league.** The last wipe is
  2026-08-18. A relegation game played after that date is still replayable right
  now and stops being so at the next Overwatch patch. Everything else is already
  lost.
- **Relegation determines S10 division membership** — which teams a scout will
  even find in each S10 division. Without it, the site's S9 standings imply a
  league structure that no longer holds.

Action: the operator supplies one match-room URL per relegation championship,
exactly like any other seed. If FACEIT ran relegation inside the existing playoff
brackets rather than as its own championship, this closes as a non-issue — and
that check is one look at a relegated team's FACEIT match history.

### 6.6 Open questions this design does not settle

- **`team_rosters` in the capture feed has no season filter.** **Settled
  2026-08-27 — scoped to the active season.** The pool is now the newest season
  with data, sharing `newest_season` with the exporter. The deciding argument was
  not collision arithmetic: you only scrim teams that are active, so a match
  against last season's squad writes a team that no longer plays into a private
  scrim log. Inert until cutover (S9 is the only season, and the built feed was
  diffed to confirm it), and it flips itself on the first ingested S10 match.
  `tools/roster_match_eval.py` applies the same filter — re-run it in week 1 of
  S10, when the pool is only the teams that have already played.
- **Player pages are season-scoped by construction.** They aggregate every
  division in the payload, so at cutover every player's page restarts from
  nothing and their S9 history survives only inside the frozen archive, under a
  different URL. A player's career is the one read where crossing the season
  boundary has obvious value; whether to give it a cross-season data source is a
  product decision, not a cutover step, and is deliberately not answered here.
- **Advanced will shrink** — S10's new Intermediate tier siphons teams from the
  bottom of Advanced, so §5's NA Advanced estimate (404 matches) is an upper
  bound.
- **Should the off-season open scrim mode?** Both scrim pages ship locked behind
  `?unlock=scrimbeta`. The league is dark for weeks and teams still scrim, which
  makes this the only window where scrim mode is the *only* thing the tool can
  do. Opening it is a decision rather than a cleanup task (`AGENTS.md`
  priority 2) — but this is the moment it is worth the most.

---

## 7. Group C, executed differently (2026-09-05)

The operator reported Season 10 match rooms exist. Group B is still seeds, which
nothing can automate — a fresh probe on 2026-09-05 re-confirmed the keyless
championship listing refuses enumeration (`err_f0` "not authorized"; the
organizer-filtered form 401s too; `open.faceit.com/data/v4/championships` is
403 without a key). Group C, though, shipped — with one change to its shape.

**What §6.4 group C said:** flip `update.yml`'s `--season` to `s10`, flip the
merge `--dir` to `data/captures/s10`, flip `CURRENT_SEASON`, deploy. Treat 7 and
8 as one change or contributions are dropped silently.

**Why that is worse than it looks.** The export flip is protected by the season
fallback, but the merge dir is not: pointing it at an empty `s10/` while the
export still falls back to S9 publishes the S9 site **with none of its 274
captured comps** — the site's whole differentiator — for as long as the seeds
take to arrive. And the pairing rule ("treat 7 and 8 as one change") is a rule a
human has to remember at a boundary that happens once a quarter.

**What shipped instead.** The season is *resolved*, not pinned twice:

- `models.resolve_season(names, pin)` — the pin when it has data, else the newest
  season that does. The exporter's existing fallback now calls it, so there is
  one definition rather than two that agree by inspection.
- `faceit-sync resolve-season --season s10` prints that answer, one line.
- `update.yml` calls it once and uses the result for the export **and** the
  captures directory it merges.

So the merge directory follows the published season automatically: S9 today with
its comps intact, S10 — page and comps together — on the first ingested S10
match. A test asserts the agreement itself in both states of a boundary, because
a disagreement is exactly the commingling the pin exists to prevent.

`CURRENT_SEASON` and `CONTRIB_DIR` still moved to `s10` in the same pass, and
still need `wrangler deploy` (invariant 11). The window that used to be dangerous
is not: no replay code in the league is live, so no upload can be dropped before
the first S10 playday on 7 September. Deploy before then.

Also landed, ahead of any decision, per group B's own note: **`Intermediate` in
`TIERS`** (both copies, now test-pinned) and the `--tier` choices. The scope
decision to exclude it is unchanged — this only means that seeding one would
classify rather than vanish into the unclassified-name fallback.

**What remains is entirely operator work:** the seed URLs (a marked block at the
foot of `matches.txt` names every division in scope), `wrangler deploy`, and the
S10 code-wipe date once the season-start patch lands. The Season Finals shape
(§6.4 consequence 2) is untouched and still has until November.


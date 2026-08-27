# Season 10 cutover — design

**Date:** 2026-08-10
**Status:** partly shipped; the rest is blocked on S10 seeds.
See **§6 — Status at the end of Season 9 (2026-08-27)** before acting on
anything below: sections 1 and 3 are live, section 4's runbook has moved and
been resequenced, and section 5 has not landed.

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
| §2 frozen archive | **Not started.** No `docs/s9/`, no `docs/archive.html`. Now unblocked — see §6.4. |
| §3 capture season-scoping | **Live and deployed.** `CURRENT_SEASON = "s9"` in `worker.js`; the merge step reads `data/captures/s9`; the `git mv` happened in `705aa77`; contributions since (`2caffc1`) land under `data/captures/s9/`, which is the proof the Worker was actually deployed. |
| §4 runbook | **Moved.** It is this document, not `CLAUDE.md` — the 2026-08-11 documentation refactor emptied `CLAUDE.md`, and `AGENTS.md` now points here. Resequenced in §6.4. |
| §5 coverage expansion (SA/OCE regions) | **Not landed.** `REGIONS` in `faceit_sync/export.py` is still `("EMEA", "NA")`, `--region` still offers only `emea`/`na`, and `want_region` is still the `startswith("e")`/`startswith("n")` pair the section says to generalise. `tools/build_capture_data.py` carries its own `REGIONS` copy that must move with it. This was meant to land early precisely so it would not be on the critical path; it is now the one piece of cutover code still outstanding, and it is still inert until a SA/OCE championship exists. |

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

**A. Unblocked today — nothing here waits on S10.**

1. **Build the frozen S9 archive** (§2). S9 is final, so this can be done now and
   never needs redoing. **Correction to §2:** do not build it from the local
   `faceit.sqlite3` — that copy is routinely days behind and invariant 2 forbids
   exporting from it. Build from CI's copy instead:
   `gunzip -c docs/faceit.sqlite3.gz > s9.sqlite3`, merge
   `owdb contribute merge --dir data/captures/s9 --out owdb_comps_s9.json`
   against it, then `faceit-sync --db s9.sqlite3 export --season s9 --format html
   --out docs/s9/index.html`. Commit `docs/s9/**` and `docs/archive.html`; never
   `owdb_comps_s9.json` (invariant 6).
2. **Land the SA/OCE region change** (§5). Inert until a SA/OCE championship
   exists, so it carries no risk to the live S9 site, and it is the one thing
   that would otherwise be written under time pressure on cutover day. Remember
   `tools/build_capture_data.py`'s own `REGIONS` copy.
3. **Decide the IndexedDB rename.** `owscout-capture` was kept "until the Season
   10 cutover" (Conventions, `AGENTS.md`) because renaming orphans every
   contributor's local data. That reasoning has not changed with the season — the
   name is invisible to users, and a rename buys tidiness at the cost of every
   scout's learned refs and unsent captures. The recommendation is to **close it
   as won't-do** and delete the deadline from `AGENTS.md`, rather than let a dated
   promise trigger a data-losing rename.
4. **Answer the relegation question** — time-critical, see §6.5.

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

- **`team_rosters` in the capture feed has no season filter.**
  `tools/build_capture_data.py` builds it from every `round_players` row in the
  DB, so after cutover it carries S9 *and* S10 rosters, including teams that have
  disbanded. Scrim opponent identification matches ten HUD names against that
  pool, and its measured guarantee — zero collisions at the 3-of-5 bar across
  8,356 lineups (`tools/roster_match_eval.py`) — was measured on one season's
  pool. Either scope it to the live season or re-measure before the pool doubles.
  Do not assume the number holds.
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

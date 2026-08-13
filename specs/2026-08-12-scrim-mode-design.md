# Scrim mode — design

**Date:** 2026-08-12
**Status:** approved, not implemented
**Roadmap:** priority 2, "Ship scrim mode" (`AGENTS.md`)
**Supersedes:** the paused implementation described in `ARCHITECTURE.md` §7

---

## 0. Why this replan

Scrim capture has been switched off in production since commit `f2881cf` — the
page renders an unconditional `#scrimpaused` overlay that no script removes. The
machinery behind it was built as a copy of the league capture flow, which is the
wrong shape: scrims are not league matches with the publish step removed.

Scrims differ in ways the current design does not model:

- **The opponent is often unknown.** Scrim partners come from other divisions,
  other regions, other tournaments, and sometimes are a "mix" of five unaffiliated
  players. There may be no team name to type.
- **The structure is free.** Any map order, any map pool, restarts, and replaying
  a single attack or defence are all normal. The point is practice, not winning.
- **The maps themselves are modified.** Scrim workshop codes let both teams play
  out every point — all three on Control, all five on Flashpoint, a guaranteed
  full attack on Hybrid and Escort.

This document replans scrim mode around how scrims actually work, and defines the
work needed to make it usable.

## 1. Decisions

| # | Decision | Rationale |
| --- | --- | --- |
| 1 | Extract a shared capture engine; keep two pages | The alternative — merging both capture pages behind a mode toggle — rewrites a tool in daily use in one un-verifiable cutover. Extraction lands one subsystem per commit, each green. |
| 2 | Capture surface is the observer HUD | Live spectating and replay watching render the identical HUD, so there is one capture path, not two. |
| 3 | Support Scrimtime **and** the OWDB code, unmodified | Scrimtime is the industry standard and teams will not switch. The OWDB code is a strict derivative, so the Standard scoreboard layout is shared and one reader serves both. |
| 4 | A captured unit is always a **full map** | Partial play is recorded as a full map with explicit "no attack data for this team" marking, rather than a separate segment type. |
| 5 | Reactive flow first, auto-detection later | Auto-detection is the better UX but the worse first build. Reactive is both the foundation and the permanent fallback. |
| 6 | Unmatched opponents are remembered locally | A recurring practice partner accumulates a profile even with no league identity. |
| 7 | Stats join on **hero**, not name or slot | The portrait bar and the scoreboard are in the same frame; hero is unique within a team. |
| 8 | Sharing is an unlisted link, with a warning | Chosen over login-gated and recipient-locked for frictionless sending, accepting that the link is the only secret. |

## 2. What the workshop codes actually render

Read from `tools/scrim_code/scrim_owdb.opy` and its Scrimtime origin
`tools/scrim_code/dkeeh.opy`. Both render the same two things, so no workshop
code change is required.

**The spectator scoreboard** (`SpecVisibility.ALWAYS`, so it renders for
spectators and in replays) is one row per player:

```
heroIcon • K • D • DamageDealt • DamageTaken • (Blocked|Healing|Accuracy%) • Ults
```

- **There are no player names on it.** Opponent identification cannot come from
  here.
- The sixth column depends on the player's role: Damage Blocked for tanks,
  Healing Dealt for supports, Accuracy-with-a-`%` for DPS.
- Row order depends on a lobby setting with three grouping styles. **This does
  not matter** — see §5.
- Above the rows sit three **legend rows** of constant text
  (`K • D • DD • DT • ACC • UU` beside a Genji / Reinhardt / Baptiste icon), and
  below them a **Match Time** row.

**The setup-phase ready-up list** (`scrim_owdb.opy:216`, `dkeeh.opy:367`) renders
`● PlayerName` for all ten players, split by team, in slot order, also
`SpecVisibility.ALWAYS`. This is workshop-drawn text rather than game font over
terrain, and it hands over all ten names before the map starts. It is the primary
source for opponent identification.

## 3. Fixed properties of a scrim

Confirmed with the operator, and relied upon throughout:

- **Hero limit is always enforced.** A hero is a unique key within a team.
- **Role limit is always 1-2-2.** Every team fields exactly one tank, two DPS and
  two supports.
- **The format is 5v5.** If 6v6 ever becomes a scrim format, the shape check in
  §5 is the single place that changes.

## 4. Starting a session, and who you are playing

### 4.1 Session scaffold from the replay-history screenshot

A session is created by dropping or pasting a screenshot of the Overwatch replay
history. `parseScrimSessionText()` already extracts map name, replay code, result
and score from that screen, including realistic OCR noise; seven tests in
`tests/test_capture_scrim.py` cover it. Its `WIP` badge reflects distrust of OCR,
not missing logic.

The screenshot is the **session manifest** — the scrim equivalent of the FACEIT
match data the league flow gets for free. It does not replace capture; it
scaffolds the maps that will then be captured from their replays.

Three additions to the existing parser flow:

1. **League-code block.** Every parsed code is checked against the codes in
   `docs/capture/data.json`. A match is refused as a scrim and offered to League
   scout instead. This is the guarantee the page's help text already advertises
   and the code does not implement — `ARCHITECTURE.md` §7 records it as a gotcha,
   and it must exist before scrims are un-paused, or a league map recorded as a
   scrim would silently stay private instead of being published.
2. **Wipe-date check.** Replay codes are invalidated by every Overwatch patch.
   `data.json` already ships `code_wipe_date`. A scaffolded session shows how long
   its codes remain valid and greys out codes already dead, so nobody scaffolds a
   session and finds it uncapturable a week later.
3. **Manual add**, always available, offering **every** map — scrims are not
   restricted to any league map pool.

### 4.2 Opponent identification

Resolved once per session, from the ten names in the ready-up list. The existing
`readHudNames()` nameplate read remains the fallback for joining mid-map or a
lobby running no workshop code at all.

**The ready-up list renders the actual battletag**, which is the same identity
`game_name` holds in the database — CI already backfills that column. Matching is
therefore **exact-first**: normalise, compare for equality, and fall back to
`simScore` only to repair OCR damage. A 5/5 exact match is effectively certain,
where a 5/5 fuzzy match is merely confident.

Normalisation before comparison: casefold, trim, and drop anything from a `#`
onward. Stored `game_name` values carry no discriminator (`Mappsy`,
`TWERKNATION`), so stripping one if the HUD renders it makes the comparison
correct whichever form appears.

`docs/capture/data.json` already ships rosters as
`{match_id: {team_id: {name, players:[{id, nick, game_name}]}}}`, where
`game_name` is the Battle.net name shown in game. Aggregated across matches, that
is a roster per team — 167 teams, 1343 players at time of writing.

`confidentOrientation()` today scores ten names against **two** known rosters to
decide which side is which. It generalises to a search over **all** teams'
rosters, reusing `simScore()` and `affinity()` and the existing confidence margin.
The existing `test_auto_side_*` tests keep guarding the narrow case.

Resolution order:

| Condition | Outcome |
| --- | --- |
| One side matches our own roster | Sides resolved with no click — this replaces the WIP "Detect sides" button |
| Other side matches a league team on **3 or more** of 5 | Labelled that team, pinned by `team_id` |
| Matches a known local group | That opponent, with "you've played them N times" |
| No match | A new local opponent, saved silently as "Opponent" |

**The bar is three recognised tags, not five, because players routinely show up
to scrims on smurf accounts.** A team fielding two smurfs is still that team, and
demanding five would push the common case back into manual typing — the exact
friction this design exists to remove.

**Measured against real data before building on it** (2026-08-13, 8 356 real
five-player lineups across 159 teams in `faceit.sqlite3`). Note rosters are not
five players — accumulated across a season the median is **8** and the max 12,
and 72 of 1 173 players have appeared for more than one team, so a loose bar had
real scope to collide:

| Bar | Uniquely correct | Ambiguous | Wrong |
| --- | --- | --- | --- |
| 3 of 5 | 99.9% | 0.1% | **0** |
| 4 of 5 | 100% | 0 | **0** |

Applying the tie-break below (highest overlap wins) resolves every one of the
ambiguous cases: **8 356 of 8 356 to the correct team, no ties, none wrong.**

With smurfs substituted in, which is the case the bar exists for:

| Smurfs among the five | Correct | Wrong | Unidentified |
| --- | --- | --- | --- |
| 1 | 100% | 0 | 0 |
| 2 | 100% | 0 | 0 |
| 3 | 0% | **0** | 100% |

Three smurfs leaves only two known names, so falling below the bar is
arithmetic, not a defect — and it fails to "Opponent" rather than to a wrong
team. This is the quantified case for §4.3's alias learning: once a team's alts
are learned they count as known names, so the same lineup identifies next time.

The label is applied without a confirmation dialog, but the session header shows
how many of five matched and offers a one-click "not them", so a low-confidence
identification is visible and cheap to correct rather than blocking.

**Tie-break, which the lower bar makes reachable.** Two teams can now each match
three. Resolution order: highest match count wins; if still level, the existing
`confidentOrientation` margin decides; if that too is inconclusive, no team is
assigned and the side falls through to the local-group path with both candidates
offered as one-click labels.

### 4.3 Learning smurfs

When a side is identified as a league team, the names that did **not** match are
very likely smurf accounts belonging to that team's players. They are recorded as
learned aliases for that `team_id`, so the same alt matches outright next time and
the identification strengthens with use rather than staying permanently marginal.

`buildLearnedRosters()` already exists for this shape of data and is consulted
before the FACEIT rosters in the current side-detection path; this generalises it
from a side-detection aid to the alias store for the opponent registry.

Two safeguards, since this writes identity data automatically:

- Aliases are only learned from an identification the user did not correct.
  Pressing "not them" discards the aliases learned from that read.
- Learned aliases are local to the browser and never uploaded with a shared
  scout, which would otherwise leak the mapping between a player's main and their
  alt accounts.

**Matched league teams are pinned by `team_id`, not by name**, so the label
survives a Battle.net or team rename. Unmatched groups have nothing but names to
key on, so they are keyed by name-set. To tolerate a substitute player or a
single OCR miss, an incoming set of five names is treated as an existing local
group when **at least four** of the five match that group's stored names at
`simScore >= STRONG_NAME_SCORE` — the same threshold the existing side-detection
code uses. Below four, it is a new group; a group matched at exactly four adopts
the incoming name as an additional known member.

Nothing here blocks capture. An unresolved opponent is simply "Opponent", and
naming or re-labelling one later re-applies across every scrim played against
that group, because the opponent is its own record (§7).

## 5. Capturing a map

Capture is **the league flow, unchanged** — snapshot, next round, undo, swap
detection, floating overlay, hero-recognition teaching. That is the point of
extracting the shared engine: there is no second capture implementation to keep
honest.

### 5.1 The stats join

The portrait bar gives **player → hero** (position identifies the player). The
scoreboard row gives **hero → stats**. Both are in the same frame, and hero limit
means hero is unique within a team, so `player → hero → stats` resolves with no
player names and no assumption about row order — and it survives mid-map swaps,
because both regions change together in the same frame.

**The row's hero must be recognised from its icon, and that icon is an image.**
The workshop renders `heroIcon(hero)` as a glyph, not text, so OCR cannot read it
— `docs/capture/scoreboard.js` documents this and discards the token as noise.
`hero_icons.json` does not help: it holds 53 display portraits for the live
preview, while recognition runs off `refs.json`, which holds HUD portrait patches.
Neither is the workshop glyph.

Identifying the row's hero therefore needs **its own reference set of workshop
hero glyphs**. This is tractable rather than research: the glyphs are a fixed,
finite, deterministic set rendered at a known size, the template-matching
machinery already exists for portraits, and the existing "teach it a miss" flow
can bootstrap the set from real scoreboards. It is nonetheless **net-new work,
and phase 3 owns it**.

Until that reference set exists, attribution degrades by role rather than
failing:

| Role | Per-team rows | Attribution without glyph recognition |
| --- | --- | --- |
| Tank | 1 | **Exact** — one row, one player |
| DPS | 2 | Ambiguous within the pair |
| Support | 2 | Ambiguous within the pair |

Two mitigations, in preference order. First, **detect the grouping mode**: under
"Group by team, sort by slot" the rows are already in slot order and join
positionally to the portrait bar with no glyph recognition at all. Second, where
the mode is role-grouped and glyphs are unavailable, store the ambiguous pair's
stats against the **role slot** rather than guessing a player, so the data is
honest about what it knows. Team-level and comp-level analysis is unaffected in
every case; only per-player attribution is.

### 5.2 Read validation by shape

Because the format is fixed at 5v5 / 1-2-2, every valid read has a known shape.
A read is accepted only if:

- there are 5 + 5 rows, split by team;
- the legend rows partition them into exactly two tank, four DPS and four
  support entries;
- the sixth column agrees with that partition — exactly two Damage-Blocked, four
  Accuracy-`%` and four Healing values;
- and the portrait bar independently reads 1-2-2 per team.

Roles here come from the **legend rows**, which are text and already parsed by
`scoreboard.js` — not from the hero glyphs. The shape check therefore works
whether or not glyph recognition (§5.1) exists yet.

Otherwise the read is discarded and retried. Two independent signals covering the
same fact is what makes this useful: if the legend partition says four DPS rows
but only three columns carry a `%`, one row was misread and the disagreeing row
is the suspect. **The same 1-2-2 check applies to the portrait-bar comp read**, so
a bad comp snapshot is rejected rather than stored.

### 5.3 Locating the scoreboard

The three legend rows are constant text at the top of the panel and the Match
Time row anchors the bottom. Finding the legend locates the scoreboard region
automatically, so **"Set SCOREBOARD box" ceases to be a manual calibration
step**. The Match Time row additionally timestamps every snapshot for free.

### 5.4 Finishing a map

On **Finish map** the tool prompts the user to skip to the end of the map (or,
when live-spectating, to wait for the end card) and then confirms a single final
scoreboard read. The final stats therefore come from a frame the user chose, not
a lucky one, and a bad read can be retried in place.

The tool knows which sides were captured on attack. If a team has no attack data,
the map is flagged **partial** at save time rather than storing a half-map as a
whole one. A restarted map is marked **void** from the session list: excluded from
analysis, still visible in the log.

### 5.5 Per-round outcomes

The top-centre score box is sampled per snapshot; a change between rounds
attributes the point to a side. This is what distinguishes "we lost Busan" from
"our dive lost first point, we swapped to poke and took the next two".

It is **optional and degrades cleanly** — uncalibrated or a failed read yields
comps and a final map score with no per-point attribution.

The score box is **not** used for the final map score. The session screenshot
already provides that, more reliably, and two sources for one fact is a bug
waiting to happen.

## 6. Fate of the four WIP features

| Feature | Fate |
| --- | --- |
| Auto side-detection | **Graduates**, generalised — roster search over all teams (§4.2) |
| Scoreboard OCR read | **Graduates** as core, with legend-anchored location and shape validation (§5.2–5.3) |
| Score-box read | **Re-aimed** from final score to per-round outcomes, optional (§5.5) |
| Screenshot session import | **Graduates**, reframed as the session manifest, not a substitute for capture (§4.1) |

## 7. Storage, sync and sharing

### 7.1 Records

Three stores, all owned by the capture app. `docs/scrims.html` remains a
read-only consumer that opens the database **without a version argument** —
`ARCHITECTURE.md` §12 invariant 5.

```
opponent      id · kind(league_team|local_group) · team_id? · label? ·
              roster_names[] · first_seen · times_played

scrim_session id · date · our_team · opponent_id · notes ·
              source(screenshot|manual) · created_at · updated_at

scrim_map     id · session_id · map · category · code · code_wipe_date ·
              score{us,them} · result · void · partial{us_attacked,them_attacked} ·
              rounds[] · snapshots[] · round_outcomes[] · final_stats[] ·
              names_read[] · created_at · updated_at
```

Every record carries a **stable id and `updated_at`**. That is what makes sync a
merge rather than a gamble, and making `opponent` its own record is what lets one
rename re-apply to every past scrim.

### 7.2 Personal sync

`GET`/`PUT /scrims` on the existing Worker, authenticated by the Discord login
already implemented there (`/auth/login`, `/auth/callback` in
`infra/upload-worker/worker.js`), stored in the `NAMES` KV namespace already
bound in `wrangler.toml`. Note the precondition: that login stays disabled until
`DISCORD_REDIRECT_URI`, `DISCORD_CLIENT_ID`, `DISCORD_CLIENT_SECRET` and
`SESSION_SECRET` are all set, and `wrangler deploy` is run by the human
(`AGENTS.md` invariant 11) — so phase 5 has an operator step, not just a commit.
Merge is
**per-record newest-`updated_at`-wins**, computed in the browser; the Worker only
stores and returns a blob. Snapshots are hero GUID lists and stat rows rather than
images, so a season of scrims sits well inside KV's per-value limit.

This also gives the Season 10 IndexedDB rename a migration path it does not
currently have: sync up under the old name, sync down under the new one.

### 7.3 Sharing a scout

`POST /scrims/share` returns an unlisted URL with a long random id;
`docs/scrims.html?share=<id>` renders it read-only. Required alongside it:

- an **explicit warning at share time** — anyone with the link can open it, so
  send it only to people who should see it;
- **revoke**, from a list of the user's live shares;
- a **default 90-day TTL**, adjustable, so a forwarded link does not stay live
  indefinitely.

### 7.4 This amends a documented invariant

`ARCHITECTURE.md` §7 currently states scrim data is *"never published to the
Worker"*, and `AGENTS.md` invariant 8 restates the separation. Sharing breaks the
first of those deliberately, so it must be **rewritten, not quietly violated**:

> Scrim data leaves the browser only by an explicit, per-report, user-initiated
> share, and never enters `data/captures/`, the dashboard build, or the
> repository.

The other protections stay absolute: never merged into `data/captures/`, never in
the dashboard build, never committed. This is a data-contract change and gets a
`CHANGELOG.md` entry.

## 8. The viewer

### 8.1 Two runtimes, one analysis

`docs/scrims.html` re-implements its own hero and role resolution. Sharing code
with the dashboard is not free: **the dashboard computes its aggregations in
Python at export time** (`aggregate_swaps` was moved JS→Python deliberately),
while `scrims.html` must compute in the browser at read time because the data is
local and private.

The fix is therefore not to share the implementation but to **stop the two from
drifting**: define each aggregation once, implement it in both, and add a parity
test that runs the JS and the Python over the same fixture and asserts identical
output. `tests/test_capture_scrim.py` already executes page JS from pytest via
node, so the harness exists.

### 8.2 Tabs

- **Sessions** — the practice log, with a coverage strip by map category and
  days-since-last-played, answering "we have not played Push in three weeks".
- **Comps** — our hero pools, comp families, swap patterns and win rate by comp,
  split by map and side. Parity with league scouting.
- **Opponents** — the same analysis scoped to one opponent across every scrim
  against them. A league-matched opponent **links out** to their public dashboard
  profile.
- **Players** — per-player, per-hero stats from the joined final reads across a
  scrim block.

Showing an opponent's scrim comps **side-by-side** with their official-match
comps is deliberately deferred: it requires a public per-team comps JSON built by
CI and fetched by `scrims.html`, and the comparison is not worth reading until
the scrim data set is large enough.

## 9. Order of work

Work happens **on a branch**, not `main` — CI auto-commits to `origin/main` every
few minutes, and interleaving a multi-commit refactor of the capture app with
that invites a bad merge (`AGENTS.md` invariant 9).

| Phase | Work | Result |
| --- | --- | --- |
| 0 | Extract `calibration.js` / `refs.js` / `snapshot.js` / `overlay.js` from both capture pages | No behaviour change; league flow provably unchanged |
| 1 | Un-pause; session scaffold; **league-code block**; wipe-date check; manual add | Scrims are capturable |
| 2 | Ready-up name read; roster search over all teams; opponent registry; auto sides | No more typing team names |
| 3 | Legend-anchored scoreboard locate; shape check; **workshop hero-glyph reference set**; hero join; finish-map final read; optional per-round outcomes | Stats |
| 4 | Viewer: sessions / comps / opponents / players, plus parity tests | The four requested outputs |
| 5 | Discord sync; share link, warning, revoke, TTL | PC↔laptop, send a scout |
| 6 | Auto map detection, reactive retained as fallback | Minimal interaction |

Phases 0 and 1 together are what "ready for use" means. Each phase leaves the
tool usable; none is a flag day.

## 10. Testing

Existing guards that must stay green throughout:

- `tests/test_capture_scrim.py` — session-text parsing, map filtering, side
  detection, script validity for all three pages.
- The `node --check` syntax tests over generated dashboard JS, run after **any**
  edit under `faceit_sync/dashboard/` (`AGENTS.md` invariant 3).
- `mypy faceit_sync`, which must stay clean.

New tests this design requires:

- Each extracted engine module gets its own test file, following the established
  `scoreboard.js` / `scoreboard.test.js` pattern.
- League-code block: a code present in `data.json` is refused as a scrim.
- Wipe-date check: codes older than `code_wipe_date` are marked dead.
- Roster search: 3-of-5 or better labels the team; below that falls through to
  the local registry; two teams tied at three resolve by the documented
  tie-break, and an inconclusive tie assigns no team.
- Smurf learning: unmatched names from an uncorrected identification become
  aliases for that `team_id`; "not them" discards them; aliases never appear in
  a shared scout payload.
- Shape validation: reads that are not 5+5 / 1-2-2 / column-consistent are
  rejected; a single misread row is localised by the disagreeing signal.
- Hero join: stats attach to the right player, including across a mid-map swap.
- Degraded attribution: with no glyph reference set, tank rows attach exactly and
  DPS/support pairs are stored against the role slot rather than guessed.
- Grouping-mode detection: slot-ordered lobbies join positionally without glyph
  recognition.
- Sync merge: per-record newest-`updated_at`-wins, both directions.
- Viewer parity: JS and Python aggregations agree on a shared fixture.

Human-only in-game validation, which cannot be verified from code:

- That the legend anchor locates the scoreboard at all three sizes.
- That the shape check does not reject valid reads in real lobbies.
- Whether the ready-up list renders the discriminator (`Name#1234`) or the bare
  name. The normalisation in §4.2 is correct either way, so this is a
  confirmation rather than a blocker.

Settled by the operator, no longer open: the ready-up list is authoritative for
identity — it renders the actual battletag, so it is the primary name source and
the HUD nameplate read is purely a fallback.

## 11. Open items, deliberately deferred

- **Side-by-side league comparison** for a league opponent (§8.2) — needs a
  public per-team comps JSON.
- **Team-shared scrim data** with multiple people capturing into one log. The
  requirement here was sending a finished scout, not co-editing, so merge-conflict
  handling is out of scope.
- **Auto map detection** (phase 6) — deliberately last, so the reactive flow is
  proven in real scrims before anything automates on top of it.

- **The scrim capture page's UI lags the league capture app.** Noted by the
  operator during phase 1 verification: it is functional but visibly rougher
  than `docs/capture/index.html`, which has had far more iteration. The
  structural defect it exposed — the setup card implying one replay code per
  scrim, when a scrim is a series of maps each with its own code — has been
  fixed; what remains is presentation. Deliberately deferred: the structure is
  right and the records were always per-map, so this is polish that can follow
  real use rather than precede it. Worth doing before scrim mode is offered
  beyond the operator's own team.

- **Promoting a scrim capture to a league capture.** Today the league-code block
  refuses a league code outright. The better outcome, when someone has *already*
  captured a map and only then realises it was a league match, is to promote the
  record rather than discard the work. This is cheaper than it sounds, because
  the two records already share their payload:

  | | League map | Scrim map |
  | --- | --- | --- |
  | id | `match_id:game_no` | `scrim_id:map_no` |
  | shared | `observations`, `bans`, `profile`, `captured_at`, `winner_side` | same fields |
  | missing | — | `match_id`, `game_no` |

  Both missing fields come from the code itself: `data.json`'s entry carries
  `{code, match_id, game_no, map, division, team_a, team_b}`. Promotion is then a
  lookup, a re-key, and a write into the `maps` store, after which the existing
  publish path handles it unchanged.

  **The one piece of real work is team orientation.** A scrim record stores
  `side_a_team`/`side_b_team` (us / them) while a league record needs FACEIT's
  `team_a`/`team_b`. The code entry carries both names so it is mappable, but
  getting it backwards would publish comps attributed to the wrong team — which
  is worse than not publishing at all. That mapping needs its own test before
  this ships.

  Deferred to phase 2, and deliberately not bolted onto the block: refusing is
  correct today, and promotion is a separate, riskier feature.

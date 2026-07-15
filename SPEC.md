# owscout — SPEC

Overwatch 2 composition extraction from in-client replays, joined to the
existing `faceit-sync` league database.

This document is the single source of truth. It supersedes all prior
discussion. Where it contradicts anything you have been told elsewhere,
this document wins.

---

## 0. Purpose

`faceit-sync` ingests FACEIT League (OW2) championship data: matches, maps,
scores, hero bans, rosters, roles, per-player stats. It cannot ingest hero
picks — **FACEIT does not expose them on any endpoint.** Two independent
endpoints (match and stats) both stop at role granularity. This was
confirmed empirically, not assumed.

Hero picks exist only inside the game, behind the replay codes that
`faceit-sync` already stores as `games.demo_code`.

`owscout` extracts compositions from those replays via screen capture and
computer vision, and makes them queryable alongside the league data.

### Scope

In scope:
- Team composition per map, per side, over time.
- Per-player hero pools.
- A cross-team database of comps with win rates.
- The same pipeline for scrims, which have no FACEIT match.

Out of scope (do not build):
- Ult economy, positioning, fight-level or round-level tactical analysis.
- Any automation of the Overwatch client (see §11).

---

## 1. Established facts — do not re-derive

These come from a read-only audit of the live database. Treat as given.

**Environment**
- Windows 11. Repo at `C:\Users\ccarn\faceit-sync`.
- DB at `C:\Users\ccarn\faceit-sync\faceit.sqlite3`, ~5 MB, **local NTFS**.
  Not a network path. No SMB locking hazard.
- Same machine runs the Overwatch client and will run capture.
- DB path resolution in faceit-sync: `--db` flag → `$FACEIT_DB` → CWD-relative
  `faceit.sqlite3`. `*.sqlite3` is git-ignored.

**Schema (authoritative — the spec drift is resolved)**
- The per-map table is **`games(match_id, game_no, …)`**. There is no
  `match_rounds` table and no `round_no` column. `matches.round` means
  *bracket round*, not map. **The map unit is `(match_id, game_no)`.**
- Tables present: `championships, teams, players, heroes, maps, matches,
  games, map_picks, hero_bans, round_players, sync_log`.
- `games.demo_code` TEXT — 6-char Crockford-style base32
  (`0123456789ABCDEFGHJKMNPQRSTVWXYZ`). 1,515/1,691 non-null (89.6%).
  **One distinct code per played map** (414/415 multi-map matches have
  all-distinct codes). Populated uniformly across June and July — no
  recency decay. The ~10% gap tracks restart/forfeit shells, not lost codes.
- `hero_bans(match_id, game_no, hero_guid, ban_order, banned_by_faction)` —
  3,098 rows, **exactly 2 bans per map**, GUIDs fully resolve against
  `heroes`. `banned_by_faction` is `"faction1"`/`"faction2"` (143 NULL,
  from restart/expired-veto cases). Resolve to a team via
  `matches.faction1_team_id` / `matches.faction2_team_id`.
- `round_players(match_id, game_no, team_id, player_id, role, …)` — 15,150
  rows, **exactly 5 players per team per map**, 3,030 team-maps.
  `player_id` and `team_id` never NULL. Nicknames resolve via `players`.
  `role` ∈ {Tank, Damage, Support}, distributed 1/2/2 per team per map
  (28 unlabelled rows from 21 stat-uncaptured games). Carries K/D/A, damage,
  healing, mitigation, elo_snapshot. **Gives who and role — never hero.**
- `heroes(guid, name, role)` — 52 seeded, 24 Damage / 14 Support / 14 Tank.
  Current for the data's patch. **This table is authoritative for the hero
  roster. Do not use any hardcoded hero list from any other source.**
- `maps(guid, name, category)` — 31 seeded across Clash(2), Control(7),
  Escort(8), Flashpoint(3), Hybrid(7), Push(4).
- **No migration framework.** Schema is `CREATE TABLE IF NOT EXISTS` in
  `db.py`. No Alembic, no version table, no ALTER path.

**Scale**
- 4 championships (S9 EMEA & NA × Master & Expert Central, Regular Season).
- 474 matches, all FINISHED. 415 Bo5. 122 teams (116 with play data),
  940 players. 1,512 real played maps.
- Date range 2026-06-11 → 2026-07-09. One regular season, ~4 weeks.
- **Per-(team, map) depth is thin**: 1,081 distinct pairs, **median 2
  samples**, max 8. 309 pairs have exactly 1. Per-team depth is fine
  (median 27 maps).

**Known fragility in faceit-sync (documented in `sync.py` header)**
- FACEIT democracy/veto tickets are ~7-day ephemeral. Codes already
  persisted are safe; *new* matches need `fetch` to run within ~7 days.
  A daily CI job at 22:00 UTC covers this.
- Admin restarts destroy a game's veto ticket → explains the NULL
  `banned_by_faction` rows and some NULL `demo_code`s.
- **`demo_code` is assigned by list index**: `sync.py:329` reads
  `match_payload["demoURLs"]`, `sync.py:400` assigns `demo_urls[idx]`.
  See §9 — this is a correctness hazard owscout must check.

---

## 2. Replay code lifetime — the wipe model

**Resolved. This is the single most important constraint in the document.**

Blizzard wipes all existing replay codes on client build changes, and does
so deliberately and periodically — they announce it and tell players to
record anything they want to keep. A wipe occurred **14 July 2026**,
invalidating every code in the database (data spans 11 June → 9 July).

Therefore:

- **There is no historical backfill. The archive is zero.** Every one of the
  1,512 stored codes is a dead pointer. The strings remain in
  `faceit.games.demo_code` forever; the replays they addressed do not exist.
- **owscout is a live-capture tool with a rolling window.** It builds value
  going forward, from the next match played, and only from matches captured
  before the next wipe.
- **The extracted data is permanent.** `owscout.sqlite3` survives wipes.
  The code is a perishable ticket; the comp row is forever. This is the
  whole point of the tool and the reason it is worth building despite the
  above.

### The capture window is the only deadline that exists

The governing number is the **inter-wipe interval** (historically on the
order of weeks, tied to bug-fix patches, not announced far ahead). A code
must be consumed inside that window or it is worthless.

Two hard consequences for design:

**1. Reactive scouting does not work. Do not design for it.**
"Get drawn against Team X, then capture their recent maps" fails whenever
the draw lands after a wipe that post-dates their matches. `codes list`
would return rows that no longer load, with no way to recover them.
Capture must be **proactive and routine** — capture shortly after matches
are played, before knowing whether the data will be needed.

**2. Full division capture is not affordable.**
~150 maps/week per championship × ~2 min skim ≈ 5 hours/week. Targeted
capture of plausible opponents, weekly, is the realistic operating mode:
roughly 50–100 maps per wipe window at 2–3 hours of operator time.

Consequence: the comp database (§10.3) is built from a **biased sample** —
whatever the operator chose to scout, in whatever window they were active.
It accumulates across wipes and becomes genuinely useful over months, but
it is never a representative sample of the league. This must be surfaced
in the output, not hidden. See §10.3.

### `code_status` and wipe boundaries

Because a wipe invalidates everything at once, code viability is a function
of one date, not per-code probing. Maintain a `wipes` table (§4); any code
belonging to a game played before the most recent wipe is `wiped` by
definition, with no need to test it. `codes list` filters on this by
default. The operator records wipes as they learn of them; there is no
API for this.

---

## 3. Architecture

```
  faceit.sqlite3 (existing, read-only to owscout)
        │  ATTACH
        ▼
  owscout.sqlite3 (new, owscout writes only)
        ▲
        │
  capture → parse → constrain → smooth → review → store
        ▲
        │
  dxcam screen grab (operator scrubs the replay by hand)
```

**Separate database file. Non-negotiable.**

Rationale, in order of importance:
1. faceit-sync's ingest does delete-and-reinsert of child rows. Writing
   into that DB means fighting it.
2. There is no migration framework. Adding tables to `faceit.sqlite3` means
   hand-editing `db.py`'s DDL and hoping.
3. The CI job and the `.cmd` launchers write to it on their own schedule.

owscout opens `owscout.sqlite3` and `ATTACH`es `faceit.sqlite3` **read-only**
(`file:...?mode=ro` URI). It never writes to the faceit DB. Cross-DB joins
work normally under ATTACH; cross-DB foreign keys do not, so FACEIT keys are
stored as plain columns and validated on write (§4).

Set `PRAGMA journal_mode=WAL` and `PRAGMA busy_timeout=5000` on the owscout
DB. Even though it's local disk and single-writer, WAL costs nothing.

DB path config mirrors faceit-sync's convention: `--faceit-db` flag →
`$FACEIT_DB` → CWD-relative `faceit.sqlite3`. Own DB: `--db` → `$OWSCOUT_DB`
→ `owscout.sqlite3`.

---

## 4. Data model (owscout.sqlite3)

Foreign keys on. All DDL as `CREATE TABLE IF NOT EXISTS`, matching
faceit-sync's convention.

```sql
game_builds(id, build_string, patch_label, first_seen_at, last_seen_at)

roi_profiles(id, resolution_w, resolution_h, hud_variant, team_size,
             slots_json, anchors_json, created_at, retired_at NULL)

hero_refs(id, hero_guid, profile_id, state CHECK(state IN ('alive','dead')),
          image_path, phash, added_at, source CHECK(source IN ('capture','review')))
-- hero_guid mirrors faceit.heroes.guid. Validated on insert, not FK'd.

scrims(id, played_on, opponent_label, our_team_id NULL, map_name,
       map_guid NULL, winner_side NULL, notes)

map_instances(id,
  source_type CHECK(source_type IN ('faceit','scrim')),
  match_id NULL, game_no NULL,          -- -> faceit.games(match_id, game_no)
  scrim_id NULL REFERENCES scrims(id),
  demo_code NULL,
  map_guid NULL, map_name, map_category NULL,
  side_a_team_id NULL, side_a_label,    -- side_a = LEFT on the HUD
  side_b_team_id NULL, side_b_label,
  winner_side CHECK(winner_side IN ('a','b','draw',NULL)),
  build_id REFERENCES game_builds(id),
  profile_id REFERENCES roi_profiles(id),
  map_verified CHECK(map_verified IN (0,1)),   -- see §9
  captured_at,
  UNIQUE(match_id, game_no),
  UNIQUE(scrim_id))
-- CHECK: exactly one of (match_id AND game_no) or scrim_id is non-null.
-- For source_type='faceit': map_guid, map_name, map_category, side_*_team_id
-- and winner_side are DERIVED FROM THE FACEIT DB ON INSERT. Do not OCR them.
-- You already know them. OCR is used only to VERIFY (§9).

comps(comp_id PK, hero_guids_json, hero_names_sorted,
      tank_count, damage_count, support_count, team_size)
-- comp_id = sha1 of sorted hero_guids. Order-independent, canonical.

comp_observations(id, map_instance_id REFERENCES map_instances(id),
                  side CHECK(side IN ('a','b')),
                  sample_ts_ms, comp_id NULL REFERENCES comps(comp_id),
                  min_slot_confidence, resolved CHECK(resolved IN (0,1)),
                  frame_path NULL,
                  UNIQUE(map_instance_id, side, sample_ts_ms))
-- comp_id stays NULL until every slot resolves. Unresolved rows are the
-- review queue (§8) and are INVISIBLE to all derived output (§10).

comp_slots(observation_id REFERENCES comp_observations(id), slot_index,
           hero_guid NULL, confidence, is_dead CHECK(is_dead IN (0,1)),
           expected_role NULL, ingame_name_raw NULL,
           player_id NULL,            -- resolved via player_aliases
           PRIMARY KEY(observation_id, slot_index))

player_aliases(id, player_id, ingame_name, first_seen_at, last_seen_at,
               confirmed CHECK(confirmed IN (0,1)),
               UNIQUE(player_id, ingame_name))
-- player_id mirrors faceit.players.id.

capture_log(id, ran_at, demo_code, map_instance_id NULL, samples_taken,
            samples_written, low_confidence, banned_hero_hits,
            map_mismatch CHECK(map_mismatch IN (0,1,NULL)), errors)

wipes(id, wiped_at, build_string NULL, source CHECK(source IN ('announced','observed')),
      notes)
-- Operator-maintained. Blizzard wipes ALL codes at once, so viability is a
-- function of this date, not of per-code probing. Seed with:
--   ('2026-07-14', 'observed', 'invalidated all S9 regular season codes')
-- A code is dead iff its game was played before MAX(wiped_at). No probing.

code_status(demo_code PK, first_seen_at,
            status CHECK(status IN ('unknown','captured','skipped','failed')),
            notes)
-- Tracks operator INTENT and outcome only. Viability comes from `wipes`.
-- Do not store 'wiped' here — it is derived, and storing it invites drift.
```

**Team size**: read from `roi_profiles.team_size`, default 5. Do not
hardcode 5 anywhere. Slot-count-agnostic parsing is free now and a rewrite
later.

---

## 5. `owscout calibrate`

Pixel coordinates live in the DB, never in source.

```
owscout calibrate [--hud-variant <name>]
```

1. Grab the current game window at native resolution. Save the full frame.
2. Open a Tk/OpenCV window. Operator drags a box over each team's hero
   portrait strip (left and right). Tool subdivides each strip into
   `team_size` equal ROIs and shows the crops for confirmation.
3. Operator drags 2-3 **anchor** boxes over fixed HUD furniture (objective
   bar, timer, scoreboard chrome). These are used at runtime to answer "is
   this frame a live match view, or a menu/killcam/loading screen".
4. Persist to `roi_profiles`, keyed on `(resolution_w, resolution_h,
   hud_variant)`.

Assume 2560×1440 as the working resolution but **derive it, never assume
it**. A profile is invalid at any other resolution; detect and refuse.

Re-calibration is expected after HUD-affecting patches. §9 tells you when.

---

## 6. `owscout refs`

```
owscout refs capture         # guided
owscout refs verify
```

**Reference icons must come from the client, at the operator's exact
resolution.** Wiki art, API CDN images and Liquipedia crops do not match
in-game rendering — different scaling, different colour profile, different
compositing. This is not a preference.

`refs capture`: read the hero list from `faceit.heroes` (52 rows, current).
Walk it. For each hero, operator gets it on screen (custom game / practice
range / any replay) and confirms; tool crops the ROI and stores image +
perceptual hash. Capture **both states**:
- `alive` — normal portrait.
- `dead` — greyed/desaturated. This is a *state*, not a different hero. The
  hero_guid must still resolve when dead.

`refs verify`: report heroes missing a ref for the active profile; report
any two refs whose phash distance is suspiciously small (visually similar
portraits will cause silent misclassification — know about it up front).

---

## 7. `owscout capture`

```
owscout capture --code <demo_code>            # FACEIT; everything else derived
owscout capture --scrim <scrim_id>
owscout capture --watch                       # continuous, auto-detects map
owscout codes list --team <name> [--uncaptured] [--limit 10]
owscout codes queue --team <name> [--limit 10]   # clipboard queue, see below
owscout codes mark --code <c> --status captured|skipped|failed
owscout codes age
```

**`--code` is the whole interface for FACEIT capture.** Given a demo_code,
look it up in `faceit.games` and derive everything: match_id, game_no,
map_guid, map_name, category, both team ids, winner, the ban list, the ten
players and their roles. The operator supplies six characters; the tool
supplies the context.

**`codes list`** joins `games → matches → teams`. Shows demo_code, map,
opponent, date, and whether a `map_instance` already exists. Filters out
codes whose game pre-dates `MAX(wipes.wiped_at)` by default — they are dead
by definition (§2). Default sort: **most recent first**.

### 7.1 Operating model — speed-mode playback, not manual scrubbing

**The replay client has its own playback speed controls. Use them.**

Load the code, set playback to 4x, alt-tab away. A ten-minute map completes
in ~2.5 minutes, unattended, while owscout samples continuously. At 1-2 fps
capture against 4x playback that is a sample every 4-8 game-seconds — far
more than sufficient, because comps are step functions.

This is strictly better than seek-and-grab skimming:
- Complete temporal coverage, so mid-fight swaps are caught rather than
  missed between seeks.
- Operator attention drops to ~20 seconds per map (paste, set speed,
  leave) against ~2 minutes of active scrubbing.
- Wall-clock is unattended and can overlap with anything else.

Using the client's own speed control is not automation. It is a feature of
the product, operated by a human. See §11 for where the line actually is.

**Revised economics.** ~20s attention + ~2.5 min unattended per map. A
50–100 map wipe window is ~20-35 minutes of attention and a few hours of
background wall-clock. This is the number that makes routine proactive
capture (§2) viable at all.

Manual scrubbing remains supported as a fallback — the tool samples whatever
is on screen and does not care how it got there.

### 7.2 Clipboard queue

Code entry is the repetitive part. It can be removed without touching the
game process at all.

`owscout codes queue --team X` loads the pending codes and places the first
on the **system clipboard**. Operator clicks the replay code field, Ctrl+V,
Enter. On capture completion the tool advances the queue and places the next
code on the clipboard automatically.

**The clipboard is an OS resource, entirely outside the Overwatch process.**
Nothing is injected, nothing is inspected, nothing is hooked. This delivers
essentially all of the ergonomic benefit of code-entry automation with none
of the risk described in §11.

### 7.3 Capture flow

- `dxcam` for capture (fall back to `mss`). **1-2 fps, not 60.**
- **Validity gate per frame**: check anchors. If they don't match, the frame
  is a menu, loading screen, killcam or highlight intro — discard silently,
  do not parse, do not log noise. Under speed-mode playback this gate does
  most of the work of detecting map start/end.
- **Change detection**: hash the ROI strip. Write an observation only when
  the comp differs from the last written, or every N seconds of *game* time
  (default 30), whichever comes first. Do not store 1,200 identical rows
  per map. Note that under 4x playback, wall-clock and game-time diverge —
  record `sample_ts_ms` in game time, derived from the playback rate, not
  from the system clock.
- **Side assignment**: side_a is the left HUD strip. On first capture of a
  map, OCR the in-game names in each strip and match against the ten known
  players from `round_players` (§8.2). Assign sides by majority match.
  Prompt only if that fails.
- **Playback rate is config, not detection.** The operator tells owscout what
  speed they set (`--speed 4`, default 1). Do not try to infer it.

---

## 8. Matching

### 8.1 Constrain before matching — this is where the accuracy comes from

For a `source_type='faceit'` instance, before matching any frame:

1. **Bans.** `SELECT hero_guid FROM faceit.hero_bans WHERE match_id=? AND
   game_no=?` — exactly 2 rows. **Exclude those refs from the candidate
   set.** A banned hero is impossible, not unlikely.
2. **Roles.** `SELECT role FROM faceit.round_players WHERE match_id=? AND
   game_no=? AND team_id=?` — exactly 5 rows, 1 Tank / 2 Damage / 2 Support.
   The observer HUD orders slots by role. Restrict each slot's candidate set
   to refs whose `heroes.role` matches the expected role for that position.
   Store the expectation in `comp_slots.expected_role`.
3. Match against the reduced set only.

Effect: a tank slot is 1-of-14, not 1-of-52. A support slot is 1-of-14. A
damage slot is 1-of-24, less bans. The problem is materially easier than
open-set classification and the accuracy follows.

If `role` is unlabelled for a game (21 known rows), fall back to the full
set for that instance and note it.

For `source_type='scrim'`: bans and roles are entered manually if known,
else full candidate set. Scrim accuracy will be lower. Say so in the output.

### 8.2 Player resolution — a 5-way match, not open-world OCR

`round_players` gives exactly 5 named players per team per map. So mapping
a HUD slot to a player is fuzzy-matching an OCR'd in-game name against a
**candidate list of five**, not against 940. Use rapidfuzz; accept above a
threshold, else leave `player_id` NULL and let review handle it. Cache
accepted matches in `player_aliases` so subsequent captures are automatic.

FACEIT nicknames and in-game names diverge often. The five-way constraint is
what makes this tractable; do not throw it away by matching globally.

### 8.3 The matcher

- Per ROI: `cv2.matchTemplate` with `TM_CCOEFF_NORMED` against the reduced
  candidate set. Best score is the confidence.
- **Dead detection first**: mean saturation of the ROI below a threshold →
  route to the `dead` ref set. Then match within it.
- **Mask the ult-charge overlay subregion** out of the ROI before matching.
  The killfeed can also occlude; if a match is low-confidence, that's often
  why — the temporal smoothing handles it.
- **Confidence floor**, default 0.80, configurable. Below it: write the slot
  with `hero_guid` NULL, `resolved=0`. Do not guess.
- **Temporal smoothing**: per `(map_instance, side, slot_index)`, take the
  modal hero over a rolling window of W samples (default 5) before
  committing a comp. This is what converts a good per-frame rate into a
  reliable output. Do not skip it.

---

## 9. Integrity checks

These are the difference between a scouting tool and a tool that quietly
lies to you. All three are hard errors, not warnings.

### 9.1 Banned hero resolved → stale ROI profile
If any slot resolves to a hero in that map's `hero_bans`, the result is
**provably wrong**. Do not write it. Log:

```
Slot resolved to banned hero <name> — ROI profile likely stale after patch.
Run `owscout calibrate`.
```

Track the rate in `capture_log.banned_hero_hits`. Above a threshold
(default 2% of resolved slots), **fail the run**. This is a better HUD-drift
detector than the anchors, because it's a logical impossibility rather than
a similarity score.

### 9.2 Map name mismatch → `demoURLs` index misalignment
**This is the important one.**

`faceit-sync` assigns `demo_code` by list index (`demo_urls[idx]`), assuming
FACEIT's `demoURLs` array aligns 1:1 and in-order with `games` rows. There
are 176 restart/forfeit shell rows and 69 `was_restarted=1` games. If FACEIT
emits demo URLs only for replays that actually occurred, **every code after
a shell in that match is off by one** — and nothing inside faceit-sync can
detect it.

owscout can. It sees the map.

On capture: OCR the map name from the replay. Compare against
`games.map_name` for that `demo_code`. On mismatch:
- Set `map_instances.map_verified = 0`, `capture_log.map_mismatch = 1`.
- **Refuse to write comp observations for that instance.**
- Log loudly, naming both maps and the match_id.

Then: `owscout verify-codes --championship <id>` — for every captured
instance, report the mismatch rate, broken down by whether the match
contains a restart shell. If mismatches cluster on post-restart games, the
index-assignment bug is confirmed and `sync.py:400` needs to key demo URLs
by something other than position.

This makes owscout a validator for faceit-sync. Treat that as a feature and
document it in the README.

### 9.3 Build change → force re-verification
Record the game build with every capture. On build change, mark the active
`roi_profile` as suspect and require `refs verify` / a calibration check
before the next capture proceeds. HUDs move.

---

## 10. Derived output

**Every derived query filters by patch/build window by default**
(`--patch current`, `--patch all`, `--since <build>`). Metas turn over on
balance patches; averaging across them produces comps that no longer exist.
Never silently pool across builds.

**Unresolved observations are invisible to all output.** Bad scouting data
is worse than none.

### 10.0 The sample-depth rule — applies to everything below

Median depth is 2 games per (team, map). Max 8. This is the binding
constraint on the entire output layer.

Therefore, mandatory in every command:
- **Always print `n`** — sample count and distinct-map count — next to every
  percentage. No exceptions.
- **Fallback chain** when a cell is too thin (`--min-samples`, default 5):
  `(team, map)` → `(team, map_category)` → `(team, all maps)`.
  **State which level was used in the output.** Never silently substitute.
- **Never render a bare percentage below `--min-samples`.** Print the raw
  fraction (`2/2`) instead. A rendered "100%" off two games is a lie of
  presentation.

### 10.1 `owscout scout player <name>`

**This is the primary scouting output.** Say so in the README.

Per-player hero pool, per role, with pick rate and n. At ~27-35 maps per
team, a player's pool is the only cell in this dataset with real depth.
"Their tank is on Winston 70% of 30 maps" is a statistic. "This team runs
X on Ilios" over 2 maps is not.

Breakdowns: overall pool, pool by map category, pool by map (with the n
caveat loud).

### 10.2 `owscout scout team <name> [--map <m>] [--last-n 5]`

Built up from players, not down from comps.

- Roster and each player's pool (§10.1), which is the load-bearing content.
- **Modal comp**: the exact 5 run most often, with n and record. Honest.
- **Per-slot pick rate** by role.
- **Synthetic likely comp**: top hero per role slot. **Label it SYNTHETIC in
  the output.** It is a composite that the team may never have actually
  fielded — check `comps` and warn explicitly when the synthesised comp has
  zero observations. This is a vibe, not a scouting report, and the output
  must say so.
- **Swap tendency**: distinct comps seen and the most common transitions.
- Ban tendency: available already from `faceit.hero_bans` — join it in, it's
  free and it's real data with 3,098 rows behind it.

There is no such thing as an "average comp". Sets of heroes do not average.
Modal comp and per-slot rate are the two honest objects; produce those.

### 10.3 `owscout comps top [--map <m>] [--mode <category>] [--min-samples 10]`

The cross-team comp database. This is the one query with real breadth —
~3,000 team-map observations if broadly captured.

Per comp: samples, distinct maps, distinct teams, map win rate, and
**Wilson lower bound**. **Sort by the Wilson bound, never by raw win rate.**
A 100% comp off 2 maps must not top the list; that is the entire point.

**Sampling bias disclosure — mandatory in the output header:**
```
Based on N maps captured of 1,512 played (X%). Captured maps are those the
operator chose to scout — this sample is NOT representative of the league.
```
Do not omit this. The comp DB is built from targeted opponent scouting, so
it over-represents the teams you were drawn against.

**Win attribution.** Map winner comes from `faceit.games` for FACEIT
sources, manual entry for scrims. A team may run several comps across one
map. Attribute the map result to each comp **proportionally to its share of
samples** on that map; store the weight. Document in `--help`: map-level
attribution is a coarse proxy, comp win rate is directional and not causal.
Do not present it as though the comp caused the win.

### 10.4 `owscout export --format csv|json`

Mirror faceit-sync's export conventions.

---

## 11. Non-goals — do not build

### The line: do not inject input into the Overwatch process

**Prohibited**: `SendInput`/`SendKeys`/`PostMessage` into the game window,
synthetic mouse clicks, menu walking, memory reads, DLL injection, any hook
into the client process.

**Permitted, and used**: reading the screen (`dxcam`), the system clipboard
(§7.2), OBS, window focus management, and the replay client's own playback
speed controls operated by a human (§7.1). These are OS resources and
product features. None of them touch the game process.

The reasoning, in order of weight:

1. **Warden cannot read intent.** Injected input has the same signature
   whether it is pasting a replay code or driving an aimbot. Enforcement is
   automated and account-level; there is no warning and appeals against
   automated detection are unproductive. The account at risk carries a
   competitive identity (Team Ireland, FACEIT League) that is not
   reconstructable. Unbounded downside against a saving of ~10 seconds per
   replay is not a close call.
2. **It is the most patch-fragile component that could exist.** OW2 is a
   DirectX fullscreen app — no accessibility tree, no window handles for
   controls. A clicker is blind coordinates or template-matched menu
   buttons, i.e. *the same CV problem again, on a less stable target*. The
   replay UI has moved repeatedly. Every patch is a coin flip.
3. **The failure mode is silent and bad.** A misfire does not raise; it
   clicks something else. Worst case, an unattended run queues into a live
   match.

§7.1 and §7.2 recover nearly all of the ergonomic benefit — attention drops
to ~20s/map — without crossing this line. That is why the line costs
almost nothing.

### Also out of scope

Ult economy, positioning, fight-level or round-level tactical analysis —
anything requiring dense temporal sampling or state beyond "who is on what".

---

## 12. Engineering requirements

Mirror faceit-sync's conventions — this is a sibling tool, not a foreign body.

- Python 3.11+. Windows-first. Full type hints, passes mypy.
- Layout: `owscout/{cli,capture,match,calibrate,refs,db,models,derive,export}.py`,
  `tests/`.
- Structured logging via `logging`, not `print()`. `--verbose` → DEBUG.
- `--dry-run` on every write command.
- **Idempotent**: re-capturing a demo_code UPDATEs, never duplicates.
  `INSERT ... ON CONFLICT DO UPDATE` on
  `(map_instance_id, side, sample_ts_ms)`.
- Config in TOML: confidence floor, sample interval, smoothing window,
  team_size, min_samples, default playback speed, DB paths.
- `pyproject.toml`, ruff, `.env.example`. Provide `.cmd` launchers matching
  the existing ergonomics (`Scout opponent.cmd`, `Capture replay.cmd`).
- **Never write to `faceit.sqlite3`.** ATTACH read-only via URI. Assert it.
- pytest. Unit tests on: comp canonicalisation (sha1 order-independence),
  Wilson interval, temporal smoothing, side assignment, the ban-constraint
  filter, the fallback chain in §10.0, and the map-mismatch check. **Ship
  3-4 sample frames as fixtures** so the matcher is testable without the
  game running. Mirror faceit-sync's use of `responses` where HTTP is
  involved (it mostly isn't here).

---

## 13. Build order

Front-loaded on risk. Do not proceed past a step that fails.

1. **`calibrate`** — ROI capture and persistence. Nothing works without it.
2. **`refs capture`** — the library, both states, from the client, at native
   res. Boring, an afternoon, foundational.
3. **One hardcoded frame, constraint-aware match, printed to stdout.**
   Use a map you played and know the answer to. **This is the gate.** If the
   observer portraits are too small or too occluded at your ROI, you learn
   it here, on day one, before any schema exists.
4. Schema + the ATTACH layer + `--code` context derivation.
5. `capture` with change detection and smoothing.
6. Integrity checks (§9). **Before** any derived output — do not build
   statistics on unvalidated data.
7. `review`.
8. Derived output (§10), in order: `scout player`, `comps top`,
   `scout team`.

Step 3 is a day. If it works, the rest is plumbing of a kind that
faceit-sync already proves can be shipped.

---

## Appendix — `owscout review`

Human-in-the-loop, required, not optional.

```
owscout review
```

Serves a minimal local page (or Tk window) listing unresolved observations:
the saved frame crop, the top-3 candidates with confidences, the expected
role, and the ban list for context. Operator clicks the right hero. Tool
writes the slot, resolves the comp if complete, and **optionally adds the
crop to `hero_refs`** (`source='review'`) so the matcher improves with use.

Nothing enters the derived views unresolved. The review queue is the price
of the output being trustworthy.

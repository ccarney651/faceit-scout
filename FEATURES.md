# OWDB — complete feature reference

Two packages that feed one website.

**`faceit_sync`** ingests FACEIT League (Overwatch 2) match data into SQLite and
renders it as a self-contained dashboard. **`owdb`** watches in-client replays,
reads the hero portraits off the observer HUD, and turns them into composition
scouting that the same dashboard displays. They share nothing but a read-only
database link and one JSON file.

*350 tests, mypy clean across 49 files.*

---

## 0. How the pieces fit

```
FACEIT API ──fetch──► faceit.sqlite3 ──export──► docs/index.html   (the live site)
                            │                          ▲
                       (read-only)                     │
                            ▼                    (merged at build)
OW replay ──capture──► owdb.sqlite3 ──publish──► data/captures/<you>.json
```

Three facts about this diagram carry most of the operational risk:

1. **There are two copies of `faceit.sqlite3`** — yours, and the one CI keeps in
   its Actions cache. They are independent. Both are built from the same upstream
   API, so they converge as long as both stay synced; nothing reconciles them.
2. **`docs/index.html` is the live site and CI is its only writer.** A local
   `dashboard.html` is a preview built from *your* database — deliberately
   untracked, because a committed copy would silently disagree with the real page.
3. **`data/captures/<contributor>.json` is the bridge.** Each contributor commits
   their own file of raw observations; the build merges them all and derives the
   report. `owdb_comps.json` is generated at build time and is NOT committed —
   a stored report outlives the observations it came from and freezes the
   analysis that produced it.

---

# Part 1 — `faceit_sync`

## 1.1 Ingest (`faceit-sync fetch`)

Pulls finished league matches into SQLite. Works **keylessly** against FACEIT's
public endpoints; an API key only unlocks championship enumeration.

**Transitive discovery.** Seeded from `matches.txt`, the enumerator walks from
known matches to the championships that contain them to every other match in
those championships. A cache miss in CI self-heals — the seed list rebuilds every
division from scratch.

**Idempotent by construction.** Every write is an upsert keyed on natural
identifiers (`match_id`, `(match_id, game_no)`), so re-running is free and a
half-finished run leaves no partial state.

**Replay-code backfill.** A plain fetch skips anything already stored
`FINISHED`, so a code absent at ingest could never arrive. The obvious fix — re-fetch
any recent match missing a code — turned out to be wrong, and measuring it is
worth recording:

> Across 676 real matches, **87 had no code on any game and only 4 had a partial
> gap**. Re-fetching all 44 recent candidates recovered **zero** codes. Missing
> codes are an all-or-nothing property of a match, not a publishing delay: replays
> were simply never published for those matches, which tracks with the division
> (17.8% of EMEA Master games lack codes vs 1.1% of NA Master).

So only two cases are re-fetched: a **partial gap** (some games have codes, some
do not — the one signature consistent with an incomplete publish) within
`--backfill-days`, and any match **ingested in the last 12 hours**, which may
genuinely not have its codes up yet. That is ~5 matches per run instead of 44.

**Restart handling.** FACEIT's demo-URL bug produces duplicate game shells when a
map is restarted. `was_restarted` marks them and integrity reporting clusters
mismatches by restart shell, so a known-bad shell doesn't look like a data error.

## 1.2 The dashboard (`faceit-sync export --format html`)

One HTML file, no external requests. Data is injected as JSON and the **entire
body renders in JavaScript** — which means one syntax error yields a completely
blank page, so a test runs `node --check` over the generated script on every run.

Hero portraits are inlined as WebP data URIs from a committed
`faceit_sync/hero_icons.json` (~97 KB, 52 heroes). The 22 MB of source art is
gitignored, so builds read the committed cache and local and CI produce identical
pages. Regenerate with `python -m faceit_sync.hero_icons <asset-dir>`.

### Regions and divisions

The site ships **EMEA** (Master / Expert / Advanced) and **NA** (Master /
Expert), picked with a paired region + division selector. Region and tier are
read from the championship *name* — the `championships.region` column says
`GLOBAL` on every row and is useless — matched as **whole words**, since a bare
`"NA" in name` would file an "Open Nationals" cup under North America.

Each region with more than one tier also gets a **Combined** view, merged on
demand from the divisions already in the payload rather than duplicated into it.
Views are ordered region-major, EMEA first, tiers strongest-first.

The chosen division is remembered in `localStorage`, so an NA coach picks their
region once rather than every visit. A stored id is validated against the current
views before use: divisions come and go between seasons, and a stale id has to
fall back to the first view rather than leave the page with nothing to render.
Shared `#scout=` / `#prep=` links still win, and deliberately do *not* overwrite
the stored preference — following a link to an NA team shouldn't relocate an EMEA
coach permanently.

Everything the FACEIT feed provides — standings, bans, maps, player stats, elo —
is populated for every division. Comp/scouting sections depend on someone having
captured replays for that division (see §5, Known gaps).

`--region emea|na` narrows the build to one region; the live site passes no
`--region` and ships everything in the database.

### Tabs

A hero strip above the tab bar ("Scout a team →" / "Contribute a capture →")
is always visible, on every tab — it's the fast path for both a first-time
visitor and a returning one, so Overview itself doesn't need to duplicate it.

**Overview** — coverage tiles (maps played, teams, teams scouted, comps
captured), standings, and the scout leaderboard (maps contributed per scout).
Deliberately does not repeat content that has its own tab (ban/map meta lives
in League meta; per-team rosters live on Scout a team and Players) — Overview
is orientation, not a preview of everything else.

A **capture recommendations** panel ranks the maps the league has played but is
still under-covered. It scores by *unseen minutes* — games × a per-mode length
estimate (Control 14, Escort 20, Hybrid 20, Push 11, Flashpoint 11, Clash 10) —
so the maps costing the most unseen play sit at the top. A map qualifies only if
it has been played at least 3 times, is still under half covered, and still has
a *live* replay code to capture (a wiped-and-unseen game can never be fixed, so
it is not listed). Each row shows the coverage fraction, `~N min unseen`, a
coverage bar that turns green at the 50% target, and a **Scout →** link straight
to the newest capturable code. The panel is withheld entirely when nothing is
under-covered — the "withhold rather than fake" rule applied to the whole site,
not just one row.

When the visitor's own contributor name (their chosen publish name in
`localStorage`) is on the leaderboard, a **contributor impact card** sits above
it: their rank medal (🥇🥈🥉), how many maps they contributed, what share of the
division's captured maps that is, and a *Capture another →* call-to-action into
the capture app — the reward loop that makes a leaderboard row feel like it is
yours.

**Scout a team** — the main working view. Detailed in §3. The team picker is
labelled *Team*, not *Opponent*: pointed at your own side the same sheet is a
self-scout, showing what an opponent prepping you is looking at. Includes a
collapsed **Draft simulator (beta)** section near the bottom — pick two teams
and walk a draft; each team's real history drives the suggestions (map-pick
frequency, per-map ban counts, overall ban rates), with already-banned heroes
excluded from the picker. Every suggestion explains itself in plain language,
with the backing replay codes one click away (see §3, Draft simulator). Opens
pre-filled with the currently scouted team; `#sim` opens the section and
`#simfull` renders the whole suggested tree expanded.

**Players** — every player on every roster, in three views. *By team* (rosters,
starters over subs, elo, top-3 captured heroes), *By role* (grouped by
competitive role — Tank / Hitscan / Flex DPS / Main Support / Flex Support),
and *Leaderboard* — a sortable table of elo, maps, K/D, per-map damage /
healing / mitigation, and **Eff**. The leaderboard runs purely off FACEIT's
stat feed, so unlike hero pools it is fully populated in **every** division,
captured or not. Rate columns carry a 5-map sample floor; counts and elo do not
need one.

**Eff** — the efficiency rating, a PER-style composite: each player's per-map
stat averages (damage, healing, mitigation, K/D) z-scored against the
division's other players in the same competitive role, then averaged across the
stats that actually vary within that role — +1 means one standard deviation
above the role average. It is a summary line, never a bare number: the
component z-scores sit beneath it (d/h/m/k = damage, healing, mitigation, K/D),
and a stat with no variance inside the role (healing for Tanks) drops out by
itself rather than being weighted by hand. Below the 5-map sample floor, or
against fewer than four same-role peers, no rating renders at all. The peer
group is a player's competitive role when captured games place them in one,
otherwise their base role (Tank / Damage / Support), so the column is populated
in every division. It does not control for team strength: players on strong
teams post better lines.

**League meta** — cross-division hero ban rates, ban-by-role split, map
popularity, attacking-first win rate per map (Escort/Hybrid only, since mirrored
modes have no attacking side), and **hero win rates** off the captured comps
joined to the match result — what actually wins, next to what gets banned. The
unit is the map (a hero on two sub-maps of one Control map played one map), each
team's lineup counts separately, and 8+ maps are needed to qualify.

**Matches** — every match card: per-map bans in draft order, replay codes inline
and click-to-copy, expandable rosters, newest/oldest sort, and the match date. A
**Played / Upcoming / Playoffs** toggle switches the list; Playoffs shows the
bracket (seeded from current standings until real playoff matches exist) and
becomes the default view automatically once real playoff matches are ingested
for the active division. Playoff championships are ingested keylessly, seeded
from `matches.txt`. Finished bracket entries are full match objects — scores,
rosters and replay codes — tagged `playoff` and opening the same match detail
page as a regular-season game; unplayed slots are bare fixtures. Match detail
pages carry a **scout push** banner whenever a game of theirs still has a live,
uncaptured replay code: what is still open to capture, the wipe warning, and a
*Scout <code> →* button to the newest one. Finished playoff games also join the
**Played** tab, tagged, so a full season reads as one history.

**Scrims** — private comp captures from the browser app's scrim mode, read
straight out of this browser's IndexedDB (`owscout-capture`, the same store the
capture app writes) by the standalone **Scrims page** (`docs/scrims.html`),
reached via the League/Scrims side toggle in the top bar. Because `docs/capture/`
and `docs/` share an origin it can read them without any upload or server
round-trip. Each scrim (our team vs opponent, date, notes) lists its maps with
the captured hero comps; an empty state points to the capture app. Scrims are
deliberately invisible to the league dashboard and to the public site — league
maps stay public, scrim maps stay private. See §2.3 (Scrim mode) below for the
capture side.

**Player pages** — every player name on the site links to `#player=<nick>`, a
drill-in off the Players tab. It is the one **season-scoped** screen: it
aggregates every division in the payload, so a player who changed team or
division mid-season is one player with a real chronology rather than two
strangers. It carries a team timeline (first and last map played per spell,
rendered only when there is more than one), per-division stat rows against
same-role peers, mode and map win rates beside their teams' own rate, the hero
pool captures have proved, and their last ten maps with a stat line and hero.

Every rate refuses under a sample floor and prints its `n`: 5+ games for a mode
or map rate, 5+ captured games on a hero for a hero win rate. The floors are
load-bearing — the median player has 38 maps but 3 per map, and only about a
tenth of players have any captured hero attribution at all. So the hero
**pool** (share of captured rounds) shows at any sample size while the hero
**win rate** is usually blank, and the map table sits beside the team's own rate
because a player plays with the same four teammates: their map record is largely
their team's, and only the gap is a player signal.

### Cross-cutting conventions

- **Map ordering** — grouped into labelled mode blocks (Control → Escort → Hybrid
  → Flashpoint → Push → Clash), and within a block ordered by *league-wide*
  popularity, not the team's own games. Sorting a column drops the grouping and
  moves the mode onto each row as a tag, so the information is never lost.
- **Sortable tables** — click any header; numeric columns sort numerically.
- **Evidence weighting** — single-sample rows render at reduced opacity. `n` is
  always shown; a rate below the sample floor renders as a raw fraction rather
  than a percentage, so `1/2` never masquerades as "50%".
- **Capture sections are dated by their real range**, not by the code wipe.
  Every capture-based panel appends `captured <from> → <to>`, and when the whole
  sample predates the latest wipe it says so outright (`— all before the
  <date> patch`). A replay-code wipe *is* a patch, so a pre-wipe sample is
  pre-patch comp data; the earlier label ("captures since <wipe date>") claimed
  the opposite, which is the one direction of error that misleads a coach.
- **A recommendation is withheld rather than faked.** "Target these maps — their
  worst" only lists maps a clear margin *below the team's own baseline*, so an
  undefeated opponent yields "no clear weak map" instead of four maps they have
  never lost on. Likewise a team whose replay codes all died reads "nothing left
  to scout", never "fully scouted" off a 0-of-0.

## 1.3 Statistics

**Wilson lower bound** ranks comps and heroes instead of raw win rate, so a 1-for-1
record cannot outrank a 12-for-18 one. **Proportional win attribution** splits
credit when several comps appear in one map. **`choose_level`** walks a fallback
chain (map → mode → global) and stops at the first level with enough samples.

`comps top` prints a **mandatory bias-disclosure header** stating how many maps
the numbers rest on — the sample is captured replays, not the league, and the
output says so rather than letting the reader assume otherwise.

**Player season aggregates (`export.py`, on each roster row).** FACEIT reports
per-game stats and an elo snapshot for every player of every match, so these are
the one player signal that exists at *full* league coverage — no capture needed.
Each roster entry carries `elo` (the rating at their most recent map) and a
`stats` block of per-map averages: eliminations, deaths, damage, healing,
mitigation, plus `kd` taken on season totals rather than as a mean of per-map
ratios. The stat sample is counted separately from maps played, because hazard-A
rows (a played game whose stats came back zeroed) are stored NULL and must not
dilute an average. Verified against the raw feed: FACEIT's own `c1` equals
`i8`/`i9`, which is what confirms the eliminations/deaths mapping.

## 1.4 Independent audit (`verify_accuracy.py`)

Re-derives every stored fact from FACEIT's raw payloads by **different routes**
than the ingest pipeline — map/score/winner/rosters from the stats feed, ban
attribution by matching game→veto-slot on the map played rather than the ban set —
then diffs against SQLite. Agreement between two independent derivations is the
evidence the data is right; any mismatch prints in full.

---

# Part 2 — `owdb`

Reads hero compositions off the observer HUD of an in-client replay. Screen
capture is **read-only** (`dxcam`, falling back to `mss`); nothing is injected into
the game process.

## 2.1 Calibrate

Drag boxes over the ten HUD portrait slots once per resolution. Stored as an
`roi_profiles` row; recalibrating retires the old profile rather than deleting it,
so historic captures stay interpretable. Resolution is **derived from the grabbed
frame, never assumed** — a profile is only valid at the resolution it was made at.

## 2.2 The reference library

Matching compares a live crop against a stored portrait per hero. How those
references are obtained is the single biggest accuracy lever, and three findings
shaped the design:

**HUD refs, not gallery art.** Portraits from the hero gallery are a *different
rendering* than the observer HUD — the correct hero caps around 0.5 similarity,
with no threshold separating right from wrong. HUD-crop against HUD-crop of the
same hero scores ~0.99. So references are learned from the HUD itself
(`refs learn`, or the GUI's Learn window): cycle heroes in a custom game, scrub
the replay, confirm each crop.

**Per-team variants.** The HUD tints the whole portrait by team, and the tint is
not strippable — it bleeds through the entire crop, not just a border. Measured
across all 52 heroes and ten separation methods (hue-neutralised, V-channel,
grayscale, and combinations), **in every method the weakest correct match scored
below the strongest wrong match** — no threshold exists. So each hero carries a
blue (`a`) and a red (`b`) reference, and this is settled, not pending.

**Alignment tolerance — the biggest single win.** The matcher compared a reference
against a crop of *identical size*, giving `matchTemplate` exactly one position and
therefore zero tolerance for a pixel or two of ROI drift. Matching now crops a
**padded** ROI and slides the reference inside it across several scales. Measured
on real frames, 30 slots, both teams: mean confidence **0.717 → 0.877**, worst slot
**0.470 → 0.678**, 23 improved, 0 worsened, all 30 resolved. The "weak heroes" were
never weak — Mauga went 0.57 → 0.89 without re-learning anything. *Lesson: check
alignment before blaming the reference library.*

**`refs verify`** reports missing heroes and near-duplicate portraits by perceptual
hash. It caught a real bug: a "Wrecking Ball" blue reference that was byte-identical
to Torbjörn's.

**`refs coverage` — learned is not the same as validated.** A full library reads as
healthy while most of it has never faced a live frame. This ranks every hero+team
reference by how it has actually performed in captures (samples, worst and mean
confidence, corrections) and lists the ones never seen at all. Corrections matter
more than low confidence: a reference that is *confidently wrong* scores high and
would otherwise look healthy. `doctor` shows the summary line.

**Ref-harvest — corrections feed back into the library.** Every slot's portrait
crop is stored at capture (~5 KB each, about a megabyte per map). When the operator
fixes a misread in Review, the crop the matcher judged is a *confirmed* portrait of
the right hero on that team, so it is promoted into the library instead of being
discarded — the lowest-confidence appearance first, since that is the one the
current reference actually failed on. Harvested exemplars are stored as `review`
refs, which are **additive**: matching already takes the best score across all of a
hero's refs, so a bad harvest can only add a weak alternative, never destroy the
canonical portrait. The loop closes: every correction makes the next capture better
without any extra work from the operator.

**Custom heroes.** OW2 ships new heroes faster than FACEIT's roster updates, so
`heroes add` registers one under a namespaced `custom:` GUID that cannot collide
with a FACEIT one.

**Palette-mismatch diagnosis.** Refs are team-tint-specific (measured: no colour
transform separates the tints), so a user running colorblind/custom UI team
colours who imports a default-palette library scores ~0.2–0.5 against the 0.55
floor — slots stay `??` with nothing saying why. Capture now watches per-side
resolve rates and, when they fit that signature (one side blind while the other
is healthy, or both blind), names the actual cause in the log and points at
relearning — instead of letting it read as "the tool is broken".

**Shareable library (`refs export` / `refs import`).** The distribution model is
*curator learns once → ship the library → others only calibrate*. Export packs
every stored ref (canonical portraits **and** harvested exemplars — the
accumulated accuracy work is exactly what is worth shipping) plus any custom
heroes into one zip (~0.8 MB for 104 refs). A new machine calibrates its own ROIs,
imports the bundle, and is capture-ready — cross-resolution is fine because
matching rescales a ref to the crop it is compared against. Import is idempotent
(a ref already present by hero+state+variant+phash is skipped), and importing
before calibrating fails with a pointer rather than half-importing. Also in the
GUI: *Import hero library…* / *Export my library…*.

## 2.3 Capture

Snapshot-driven, not continuous. The operator navigates the replay and presses a
key at moments that matter. This is deliberate: OW caps replay playback at 2×, so
watching a 20-minute match still costs 10 minutes, whereas compositions are step
functions — jumping between the steps is strictly faster than sampling through
them.

**Keys** (all configurable, persisted in `app_settings`):

| Default | Action |
|---|---|
| `F8` | Snapshot the comp |
| `F7` | Next round / point captured |
| `1/2/3` | Pick the control sub-map directly (also switches OW's POV - measured harmless, the top bar is constant across POVs; `Ctrl+1/2/3` works too if you alt-tab and type numbers elsewhere) |
| `F6` | Cycle the control sub-map (fallback) |
| `F5` | Flip who is attacking |
| `F9` | Undo the last action - snapshot **or** round marker (LIFO: snapshots taken after a marker come off first, so an undone round can never leave orphaned round tags in the data) |
| `ESC` | Finish |

The hooks **do not suppress the keypress**, so anything bound also reaches
Overwatch. That rules out most of the keyboard — number keys switch player POV,
space pauses — and is why the defaults are F-keys, which OW leaves unbound. The
dialog rejects duplicate bindings and `ESC`.

**On-screen overlay.** Always-on-top, showing the key legend and the last snapshot
result, so nothing requires alt-tabbing out of the game.

**Dedupe.** A snapshot identical to the previous one is dropped. Two refinements:
a snapshot differing *only* by slots degrading to `??` is also dropped (a worse
read is not new information), while a round or sub-map change lets an identical
comp through (the same comp on a new point is a real observation).

**Auto side-detection.** Picking which team is on the left of the HUD used to
be a manual, error-prone step — get it wrong and every side-dependent stat is
mirrored. Capture now reads the player-name bars under the portraits with
Windows' built-in OCR (no external install) on the first snapshot and matches
them against the two FACEIT rosters. Measured on real frames: correct on 3/3,
**including a player whose battletag (WHITEBEARD) shares nothing with any FACEIT
nickname** — only the two-roster contrast has to win, not every name, so
battletags are not required data. Two strict gates (orientation lead ≥100 and
≥3 individually-strong name matches) exist because a garbage frame cleared the
naive margin — noise must be refused, never guessed. Auto is the GUI default;
the manual pick remains as the override, and in auto mode nothing is written
until a confident read happens.

**Round, sub-map and phase tagging.** On control maps the operator must declare
the starting sub-map with `F6` before any snapshot is accepted — the first
sub-map varies per lobby, and a silent default would tag every round-1 snapshot
with a guess. After that, advancing a round auto-selects the next unplayed
sub-map and `F6` cycles the remaining ones. Attack/defend is derived for Escort/Hybrid — red attacks round 1, teams flip
each round — but from **round 3 the attacker is decided by time bank**, not parity,
so the operator confirms with `F5` and the resolved phase is stored per
observation. Analysis prefers the stored value and only falls back to the parity
guess for older captures.

**Temporal smoothing** takes the modal hero per slot across a window, so one bad
frame cannot corrupt a slot.

**Scrim mode in the browser capture app** (`docs/capture/`, §0 / the Capture
tab's segmented League↔Private scrim switch) is the same snapshot pipeline with
no FACEIT match behind it. Our team, opponent, date and notes are saved into a
local scrim session (IndexedDB store `scrims`); each map you capture — picked
from a static map list, optionally with a replay code — goes to `scrim_maps`
with observations, hero crops and scoreboard reads exactly like a league map,
just with `side_a_team`/`side_b_team` labelled from the scrim's teams. Sides are
always manual (there are no rosters to auto-detect against). Records are
**local-only**: never claimed, never published, never merged into
`data/captures/` — they surface only on the **Scrims page** (`scrims.html`),
which reads the same IndexedDB from the shared origin. Export/Import buttons back the
scrims up as a JSON bundle. The replay-code field is optional but a **known
FACEIT league code is hard-blocked**: it stays public, so the app explains why
and offers to switch over to League capture and load that code instead.

**Onboarding — the first-capture tour.** Both apps (league and scrim) open with
a guided, non-blocking walkthrough while nothing has been captured yet: six
steps that point at the actual controls (with a highlight ring around them),
advance automatically as each step's action completes, and can be stepped back
through. A revisit resumes at the first unfinished step; dismissal is remembered
per app (existing contributors are skipped). A first-time visitor also gets a
welcome header and a pulsing *Auto-calibrate* button after screen share;
publishing the first capture fires a celebration toast with a direct link to
the dashboard's leaderboard. Returning contributors see a welcome-back strip
with how many maps this browser has published and how many are pending. The
tour yields to fullscreen capture and comes back when it ends.

**Auto-calibrate is preview-first.** The one-click scan hunts candidate boxes
over the live screen share and shows them with an X/10 confidence verdict
("this looks right" / "usable but check the boxes" / "placement is likely
off") — **nothing is written until you click *Use these boxes***, so a bad scan
cannot silently lock a bad ROI. Retry and clear are one click each, and the
preview disappears when screen sharing stops.

**WIP badges.** Experimental OCR reads wear an amber ⚠ tag with a tooltip
naming the feature: the scoreboard and score reads in the league app;
scoreboard, auto side-detection and screenshot import in the scrim app.
Known-limits features wear their warning on the button rather than being hidden.

## 2.4 Integrity and the review gate

**Banned-hero detection.** A resolved hero that was banned this map is impossible,
so it means the ROI profile is stale. Those observations are skipped, and a run
exceeding a 2% hit rate fails outright with a message to recalibrate.

**No auto-greenlight.** Captures are written as **drafts**. Exports read only
finalized maps, so nothing reaches the dashboard without the operator looking at
it. Review (GUI or `owdb drafts`) groups observations by round and sub-map,
flags low-confidence comps, and offers **in-review correction**: `correct_hero_in_map`
replaces a misread across an entire map side and re-canonicalises the affected
comps. Finalize greenlights; discard drops the draft.

**`owdb doctor`** health-checks calibration, reference coverage and pending
drafts in one command.

## 2.5 Comp analysis

**Comp identity is a family, not an exact five.** Two lineups are the same comp if
they share **≥4 heroes**, or **exactly 3 including the same tank** — the tank
anchors identity in 5v5. Because that relation is not transitive, clustering is
greedy: the most-frequent lineup anchors a family and absorbs the lineups matching
it.

A mid-map change is therefore either a **flex** (same comp) or a **core** swap
(different comp), and the two mean different things when scouting.

**Swap triggers.** Each swap records the enemy lineup at that moment. Heroes
present in at least half a swap's occurrences, *and* more often than in the
team's own baseline (their overall enemy-lineup presence rate across every
observation, swap or not — see `aggregate_swaps` in `owdb/scout.py`), are
reported as its trigger — "they answer a D.Va with this". Baseline subtraction
means an enemy hero present in every game no longer qualifies just for being
omnipresent. Read triggers as directional, not causal — this only rules out one
false-positive shape, it does not prove causation.

**Segments.** A segment is the attack/defend phase on Escort/Hybrid, the sub-map on
Control, and the whole map otherwise. Every per-map breakdown is per segment, and
each keeps both the comp they **opened** on and the one they **settled into**.

## 2.6 The scouting report (§3 renders it)

`team_scout` produces, per team: overall comp families; per map → per segment
opening and settled comps; recurring swaps with triggers, both overall and
per map; hero pool counted in **rounds** with roles attached; and ban-response —
how their opening comp shifts when a given hero is banned.

## 2.7 GUI — removed, not the capture path

The native Windows Tk GUI that used to live in `owdb/gui.py` was **removed in
2026-08-08** — unmaintained, not distributed, superseded by the browser capture
app at `docs/capture/` (zero-install, runs in any modern browser via
`getDisplayMedia` + tesseract.js). That app is the only supported capture path.
Its tested first-run helpers (ETA text, the read-only "faceit DB empty?" check,
the "Step N of 3" setup hint) survived the removal in `owdb/firstrun.py`.

---

# Part 2.8 — Contributing scouting data

The tool is built to take captures from many people, so the unit of contribution
is the raw **observation**, not a finished report. Two summaries cannot be merged,
and a summary is frozen against the analysis that made it; raw observations merge
cleanly and are re-derived by whatever the analysis does today.

## The workflow

```
Open docs/capture/     # the browser capture app - share screen, calibrate, capture, review
Publish my captures    # uploads to the OPEN endpoint under your chosen name -
                       # the site rebuilds itself within a couple of minutes
```

Open access, zero setup: the tool generates an identity token silently on first
publish, and the first install to upload under a display name claims it — so a
stranger cannot overwrite your file, yet nobody is ever issued keys or needs an
account. The endpoint (infra/upload-worker) holds the only GitHub credential as
a server secret, forces the contributor identity from the claim (never from the
file), caps size, rate-limits per name, and writes exactly one path per name.
Build-time validation and git history remain the real gates. The curator's
direct GitHub-token path and the manual file relay both still work as fallbacks.

The build merges every contributor file and rebuilds the page. Only **finalized**
maps are exported: the review gate is what keeps unvetted data out of a shared
dataset.

## Identity, and why it is the load-bearing part

`map_instances.id` is a local autoincrement, so Alice's map #20 and Bob's map #7
can be the same real game with nothing in the row to say so. Merging on it
double-counts — measured on real data, 8 maps became 9 and 16 rounds became 20,
inflating every rate that divides by them. The exchange format therefore keys on
FACEIT's `(match_id, game_no)`, which is identical on every machine, and **local
ids never leave the machine**.

This also gives the dataset an enforced property against bad data — enforced at
merge time, not merely implied by the format: every contributed map must name a
`(match_id, game_no)` FACEIT has a record of, any team name it carries must be
one of the two teams FACEIT says played (the signature of scouting the wrong
replay code), and its replay code must agree when FACEIT published one. Rejected
views are dropped loudly, per view — one contributor's bad view of a real game
never blocks another's good view of it.

## When two people scout the same map

**First submission wins.** That contributor owns the map, and may update their own
submission — otherwise re-scouting a map you fixed in Review would be discarded.
Anyone else's view is *ignored but retained*: ignoring is reversible and rejecting
is not, so a broken first submission can be replaced from data already in hand.

Priority comes from the **commit that added the file**, never from timestamps
inside it — a contributing machine controls its own clock. (This is why CI checks
out with `fetch-depth: 0`; a shallow clone would make every file look equally old
and fall back to alphabetical order.)

Contributions are self-describing: they carry any operator-added heroes they
reference, so a build server merges with nothing but the FACEIT roster and the
files themselves.

## The curator override

First-wins' honest cost is that quality tracks who was fastest: a bad first
submission (wrong left team, stale calibration) locks a map. The escape hatch is
`data/captures/overrides.json` — a committed list of `{match_id, game_no, prefer,
reason}` entries that reassign one map to a named contributor's view. Because it
is a committed file, using it is an auditable act only the repo owner can merge,
not a hidden knob. An override naming a contributor with no view of that map
falls back to first-wins rather than making the map vanish, and a malformed file
degrades to first-wins rather than blocking the build.

## The admin capture panel

The worker also exposes an admin view of capture activity, gated **server-side**
by the `ADMIN_IDS` environment variable (comma-separated Discord ids) — the
caller's own session flag is only a UI hint and never grants access. *Live
scouts* (`/admin/claims`, forwarded to the claim room's Durable Object — the
single source of truth for live locks) shows who currently holds a scouting
claim and for how long; *recent contributors* lists every committed file with
its owner, login status, last upload and map count, and drills into one
contributor's submission (`/admin/contributor`) — read from GitHub, so the admin
sees exactly the same data the build merges. The capture app renders both
panels, for admins only.

---

# Part 3 — The scouting page, section by section

Reached via **Scout a team**. Sections above the fold come from captured replays;
the rest from FACEIT's draft data. The **Prep sheet** toggle condenses all of it
to one screen of decisions — ban candidates by round share, what they will ban,
their first ban when drafting first, what they will pick, which maps to target,
their comps, and how their opener moves under a key ban. Its URL carries the team
(`#prep=<Team>`), so a link pasted into Discord lands a teammate on the right
sheet.

**Common comps** — the comp families they actually run, with maps played and W-L.

**Hero pool** — split into Tank / Damage / Support cards, counted in **rounds, not
maps**. A hero played every round is a staple; one played for a single point is
not; counting maps flattens both to "1 map".

**Map scouting** — one collapsible card per map, mode-grouped. Openers on the left
by segment, the **swaps seen on that map** on the right. Where they changed off
their opener, only the heroes that *actually changed* are shown — repeating four
unchanged portraits buries the one that matters.

**Common swaps** — recurring changes across all maps, led by the trigger.

**When a hero is banned** — how their opening comp shifts under a given ban.

**Preferred bans / first bans** — overall and when they draft first.

**Maps — picks & win rate** — mode-grouped, popularity-ordered.

**Signature setups** — maps they both *picked* and *banned first* on: a fully
self-chosen draft, so a repeated map with a strong win rate is likely a rehearsed
strategy. Now also shows the comp they actually run there.

**Matches** — full match cards in a scrolling box, so an unbounded match list
can't push the analysis below it off the screen.

**Win rate by banned hero** — one block per hero with two rows: when *they* banned
it, and when the *opponent* did. Banning a hero and having it taken from you are
different situations and averaging them hides both. Sorted by win %, direction
toggleable.

**Counter-bans** — genuine responses only: the opponent banned first and this team
replied second. Cases where they banned first are excluded, because those aren't
responses.

**Bans on maps they pick** — ordered by ban count, which also surfaces their
most-picked map first.

**Draft simulator (beta)** — the collapsed simulator from §1.2, detailed here
because the sections above all feed it. Pick two teams and walk a draft (Game 1
map + the ban rotation); suggestions are driven by each team's real history —
map-pick frequency, per-map and overall ban counts — on a tested pure decision
layer, and every auto suggestion carries its reasoning:

- **Why <map>?** / **Why <hero>?** sit on every auto-suggestion card in plain
  language, recomputed as the draft state changes — never hover-only. Map
  claims say "their most-picked <mode> map"; ban claims say "most-banned
  overall" or "most on this map", and a ban repeated well above the division
  rate is marked **★ signature ban**. "The most" claims are computed against the
  *current* legal suggestion set, so an override is never mislabelled as the top.
- **The evidence is one click away.** Each suggestion's why-line also offers
  the backing replay codes (preferring bans seen on this very map) in a
  popover — a suggestion points at the games it came from rather than asserting.
- **A hint is labelled a hint.** A read resting on a single case or a thin
  sample appends "a single case, not a pattern" / "this read is a hint, not a
  pattern" instead of presenting a guess as a finding.
- **The legend is always visible.** Chip counts are defined inline ("3× on a
  map chip = times that team has picked it this season"; "2× here · 5× on a ban
  chip = bans on this map · this season"; "★ = signature ban"), along with the
  rules of the draft ("A team can't repeat its own ban down a line") and how
  much data each read rests on (ban reads use the most recent N maps; map picks
  stay full-season).

**Team Compare** — two teams side-by-side, reached from the Scout page's
"Compare…" button or the deep link `#compare=<A>|<B>` (both team names
URL-encoded, pipe-separated; nav highlights Teams). A radar across **eight
axes** sits over a two-column comparison. Five axes are pure FACEIT: map win
rate, map pool breadth, ban pressure (bans per game), pick agency (maps
picked per game) and **Team Eff** (mean of the roster's qualified Eff ratings —
three or more players at the 5-map floor, else honest "not enough"). The three
capture axes — comp diversity (family count), hero pool breadth (distinct
heroes above a 5%-of-rounds floor) and adaptability (swaps per captured map) —
render only where someone captured that side, and a team with no captures reads
as dimmed rather than inflated. Values are capped per axis (fixed caps, not
division-relative), so two weak teams stay two small shapes; an axis neither
side sampled is dropped with a note. Under the radar, each team gets a card —
**Maps** (mode-grouped win-rate table), **Bans** (what they value above the
division rate), **Captured comps** (top families + hero pool) and **Top by
Eff**. The **perspective toggle** flips which side is "you" (and which is
"them"), re-reading the ban tables from that team's angle. A **Head to head**
list ties the pair together — their matches with clickable details.

---

# Part 4 — Design rules

**Testable core, thin runtime shell.** Every non-trivial decision lives in a pure
function taking plain data. The parts that need a GPU, a display or the game are
thin shells marked no-cover. This is why matching, comp identity, phase derivation
and swap detection are all unit-tested without cv2 or Overwatch.

**Two databases, one direction.** owdb never writes to `faceit.sqlite3`; it
ATTACHes it read-only. Cross-database foreign keys don't exist in SQLite, so
FACEIT keys are stored as plain validated columns.

**Additive schema.** All DDL is `CREATE TABLE IF NOT EXISTS` plus in-place
migrations; upgrading never drops operator data.

**ASCII-only CLI output.** The Windows console is cp1252 and *crashes* on arrows,
×, and emoji. Console strings stay ASCII; the GUI and dashboard are free to use
whatever they like.

**Say what the number rests on.** Sample counts are shown, thin evidence is
visually weakened, sub-threshold rates render as fractions, and comp statistics
carry a bias header. The tool is a scouting aid on a small sample and the
presentation is built to keep that visible.

---

# Part 5 — Known gaps

- **Per-player hero pools depend on capture coverage.** Name OCR *is* wired (the
  scout page renders player pools from HUD attribution), but only for maps someone
  scouted — so in a division with no captures the pools are empty. Elo and per-map
  stats do not have this problem: they come off FACEIT's own feed for every player
  of every match (see §1.3).
- **Map-name verification is stubbed** — the OCR hook returns `None`, so map
  mismatch reads "not checked". It is unclear whether the map name is reliably on
  the observer HUD at all.
- **Most of the library has never been checked against a live frame** (currently 88
  of 104 hero+team refs). They are unvalidated rather than known-bad; `refs
  coverage` tracks this and it shrinks with every capture.

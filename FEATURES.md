# faceit-scout — complete feature reference

Two packages that feed one website.

**`faceit_sync`** ingests FACEIT League (Overwatch 2) match data into SQLite and
renders it as a self-contained dashboard. **`owscout`** watches in-client replays,
reads the hero portraits off the observer HUD, and turns them into composition
scouting that the same dashboard displays. They share nothing but a read-only
database link and one JSON file.

*196 tests, mypy clean across 44 files.*

---

## 0. How the pieces fit

```
FACEIT API ──fetch──► faceit.sqlite3 ──export──► docs/index.html   (the live site)
                            │                          ▲
                       (read-only)                     │
                            ▼                    (merged at build)
OW replay ──capture──► owscout.sqlite3 ──publish──► data/captures/<you>.json
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
   report. `owscout_comps.json` is generated at build time and is NOT committed —
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

### Tabs

**Overview** — division summary, most-picked maps, ban leaders, data-quality
counters (walkovers, restarts, DC'd games, attribution coverage).

**Scout a team** — the main working view. Detailed in §3.

**Draft simulator** — a manual scenario planner. Pick two teams and walk a draft;
each team's real history drives the suggestions (map-pick frequency, per-map ban
counts, overall ban rates), with already-banned heroes excluded from the picker.

**League meta** — cross-division hero ban rates, ban-by-role split, map
popularity, and attacking-first win rate per map (Escort/Hybrid only, since
mirrored modes have no attacking side).

**Matches** — every match card: per-map bans in draft order, replay codes inline
and click-to-copy, expandable rosters, newest/oldest sort, and the match date.

### Cross-cutting conventions

- **Map ordering** — grouped into labelled mode blocks (Control → Escort → Hybrid
  → Flashpoint → Push → Clash), and within a block ordered by *league-wide*
  popularity, not the team's own games. Sorting a column drops the grouping and
  moves the mode onto each row as a tag, so the information is never lost.
- **Sortable tables** — click any header; numeric columns sort numerically.
- **Evidence weighting** — single-sample rows render at reduced opacity. `n` is
  always shown; a rate below the sample floor renders as a raw fraction rather
  than a percentage, so `1/2` never masquerades as "50%".

## 1.3 Statistics

**Wilson lower bound** ranks comps and heroes instead of raw win rate, so a 1-for-1
record cannot outrank a 12-for-18 one. **Proportional win attribution** splits
credit when several comps appear in one map. **`choose_level`** walks a fallback
chain (map → mode → global) and stops at the first level with enough samples.

`comps top` prints a **mandatory bias-disclosure header** stating how many maps
the numbers rest on — the sample is captured replays, not the league, and the
output says so rather than letting the reader assume otherwise.

## 1.4 Independent audit (`verify_accuracy.py`)

Re-derives every stored fact from FACEIT's raw payloads by **different routes**
than the ingest pipeline — map/score/winner/rosters from the stats feed, ban
attribution by matching game→veto-slot on the map played rather than the ban set —
then diffs against SQLite. Agreement between two independent derivations is the
evidence the data is right; any mismatch prints in full.

---

# Part 2 — `owscout`

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
| `F6` | Cycle the control sub-map |
| `F5` | Flip who is attacking |
| `F9` | Undo the last snapshot |
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

**Round, sub-map and phase tagging.** Control maps start on a sub-map; `F6` picks
from the not-yet-played ones and advancing a round auto-selects the next unplayed
one. Attack/defend is derived for Escort/Hybrid — red attacks round 1, teams flip
each round — but from **round 3 the attacker is decided by time bank**, not parity,
so the operator confirms with `F5` and the resolved phase is stored per
observation. Analysis prefers the stored value and only falls back to the parity
guess for older captures.

**Temporal smoothing** takes the modal hero per slot across a window, so one bad
frame cannot corrupt a slot.

## 2.4 Integrity and the review gate

**Banned-hero detection.** A resolved hero that was banned this map is impossible,
so it means the ROI profile is stale. Those observations are skipped, and a run
exceeding a 2% hit rate fails outright with a message to recalibrate.

**No auto-greenlight.** Captures are written as **drafts**. Exports read only
finalized maps, so nothing reaches the dashboard without the operator looking at
it. Review (GUI or `owscout drafts`) groups observations by round and sub-map,
flags low-confidence comps, and offers **in-review correction**: `correct_hero_in_map`
replaces a misread across an entire map side and re-canonicalises the affected
comps. Finalize greenlights; discard drops the draft.

**`owscout doctor`** health-checks calibration, reference coverage and pending
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
present in at least half a swap's occurrences are reported as its trigger — "they
answer a D.Va with this". *Known limitation: there is no baseline subtraction, so
an enemy hero present in every game can appear as a trigger. Read triggers as
directional, not causal.*

**Segments.** A segment is the attack/defend phase on Escort/Hybrid, the sub-map on
Control, and the whole map otherwise. Every per-map breakdown is per segment, and
each keeps both the comp they **opened** on and the one they **settled into**.

## 2.6 The scouting report (§3 renders it)

`team_scout` produces, per team: overall comp families; per map → per segment
opening and settled comps; recurring swaps with triggers, both overall and
per map; hero pool counted in **rounds** with roles attached; and ban-response —
how their opening comp shifts when a given hero is banned.

## 2.7 GUI

Everything above behind buttons, for operators who never touch a CLI. Worker
threads with a queue drained on the Tk main loop, so the window never freezes and
no Tk call happens off-thread.

Notable: the code list **filters by team** (scouting happens one opponent at a
time); a **sync-freshness banner** turns amber when the faceit DB hasn't been
synced for a day, because a stale database hides every code published since and
looks identical to "no new matches"; and Publish states plainly that
`owscout_comps.json` is the file to commit.

---

# Part 2.8 — Contributing scouting data

The tool is built to take captures from many people, so the unit of contribution
is the raw **observation**, not a finished report. Two summaries cannot be merged,
and a summary is frozen against the analysis that made it; raw observations merge
cleanly and are re-derived by whatever the analysis does today.

## The workflow

```
owscout gui            # calibrate, learn portraits, capture, review, finalize
Publish my captures    # writes data/captures/<you>.json
git commit + push      # (or open a PR) - this is what reaches the site
```

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

---

# Part 3 — The scouting page, section by section

Reached via **Scout a team**. Sections above the fold come from captured replays;
the rest from FACEIT's draft data.

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

---

# Part 4 — Design rules

**Testable core, thin runtime shell.** Every non-trivial decision lives in a pure
function taking plain data. The parts that need a GPU, a display or the game are
thin shells marked no-cover. This is why matching, comp identity, phase derivation
and swap detection are all unit-tested without cv2 or Overwatch.

**Two databases, one direction.** owscout never writes to `faceit.sqlite3`; it
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

- **Player-name OCR is not wired** (SPEC §8.2), so per-player hero pools stay
  empty. Comps are captured per *team*, not attributed to individuals.
- **Map-name verification is stubbed** — the OCR hook returns `None`, so map
  mismatch reads "not checked". It is unclear whether the map name is reliably on
  the observer HUD at all.
- **Most of the library has never been checked against a live frame** (currently 88
  of 104 hero+team refs). They are unvalidated rather than known-bad; `refs
  coverage` tracks this and it shrinks with every capture.
- **Swap triggers lack baseline subtraction** (see §2.5).
- **The `.exe` exists but has only been smoke-tested.** `pyinstaller owscout.spec`
  builds a standalone ~76 MB `dist/owscout.exe`; it launches, keeps its data next
  to the exe, and bundles every dependency — but a full capture session from the
  frozen build (dxcam grab, hotkeys, calibration UI) hasn't been exercised yet.
  A new user's setup: download the exe + ref bundle → calibrate → import → capture.

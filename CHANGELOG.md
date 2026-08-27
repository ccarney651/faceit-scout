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

## 2026-08-27

### Added
- **Season 9 is frozen at `/s9/`**, linked from a new `/archive.html` and from
  the footer of every page. It is a point-in-time export — standings, teams,
  players, League meta and all 274 captured comps exactly as they stood when the
  last match was played on 17 August — and it is never rebuilt. Read it as
  history: the rosters are the ones that played, and its replay codes were
  invalidated by later patches.
- **The site says which season it is showing.** The header carries the season
  beside the wordmark, read from the data the page was built from rather than
  from the build flag, so a fallback is visible rather than silent.
- **A finished season explains itself.** Between seasons there is nothing to
  capture — every code from the season that just ended predates the patch that
  ended it — and the hero slot used to render empty there, which reads as a
  broken site rather than a finished one. It now says so, and names when the
  next season starts until that date passes.
- **SA and OCE are supported regions**, ready for Season 10's SA Master and OCE
  Master. Inert until such a championship exists, which is why it landed now
  rather than on cutover day.

### Changed
- **A pinned season with no data no longer fails the build.** `export --season
  s10` against a database with no Season 10 matches used to write a 0-byte file
  and exit 1; CI runs under `bash -e`, so that failed the whole job before the
  publish step and froze the site silently. The pin now falls back to the newest
  season that does have matches, which means it can be flipped to `s10` at any
  time and the site switches itself over on the first ingested Season 10 match.
  An explicit pin still wins whenever it can be satisfied.
- **`--region` matches region names exactly rather than by first letter.** With
  four regions the old prefix test was one addition away from resolving the
  wrong one, and a wrong region narrows the export silently rather than failing.
  The CLI's choices are now derived from `export.REGIONS` instead of restating
  them, and a test pins `tools/build_capture_data.py`'s separate copy to the
  same tuple.
- **The `owscout-capture` IndexedDB name is kept permanently.** The promise to
  revisit it at the Season 10 cutover is closed as won't-do: the name is
  invisible to users, and renaming it would orphan every contributor's learned
  refs, unsent captures and scrim history.
- **The Season 10 cutover runbook is resequenced, and its trigger is corrected.**
  Season 9 finished on 2026-08-17. The original runbook fired "once S9's last
  match finishes", which is now demonstrably wrong: no S10 championship exists
  yet, so flipping the live export to `--season s10` today would publish an empty
  site. The trigger is **S10 having real results**, and until then the live
  export stays pinned to `--season s9` — which also keeps trickling S10 rows off
  the live site on its own.

  `specs/2026-08-10-season10-cutover-design.md` gains a §6 recording what of the
  design actually shipped (season filtering and capture season-scoping are live
  and deployed; the frozen archive and SA/OCE region support are not), and
  regroups the steps by what gates them: unblocked today, gated on S10 rooms
  existing, gated on S10 results. Two corrections came out of it — the frozen S9
  archive must be built from CI's DB (`docs/faceit.sqlite3.gz`), not the local
  one, or it violates invariant 2; and the runbook lives in that design document,
  not in `CLAUDE.md`, which the 2026-08-11 documentation refactor emptied.

  Documented alongside it: relegation matches are unreachable by the keyless
  crawler (it is scoped to a championship it was handed), which makes them the
  only live replay codes left in the league and the only record of who is in
  which S10 division (ingesting them was considered and deliberately skipped);
  and `team_rosters` in the capture feed has no season filter, so its measured
  zero-collision guarantee does not automatically survive a second season
  entering the pool.

### Fixed
- `ARCHITECTURE.md` §10 was missing the 2026-08-18 code wipe from its list of
  recorded wipes, and still described the cutover as deferred until Season 9
  finishes.

## 2026-08-24

### Added
- **Every player has a page.** `#player=<nick>` is a new drill-in off the
  Players tab, reached by clicking a player name anywhere on the site — the
  Players tab, team roster cards, and match scoreboards. It carries their team
  timeline (with real first/last dates per spell, so a mid-season swap reads as
  "Alpha until 2026-07-08, Dystopia since 2026-07-10"), per-division stat rows,
  mode and map win rates beside their teams' own, their hero pool, and their
  last ten maps.

  Unlike every other screen it is **season-scoped, not division-scoped**: it
  aggregates every division in the payload, which is the only scope in which a
  player who moved division mid-season is one player rather than two. The
  headline elo and Eff follow their *current* division, not the one they played
  most maps in.

  **Every rate refuses under a floor**, and the floors are the feature rather
  than a caveat. Measured against the live data: the median player has 38 maps
  but only 3 per map and 8 per mode, so mode is the headline grain and map the
  drill-down, both needing 5+ games. Only 128 of 1187 players have any captured
  hero attribution at all, at a median of 8 games — so per-hero **win rate**
  needs 3+ captured games on that hero and is blank for most people, while
  the hero **pool** (share of captured rounds) shows at any sample size. The
  win column fills in as capture coverage grows, with no rewrite.

  Map rows also carry the team's own rate, because a player plays with the same
  four teammates: their map record is largely their team's, and the useful read
  is where the two diverge — which is where someone was subbed in or out.

### Changed
- **The inlined payload's per-game roster rows now carry `mit`**
  (`matches[].games[].rosters[].players[].mit`, from `round_players.damage_mitigated`).
  Without it a Tank's per-map table would omit the stat their season card leads
  with. It stays `null` on a zeroed row (data hazard A) rather than coalescing
  to 0, which would claim a measurement that was never taken. Costs about
  512 KB raw (~60 KB gzipped) on a 9.1 MB page.

---

## 2026-08-20

### Fixed
- **Text on a coloured fill is readable again in every palette.** Eight rules put
  `#fff` on the accent fill, which is the light palette's answer written down and
  then used everywhere. In the seven dark
  palettes it failed WCAG AA outright - 1.93:1 on Teal, 2.11:1 on Overwatch,
  3.08:1 on the default - and the worst of them was the "Open League capture"
  button, the single largest element on both paused scrim pages. They read
  `var(--on-accent)` now, which the palettes define as the accent's partner and
  which measures 4.7-9.5:1. The same fix reached the W/L pips, where a 10px
  white letter sat on raw `--good` at 2.54:1; the fill is darkened to carry it.

  One of these was a typo rather than an oversight: the draft-simulator
  probability bar asked for `color-mix(... var(--bad) 78%, #000 0%)`, and naming
  both percentages makes them normalise - 78/(78+0) is 100% - so the darkening
  it depended on had silently never happened.

- **Icon buttons on the capture pages are one line again.** `.ticon` was
  `display:block`, so all sixteen buttons that pair an icon with a label
  (Refresh, Skip, Auto-calibrate, Control panel, Fullscreen, Exit, Fix reads)
  stacked the icon above the text and stood twice as tall as their neighbours,
  breaking the alignment of every row they sat in. Every use site already set
  `vertical-align`, which does nothing to a block box.

- **A palette chosen anywhere now applies on the scrims viewer.**
  `docs/scrims.html` was the only themed page that never read the shared
  `owdb.palette` key, so it stayed indigo while the other three re-themed. It
  now has the same pre-paint bootstrap and picker as its capture-side twin.

- **The modal viewport fix reached the League capture page.** `scrim.html` had
  grown a max-height and a scrolling body so a tall dialog keeps its buttons
  on screen; `index.html` never got it, and in a short browser window its
  confirm buttons could sit below the fold.

- **Scouting a team now reads its playoff run.** Team-facing panels were built
  from the regular season alone, so the moment the bracket started, a team's
  comps, ban tendencies, replay-code links and scouting-coverage row stopped at
  the end of the group stage - hiding 150 finished matches and 431 replay codes
  league-wide, which are both the most recent form there is and the freshest
  capture targets on the site. They now read every match a team has actually
  played. Standings, power rankings and the League meta panel are deliberately
  unchanged: a playoff result must not move a regular-season table, and the meta
  panel's counts stay comparable with the header summary.

  On a Combined view the effect was total rather than partial - the merged view
  never carried the bracket at all, so no playoff game reached the capture
  work-list and a playoff match page could not be opened from one.

  Measured on the current season: EMEA Master went from 2 teams with a live
  capture target to 8, and every division gained under-covered maps that had
  been invisible.

### Changed
- **One design system instead of four that resembled each other.** The four
  pages had drifted the way pages do when each keeps its own copy:

  - Forty-two rules - the shell, the whole table and chip layer, the stat
    tiles, the bar rows - were written out byte-for-byte in both the dashboard
    and `docs/scrims.html`. They live in `docs/theme.css` once now. Two had
    already drifted apart before the move (`.poolgrid` was auto-fit/210px on
    one page and auto-fill/240px on the other; `thead th` had gained a nowrap
    on one only), which is what duplication buys.
  - `.wl` meant two different components: a row of filled W/L pips on the
    dashboard, a coloured W-L-D count with a draw state on scrims. The scrims
    one is `.wld` now - two components, two names.
  - Corner radii were twelve different values across the four pages
    (3,4,5,6,7,8,9,10,11,12,20,999px). There is a four-step scale now -
    `--r-sm/-md/-lg/-pill` - and every page reads it, including the pop-out
    control panel, which is a separate document and so gets the scale passed
    in alongside the colours it already received.
  - Breakpoints were six (640/680/720/820/900/980). Every media query is now on
    the documented pair, 640px (phone) and 900px (tablet).
  - The two capture pages are the same tool pointed at two competitions, but
    their `button` was 6px/7-11px on one and 7px/9-13px on the other, so every
    control changed size when an operator moved between them. Shared selectors
    are identical.

  `tests/test_ui_consistency.py` holds each of these as an invariant, so the
  next copy-paste fails a test rather than surfacing months later.

### Removed
- Unreferenced CSS: an earlier draft-simulator layer (`.probbar`, `.simblock`,
  `.simrow`, `.modelbl`, `.simnext` and children), `table.blocks tr.blk`, and
  `.lock` on the League capture page. None was reachable from any consumer.

---

## 2026-08-19

### Added
- **The replay code can be read off the screen.** Overwatch prints it on the HUD
  banner the whole time, and it was being typed by hand - six random characters,
  mid-scrim. A *Read code* button on the scrim panel now fills the field from
  the screen, and one on the league page checks the code you have selected
  against the one actually on screen.

  That second case is the point. The league picker is a dropdown of lookalike
  six-character strings; picking the wrong one attributes every comp captured
  afterwards to the wrong match, teams and players, publishes it, and gives no
  signal that it happened. The read is checked against the division's feed, so
  an exact match selects it, a unique one-character miss is offered as a
  correction, and anything else changes nothing.

  Codes turn out to be **Crockford Base32** - measured across all 4328 in the
  database, the alphabet is the ten digits plus A-Z without I, L, O and U, each
  of the 32 symbols appearing 750-850 times. That is a published standard whose
  exclusions exist for exactly our reason (I and L confusable with 1, O with 0),
  so the OCR correction rules come from its spec rather than from guesswork.

  Measured 12/12 correct with **zero wrong reads** across twelve real frames in
  two window modes, and confirmed live on 2026-08-19 against `SZDPQQ`.
  Zero-wrong is the gate that mattered: a refused read costs a retry, a wrong
  one is a corrupted record that looks correct forever. A read that cannot be
  validated is discarded rather than guessed at, and on the scrim page - which
  has no feed to check against - nothing is ever recorded without the operator
  seeing it in the panel field first.

  The code plate is semi-transparent, so no single contrast setting works: the
  boost that read every stored frame returned an empty crop on the first live
  one, where no boost at all read it perfectly. Each read therefore runs three
  preprocessing passes and takes the answer only when they agree. Disagreement
  refuses, which is also the only workable guard against the one failure the
  validator cannot catch - a crop clipping a glyph, yielding six valid
  characters that are the wrong code.

### Confirmed live
- **2026-08-19, `SZDPQQ`, Ilios, The Hyenas vs Telacy Navy.** Read correctly
  with the right code already selected, and - with a deliberately wrong code
  selected - it read the screen and moved the selection back to the right match.
  That second case is the entire point of the feature.
- **Every resolution from 1280x720 to 3840x2160 reads correctly**, zero wrong
  (`tools/real_frame_eval/`). The crop is expressed as fractions of the
  calibration box, which is itself fractions of the frame, so scale-invariance
  is structural rather than tuned - this measures that it actually holds.
  Aspect ratios other than 16:9 are **not** covered: the HUD fractions assume
  it, and no ultrawide frame exists to test against.

  The code plate is semi-transparent, so no single contrast setting works: the
  boost that read every stored frame returned an empty crop on the first live
  one, where no boost at all read it perfectly. Each read therefore runs three
  preprocessing passes and takes the answer only when they agree. Disagreement
  refuses, which is also the only workable guard against the one failure
  `foldCode` cannot catch - a crop clipping a glyph, yielding six valid
  characters that are the wrong code.

### Changed
- **The capture panel is the scrim workflow; the page is setup only.** The page
  could still add a map, start it, enter bans and import a session - and its
  "Start map" ran before bans had anywhere to be entered on that surface, so a
  map could begin with the draft unrecorded. Everything done DURING a scrim now
  lives in the pop-out panel: choose the map, note the bans, capture, finish,
  choose the next, close the scrim out. The page keeps what happens before the
  game - share the screen, calibrate, name the scrim - and nothing else. That is
  305 lines of markup and handlers gone from it.

  The panel's next-map row gained an optional replay-code field, because
  removing the page's field would otherwise have left no way to record one at
  all. The screenshot importer's UI went too; `parseScrimSessionText` stays,
  since the replay-code OCR reads the same replay-history text.

- **The pre-map panel says what it is for.** It led with "no map running", which
  names what is not happening. It now reads "Select the map, and any bans" - the
  second half only when the scrim uses them.

- **"Finish scrim capture" waits for a captured map.** Closing out a scrim with
  nothing in it left an empty record and threw away the setup.

- **Hero bans are picked from the capture panel, before the map starts.** They
  were entered from a 53-entry dropdown that only appeared *while a map was
  running* - after the draft they were meant to record. The panel now carries a
  role-grouped grid of hero portraits, laid out like the in-game hero select,
  on the pre-map screen beside the map picker. Clicking a portrait bans it and
  clicking it again undoes that, so a misclick is fixable where it happened.

  Both surfaces render the same picker, so a ban set on either is set
  everywhere. The map-start paths no longer clear the ban list - they used to,
  which would have eaten every ban the moment Start was pressed - and it is
  cleared when a map finishes instead.

- **"No bans this map" is recorded as a fact.** An empty ban list could not say
  it: that is equally what a map nobody recorded bans for looks like, so the
  viewer excluded both from the denominator and every ban rate was computed
  against too small a pool. A map explicitly played without bans now counts as
  the evidence it is.

- **The capture panel opens when a scrim is saved, and can close a scrim out.**
  Saving a scrim pops the panel immediately - it runs inside the click, which is
  what satisfies the browser's user-gesture rule - so the whole loop happens
  there: pick map, pick bans, capture, finish, next map. "Finish scrim capture"
  sits beside that loop and is rendered only between maps, so it is unreachable
  mid-capture by construction rather than by a refusal. It ends the capture
  session only: the scrim stays in the picker and stays editable.

- **The hero role table has one copy again.** `ROLE_MAP` moved out of
  `docs/scrims.html` into `docs/capture/engine/heroes.js`, which both pages now
  load - the ban grid needs roles too, and a second hand-kept copy would be a
  second chance to drift from `faceit_sync/subroles.py`. The first copy had
  already drifted silently. `docs/scrims.html` gains its only external script.

### Changed
- **The replay-code reader now checks the crop, not just the contrast.** It
  reads the code at five crop geometries and records it only when all five
  agree. A disagreement says so, and says what to do: *the code read
  differently when the crop was nudged — re-run Auto-calibrate.*

  The reason is a measured failure, not a precaution. The crop is positioned
  relative to the calibration box, so it is exactly as right as that box is —
  and the tool itself tells you to drag the boxes by hand when auto-calibrate
  scores low. Over twelve real frames, a box off by more than about 2% did not
  produce a failed read; it produced a **wrong** one, a well-formed six-character
  code belonging to no game, 54 times. The three-contrast check could not see
  it: a crop in the wrong place is wrong identically at every contrast, so the
  passes agreed. A wrong code attributes a whole map's comps to another match
  and looks exactly like a correct one. Zero wrong across the same frames now.

- **Scrim mode is merged, and stays closed.** Everything built for scrims -
  panel-first capture, the hero-grid ban picker, player names against heroes,
  the replay-code reader - is now on the live site rather than a branch, but
  both scrim pages open behind a lock. Capture and viewer are gated together:
  unlocking one alone would ship a tool that records scrims nobody can read.

  The overlay is static markup and the gate script only ever removes it, so a
  syntax error, a blocked script or a browser with localStorage off all leave
  the page locked. It is a soft gate, not a security boundary - nothing behind
  it is secret, and it writes only to your own browser.

- **Registered the 2026-08-19 patch code wipe, dated the 18th.** Every replay
  code from before the patch is dead, so the site marks those maps lost to the
  wipe rather than offering them.

  The date is deliberately a day early. `codeDead` is date-granular
  (`when[:10] <= wipe`), and the patch landed mid-evening, so dating it the
  19th would have marked that day's post-patch league games dead too - and
  their codes are alive. Offering a dead code costs one failed capture attempt;
  hiding a live one loses the map for good, because a code nobody scouts is
  never recoverable. The reasoning is recorded beside the entry in
  `owdb/db.py`, which remains the only place a wipe date is written.

### Fixed
- **The scrims viewer rendered an empty shell.** Its CSP is
  `script-src 'unsafe-inline'` with no `'self'` - correct while every line it
  ran was inline, and wrong the moment it gained an external script (the
  `engine/heroes.js` extraction above). The browser blocked the file,
  `OWDBHeroes is not defined` threw at the top of the inline script, and the
  page stopped before it defined a single tab: no nav, no content, on every
  tab and both the demo and real data. The policy now allows `'self'`, and a
  test fails if any page loads a script its own CSP forbids. Same shape as the
  `scoreboard.js` block found earlier this month, and invisible to `curl -I`
  for the same reason - the policy is a `<meta http-equiv>` tag.
- **A stalled OCR read hung the capture pages with nothing to show for it.**
  `ocrWorker()`'s deadline only covers *loading* the engine; a `recognize()`
  that stalls after that never returns, and because tesseract.js runs one job
  at a time per worker, every other read sharing it queues behind and hangs
  too. The guard existed inside the league page's `ocrNames()` alone, so the
  scrim page's four reads - HUD names, both scoreboard crops, the replay code -
  and the league page's own replay-code read had no deadline at all. All of
  them now go through one helper that times out and discards the wedged
  worker. This is what let a failure stay silent: the scrim page's side
  detection is written to say *why* it failed, and could say nothing for an
  error that never arrived.
- **The scrim panel never said who was on which hero.** It read the ten HUD
  names, saved them with every snapshot and paired them into the finished map -
  and then printed a hardcoded em-dash in all ten Player cells, so the one
  screen the operator watches during a scrim showed nothing it already knew.
  The cell now shows the name read for that slot, replaced by a roster's own
  spelling when the read matches one (ours, or the opponent's when they were
  identified as a league team). A blank cell means nothing was read there -
  a name is never invented to fill one.
- **Scrim side detection died on a missing database store.** The `opponents`
  store was added during opponent identification and folded into an existing
  schema version, on the reasoning that the version had not shipped yet.
  Anyone already testing that version held a database created before the store
  existed, and `onupgradeneeded` fires once per version - so it was never
  created for them, and every side-detection attempt threw
  `'opponents' is not a known object store name`. The version is bumped, which
  only ever adds stores, so learned hero portraits are untouched.

  The rule, with no exception for unshipped versions: a store added to an
  already-issued version reaches nobody who has already used it.

- **HUD names were being cropped with their neighbour's plate border attached.**
  Each name crop padded the portrait cell by 5% of its width on either side,
  which on a tight HUD reaches into the *next* name plate and drags its edge in.
  Tesseract reads those bars as `|`, `i`, `§` or `}`, so a perfectly legible
  `ASHBORN` came back as `§ ASHBORN |}`. The crop now follows the glyphs, and
  a run touching the cell edge is treated as the border rather than a letter -
  unless it is wide, because a name like `CHEESEBURGER` genuinely fills its
  cell and must not be clipped.

  Measured over twelve real frames with known ground truth, live captures and
  archived ones together: exact reads go from 75/120 to 110/120, stray
  characters from 57 to 2, and no frame got worse.

- **A name wrapped in that punctuation matched nothing.** The comparison
  lowercased and cut at `#` and nothing else, so `§ ASHBORN |}` was never equal
  to `ashborn`, and `i XYPHER |` normalised whole to `ixypher`. In the field
  four of five legible names were discarded and scrim side detection reported
  that it could not tell which side was ours - on a read a person resolves at a
  glance. Names now normalise without punctuation and also match on their
  whitespace-separated fragments of three characters or more, so a stray `i`
  falls away without taking `XYPHER` with it. The three-of-five bar is
  unchanged, so noise still cannot name a team on its own.

---

## 2026-08-18 (later)

### Added
- **Hero bans can be recorded from the capture panel.** Bans are a per-map fact
  noted while the map runs, and the operator is watching the game with the panel
  on top - so asking them to alt-tab back to the setup card to record one was
  asking them not to record it. The panel now carries the same hero picker,
  by-us/by-them picker and ban list as the card, beside the map controls, and
  only when the scrim uses bans.

### Fixed
- **Scrim side detection could never fire.** It matches the HUD against our own
  roster and abstains when that roster is empty - and it was always empty: the
  store meant to remember which team is ours had no writer anywhere in the page,
  and a scrim created without filling in "Our team" had nothing else to offer.
  Every scrim therefore fell back to picking the left team by hand.

  Naming the team on a scrim now remembers it for every future scrim, and a new
  scrim starts pre-filled with it. Finishing a map also *learns* the names on
  our side of the HUD, which covers stand-ins, alt accounts, and teams that are
  not in the league feed at all. Learning is tied to finishing a map rather than
  to the side control changing: on change, a single swap would teach it the
  opposing five as well, both sides would then match "us", and the detector -
  which refuses to guess when both overlap - would abstain for good.

  When it still cannot tell, the message now names the cause. It used to say
  "pick the left team above", which is what to do, not what was wrong.

---

## 2026-08-18

### Fixed
- **The HUD name crop was pointed at the wrong part of the screen.** Calibration
  fits its box to the hero *portraits*, and the name crop assumed the name sat at
  a fixed 48-90% of that box's height. On a real frame that band straddles the
  portrait bottom, the name and the health bar - and the bar, being a solid
  bright block, is the brightest thing in it. Reads came back as letter-soup or
  empty.

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

### Fixed
- **The two capture pages no longer fight over the IndexedDB schema, and the
  database moves to version 5.** Each page opened `owscout-capture` at version
  4 declaring only the stores it used, but `onupgradeneeded` fires once per
  version — so whichever page a browser opened *first* created its own stores
  and fixed the version, leaving the other page's stores uncreated and every
  transaction on them throwing *"One of the specified object stores was not
  found"*. Opening the league page first killed scrim capture; opening the
  scrim page first killed league capture. Both pages now pass the single
  `ALL_STORES` map in `docs/capture/engine/idb.js`.

  **Version 5 is what repairs existing browsers.** One stuck at v4 with half
  the stores would never fire `onupgradeneeded` again without a version change.
  The upgrade only ever *adds* stores, so learned hero references, custom
  heroes and captured maps are untouched — verified in a real browser.

  The bug predates this work (`main` at `7e7bde2` fails identically) and only
  became reachable when scrim capture was un-paused, since a paused scrim page
  never touched its stores. Contributors with an established database were
  unaffected, having accumulated every store over time; a fresh install hit it
  immediately.

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
  Nine modules — `names.js`, `util.js`, `idb.js`, `frames.js`,
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

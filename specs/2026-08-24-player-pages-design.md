# Player pages — design

**Date:** 2026-08-24
**Status:** design approved in conversation; spec awaiting operator review

## Goal

An individual page per player on the dashboard: current team (and any mid-season
swaps), per-map and per-mode win rates, per-map stat averages against same-role
peers, and the hero pool captures have proved. Reached at `#player=<nick>` from
any player name on the site.

The page is **season-scoped**, not division-scoped: a player who moved team or
division mid-season is one player, shown with their real chronology.

## Background: what's already there

- **The payload is already one season.** CI exports `--season s9`
  (`.github/workflows/update.yml:149`), so `DATA.divisions` holds exactly the
  divisions of the current season. "Season-scoped" costs no new filtering — it
  means aggregating across all of `DATA.divisions` rather than only `D()`.
- **Every FACEIT-side input already ships.** `teams[].roster[]`
  (`faceit_sync/export.py:302-370`) carries nick, `game_name`, role, elo,
  `games`, `last_seen`, `current` and per-map stat averages for **every player of
  every division**. `matches[].games[]` (`export.py:426-461`) carries `map`,
  `map_category`, `winner_team` and `rosters[].players[]` with per-game
  `nick / role / cap / e / d / dmg / heal`. Nothing needs collecting.
- **Hero attribution exists but is thin.** `DATA.owdb_pergame_players` maps
  `"<match_id>:<game_no>" -> {nick: hero}`. Measured 2026-08-24 against the live
  payload: **122 games attributed, 128 of 1187 players with any attributed game
  (10.8%), median 8 attributed games each.**
- **The peer-cohort question is already answered.** `efficiencyRatings` /
  `effZ` / `EFF_GROUP_MIN` (`pure.js:106-134`) z-score a player against the same
  competitive role in the same division, refusing under 5 maps or 4 peers.
  `effGroupOf` / `seatOfPlayer` (`app.js:2351-2368`) assign the cohort. The
  player page reuses all of it unchanged.
- **Playoff games must come through `leagueMatches`.** `leagueMatches(matches,
  playoffs)` (`pure.js:181`) supplies regular season + finished bracket. The
  2026-08-20 fix exists because team-facing reads silently stopped at the group
  stage; a player page reading `D().matches` directly would reintroduce exactly
  that bug.
- **Pseudo-tab routing has a proven pattern**, used three times: `#match=`,
  `#scout=` / `#prep=`, `#compare=`. Each resolves a division, sets state, and
  renders a non-nav view with a `hashFor` special-case and a nav-highlight
  override (`app.js:3097-3190`).
- **`docs/theme.css` supplies the whole visual vocabulary**: `.card`, `.tile`,
  `.pill`, `.section-h`, `.barrow`, `.chip`, the `--r-*` radii and the role
  colours. `.backlink`, `.roster`, `.tlink`, `.wsel` are dashboard-page-specific
  and live in `head.html`.

## The evidence problem, measured

Every claim this page makes needs a sample behind it. Measured against
`faceit.sqlite3` and the live payload on 2026-08-24:

| Grain | Median sample per player | Share reaching n≥5 |
|---|---|---|
| Maps played, season | 38 | — |
| Per **mode** (5 modes) | 8 | 69% |
| Per **map** (13 maps) | 3 | 35% |
| Per **hero** (captures only) | ~3, and only for 10.8% of players | negligible |

Three consequences, and they are design decisions rather than caveats:

1. **Mode is the headline grain; map is the drill-down.** A per-map win rate at
   n=3 is not a number to show a coach without its `n` beside it.
2. **A player's map record is largely their team's**, because they play with the
   same four teammates. The page prints the team's rate in the same row and says
   so. The differentiating read is *divergence* — which is precisely the sub and
   mid-season-swap case (61 players changed team this season).
3. **Per-hero win rate sits behind a hard floor** (n≥3 games on that hero — see
   the amendment below) and
   will therefore be blank for nearly everyone this season. It is paired with the
   hero **pool** (share of rounds), which is factual at any sample size, so the
   section has a non-empty state today and gains the win-rate column as capture
   coverage grows. No rewrite is needed when it does.

## Scope decisions

| Decision | Choice | Why |
|---|---|---|
| Scope | Season, across every division in the payload | The user's call. The payload is already season-scoped, so this is free; it is also the only scope in which a mid-season division move is representable. |
| Identity key | `nick` | Verified zero duplicate nicknames across all 1187 players; `nick` is already the join key for `owdb_comps` and `per_game_players`. Adding `player_id` to game rosters would cost ~1.6 MB to solve a collision that does not exist. Accepted risk: a mid-season nickname change splits one player into two pages (see Risks). |
| Surface | Pseudo-tab via `#player=<nick>` | Same non-nav drill-in status as `#match=` / `#compare=`; no sixth nav button. Nav highlights Players. |
| Where the aggregation runs | Client-side, `pure.js` | Every input already ships. ~39,390 player-game rows is milliseconds in JS and **zero added bytes** on a 9.14 MB / 1.50 MB-gzipped page. Pre-aggregating server-side would add an estimated 0.5–1 MB for no new information, against a page-weight concern AGENTS.md already flags. It also lands on the documented side of the pure/impure boundary: logic that can mislead a coach belongs in `pure.js`. |
| Stat baseline | Same role, same division | Reuses `efficiencyRatings`' cohort so a player reads identically on their page, the Players tab and Team Compare. A Master dmg average and an Advanced one are different units; blending them across a season would be the one comparison the rest of the site refuses to make. |
| Cross-division players | One stat row per division, never blended | Follows from the baseline decision. 17 of 1187 players are affected. |
| Match source | `leagueMatches(div.matches, div.playoffs)` per division | Playoff games are real games. Reading `matches` directly is the 2026-08-20 bug. |
| Recency window | Full season | Matches every other team-facing read. A window control is future work, not a v1 gap. |

## Design

### 1. Pure layer — `faceit_sync/dashboard/pure.js`

One spine function plus small helpers, all above `bootApp(` so
`tests/test_dashboard_logic.py` can execute them in node without a DOM.

`divisions` is `DATA.divisions` itself — the whole season, keyed by
championship id — not the selected division. `comps` is `DATA.owdb_comps` and
`pergame` is `DATA.owdb_pergame_players`; both are passed in rather than read
from a global so the function stays executable in node.

```
playerSeason(nick, divisions, comps, pergame) -> {
  found:    bool,
  teams:    [{team, division, games, firstSeen, lastSeen}],   // chronological
  current:  {team, division} | null,                          // last entry
  divisions:[{division, role, games, stats, elo}],            // one row each
  modes:    [{mode, games, wins, wr|null, teamWr|null}],      // wr null under floor
  maps:     [{map, mode, games, wins, wr|null, teamWr|null}],
  recent:   [{matchId, at, division, team, opponent, map, won, stats, hero|null}],
  heroes:   [{hero, rounds, share, games, wins, wr|null}],    // wr null under floor
}
```

Floors, named constants beside the existing `LB_MIN_GAMES` / `EFF_GROUP_MIN`:

| Constant | Value | Applies to |
|---|---|---|
| `PLAYER_MODE_MIN` | 5 | mode win rate |
| `PLAYER_MAP_MIN` | 5 | per-map win rate |
| `PLAYER_HERO_MIN` | 3 | per-hero win rate (amended 2026-08-24, see below) |

`teamWr` is the player's **current team on that row**, over the same division
and season, across all of that team's games — not only the ones the player
appeared in. That is what makes divergence visible for a sub.

`recent` is returned in full, newest first; the view slices it. Pure functions
do not decide how many rows fit on a screen.

`heroes` joins two sources and the distinction matters: `rounds` and `share`
come from `comps[team].scout.players[]` (capture pools, factual at any sample),
while `games` / `wins` / `wr` come from `pergame` joined to each game's
`winner_team`. A hero can therefore have a pool share and no win rate, which is
the expected state for nearly every player this season.

A rate under its floor is `null`, never a number — the renderer decides how to
say "not enough games", and the pure layer never emits a figure it cannot stand
behind. `n` is always returned alongside so the page can print it.

**Team timeline** is derived from game chronology (`matches[].finished_at` +
`games[].rosters[]`), not from `roster[].last_seen`. `last_seen` gives only the
final date per (team, player); the chronology gives real first/last dates per
spell, which is what makes "swapped after 2026-07-12" truthful.

**Eff** is not recomputed. `renderPlayer` builds the same per-division player
list `renderPlayers` builds and calls the existing `efficiencyRatings`, so there
is exactly one definition of the rating on the site.

### 2. State + routing — `faceit_sync/dashboard/app.js`

- `let PLAYER_NICK = null;`
- `hashFor('playerdetail')` → `'player=' + encodeURIComponent(PLAYER_NICK)`.
- `hashDispatch` handles `player=`: resolve the nick's **primary** division (most
  games) to set `CURRENT_VIEW`, so the header and division select are coherent,
  then `show('playerdetail')`. An unresolvable nick lands on the Players tab —
  never a blank page, matching how `#match=` handles a stale id.
- `show()` maps `playerdetail` → nav id `players`.
- `gotoPlayer(nick)` mirrors `gotoScout`.
- A global `[data-player]` click delegate beside the existing `[data-scout]` one
  (`app.js:325`), guarded the same way so it never fires inside an `<a>` or a
  nested `[data-scout]`.

### 3. Entry points

Player names become links in three places that already list them: the Players
tab (all three views), team roster cards on the Teams/Scout pages, and the
per-map scoreboards on match detail. Each gains `data-player="<nick>"` — no new
UI, no new buttons.

### 4. The view — `renderPlayer()` in `app.js`, CSS in `head.html`

Top to bottom:

1. **Identity header** — `‹ Players` backlink, nick, `game_name` (BattleTag),
   current team with `teamAvatar()` (click → `#scout=`), role chip, division.
   No player avatar exists in the schema; the team avatar carries the weight.
2. **Headline tiles** (`.tile` in `.grid cols-4`) — maps played, map win rate,
   Eff, elo. Each shows `n` or `—` per its floor.
3. **Team timeline** — rendered **only** when the player has more than one team
   or division. Absent, not empty, for the other ~94%.
4. **Season stats** — per-map averages plus the Eff composite with its component
   z's, against the same-role same-division cohort, one row per division.
5. **Modes & maps** — mode win rates as `.barrow` bars; the map table below,
   sorted with `mapCmp` and grouped with `byMode`. **Sort before handing rows to
   `table()`** — `table()`'s group header only collapses *consecutive* same-group
   rows, which is the bug Team Compare shipped and had to fix the same day. Each
   row carries the team's rate beside the player's.
6. **Hero pool** — hero icons by share of rounds, with a win-rate column that
   appears per hero only at `PLAYER_HERO_MIN`. With no captures at all, the
   existing "not scouted yet" state plus the capture link.
7. **Recent maps** — last ~10 games: date, opponent, map, result, stat line, and
   hero where `per_game_players` has it. Rows click through to `#match=`.

### 5. CSS — `head.html`

One new component: the team-swap timeline strip. Everything else composes from
`theme.css` primitives. The rule stays in `head.html` rather than `theme.css`
because `docs/scrims.html` has no player pages, and
`tests/test_ui_consistency.py` fails a selector defined in both data pages.

No new tokens. Radii from `--r-sm/-md/-lg/-pill`; role colours from
`--tank/--damage/--support`; win/loss from the existing `winVar()`; any
saturated fill takes `--on-accent` as its ink. Light, dark and violet palettes
follow automatically.

Mobile: the 640px pass is shared at the foot of `theme.css`. The 13-map table
must scroll inside its own container rather than pushing the page sideways;
recent-maps rows collapse to two lines. Breakpoints stay on 640 / 900 / 1500.

### 6. Export change — `faceit_sync/export.py`

Game rosters carry `e / d / dmg / heal` but **not `mit`** (`export.py:442-453`),
so a Tank's per-map table would silently omit the stat their season card leads
with. Add `rp.damage_mitigated` to that query and `"mit"` to the emitted row.

Measured cost: **+512 KB raw (~60 KB gzipped) on a 9.14 MB / 1.50 MB page.**
An internally inconsistent page is the worse outcome.

## Testing

`tests/test_dashboard_logic.py` (pure layer, node, no DOM):

- team timeline across a mid-season swap — order, dates, `current`
- a cross-division player yields **two** stat rows, never a blend
- mode aggregation and map aggregation from the same fixture
- each floor: `null` at n−1, a number at n
- playoff games are counted (fixture with a `playoffs` entry)
- a player with zero captures returns `heroes: []` rather than throwing
- an unknown nick returns `found: false`

`tests/test_export.py` — game rosters carry `mit`.

`tests/test_ui_consistency.py` — unchanged, and must stay green; it reads
`faceit_sync/dashboard/head.html`, not the generated `docs/index.html`.

**The three that must always run after a dashboard change:**

```bash
.venv/Scripts/python.exe -m pytest \
  tests/test_export.py::test_dashboard_javascript_is_syntactically_valid \
  tests/test_export.py::test_export_html_is_self_contained_and_valid \
  tests/test_dashboard_logic.py
```

Visual check: build a preview to a **scratch path** and screenshot with headless
Edge using `--screenshot=FILE` (the GUI executable produces no stdout, so
`--dump-dom` yields nothing on Windows). Never export onto `docs/index.html` —
invariant 2; the local DB runs days behind CI's.

## Documentation to update

| File | What |
|---|---|
| `CHANGELOG.md` | Required — visible on owdb.io, and `mit` is a data-contract change |
| `ARCHITECTURE.md` §4 | The "Views and tabs" paragraph enumerates the drill-ins; add `#player=` |
| `ARCHITECTURE.md` §9 | The inlined-payload contract: game rosters gain `mit` |
| `ARCHITECTURE.md` §13 | Only if a new test file appears |
| `specs/BACKLOG.md` | Resolves the dangling "player index work" reference (line 241) and folds in the P3 *per-map scoreboard context* item, which this page delivers |
| `FEATURES.md` | Known to lag; add the entry rather than widen the gap |

## Out of scope

- **Per-game elo trend.** `elo_snapshot` exists per game but is exported only as
  the latest value. Shipping it per game costs **+473 KB raw** for one trend
  line. Season form can be sparklined from the per-game stats already present
  via `sparklinePoints`. Deferred with the number recorded.
- **Career / multi-season pages.** The payload is one season by construction.
- **Scrim players.** Invariant 8 — scrims never enter the dashboard build.
- **Cross-division player search** beyond what the Players tab already offers.
- **A recency window control** on the page.

## Amendment 2026-08-24 — the hero floor is 3, not 5

Decided by the operator after looking at the live page, and measured rather than
guessed. Captured attribution is the scarcest input on this page, so the hero
floor buys far more coverage per point than the map and mode floors do:

| Floor | (player, hero) cells showing a rate | Distinct players |
|---|---|---|
| n≥5 | 56 | 54 |
| n≥4 | 82 | 64 |
| **n≥3** | **113** | **71** |

Three doubles the cells for a third more players. The cost is stated rather than
hidden: of the 31 cells sitting at exactly 3 games, **10 read 0% or 100%** —
the two most fact-like numbers a three-game sample can produce. That is why the
game count is never optional beside the rate, and why the map and mode floors
stay at 5: they are not sample-starved, so lowering them would buy little and
cost the same.

## Risks

| Risk | Mitigation |
|---|---|
| A mid-season **nickname change** splits one player into two pages | FACEIT gives no nickname history, so this cannot be solved with the data we hold. Stated on the page rather than silently wrong. `player_id` is available server-side if it ever becomes worth the ~1.6 MB. |
| Map win rates read as a **player** signal when they are largely a **team** signal | The team's rate sits in the same row, and the section says so. |
| Hero win rate is blank for nearly every player this season | Deliberate — the floor is the feature. The hero **pool** is the section's non-empty state, and the column fills in as coverage grows. |
| Reading `div.matches` instead of `leagueMatches(...)` silently drops playoffs | Covered by a test with a `playoffs` fixture. |
| A JS syntax error blanks the entire page and bracket checks miss it | The three mandatory tests, run after every edit under `faceit_sync/dashboard/`. |

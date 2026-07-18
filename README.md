# faceit-scout

Two packages that feed one scouting dashboard:

- **`faceit_sync`** — incremental, idempotent ingest of **FACEIT League
  (Overwatch 2)** championship data into a local **SQLite** database, exported as
  a self-contained HTML dashboard.
- **`owscout`** — reads hero compositions off the observer HUD of in-client
  replays and turns them into per-team composition scouting on the same page.

**→ [FEATURES.md](FEATURES.md) documents every feature in both packages and how
each one works.** The rest of this file covers `faceit_sync` ingest specifically.

---

## faceit_sync

Incremental, idempotent ingest of **FACEIT League (Overwatch 2)** championship
data into a local **SQLite** database.

It is built to run 2–3× per week against in-progress seasons:

- **Incremental** — enumerates a championship's matches (or takes an explicit
  list) and only fetches what it needs.
- **Idempotent** — re-running never duplicates rows. Matches already stored as
  `FINISHED` are skipped (and not even re-fetched) unless `--force-refresh` is
  given, because veto, results and stats never change once a match ends.
  **Replay codes are a partial exception.** A code absent at ingest would never
  arrive under a pure skip, so two narrow cases are re-fetched: a match with a
  *partial* gap (some games have codes, some do not) within `--backfill-days`
  (default 14), and any match ingested in the last 12 hours. Matches with no code
  on *any* game are left alone — measured across 676 matches, that state is
  permanent (replays were never published for them), and re-fetching them
  recovered nothing.
- **Honest about missing data** — where a value genuinely isn't available it is
  stored as `NULL`, never zero-filled or guessed. See **[Data quality](#data-quality)**.

---

## Why the public API instead of scraping the site

Every datum here comes from FACEIT's own JSON endpoints, four of which are
public and were verified working **logged out, with no auth**:

| Purpose | Endpoint | Auth |
|---|---|---|
| Enumerate a championship's match ids | `GET open.faceit.com/data/v4/championships/{id}/matches` | Bearer key (free) |
| Match detail (rosters, results, veto, demos) | `api.faceit.com/match/v2/match/{id}` | none |
| Veto history (**durable** attribution) | `api.faceit.com/democracy/v1/match/{id}/history` | none |
| Live veto feed (ephemeral) | `api.faceit.com/democracy/v1/match/{id}` | none |
| Per-game player stats | `api.faceit.com/stats/v1/stats/matches/{id}` | none |

Scraping the rendered site would mean parsing a JS single-page app, would break
on every markup change, and would still be hitting these same endpoints
underneath — only slower and more fragile. Consuming the JSON directly is
faster, stable, and polite (we send a descriptive `User-Agent`, pool
connections, and rate-limit ourselves; see [Engineering](#engineering-notes)).

> **User-Agent note.** FACEIT's edge **blocks browser-like User-Agents**
> (`Mozilla/5.0` → HTTP 403) but accepts a descriptive client string. We
> therefore send an honest `faceit-sync/…` UA and never impersonate a browser.

Only match *enumeration* needs the free Data API key. If you already have match
ids/URLs, the whole pipeline runs keyless.

---

## Install

```bash
python -m venv .venv && . .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
cp .env.example .env                               # add FACEIT_API_KEY if enumerating
```

## Usage

```bash
# Enumerate + ingest a whole championship (needs FACEIT_API_KEY):
faceit-sync fetch --championship 938f6e68-b374-4f0f-b3e1-3bf1bdfbfd11

# Mass-import specific matches, keyless — paste room URLs or bare ids:
faceit-sync fetch --matches \
    https://www.faceit.com/en/ow2/room/1-84e049a3-bf72-426a-a88e-f5c5039abd8f \
    1-2ae09905-dcbf-46b0-a272-fa08afa3f293

# ...or from a file (one id/URL per line, '#' comments allowed):
faceit-sync fetch --matches-file matches.txt

faceit-sync fetch --championship <id> --force-refresh   # re-ingest finished matches
faceit-sync fetch --championship <id> --dry-run -v       # fetch+parse, write nothing

# Export:
faceit-sync export --championship <id> --format csv --out games.csv
faceit-sync export --championship <id> --format json --out full.json

# Interactive HTML dashboard (self-contained; double-click to open, works offline):
faceit-sync export --championship <id> --format html      # -> dashboard-<id>.html

# Team analysis (ban tendencies, map picks, win rates):
faceit-sync stats --team "Vertex"
```

### Docker

```bash
docker compose build
docker compose run --rm faceit-sync fetch --matches 1-....   # DB persists in ./data
```

---

## Schema

FACEIT ids are primary keys throughout; foreign keys are enforced
(`PRAGMA foreign_keys = ON`).

```
championships(id, name, game, region)
teams(id, name, avatar_url)
players(id, nickname)                                              -- seeded from rosters/stats
matches(id, championship_id, round, group_no, status, best_of,
        scheduled_at, started_at, finished_at,
        faction1_team_id, faction2_team_id, winner_faction, forfeit, fetched_at)
games(match_id, game_no, map_guid, map_category,
      attacking_first_faction, side_picked_by_faction,
      faction1_score, faction2_score, winner_faction,
      demo_code, was_restarted)
map_picks(match_id, game_no, map_guid, picked_by_faction)          -- picked_by NULLable
hero_bans(match_id, game_no, hero_guid, ban_order, banned_by_faction) -- banned_by NULLable
round_players(match_id, game_no, team_id, player_id, role, elo_snapshot,
              stats_captured, eliminations, deaths, assists, damage,
              healing, damage_mitigated)                            -- stats NULLable
heroes(guid, name, role)      -- seeded from the veto hero pool
maps(guid, name, category)    -- seeded from the veto map pool
sync_log(id, ran_at, championship_id, matches_seen, inserted, updated,
         skipped, warnings, errors)
```

We deliberately **do not store raw JSON**. The match payload repeats the full
hero list — with two CDN image URLs per hero — inside every per-round veto entry
(~200 KB of payload for ~2 KB of information). Everything is extracted on ingest.

### The Overwatch 2 stat codes

FACEIT's stats payload uses opaque keys (`i8`, `i14`, …). We mapped them by
pulling several real matches and correlating each code against player role. The
mapping lives in one place ([`models.STAT_FIELD_MAP`](faceit_sync/models.py)):

| Column | Code | Evidence (per-role average) |
|---|---|---|
| `eliminations` | `i8` | Damage 17.6 / Tank 18.0 / Support 11.3 |
| `deaths` | `i9` | ~5–6, uniform across roles |
| `assists` | `i10` | **Support 17.9** ≫ Tank 5.0 / Damage 2.3 |
| `damage` | `i13` | Tank 10169 / Damage 8286 / Support 4398 |
| `healing` | `i14` | **Support 9594** ≫ Tank 1054 / Damage 221 |
| `damage_mitigated` | `i17` | **Tank 13223** ≫ others |

If FACEIT changes these codes, correct them in that one dict.

---

## Data quality

**This section is the point of the project.** Overwatch-on-FACEIT data has
sharp edges that silently corrupt naïve ingests. Three were found by comparing
real payloads; each is handled explicitly and tested.

### Hazard A — zeroed player rows are **not** forfeits

Overwatch captures stats at game end. If a team disconnects seconds before that,
all five of its player rows come back **zeroed** with `i16 == "-"`, and the match
payload's `clientCustom.stats` shows `players: []`. **The game was still played
to completion and the result is valid.**

- **How it was found.** Match `1-2ae09905…` (a 3–0) has, in game 3, five rows for
  the losing team with `role='-'` and every stat `0` — while `results[]` records
  a valid win for that game and a demo code exists for it.
- **How it's handled.** We never write `0` for a missing stat — we write `NULL`
  and set `round_players.stats_captured = 0`. Game outcomes come from
  `results[]`, never from stat rows. A warning is logged (and counted) whenever a
  game is in `results[]` with a demo code but a team's stat rows are empty.
- **Tested by** `tests/test_stats_null.py`.

### Hazard B — admin restarts destroy that game's veto ticket

If an admin restarts a game, that game's veto ticket in **democracy** is wiped:
its entities all revert to `status: "open"`, `selected_by: "n/a"`. The **bans
still exist** in the match payload's `heroes.pick`, but *who* banned them is gone.

- **How it was found.** The ticket originally said restarts show up as `sessions[]`
  having more than one entry — but **`sessions[]` does not exist on any observed
  payload**, including a match that *was* restarted. Worse, a restart **breaks the
  positional alignment** between democracy slots and played games. In match
  `1-2ae09905…` (played games 1–3), democracy slot 0 actually holds **game 2's**
  ban-set, slot 2 holds game 3's, one slot is `open`, and **game 1's veto is
  absent entirely**. Joining slot-by-index would have mis-attributed every ban.
- **How it's handled.** We join a game to its veto slot by **ban-set equality**
  (the two heroes computed as banned from the match payload — `pool − heroes.pick`
  — matched against a slot's dropped heroes), not by position. A played game whose
  ban-set matches no democracy slot has its veto wiped → `games.was_restarted = 1`,
  bans still come from the match payload, and `hero_bans.banned_by_faction` is
  `NULL`. (On this match that is game 1.) Reconciliation invariant: **every played
  game has exactly one ban pair.** Any democracy veto slot that matches no played
  game is logged as an orphan.
- **Tested by** `tests/test_restart.py`.

### Hazard C — the *live* veto feed is ephemeral, but `/history` is durable

The live democracy endpoint `…/democracy/v1/match/{id}` returns **404 for matches
more than about a week old**. Taken alone, that would make veto attribution — who
banned which hero, who picked which map/side — capturable only while a match is
fresh. **But there is a second endpoint** that persists the same veto log:
`…/democracy/v1/match/{id}/**history**`.

- **How it was found.** The live feed 404s stably for matches ≥ ~8 days old. But
  probing sibling endpoints on an *expired* match, `…/history` returned `200` with
  the full veto log — and it returns `200` for **every** match tested across the
  whole date range. Its entities are even cleaner: `selected_by` (attribution) and
  `round` (ban order) live directly on each drop, no `config` needed.
- **How it's handled.** The client fetches `/history` **first** (durable) and only
  falls back to the live feed if history is missing. This recovers attribution for
  old matches, not just fresh ones — in the reference batch of 50 matches (all >8
  days old, live feed fully expired), **94 % of bans are attributed** this way.
- **What's still lost.** When a game's veto was genuinely *disrupted* — an admin
  restart, or a paused/re-run veto (e.g. to add a caster) — that game's ticket is
  absent from `/history` too (empty/`open`). Those games keep their bans (from the
  match payload) with `banned_by_faction = NULL` and `was_restarted = 1`. The
  `stats` command surfaces the unattributed count so the gap is never mistaken for
  "no bans."

### Can ban attribution be reconstructed after the live feed expires? Yes — via `/history`.

An earlier version of this project concluded "no": the match payload stores only the
surviving hero *set* (a banned hero is recoverable solely as "absent from this game's
survivor list"), with no ban order — the `matchCustom.tree.…voting_per_round[g].value`
that looks promising is just the full 52-hero pool copied verbatim into every round
(the ~200 KB of bloat noted above). All true. **But it was looking in the wrong
place.** The ordered, attributed veto log is served by the durable
`…/democracy/v1/match/{id}/history` endpoint (see Hazard C), which persists long after
the live feed 404s. So attribution *is* recoverable for old matches — no inference or
ban-order guessing required, because `/history` records `selected_by` per drop
outright. The only irrecoverable cases are genuinely disrupted vetos (restart /
paused veto), where the record is absent everywhere.

### On Game-1 ban attribution

The ticket asked whether Game-1 first-ban order could be derived (games 2+ have
the previous game's loser ban first; Game 1 has no previous game, and the
`team_a`/`team_b` voting order is **not** a fixed alias for `faction1`).

Finding: attribution never needs that inference. When democracy is present, each
ban's `selected_by` is already faction-labeled for **every** game including
Game 1, and the heroes ticket's `config[]` array gives the ban order directly —
so `team_a`↔`faction` mapping is moot. When democracy is *absent* (Hazard C, or a
restart), the ordering config is gone too, so there is nothing to derive from.
**Decision: attribution is derivable iff democracy is present; otherwise it is
left `NULL`. We do not guess.** (For the record, both democracy-bearing matches
observed had `faction1` banning first in Game 1, but with n=2 and no need to rely
on it, this is not encoded as a rule.)

### A note on elo

Elo appears in the match roster (`teams.factionN.roster[].elo`) but **not** in
the stats payload at all (zero occurrences of `elo`). The ticket's instruction to
"store the stats snapshot, not the live match value" can't be followed because
that field doesn't exist. Since each finished match is ingested once, promptly
(within the sync cadence), the roster value is effectively the near-match-time
snapshot; that is what `round_players.elo_snapshot` stores.

---

## Engineering notes

- One `requests.Session` (connection pooling, keep-alive); descriptive User-Agent.
- Global rate limit, default **4 req/s** (`FACEIT_RATE_LIMIT`), monotonic-clock based.
- `429` → exponential backoff + jitter, honouring `Retry-After`. `5xx` (incl.
  `503`) → retry. Backoff sleep and RNG are injectable, so tests are deterministic.
- Idempotent writes: reference rows upsert; per-match child rows are deleted and
  re-inserted atomically, so a re-ingest leaves row counts unchanged.
- Full type hints; passes `mypy` (strict). Structured logging via `logging`.
- **Endpoint correction:** the documented stats path
  `…/stats/v1/stats/time/matches/{id}` returns 404; the working path has **no**
  `/time` segment (`…/stats/v1/stats/matches/{id}`).

## Layout

```
faceit_sync/
  cli.py         # argparse: fetch / export / stats
  client.py      # HTTP: session, rate limit, backoff, endpoints
  models.py      # typed records + empirical stat-code map
  db.py          # schema, connection, idempotent writes
  sync.py        # extraction, reconciliation, orchestration, mass-import
  export.py      # csv/json/html export + team stats
  _dashboard.py  # self-contained HTML dashboard template
tests/           # pagination, backoff, idempotency, hazard A, hazard B, url-parse, html export
```

> **Analysis note.** In the dashboard, attacking-first win-rate is shown only for
> **Escort** and **Hybrid** — the asymmetric modes. On Control, Flashpoint and Push
> the sides are mirrored, so "attacks first" is competitively meaningless there.

## Tests

```bash
pip install -e ".[dev]"
pytest
mypy faceit_sync
```

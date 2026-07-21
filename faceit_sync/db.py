"""SQLite persistence: schema, connection management, and idempotent writes.

Idempotency strategy
--------------------
Parent/reference rows (championships, teams, heroes, maps, matches) are written
with ``INSERT ... ON CONFLICT DO UPDATE``. Per-game child rows (games, map_picks,
hero_bans, round_players) are rewritten atomically: for each match we delete its
existing children and re-insert. Because a match's children only change on first
ingest or an explicit ``--force-refresh`` (finished matches are immutable and
skipped otherwise), re-running a sync never duplicates rows and leaves counts
unchanged.
"""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from typing import Iterator, Optional

from .models import (
    Game,
    Hero,
    HeroBan,
    Map,
    MapPick,
    Match,
    Player,
    RoundPlayer,
    Team,
    Championship,
)

SCHEMA = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS championships (
    id     TEXT PRIMARY KEY,
    name   TEXT,
    game   TEXT,
    region TEXT
);

CREATE TABLE IF NOT EXISTS teams (
    id         TEXT PRIMARY KEY,
    name       TEXT,
    avatar_url TEXT
);

CREATE TABLE IF NOT EXISTS players (
    id        TEXT PRIMARY KEY,
    nickname  TEXT,
    game_name TEXT          -- Battle.net in-game name; what the OW HUD shows
);

CREATE TABLE IF NOT EXISTS heroes (
    guid TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    role TEXT
);

CREATE TABLE IF NOT EXISTS maps (
    guid     TEXT PRIMARY KEY,
    name     TEXT NOT NULL,
    category TEXT
);

CREATE TABLE IF NOT EXISTS matches (
    id               TEXT PRIMARY KEY,
    championship_id  TEXT NOT NULL REFERENCES championships(id),
    round            INTEGER,
    group_no         INTEGER,
    status           TEXT NOT NULL,
    best_of          INTEGER,
    scheduled_at     TEXT,
    started_at       TEXT,
    finished_at      TEXT,
    faction1_team_id TEXT REFERENCES teams(id),
    faction2_team_id TEXT REFERENCES teams(id),
    winner_faction   TEXT,
    forfeit          INTEGER NOT NULL DEFAULT 0,
    fetched_at       TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS games (
    match_id                TEXT NOT NULL REFERENCES matches(id) ON DELETE CASCADE,
    game_no                 INTEGER NOT NULL,
    map_guid                TEXT,
    map_category            TEXT,
    attacking_first_faction TEXT,
    side_picked_by_faction  TEXT,
    faction1_score          INTEGER,
    faction2_score          INTEGER,
    winner_faction          TEXT,
    demo_code               TEXT,
    was_restarted           INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (match_id, game_no)
);

CREATE TABLE IF NOT EXISTS map_picks (
    match_id          TEXT NOT NULL REFERENCES matches(id) ON DELETE CASCADE,
    game_no           INTEGER NOT NULL,
    map_guid          TEXT,
    picked_by_faction TEXT,
    PRIMARY KEY (match_id, game_no)
);

CREATE TABLE IF NOT EXISTS hero_bans (
    match_id          TEXT NOT NULL REFERENCES matches(id) ON DELETE CASCADE,
    game_no           INTEGER NOT NULL,
    hero_guid         TEXT NOT NULL,
    ban_order         INTEGER NOT NULL,
    banned_by_faction TEXT,               -- NULL when democracy absent/restarted
    PRIMARY KEY (match_id, game_no, hero_guid)
);

CREATE TABLE IF NOT EXISTS round_players (
    match_id         TEXT NOT NULL REFERENCES matches(id) ON DELETE CASCADE,
    game_no          INTEGER NOT NULL,
    team_id          TEXT,
    player_id        TEXT NOT NULL,
    role             TEXT,
    elo_snapshot     INTEGER,
    stats_captured   INTEGER NOT NULL,
    eliminations     INTEGER,
    deaths           INTEGER,
    assists          INTEGER,
    damage           INTEGER,
    healing          INTEGER,
    damage_mitigated INTEGER,
    PRIMARY KEY (match_id, game_no, player_id)
);

CREATE TABLE IF NOT EXISTS sync_log (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    ran_at          TEXT NOT NULL,
    championship_id TEXT,
    matches_seen    INTEGER NOT NULL,
    inserted        INTEGER NOT NULL,
    updated         INTEGER NOT NULL,
    skipped         INTEGER NOT NULL,
    warnings        INTEGER NOT NULL,
    errors          INTEGER NOT NULL
);
"""


# A match stored moments after it ended may not have its replay codes up
# yet; re-check those for this long. Beyond it, a code-less match is
# code-less for good (see Database.matches_needing_backfill).
DEFAULT_BACKFILL_FRESH_HOURS = 12


class Database:
    """Thin wrapper around a SQLite connection with typed write helpers."""

    def __init__(self, path: str) -> None:
        self.path = path
        self.conn = sqlite3.connect(path)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")
        self.init_schema()

    def init_schema(self) -> None:
        self.conn.executescript(SCHEMA)
        # Idempotent column adds for DBs created before the column existed (the CI
        # DB is long-lived and updated in place, so CREATE TABLE IF NOT EXISTS
        # never re-runs for it).
        self._ensure_column("players", "game_name", "TEXT")
        self.conn.commit()

    def _ensure_column(self, table: str, column: str, decl: str) -> None:
        cols = {r[1] for r in self.conn.execute(f"PRAGMA table_info({table})")}
        if column not in cols:
            self.conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {decl}")

    def close(self) -> None:
        self.conn.close()

    def __enter__(self) -> "Database":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        try:
            yield self.conn
            self.conn.commit()
        except Exception:
            self.conn.rollback()
            raise

    # --- idempotency helpers -------------------------------------------------

    def matches_needing_backfill(
        self, since_days: int, fresh_hours: int = DEFAULT_BACKFILL_FRESH_HOURS
    ) -> set[str]:
        """Stored FINISHED matches worth re-fetching for replay codes.

        A plain fetch skips anything already stored FINISHED, so a code that was
        not there at ingest would never arrive. But re-fetching every match with a
        missing code is wasted work: MEASURED on 676 real matches, replay codes are
        an all-or-nothing property of a match — 87 matches had no code on any game,
        only 4 had a partial gap, and re-fetching all of them recovered ZERO codes.
        Replays were simply never published for those matches (it tracks with the
        division: 17.8% of EMEA Master games vs 1.1% of NA Master), so no amount of
        re-fetching will conjure one.

        Two cases are therefore worth the API call:

        * a **partial gap** — some games have codes and some do not, the only
          signature consistent with an incomplete publish; and
        * a **just-ingested** match (``fresh_hours``), where a match stored moments
          after it ended may genuinely not have its codes up yet.

        Everything else is left alone. On the operator's database this is ~5
        matches per run instead of 44.
        """
        if since_days <= 0:
            return set()
        rows = self.conn.execute(
            """SELECT m.id FROM matches m JOIN games g ON g.match_id = m.id
               WHERE m.status = 'FINISHED' AND m.finished_at >= datetime('now', ?)
               GROUP BY m.id
               HAVING (SUM(g.demo_code IS NULL) > 0 AND SUM(g.demo_code IS NOT NULL) > 0)
                   OR (SUM(g.demo_code IS NOT NULL) = 0
                       AND m.finished_at >= datetime('now', ?))""",
            (f"-{int(since_days)} days", f"-{int(fresh_hours)} hours"),
        ).fetchall()
        return {str(r["id"]) for r in rows}

    def match_status(self, match_id: str) -> Optional[str]:
        row = self.conn.execute(
            "SELECT status FROM matches WHERE id = ?", (match_id,)
        ).fetchone()
        return None if row is None else str(row["status"])

    # --- reference / parent upserts ------------------------------------------

    def upsert_championship(self, c: Championship) -> None:
        self.conn.execute(
            """INSERT INTO championships (id, name, game, region)
               VALUES (?, ?, ?, ?)
               ON CONFLICT(id) DO UPDATE SET
                   name=excluded.name, game=excluded.game, region=excluded.region""",
            (c.id, c.name, c.game, c.region),
        )

    def upsert_team(self, t: Team) -> None:
        self.conn.execute(
            """INSERT INTO teams (id, name, avatar_url) VALUES (?, ?, ?)
               ON CONFLICT(id) DO UPDATE SET
                   name=excluded.name, avatar_url=excluded.avatar_url""",
            (t.id, t.name, t.avatar_url),
        )

    def upsert_player(self, p: Player) -> None:
        # COALESCE so we never overwrite a known name with NULL.
        self.conn.execute(
            """INSERT INTO players (id, nickname, game_name) VALUES (?, ?, ?)
               ON CONFLICT(id) DO UPDATE SET
                   nickname=COALESCE(excluded.nickname, players.nickname),
                   game_name=COALESCE(excluded.game_name, players.game_name)""",
            (p.id, p.nickname, p.game_name),
        )

    def upsert_hero(self, h: Hero) -> None:
        self.conn.execute(
            """INSERT INTO heroes (guid, name, role) VALUES (?, ?, ?)
               ON CONFLICT(guid) DO UPDATE SET name=excluded.name, role=excluded.role""",
            (h.guid, h.name, h.role),
        )

    def upsert_map(self, m: Map) -> None:
        self.conn.execute(
            """INSERT INTO maps (guid, name, category) VALUES (?, ?, ?)
               ON CONFLICT(guid) DO UPDATE SET name=excluded.name, category=excluded.category""",
            (m.guid, m.name, m.category),
        )

    def upsert_match(self, m: Match) -> bool:
        """Insert or update a match. Returns True if the row was newly inserted."""
        existed = self.match_status(m.id) is not None
        self.conn.execute(
            """INSERT INTO matches (
                   id, championship_id, round, group_no, status, best_of,
                   scheduled_at, started_at, finished_at,
                   faction1_team_id, faction2_team_id, winner_faction, forfeit, fetched_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(id) DO UPDATE SET
                   championship_id=excluded.championship_id, round=excluded.round,
                   group_no=excluded.group_no, status=excluded.status,
                   best_of=excluded.best_of, scheduled_at=excluded.scheduled_at,
                   started_at=excluded.started_at, finished_at=excluded.finished_at,
                   faction1_team_id=excluded.faction1_team_id,
                   faction2_team_id=excluded.faction2_team_id,
                   winner_faction=excluded.winner_faction, forfeit=excluded.forfeit,
                   fetched_at=excluded.fetched_at""",
            (
                m.id, m.championship_id, m.round, m.group_no, m.status, m.best_of,
                m.scheduled_at, m.started_at, m.finished_at,
                m.faction1_team_id, m.faction2_team_id, m.winner_faction,
                int(m.forfeit), m.fetched_at,
            ),
        )
        return not existed

    # --- per-match children (delete + reinsert => idempotent) ----------------

    def replace_children(
        self,
        match_id: str,
        games: list[Game],
        map_picks: list[MapPick],
        hero_bans: list[HeroBan],
        round_players: list[RoundPlayer],
    ) -> None:
        c = self.conn
        for table in ("games", "map_picks", "hero_bans", "round_players"):
            c.execute(f"DELETE FROM {table} WHERE match_id = ?", (match_id,))

        c.executemany(
            """INSERT INTO games (
                   match_id, game_no, map_guid, map_category,
                   attacking_first_faction, side_picked_by_faction,
                   faction1_score, faction2_score, winner_faction,
                   demo_code, was_restarted)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            [
                (g.match_id, g.game_no, g.map_guid, g.map_category,
                 g.attacking_first_faction, g.side_picked_by_faction,
                 g.faction1_score, g.faction2_score, g.winner_faction,
                 g.demo_code, int(g.was_restarted))
                for g in games
            ],
        )
        c.executemany(
            """INSERT INTO map_picks (match_id, game_no, map_guid, picked_by_faction)
               VALUES (?, ?, ?, ?)""",
            [(p.match_id, p.game_no, p.map_guid, p.picked_by_faction) for p in map_picks],
        )
        c.executemany(
            """INSERT INTO hero_bans (
                   match_id, game_no, hero_guid, ban_order, banned_by_faction)
               VALUES (?, ?, ?, ?, ?)""",
            [(b.match_id, b.game_no, b.hero_guid, b.ban_order, b.banned_by_faction)
             for b in hero_bans],
        )
        c.executemany(
            """INSERT INTO round_players (
                   match_id, game_no, team_id, player_id, role, elo_snapshot,
                   stats_captured, eliminations, deaths, assists, damage,
                   healing, damage_mitigated)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            [
                (r.match_id, r.game_no, r.team_id, r.player_id, r.role, r.elo_snapshot,
                 int(r.stats_captured), r.eliminations, r.deaths, r.assists, r.damage,
                 r.healing, r.damage_mitigated)
                for r in round_players
            ],
        )

    def insert_sync_log(
        self,
        ran_at: str,
        championship_id: Optional[str],
        matches_seen: int,
        inserted: int,
        updated: int,
        skipped: int,
        warnings: int,
        errors: int,
    ) -> None:
        self.conn.execute(
            """INSERT INTO sync_log (
                   ran_at, championship_id, matches_seen, inserted, updated,
                   skipped, warnings, errors)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (ran_at, championship_id, matches_seen, inserted, updated,
             skipped, warnings, errors),
        )
        self.conn.commit()

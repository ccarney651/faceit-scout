"""owscout's own SQLite database (``owscout.sqlite3``).

Separate file from ``faceit.sqlite3`` — non-negotiable (SPEC §3). owscout never
writes to the faceit DB; it ATTACHes it read-only (``mode=ro`` URI) when it needs
context — see :meth:`Database.attach_faceit`. Cross-DB joins work under ATTACH;
cross-DB foreign keys do not, so faceit keys are stored as plain, validated
columns (SPEC §3).

The full SPEC §4 data model is present. All DDL is ``CREATE TABLE IF NOT
EXISTS``, matching faceit-sync's convention (SPEC §4, §12).
"""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Iterator, Mapping, Optional, Sequence

from .derive import ObsRow
from .faceit import faceit_ro_uri
from .integrity import VerifyCodesRow
from .models import (
    DEFAULT_DIVISION,
    CodeContext,
    CodeListing,
    Comp,
    DraftMap,
    FaceitHero,
    HeroRef,
    ObsDetail,
    Rect,
    RoiProfile,
)

SCHEMA = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS roi_profiles (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    resolution_w INTEGER NOT NULL,
    resolution_h INTEGER NOT NULL,
    hud_variant  TEXT    NOT NULL DEFAULT 'default',
    team_size    INTEGER NOT NULL,
    slots_json   TEXT    NOT NULL,
    anchors_json TEXT    NOT NULL,
    created_at   TEXT    NOT NULL,
    retired_at   TEXT              -- NULL => active
);

CREATE TABLE IF NOT EXISTS hero_refs (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    hero_guid  TEXT    NOT NULL,           -- mirrors faceit.heroes.guid (validated, not FK'd)
    profile_id INTEGER NOT NULL REFERENCES roi_profiles(id),
    state      TEXT    NOT NULL CHECK(state IN ('alive','dead')),
    image_path TEXT    NOT NULL,
    phash      TEXT    NOT NULL,
    added_at   TEXT    NOT NULL,
    source     TEXT    NOT NULL CHECK(source IN ('capture','review')),
    variant    TEXT    NOT NULL DEFAULT 'a'   -- 'a'=left/blue team, 'b'=right/red team
);
-- One canonical 'capture' ref per (hero, profile, state, variant); 'review'
-- exemplars accumulate freely. The variant lets a hero carry a blue-team AND a
-- red-team portrait, since the HUD tints the background by team.
CREATE UNIQUE INDEX IF NOT EXISTS ux_hero_refs_capture
    ON hero_refs(hero_guid, profile_id, state, variant) WHERE source = 'capture';

CREATE TABLE IF NOT EXISTS game_builds (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    build_string  TEXT NOT NULL UNIQUE,
    patch_label   TEXT,
    first_seen_at TEXT NOT NULL,
    last_seen_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS scrims (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    played_on      TEXT,
    opponent_label TEXT,
    our_team_id    TEXT,                    -- mirrors faceit.teams.id (optional)
    map_name       TEXT,
    map_guid       TEXT,
    winner_side    TEXT CHECK(winner_side IN ('a','b','draw') OR winner_side IS NULL),
    notes          TEXT
);

CREATE TABLE IF NOT EXISTS map_instances (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    source_type    TEXT NOT NULL CHECK(source_type IN ('faceit','scrim')),
    match_id       TEXT,                    -- -> faceit.games(match_id, game_no)
    game_no        INTEGER,
    scrim_id       INTEGER REFERENCES scrims(id),
    demo_code      TEXT,
    map_guid       TEXT,
    map_name       TEXT,
    map_category   TEXT,
    side_a_team_id TEXT,                     -- side_a = LEFT on the HUD
    side_a_label   TEXT,
    side_b_team_id TEXT,
    side_b_label   TEXT,
    winner_side    TEXT CHECK(winner_side IN ('a','b','draw') OR winner_side IS NULL),
    build_id       INTEGER REFERENCES game_builds(id),
    profile_id     INTEGER REFERENCES roi_profiles(id),
    map_verified   INTEGER CHECK(map_verified IN (0,1)),   -- see SPEC §9
    captured_at    TEXT,
    finalized_at   TEXT,                     -- NULL => draft (excluded from exports)
    bans_json      TEXT,                     -- banned hero guids for this map (JSON)
    -- Exactly one of (match_id AND game_no) or scrim_id is non-null.
    CHECK ((match_id IS NOT NULL AND game_no IS NOT NULL AND scrim_id IS NULL)
        OR (match_id IS NULL AND game_no IS NULL AND scrim_id IS NOT NULL)),
    UNIQUE(match_id, game_no),
    UNIQUE(scrim_id)
);

CREATE TABLE IF NOT EXISTS comps (
    comp_id           TEXT PRIMARY KEY,       -- sha1 of sorted hero_guids
    hero_guids_json   TEXT NOT NULL,
    hero_names_sorted TEXT NOT NULL,
    tank_count        INTEGER NOT NULL,
    damage_count      INTEGER NOT NULL,
    support_count     INTEGER NOT NULL,
    team_size         INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS comp_observations (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    map_instance_id INTEGER NOT NULL REFERENCES map_instances(id),
    side            TEXT NOT NULL CHECK(side IN ('a','b')),
    sample_ts_ms    INTEGER NOT NULL,
    comp_id         TEXT REFERENCES comps(comp_id),   -- NULL until every slot resolves
    min_slot_confidence REAL,
    resolved        INTEGER NOT NULL CHECK(resolved IN (0,1)),
    frame_path      TEXT,
    sub_map         TEXT,                     -- control-map sub-map, e.g. 'Lighthouse'
    round_no        INTEGER,                  -- operator-marked round/point number
    UNIQUE(map_instance_id, side, sample_ts_ms)
);

CREATE TABLE IF NOT EXISTS comp_slots (
    observation_id INTEGER NOT NULL REFERENCES comp_observations(id),
    slot_index     INTEGER NOT NULL,
    hero_guid      TEXT,
    confidence     REAL,
    is_dead        INTEGER CHECK(is_dead IN (0,1)),
    expected_role  TEXT,
    ingame_name_raw TEXT,
    player_id      TEXT,                     -- resolved via player_aliases
    PRIMARY KEY(observation_id, slot_index)
);

CREATE TABLE IF NOT EXISTS player_aliases (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    player_id     TEXT NOT NULL,             -- mirrors faceit.players.id
    ingame_name   TEXT NOT NULL,
    first_seen_at TEXT,
    last_seen_at  TEXT,
    confirmed     INTEGER CHECK(confirmed IN (0,1)),
    UNIQUE(player_id, ingame_name)
);

CREATE TABLE IF NOT EXISTS capture_log (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    ran_at          TEXT NOT NULL,
    demo_code       TEXT,
    map_instance_id INTEGER REFERENCES map_instances(id),
    samples_taken   INTEGER,
    samples_written INTEGER,
    low_confidence  INTEGER,
    banned_hero_hits INTEGER,
    map_mismatch    INTEGER CHECK(map_mismatch IN (0,1) OR map_mismatch IS NULL),
    errors          INTEGER
);

CREATE TABLE IF NOT EXISTS wipes (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    wiped_at     TEXT NOT NULL UNIQUE,
    build_string TEXT,
    source       TEXT NOT NULL CHECK(source IN ('announced','observed')),
    notes        TEXT
);

CREATE TABLE IF NOT EXISTS code_status (
    demo_code     TEXT PRIMARY KEY,
    first_seen_at TEXT,
    status        TEXT NOT NULL CHECK(status IN ('unknown','captured','skipped','failed')),
    notes         TEXT
);

-- Optional single-portrait ROI used only by 'refs learn' (teaching HUD refs
-- from a solo custom-game replay, where one hero sits in one box). Separate
-- from the profile's 10 capture slots; one per profile.
CREATE TABLE IF NOT EXISTS learn_slots (
    profile_id INTEGER PRIMARY KEY REFERENCES roi_profiles(id),
    rect_json  TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

-- Heroes added by the operator ahead of faceit's roster catching up (OW2 is a
-- live game). Merged with faceit.heroes for learning and matching; guids are
-- namespaced 'custom:...' so they never collide with faceit guids.
CREATE TABLE IF NOT EXISTS custom_heroes (
    guid     TEXT PRIMARY KEY,
    name     TEXT NOT NULL UNIQUE,
    role     TEXT CHECK(role IN ('tank','damage','support') OR role IS NULL),
    added_at TEXT NOT NULL
);
"""

# The known wipe that invalidated every stored S9 code (SPEC §2, §4). Seeded
# idempotently; a code whose game pre-dates MAX(wiped_at) is dead by definition.
_SEED_WIPES = [
    ("2026-07-14", "observed", "invalidated all S9 regular season codes"),
]


def _utcnow() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _winner_side(winner_faction: Optional[str], side_a_faction: str) -> Optional[str]:
    """Map a faceit winner faction onto HUD side 'a'/'b' given which faction is
    side A. None winner -> None."""
    if winner_faction not in ("faction1", "faction2"):
        return None
    return "a" if winner_faction == side_a_faction else "b"


class Database:
    """Thin wrapper around the owscout SQLite connection.

    WAL + a busy timeout cost nothing on local disk and buy safety if the CI
    job or a launcher ever runs concurrently (SPEC §3).
    """

    def __init__(self, path: str) -> None:
        self.path = path
        # uri=True so ATTACH can use a read-only file: URI for the faceit DB.
        # A plain filename (not starting "file:") is still used verbatim.
        self.conn = sqlite3.connect(path, uri=True)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode = WAL")
        self.conn.execute("PRAGMA busy_timeout = 5000")
        self.conn.execute("PRAGMA foreign_keys = ON")
        self._faceit_attached = False
        self.init_schema()

    def init_schema(self) -> None:
        self._migrate()
        self.conn.executescript(SCHEMA)
        for wiped_at, source, notes in _SEED_WIPES:
            self.conn.execute(
                "INSERT OR IGNORE INTO wipes (wiped_at, source, notes) VALUES (?, ?, ?)",
                (wiped_at, source, notes),
            )
        self.conn.commit()

    def _migrate(self) -> None:
        """In-place upgrades for DBs created before a column existed. Runs before
        the CREATE-IF-NOT-EXISTS schema, which can't add columns to a live table."""
        tables = {r[0] for r in self.conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
        if "hero_refs" in tables:
            cols = {r[1] for r in self.conn.execute("PRAGMA table_info(hero_refs)")}
            if "variant" not in cols:
                # Existing refs are all from the left/blue team.
                self.conn.execute(
                    "ALTER TABLE hero_refs ADD COLUMN variant TEXT NOT NULL DEFAULT 'a'")
                self.conn.execute("DROP INDEX IF EXISTS ux_hero_refs_capture")
                self.conn.commit()
        if "map_instances" in tables:
            cols = {r[1] for r in self.conn.execute("PRAGMA table_info(map_instances)")}
            if "finalized_at" not in cols:
                self.conn.execute("ALTER TABLE map_instances ADD COLUMN finalized_at TEXT")
                self.conn.commit()
            if "bans_json" not in cols:
                self.conn.execute("ALTER TABLE map_instances ADD COLUMN bans_json TEXT")
                self.conn.commit()
        if "comp_observations" in tables:
            cols = {r[1] for r in self.conn.execute("PRAGMA table_info(comp_observations)")}
            if "sub_map" not in cols:
                self.conn.execute("ALTER TABLE comp_observations ADD COLUMN sub_map TEXT")
                self.conn.commit()
            if "round_no" not in cols:
                self.conn.execute("ALTER TABLE comp_observations ADD COLUMN round_no INTEGER")
                self.conn.commit()

    # --- read-only ATTACH of the faceit DB (SPEC §3) -------------------------

    def attach_faceit(self, faceit_db_path: str) -> None:
        """ATTACH faceit.sqlite3 read-only as schema ``faceit``. Idempotent.

        Read-only is enforced by the ``mode=ro`` URI at the SQLite level, not by
        our discipline — a write against ``faceit.*`` raises. Cross-DB joins then
        work; cross-DB foreign keys do not (SPEC §3), so faceit keys are plain
        validated columns."""
        if self._faceit_attached:
            return
        self.conn.execute("ATTACH DATABASE ? AS faceit", (faceit_ro_uri(faceit_db_path),))
        self._faceit_attached = True

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

    # --- roi_profiles --------------------------------------------------------

    def save_profile(self, profile: RoiProfile) -> int:
        """Persist a profile, retiring any active profile for the same
        (resolution_w, resolution_h, hud_variant) first.

        Re-calibration is expected after HUD-affecting patches (SPEC §5, §9.3);
        keeping the old rows as ``retired`` preserves the history rather than
        clobbering it. Returns the new profile's row id.
        """
        now = _utcnow()
        with self.transaction() as c:
            c.execute(
                """UPDATE roi_profiles SET retired_at = ?
                   WHERE resolution_w = ? AND resolution_h = ?
                     AND hud_variant = ? AND retired_at IS NULL""",
                (now, profile.resolution_w, profile.resolution_h, profile.hud_variant),
            )
            cur = c.execute(
                """INSERT INTO roi_profiles (
                       resolution_w, resolution_h, hud_variant, team_size,
                       slots_json, anchors_json, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    profile.resolution_w,
                    profile.resolution_h,
                    profile.hud_variant,
                    profile.team_size,
                    profile.slots_json(),
                    profile.anchors_json(),
                    now,
                ),
            )
        profile.id = int(cur.lastrowid or 0)
        profile.created_at = now
        return profile.id

    def set_learn_slot(self, profile_id: int, rect: Rect) -> None:
        """Store (replace) the single-portrait ROI used by ``refs learn`` for a
        profile. Independent of the profile's capture slots."""
        with self.transaction() as c:
            c.execute(
                """INSERT INTO learn_slots (profile_id, rect_json, updated_at)
                   VALUES (?, ?, ?)
                   ON CONFLICT(profile_id) DO UPDATE SET
                       rect_json = excluded.rect_json,
                       updated_at = excluded.updated_at""",
                (profile_id, json.dumps(rect.as_list()), _utcnow()),
            )

    def clear_learn_slot(self, profile_id: int) -> None:
        """Forget the single-portrait learn ROI, reverting ``refs learn`` to
        scanning all ten slots."""
        with self.transaction() as c:
            c.execute("DELETE FROM learn_slots WHERE profile_id = ?", (profile_id,))

    # --- custom heroes (live-game roster additions) --------------------------

    def add_custom_hero(self, name: str, role: Optional[str] = None) -> str:
        """Register a hero not yet in faceit.heroes (a freshly-released OW2 hero).
        Returns its namespaced guid. Idempotent on name (updates the role)."""
        name = name.strip()
        if not name:
            raise ValueError("hero name is required")
        slug = "".join(ch.lower() if ch.isalnum() else "_" for ch in name).strip("_")
        guid = f"custom:{slug}"
        with self.transaction() as c:
            c.execute(
                """INSERT INTO custom_heroes (guid, name, role, added_at)
                   VALUES (?, ?, ?, ?)
                   ON CONFLICT(name) DO UPDATE SET role = excluded.role""",
                (guid, name, role, _utcnow()),
            )
        return guid

    def list_custom_heroes(self) -> list[FaceitHero]:
        """Operator-added heroes, as FaceitHero records to merge with the roster."""
        rows = self.conn.execute(
            "SELECT guid, name, role FROM custom_heroes ORDER BY name").fetchall()
        return [FaceitHero(guid=str(r["guid"]), name=str(r["name"]), role=r["role"])
                for r in rows]

    def remove_custom_hero(self, guid: str) -> None:
        with self.transaction() as c:
            c.execute("DELETE FROM custom_heroes WHERE guid = ?", (guid,))

    def get_learn_slot(self, profile_id: int) -> Optional[Rect]:
        """The single-portrait learn ROI for a profile, or None if not set."""
        row = self.conn.execute(
            "SELECT rect_json FROM learn_slots WHERE profile_id = ?",
            (profile_id,),
        ).fetchone()
        return None if row is None else Rect.from_list(json.loads(row["rect_json"]))

    def get_active_profile(
        self, resolution_w: int, resolution_h: int, hud_variant: str = "default"
    ) -> Optional[RoiProfile]:
        """The current (non-retired) profile for a (resolution, variant), or
        None. A profile is only valid at the resolution it was calibrated on."""
        row = self.conn.execute(
            """SELECT * FROM roi_profiles
               WHERE resolution_w = ? AND resolution_h = ?
                 AND hud_variant = ? AND retired_at IS NULL
               ORDER BY id DESC LIMIT 1""",
            (resolution_w, resolution_h, hud_variant),
        ).fetchone()
        return None if row is None else self._row_to_profile(row)

    def latest_active_profile(
        self, hud_variant: str = "default"
    ) -> Optional[RoiProfile]:
        """The most recent active profile for a HUD variant, across resolutions.
        Used offline (e.g. ``refs verify``) where no live frame is available."""
        row = self.conn.execute(
            """SELECT * FROM roi_profiles
               WHERE hud_variant = ? AND retired_at IS NULL
               ORDER BY id DESC LIMIT 1""",
            (hud_variant,),
        ).fetchone()
        return None if row is None else self._row_to_profile(row)

    # --- hero_refs -----------------------------------------------------------

    def save_ref(
        self,
        *,
        hero_guid: str,
        profile_id: int,
        state: str,
        image_path: str,
        phash: str,
        source: str = "capture",
        variant: str = "a",
    ) -> int:
        """Store a reference portrait. A 'capture' ref replaces the existing
        canonical one for (hero, profile, state, variant) — idempotent re-capture
        (SPEC §12). 'review' refs are additive. ``variant`` distinguishes the
        blue-team ('a') from the red-team ('b') portrait. Returns the row id."""
        now = _utcnow()
        with self.transaction() as c:
            if source == "capture":
                c.execute(
                    """DELETE FROM hero_refs
                       WHERE hero_guid = ? AND profile_id = ? AND state = ?
                         AND variant = ? AND source = 'capture'""",
                    (hero_guid, profile_id, state, variant),
                )
            cur = c.execute(
                """INSERT INTO hero_refs (
                       hero_guid, profile_id, state, image_path, phash,
                       added_at, source, variant)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (hero_guid, profile_id, state, image_path, phash, now, source, variant),
            )
        return int(cur.lastrowid or 0)

    def get_refs(
        self,
        profile_id: int,
        *,
        state: Optional[str] = None,
        source: Optional[str] = None,
    ) -> list[HeroRef]:
        """All refs for a profile, optionally filtered by state and/or source."""
        sql = "SELECT * FROM hero_refs WHERE profile_id = ?"
        params: list[object] = [profile_id]
        if state is not None:
            sql += " AND state = ?"
            params.append(state)
        if source is not None:
            sql += " AND source = ?"
            params.append(source)
        sql += " ORDER BY hero_guid, state, id"
        rows = self.conn.execute(sql, params).fetchall()
        return [self._row_to_ref(r) for r in rows]

    @staticmethod
    def _row_to_ref(row: sqlite3.Row) -> HeroRef:
        return HeroRef(
            id=int(row["id"]),
            hero_guid=str(row["hero_guid"]),
            profile_id=int(row["profile_id"]),
            state=str(row["state"]),
            image_path=str(row["image_path"]),
            phash=str(row["phash"]),
            added_at=row["added_at"],
            source=str(row["source"]),
            variant=str(row["variant"]) if "variant" in row.keys() else "a",
        )

    @staticmethod
    def _row_to_profile(row: sqlite3.Row) -> RoiProfile:
        return RoiProfile(
            id=int(row["id"]),
            resolution_w=int(row["resolution_w"]),
            resolution_h=int(row["resolution_h"]),
            hud_variant=str(row["hud_variant"]),
            team_size=int(row["team_size"]),
            slots=RoiProfile.slots_from_json(row["slots_json"]),
            anchors=RoiProfile.anchors_from_json(row["anchors_json"]),
            created_at=row["created_at"],
            retired_at=row["retired_at"],
        )

    # --- wipes / code_status -------------------------------------------------

    def latest_wipe_date(self) -> Optional[str]:
        """MAX(wiped_at). Any code whose game pre-dates this is dead (SPEC §2)."""
        row = self.conn.execute("SELECT MAX(wiped_at) AS w FROM wipes").fetchone()
        return None if row is None or row["w"] is None else str(row["w"])

    def upsert_code_status(
        self, demo_code: str, status: str, notes: Optional[str] = None
    ) -> None:
        """Record operator INTENT/outcome for a code. Viability is NOT stored
        here — it derives from ``wipes`` (SPEC §4)."""
        with self.transaction() as c:
            c.execute(
                """INSERT INTO code_status (demo_code, first_seen_at, status, notes)
                   VALUES (?, ?, ?, ?)
                   ON CONFLICT(demo_code) DO UPDATE SET
                       status = excluded.status, notes = excluded.notes""",
                (demo_code, _utcnow(), status, notes),
            )

    def get_code_status(self, demo_code: str) -> Optional[str]:
        row = self.conn.execute(
            "SELECT status FROM code_status WHERE demo_code = ?", (demo_code,)
        ).fetchone()
        return None if row is None else str(row["status"])

    # --- codes list / age (SPEC §7) ------------------------------------------

    def list_codes(
        self,
        faceit_db_path: str,
        *,
        team: Optional[str] = None,
        uncaptured: bool = False,
        include_wiped: bool = False,
        division: Optional[str] = DEFAULT_DIVISION,
        limit: Optional[int] = None,
    ) -> list[CodeListing]:
        """Capturable codes joined faceit games→matches→teams, with a captured
        flag (does a map_instance exist) and wipe status. Filters out codes whose
        game pre-dates the latest wipe by default (SPEC §2, §7), and restricts to
        one skill division (default Master). Newest first."""
        self.attach_faceit(faceit_db_path)
        wipe = self.latest_wipe_date()
        sql = """
            SELECT g.demo_code, g.match_id, g.game_no, mp.name AS map_name,
                   m.finished_at, t1.name AS team_a, t2.name AS team_b,
                   EXISTS(SELECT 1 FROM map_instances mi
                          WHERE mi.match_id = g.match_id AND mi.game_no = g.game_no)
                       AS captured
            FROM faceit.games g
            JOIN faceit.matches m ON m.id = g.match_id
            LEFT JOIN faceit.maps  mp ON mp.guid = g.map_guid
            LEFT JOIN faceit.teams t1 ON t1.id = m.faction1_team_id
            LEFT JOIN faceit.teams t2 ON t2.id = m.faction2_team_id
            LEFT JOIN faceit.championships ch ON ch.id = m.championship_id
            WHERE g.demo_code IS NOT NULL
        """
        params: list[object] = []
        if division is not None:
            sql += " AND ch.name LIKE ?"
            params.append(f"%{division}%")
        if team is not None:
            sql += " AND (t1.name = ? COLLATE NOCASE OR t2.name = ? COLLATE NOCASE)"
            params += [team, team]
        if not include_wiped and wipe is not None:
            sql += " AND substr(m.finished_at, 1, 10) > ?"
            params.append(wipe)
        if uncaptured:
            sql += """ AND NOT EXISTS(SELECT 1 FROM map_instances mi
                                      WHERE mi.match_id = g.match_id AND mi.game_no = g.game_no)"""
        sql += " ORDER BY m.finished_at DESC, g.game_no"
        if limit is not None:
            sql += " LIMIT ?"
            params.append(limit)
        rows = self.conn.execute(sql, params).fetchall()

        def is_wiped(finished_at: Optional[str]) -> bool:
            return bool(wipe and finished_at and finished_at[:10] <= wipe)

        return [
            CodeListing(
                demo_code=str(r["demo_code"]), match_id=str(r["match_id"]),
                game_no=int(r["game_no"]), map_name=r["map_name"],
                finished_at=r["finished_at"], team_a=r["team_a"], team_b=r["team_b"],
                captured=bool(r["captured"]), wiped=is_wiped(r["finished_at"]),
            )
            for r in rows
        ]

    def code_age_summary(
        self, faceit_db_path: str, division: Optional[str] = DEFAULT_DIVISION
    ) -> dict[str, object]:
        """Totals for ``owscout codes age``: latest wipe and how many stored
        codes are alive (post-wipe) vs dead, and how many captured — within one
        skill division (default Master)."""
        self.attach_faceit(faceit_db_path)
        wipe = self.latest_wipe_date()
        div = f"%{division}%" if division is not None else "%"
        total = self.conn.execute(
            """SELECT COUNT(*) FROM faceit.games g JOIN faceit.matches m ON m.id=g.match_id
               JOIN faceit.championships ch ON ch.id=m.championship_id
               WHERE g.demo_code IS NOT NULL AND ch.name LIKE ?""",
            (div,),
        ).fetchone()[0]
        alive = 0
        if wipe is not None:
            alive = self.conn.execute(
                """SELECT COUNT(*) FROM faceit.games g JOIN faceit.matches m ON m.id=g.match_id
                   JOIN faceit.championships ch ON ch.id=m.championship_id
                   WHERE g.demo_code IS NOT NULL AND ch.name LIKE ?
                     AND substr(m.finished_at,1,10) > ?""",
                (div, wipe),
            ).fetchone()[0]
        captured = self.conn.execute(
            "SELECT COUNT(*) FROM map_instances WHERE match_id IS NOT NULL"
        ).fetchone()[0]
        return {"latest_wipe": wipe, "total_codes": int(total),
                "alive_codes": int(alive), "dead_codes": int(total) - int(alive),
                "captured": int(captured)}

    # --- review (SPEC appendix) ----------------------------------------------

    def unresolved_observations(
        self, limit: Optional[int] = None
    ) -> list[dict[str, object]]:
        """Observations with at least one unresolved slot — the review queue.
        Each carries its slots so a UI can present the gaps (SPEC appendix)."""
        sql = """
            SELECT o.id, o.map_instance_id, o.side, o.sample_ts_ms, o.frame_path,
                   mi.map_name, mi.demo_code
            FROM comp_observations o
            JOIN map_instances mi ON mi.id = o.map_instance_id
            WHERE o.resolved = 0
            ORDER BY o.id
        """
        if limit is not None:
            sql += " LIMIT ?"
        rows = self.conn.execute(sql, (limit,) if limit is not None else ()).fetchall()
        out: list[dict[str, object]] = []
        for r in rows:
            slots = self.conn.execute(
                """SELECT slot_index, hero_guid, confidence, expected_role
                   FROM comp_slots WHERE observation_id = ? ORDER BY slot_index""",
                (r["id"],),
            ).fetchall()
            out.append({
                "id": int(r["id"]), "side": r["side"], "sample_ts_ms": r["sample_ts_ms"],
                "frame_path": r["frame_path"], "map_name": r["map_name"],
                "demo_code": r["demo_code"],
                "slots": [dict(s) for s in slots],
            })
        return out

    def resolve_slot(
        self,
        observation_id: int,
        slot_index: int,
        hero_guid: str,
        *,
        hero_roles: dict[str, str],
        hero_names: dict[str, str],
    ) -> bool:
        """Set a slot's hero (operator's pick). If that completes the
        observation, canonicalise + store the comp and mark it resolved. Returns
        True iff the observation became fully resolved (SPEC appendix)."""
        import json

        from .comps import canonical_comp

        with self.transaction() as c:
            c.execute(
                "UPDATE comp_slots SET hero_guid = ? WHERE observation_id = ? AND slot_index = ?",
                (hero_guid, observation_id, slot_index),
            )
            guids = [
                s["hero_guid"] for s in c.execute(
                    "SELECT hero_guid FROM comp_slots WHERE observation_id = ? ORDER BY slot_index",
                    (observation_id,),
                ).fetchall()
            ]
            if not guids or any(g is None for g in guids):
                return False
            comp = canonical_comp(guids, hero_roles, hero_names)
            c.execute(
                """INSERT INTO comps (comp_id, hero_guids_json, hero_names_sorted,
                       tank_count, damage_count, support_count, team_size)
                   VALUES (?, ?, ?, ?, ?, ?, ?) ON CONFLICT(comp_id) DO NOTHING""",
                (comp.comp_id, json.dumps(comp.hero_guids), comp.hero_names_sorted,
                 comp.tank_count, comp.damage_count, comp.support_count, comp.team_size),
            )
            c.execute(
                "UPDATE comp_observations SET comp_id = ?, resolved = 1 WHERE id = ?",
                (comp.comp_id, observation_id),
            )
        return True

    # --- derived output (SPEC §10) -------------------------------------------

    def resolved_observations(self, team_id: Optional[str] = None) -> list[ObsRow]:
        """Resolved comp observations flattened for aggregation (SPEC §10).
        Unresolved rows are excluded — bad scouting data is worse than none.
        ``team_id`` restricts to observations of that team (either HUD side)."""
        sql = """
            SELECT o.comp_id, c.hero_names_sorted AS hero_names, o.map_instance_id, o.side,
                   mi.map_guid, o.sub_map AS sub_map,
                   CASE o.side WHEN 'a' THEN mi.side_a_team_id ELSE mi.side_b_team_id END AS team_id,
                   CASE o.side WHEN 'a' THEN mi.side_a_label ELSE mi.side_b_label END AS team_name,
                   (mi.winner_side = o.side) AS won
            FROM comp_observations o
            JOIN map_instances mi ON mi.id = o.map_instance_id
            JOIN comps c ON c.comp_id = o.comp_id
            WHERE o.resolved = 1 AND o.comp_id IS NOT NULL
              AND mi.finalized_at IS NOT NULL
        """
        params: list[object] = []
        if team_id is not None:
            sql += """ AND ((o.side = 'a' AND mi.side_a_team_id = ?)
                          OR (o.side = 'b' AND mi.side_b_team_id = ?))"""
            params += [team_id, team_id]
        rows = self.conn.execute(sql, params).fetchall()
        return [
            ObsRow(
                comp_id=str(r["comp_id"]), hero_names=str(r["hero_names"]),
                map_instance_id=int(r["map_instance_id"]), side=str(r["side"]),
                map_guid=r["map_guid"], team_id=r["team_id"], won=bool(r["won"]),
                team_name=r["team_name"], sub_map=r["sub_map"],
            )
            for r in rows
        ]

    # --- draft review / finalize (the greenlight gate) -----------------------

    def list_draft_maps(self) -> list[DraftMap]:
        """Captured-but-not-finalized maps that have observations, newest first.
        These are awaiting operator review; none are in the export yet."""
        rows = self.conn.execute(
            """SELECT mi.id, mi.demo_code, mi.map_name, mi.side_a_label,
                      mi.side_b_label, mi.captured_at, COUNT(o.id) AS obs
               FROM map_instances mi
               JOIN comp_observations o ON o.map_instance_id = mi.id
               WHERE mi.finalized_at IS NULL
               GROUP BY mi.id
               ORDER BY mi.id DESC"""
        ).fetchall()
        return [
            DraftMap(id=int(r["id"]), demo_code=r["demo_code"], map_name=r["map_name"],
                     side_a=r["side_a_label"], side_b=r["side_b_label"],
                     observations=int(r["obs"]), captured_at=r["captured_at"])
            for r in rows
        ]

    def map_side_comps(
        self, map_instance_id: int
    ) -> dict[str, list[tuple[str, int, bool, Optional[str], Optional[int], Optional[float]]]]:
        """Per side ('a'/'b'), the distinct comps observed as
        (hero_names, times_seen, resolved, sub_map, round_no, min_confidence), for
        review. Grouped per round and sub-map; min_confidence is the weakest slot
        confidence seen for that comp, so shaky captures can be flagged."""
        rows = self.conn.execute(
            """SELECT o.side, o.resolved AS resolved, o.sub_map AS sub_map,
                      o.round_no AS round_no, c.hero_names_sorted AS names, COUNT(*) AS n,
                      MIN(o.min_slot_confidence) AS conf
               FROM comp_observations o
               LEFT JOIN comps c ON c.comp_id = o.comp_id
               WHERE o.map_instance_id = ?
               GROUP BY o.side, o.round_no, o.sub_map, o.comp_id
               ORDER BY o.side, o.round_no, o.sub_map, n DESC""",
            (map_instance_id,),
        ).fetchall()
        out: dict[str, list[tuple[str, int, bool, Optional[str], Optional[int], Optional[float]]]] = {"a": [], "b": []}
        for r in rows:
            out.setdefault(str(r["side"]), []).append(
                (r["names"] or "(unresolved)", int(r["n"]), bool(r["resolved"]),
                 r["sub_map"], r["round_no"], r["conf"]))
        return out

    def correct_hero_in_map(
        self, map_instance_id: int, side: str, wrong_guid: str, right_guid: str,
        *, hero_roles: dict[str, str], hero_names: dict[str, str],
    ) -> int:
        """Fix a systematic misread: replace ``wrong_guid`` with ``right_guid`` in
        every slot on ``side`` of this map, re-canonicalising each affected
        observation's comp. Returns the number of observations changed. The whole
        point of Review — one action fixes a hero the matcher got wrong."""
        import json

        from .comps import canonical_comp

        changed = 0
        with self.transaction() as c:
            obs_ids = [int(r["id"]) for r in c.execute(
                "SELECT id FROM comp_observations WHERE map_instance_id = ? AND side = ?",
                (map_instance_id, side)).fetchall()]
            for oid in obs_ids:
                n = c.execute(
                    "UPDATE comp_slots SET hero_guid = ? "
                    "WHERE observation_id = ? AND hero_guid = ?",
                    (right_guid, oid, wrong_guid)).rowcount
                if not n:
                    continue
                changed += 1
                guids = [s["hero_guid"] for s in c.execute(
                    "SELECT hero_guid FROM comp_slots WHERE observation_id = ? "
                    "ORDER BY slot_index", (oid,)).fetchall()]
                if guids and all(g is not None for g in guids):
                    comp = canonical_comp(guids, hero_roles, hero_names)
                    c.execute(
                        """INSERT INTO comps (comp_id, hero_guids_json, hero_names_sorted,
                               tank_count, damage_count, support_count, team_size)
                           VALUES (?, ?, ?, ?, ?, ?, ?) ON CONFLICT(comp_id) DO NOTHING""",
                        (comp.comp_id, json.dumps(comp.hero_guids), comp.hero_names_sorted,
                         comp.tank_count, comp.damage_count, comp.support_count, comp.team_size))
                    c.execute(
                        "UPDATE comp_observations SET comp_id = ?, resolved = 1 WHERE id = ?",
                        (comp.comp_id, oid))
        return changed

    def finalize_map(self, map_instance_id: int) -> None:
        """Greenlight a reviewed map: mark it finalized (enters exports) and its
        code captured. Idempotent."""
        now = _utcnow()
        with self.transaction() as c:
            c.execute("UPDATE map_instances SET finalized_at = ? WHERE id = ?",
                      (now, map_instance_id))
            row = c.execute("SELECT demo_code FROM map_instances WHERE id = ?",
                            (map_instance_id,)).fetchone()
            if row and row["demo_code"]:
                c.execute(
                    """INSERT INTO code_status (demo_code, first_seen_at, status, notes)
                       VALUES (?, ?, 'captured', NULL)
                       ON CONFLICT(demo_code) DO UPDATE SET status = 'captured'""",
                    (row["demo_code"], now))

    def discard_map(self, map_instance_id: int) -> None:
        """Delete a draft map and its observations — for test runs / bad captures.
        Leaves the code un-greenlit."""
        with self.transaction() as c:
            c.execute(
                """DELETE FROM comp_slots WHERE observation_id IN
                   (SELECT id FROM comp_observations WHERE map_instance_id = ?)""",
                (map_instance_id,))
            c.execute("DELETE FROM comp_observations WHERE map_instance_id = ?",
                      (map_instance_id,))
            c.execute("DELETE FROM map_instances WHERE id = ?", (map_instance_id,))

    def delete_observations_at(self, map_instance_id: int, sample_ts_ms: int) -> int:
        """Delete both sides' observations for one snapshot (undo). Returns rows removed."""
        with self.transaction() as c:
            ids = [int(r["id"]) for r in c.execute(
                "SELECT id FROM comp_observations WHERE map_instance_id = ? "
                "AND sample_ts_ms = ?", (map_instance_id, sample_ts_ms)).fetchall()]
            if ids:
                qs = ",".join("?" * len(ids))
                c.execute(f"DELETE FROM comp_slots WHERE observation_id IN ({qs})", ids)
                c.execute(f"DELETE FROM comp_observations WHERE id IN ({qs})", ids)
        return len(ids)

    def ref_variant_coverage(self, profile_id: int) -> dict[str, int]:
        """Distinct heroes with a ref, per team variant ('a' blue / 'b' red)."""
        rows = self.conn.execute(
            "SELECT variant, COUNT(DISTINCT hero_guid) AS n FROM hero_refs "
            "WHERE profile_id = ? GROUP BY variant", (profile_id,)).fetchall()
        return {str(r["variant"]): int(r["n"]) for r in rows}

    def map_status_counts(self) -> dict[str, int]:
        """Counts of draft (captured, not finalized) vs finalized maps."""
        draft = self.conn.execute(
            "SELECT COUNT(*) FROM map_instances WHERE finalized_at IS NULL").fetchone()[0]
        final = self.conn.execute(
            "SELECT COUNT(*) FROM map_instances WHERE finalized_at IS NOT NULL").fetchone()[0]
        return {"draft": int(draft), "finalized": int(final)}

    def observation_details(self, *, finalized_only: bool = True) -> list[ObsDetail]:
        """Every resolved observation with the context the scouting analysis needs
        (map/side/team/ts/round/sub-map/lineup), ordered by map then time then side
        so per-map timelines can be assembled. Finalized maps only by default."""
        import json
        sql = """
            SELECT o.map_instance_id, o.side, o.sample_ts_ms, o.sub_map, o.round_no,
                   c.hero_guids_json AS guids, mi.map_name, mi.map_category,
                   mi.side_a_label, mi.side_b_label, mi.winner_side, mi.bans_json
            FROM comp_observations o
            JOIN map_instances mi ON mi.id = o.map_instance_id
            JOIN comps c ON c.comp_id = o.comp_id
            WHERE o.resolved = 1
        """
        if finalized_only:
            sql += " AND mi.finalized_at IS NOT NULL"
        sql += " ORDER BY o.map_instance_id, o.sample_ts_ms, o.side"
        out: list[ObsDetail] = []
        for r in self.conn.execute(sql).fetchall():
            out.append(ObsDetail(
                map_instance_id=int(r["map_instance_id"]), side=str(r["side"]),
                sample_ts_ms=int(r["sample_ts_ms"]), sub_map=r["sub_map"],
                round_no=r["round_no"],
                hero_guids=tuple(json.loads(r["guids"])),
                map_name=r["map_name"], map_category=r["map_category"],
                side_a_team=r["side_a_label"], side_b_team=r["side_b_label"],
                winner_side=r["winner_side"],
                bans=tuple(json.loads(r["bans_json"])) if r["bans_json"] else (),
            ))
        return out

    def capture_coverage(self, faceit_db_path: str) -> tuple[int, int]:
        """(captured maps, total played maps) for the §10.3 bias disclosure."""
        self.attach_faceit(faceit_db_path)
        captured = self.conn.execute(
            "SELECT COUNT(*) FROM map_instances "
            "WHERE source_type = 'faceit' AND finalized_at IS NOT NULL"
        ).fetchone()[0]
        total = self.conn.execute(
            "SELECT COUNT(*) FROM faceit.games WHERE demo_code IS NOT NULL"
        ).fetchone()[0]
        return int(captured), int(total)

    def comp_hero_guids(self) -> dict[str, list[str]]:
        """comp_id -> its hero_guids (for synthetic-comp role rollups)."""
        import json
        rows = self.conn.execute("SELECT comp_id, hero_guids_json FROM comps").fetchall()
        return {str(r["comp_id"]): list(json.loads(r["hero_guids_json"])) for r in rows}

    def player_hero_maps(self, player_id: str) -> list[tuple[int, str]]:
        """Resolved (map_instance_id, hero_guid) for a player — needs player_id
        resolution during capture/review (SPEC §8.2), else empty (SPEC §10.1)."""
        rows = self.conn.execute(
            """SELECT o.map_instance_id, s.hero_guid
               FROM comp_slots s
               JOIN comp_observations o ON o.id = s.observation_id
               WHERE s.player_id = ? AND s.hero_guid IS NOT NULL AND o.resolved = 1""",
            (player_id,),
        ).fetchall()
        return [(int(r["map_instance_id"]), str(r["hero_guid"])) for r in rows]

    def team_ban_tendencies(
        self, faceit_db_path: str, team_id: str
    ) -> list[tuple[str, int]]:
        """A team's most-banned heroes from faceit.hero_bans — real data with
        thousands of rows behind it, joined in free (SPEC §10.2)."""
        self.attach_faceit(faceit_db_path)
        rows = self.conn.execute(
            """SELECT h.name AS hero, COUNT(*) AS n
               FROM faceit.hero_bans b
               JOIN faceit.matches m ON m.id = b.match_id
               JOIN faceit.heroes h ON h.guid = b.hero_guid
               WHERE (b.banned_by_faction = 'faction1' AND m.faction1_team_id = ?)
                  OR (b.banned_by_faction = 'faction2' AND m.faction2_team_id = ?)
               GROUP BY h.name ORDER BY n DESC, h.name""",
            (team_id, team_id),
        ).fetchall()
        return [(str(r["hero"]), int(r["n"])) for r in rows]

    def team_roster(
        self, faceit_db_path: str, team_id: str, limit: int = 5
    ) -> list[tuple[str, str, int]]:
        """A team's most-frequent players (player_id, nickname, maps) from
        faceit.round_players (SPEC §10.2)."""
        self.attach_faceit(faceit_db_path)
        rows = self.conn.execute(
            """SELECT rp.player_id, p.nickname, COUNT(*) AS maps
               FROM faceit.round_players rp
               LEFT JOIN faceit.players p ON p.id = rp.player_id
               WHERE rp.team_id = ?
               GROUP BY rp.player_id ORDER BY maps DESC LIMIT ?""",
            (team_id, limit),
        ).fetchall()
        return [(str(r["player_id"]), str(r["nickname"] or r["player_id"]), int(r["maps"]))
                for r in rows]

    # --- integrity / logging (SPEC §9) ---------------------------------------

    def insert_capture_log(
        self,
        *,
        demo_code: Optional[str],
        map_instance_id: Optional[int],
        samples_taken: int,
        samples_written: int,
        low_confidence: int,
        banned_hero_hits: int,
        map_mismatch: Optional[int],
        errors: int,
    ) -> None:
        self.conn.execute(
            """INSERT INTO capture_log (
                   ran_at, demo_code, map_instance_id, samples_taken,
                   samples_written, low_confidence, banned_hero_hits,
                   map_mismatch, errors)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (_utcnow(), demo_code, map_instance_id, samples_taken, samples_written,
             low_confidence, banned_hero_hits, map_mismatch, errors),
        )
        self.conn.commit()

    def set_map_verified(self, map_instance_id: int, verified: int) -> None:
        with self.transaction() as c:
            c.execute("UPDATE map_instances SET map_verified = ? WHERE id = ?",
                      (verified, map_instance_id))

    def verify_codes_rows(self, faceit_db_path: str) -> list[VerifyCodesRow]:
        """Every captured faceit instance with its map-verification outcome and
        whether its match contains a restart shell (cross-DB via ATTACH, SPEC §9.2)."""
        self.attach_faceit(faceit_db_path)
        rows = self.conn.execute(
            """SELECT mi.match_id, mi.game_no, mi.map_verified,
                      EXISTS(SELECT 1 FROM faceit.games g
                             WHERE g.match_id = mi.match_id AND g.was_restarted = 1)
                          AS has_restart
               FROM map_instances mi
               WHERE mi.source_type = 'faceit' AND mi.match_id IS NOT NULL
               ORDER BY mi.match_id, mi.game_no"""
        ).fetchall()
        return [
            VerifyCodesRow(
                match_id=str(r["match_id"]),
                game_no=int(r["game_no"]),
                map_verified=(None if r["map_verified"] is None else int(r["map_verified"])),
                match_has_restart=bool(r["has_restart"]),
            )
            for r in rows
        ]

    # --- capture persistence (SPEC §4, §7) -----------------------------------

    def upsert_map_instance_from_context(
        self,
        ctx: CodeContext,
        side_a_faction: str,
        *,
        profile_id: Optional[int] = None,
        build_id: Optional[int] = None,
        map_verified: Optional[int] = None,
    ) -> int:
        """Create/update the map_instance for a faceit code. All map/team/winner
        fields are DERIVED from the faceit context, never OCR'd (SPEC §4).
        ``side_a_faction`` says which faction is on the LEFT HUD strip.
        Idempotent on (match_id, game_no) — re-capture UPDATEs (SPEC §12)."""
        if side_a_faction not in ("faction1", "faction2"):
            raise ValueError(f"side_a_faction must be faction1/faction2, got {side_a_faction!r}")
        a_is_f1 = side_a_faction == "faction1"
        side_a_team_id = ctx.faction1_team_id if a_is_f1 else ctx.faction2_team_id
        side_a_label = ctx.faction1_team_name if a_is_f1 else ctx.faction2_team_name
        side_b_team_id = ctx.faction2_team_id if a_is_f1 else ctx.faction1_team_id
        side_b_label = ctx.faction2_team_name if a_is_f1 else ctx.faction1_team_name
        winner_side = _winner_side(ctx.winner_faction, side_a_faction)

        bans_json = json.dumps([b.hero_guid for b in ctx.bans]) if ctx.bans else None
        with self.transaction() as c:
            c.execute(
                """INSERT INTO map_instances (
                       source_type, match_id, game_no, demo_code,
                       map_guid, map_name, map_category,
                       side_a_team_id, side_a_label, side_b_team_id, side_b_label,
                       winner_side, build_id, profile_id, map_verified, captured_at, bans_json)
                   VALUES ('faceit', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(match_id, game_no) DO UPDATE SET
                       demo_code=excluded.demo_code, map_guid=excluded.map_guid,
                       map_name=excluded.map_name, map_category=excluded.map_category,
                       side_a_team_id=excluded.side_a_team_id, side_a_label=excluded.side_a_label,
                       side_b_team_id=excluded.side_b_team_id, side_b_label=excluded.side_b_label,
                       winner_side=excluded.winner_side, build_id=excluded.build_id,
                       profile_id=excluded.profile_id, map_verified=excluded.map_verified,
                       captured_at=excluded.captured_at, bans_json=excluded.bans_json""",
                (ctx.match_id, ctx.game_no, ctx.demo_code, ctx.map_guid, ctx.map_name,
                 ctx.map_category, side_a_team_id, side_a_label, side_b_team_id,
                 side_b_label, winner_side, build_id, profile_id, map_verified,
                 _utcnow(), bans_json),
            )
        row = self.conn.execute(
            "SELECT id FROM map_instances WHERE match_id = ? AND game_no = ?",
            (ctx.match_id, ctx.game_no),
        ).fetchone()
        return int(row["id"])

    def upsert_comp(self, comp: Comp) -> None:
        """Store a canonical comp. Immutable by construction, so conflicts are
        ignored (the same comp_id always describes the same five heroes)."""
        import json
        with self.transaction() as c:
            c.execute(
                """INSERT INTO comps (comp_id, hero_guids_json, hero_names_sorted,
                       tank_count, damage_count, support_count, team_size)
                   VALUES (?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(comp_id) DO NOTHING""",
                (comp.comp_id, json.dumps(comp.hero_guids), comp.hero_names_sorted,
                 comp.tank_count, comp.damage_count, comp.support_count, comp.team_size),
            )

    def upsert_comp_observation(
        self,
        *,
        map_instance_id: int,
        side: str,
        sample_ts_ms: int,
        comp_id: Optional[str],
        min_slot_confidence: Optional[float],
        resolved: int,
        slots: Sequence[Mapping[str, object]],
        frame_path: Optional[str] = None,
        comp: Optional[Comp] = None,
        sub_map: Optional[str] = None,
        round_no: Optional[int] = None,
    ) -> int:
        """Insert/replace one observation and its slots. Idempotent on
        (map_instance_id, side, sample_ts_ms) — re-capture UPDATEs (SPEC §12).

        A resolved observation's ``comp_id`` is a foreign key into ``comps``, so
        when ``comp`` is given it is inserted first, in the same transaction."""
        import json
        with self.transaction() as c:
            if comp is not None:
                c.execute(
                    """INSERT INTO comps (comp_id, hero_guids_json, hero_names_sorted,
                           tank_count, damage_count, support_count, team_size)
                       VALUES (?, ?, ?, ?, ?, ?, ?) ON CONFLICT(comp_id) DO NOTHING""",
                    (comp.comp_id, json.dumps(comp.hero_guids), comp.hero_names_sorted,
                     comp.tank_count, comp.damage_count, comp.support_count, comp.team_size),
                )
            c.execute(
                """INSERT INTO comp_observations (
                       map_instance_id, side, sample_ts_ms, comp_id,
                       min_slot_confidence, resolved, frame_path, sub_map, round_no)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(map_instance_id, side, sample_ts_ms) DO UPDATE SET
                       comp_id=excluded.comp_id,
                       min_slot_confidence=excluded.min_slot_confidence,
                       resolved=excluded.resolved, frame_path=excluded.frame_path,
                       sub_map=excluded.sub_map, round_no=excluded.round_no""",
                (map_instance_id, side, sample_ts_ms, comp_id,
                 min_slot_confidence, resolved, frame_path, sub_map, round_no),
            )
            obs_id = int(c.execute(
                """SELECT id FROM comp_observations
                   WHERE map_instance_id = ? AND side = ? AND sample_ts_ms = ?""",
                (map_instance_id, side, sample_ts_ms),
            ).fetchone()["id"])
            # Slots are rewritten wholesale so re-capture never leaves stale rows.
            c.execute("DELETE FROM comp_slots WHERE observation_id = ?", (obs_id,))
            c.executemany(
                """INSERT INTO comp_slots (observation_id, slot_index, hero_guid,
                       confidence, is_dead, expected_role, ingame_name_raw, player_id)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                [(obs_id, s["slot_index"], s.get("hero_guid"), s.get("confidence"),
                  s.get("is_dead"), s.get("expected_role"), s.get("ingame_name_raw"),
                  s.get("player_id")) for s in slots],
            )
        return obs_id

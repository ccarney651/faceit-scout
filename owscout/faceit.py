"""Read-only access to the existing ``faceit.sqlite3``.

owscout NEVER writes to the faceit DB (SPEC §3, §12). We open it via a
``file:...?mode=ro`` URI, which makes any write attempt fail at the SQLite
level — the enforcement is the connection mode, not our own discipline.

This is deliberately minimal: only the hero-roster read that ``refs`` needs.
The full ATTACH layer and ``--code`` context derivation are a later build-order
step (SPEC §13.4).
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Optional

from .models import FaceitHero

# faceit round_players.role / heroes.role values we constrain on. Anything else
# ('None', NULL, '-') is treated as unlabelled -> no role constraint (SPEC §8.1).
KNOWN_ROLES: frozenset[str] = frozenset({"Tank", "Damage", "Support"})


def faceit_ro_uri(path: str) -> str:
    """A read-only SQLite URI for the faceit DB at ``path``."""
    # as_uri() percent-encodes and gives a file:// URL; append the ro mode.
    return f"{Path(path).resolve().as_uri()}?mode=ro"


def connect_ro(path: str) -> sqlite3.Connection:
    """Open the faceit DB read-only. Writes raise ``sqlite3.OperationalError``."""
    if not Path(path).exists():
        raise FileNotFoundError(
            f"faceit DB not found: {path} — point --faceit-db / $FACEIT_DB at it"
        )
    conn = sqlite3.connect(faceit_ro_uri(path), uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def load_heroes(conn: sqlite3.Connection) -> list[FaceitHero]:
    """The authoritative hero roster from ``faceit.heroes`` (SPEC §1)."""
    rows = conn.execute(
        "SELECT guid, name, role FROM heroes ORDER BY name"
    ).fetchall()
    return [FaceitHero(guid=r["guid"], name=r["name"], role=r["role"]) for r in rows]


def hero_roles(conn: sqlite3.Connection) -> dict[str, str]:
    """Map hero_guid -> role for constraint filtering (SPEC §8.1 step 2)."""
    return {h.guid: h.role for h in load_heroes(conn) if h.role in KNOWN_ROLES}


def load_bans(conn: sqlite3.Connection, match_id: str, game_no: int) -> list[str]:
    """The banned hero_guids for a map — exactly 2 (SPEC §1). A banned hero is
    impossible for BOTH teams, so this excludes them from every slot (§8.1)."""
    rows = conn.execute(
        "SELECT hero_guid FROM hero_bans WHERE match_id = ? AND game_no = ?",
        (match_id, game_no),
    ).fetchall()
    return [r["hero_guid"] for r in rows]


def load_team_roles(
    conn: sqlite3.Connection, match_id: str, game_no: int, team_id: str
) -> list[str]:
    """The 5 role labels for a team on a map (SPEC §8.1 step 2). Unlabelled
    values are returned as-is; the caller decides whether to constrain."""
    rows = conn.execute(
        """SELECT role FROM round_players
           WHERE match_id = ? AND game_no = ? AND team_id = ?
           ORDER BY player_id""",
        (match_id, game_no, team_id),
    ).fetchall()
    return [r["role"] for r in rows]


def team_ids_for_map(
    conn: sqlite3.Connection, match_id: str
) -> tuple[Optional[str], Optional[str]]:
    """(faction1_team_id, faction2_team_id) for a match."""
    row = conn.execute(
        "SELECT faction1_team_id, faction2_team_id FROM matches WHERE id = ?",
        (match_id,),
    ).fetchone()
    if row is None:
        return None, None
    return row["faction1_team_id"], row["faction2_team_id"]


def resolve_player_id(conn: sqlite3.Connection, nickname: str) -> Optional[str]:
    """Look up a player id by nickname (case-insensitive exact, then substring)."""
    row = conn.execute(
        "SELECT id FROM players WHERE nickname = ? COLLATE NOCASE", (nickname,)
    ).fetchone()
    if row is not None:
        return str(row["id"])
    row = conn.execute(
        "SELECT id FROM players WHERE nickname LIKE ? COLLATE NOCASE ORDER BY nickname LIMIT 1",
        (f"%{nickname}%",),
    ).fetchone()
    return None if row is None else str(row["id"])


def resolve_team_id(conn: sqlite3.Connection, name: str) -> Optional[str]:
    """Look up a team id by name (case-insensitive exact, then substring)."""
    row = conn.execute(
        "SELECT id FROM teams WHERE name = ? COLLATE NOCASE", (name,)
    ).fetchone()
    if row is not None:
        return str(row["id"])
    row = conn.execute(
        "SELECT id FROM teams WHERE name LIKE ? COLLATE NOCASE ORDER BY name LIMIT 1",
        (f"%{name}%",),
    ).fetchone()
    return None if row is None else str(row["id"])

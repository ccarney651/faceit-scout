"""Typed records extracted from FACEIT payloads, plus the empirically-derived
field mappings that turn FACEIT's opaque ``i*`` stat codes into named metrics.

The mappings in this module were not guessed: they were established by pulling
several real championship matches and correlating each code against player role
(see the README "Data quality" section). Keeping them in one place makes them
trivial to correct if FACEIT changes the schema.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass, field

# --- Overwatch 2 stats: FACEIT ``i*`` code -> named per-game metric -----------
# Derived from role-correlation across real matches:
#   i8  eliminations   (Damage/Tank high)
#   i9  deaths         (~uniform ~5-6 across roles)
#   i10 assists        (Support dominates: 17.9 vs 2-5)
#   i13 damage         (Tank/Damage high)
#   i14 healing        (Support dominates: ~9600 vs <1100)
#   i17 damage_mitigated (Tank dominates: ~13200) -- bonus, tank-flavoured
STAT_FIELD_MAP: dict[str, str] = {
    "eliminations": "i8",
    "deaths": "i9",
    "assists": "i10",
    "damage": "i13",
    "healing": "i14",
    "damage_mitigated": "i17",
}

# A stats player row for a game that was played to completion but whose capture
# failed (team DC'd at game end) comes back with this sentinel role and all
# zeros. Such rows are NOT forfeits: the game counts, the stats are just absent.
UNCAPTURED_ROLE_SENTINEL = "-"

FACTION1 = "faction1"
FACTION2 = "faction2"

# Championship names carry the stage suffix ("S9 EMEA Master Central - Regular
# Season" vs "S9 EMEA Master Central - Playoffs"). The playoff classification and
# the base-name pairing are shared by ingest (which needs the sibling division's
# teams to seed a bracket crawl) and export (which attaches playoff results to
# the matching regular-season division).
_PLAYOFF_STAGE_SUFFIX = re.compile(
    r"\s*-\s*(regular season|playoffs?|playoff stage|knockout stage)\s*$",
    re.IGNORECASE,
)


def is_playoff_name(name: str | None) -> bool:
    """A playoff/knockout championship, separate from the regular-season division."""
    low = (name or "").lower()
    return "playoff" in low or "knockout" in low


def playoff_base_name(name: str | None) -> str | None:
    """The shared division name minus the stage suffix, used to pair a playoff
    championship with its regular-season division."""
    if not name:
        return None
    base = _PLAYOFF_STAGE_SUFFIX.sub("", name.strip())
    return base or None


# The season a championship belongs to is carried only by its name ("S9 EMEA
# Master Central - Regular Season"); there is no season column anywhere in the
# schema. Both the site (which season to render) and the capture feed (whose
# rosters are still active) derive it from here rather than each parsing it,
# because the numeric comparison below is easy to get wrong in a copy.
_SEASON_RE = re.compile(r"\bS(\d+)\b", re.IGNORECASE)


def season_of(name: str | None) -> str | None:
    """The season a championship name encodes ('s9', 's10', ...), or None.

    Matched with a word boundary (mirrors the region match): a bare substring
    test would let "S90 EMEA..." match "s9", or a name merely containing "s9"
    mid-word false-match.
    """
    if not name:
        return None
    m = _SEASON_RE.search(name)
    return f"s{m.group(1)}" if m else None


def newest_season(names: Iterable[str | None]) -> str | None:
    """The highest-numbered season across these championship names.

    Compared numerically, not lexically: sorted as strings 's9' beats 's10',
    which would pin the caller to the season that just ended for as long as
    both are in the database.
    """
    seasons = {s for s in (season_of(n) for n in names) if s}
    return max(seasons, key=lambda s: int(s[1:]), default=None)


def resolve_season(names: Iterable[str | None], pin: str | None) -> str | None:
    """The season a pinned export ACTUALLY renders: the pin if it has data,
    otherwise the newest season that does (None when nothing parses).

    Callers pass the names of championships that have PLAYED matches, not every
    championship: see :func:`faceit_sync.export.championship_names_with_results`
    for why a seeded-but-unplayed season must not win.

    One function because two callers must agree. The exporter falls back so a
    season pinned before its first match still publishes a live page; CI has to
    merge the SAME season's captured comps, or a fallback page shows one season's
    standings under another season's scouting - the exact commingling the pin
    exists to prevent.
    """
    names = list(names)
    want = pin.strip().lower() if pin else None
    if want and any(season_of(n) == want for n in names):
        return want
    return newest_season(names)


@dataclass(slots=True)
class Championship:
    id: str
    name: str | None
    game: str | None
    region: str | None


@dataclass(slots=True)
class Team:
    id: str
    name: str | None
    avatar_url: str | None


@dataclass(slots=True)
class Player:
    id: str
    nickname: str | None
    game_name: str | None = None   # Battle.net in-game name (what the OW HUD shows)


@dataclass(slots=True)
class Hero:
    guid: str
    name: str
    role: str | None


@dataclass(slots=True)
class Map:
    guid: str
    name: str
    category: str | None


@dataclass(slots=True)
class Match:
    id: str
    championship_id: str
    round: int | None
    group_no: int | None
    status: str
    best_of: int | None
    scheduled_at: str | None
    started_at: str | None
    finished_at: str | None
    faction1_team_id: str | None
    faction2_team_id: str | None
    winner_faction: str | None
    forfeit: bool
    fetched_at: str


@dataclass(slots=True)
class Game:
    match_id: str
    game_no: int
    map_guid: str | None
    map_category: str | None
    attacking_first_faction: str | None
    side_picked_by_faction: str | None
    faction1_score: int | None
    faction2_score: int | None
    winner_faction: str | None
    demo_code: str | None
    was_restarted: bool


@dataclass(slots=True)
class MapPick:
    match_id: str
    game_no: int
    map_guid: str | None
    picked_by_faction: str | None


@dataclass(slots=True)
class HeroBan:
    match_id: str
    game_no: int
    hero_guid: str
    ban_order: int
    banned_by_faction: str | None  # NULL when democracy absent/restarted


@dataclass(slots=True)
class RoundPlayer:
    match_id: str
    game_no: int
    team_id: str | None
    player_id: str
    role: str | None
    elo_snapshot: int | None
    stats_captured: bool
    eliminations: int | None
    deaths: int | None
    assists: int | None
    damage: int | None
    healing: int | None
    damage_mitigated: int | None


@dataclass(slots=True)
class MatchBundle:
    """Everything extracted from one match's three payloads, ready to persist."""

    match: Match
    teams: list[Team]
    players: list[Player]
    games: list[Game]
    map_picks: list[MapPick]
    hero_bans: list[HeroBan]
    round_players: list[RoundPlayer]
    heroes: list[Hero]
    maps: list[Map]
    warnings: list[str] = field(default_factory=list)

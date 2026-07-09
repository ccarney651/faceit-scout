"""Typed records extracted from FACEIT payloads, plus the empirically-derived
field mappings that turn FACEIT's opaque ``i*`` stat codes into named metrics.

The mappings in this module were not guessed: they were established by pulling
several real championship matches and correlating each code against player role
(see the README "Data quality" section). Keeping them in one place makes them
trivial to correct if FACEIT changes the schema.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

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


@dataclass(slots=True)
class Championship:
    id: str
    name: Optional[str]
    game: Optional[str]
    region: Optional[str]


@dataclass(slots=True)
class Team:
    id: str
    name: Optional[str]
    avatar_url: Optional[str]


@dataclass(slots=True)
class Player:
    id: str
    nickname: Optional[str]


@dataclass(slots=True)
class Hero:
    guid: str
    name: str
    role: Optional[str]


@dataclass(slots=True)
class Map:
    guid: str
    name: str
    category: Optional[str]


@dataclass(slots=True)
class Match:
    id: str
    championship_id: str
    round: Optional[int]
    group_no: Optional[int]
    status: str
    best_of: Optional[int]
    scheduled_at: Optional[str]
    started_at: Optional[str]
    finished_at: Optional[str]
    faction1_team_id: Optional[str]
    faction2_team_id: Optional[str]
    winner_faction: Optional[str]
    forfeit: bool
    fetched_at: str


@dataclass(slots=True)
class Game:
    match_id: str
    game_no: int
    map_guid: Optional[str]
    map_category: Optional[str]
    attacking_first_faction: Optional[str]
    side_picked_by_faction: Optional[str]
    faction1_score: Optional[int]
    faction2_score: Optional[int]
    winner_faction: Optional[str]
    demo_code: Optional[str]
    was_restarted: bool


@dataclass(slots=True)
class MapPick:
    match_id: str
    game_no: int
    map_guid: Optional[str]
    picked_by_faction: Optional[str]


@dataclass(slots=True)
class HeroBan:
    match_id: str
    game_no: int
    hero_guid: str
    ban_order: int
    banned_by_faction: Optional[str]  # NULL when democracy absent/restarted


@dataclass(slots=True)
class RoundPlayer:
    match_id: str
    game_no: int
    team_id: Optional[str]
    player_id: str
    role: Optional[str]
    elo_snapshot: Optional[int]
    stats_captured: bool
    eliminations: Optional[int]
    deaths: Optional[int]
    assists: Optional[int]
    damage: Optional[int]
    healing: Optional[int]
    damage_mitigated: Optional[int]


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

"""Competitive seat assignments ("subroles") for hero display and analysis.

Organised OW is played in five seats — Tank, Hitscan DPS, Flex DPS, Main
Support, Flex Support — and teams think in seats, not in the game's three
roles. A comp printed in seat order reads as a lineup; hero pools compared
seat-by-seat show where a matchup is actually contested.

Hero->seat is genuinely fuzzy at the edges (the operator's own caveat): some
heroes are played from either DPS seat depending on the team. This table is the
STATIC baseline — heroes absent from it fall back to their base role in every
consumer, so an unclassified hero degrades to today's behaviour rather than
being guessed. The proper resolution of the ambiguity arrives with player
attribution: once captures say WHO played a hero, each team's seats are
inferable from their own data and can override this table per team.

DUAL marks heroes commonly played from both DPS seats; consumers may choose to
display the primary seat (the dict value) while treating matches against either
seat as valid.
"""

from __future__ import annotations

TANK = "Tank"
HITSCAN = "Hitscan"
FLEX_DPS = "Flex DPS"
MAIN_SUPPORT = "Main Support"
FLEX_SUPPORT = "Flex Support"

SEAT_ORDER: tuple[str, ...] = (TANK, HITSCAN, FLEX_DPS, MAIN_SUPPORT, FLEX_SUPPORT)

# Primary seat per hero. Deliberately incomplete: 2026-era heroes the curator
# has not classified yet are left out and fall back to base role.
SUBROLE: dict[str, str] = {
    # Tanks are one seat.
    "DVa": TANK, "Domina": TANK, "Doomfist": TANK, "Hazard": TANK,
    "Junker Queen": TANK, "Mauga": TANK, "Orisa": TANK, "Ramattra": TANK,
    "Reinhardt": TANK, "Roadhog": TANK, "Sigma": TANK, "Winston": TANK,
    "Wrecking Ball": TANK, "Zarya": TANK,
    # Hitscan seat.
    "Ashe": HITSCAN, "Cassidy": HITSCAN, "Sojourn": HITSCAN,
    "Soldier 76": HITSCAN, "Tracer": HITSCAN, "Widowmaker": HITSCAN,
    "Sombra": HITSCAN,
    # Flex DPS seat.
    "Bastion": FLEX_DPS, "Echo": FLEX_DPS, "Genji": FLEX_DPS,
    "Hanzo": FLEX_DPS, "Junkrat": FLEX_DPS, "Mei": FLEX_DPS,
    "Pharah": FLEX_DPS, "Reaper": FLEX_DPS, "Symmetra": FLEX_DPS,
    "Torbjorn": FLEX_DPS, "Venture": FLEX_DPS,
    # Main support seat.
    "Brigitte": MAIN_SUPPORT, "LifeWeaver": MAIN_SUPPORT, "Lucio": MAIN_SUPPORT,
    "Mercy": MAIN_SUPPORT, "Moira": MAIN_SUPPORT,
    # Flex support seat.
    "Ana": FLEX_SUPPORT, "Baptiste": FLEX_SUPPORT, "Illari": FLEX_SUPPORT,
    "Kiriko": FLEX_SUPPORT, "Zenyatta": FLEX_SUPPORT,
    # ---- awaiting curator classification (2026 heroes + genuine edge cases):
    # Anran, Emre, Freja, Shion, Sierra, Vendetta (Damage)
    # Jetpack Cat, Juno, Mizuki, Wuyang (Support)
}

# Commonly played from both DPS seats; the dict above holds the primary.
DUAL: frozenset[str] = frozenset({"Tracer", "Sombra", "Hanzo"})


def seat_of(hero_name: str) -> str | None:
    """The hero's competitive seat, or None when unclassified."""
    return SUBROLE.get(hero_name)

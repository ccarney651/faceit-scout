"""Typed records for owscout, plus JSON (de)serialisation for the pieces that
persist as opaque columns.

Pixel coordinates live in the DB, never in source (SPEC §5). Several of these
types are the in-memory shape of what gets written to owscout tables; the
faceit-derived records (``FaceitHero``, ``CodeContext`` and friends) mirror
read-only faceit rows.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import NamedTuple

# The observer HUD carries `team_size` hero portraits per team. Read the real
# value from `roi_profiles.team_size`; this is only the default when the
# operator does not override it (SPEC §4: "do not hardcode 5 anywhere").
DEFAULT_TEAM_SIZE = 5

# The assumed working resolution. SPEC §5: assume 2560x1440 but DERIVE it from
# the grabbed frame, never assume it. A profile is only valid at the resolution
# it was calibrated on.
WORKING_RESOLUTION: tuple[int, int] = (2560, 1440)

# side_a is the LEFT HUD strip, side_b the RIGHT (SPEC §4, map_instances).
SIDE_LEFT = "a"
SIDE_RIGHT = "b"

# FACEIT championships split into skill divisions named in the championship title
# ("... Master Central ...", "... Expert Central ..."). owscout defaults to Master.
DEFAULT_DIVISION = "master"


def division_of(championship_name: str | None) -> str | None:
    """The skill division a championship belongs to, from its name."""
    if not championship_name:
        return None
    low = championship_name.lower()
    if "master" in low:
        return "master"
    if "expert" in low:
        return "expert"
    return None

# A hero portrait is captured in two visual states (SPEC §6). "dead" is a
# greyed/desaturated STATE of the same hero, not a different hero — the
# hero_guid must still resolve when dead.
STATE_ALIVE = "alive"
STATE_DEAD = "dead"
REF_STATES: tuple[str, ...] = (STATE_ALIVE, STATE_DEAD)


class FaceitHero(NamedTuple):
    """A hero row read (read-only) from ``faceit.heroes`` — the authoritative
    roster for the data's patch (SPEC §1)."""

    guid: str
    name: str
    role: str | None


class CodeListing(NamedTuple):
    """A capturable demo_code with its context, for ``owscout codes list`` (SPEC §7)."""

    demo_code: str
    match_id: str
    game_no: int
    map_name: str | None
    finished_at: str | None
    team_a: str | None
    team_b: str | None
    captured: bool
    wiped: bool


class Rect(NamedTuple):
    """An axis-aligned pixel box: (x, y, w, h), top-left origin."""

    x: int
    y: int
    w: int
    h: int

    def as_list(self) -> list[int]:
        return [self.x, self.y, self.w, self.h]

    @classmethod
    def from_list(cls, values: list[int] | tuple[int, ...]) -> "Rect":
        x, y, w, h = values
        return cls(int(x), int(y), int(w), int(h))

    @property
    def is_empty(self) -> bool:
        return self.w <= 0 or self.h <= 0


@dataclass(frozen=True)
class Anchor:
    """A fixed HUD landmark used at runtime to decide "is this a live match
    view, or a menu/killcam/loading screen" (SPEC §5 step 3, §7.3)."""

    name: str
    rect: Rect


@dataclass
class RoiProfile:
    """A calibrated set of ROIs for one (resolution, hud_variant).

    ``slots`` maps side ("a"/"b") -> the per-slot portrait boxes, left-to-right.
    """

    resolution_w: int
    resolution_h: int
    hud_variant: str
    team_size: int
    slots: dict[str, list[Rect]]
    anchors: list[Anchor]
    id: int | None = None
    created_at: str | None = None
    retired_at: str | None = None

    def valid_at(self, width: int, height: int) -> bool:
        """A profile is invalid at any other resolution (SPEC §5)."""
        return self.resolution_w == width and self.resolution_h == height

    # --- JSON columns --------------------------------------------------------

    def slots_json(self) -> str:
        return json.dumps(
            {side: [r.as_list() for r in rects] for side, rects in self.slots.items()}
        )

    def anchors_json(self) -> str:
        return json.dumps(
            [{"name": a.name, "rect": a.rect.as_list()} for a in self.anchors]
        )

    @staticmethod
    def slots_from_json(raw: str) -> dict[str, list[Rect]]:
        data = json.loads(raw)
        return {side: [Rect.from_list(v) for v in rects] for side, rects in data.items()}

    @staticmethod
    def anchors_from_json(raw: str) -> list[Anchor]:
        data = json.loads(raw)
        return [Anchor(name=a["name"], rect=Rect.from_list(a["rect"])) for a in data]


@dataclass(frozen=True)
class BanInfo:
    hero_guid: str
    hero_name: str | None
    banned_by_faction: str | None   # 'faction1' | 'faction2' | None (restart/expired)
    banned_by_team_id: str | None


@dataclass(frozen=True)
class PlayerInfo:
    team_id: str | None
    team_name: str | None
    faction: str | None             # 'faction1' | 'faction2'
    player_id: str
    nickname: str | None
    role: str | None


@dataclass(frozen=True)
class CodeContext:
    """Everything a demo_code implies, derived from the faceit DB (SPEC §7). The
    operator supplies six characters; owscout supplies the context."""

    demo_code: str
    match_id: str
    game_no: int
    map_guid: str | None
    map_name: str | None
    map_category: str | None
    faction1_team_id: str | None
    faction1_team_name: str | None
    faction2_team_id: str | None
    faction2_team_name: str | None
    winner_faction: str | None      # 'faction1' | 'faction2' | None
    bans: list[BanInfo]
    players: list[PlayerInfo]
    already_captured: bool             # a map_instance already exists (cross-DB)
    championship_name: str | None = None
    division: str | None = None        # 'master' | 'expert' | None, from the championship name

    def team_name(self, faction: str | None) -> str | None:
        if faction == "faction1":
            return self.faction1_team_name
        if faction == "faction2":
            return self.faction2_team_name
        return None


@dataclass(frozen=True)
class Comp:
    """A canonical, order-independent team composition (SPEC §4 ``comps``).
    ``comp_id`` is the sha1 of the sorted hero_guids, so the same five heroes
    always hash to the same id regardless of slot order."""

    comp_id: str
    hero_guids: list[str]          # sorted, canonical
    hero_names_sorted: str
    tank_count: int
    damage_count: int
    support_count: int
    team_size: int


@dataclass(frozen=True)
class HeroRef:
    """A stored reference portrait for one hero, in one visual state, under one
    ROI profile (SPEC §4 ``hero_refs``). ``phash`` is a hex-encoded perceptual
    hash used both to match at runtime and to flag near-duplicate refs."""

    hero_guid: str
    profile_id: int
    state: str
    image_path: str
    phash: str
    source: str  # 'capture' | 'review'
    id: int | None = None
    added_at: str | None = None

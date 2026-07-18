"""Control-map sub-map reference data.

OW2 control maps rotate between named sub-maps with distinct geometry, and
different sub-maps favour different comps — so a captured comp is more useful when
tagged with the sub-map being played. Non-control maps (Push/Escort/Hybrid/
Flashpoint) are treated as single-geometry here and return no sub-maps.

Pure data + lookup, so it is unit-tested without the game or DB.
"""

from __future__ import annotations

# Lowercased canonical map name -> ordered sub-maps (control point rotation).
CONTROL_SUBMAPS: dict[str, list[str]] = {
    "ilios": ["Lighthouse", "Ruins", "Well"],
    "lijiang tower": ["Control Center", "Garden", "Night Market"],
    "nepal": ["Sanctum", "Shrine", "Village"],
    "oasis": ["City Center", "Gardens", "University"],
    "antarctic peninsula": ["Icebreaker", "Labs", "Sublevel"],
    "samoa": ["Beach", "Downtown", "Volcano"],
    "busan": ["Downtown", "Sanctuary", "MEKA Base"],
}

# Map-name spellings seen in the faceit data -> a canonical key above.
_ALIASES: dict[str, str] = {
    "antarctica": "antarctic peninsula",
    "lijiang": "lijiang tower",
}


def submaps_for(map_name: str | None) -> list[str]:
    """The sub-maps for a control map, in rotation order — or an empty list if the
    map is not a control map (case-insensitive, alias-aware)."""
    if not map_name:
        return []
    key = map_name.strip().lower()
    key = _ALIASES.get(key, key)
    return list(CONTROL_SUBMAPS.get(key, []))


def is_control_map(map_name: str | None) -> bool:
    """Whether the map rotates between sub-maps (i.e. sub-map tagging applies)."""
    return bool(submaps_for(map_name))

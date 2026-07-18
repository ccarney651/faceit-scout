"""Multi-contributor scouting data: the exchange format and the merge.

owscout is built to become a public tool, which changes what a "publish" is. A
single operator can publish *conclusions* — a finished report — because nothing
else has to combine with it. Many contributors cannot: two summaries do not merge,
and a summary is frozen against the analysis that produced it.

So the unit of contribution is the raw OBSERVATION, and the report is derived
centrally from everyone's observations. Two consequences make this worth the
change:

* improvements to the analysis apply retroactively to every past contribution,
  rather than only to data captured afterwards; and
* the same map captured by two people can be reconciled, because there is
  something to compare.

**Identity is the load-bearing detail.** ``map_instances.id`` is a local
autoincrement: Alice's map #20 and Bob's map #7 can be the same real game, and
nothing in the row says so. Merging on it silently double-counts — measured on
real data, 8 maps became 9 and 16 rounds became 20, inflating every rate that
divides by them. The canonical identity is FACEIT's ``(match_id, game_no)``, which
is the same on every machine. **Local ids never leave the machine.**

Conflict policy is FIRST-WINS: whoever submits a map first owns it, that
contributor may update their own submission, and other views of the same map are
IGNORED but retained. Ignoring is reversible and rejecting is not — a broken first
submission can then be replaced from data already in hand instead of asking
someone to re-scout.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Iterable, Mapping, NamedTuple, Optional, Sequence

from .models import ObsDetail

log = logging.getLogger("owscout.contribute")

# Bump when the on-disk shape changes incompatibly. Readers refuse formats they
# do not understand rather than silently misreading a contributor's data.
CONTRIB_FORMAT = 1

CONTRIB_DIR = "data/captures"


class MapKey(NamedTuple):
    """The identity of a real game, stable across every contributor's machine."""

    match_id: str
    game_no: int


class MergeResult(NamedTuple):
    """``maps`` is the accepted view of each game; ``owner`` says who claimed it;
    ``ignored`` lists (contributor, key) for later views that were not used —
    retained deliberately, see the module docstring."""

    maps: dict[MapKey, dict[str, Any]]
    owner: dict[MapKey, str]
    ignored: list[tuple[str, MapKey]]


def build_contribution(
    db: Any, *, contributor: str, tool_version: str,
    finalized_only: bool = True,
) -> dict[str, Any]:
    """Everything this machine has captured, in the exchange format.

    Only finalized maps are exported by default: a draft has not passed the
    operator's review gate, and unreviewed data is exactly what a shared dataset
    must not accumulate.
    """
    rows = db.conn.execute(
        """SELECT id, match_id, game_no, demo_code, map_guid, map_name, map_category,
                  side_a_team_id, side_a_label, side_b_team_id, side_b_label,
                  winner_side, captured_at, bans_json, profile_id
           FROM map_instances
           WHERE match_id IS NOT NULL AND game_no IS NOT NULL"""
        + (" AND finalized_at IS NOT NULL" if finalized_only else ""),
    ).fetchall()

    profiles = {
        int(r["id"]): {"w": int(r["resolution_w"]), "h": int(r["resolution_h"]),
                       "hud_variant": str(r["hud_variant"])}
        for r in db.conn.execute(
            "SELECT id, resolution_w, resolution_h, hud_variant FROM roi_profiles")
    }

    maps: list[dict[str, Any]] = []
    for r in rows:
        obs = db.conn.execute(
            """SELECT o.side, o.sample_ts_ms, o.sub_map, o.round_no, o.phase,
                      (SELECT group_concat(s.hero_guid, ',') FROM comp_slots s
                        WHERE s.observation_id = o.id AND s.hero_guid IS NOT NULL
                        ORDER BY s.slot_index) AS guids
               FROM comp_observations o
               WHERE o.map_instance_id = ? AND o.resolved = 1
               ORDER BY o.side, o.sample_ts_ms""",
            (int(r["id"]),),
        ).fetchall()
        if not obs:
            continue
        maps.append({
            # Canonical identity - deliberately NOT the local map_instances.id.
            "match_id": str(r["match_id"]), "game_no": int(r["game_no"]),
            "demo_code": r["demo_code"],
            "map_guid": r["map_guid"], "map_name": r["map_name"],
            "map_category": r["map_category"],
            "side_a_team_id": r["side_a_team_id"], "side_a_team": r["side_a_label"],
            "side_b_team_id": r["side_b_team_id"], "side_b_team": r["side_b_label"],
            "winner_side": r["winner_side"],
            "captured_at": r["captured_at"],
            "bans": json.loads(r["bans_json"]) if r["bans_json"] else [],
            # Provenance: trust decisions later can only use what is recorded now.
            "profile": profiles.get(int(r["profile_id"] or 0)),
            "observations": [
                {"side": str(o["side"]), "ts": int(o["sample_ts_ms"]),
                 "sub_map": o["sub_map"], "round_no": o["round_no"],
                 "phase": o["phase"],
                 "heroes": [g for g in str(o["guids"]).split(",") if g]}
                for o in obs
            ],
        })

    # Operator-added heroes travel WITH the contribution. OW2 ships heroes faster
    # than FACEIT's roster updates, so a contributor can legitimately reference a
    # guid the merging side has never heard of; without this it would render as a
    # raw 'custom:...' string in someone else's report.
    used = {g for m in maps for o in m["observations"] for g in o["heroes"]}
    heroes = {h.guid: {"name": h.name, "role": h.role}
              for h in db.list_custom_heroes() if h.guid in used}

    return {
        "format": CONTRIB_FORMAT,
        "contributor": contributor,
        "tool_version": tool_version,
        "heroes": heroes,
        "maps": maps,
    }


def load_contribution(path: str | Path) -> dict[str, Any]:
    """Read and validate one contributor file. Raises ValueError on a format this
    build does not understand, rather than guessing at the contents."""
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    fmt = data.get("format")
    if fmt != CONTRIB_FORMAT:
        raise ValueError(f"{path}: unsupported contribution format {fmt!r} "
                         f"(this build reads {CONTRIB_FORMAT})")
    if not data.get("contributor"):
        raise ValueError(f"{path}: no contributor name")
    return data


# Reserved filenames in the contributions directory that are NOT contributions.
OVERRIDES_FILE = "overrides.json"


def merge_first_wins(
    contributions: Sequence[Mapping[str, Any]],
    overrides: Optional[Mapping[MapKey, str]] = None,
) -> MergeResult:
    """Combine contributions in PRIORITY ORDER (earliest submission first).

    Whoever submits a map first owns it. That contributor may update their own
    submission — otherwise re-scouting a map you fixed in Review would be thrown
    away, which is the opposite of the intent. Anyone else's view of an already
    claimed map is ignored and recorded.

    ``overrides`` is the curator's escape hatch for exactly the weakness of
    first-wins: quality becomes a function of who was fastest, so a bad first
    submission (wrong left team, stale calibration) locks a map. An override
    reassigns one map to a named contributor's view. It lives in a committed
    file, so using it is an auditable act, not a hidden knob — and if the named
    contributor never supplied that map, ownership falls back to first-wins
    rather than making the map disappear.

    Ordering is the caller's job precisely because it must not come from the
    files: a contributor supplies their own timestamps, and a clock can drift or
    be set deliberately. Use commit date or server receipt time.
    """
    # Every contributor's latest view of every map (self-update folds in here),
    # plus who arrived when. Ownership is decided AFTER collection, which is
    # what lets an override fall back safely.
    views: dict[MapKey, dict[str, dict[str, Any]]] = {}
    arrival: dict[MapKey, list[str]] = {}

    for contrib in contributions:
        who = str(contrib["contributor"])
        for m in contrib.get("maps", []):
            if not m.get("match_id") or m.get("game_no") is None:
                log.warning("%s: map without a FACEIT identity, skipped", who)
                continue
            key = MapKey(str(m["match_id"]), int(m["game_no"]))
            views.setdefault(key, {})[who] = dict(m, contributor=who)
            order = arrival.setdefault(key, [])
            if who not in order:
                order.append(who)

    maps: dict[MapKey, dict[str, Any]] = {}
    owner: dict[MapKey, str] = {}
    ignored: list[tuple[str, MapKey]] = []
    for key, by_who in views.items():
        preferred = (overrides or {}).get(key)
        if preferred is not None and preferred not in by_who:
            log.warning("override for %s prefers %r, who has no view of it - "
                        "falling back to first-wins", key, preferred)
            preferred = None
        winner = preferred or arrival[key][0]
        owner[key] = winner
        maps[key] = by_who[winner]
        ignored.extend((who, key) for who in arrival[key] if who != winner)
    return MergeResult(maps=maps, owner=owner, ignored=ignored)


def load_overrides(directory: str | Path) -> dict[MapKey, str]:
    """The curator's committed override list, or {} when absent/unreadable. A
    malformed overrides file must degrade to first-wins, not block the build."""
    path = Path(directory) / OVERRIDES_FILE
    if not path.is_file():
        return {}
    try:
        with path.open(encoding="utf-8") as fh:
            data = json.load(fh)
        return {MapKey(str(o["match_id"]), int(o["game_no"])): str(o["prefer"])
                for o in data.get("overrides", [])}
    except (OSError, ValueError, KeyError, TypeError) as exc:
        log.warning("ignoring malformed %s: %s", path, exc)
        return {}


def to_obs_details(maps: Mapping[MapKey, Mapping[str, Any]]) -> list[ObsDetail]:
    """Merged maps -> the flat rows the scouting analysis consumes.

    ``map_instance_id`` is re-issued here as a merge-local index. It is an
    arbitrary handle for grouping within one derivation and is never persisted or
    shared; the identity that means anything is the MapKey it came from.
    """
    out: list[ObsDetail] = []
    for idx, (key, m) in enumerate(sorted(maps.items()), start=1):
        for o in m.get("observations", []):
            out.append(ObsDetail(
                map_instance_id=idx,
                side=str(o["side"]),
                sample_ts_ms=int(o["ts"]),
                sub_map=o.get("sub_map"),
                round_no=o.get("round_no"),
                phase=o.get("phase"),
                hero_guids=tuple(o.get("heroes") or ()),
                map_name=m.get("map_name"),
                map_category=m.get("map_category"),
                side_a_team=m.get("side_a_team"),
                side_b_team=m.get("side_b_team"),
                winner_side=m.get("winner_side"),
                bans=tuple(m.get("bans") or ()),
            ))
    return out


def to_obs_rows(
    maps: Mapping[MapKey, Mapping[str, Any]],
    hero_roles: Mapping[str, str], hero_names: Mapping[str, str],
) -> list[Any]:
    """Merged maps -> ``derive.ObsRow`` for the cross-team comp summary."""
    from .comps import canonical_comp
    from .derive import ObsRow

    rows: list[Any] = []
    for idx, (key, m) in enumerate(sorted(maps.items()), start=1):
        for o in m.get("observations", []):
            guids = [g for g in (o.get("heroes") or ())]
            if not guids:
                continue
            comp = canonical_comp(guids, hero_roles, hero_names)
            side = str(o["side"])
            rows.append(ObsRow(
                comp_id=comp.comp_id,
                hero_names=comp.hero_names_sorted,
                map_instance_id=idx,
                side=side,
                map_guid=m.get("map_guid"),
                team_id=m.get(f"side_{side}_team_id"),
                won=(m.get("winner_side") == side),
                team_name=m.get(f"side_{side}_team"),
                sub_map=o.get("sub_map"),
            ))
    return rows


def merged_payload(
    contributions: Sequence[Mapping[str, Any]],
    hero_roles: Mapping[str, str], hero_names: Mapping[str, str],
    overrides: Optional[Mapping[MapKey, str]] = None,
) -> dict[str, Any]:
    """The published artifact, derived from many contributors' raw observations.

    Same shape the single-operator path produced, so the dashboard is unchanged —
    only where the data comes from has changed."""
    from .derive import dashboard_comps
    from .scout import team_scout

    # Fold in any custom heroes the contributors declared, so the merging side
    # needs nothing beyond the faceit roster and the files themselves.
    roles, names = dict(hero_roles), dict(hero_names)
    for c in contributions:
        for guid, h in (c.get("heroes") or {}).items():
            names[guid] = str(h.get("name") or guid)
            if h.get("role"):
                roles[guid] = str(h["role"])

    merged = merge_first_wins(contributions, overrides=overrides)
    payload = dashboard_comps(to_obs_rows(merged.maps, roles, names))
    report = team_scout(to_obs_details(merged.maps), roles, names)
    teams = payload["teams"]
    assert isinstance(teams, dict)
    for team, r in report.items():
        teams.setdefault(team, {"maps_captured": 0, "comps": []})["scout"] = r
    payload["contributors"] = sorted({str(c["contributor"]) for c in contributions})
    payload["maps_merged"] = len(merged.maps)
    payload["views_ignored"] = len(merged.ignored)
    return payload


def contribution_files(directory: str | Path) -> list[Path]:
    """Contributor files in a stable, name-sorted order. Callers that need true
    submission order (which decides who owns a contested map) should order by
    commit date instead — see :func:`merge_first_wins`."""
    d = Path(directory)
    if not d.is_dir():
        return []
    return sorted(p for p in d.glob("*.json") if p.name != OVERRIDES_FILE)


def git_submission_order(paths: Iterable[Path]) -> list[Path]:
    """Order files by when each was first COMMITTED, oldest first.

    The contributing machine cannot be trusted to timestamp its own submission,
    so first-wins is decided by the receiving side. In a git flow that is the
    commit that added the file. Files git knows nothing about sort last, by name.
    """
    import subprocess

    def added_at(p: Path) -> str:
        try:
            out = subprocess.run(
                ["git", "log", "--diff-filter=A", "--format=%cI", "-1", "--", str(p)],
                capture_output=True, text=True, timeout=15)
            return out.stdout.strip() or "9999"
        except Exception:  # noqa: BLE001 - no git, or not a repo
            return "9999"

    return sorted(paths, key=lambda p: (added_at(p), p.name))


def resolve_contributions(
    directory: str | Path, *, use_git_order: bool = True
) -> list[dict[str, Any]]:
    """Every contributor file in the directory, loaded and put in priority order."""
    paths = contribution_files(directory)
    if use_git_order:
        paths = git_submission_order(paths)
    out: list[dict[str, Any]] = []
    for p in paths:
        try:
            out.append(load_contribution(p))
        except (OSError, ValueError) as exc:
            # One malformed contribution must not take the whole site down.
            log.warning("skipping %s: %s", p, exc)
    return out

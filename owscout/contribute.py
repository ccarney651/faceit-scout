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

# The deployed upload worker. Baked into builds so end users configure
# NOTHING; empty until the curator deploys infra/upload-worker.
DEFAULT_UPLOAD_ENDPOINT = ""


class MapKey(NamedTuple):
    """The identity of a real game, stable across every contributor's machine."""

    match_id: str
    game_no: int


class KnownGame(NamedTuple):
    """What FACEIT says about a real game: who played it, and its replay code."""

    teams: frozenset[str]           # both team names, lowercased
    demo_code: Optional[str]        # None when FACEIT never published one


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


def known_games(faceit_db_path: str) -> dict[MapKey, KnownGame]:
    """Every game FACEIT knows about, keyed the same way contributions are.

    This is the enforcement of a promise the format only implied: a contributed
    map names a real FACEIT game, so nobody can invent a match. Implied is not
    enforced — without this table the merge trusted match_id blindly, and a
    malformed or malicious file could put games that never happened on the site.
    """
    from .faceit import connect_ro

    with connect_ro(faceit_db_path) as fdb:
        rows = fdb.execute(
            """SELECT g.match_id, g.game_no, g.demo_code,
                      t1.name AS a, t2.name AS b
               FROM games g
               JOIN matches m ON m.id = g.match_id
               LEFT JOIN teams t1 ON t1.id = m.faction1_team_id
               LEFT JOIN teams t2 ON t2.id = m.faction2_team_id""",
        ).fetchall()
    return {
        MapKey(str(r["match_id"]), int(r["game_no"])): KnownGame(
            teams=frozenset(str(n).lower() for n in (r["a"], r["b"]) if n),
            demo_code=r["demo_code"])
        for r in rows
    }


def validate_maps(
    contrib: Mapping[str, Any], known: Mapping[MapKey, KnownGame]
) -> tuple[dict[str, Any], list[tuple[Optional[MapKey], str]]]:
    """One contribution -> (cleaned copy, rejected maps with reasons).

    Applied PER VIEW, before ownership: if Alice's view of a real game carries
    the wrong team names and Bob's is right, Alice's view is dropped and Bob's
    must still be able to win the map. Three checks:

    * the game must exist in faceit.games — fabrication or corruption;
    * any team name the contribution carries must be one of the two teams
      FACEIT says played — the signature of scouting the WRONG replay code and
      attaching it to this match, which would poison another team's report; and
    * the replay code must agree when FACEIT published one (lenient when it
      did not — some matches never get codes, yet the operator may have one).
    """
    who = str(contrib.get("contributor", "?"))
    cleaned: list[dict[str, Any]] = []
    rejects: list[tuple[Optional[MapKey], str]] = []
    for m in contrib.get("maps", []):
        if not m.get("match_id") or m.get("game_no") is None:
            rejects.append((None, "no FACEIT identity"))
            continue
        key = MapKey(str(m["match_id"]), int(m["game_no"]))
        game = known.get(key)
        if game is None:
            rejects.append((key, "game does not exist on FACEIT"))
            continue
        names = [str(m.get(f"side_{s}_team") or "").lower() for s in ("a", "b")]
        bad = [n for n in names if n and n not in game.teams]
        if bad:
            rejects.append((key, f"team {bad[0]!r} did not play this game"))
            continue
        code = m.get("demo_code")
        if code and game.demo_code and str(code) != str(game.demo_code):
            rejects.append((key, f"replay code {code!r} does not match FACEIT's"))
            continue
        cleaned.append(m)
    for rkey, why in rejects:
        log.warning("rejected map from %s (%s): %s", who, rkey, why)
    return dict(contrib, maps=cleaned), rejects


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
    known: Optional[Mapping[MapKey, KnownGame]] = None,
) -> dict[str, Any]:
    """The published artifact, derived from many contributors' raw observations.

    Same shape the single-operator path produced, so the dashboard is unchanged —
    only where the data comes from has changed. When ``known`` is given, every
    contributed map is validated against it first; rejected views never reach
    the merge, and the count is reported in the payload."""
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

    rejected = 0
    if known is not None:
        checked = []
        for c in contributions:
            cleaned, rejects = validate_maps(c, known)
            rejected += len(rejects)
            checked.append(cleaned)
        contributions = checked

    merged = merge_first_wins(contributions, overrides=overrides)
    payload = dashboard_comps(to_obs_rows(merged.maps, roles, names))
    report = team_scout(to_obs_details(merged.maps), roles, names)
    teams = payload["teams"]
    assert isinstance(teams, dict)
    for team, r in report.items():
        teams.setdefault(team, {"maps_captured": 0, "comps": []})["scout"] = r
    payload["contributors"] = sorted({str(c["contributor"]) for c in contributions})
    # Which real games are covered - lets the site badge scouted games and show
    # the "still to scout" queue per team, which is the capture work-list.
    payload["captured_games"] = sorted(f"{k.match_id}:{k.game_no}" for k in merged.maps)
    # Games on or before this date have DEAD replay codes: the site must not
    # count them as scoutable (unless someone captured them before the wipe).
    from .db import LATEST_KNOWN_WIPE
    payload["code_wipe_date"] = LATEST_KNOWN_WIPE
    payload["maps_merged"] = len(merged.maps)
    payload["views_ignored"] = len(merged.ignored)
    payload["maps_rejected"] = rejected
    return payload


# --- open-access upload (the Worker endpoint) ---------------------------------
# No keys, no accounts: the tool generates a random identity token on first
# publish and the first install to upload under a display name CLAIMS it
# server-side. A stranger cannot overwrite someone else's file, yet nobody is
# ever issued anything. See infra/upload-worker/worker.js.


def push_to_endpoint(
    content: bytes, *, endpoint: str, name: str, token: str, session: Any = None
) -> dict[str, Any]:
    """POST a contribution to the open upload endpoint. The only credential is
    the install's own auto-generated token; losing it means picking a new name,
    never losing data (the old file stays, the curator can reassign)."""
    if session is None:
        import requests
        session = requests.Session()
    resp = session.post(endpoint, data=content, timeout=60,
                        headers={"X-Owscout-Name": name,
                                 "X-Owscout-Token": token,
                                 "Content-Type": "application/json"})
    try:
        body = resp.json()
    except Exception:  # noqa: BLE001
        body = {}
    if resp.status_code != 200:
        raise RuntimeError(str(body.get("error") or f"upload failed (HTTP {resp.status_code})"))
    return dict(body)


def push_contribution(
    content: bytes,
    *,
    repo: str,
    token: str,
    path: str,
    branch: str = "main",
    session: Any = None,
) -> dict[str, str]:
    """Upload one contributor file straight into the site's repo via the GitHub
    Contents API - one HTTPS call, no git install on the contributing machine.

    The repo IS the upload server: commits land in data/captures/, the site
    workflow rebuilds on that path, and every downstream rule (first-wins by
    commit date, FACEIT validation, curator overrides) applies to an API commit
    exactly as it would to a hand-made one. Full git history stays the audit
    trail, so a bad upload is a revert, never a loss.

    Returns {"action": "created"|"updated", "commit": sha}. Raises RuntimeError
    with a plain-language hint on the failures teammates will actually hit
    (bad token, no access, wrong repo name).
    """
    if session is None:
        import requests
        session = requests.Session()
    base = f"https://api.github.com/repos/{repo}/contents/{path}"
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "User-Agent": "owscout-sync",
    }
    # Updating an existing file requires its current blob sha; absent file = create.
    sha: Optional[str] = None
    got = session.get(base, headers=headers, params={"ref": branch}, timeout=30)
    if got.status_code == 200:
        sha = got.json().get("sha")
    elif got.status_code not in (404,):
        _raise_push_error(got, repo)

    import base64
    body: dict[str, Any] = {
        "message": f"contribution: {Path(path).stem}",
        "content": base64.b64encode(content).decode("ascii"),
        "branch": branch,
    }
    if sha:
        body["sha"] = sha
    put = session.put(base, headers=headers, json=body, timeout=30)
    if put.status_code not in (200, 201):
        _raise_push_error(put, repo)
    out = put.json()
    return {"action": "updated" if sha else "created",
            "commit": str((out.get("commit") or {}).get("sha", ""))}


def _raise_push_error(resp: Any, repo: str) -> None:
    hints = {
        401: "the sync token is wrong or expired - paste a fresh one in Sync settings",
        403: "the token does not have Contents write access to " + repo,
        404: f"repo {repo!r} not found, or the token cannot see it",
        409: "the file changed mid-upload - press Publish again",
    }
    hint = hints.get(resp.status_code, "")
    raise RuntimeError(
        f"upload failed (HTTP {resp.status_code})" + (f": {hint}" if hint else ""))


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

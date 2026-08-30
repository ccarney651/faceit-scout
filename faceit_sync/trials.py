"""The local trialist comparison tool.

A private, never-committed page for judging trial candidates against each other:
search the league's players by either name they go by, keep a pool of them, and
read them as columns in one table per role.

Design: `specs/2026-08-30-trialist-comparison-design.md`.

This module owns no analysis. Every rate, record and z-score on the page comes
from `faceit_sync/dashboard/pure.js`, inlined unchanged and called with the same
payload the live dashboard uses — so a number here and the same number on the
site cannot disagree.
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any

from ._dashboard import _inline_theme_css
from .db import Database
from .export import _region_of, _tier_of, build_dashboard_data

_DASHBOARD_DIR = Path(__file__).parent / "dashboard"

# A second role has to clear this share of a player's role-bearing maps before it
# earns them a column in that role's table. Without a floor, every DPS who
# covered a tank once turns up in the tank table; at 10% the real flex cases
# (Warglabidoo: 60 Damage, 7 Tank) still surface.
FLEX_SHARE = 0.10

UNASSIGNED = "Unassigned"


def build_search_index(data: dict[str, Any]) -> list[dict[str, Any]]:
    """One searchable entry per player, across every division in the payload.

    A shortlist is written in in-game names; FACEIT knows nicknames. They differ
    often enough that searching only one of them makes the tool look empty for
    players who are plainly in the data, so both ride on every entry.

    A player who appears in several divisions (a regular season and its playoffs,
    or a mid-season move) collapses to ONE entry: `maps` counts every game they
    played, while the identity fields come from wherever they most recently
    played. This is a find-me index — the full chronology comes from
    `playerSeason()` at render time and is deliberately not duplicated here.

    Counts come from the per-game rosters, never from ``teams[].roster[]``. That
    rollup is per championship, and playoffs are their own championship, so its
    ``games`` silently stops at the group stage: it puts Warglabidoo's season at
    55 maps when he actually played 67. The roster is read only for the two
    things the per-game entries do not carry — the in-game name and elo.
    """
    by_nick: dict[str, dict[str, Any]] = {}
    roles: dict[str, Counter[str]] = {}
    roster_seen: dict[str, str] = {}     # nick -> latest roster row used, by date

    def entry_for(nick: str) -> dict[str, Any]:
        e = by_nick.get(nick)
        if e is None:
            e = by_nick[nick] = {"nick": nick, "game": None, "role": None,
                                 "team": None, "region": None, "tier": None,
                                 "div": None, "elo": None, "maps": 0, "last": ""}
            roles[nick] = Counter()
            roster_seen[nick] = ""
        return e

    for _cid, div in (data.get("divisions") or {}).items():
        name = str(div.get("summary", {}).get("championship") or "")
        region, tier = _region_of(name), _tier_of(name)
        # The regular season AND the playoffs. Reads that stop at the group stage
        # are a bug this repo has already shipped once.
        for m in list(div.get("matches") or []) + list(div.get("playoffs") or []):
            at = m.get("finished_at") or ""
            for g in m.get("games") or []:
                if not g.get("map"):
                    continue                      # walkover or unplayed slot
                for r in g.get("rosters") or []:
                    for p in r.get("players") or []:
                        nick = p.get("nick")
                        if not nick:
                            continue
                        entry = entry_for(nick)
                        entry["maps"] += 1
                        role = p.get("role")
                        if role and role != "None":
                            roles[nick][role] += 1
                        # Ties resolve to the later-iterated match, which is
                        # arbitrary but stable.
                        if at >= entry["last"]:
                            entry.update(last=at, team=r.get("team"),
                                         region=region, tier=tier, div=name)
        # The roster carries the in-game name and elo, which the per-game entries
        # do not. Its `games` count is deliberately ignored (see the docstring).
        for team in div.get("teams") or []:
            for p in team.get("roster") or []:
                nick = p.get("nick")
                if not nick:
                    continue
                entry = entry_for(nick)
                seen = p.get("last_seen") or ""
                if seen >= roster_seen[nick]:
                    roster_seen[nick] = seen
                    entry.update(game=p.get("game_name"), elo=p.get("elo"))
                    if not entry["last"]:
                        # Roster row with no game rows behind it (every match a
                        # walkover). Better a stale label than a blank one.
                        entry.update(last=seen, team=team.get("name"),
                                     region=region, tier=tier, div=name)
                if entry["role"] is None:
                    entry["role"] = p.get("role")

    for nick, entry in by_nick.items():
        counts = roles[nick]
        entry["roles"] = dict(counts.most_common())
        entry["tables"] = _tables_for(counts)
        if counts:
            entry["role"] = counts.most_common(1)[0][0]

    # Most-played first: the people with enough sample to judge sort to the top.
    return sorted(by_nick.values(), key=lambda e: (-e["maps"], e["nick"].lower()))


def _tables_for(counts: Counter[str]) -> list[str]:
    """Which role tables a player belongs in, dominant role first.

    A player sits in their dominant role's table; any other role they played on
    at least ``FLEX_SHARE`` of their role-bearing maps earns them a column there
    too. A player FACEIT recorded no role for at all goes to ``Unassigned``
    rather than being dropped from the page.
    """
    total = sum(counts.values())
    if not total:
        return [UNASSIGNED]
    ranked = sorted(counts.items(), key=lambda rn: (-rn[1], rn[0]))
    dominant = ranked[0][0]
    return [dominant] + [r for r, n in ranked[1:] if n / total >= FLEX_SHARE]


def _json_blob(value: Any) -> str:
    """JSON safe to inline in a <script> block.

    Escaping every `<` as \\u003c closes both the `</script>` breakout and the
    `<!--` one; JSON.parse decodes it back transparently, so the round trip is
    lossless. Same treatment export_html gives the dashboard's payload.
    """
    return json.dumps(value, ensure_ascii=True).replace("<", "\\u003c")


def build_trials_page(data: dict[str, Any]) -> str:
    """Render the whole trials tool as one self-contained HTML string.

    `pure.js` is inlined unchanged ahead of the app, so every rate and z-score
    the page prints is computed by the same code the live dashboard runs.
    """
    shell = (_DASHBOARD_DIR / "trials.html").read_text(encoding="utf-8")
    pure = (_DASHBOARD_DIR / "pure.js").read_text(encoding="utf-8")
    app = (_DASHBOARD_DIR / "trials.js").read_text(encoding="utf-8")
    index = build_search_index(data)
    # FLEX_SHARE lives in Python but the page's methodology section quotes it, so
    # it rides along in the payload rather than being retyped into the prose.
    meta = {"flex_share": FLEX_SHARE}
    blob = (f"window.__OWDB_DATA__={_json_blob(data)};\n"
            f"var __TRIALS_INDEX__={_json_blob(index)};\n"
            f"var __TRIALS_META__={_json_blob(meta)};\n"
            "window.__TRIALS_INDEX__=__TRIALS_INDEX__;\n"
            "window.__TRIALS_META__=__TRIALS_META__;")
    return (shell
            .replace("/* __THEME_CSS__ */", _inline_theme_css())
            .replace("/* __PURE_JS__ */", pure)
            .replace("/* __DATA__ */", blob)
            .replace("/* __APP_JS__ */", app))


def write_trials_page(db: Database, out_path: str,
                      championship_id: str | None = None,
                      only_tier: str | None = None,
                      only_region: str | None = None,
                      only_season: str | None = None) -> int:
    """Build the trials page and write it to ``out_path``.

    Returns the number of divisions with data, and writes nothing at all when
    that is zero — an empty page would look like a broken tool rather than an
    empty database.
    """
    data = build_dashboard_data(db, championship_id, only_tier, only_region,
                                only_season)
    if not data:
        return 0
    with open(out_path, "w", encoding="utf-8") as fh:
        fh.write(build_trials_page(data))
    return len(data["divisions"])

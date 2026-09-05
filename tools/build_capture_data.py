"""Emit docs/capture/data.json — the codes + rosters feed the browser capture
app consumes instead of crawling FACEIT. CI-run (reads faceit.sqlite3); the app
fetches it same-origin. Scoped to the regions the site ships, all tiers,
post-wipe coded games.

``division`` is REGION-QUALIFIED ("EMEA Master", "NA Expert"), not a bare tier.
The app's picker is one dropdown filtering on equality, so bare tiers would
merge two regions' codes under a single "Master" with nothing telling them
apart.

    faceit-sync ... export ...          # (CI already builds the DB)
    .venv/Scripts/python tools/build_capture_data.py

data.json:
  { built_at, code_wipe_date, divisions:[...],
    codes: [{code,match_id,game_no,map,division,team_a,team_b,t1,t2,finished_at}],
    rosters:      { <match_id>: { <team_id>: {name, players:[...]} } },
    lineups:      { "<match_id>:<game_no>": { <team_id>:
                      {name, players:[{id,nick,game_name,role}]} } },
    hero_roles:   { <hero_guid>: "Tank"|"Damage"|"Support" },
    team_rosters: { <team_id>: {name, players:[{id,nick,game_name}]} } }
`rosters` is per coded match (capture attribution); `lineups` is the exact five
who played ONE game, with roles (player assignment); `team_rosters` is the ACTIVE
season's teams with their accumulated squads (scrim opponent identification).
Whether a code is already scouted is read from the sibling docs/captured.json,
so it is not duplicated here.
"""
from __future__ import annotations

import json
import os
import sqlite3
from datetime import UTC, datetime

from faceit_sync.models import newest_season, season_of
from owdb.db import LATEST_KNOWN_WIPE

FACEIT_DB = os.environ.get("FACEIT_DB", "faceit.sqlite3")
OUT = os.environ.get("CAPTURE_OUT", os.path.join("docs", "capture", "data.json"))
# Regions the site ships, strongest-audience first. Order drives the app's
# division dropdown. Kept in sync with faceit_sync.export.REGIONS.
REGIONS = ("EMEA", "NA", "SA", "OCE")
# Single source of truth for the league-wide replay-code wipe: owdb.db's
# LATEST_KNOWN_WIPE (never duplicate it here — bump it in _SEED_WIPES instead).
CODE_WIPE_DATE = LATEST_KNOWN_WIPE
# Skill tiers, strongest first, likewise kept in sync with
# faceit_sync.export.TIERS (a test pins the two together). Intermediate is
# Season 10's new division, between Advanced and Open.
TIERS = ("Master", "Expert", "Advanced", "Intermediate", "Open")


def _tier(name: str) -> str | None:
    return next((t for t in TIERS if t in (name or "")), None)


def _region(name: str) -> str | None:
    """Whole-word region match — a bare '%NA%' would also hit any championship
    whose name merely contains those letters. Mirrors owdb.db.list_codes."""
    words = (name or "").upper().replace("-", " ").split()
    return next((r for r in REGIONS if r in words), None)


def _division(name: str) -> str | None:
    """The region-qualified division label ('EMEA Master'), or None if the
    championship name carries no region or no tier."""
    region, tier = _region(name), _tier(name)
    return f"{region} {tier}" if region and tier else None


def main() -> None:
    con = sqlite3.connect(FACEIT_DB)
    con.row_factory = sqlite3.Row
    codes: list[dict[str, object]] = []
    rosters: dict[str, dict[str, dict[str, object]]] = {}
    seen_divs: set[str] = set()

    rows = con.execute(
        """
        SELECT g.demo_code code, g.match_id, g.game_no,
               mp.name map, g.map_category cat, g.map_guid map_guid,
               m.finished_at, ch.name champ,
               m.faction1_team_id t1, m.faction2_team_id t2,
               t1.name team_a, t2.name team_b
        FROM games g
        JOIN matches m ON m.id = g.match_id
        JOIN championships ch ON ch.id = m.championship_id
        LEFT JOIN maps  mp ON mp.guid = g.map_guid
        LEFT JOIN teams t1 ON t1.id = m.faction1_team_id
        LEFT JOIN teams t2 ON t2.id = m.faction2_team_id
        WHERE g.demo_code IS NOT NULL AND g.demo_code <> ''
          AND substr(m.finished_at, 1, 10) > ?
        ORDER BY m.finished_at DESC, g.game_no
        """,
        (CODE_WIPE_DATE,),
    ).fetchall()

    match_ids: set[str] = set()
    for r in rows:
        # Region is filtered here rather than in SQL: a championship naming
        # neither region (a one-off cup) is dropped, not mislabelled.
        div = _division(r["champ"])
        if not div:
            continue
        seen_divs.add(div)
        codes.append({
            "code": r["code"], "match_id": r["match_id"], "game_no": r["game_no"],
            "map": r["map"], "map_category": r["cat"], "map_guid": r["map_guid"],
            "division": div,
            "team_a": r["team_a"], "team_b": r["team_b"],
            "t1": r["t1"], "t2": r["t2"], "finished_at": r["finished_at"],
        })
        match_ids.add(r["match_id"])

    # One roster set per match (the players who appeared, per team). game_name is
    # the Battle.net HUD name — kept for the future OCR/attribution phase.
    for mid in match_ids:
        by_team: dict[str, dict[str, object]] = {}
        for rp in con.execute(
            """SELECT rp.team_id, te.name tname, rp.player_id pid,
                      COALESCE(p.nickname, rp.player_id) nick, p.game_name gname
               FROM round_players rp
               LEFT JOIN players p ON p.id = rp.player_id
               LEFT JOIN teams te ON te.id = rp.team_id
               WHERE rp.match_id = ? AND rp.team_id IS NOT NULL
               GROUP BY rp.team_id, rp.player_id""",
            (mid,),
        ):
            slot = by_team.setdefault(rp["team_id"], {"name": rp["tname"], "players": []})
            # id = FACEIT player_id: the browser's HUD-name OCR matches game_name to
            # a roster entry, then attributes the hero to this id (pairs[hero,id]).
            slot["players"].append(
                {"id": rp["pid"], "nick": rp["nick"], "game_name": rp["gname"]})
        rosters[mid] = by_team

    # The exact five who played ONE game, per team, WITH their FACEIT role.
    #
    # Keyed per game rather than per match, which is not a refinement of `rosters`
    # above but a correctness requirement. `rosters` groups by (team, player)
    # across the whole match, so a substitution inflates it: measured over the
    # database, 610 of 2260 match-teams (27%) carry more than five players. The
    # browser's role-constrained assignment
    # (docs/capture/engine/assign.js, specs/2026-08-16-player-assignment-design.md)
    # depends on an EXACT COVER of five players over five slots — hand it six and
    # the damage group has three candidates for two slots, so the constraint that
    # makes the whole thing work is gone and a substitute who never played this
    # game becomes a candidate.
    #
    # Additive, deliberately: `rosters` is what engine/opponents.js consumes for
    # scrim opponent identification, and there the ACCUMULATED squad is the right
    # answer. Two consumers, two correct shapes; neither should be bent to serve
    # the other.
    #
    # role is FACEIT's own per-game value (the i16 stats field). A game whose
    # stats never captured comes back with the '-' sentinel, stored here as null —
    # assign.js leaves such a group to the operator rather than forcing it.
    lineups: dict[str, dict[str, dict[str, object]]] = {}
    for c in codes:
        key = f"{c['match_id']}:{c['game_no']}"
        if key in lineups:
            continue
        by_team = {}
        for rp in con.execute(
            """SELECT rp.team_id, te.name tname, rp.player_id pid,
                      COALESCE(p.nickname, rp.player_id) nick, p.game_name gname,
                      rp.role
               FROM round_players rp
               LEFT JOIN players p ON p.id = rp.player_id
               LEFT JOIN teams te ON te.id = rp.team_id
               WHERE rp.match_id = ? AND rp.game_no = ? AND rp.team_id IS NOT NULL""",
            (c["match_id"], c["game_no"]),
        ):
            slot = by_team.setdefault(rp["team_id"], {"name": rp["tname"], "players": []})
            role = rp["role"] if rp["role"] in ("Tank", "Damage", "Support") else None
            slot["players"].append({
                "id": rp["pid"], "nick": rp["nick"],
                "game_name": rp["gname"], "role": role})
        lineups[key] = by_team

    # guid -> role for every hero. The browser had no role data at all for the
    # built-in heroes (only CUSTOM_HEROES carried one), and the role-constrained
    # player assignment reads the role OFF THE RECOGNISED HERO to decide which
    # players can be standing in a slot. 52 entries, so the size cost is nil.
    hero_roles = {
        r["guid"]: r["role"]
        for r in con.execute("SELECT guid, role FROM heroes WHERE role IS NOT NULL")
    }

    # A roster per TEAM, across every match they have played — not just the
    # handful with live replay codes. `rosters` above is keyed by match and only
    # covers coded games, which is right for attributing a capture but useless
    # for identifying a scrim opponent: it currently carries about 8 teams out
    # of 159. Scrim opponent identification (phase 2 of
    # specs/2026-08-12-scrim-mode-design.md) matches ten HUD names against every
    # team in the league, so it needs the full set.
    #
    # ACTIVE SEASON ONLY. A team that did not return for the new season is not
    # someone you scrim, so matching a scrim against last season's squad is not
    # a near miss - it writes a team that no longer plays into a private scrim
    # log. Scoping here also stops the pool growing by a season every year,
    # which is what the measured collision rate rests on: zero wrong teams at
    # the 3-of-5 bar across 8830 real lineups (tools/roster_match_eval.py, which
    # applies this same filter so the number describes the pool that ships).
    # The season comes from faceit_sync.models so the feed and the site cannot
    # disagree about which one is current.
    #
    # Accumulated WITHIN that season, deliberately: a season's subs and
    # stand-ins are exactly the names that let a lineup still be recognised when
    # two players are on smurf accounts.
    #
    # A championship whose name carries no season is dropped rather than kept -
    # a row that cannot be dated can never age out, so keeping it would quietly
    # rebuild the unbounded pool. Mirrors _division() dropping a region-less
    # name instead of guessing. A database where NOTHING names a season needs no
    # special case: `season` is then None and so is every row's, so the equality
    # keeps them all rather than shipping a pool that identifies nobody.
    # PLAYED, not merely seeded. The season's championships enter the database
    # when its rooms are seeded, which is days before its first game - and the
    # pool below is built from round_players, which only a played match has. Read
    # off every championship name, the newest season would flip the moment the
    # seeds landed and ship an EMPTY pool: no opponent identification at all,
    # during exactly the week when last season's squads are still the best guess
    # available. Restricting to championships that have produced players makes
    # the handover happen when there is something to hand over to.
    season = newest_season(
        row["name"] for row in con.execute(
            """SELECT DISTINCT ch.name FROM championships ch
               JOIN matches m ON m.championship_id = ch.id
               JOIN round_players rp ON rp.match_id = m.id"""))
    team_rosters: dict[str, dict[str, object]] = {}
    # Not GROUP BY (team, player): the championship name has to survive to the
    # filter, and grouping across seasons would hand it an arbitrary one of them
    # - dropping a player who DID play this season because SQLite happened to
    # pick their row from last one. Filter first, dedupe here. The ORDER BY is
    # what GROUP BY used to provide implicitly; without it the roster order
    # churns every build and the committed feed diffs against itself.
    seen_pair: set[tuple[str, str]] = set()
    for rp in con.execute(
        """SELECT rp.team_id tid, te.name tname, rp.player_id pid,
                  COALESCE(p.nickname, rp.player_id) nick, p.game_name gname,
                  ch.name champ
           FROM round_players rp
           JOIN matches m ON m.id = rp.match_id
           JOIN championships ch ON ch.id = m.championship_id
           LEFT JOIN players p ON p.id = rp.player_id
           LEFT JOIN teams te ON te.id = rp.team_id
           WHERE rp.team_id IS NOT NULL
           ORDER BY rp.team_id, rp.player_id"""
    ):
        if season_of(rp["champ"]) != season:
            continue
        pair = (rp["tid"], rp["pid"])
        if pair in seen_pair:
            continue
        seen_pair.add(pair)
        slot = team_rosters.setdefault(rp["tid"], {"name": rp["tname"], "players": []})
        slot["players"].append(
            {"id": rp["pid"], "nick": rp["nick"], "game_name": rp["gname"]})

    con.close()

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    payload = {
        "built_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "code_wipe_date": CODE_WIPE_DATE,
        "regions": list(REGIONS),
        # Region-major, then tier strongest-first — the order the app's dropdown
        # renders in.
        "divisions": [f"{r} {t}" for r in REGIONS for t in TIERS
                      if f"{r} {t}" in seen_divs],
        "codes": codes,
        "rosters": rosters,
        "lineups": lineups,
        "hero_roles": hero_roles,
        "team_rosters": team_rosters,
    }
    with open(OUT, "w", encoding="utf-8") as fh:
        json.dump(payload, fh)
    print(f"wrote {OUT}  ({len(codes)} codes across {sorted(seen_divs)}, "
          f"{len(rosters)} matches, {len(lineups)} game lineups, "
          f"{len(team_rosters)} team rosters, "
          f"{os.path.getsize(OUT)//1024} KB)")


if __name__ == "__main__":
    main()

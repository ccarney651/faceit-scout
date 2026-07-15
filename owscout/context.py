"""``--code`` context derivation (SPEC §7, build step 4).

Given a ``demo_code``, derive everything faceit already knows about that map:
match_id, game_no, map, both teams, winner, the two bans, and the ten players
with their roles. The operator supplies six characters; the tool supplies the
context.

This runs over the owscout connection with faceit ATTACHed read-only, so it can
join faceit rows against owscout's own ``map_instances`` in one query to report
whether the map was already captured — the payoff of the ATTACH layer (SPEC §3).
"""

from __future__ import annotations

from .db import Database
from .models import BanInfo, CodeContext, PlayerInfo


class CodeNotFound(LookupError):
    """No faceit game carries this demo_code (or it pre-dates our data)."""


class AmbiguousCode(LookupError):
    """More than one game carries this demo_code — do not guess which map."""


def _faction_of(team_id: str | None, f1: str | None, f2: str | None) -> str | None:
    if team_id is not None and team_id == f1:
        return "faction1"
    if team_id is not None and team_id == f2:
        return "faction2"
    return None


def derive_code_context(db: Database, faceit_db_path: str, demo_code: str) -> CodeContext:
    """Resolve a demo_code to a :class:`CodeContext`. Raises :class:`CodeNotFound`
    or :class:`AmbiguousCode`."""
    db.attach_faceit(faceit_db_path)
    c = db.conn

    rows = c.execute(
        """SELECT g.match_id, g.game_no, g.map_guid, g.map_category AS game_category,
                  g.winner_faction AS winner,
                  m.faction1_team_id AS f1, m.faction2_team_id AS f2,
                  mp.name AS map_name, mp.category AS map_category,
                  t1.name AS f1_name, t2.name AS f2_name
           FROM faceit.games g
           JOIN faceit.matches m ON m.id = g.match_id
           LEFT JOIN faceit.maps  mp ON mp.guid = g.map_guid
           LEFT JOIN faceit.teams t1 ON t1.id = m.faction1_team_id
           LEFT JOIN faceit.teams t2 ON t2.id = m.faction2_team_id
           WHERE g.demo_code = ?""",
        (demo_code,),
    ).fetchall()

    if not rows:
        raise CodeNotFound(demo_code)
    if len(rows) > 1:
        where = ", ".join(f"{r['match_id']}#{r['game_no']}" for r in rows)
        raise AmbiguousCode(f"{demo_code} maps to {len(rows)} games: {where}")

    g = rows[0]
    match_id, game_no = g["match_id"], g["game_no"]
    f1, f2 = g["f1"], g["f2"]

    ban_rows = c.execute(
        """SELECT b.hero_guid, b.banned_by_faction, h.name AS hero_name
           FROM faceit.hero_bans b
           LEFT JOIN faceit.heroes h ON h.guid = b.hero_guid
           WHERE b.match_id = ? AND b.game_no = ?
           ORDER BY b.ban_order""",
        (match_id, game_no),
    ).fetchall()
    bans = [
        BanInfo(
            hero_guid=b["hero_guid"],
            hero_name=b["hero_name"],
            banned_by_faction=b["banned_by_faction"],
            banned_by_team_id=(f1 if b["banned_by_faction"] == "faction1"
                               else f2 if b["banned_by_faction"] == "faction2" else None),
        )
        for b in ban_rows
    ]

    player_rows = c.execute(
        """SELECT rp.team_id, rp.player_id, rp.role, p.nickname
           FROM faceit.round_players rp
           LEFT JOIN faceit.players p ON p.id = rp.player_id
           WHERE rp.match_id = ? AND rp.game_no = ?
           ORDER BY rp.team_id, rp.player_id""",
        (match_id, game_no),
    ).fetchall()
    players = [
        PlayerInfo(
            team_id=r["team_id"],
            team_name=(g["f1_name"] if r["team_id"] == f1
                       else g["f2_name"] if r["team_id"] == f2 else None),
            faction=_faction_of(r["team_id"], f1, f2),
            player_id=r["player_id"],
            nickname=r["nickname"],
            role=r["role"],
        )
        for r in player_rows
    ]

    # Cross-DB: has owscout already captured this map? (the ATTACH payoff)
    already = c.execute(
        "SELECT 1 FROM map_instances WHERE match_id = ? AND game_no = ?",
        (match_id, game_no),
    ).fetchone() is not None

    return CodeContext(
        demo_code=demo_code,
        match_id=match_id,
        game_no=int(game_no),
        map_guid=g["map_guid"],
        map_name=g["map_name"],
        map_category=g["map_category"] if g["map_category"] is not None else g["game_category"],
        faction1_team_id=f1,
        faction1_team_name=g["f1_name"],
        faction2_team_id=f2,
        faction2_team_name=g["f2_name"],
        winner_faction=g["winner"],
        bans=bans,
        players=players,
        already_captured=already,
    )


def format_context(ctx: CodeContext) -> str:
    """Human-readable stdout block for ``owscout code show``."""
    winner_name = ctx.team_name(ctx.winner_faction) or "(unknown/none)"
    lines = [
        f"demo_code {ctx.demo_code}  ->  match {ctx.match_id} game {ctx.game_no}",
        f"map:     {ctx.map_name or '?'} ({ctx.map_category or '?'})",
        f"side A (faction1): {ctx.faction1_team_name or ctx.faction1_team_id or '?'}",
        f"side B (faction2): {ctx.faction2_team_name or ctx.faction2_team_id or '?'}",
        f"winner:  {winner_name}"
        + (f" [{ctx.winner_faction}]" if ctx.winner_faction else ""),
        f"already captured: {'yes' if ctx.already_captured else 'no'}",
        "",
        "bans:",
    ]
    for b in ctx.bans:
        by = ctx.team_name(b.banned_by_faction) or b.banned_by_faction or "unknown"
        lines.append(f"  {b.hero_name or b.hero_guid:<16} banned by {by}")
    if not ctx.bans:
        lines.append("  (none recorded)")

    lines.append("")
    lines.append("players:")
    for faction in ("faction1", "faction2"):
        roster = [p for p in ctx.players if p.faction == faction]
        label = ctx.team_name(faction) or faction
        lines.append(f"  {label}:")
        for p in roster:
            lines.append(f"    {p.nickname or p.player_id:<20} {p.role or '-'}")
        if not roster:
            lines.append("    (no players recorded)")
    return "\n".join(lines)

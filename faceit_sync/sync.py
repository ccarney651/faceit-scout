"""Extraction + reconciliation + orchestration.

This module turns the three raw FACEIT payloads (match / democracy / stats) into
the normalized :class:`MatchBundle`, applying the three data hazards discovered
during investigation:

  (A) Zeroed player rows are NOT forfeits. Rows with role ``-`` and all-zero
      stats come from a game played to completion whose capture failed (a team
      DC'd at game end). We write NULL (never 0) and ``stats_captured=False``,
      and take the game outcome from ``results[]``.

  (B) Admin restarts destroy that game's democracy veto ticket. We do NOT rely on
      ``sessions[]`` (absent from every observed payload). Instead we reconcile:
      a game present in ``results[]`` whose democracy heroes ticket is all-``open``
      was restarted -> bans still come from the match payload, but
      ``banned_by_faction`` is NULL and ``was_restarted=True``.

  (C) Democracy is ephemeral (~7-day retention). When the whole democracy payload
      is absent (404), no game has veto attribution -> all ``banned_by_faction`` /
      ``picked_by`` are NULL. This is unrecoverable, which is why ingest must run
      often enough to capture matches while fresh.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Iterable, Optional

from .client import FaceitClient
from .db import Database
from .models import (
    FACTION1,
    FACTION2,
    STAT_FIELD_MAP,
    UNCAPTURED_ROLE_SENTINEL,
    Championship,
    Game,
    Hero,
    HeroBan,
    Map,
    MapPick,
    Match,
    MatchBundle,
    Player,
    RoundPlayer,
    Team,
)

log = logging.getLogger(__name__)


class EnumerationError(RuntimeError):
    """Raised when a championship can't be enumerated (no seed teams, no key)."""


# --- small helpers -----------------------------------------------------------

def _to_int(v: Any) -> Optional[int]:
    if v is None or isinstance(v, bool):
        return int(v) if isinstance(v, bool) else None
    s = str(v).strip()
    if s == "" or s == UNCAPTURED_ROLE_SENTINEL:
        return None
    try:
        return int(float(s))
    except (ValueError, TypeError):
        return None


def _tag_value(tags: Any, prefix: str) -> Optional[str]:
    if not isinstance(tags, list):
        return None
    for t in tags:
        if isinstance(t, str) and t.startswith(prefix):
            return t[len(prefix):]
    return None


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# FACEIT match ids are ``1-<uuid>``; accept either a bare id or a room URL.
_MATCH_ID_RE = re.compile(r"1-[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}"
                          r"-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}")


def parse_match_id(ref: str) -> Optional[str]:
    """Extract a match id from a bare id or a faceit room URL; None if invalid."""
    m = _MATCH_ID_RE.search(ref.strip())
    return m.group(0) if m else None


def dedupe_preserving_order(refs: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for r in refs:
        if r not in seen:
            seen.add(r)
            out.append(r)
    return out


# --- pool parsing (seed heroes / maps) ---------------------------------------

def parse_heroes(match_payload: dict[str, Any]) -> list[Hero]:
    entities = match_payload.get("voting", {}).get("heroes", {}).get("entities", []) or []
    out: list[Hero] = []
    for e in entities:
        guid = e.get("guid")
        if not guid:
            continue
        role = _tag_value(e.get("filters", {}).get("voting_tags"), "role:")
        out.append(Hero(guid=guid, name=e.get("name") or guid, role=role))
    return out


def parse_maps(match_payload: dict[str, Any]) -> list[Map]:
    entities = match_payload.get("voting", {}).get("map", {}).get("entities", []) or []
    out: list[Map] = []
    for e in entities:
        guid = e.get("guid")
        if not guid:
            continue
        cat = _tag_value(e.get("filters", {}).get("voting_tags"), "cat:")
        out.append(Map(guid=guid, name=e.get("name") or guid, category=cat))
    return out


# --- democracy reconciliation -------------------------------------------------

def _democracy_slots(dem_payload: Optional[dict[str, Any]]) -> list[dict[str, Any]]:
    """Group democracy tickets into per-game slots.

    Tickets come in fixed groups of three (map, attacking_first, heroes); the
    group index is the Bo-N game slot (0-based). Returns one dict per slot keyed
    by entity_type.
    """
    if not dem_payload:
        return []
    tickets = dem_payload.get("tickets", []) or []
    slots: list[dict[str, Any]] = []
    for i in range(0, len(tickets), 3):
        slot: dict[str, Any] = {}
        for t in tickets[i:i + 3]:
            etype = t.get("entity_type")
            if etype:
                slot[etype] = t
        slots.append(slot)
    return slots


@dataclass(slots=True)
class _SlotInfo:
    """A democracy game-slot, indexed for joining to a played game."""

    ordered_bans: list[tuple[str, Optional[str]]]
    drop_set: frozenset[str]
    map_guid: Optional[str]
    map_ticket: Optional[dict[str, Any]]
    atk_ticket: Optional[dict[str, Any]]
    used: bool = field(default=False)


def _previous_loser(winners: list[Optional[str]], g: int) -> Optional[str]:
    """Faction that lost game g-1 (bans first in game g). None if unknown."""
    idx = g - 2
    if idx < 0 or idx >= len(winners):
        return None
    w = winners[idx]
    return FACTION2 if w == FACTION1 else FACTION1 if w == FACTION2 else None


def _order_bans(
    pairs: list[tuple[str, Optional[str]]], first_banner: Optional[str],
) -> list[tuple[str, Optional[str]]]:
    """Put the first-banning faction's ban first. Order is cosmetic otherwise."""
    if not first_banner or len(pairs) != 2:
        return pairs
    a, b = pairs
    if a[1] != first_banner and b[1] == first_banner:
        return [b, a]
    return [a, b]


def _pick_guid(ticket: Optional[dict[str, Any]]) -> Optional[str]:
    """Guid of the entity a map/side ticket resolved to ('pick')."""
    if not ticket:
        return None
    for e in ticket.get("entities", []) or []:
        if e.get("status") == "pick":
            return _entity_guid(e)
    return None


def _democracy_slot_infos(dem_payload: Optional[dict[str, Any]]) -> list[_SlotInfo]:
    infos: list[_SlotInfo] = []
    for slot in _democracy_slots(dem_payload):
        ordered, _ = _ordered_bans_from_ticket(slot.get("heroes"))
        infos.append(_SlotInfo(
            ordered_bans=ordered,
            drop_set=frozenset(g for g, _ in ordered),
            map_guid=_pick_guid(slot.get("map")),
            map_ticket=slot.get("map"),
            atk_ticket=slot.get("attacking_first"),
        ))
    return infos


def _match_slot(
    infos: list[_SlotInfo], ban_set: frozenset[str], game_map: Optional[str],
) -> Optional[_SlotInfo]:
    """Join a played game to its veto slot.

    Prefer exact ban-set equality; fall back to the map the game was played on.
    The map fallback rescues the rare game where FACEIT's two feeds disagree on
    one banned hero (so the ban-sets differ) — there we still attribute the heroes
    both feeds agree on, and leave the single disputed hero NULL.
    """
    for info in infos:
        if not info.used and info.drop_set and info.drop_set == ban_set:
            info.used = True
            return info
    if game_map:
        for info in infos:
            if not info.used and info.drop_set and info.map_guid == game_map:
                info.used = True
                return info
    return None


def _entity_guid(e: dict[str, Any]) -> Optional[str]:
    """Hero/map guid, tolerant of both veto payload shapes.

    The live democracy feed nests it under ``properties.guid``; the durable
    ``/history`` feed puts it directly on the entity as ``guid``.
    """
    return e.get("properties", {}).get("guid") or e.get("guid")


def _ordered_bans_from_ticket(
    heroes_ticket: Optional[dict[str, Any]],
) -> tuple[list[tuple[str, Optional[str]]], bool]:
    """Return ((guid, banned_by_faction) in ban order, is_open).

    Attribution always comes from each drop's ``selected_by``. Ban order comes
    from ``config`` (live feed) or the entity ``round`` (``/history`` feed); when
    neither is present, payload order is kept (order is cosmetic — attribution is
    per-entity). ``is_open`` is True when the ticket has no drops (all ``open``)
    — i.e. the game was restarted (veto wiped) or is unplayed.
    """
    if not heroes_ticket:
        return [], True
    entities = heroes_ticket.get("entities", []) or []
    drops = [e for e in entities if e.get("status") == "drop"]
    if not drops:
        return [], True

    config = heroes_ticket.get("config")
    if isinstance(config, list) and config:
        # Live feed: config gives the voter sequence; match drops by selected_by.
        ordered: list[tuple[str, Optional[str]]] = []
        remaining = list(drops)
        for cfg in config:
            voter = cfg.get("voter")
            picked = next((d for d in remaining if d.get("selected_by") == voter), None)
            if picked is not None:
                remaining.remove(picked)
                guid = _entity_guid(picked)
                if guid:
                    ordered.append((guid, voter))
        for d in remaining:
            guid = _entity_guid(d)
            if guid:
                ordered.append((guid, d.get("selected_by")))
        return ordered, False

    # History feed (or no config): order by ban-step 'round', stable otherwise.
    ordered_drops = sorted(drops, key=lambda e: e.get("round") or 0)
    ordered = [
        (guid, d.get("selected_by"))
        for d in ordered_drops
        if (guid := _entity_guid(d))
    ]
    return ordered, False


def _pick_selected_by(ticket: Optional[dict[str, Any]]) -> Optional[str]:
    """Faction that made the final 'pick' in a map / attacking_first ticket."""
    if not ticket:
        return None
    for e in ticket.get("entities", []) or []:
        if e.get("status") == "pick":
            return e.get("selected_by")
    return None


# --- the main extraction ------------------------------------------------------

def extract_bundle(
    match_payload: dict[str, Any],
    dem_payload: Optional[dict[str, Any]],
    stats: list[dict[str, Any]],
    *,
    fetched_at: Optional[str] = None,
) -> MatchBundle:
    fetched_at = fetched_at or _now_iso()
    warnings: list[str] = []

    match_id = match_payload.get("id", "")
    entity = match_payload.get("entity", {}) or {}
    championship_id = entity.get("id", "")
    entity_custom = match_payload.get("entityCustom", {}) or {}

    (teams, elo_by_player, team_by_player, faction_ids,
     nick_by_player, game_by_player) = _parse_teams(match_payload)

    results = match_payload.get("results", []) or []
    voting = match_payload.get("voting", {}) or {}
    map_pick = voting.get("map", {}).get("pick", []) or []
    atk_pick = voting.get("attacking_first", {}).get("pick", []) or []
    hero_survivors = voting.get("heroes", {}).get("pick", []) or []
    hero_pool_entities = voting.get("heroes", {}).get("entities", []) or []
    pool_guids_ordered = [e.get("guid") for e in hero_pool_entities if e.get("guid")]
    demo_urls = match_payload.get("demoURLs", []) or []

    stats_by_round = {
        _to_int(g.get("matchRound")): g for g in stats if _to_int(g.get("matchRound"))
    }
    best_of = _to_int(stats[0].get("bestOf")) if stats else None

    # Player identities: rosters carry nicknames; augment with stats rows for any
    # subs who played but weren't on the listed roster.
    for sg in stats:
        for tm in sg.get("teams", []) or []:
            for pl in tm.get("players", []) or []:
                pid = pl.get("playerId")
                if pid and pid not in nick_by_player:
                    nick_by_player[pid] = pl.get("nickname")
    players = [Player(id=pid, nickname=nn, game_name=game_by_player.get(pid))
               for pid, nn in nick_by_player.items()]

    # Forfeit: FACEIT flags it per-faction in summaryResults / results.
    def _any_forfeit(node: dict[str, Any]) -> bool:
        facs = node.get("factions", {}) or {}
        return any(bool((facs.get(f, {}) or {}).get("forfeit")) for f in (FACTION1, FACTION2))
    forfeit = _any_forfeit(match_payload.get("summaryResults", {}) or {}) or any(
        _any_forfeit(r) for r in results
    )

    dem_present = dem_payload is not None
    # Pre-process democracy slots. Index alignment between democracy slots and
    # played games is NOT reliable across restarts (verified on real data: a
    # restarted game leaves an 'open' slot and shifts the rest), so we join a
    # game to its veto slot by BAN-SET equality, not by position.
    slot_infos = _democracy_slot_infos(dem_payload)

    # per-game winners (chronological) — used both for the match winner and to
    # derive ban order (the previous map's loser bans first).
    winners = [r.get("winner") for r in results]
    wins = {FACTION1: 0, FACTION2: 0}
    for w in winners:
        if w in wins:
            wins[w] += 1
    winner_faction: Optional[str] = None
    if wins[FACTION1] != wins[FACTION2]:
        winner_faction = FACTION1 if wins[FACTION1] > wins[FACTION2] else FACTION2

    match = Match(
        id=match_id,
        championship_id=championship_id,
        round=_to_int(entity_custom.get("round")),
        group_no=_to_int(entity_custom.get("group")),
        status=match_payload.get("status", "UNKNOWN"),
        best_of=best_of,
        scheduled_at=match_payload.get("scheduledAt") or None,
        started_at=match_payload.get("startedAt") or None,
        finished_at=match_payload.get("finishedAt") or None,
        faction1_team_id=faction_ids.get(FACTION1),
        faction2_team_id=faction_ids.get(FACTION2),
        winner_faction=winner_faction,
        forfeit=forfeit,
        fetched_at=fetched_at,
    )

    games: list[Game] = []
    map_picks: list[MapPick] = []
    hero_bans: list[HeroBan] = []
    round_players: list[RoundPlayer] = []

    n_games = len(results)
    for g in range(1, n_games + 1):
        idx = g - 1
        result = results[idx]
        factions = result.get("factions", {}) or {}
        map_guid = map_pick[idx] if idx < len(map_pick) else None
        demo_code = demo_urls[idx] if idx < len(demo_urls) else None

        # --- hero bans: WHICH heroes come from the match payload --------------
        # Bans = pool minus survivors, but only when a survivor list exists for
        # this game. An absent/empty heroes.pick means no hero veto was recorded
        # (e.g. a game conceded after the veto, or a disrupted veto) -> NO bans;
        # never treat "pool minus nothing" as "all 52 banned".
        has_veto = idx < len(hero_survivors) and bool(hero_survivors[idx])
        if has_veto:
            survivors = set(hero_survivors[idx])
            banned_guids = [gd for gd in pool_guids_ordered if gd not in survivors]
        else:
            banned_guids = []
            warnings.append(f"game {g}: no hero veto recorded")

        # --- attribution: join this game to its veto slot (ban-set, then map) --
        ban_set = frozenset(banned_guids)
        slot = _match_slot(slot_infos, ban_set, map_guid) if (dem_present and banned_guids) else None

        if slot is not None:
            attr = {gd: fac for gd, fac in slot.ordered_bans}
            pairs: list[tuple[str, Optional[str]]] = [(gd, attr.get(gd)) for gd in banned_guids]
            map_pick_by = _pick_selected_by(slot.map_ticket)
            side_pick_by = _pick_selected_by(slot.atk_ticket)
            was_restarted = False
        else:
            # Veto record for this played game is absent (restart / disruption).
            # Bans are still real; attribution is unrecoverable.
            pairs = [(gd, None) for gd in banned_guids]
            map_pick_by = None
            side_pick_by = None
            was_restarted = dem_present and bool(banned_guids)

        # Ban ORDER by the verified rule (not FACEIT's unreliable `round` field):
        # game 1 -> faction1 bans first; later games -> the previous map's loser
        # bans first. With one ban per team, that fixes the whole order.
        first_banner = FACTION1 if g == 1 else _previous_loser(winners, g)
        for order, (guid, faction) in enumerate(_order_bans(pairs, first_banner), start=1):
            hero_bans.append(HeroBan(match_id, g, guid, order, faction))

        # --- map category from stats (per-round) ------------------------------
        sgame = stats_by_round.get(g)
        map_category = sgame.get("i18") if sgame else None

        games.append(Game(
            match_id=match_id,
            game_no=g,
            map_guid=map_guid,
            map_category=map_category,
            attacking_first_faction=(atk_pick[idx] if idx < len(atk_pick) else None),
            side_picked_by_faction=side_pick_by,
            faction1_score=_to_int(factions.get(FACTION1, {}).get("score")),
            faction2_score=_to_int(factions.get(FACTION2, {}).get("score")),
            winner_faction=result.get("winner"),
            demo_code=demo_code,
            was_restarted=was_restarted,
        ))
        map_picks.append(MapPick(match_id, g, map_guid, map_pick_by))

        # --- round players from stats (hazard A) ------------------------------
        rp, w = _round_players_for_game(
            match_id, g, sgame, elo_by_player, team_by_player, faction_ids, demo_code,
        )
        round_players.extend(rp)
        warnings.extend(w)

    # Any democracy veto slot that never matched a played game is an orphan
    # (its game may have been restarted and re-vetoed elsewhere). Surface it.
    for info in slot_infos:
        if info.drop_set and not info.used:
            warnings.append(
                f"democracy veto slot {sorted(info.drop_set)} matched no played game"
            )

    return MatchBundle(
        match=match,
        teams=teams,
        players=players,
        games=games,
        map_picks=map_picks,
        hero_bans=hero_bans,
        round_players=round_players,
        heroes=parse_heroes(match_payload),
        maps=parse_maps(match_payload),
        warnings=warnings,
    )


def _parse_teams(
    match_payload: dict[str, Any],
) -> tuple[list[Team], dict[str, Optional[int]], dict[str, str],
           dict[str, str], dict[str, Optional[str]], dict[str, Optional[str]]]:
    teams_node = match_payload.get("teams", {}) or {}
    teams: list[Team] = []
    elo_by_player: dict[str, Optional[int]] = {}
    team_by_player: dict[str, str] = {}
    faction_ids: dict[str, str] = {}
    nick_by_player: dict[str, Optional[str]] = {}
    game_by_player: dict[str, Optional[str]] = {}   # Battle.net in-game name
    for fac in (FACTION1, FACTION2):
        t = teams_node.get(fac)
        if not t:
            continue
        tid = t.get("id")
        if tid:
            faction_ids[fac] = tid
            teams.append(Team(id=tid, name=t.get("name"), avatar_url=t.get("avatar")))
        # roster + substitutes both carry player identity
        for pl in (t.get("roster", []) or []) + (t.get("substitutes", []) or []):
            pid = pl.get("id")
            if pid:
                elo_by_player[pid] = _to_int(pl.get("elo"))
                nick_by_player[pid] = pl.get("nickname")
                game_by_player[pid] = pl.get("gameName")
                if tid:
                    team_by_player[pid] = tid
    return (teams, elo_by_player, team_by_player, faction_ids,
            nick_by_player, game_by_player)


def _round_players_for_game(
    match_id: str,
    game_no: int,
    sgame: Optional[dict[str, Any]],
    elo_by_player: dict[str, Optional[int]],
    team_by_player: dict[str, str],
    faction_ids: dict[str, str],
    demo_code: Optional[str],
) -> tuple[list[RoundPlayer], list[str]]:
    warnings: list[str] = []
    out: list[RoundPlayer] = []
    if not sgame:
        # Played game with no stats object at all: fall back to nothing rather
        # than fabricating rows; surface it.
        warnings.append(f"game {game_no}: no stats object present")
        return out, warnings

    for tm in sgame.get("teams", []) or []:
        team_id = tm.get("teamId")
        players = tm.get("players", []) or []
        uncaptured = 0
        for pl in players:
            pid = pl.get("playerId")
            if not pid:
                continue
            role = pl.get("i16")
            captured = role != UNCAPTURED_ROLE_SENTINEL
            if not captured:
                uncaptured += 1
            out.append(RoundPlayer(
                match_id=match_id,
                game_no=game_no,
                team_id=team_id or team_by_player.get(pid),
                player_id=pid,
                role=None if role == UNCAPTURED_ROLE_SENTINEL else role,
                elo_snapshot=elo_by_player.get(pid),
                stats_captured=captured,
                # HAZARD A: never coerce a missing stat to 0 -> NULL when uncaptured
                eliminations=_to_int(pl.get(STAT_FIELD_MAP["eliminations"])) if captured else None,
                deaths=_to_int(pl.get(STAT_FIELD_MAP["deaths"])) if captured else None,
                assists=_to_int(pl.get(STAT_FIELD_MAP["assists"])) if captured else None,
                damage=_to_int(pl.get(STAT_FIELD_MAP["damage"])) if captured else None,
                healing=_to_int(pl.get(STAT_FIELD_MAP["healing"])) if captured else None,
                damage_mitigated=_to_int(pl.get(STAT_FIELD_MAP["damage_mitigated"])) if captured else None,
            ))
        # HAZARD A warning: game played (demo exists) but a whole team's rows empty
        if players and uncaptured == len(players) and demo_code:
            warnings.append(
                f"game {game_no}: team {team_id} stats not captured (all rows zeroed) "
                f"but game was played (demo {demo_code}) -> stored as NULL"
            )
    return out, warnings


# --- orchestration ------------------------------------------------------------

class SyncResult:
    def __init__(self) -> None:
        self.matches_seen = 0
        self.inserted = 0
        self.updated = 0
        self.skipped = 0
        self.warnings = 0
        self.errors = 0

    def as_dict(self) -> dict[str, int]:
        return {
            "matches_seen": self.matches_seen, "inserted": self.inserted,
            "updated": self.updated, "skipped": self.skipped,
            "warnings": self.warnings, "errors": self.errors,
        }


# Replay codes appear after a match finishes, so recent FINISHED matches missing
# codes are re-fetched despite being stored. Two weeks is well past the point where
# a code will ever show up, and the set is small (matches missing codes only).
DEFAULT_BACKFILL_DAYS = 14


class SyncEngine:
    def __init__(self, client: FaceitClient, db: Database,
                 backfill_days: int = DEFAULT_BACKFILL_DAYS) -> None:
        self.client = client
        self.db = db
        self.backfill_days = backfill_days
        self._backfill: Optional[set[str]] = None

    def _skip_stored(self, match_id: str, force_refresh: bool) -> bool:
        """Whether an already-stored match can be skipped. A stored FINISHED match
        is re-fetched when it is still missing replay codes and recent enough for
        them to appear (see Database.matches_needing_backfill)."""
        if force_refresh or self.db.match_status(match_id) != "FINISHED":
            return False
        if self._backfill is None:      # computed once per run, not per match
            self._backfill = self.db.matches_needing_backfill(self.backfill_days)
        if match_id in self._backfill:
            log.info("re-fetch %s (stored FINISHED but missing replay codes)", match_id)
            return False
        return True

    def ingest_match(
        self,
        match_id: str,
        championship_id: Optional[str] = None,
        *,
        force_refresh: bool = False,
        dry_run: bool = False,
    ) -> str:
        """Ingest a single match. Returns 'inserted' | 'updated' | 'skipped'."""
        if self._skip_stored(match_id, force_refresh):
            log.info("skip %s (already stored FINISHED)", match_id)
            return "skipped"

        match_payload = self.client.get_match(match_id)
        # Only ingest matches that have actually been played. Scheduled/ongoing
        # matches carry no results and would otherwise be stored empty and
        # re-fetched on every run.
        status = match_payload.get("status", "")
        if status != "FINISHED" or not match_payload.get("results"):
            log.info("skip %s (status=%s, not a finished match)", match_id, status or "?")
            return "skipped"

        dem_payload = self.client.get_democracy(match_id)
        stats = self.client.get_stats(match_id)
        if dem_payload is None:
            log.warning(
                "%s: democracy unavailable (404 / expired) -> veto attribution NULL",
                match_id,
            )

        bundle = extract_bundle(match_payload, dem_payload, stats)
        for w in bundle.warnings:
            log.warning("%s: %s", match_id, w)

        if dry_run:
            log.info(
                "[dry-run] %s: %d games, %d bans, %d player-rows, %d warnings",
                match_id, len(bundle.games), len(bundle.hero_bans),
                len(bundle.round_players), len(bundle.warnings),
            )
            return "skipped"

        newly = self._persist(bundle, championship_id, match_payload)
        return "inserted" if newly else "updated"

    def _persist(
        self,
        bundle: MatchBundle,
        championship_id: Optional[str],
        match_payload: dict[str, Any],
    ) -> bool:
        entity = match_payload.get("entity", {}) or {}
        champ = Championship(
            id=bundle.match.championship_id or (championship_id or ""),
            name=entity.get("name"),
            game=match_payload.get("game"),
            region=match_payload.get("region"),
        )
        with self.db.transaction():
            self.db.upsert_championship(champ)
            for t in bundle.teams:
                self.db.upsert_team(t)
            for pl in bundle.players:
                self.db.upsert_player(pl)
            for h in bundle.heroes:
                self.db.upsert_hero(h)
            for m in bundle.maps:
                self.db.upsert_map(m)
            newly = self.db.upsert_match(bundle.match)
            self.db.replace_children(
                bundle.match.id, bundle.games, bundle.map_picks,
                bundle.hero_bans, bundle.round_players,
            )
        return newly

    def known_team_ids(self, championship_id: str) -> list[str]:
        """Real team ids in this championship (UUIDs).

        Bracket byes appear as a pseudo-team id like ``bye`` which isn't a real
        team (enumerating it 404s), so we keep only UUID-shaped ids.
        """
        rows = self.db.conn.execute(
            """SELECT tid FROM (
                   SELECT faction1_team_id tid FROM matches WHERE championship_id=?
                   UNION SELECT faction2_team_id FROM matches WHERE championship_id=?
               ) WHERE tid IS NOT NULL""",
            (championship_id, championship_id),
        ).fetchall()
        return [str(r[0]) for r in rows
                if len(str(r[0])) == 36 and str(r[0]).count("-") == 4]

    def _ingest_and_tally(
        self, mid: str, cid: str, result: "SyncResult", *,
        force_refresh: bool, dry_run: bool,
    ) -> None:
        if self._skip_stored(mid, force_refresh):
            result.skipped += 1
            return
        try:
            outcome = self.ingest_match(mid, cid, force_refresh=force_refresh, dry_run=dry_run)
        except Exception:  # noqa: BLE001 - one bad match must not abort the run
            log.exception("error ingesting %s", mid)
            result.errors += 1
            return
        if outcome == "inserted":
            result.inserted += 1
        elif outcome == "updated":
            result.updated += 1
        else:
            result.skipped += 1

    def run(
        self,
        championship_id: str,
        *,
        force_refresh: bool = False,
        dry_run: bool = False,
    ) -> SyncResult:
        """Enumerate + ingest a whole championship, keyless.

        Transitive discovery: starting from the teams already known for this
        championship (even one seed match is enough), we enumerate each team's
        matches; ingesting them reveals new opponents, which we then enumerate
        too, until the team graph is exhausted. In a connected schedule this
        reaches every team and match from any single seed.
        """
        result = SyncResult()
        seed_teams = self.known_team_ids(championship_id)
        if not seed_teams:
            if self.client.api_key:
                for s in self.client.iter_championship_matches(championship_id):
                    mid = s.get("match_id") or s.get("id")
                    if mid:
                        result.matches_seen += 1
                        self._ingest_and_tally(mid, championship_id, result,
                                               force_refresh=force_refresh, dry_run=dry_run)
                self._write_sync_log(result, championship_id)
                return result
            raise EnumerationError(
                "No teams are known for this championship yet, and no FACEIT_API_KEY is set. "
                "Seed a few matches first, e.g.:  faceit-sync fetch --matches <room-url> ..."
            )

        processed: set[str] = set()
        seen: set[str] = set()
        while True:
            teams = [t for t in self.known_team_ids(championship_id) if t not in processed]
            if not teams:
                break
            for tid in teams:
                processed.add(tid)
                try:
                    matches = list(
                        self.client.iter_team_championship_matches(championship_id, tid)
                    )
                except Exception:  # noqa: BLE001 - a bad team must not abort enumeration
                    log.exception("error enumerating team %s", tid)
                    result.errors += 1
                    continue
                for m in matches:
                    if m.get("status") != "finished":
                        continue
                    mid = m["match_id"]
                    if mid in seen:
                        continue
                    seen.add(mid)
                    result.matches_seen += 1
                    self._ingest_and_tally(mid, championship_id, result,
                                           force_refresh=force_refresh, dry_run=dry_run)
        log.info("championship %s: %d matches across %d teams",
                 championship_id, len(seen), len(processed))
        self._write_sync_log(result, championship_id)
        return result

    def _write_sync_log(self, result: "SyncResult", cid: Optional[str]) -> None:
        self.db.insert_sync_log(
            ran_at=_now_iso(), championship_id=cid,
            matches_seen=result.matches_seen, inserted=result.inserted,
            updated=result.updated, skipped=result.skipped,
            warnings=result.warnings, errors=result.errors,
        )

    def run_all(self, *, force_refresh: bool = False, dry_run: bool = False) -> SyncResult:
        """Update every championship currently stored (all divisions)."""
        total = SyncResult()
        cids = [
            str(r[0]) for r in
            self.db.conn.execute("SELECT id FROM championships ORDER BY name").fetchall()
        ]
        for cid in cids:
            r = self.run(cid, force_refresh=force_refresh, dry_run=dry_run)
            total.matches_seen += r.matches_seen
            total.inserted += r.inserted
            total.updated += r.updated
            total.skipped += r.skipped
            total.warnings += r.warnings
            total.errors += r.errors
        return total

    def backfill_game_names(
        self, *, limit: Optional[int] = None,
        progress: Optional[Callable[[int, int], None]] = None,
    ) -> int:
        """Fill players.game_name (Battle.net names) for already-stored matches.

        game_name arrived after most matches were ingested, and normal sync skips
        finished matches, so historical rosters have it NULL. This is a cheap,
        targeted backfill: only matches that HAVE a demo code (the scoutable ones,
        where attribution matters) and still have a player missing a game_name,
        newest first, one match-detail call each. Returns players updated.
        """
        mids = [
            r[0] for r in self.db.conn.execute(
                """SELECT DISTINCT g.match_id
                   FROM games g JOIN matches m ON m.id = g.match_id
                   WHERE g.demo_code IS NOT NULL
                   ORDER BY m.finished_at DESC"""
            ).fetchall()
        ]
        updated = done = 0
        for mid in mids:
            missing = self.db.conn.execute(
                """SELECT COUNT(*) FROM round_players rp
                   JOIN players p ON p.id = rp.player_id
                   WHERE rp.match_id = ? AND p.game_name IS NULL""",
                (mid,),
            ).fetchone()[0]
            if not missing:
                continue
            try:
                payload = self.client.get_match(mid)
                *_, game_by_player = _parse_teams(payload)
            except Exception:  # noqa: BLE001 - one bad match must not abort the batch
                log.exception("backfill: could not fetch %s", mid)
                continue
            for pid, gn in game_by_player.items():
                if gn:
                    cur = self.db.conn.execute(
                        "UPDATE players SET game_name = ? "
                        "WHERE id = ? AND game_name IS NULL",
                        (gn, pid),
                    )
                    updated += cur.rowcount
            self.db.conn.commit()
            done += 1
            if progress is not None:
                progress(done, len(mids))
            if limit is not None and done >= limit:
                break
        log.info("backfill: filled %d game_name(s) across %d match(es)", updated, done)
        return updated

    def run_matches(
        self,
        refs: Iterable[str],
        *,
        force_refresh: bool = False,
        dry_run: bool = False,
        progress: Optional[Callable[[int, int], None]] = None,
    ) -> SyncResult:
        """Mass-import an explicit list of match refs (ids or room URLs).

        Keyless: uses only the public match/democracy/stats endpoints. Each
        match's championship is derived from its own payload, so no championship
        id is required.

        ``progress(done, total)`` is called after every match. A first-run
        bootstrap is hundreds of rate-limited requests, which without this looks
        exactly like a hung application; callers that can show a bar should.
        Errors in the callback are never allowed to abort the import.
        """
        result = SyncResult()
        parsed: list[str] = []
        for ref in refs:
            match_id = parse_match_id(str(ref))
            if not match_id:
                log.warning("skip unparseable match ref: %r", ref)
                result.errors += 1
                continue
            parsed.append(match_id)

        queue = dedupe_preserving_order(parsed)
        total = len(queue)
        for done, match_id in enumerate(queue, start=1):
            try:
                result.matches_seen += 1
                if self._skip_stored(match_id, force_refresh):
                    result.skipped += 1
                    continue
                try:
                    outcome = self.ingest_match(
                        match_id, force_refresh=force_refresh, dry_run=dry_run,
                    )
                except Exception:  # noqa: BLE001 - one bad match must not abort the batch
                    log.exception("error ingesting %s", match_id)
                    result.errors += 1
                    continue
                if outcome == "inserted":
                    result.inserted += 1
                elif outcome == "updated":
                    result.updated += 1
                else:
                    result.skipped += 1
            finally:
                # In `finally` so a skip or an ingest error still advances the
                # bar - a bar that freezes on a bad match is worse than none.
                if progress is not None:
                    try:
                        progress(done, total)
                    except Exception:  # noqa: BLE001 - display must not break import
                        log.debug("progress callback failed", exc_info=True)

        self.db.insert_sync_log(
            ran_at=_now_iso(), championship_id=None,
            matches_seen=result.matches_seen, inserted=result.inserted,
            updated=result.updated, skipped=result.skipped,
            warnings=result.warnings, errors=result.errors,
        )
        return result

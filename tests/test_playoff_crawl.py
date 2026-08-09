"""Playoff bracket discovery through the keyless crawler.

Keyless discovery is transitive: it enumerates matches only for teams already in
a championship's match graph. A playoff bracket's teams are the regular season's
qualifiers, so a team whose first playoff match is against another not-yet-known
team would stay invisible until it linked into a known one — late in a bracket.
The crawler closes that gap two ways:

  * ``_related_division_teams`` seeds a playoff championship's crawl with the
    sibling regular-season division's teams (the qualifiers), so every bracket
    slot is discoverable from the first run.
  * ``run_all`` crawls regular-season divisions before their playoff siblings,
    so those sibling teams are fully known before the bracket is crawled.
"""

from __future__ import annotations

import responses
from conftest import NORMAL_30_ID, make_client, register_match

from faceit_sync.client import CHAMP_MATCHES_URL
from faceit_sync.db import Database
from faceit_sync.sync import SyncEngine

PO = "c2e6135e-8160-4991-a869-1bcd575bf2cf"       # S9 EMEA Master Central - Playoffs
REG = "938f6e68-b374-4f0f-b3e1-3bf1bdfbfd11"      # S9 EMEA Master Central - Regular Season
TPLAY = "aaaaaaaa-0000-0000-0000-000000000001"
TREG = "bbbbbbbb-0000-0000-0000-000000000002"


def _seed(db: Database) -> None:
    """One stored match per championship, so each has a distinct known-team set."""
    c = db.conn
    c.execute("INSERT INTO championships(id,name) VALUES(?,?)",
              (PO, "S9 EMEA Master Central - Playoffs"))
    c.execute("INSERT INTO championships(id,name) VALUES(?,?)",
              (REG, "S9 EMEA Master Central - Regular Season"))
    c.execute("INSERT INTO teams(id,name) VALUES(?,?)", (TPLAY, "Playoff Team"))
    c.execute("INSERT INTO teams(id,name) VALUES(?,?)", (TREG, "Regular Only Team"))
    c.execute(
        "INSERT INTO matches(id,championship_id,status,fetched_at,faction1_team_id,"
        "faction2_team_id) VALUES('seed-po',?,'FINISHED',datetime('now'),?,NULL)",
        (PO, TPLAY))
    c.execute(
        "INSERT INTO matches(id,championship_id,status,fetched_at,faction1_team_id,"
        "faction2_team_id) VALUES('seed-reg',?,'FINISHED',datetime('now'),?,NULL)",
        (REG, TREG))
    c.commit()


def test_related_division_teams_unions_the_sibling_regular_season(db: Database) -> None:
    """A playoff championship is seeded with the regular-season division's teams;
    a regular-season division never seeds from a sibling."""
    _seed(db)
    engine = SyncEngine(make_client()[0], db)
    assert engine._related_division_teams(PO) == {TREG}
    assert engine._related_division_teams(REG) == set()


def test_related_division_teams_is_empty_for_a_non_playoff_name(db: Database) -> None:
    _seed(db)
    db.conn.execute("UPDATE championships SET name='S9 EMEA Master Central - Regular Season' "
                    "WHERE id=?", (PO,))
    db.conn.commit()
    engine = SyncEngine(make_client()[0], db)
    # The championship is no longer named as a playoff -> no sibling seeding.
    assert engine._related_division_teams(PO) == set()


@responses.activate
def test_run_disovers_a_playoff_match_for_a_sibling_regular_team(db: Database) -> None:
    """A match involving a team only known from the regular season (never yet in
    the bracket's own graph) is discovered and ingested when crawling the
    playoff championship."""
    _seed(db)
    responses.add(
        responses.GET, CHAMP_MATCHES_URL, json={"payload": {"items": []}}, status=200,
        match=[responses.matchers.query_param_matcher({
            "championshipId": PO, "participantType": "TEAM",
            "participantId": TPLAY, "type": "past", "limit": 30, "offset": 0})])
    responses.add(
        responses.GET, CHAMP_MATCHES_URL, json={"payload": {"items": [
            {"origin": {"id": "1-new", "state": "FINISHED"}, "status": "finished"}]}},
        status=200,
        match=[responses.matchers.query_param_matcher({
            "championshipId": PO, "participantType": "TEAM",
            "participantId": TREG, "type": "past", "limit": 30, "offset": 0})])
    register_match(responses, "1-new", prefix="normal_30", democracy=True, veto="history")

    engine = SyncEngine(make_client()[0], db)
    result = engine.run(PO)

    assert result.matches_seen == 1        # the one match found via the sibling team
    assert result.inserted == 1
    # The discovered match was ingested (the fixture is the real match payload).
    stored = {r[0] for r in db.conn.execute("SELECT id FROM matches")}
    assert NORMAL_30_ID in stored


@responses.activate
def test_run_all_crawls_regular_divisions_before_playoff(db: Database) -> None:
    """run_all must fully discover the regular division before the bracket crawl
    seeds from it — otherwise the sibling teams are only half-known."""
    _seed(db)
    for cid in (PO, REG):
        for tid in (TPLAY, TREG):
            responses.add(
                responses.GET, CHAMP_MATCHES_URL, json={"payload": {"items": []}},
                status=200,
                match=[responses.matchers.query_param_matcher({
                    "championshipId": cid, "participantType": "TEAM",
                    "participantId": tid, "type": "past", "limit": 30, "offset": 0})])

    engine = SyncEngine(make_client()[0], db)
    engine.run_all()

    order = [r[0] for r in db.conn.execute(
        "SELECT championship_id FROM sync_log ORDER BY ran_at")]
    assert order == [REG, PO]

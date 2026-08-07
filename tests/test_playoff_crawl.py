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

from faceit_sync.client import CHAMP_MATCHES_URL, DATA_API_BASE
from faceit_sync.db import Database
from faceit_sync.sync import SyncEngine
from conftest import NORMAL_30_ID, make_client, register_match

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


ORG = "f0e8a591-08fd-4619-9d59-d97f0571842e"


def _seed_with_organizer(db: Database) -> None:
    """Regular-season division has an organizer_id so discovery can match."""
    c = db.conn
    c.execute(
        "INSERT INTO championships(id,name,game,organizer_id) VALUES(?,?,?,?)",
        (REG, "S9 EMEA Master Central - Regular Season", "ow2", ORG))
    c.execute("INSERT INTO teams(id,name) VALUES(?,?)", (TREG, "Regular Only Team"))
    c.execute(
        "INSERT INTO matches(id,championship_id,status,fetched_at,faction1_team_id,"
        "faction2_team_id) VALUES('seed-reg',?,'FINISHED',datetime('now'),?,NULL)",
        (REG, TREG))
    c.commit()


@responses.activate
def test_discover_playoff_championships_finds_same_organizer_playoff(db: Database) -> None:
    """Data API list is filtered to playoff championships matching a known base
    name and sharing the regular-season division's organizer."""
    _seed_with_organizer(db)
    url = f"{DATA_API_BASE}/championships"
    responses.add(responses.GET, url, json={
        "items": [
            {"championship_id": PO, "name": "S9 EMEA Master Central - Playoffs",
             "organizer_id": ORG},
            {"championship_id": "other-cid", "name": "Other League - Playoffs",
             "organizer_id": "other-org"},
            {"championship_id": REG, "name": "S9 EMEA Master Central - Regular Season",
             "organizer_id": ORG},
        ]
    }, status=200)

    engine = SyncEngine(make_client(api_key="key")[0], db)
    found = engine._discover_playoff_championships("ow2")

    assert found == [(PO, "S9 EMEA Master Central - Playoffs", ORG)]


@responses.activate
def test_run_all_discovers_and_crawls_new_playoff_championship(db: Database) -> None:
    """If the DB has only the regular season, run_all discovers the playoff
    championship via the Data API and then crawls it."""
    _seed_with_organizer(db)
    # Data API list finds the playoff championship.
    list_url = f"{DATA_API_BASE}/championships"
    responses.add(responses.GET, list_url, json={
        "items": [
            {"championship_id": PO, "name": "S9 EMEA Master Central - Playoffs",
             "organizer_id": ORG},
        ]
    }, status=200)
    # Regular-season crawl has no matches beyond the seed.
    responses.add(
        responses.GET, CHAMP_MATCHES_URL, json={"payload": {"items": []}},
        status=200,
        match=[responses.matchers.query_param_matcher({
            "championshipId": REG, "participantType": "TEAM",
            "participantId": TREG, "type": "past", "limit": 30, "offset": 0})])
    # The discovered playoff championship has no matches.
    for tid in (TPLAY, TREG):
        responses.add(
            responses.GET, CHAMP_MATCHES_URL, json={"payload": {"items": []}},
            status=200,
            match=[responses.matchers.query_param_matcher({
                "championshipId": PO, "participantType": "TEAM",
                "participantId": tid, "type": "past", "limit": 30, "offset": 0})])
    # Keyed crawl of the discovered playoff championship (no teams in DB yet).
    responses.add(
        responses.GET, f"{DATA_API_BASE}/championships/{PO}/matches",
        json={"items": []}, status=200)

    engine = SyncEngine(make_client(api_key="key")[0], db)
    engine.run_all()

    order = [r[0] for r in db.conn.execute(
        "SELECT championship_id FROM sync_log ORDER BY ran_at")]
    assert order == [REG, PO]
    stored = {r[0] for r in db.conn.execute("SELECT id FROM championships")}
    assert PO in stored


def test_discover_playoff_championships_skipped_without_api_key(db: Database) -> None:
    """No Data API key means no discovery; existing divisions still crawl."""
    _seed_with_organizer(db)
    engine = SyncEngine(make_client()[0], db)
    assert engine._discover_playoff_championships("ow2") == []

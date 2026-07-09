"""Shared test fixtures and helpers."""

from __future__ import annotations

import random
from pathlib import Path
from typing import Optional

import pytest

from faceit_sync.client import (
    DEMOCRACY_URL,
    MATCH_URL,
    STATS_URL,
    FaceitClient,
)
from faceit_sync.db import Database

FIXTURES = Path(__file__).parent / "fixtures"

# Real match ids of the captured fixtures.
CLEAN_ID = "1-84e049a3-bf72-426a-a88e-f5c5039abd8f"
RESTART_DC_ID = "1-2ae09905-dcbf-46b0-a272-fa08afa3f293"
NORMAL_30_ID = "1-a1f0047a-5d05-4b40-aa47-58d18f92fc60"


def load_fixture(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


@pytest.fixture()
def db(tmp_path: Path) -> Database:
    database = Database(str(tmp_path / "test.sqlite3"))
    yield database
    database.close()


def make_client(api_key: Optional[str] = None) -> tuple[FaceitClient, list[float]]:
    """A client with no real sleeping and a seeded RNG; returns (client, sleeps)."""
    sleeps: list[float] = []
    client = FaceitClient(
        api_key=api_key,
        rate_limit=1_000_000.0,          # effectively disable inter-request spacing
        sleep=sleeps.append,
        rng=random.Random(0),
    )
    return client, sleeps


def register_match(
    responses_mock, match_id: str, *, prefix: str, democracy: bool, veto: str = "live"
) -> None:
    """Register match/democracy/stats endpoints for one match from fixtures.

    ``veto`` selects which veto feed carries the data (the client tries the
    durable ``/history`` path first, then the live democracy endpoint):
      * "live"    -> /history 404s, live democracy serves ``{prefix}_democracy.json``
      * "history" -> /history serves ``{prefix}_history.json``, live 404s
    Ignored when ``democracy`` is False (both 404).

    A single registered response in the ``responses`` library matches unlimited
    times, so this supports repeated ingests (idempotency tests).
    """
    nf = {"errors": [{"code": "err_nf0"}]}
    history_url = DEMOCRACY_URL.format(id=match_id) + "/history"
    live_url = DEMOCRACY_URL.format(id=match_id)

    responses_mock.add(
        responses_mock.GET, MATCH_URL.format(id=match_id),
        body=load_fixture(f"{prefix}_match.json"),
        content_type="application/json", status=200,
    )
    if not democracy:
        responses_mock.add(responses_mock.GET, history_url, json=nf, status=404)
        responses_mock.add(responses_mock.GET, live_url, json=nf, status=404)
    elif veto == "history":
        responses_mock.add(
            responses_mock.GET, history_url,
            body=load_fixture(f"{prefix}_history.json"),
            content_type="application/json", status=200,
        )
        responses_mock.add(responses_mock.GET, live_url, json=nf, status=404)
    else:  # "live": history missing, live feed present
        responses_mock.add(responses_mock.GET, history_url, json=nf, status=404)
        responses_mock.add(
            responses_mock.GET, live_url,
            body=load_fixture(f"{prefix}_democracy.json"),
            content_type="application/json", status=200,
        )
    responses_mock.add(
        responses_mock.GET, STATS_URL.format(id=match_id),
        body=load_fixture(f"{prefix}_stats.json"),
        content_type="application/json", status=200,
    )

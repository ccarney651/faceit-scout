"""429 -> exponential backoff + jitter, honouring Retry-After; 503 -> retry."""

from __future__ import annotations

import responses

from faceit_sync.client import MATCH_URL
from conftest import make_client

MID = "1-abc00000-0000-0000-0000-000000000000"


@responses.activate
def test_429_then_success_backs_off() -> None:
    url = MATCH_URL.format(id=MID)
    responses.add(responses.GET, url, json={}, status=429)   # no Retry-After
    responses.add(responses.GET, url, json={"payload": {"id": MID}}, status=200)

    client, sleeps = make_client()
    payload = client.get_match(MID)

    assert payload["id"] == MID
    assert len(responses.calls) == 2
    # An exponential backoff sleep (base 0.5 * 2^0 + jitter) was performed.
    assert any(s >= 0.5 for s in sleeps)


@responses.activate
def test_retry_after_header_is_honoured() -> None:
    url = MATCH_URL.format(id=MID)
    responses.add(responses.GET, url, status=429, headers={"Retry-After": "2"})
    responses.add(responses.GET, url, json={"payload": {"id": MID}}, status=200)

    client, sleeps = make_client()
    client.get_match(MID)

    assert 2.0 in sleeps


@responses.activate
def test_503_is_retried() -> None:
    url = MATCH_URL.format(id=MID)
    responses.add(responses.GET, url, status=503)
    responses.add(responses.GET, url, status=503)
    responses.add(responses.GET, url, json={"payload": {"id": MID}}, status=200)

    client, _ = make_client()
    assert client.get_match(MID)["id"] == MID
    assert len(responses.calls) == 3


@responses.activate
def test_retries_exhausted_raises() -> None:
    from faceit_sync.client import FaceitAPIError
    import pytest

    url = MATCH_URL.format(id=MID)
    for _ in range(10):
        responses.add(responses.GET, url, status=503)

    client, _ = make_client()  # default max_retries=5
    with pytest.raises(FaceitAPIError):
        client.get_match(MID)

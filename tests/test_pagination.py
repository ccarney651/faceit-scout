"""Data API pagination must exhaust all pages."""

from __future__ import annotations

import responses

from faceit_sync.client import DATA_API_BASE
from conftest import make_client


@responses.activate
def test_pagination_exhausts_all_pages() -> None:
    champ = "CID"
    url = f"{DATA_API_BASE}/championships/{champ}/matches"

    def page(start: int, count: int) -> dict:
        return {"items": [{"match_id": f"1-m{start + i}"} for i in range(count)],
                "start": start, "end": start + count}

    # Full page, full page, partial page (< limit) -> stop.
    responses.add(responses.GET, url, json=page(0, 20), status=200)
    responses.add(responses.GET, url, json=page(20, 20), status=200)
    responses.add(responses.GET, url, json=page(40, 5), status=200)

    client, _ = make_client(api_key="key")
    got = list(client.iter_championship_matches(champ))

    assert len(got) == 45
    assert got[0]["match_id"] == "1-m0"
    assert got[-1]["match_id"] == "1-m44"
    # 3 pages requested, and the Authorization header was sent.
    assert len(responses.calls) == 3
    assert responses.calls[0].request.headers["Authorization"] == "Bearer key"


@responses.activate
def test_pagination_stops_on_empty_page() -> None:
    champ = "CID"
    url = f"{DATA_API_BASE}/championships/{champ}/matches"
    responses.add(responses.GET, url, json={"items": [{"match_id": "1-x"} for _ in range(20)]}, status=200)
    responses.add(responses.GET, url, json={"items": []}, status=200)

    client, _ = make_client(api_key="key")
    got = list(client.iter_championship_matches(champ))
    assert len(got) == 20

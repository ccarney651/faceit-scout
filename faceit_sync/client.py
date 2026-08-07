"""HTTP client for FACEIT's public endpoints.

Politeness & robustness:
  * a single ``requests.Session`` (connection pooling, keep-alive),
  * a global rate limit (default 4 req/s),
  * 429 -> exponential backoff + jitter, honouring ``Retry-After``,
  * 5xx (incl. 503) -> retry with backoff.

User-Agent note: FACEIT's edge blocks browser-like UAs (``Mozilla/5.0`` -> 403)
but accepts a descriptive client UA. We therefore send an honest, descriptive
User-Agent and never impersonate a browser.

Endpoints (verified working logged-out, no auth on the internal three):
  * Data API (needs key):  https://open.faceit.com/data/v4/championships/{id}/matches
  * Match detail:          https://api.faceit.com/match/v2/match/{id}
  * Democracy (veto):      https://api.faceit.com/democracy/v1/match/{id}
  * Stats:                 https://api.faceit.com/stats/v1/stats/matches/{id}
                           (NB: the documented ``/stats/time/matches/{id}`` path 404s;
                            the working path has no ``/time`` segment.)
"""

from __future__ import annotations

import logging
import random
import time
from typing import Any, Callable, Iterator, Optional

import requests

log = logging.getLogger(__name__)

DEFAULT_USER_AGENT = "faceit-sync/0.1 (+https://github.com/local/faceit-sync)"

DATA_API_BASE = "https://open.faceit.com/data/v4"
# Keyless: lists a participant's matches in a championship (used to enumerate a
# whole league by unioning across its teams, without the Data API key).
CHAMP_MATCHES_URL = "https://api.faceit.com/championships/v1/matches"
MATCH_URL = "https://api.faceit.com/match/v2/match/{id}"
DEMOCRACY_URL = "https://api.faceit.com/democracy/v1/match/{id}"
STATS_URL = "https://api.faceit.com/stats/v1/stats/matches/{id}"

RETRYABLE_STATUS = frozenset({429, 500, 502, 503, 504})


class FaceitAPIError(RuntimeError):
    """Non-retryable API failure (or retries exhausted)."""

    def __init__(self, status: int, url: str, body: str = "") -> None:
        super().__init__(f"HTTP {status} for {url}: {body[:200]}")
        self.status = status
        self.url = url


class RateLimiter:
    """Simple global minimum-interval limiter, monotonic-clock based."""

    def __init__(
        self,
        rate_per_sec: float,
        *,
        sleep: Callable[[float], None] = time.sleep,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        self.min_interval = 1.0 / rate_per_sec if rate_per_sec > 0 else 0.0
        self._sleep = sleep
        self._monotonic = monotonic
        self._next_allowed = 0.0

    def acquire(self) -> None:
        now = self._monotonic()
        wait = self._next_allowed - now
        if wait > 0:
            self._sleep(wait)
            now = self._monotonic()
        self._next_allowed = max(now, self._next_allowed) + self.min_interval


class FaceitClient:
    def __init__(
        self,
        api_key: Optional[str] = None,
        *,
        rate_limit: float = 4.0,
        user_agent: str = DEFAULT_USER_AGENT,
        session: Optional[requests.Session] = None,
        max_retries: int = 5,
        backoff_base: float = 0.5,
        backoff_cap: float = 30.0,
        sleep: Callable[[float], None] = time.sleep,
        monotonic: Callable[[], float] = time.monotonic,
        rng: Optional[random.Random] = None,
    ) -> None:
        self.api_key = api_key
        self.max_retries = max_retries
        self.backoff_base = backoff_base
        self.backoff_cap = backoff_cap
        self._sleep = sleep
        self._rng = rng or random.Random()
        self._limiter = RateLimiter(rate_limit, sleep=sleep, monotonic=monotonic)

        self.session = session or requests.Session()
        self.session.headers.update(
            {"User-Agent": user_agent, "Accept": "application/json"}
        )

    # --- core request with retry/backoff -------------------------------------

    def _request(
        self, url: str, *, params: Optional[dict[str, Any]] = None, auth: bool = False
    ) -> requests.Response:
        headers: dict[str, str] = {}
        if auth:
            if not self.api_key:
                raise FaceitAPIError(
                    401, url, "FACEIT_API_KEY required for the Data API but not set"
                )
            headers["Authorization"] = f"Bearer {self.api_key}"

        attempt = 0
        while True:
            self._limiter.acquire()
            resp = self.session.get(url, params=params, headers=headers, timeout=30)
            if resp.status_code not in RETRYABLE_STATUS:
                return resp

            if attempt >= self.max_retries:
                raise FaceitAPIError(resp.status_code, url, resp.text)

            delay = self._retry_delay(resp, attempt)
            log.warning(
                "retryable HTTP %s for %s; backing off %.2fs (attempt %d/%d)",
                resp.status_code, url, delay, attempt + 1, self.max_retries,
            )
            self._sleep(delay)
            attempt += 1

    def _retry_delay(self, resp: requests.Response, attempt: int) -> float:
        retry_after = resp.headers.get("Retry-After")
        if retry_after is not None:
            try:
                return float(retry_after)
            except ValueError:
                pass  # HTTP-date form not expected from this API; fall through
        backoff = min(self.backoff_cap, self.backoff_base * (2 ** attempt))
        return backoff + self._rng.uniform(0.0, backoff)

    def _get_json(
        self, url: str, *, params: Optional[dict[str, Any]] = None, auth: bool = False
    ) -> Any:
        resp = self._request(url, params=params, auth=auth)
        if resp.status_code != 200:
            raise FaceitAPIError(resp.status_code, url, resp.text)
        return resp.json()

    # --- Data API: enumerate a championship's matches (needs key) ------------

    def iter_championship_matches(
        self, championship_id: str, *, page_size: int = 20
    ) -> Iterator[dict[str, Any]]:
        """Yield match summary dicts, paginating offset/limit to exhaustion.

        Falls back to the leaderboards-scoped path if the championship's matches
        endpoint 404s (unpublished championship).
        """
        base = f"{DATA_API_BASE}/championships/{championship_id}/matches"
        try:
            yield from self._paginate(base)
            return
        except FaceitAPIError as exc:
            if exc.status != 404:
                raise
            log.warning(
                "matches endpoint 404 for championship %s; trying leaderboards fallback",
                championship_id,
            )
        fallback = f"{DATA_API_BASE}/leaderboards/championships/{championship_id}/matches"
        yield from self._paginate(fallback)

    def iter_team_championship_matches(
        self, championship_id: str, team_id: str, *, page_size: int = 30
    ) -> Iterator[dict[str, Any]]:
        """Yield {match_id, status} for a team's past matches in a championship.

        Keyless (no Data API key). Enumerate a whole championship by unioning this
        across every team known to have played in it. Match id is at ``origin.id``.
        """
        offset = 0
        while True:
            payload = self._get_json(CHAMP_MATCHES_URL, params={
                "championshipId": championship_id, "participantType": "TEAM",
                "participantId": team_id, "type": "past",
                "limit": page_size, "offset": offset,
            })
            body = payload.get("payload", payload) if isinstance(payload, dict) else {}
            items = body.get("items", []) if isinstance(body, dict) else []
            if not items:
                return
            for it in items:
                mid = (it.get("origin") or {}).get("id")
                if mid:
                    yield {"match_id": mid, "status": it.get("status")}
            if len(items) < page_size:
                return
            offset += page_size

    def _paginate(self, url: str) -> Iterator[dict[str, Any]]:
        offset = 0
        page_size = 20
        while True:
            payload = self._get_json(
                url, params={"offset": offset, "limit": page_size}, auth=True
            )
            items = payload.get("items", []) if isinstance(payload, dict) else []
            if not items:
                return
            yield from items
            if len(items) < page_size:
                return
            offset += page_size

    # --- Internal detail endpoints (no key) ----------------------------------

    def get_match(self, match_id: str) -> dict[str, Any]:
        data = self._get_json(MATCH_URL.format(id=match_id))
        payload = data.get("payload", data)
        return payload if isinstance(payload, dict) else {}

    def get_democracy(self, match_id: str) -> Optional[dict[str, Any]]:
        """Return the veto (democracy) payload with ban attribution, or None.

        The live ``/democracy/v1/match/{id}`` feed is ephemeral (~7-day window),
        but ``/democracy/v1/match/{id}/history`` PERSISTS the same veto log — with
        per-drop ``selected_by`` (attribution) and ``round`` (order) — long after
        the live feed 404s. We therefore try ``/history`` first (durable) and fall
        back to the live endpoint, so attribution is recoverable for old matches.
        """
        base = DEMOCRACY_URL.format(id=match_id)
        for url in (f"{base}/history", base):
            resp = self._request(url)
            if resp.status_code == 404:
                continue
            if resp.status_code != 200:
                raise FaceitAPIError(resp.status_code, url, resp.text)
            payload = resp.json().get("payload", {})
            if isinstance(payload, dict) and payload.get("tickets"):
                return payload
        return None

    def get_stats(self, match_id: str) -> list[dict[str, Any]]:
        data = self._get_json(STATS_URL.format(id=match_id))
        return data if isinstance(data, list) else []

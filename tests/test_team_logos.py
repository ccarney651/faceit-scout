"""S7+S13: logo fetching is locked down — only https image URLs on FACEIT's
own CDN hosts are ever requested, non-image responses are rejected, downloads
are size-capped, and a single pooled Session (not a fresh request per logo) is
used so the export step can't be turned into an SSRF or a resource bomb."""

from __future__ import annotations

import base64

import responses

from faceit_sync.team_logos import (
    MAX_LOGO_BYTES,
    _fetch_one,
    _safe_logo_url,
)

CDN = "https://distribution.faceit-cdn.net/images/abc.jpg"

# A valid 1x1 transparent PNG (works whether or not Pillow is installed).
_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=="
)


def _register(body: bytes, content_type: str) -> None:
    responses.add(responses.GET, CDN, body=body, content_type=content_type)


def test_safe_logo_url_allows_only_https_faceit_cdn() -> None:
    assert _safe_logo_url(CDN)
    assert _safe_logo_url("https://assets.faceit-cdn.net/images/abc.jpg")
    # Scheme must be https...
    assert not _safe_logo_url("http://distribution.faceit-cdn.net/images/abc.jpg")
    # ...and the host must be FACEIT's CDN, not a lookalike or arbitrary host.
    assert not _safe_logo_url("https://distribution.faceit-cdn.net.evil.com/abc.jpg")
    assert not _safe_logo_url("https://example.com/abc.jpg")
    assert not _safe_logo_url("file:///etc/passwd")


@responses.activate
def test_fetch_one_inlines_fetched_image() -> None:
    _register(_PNG, "image/png")
    result = _fetch_one(CDN)
    assert result is not None
    assert result.startswith("data:image/")
    assert len(responses.calls) == 1


@responses.activate
def test_fetch_one_rejects_non_image_content_type() -> None:
    _register(b"<html>", "text/html")
    assert _fetch_one(CDN) is None


@responses.activate
def test_fetch_one_rejects_oversized_download() -> None:
    _register(b"x" * (MAX_LOGO_BYTES + 1), "image/png")
    assert _fetch_one(CDN) is None


@responses.activate
def test_fetch_one_refuses_non_cdn_url_without_request() -> None:
    """The URL guard must fail closed before any network call is made."""
    assert _fetch_one("https://example.com/abc.jpg") is None
    assert len(responses.calls) == 0


@responses.activate
def test_fetch_one_sends_descriptive_ua_via_pooled_session() -> None:
    """S13: fetches go through the module-level Session (connection pooling)
    carrying the honest faceit-sync UA, not a browser impersonation."""
    _register(_PNG, "image/png")
    assert _fetch_one(CDN) is not None
    req = responses.calls[0].request
    assert req.headers["User-Agent"].startswith("faceit-sync/")

"""Team logo inlining so the dashboard stays a single self-contained file.

The FACEIT API hands us CDN URLs for team avatars. The dashboard is shipped as
one HTML file that must render offline, so those URLs are fetched at export
time, downscaled, and embedded as data URIs. The result is cached in
``team_logos.json`` so local builds and CI produce the same file without
re-fetching every run.

Regenerate after a team changes its logo or a new team appears::

    python -m faceit_sync.team_logos
"""

from __future__ import annotations

import base64
import io
import json
import logging
from pathlib import Path
from typing import Mapping, Optional

import requests

log = logging.getLogger("faceit_sync.team_logos")

LOGO_CACHE = Path(__file__).with_name("team_logos.json")
# Rendered at the same size as match-card hero portraits (a little larger than
# the header icon) so the cached file stays small.
LOGO_PX = 64


def load_team_logos() -> dict[str, dict[str, str]]:
    """``{team_name: {url, data}}`` from the committed cache, or ``{}``."""
    if not LOGO_CACHE.is_file():
        log.info("no logo cache at %s - team logos will be fetched on demand", LOGO_CACHE)
        return {}
    try:
        with LOGO_CACHE.open(encoding="utf-8") as fh:
            logos = json.load(fh)
    except (OSError, ValueError) as exc:
        log.warning("logo cache unreadable (%s) - logos will be fetched on demand", exc)
        return {}
    return {str(k): dict(v) for k, v in logos.items() if isinstance(v, dict)}


def _fetch_one(url: str) -> str | None:
    try:
        resp = requests.get(url, timeout=30)
        resp.raise_for_status()
        data = resp.content
    except Exception as exc:  # noqa: BLE001 - network/asset failure is not fatal
        log.warning("could not fetch logo %s: %s", url, exc)
        return None
    try:
        from PIL import Image
    except ImportError:
        # Pillow absent: just inline the raw bytes as a generic data URI.
        mime = "image/jpeg" if url.lower().endswith((".jpg", ".jpeg")) else "image/png"
        b64 = base64.b64encode(data).decode("ascii")
        return f"data:{mime};base64,{b64}"

    try:
        with Image.open(io.BytesIO(data)) as src:
            im = src.convert("RGBA")
            im.thumbnail((LOGO_PX, LOGO_PX), getattr(getattr(Image, "Resampling", Image), "LANCZOS"))
            buf = io.BytesIO()
            im.save(buf, format="WEBP", quality=82, method=6)
            b64 = base64.b64encode(buf.getvalue()).decode("ascii")
        return f"data:image/webp;base64,{b64}"
    except Exception as exc:  # noqa: BLE001
        log.warning("could not process logo %s: %s", url, exc)
        return None


def build_team_logos(urls: Mapping[str, Optional[str]]) -> dict[str, str]:
    """Fetch and inline any team logos not already in the cache.

    Returns ``{team_name: data-URI}`` (cached + freshly fetched). Network or
    processing failures leave that team's logo out rather than breaking the build.
    """
    cache = load_team_logos()
    needed = {name: url for name, url in urls.items()
              if url and cache.get(name, {}).get("url") != url}
    if not needed:
        return {name: entry["data"] for name, entry in cache.items()}

    fetched = 0
    for name, url in needed.items():
        data_uri = _fetch_one(url)
        if data_uri:
            cache[name] = {"url": url, "data": data_uri}
            fetched += 1

    log.info("fetched %d new team logo(s) (%d already cached)", fetched, len(urls) - fetched)
    # Persist the cache so the next build is fast and identical.
    try:
        with LOGO_CACHE.open("w", encoding="utf-8") as fh:
            json.dump(cache, fh, indent=0, sort_keys=True)
    except OSError as exc:
        log.warning("could not write logo cache: %s", exc)
    return {name: entry["data"] for name, entry in cache.items()}


def _main() -> int:  # pragma: no cover - operator tool
    """Regenerate the committed logo cache from the local DB."""
    import sqlite3
    import sys

    db_path = sys.argv[1] if len(sys.argv) > 1 else "faceit.sqlite3"
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    rows = conn.execute("SELECT name, avatar_url FROM teams WHERE avatar_url IS NOT NULL").fetchall()
    urls = {r["name"]: r["avatar_url"] for r in rows}
    if not urls:
        print("no team logos to fetch")
        return 1
    logos = build_team_logos(urls)
    kb = LOGO_CACHE.stat().st_size / 1024 if LOGO_CACHE.is_file() else 0
    print(f"wrote {LOGO_CACHE.name}: {len(logos)} logos, {kb:.0f} KB")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(_main())

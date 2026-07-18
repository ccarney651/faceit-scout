"""Hero portrait icons, downscaled and inlined into the dashboard.

A comp read as five hero *names* is five words you have to parse; read as five
portraits it is recognisable at a glance — which is how scouting pages elsewhere
present compositions. The source art is far too large to inline (~130 KB each), so
it is downscaled and embedded as data URIs, keeping the dashboard a single
self-contained file with no external requests.

The downscaled result is COMMITTED as :data:`ICON_CACHE` (~96 KB of WebP) and is
the single source of truth for every build. The 22 MB of source PNGs cannot go in
the repo, so a build that reads them directly — as CI does — would silently render
a portrait-less page while the operator's machine rendered portraits. Loading the
cache everywhere means local and CI produce the identical dashboard.

Regenerate after adding a hero::

    python -m faceit_sync.hero_icons overwatch-hero-icons/normal
"""

from __future__ import annotations

import base64
import io
import json
import logging
import os
import re
from pathlib import Path

log = logging.getLogger("faceit_sync.hero_icons")

DEFAULT_ICON_DIR = "overwatch-hero-icons/normal"
# Committed alongside the code so every build - local, CI, packaged - inlines the
# same portraits without needing the source art.
ICON_CACHE = Path(__file__).with_name("hero_icons.json")
# Rendered at ~28px; 44 gives a crisp result on HiDPI without bloating the page.
ICON_PX = 44


def slug(name: str) -> str:
    """Hero name -> asset key ('D.Va' / 'Wrecking Ball' -> 'dva' / 'wreckingball')."""
    return re.sub(r"[^a-z0-9]", "", name.lower())


def load_hero_icons() -> dict[str, str]:
    """``{hero_slug: data-URI}`` from the committed cache, or ``{}`` if it is
    missing or unreadable (the dashboard then falls back to text chips)."""
    if not ICON_CACHE.is_file():
        log.info("no icon cache at %s - dashboard will use text chips", ICON_CACHE)
        return {}
    try:
        with ICON_CACHE.open(encoding="utf-8") as fh:
            icons = json.load(fh)
    except (OSError, ValueError) as exc:
        log.warning("icon cache unreadable (%s) - dashboard will use text chips", exc)
        return {}
    log.info("loaded %d hero icons from %s", len(icons), ICON_CACHE.name)
    return {str(k): str(v) for k, v in icons.items()}


def build_hero_icons(
    icon_dir: str | os.PathLike[str] | None = None, size: int = ICON_PX
) -> dict[str, str]:
    """``{hero_slug: data-URI}`` built fresh from the source PNGs, or ``{}`` if the
    assets (or Pillow) are unavailable. Set $FACEIT_HERO_ICONS to override the
    folder. This is the regeneration path — readers want :func:`load_hero_icons`."""
    root = Path(icon_dir or os.environ.get("FACEIT_HERO_ICONS", DEFAULT_ICON_DIR))
    if not root.is_dir():
        log.info("hero icons not found at %s - dashboard will use text chips", root)
        return {}
    try:
        from PIL import Image
    except ImportError:
        log.info("Pillow not installed - dashboard will use text chips")
        return {}

    out: dict[str, str] = {}
    for path in sorted(root.glob("*.png")):
        # Pillow moved the resampling enum in 9.1; support both.
        lanczos = getattr(getattr(Image, "Resampling", Image), "LANCZOS")
        try:
            with Image.open(path) as src:
                im = src.convert("RGBA")
                im.thumbnail((size, size), lanczos)
                buf = io.BytesIO()
                # WebP is a fraction of PNG at this size and is universally
                # supported by browsers new enough for the rest of this page.
                im.save(buf, format="WEBP", quality=82, method=6)
            b64 = base64.b64encode(buf.getvalue()).decode("ascii")
            out[slug(path.stem)] = f"data:image/webp;base64,{b64}"
        except Exception as exc:  # noqa: BLE001 - a bad asset must not break the build
            log.warning("skipping hero icon %s: %s", path.name, exc)
    log.info("inlined %d hero icons from %s", len(out), root)
    return out


def _main() -> int:  # pragma: no cover - operator tool
    """Rebuild the committed icon cache from the source PNGs."""
    import sys
    icons = build_hero_icons(sys.argv[1] if len(sys.argv) > 1 else None)
    if not icons:
        print("no icons built - check the asset folder and that Pillow is installed")
        return 1
    with ICON_CACHE.open("w", encoding="utf-8") as fh:
        json.dump(icons, fh, indent=0, sort_keys=True)
    kb = ICON_CACHE.stat().st_size / 1024
    print(f"wrote {ICON_CACHE.name}: {len(icons)} icons, {kb:.0f} KB")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(_main())

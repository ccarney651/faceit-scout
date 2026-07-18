"""Hero portrait icons, downscaled and inlined into the dashboard.

A comp read as five hero *names* is five words you have to parse; read as five
portraits it is recognisable at a glance — which is how scouting pages elsewhere
present compositions. The source art is far too large to inline (~130 KB each), so
it is downscaled once at build time and embedded as data URIs, keeping the
dashboard a single self-contained file with no external requests.

Assets are optional: if the folder or Pillow is missing this returns ``{}`` and
the dashboard falls back to text chips.
"""

from __future__ import annotations

import base64
import io
import logging
import os
import re
from pathlib import Path

log = logging.getLogger("faceit_sync.hero_icons")

DEFAULT_ICON_DIR = "overwatch-hero-icons/normal"
# Rendered at ~28px; 44 gives a crisp result on HiDPI without bloating the page.
ICON_PX = 44


def slug(name: str) -> str:
    """Hero name -> asset key ('D.Va' / 'Wrecking Ball' -> 'dva' / 'wreckingball')."""
    return re.sub(r"[^a-z0-9]", "", name.lower())


def load_hero_icons(
    icon_dir: str | os.PathLike[str] | None = None, size: int = ICON_PX
) -> dict[str, str]:
    """``{hero_slug: data-URI}`` for every portrait found, or ``{}`` if the assets
    (or Pillow) are unavailable. Set $FACEIT_HERO_ICONS to override the folder."""
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

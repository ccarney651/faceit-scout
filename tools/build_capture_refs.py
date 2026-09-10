"""Emit docs/capture/refs.json — the trained HUD hero library for the browser
capture app. Curator-run locally (needs owdb.sqlite3 with a trained profile);
commit the output. The browser app fetches it same-origin.

    .venv/Scripts/python tools/build_capture_refs.py

Each ref = a grayscale face crop resized to REF_W x REF_H, base64-encoded, with
its hero name and team variant ('a'=left/blue, 'b'=right/red). Mirrors the
desktop matcher's inputs so recognition behaves the same in the browser.

Both the ALIVE and the DEAD portrait are emitted, under the same variant. The
engine matcher (docs/capture/engine/refs.js `bestMatch`) scores a crop against
every ref sharing its variant and keeps the best, so a dimmed/eliminated replay
portrait matches its dead exemplar instead of drifting onto another hero. The
entry shape is unchanged ({n,g,v,d}) — a hero just contributes up to two per
side.
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import sqlite3
from collections.abc import Callable, Iterable

OWDB_DB = "owdb.sqlite3"
FACEIT_DB = "faceit.sqlite3"
REF_W, REF_H = 64, 36
OUT = os.path.join("docs", "capture", "refs.json")

# (hero_guid, variant, state, image_path)
RefRow = tuple[str, str, str, str]


def hero_names() -> dict[str, str]:
    names: dict[str, str] = {}
    with sqlite3.connect(FACEIT_DB) as f:
        for guid, name in f.execute("SELECT guid, name FROM heroes"):
            names[guid] = name
    try:
        with sqlite3.connect(OWDB_DB) as o:
            for guid, name in o.execute("SELECT guid, name FROM custom_heroes"):
                names[guid] = name
    except sqlite3.Error:
        pass
    return names


def active_profile_id(conn: sqlite3.Connection, hud_variant: str = "default") -> int:
    """The newest un-retired ROI profile for a HUD variant — the one `owdb
    calibrate` last wrote and everything else reads. Hardcoding an id (this was
    `PROFILE_ID = 4`) silently rebuilds from a retired profile after a
    recalibration."""
    row = conn.execute(
        "SELECT id FROM roi_profiles WHERE hud_variant=? AND retired_at IS NULL "
        "ORDER BY id DESC LIMIT 1",
        (hud_variant,),
    ).fetchone()
    if row is None:
        raise SystemExit(f"no active '{hud_variant}' profile — run `owdb calibrate`")
    return int(row[0])


def select_ref_rows(conn: sqlite3.Connection, profile_id: int) -> list[RefRow]:
    """Every ref for a profile — both alive and dead states, and both the
    canonical `capture` refs and any additive `review` exemplars. The engine
    matcher keeps the best score across all of a hero's refs, so more is fine."""
    return list(
        conn.execute(
            "SELECT hero_guid, variant, state, image_path FROM hero_refs "
            "WHERE profile_id=?",
            (profile_id,),
        )
    )


def ref_entries(
    rows: Iterable[RefRow],
    names: dict[str, str],
    load_small: Callable[[str], bytes | None],
) -> list[dict[str, str]]:
    """Turn DB ref rows into refs.json entries. `load_small` returns the
    REF_W*REF_H grayscale bytes for an image path, or None if it can't be read —
    those rows are dropped."""
    entries: list[dict[str, str]] = []
    for guid, variant, _state, path in rows:
        if not path:
            continue
        small = load_small(path)
        if small is None:
            continue
        entries.append({
            "n": names.get(guid, guid[:6]),
            "g": guid,                          # hero GUID — the contribution format uses guids
            "v": variant,
            "d": base64.b64encode(bytes(small)).decode("ascii"),
        })
    return entries


def _cv2_loader() -> Callable[[str], bytes | None]:
    import cv2

    def load(path: str) -> bytes | None:
        if not os.path.exists(path):
            return None
        img = cv2.imread(path, cv2.IMREAD_GRAYSCALE)
        if img is None:
            return None
        small = cv2.resize(img, (REF_W, REF_H), interpolation=cv2.INTER_AREA)
        return small.tobytes()

    return load


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--profile", type=int, default=None,
                    help="ROI profile id (default: the active 'default' profile)")
    args = ap.parse_args()

    names = hero_names()
    with sqlite3.connect(OWDB_DB) as c:
        pid = args.profile if args.profile is not None else active_profile_id(c)
        rows = select_ref_rows(c, pid)
    refs = ref_entries(rows, names, _cv2_loader())
    if not refs:
        raise SystemExit(f"no refs for profile {pid} — is owdb.sqlite3 trained?")
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    payload = {"w": REF_W, "h": REF_H, "left_fraction": 0.42, "top_fraction": 0.45, "refs": refs}
    with open(OUT, "w", encoding="utf-8") as fh:
        json.dump(payload, fh)
    a = sum(1 for r in refs if r["v"] == "a")
    b = sum(1 for r in refs if r["v"] == "b")
    print(f"wrote {OUT} from profile {pid}  "
          f"({len(refs)} refs: {a} blue + {b} red, {os.path.getsize(OUT)//1024} KB)")


if __name__ == "__main__":
    main()

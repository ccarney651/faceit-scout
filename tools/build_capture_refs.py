"""Emit docs/capture/refs.json — the trained HUD hero library for the browser
capture app. Curator-run locally (needs owscout.sqlite3 with a trained profile);
commit the output. The browser app fetches it same-origin.

    .venv/Scripts/python tools/build_capture_refs.py

Each ref = a grayscale face crop resized to REF_W x REF_H, base64-encoded, with
its hero name and team variant ('a'=left/blue, 'b'=right/red). Mirrors the
desktop matcher's inputs so recognition behaves the same in the browser.
"""
from __future__ import annotations

import base64
import json
import os
import sqlite3

import cv2

OWSCOUT_DB = "owscout.sqlite3"
FACEIT_DB = "faceit.sqlite3"
PROFILE_ID = 4
REF_W, REF_H = 64, 36
OUT = os.path.join("docs", "capture", "refs.json")


def hero_names() -> dict[str, str]:
    names: dict[str, str] = {}
    with sqlite3.connect(FACEIT_DB) as f:
        for guid, name in f.execute("SELECT guid, name FROM heroes"):
            names[guid] = name
    try:
        with sqlite3.connect(OWSCOUT_DB) as o:
            for guid, name in o.execute("SELECT guid, name FROM custom_heroes"):
                names[guid] = name
    except sqlite3.Error:
        pass
    return names


def main() -> None:
    names = hero_names()
    refs: list[dict[str, str]] = []
    with sqlite3.connect(OWSCOUT_DB) as c:
        rows = c.execute(
            "SELECT hero_guid, variant, image_path FROM hero_refs "
            "WHERE profile_id=? AND state='alive'",
            (PROFILE_ID,),
        ).fetchall()
    for guid, variant, path in rows:
        if not path or not os.path.exists(path):
            continue
        img = cv2.imread(path, cv2.IMREAD_GRAYSCALE)
        if img is None:
            continue
        small = cv2.resize(img, (REF_W, REF_H), interpolation=cv2.INTER_AREA)
        refs.append({
            "n": names.get(guid, guid[:6]),
            "g": guid,                          # hero GUID — the contribution format uses guids
            "v": variant,
            "d": base64.b64encode(small.tobytes()).decode("ascii"),
        })
    if not refs:
        raise SystemExit("no profile refs found — is owscout.sqlite3 trained?")
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    payload = {"w": REF_W, "h": REF_H, "left_fraction": 0.42, "top_fraction": 0.45, "refs": refs}
    with open(OUT, "w", encoding="utf-8") as fh:
        json.dump(payload, fh)
    a = sum(1 for r in refs if r["v"] == "a")
    b = sum(1 for r in refs if r["v"] == "b")
    print(f"wrote {OUT}  ({len(refs)} refs: {a} blue + {b} red, {os.path.getsize(OUT)//1024} KB)")


if __name__ == "__main__":
    main()

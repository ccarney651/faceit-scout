"""THROWAWAY diagnostic — see exactly what the refs trainer's --auto crop grabs.

Run it while the refs_trainer workshop code is running and you are spectating,
with bots on both teams (alive). It grabs one frame and writes, under
``refs_diag/``:

  frame.png            the raw grab
  overlay.png          the active profile's 10 slot cells (red) + the face_subrect
                       the matcher/ref-capture actually uses (green)
  faces.png            those 10 face crops, 6x zoom, labelled — this is what a
                       ref would look like

Look at faces.png: each tile should be JUST the hero's face — no "0%" ult badge
top-left, no name-plate text along the bottom. If the green boxes in overlay.png
are shifted off the portraits, the active profile needs recalibrating for this
lobby; if they're on the portraits but still catch the badge/name, the
face_subrect fractions need tightening.

    .venv/Scripts/python tools/diag_refs_crop.py [--from frame.png] [--profile N]
"""
from __future__ import annotations

import argparse
from pathlib import Path

import cv2

from owdb.db import Database
from owdb.match import (
    PORTRAIT_TOP_FRACTION,
    ULT_OVERLAY_LEFT_FRACTION,
    face_subrect,
)
from owdb.models import Rect

OUT = Path("refs_diag")


def _crop(frame, r: Rect):
    return frame[r.y : r.y + r.h, r.x : r.x + r.w]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--from", dest="src", help="annotate this PNG instead of grabbing")
    ap.add_argument("--db", default="owdb.sqlite3")
    ap.add_argument("--profile", type=int, default=None, help="profile id (default: active)")
    ap.add_argument("--left", type=float, default=ULT_OVERLAY_LEFT_FRACTION)
    ap.add_argument("--top", type=float, default=PORTRAIT_TOP_FRACTION)
    args = ap.parse_args()

    OUT.mkdir(exist_ok=True)

    if args.src:
        frame = cv2.imread(args.src)
        if frame is None:
            raise SystemExit(f"could not read {args.src}")
        h, w = frame.shape[:2]
    else:
        from owdb import capture

        frame, w, h = capture.grab_frame()
        cv2.imwrite(str(OUT / "frame.png"), frame)
    print(f"frame {w}x{h}")

    with Database(args.db) as db:
        if args.profile is not None:
            row = db.conn.execute(
                "SELECT * FROM roi_profiles WHERE id=?", (args.profile,)
            ).fetchone()
            profile = db._row_to_profile(row)
        else:
            profile = db.get_active_profile(w, h, "default") or db.latest_active_profile("default")
    if profile is None:
        raise SystemExit("no profile")
    print(f"profile #{profile.id}  {profile.resolution_w}x{profile.resolution_h}  "
          f"left={args.left} top={args.top}")

    overlay = frame.copy()
    tiles = []
    for side in ("a", "b"):
        for i, cell in enumerate(profile.slots[side]):
            face = face_subrect(cell, args.left, args.top)
            cv2.rectangle(overlay, (cell.x, cell.y),
                          (cell.x + cell.w, cell.y + cell.h), (0, 0, 255), 1)
            cv2.rectangle(overlay, (face.x, face.y),
                          (face.x + face.w, face.y + face.h), (0, 255, 0), 2)
            crop = _crop(frame, face)
            if crop.size:
                big = cv2.resize(crop, (face.w * 6, face.h * 6), interpolation=cv2.INTER_NEAREST)
                cv2.putText(big, f"{side}{i}", (4, 20), cv2.FONT_HERSHEY_SIMPLEX,
                            0.6, (0, 255, 255), 2)
                tiles.append(big)

    cv2.imwrite(str(OUT / "overlay.png"), overlay)

    if tiles:
        tw = max(t.shape[1] for t in tiles) + 8
        th = max(t.shape[0] for t in tiles) + 8
        rows = []
        for r in range(0, len(tiles), 5):
            band = [cv2.resize(cv2.copyMakeBorder(t, 4, 4, 4, 4, cv2.BORDER_CONSTANT,
                                                  value=(30, 30, 30)), (tw, th))
                    for t in tiles[r : r + 5]]
            rows.append(cv2.hconcat(band))
        cv2.imwrite(str(OUT / "faces.png"), cv2.vconcat(rows))

    print(f"wrote {OUT}/overlay.png and {OUT}/faces.png")


if __name__ == "__main__":
    main()

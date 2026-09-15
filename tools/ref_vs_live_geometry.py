"""Compare the geometry the refs were baked from (roi_profiles id 7 'replay')
against the geometry the replay bot crops with (calib.js FROZEN), using
owdb.match.face_subrect for the ref side and the same fractions for the live
side.
"""
import json
import sqlite3

LF = 0.42
TF = 0.45
RF = 0.06

conn = sqlite3.connect("owdb.sqlite3")
row = conn.execute("SELECT slots_json FROM roi_profiles WHERE id=7").fetchone()
slots = json.loads(row[0])
conn.close()

# calib.js FROZEN
FROZEN = {
    "a": {"x": 55.33490566037736, "y": 98, "w": 706.25, "h": 103.97607478673905},
    "b": {"x": 1799.3349056603774, "y": 95, "w": 706.25, "h": 108.85047245433347},
}


def ref_rect(cell):
    """owdb face_subrect: integer cut from the profile slot rect."""
    x, y, w, h = cell
    cut = round(w * LF)
    right_cut = round(w * RF)
    height = round(h * TF)
    return x + cut, y, w - cut - right_cut, height


def live_rect(side, i):
    """replay_bot calib.cells(side): float cut from the FROZEN box."""
    b = FROZEN[side]
    cw = b["w"] / 5
    return b["x"] + i * cw + cw * LF, b["y"], cw * (1 - LF - RF), b["h"] * TF


print("side  slot   ref x   live x   delta x")
for side in ("a", "b"):
    for i in range(5):
        rx, _, rw, rh = ref_rect(slots[side][i])
        lx, _, lw, lh = live_rect(side, i)
        print(f"  {side}     {i}   {rx:6.1f}  {lx:7.2f}  {rx - lx:+6.2f}   "
              f"ref {rw}x{rh}  live {lw:.1f}x{lh:.1f}")
    print()

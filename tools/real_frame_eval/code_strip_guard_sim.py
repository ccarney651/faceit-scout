"""Would reading at several GEOMETRIES, not just several contrasts, catch it?

The shipped rule runs three contrast levels and accepts only when the passes
agree. `code_strip_tolerance.py` shows that guard does not hold when the strip
itself is wrong: a shifted crop shifts identically under every contrast, so all
three passes agree on the same wrong code. Agreement was designed against
per-pass noise, and a geometry error is not noise.

A geometry error is, however, exactly what a second geometry exposes. This
simulates the candidate rule - read at strip offsets {-d, 0, +d}, each still a
contrast ladder, and accept only if all three agree - against the measured read
table, so no tesseract is needed to try a value of d.

Read as: for a scout whose strip is off by `e`, what does the rule do?
"""
import json
import pathlib
import sys

TAGS = {
    'dx': lambda v: f"dx{v:+.2f}",
    'dy': lambda v: f"dy{v:+.2f}",
    'scale': lambda v: f"scale{1 + v:.2f}",
}
GRID = [round(i / 100, 2) for i in range(-5, 6)]


def load(dir_):
    return json.loads((pathlib.Path(dir_) / 'reads.json').read_text(encoding='utf-8'))


def read_at(table, frame, axis, off):
    """The shipped ladder's answer at this absolute strip error, or None."""
    entry = table[frame].get(TAGS[axis](round(off, 2)))
    return entry['got'] if entry else '__missing__'


def simulate(table, axis, delta):
    """rows: (e, accepted-correct, accepted-WRONG, refused) over all frames."""
    rows = []
    for e in GRID:
        good = bad = refused = 0
        for frame in table:
            want = next(iter(table[frame].values()))['want']
            probes = [read_at(table, frame, axis, e + d) for d in (-delta, 0.0, delta)]
            if any(p == '__missing__' for p in probes):
                continue
            got = probes[0] if (probes[0] is not None and probes[0] == probes[1] == probes[2]) else None
            if got is None:
                refused += 1
            elif got == want:
                good += 1
            else:
                bad += 1
        rows.append((e, good, bad, refused))
    return rows


def shipped(table, axis):
    rows = []
    for e in GRID:
        good = bad = refused = 0
        for frame in table:
            want = next(iter(table[frame].values()))['want']
            got = read_at(table, frame, axis, e)
            if got == '__missing__':
                continue
            if got is None:
                refused += 1
            elif got == want:
                good += 1
            else:
                bad += 1
        rows.append((e, good, bad, refused))
    return rows


def show(title, rows):
    print(f"\n{title}")
    print("  strip error   correct  WRONG  refused")
    for e, good, bad, refused in rows:
        if good + bad + refused == 0:
            # A probe fell outside the rendered grid, so every frame was
            # skipped. Said explicitly: three zeros here would otherwise read
            # as a perfect score at the widest error measured.
            print(f"  {e:+.2f}        (probe outside the grid - not evaluated)")
            continue
        flag = '  <-- accepts a wrong code' if bad else ''
        print(f"  {e:+.2f}        {good:7} {bad:6} {refused:8}{flag}")


if __name__ == '__main__':
    d = sys.argv[1] if len(sys.argv) > 1 else 'code_strip_crops'
    table = load(d)
    delta = float(sys.argv[2]) if len(sys.argv) > 2 else 0.01
    for axis in ('dx', 'dy', 'scale'):
        show(f"{axis}: SHIPPED (contrast ladder only)", shipped(table, axis))
        show(f"{axis}: CANDIDATE (geometry probes +/-{delta:.2f}, each a ladder)",
             simulate(table, axis, delta))

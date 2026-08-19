"""Does the geometry-probe guard hold when the error is NOT on the probed axis?

code_strip_guard_sim.py probed the same axis the error was on - a dx probe
against a dx error. That is the easy case, and shipping on it would repeat the
exact mistake this work uncovered: believing a guard because it was only ever
tested where it obviously works. The scout's strip can be wrong in x, in y, in
size, or in all three, and the guard does not get told which.

So the probes here are the ones a page would actually run: three fixed offsets
that differ from each other on EVERY axis at once, applied blind. Each probe is
still a full contrast ladder; the code is accepted only when all three probes
return the same one.

Error cases are the ones where the shipped rule was measured returning a WRONG
code, plus the unperturbed case to price the guard when nothing is wrong.

  python tools/real_frame_eval/code_strip_guard_check.py code_guard_crops
  node tools/real_frame_eval/code_strip_tolerance.js code_guard_crops
  python tools/real_frame_eval/code_strip_guard_check.py --score code_guard_crops
"""
import json
import pathlib
import shutil
import sys

from PIL import Image

sys.path.insert(0, 'tools/real_frame_eval')
from code_crop import offsets, stem_of
from code_strip_tolerance import perturb, render_one
from code_truth import CODES, strip_a

# The candidate rule, exactly as a page would run it. ONE AXIS PER PROBE.
#
# The first attempt moved all three axes at once, and it failed in both
# directions: the compound probe displaced further than any single axis, so it
# refused 3 of 12 reads on a perfectly good strip, while its 1% of strip
# HEIGHT was about one pixel - too small to disturb a vertically clipped crop,
# which let two wrong codes through (H6R64B read as HARAAR at dy -5%).
#
# So each probe moves one axis, and dy moves further than dx because a strip
# is ~7x wider than it is tall and the probe has to be worth pixels, not
# percent. +/-2% on dy scores zero wrong against the per-axis table where
# +/-1% did not, and +/-3% refuses half of all good reads.
PROBES = [
    ('p0', dict()),                  # the scout's own strip
    ('p1', dict(dx=-0.01)),
    ('p2', dict(dx=+0.01)),
    ('p3', dict(dy=-0.02)),
    ('p4', dict(dy=+0.02)),
]

ERRORS = [('none', {})]
for v in (-0.04, 0.03):
    ERRORS.append((f"dx{v:+.2f}", dict(dx=v)))
for v in (-0.05, -0.03, 0.03):
    ERRORS.append((f"dy{v:+.2f}", dict(dy=v)))
for v in (0.97, 1.05):
    ERRORS.append((f"scale{v:.2f}", dict(scale=v)))


def combine(a, err, probe):
    """Apply the scout's error, then the page's blind probe on top of it."""
    return perturb(perturb(a, **{'scale': 1.0, 'dx': 0.0, 'dy': 0.0, **err}),
                   **{'scale': 1.0, 'dx': 0.0, 'dy': 0.0, **probe})


def render(dest: pathlib.Path) -> None:
    if dest.exists():
        shutil.rmtree(dest)
    dest.mkdir(parents=True)
    o, manifest, n = offsets(), {}, 0
    for f in sorted(pathlib.Path('screenshots').glob('*.png')):
        stem = stem_of(f)
        if stem not in CODES:
            continue
        img = Image.open(f).convert('RGB')
        a = strip_a(img.size)
        if a is None:
            continue
        for etag, err in ERRORS:
            for ptag, probe in PROBES:
                n += render_one(img, combine(a, err, probe), dest, stem, f"{etag}-{ptag}", o)
        manifest[stem] = CODES[stem]
    (dest / 'manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    print(f"rendered {n} crop sets over {len(manifest)} frames, "
          f"{len(ERRORS)} error cases x {len(PROBES)} probes")


def score(dest: pathlib.Path) -> None:
    table = json.loads((dest / 'reads.json').read_text(encoding='utf-8'))
    print("scout's strip error   guard: correct  WRONG  refused    (shipped rule for comparison)")
    for etag, _ in ERRORS:
        good = bad = refused = 0
        s_good = s_bad = s_ref = 0
        for frame, tags in table.items():
            want = next(iter(tags.values()))['want']
            reads = [tags.get(f"{etag}-{p}", {}).get('got', '__missing__') for p, _ in PROBES]
            if any(r == '__missing__' for r in reads):
                continue
            # The shipped rule is probe p0 alone: the contrast ladder at the
            # scout's own strip, with no second geometry.
            centre = reads[0]
            if centre is None:
                s_ref += 1
            elif centre == want:
                s_good += 1
            else:
                s_bad += 1
            got = reads[0] if (reads[0] is not None and all(r == reads[0] for r in reads)) else None
            if got is None:
                refused += 1
            elif got == want:
                good += 1
            else:
                bad += 1
        flag = '  <-- GUARD LET A WRONG CODE THROUGH' if bad else ''
        print(f"  {etag:<18} {good:7} {bad:6} {refused:8}     "
              f"({s_good} ok / {s_bad} wrong / {s_ref} refused){flag}")


if __name__ == '__main__':
    args = [a for a in sys.argv[1:] if a != '--score']
    d = pathlib.Path(args[0] if args else 'code_guard_crops')
    if '--score' in sys.argv:
        score(d)
    else:
        render(d)

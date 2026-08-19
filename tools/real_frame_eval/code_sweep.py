"""Fit the code-crop offsets across every ground-truth frame.

Scored on REAL OCR OUTPUT, not on an ink proxy. The plan called for an ink-based
score for speed, on the assumption that a full OCR sweep would be too slow - but
the frame set is twelve images, so scoring on the thing we actually care about
(does the read come back as the known code) is affordable and is strictly better
evidence than a stand-in for it.

That matters here because the failure mode the first eval found is invisible to
an ink score: the crops LOOK clean, and tesseract invents a leading character out
of the mottled plate edge anyway. A geometry score would have called those boxes
good.

Renders every candidate first (cheap), then hands the whole lot to one node
process that reuses a single tesseract worker (the expensive part is worker
startup, not recognition).

Ranking: most correct wins, and ANY wrong read disqualifies a candidate outright
regardless of how many it gets right. A wrong code is a corrupted record.
"""
import glob
import itertools
import json
import pathlib
import shutil
import subprocess
import sys

sys.path.insert(0, 'tools/real_frame_eval')
from code_crop import DEFAULTS, render
from code_truth import CODES

WORK = pathlib.Path('code_sweep_work')

# The first eval's failures were all a spurious character at the crop EDGE, so
# the levers are how wide the box is and how much margin it carries. Vertical
# placement was already landing the text band centred on every frame.
GRID = {
    'PAD': [0.10, 0.18, 0.26],
    'DW': [0.139, 0.151, 0.163],
    'DX': [1.063, 1.073, 1.083],
    'DY': [-0.563, -0.543, -0.523],
    'DH': [0.217, 0.237, 0.257],
}

# Only frames whose HUD sits where auto-calibrate expects it can constrain
# offsets expressed against auto-calibrate's box - see code_truth.STRIPS.
FIT_SIZES = {(2559, 1439)}


def candidates():
    keys = sorted(GRID)
    for combo in itertools.product(*(GRID[k] for k in keys)):
        o = dict(DEFAULTS)
        o.update(dict(zip(keys, combo)))
        yield o


def main():
    if WORK.exists():
        shutil.rmtree(WORK)
    WORK.mkdir()
    frames = [f for f in sorted(glob.glob('screenshots/*.png'))]
    index = []
    for i, o in enumerate(candidates()):
        d = WORK / f'c{i:03d}'
        n = 0
        for f in frames:
            from PIL import Image
            if Image.open(f).size not in FIT_SIZES:
                continue
            if render(f, d, o):
                n += 1
        if n:
            index.append({'dir': str(d).replace('\\', '/'), 'offsets': o})
    (WORK / 'index.json').write_text(json.dumps(index, indent=2), encoding='utf-8')
    print(f'rendered {len(index)} candidates x {len(CODES)} frames')

    proc = subprocess.run(
        ['node', 'tools/real_frame_eval/code_sweep_score.js', str(WORK / 'index.json')],
        capture_output=True, text=True, encoding='utf-8')
    print(proc.stdout)
    if proc.returncode != 0:
        print(proc.stderr)
        sys.exit(1)

    results = json.loads((WORK / 'results.json').read_text(encoding='utf-8'))
    clean = [r for r in results if r['wrong'] == 0]
    print(f'{len(clean)} of {len(results)} candidates had zero wrong reads')
    if not clean:
        print('NO CANDIDATE IS SAFE - every one produced a wrong read. Stop and rethink.')
        sys.exit(1)
    clean.sort(key=lambda r: (-r['correct'], r['offsets']['PAD']))
    best = clean[0]
    print('\ntop 5 (correct / no-read / offsets):')
    for r in clean[:5]:
        print(f"  {r['correct']:2d} / {r['none']:2d}  {r['offsets']}")

    # Robustness: how many of the top score's neighbours also reach it. A single
    # winning cell in a field of losers is a fit that will not survive a HUD this
    # set does not contain.
    peak = best['correct']
    at_peak = [r for r in clean if r['correct'] == peak]
    print(f'\n{len(at_peak)} of {len(clean)} safe candidates reach the top score of {peak}')
    for k in ('PAD', 'DW', 'DX'):
        vs = sorted({r['offsets'][k] for r in at_peak})
        print(f'  {k}: works across {vs}')

    pathlib.Path('tools/real_frame_eval/code_offsets.json').write_text(
        json.dumps(best['offsets'], indent=2), encoding='utf-8')
    print('\nwrote code_offsets.json', best['offsets'])


if __name__ == '__main__':
    main()

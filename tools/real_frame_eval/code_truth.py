"""Frame -> replay code, and the calibrated TEAM 1 strip per frame size.

The 2557x1438 codes are lifted from gen_truth.py, where they were hand-verified
because the name-attribution eval needed each frame's code to resolve its
lineup. There they were incidental context; here they are the thing under test.

The 2026-08-18 codes were read off the frames by eye for this work. All three
differ - D9X9N2, 9962X3, G84XPD - so the obvious assumption that frames from one
session share a code is wrong, and a wrong truth entry would make a correct
reader look broken.

Two of those three are LIVE custom games (ScrimTime Lite), not replays, and the
code sits in the same HUD slot in both cases. That is worth keeping in the set:
it shows the locator is not replay-only. Their codes are not in faceit.sqlite3 -
they are scrims - but truth here is what is printed on the screen, not what the
league feed knows.

The strip boxes are what auto-calibrate places on these frames. The 2557x1438
values are gen_all.py's, unchanged. The 2559x1439 frames are a WINDOWED desktop
capture, so the game viewport is inset by the title bar and window border and
the strip is NOT at the same pixel offsets. That is the whole reason they are in
the set: a reader that only works on fullscreen frames has not been tested.
"""

CODES = {
    '200028': 'K3A6HZ',
    '231525': 'TJDE6W',
    '231549': 'TJDE6W',
    '231604': 'TJDE6W',
    '231629': 'H6R64B',
    '231639': 'H6R64B',
    '231647': 'H6R64B',
    '231657': 'H6R64B',
    'image': 'GPJW93',
    '234927': 'D9X9N2',
    '234953': '9962X3',
    '235003': 'G84XPD',
}

# size -> the TEAM 1 five-portrait strip (x, y, w, h)
STRIPS = {
    # The July frames sit at a DIFFERENT HUD position from the live tool: their
    # portrait strip starts at x=57, where AUTO_STRIPS would put it at x=129 -
    # rendering the auto box on one of them cuts the first portrait in half.
    # Whatever produced them (a different UI scale, a different build), they
    # cannot constrain geometry expressed against auto-calibrate's box, so they
    # are kept for reading accuracy but excluded from the geometry fit.
    (2557, 1438): (57, 97, 700, 111),
    # THE LIVE CONVENTION. Not hand-measured: this is what auto-calibrate
    # actually produces, confirmed by reading boxes.a out of a real capture
    # session on a 2560x1440 share - (129.536, 119.808, 660.224, 97.2), which
    # is AUTO_STRIPS' fractions with no sweep correction applied.
    #
    # It matters that these are different numbers from a hand measurement of
    # the same HUD. The offsets are fractions OF THIS BOX, so fitting them
    # against a strip the tool never produces fits them to nothing: measured
    # against the 2557x1438 convention the code is 0.198 strip-heights tall,
    # measured against this one it is 0.237. The first eval scored 12/12
    # through a rectangle that does not occur in the field.
    (2559, 1439): (129.536, 119.808, 660.224, 97.2),
}


def strip_a(size):
    """The calibrated TEAM 1 strip for a frame of this size, or None."""
    return STRIPS.get(tuple(size))


if __name__ == '__main__':
    import json
    import pathlib
    pathlib.Path('tools/real_frame_eval/code_truth.json').write_text(
        json.dumps(CODES, indent=2), encoding='utf-8')
    print('wrote code_truth.json', len(CODES), 'frames')

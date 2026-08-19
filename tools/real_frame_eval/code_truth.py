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
    (2557, 1438): (57, 97, 700, 111),
    # Fitted on 234927 by cropping and comparing against the fullscreen strip
    # until it frames the same HUD region: portrait top down to the bottom of
    # the health/ult bar. A first attempt stopped at the name row, which looks
    # plausible on its own but is a different region, so the code offsets -
    # being fractions of the strip - would not have transferred.
    (2559, 1439): (127, 123, 660, 105),
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

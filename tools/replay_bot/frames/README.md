# Golden frames

Real HUD frames the crop and matcher paths are validated against. **These are
deliberately not committed** — the repo tracks exactly one image (`docs/og.png`),
and `tools/real_frame_eval` keeps its frames out of git the same way. A few
megabytes per frame would dwarf the source.

Keep them here locally. `.gitignore` in this directory ignores everything except
itself and this file.

## Where they come from

A frame is only useful if it was produced the way the bot produces one: a
`getDisplayMedia` share of the **Overwatch window** (not the display), at the
resolution recorded in `../calib.js`, borderless windowed.

Capture one by running the snippet below in the capture page's console with a
replay paused and all ten players alive. It saves the raw frame and a second
copy with the calibration box and the ten crop cells drawn on, which is the one
to actually look at.

```js
(() => {
  const w = vid.videoWidth, h = vid.videoHeight;
  const save = (cv, name) => cv.toBlob(b => {
    const a = document.createElement('a');
    a.href = URL.createObjectURL(b); a.download = name; a.click();
  }, 'image/png');
  const raw = document.createElement('canvas');
  raw.width = w; raw.height = h;
  raw.getContext('2d').drawImage(vid, 0, 0);
  save(raw, `owdb-raw-${w}x${h}.png`);
  setTimeout(() => {
    const an = document.createElement('canvas');
    an.width = w; an.height = h;
    const cx = an.getContext('2d');
    cx.drawImage(vid, 0, 0); cx.lineWidth = 2;
    for (const [side, col] of [['a', '#4da3ff'], ['b', '#ff5c5c']]) {
      const bx = boxes[side]; if (!bx) continue;
      cx.strokeStyle = col; cx.strokeRect(bx.x, bx.y, bx.w, bx.h);
      cx.strokeStyle = '#3fe08f';
      for (let i = 0; i < 5; i++) {
        const cw = bx.w / 5;
        cx.strokeRect(bx.x + i * cw + cw * LF, bx.y, cw * (1 - LF), bx.h * TF);
      }
    }
    save(an, `owdb-boxes-${w}x${h}.png`);
  }, 800);
})();
```

**Press "Use boxes" and confirm the page says calibration looks good before
capturing.** Auto-calibrate reports "10/10 portraits confident" for a detection
it has not committed yet, so a frame taken before that button records the
`AUTO_STRIPS` default rather than the real geometry. That default is
`(129.536, 119.808, 660.224, 97.2)`; it is shifted right by half a portrait and
drops onto the health pips, and it is impossible to spot as a number — which is
exactly why the annotated copy exists.

## What is here

| Frame | Notes |
|---|---|
| `2026-09-08-busan-2560x1440.png` | The bootstrap frame. Geometry is good, but it is a **workshop lobby**, not a league replay — placeholder entity names, and an unrepresentative hero spread. Fine for validating crop geometry; poor for judging matcher confidence. |

A league replay frame is still wanted, so matcher scores can be measured against
the heroes and name plates the bot will really meet.

## What the bot leaves here

A run names every frame it takes for what it was: `cap-timeline-*` and
`cap-zero-*`/`cap-one-*` from the setup, `cap-t<seconds>-*` for each sample,
`cap-settle-*`/`cap-q-*` from waiting, `cap-pause-*` from the motion check, and
`probe-*` from whichever probe was run. Only the samples - the ones read as
`cap-t<seconds>-*` - are `.png`; everything else is scratch and written as
`.bmp`, because PNG's compression costs more than the capture itself does.

A map that **succeeds** has its scratch frames swept away when it finishes -
the samples were already copied out. A map that **fails** keeps only the first
scratch frame it took plus the dozen most recent - what the map opened on, and
what was on screen when it broke - converted to `.png` since those are staying
for good; everything else from a failed map is discarded rather than kept
forever, because a run that loops (retrying a check that never resolves) used
to leave as many scratch frames as it took retries. Retention is not tidiness,
it is the recovery path: **a replay code imports once**, so a map read badly
cannot be re-captured on that account, but a better matcher can re-read its
frames offline for nothing. That is why the guards refuse loudly rather than
carrying on: only a broken *grab* is unrecoverable, and a kept scratch frame is
how that gets told apart from a bad read.

They are gitignored like everything else here. `contact_sheet.js` renders the
ten crops of any of them, which is how a geometry problem gets looked at rather
than believed.

## The corpus, and why it is a subdirectory

`corpus/` holds the frames that have been **looked at and labelled**. It exists
because a run names its frames `cap-<tag>-<n>.png` with `n` restarting at zero
every time, so **the next run overwrites the last one's**. The corpus first
pointed straight at this directory, and a five-map run replaced three labelled
witnesses - one of them the frame whose 15.1 tint was the whole evidence for
reading the team plates off the portrait band. Every test still passed, because
the replacements happened to fall on the same side of every threshold.

Copy a new witness in by hand. A label pointing at a frame out here has a
countdown on it.

**The ones that have been looked at are named in `../corpus.js`**, with a note
on what is actually in each. That file is the committed half of this directory:
the frames are megabytes and stay out of git, the labels are small and are the
whole point. `../fakeio.js` replays frames through `capture.js` with no client
attached, and `node tools/replay_bot/corpus_sweep.js` runs every detector over
everything here and prints what it said - which is how a detector that was
measured on three maps and wrong on six frames got caught without spending a
code.

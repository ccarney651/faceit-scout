# Replay-code OCR Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Read the six-character Overwatch replay code off the live HUD on demand, so a scrim map's code fills itself and a league capture can prove it is filed against the match actually on screen.

**Architecture:** One DOM-free engine module (`engine/replaycode.js`) owns the alphabet, the crop geometry and the validation gate. Both capture pages call it through their existing shared Tesseract worker. The crop is anchored to the already-calibrated TEAM 1 portrait strip (`boxes.a`), never to screen fractions. Geometry is fitted offline against twelve real frames with known codes before it ships.

**Tech Stack:** Vanilla ES5-flavoured JS (UMD IIFE, browser global + CommonJS), `node:test` for module unit tests, pytest as the suite of record, Tesseract.js 5.1.1 via the shared worker, Pillow + NumPy for the offline eval.

**Spec:** `specs/2026-08-19-replay-code-ocr-design.md`

## Global Constraints

- **Alphabet is Crockford Base32**, exactly: `0123456789ABCDEFGHJKMNPQRSTVWXYZ`. 32 symbols, no `I`, `L`, `O`, `U`.
- **Folding rules are the published spec's, not inventions:** `I`→`1`, `L`→`1`, `O`→`0`. Case-insensitive input. **Do not fold `U` to anything** — a `U` fails the read.
- **Codes are always exactly 6 characters.** Any other length is a failed read.
- **A refused read is correct behaviour; a wrong read is a corrupted record.** Never write an unvalidated code. Gate: zero wrong reads across the ground-truth frames.
- **One shared Tesseract worker.** `tessedit_pageseg_mode` AND `tessedit_char_whitelist` must be set before a code read and restored after (`pageseg_mode` back to `'7'`, whitelist back to `''`). Reads must not overlap.
- **Never commit `docs/capture/data.json`.** Restore with `git checkout -- docs/capture/data.json`.
- **`screenshots/` is gitignored** (56 MB). Frames referenced here exist locally only.
- **Plans and specs live in `specs/`, never `docs/`** — `docs/` is the published GitHub Pages site.
- Run `.venv/Scripts/python.exe tools/capture_divergence.py` before and after touching shared capture code. Baseline on `scrim-mode`: shared 35 / identical 12 / diverged 23. Task 8 adds an identical `readReplayCode()` to both pages, so `shared` and `identical` are each expected to rise by one - record the new baseline, do not suppress it.
- Serve with `.venv/Scripts/python.exe -m http.server 8000 --directory docs`; open `http://localhost:8000/capture/`. Never `file://`. Hard-refresh (Ctrl+Shift+R) after editing `engine/*.js`.

---

## File Structure

| File | Responsibility |
| --- | --- |
| `docs/capture/engine/replaycode.js` | **Create.** Alphabet, `foldCode()`, `codeBox()`. DOM-free, no OCR, no page globals. |
| `docs/capture/engine/frames.js` | **Modify.** Add `codeCanvas(frame, box)` — the upscale+contrast crop, beside `nameCanvas()`. Both pages already destructure from this module; `index.html` has no `scoreCanvas()` of its own, and the contrast curve must match the offline prototype exactly or the parity check compares two different images. |
| `docs/capture/engine/replaycode.test.js` | **Create.** `node:test` units, auto-discovered by `tests/test_capture_js_units.py`. |
| `tools/real_frame_eval/code_truth.py` | **Create.** Frame stem → known code, and the calibrated `boxes.a` per frame size. |
| `tools/real_frame_eval/code_crop.py` | **Create.** Python mirror of the crop + preprocessing, for sweeping. |
| `tools/real_frame_eval/code_eval.js` | **Create.** Runs real Tesseract over rendered crops; reports correct / wrong / no-read. |
| `tools/real_frame_eval/code_sweep.py` | **Create.** Sweeps the offsets to fit the shipping values. |
| `tools/real_frame_eval/code_parity.js` | **Create.** Runs shipped `codeBox()` over the same frames as the Python prototype. |
| `docs/capture/scrim.html` | **Modify.** `readReplayCode()`, *Read code* button in `prow-next`, one read at map start. |
| `docs/capture/index.html` | **Modify.** `readReplayCode()`, *Read code* button by the picker, snap-to-feed. |
| `tests/test_capture_scrim.py` | **Modify.** Scrim wiring tests. |
| `tests/test_capture_replaycode.py` | **Create.** League-page wiring + snap-to-feed tests. |
| `ARCHITECTURE.md`, `CHANGELOG.md` | **Modify.** Document the module and the behaviour. |

---

## Task 1: The validation gate

**Files:**
- Create: `docs/capture/engine/replaycode.js`
- Test: `docs/capture/engine/replaycode.test.js`

**Interfaces:**
- Consumes: nothing.
- Produces: `OWDBReplayCode.ALPHABET` (string, 32 chars); `OWDBReplayCode.foldCode(raw) -> string|null` returning a 6-char uppercase code or `null`.

- [ ] **Step 1: Write the failing test**

Create `docs/capture/engine/replaycode.test.js`:

```js
const test = require('node:test');
const assert = require('node:assert');
const R = require('./replaycode.js');

test('the alphabet is Crockford Base32', () => {
  assert.strictEqual(R.ALPHABET, '0123456789ABCDEFGHJKMNPQRSTVWXYZ');
  assert.strictEqual(R.ALPHABET.length, 32);
  for (const ch of 'ILOU') assert.ok(R.ALPHABET.indexOf(ch) === -1, ch + ' must not be in the alphabet');
});

test('a clean read passes through', () => {
  assert.strictEqual(R.foldCode('D9X9N2'), 'D9X9N2');
});

test('lower case is accepted, as Crockford decoders must', () => {
  assert.strictEqual(R.foldCode('d9x9n2'), 'D9X9N2');
});

test('OCR punctuation around the code is discarded', () => {
  // The crop carries the plate edges; the name-crop work showed OCR wraps a
  // legible string in invented punctuation.
  assert.strictEqual(R.foldCode('| D9X9N2 |'), 'D9X9N2');
  assert.strictEqual(R.foldCode('  D9X9N2\n'), 'D9X9N2');
});

test('I and L fold to 1, and O folds to 0 - the published decoder rule', () => {
  assert.strictEqual(R.foldCode('I9X9N2'), '19X9N2');
  assert.strictEqual(R.foldCode('L9X9N2'), '19X9N2');
  assert.strictEqual(R.foldCode('O9X9N2'), '09X9N2');
});

test('U is not folded - it fails the read', () => {
  // Crockford excludes U for accidental obscenity, not for visual ambiguity,
  // so there is no principled character to fold it to. Guessing V would be ours.
  assert.strictEqual(R.foldCode('U9X9N2'), null);
});

test('anything but exactly six characters is not a code', () => {
  assert.strictEqual(R.foldCode('D9X9N'), null);
  assert.strictEqual(R.foldCode('D9X9N23'), null);
  assert.strictEqual(R.foldCode(''), null);
  assert.strictEqual(R.foldCode(null), null);
  assert.strictEqual(R.foldCode(undefined), null);
});

test('a character outside the alphabet fails the whole read', () => {
  // Not "drop the bad character and hope" - five good characters and one
  // unknown is not five-sixths of a code, it is no code.
  assert.strictEqual(R.foldCode('D9X9N#'), null);
});
```

- [ ] **Step 2: Run it to verify it fails**

```bash
cd docs/capture/engine && node --test replaycode.test.js
```

Expected: FAIL — `Cannot find module './replaycode.js'`.

- [ ] **Step 3: Write the minimal implementation**

Create `docs/capture/engine/replaycode.js`:

```js
// docs/capture/engine/replaycode.js
// The replay code Overwatch prints on the HUD: its alphabet, where it sits on
// screen, and whether a given OCR read is a code at all.
//
// THE ALPHABET IS CROCKFORD BASE32, and that is measured, not assumed. Across
// all 4328 codes in faceit.sqlite3 (games.demo_code) every code is exactly six
// characters and only 32 distinct symbols ever appear - the ten digits plus
// A-Z without I, L, O and U - each of them 750-850 times. Zero occurrences of
// four specific characters in 25,968 draws rules out a 36-symbol alphabet.
// That set is Crockford's exactly, and 32 symbols x 6 characters is 30 bits.
//
// This matters because Crockford documents WHY those four are missing, and the
// reasons are our OCR problem: I and L "can be confused with 1", O "can be
// confused with 0". The spec then prescribes the decoder rule directly - "i and
// l will be treated as 1 and o will be treated as 0" - so the folding below is
// a published standard rather than a guess about what tesseract tends to do.
//
// U is excluded for "accidental obscenity", which has nothing to do with visual
// ambiguity, so there is no principled character to fold it to. A U therefore
// FAILS the read. An earlier draft folded it to V by inference; that was ours,
// not Crockford's, and it is exactly the kind of invention that turns a refused
// read into a wrong one.
//
// See specs/2026-08-19-replay-code-ocr-design.md.
//
// Works as a browser global (`window.OWDBReplayCode`) and as a CommonJS module
// for node:test / pytest.

(function (global) {
  'use strict';

  var ALPHABET = '0123456789ABCDEFGHJKMNPQRSTVWXYZ';
  var LEN = 6;

  // Crockford's decoder rule. Deliberately not a general "what OCR gets wrong"
  // table: every entry here is in the published spec.
  var FOLD = { I: '1', L: '1', O: '0' };

  // foldCode(raw) -> 'D9X9N2' | null
  //
  // Null means NO READ, and the caller must write nothing. Five good characters
  // and one unreadable is not five-sixths of a code - it is not a code, and
  // filling in the sixth would produce a record indistinguishable from a
  // correct one.
  function foldCode(raw) {
    var s = String(raw == null ? '' : raw).toUpperCase();
    // The crop carries the plate's edges, and OCR wraps legible text in
    // invented punctuation - see engine/opponents.js norm() for the same
    // finding on HUD names.
    s = s.replace(/[^A-Z0-9]/g, '');
    var out = '';
    for (var i = 0; i < s.length; i++) {
      var ch = FOLD[s[i]] || s[i];
      if (ALPHABET.indexOf(ch) === -1) return null;
      out += ch;
    }
    return out.length === LEN ? out : null;
  }

  var Mod = { ALPHABET: ALPHABET, LEN: LEN, foldCode: foldCode };

  if (typeof module !== 'undefined' && module.exports) module.exports = Mod;
  else global.OWDBReplayCode = Mod;
})(typeof self !== 'undefined' ? self : this);
```

- [ ] **Step 4: Run the tests to verify they pass**

```bash
cd docs/capture/engine && node --test replaycode.test.js
```

Expected: PASS, 8/8. Then from the repo root, confirm pytest discovers it:

```bash
.venv/Scripts/python.exe -m pytest tests/test_capture_js_units.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add docs/capture/engine/replaycode.js docs/capture/engine/replaycode.test.js
git commit -m "Add the replay-code validation gate"
```

---

## Task 2: Where the code sits on screen

**Files:**
- Modify: `docs/capture/engine/replaycode.js`
- Test: `docs/capture/engine/replaycode.test.js`

**Interfaces:**
- Consumes: Task 1's module.
- Produces: `OWDBReplayCode.codeBox(boxA) -> {x, y, w, h}` — the crop rectangle in frame pixels, given the calibrated TEAM 1 portrait strip `{x, y, w, h}`.

**Starting offsets.** Measured on `Screenshot 2026-07-15 231525.png` (2557×1438), whose code is `TJDE6W`, against the strip `tools/real_frame_eval/gen_all.py` already uses for that frame size, `boxes.a = (57, 97, 700, 111)`:

| | pixels | as a fraction of the strip |
| --- | --- | --- |
| code left | 812 | `a.x + 1.079 * a.w` |
| code width | 89 | `0.127 * a.w` |
| code top | 42 | `a.y - 0.495 * a.h` |
| code height | 22 | `0.198 * a.h` |

These are **provisional** and are refitted in Task 5. Pad generously (the crop may include plate edge; `foldCode` strips punctuation).

- [ ] **Step 1: Write the failing test**

Append to `docs/capture/engine/replaycode.test.js`:

```js
test('the crop is placed relative to the calibrated strip, not the screen', () => {
  // Two frames of the same HUD at different scales must produce boxes in the
  // same proportion. Screen fractions are what broke the HUD name band when
  // the window mode changed - see the 2026-08-18 changelog entry.
  const small = R.codeBox({ x: 57, y: 97, w: 700, h: 111 });
  const big = R.codeBox({ x: 114, y: 194, w: 1400, h: 222 });
  assert.ok(Math.abs((big.x - 114) / 1400 - (small.x - 57) / 700) < 1e-9);
  assert.ok(Math.abs(big.w / 1400 - small.w / 700) < 1e-9);
});

test('the crop sits above the strip and to its right', () => {
  const a = { x: 57, y: 97, w: 700, h: 111 };
  const box = R.codeBox(a);
  assert.ok(box.x > a.x + a.w, 'the code is right of the portrait strip');
  assert.ok(box.y + box.h < a.y, 'the code is above the portrait strip');
});

test('the crop lands on the known code position for a real frame', () => {
  // TJDE6W on Screenshot 2026-07-15 231525.png (2557x1438), measured.
  const box = R.codeBox({ x: 57, y: 97, w: 700, h: 111 });
  assert.ok(box.x <= 812 && box.x + box.w >= 812 + 89,
    'the crop must contain the measured code rectangle x=812..901');
  assert.ok(box.y <= 42 && box.y + box.h >= 42 + 22,
    'the crop must contain the measured code rectangle y=42..64');
});

test('a missing or malformed strip yields no box rather than NaNs', () => {
  assert.strictEqual(R.codeBox(null), null);
  assert.strictEqual(R.codeBox({ x: 0, y: 0, w: 0, h: 0 }), null);
});
```

- [ ] **Step 2: Run it to verify it fails**

```bash
cd docs/capture/engine && node --test replaycode.test.js
```

Expected: FAIL — `R.codeBox is not a function`.

- [ ] **Step 3: Write the minimal implementation**

In `replaycode.js`, before the `Mod` object:

```js
  // Where the code sits, as fractions of the calibrated TEAM 1 portrait strip.
  //
  // ANCHORED TO THE STRIP, NOT TO THE SCREEN. auto-calibrate has already fitted
  // that strip to this particular HUD at this particular resolution and window
  // mode, so expressing the crop against it costs nothing and inherits all of
  // that work. The HUD name band was originally a fraction of the SCREEN and
  // straddled the portrait bottom, the name and the health bar the moment the
  // window mode changed; that is the mistake this avoids.
  //
  // Fitted by tools/real_frame_eval/code_sweep.py - do not hand-edit.
  var DX = 1.079;      // left edge, in strip widths right of the strip's left edge
  var DW = 0.127;      // width, in strip widths
  var DY = -0.495;     // top edge, in strip heights below the strip's top (negative = above)
  var DH = 0.198;      // height, in strip heights
  var PAD = 0.35;      // extra margin, in multiples of the box's own size

  function codeBox(a) {
    if (!a || !(a.w > 0) || !(a.h > 0)) return null;
    var w = DW * a.w, h = DH * a.h;
    var px = w * PAD, py = h * PAD;
    return {
      x: Math.round(a.x + DX * a.w - px),
      y: Math.round(a.y + DY * a.h - py),
      w: Math.round(w + 2 * px),
      h: Math.round(h + 2 * py),
    };
  }
```

Add `codeBox: codeBox` and the four offsets to `Mod` (the sweep needs to read them):

```js
  var Mod = {
    ALPHABET: ALPHABET, LEN: LEN, foldCode: foldCode, codeBox: codeBox,
    OFFSETS: { DX: DX, DW: DW, DY: DY, DH: DH, PAD: PAD },
  };
```

- [ ] **Step 4: Run the tests to verify they pass**

```bash
cd docs/capture/engine && node --test replaycode.test.js
```

Expected: PASS, 12/12.

- [ ] **Step 5: Commit**

```bash
git add docs/capture/engine/replaycode.js docs/capture/engine/replaycode.test.js
git commit -m "Locate the replay code against the calibrated strip"
```

---

## Task 3: Ground truth for the frames

**Files:**
- Create: `tools/real_frame_eval/code_truth.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `CODES` (dict: frame stem → 6-char code) and `strip_a(size) -> (x, y, w, h)` for use by Tasks 4–6.

The codes for the 2557×1438 frames are already hand-verified in `tools/real_frame_eval/gen_truth.py` — they were needed there to resolve each frame's lineup. This lifts them into one place and adds the 2026-08-18 windowed frames.

- [ ] **Step 1: Confirm the windowed frames' codes by eye**

Open each of `screenshots/Screenshot 2026-08-18 234927.png`, `234953.png`, `235003.png` and read the code printed right of the TEAM 1 banner. `234927` is known to be `D9X9N2`. Record what the other two actually say — **do not assume they match** just because they are from the same session; if a different replay was loaded the code differs, and a wrong truth entry would make a correct reader look broken.

- [ ] **Step 2: Write the truth table**

Create `tools/real_frame_eval/code_truth.py`:

```python
"""Frame -> replay code, and the calibrated TEAM 1 strip per frame size.

The 2557x1438 codes are lifted from gen_truth.py, where they were hand-verified
because the name-attribution eval needed each frame's code to resolve its
lineup. There they were incidental context; here they are the thing under test.

The strip boxes are what auto-calibrate places on these frames - the 2557x1438
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
    # 234953 / 235003 - fill in from Step 1, or drop them from the set.
}

# size -> the TEAM 1 five-portrait strip (x, y, w, h)
STRIPS = {
    (2557, 1438): (57, 97, 700, 111),
}


def strip_a(size):
    """The calibrated TEAM 1 strip for a frame of this size, or None."""
    return STRIPS.get(tuple(size))
```

- [ ] **Step 3: Measure the windowed frames' strip**

The 2559×1439 frames have no entry yet. Measure the TEAM 1 five-portrait strip on `234927` — left edge of the first portrait, top of the portraits, full width across five cells, height down to the bottom of the name row — and add it:

```python
STRIPS = {
    (2557, 1438): (57, 97, 700, 111),
    (2559, 1439): (?, ?, ?, ?),   # measured on 234927
}
```

Verify by cropping and looking at it:

```bash
.venv/Scripts/python.exe -c "
from PIL import Image
import sys; sys.path.insert(0,'tools/real_frame_eval')
from code_truth import strip_a
im = Image.open('screenshots/Screenshot 2026-08-18 234927.png')
x,y,w,h = strip_a(im.size)
im.crop((x,y,x+w,y+h)).save('strip_check.png')
print('wrote strip_check.png', im.size)
"
```

Open `strip_check.png`. It must show exactly the five TEAM 1 portraits with their names, no more. Iterate until it does, then delete it.

- [ ] **Step 4: Commit**

```bash
git add tools/real_frame_eval/code_truth.py
git commit -m "Collect the ground-truth codes and strips for the frame set"
```

---

## Task 4: Offline read, measured

**Files:**
- Create: `tools/real_frame_eval/code_crop.py`
- Create: `tools/real_frame_eval/code_eval.js`

**Interfaces:**
- Consumes: `code_truth.CODES`, `code_truth.strip_a`, `OWDBReplayCode.codeBox`, `OWDBReplayCode.foldCode`.
- Produces: `code_crop.render(frame_path, out_dir)` writing one PNG per frame; `code_eval.js` printing a per-frame table plus totals.

- [ ] **Step 1: Write the crop renderer**

Create `tools/real_frame_eval/code_crop.py`:

```python
"""Render the replay-code crop from a real frame, exactly as the browser would.

Preprocessing mirrors what the name crops needed (engine/frames.js nameCanvas):
upscale hard, greyscale, then push contrast. The code sits on a semi-transparent
plate over arbitrary game art, which is the same problem the name plates had -
and there the contrast step took reads from 15/90 to 77/90.

Geometry comes from the SHIPPED codeBox() offsets via code_offsets.json, written
by code_sweep.py, so this tool and the browser cannot disagree about where to
look.
"""
import json
import pathlib
import sys

import numpy as np
from PIL import Image

sys.path.insert(0, 'tools/real_frame_eval')
from code_truth import strip_a

SCALE = 6
CONTRAST = 1.9        # harder than the name crops' 1.5: fewer, larger glyphs
MID = 140


def offsets():
    p = pathlib.Path('tools/real_frame_eval/code_offsets.json')
    if p.exists():
        return json.loads(p.read_text())
    return {'DX': 1.079, 'DW': 0.127, 'DY': -0.495, 'DH': 0.198, 'PAD': 0.35}


def code_box(a, o=None):
    o = o or offsets()
    x, y, w, h = a
    bw, bh = o['DW'] * w, o['DH'] * h
    px, py = bw * o['PAD'], bh * o['PAD']
    return (round(x + o['DX'] * w - px), round(y + o['DY'] * h - py),
            round(bw + 2 * px), round(bh + 2 * py))


def render(frame_path, out_dir, o=None):
    img = Image.open(frame_path).convert('RGB')
    a = strip_a(img.size)
    if a is None:
        return None
    bx, by, bw, bh = code_box(a, o)
    crop = img.crop((bx, by, bx + bw, by + bh)).resize(
        (bw * SCALE, bh * SCALE), Image.LANCZOS)
    g = np.asarray(crop.convert('L')).astype(np.int16)
    g = np.clip((g - 128) * CONTRAST + MID, 0, 255).astype(np.uint8)
    out_dir = pathlib.Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = pathlib.Path(frame_path).stem.split()[-1]
    out = out_dir / (stem + '.png')
    Image.fromarray(g).save(out)
    return out


if __name__ == '__main__':
    import glob
    for f in sorted(glob.glob('screenshots/*.png')):
        p = render(f, sys.argv[1] if len(sys.argv) > 1 else 'code_crops')
        if p:
            print('rendered', p)
```

- [ ] **Step 2: Render and eyeball the crops**

```bash
.venv/Scripts/python.exe tools/real_frame_eval/code_crop.py code_crops
```

Open two or three of the PNGs. Each must contain the six-character code, legibly, with little else. **If the code is not in the crop, stop and fix the offsets before going further** — every later number would be measuring the wrong rectangle.

- [ ] **Step 3: Write the eval**

Create `tools/real_frame_eval/code_eval.js`:

```js
// Read every rendered code crop with real tesseract and score it against the
// known code. Run from the repo root:
//   node tools/real_frame_eval/code_eval.js code_crops
//
// The gate is WRONG=0. A low read rate is a nuisance the operator retries past;
// a wrong read is a corrupted record that looks exactly like a correct one.
const fs = require('fs');
const path = require('path');
const { createWorker } = require('tesseract.js');
const R = require('../../docs/capture/engine/replaycode.js');
const TRUTH = JSON.parse(fs.readFileSync(path.join(__dirname, 'code_truth.json'), 'utf8'));

(async () => {
  const dir = process.argv[2] || 'code_crops';
  const w = await createWorker('eng');
  await w.setParameters({
    tessedit_pageseg_mode: '7',
    tessedit_char_whitelist: R.ALPHABET,
  });
  let ok = 0, wrong = 0, none = 0;
  for (const f of fs.readdirSync(dir).filter(f => f.endsWith('.png')).sort()) {
    const stem = path.basename(f, '.png');
    const want = TRUTH[stem];
    if (!want) { console.log(stem.padEnd(10), 'no ground truth - skipped'); continue; }
    const { data } = await w.recognize(path.join(dir, f));
    const raw = (data.text || '').trim();
    const got = R.foldCode(raw);
    let verdict;
    if (got === want) { verdict = 'ok'; ok++; }
    else if (got === null) { verdict = 'NO READ'; none++; }
    else { verdict = 'WRONG'; wrong++; }
    console.log(stem.padEnd(10), 'want', want, 'raw', JSON.stringify(raw).padEnd(14),
                'got', String(got).padEnd(8), verdict);
  }
  await w.terminate();
  console.log(`\ncorrect ${ok}  no-read ${none}  WRONG ${wrong}`);
  if (wrong > 0) { console.error('GATE FAILED: a wrong read is a corrupted record'); process.exit(1); }
})();
```

- [ ] **Step 4: Export the truth table as JSON for the JS side**

Add to the bottom of `tools/real_frame_eval/code_truth.py`:

```python
if __name__ == '__main__':
    import json
    import pathlib
    pathlib.Path('tools/real_frame_eval/code_truth.json').write_text(
        json.dumps(CODES, indent=2), encoding='utf-8')
    print('wrote code_truth.json', len(CODES), 'frames')
```

Then:

```bash
.venv/Scripts/python.exe tools/real_frame_eval/code_truth.py
node tools/real_frame_eval/code_eval.js code_crops
```

Expected: a per-frame table and a total line. **Record the numbers.** `WRONG` must be 0; if it is not, the fix is a tighter gate in `foldCode` or a better crop, never a looser comparison.

- [ ] **Step 5: Commit**

```bash
git add tools/real_frame_eval/code_crop.py tools/real_frame_eval/code_eval.js tools/real_frame_eval/code_truth.py
git commit -m "Measure the replay-code read against real frames"
```

---

## Task 5: Fit the offsets

**Files:**
- Create: `tools/real_frame_eval/code_sweep.py`
- Modify: `docs/capture/engine/replaycode.js` (the four constants only)

**Interfaces:**
- Consumes: `code_crop.code_box`, `code_truth`.
- Produces: `tools/real_frame_eval/code_offsets.json`, and the fitted constants written into `replaycode.js`.

The Task 2 offsets came from one frame, read by eye. This fits them across the set and measures how much slack there is — `rowfind_sweep.py` is the precedent.

- [ ] **Step 1: Write the sweep**

Create `tools/real_frame_eval/code_sweep.py`:

```python
"""Fit the code-crop offsets across every ground-truth frame.

Scores a candidate box WITHOUT running OCR: the code plate is a bright,
high-contrast text run on a darker plate, so a box is good when it contains one
horizontal band of text with quiet margins above and below. Scoring on ink
rather than on OCR output keeps the sweep fast and keeps it measuring GEOMETRY -
an OCR-scored sweep would happily reward a box that clips a character if
tesseract guessed the rest.

Also reports robustness: how far each offset can move before the score collapses.
A fit that only works at the exact value is a fit that will break on a HUD scale
this set does not contain.
"""
import glob
import itertools
import json
import pathlib
import sys

import numpy as np
from PIL import Image

sys.path.insert(0, 'tools/real_frame_eval')
from code_truth import CODES, strip_a


def ink_score(img, box):
    x, y, w, h = box
    if w <= 0 or h <= 0:
        return 0.0
    a = np.asarray(img.convert('L').crop((x, y, x + w, y + h))).astype(np.float32)
    if a.size == 0:
        return 0.0
    thr = np.percentile(a, 80)
    on = (a >= thr).astype(np.float32)
    rows = on.mean(axis=1)
    # one contiguous band of text, with margins that are quiet
    band = rows > 0.15
    if not band.any():
        return 0.0
    top, bot = band.argmax(), len(band) - band[::-1].argmax()
    covered = (bot - top) / len(band)
    quiet = 1.0 - max(rows[:top].mean() if top else 0.0,
                      rows[bot:].mean() if bot < len(band) else 0.0)
    # want the band centred and occupying a healthy but not total fraction
    return float(on.mean() * quiet * (1.0 - abs(covered - 0.55)))


def main():
    frames = []
    for f in sorted(glob.glob('screenshots/*.png')):
        stem = pathlib.Path(f).stem.split()[-1]
        if stem not in CODES:
            continue
        img = Image.open(f).convert('RGB')
        a = strip_a(img.size)
        if a:
            frames.append((stem, img, a))
    print('frames in sweep:', len(frames))

    best, grid = None, []
    for dx in np.arange(1.02, 1.14, 0.01):
        for dy in np.arange(-0.60, -0.38, 0.02):
            for dw in np.arange(0.10, 0.17, 0.01):
                for dh in np.arange(0.16, 0.25, 0.02):
                    o = {'DX': float(dx), 'DW': float(dw), 'DY': float(dy),
                         'DH': float(dh), 'PAD': 0.35}
                    from code_crop import code_box
                    s = sum(ink_score(img, code_box(a, o)) for _, img, a in frames)
                    grid.append((s, o))
                    if best is None or s > best[0]:
                        best = (s, o)
    grid.sort(reverse=True, key=lambda t: t[0])
    print('best score', round(best[0], 4), best[1])
    print('\ntop 5:')
    for s, o in grid[:5]:
        print(' ', round(s, 4), o)
    within = [o for s, o in grid if s >= best[0] * 0.9]
    for k in ('DX', 'DW', 'DY', 'DH'):
        vs = [o[k] for o in within]
        print(f'{k}: within 10% of best across {min(vs):.3f}..{max(vs):.3f}')
    pathlib.Path('tools/real_frame_eval/code_offsets.json').write_text(
        json.dumps(best[1], indent=2), encoding='utf-8')
    print('\nwrote code_offsets.json')


if __name__ == '__main__':
    main()
```

- [ ] **Step 2: Run it**

```bash
.venv/Scripts/python.exe tools/real_frame_eval/code_sweep.py
```

Read the robustness lines. **If any offset's 10% band is narrower than roughly ±0.02, say so and stop** — a knife-edge fit will not survive a HUD this set does not contain, and the honest response is to widen `PAD` rather than ship a brittle number.

- [ ] **Step 3: Re-render and re-measure with the fitted offsets**

```bash
.venv/Scripts/python.exe tools/real_frame_eval/code_crop.py code_crops
node tools/real_frame_eval/code_eval.js code_crops
```

Expected: correct count no worse than Task 4's, `WRONG` still 0.

- [ ] **Step 4: Write the fitted constants into the module**

Edit the `DX`/`DW`/`DY`/`DH` values in `docs/capture/engine/replaycode.js` to match `code_offsets.json`. Re-run the module tests — the "lands on the known code position" test from Task 2 must still pass:

```bash
cd docs/capture/engine && node --test replaycode.test.js
```

- [ ] **Step 5: Commit**

```bash
git add tools/real_frame_eval/code_sweep.py tools/real_frame_eval/code_offsets.json docs/capture/engine/replaycode.js
git commit -m "Fit the code-crop offsets across the frame set"
```

---

## Task 6: Parity — the shipped code over the same pixels

**Files:**
- Create: `tools/real_frame_eval/code_parity.js`

**Interfaces:**
- Consumes: `OWDBReplayCode.codeBox`, `code_offsets.json`.
- Produces: a pass/fail comparison.

The Python prototype and the shipped module are two implementations of one rectangle. `rowfind_parity.py`/`.js` exists because they drifted once.

- [ ] **Step 1: Write the parity check**

Create `tools/real_frame_eval/code_parity.js`:

```js
// The shipped codeBox() must place the same rectangle as the Python prototype
// that was swept. Two implementations of one number drift; this is what catches
// it. Run from the repo root:
//   node tools/real_frame_eval/code_parity.js
const fs = require('fs');
const path = require('path');
const R = require('../../docs/capture/engine/replaycode.js');

const fitted = JSON.parse(fs.readFileSync(path.join(__dirname, 'code_offsets.json'), 'utf8'));
let bad = 0;
for (const [k, v] of Object.entries(fitted)) {
  if (Math.abs(R.OFFSETS[k] - v) > 1e-9) {
    console.error(`OFFSET DRIFT ${k}: module ${R.OFFSETS[k]} vs fitted ${v}`);
    bad++;
  }
}
// And the box itself, on the strips the sweep actually used.
for (const a of [{ x: 57, y: 97, w: 700, h: 111 }, { x: 114, y: 194, w: 1400, h: 222 }]) {
  const b = R.codeBox(a);
  const bw = fitted.DW * a.w, bh = fitted.DH * a.h;
  const px = bw * fitted.PAD, py = bh * fitted.PAD;
  const want = {
    x: Math.round(a.x + fitted.DX * a.w - px), y: Math.round(a.y + fitted.DY * a.h - py),
    w: Math.round(bw + 2 * px), h: Math.round(bh + 2 * py),
  };
  for (const k of ['x', 'y', 'w', 'h']) {
    if (b[k] !== want[k]) { console.error(`BOX DRIFT ${k}: ${b[k]} vs ${want[k]}`); bad++; }
  }
}
if (bad) { console.error('parity FAILED'); process.exit(1); }
console.log('parity ok - shipped codeBox matches the swept offsets');
```

- [ ] **Step 2: Run it**

```bash
node tools/real_frame_eval/code_parity.js
```

Expected: `parity ok`.

- [ ] **Step 3: Commit**

```bash
git add tools/real_frame_eval/code_parity.js
git commit -m "Check the shipped code box against the swept prototype"
```

---

## Task 7: Read it in the browser (scrim page)

**Files:**
- Modify: `docs/capture/scrim.html`
- Test: `tests/test_capture_scrim.py`

**Interfaces:**
- Consumes: `OWDBReplayCode.codeBox`, `OWDBReplayCode.foldCode`, `OWDBReplayCode.ALPHABET`, existing `grabFrame()`, `ocrWorker()`, `boxes`, and `codeCanvas()` added to `engine/frames.js` in Step 3.
- Produces: `readReplayCode() -> Promise<string|null>` on the page; a *Read code* button in the panel's `prow-next` row.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_capture_scrim.py`:

```python
def test_the_panel_can_read_the_replay_code_off_the_screen() -> None:
    row = _extract(("{id:'prow-next'", "{id:'prow-main'"))
    assert "readReplayCode(" in row, "the panel has no way to read the code"


def test_reading_the_code_restores_the_shared_workers_settings() -> None:
    # One worker is shared with readHudNames and readScoreboard. Its header
    # records that no whitelist is set globally because readScoreboard needs
    # full text - so a code-only whitelist that is not restored silently
    # breaks the scoreboard read instead of failing loudly.
    src = _extract(("async function readReplayCode(", "// ---------- hero bans"))
    assert "tessedit_char_whitelist" in src
    assert src.count("setParameters") >= 2, "the whitelist is set but never restored"
    assert "tessedit_char_whitelist:''" in src.replace(" ", ""), (
        "the whitelist must be cleared again, not left set to the code alphabet"
    )


def test_an_unreadable_code_writes_nothing() -> None:
    # foldCode returning null must leave the field alone. A plausible wrong
    # code in a saved record is indistinguishable from a correct one.
    src = _extract(("async function readReplayCode(", "// ---------- hero bans"))
    assert "foldCode(" in src, "the read is not put through the validation gate"
```

- [ ] **Step 2: Run them to verify they fail**

```bash
.venv/Scripts/python.exe -m pytest tests/test_capture_scrim.py -q -k "replay_code or restores_the_shared or unreadable_code"
```

Expected: FAIL — extraction anchor not found / `readReplayCode` absent.

- [ ] **Step 3: Add the crop canvas to the shared frames module**

`scoreCanvas()` exists only on `scrim.html`, and it upscales without touching
contrast. The offline prototype (`code_crop.py`) applies `(g-128)*1.9+140` after
a 6× upscale, and **if the browser does not apply the same curve, the parity
check is comparing two different images through the same rectangle.**
`nameCanvas()` in `engine/frames.js` already does exactly this shape of work at
1.5/140, so the new crop belongs beside it — and putting it there also solves
`index.html` having no crop helper at all.

In `docs/capture/engine/frames.js`, next to `nameCanvas`:

```js
    // The replay-code crop: upscale hard, then push contrast, exactly as
    // nameCanvas does for HUD names. The code sits on a semi-transparent plate
    // over arbitrary game art - the same problem, and contrast is what solved
    // it there (15/90 reads to 77/90).
    //
    // These constants are duplicated in tools/real_frame_eval/code_crop.py,
    // which is what the crop offsets were swept against. THEY MUST MATCH: the
    // parity check compares rectangles, and a different contrast curve would
    // still be two different images through the same box.
    function codeCanvas(frame, box) {
      var sc = 6;
      var cv = ctx.doc.createElement('canvas');
      cv.width = Math.max(1, Math.round(box.w * sc));
      cv.height = Math.max(1, Math.round(box.h * sc));
      var cx = cv.getContext('2d', { willReadFrequently: true });
      cx.imageSmoothingEnabled = true; cx.imageSmoothingQuality = 'high';
      cx.drawImage(frame, box.x, box.y, box.w, box.h, 0, 0, cv.width, cv.height);
      var im = cx.getImageData(0, 0, cv.width, cv.height), d = im.data;
      for (var i = 0; i < d.length; i += 4) {
        var g = 0.299 * d[i] + 0.587 * d[i + 1] + 0.114 * d[i + 2];
        g = (g - 128) * 1.9 + 140; g = g < 0 ? 0 : g > 255 ? 255 : g;
        d[i] = d[i + 1] = d[i + 2] = g;
      }
      cx.putImageData(im, 0, 0);
      return cv;
    }
```

Export it in the returned object, beside `nameCanvas: nameCanvas,`:

```js
      codeCanvas: codeCanvas,
```

Then add `codeCanvas` to the destructuring line in **both** pages
(`scrim.html` ~line 871, `index.html` ~line 617):

```js
const {ensureWork, grabFrame, grayCanvas, cellGrayPadded, nameRow, nameCanvas, codeCanvas, detectContentRect, stopCapture, togglePreview, readyForCapture}=frames;
```

- [ ] **Step 4: Load the module and implement the read**

In `docs/capture/scrim.html`, add the script tag next to the others (line ~402):

```html
<script src="engine/replaycode.js"></script>
```

Add, immediately before the `// ---------- hero bans ----------` block:

```js
// ---------- replay code off the screen ----------
// The code Overwatch prints on the HUD banner, read on demand. Geometry and
// validation live in engine/replaycode.js; this is the browser half - grab a
// frame, crop, hand it to the shared OCR worker, and put the result through
// the gate.
//
// The worker is SHARED with readHudNames() and readScoreboard(), and
// engine/refs.js's header records why no character whitelist is set globally:
// readScoreboard() needs full sentences and a code-only whitelist would break
// it. So both parameters are set here and restored immediately after - a
// whitelist left in place would not throw, it would quietly corrupt the next
// scoreboard read.
async function readReplayCode(){
  if(!vid.srcObject) return null;
  if(!boxes.a){ toast('calibrate first — the code is found relative to the left team\'s portraits','warn'); return null; }
  const box=OWDBReplayCode.codeBox(boxes.a);
  if(!box) return null;
  try{
    const w=await ocrWorker();
    await w.setParameters({ tessedit_pageseg_mode:'7', tessedit_char_whitelist:OWDBReplayCode.ALPHABET });
    const {data}=await w.recognize(codeCanvas(grabFrame(), box));
    await w.setParameters({ tessedit_pageseg_mode:'7', tessedit_char_whitelist:'' });
    return OWDBReplayCode.foldCode(data && data.text);
  }catch(e){
    console.error('[owdb] replay-code read failed:', e);
    return null;
  }
}
```

- [ ] **Step 5: Add the button to the panel's next-map row**

In the `{id:'prow-next', ...}` render function, after the code input is appended:

```js
      mk(row,'⌘ Read code',async()=>{
        const got=await readReplayCode();
        if(got){ code.value=got; LAST_CODE=got; snapMsg('read '+got); }
        else snapMsg('could not read the code — try again',true);
      },'');
```

- [ ] **Step 6: Read once at map start when the field is empty**

In `startMapNamed()`, after `code=(code||'').trim();`:

```js
  // One free attempt: the replay is on screen right now, and a code recorded
  // automatically is one the operator never has to type. Only when they left
  // it blank - a typed code is theirs and is never overwritten.
  if(!code){ const read=await readReplayCode(); if(read) code=read; }
```

- [ ] **Step 7: Run the tests to verify they pass**

```bash
.venv/Scripts/python.exe -m pytest tests/test_capture_scrim.py -q
.venv/Scripts/python.exe -m pytest -q
```

Expected: all PASS. Then check syntax and divergence:

```bash
.venv/Scripts/python.exe tools/capture_divergence.py | grep -i "^shared"
```

Expected: unchanged from the baseline in Global Constraints.

- [ ] **Step 8: Commit**

```bash
git add docs/capture/engine/frames.js docs/capture/scrim.html tests/test_capture_scrim.py
git commit -m "Read the replay code from the scrim panel"
```

---

## Task 8: Snap to the feed (league page)

**Files:**
- Modify: `docs/capture/index.html`
- Test: `tests/test_capture_replaycode.py` (create)

**Interfaces:**
- Consumes: `readReplayCode()` (same implementation as Task 7, page-local), `currentCodes()`, `codeKey()`, `selectedCode()`.
- Produces: `matchReadCode(read, codes) -> {kind:'exact'|'near'|'none', code}` — pure, testable.

This is the wrong-match guard: the read is checked against the feed rather than trusted.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_capture_replaycode.py`:

```python
"""The league page checks a read replay code against the feed.

Picking the wrong code from the dropdown attributes every captured comp to the
wrong match, teams and players - and publishes it, with no later signal that it
happened. This is the guard.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

APP = Path(__file__).resolve().parents[1] / "docs" / "capture" / "index.html"


def _run(body: str) -> object:
    node = shutil.which("node")
    if not node:
        pytest.skip("node not available")
    html = APP.read_text(encoding="utf-8")
    start = html.index("function matchReadCode(")
    end = html.index("\n}", start) + 2
    src = html[start:end] + "\nconsole.log(JSON.stringify((()=>{" + body + "})()));"
    tmp = Path("code_match_tmp.js")
    tmp.write_text(src, encoding="utf-8")
    try:
        proc = subprocess.run([node, str(tmp)], capture_output=True, text=True, encoding="utf-8")
        assert proc.returncode == 0, f"node failed:\n{proc.stderr}"
    finally:
        tmp.unlink(missing_ok=True)
    return json.loads(proc.stdout)


FEED = "[{code:'7DNNFL'},{code:'K3A6HZ'},{code:'TJDE6W'}]"


def test_an_exact_read_selects_that_match() -> None:
    got = _run(f"return matchReadCode('K3A6HZ', {FEED});")
    assert got == {"kind": "exact", "code": "K3A6HZ"}


def test_a_one_character_miss_is_offered_as_a_correction() -> None:
    # 7DNNF1 vs 7DNNFL - the exact confusion Crockford excludes L for.
    got = _run(f"return matchReadCode('7DNNF1', {FEED});")
    assert got == {"kind": "near", "code": "7DNNFL"}


def test_a_read_matching_nothing_changes_nothing() -> None:
    got = _run(f"return matchReadCode('ZZZZZZ', {FEED});")
    assert got["kind"] == "none"


def test_an_ambiguous_near_match_abstains() -> None:
    # Two feed codes one character away: choosing either could file the
    # capture against the wrong match, which is the failure being prevented.
    got = _run("return matchReadCode('AAAAAA', [{code:'AAAAAB'},{code:'AAAAAC'}]);")
    assert got["kind"] == "none", "a tie must not be resolved by picking the first"
```

- [ ] **Step 2: Run them to verify they fail**

```bash
.venv/Scripts/python.exe -m pytest tests/test_capture_replaycode.py -q
```

Expected: FAIL — `matchReadCode(` not found in `index.html`.

- [ ] **Step 3: Implement the matcher**

In `docs/capture/index.html`, add the script tag `<script src="engine/replaycode.js"></script>` alongside the other engine modules, and add near `selectedCode()`:

```js
// matchReadCode(read, codes) — what a code read off the screen corresponds to
// in this division's feed.
//
// The feed is what makes the league read trustworthy: a scrim read stands
// alone, but here every code has a right answer available, so a one-character
// miss is recoverable rather than fatal. Crockford excludes I/L/O precisely
// because they are confusable with 1/0, and foldCode already applies the
// published folding - this catches what is left.
//
// A TIE ABSTAINS. Two feed codes one character from the read means choosing
// either could file the capture against the wrong match, which is the exact
// failure this exists to prevent.
function matchReadCode(read, codes){
  if(!read) return {kind:'none', code:null};
  const list=(codes||[]).map(c=>c.code).filter(Boolean);
  if(list.indexOf(read)!==-1) return {kind:'exact', code:read};
  const near=list.filter(c=>{
    if(c.length!==read.length) return false;
    let d=0; for(let i=0;i<c.length;i++) if(c[i]!==read[i]) d++;
    return d===1;
  });
  if(near.length===1) return {kind:'near', code:near[0]};
  return {kind:'none', code:null};
}
```

- [ ] **Step 4: Wire the button**

Add a *Read code* button beside the code picker (near `id="code"` in the markup), and its handler:

```js
document.getElementById('readcode').onclick=async()=>{
  const got=await readReplayCode();
  if(!got){ snapMsg('could not read the code off the screen — try again', true); return; }
  const cs=currentCodes(), m=matchReadCode(got, cs);
  if(m.kind==='none'){ snapMsg('screen says '+esc(got)+', which is not a code in this division — nothing changed', true); return; }
  const idx=cs.findIndex(c=>c.code===m.code);
  const sel=document.getElementById('code');
  const cur=selectedCode();
  if(cur && cur.code===m.code){ snapMsg('screen says '+esc(m.code)+' — matches what is selected'); return; }
  sel.value=String(idx); onCode();
  snapMsg((m.kind==='near'?'read '+esc(got)+', nearest code is ':'screen says ')
      +esc(m.code)+' — selected it');
};
```

Copy `readReplayCode()` from Task 7 verbatim into `index.html`. It stays
page-local on both pages because `boxes`, `vid` and `ocrWorker` are page globals
— but `codeCanvas` now comes from `engine/frames.js` (Task 7 Step 3), so the two
copies are byte-identical and `tools/capture_divergence.py` reports it as a
shared-and-identical function rather than a divergence.

**Use `snapMsg(text, isWarning)` for the messages, not `msg()`** — there is no
`msg()` on either page. `index.html` has `snapMsg(t, warn)` at line ~1310, the
same signature `scrim.html` uses.

- [ ] **Step 5: Run the tests to verify they pass**

```bash
.venv/Scripts/python.exe -m pytest tests/test_capture_replaycode.py -q
.venv/Scripts/python.exe -m pytest -q
```

Expected: all PASS.

- [ ] **Step 6: Commit**

```bash
git add docs/capture/index.html tests/test_capture_replaycode.py
git commit -m "Check a read replay code against the league feed"
```

---

## Task 9: Live verification and documentation

**Files:**
- Modify: `ARCHITECTURE.md`, `CHANGELOG.md`

- [ ] **Step 1: Verify in a real browser**

```bash
.venv/Scripts/python.exe -m http.server 8000 --directory docs
```

Open `http://localhost:8000/capture/scrim.html`, hard-refresh, share the Overwatch window with a replay loaded, auto-calibrate, then press **Read code** in the panel. Confirm the field fills with the code printed on screen. Then start a map with the field blank and confirm it fills itself.

Repeat on `http://localhost:8000/capture/index.html`: select a *deliberately wrong* code, press **Read code**, and confirm it moves the selection to the right match and says so. **That is the feature's whole purpose — verify this case specifically, not just the happy path.**

- [ ] **Step 2: Record what actually happened**

Add the measured numbers from Task 5 to `tools/real_frame_eval/README.md`: frames, correct, no-read, wrong. If the live read behaved differently from the offline eval, say so there — the frames are 2026-07 and 2026-08 captures and the live HUD has differed from them before.

- [ ] **Step 3: Document it**

`ARCHITECTURE.md`, in the engine module table:

```markdown
| `engine/replaycode.js` | The replay code on the HUD banner: its Crockford Base32 alphabet, where it sits relative to the calibrated portrait strip, and whether a read is a code at all |
```

`CHANGELOG.md`, under a `### Added` heading for the date, saying what it does for the operator, what the gate was, and that a refused read is by design.

- [ ] **Step 4: Full verification**

```bash
.venv/Scripts/python.exe -m pytest -q
.venv/Scripts/python.exe tools/capture_divergence.py | grep -i "^shared"
node tools/real_frame_eval/code_parity.js
git status --short   # docs/capture/data.json must NOT appear
```

- [ ] **Step 5: Commit**

```bash
git add ARCHITECTURE.md CHANGELOG.md tools/real_frame_eval/README.md
git commit -m "Document reading the replay code off the screen"
```

---

## Self-review notes

**Spec coverage.** §2 geometry → Tasks 2, 3, 5. §3 alphabet and folding → Task 1. §4.1 module → Tasks 1–2. §4.2 read pipeline and worker restore → Task 7. §4.3 refuse rather than guess → Task 1 tests, Task 7 test. §4.4 snap to feed → Task 8. §4.5 scrim fill → Task 7. §4.6 on-demand trigger → Tasks 7–8 (no polling anywhere). §6 three proofs → Tasks 4 (eval), 5 (sweep), 6 (parity). §8 risks → Task 5 Step 2 stops on a knife-edge fit; Task 7 handles the uncalibrated case with a message.

**Not covered by a task, deliberately:** §7's out-of-scope list needs no work, and `refuseIfLeagueCode()` already runs inside `startMapNamed()` on the code passed to it, so a read code inherits the block with no change — verified in the current source rather than assumed.

**Known gap for the executor:** Task 3 Step 1 requires reading two frames by eye. If `234953`/`235003` turn out to show a different code from `234927`, put the real value in — a wrong truth entry makes a correct reader look broken, which is the worst possible way to be wrong here.

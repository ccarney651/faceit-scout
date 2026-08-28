# Scrim Hero Bans Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** One enforced hero ban per team, chosen in-game during setup and drawn on the spectator view as text, so the capture tool reads the bans instead of the operator remembering them.

**Architecture:** Two halves that meet at a text row on the HUD. The workshop half (`scrim_owdb.opy`) owns input, the three rules and enforcement via `setAllowedHeroes`. The capture half reads that row with OCR and prefills the panel's existing ban picker. They are independently testable and are built in that order reversed — JS first, because the `.opy` cannot be verified at the desk beyond compiling.

**Tech Stack:** OverPy (compiles to Overwatch Workshop), vanilla browser JS (no build step, `node:test` for units), tesseract.js for OCR, pytest as the suite of record.

**Spec:** `specs/2026-08-27-scrim-hero-bans-design.md` — read it before starting. It records what was verified in game and what was ruled out; this plan does not repeat the reasoning.

## Global Constraints

- **pytest is the suite of record.** `.venv/Scripts/python.exe -m pytest` must be green at every commit. JS unit tests run under it via `tests/test_capture_js_units.py`, which auto-discovers `docs/capture/**/*.test.js` — a new `.test.js` needs no registration.
- **Never call `w.recognize()` directly.** Every OCR read goes through `ocrRead(w, cv)`. A test fails if you do.
- **No IndexedDB version bump.** `bans` already exists on the map record. Bumping the schema from the wrong place is a documented footgun (`AGENTS.md` invariant 5).
- **No new place to register a hero.** The name index is built from `refs.json`, which both capture pages already load. `AGENTS.md` lists four registration points; do not create a fifth.
- **Exact-after-normalization matching only.** No edit distance, no fuzzy fallback. See design §4.3 — it converts a safe abstention into a plausible wrong answer.
- **The HUD renders UPPERCASE.** Confirmed in game. Never write a case-sensitive matcher.
- **`docs/` is the GitHub Pages web root.** No developer documentation there (`AGENTS.md` invariant 10).
- **The capture pages are forked.** Run `.venv/Scripts/python.exe tools/capture_divergence.py` before and after touching shared capture code.
- **The HUD row format, confirmed in game 2026-08-27:**
  `BANS  : SOMBRA | MAUGA` and `MAP   : SAMOA` — uppercase, colon-separated label, ` | ` between the two bans.

---

## File Structure

| File | Responsibility |
| --- | --- |
| `docs/capture/engine/banrow.js` (create) | Pure: normalize a hero name, build the name→GUID index, find a labelled row in OCR text, parse and shape-validate the bans. No DOM, no OCR, no globals. |
| `docs/capture/engine/banrow.test.js` (create) | `node:test` units for the above. Auto-discovered by pytest. |
| `docs/capture/scrim.html` (modify) | The `⌘ Read bans` button in the panel's bans row: crop, OCR, hand the text to `banrow.js`, fill `MAP_BANS` / `MAP_BANS_NONE`. |
| `tools/scrim_code/scrim_owdb.opy` (modify) | The ban phase: settings panel, keybind, R1/R2/R3, enforcement, timer clear, the two HUD rows. |
| `tools/scrim_code/scrim_owdb.txt` (regenerate) | Compiled output. Never hand-edited. |
| `ARCHITECTURE.md`, `CHANGELOG.md`, `specs/BACKLOG.md` (modify) | Record the feature and close the map-name item. |

`banrow.js` is deliberately separate from `heroes.js`: `heroes.js` is the role table shared with `docs/scrims.html`, and the viewer has no reason to carry an OCR parser.

---

### Task 1: The pure ban-row parser

**Files:**
- Create: `docs/capture/engine/banrow.js`
- Test: `docs/capture/engine/banrow.test.js`

**Interfaces:**
- Consumes: `OWDBHeroes.inferRole(name)` from `docs/capture/engine/heroes.js`, which returns `'Tank' | 'Damage' | 'Support' | null`.
- Produces, on `window.OWDBBanRow` (and `module.exports`):
  - `normalizeHeroName(s) -> string` — NFKD accent-fold, lowercase, strip non-alphanumerics.
  - `buildHeroIndex(catalogue) -> {normalizedName: {g, n}}` where `catalogue` is `[{n, g}]`. It carries the **canonical** name, not just the GUID — see the role-check note in Step 3.
  - `findRow(text, label) -> string|null` — the content after the FIRST `:` on the labelled line.
  - `parseBans(text, index, roleOf) -> {ok, bans, none, why}` where `bans` is `[{g, n}]` with `n` the canonical catalogue spelling.

- [ ] **Step 1: Write the failing test**

Create `docs/capture/engine/banrow.test.js`:

```js
const test = require('node:test');
const assert = require('node:assert');
const B = require('./banrow.js');
const H = require('./heroes.js');

// The catalogue shape refs.json produces, using the spellings it really writes.
const CAT = [
  { n: 'Sombra', g: 'g-sombra' }, { n: 'Mauga', g: 'g-mauga' },
  { n: 'DVa', g: 'g-dva' }, { n: 'Lucio', g: 'g-lucio' },
  { n: 'Torbjorn', g: 'g-torb' }, { n: 'Soldier 76', g: 'g-s76' },
  { n: 'Ana', g: 'g-ana' }, { n: 'Genji', g: 'g-genji' },
];
const IDX = B.buildHeroIndex(CAT);
const ROLE = H.inferRole;

test('the display spellings the workshop draws reach the refs.json entries', () => {
  // Verified in game 2026-08-27: the HUD draws these, refs.json stores the
  // right-hand column, and one normalization has to bridge them.
  assert.strictEqual(B.normalizeHeroName('D.VA'), B.normalizeHeroName('DVa'));
  assert.strictEqual(B.normalizeHeroName('LÚCIO'), B.normalizeHeroName('Lucio'));
  assert.strictEqual(B.normalizeHeroName('TORBJÖRN'), B.normalizeHeroName('Torbjorn'));
  assert.strictEqual(B.normalizeHeroName('SOLDIER: 76'), B.normalizeHeroName('Soldier 76'));
});

test('findRow pulls the labelled line out of a multi-line OCR read', () => {
  const text = 'OWDB SCRIM\nBANS  : SOMBRA | MAUGA\nMAP   : SAMOA\n';
  assert.strictEqual(B.findRow(text, 'BANS'), 'SOMBRA | MAUGA');
  assert.strictEqual(B.findRow(text, 'MAP'), 'SAMOA');
  assert.strictEqual(B.findRow(text, 'NOPE'), null);
});

test('two bans of different roles are accepted and resolved to guids', () => {
  const r = B.parseBans('BANS  : SOMBRA | MAUGA', IDX, ROLE);
  assert.strictEqual(r.ok, true);
  assert.strictEqual(r.none, false);
  assert.deepStrictEqual(r.bans.map(b => b.g), ['g-sombra', 'g-mauga']);
});

test('an explicit none is a fact, not a failure to read', () => {
  const r = B.parseBans('BANS  : NONE', IDX, ROLE);
  assert.strictEqual(r.ok, true);
  assert.strictEqual(r.none, true);
  assert.deepStrictEqual(r.bans, []);
});

test('a missing row abstains rather than reporting no bans', () => {
  const r = B.parseBans('MAP   : SAMOA', IDX, ROLE);
  assert.strictEqual(r.ok, false);
  assert.match(r.why, /could not find/i);
});

test('exactly one ban is a misread - the game cannot start that way', () => {
  const r = B.parseBans('BANS  : SOMBRA', IDX, ROLE);
  assert.strictEqual(r.ok, false);
  assert.match(r.why, /two|one/i);
});

test('two bans sharing a role is a misread - the workshop forbids it', () => {
  const r = B.parseBans('BANS  : SOMBRA | GENJI', IDX, ROLE);
  assert.strictEqual(r.ok, false);
  assert.match(r.why, /role/i);
});

test('the role check runs on the catalogue spelling, not the OCR text', () => {
  // inferRole knows "Soldier 76" and does NOT know "SOLDIER: 76". Taking the
  // role from the OCR string would skip R2 for every punctuated hero, which is
  // precisely the set this module exists to handle. Both of these are Damage.
  const r = B.parseBans('BANS  : SOLDIER: 76 | GENJI', IDX, ROLE);
  assert.strictEqual(r.ok, false);
  assert.match(r.why, /role/i);
});

test('a hero resolves to the catalogue spelling, not what the OCR read', () => {
  const r = B.parseBans('BANS  : D.VA | GENJI', IDX, ROLE);
  assert.strictEqual(r.ok, true);
  assert.deepStrictEqual(r.bans.map(b => b.n), ['DVa', 'Genji']);
});

test('an unreadable hero abstains instead of guessing a near match', () => {
  const r = B.parseBans('BANS  : SOMBKA | MAUGA', IDX, ROLE);
  assert.strictEqual(r.ok, false);
  assert.match(r.why, /SOMBKA/);
});
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `node --test docs/capture/engine/banrow.test.js`
Expected: FAIL — `Cannot find module './banrow.js'`

- [ ] **Step 3: Write the implementation**

Create `docs/capture/engine/banrow.js`:

```js
// docs/capture/engine/banrow.js
// Reading the workshop's ban row off the spectator HUD.
//
// The workshop draws one text row per map (specs/2026-08-27-scrim-hero-bans-design.md):
//
//     BANS  : SOMBRA | MAUGA
//     MAP   : SAMOA
//
// Confirmed in game 2026-08-27 - a bare Hero renders as its NAME, uppercase,
// with accents and punctuation intact. heroIcon() is the thing that draws a
// glyph, and the row deliberately does not use it.
//
// The label is a TEXTUAL anchor, not a geometric one. The caller OCRs a
// generous crop of the left column and hands the whole multi-line read here;
// findRow picks the line out. That is why the crop does not have to be
// precise, and it is the difference between this and the replay-code reader,
// where a mis-placed crop yields a well-formed WRONG code and needed five
// geometry probes to catch.
//
// Nothing here touches the DOM or tesseract, so it is unit-tested directly.

(function (global) {
  'use strict';

  // refs.json writes "DVa", "Soldier 76", "Lucio", "Torbjorn"; the game draws
  // "D.VA", "SOLDIER: 76", "LÚCIO", "TORBJÖRN". Folding accents, dropping
  // punctuation and lowercasing bridges every one of them, with zero
  // collisions across all 53 catalogue names (measured, design section 4.2).
  function normalizeHeroName(s) {
    return String(s == null ? '' : s)
      .normalize('NFKD')
      .replace(/[̀-ͯ]/g, '')
      .toLowerCase()
      .replace(/[^a-z0-9]/g, '');
  }

  // Maps to the WHOLE entry, not just the guid. The role check has to run on
  // the catalogue spelling: inferRole knows "Soldier 76" and does not know
  // "SOLDIER: 76", so resolving the role from the OCR text would silently skip
  // R2 for every hero whose display name carries punctuation - D.Va, Lúcio,
  // Torbjörn, Soldier: 76 - which is exactly the set this module exists for.
  function buildHeroIndex(catalogue) {
    var index = {};
    (catalogue || []).forEach(function (h) {
      if (!h || !h.n || !h.g) return;
      var key = normalizeHeroName(h.n);
      if (key) index[key] = { g: h.g, n: h.n };
    });
    return index;
  }

  // The label may be followed by spaces before the colon, and OCR routinely
  // adds or drops one. Anchor on the word, take everything after the colon.
  function findRow(text, label) {
    var lines = String(text == null ? '' : text).split(/[\r\n]+/);
    var wanted = normalizeHeroName(label);
    for (var i = 0; i < lines.length; i++) {
      var at = lines[i].indexOf(':');
      if (at === -1) continue;
      if (normalizeHeroName(lines[i].slice(0, at)) !== wanted) continue;
      return lines[i].slice(at + 1).trim();
    }
    return null;
  }

  function fail(why) { return { ok: false, bans: [], none: false, why: why }; }

  // Validation is by SHAPE, not by OCR confidence: the workshop enforced these
  // rules, so a read that breaks one is a misread rather than an unusual scrim.
  function parseBans(text, index, roleOf) {
    var row = findRow(text, 'BANS');
    if (row === null) return fail('could not find the BANS row on screen');

    if (normalizeHeroName(row) === 'none') {
      return { ok: true, bans: [], none: true, why: null };
    }

    var parts = row.split('|').map(function (p) { return p.trim(); })
      .filter(function (p) { return p.length; });
    if (parts.length !== 2) {
      return fail('expected two bans, read ' + parts.length
        + ' - a map cannot start with one, so this is a misread');
    }

    var bans = [];
    for (var i = 0; i < parts.length; i++) {
      var hit = index[normalizeHeroName(parts[i])];
      if (!hit) return fail('no hero matches "' + parts[i] + '"');
      bans.push({ g: hit.g, n: hit.n });
    }

    // roleOf sees the canonical name, so this check actually runs.
    var roleA = roleOf(bans[0].n), roleB = roleOf(bans[1].n);
    if (roleA && roleB && roleA === roleB) {
      return fail('both bans read as the ' + roleA + ' role, which the ban phase forbids');
    }
    return { ok: true, bans: bans, none: false, why: null };
  }

  var Mod = {
    normalizeHeroName: normalizeHeroName,
    buildHeroIndex: buildHeroIndex,
    findRow: findRow,
    parseBans: parseBans,
  };

  if (typeof module !== 'undefined' && module.exports) module.exports = Mod;
  else global.OWDBBanRow = Mod;
})(typeof self !== 'undefined' ? self : this);
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `node --test docs/capture/engine/banrow.test.js`
Expected: PASS, 8 tests.

Note `parseBans` resolves the ban name through the index but stores the **OCR'd** spelling in `n`. That is intentional for the chip label to read as the operator saw it; the GUID is what the record keys on.

- [ ] **Step 5: Confirm pytest picks the new suite up**

Run: `.venv/Scripts/python.exe -m pytest tests/test_capture_js_units.py -q`
Expected: PASS. It globs `docs/capture/**/*.test.js`, so no registration was needed.

- [ ] **Step 6: Commit**

```bash
git add docs/capture/engine/banrow.js docs/capture/engine/banrow.test.js
git commit -m "Read the workshop's ban row without guessing at a near match"
```

---

### Task 2: Wire the read into the capture panel

**Files:**
- Modify: `docs/capture/scrim.html` — add `engine/banrow.js` to the script list (~line 437), the CSP if needed, and a `⌘ Read bans` button in the panel's bans row (`renderBansInto`, ~line 1640).
- Test: `tests/test_capture_scrim.py`

**Interfaces:**
- Consumes: `OWDBBanRow.buildHeroIndex`, `OWDBBanRow.parseBans` (Task 1); existing `heroCatalog()`, `ocrWorker()`, `ocrRead(w, cv)`, `grabFrame()`, `boxes.a`, `MAP_BANS`, `MAP_BANS_NONE`, `setNoBans()`, `clearBans()`, `renderBans()`, `snapMsg(text, isError)`.
- Produces: `readBanRow()` returning the `parseBans` result, and `LAST_BAN_READ` holding `{why, raw}` for the failure message.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_capture_scrim.py`:

```python
def test_scrim_page_loads_the_ban_row_parser() -> None:
    """A script the page uses but never loads is invisible to pytest and fatal
    in the browser - the CSP has silently broken three scripts already."""
    page = (Path(__file__).resolve().parents[1]
            / "docs" / "capture" / "scrim.html").read_text(encoding="utf-8")
    assert "engine/banrow.js" in page, "banrow.js is used but never loaded"
    assert "OWDBBanRow" in page, "banrow.js is loaded but never called"


def test_scrim_page_reads_bans_through_the_deadline_wrapped_ocr() -> None:
    """ocrWorker()'s timeout only covers LOADING tesseract. A recognize() that
    stalls afterwards never returns and takes every other read down with it."""
    page = (Path(__file__).resolve().parents[1]
            / "docs" / "capture" / "scrim.html").read_text(encoding="utf-8")
    body = page[page.index("async function readBanRow"):]
    body = body[:body.index("\n}")]
    assert "ocrRead(" in body, "the ban read must go through ocrRead"
    assert ".recognize(" not in body, "call ocrRead, never recognize directly"
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/test_capture_scrim.py -k ban_row -q`
Expected: FAIL — `engine/banrow.js is used but never loaded`.

- [ ] **Step 3: Record the divergence baseline before touching shared code**

Run: `.venv/Scripts/python.exe tools/capture_divergence.py`
Keep the output. The number must not rise in step 6.

- [ ] **Step 4: Implement**

Add the script to the existing one-line list in `docs/capture/scrim.html` (~line 437), immediately after `engine/heroes.js`:

```html
<script src="engine/banrow.js"></script>
```

Add the reader beside the other reads (near `readReplayCode`, ~line 1510):

```js
// ---------- reading the workshop's ban row ----------
//
// A GENEROUS crop, on purpose. The label is a textual anchor, so the crop only
// has to CONTAIN the row - unlike the replay code, where the crop has to land
// on it and being 2% off returns a well-formed wrong answer. Page-seg mode 6
// keeps the lines separate so findRow can pick one out.
let LAST_BAN_READ={why:null, raw:null};
async function readBanRow(){
  LAST_BAN_READ={why:null, raw:null};
  if(!vid.srcObject){ LAST_BAN_READ.why='share your screen first'; return null; }
  if(!boxes.a){ LAST_BAN_READ.why='calibrate first — the row is found in the left column'; return null; }
  const frame=grabFrame();
  // The workshop draws its rows above the portrait strip, in the same column.
  const b=boxes.a;
  const cv=document.createElement('canvas');
  const x=Math.max(0, Math.round(b.x - b.w*0.10));
  const y=0;
  const w=Math.round(b.w*1.30);
  const h=Math.max(1, Math.round(b.y));
  cv.width=w; cv.height=h;
  cv.getContext('2d').drawImage(frame, x, y, w, h, 0, 0, w, h);
  const worker=await ocrWorker();
  await worker.setParameters({ tessedit_pageseg_mode:'6' });
  const {data}=await ocrRead(worker, cv);
  await worker.setParameters({ tessedit_pageseg_mode:'7' });
  const text=(data&&data.text)||'';
  LAST_BAN_READ.raw=text;
  const res=OWDBBanRow.parseBans(text, OWDBBanRow.buildHeroIndex(heroCatalog()), OWDBHeroes.inferRole);
  if(!res.ok){ LAST_BAN_READ.why=res.why; return null; }
  return res;
}
```

Add the button in `renderBansInto` (~line 1651), directly after the `no bans this map` button is appended:

```js
  // Prefill from the screen. It fills the picker rather than replacing it:
  // an abstention leaves the grid exactly as it was and the operator picks by
  // hand, which is how every scrim worked before this existed.
  const read=d.createElement('button'); read.type='button';
  read.textContent='⌘ Read bans'; read.className='ghost';
  read.title='Read the ban row off the workshop HUD and fill the picker';
  read.onclick=async()=>{
    const res=await readBanRow();
    if(!res){ snapMsg(esc(LAST_BAN_READ.why||'could not read the ban row'), true); return; }
    if(res.none){ setNoBans(); renderBans(); snapMsg('read: no bans this map'); return; }
    // `by` stays null - the workshop knows Team 1 and Team 2, this page knows
    // us and them, and nothing here maps between them. "by either" is already
    // a supported value and a wrong attribution is worse than none.
    MAP_BANS=res.bans.map(b=>({g:b.g, n:heroName(b.g)||b.n, by:null}));
    MAP_BANS_NONE=false;
    renderBans();
    snapMsg('read '+res.bans.map(b=>b.n).join(' + '));
  };
  box.appendChild(read);
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `.venv/Scripts/python.exe -m pytest tests/test_capture_scrim.py tests/test_capture_csp.py tests/test_page_csp_permits_own_scripts.py -q`
Expected: PASS. The CSP test is included because a new `<script src>` on a page whose policy lacks `'self'` renders it blank, which has happened three times.

- [ ] **Step 6: Confirm divergence did not rise**

Run: `.venv/Scripts/python.exe tools/capture_divergence.py`
Expected: the same count as step 3. This change is scrim-only; `index.html` has no ban row.

- [ ] **Step 7: Commit**

```bash
git add docs/capture/scrim.html tests/test_capture_scrim.py
git commit -m "Fill the ban picker from the screen, and abstain when unsure"
```

---

### Task 3: The ban phase in the workshop code

**Files:**
- Modify: `tools/scrim_code/scrim_owdb.opy`
- Regenerate: `tools/scrim_code/scrim_owdb.txt`

**Interfaces:**
- Consumes: existing `Keybind_ButtonArray`, `Keybind_Command`, `Colour_TextTypeA/B/C`, `ReadyUp_PlayerReady`, `Setup_SetupTimeOverride`.
- Produces: globals `Ban_Enabled`, `Ban_Team1`, `Ban_Team2` (Hero or `null`), `Keybind_BanHero`; the macro `Ban_SameRole(hero, other)`; and the subroutine `Ban_Apply()`. The R3 start guard is written inline in both start rules (Step 5) rather than factored out — a macro would be inlined into both anyway, and naming it would hide that there are two copies to keep in step.

Read design §3 in full before starting. The three rules and the fail-open behaviour are the whole point of this task.

- [ ] **Step 1: Add the settings panel and variables**

In the settings rules block (~line 135), add a new rule. Panel `1.` is free — the strip removed Language, Log Generator and Debug, so the in-game list currently reads 2,3,4,5,7:

```python
rule "Settings: Hero Ban Options":
    Ban_Enabled = createWorkshopSettingBool("1. Hero Bans", "Enable Hero Bans", true)
```

Declare the globals beside the others (~line 99), using free indices:

```python
globalvar Ban_Enabled 39
globalvar Ban_Team1 40
globalvar Ban_Team2 41
globalvar Keybind_BanHero 42
```

Add the keybind to the `7. Keybinds` rule (~line 176). Index 8 is Melee. **Not Reload** — `Keybind_Ready` already uses it, so `Interact + Reload` is Ready Up:

```python
    Keybind_BanHero = Keybind_ButtonArray[createWorkshopSettingEnum("7. Keybinds", "Ban Hero", 8, ["Primary Fire", "Secondary Fire", "Ability 1", "Ability 2", "Ultimate", "Interact", "Jump", "Crouch", "Melee", "Reload"], 4)]
```

- [ ] **Step 2: Verify it still compiles**

Run: `cd tools/scrim_code && npm run build`
Expected: no error, `scrim_owdb.txt` rewritten.

- [ ] **Step 3: Add the ban input rule with R1 and R2**

```python
rule "Bans: Toggle Ban On Current Hero":
    @Event eachPlayer
    @Condition Ban_Enabled == true
    @Condition isInSetup() == true
    @Condition eventPlayer.isHoldingButton(Keybind_Command) == true
    @Condition eventPlayer.isHoldingButton(Keybind_BanHero) == true

    # R1: one ban per team, so a second confirm REPLACES the first.
    # Pressing again on your own banned hero clears it, which is the only route
    # back to "neither team banned" once a team has banned - and R3 makes that
    # a state teams need to be able to reach.
    if eventPlayer.getTeam() == Team.1 and Ban_Team1 == eventPlayer.getHero():
        Ban_Team1 = null
    elif eventPlayer.getTeam() == Team.2 and Ban_Team2 == eventPlayer.getHero():
        Ban_Team2 = null
    # R2: the two bans may not share a role. Checked on EVERY confirm including
    # a change, or team 1 could ban a tank, wait for team 2 to ban a tank, then
    # switch onto one and collide.
    elif Ban_SameRole(eventPlayer.getHero(), Ban_Team2 if eventPlayer.getTeam() == Team.1 else Ban_Team1):
        smallMessage(eventPlayer, "That role is already banned by the other team")
    elif eventPlayer.getTeam() == Team.1:
        Ban_Team1 = eventPlayer.getHero()
    else:
        Ban_Team2 = eventPlayer.getHero()
    Ban_Apply()
    waitUntil(not eventPlayer.isHoldingButton(Keybind_BanHero), 1)
```

Put these above the rule. **`Ban_SameRole` must be a `macro`, not a `def`** — Workshop
subroutines take no parameters and return no value, so a `def` cannot express
this. A `macro` is inlined into the AST and evaluates to a value:

```python
macro Ban_SameRole(hero, other):
    other != null and ((hero in getTankHeroes() and other in getTankHeroes())
        or (hero in getDamageHeroes() and other in getDamageHeroes())
        or (hero in getSupportHeroes() and other in getSupportHeroes()))


def Ban_Apply():
    @Name "Subroutine: Apply hero bans"
    # Enforcement. "If a player's current hero becomes unavailable, the player
    # is forced to choose a different hero and respawn" - which doubles as the
    # visible confirmation that the ban took.
    #
    # A parameterless subroutine reading the globals, because that is the only
    # shape Workshop subroutines have. The filter needs no null branch: `null`
    # never equals a hero, so one ban, two bans and none all fall out of the
    # same expression.
    if Ban_Team1 == null and Ban_Team2 == null:
        getAllPlayers().resetHeroAvailability()
    else:
        getAllPlayers().setAllowedHeroes(getAllHeroes().filter(
            lambda h: h != Ban_Team1 and h != Ban_Team2))
```

`.filter(lambda ...)` rather than `.exclude(...)`: filter is the idiom already
used throughout `dkeeh.opy` and it compiles to `Filtered Array`.

- [ ] **Step 4: Verify it compiles**

Run: `cd tools/scrim_code && npm run build`
Expected: no error.

This code was compile-verified against the bundled OverPy before the plan was
written, and the output checked to contain
`Set Player Allowed Heroes(All Players(All Teams), Filtered Array(All Heroes, ...))`
and `Array Contains(All Tank Heroes, ...)`. If it fails here, the cause is
integration with the surrounding file, not the snippet.

One known cost: because a macro is inlined, the
`Ban_Team2 if ... else Ban_Team1` sub-expression is emitted **four times** in the
compiled condition. Harmless at this size — the whole mode is 50 KB against
Scrimtime's 142 KB — but if element count ever matters, assign it to a global
first and pass that.

- [ ] **Step 5: Add R3 to BOTH start rules**

Add the same guard to `Setup: Both Teams Ready, Start Match (Captain-Only Mode)` (~line 346) **and** `(All Players Mode)` (~line 369), directly after the existing minimum-players guard. **Both, or a lobby in the other ready mode starts with one ban and the record is silently wrong:**

```python
    if Ban_Enabled and (Ban_Team1 == null) != (Ban_Team2 == null):
        smallMessage(getAllPlayers(), "Both teams ready, but only one hero is banned - ban a second or clear it")
        return
```

- [ ] **Step 6: Add the reset and the timer fail-open**

```python
rule "Bans: Reset At Setup Start":
    @Condition isInSetup() == true
    # At phase START, not only at end, so each map's bans are independent of
    # whatever the previous map left behind.
    Ban_Team1 = null
    Ban_Team2 = null
    getAllPlayers().resetHeroAvailability()


rule "Bans: Clear A Lone Ban Before The Timer Expires":
    @Condition Ban_Enabled == true
    @Condition isInSetup() == true
    @Condition getMatchTime() <= 5
    @Condition (Ban_Team1 == null) != (Ban_Team2 == null)

    # R3's guard only blocks the READY path; setup time expiring ends setup
    # regardless. Clearing keeps the invariant (no map starts with exactly one
    # ban) while failing toward no-bans rather than stalling a live scrim.
    Ban_Team1 = null
    Ban_Team2 = null
    Ban_Apply()
    smallMessage(getAllPlayers(), "Only one hero was banned - bans cleared for this map")
```

- [ ] **Step 7: Add the two HUD rows**

Sort orders 0.2 and 0.3 place these above the ready-up list (2.x/4.x) and below the setup header (0.1):

```python
rule "Bans: Spectator HUD Row":
    # SpecVisibility.ALWAYS so it renders for spectators AND in replays, which
    # is where captures are actually taken from. The label is the capture
    # tool's textual anchor - do not remove the colon or reword "BANS".
    # A bare Hero renders as its NAME (confirmed in game 2026-08-27); heroIcon()
    # would draw a glyph that OCR cannot read.
    hudSubheader(getAllPlayers(), "BANS  : {0}".format(
                     "NONE" if Ban_Team1 == null and Ban_Team2 == null else
                     "{0} | {1}".format(Ban_Team1, Ban_Team2)),
                 HudPosition.LEFT, 0.2, Colour_TextTypeA,
                 HudReeval.VISIBILITY_AND_STRING, SpecVisibility.ALWAYS)
    hudSubheader(getAllPlayers(), "MAP   : {0}".format(getCurrentMap()),
                 HudPosition.LEFT, 0.3, Colour_TextTypeA,
                 HudReeval.VISIBILITY_AND_STRING, SpecVisibility.ALWAYS)
```

The `NONE` branch is not cosmetic: an absent row means "could not read" and a present row reading `NONE` means "known, no bans". `parseBans` depends on the distinction.

- [ ] **Step 8: Compile and run the full suite**

Run: `cd tools/scrim_code && npm run build`
Then: `.venv/Scripts/python.exe -m pytest -q`
Expected: both clean.

- [ ] **Step 9: Commit**

```bash
git add tools/scrim_code/scrim_owdb.opy tools/scrim_code/scrim_owdb.txt
git commit -m "Ban one hero per team in game, and draw it where capture can read it"
```

---

### Task 4: Documentation

**Files:**
- Modify: `ARCHITECTURE.md` (§7 Scrims), `CHANGELOG.md`, `specs/BACKLOG.md`, `tools/scrim_code/README.md`

- [ ] **Step 1: Record the feature in `ARCHITECTURE.md` §7**

Add under the scrims gotchas, after the league-code-block paragraph:

```markdown
**Hero bans are read off the workshop HUD, not remembered.**
`tools/scrim_code/scrim_owdb.opy` runs a ban phase during setup: one hero per
team, enforced with `setAllowedHeroes`, the two bans forced to different roles,
and the map blocked from starting with exactly one. It draws
`BANS  : SOMBRA | MAUGA` and `MAP   : SAMOA` with `SpecVisibility.ALWAYS`, so
both survive into the replay where captures are taken.
`docs/capture/engine/banrow.js` finds those rows by their label in a multi-line
OCR read — a TEXTUAL anchor, so the crop only has to contain the row rather than
land on it. It validates by shape (two bans or none, never one; different roles;
both resolving to known heroes) and abstains otherwise, filling the panel's ban
picker rather than replacing it. Matching is exact after normalization; fuzzy
matching would turn a safe abstention into a plausible wrong answer.
```

- [ ] **Step 2: Close the map-name item in `specs/BACKLOG.md`**

Replace the "Map-name verification is stubbed" bullet with:

```markdown
- **Map-name verification: answerable now.** The open question was whether the
  map name is reliably on the observer HUD at all. It is not — but the scrim
  workshop code draws it (`MAP   : SAMOA`, confirmed in game 2026-08-27), so
  for scrims the map can be verified against the HUD rather than trusting the
  operator's panel selection. League captures still have no such row, so the
  stub stays for them.
```

- [ ] **Step 3: Add the `CHANGELOG.md` entry**

Under a dated `### Added`:

```markdown
- **Hero bans are captured from the game instead of remembered.** The scrim
  workshop code gains a ban phase: each team bans one hero during setup by
  switching to it and pressing Interact + Melee, the ban is enforced for all ten
  players, the two bans must be different roles, and a map cannot start with
  exactly one ban. The bans are drawn on the spectator view, so the capture
  panel's *Read bans* button fills the picker from the screen. It abstains
  rather than guessing, and the manual picker is unchanged — which matters,
  because bans are only recorded in lobbies running this workshop code.
```

- [ ] **Step 4: Add the ban keybind to the README control table**

In `tools/scrim_code/README.md`, add a row and a Kept bullet:

```markdown
| Ban hero (during setup) | Interact + Melee |
```

- [ ] **Step 5: Verify and commit**

Run: `.venv/Scripts/python.exe -m pytest -q`
Expected: PASS, including `tests/test_docs_links.py`.

```bash
git add ARCHITECTURE.md CHANGELOG.md specs/BACKLOG.md tools/scrim_code/README.md
git commit -m "Document the scrim ban phase and what it does not cover"
```

---

## In-game validation — the part no task can close

These need Overwatch and the operator. Design §6 carries the full list; the load-bearing one is already done (a bare `Hero` renders as text, confirmed 2026-08-27).

1. The ban row and MAP row render **in the replay viewer**, not just live. Captures are taken from replays, so this is the real target.
2. The rows do not collide with the spectator scoreboard, which shares the left column. The voice-chat name card that overlapped the probe does not exist in replays.
3. OCR reads the row at the operator's resolution — run *Read bans* against a real captured scrim.
4. `setAllowedHeroes` removes the hero for all ten players and force-swaps anyone on it.
5. The R3 guard blocks the start in **both** ready modes.
6. The setup timer expiring with one ban clears it.

Until 1–3 pass, the feature is built but unproven. That is the same gap the rest of scrim mode carries: every analysis is proven against fixtures rather than a real captured scrim.

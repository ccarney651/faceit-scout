# OWDB UI Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the current generic-indigo, system-font visual design across the dashboard, capture app, and scrims page with the approved "Broadcast Violet" system (new color tokens, Space Grotesk/Inter typography, flat-line/accent-bar shape, the `[ow]db` wordmark, a unified toggle component) via one shared `docs/theme.css`, without changing any functionality, IA, or data logic.

**Architecture:** One new file, `docs/theme.css`, becomes the single source of truth for tokens, fonts, and the small set of primitives that are genuinely duplicated across pages today (`.card`, `.btn`, `.prodname` wordmark, `.sidetoggle`/`.sidebox`, `nav`, `.eyebrow`, the body reset). `docs/scrims.html` and `docs/capture/*.html` `<link>` it directly. `docs/index.html` cannot — an existing test requires it stay a single self-contained file — so `faceit_sync/_dashboard.py` inlines the same file's content (fonts base64-embedded) into the assembled `<style>` block at build time instead. Everything else (tables, chips, tags, pills, and every dashboard/capture/scrims-specific component) is left as-is: it already consumes the same CSS custom properties theme.css redefines, so it re-themes automatically with zero edits.

**Tech Stack:** Plain HTML/CSS, no build step or bundler (existing convention). Python 3 for the dashboard's template-assembly step (`faceit_sync/_dashboard.py`). Self-hosted Google Fonts (Space Grotesk, Inter) as `.woff2`.

## Global Constraints

- `docs/index.html` must remain byte-for-byte self-contained: `tests/test_export.py::test_export_html_is_self_contained_and_valid` asserts no `<link rel="stylesheet">`, no `url(http…)`, no non-`canonical`/`icon` `<link>` rel, and no unexpected external hosts. Never violate this for the dashboard build.
- Run `pytest tests/test_export.py::test_dashboard_javascript_is_syntactically_valid` after every edit to a `faceit_sync/dashboard/*` part file (project convention, CLAUDE.md).
- Run the full `pytest` suite and `mypy --strict faceit_sync` before any commit that touches `faceit_sync/`.
- Never hand-edit `docs/index.html` — only regenerate via `faceit-sync export` from a local (throwaway, gitignored) DB, or inspect the assembled `HTML_TEMPLATE` directly. The live `docs/index.html` is CI's to write.
- For every dashboard/capture/scrims change, verify visually before committing: build the real artifact, share a `file://` path plus a headless-Edge screenshot (`msedge --headless --screenshot=FILE "file:///…#tab"`), per the design spec's rollout plan.
- Colors/fonts/shapes below are exact values from `specs/2026-08-10-owdb-ui-redesign-design.md` — do not improvise different hex values.
- Nothing gets pushed to `origin` without explicit user sign-off (standing instruction).

---

## File Structure

```
docs/
  theme.css                 [new]  shared tokens, fonts, .card/.btn/.prodname/.sidetoggle/nav/.eyebrow/body-reset
  fonts/
    space-grotesk-600.woff2 [new]
    space-grotesk-700.woff2 [new]
    inter-400.woff2         [new]
    inter-500.woff2         [new]
    inter-600.woff2         [new]
    inter-700.woff2         [new]
  index.html                 (generated — not edited directly)
  scrims.html                [modify] link theme.css, delete duplicated CSS, update wordmark/toggle markup
  capture/
    index.html                [modify] link ../theme.css, delete duplicated CSS, update wordmark/toggle markup
    scrim.html                 [modify] link ../theme.css, delete duplicated CSS, update wordmark/toggle markup

faceit_sync/
  dashboard/
    head.html                [modify] delete duplicated CSS, add __THEME_CSS__ marker, update wordmark/toggle markup
  _dashboard.py                [modify] read docs/theme.css + docs/fonts/*.woff2, base64-embed fonts, inline into head.html's __THEME_CSS__ marker

tests/
  test_export.py               [modify] add a test asserting the dashboard's inlined theme still passes the self-contained check with the new fonts/tokens present

CLAUDE.md                     [modify, last task] document docs/theme.css as the shared source of truth
```

**What is intentionally NOT touched:** table/chip/tag/pill/nav-content CSS beyond what's listed above, all page-specific components (radar chart, draft simulator, playoffs bracket, match cards, capture's video-capture stage/calibration/toast/modal/tour, scrims' scrim-card/map-row), all JS logic, all routing, all data flow. These already consume the CSS custom properties theme.css redefines, so they re-theme automatically.

---

## Task 1: Self-hosted font files

**Files:**
- Create: `docs/fonts/space-grotesk-600.woff2`
- Create: `docs/fonts/space-grotesk-700.woff2`
- Create: `docs/fonts/inter-400.woff2`
- Create: `docs/fonts/inter-500.woff2`
- Create: `docs/fonts/inter-600.woff2`
- Create: `docs/fonts/inter-700.woff2`

**Interfaces:**
- Produces: six `.woff2` files at the exact paths above, each a single-family/single-weight/latin-subset WOFF2. Task 2's `@font-face` rules and Task 3's base64-embedding step reference these exact filenames — do not rename them.

This is an asset-acquisition step, not a code step — there is no way to "write code" that produces valid font binary data, so the deliverable is the files themselves at the exact paths, verified by presence and format.

- [ ] **Step 1: Download the fonts**

Use [google-webfonts-helper](https://gwfh.mranftl.com/fonts) (mirrors Google Fonts, gives direct woff2-only downloads without extra weights):
- Space Grotesk → select weights **600, 700** → "modern" (woff2 only) → download.
- Inter → select weights **400, 500, 600, 700** → "modern" (woff2 only) → download.

Rename the downloaded files to match the exact filenames listed above and place them in `docs/fonts/` (create the directory if it doesn't exist).

- [ ] **Step 2: Verify the files are valid WOFF2**

Run:
```bash
for f in docs/fonts/*.woff2; do file "$f"; done
```
Expected: each line reports something containing `Web Open Font Format` (or, if `file` doesn't recognize woff2 on this system, at minimum confirm each file is non-empty and starts with the 4-byte magic `wOF2`):
```bash
for f in docs/fonts/*.woff2; do head -c4 "$f" | od -c | head -1; done
```
Expected output for every file: `w   O   F   2` as the first four bytes.

- [ ] **Step 3: Commit**

```bash
git add docs/fonts/
git commit -m "Add self-hosted Space Grotesk + Inter font files for OWDB redesign"
```

---

## Task 2: Create `docs/theme.css`

**Files:**
- Create: `docs/theme.css`

**Interfaces:**
- Consumes: the six font files from Task 1 (referenced by relative `url('fonts/…woff2')`).
- Produces: CSS custom properties `--font-display`, `--font-body`, `--bg`, `--surface`, `--surface2`, `--fg`, `--muted`, `--faint`, `--line`, `--line2`, `--accent`, `--accent-bright`, `--accent-weak`, `--tank`, `--damage`, `--support`, `--good`, `--mid`, `--bad`, `--shadow` (all consumed by every downstream task and by every existing page-specific rule in all four surfaces — same names as today, new values). Also produces classes `.card`, `.btn`, `.btn.primary`, `.prodname` (with `.wordmark`/`.br`/`.ow`/`.db`/`.sub` children), `.sidetoggle`/`.sidebox`, `nav`/`nav button`, `.eyebrow`, plus the `body`/`*`/`html`/`.tnum` base reset — all consumed by Tasks 3–6.

- [ ] **Step 1: Write `docs/theme.css`**

```css
/* docs/theme.css — OWDB shared design tokens + primitives.
   Linked directly by docs/scrims.html and docs/capture/*.html.
   Inlined at build time into docs/index.html by faceit_sync/_dashboard.py
   (with fonts base64-embedded for that build only), because the exported
   dashboard must stay a single self-contained file — see
   tests/test_export.py::test_export_html_is_self_contained_and_valid.
   Everything else (tables, chips, tags, pills, and every page-specific
   component) stays defined per-page; it already reads these same custom
   properties, so it re-themes automatically without being duplicated here. */

@font-face{font-family:'Space Grotesk';font-weight:600;font-style:normal;font-display:swap;src:url('fonts/space-grotesk-600.woff2') format('woff2')}
@font-face{font-family:'Space Grotesk';font-weight:700;font-style:normal;font-display:swap;src:url('fonts/space-grotesk-700.woff2') format('woff2')}
@font-face{font-family:'Inter';font-weight:400;font-style:normal;font-display:swap;src:url('fonts/inter-400.woff2') format('woff2')}
@font-face{font-family:'Inter';font-weight:500;font-style:normal;font-display:swap;src:url('fonts/inter-500.woff2') format('woff2')}
@font-face{font-family:'Inter';font-weight:600;font-style:normal;font-display:swap;src:url('fonts/inter-600.woff2') format('woff2')}
@font-face{font-family:'Inter';font-weight:700;font-style:normal;font-display:swap;src:url('fonts/inter-700.woff2') format('woff2')}

:root{
  --font-display:'Space Grotesk',ui-sans-serif,system-ui,-apple-system,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;
  --font-body:'Inter',ui-sans-serif,system-ui,-apple-system,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;
  color-scheme:light;
  --bg:#f7f5fb; --surface:#ffffff; --surface2:#eeeaf7; --fg:#1c1730; --muted:#5a5270;
  --faint:#867a99; --line:#e2dcf0; --line2:#d3caea;
  --accent:#7c3aed; --accent-bright:#6d28d9; --accent-weak:rgba(124,58,237,.10);
  --tank:#3f80c4; --damage:#d5563f; --support:#33a06a;
  --good:#1f9d61; --mid:#b8860b; --bad:#cf4b36;
  --shadow:0 1px 2px rgba(16,24,40,.06),0 1px 3px rgba(16,24,40,.05);
}
@media (prefers-color-scheme: dark){
  :root{color-scheme:dark;--bg:#130f24;--surface:#1e1730;--surface2:#241d3a;--fg:#f0e9fb;--muted:#cfc7e2;
    --faint:#8f7ea8;--line:#2e2846;--line2:#3a3358;--accent:#a855f7;--accent-bright:#e2b8ff;--accent-weak:rgba(216,111,255,.15);
    --tank:#5a9bd8;--damage:#e9694f;--support:#46b57c;--good:#34b877;--mid:#d3a02a;--bad:#e5624a;
    --shadow:0 1px 2px rgba(0,0,0,.3);}
}
:root[data-theme="dark"]{color-scheme:dark;--bg:#130f24;--surface:#1e1730;--surface2:#241d3a;--fg:#f0e9fb;--muted:#cfc7e2;
  --faint:#8f7ea8;--line:#2e2846;--line2:#3a3358;--accent:#a855f7;--accent-bright:#e2b8ff;--accent-weak:rgba(216,111,255,.15);
  --tank:#5a9bd8;--damage:#e9694f;--support:#46b57c;--good:#34b877;--mid:#d3a02a;--bad:#e5624a;
  --shadow:0 1px 2px rgba(0,0,0,.3);}
:root[data-theme="light"]{color-scheme:light;--bg:#f7f5fb;--surface:#ffffff;--surface2:#eeeaf7;--fg:#1c1730;--muted:#5a5270;
  --faint:#867a99;--line:#e2dcf0;--line2:#d3caea;--accent:#7c3aed;--accent-bright:#6d28d9;--accent-weak:rgba(124,58,237,.10);
  --tank:#3f80c4;--damage:#d5563f;--support:#33a06a;--good:#1f9d61;--mid:#b8860b;--bad:#cf4b36;
  --shadow:0 1px 2px rgba(16,24,40,.06),0 1px 3px rgba(16,24,40,.05);}

*{box-sizing:border-box}
html{-webkit-text-size-adjust:100%}
body{margin:0;background:var(--bg);color:var(--fg);font-variant-numeric:tabular-nums;
  font-family:var(--font-body);font-size:14px;line-height:1.5;-webkit-font-smoothing:antialiased}
.tnum{font-variant-numeric:tabular-nums}
h1,h2,h3,.section-h h2,.tile .n,.gsc,.pname,.cmp-name,.brand h1{font-family:var(--font-display)}

.eyebrow{font-size:10.5px;font-weight:700;text-transform:uppercase;letter-spacing:.07em;color:var(--faint);margin:0 0 6px}

/* card: flat surface, thin border, left accent bar. Every component that
   hand-rolls its own card-like border/background (.profcard, .funnel,
   .snode, .gcard, .pcard, .uprow, details.mapblk, …) already reads
   --line/--surface/--accent and re-themes on its own; only the literal
   .card class needs its shape redefined here. */
.card{background:var(--surface);border:1px solid var(--line);border-left:3px solid var(--accent);
  border-radius:4px;padding:12px 14px;box-shadow:none}

/* buttons: outlined by default (matches the approved mockup); .primary is
   an available filled variant for a page's one standout CTA, opt-in. */
.btn{cursor:pointer;font-weight:650;font:inherit;background:transparent;color:var(--accent-bright);
  border:1px solid var(--accent);border-radius:4px;padding:8px 11px}
.btn:hover{background:var(--accent-weak)}
.btn.primary{background:var(--accent);color:#fff;border-color:transparent}
.btn.primary:hover{filter:brightness(1.06);background:var(--accent)}

/* wordmark: lowercase "owdb" in brackets, split-weight. Markup:
   <span class="prodname"><span class="wordmark"><span class="br">[</span><span class="ow">ow</span><span class="db">db</span><span class="br">]</span></span><span class="sub">FACEIT League</span></span> */
.prodname{display:flex;align-items:baseline;gap:8px;margin-bottom:2px}
.prodname .wordmark{font-family:var(--font-display);font-size:15px;font-weight:700;letter-spacing:.02em}
.prodname .br{color:var(--accent)}
.prodname .ow{color:var(--accent-bright);font-weight:700}
.prodname .db{color:var(--faint);font-weight:500}
.prodname .sub{font-size:11px;letter-spacing:.08em;color:var(--faint);font-weight:600;text-transform:uppercase}

/* unified segmented-control toggle — the one pattern for both the
   League/Scrims switch and the Data/Capture switch, replacing the old
   separate .navcap/.navcapdim/.modebtns markup. */
.sidebox{display:flex;flex-direction:column;align-items:flex-end;gap:6px;margin-left:auto}
.sidetoggle{display:inline-flex;border:1px solid var(--line);border-radius:4px;overflow:hidden;background:var(--surface2)}
.sidetoggle a,.sidetoggle span{padding:6px 14px;font-size:12.5px;font-weight:700;text-decoration:none;white-space:nowrap;color:var(--muted)}
.sidetoggle span.on{background:var(--accent);color:#fff}
.sidetoggle a:hover{color:var(--fg);background:color-mix(in srgb,var(--accent) 10%,transparent)}

/* topbar tab nav — shared between the dashboard and scrims.html (capture
   pages use their own <header>, not a tab bar; harmless if unused there). */
nav{display:flex;gap:2px;margin-top:10px}
nav button{border:0;background:transparent;color:var(--muted);padding:9px 14px;border-radius:4px 4px 0 0;
  cursor:pointer;font-size:13.5px;font-weight:600;border-bottom:2px solid transparent;margin-bottom:-1px}
nav button:hover{color:var(--fg)}
nav button.active{color:var(--accent);border-bottom-color:var(--accent)}
nav button:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
```

- [ ] **Step 2: Verify the CSS parses**

Run:
```bash
node --check <(printf 'const css = require("fs").readFileSync("docs/theme.css","utf8"); if (!css.includes("--accent")) throw new Error("missing token");')
```
This is a smoke check, not a real CSS parser — the substantive verification is Task 3's dashboard build + screenshot, and Tasks 4–6's screenshots, since that's where this file actually renders. Expected: no error.

- [ ] **Step 3: Commit**

```bash
git add docs/theme.css
git commit -m "Add docs/theme.css: shared OWDB design tokens and primitives"
```

---

## Task 3: Inline `theme.css` into the dashboard build

**Files:**
- Modify: `faceit_sync/_dashboard.py`
- Modify: `faceit_sync/dashboard/head.html`
- Test: `tests/test_export.py`

**Interfaces:**
- Consumes: `docs/theme.css` (Task 2), `docs/fonts/*.woff2` (Task 1), the existing `_PARTS`/`_build_template()` concatenation in `_dashboard.py`.
- Produces: `HTML_TEMPLATE` (unchanged name/type — still a `str` module-level constant in `faceit_sync/_dashboard.py`) now contains the inlined, font-embedded theme CSS in place of the old duplicated token/`.card`/`.btn`/`.prodname`/`.sidetoggle`/`nav`/`.eyebrow` rules.

- [ ] **Step 1: Add the inline marker to `head.html`**

In `faceit_sync/dashboard/head.html`, the `<style>` block currently opens at line 24 with:
```html
<style>
:root{
```
Change it to:
```html
<style>
/* __THEME_CSS__ */
:root{
```
(This mirrors the existing `// __DATA_INLINE__` placeholder convention already used later in the same file.)

- [ ] **Step 2: Delete the now-duplicated token blocks from `head.html`**

Delete these exact lines (the four `:root`/media-query token blocks, now owned by `theme.css`):

```css
:root{
  --bg:#f5f7fa; --surface:#ffffff; --surface2:#eef1f6; --fg:#171a20; --muted:#5c6674;
  --faint:#8b95a4; --line:#e3e8f0; --line2:#d6dce6;
  --accent:#4f46e5; --accent-weak:rgba(79,70,229,.12);
  --tank:#3f80c4; --damage:#d5563f; --support:#33a06a;
  --good:#1f9d61; --mid:#b8860b; --bad:#cf4b36;
  --shadow:0 1px 2px rgba(16,24,40,.06),0 1px 3px rgba(16,24,40,.05);
}
@media (prefers-color-scheme: dark){
  :root{--bg:#0d1015;--surface:#161a21;--surface2:#1d232c;--fg:#e7ebf2;--muted:#98a2b2;
    --faint:#6b7686;--line:#252c37;--line2:#313a48;--accent:#8087ff;--accent-weak:rgba(128,135,255,.16);
    --tank:#5a9bd8;--damage:#e9694f;--support:#46b57c;--good:#34b877;--mid:#d3a02a;--bad:#e5624a;
    --shadow:0 1px 2px rgba(0,0,0,.3);}
}
:root[data-theme="dark"]{--bg:#0d1015;--surface:#161a21;--surface2:#1d232c;--fg:#e7ebf2;--muted:#98a2b2;
  --faint:#6b7686;--line:#252c37;--line2:#313a48;--accent:#8087ff;--accent-weak:rgba(128,135,255,.16);
  --tank:#5a9bd8;--damage:#e9694f;--support:#46b57c;--good:#34b877;--mid:#d3a02a;--bad:#e5624a;
  --shadow:0 1px 2px rgba(0,0,0,.3);}
:root[data-theme="light"]{--bg:#f5f7fa;--surface:#ffffff;--surface2:#eef1f6;--fg:#171a20;--muted:#5c6674;
  --faint:#8b95a4;--line:#e3e8f0;--line2:#d6dce6;--accent:#4f46e5;--accent-weak:rgba(79,70,229,.12);
  --tank:#3f80c4;--damage:#d5563f;--support:#33a06a;--good:#1f9d61;--mid:#b8860b;--bad:#cf4b36;
  --shadow:0 1px 2px rgba(16,24,40,.06),0 1px 3px rgba(16,24,40,.05);}

*{box-sizing:border-box}
html{-webkit-text-size-adjust:100%}
body{margin:0;background:var(--bg);color:var(--fg);font-variant-numeric:tabular-nums;
  font-family:ui-sans-serif,system-ui,-apple-system,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;
  font-size:14px;line-height:1.5;-webkit-font-smoothing:antialiased}
.tnum{font-variant-numeric:tabular-nums}
```

Leave the `/* ---- app shell ---- */` comment and everything from `.topbar{` onward in place, EXCEPT the specific rules deleted in the next step.

- [ ] **Step 3: Delete the now-duplicated `.prodname`, `.sidebox`/`.sidetoggle`/`.modebtns`/`.navcap`/`.navcapdim`, `.eyebrow`, `.card`, and standalone `.btn` rules**

Delete:
```css
.prodname{display:block;font-size:15px;font-weight:800;letter-spacing:.1em;color:var(--accent);margin-bottom:2px}
.prodname span{font-size:11px;letter-spacing:.08em;color:var(--faint);font-weight:600}
```
(keep `.brand{...}`, `.brand h1{...}`, `.brand .meta{...}` unchanged)

`nav`/`nav button` rules are also now duplicated with `theme.css` — delete them too:
```css
nav{display:flex;gap:2px;margin-top:10px}
nav button{border:0;background:transparent;color:var(--muted);padding:9px 14px;border-radius:8px 8px 0 0;
  cursor:pointer;font-size:13.5px;font-weight:600;border-bottom:2px solid transparent;margin-bottom:-1px}
nav button:hover{color:var(--fg)}
nav button.active{color:var(--accent);border-bottom-color:var(--accent)}
nav button:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
```
(keep `.toprow{...}` unchanged)

and:
```css
.sidebox{display:flex;flex-direction:column;align-items:flex-end;gap:6px;margin-left:auto}
.sidetoggle{display:inline-flex;border:1px solid var(--line);border-radius:8px;overflow:hidden;background:var(--surface2)}
.sidetoggle a,.sidetoggle span{padding:6px 14px;font-size:12.5px;font-weight:700;text-decoration:none;white-space:nowrap;color:var(--muted)}
.sidetoggle span.on{background:var(--accent);color:#0b1020}
.sidetoggle a:hover{color:var(--fg)}
.modebtns{display:flex;gap:6px}
.navcap{background:var(--accent-weak);color:var(--accent);text-decoration:none;padding:7px 13px;border-radius:8px;font-size:13px;font-weight:700;border:1px solid var(--accent);white-space:nowrap}
.navcapdim{background:transparent;color:var(--muted);text-decoration:none;padding:7px 13px;border-radius:8px;font-size:13px;font-weight:650;border:1px solid var(--line);white-space:nowrap}
.navcapdim:hover{border-color:var(--accent);color:var(--fg)}
```
(keep `main{...}` unchanged)

then delete:
```css
.eyebrow{font-size:10.5px;font-weight:700;text-transform:uppercase;letter-spacing:.07em;color:var(--faint);margin:0 0 6px}
```
(keep `.eyebrow .note,.eyebrow .faint{...}`, `.eyebrow .note{...}`, `.opener{...}`, `.bvs{...}` unchanged — these are dashboard-specific extensions of the shared `.eyebrow` base)

then delete:
```css
.card{background:var(--surface);border:1px solid var(--line);border-radius:10px;padding:12px 14px;box-shadow:none}
```
(keep `.hero{...}`, `.grid{...}` and everything else in that block unchanged)

then change:
```css
select,input,.btn{font:inherit;color:var(--fg);background:var(--surface);border:1px solid var(--line2);
  border-radius:9px;padding:8px 11px}
```
to:
```css
select,input{font:inherit;color:var(--fg);background:var(--surface);border:1px solid var(--line2);
  border-radius:9px;padding:8px 11px}
```
then delete:
```css
.btn{cursor:pointer;font-weight:600;background:var(--accent);color:#fff;border-color:transparent}
.btn:hover{filter:brightness(1.06)}
```
(keep `select:focus,input:focus{...}` through `.winlab{...}` unchanged)

- [ ] **Step 4: Update the wordmark and toggle markup in `head.html`**

Change:
```html
<div class="brand"><span class="prodname">owdb <span>FACEIT League</span></span>
  <h1 id="title"></h1>
  <select id="division" class="hidden" aria-label="Division"></select>
  <span class="meta" id="subtitle"></span></div>
<div class="sidebox">
  <div class="modebtns"><span class="navcap">Data</span><a class="navcapdim" href="capture/" title="Scout comps in your browser &mdash; no install, no exe">Capture <span id="navcapcount"></span></a></div>
</div>
```
to:
```html
<div class="brand"><span class="prodname"><span class="wordmark"><span class="br">[</span><span class="ow">ow</span><span class="db">db</span><span class="br">]</span></span><span class="sub">FACEIT League</span></span>
  <h1 id="title"></h1>
  <select id="division" class="hidden" aria-label="Division"></select>
  <span class="meta" id="subtitle"></span></div>
<div class="sidebox">
  <div class="sidetoggle"><span class="on">Data</span><a href="capture/" title="Scout comps in your browser &mdash; no install, no exe">Capture <span id="navcapcount"></span></a></div>
</div>
```

- [ ] **Step 5: Wire `faceit_sync/_dashboard.py` to inline the theme**

Current file:
```python
from pathlib import Path

_DASHBOARD_DIR = Path(__file__).resolve().parent / "dashboard"
_PARTS = ("head.html", "pure.js", "app.js", "boot.js")


def _build_template() -> str:
    """Concatenate the dashboard's part files into ``HTML_TEMPLATE``.

    The page shell + CSS, the pure decision helpers (the code the tests
    execute), the ``bootApp`` body, and the data-delivery bootstrap each live
    in their own file under ``dashboard/``. Import-time assembly keeps the
    parts the single source of truth — no stale generated artifact to forget.
    """
    return "".join(
        (_DASHBOARD_DIR / name).read_text(encoding="utf-8") for name in _PARTS
    )


HTML_TEMPLATE = _build_template()
```

Replace with:
```python
import base64
import re
from pathlib import Path

_DASHBOARD_DIR = Path(__file__).resolve().parent / "dashboard"
_DOCS_DIR = Path(__file__).resolve().parent.parent / "docs"
_PARTS = ("head.html", "pure.js", "app.js", "boot.js")

_FONT_URL_RE = re.compile(r"url\('fonts/([^']+\.woff2)'\)")


def _inline_theme_css() -> str:
    """Read docs/theme.css and embed its fonts as base64 data URIs.

    docs/scrims.html and docs/capture/*.html link docs/theme.css directly
    (real files, real requests — fine, they aren't self-contained). The
    exported dashboard can't do that: it must stay a single file with zero
    external loads (tests/test_export.py::
    test_export_html_is_self_contained_and_valid), and its CSP's
    ``font-src data:`` wouldn't permit a separate font file anyway. So for
    this build only, every ``url('fonts/NAME.woff2')`` reference becomes a
    base64 data URI, and the whole file gets inlined into the page's
    ``<style>`` block in place of the ``__THEME_CSS__`` marker.
    """
    theme_css = (_DOCS_DIR / "theme.css").read_text(encoding="utf-8")

    def _embed(match: re.Match[str]) -> str:
        font_bytes = (_DOCS_DIR / "fonts" / match.group(1)).read_bytes()
        encoded = base64.b64encode(font_bytes).decode("ascii")
        return f"url(data:font/woff2;base64,{encoded})"

    return _FONT_URL_RE.sub(_embed, theme_css)


def _build_template() -> str:
    """Concatenate the dashboard's part files into ``HTML_TEMPLATE``.

    The page shell + CSS, the pure decision helpers (the code the tests
    execute), the ``bootApp`` body, and the data-delivery bootstrap each live
    in their own file under ``dashboard/``. Import-time assembly keeps the
    parts the single source of truth — no stale generated artifact to forget.
    The shared design tokens/primitives in docs/theme.css get inlined here
    (fonts base64-embedded) so the exported page stays self-contained while
    still sharing one canonical stylesheet with the capture app and scrims
    page.
    """
    parts = "".join(
        (_DASHBOARD_DIR / name).read_text(encoding="utf-8") for name in _PARTS
    )
    return parts.replace("/* __THEME_CSS__ */", _inline_theme_css())


HTML_TEMPLATE = _build_template()
```

- [ ] **Step 6: Run the dashboard JS syntax test**

Run: `.venv/Scripts/python.exe -m pytest tests/test_export.py::test_dashboard_javascript_is_syntactically_valid -v`
Expected: PASS

- [ ] **Step 7: Run the existing self-contained test**

Run: `.venv/Scripts/python.exe -m pytest tests/test_export.py::test_export_html_is_self_contained_and_valid -v`
Expected: PASS — this is the regression check for the constraint that drove this task's design. If it fails on the `<link>` check, `docs/theme.css` leaked an actual `<link rel="stylesheet">` into `head.html` (it shouldn't; only the marker + inlined content should be present). If it fails on `url(http`, a font path was left un-embedded (check the `_FONT_URL_RE` substitution ran).

- [ ] **Step 8: Add a regression test pinning the inlined theme**

In `tests/test_export.py`, add (near `test_export_html_is_self_contained_and_valid`):

```python
def test_dashboard_inlines_theme_css_with_embedded_fonts() -> None:
    """The dashboard's shared design tokens come from docs/theme.css, inlined
    with fonts base64-embedded — not linked (that would break the
    self-contained guarantee) and not left as a stray marker."""
    from faceit_sync._dashboard import HTML_TEMPLATE

    assert "__THEME_CSS__" not in HTML_TEMPLATE, "theme marker was not substituted"
    assert "--font-display" in HTML_TEMPLATE, "theme tokens missing from dashboard"
    assert "url(data:font/woff2;base64," in HTML_TEMPLATE, "fonts were not base64-embedded"
    assert "url('fonts/" not in HTML_TEMPLATE, "a font reference leaked through unembedded"
```

- [ ] **Step 9: Run the new test**

Run: `.venv/Scripts/python.exe -m pytest tests/test_export.py::test_dashboard_inlines_theme_css_with_embedded_fonts -v`
Expected: PASS

- [ ] **Step 10: Build a local preview and verify visually**

Run (from repo root, using whatever local `faceit.sqlite3` is already present — this is a throwaway preview, gitignored):
```bash
.venv/Scripts/faceit-sync export --format html --out dashboard.html
```
Then screenshot a couple of tabs and widths:
```bash
msedge --headless --disable-gpu --window-size=1440,900 --screenshot=dashboard-overview.png "file:///$(pwd)/dashboard.html#overview"
msedge --headless --disable-gpu --window-size=390,844 --screenshot=dashboard-overview-mobile.png "file:///$(pwd)/dashboard.html#overview"
```
Share both the `file:///…/dashboard.html` path and the two screenshots with the user for visual sign-off before proceeding to Task 4. Expected: violet background, `[ow]db` wordmark, Space Grotesk headings, flat-bordered cards with a left accent stripe, outlined buttons.

- [ ] **Step 11: Run the full test suite and mypy**

Run: `.venv/Scripts/python.exe -m pytest` and `.venv/Scripts/python.exe -m mypy faceit_sync`
Expected: all pass, no type errors.

- [ ] **Step 12: Commit**

```bash
git add faceit_sync/_dashboard.py faceit_sync/dashboard/head.html tests/test_export.py
git commit -m "Inline docs/theme.css into the dashboard build; apply new wordmark/toggle"
```

---

## Task 4: Migrate `docs/scrims.html`

**Files:**
- Modify: `docs/scrims.html`

**Interfaces:**
- Consumes: `docs/theme.css` (Task 2) via `<link>`.

- [ ] **Step 1: Add the stylesheet link and dark theme attribute**

Change:
```html
<html lang="en">
```
to:
```html
<html lang="en" data-theme="dark">
```
Add, right after the existing `<meta http-equiv="Content-Security-Policy" …>` line (line 10):
```html
<link rel="stylesheet" href="theme.css">
```

- [ ] **Step 2: Loosen the CSP to permit the linked stylesheet**

Change:
```html
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; font-src data:; object-src 'none'; frame-src 'none'; base-uri 'self'; form-action 'none'">
```
to:
```html
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline' 'self'; img-src 'self' data:; connect-src 'self'; font-src 'self' data:; object-src 'none'; frame-src 'none'; base-uri 'self'; form-action 'none'">
```
(`style-src` needs `'self'` for the `<link>`; `font-src` needs `'self'` for `theme.css`'s real `.woff2` file requests.)

- [ ] **Step 3: Delete the now-duplicated `:root` token block and body reset**

Delete:
```css
:root{color-scheme:dark;
  --bg:#0d1015;--surface:#161a21;--surface2:#1d232c;--fg:#e7ebf2;--muted:#98a2b2;
  --faint:#6b7686;--line:#252c37;--line2:#313a48;--accent:#8087ff;--accent-weak:rgba(128,135,255,.16);
  --tank:#5a9bd8;--damage:#e9694f;--support:#46b57c;--good:#34b877;--mid:#d3a02a;--bad:#e5624a;
  --shadow:0 1px 2px rgba(0,0,0,.3);
}
*{box-sizing:border-box}
html{-webkit-text-size-adjust:100%}
body{margin:0;background:var(--bg);color:var(--fg);font-variant-numeric:tabular-nums;
  font-family:ui-sans-serif,system-ui,-apple-system,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;
  font-size:14px;line-height:1.5;-webkit-font-smoothing:antialiased}
.tnum{font-variant-numeric:tabular-nums}
```

- [ ] **Step 4: Delete the now-duplicated `.prodname`, nav, toggle, and `.eyebrow`/`.card` rules**

Delete:
```css
.prodname{display:block;font-size:11px;font-weight:800;letter-spacing:.14em;color:var(--accent);margin-bottom:2px}
.prodname span{color:var(--faint);font-weight:600;letter-spacing:.08em}
```
(keep `.brand{...}`, `.brand h1{...}` unchanged)

Delete:
```css
nav{display:flex;gap:2px;margin-top:10px}
nav button{border:0;background:transparent;color:var(--muted);padding:9px 14px;border-radius:8px 8px 0 0;
  cursor:pointer;font-size:13.5px;font-weight:600;border-bottom:2px solid transparent;margin-bottom:-1px}
nav button:hover{color:var(--fg)}
nav button.active{color:var(--accent);border-bottom-color:var(--accent)}
nav button:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
```
(keep `.toprow{...}` unchanged)

Delete:
```css
.sidebox{display:flex;flex-direction:column;align-items:flex-end;gap:6px;margin-left:auto}
.sidetoggle{display:inline-flex;border:1px solid var(--line);border-radius:8px;overflow:hidden;background:var(--surface2)}
.sidetoggle a,.sidetoggle span{padding:6px 14px;font-size:12.5px;font-weight:700;text-decoration:none;white-space:nowrap;color:var(--muted)}
.sidetoggle span.on{background:var(--accent);color:#0b1020}
.sidetoggle a:hover{color:var(--fg)}
.modebtns{display:flex;gap:6px}
.navcap{background:var(--accent-weak);color:var(--accent);text-decoration:none;padding:7px 13px;border-radius:8px;font-size:13px;font-weight:700;border:1px solid var(--accent);white-space:nowrap}
.navcapdim{background:transparent;color:var(--muted);text-decoration:none;padding:7px 13px;border-radius:8px;font-size:13px;font-weight:650;border:1px solid var(--line);white-space:nowrap}
.navcapdim:hover{border-color:var(--accent);color:var(--fg)}
```
(keep `main{...}` unchanged)

Delete:
```css
.card{background:var(--surface);border:1px solid var(--line);border-radius:10px;padding:12px 14px;box-shadow:none}
.eyebrow{font-size:10.5px;font-weight:700;text-transform:uppercase;letter-spacing:.07em;color:var(--faint);margin:0 0 6px}
```
(keep `.grid{...}` and everything after unchanged; if scrims.html has any `.eyebrow`-extension rules analogous to the dashboard's `.eyebrow .note`, keep those — check for them before deleting the base rule)

- [ ] **Step 5: Update the wordmark and toggle markup**

Change:
```html
<span class="prodname">owdb<span> · Private Scrims</span></span>
<div class="brand">
  <h1>Scrim Tracking</h1>
</div>
```
to:
```html
<span class="prodname"><span class="wordmark"><span class="br">[</span><span class="ow">ow</span><span class="db">db</span><span class="br">]</span></span><span class="sub">Private Scrims</span></span>
<div class="brand">
  <h1>Scrim Tracking</h1>
</div>
```
Change:
```html
<div class="sidetoggle"><a href="index.html">League</a><span class="on">Scrims</span></div>
<div class="modebtns"><span class="navcap">Data</span><a class="navcapdim" href="capture/scrim.html">Capture</a></div>
```
to:
```html
<div class="sidetoggle"><a href="index.html">League</a><span class="on">Scrims</span></div>
<div class="sidetoggle"><span class="on">Data</span><a href="capture/scrim.html">Capture</a></div>
```

- [ ] **Step 6: Verify visually**

```bash
msedge --headless --disable-gpu --window-size=1440,900 --screenshot=scrims.png "file:///$(pwd)/docs/scrims.html"
```
Share the screenshot and the `file:///…/docs/scrims.html` path with the user. Expected: same violet palette/typography/card shape as the dashboard preview, wordmark and both toggles rendering correctly, existing scrim data/tabs unaffected.

- [ ] **Step 7: Commit**

```bash
git add docs/scrims.html
git commit -m "Migrate docs/scrims.html to shared docs/theme.css"
```

---

## Task 5: Migrate `docs/capture/index.html`

**Files:**
- Modify: `docs/capture/index.html`

**Interfaces:**
- Consumes: `docs/theme.css` (Task 2) via `<link>`.

- [ ] **Step 1: Add the stylesheet link and dark theme attribute**

Change:
```html
<html lang="en"><head><meta charset="utf-8">
```
to:
```html
<html lang="en" data-theme="dark"><head><meta charset="utf-8">
```
Add, right after the existing CSP `<meta>` line:
```html
<link rel="stylesheet" href="../theme.css">
```

- [ ] **Step 2: Loosen the CSP**

Change:
```html
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; script-src 'unsafe-inline' https://cdn.jsdelivr.net; style-src 'unsafe-inline'; img-src 'self' data:; connect-src 'self' https://upload.owdb.io wss://upload.owdb.io https://cdn.jsdelivr.net https://tessdata.projectnaptha.com; worker-src https://cdn.jsdelivr.net; font-src data:; object-src 'none'; frame-src 'none'; base-uri 'self'; form-action 'none'">
```
to:
```html
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; script-src 'unsafe-inline' https://cdn.jsdelivr.net; style-src 'unsafe-inline' 'self'; img-src 'self' data:; connect-src 'self' https://upload.owdb.io wss://upload.owdb.io https://cdn.jsdelivr.net https://tessdata.projectnaptha.com; worker-src https://cdn.jsdelivr.net; font-src 'self' data:; object-src 'none'; frame-src 'none'; base-uri 'self'; form-action 'none'">
```

- [ ] **Step 3: Delete the now-duplicated `:root` block, body base, `.card`, `.eyebrow`, `.pill`**

Change:
```css
:root{color-scheme:dark;--bg:#0d1015;--surface:#161a21;--surface2:#1d232c;--fg:#e7ebf2;--muted:#98a2b2;--faint:#6b7686;--line:#252c37;--accent:#8087ff;--good:#34b877;--mid:#d3a02a;--bad:#e5624a;--blue:#5a9bd8;--red:#e9694f}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--fg);font:14px/1.5 system-ui,Segoe UI,sans-serif}
```
to:
```css
:root{--blue:#5a9bd8;--red:#e9694f}
```
(`--blue`/`--red` are capture-specific team-side indicators not in the shared token set — keep them; `--line2` was already referenced with an inline fallback (`var(--line2,#313a48)`) elsewhere in this file's CSS and is now provided for real by `theme.css`, so those fallbacks stay harmless but could be cleaned up — leave them, not required for this task)

Delete:
```css
.card{background:var(--surface);border:1px solid var(--line);border-radius:10px;padding:12px 14px}
```
(keep `summary.cardsum{...}` and everything else unchanged)

Change:
```css
.pill{display:inline-block;padding:2px 8px;border-radius:20px;background:var(--surface2);border:1px solid var(--line);font-size:12px;margin-right:6px}
```
— **keep this one** (it is not part of the shared set moved to `theme.css` in this pass; no change needed).

Delete:
```css
.eyebrow{font-size:11px;letter-spacing:.09em;text-transform:uppercase;color:var(--accent);font-weight:800}
```
(the shared `.eyebrow` from `theme.css` replaces it — this intentionally changes capture's eyebrow from accent-colored/800-weight to the same faint-colored/700-weight label style used everywhere else, fixing the exact inconsistency the redesign targets)

- [ ] **Step 4: Add the `.sidebox`/toggle markup in place of the old modebtns block, and the wordmark**

Change:
```html
<header>
  <div class="hrow">
    <div>
      <div class="eyebrow">owdb · FACEIT League</div>
      <h1>Capture comps — League</h1>
    </div>
    <div class="sidebox">
      <div class="modebtns"><a class="navcapdim" href="../">Data</a><span class="navcap">Capture</span></div>
    </div>
  </div>
```
to:
```html
<header>
  <div class="hrow">
    <div>
      <span class="prodname"><span class="wordmark"><span class="br">[</span><span class="ow">ow</span><span class="db">db</span><span class="br">]</span></span><span class="sub">FACEIT League</span></span>
      <h1>Capture comps — League</h1>
    </div>
    <div class="sidebox">
      <div class="sidetoggle"><a href="../">Data</a><span class="on">Capture</span></div>
    </div>
  </div>
```

- [ ] **Step 5: Verify visually**

```bash
msedge --headless --disable-gpu --window-size=1440,900 --screenshot=capture-index.png "file:///$(pwd)/docs/capture/index.html"
```
Share the screenshot and `file:///…/docs/capture/index.html` path with the user. Pay particular attention to the calibration/video-preview panel and the toast/modal/tour components (unique to this page, untouched by this task) still reading clearly against the new tinted background.

- [ ] **Step 6: Commit**

```bash
git add docs/capture/index.html
git commit -m "Migrate docs/capture/index.html to shared docs/theme.css"
```

---

## Task 6: Migrate `docs/capture/scrim.html`

**Files:**
- Modify: `docs/capture/scrim.html`

**Interfaces:**
- Consumes: `docs/theme.css` (Task 2) via `<link>`. Mirrors Task 5 exactly (this file is near-identical to `capture/index.html`).

- [ ] **Step 1: Add the stylesheet link, dark theme attribute, and loosen the CSP**

Same pattern as Task 5 Steps 1–2: add `<html lang="en" data-theme="dark">`, add `<link rel="stylesheet" href="../theme.css">` after the CSP meta tag, and change `style-src 'unsafe-inline';` → `style-src 'unsafe-inline' 'self';` and `font-src data:;` → `font-src 'self' data:;` in:
```html
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; script-src 'unsafe-inline' https://cdn.jsdelivr.net; style-src 'unsafe-inline'; img-src 'self' data:; connect-src 'self' https://cdn.jsdelivr.net https://tessdata.projectnaptha.com; worker-src https://cdn.jsdelivr.net; font-src data:; object-src 'none'; frame-src 'none'; base-uri 'self'; form-action 'none'">
```

- [ ] **Step 2: Delete the now-duplicated `:root` block, body base, `.card`, `.eyebrow`**

Change (line 10):
```css
:root{color-scheme:dark;--bg:#0d1015;--surface:#161a21;--surface2:#1d232c;--fg:#e7ebf2;--muted:#98a2b2;--faint:#6b7686;--line:#252c37;--accent:#8087ff;--good:#34b877;--mid:#d3a02a;--bad:#e5624a;--blue:#5a9bd8;--red:#e9694f}
```
to:
```css
:root{--blue:#5a9bd8;--red:#e9694f}
```
Delete (lines 11-12, confirmed byte-identical to `capture/index.html`):
```css
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--fg);font:14px/1.5 system-ui,Segoe UI,sans-serif}
```
Delete (line 22):
```css
.card{background:var(--surface);border:1px solid var(--line);border-radius:10px;padding:12px 14px}
```
Delete (line 92):
```css
.eyebrow{font-size:11px;letter-spacing:.09em;text-transform:uppercase;color:var(--accent);font-weight:800}
```

- [ ] **Step 3: Recolor the `#scrimpaused` interstitial to use tokens**

Change:
```html
<div id="scrimpaused" style="position:fixed;inset:0;z-index:999999;background:#0b1020;display:flex;align-items:center;justify-content:center;text-align:center;padding:24px">
  <div style="max-width:520px">
    <div style="font-size:13px;font-weight:700;letter-spacing:.08em;text-transform:uppercase;color:#8087ff;margin-bottom:8px">owdb</div>
    <h1 style="font-size:26px;margin:0 0 10px">Scrims are paused</h1>
    <p style="color:#aab;font-size:14px;line-height:1.5;margin:0 0 20px">Scrim capture is paused while we finish it up. Head to the League capture tool to scout FACEIT maps instead.</p>
    <a href="index.html" style="display:inline-block;background:#8087ff;color:#0b1020;font-weight:700;padding:10px 18px;border-radius:8px;text-decoration:none">Open League capture →</a>
  </div>
</div>
```
to:
```html
<div id="scrimpaused" style="position:fixed;inset:0;z-index:999999;background:var(--bg);display:flex;align-items:center;justify-content:center;text-align:center;padding:24px">
  <div style="max-width:520px">
    <div style="font-size:13px;font-weight:700;letter-spacing:.08em;text-transform:uppercase;color:var(--accent);margin-bottom:8px">owdb</div>
    <h1 style="font-size:26px;margin:0 0 10px">Scrims are paused</h1>
    <p style="color:var(--muted);font-size:14px;line-height:1.5;margin:0 0 20px">Scrim capture is paused while we finish it up. Head to the League capture tool to scout FACEIT maps instead.</p>
    <a href="index.html" style="display:inline-block;background:var(--accent);color:#fff;font-weight:700;padding:10px 18px;border-radius:4px;text-decoration:none">Open League capture →</a>
  </div>
</div>
```
(This element renders before `theme.css`'s tokens would otherwise be available if it were the very first thing painted, but since it's inside `<body>` after `<head>` — where the `<link>` already loaded — the custom properties are already defined; no flash-of-unstyled-content risk beyond what already exists for the rest of the page.)

- [ ] **Step 4: Add the toggle/wordmark markup**

Change:
```html
<div>
  <div class="eyebrow">owdb · Private Scrims</div>
  <h1>Capture comps — Scrims</h1>
</div>
<div class="sidebox">
  <div class="sidetoggle"><a href="index.html">League</a><span class="on">Scrims</span></div>
  <div class="modebtns"><a class="navcapdim" href="../scrims.html">Data</a><span class="navcap">Capture</span></div>
</div>
```
to:
```html
<div>
  <span class="prodname"><span class="wordmark"><span class="br">[</span><span class="ow">ow</span><span class="db">db</span><span class="br">]</span></span><span class="sub">Private Scrims</span></span>
  <h1>Capture comps — Scrims</h1>
</div>
<div class="sidebox">
  <div class="sidetoggle"><a href="index.html">League</a><span class="on">Scrims</span></div>
  <div class="sidetoggle"><a href="../scrims.html">Data</a><span class="on">Capture</span></div>
</div>
```

- [ ] **Step 5: Verify visually**

```bash
msedge --headless --disable-gpu --window-size=1440,900 --screenshot=capture-scrim.png "file:///$(pwd)/docs/capture/scrim.html"
```
Share the screenshot and path with the user, including the `#scrimpaused` interstitial (it's shown by default since scrims are currently paused).

- [ ] **Step 6: Commit**

```bash
git add docs/capture/scrim.html
git commit -m "Migrate docs/capture/scrim.html to shared docs/theme.css"
```

---

## Task 7: Consistency pass + document the convention

**Files:**
- Modify: `CLAUDE.md`

**Interfaces:** None — this task only verifies and documents; no code interfaces change.

- [ ] **Step 1: Side-by-side visual check**

With all four surfaces migrated, take one more full round of screenshots (dashboard light, dashboard dark, scrims, capture index, capture scrim) and review them together for consistency — same wordmark rendering, same card/button shape, same font pairing, same accent color, same toggle style. Fix anything that looks wrong before proceeding (return to the relevant task above rather than patching ad hoc).

Run: `.venv/Scripts/python.exe -m pytest` and `.venv/Scripts/python.exe -m mypy faceit_sync` one final time across all changes.
Expected: all pass.

- [ ] **Step 2: Update CLAUDE.md's conventions section**

In `CLAUDE.md`, under "### Codebase conventions", add a new bullet after the existing "Don't overengineer unless necessary for expandability" line:

```markdown
- **Shared design tokens/primitives live in `docs/theme.css`** — colors,
  fonts, `.card`, `.btn`, the `.prodname` wordmark, `.sidetoggle`/`.sidebox`,
  `nav`, and `.eyebrow`. `docs/scrims.html` and `docs/capture/*.html` link it
  directly; `docs/index.html` can't (it must stay self-contained — see
  `tests/test_export.py::test_export_html_is_self_contained_and_valid`), so
  `faceit_sync/_dashboard.py` inlines the same file's content (with fonts
  base64-embedded) into the dashboard build instead. Edit `docs/theme.css`
  for anything in that shared set; don't re-add a per-page copy — that
  duplication is exactly what caused the pre-redesign inconsistency.
  Everything else (tables, chips, tags, pills, and all page-specific
  components) stays defined per-page, since it already consumes these same
  tokens and re-themes automatically.
```

- [ ] **Step 3: Commit**

```bash
git add CLAUDE.md
git commit -m "Document docs/theme.css as the shared UI source of truth"
```

---

## Self-Review Notes

- **Spec coverage:** every scope-decision row in `specs/2026-08-10-owdb-ui-redesign-design.md` maps to a task above — tokens/typography/shape/wordmark (Task 2), CSS architecture incl. the corrected inline-vs-link split (Tasks 2–3), rollout order (Tasks 3→4→5→6→7 matches dashboard→scrims→capture→consistency), per-step verification via real artifacts (every task's second-to-last step), CLAUDE.md documentation (Task 7).
- **Explicitly out of scope**, confirmed absent from all tasks: Season 10 cutover, scrim-mode `.wip` feature graduation, any IA/routing/JS-logic change, any new theme beyond the token-naming groundwork already in `theme.css`.
- **Font weight consistency:** Task 1 downloads exactly the weights Task 2's `@font-face` rules reference (600/700 Space Grotesk, 400/500/600/700 Inter) — no mismatch.
- **CSP changes are scoped per-page**: only `style-src`/`font-src` loosened on the three linking pages; the dashboard's CSP is untouched since nothing there changes to a real external load.

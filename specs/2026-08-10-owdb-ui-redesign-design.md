# OWDB UI redesign — design

**Date:** 2026-08-10
**Status:** approved, ready for implementation planning

## Goal

Replace the current visual design — generic "AI SaaS" indigo (`#4f46e5`/`#8087ff`),
pure system-font stack, four independently-duplicated inline stylesheets — with a
distinctive, cohesive system across all three user-facing surfaces (the dashboard,
the capture app, the private scrims page), without changing any functionality,
information architecture, routing, or data logic. This is a re-skin plus a CSS
consolidation, not a rebuild.

## Background: what's already there

- Four HTML surfaces each carry their own inline `<style>` block with duplicated
  (copy-pasted, not shared) tokens and component CSS: `faceit_sync/dashboard/head.html`
  (source template for the live `docs/index.html`, the only surface with real
  light/dark support), `docs/capture/index.html`, `docs/capture/scrim.html`, and
  `docs/scrims.html` (dark-only, closest existing match to the dashboard's dark
  tokens already).
- The existing system's *bones* are sound and are being kept: CSS custom
  properties for all tokens, semantic role colors (`--tank`/`--damage`/`--support`/
  `--good`/`--mid`/`--bad`) distinct from the brand accent, `font-variant-numeric:
  tabular-nums` throughout for aligned stat columns, a 10px-radius card/hairline-border
  component language, sticky headers/nav, `color-mix()` for tinted variants.
- No web fonts anywhere today — pure system-font stack
  (`ui-sans-serif, system-ui, -apple-system, "Segoe UI", Roboto, Helvetica, Arial`).
- Dark mode is already the "native" identity even though light is the CSS
  fallback default on the dashboard (favicon and `theme-color` meta hardcode the
  dark background); capture and scrims are dark-only by design (video-preview
  context) and stay that way.
- `docs/index.html` is a build artifact: CI's `update.yml` regenerates it from
  `faceit_sync/dashboard/head.html` on every run. A prior session shipped a
  branding fix by hand-patching the *output* instead of the *template*, which
  regressed on the next CI run — the fix has to land in `head.html` (and,
  correspondingly, in `theme.css` being *linked from* `head.html`), never only
  in the generated `docs/index.html`.
- No style guide or design-tokens doc exists; `README.md`/`FEATURES.md` are
  purely functional. This document is the first place color/type/component
  conventions are written down.

## Scope decisions

| Decision | Choice | Why |
|---|---|---|
| Surfaces covered | All three (dashboard, capture, scrims), unified | The "feels inconsistent" complaint is caused by four independently-diverging copies of the same design; fixing only one surface leaves the root cause in place. |
| Visual mood | Data-analyst tool + esports broadcast, mixed | Explicit requirement: usable for fast on-the-fly lookups *and* slower deliberate scouting sessions — pure "terminal/data-tool" or pure "broadcast graphics" each lean too far one way. |
| Accent color | Purple family ("Broadcast Violet"), token-named for future theming | Moves off the generic `#4f46e5` indigo cliché while keeping brand continuity; semantic (not literally-named) tokens mean a future alternate theme is a second `[data-theme]` override block, not a rewrite — no extra machinery built now, just naming discipline. |
| Background | Violet-tinted near-black, not neutral gray-black | Matches the reference palette's overall mood; cohesive with the accent family rather than treating color as accent-only. |
| Default theme | Unchanged — OS-preference-driven (`prefers-color-scheme`), manual `data-theme` override stays | No reason to change existing behavior; not a complaint that was raised. |
| Typography | Space Grotesk (headings/stat numbers/team names) + Inter (body/tables/labels), self-hosted woff2 | A distinctive typeface is the highest-leverage fix for "feels generic"; self-hosted (not CDN) so the capture app has no external dependency; Space Grotesk chosen over more literally "gamer" faces (Chakra Petch, Rajdhani) to keep the analyst-tool half of the mood rather than lean all the way into broadcast-HUD lettering. |
| Shape language | Flat surfaces, thin border, 3px left accent bar (replacing filled/bordered cards); outlined buttons except primary CTAs | Quietest of the three options explored — reads as data tool first, lets the accent color carry the esports energy instead of heavy chrome. |
| Wordmark | `[ow` bold/bright + `db]` dimmer, brackets in accent color, keeps the existing lowercase | User likes lowercase but wanted more visual presence than plain styled text; brackets echo a scoreboard/terminal readout without literally reworking the logotype. |
| CSS architecture | One shared `docs/theme.css`; scrims/capture `<link>` it, the dashboard inlines it at build time (a test requires the exported dashboard stay a single self-contained file — see Architecture) | Root-causes the inconsistency complaint instead of re-skinning four copies in parallel; stays within the "no build step, plain static files" convention — one more static asset, not a bundler. |
| Structural changes | In scope, but bounded: no tab/IA/routing/JS-logic changes; only component-pattern unification (toggle style, card header hierarchy, hero banner treatment, button emphasis) | Explicit requirement: "open to structural, but don't break anything." Full IA rework wasn't requested and isn't warranted by the specific complaints raised. |
| Rollout | Incremental, one surface at a time (foundation → dashboard → scrims → capture → consistency pass), each step verified before the next | `docs/index.html` is live and CI-regenerated; a single big-bang diff across four files has a much larger blast radius than four independently-verified steps, especially given the recent branding-regression incident. |
| Verification per step | Real local build artifacts (local `dashboard.html` export, the actual `docs/scrims.html`/`docs/capture/*.html`), shared as a `file://` path plus a headless-Edge screenshot, checked against the real thing in the user's own browser before proceeding | Explicit requirement — mockups get the direction right, but the actual generated/static files are what must be verified once real code is being changed. |

## Design tokens

### Color

| Token | Dark | Light (dashboard only) |
|---|---|---|
| `--bg` | `#130f24` | `#f7f5fb` |
| `--surface` | `#1e1730` | `#ffffff` |
| `--surface2` | `#241d3a` | `#eeeaf7` |
| `--fg` | `#f0e9fb` | `#1c1730` |
| `--muted` | `#cfc7e2` | `#5a5270` |
| `--faint` | `#8f7ea8` | `#867a99` |
| `--line` | `#2e2846` | `#e2dcf0` |
| `--line2` | `#3a3358` | `#d3caea` |
| `--accent` | `#a855f7` | `#7c3aed` |
| `--accent-bright` | `#e2b8ff` | `#6d28d9` |
| `--accent-weak` | `rgba(216,111,255,.15)` | `rgba(124,58,237,.10)` |

`--tank` (`#3f80c4`/`#5a9bd8`), `--damage` (`#d5563f`/`#e9694f`), `--support`
(`#33a06a`/`#46b57c`), `--good`, `--mid`, `--bad` keep their current light/dark
hex values unchanged — they're already meaningful, already distinct from the
brand accent, and weren't part of the complaint.

Token *names* stay semantic (`--accent`, not `--purple`) specifically so a
future theme is an additive `[data-theme="…"]` override block reusing the same
names, not a find-and-replace across four files.

### Typography

- **Space Grotesk**, weights 600/700 — headings, stat/tile numbers, team
  names, the wordmark.
- **Inter**, weights 400/500/600/700 — body text, table cells, labels,
  buttons.
- Both self-hosted as woff2 under `docs/fonts/` (latin subset, `font-display:
  swap`), not loaded from a CDN — keeps the capture app dependency-free and
  avoids a new external network call on a page that already has enough moving
  parts (screen capture, tesseract.js).
- `font-variant-numeric: tabular-nums` stays applied everywhere numbers
  appear, unchanged from today.
- Monospace stack for replay codes (`.rc`) is unchanged.

### Wordmark

`[ow` in Space Grotesk 700, `--accent-bright`; `db]` in Space Grotesk 500,
`--faint`; brackets in `--accent`. Lowercase preserved. Used at both full
banner size and topbar size (topbar keeps the existing "FACEIT League"
sub-label to its right, unchanged).

### Shape

- Cards/tiles: `background: var(--surface)`, `1px solid var(--line)` border,
  `3px solid var(--accent)` left border only, `4px` corner radius — replacing
  the current 10px-all-around rounded, shadowed/bordered card.
- Buttons: outlined (`1px solid var(--accent)`, `--accent-bright` text,
  transparent fill) by default; filled (`--accent` background, white text)
  reserved for the single primary CTA per page (e.g. "Contribute a capture").
- Chips/pills/tags: unchanged shape (pill radius), recolored to the new
  accent-weak background + accent-bright text.
- Tables: unchanged structure (sticky header, sortable-arrow headers, grouped
  `.blocks` rows, `.scroll` overflow wrapper) — re-skinned only (new border/
  hover colors, slightly more cell padding for scanability).

## Architecture

### Shared stylesheet

`docs/theme.css` — new, git-tracked, static file holding the token set above
plus shared component classes: `.card`, `.tile`, `.chip`, `.tag`, `.pill`,
table base styles, `.btn`, nav/tab styles, and one unified segmented-control
toggle class (replacing today's two different patterns — the dashboard's
`sidebox` link-cluster for Data/Capture and the `sidetoggle` used for
League/Scrims).

**Constraint discovered during planning:** `tests/test_export.py`'s
`test_export_html_is_self_contained_and_valid` deliberately asserts the
*dashboard* (`docs/index.html`) is a single self-contained file — no
`<link rel="stylesheet">` is permitted (only `canonical`/`icon` rels pass),
and no separate asset loads at all. This is an intentional, tested
invariant (the exported file must render fully offline on its own), not an
oversight, so the dashboard cannot simply `<link>` `theme.css` the way the
design originally assumed. `docs/scrims.html` and `docs/capture/*.html` are
static hand-authored files with no such test and are unaffected.

The mechanism therefore differs by surface, while the *source of truth*
stays singular:

- `docs/capture/index.html` and `docs/capture/scrim.html` link
  `../theme.css`; `docs/scrims.html` links `theme.css` directly (same
  directory level as `docs/index.html`). CSP on these three pages gets
  `style-src 'unsafe-inline' 'self'` (was `'unsafe-inline'` only) so the
  `<link>` is permitted to load.
- The dashboard instead gets `theme.css` **inlined at build time**:
  `faceit_sync/_dashboard.py` reads `docs/theme.css`'s content and
  concatenates it into the assembled `<style>` block of the generated
  `docs/index.html`, the same way it already concatenates `head.html`/
  `pure.js`/`app.js`/`boot.js`. Because this read happens in the *template
  assembly step* CI runs on every export, every future CI run carries the
  shared stylesheet forward automatically — this still closes the failure
  mode from the prior branding-regression incident (fixing only the
  generated output would not), just via inlining instead of a `<link>`.
  `docs/index.html`'s CSP (`style-src 'unsafe-inline'`) needs no change,
  since the content lands inline.
- Page-specific CSS that has no cross-page equivalent stays inline per page:
  the dashboard's radar-chart SVG styling, capture's video-capture
  stage/calibration-overlay/toast/modal/tour/stepper components, scrims'
  `.scrim-card`/`.map-row` styling. Only the genuinely duplicated core
  (tokens, cards, tables, nav, buttons, chips) moves to the shared file.
- Confirmed during planning: `faceit-sync export` opens exactly the path
  passed via `--out` (`open(args.out, "w", ...)` in `faceit_sync/cli.py`)
  and touches nothing else — `docs/theme.css` and `docs/fonts/` are safe as
  permanently tracked files the export step will never clobber.

This keeps the project's existing "no build step, plain concatenated static
files" convention intact — `theme.css` is one more static asset, read either
by the browser (`<link>`, for scrims/capture) or by the existing Python
concatenation step (for the dashboard), never by a bundler or preprocessor.

### Fonts: same split, for the same reason

`docs/fonts/*.woff2` (self-hosted Space Grotesk 600/700, Inter
400/500/600/700) are real files, referenced by normal `@font-face
{ src: url('fonts/…woff2') }` rules inside `docs/theme.css`. That works
as-is for scrims/capture (real file, real request, cacheable) — but a real
file request is exactly what the dashboard's self-contained test and its
`font-src data:` CSP both forbid. So for the dashboard build only,
`faceit_sync/_dashboard.py` additionally base64-encodes each `.woff2` and
substitutes `url('fonts/…woff2')` for `url(data:font/woff2;base64,…)` before
inlining — the dashboard's `<style>` block ends up with fonts embedded
directly, `docs/theme.css` itself stays untouched/human-readable, and no CSP
change is needed on the dashboard for fonts (`font-src data:` already
permits it).

### Component-pattern changes (bounded)

- Unify the Data/Capture and League/Scrims toggles into one segmented-control
  component.
- Give card/tile headers a consistent eyebrow-label → title → value
  hierarchy (today it varies card to card).
- Hero/callout banners (e.g. the capture-funnel nudge) move to the flat-line/
  accent-bar treatment instead of a bordered card.
- Buttons: outlined by default, filled only for the primary CTA per page.

**Explicitly unchanged:** tab structure (Overview/Teams/Players/Meta/Matches),
hash routing, deep links (`#compare=`, `#prep=`, playoffs toggle, draft sim),
all JS logic/data flow, the IndexedDB scrims side-channel, the capture
calibration/CV pipeline.

## Rollout & verification

Incremental, one surface at a time; each step is its own commit, verified
before the next begins:

1. **Foundation** — create `docs/theme.css` (full token set + shared
   components) and `docs/fonts/` (self-hosted woff2s). No page changes.
2. **Dashboard** — wire `faceit_sync/_dashboard.py` to inline `theme.css`
   (fonts base64-embedded) into the assembled `<style>` block, apply
   wordmark/shape/component changes, remove the inline CSS it replaces.
   Verify: `pytest
   tests/test_export.py::test_dashboard_javascript_is_syntactically_valid`;
   build a local `dashboard.html` export preview; share its `file://` path
   plus a headless-Edge screenshot (`msedge --headless
   --screenshot=FILE "file:///…#tab"`) across a couple of tabs and viewport
   widths.
3. **Scrims page** — migrate `docs/scrims.html` (smallest diff, already
   closest to the dashboard's dark tokens). Share path + screenshot.
4. **Capture app** — migrate `docs/capture/index.html` and
   `docs/capture/scrim.html` last, since they carry the most unique
   components (toasts, modal, tour, calibration overlay, stepper) to re-skin
   carefully; verify the live-preview/calibration panel still reads clearly
   against the new tinted background. Share path + screenshot.
5. **Consistency pass** — side-by-side check across all four; update
   CLAUDE.md's conventions section to name `theme.css` as the shared source
   of truth for future UI work, so it doesn't drift back into four copies.

Full `pytest` + `mypy --strict` run before any commit lands, per existing
project convention. Nothing gets pushed without explicit user sign-off.

## Explicitly out of scope

- Season 10 cutover work (tracked separately in
  `specs/2026-08-10-season10-cutover-design.md`).
- Graduating the `.wip`-badged experimental scrim-mode features out of
  experimental status.
- Any new features, data changes, or IA/navigation restructuring beyond the
  bounded component-pattern unification above.
- Building out actual multi-theme support — only the *naming* groundwork for
  it (semantic token names) is included now.

## Risks

- **Page weight**: adding two webfont families increases initial load,
  partially offset by self-hosting + subsetting + `font-display: swap`. Given
  CLAUDE.md already flags page-weight growth as a watch item, this is worth
  a rough before/after size check during implementation.
- **CI regeneration**: the same class of risk that caused the prior branding
  regression — mitigated by putting the `<link>` in `head.html` (the
  template), not patching generated output, and documented above as a
  first-class design decision rather than an afterthought.
- **Contrast**: several new tokens (e.g. `--faint` on `--bg`) should get a
  quick contrast-ratio check during implementation, particularly for the
  dimmer half of the wordmark and muted table text, since the new background
  is darker/more saturated than today's neutral dark.

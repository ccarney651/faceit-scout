# Capture page theme picker + themed control panel — design

**Date:** 2026-08-10
**Status:** approved, ready for implementation

## Goal

The dashboard has a palette picker (`docs/theme.css` + `head.html`/`app.js`);
`docs/capture/index.html` and `docs/capture/scrim.html` link `theme.css` but
have no picker UI, and their Document Picture-in-Picture "control panel" /
"floating overlay" window is fully hardcoded to the pre-redesign indigo colors
regardless of any palette. Fix both.

## Scope

- Add the same `.themepick` palette `<select>` (7 options, no mode toggle —
  capture stays dark-only, unchanged design decision) to the top bar of
  `docs/capture/index.html` and `docs/capture/scrim.html`.
- Reuse the dashboard's exact `localStorage['owdb.palette']` key so a palette
  choice carries across all `docs/` pages for free (same origin). Early-apply
  inline `<head>` script mirrors `head.html`'s pattern, palette-only.
- The PiP "control panel"/"floating overlay" (`popout()` in both files)
  currently builds its `<style>` block from literal hex. Replace those
  literals with values read via `getComputedStyle(document.documentElement)`
  on the opener (`--bg`, `--surface`, `--surface2`, `--fg`, `--muted`,
  `--line`, `--accent`, `--accent-bright`, `--good`, `--mid`, `--bad`) so the
  panel always matches whatever palette is currently active on the page that
  opened it — not a `<link>` into the PiP document (untrusted to resolve
  reliably in that separate browsing context).
- Palette `<select>` `onchange` also rebuilds the PiP window's `<style>`
  `textContent` (if open) from fresh computed values, so an in-progress
  session updates live instead of requiring a reopen.

## Out of scope

Mode toggle on capture, `docs/scrims.html`, dashboard changes.

## Testing

Extend `tests/test_capture_scrim.py` (existing `node --check` coverage on
both files) with assertions that the picker markup/early-apply script exist,
mirroring `test_export.py`'s `test_dashboard_theme_css_ships_*` pattern. Full
`pytest` before commit. The PiP window itself can't be driven by jsdom
(`documentPictureInPicture` unsupported) — verified manually in a real
Chrome/Edge window.

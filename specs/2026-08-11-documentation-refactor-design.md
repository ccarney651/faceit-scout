# Documentation refactor — design

**Date:** 2026-08-11
**Status:** approved, ready for implementation planning

## Goal

The project has outgrown any one person's working memory. There is no single
document that explains what every part of OWDB is, how it works, and how the
parts feed each other. The existing docs each cover a slice — `README.md` covers
ingest, `SPEC.md` covers the capture design, `FEATURES.md` enumerates features —
and none of them draws the whole map.

Produce that map: **one document that explains every section of the project and
how the sections connect**, readable as a guided tour by the project owner and
usable as a retrieval index by any coding agent. Alongside it, remove the dead
files the repo has accumulated, and start a maintained changelog.

This is a **documentation and file-deletion change only**. No source code
behaviour changes.

## Background: what exists today

Current documentation, roughly 90 KB across four files with real overlap:

| File | Size | Covers | Problem |
| --- | --- | --- | --- |
| `README.md` | 16 KB | `faceit_sync` ingest, schema, the three data hazards | Says nothing about `owdb`, the browser capture app, scrims, or infra |
| `FEATURES.md` | 42 KB | Feature-by-feature reference for both packages | `specs/BACKLOG.md` flags it as "six features behind" |
| `SPEC.md` | 33 KB | `owdb` capture design reference | Design intent, not current-state; predates the browser capture app |
| `CLAUDE.md` | 15 KB | Agent guidance: commands, architecture summary, gotchas, roadmap | Claude-Code-specific filename; other agents never load it |

None of them answers "what is every top-level directory for?" or "if I change
X, what else breaks?". The architecture summary inside `CLAUDE.md` is the
closest thing to a map and it is compressed for agent consumption, not written
to teach.

**No `AGENTS.md` exists.** The repo already runs opencode (`opencode.json`,
`.opencode/commands/`), and `AGENTS.md` is the file opencode, Codex, Cursor, and
Amp read by convention. Those agents currently start with zero project context.

**Accumulated dead files**, confirmed by inspection:

- `crops/` — 1,530 tracked PNG debug crops, committed 2026-07-20 (`43c926a`),
  added to `.gitignore` afterwards but never untracked. Regenerated at runtime.
- `GUIDED` — marker file whose entire content documents `gui.main` /
  `_App(guided=True)`, in the native GUI removed 2026-08-08.
- `DISTRIBUTION.md` — reduced to a tombstone that redirects to `FEATURES.md`
  §2.7.
- `poc/browser-capture.html`, `poc/build_browser_poc.py` — proof of concept
  superseded by the shipped `docs/capture/`.
- Untracked working-tree junk: eleven stray `.log` files, `build/`, `dist/`,
  `owscout.sqlite3.bak-20260717-234643`, `owdb_refs.zip`,
  `dashboard_artifact.html`.
- `.opencode/` is not in `.gitignore`, so its `node_modules` tree shows as
  untracked noise in every `git status`.

**No changelog.** 690 commits since 2026-07-09 — 429 human, 261 CI
auto-updates — and no version tags. The history of why the project looks the way
it does exists only in commit messages.

## Decisions

These were settled during brainstorming and are not open in implementation.

1. **A new `ARCHITECTURE.md` sits above the existing docs; it does not replace
   them.** `README.md`, `FEATURES.md`, and `SPEC.md` stay as reference layers and
   are not rewritten. Rejected: a full restructure into a `docs/` tree, and a
   single mega-document absorbing all three — both are large rewrites that risk
   dropping hard-won detail (particularly the data-hazard analysis in
   `README.md`) for a presentation gain.

2. **`ARCHITECTURE.md` lives at the repository root**, not under `docs/`.
   `docs/` is the GitHub Pages web root — it holds `CNAME` (owdb.io) and
   `.nojekyll` — so any file placed there is published to the live site.

3. **Primary reader is the project owner learning their own project.**
   Explanatory tone: assumes the domain (Overwatch, FACEIT) is understood,
   explains the technical choices and the reasoning behind them, defines jargon.

4. **`AGENTS.md` becomes the canonical agent instruction file.** It carries the
   real content — commands, gotchas, conventions, invariants, and a pointer to
   `ARCHITECTURE.md`. `CLAUDE.md` shrinks to a short pointer that names
   `AGENTS.md` as canonical, plus anything genuinely Claude-Code-specific.
   Rejected: two full copies, which drift apart within weeks.

5. **`ARCHITECTURE.md` is written for retrieval as well as reading**, so a cold
   agent that greps into its middle still lands in context. Five mechanical
   rules, specified below. No separate agent-only copy of the document.

6. **Cleanup is limited to files nothing runs.** All seven root `.cmd`
   launchers, `verify_accuracy.py`, `Dockerfile`, `docker-compose.yml`, and
   `opencode.json` are kept. Rejected: also retiring the four native-capture
   `.cmd` files, since the Python capture CLI still works and is still used
   locally.

7. **`CHANGELOG.md` is reconstructed from full git history**, then maintained
   going forward. Rejected: starting fresh from today, which loses the narrative
   of how the project reached its current shape.

## Deliverable 1 — `ARCHITECTURE.md`

### Structure

Fourteen sections. Every subsystem section (3 through 8) uses one fixed
five-part template so the document is scannable once the shape is learned:

> **What it does** → **How it works** → **Files** → **How it connects** →
> **Gotchas**

| # | Section | Content |
| --- | --- | --- |
| 0 | Orientation | What OWDB is in one paragraph; a "I want to change X, where do I look?" routing table |
| 1 | The map | Full data-flow diagram; every artifact named with its writer and its readers |
| 2 | Repository tour | Every top-level directory and root file, one line each, tagged live / reference / dead |
| 3 | Ingest (`faceit_sync`) | `client.py` / `db.py` / `models.py` / `sync.py`; keyless transitive discovery; idempotent writes; scheduled fixtures; the three data hazards; the opaque FACEIT stat codes |
| 4 | Dashboard build | `faceit_sync/_dashboard.py` concatenation of the four parts; the `pure.js` testability seam; inline data vs `--external-data`; theme inlining; hero icons |
| 5 | Capture (Python `owdb`) | calibrate → refs → capture → match → integrity → comps → scout; why the CV layer stays thin and is excluded from mypy; the read-only `ATTACH` of the faceit DB |
| 6 | Browser capture app | `docs/capture/`; `getDisplayMedia` + tesseract.js; IndexedDB `owscout-capture` v4; the CSP `<meta>` trap; the publish path to the Worker |
| 7 | Scrims | The local-first side channel; why `docs/scrims.html` can read the capture app's IndexedDB; hero guid resolution via `capture/refs.json` |
| 8 | Infra and CI | Cloudflare Worker (uploads, Discord auth, the claims Durable Object); `.github/workflows/update.yml`; the two-independent-copies-of-the-DB problem |
| 9 | Data contracts | Exact shape of every file crossing a boundary: `data/captures/<season>/*.json`, `owdb_comps.json`, `docs/capture/data.json`, `docs/capture/refs.json`, the inlined dashboard data blob |
| 10 | Lifecycles and operations | Code wipes, season cutover, what CI does on a timer, how each piece deploys |
| 11 | Glossary | replay code, veto, comp, sub-role, wipe, division/tier, observation vs. capture, curator, and the rest of the project's jargon |
| 12 | Invariants | Imperative "never do this" rules, each with its failure mode attached |
| 13 | Testing map | Which test file guards which subsystem; the tests that must always run; the verification commands |

### Retrieval rules

These apply to the whole document and cost a human reader nothing:

1. **Literal repo-relative paths everywhere** — `faceit_sync/dashboard/pure.js`,
   never "the pure-logic module". Greppable in both directions.
2. **Every section opens with a one-line summary**, so a grep hit lands beside
   context rather than mid-argument.
3. **Self-contained paragraphs** — no "it" or "this" reaching back across a
   heading boundary.
4. **Table of contents with anchors; unique, stable headings** — so an agent can
   be pointed at `ARCHITECTURE.md#4-dashboard-build` directly.
5. **Invariants stated as imperative rules with the consequence attached** —
   "Never hand-edit `docs/index.html`: CI regenerates it from
   `faceit_sync/dashboard/head.html` on every run and the edit is lost."

### Accuracy requirement

**Every factual claim is verified against the code while writing.** Read the
modules; do not paraphrase `CLAUDE.md` or `FEATURES.md`, both of which contain
claims known to lag the code (`specs/BACKLOG.md` flags `FEATURES.md` as six
features behind). Anything that cannot be confirmed from source is either
omitted or marked explicitly as unverified — never guessed.

This is the primary quality risk in the whole change: a confidently wrong
architecture document is worse than no architecture document, because it will be
trusted by both the owner and every agent that reads it.

## Deliverable 2 — cleanup

**Delete from the working tree** (all untracked or ignored, none in git):
the eleven stray root `.log` files, `build/`, `dist/`,
`owscout.sqlite3.bak-20260717-234643`, `owdb_refs.zip`,
`dashboard_artifact.html`. `dashboard.html` is **kept** — it is the local
preview build.

**Remove from git:**

- `crops/` — `git rm --cached -r`, leaving the files on disk. They are
  regenerable runtime debug output and are already in `.gitignore`; the point is
  to stop tracking 1,530 files, not to destroy local data.
- `GUIDED`, `DISTRIBUTION.md`, `poc/` — `git rm`, deleted outright.

**Before deleting any tracked file, grep the repository for inbound references
and fix them.** `DISTRIBUTION.md` in particular is likely referenced from
`README.md` or `FEATURES.md`.

**`.gitignore` additions:** `.opencode/`, and `dashboard_artifact.html` beside
the existing `dashboard.html` rule (a literal filename, not a `dashboard*.html`
glob — the glob would also swallow deliberately-named preview builds).

**Explicitly kept:** all seven root `.cmd` launchers, `verify_accuracy.py`,
`Dockerfile`, `docker-compose.yml`, `opencode.json`.

## Deliverable 3 — `CHANGELOG.md`

Root-level `CHANGELOG.md`, Keep a Changelog section headings (Added / Changed /
Fixed / Removed), reverse-chronological.

**Date-based entries, not semantic versions** — the project has no version tags
and ships continuously to a live site, so a version number would be fiction.

Reconstructed from the 429 human commits between 2026-07-09 and 2026-08-11,
grouped by date into themed entries. The 261 CI auto-update commits collapse
into a single standing note rather than appearing individually.

A short "how to maintain this" header at the top states when to add an entry, so
the file stays alive rather than going stale after one session.

## Deliverable 4 — `AGENTS.md` and `CLAUDE.md`

`AGENTS.md` receives the current `CLAUDE.md` content, restructured:

- Commands, gotchas, conventions, and the roadmap stay inline — agents need
  those without a second file read.
- The architecture prose that `ARCHITECTURE.md` now covers in depth is replaced
  by a pointer with section anchors.
- The invariants list is stated imperatively with failure modes, matching
  `ARCHITECTURE.md` §12.

`CLAUDE.md` is reduced to a short file naming `AGENTS.md` as canonical, plus any
genuinely Claude-Code-specific guidance.

## Out of scope

- Rewriting `README.md`, `FEATURES.md`, or `SPEC.md`. They remain as reference
  layers. Bringing `FEATURES.md` up to date is a separate, already-tracked
  backlog item.
- Any change to `docs/index.html`, `docs/capture/`, `docs/scrims.html`, or
  anything the live site renders.
- Any source code change.
- Deleting the four native-capture `.cmd` launchers.

## Verification

- `.venv/Scripts/python.exe -m pytest` — full suite passes, confirming no
  deletion broke a test fixture or import.
- `.venv/Scripts/python.exe -m mypy faceit_sync` — stays clean.
- `git status` is quiet after cleanup apart from the intended changes.
- Every internal link in `ARCHITECTURE.md` resolves to a file that exists —
  checked mechanically, since the document is dense with paths and a broken path
  is exactly the kind of error that erodes trust in it.

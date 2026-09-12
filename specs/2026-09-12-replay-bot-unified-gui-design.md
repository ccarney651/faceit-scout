# Replay-bot unified GUI — design

## Problem

Running a scouting session today means three separate, manually-sequenced
steps, only one of which has a GUI:

1. Make sure `docs/capture/data.json` is fresh (the operator currently forces
   this by hand via the site's "Fetch new matches" button when CI's own daily
   cron has silently skipped — a known, still-open bug).
2. Start `node tools/replay_bot/run.js --code-stack ...` (or a filtered
   variant) from a console and watch text scroll for however many hours the
   run takes.
3. Separately start `node tools/replay_bot/review/server.js`, open a browser,
   review flagged maps, finalize, upload.

The ask: one GUI page that covers the whole loop — press a button to get
fresh codes, confirm Overwatch is ready, press Go, walk away, come back to a
finished run with anything uncertain surfaced for review.

## Scope (v1)

Confirmed with the operator during brainstorming:

- **Full pipeline**, not just review — fetching codes and running the capture
  loop join the existing review/finalize/upload GUI, all in one page.
- **Overwatch readiness is a manual precondition**, not automated. There is no
  existing automation for launching the client or navigating from a login
  screen to the Replay History tab (the three recorded chunks —
  `open-import`, `set-interval`, `leave-replay` — all assume that tab is
  already open), and building it would mean automating the most fragile part
  of the whole system for the first time, with no human present to unstick a
  patch prompt or login screen if it goes wrong. The GUI's Go step confirms
  the precondition; it does not attempt to satisfy it.
- **One localhost web page**, no framework, no build step — the same shape as
  today's `review/server.js` (Node's `http` module only).

## What "fetch codes" actually means

This needed correcting mid-design: `scrape_codes.js` is **not** the production
code source — its own header calls its output "arbitrary codes, for
testing," and `run.js`'s `--codes`/`--code-stack` flags exist for exactly
that (simulating an overnight run against a reusable test pool). Real league
codes come from `docs/capture/data.json` (`FEED` in `run.js`), which `run.js`
reads with no flags at all and filters to whatever's live and uncaptured.

That feed is rebuilt by CI, not locally. Getting a fresh one today means:

1. `POST` to `DATA.refresh_endpoint` (the same call the dashboard's "Fetch new
   matches" button makes) — kicks a `repository_dispatch` that pulls new
   FACEIT matches, re-merges every contribution, and republishes. Takes
   ~2 minutes.
2. Once that finishes, CI has committed a fresh `docs/capture/data.json` to
   `origin/main` — **not** to whatever branch the local checkout is on. Since
   `run.js` reads the file straight off local disk, the GUI needs to pull
   just that one file from `origin/main` (`git fetch origin && git checkout
   origin/main -- docs/capture/data.json`) regardless of the operator's
   current branch, rather than a full pull/merge.
3. `run.js`'s own freshness guard (`feed.built_at` must be today) then passes
   without `--stale-ok`.

So "Fetch codes" is really "refresh the feed," and it's a real network
round-trip with a ~2-minute wait baked in — not an instant local action. The
GUI should show that wait honestly (a spinner/status line, not a button that
looks broken for two minutes) and let the operator skip it if the feed is
already fresh today (check `built_at` first; only hit the endpoint if
stale).

## Architecture

Extend `tools/replay_bot/review/server.js` in place — same command
(`node tools/replay_bot/review/server.js`), same port convention — rather
than adding a new entry point. It already owns the review/finalize/upload
half; this adds a **Run** view alongside the existing **Review** view and a
few new endpoints. `page.html` gains a simple tab switch between the two;
which tab is active on load depends on whether a run is currently in
progress (see below).

New server-side pieces, all in the same dependency-free style as the
existing file:

- `GET /status` — polled by the page (every 1–2s while a run is active,
  otherwise idle). Returns: feed freshness (`built_at`, `fresh: bool`), the
  live/dead child-process state, and a tally derived from
  `state/attempts.json` (done / failed / total-so-far) — the same file
  `failureList()` already reads, so no new bookkeeping format is needed.
- `POST /refresh-feed` — does the `refresh_endpoint` POST + poll-for-done +
  `git checkout origin/main -- docs/capture/data.json`. Reports failure
  plainly (network error, endpoint down, git conflict) rather than silently
  leaving a stale feed.
- `POST /go` — refuses if a run is already active or the precondition
  checkbox wasn't confirmed. Otherwise `child_process.spawn`s `run.js` (with
  whatever filter flags the page collected — divisions/teams/limit — none by
  default) and keeps the handle in server memory. Streams stdout/stderr
  lines to any connected page via Server-Sent Events (one persistent
  connection, simplest thing that works for a single operator on
  localhost — no WebSocket library needed).
- `POST /stop` — same as today's operator Ctrl-C: writes nothing extra,
  just sends the child a signal it already handles gracefully (`run.js`
  finishes the in-progress map, then exits — never mid-map, per its own
  header comment).

The child process handle only lives as long as the server process does.
There's no reattach-after-server-restart story in v1 — the server is meant
to be started once and left running for the session, same as
`review/server.js` is today. If the server process dies mid-run, the bot
keeps running (it's an independent child), but the GUI loses its live feed
until restarted; `/status`'s `state/attempts.json`-derived tally still lets
a restarted server show where things stand.

## Flow

1. Open the page. If `state/attempts.json` shows an attempt with no
   matching outcome yet (or the child handle is alive), land on **Run**,
   showing live progress. Otherwise land on whichever view was open last, or
   **Run** if there's nothing to review.
2. **Run** view: feed freshness shown up top with a **Refresh** button if
   stale; a precondition checkbox ("Overwatch is open on the Replay History
   tab"); optional division/team filters (same ones `run.js` already
   supports); **Go** (disabled until the checkbox is ticked and the feed is
   fresh); a live log pane (streamed stdout) plus a compact tally (done/
   failed/remaining) computed from `/status`; **Stop**.
3. When the run ends (child exits, by completion or Stop), the page
   auto-switches to **Review**, pointed at the newest `out/*.review.json` —
   exactly today's `review/server.js` behavior, just reached without a
   second command.
4. On a successful **Upload** (existing flow, unchanged), the server also
   invokes `prune_frames.js` for that session and surfaces its one-line
   result ("frames/ wiped" or "left alone — N flagged maps") in the UI
   rather than only the terminal.

## Error handling

- Feed stale and operator hits Go anyway: same as today — `run.js` refuses
  and the page shows its actual refusal text, no `--stale-ok` button (that
  override "rarely should" be used per `run.js`'s own comment, and this is
  exactly the unattended-overnight case where a silent wrong answer is
  expensive).
- `run.js`'s existing two-consecutive-failure abort fires unchanged; the
  page just reports it (via the stream) rather than the operator finding a
  dead terminal in the morning.
- Child process crash (not a clean exit): `/status` reflects "not running"
  once the handle's `exit` event fires; whatever the log pane already
  captured stays visible for diagnosis.
- `/refresh-feed` network/git failures are reported inline, not swallowed —
  matches the project's general rule (`AGENTS.md`'s CSP/silence gotchas)
  that a silent failure here is worse than a loud one.

## Testing

- Pure logic (feed-freshness check reuse, attempts-tally derivation,
  view-to-land-on-open decision) factored so it's unit-testable the way
  `review/server.js`'s existing helpers already are (`server.test.js`).
- The SSE streaming and child-process lifecycle are integration-shaped, not
  unit-shaped — a small test spawning a fake child (a short-lived script
  standing in for `run.js`) and asserting the server's `/status` and stream
  behavior end-to-end is more useful here than mocking `child_process`.
- No browser automation for this — consistent with the rest of the repo's
  "pytest/node --test cannot see through a real browser" limitation; a
  manual pass (start the server, click through Run → Go against `--dry`,
  confirm the tab switch and log stream) is the acceptance step before
  trusting it on a real overnight run.

## Open questions for the plan

- Exact SSE vs. plain polling for the log stream — SSE avoids re-sending the
  whole log every poll, but plain polling is less code. Leaning SSE given
  runs are hours long and the log can get large; worth a quick sanity check
  during planning rather than deciding here.
- Division/team filter UI on the Run view can mirror `run.js`'s existing
  flag names directly rather than inventing new ones — low-risk, deferred to
  implementation.

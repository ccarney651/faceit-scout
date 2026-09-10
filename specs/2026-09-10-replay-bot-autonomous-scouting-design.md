# Replay-bot autonomous scouting — design

## 0. Why this exists

`replay-bot-full-automation-goal` (memory) states the direction: the bot should
eventually replace human captures entirely. Attribution shipped 2026-09-10, so
the bot now produces the same fields a human does. What it does **not** have is
the step between "the bot captured a map" and "that map is on the site":

- nothing tells the operator which of the bot's reads to trust and which to
  check — every read ships at face value, or not at all;
- there is no surface to correct a read before it uploads (the browser tool's
  Review UI only sees its own IndexedDB captures, not `out/*.json`);
- there is no upload path from `out/*.json` at all — `run.js` writes a file and
  stops.

The operator's stated end state (2026-09-10): *open Overwatch on the replay
list, start the bot, walk away. It scouts every queued FACEIT map. Afterwards,
open a local page, glance at every map with the low-confidence reads flagged,
fix what is wrong, upload.* This document is the plan for the middle three
pieces. Reliability of the unattended loop itself (the events-viewer `K` bug,
fixed in `bd65c9f`) is a precondition, tracked separately.

This is a **local** system, deliberately separate from `docs/capture/`. If the
bot proves reliable the contribution mechanism can retire and the site can read
the bot's output directly; nothing here should make that harder.

## 1. Scope

**In:**

- `resolve.js` — a map's per-sample reads aggregated to a per-round, per-slot
  result with an explicit confidence, and a `flags[]` list of what the operator
  should look at.
- A session review artifact (`out/<session>.review.json`) carrying everything
  the review page needs: resolved heroes, alternatives, vote support, per-read
  scores, frame-crop paths, attribution + its `conf`, and the flags.
- `tools/replay_bot/review/` — a tiny local server plus a static page. Reads the
  review artifact, serves the frames, shows every map round-by-round with
  flagged slots surfaced, lets the operator correct heroes and player
  attribution, and on finalize writes the clean contribution.
- Upload — the finalized contribution `POST`ed to the existing upload worker as
  contributor `replay-bot`.

**Out:**

- `sub_map` / `phase` — still deferred, own design (`replay-bot-full-automation-goal`).
- Any change to how the site *ingests* contributions. The bot's file merges
  exactly like a human's.
- Auto-upload. The operator always clicks.
- Packaging the review page as a desktop app. Local server + browser tab for now.

## 2. `resolve.js` — round resolution and confidence

### 2.1 What it consumes

`capture.js`'s `captureMap()` result: `samples[]` (each `{ t, at, a, b,
framePath }`, where `a`/`b` are five `{ name, guid, score }` reads), `segments`,
`missed[]`, and `attribute.js`'s once-per-map `{ a: {ids, conf}, b: {ids, conf} }`.

### 2.2 What it produces

Per map, a `rounds[]` where each entry is:

```
{
  round_no,
  from_t, to_t,
  a: [ slot, slot, slot, slot, slot ],
  b: [ ... ],
}
```

and each `slot` is:

```
{
  guid,               // the voted hero, or null if nothing was read
  name,               // display name, for the review page
  support,            // vote.js's share of frames that agreed (0..1)
  reads: [score...],  // every per-sample match score for this slot this round
  contested: bool,    // vote.js said the slot was genuinely split
  alt_guid,           // when contested, the runner-up
  player_id,          // from attribution (once per map, same for every round)
  player_conf,        // 'forced' | 'matched' | null, from assign.js
  flags: [ ... ],     // subset of the flag vocabulary below, this slot's
}
```

Voting reuses `vote.js` unmodified — it already resolves a slot across frames
and reports `support` and `contested`. `resolve.js` groups the map's samples by
round first (using `emit.roundNoFor`, already the shipped mapping), then votes
each slot within each round's frames.

### 2.3 The flag vocabulary

A flag is a reason to look, not a verdict. One slot can carry several.

| flag | raised when |
|---|---|
| `low-support` | the winning hero held < `SUPPORT_MIN` (0.67) of the round's frames for that slot |
| `low-score` | the winning hero's best per-sample score < `LOW_SCORE` (0.6, `capture.js`'s own constant) |
| `contested` | `vote.js` reported the slot split — a real mid-round swap, or noise |
| `no-read` | not one frame in the round produced a hero for this slot |
| `attribution-abstained` | `assign.js` returned `null` for this slot's player |
| `unknown-hero` | the guid is a `custom:` guid or absent from the feed's `hero_roles` |

Map-level flags, raised on the round they concern:

| flag | raised when |
|---|---|
| `round-unsampled` | a play segment produced zero samples |
| `sparse-round` | a round's realised samples < half its planned samples (`missed[]` heavy) |

`FLAG_THRESHOLDS` live as named constants at the top of `resolve.js`, each with
the one-line reason it is the value it is, the same way `capture.js` documents
`QUIESCE_MS`. They are first guesses and the header says so; the first few real
review sessions retune them.

### 2.4 What resolve.js does NOT do

- It does not drop a low-confidence read. A flagged slot still carries its best
  guess; the operator decides.
- It does not touch attribution. `assign.js` already abstains where the evidence
  is thin; `resolve.js` only surfaces that it did.
- It is pure. `capture.js`/`run.js` call it; it imports `vote.js` and the
  feed's `hero_roles`, nothing that touches the machine.

## 2.5 Side detection (added 2026-09-10 after the first review session)

The replay viewer does not always put the feed's `code.t1` on the left of the
screen, and `heroes_a` is whatever is on the left. When it is reversed, every
comp on the map is filed under the opponent, and nothing downstream catches it.

`attribute.js` OCRs both name strips on its once-per-map frame and runs
`docs/capture/engine/names.js`'s `confidentOrientation` — the browser tool's
own side-detect, unmodified — against both rosters. It returns:

- `'direct'` — the feed order holds, `side_a` = `code.t1`;
- `'swapped'` — `code.t2` is on the left; `run.js` relabels so `side_a_team*`
  is the team actually on the left (screen side stays `a` = left);
- `null` — the read was not decisive; feed order is kept and the review page
  flags the map so the operator confirms which team is on the left.

The per-side assignment inside `attribute.js` already uses the detected team,
so a swapped map's players are attributed correctly regardless of the label.

## 3. The session artifact

`run.js` currently writes one file: `out/replay-bot-<date>.json`, the
contribution. That stays, and is what uploads. A second file is added:

`out/replay-bot-<date>.review.json`:

```
{
  session: "replay-bot-2026-09-10",
  built_at, feed_built_at,
  maps: [
    {
      demo_code, match_id, game_no, map_name, map_category,
      side_a_team, side_b_team,
      rounds: [ <resolve.js output, per §2.2> ],
      attribution: { a: {...}, b: {...} },
      frames: { "<round_no>": { a: "<crop path>", b: "<crop path>" } },
      corrections: [],     // filled by the review page, empty until then
      status: "unreviewed" // -> "reviewed" once the operator signs it off
    }
  ]
}
```

`frames` points at **portrait-row crops**, not whole 7MB frames — one strip per
side per round, cut from the frame the round's first sample was read off, at
`calib.FROZEN.boxes`. `contact_sheet.js` / `crop.js` already do this cutting;
`resolve.js`'s writer reuses it. Crops live in `out/<session>/crops/`.

The raw per-sample reads stay in `review.json` (`slot.reads`) for audit — the
review page can show "this slot read Kiriko 5 times and Mizuki once" without
re-reading a frame.

## 4. The review page

### 4.1 Server

`node tools/replay_bot/review/server.js [<session>]` — defaults to the newest
`out/*.review.json`. A dependency-free `http` server on `localhost:<port>`
(port printed, and opened if `--open`). Routes:

- `GET /` — the page (one static HTML file, inline CSS/JS, same house style as
  `docs/capture/`).
- `GET /review.json` — the artifact.
- `GET /crops/<path>` — a crop, from `out/<session>/crops/`.
- `GET /hero-list` — `{guid, name, role, icon}` for the type-ahead, from
  `docs/capture/engine/refs.js` + `hero_icons.json` (reused, not copied).
- `POST /save` — the artifact back, with `corrections` and `status` filled.
- `POST /finalize` — rebuild the contribution from the reviewed artifact, write
  it over `out/<session>.json`, return a summary.
- `POST /upload` — `POST` the finalized contribution to the worker; return the
  worker's reply.

The server holds no state beyond the file. A crash loses nothing unsaved that a
reload would not.

### 4.2 Page

Per map, in queue order:

- A header: code, map, teams, and a one-line confidence summary ("2 rounds · 3
  flags · attribution 9/10").
- Per round, two rows (side a, side b) of five slots. Each slot: the portrait
  crop, the resolved hero name + icon, the attributed player, and the flags as
  small tags. A flagged slot is tinted; the map's flagged slots are also
  collected into a strip at the top of the map so nothing is missed by
  scrolling.
- Correcting a hero: click the slot → a type-ahead over `/hero-list` → pick →
  the correction is recorded against **that slot in that round** (not the whole
  map — the Nepal run showed a real between-round change). A "same for every
  round" affordance for the common case.
- Correcting a player: the roster for that side as one-click chips (roster is
  five), same as `docs/capture/`'s `assignPlayer`.
- Dropping a spurious read: a slot marked empty emits no hero for that
  round/side.
- "Mark map reviewed" per map; "Finalize session" enabled once every map is
  reviewed (or explicitly skipped).

### 4.3 Corrections are data, applied at finalize

The page never rewrites `rounds[]` in place. It appends to `corrections[]`:

```
{ round_no, side, slot, was_guid, now_guid | null, kind: "hero" }
{ round_no, side, slot, was_id, now_id | null, kind: "player" }
```

`finalize` replays them over `resolve.js`'s output to produce the final
per-round comps. This keeps the original machine reading visible beside the
human correction — the same reason `emit.js` keeps the bot's `tool_version`
distinct: a correction the operator later doubts can be read back.

## 5. Finalized contribution

`finalize` emits the `format: 1` contribution `emit.js` already produces, with
one change from today: **one observation per round per side**, the reviewed
comp, rather than one per sample.

- Rationale: a human contributor produces ~1 observation per round per side, and
  `owdb` derives opening comps and hero pools from observation frequency — many
  near-identical per-sample rows from the bot would skew that. The 2026-09-08
  design (§6.1) chose per-sample because there was no review step to collapse
  them; there is now.
- A `contested` slot the operator confirms as a real swap emits **two**
  observations for that round/side, at the sample timestamps where each hero
  held — the shape `docs/capture/` already uses for a mid-round swap.
- `ts` is the round's first sample time in ms (unchanged unit).
- `pairs` is the reviewed `[guid, player_id|null]` per slot, unchanged shape.
- `emit.js` grows a `fromRounds(rounds, code, opts)` entry point beside the
  existing `mapRecord`; the per-sample path stays for `capture_map.js` and any
  caller that wants raw observations.

## 6. Upload

`push(contribution)` in the review server: a plain `POST` to
`https://upload.owdb.io` with headers `X-Owdb-Name: replay-bot`,
`X-Owdb-Token: <token>`, `Content-Type: application/json`. Node's global
`fetch`; no Python. The token is generated once and kept in
`tools/replay_bot/state/upload-token.json` (gitignored) — the same throwaway
random identity `docs/capture/` keeps in `localStorage`, with the same meaning
(first upload under a name claims it; losing the token means the curator
reassigns, never data loss). `owdb/contribute.py`'s `push_to_endpoint` is the
reference for the request; this is a 15-line re-expression of it, not a shell
-out.

The worker writes `data/captures/<season>/replay-bot.json` and CI merges it
first-wins by git order — so a map a human already scouted keeps the human's
read, and the bot fills only the gaps. Exactly today's contribution behaviour.

## 7. Components

| file | new? | does |
|---|---|---|
| `tools/replay_bot/resolve.js` | yes | per-sample reads → per-round per-slot result + flags (§2) |
| `tools/replay_bot/resolve.test.js` | yes | `node:test` over synthetic sample lists |
| `tools/replay_bot/review/server.js` | yes | the local server (§4.1) |
| `tools/replay_bot/review/page.html` | yes | the review UI (§4.2) |
| `tools/replay_bot/review/server.test.js` | yes | routes, finalize, correction replay |
| `tools/replay_bot/emit.js` | changed | `fromRounds()` entry point (§5) |
| `tools/replay_bot/run.js` | changed | call `resolve.js`, write `review.json` + crops |
| `tools/replay_bot/state/upload-token.json` | runtime | the claim token, gitignored |

## 8. Testing

- `resolve.js` — synthetic `samples[]` fixtures: a unanimous round, a
  one-frame misread outvoted, a genuine mid-round swap (→ `contested` +
  `alt_guid`), an unsampled round, an attribution abstention. Each asserts the
  exact `flags[]`.
- `emit.fromRounds` — a reviewed `rounds[]` → the expected `observations[]`,
  including the two-observation contested case and the `pairs` zip.
- `review/server.js` — `node:test` against a temp `review.json`: each route,
  `finalize` replaying a hero correction and a player correction, `upload` with
  a stubbed `fetch` (injected, same DI shape as `io`).
- The page gets no automated test beyond the server; it is small and its logic
  is the server's.
- Live: one end-to-end session — capture a handful of maps, review them, upload,
  confirm the maps land on owdb.io attributed to `replay-bot`.

## 9. Build order

1. `resolve.js` + tests. `run.js` writes `review.json` + crops alongside the
   existing output. No behaviour change to the contribution yet.
2. `emit.fromRounds` + tests.
3. `review/server.js` + `page.html` + tests — read, render, correct, save.
4. `finalize` — corrections replayed, contribution rewritten per-round.
5. `upload` — token, POST, worker reply surfaced.
6. Live end-to-end session; retune `FLAG_THRESHOLDS` and `QUIESCE_MS` from what
   it shows.

## 10. Risks

| risk | handling |
|---|---|
| `FLAG_THRESHOLDS` are guesses | named constants with stated reasons; step 6 retunes them against real reads, like `assign.js`'s `FLOOR`/`MARGIN` |
| per-round observations diverge from what `owdb` expects | §5 — verified against `owdb/contribute.py`'s reader before step 4 ships; the per-sample path stays available |
| the review page is one more UI to maintain | kept dependency-free and server-thin; no framework, no build step |
| a between-round comp change read as noise, or vice versa | `contested` surfaces it either way; the operator confirms swap vs misread per slot |
| `QUIESCE_MS=400` marginal post-speedup (seen on the validation run) | measured and retuned in step 6 with `probe_limits.js`, not guessed at here |

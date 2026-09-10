# Replay-bot player attribution — design

## 0. Why this exists

`specs/2026-09-08-replay-bot-design.md` §6.2 named this gap on the day the bot
shipped: `pairs` — the `[[hero_guid, player_id|null]…]` per observation that
says who was on what, not just which side — is hardcoded to `[]`, because "player
attribution needs name OCR the bot does not yet run." That was a known, accepted
absence at v0.1, not an oversight.

The goal now is broader than closing that one field: replay-bot should
eventually be able to fully replace a human operator's contribution for a
FACEIT league game, end to end. Auditing what a human capture supplies that
the bot's `pairs: []`/`sub_map: null`/`phase: null` currently don't found that
`bans` and `winner_side` are **not** real gaps — `faceit_sync` already sources
both directly from FACEIT's own match API (`hero_bans`, `games.winner_faction`),
independent of any capture, bot or human. Attribution is the one gap nothing
else in the system covers. `sub_map`/`phase` is real but smaller, and only ever
existed in the old desktop `.exe` — a separate design, later.

This document is the plan for closing `pairs`. It supersedes the `pairs` row of
§6.2's table.

## 1. What already exists

Player attribution shipped live on `docs/capture/index.html`/`scrim.html` on
2026-08-18 (`specs/2026-08-16-player-assignment-design.md`). Auditing that path
for reuse, the same way `crop.js`/`match.js` already reuse pieces of it for hero
matching:

| Module | Portable as-is? | Why |
|---|---|---|
| `docs/capture/engine/names.js` | Yes | Pure string similarity (`simScore`, `normName`, `_matchTotal`). Already documented as working "as a browser global and as a CommonJS module for node:test." No DOM. |
| `docs/capture/engine/assign.js` | Yes | Pure function `assign(reads, players, slotRoles, opts) -> {ids, conf}`. Requires `names.js` the same way whether run in a browser or Node. No DOM. |
| `docs/capture/engine/frames.js` (`nameRow`, `findNameRow`, `findNameSpan`) | No | `findNameRow`/`findNameSpan` are pure RGBA-array math, but the `nameRow()`/`cellNameSpan()` wrappers around them call `ctx.doc.createElement('canvas')` — a browser DOM dependency `match.js` and `crop.js` do not have to carry, because they never touch this file. |

`match.js` already `require()`s `docs/capture/engine/refs.js` and `util.js`
directly, unmodified, because those are pure. `crop.js` does not do that for
`refs.js`'s `learnCrop()` — that function is canvas-shaped — and instead
mirrors it step for step against `@napi-rs/canvas`, with its header saying so
explicitly: *"THIS FILE DELIBERATELY MIRRORS learnCrop() ... and that is the
whole point of it."* This design follows the same split: `names.js` and
`assign.js` get `require()`d unchanged; the name-row finding gets mirrored the
way `crop.js` already mirrors `refs.js`.

## 2. Scope

- One capture's worth of attribution: given a map already being captured (hero
  reads already resolved per slot), determine which FACEIT player is standing
  in each of the ten slots, once, and stamp it onto every observation of that
  map.
- Full role-constraint parity with `assign.js` — not OCR-only. The feed already
  carries role per player per game for free (`lineups[…].players[].role]`), so
  skipping the constraint step means re-deriving it later regardless once
  OCR-only proves insufficient on some map, per the questions this design
  already answered.
- Resolved **once per map**, off the first frame a sample was already taken
  from — not once per sample, not once per round. Replay HUDs are static per
  slot for the life of a map (confirmed visually against tonight's `7V4END`
  frames: `SHIRO`/`VOID`/`TANNGRISNIR`/`ENPASSANT`/`ICEICEICE` sit fixed above
  their portraits). A mid-map substitution would go undetected; accepted, since
  league substitutions mid-map are rare and this can be revisited if it ever
  actually happens.
- Out of scope: `sub_map`, `phase` (§0, deferred to its own design — no existing
  capture path does this today, live or replay, so there is no precedent to
  reuse and it needs its own investigation).

## 3. Components

**`tools/replay_bot/nameplate.js`** (new). Mirrors `frames.js`'s `findNameRow`,
`findNameSpan`, `nameRow` and `cellNameSpan` against `@napi-rs/canvas` instead
of DOM canvas — same reasoning, same shape as `crop.js`'s relationship to
`refs.js`. Exports a crop-the-name-strip-for-one-slot function that `attribute.js`
calls five times per side.

**`tools/replay_bot/attribute.js`** (new). Per-map orchestration:

1. Take the frame the map's first successful sample already read (no extra
   grab).
2. For each side, for each of its five slots: crop the name strip
   (`nameplate.js`), OCR it (tesseract.js), collecting five raw strings.
3. Build `players` per side from `lineups[matchId:gameNo][code.t1|t2].players`
   — `{id, names: [game_name, nick], role}` per player, confirmed against a
   real match (`code.t1`/`t2` are exactly the team GUIDs keying `lineups`).
4. Build `slotRoles` per side from the hero already recognised in that slot
   (the sample's `heroes_a[i]`/`heroes_b[i]` guid) looked up in the feed's
   `hero_roles[guid]`.
5. Call `Assign.assign(reads, players, slotRoles)` per side (`require()`d
   directly from `docs/capture/engine/assign.js`, unmodified). Returns
   `{ids, conf}` per side.
6. Return `{a: {ids, conf}, b: {ids, conf}}` for the map, or throw if the frame
   itself cannot be read (crop/OCR hard failure) — the caller decides what a
   throw means (§7).

**Wiring into `capture.js`/`run.js`**: called once, right after the first
sample of a map is captured and read, alongside (not instead of) the existing
hero-matching flow.

**`emit.js`**: `observations()` currently writes `pairs: []` unconditionally.
Changed to accept the map's `{a, b}` attribution result (or `null`, if
attribution didn't run or failed) and zip it against each observation's own
`heroes` in slot order: `pairs: heroes.map((guid, i) => [guid, ids[i]])` —
`ids[i]` may itself be `null` (§6), which is a supported absence the schema
already tolerates, same as `pairs: []` is today.

## 4. Geometry — the one thing that isn't just wiring

`frames.js`'s `NAME_BAND_TOP`/`NAME_BAND_BOT` (0.30–1.15, fractions of the
portrait box height) are fitted to **live** `getDisplayMedia` geometry.
`player-attribution-live`'s own notes record that replay-viewer frames measure
the portrait strip ~6% wider and ~14% taller than live geometry — the exact
mistake that memory warns the next person off making twice. These fractions
must not be assumed to transfer; they need re-fitting against replay-bot's own
frozen `calib.FROZEN.boxes`, verified against real replay-bot frames (plenty of
kept `.png` samples already on disk with clearly legible names) before being
frozen as replay-bot's own constants — the same "fit against the box the tool
actually produces, not a screenshot" discipline `calibration-relative-geometry`
already established for the portrait boxes themselves.

## 5. Confidence and abstention

Unchanged from `assign.js`'s own contract, because nothing about running it
from a replay changes what a slot's evidence means: `'forced'` (role alone
settled it, no name evidence used — this is how a totally unreadable HUD still
tags the tank), `'matched'` (cleared both the floor and the margin), or `null`
(abstain — the merge already treats a missing `player_id` as a supported
absence, never a guess). `conf` itself is not written into `pairs` — only
`ids`, with `null` standing in for an abstained slot, same shape the schema
already expects.

## 6. Failure isolation

Attribution failing must not fail the map capture. The core value of a
captured map — hero comps, round structure — does not depend on knowing who
was playing which hero, and a map is a one-shot code: burning it because OCR
crashed on the name strip would be strictly worse than shipping the map without
`pairs`. So `attribute.js`'s call is wrapped at the call site; any throw (bad
crop, OCR failure, missing `lineups` entry for an ad-hoc/synthesised code) logs
a warning and the map proceeds with `pairs: []` for every observation, exactly
today's behaviour. This is the one place this feature is allowed to degrade
silently rather than refuse loudly — because the alternative (refusing) would
throw away real captured value over an additive feature, not because degrading
silently is this codebase's normal instinct.

## 7. Testing

- **`nameplate.js` unit tests**, `node:test`, against new corpus witnesses —
  `corpus.js` gets one or two new entries (frames already on disk have legible
  names; a witness needs adding the same hand-labelled way every other one was)
  so the row-finding is checked against real replay pixels, not live ones.
- **`attribute.js` unit tests** with an injected fake OCR (same
  dependency-injection shape as `io` throughout replay-bot — a function that
  returns canned strings per crop) so the orchestration, the `lineups` lookup,
  and the `assign()` wiring are all tested without a real tesseract call in the
  suite.
- **`emit.js` unit tests** extended to cover the new `pairs` zip, both the
  attributed and the `null`/failed-attribution paths.
- **Measured accuracy, live.** Same caveat as hero accuracy: FACEIT codes 403
  on owreplays, so there is no automated answer key for who-played-what on a
  league game either. `verify_sheet.js`'s pattern — render the crop, look at it
  — extends naturally: render the name crop next to the assigned player and eye
  it, the same way D.Mon's hero misread was caught by looking rather than by an
  automated score.

## 8. Risks

| Risk | Handling |
|---|---|
| Replay name-band geometry differs from live's | §4 — fit and freeze against replay-bot's own frames, never borrow live's constants |
| A mid-map substitution | Accepted (§2); revisit only if it's actually observed to happen |
| `lineups` entry absent (ad-hoc/synthesised codes, a stale feed) | `attribute.js` throws, caller degrades to `pairs: []` (§6) — same as `assign.js`'s own live fallback when `lineups` is missing |
| tesseract.js adds real weight/startup cost to the toolchain | Runs once per map, not per sample — the live tool's per-snapshot cost concerns don't apply here |
| `FLOOR`/`MARGIN` (45/1) were tuned against live OCR error characteristics | Replay footage is rendered UI text with no broadcast/camera noise, plausibly cleaner than live — worth measuring once real reads exist rather than assuming the live thresholds transfer unchanged |

## 9. Open items

- Exact corpus witnesses for `nameplate.js` testing — pick frames once the
  geometry-fitting pass (§4) is done, so the same frames double as both.
- Whether `FLOOR`/`MARGIN` need re-tuning for replay OCR specifically, once a
  real batch of reads exists to measure against (mirrors
  `player-assignment-design.md` §7's own "replace the synthetic model" plan).
- `sub_map`/`phase` — explicitly deferred, own design, no existing precedent to
  build from (§0, §2).

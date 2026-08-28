# Scrim hero bans — design

One hero ban per team, chosen and enforced in-game during setup, rendered on the
spectator view so the capture tool can read it instead of the operator
remembering it.

Status: design agreed 2026-08-27. Not implemented.

## 0. Why

Bans are the one part of the scrim loop that still depends on someone's memory.
The capture panel has had a role-grouped ban picker since 2026-08-19, but it
records what the operator *tells* it, and the operator is either recalling the
draft after the fact or writing it down mid-scrim. Everything else in the loop —
who is on which hero, which side we are, the replay code — is read off the
screen.

A ban the game itself enforced is also a ban that cannot be misremembered, which
makes the recorded scrim more trustworthy than the current honour system.

## 1. Decisions

Settled with the operator before design:

- **The workshop enforces the ban**, it does not merely display it.
  `setAllowedHeroes` removes the hero for all ten players.
- **One code, not two.** The ban phase lives inside `scrim_owdb.opy`. A workshop
  script cannot load another script, and it only starts running once a map is
  already loaded.
- **One ban per team**, during setup, with no turn order and no explicit skip.
- **The two bans may not share a role.**
- **A map may not start with exactly one ban** — two or none.
- **The ban list stays on the spectator view for the whole map**, so capture can
  read it at any point, including from a replay.

### 1.1 What was ruled out, and why

- **Map picking in the workshop.** Impossible. The whole API carries three map
  constructs — the `Map` type, the `Map Rotation` lobby setting, and
  `getCurrentMap()`, which is `isConstant`. Nothing sets, queues or advances a
  map. A map-veto tool would have to live in the web panel, as its own feature.
- **A ban-phase code that hands off to the scrim code.** Impossible. Importing a
  workshop code is a manual host action that replaces the running script.
- **A hero-select menu drawn in workshop text.** Rejected: it needs a hard-coded
  hero list, which becomes a fifth place every new hero must be registered
  (`AGENTS.md` already lists four). Reading `getHero()` needs none.
- **Fuzzy matching of the OCR'd hero name.** Rejected — see §4.3.

## 2. What the workshop can actually do

Verified against the bundled OverPy definitions
(`tools/scrim_code/node_modules/overpy/overpy.js`), not assumed:

| Need | API | Notes |
| --- | --- | --- |
| Enforce a ban | `player.setAllowedHeroes(heroes)` | "If a player's current hero becomes unavailable, the player is forced to choose a different hero and respawn." |
| Undo | `player.resetHeroAvailability()` | |
| Role of a hero | `getTankHeroes()` / `getDamageHeroes()` / `getSupportHeroes()` | All `isConstant`, all dynamic — no hero list to maintain |
| Full roster | `getAllHeroes()` | |
| Map name | `getCurrentMap()` | Read-only |

**A `Hero` value embedded in a string renders as its name in readable text —
CONFIRMED IN GAME 2026-08-27.** This was the load-bearing assumption of the whole
design; had it rendered as a glyph, the read would have needed a workshop glyph
reference set and this feature would sit behind phase 3. It does not.

Checked with `tools/scrim_code/probe_hero_text.opy`, which draws the same heroes
twice — once bare, once through `heroIcon()` — so the comparison is on screen
rather than in the abstract. The bare row rendered `LÚCIO / D.VA / TORBJÖRN` and
`SOLDIER: 76 / WRECKING BALL / JUNKER QUEEN` as words; the `heroIcon()` row
rendered portraits.

Three findings came with it:

- **`getCurrentMap()` renders as text too** (`MAP : SAMOA`). The map-name
  verification stubbed in `specs/BACKLOG.md` is therefore possible, not
  impossible — see §4.1.
- **The HUD font renders everything in UPPERCASE.** Harmless, because the
  normalization in §4.2 lowercases, but a case-sensitive matcher would fail on
  every hero. Do not write one.
- **All four hard spellings survive intact** — the accent in `LÚCIO`, the umlaut
  in `TORBJÖRN`, the colon in `SOLDIER: 76`, the full stop in `D.VA`. These are
  exactly the spellings `refs.json` does not use (§4.2).

## 3. The in-game half

Current behaviour, plus a ban phase. New settings live under **`1. Hero Bans`** —
panels 1, 6 and 8 are free because the strip removed Language, Log Generator and
Debug, and the in-game list currently reads 2,3,4,5,7. Numbering it 1 also puts
it in the order it happens.

### 3.1 Input

During setup, switch to a hero and press `Interact + Melee`. Pressing it again
while on your own banned hero **clears** the ban. Clearing is not a convenience:
it is the only route back to "neither team banned" once a team has banned, and
R3 below makes that a state teams will need to reach.

The binding is `Keybind_Command + Keybind_BanHero`, following the existing
pattern where every combo pairs Command with one other button, and it is
rebindable under `7. Keybinds` like the rest. **Melee because the obvious choice
is already taken**: `Keybind_Command` defaults to Interact and `Keybind_Ready` to
Reload, so `Interact + Reload` is Ready Up. Interact is also paired with Jump
(defender teleport) and Ultimate (add setup time). Melee is free, deliberate to
press, and not a movement key — which matters for a bind used while standing in
spawn during setup.

### 3.2 The three rules

| | Rule | Mechanism |
| --- | --- | --- |
| R1 | One ban per team | A second confirm replaces the first |
| R2 | The two bans may not share a role | Membership test against the role getters, evaluated against the *other* team's current ban |
| R3 | A map may not start with exactly one ban | A guard in the match-start rules |

R2 is checked on **every** confirm including a change, or team 1 could ban a
tank, wait for team 2 to ban a tank, then switch and collide.

### 3.3 Where R3 attaches

Both match-start rules already carry a guard of exactly the right shape:

```
if getNumberOfPlayers(Team.ALL) < ReadyUp_MinimumPlayersToStart:
    smallMessage(getAllPlayers(), "Both teams ready, but not enough players...")
    return
```

The ban symmetry check is a second guard beside it. **It must be added to both
rules** — `Setup: Both Teams Ready, Start Match (Captain-Only Mode)` and
`(All Players Mode)`. This is a forked cluster of the same kind as the capture
pages' snapshot/review/finish functions, and it fails silently: a lobby in the
other ready mode starts with one ban and the record is wrong with nothing saying
so.

### 3.4 The timer, which R3 does not cover

The guard only blocks the ready path. Setup time expiring ends setup regardless,
so an idle lobby holding one ban would start anyway.

**At ~5s remaining with exactly one ban, clear the lone ban and announce it.**
The invariant holds — no map ever starts with exactly one ban — and it fails
toward no-bans rather than blocking a live scrim. Freezing the setup timer was
the alternative and was rejected: `ReadyUp_FreezeSetupTime` is a user setting
that defaults off, and overriding someone's setting to protect our feature is
worse than dropping the ban.

Every path in this feature fails open. That is the opposite of the scrim page's
lock, which fails closed, and deliberately so: there the risk worth engineering
against is shipping an unfinished tool, here it is stalling a live scrim.

### 3.5 Reset

`resetHeroAvailability()` runs at phase **start**, not only at end, so each map's
bans are independent regardless of what the previous map left behind.

## 4. The capture half

### 4.1 The HUD contract

One row, `SpecVisibility.ALWAYS`, persistent for the map, in the existing left
column beside the scoreboard:

```
BANS  Sombra | Mauga
MAP   Ilios
```

- **`BANS` is a constant literal anchor.** The row is located by finding it, the
  way §5.3 of the scrim-mode design anchors the scoreboard on its legend rows —
  not by a fixed offset from the calibration box. The replay-code reader is the
  standing warning about offsets from `boxes.a`.
- Order is Team 1 then Team 2.
- **The zero case is drawn explicitly, as `BANS  none`.** An absent row means
  "could not read"; a present row reading none means "known: no bans". Without
  that distinction the reader has to guess, and guessing is how a wrong record
  gets written.
- `MAP` is close to free once a text row exists, and it closes the "map-name
  verification is stubbed" item in `specs/BACKLOG.md`: capture could verify the
  map against the HUD rather than trusting the panel selection. **Confirmed
  rendering in game 2026-08-27** as `MAP : SAMOA` (§2). Note the backlog framed
  this as an open question — "is the map name reliably on the observer HUD at
  all?" — and the answer is that it is not, but the workshop can put it there.

### 4.2 The read path

Crop the anchored row, then `ocrRead()` — the deadline-wrapped reader. Never
`w.recognize()` directly; a test fails if you do, because a stalled recognize
takes every other read down with it.

Then normalize and look up. **The name the workshop draws is the game's display
spelling, which is not the spelling `refs.json` stores.** `heroes.js` already
carries the scar: "D.Va", "Soldier: 76" and "Lifeweaver" are display spellings
`refs.json` never writes, and when a copy of that table used them those heroes
matched nothing and fell out of every role split, silently.

One normalization resolves it — NFKD accent-fold, lowercase, strip
non-alphanumerics:

| Workshop draws | `refs.json` stores | Normalized |
| --- | --- | --- |
| `D.Va` | `DVa` | `dva` |
| `Soldier: 76` | `Soldier 76` | `soldier76` |
| `Lúcio` | `Lucio` | `lucio` |
| `Torbjörn` | `Torbjorn` | `torbjorn` |
| `Lifeweaver` | `LifeWeaver` | `lifeweaver` |

The workshop draws these in UPPERCASE (`LÚCIO`, `D.VA`, `SOLDIER: 76`) — verified
in game, §2 — which the lowercase step absorbs. A case-sensitive matcher would
fail on every hero.

Measured over all 53 hero names in `refs.json`: **zero collisions**, every name
reaching a distinct GUID. The index is built from `refs.json`, which both capture
pages already load — so this adds **no new place to register a hero**.

### 4.3 Validation by shape, not by confidence

The in-game rules hand the reader three checks for free:

| Check | From | A failure means |
| --- | --- | --- |
| Count is 0 or 2, never 1 | R3 | Misread — no real scrim starts with one ban |
| The two have different roles | R2, via `heroes.js` ROLE_MAP | Misread |
| Both resolve to known heroes | The closed 53-name vocabulary | Misread |

This is the same principle as §5.2 of the scrim-mode design, and it is stronger
than an OCR confidence threshold because it tests rules the game enforced rather
than how sure tesseract felt.

**Why this read is safer than the replay code.** A mis-cropped replay code
returns a well-formed *wrong* code — any six characters in the alphabet are
valid, which is why it needed five geometry probes. Hero names are a closed
vocabulary with no normalization collisions, so a mis-crop yields text matching
nothing and the read abstains. The failure mode is "no read", not "wrong read".

**The one way to lose that property is fuzzy matching.** Exact-after-
normalization only, no edit-distance fallback. It looks like an obvious
improvement and it is not: it converts a safe abstention into a plausible wrong
answer. That belongs in a comment at the call site.

### 4.4 Integration

A `Read bans` button on the capture panel, mirroring the existing `Read code`
button: it **prefills** the role-grouped ban picker and the operator confirms or
corrects. It does not replace the picker. An abstention leaves the picker empty
and the operator picks by hand exactly as today, so nothing regresses when the
read fails.

Storage is unchanged. `bans: [<guid>, ...]` already exists on the record — no
schema change and **no IndexedDB version bump**, which matters because the
capture app owns that schema and bumping it from the wrong place is a documented
footgun.

## 5. What this is not

- Not a map pick or veto (§1.1) — that would be a panel feature.
- Not multiple bans per team, and not a draft. One each.
- Not a replacement for the panel's ban picker.
- Not usable with ScrimTime Lite. Lite is defined as ScrimTime minus the
  Spectator Scoreboard and Log Generator, and the scoreboard is what capture
  reads; the bans described here are drawn by *our* code. Which workshop code the
  lobby runs decides what capture can see at all.
- **Not available in a lobby someone else hosts.** Confirmed with the operator
  2026-08-27: scrims today run a mix of ScrimTime and ScrimTime Lite depending on
  who hosts. The ban row is drawn by `scrim_owdb.opy`, so bans are recorded only
  in lobbies the operator hosts with our code. Everywhere else the panel's manual
  ban picker stays the only path — which is exactly why §4.4 prefills the picker
  rather than replacing it.

### 5.1 What the host mix costs, by feature

| Capture feature | Reads | ScrimTime | Lite | Ours |
| --- | --- | --- | --- | --- |
| Hero comps | Observer HUD portraits (base game) | ✓ | ✓ | ✓ |
| Opponent identification | Workshop ready-up list | ✓ | ✓ | ✓ |
| Stats (phase 3) | Workshop spectator scoreboard | ✓ | **✗** | ✓ |
| Hero bans (this design) | Our ban row | **✗** | **✗** | ✓ |

Comps are unaffected by any of this — they come off the base game's observer
HUD, not the workshop. The exposure is that **phase 3 can never work in a Lite
lobby**, and bans only work in ours.

## 6. Testing

**In game, by a human. Verified 2026-08-27/28 unless marked otherwise:**

1. ~~A bare `Hero` in a string renders as readable text, not a glyph.~~ **DONE** —
   it does, and `getCurrentMap()` too (§2).
2. ~~The ban row does not collide with the scoreboard.~~ **DONE** — no collision.
   The player card that overlapped the probe was the voice-chat indicator, which
   does not exist in the replay viewer.
3. ~~The rows render in the replay viewer.~~ **DONE** — confirmed in a real
   replay, which is the context capture actually reads from.
4. ~~Bans persist across rounds of the same map.~~ **DONE** on Control (Nepal)
   and Hybrid. Escort shares the asymmetric code path.
5. ~~The per-team `BAN:` lines render for players during setup and clear when the
   round starts.~~ **DONE.**
6. ~~The ban keybind hint renders with each player's own binding.~~ **DONE** —
   shown as `[F + MOUSE 4]` for an operator with melee on mouse 4, confirming
   `inputBindingString` resolves per player rather than to a fixed key.
7. **Still open — `Read bans` against a real replay.** The OCR path has never
   faced the workshop font at the operator's resolution. This is the last thing
   between the feature and being trusted.
8. **Still open — `setAllowedHeroes` across a full team.** Banning works, but it
   has only been exercised in a near-empty lobby; that a player already on the
   banned hero is force-swapped is untested with ten people.
9. **Still open — the R3 guard in *both* ready modes** (§3.3), and the setup
   timer expiring while exactly one ban is set (§3.4).

### 6.1 Two in-game failures worth not repeating

Both cost a test cycle and neither was visible from the compiled output.

- **`destroyAllHudTexts()` wipes everything when the match starts.** A rule that
  creates HUD text once, on a condition that never transitions again, is erased
  and never returns — which is why the ban row vanished at "DEFEND OBJECTIVE A"
  on the first test. The scoreboard survives by being conditioned on
  `isGameInProgress()` with a `wait()`, so it is *recreated* after each wipe.
  Anything that must outlive the setup phase has to follow that pattern.
- **`getAllPlayers()` with `SpecVisibility.NEVER` renders for nobody.** Every
  `NEVER` row in `scrim_owdb.opy` targets `eventPlayer`; every `getAllPlayers()`
  row uses `ALWAYS` or default. The combination is used nowhere else and it
  displays to no one — spectators *and* players. Reaching for `NEVER` to keep the
  spectator view tidy is how the per-team lines were invisible for two builds.

**At the desk:**

- Normalization and name-to-GUID mapping: pure, unit-tested beside
  `heroes.test.js`.
- The three shape checks: pure, unit-tested.
- That `scrim_owdb.opy` still compiles: `npm run build` in `tools/scrim_code/`.
- `tools/capture_divergence.py` before and after, since the panel is shared.
- The browser verifier after any capture-page change.

## 7. Open items

- **Hero names render in the viewer's client language.** The strip already
  removed multi-language UI, so this is consistent, but the read assumes an
  English client. Not worth solving until it bites.
- **Which workshop code the operator's scrims actually run** (§5). If they run
  Lite, phase 3's stats read has nothing to read, ever.
- **A source-level diff against ScrimTime Lite** is not possible without its
  export. Obtain it the way `dkeeh_raw.txt` was obtained: import `0PP1T` in a
  custom game and copy the settings out.
- **`tools/scrim_code/README.md` overstates the strip's saving.** It says the
  strip "roughly halves the compiled size"; measured, `scrim_owdb.txt` is 50,446
  bytes against `dkeeh_raw.txt`'s 141,746 — 35.6%, closer to a third. Correct it
  when this work lands.

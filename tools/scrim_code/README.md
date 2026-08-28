# OWDB Scrim workshop code

A **lean custom-game code** for Overwatch 2 scrims, built for the OWDB project
(`docs/`). It is a **stripped derivative of Scrimtime (DKEEH) v1.73** by Caldoran,
re-authored via the OverPy decompiler so teams can keep the Scrimtime experience
they already know at a lower server cost.

## Why strip Scrimtime instead of writing from scratch

- Feature-parity with the industry standard — teams already know the ready-up,
  add-time, defender-teleport and scoreboard UX.
- The **spectator scoreboard layout is preserved**, which is exactly what the
  OWDB capture tool will OCR in the scrim-tracker feature (Phase 2+).
- Bloat removed (see below) cuts the compiled size to **about a third** and
  removes the per-event processing that tanks host FPS. Measured 2026-08-27:
  `scrim_owdb.txt` is 50,446 bytes against `dkeeh_raw.txt`'s 141,746 — 35.6%,
  across 35 rules versus 80.

### What was stripped

| Removed | Why |
|---|---|
| Log Generator (~20 event-driven rules: kills, damage, healing, abilities, ults, hero-swap tracking…) | The biggest FPS cost; OWDB reads the screen, not a log. |
| Multi-language UI (40×7 language strings + Change Language keybind) | Enormous string budget, unused in this team. |
| Debug mode (5 rules + settings) | Dev-only. |
| Legacy scoreboard presets (Legacy Standard, Legacy OWL/OWC) | Only the Standard preset is kept; fewer HUD texts. |
| Disabled mode presets (Control 6v6, Balanced Overwatch variants) | Dead settings. |

### Kept (feature set)

- **Setup phase** — ready-up toggle, hold-to-force-team-ready, add setup time,
  defender teleport between objective and spawn.
- **Map completion** — Assault/Escort/Hybrid full-attack guarantee, Control ends
  after 3 rounds, Flashpoint after 5 captures.
- **Spectator scoreboard** (Standard preset, Small/Medium/Large, all grouping
  styles) — created with `SpecVisibility.ALWAYS`, so it renders for spectators
  **and in replays**; that is what the capture tool reads.
- **Hero bans** (added for OWDB, not in Scrimtime) — one per team during setup,
  enforced with `setAllowedHeroes`, the two forced to different roles, and the
  map blocked from starting with exactly one. Drawn on the spectator view as
  text so the capture tool can read it. Toggle under `1. Hero Bans`.
- **Match time display** + host-spectator scoreboard toggle (Z+Q).
- The in-game **Settings panel** (ready up / setup phase / map completion /
  scoreboard / keybinds) with Scrimtime's original tunables.

## Build

Requires Node + npm (OverPy is an npm package).

```bash
npm install
npm run build        # scrim_owdb.opy -> scrim_owdb.txt (paste-ready)
npm run decompile:dkeeh   # regenerate dkeeh.opy from a fresh dkeeh_raw.txt export
```

`scrim_owdb.txt` is the file you paste into Overwatch. The `.opy` source is
the versioned, patchable form — edit that, then rebuild.

## The share code

**`B4GM8`** — minted 2026-08-28. Hosts should load this rather than pasting the
script; it is the only way bans and the spectator scoreboard reach a scrim
somebody else is hosting.

Two things about it that are easy to get wrong:

- **It was uploaded from the alt account `ragecomic`, not `gcb`.** Re-uploading
  from a different account almost certainly mints a NEW code rather than
  updating this one, which would strand every host on the old version. Confirm
  before anyone tries. Whoever holds `ragecomic` is the one who can publish
  workshop changes.
- **Always pick "update an existing code", never "upload a new one."** It keeps
  the code stable for the team, it does not consume the create-code rate limit
  (which is real and has no published cooldown), and it counts as activity
  against expiry.

**Codes expire six months after creation** unless imported or uploaded to often
enough. Regular use by the team is what keeps this one alive; a code that only
gets loaded occasionally will quietly die, probably mid-season.

## Import in Overwatch

**Do not look for an "Import Code" button — that is a different mechanism.**
Overwatch has two, and they are not interchangeable:

- **Import** takes a short *share code* (`DKEEH`, `0PP1T`) and downloads a
  published mode. It cannot take a script.
- **Copy / Paste** moves the whole settings blob, workshop rules included,
  through your operating system's clipboard. That is how a script gets in.

To load `scrim_owdb.txt`:

1. Open `scrim_owdb.txt` in a text editor and copy all of it (Ctrl+A, Ctrl+C).
   **Do this first** — see step 4.
2. Custom Game > Create > **Settings** (top right).
3. Stay on the **Settings** screen. The button row is in the **Summary panel on
   the right**; do NOT go into the Workshop sub-screen, which has no paste
   control at all.
4. Click the orange **Paste** button beside Copy. It only appears when the
   clipboard already holds valid workshop text, so an empty clipboard shows
   nothing and looks like a missing feature.

Pasting replaces **all** lobby settings, not only the rules. Use a fresh lobby.

Pasting also fails outright if the Overwatch client language is not English —
`scrim_owdb.txt` is compiled `en-US`. Going the other way, a mode is exported
with the **Copy** button in the same place, which is how `dkeeh_raw.txt` was
obtained. A share code is minted separately via **Copy Settings** in the Custom
Game menu.

## Controls (default keybinds)

| Action | Input |
|---|---|
| Ready up / unready | Interact + Reload |
| Ban a hero (during setup) | Interact + Melee, while playing that hero |
| Force team ready (hold) | Interact + Reload, hold 3 s |
| Add setup time | Interact + Ultimate (+30 s, cap 90 s) |
| Defender teleport | Interact + Jump |
| Host: toggle scoreboard | Ultimate + Ability 1 (Z+Q) |

Rebindable in the workshop Settings panel under **7. Keybinds**.

## Recommended lobby settings for scrim conventions

The workshop logic handles ready-up and map-completion bookkeeping; the actual
**flow** (how many points / rounds are played) is governed by lobby settings,
which is how teams run scrims today:

- **Control / Flashpoint** — teams play out *every* point even after a 3-0/2-0
  (scrim convention). In the lobby settings set the mode to keep the map going
  (e.g. disable early-end conditions) so the full best-of-5 is played; the
  workshop's "End Control After Three Rounds" setting controls whether the code
  force-ends it (turn **off** to play all points).
- **Hybrid / Escort** — both teams get a **full attack** regardless of distance.
  Leave the standard two-round flow; the map-completion rules ensure round 2 is
  fully attacked. If both teams full-cap and agree to "play it out" (one extra
  attack turn each), run the extra turns as a rematch round — the code's ready-up
  handles each new round.
- **Push** — normal match flow; nothing special.
- **Partial practice** (single sub-map of Control, one attack/defense, etc.) —
  just play that slice; the scoreboard and capture tool read whatever was played.

## In-game validation checklist (must be done by a human)

These cannot be verified outside the game:

1. **Setup phase** — ready-up toggle lights the ○/● list; both-teams-ready starts
   the countdown; hold-to-force-team-ready works; adding setup time increments
   the timer and respects the max.
2. **Defender teleport** — spawn↔objective teleport works on each map type
   (Escort/Hybrid/Control/Flashpoint); Push correctly excludes it.
3. **Map completion** — attacker-fail case sets the attacking score so round 2 is
   fully attacked; Control ends at 3 rounds, Flashpoint at 5.
4. **Scoreboard** — appears top-left for a **spectator**, and is present in the
   **replay** of the scrim; matches stats visually; host toggle hides/shows it.
5. **FPS** — host machine stays at a playable framerate through a full map.
   Compare against Scrimtime (DKEEH) if this is the reason for using this code.

## Licence note

Scrimtime (DKEEH) is **not open source**. This stripped copy is for this team's
own private scrims. Do **not** publish a stripped share code publicly as if it
were original work. If public publication ever becomes a goal, the clean base is
**Scrimmie** (open-source, CC BY-NC-SA, includes LogTime).

## Relationship to OWDB

- `tools/scrim_code/` = the workshop code only.
- The **capture** side (reading the scoreboard off-screen) lives in `owdb/`
  and `docs/capture/` and is developed separately — see `FEATURES.md`.
- `dkeeh_raw.txt` (original export) and `dkeeh.opy` (its decompilation) are kept
  as reference so the strip can be re-derived when DKEEH updates.

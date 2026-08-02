# OW Scout Scrim workshop code

A **lean custom-game code** for Overwatch 2 scrims, built for the OW Scout project
(`docs/`). It is a **stripped derivative of Scrimtime (DKEEH) v1.73** by Caldoran,
re-authored via the OverPy decompiler so teams can keep the Scrimtime experience
they already know at a lower server cost.

## Why strip Scrimtime instead of writing from scratch

- Feature-parity with the industry standard — teams already know the ready-up,
  add-time, defender-teleport and scoreboard UX.
- The **spectator scoreboard layout is preserved**, which is exactly what the
  OW Scout capture tool will OCR in the scrim-tracker feature (Phase 2+).
- Bloat removed (see below) roughly **halves the compiled size** and removes the
  per-event processing that tanks host FPS.

### What was stripped

| Removed | Why |
|---|---|
| Log Generator (~20 event-driven rules: kills, damage, healing, abilities, ults, hero-swap tracking…) | The biggest FPS cost; OW Scout reads the screen, not a log. |
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
- **Match time display** + host-spectator scoreboard toggle (Z+Q).
- The in-game **Settings panel** (ready up / setup phase / map completion /
  scoreboard / keybinds) with Scrimtime's original tunables.

## Build

Requires Node + npm (OverPy is an npm package).

```bash
npm install
npm run build        # scrim_owscout.opy -> scrim_owscout.txt (paste-ready)
npm run decompile:dkeeh   # regenerate dkeeh.opy from a fresh dkeeh_raw.txt export
```

`scrim_owscout.txt` is the file you paste into Overwatch. The `.opy` source is
the versioned, patchable form — edit that, then rebuild.

## Import in Overwatch

1. Custom Game > Create.
2. Settings > Workshop > Import Code; paste the entire `scrim_owscout.txt`.
3. Save. Share code is minted in-game via **Copy Settings** (Custom Game menu).

## Controls (default keybinds)

| Action | Input |
|---|---|
| Ready up / unready | Interact + Reload |
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

## Relationship to OW Scout

- `tools/scrim_code/` = the workshop code only.
- The **capture** side (reading the scoreboard off-screen) lives in `owscout/`
  and `docs/capture/` and is developed separately — see `FEATURES.md`.
- `dkeeh_raw.txt` (original export) and `dkeeh.opy` (its decompilation) are kept
  as reference so the strip can be re-derived when DKEEH updates.

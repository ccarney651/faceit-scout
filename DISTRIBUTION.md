# Giving owscout to a teammate

The whole tool is one file: `owscout.exe` (~77 MB). It carries the curator's
learned hero library and the seed match list inside it — no Python, no separate
downloads.

## Their setup (once, ~5 minutes + one background sync)

1. Put `owscout.exe` in its own folder (e.g. `C:\owscout\`). It keeps all its
   data — database, calibration, captures — next to itself.
2. Run it. Windows SmartScreen will warn because the exe is unsigned:
   **More info → Run anyway.**
3. Open Overwatch (windowed/borderless) with any replay on screen, then click
   **Calibrate** and drag the two boxes as prompted. When it finishes, the log
   says `pre-trained hero library loaded (104 refs)` — they are now trained.
4. Click **Sync codes from FACEIT**. The first run builds the match database
   from scratch and takes a while; it only happens once.
5. Capture normally: pick a code, pick the left team, **Start hotkey capture**,
   F8 at key moments in the replay, ESC when done. Review → finalize.

If heroes consistently fail to match on one side, the log will say so and name
the likely cause (custom/colorblind UI team colours) — that machine needs to
relearn its own portraits via **Learn heroes**.

## Getting their scouting onto the site

6. **Publish my captures** (with their name in the "as" box) writes
   `data\captures\<name>.json` next to the exe, and the log says where.
7. They send that file to the curator (Discord/email — it's small).
8. The curator drops it into the repo's `data/captures/`, commits, pushes.
   The next site build merges it: first submission of a map wins, duplicates
   are kept but ignored, and every map is validated against FACEIT's records —
   fabricated games, wrong teams, or wrong codes are rejected loudly.

## Rebuilding the exe (curator only)

```
.venv\Scripts\python -m owscout.cli refs export --out owscout_refs.zip
.venv\Scripts\pyinstaller --noconfirm owscout.spec
```

Export the refs first — the spec bakes `owscout_refs.zip`, `matches.txt` and the
dashboard's hero icons into the binary, and warns if the bundle is missing.

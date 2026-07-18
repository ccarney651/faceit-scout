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

6. One-time: the curator sends them an **upload token**, and they paste it under
   **Sync settings…** (next to Publish). Repo stays the default.
7. From then on, **Publish my captures** uploads their file straight into the
   site's repo, and **the site rebuilds itself within a couple of minutes** —
   no git, no file relay, nothing else to do.
8. Every upload is still validated at build time: first submission of a map
   wins, duplicates are kept but ignored, and maps are checked against FACEIT's
   records — fabricated games, wrong teams, or wrong codes are rejected loudly.
   Every upload is a git commit, so anything bad is a one-click revert.

Without a token, Publish still writes `data\captures\<name>.json` next to the
exe and the log says to send it to the curator - the manual fallback keeps
working.

### Curator: issuing an upload token

GitHub -> Settings -> Developer settings -> **Fine-grained personal access
tokens** -> Generate new token:
- **Repository access:** Only select repositories -> the site repo
- **Permissions:** Contents -> **Read and write** (nothing else)
- Set an expiry you're comfortable with; revoke any time from the same page.

One shared token for a trusted team is fine to start (blast radius: this one
repo's files, all recoverable from git history). Per-teammate tokens need each
of them to be a repo collaborator - do that when the group grows past people
you'd hand your keyboard to.

## Rebuilding the exe (curator only)

```
.venv\Scripts\python -m owscout.cli refs export --out owscout_refs.zip
.venv\Scripts\pyinstaller --noconfirm owscout.spec
```

Export the refs first — the spec bakes `owscout_refs.zip`, `matches.txt` and the
dashboard's hero icons into the binary, and warns if the bundle is missing.

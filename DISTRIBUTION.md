# Giving OW Scout to anyone

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

6. **Publish my captures** (with a display name in the "as" box) uploads their
   file to the open endpoint - **the site rebuilds itself within a couple of
   minutes.** Nothing to configure, nothing to be issued: the first upload
   under a name claims it for that install, so nobody can overwrite anyone
   else's file, yet no keys or accounts exist anywhere.
7. Every upload is still validated at build time: first submission of a map
   wins, duplicates are kept but ignored, and maps are checked against FACEIT's
   records - fabricated games, wrong teams, or wrong codes are rejected loudly.
   Every upload is a git commit, so anything bad is a one-click revert, and the
   curator can block a name via the worker's DENYLIST.

If the endpoint is unreachable, Publish still writes
`data\captures\<name>.json` locally and says so - nothing is ever lost.

## Troubleshooting

**"Self-protection failed. Error code: 4" (or similar security errors) when
calibrating or capturing.** Not an OW Scout error - security software reacting
to an unsigned app doing screen capture. In order of likelihood:

1. Move `owscout.exe` OUT of Downloads into its own folder (e.g. `C:\OWScout\`),
   then right-click -> Properties -> tick **Unblock** if shown -> Apply.
2. Add that folder to your antivirus exclusions (Kaspersky/ESET/Avast/360 all
   have "self-protection" modules that produce exactly this message).
3. If FACEIT Anti-Cheat is installed, exit it fully before scouting - kernel
   anticheat and screen capture clash, and replays do not need AC.
4. Run the exe as administrator once.
5. Make sure Overwatch is windowed/borderless, not exclusive fullscreen.

**Nothing matches / all slots read `??`** - see the log: if it names custom UI
colours, that machine needs to relearn portraits (Learn heroes).

## Deploying the upload endpoint (curator, once)

The endpoint is a Cloudflare Worker (free tier) in `infra/upload-worker/`:

```
npm i -g wrangler
cd infra/upload-worker
wrangler login                       # opens the browser, one time
wrangler kv namespace create NAMES   # paste the printed id into wrangler.toml
wrangler secret put GITHUB_TOKEN     # fine-grained PAT: Contents RW, site repo only
wrangler deploy                      # prints the endpoint URL
```

Then set `DEFAULT_UPLOAD_ENDPOINT` in `owscout/contribute.py` to that URL and
rebuild the exe - end users inherit it and configure nothing. The GitHub token
never leaves Cloudflare's secret store; contributors hold no credential at all.

## Rebuilding the exe (curator only)

```
.venv\Scripts\python -m owscout.cli refs export --out owscout_refs.zip
.venv\Scripts\pyinstaller --noconfirm owscout.spec
```

Export the refs first — the spec bakes `owscout_refs.zip`, `matches.txt` and the
dashboard's hero icons into the binary, and warns if the bundle is missing.

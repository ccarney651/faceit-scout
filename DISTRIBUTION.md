# Giving OW Scout to anyone

The whole tool is one file: `owscout.exe` (~90 MB). It carries the curator's
learned hero library and the seed match list inside it — no Python, no separate
downloads.

## Their setup (once, ~2 minutes + one background sync)

1. Put `owscout.exe` in its own folder (e.g. `C:\owscout\`). It keeps all its
   data — database, calibration, captures — next to itself.
2. Run it. The first time, Windows shows a blue **"Windows protected your PC"**
   box — this is **expected and normal for any app that isn't code-signed yet**,
   not a virus warning. Click **More info → Run anyway**. (The dialog names the
   app "OW Scout" and it only appears once per machine.) See *Why Windows warns*
   below if you want to verify the download first.
3. Open Overwatch (windowed/borderless) with any replay on screen, then click
   **Calibrate to my screen**. It **auto-draws** the boxes from the HUD layout —
   if the green boxes sit on the portraits, press **ENTER** to save (no dragging).
   Only if they don't line up (ultrawide, or a changed HUD scale) press **ESC**
   and drag the two boxes by hand. When it finishes, the log says
   `pre-trained hero library loaded (104 refs)` — they are now trained.
4. Click **Sync codes from FACEIT**. The first run **downloads the current match
   database from the site** (~1.3 MB, a few seconds) — it does not re-crawl
   FACEIT. If the site is unreachable it falls back to building from FACEIT
   directly, which is slow (a progress bar shows how far along). Later syncs top
   up with the newest matches in seconds.
5. Capture normally: pick a code, pick the left team, **Start hotkey capture**,
   then either press the keys (F8 snapshot, etc.) or **click the buttons in the
   overlay** — whichever suits. On control maps the overlay shows sub-map picks;
   on escort/hybrid it shows a "flip who's attacking" button. ESC (or Done) when
   finished, then Review → finalize.

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

## Un-scouting a code (undo an accidental publish)

If someone publishes a map they didn't mean to, that code disappears from
everyone's app (it's now "scouted"). The curator frees it up again:

```
owscout --faceit-db faceit.sqlite3 contribute unscout SXD9K6      # or match_id:game_no
owscout --faceit-db faceit.sqlite3 contribute unscout SXD9K6 --undo   # re-allow it
```

That writes an `exclude` entry into `data/captures/overrides.json`; the next
build drops the map from the report AND the already-scouted feed, so the code
comes back in the apps. It's a committed file, so it's an auditable curator act -
you can also just edit `overrides.json` directly on GitHub (that's curator-only
by repo access, which is why there's no public "un-scout" button: anyone could
wipe scouting work). The publisher's OWN app still hides it via their local
capture until they **Discard** that draft in Review.

## Why Windows warns (and how to be sure it's safe)

The warning is **not** malware detection. Windows SmartScreen flags *any*
executable that hasn't been bought a code-signing certificate — a brand-new
indie tool always trips it. The build already does what it can without a
certificate: it is **not packed** (packers are what most antivirus actually
reacts to) and it carries proper Windows file properties (right-click →
Properties → Details shows "OW Scout"), so it presents as a real named app, not
an anonymous binary.

To be certain the download wasn't tampered with, verify its checksum against the
`owscout.exe.sha256` published next to it on the release:

```powershell
Get-FileHash owscout.exe -Algorithm SHA256
```

The printed hash should equal the one in `owscout.exe.sha256`.

The permanent fix (removes the warning entirely) is code signing — see
*Signing the exe* below.

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

Publish `owscout.exe.sha256` alongside the exe so downloaders can verify it:

```powershell
(Get-FileHash dist\owscout.exe -Algorithm SHA256).Hash > dist\owscout.exe.sha256
```

## Signing the exe (removes the SmartScreen warning)

Code signing is the only thing that makes the warning disappear entirely. The
affordable, correct option today is **Azure Trusted Signing** (~$10/month):
Microsoft's own signing service, trusted by SmartScreen **immediately** — no
"reputation" wait, and it signs every rebuild.

1. Create an Azure account, a Trusted Signing account + certificate profile, and
   complete identity verification (individual verification is available).
2. Install the `Az.CodeSigning` tooling / `signtool`.
3. Sign after each build:
   ```powershell
   signtool sign /v /fd SHA256 /tr http://timestamp.acs.microsoft.com /td SHA256 `
     /dlib <trusted-signing.dll> /dmdf <metadata.json> dist\owscout.exe
   ```

Traditional OV certificates (~$100–250/yr) also work but still need to *earn*
SmartScreen reputation download-by-download; an EV certificate (~$300+/yr, on a
hardware token) grants instant trust like Trusted Signing does. For this
project's cadence (frequent rebuilds, small audience), Trusted Signing is the
best value. Until then, the unsigned build ships with the mitigations above
(no packer, real file metadata, published checksum).

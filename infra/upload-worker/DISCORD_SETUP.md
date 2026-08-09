# Turning on Discord logins + the admin roster

The code is already deployed and **inert** — it does nothing until the five
values below exist on the Worker. Nothing here changes the `.exe` upload path or
existing contributors; it only adds accounts on top.

When it's on:
- scouts published from the browser tool are attributed to the **Discord account**
  (not a typed name), keyed by Discord user-id so nobody can publish under someone
  else's name;
- you (and anyone in `ADMIN_IDS`) get an **"Admin — who's contributing"** card in
  the capture tool listing every contributor, their Discord id, and when they last
  uploaded.

---

## 1. Create the Discord application (~2 min)
1. Go to <https://discord.com/developers/applications> → **New Application**, name it
   e.g. "OW Scout".
2. Left sidebar → **OAuth2**.
3. Under **Redirects**, click **Add Redirect** and paste **exactly**:
   ```
   https://upload.owdb.io/auth/callback
   ```
   Save. (It must match character-for-character or Discord refuses the login.)
4. Copy the **Client ID** (under OAuth2 / General).
5. Click **Reset Secret** → copy the **Client Secret** (shown once).

No bot, no extra scopes — the login only asks for `identify` (username + id).

## 2. Find your own Discord user-id (for admin access)
1. Discord → **User Settings → Advanced → Developer Mode: ON**.
2. Right-click your name anywhere → **Copy User ID**. It's a long number like
   `216773414761...`. That goes in `ADMIN_IDS`.

## 3. Set the five values on the Worker
From `infra/upload-worker/` (secrets keep them out of the public repo):
```bash
npx wrangler secret put DISCORD_CLIENT_ID        # paste the Client ID at the prompt
npx wrangler secret put DISCORD_CLIENT_SECRET    # paste the Client Secret at the prompt
npx wrangler secret put SESSION_SECRET           # any long random string (see below)
npx wrangler secret put DISCORD_REDIRECT_URI     # paste https://upload.owdb.io/auth/callback at the prompt
npx wrangler secret put ADMIN_IDS                # your user-id at the prompt (comma-separated for more admins)
```
Generate a `SESSION_SECRET` (this signs the login tokens — keep it private, and if
you ever change it everyone is logged out):
```bash
node -e "console.log(require('crypto').randomBytes(32).toString('hex'))"
```

> `DISCORD_REDIRECT_URI` and `ADMIN_IDS` aren't sensitive, so you *may* instead
> uncomment them under `[vars]` in `wrangler.toml`. Secrets are simplest.

## 4. Redeploy
```bash
npx wrangler deploy
```
That's it. `/auth/login` now starts a real Discord flow instead of bouncing back
with `login_error=notconfigured`.

## 5. Test end-to-end
1. Open the capture tool (`.../capture/`), scroll to **Publish** → **Log in with
   Discord** → authorize. You should return to the page showing **"logged in as
   <you>"**, and the *Publish as* box locks to your handle.
2. Because your id is in `ADMIN_IDS`, an **Admin — who's contributing** card
   appears. Click **Refresh** — it lists contributors (empty until someone
   publishes while logged in).
3. Capture a map and **Publish** — the file lands as `data/captures/u_<your-id>.json`
   with `"contributor": "<your handle>"` and `"discord_id": "<your id>"`.

---

## How it works (for future me)
- **Session** = `base64url(JSON) . base64url(HMAC-SHA256(JSON, SESSION_SECRET))`,
  30-day expiry. The browser can read the payload (name/id/admin) for display, but
  only the Worker can mint/verify one, so a valid signature == a real Discord login.
  Returned to the app in the URL fragment after `/auth/callback`; stored in
  `localStorage.owscout_session`; sent as `X-Owscout-Session` on publish.
- **Authoritative identity**: on publish, a valid session overrides any typed name
  — `contributor` = sanitized Discord handle, file/claim keyed on `u_<discord_id>`.
  The `discord:<id>` token prefix is reserved so a keyless upload can't forge it.
- **Admin roster**: `GET /admin/contributors` walks the KV claim records and
  returns `{name, discord_id, login, last_upload, last_maps}` per contributor,
  gated server-side to `ADMIN_IDS` (the session's `admin` flag is only a UI hint).
- **Off switch**: delete any of the four `DISCORD_*`/`SESSION_SECRET` values and
  redeploy — logins go inert again and publishing falls back to the name-claim.

## Later: paid access (not built)
This login is step 1 of the "contribute-or-pay" plan (see the project backlog).
The entitlement check would live in this same Worker: `paid OR maps_this_season >= N`,
with the data moved behind the Worker so the static site can be gated. Deferred to
next season by request.

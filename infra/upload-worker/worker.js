/**
 * owdb upload endpoint (Cloudflare Worker) - OPEN ACCESS.
 *
 * Anyone may contribute; nobody is issued anything. The tool generates a random
 * identity token on first publish and sends it with the chosen display name.
 * The first install to upload under a name CLAIMS it (name -> token hash in
 * KV); later uploads must present the same token, so a stranger cannot
 * overwrite someone else's file - but no curator ever hands out keys. The
 * GitHub token exists only as a server secret; contributors never hold any
 * credential worth stealing.
 *
 * What keeps an open endpoint sane:
 *  - a name writes exactly one file: data/captures/<name>.json
 *  - shape checks + 5 MB cap here; REAL validation (games must exist on
 *    FACEIT, teams must match) runs at site build, where junk is dropped
 *    loudly and every upload is a git commit - i.e. revertable
 *  - 30s per-name rate limit; DENYLIST env var for problem names
 *
 * Deploy (once):
 *   npm i -g wrangler
 *   cd infra/upload-worker
 *   wrangler kv namespace create NAMES      # paste the id into wrangler.toml
 *   wrangler secret put GITHUB_TOKEN        # fine-grained PAT, Contents RW, site repo only
 *   wrangler deploy
 */

const NAME_RE = /^[a-z0-9_-]{2,24}$/;
const MAX_BYTES = 5 * 1024 * 1024;
const MIN_INTERVAL_MS = 30_000;
const REFRESH_COOLDOWN_MS = 10 * 60_000;   // a site rebuild takes ~2 minutes
const FORMAT = 1;

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    // CORS preflight. Must be a 204 with NO body (a 204 carrying a body is
    // illegal and the runtime 500s it, which breaks the browser capture app's
    // preflight even though keyless clients like the exe never preflight).
    if (request.method === "OPTIONS") {
      return new Response(null, {
        status: 204,
        headers: {
          "access-control-allow-origin": "*",
          "access-control-allow-methods": "GET, POST, OPTIONS",
          "access-control-allow-headers": "content-type,x-owdb-name,x-owdb-token,x-owdb-session",
          "access-control-max-age": "86400",
        },
      });
    }

    // /refresh - anyone may ask the site to pull new FACEIT matches NOW rather
    // than waiting for the 9pm build. It fires a repository_dispatch (which the
    // existing Contents-write token can do - no extra permission) and the
    // workflow does the real work. Globally cooled down: a build takes ~2min,
    // so more often than that is pure noise, and the cooldown is the whole
    // abuse story for an open trigger.
    if (url.pathname === "/refresh") {
      if (request.method !== "POST") return json(405, { error: "POST to refresh" });
      const last = Number((await env.NAMES.get("_refresh_at")) || 0);
      const waitMs = REFRESH_COOLDOWN_MS - (Date.now() - last);
      if (waitMs > 0) {
        return json(429, {
          error: `a refresh is already running or just ran - try again in ${Math.ceil(waitMs / 1000)}s`,
          retry_after: Math.ceil(waitMs / 1000),
        });
      }
      // Claim the cooldown BEFORE the slow GitHub call. Writing it only after
      // the dispatch (as originally) was a TOCTOU: N concurrent refreshes all
      // read the same stale timestamp and all fired. KV has no compare-and-set,
      // so the lock is write-then-verify with a unique claim value: the loser's
      // write is overwritten and its read-back sees someone else's claim. The
      // TTL self-heals a claim if the worker dies mid-dispatch.
      const claim = String(Date.now());
      await env.NAMES.put("_refresh_at", claim, {
        expirationTtl: Math.ceil(REFRESH_COOLDOWN_MS / 1000),
      });
      if ((await env.NAMES.get("_refresh_at")) !== claim) {
        return json(429, {
          error: `a refresh is already running or just ran - try again in ${Math.ceil(waitMs / 1000)}s`,
          retry_after: Math.ceil(waitMs / 1000),
        });
      }
      const res = await fetch(`https://api.github.com/repos/${env.REPO}/dispatches`, {
        method: "POST",
        headers: {
          Authorization: `Bearer ${env.GITHUB_TOKEN}`,
          Accept: "application/vnd.github+json",
          "User-Agent": "owdb-upload-worker",
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ event_type: "refresh" }),
      });
      if (res.status !== 204) {
        // A failed dispatch shouldn't burn the whole cooldown window - release
        // the claim so the site can be retried promptly.
        await env.NAMES.delete("_refresh_at");
        return json(502, { error: `could not start the refresh (HTTP ${res.status})` });
      }
      return json(200, { started: true });
    }

    // Live scouting claims - an advisory soft-lock so two scouts don't capture the
    // same map at once (first-wins at merge means duplicates only waste effort, but
    // steering people apart is better). Backed by a single Durable Object (the
    // "claim room"): a WebSocket per scout gives instant, strongly-consistent
    // claim/release across everyone, and a dropped connection frees that scout's
    // maps at once. GET /claims + POST /claim|/unclaim stay as HTTP fallbacks that
    // hit the same DO. The Worker resolves identity, then forwards to the DO.
    if (url.pathname === "/claims" || url.pathname === "/claim" || url.pathname === "/unclaim" || url.pathname === "/claims/ws") {
      const { owner, by } = await claimIdentity(request, env);
      const stub = env.CLAIM_ROOM.get(env.CLAIM_ROOM.idFromName("global"));
      const fwd = new Request(request.url, request);   // preserves method/body and the Upgrade header for WS
      fwd.headers.set("x-owner", owner);
      fwd.headers.set("x-by", by);
      return stub.fetch(fwd);
    }

    // Discord OAuth (scaffold). Inert until DISCORD_* + SESSION_SECRET are set:
    // /auth/login then bounces back with ?#login_error=notconfigured instead of
    // starting a flow. These are browser navigations (not fetch), so no CORS.
    if (url.pathname === "/auth/login") return authLogin(url, env);
    if (url.pathname === "/auth/callback") return authCallback(url, env);

    // Admin roster: who is sending scout reports. Gated to ADMIN_IDS (Discord ids).
    if (url.pathname === "/admin/contributors") return adminContributors(request, env);
    // Admin live view: who currently holds a scouting claim. Gated to ADMIN_IDS.
    if (url.pathname === "/admin/claims") return adminClaims(request, env);
    // Admin detail: what one contributor actually submitted. Gated to ADMIN_IDS.
    if (url.pathname === "/admin/contributor") return adminContributorDetail(request, env);

    if (request.method !== "POST") {
      return json(405, { error: "POST a contribution with X-Owdb-Name and X-Owdb-Token" });
    }
    const name = (request.headers.get("x-owdb-name") || "").trim().toLowerCase();
    let token = request.headers.get("x-owdb-token") || "";
    // Optional Discord login: a valid signed session is an unforgeable identity,
    // so it supplies a stable per-account token ("discord:<id>") that flows through
    // the existing name-claim unchanged. That prefix is reserved for verified
    // sessions, so a keyless upload can't hand-craft one to impersonate a login.
    const sess = await verifySession(request.headers.get("x-owdb-session"), env);
    if (sess) token = "discord:" + sess.d;
    else if (token.startsWith("discord:")) return json(400, { error: "that token prefix is reserved for Discord login" });
    // Resolve identity. A Discord session is AUTHORITATIVE: the display name and
    // ownership come from the verified account and are keyed by discord_id, so a
    // logged-in scout's reports are always attributed to their account and can't
    // be published under a spoofed name. Otherwise the classic first-come
    // name-claim applies (name -> token hash).
    let displayName, claimKey;
    if (sess) {
      displayName = sanitizeName(sess.n) || ("scout-" + String(sess.d).slice(-6));
      claimKey = "u_" + sess.d;                    // stable per-account file + KV key
    } else {
      if (!NAME_RE.test(name)) return json(400, { error: "name must be 2-24 chars of a-z 0-9 _ -" });
      // "u_<id>" is the file/KV namespace for verified Discord accounts. A keyless
      // upload must not be able to pick that name, or it could claim - and, because
      // Discord-written records carry no token hash, overwrite - a logged-in
      // scout's file. Reserve the prefix for real sessions.
      if (name.startsWith("u_")) return json(400, { error: "names starting with 'u_' are reserved for Discord logins" });
      if (token.length < 16 || token.length > 128) return json(400, { error: "malformed identity token" });
      displayName = name;
      claimKey = name;
    }
    const denies = (env.DENYLIST || "").split(",").map((x) => x.trim()).filter(Boolean);
    if (denies.includes(displayName) || (sess && denies.includes(String(sess.d)))) {
      return json(403, { error: "this account is blocked - contact the curator" });
    }

    const body = await request.text();
    if (body.length > MAX_BYTES) return json(413, { error: "contribution too large" });
    let data;
    try { data = JSON.parse(body); } catch { return json(400, { error: "body is not JSON" }); }
    if (data.format !== FORMAT) return json(400, { error: `unsupported format ${data.format}` });
    if (!Array.isArray(data.maps)) return json(400, { error: "no maps array" });
    for (const m of data.maps) {
      if (!m || typeof m.match_id !== "string" || !Number.isInteger(m.game_no)) {
        return json(400, { error: "a map is missing its FACEIT identity" });
      }
    }

    // Ownership + rate limit on the claim key. Legacy uploads must match the token
    // that first claimed the name; Discord uploads are already proven by the
    // signed session, so the record just tracks them for the admin roster.
    const rec = await env.NAMES.get(claimKey, { type: "json" });
    if (!sess) {
      const tokenHash = await sha256hex(token);
      if (rec && rec.h && rec.h !== tokenHash) {
        return json(403, { error: `the name '${displayName}' is already used from another ` +
                                   "install - pick a different name in the Publish box" });
      }
    }
    if (rec && Date.now() - (rec.t || 0) < MIN_INTERVAL_MS) {
      return json(429, { error: "uploading too fast - wait half a minute" });
    }

    data.contributor = displayName;        // server-side identity, always
    if (sess) data.discord_id = sess.d;    // account attribution when logged in
    else delete data.discord_id;           // never let a keyless upload assert one
    const path = `data/captures/${claimKey}.json`;
    const content = btoa(unescape(encodeURIComponent(JSON.stringify(data, null, 2))));

    const gh = (url, init = {}) => fetch(`https://api.github.com/repos/${env.REPO}/${url}`, {
      ...init,
      headers: {
        Authorization: `Bearer ${env.GITHUB_TOKEN}`,
        Accept: "application/vnd.github+json",
        "User-Agent": "owdb-upload-worker",
        ...(init.headers || {}),
      },
    });

    let sha;
    const head = await gh(`contents/${path}`);
    if (head.status === 200) sha = (await head.json()).sha;
    else if (head.status !== 404) return json(502, { error: `github: HTTP ${head.status}` });

    const put = await gh(`contents/${path}`, {
      method: "PUT",
      body: JSON.stringify({
        message: `contribution: ${displayName} (${data.maps.length} maps)`,
        content,
        ...(sha ? { sha } : {}),
      }),
    });
    if (put.status !== 200 && put.status !== 201) {
      return json(502, { error: `github: HTTP ${put.status}` });
    }
    // Roster record for the admin panel: who, their discord id, when, last size.
    const newRec = sess
      ? { d: sess.d, n: displayName, t: Date.now(), maps: data.maps.length }
      : { h: await sha256hex(token), n: displayName, t: Date.now(), maps: data.maps.length };
    await env.NAMES.put(claimKey, JSON.stringify(newRec));
    return json(200, { action: sha ? "updated" : "created", maps: data.maps.length, as: displayName });
  },
};

async function sha256hex(s) {
  const d = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(s));
  return [...new Uint8Array(d)].map((b) => b.toString(16).padStart(2, "0")).join("");
}

// --- Discord OAuth + signed sessions (scaffold; inert until env is set) --------
// A session token is base64url(JSON payload) + "." + base64url(HMAC-SHA256(body)).
// The app can read the payload for display, but only the Worker (which holds
// SESSION_SECRET) can mint or trust one, so a valid signature == a verified
// Discord identity. Setup, when you're ready to turn it on:
//   - create a Discord app; add redirect  <worker>/auth/callback
//   - wrangler secret put DISCORD_CLIENT_ID / DISCORD_CLIENT_SECRET
//   - wrangler secret put SESSION_SECRET            (any long random string)
//   - set DISCORD_REDIRECT_URI in wrangler.toml [vars] to that callback URL
function b64url(bytes) {
  return btoa(String.fromCharCode(...new Uint8Array(bytes)))
    .replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}
function b64urlToBytes(s) {
  const bin = atob(s.replace(/-/g, "+").replace(/_/g, "/"));
  return Uint8Array.from(bin, (c) => c.charCodeAt(0));
}
async function hmacB64(secret, msg) {
  const key = await crypto.subtle.importKey("raw", new TextEncoder().encode(secret),
    { name: "HMAC", hash: "SHA-256" }, false, ["sign"]);
  return b64url(await crypto.subtle.sign("HMAC", key, new TextEncoder().encode(msg)));
}
async function signSession(payload, env) {
  const body = b64url(new TextEncoder().encode(JSON.stringify(payload)));
  return body + "." + (await hmacB64(env.SESSION_SECRET, body));
}
async function verifySession(tok, env) {
  try {
    if (!tok || !env.SESSION_SECRET) return null;
    const [body, sig] = tok.split(".");
    if (!body || !sig) return null;
    if ((await hmacB64(env.SESSION_SECRET, body)) !== sig) return null;
    const p = JSON.parse(new TextDecoder().decode(b64urlToBytes(body)));
    return p.exp && Date.now() < p.exp ? p : null;
  } catch { return null; }
}
function oauthReady(env) {
  return !!(env.DISCORD_CLIENT_ID && env.DISCORD_CLIENT_SECRET &&
            env.DISCORD_REDIRECT_URI && env.SESSION_SECRET);
}
async function authLogin(url, env) {
  const back = safeBack(url.searchParams.get("redirect"));
  if (!oauthReady(env)) {   // inert: bounce back with a flag the app explains
    return Response.redirect(back + (back.includes("#") ? "&" : "#") + "login_error=notconfigured", 302);
  }
  const state = await signSession({ r: back, exp: Date.now() + 600000 }, env);   // 10 min
  const p = new URLSearchParams({
    client_id: env.DISCORD_CLIENT_ID, redirect_uri: env.DISCORD_REDIRECT_URI,
    response_type: "code", scope: "identify", state,
  });
  return Response.redirect("https://discord.com/oauth2/authorize?" + p.toString(), 302);
}
async function authCallback(url, env) {
  const code = url.searchParams.get("code");
  const st = await verifySession(url.searchParams.get("state"), env);
  if (!oauthReady(env) || !code || !st) return new Response("login failed", { status: 400 });
  const tokRes = await fetch("https://discord.com/api/oauth2/token", {
    method: "POST", headers: { "content-type": "application/x-www-form-urlencoded" },
    body: new URLSearchParams({
      client_id: env.DISCORD_CLIENT_ID, client_secret: env.DISCORD_CLIENT_SECRET,
      grant_type: "authorization_code", code, redirect_uri: env.DISCORD_REDIRECT_URI,
    }),
  });
  if (!tokRes.ok) return new Response("discord token exchange failed", { status: 502 });
  const at = (await tokRes.json()).access_token;
  const uRes = await fetch("https://discord.com/api/users/@me", { headers: { Authorization: "Bearer " + at } });
  if (!uRes.ok) return new Response("discord user fetch failed", { status: 502 });
  const u = await uRes.json();
  const admins = (env.ADMIN_IDS || "").split(",").map((x) => x.trim()).filter(Boolean);
  const session = await signSession(
    { d: u.id, n: u.global_name || u.username || "scout",
      admin: admins.includes(String(u.id)), exp: Date.now() + 30 * 86400000 }, env);   // 30 days
  const back = safeBack(st.r);
  return Response.redirect(back + (back.includes("#") ? "&" : "#") + "session=" + encodeURIComponent(session), 302);
}

function sanitizeName(s) {
  const x = String(s || "").toLowerCase().replace(/[^a-z0-9_-]/g, "").slice(0, 24);
  return x.length >= 2 ? x : "";
}

// Only the real app origin may be used as a post-login redirect target - other
// absolute URLs (http://evil.example) are bounced to the app root. The app
// (docs/capture/) lives on owdb.io, a different origin from this Worker
// (upload.owdb.io), so the caller always sends its full page URL and we must
// return a full absolute URL too: Response.redirect() cannot resolve a bare
// relative path in the Workers runtime (no implicit document base URL).
const APP_ORIGIN = "https://owdb.io";
function safeBack(s) {
  try {
    const u = new URL(s);
    return u.origin === APP_ORIGIN ? u.origin + u.pathname + u.search : APP_ORIGIN + "/";
  } catch {
    return APP_ORIGIN + "/";
  }
}

// Resolve who is claiming. owner = who may release/refresh a claim (account when
// logged in, else a hash of the anon identity token); by = best-effort display
// name. Used for HTTP paths (headers) and, via an explicit WS `identify` message,
// for the socket — never from the query string, so identity tokens don't end up
// in proxy/access logs.
async function resolveIdentity({ session, name, token }, env) {
  const sess = await verifySession(session, env);
  const nm = String(name || "").trim().toLowerCase();
  const tok = String(token || "");
  const owner = sess ? "u_" + sess.d : (tok ? "t_" + (await sha256hex(tok)).slice(0, 16) : "anon");
  const by = sess ? (sanitizeName(sess.n) || "scout-" + String(sess.d).slice(-6))
                  : (NAME_RE.test(nm) ? nm : "a scout");
  return { owner, by };
}
async function claimIdentity(request, env) {
  const url = new URL(request.url);
  const pick = (h, q) => request.headers.get(h) || url.searchParams.get(q) || "";
  return resolveIdentity({
    session: pick("x-owdb-session", "session"),
    name: pick("x-owdb-name", "name"),
    token: pick("x-owdb-token", "token"),
  }, env);
}

// The admin roster is the whole point of "who is sending reports": it walks the
// KV claim records (one per contributor) and returns name + discord id + when
// they last uploaded + last batch size. Gated server-side to ADMIN_IDS - the
// session's own admin flag is only a UI hint, never the authority.
async function adminContributors(request, env) {
  const sess = await verifySession(request.headers.get("x-owdb-session"), env);
  const admins = (env.ADMIN_IDS || "").split(",").map((x) => x.trim()).filter(Boolean);
  if (!sess || !admins.includes(String(sess.d))) return json(403, { error: "admins only" });
  const out = [];
  let cursor;
  do {
    const page = await env.NAMES.list({ cursor });
    for (const k of page.keys) {
      if (k.name === "_refresh_at" || k.name.startsWith("claim:")) continue;
      const r = await env.NAMES.get(k.name, { type: "json" });
      if (!r) continue;
      out.push({
        key: k.name,
        name: r.n || k.name,
        discord_id: r.d || null,
        login: !!r.d,
        last_upload: r.t || null,
        last_maps: r.maps ?? null,
      });
    }
    cursor = page.list_complete ? null : page.cursor;
  } while (cursor);
  out.sort((a, b) => (b.last_upload || 0) - (a.last_upload || 0));
  return json(200, { contributors: out, count: out.length });
}

// Admin live view: which maps are currently being scouted. Forwards to the
// ClaimRoom Durable Object, which is the single source of truth for live locks.
// Gated to ADMIN_IDS - the session's own admin flag is only a UI hint.
async function adminClaims(request, env) {
  const sess = await verifySession(request.headers.get("x-owdb-session"), env);
  const admins = (env.ADMIN_IDS || "").split(",").map((x) => x.trim()).filter(Boolean);
  if (!sess || !admins.includes(String(sess.d))) return json(403, { error: "admins only" });
  const stub = env.CLAIM_ROOM.get(env.CLAIM_ROOM.idFromName("global"));
  const name = sanitizeName(sess.n) || ("scout-" + String(sess.d).slice(-6));
  const fwd = new Request(request.url, request);
  fwd.headers.set("x-owner", "u_" + sess.d);
  fwd.headers.set("x-by", name);
  return stub.fetch(fwd);
}

// Admin detail: the actual maps a contributor has submitted. Reads the
// committed file from GitHub so the admin sees the same data the build does.
// Gated to ADMIN_IDS.
async function adminContributorDetail(request, env) {
  const sess = await verifySession(request.headers.get("x-owdb-session"), env);
  const admins = (env.ADMIN_IDS || "").split(",").map((x) => x.trim()).filter(Boolean);
  if (!sess || !admins.includes(String(sess.d))) return json(403, { error: "admins only" });
  const url = new URL(request.url);
  const key = (url.searchParams.get("key") || "").trim();
  if (!key) return json(400, { error: "missing key" });
  if (key.includes("..") || key.includes("/") || key.includes("\\")) return json(400, { error: "invalid key" });
  const gh = await fetch(`https://api.github.com/repos/${env.REPO}/contents/data/captures/${encodeURIComponent(key)}.json`, {
    headers: {
      Authorization: `Bearer ${env.GITHUB_TOKEN}`,
      Accept: "application/vnd.github+json",
      "User-Agent": "owdb-upload-worker",
    },
  });
  if (gh.status === 404) return json(404, { error: "contributor file not found" });
  if (!gh.ok) return json(502, { error: `github: HTTP ${gh.status}` });
  let body, raw;
  try {
    body = await gh.json();
    raw = new TextDecoder().decode(Uint8Array.from(atob(body.content), (c) => c.charCodeAt(0)));
  } catch {
    return json(502, { error: "could not decode contributor file" });
  }
  let content;
  try { content = JSON.parse(raw); } catch { return json(502, { error: "contributor file is not valid JSON" }); }
  const maps = (content.maps || []).map((m) => ({
    match_id: m.match_id,
    game_no: m.game_no,
    demo_code: m.demo_code,
    map_name: m.map_name,
    map_category: m.map_category,
    side_a_team: m.side_a_team,
    side_b_team: m.side_b_team,
    captured_at: m.captured_at,
    observations: Array.isArray(m.observations) ? m.observations.length : null,
  }));
  return json(200, {
    key,
    name: content.contributor || key,
    tool_version: content.tool_version || null,
    maps_count: maps.length,
    maps,
  });
}

function json(status, obj) {
  return new Response(JSON.stringify(obj), {
    status,
    headers: {
      "content-type": "application/json",
      // The dashboard calls /refresh from the Pages origin.
      "access-control-allow-origin": "*",
      "access-control-allow-headers": "content-type,x-owdb-name,x-owdb-token,x-owdb-session",
      // JSON APIs shouldn't be framed, sniffed, or leak Referer.
      "content-security-policy": "default-src 'none'",
      "x-content-type-options": "nosniff",
      "referrer-policy": "no-referrer",
    },
  });
}

// ---------------------------------------------------------------------------
// ClaimRoom - the live scouting-claims Durable Object (one global instance).
// Holds { "match:game": {owner, by, at} }, persisted to SQLite-backed storage.
// Each scout keeps a hibernatable WebSocket; claim/release is broadcast to all
// instantly, and a dropped socket frees that scout's maps at once (no TTL wait).
// An alarm prunes zombie claims from half-open sockets as a backstop.
// ---------------------------------------------------------------------------
const CLAIM_STALE_MS = 6 * 60_000;   // prune a claim not refreshed within this (heartbeat is ~90s)
const CLAIM_PRUNE_EVERY_MS = 5 * 60_000;

export class ClaimRoom {
  constructor(ctx, env) { this.ctx = ctx; this.env = env; this.claims = null; }

  async load() { if (this.claims === null) this.claims = (await this.ctx.storage.get("claims")) || {}; return this.claims; }
  persist() { return this.ctx.storage.put("claims", this.claims); }
  publicClaims() { const o = {}; for (const k in this.claims) o[k] = { by: this.claims[k].by, at: this.claims[k].at }; return o; }
  broadcast(msg, except) { const s = JSON.stringify(msg); for (const ws of this.ctx.getWebSockets()) { if (ws === except) continue; try { ws.send(s); } catch (e) {} } }

  // key must be match_id:game_no
  ok(key) { return /^[\w-]+:\d+$/.test(key); }
  doClaim(key, owner, by) {
    const cur = this.claims[key];
    if (cur && cur.owner !== owner) return { ok: false, by: cur.by };   // someone else holds it (advisory)
    this.claims[key] = { owner, by, at: Date.now() };
    this.broadcast({ type: "set", key, claim: { by, at: this.claims[key].at } });
    return { ok: true, by };
  }
  doRelease(key, owner) {
    const cur = this.claims[key];
    if (cur && cur.owner === owner) { delete this.claims[key]; this.broadcast({ type: "del", key }); return true; }
    return false;
  }

  async fetch(request) {
    await this.load();
    const url = new URL(request.url);
    const owner = request.headers.get("x-owner") || "anon";
    const by = request.headers.get("x-by") || "a scout";

    if (request.headers.get("Upgrade") === "websocket") {
      const pair = new WebSocketPair();
      const [client, server] = Object.values(pair);
      this.ctx.acceptWebSocket(server);                 // hibernatable: no duration charge while idle
      // Identity arrives on the first message (an `identify` frame), not the
      // upgrade, so tokens never ride in the WS URL.
      server.send(JSON.stringify({ type: "snapshot", claims: this.publicClaims() }));
      await this.ensureAlarm();
      return new Response(null, { status: 101, webSocket: client });
    }

    if (url.pathname.endsWith("/claims")) return json(200, { claims: this.publicClaims() });
    if (url.pathname.endsWith("/claim") || url.pathname.endsWith("/unclaim")) {
      let body; try { body = JSON.parse((await request.text()) || "{}"); } catch { return json(400, { error: "body is not JSON" }); }
      const key = String(body.key || "");
      if (!this.ok(key)) return json(400, { error: "bad claim key" });
      if (url.pathname.endsWith("/unclaim")) { this.doRelease(key, owner); await this.persist(); return json(200, { ok: true }); }
      const r = this.doClaim(key, owner, by); await this.persist(); await this.ensureAlarm();
      return json(200, r);
    }
    return json(404, { error: "not found" });
  }

  async webSocketMessage(ws, raw) {
    let m; try { m = JSON.parse(raw); } catch { return; }
    if (m.type === "identify") {
      const { owner, by } = await resolveIdentity({
        session: m.session, name: m.name, token: m.token,
      }, this.env);
      ws.serializeAttachment({ owner, by });
      try { ws.send(JSON.stringify({ type: "identified" })); } catch (e) {}
      return;
    }
    const { owner, by } = ws.deserializeAttachment() || {};
    if (m.type === "claim" && this.ok(m.key)) {
      const r = this.doClaim(m.key, owner, by);
      try { ws.send(JSON.stringify({ type: "claimresult", key: m.key, ok: r.ok, by: r.by })); } catch (e) {}
      this.persist();
    } else if (m.type === "unclaim" && this.ok(m.key)) {
      this.doRelease(m.key, owner); this.persist();
    } else if (m.type === "ping") {
      try { ws.send(JSON.stringify({ type: "pong" })); } catch (e) {}
    }
  }
  webSocketClose(ws) { this.releaseAllOwned(ws); }
  webSocketError(ws) { this.releaseAllOwned(ws); }

  // Free every claim held by a departing socket's owner - unless another of that
  // owner's tabs is still open (so a second tab doesn't drop the first's locks).
  releaseAllOwned(ws) {
    const { owner } = ws.deserializeAttachment() || {};
    if (!owner) return;
    const stillHere = this.ctx.getWebSockets().some((s) => s !== ws && (s.deserializeAttachment() || {}).owner === owner);
    if (stillHere) return;
    let changed = false;
    for (const k in this.claims) if (this.claims[k].owner === owner) { delete this.claims[k]; this.broadcast({ type: "del", key: k }); changed = true; }
    if (changed) this.persist();
  }

  async ensureAlarm() { if (!(await this.ctx.storage.getAlarm())) await this.ctx.storage.setAlarm(Date.now() + CLAIM_PRUNE_EVERY_MS); }
  async alarm() {
    await this.load();
    const now = Date.now(); let changed = false;
    for (const k in this.claims) if (now - (this.claims[k].at || 0) > CLAIM_STALE_MS) { delete this.claims[k]; this.broadcast({ type: "del", key: k }); changed = true; }
    if (changed) await this.persist();
    if (Object.keys(this.claims).length) await this.ctx.storage.setAlarm(now + CLAIM_PRUNE_EVERY_MS);   // keep pruning while claims exist
  }
}

/**
 * owscout upload endpoint (Cloudflare Worker) - OPEN ACCESS.
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
    if (request.method === "OPTIONS") return json(204, {});   // CORS preflight

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
      const res = await fetch(`https://api.github.com/repos/${env.REPO}/dispatches`, {
        method: "POST",
        headers: {
          Authorization: `Bearer ${env.GITHUB_TOKEN}`,
          Accept: "application/vnd.github+json",
          "User-Agent": "owscout-upload-worker",
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ event_type: "refresh" }),
      });
      if (res.status !== 204) {
        return json(502, { error: `could not start the refresh (HTTP ${res.status})` });
      }
      await env.NAMES.put("_refresh_at", String(Date.now()));
      return json(200, { started: true });
    }

    if (request.method !== "POST") {
      return json(405, { error: "POST a contribution with X-Owscout-Name and X-Owscout-Token" });
    }
    const name = (request.headers.get("x-owscout-name") || "").trim().toLowerCase();
    const token = request.headers.get("x-owscout-token") || "";
    if (!NAME_RE.test(name)) {
      return json(400, { error: "name must be 2-24 chars of a-z 0-9 _ -" });
    }
    if (token.length < 16 || token.length > 128) {
      return json(400, { error: "malformed identity token" });
    }
    if ((env.DENYLIST || "").split(",").map((x) => x.trim()).includes(name)) {
      return json(403, { error: "this name is blocked - contact the curator" });
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

    // First upload claims the name; afterwards only the claiming install may
    // write it. Identity is a fact of the token, not a claim in the file.
    const tokenHash = await sha256hex(token);
    const rec = await env.NAMES.get(name, { type: "json" });
    if (rec && rec.h !== tokenHash) {
      return json(403, { error: `the name '${name}' is already used from another ` +
                                 "install - pick a different name in the Publish box" });
    }
    if (rec && Date.now() - (rec.t || 0) < MIN_INTERVAL_MS) {
      return json(429, { error: "uploading too fast - wait half a minute" });
    }

    data.contributor = name;               // server-side identity, always
    const path = `data/captures/${name}.json`;
    const content = btoa(unescape(encodeURIComponent(JSON.stringify(data, null, 2))));

    const gh = (url, init = {}) => fetch(`https://api.github.com/repos/${env.REPO}/${url}`, {
      ...init,
      headers: {
        Authorization: `Bearer ${env.GITHUB_TOKEN}`,
        Accept: "application/vnd.github+json",
        "User-Agent": "owscout-upload-worker",
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
        message: `contribution: ${name} (${data.maps.length} maps)`,
        content,
        ...(sha ? { sha } : {}),
      }),
    });
    if (put.status !== 200 && put.status !== 201) {
      return json(502, { error: `github: HTTP ${put.status}` });
    }
    await env.NAMES.put(name, JSON.stringify({ h: tokenHash, t: Date.now() }));
    return json(200, { action: sha ? "updated" : "created", maps: data.maps.length });
  },
};

async function sha256hex(s) {
  const d = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(s));
  return [...new Uint8Array(d)].map((b) => b.toString(16).padStart(2, "0")).join("");
}

function json(status, obj) {
  return new Response(JSON.stringify(obj), {
    status,
    headers: {
      "content-type": "application/json",
      // The dashboard calls /refresh from the Pages origin.
      "access-control-allow-origin": "*",
      "access-control-allow-headers": "content-type,x-owscout-name,x-owscout-token",
    },
  });
}

// Strava login + API proxy for the gallery's "Add poster" page (Cloudflare Worker).
//
// Keeps the Strava app's client secret off the public site. Routes:
//   GET  /auth/start?return=<page url>  -> Strava consent page (scope read,activity:read_all)
//   GET  /auth/callback                 -> exchanges the code, then redirects back to <page url>#access_token=…
//   POST /auth/refresh {refresh_token}  -> fresh tokens (JSON)
//   GET  /api/activities/<id>[/streams] -> the same Strava API call, authorized by the caller's Bearer token
// Only pages on ALLOWED_ORIGINS may use it. Secrets: STRAVA_CLIENT_ID, STRAVA_CLIENT_SECRET (wrangler secret put).
// STRAVA_API / STRAVA_OAUTH exist only so it can be tested against a local fake.

const SCOPE = "read,activity:read_all";
const STATE_TTL_MS = 10 * 60 * 1000;
const API_PATH = /^\/api\/(athlete|activities\/\d+(\/streams)?)$/;
const RATE_HEADERS = ["X-RateLimit-Limit", "X-RateLimit-Usage", "X-ReadRateLimit-Limit", "X-ReadRateLimit-Usage"];

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    const origins = (env.ALLOWED_ORIGINS || "").split(",").map(s => s.trim()).filter(Boolean);
    const oauth = env.STRAVA_OAUTH || "https://www.strava.com/oauth";
    const api = env.STRAVA_API || "https://www.strava.com/api/v3";
    try {
      if (url.pathname === "/auth/start" && request.method === "GET") return await start(url, env, origins, oauth);
      if (url.pathname === "/auth/callback" && request.method === "GET") return await callback(url, env, origins, oauth);
      const origin = request.headers.get("Origin");
      if (!origin || !origins.includes(origin)) return text(403, "Origin not allowed");
      if (request.method === "OPTIONS") return new Response(null, { status: 204, headers: cors(origin) });
      if (url.pathname === "/auth/refresh" && request.method === "POST") return await refresh(request, env, origin, oauth);
      if (API_PATH.test(url.pathname) && request.method === "GET") return await proxy(request, url, origin, api);
      return text(404, "Not found", cors(origin));
    } catch (e) {
      return text(500, "Worker error: " + (e && e.message || e));
    }
  },
};

function text(status, body, headers = {}) {
  return new Response(body, { status, headers: { "Content-Type": "text/plain; charset=utf-8", ...headers } });
}
function cors(origin) {
  return { "Access-Control-Allow-Origin": origin, "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
           "Access-Control-Allow-Headers": "Authorization, Content-Type", "Access-Control-Expose-Headers": RATE_HEADERS.join(", "),
           "Access-Control-Max-Age": "600", "Vary": "Origin" };
}
function allowedReturn(ret, origins) {
  try { return origins.includes(new URL(ret).origin); } catch { return false; }
}

// ---------- signed state: the page to return to, a nonce and a timestamp, HMAC'd with the client secret ----------
const b64u = bytes => btoa(String.fromCharCode(...new Uint8Array(bytes))).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
const unb64u = s => Uint8Array.from(atob(s.replace(/-/g, "+").replace(/_/g, "/")), c => c.charCodeAt(0));
async function hmacKey(secret) {
  return crypto.subtle.importKey("raw", new TextEncoder().encode(secret), { name: "HMAC", hash: "SHA-256" }, false, ["sign", "verify"]);
}
async function signState(payload, secret) {
  const body = b64u(new TextEncoder().encode(JSON.stringify(payload)));
  const sig = await crypto.subtle.sign("HMAC", await hmacKey(secret), new TextEncoder().encode(body));
  return body + "." + b64u(sig);
}
async function readState(state, secret) {
  const [body, sig] = (state || "").split(".");
  if (!body || !sig) return null;
  const ok = await crypto.subtle.verify("HMAC", await hmacKey(secret), unb64u(sig), new TextEncoder().encode(body));
  if (!ok) return null;
  const p = JSON.parse(new TextDecoder().decode(unb64u(body)));
  return Date.now() - p.t <= STATE_TTL_MS ? p : null;
}

async function start(url, env, origins, oauth) {
  const ret = url.searchParams.get("return");
  if (!allowedReturn(ret, origins)) return text(400, "return must be a page on an allowed origin");
  const nonce = b64u(crypto.getRandomValues(new Uint8Array(12)));
  const state = await signState({ r: ret, n: nonce, t: Date.now() }, env.STRAVA_CLIENT_SECRET);
  const q = new URLSearchParams({ client_id: env.STRAVA_CLIENT_ID, response_type: "code", approval_prompt: "auto",
                                  scope: SCOPE, redirect_uri: url.origin + "/auth/callback", state });
  return Response.redirect(oauth + "/authorize?" + q, 302);
}

async function callback(url, env, origins, oauth) {
  const st = await readState(url.searchParams.get("state"), env.STRAVA_CLIENT_SECRET);
  if (!st || !allowedReturn(st.r, origins)) return text(400, "This login link is invalid or expired. Start again from the Add poster page.");
  const back = (params) => Response.redirect(st.r.split("#")[0] + "#" + new URLSearchParams(params), 302);
  if (url.searchParams.get("error")) return back({ strava_error: url.searchParams.get("error") });
  const res = await fetch(oauth + "/token", { method: "POST", headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body: new URLSearchParams({ client_id: env.STRAVA_CLIENT_ID, client_secret: env.STRAVA_CLIENT_SECRET,
                                code: url.searchParams.get("code") || "", grant_type: "authorization_code" }) });
  if (!res.ok) return back({ strava_error: "token_exchange_failed_" + res.status });
  const tok = await res.json();
  // tokens travel in the fragment, which browsers never send to a server
  return back({ access_token: tok.access_token, refresh_token: tok.refresh_token, expires_at: String(tok.expires_at),
                scope: url.searchParams.get("scope") || "", athlete: (tok.athlete && tok.athlete.firstname) || "" });
}

async function refresh(request, env, origin, oauth) {
  let body;
  try { body = await request.json(); } catch { body = {}; }
  if (!body.refresh_token) return text(400, "refresh_token missing", cors(origin));
  const res = await fetch(oauth + "/token", { method: "POST", headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body: new URLSearchParams({ client_id: env.STRAVA_CLIENT_ID, client_secret: env.STRAVA_CLIENT_SECRET,
                                grant_type: "refresh_token", refresh_token: body.refresh_token }) });
  const tok = await res.json().catch(() => ({}));
  if (!res.ok) return new Response(JSON.stringify({ error: tok.message || "refresh failed" }),
                                   { status: res.status, headers: { "Content-Type": "application/json", ...cors(origin) } });
  return new Response(JSON.stringify({ access_token: tok.access_token, refresh_token: tok.refresh_token, expires_at: tok.expires_at }),
                      { headers: { "Content-Type": "application/json", ...cors(origin) } });
}

async function proxy(request, url, origin, api) {
  const auth = request.headers.get("Authorization");
  if (!auth || !auth.startsWith("Bearer ")) return text(401, "Bearer token required", cors(origin));
  const res = await fetch(api + url.pathname.slice(4) + url.search, { headers: { Authorization: auth } });
  const headers = { "Content-Type": res.headers.get("Content-Type") || "application/json", ...cors(origin) };
  for (const h of RATE_HEADERS) { const v = res.headers.get(h); if (v) headers[h] = v; }
  return new Response(res.body, { status: res.status, headers });
}

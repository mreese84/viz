# Strava login Worker

A small Cloudflare Worker that lets the gallery's **Add poster** page log in to Strava and read your activities
without putting the Strava app's client secret in the public site. It holds the secret, exchanges the login code
for tokens, refreshes them, and forwards the two Strava API calls the page needs. Only pages on
`ALLOWED_ORIGINS` (in `wrangler.toml`) can use it.

## One-time setup

You need Node.js (18+) and a free Cloudflare account. From this folder:

1. Log in to Cloudflare:
   ```
   npx wrangler login
   ```
2. Deploy:
   ```
   npx wrangler deploy
   ```
   It prints the Worker's address, e.g. `https://viz-strava-auth.<your-subdomain>.workers.dev`.
3. Store your Strava app's id and secret (from https://www.strava.com/settings/api) as Worker secrets; each command prompts for the value:
   ```
   npx wrangler secret put STRAVA_CLIENT_ID
   npx wrangler secret put STRAVA_CLIENT_SECRET
   ```
4. On https://www.strava.com/settings/api set **Authorization Callback Domain** to the Worker's host, e.g.
   `viz-strava-auth.<your-subdomain>.workers.dev` (no `https://`). `localhost` keeps working for the local scripts.
5. Put the Worker's address in `src/site.json` (`"stravaWorker"`), commit, and push.

## Check it

Open `https://<worker address>/auth/start?return=https://mreese84.github.io/viz/new/`. You should land on Strava's
consent page. Anything else (a 400 message) means a setting above is off.

## Routes

- `GET /auth/start?return=<page>` → Strava consent (scope `read,activity:read_all`)
- `GET /auth/callback` → exchanges the code, redirects to `<page>#access_token=…&refresh_token=…&expires_at=…`
- `POST /auth/refresh` `{"refresh_token": …}` → new tokens
- `GET /api/activities/<id>` and `/api/activities/<id>/streams` (and `/api/athlete`) → forwarded to Strava with the caller's token

The login state is signed with the client secret and expires after 10 minutes. Tokens are returned in the URL
fragment, which browsers never send to a server.

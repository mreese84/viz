"""Shared Strava API helpers (standard library only): .env, OAuth tokens with auto-refresh, rate-limited GET.

Secrets live in .env (STRAVA_CLIENT_ID, STRAVA_CLIENT_SECRET) and tokens in .strava_tokens.json, both
git-ignored. Nothing here prints a secret or token.
"""
import json, os, sys, time, urllib.error, urllib.parse, urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ENV_PATH = os.path.join(ROOT, ".env")
TOKENS_PATH = os.path.join(ROOT, ".strava_tokens.json")
# Overridable only so the scripts can be tested against a local fake; normal use never sets these.
API = os.environ.get("STRAVA_API_BASE", "https://www.strava.com/api/v3")
OAUTH = os.environ.get("STRAVA_OAUTH_BASE", "https://www.strava.com/oauth")
SCOPE = "read,activity:read_all"

class StravaError(Exception):
    pass

def load_env():
    """STRAVA_CLIENT_ID / STRAVA_CLIENT_SECRET from the environment or .env (environment wins)."""
    vals = {}
    if os.path.exists(ENV_PATH):
        for line in open(ENV_PATH, encoding="utf-8"):
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line: continue
            k, v = line.split("=", 1)
            vals[k.strip()] = v.strip().strip('"').strip("'")
    out = {k: os.environ.get(k) or vals.get(k, "") for k in ("STRAVA_CLIENT_ID", "STRAVA_CLIENT_SECRET")}
    missing = [k for k, v in out.items() if not v]
    if missing:
        raise StravaError(f"{', '.join(missing)} not set. Copy .env.example to .env and fill it in "
                          "from https://www.strava.com/settings/api.")
    return out

def save_tokens(tok):
    keep = {k: tok[k] for k in ("access_token", "refresh_token", "expires_at") if k in tok}
    if "scope" in tok: keep["scope"] = tok["scope"]
    fd = os.open(TOKENS_PATH, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)   # owner-only
    with os.fdopen(fd, "w") as f: json.dump(keep, f)

def load_tokens():
    if not os.path.exists(TOKENS_PATH):
        raise StravaError("No Strava tokens yet. Run: python3 scripts/strava_auth.py")
    return json.load(open(TOKENS_PATH))

def _error_text(e):
    """Strava's error message from an HTTPError, without echoing anything that could hold a secret."""
    try:
        body = json.loads(e.read().decode("utf-8", "replace"))
        msg = body.get("message", "")
        errs = "; ".join(f'{x.get("resource","")}.{x.get("field","")}: {x.get("code","")}' for x in body.get("errors", []))
        return f"HTTP {e.code} {msg}" + (f" ({errs})" if errs else "")
    except Exception:
        return f"HTTP {e.code}"

def token_request(params):
    """POST to /oauth/token (code exchange or refresh). Returns the token response."""
    data = urllib.parse.urlencode(params).encode()
    try:
        with urllib.request.urlopen(urllib.request.Request(OAUTH + "/token", data=data, method="POST"), timeout=30) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        raise StravaError("Token request failed: " + _error_text(e)) from None

def refresh(tok=None):
    env, tok = load_env(), tok or load_tokens()
    new = token_request({"client_id": env["STRAVA_CLIENT_ID"], "client_secret": env["STRAVA_CLIENT_SECRET"],
                         "grant_type": "refresh_token", "refresh_token": tok["refresh_token"]})
    new.setdefault("scope", tok.get("scope"))
    save_tokens(new)   # Strava may rotate the refresh token, so always save the new pair
    return new

def access_token():
    tok = load_tokens()
    if tok.get("expires_at", 0) - 60 < time.time():
        tok = refresh(tok)
    return tok["access_token"]

# ---------- Rate limits ----------
# Strava sends overall and read limits as "15-minute,daily" pairs, e.g. X-ReadRateLimit-Usage: 12,340
usage = {}

def _note_limits(headers):
    for kind, prefix in (("overall", "X-RateLimit"), ("read", "X-ReadRateLimit")):
        lim, use = headers.get(prefix + "-Limit"), headers.get(prefix + "-Usage")
        if lim and use:
            (l15, lday), (u15, uday) = [tuple(int(x) for x in v.split(",")[:2]) for v in (lim, use)]
            usage[kind] = dict(limit15=l15, limitDay=lday, used15=u15, usedDay=uday)

def usage_line():
    if not usage: return "rate limits: (no headers seen)"
    return "rate limits: " + "; ".join(f'{k} {v["used15"]}/{v["limit15"]} per 15 min, {v["usedDay"]}/{v["limitDay"]} today'
                                       for k, v in usage.items())

def _wait_for_window():
    """Sleep until the next 15-minute window (Strava's windows start at :00, :15, :30, :45 UTC)."""
    for v in usage.values():
        if v["usedDay"] >= v["limitDay"]:
            raise StravaError("Daily Strava rate limit used up; try again after midnight UTC. " + usage_line())
    wait = 900 - time.time() % 900 + 5
    print(f"  rate limited (429); waiting {wait/60:.1f} min for the next 15-minute window", file=sys.stderr)
    time.sleep(wait)

def get(path, params=None, retries=3):
    """GET an API path as the authorized athlete. Refreshes the token once on 401, waits out 429s."""
    url = API + path + ("?" + urllib.parse.urlencode(params) if params else "")
    refreshed = False
    for attempt in range(retries + 1):
        req = urllib.request.Request(url, headers={"Authorization": "Bearer " + access_token()})
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                _note_limits(r.headers)
                return json.load(r)
        except urllib.error.HTTPError as e:
            _note_limits(e.headers)
            if e.code == 401 and not refreshed:
                refresh(); refreshed = True; continue
            if e.code == 429 and attempt < retries:
                _wait_for_window(); continue
            if e.code == 404:
                raise StravaError(f"{path}: not found (wrong id, or not your activity?)") from None
            raise StravaError(f"{path}: " + _error_text(e)) from None
    raise StravaError(f"{path}: still rate limited after {retries} waits")

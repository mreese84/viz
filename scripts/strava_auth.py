"""One-time Strava authorization for your own account.

    python3 scripts/strava_auth.py [--port 8721]

Needs STRAVA_CLIENT_ID and STRAVA_CLIENT_SECRET in .env (copy .env.example), and the Strava app's
"Authorization Callback Domain" set to localhost. Opens your browser at Strava's consent page
(scope read,activity:read_all), catches the redirect on http://localhost:<port>/callback, exchanges
the code and saves tokens to .strava_tokens.json (git-ignored, owner-only). Other scripts refresh the
tokens automatically after that; run this again only if you revoke access or change scopes.
"""
import argparse, http.server, secrets, socket, sys, threading, urllib.parse, webbrowser
import strava_client as sc

def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--port", type=int, default=8721)
    ap.add_argument("--timeout", type=int, default=300, help="seconds to wait for the browser (default 300)")
    args = ap.parse_args()
    env = sc.load_env()
    state, redirect = secrets.token_urlsafe(16), f"http://localhost:{args.port}/callback"
    result, done = {}, threading.Event()

    class Callback(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            u = urllib.parse.urlparse(self.path)
            if u.path != "/callback":
                self.send_response(404); self.end_headers(); return
            q = dict(urllib.parse.parse_qsl(u.query))
            ok = q.get("state") == state and "code" in q
            result.update(q, ok=ok)
            self.send_response(200 if ok else 400)
            self.send_header("Content-Type", "text/html; charset=utf-8"); self.end_headers()
            msg = "Strava access granted. You can close this tab." if ok else "Strava authorization failed or was cancelled. Check the terminal."
            self.wfile.write(f"<!doctype html><meta charset=utf-8><title>Strava</title><p style='font:16px system-ui;margin:3em'>{msg}</p>".encode())
            done.set()
        def log_message(self, *a): pass   # keep the terminal quiet (the URL carries the one-time code)

    # "localhost" may resolve to IPv4 or IPv6 in the browser, so listen on both loopbacks (never the network)
    class Server6(http.server.HTTPServer): address_family = socket.AF_INET6
    servers = []
    try:
        servers.append(http.server.HTTPServer(("127.0.0.1", args.port), Callback))
    except OSError as e:
        sys.exit(f"Can't listen on port {args.port} ({e.strerror}). Try --port with another number.")
    try:
        servers.append(Server6(("::1", args.port), Callback))
    except OSError:
        pass   # no IPv6 loopback; IPv4 is enough
    url = sc.OAUTH + "/authorize?" + urllib.parse.urlencode({
        "client_id": env["STRAVA_CLIENT_ID"], "response_type": "code", "redirect_uri": redirect,
        "approval_prompt": "auto", "scope": sc.SCOPE, "state": state})
    # Serve before opening the browser: webbrowser.open() blocks until a command-line browser exits,
    # and that browser is itself waiting for this callback.
    for srv in servers: threading.Thread(target=srv.serve_forever, daemon=True).start()
    print("Opening Strava in your browser. If it doesn't open, visit:\n  " + url)
    webbrowser.open(url)
    done.wait(args.timeout)
    for srv in servers: srv.shutdown(); srv.server_close()

    if not result:
        sys.exit(f"No response from Strava within {args.timeout} s. Run again when ready.")
    if result.get("error"):
        sys.exit(f"Strava returned: {result['error']} (did you click Cancel?)")
    if not result.get("ok"):
        sys.exit("The callback didn't match this login attempt (state mismatch). Run again.")
    granted = set(result.get("scope", "").split(","))
    tok = sc.token_request({"client_id": env["STRAVA_CLIENT_ID"], "client_secret": env["STRAVA_CLIENT_SECRET"],
                            "code": result["code"], "grant_type": "authorization_code"})
    tok["scope"] = ",".join(sorted(granted))
    sc.save_tokens(tok)
    who = tok.get("athlete", {}).get("firstname")
    print(f"Authorized{(' as ' + who) if who else ''}. Tokens saved to .strava_tokens.json (git-ignored).")
    if "activity:read_all" not in granted:
        print("Warning: 'View data about your private activities' wasn't granted; private activities "
              "will fail to fetch. Run again and keep that box ticked.")

if __name__ == "__main__":
    try:
        main()
    except sc.StravaError as e:
        sys.exit(str(e))

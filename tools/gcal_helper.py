#!/usr/bin/env python3
"""Mac-side Google Calendar helper (read-only). Standard library only.

Runs on the Mac, NOT in Docker, because the Google credentials live in the macOS
Keychain, which containers cannot read (CLAUDE.md rule 7). It writes a plain JSON
file of upcoming events into ~/IG-Harness-data, which the harness imports.

  python3 tools/gcal_helper.py store-client <client_secret.json>   one time
  python3 tools/gcal_helper.py login                               one time (browser)
  python3 tools/gcal_helper.py sync                                whenever you like

Keychain items: ig-harness-google-client (account calendar), ig-harness-google-calendar
(account refresh-token). Scope: calendar.readonly. Only the primary calendar is read.
Only title, start, end and status are kept: no attendees, descriptions or links.
"""
import base64, hashlib, http.server, json, os, secrets, subprocess, sys, threading
import urllib.parse, urllib.request, webbrowser
from datetime import datetime, timedelta, timezone
from pathlib import Path

SCOPE = "https://www.googleapis.com/auth/calendar.readonly"
AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
EVENTS_URL = "https://www.googleapis.com/calendar/v3/calendars/primary/events"
CLIENT_ITEM, CLIENT_ACCT = "ig-harness-google-client", "calendar"
TOKEN_ITEM, TOKEN_ACCT = "ig-harness-google-calendar", "refresh-token"
OUT = Path(os.environ.get("IG_DATA_DIR", Path.home() / "IG-Harness-data")) / "calendar_events.json"
DAYS_BACK, DAYS_AHEAD = 7, 90


def kc_get(item: str, acct: str) -> str | None:
    r = subprocess.run(["security", "find-generic-password", "-s", item, "-a", acct, "-w"],
                       capture_output=True, text=True)
    return r.stdout.strip() if r.returncode == 0 else None


def kc_set(item: str, acct: str, value: str) -> None:
    subprocess.run(["security", "add-generic-password", "-U", "-s", item, "-a", acct, "-w", value],
                   check=True, capture_output=True)


def normalize_event(item: dict) -> dict | None:
    """Keep only title, times, status. Returns None for cancelled events."""
    if item.get("status") == "cancelled":
        return None
    s, e = item.get("start", {}), item.get("end", {})
    start = s.get("dateTime") or s.get("date")
    if not item.get("id") or not start:
        return None
    return {"id": item["id"], "title": item.get("summary") or "(no title)", "start": start,
            "end": e.get("dateTime") or e.get("date"), "all_day": "date" in s,
            "status": item.get("status", "confirmed")}


def _post(url: str, data: dict) -> dict:
    req = urllib.request.Request(url, urllib.parse.urlencode(data).encode())
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def _client() -> dict:
    raw = kc_get(CLIENT_ITEM, CLIENT_ACCT)
    if not raw:
        sys.exit("No Google client in Keychain. Run: store-client <file>")
    return json.loads(raw)


def store_client(path: str) -> None:
    p = Path(path).expanduser()
    inst = json.loads(p.read_text()).get("installed")
    if not inst:
        sys.exit("That file is not a 'Desktop app' client. Nothing stored.")
    kc_set(CLIENT_ITEM, CLIENT_ACCT, json.dumps({"client_id": inst["client_id"],
                                                 "client_secret": inst["client_secret"]}))
    p.unlink()
    print("Stored in Keychain and deleted the downloaded file.")


def login() -> None:
    c = _client()
    verifier = secrets.token_urlsafe(64)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    state, got = secrets.token_urlsafe(16), {}

    class H(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            got.update({k: v[0] for k, v in q.items()})
            self.send_response(200); self.send_header("Content-Type", "text/plain"); self.end_headers()
            self.wfile.write(b"IG Harness: you can close this tab and return to Terminal.")
        def log_message(self, *a): pass

    srv = http.server.HTTPServer(("127.0.0.1", 0), H)
    redirect = f"http://127.0.0.1:{srv.server_port}"
    url = AUTH_URL + "?" + urllib.parse.urlencode({
        "client_id": c["client_id"], "redirect_uri": redirect, "response_type": "code",
        "scope": SCOPE, "access_type": "offline", "prompt": "consent", "state": state,
        "code_challenge": challenge, "code_challenge_method": "S256"})
    print("Opening your browser to approve READ-ONLY calendar access...")
    webbrowser.open(url)
    threading.Thread(target=srv.handle_request, daemon=True).start()
    for _ in range(300):
        if got:
            break
        import time; time.sleep(1)
    if got.get("state") != state or "code" not in got:
        sys.exit(f"Login failed or timed out ({got.get('error', 'no response')}).")
    tok = _post(TOKEN_URL, {"code": got["code"], "client_id": c["client_id"],
                            "client_secret": c["client_secret"], "redirect_uri": redirect,
                            "grant_type": "authorization_code", "code_verifier": verifier})
    if "refresh_token" not in tok:
        sys.exit("Google did not return a refresh token. Remove the app at myaccount.google.com/permissions and retry.")
    kc_set(TOKEN_ITEM, TOKEN_ACCT, tok["refresh_token"])
    print("Logged in. Token stored in Keychain. Now run: sync")


def sync() -> None:
    c, refresh = _client(), kc_get(TOKEN_ITEM, TOKEN_ACCT)
    if not refresh:
        sys.exit("Not logged in. Run: login")
    access = _post(TOKEN_URL, {"client_id": c["client_id"], "client_secret": c["client_secret"],
                               "refresh_token": refresh, "grant_type": "refresh_token"})["access_token"]
    now = datetime.now(timezone.utc)
    t_min, t_max = now - timedelta(days=DAYS_BACK), now + timedelta(days=DAYS_AHEAD)
    events, page = [], None
    while True:
        params = {"timeMin": t_min.isoformat(), "timeMax": t_max.isoformat(), "singleEvents": "true",
                  "orderBy": "startTime", "maxResults": "250", "fields": "nextPageToken,items(id,status,summary,start,end)"}
        if page:
            params["pageToken"] = page
        req = urllib.request.Request(EVENTS_URL + "?" + urllib.parse.urlencode(params),
                                     headers={"Authorization": f"Bearer {access}"})
        with urllib.request.urlopen(req, timeout=30) as r:
            body = json.load(r)
        events += [e for e in map(normalize_event, body.get("items", [])) if e]
        page = body.get("nextPageToken")
        if not page:
            break
    OUT.parent.mkdir(parents=True, exist_ok=True)
    tmp = OUT.with_suffix(".tmp")
    tmp.write_text(json.dumps({"fetched_at": now.isoformat(), "window_start": t_min.isoformat(),
                               "window_end": t_max.isoformat(), "events": events}, ensure_ascii=False))
    tmp.replace(OUT)
    print(f"Wrote {len(events)} events to {OUT}")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "store-client" and len(sys.argv) == 3: store_client(sys.argv[2])
    elif cmd == "login": login()
    elif cmd == "sync": sync()
    else: sys.exit(__doc__)

#!/usr/bin/env python3
"""Mac-side Google helper (Calendar and Gmail, both read-only). Standard library only.

Runs on the Mac, NOT in Docker, because the Google credentials live in the macOS
Keychain, which containers cannot read (CLAUDE.md rule 7). It writes a plain JSON
file of upcoming events into ~/IG-Harness-data, which the harness imports.

  python3 tools/google_helper.py store-client <client_secret.json>   one time
  python3 tools/google_helper.py login | sync                        calendar (login once)
  python3 tools/google_helper.py login-gmail | sync-gmail            Gmail (login once)
  python3 tools/google_helper.py sync-correspondence                 past threads with each person (for style profiles)
  python3 tools/google_helper.py sync-events                         event emails of the past year (Geneva and beyond); later runs read the last 3 weeks

Keychain items: ig-harness-google-client (account calendar), ig-harness-google-calendar and
ig-harness-google-gmail (account refresh-token). Scopes: calendar.readonly, gmail.readonly.
There is NO send or draft code in this file: Gmail access here cannot create or send mail.
Calendar keeps only title, start, end, status, location, a join link and her own response (attendees are counted, never listed). Gmail keeps recent inbox threads (sender,
subject, snippet, trimmed text) in ~/IG-Harness-data, on this Mac only.
"""
import base64, hashlib, http.server, json, os, re, secrets, ssl, subprocess, sys, threading
import urllib.parse, urllib.request, webbrowser
from datetime import datetime, timedelta, timezone
from pathlib import Path

SCOPE = "https://www.googleapis.com/auth/calendar.readonly"
GMAIL_SCOPE = "https://www.googleapis.com/auth/gmail.readonly"
GMAIL_API = "https://gmail.googleapis.com/gmail/v1/users/me"
AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
EVENTS_URL = "https://www.googleapis.com/calendar/v3/calendars/primary/events"
CLIENT_ITEM, CLIENT_ACCT = "ig-harness-google-client", "calendar"
TOKEN_ITEM, TOKEN_ACCT = "ig-harness-google-calendar", "refresh-token"
GMAIL_TOKEN_ITEM = "ig-harness-google-gmail"
DATA = Path(os.environ.get("IG_DATA_DIR", Path.home() / "IG-Harness-data"))
OUT = DATA / "calendar_events.json"
GMAIL_OUT = DATA / "gmail_recent.json"
CORR_OUT = DATA / "correspondence.json"
EVENT_OUT = DATA / "event_mail.json"
CORR_THREADS = 8
BODY_CHARS_CORR = 1500
GMAIL_QUERY = "in:inbox newer_than:3d -category:promotions -category:social -category:forums"
GMAIL_MAX_THREADS = 100
BODY_CHARS = 3000
DAYS_BACK, DAYS_AHEAD = 400, 180     # a year back for the Events archive, half a year ahead


_CTX: ssl.SSLContext | None = None


def _ssl_context() -> ssl.SSLContext:
    """Verify HTTPS against the Mac's own certificate list (python.org builds ship none). Built once: loading the list on every request was slow."""
    global _CTX
    if _CTX is None:
        _CTX = ssl.create_default_context()
        if os.path.exists("/etc/ssl/cert.pem"):
            _CTX.load_verify_locations("/etc/ssl/cert.pem")
    return _CTX


def kc_get(item: str, acct: str) -> str | None:
    r = subprocess.run(["security", "find-generic-password", "-s", item, "-a", acct, "-w"],
                       capture_output=True, text=True)
    return r.stdout.strip() if r.returncode == 0 else None


def kc_set(item: str, acct: str, value: str) -> None:
    subprocess.run(["security", "add-generic-password", "-U", "-s", item, "-a", acct, "-w", value],
                   check=True, capture_output=True)


def normalize_event(item: dict) -> dict | None:
    """Keep only what the harness needs: title, times, status, where, a join link, and HER response (accepted / tentative / declined /
    needsAction). Never the description or anyone's email address (attendees are only counted). Returns None for cancelled events."""
    if item.get("status") == "cancelled":
        return None
    s, e = item.get("start", {}), item.get("end", {})
    start = s.get("dateTime") or s.get("date")
    if not item.get("id") or not start:
        return None
    attendees = item.get("attendees") or []
    me = next((a for a in attendees if a.get("self")), None)
    self_org = bool((item.get("organizer") or {}).get("self"))
    link = item.get("hangoutLink") or next((ep.get("uri") for ep in (item.get("conferenceData") or {}).get("entryPoints", []) if ep.get("uri", "").startswith("http")), None)
    return {"id": item["id"], "title": item.get("summary") or "(no title)", "start": start,
            "end": e.get("dateTime") or e.get("date"), "all_day": "date" in s,
            "status": item.get("status", "confirmed"),
            "my_response": me.get("responseStatus") if me else ("accepted" if self_org else None),
            "self_organizer": self_org, "attendee_count": len(attendees),
            "location": (item.get("location") or "")[:200] or None, "link": link}


def _post(url: str, data: dict) -> dict:
    req = urllib.request.Request(url, urllib.parse.urlencode(data).encode())
    with urllib.request.urlopen(req, timeout=30, context=_ssl_context()) as r:
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


def login(scope: str = SCOPE, item: str = TOKEN_ITEM) -> None:
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
        "scope": scope, "access_type": "offline", "prompt": "consent", "state": state,
        "code_challenge": challenge, "code_challenge_method": "S256"})
    print(f"Opening your browser to approve this access: {scope.rsplit('/', 1)[-1]}")
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
    kc_set(item, TOKEN_ACCT, tok["refresh_token"])
    print("Logged in. Token stored in Keychain.")


def _access_token(item: str, login_cmd: str) -> str:
    c, refresh = _client(), kc_get(item, TOKEN_ACCT)
    if not refresh:
        sys.exit(f"Not logged in. Run: {login_cmd}")
    return _post(TOKEN_URL, {"client_id": c["client_id"], "client_secret": c["client_secret"],
                             "refresh_token": refresh, "grant_type": "refresh_token"})["access_token"]


def sync() -> None:
    access = _access_token(TOKEN_ITEM, "login")
    now = datetime.now(timezone.utc)
    t_min, t_max = now - timedelta(days=DAYS_BACK), now + timedelta(days=DAYS_AHEAD)
    events, page = [], None
    while True:
        params = {"timeMin": t_min.isoformat(), "timeMax": t_max.isoformat(), "singleEvents": "true",
                  "orderBy": "startTime", "maxResults": "250", "fields": "nextPageToken,items(id,status,summary,start,end,location,hangoutLink,organizer(self),attendees(self,responseStatus),conferenceData(entryPoints(uri)))"}
        if page:
            params["pageToken"] = page
        req = urllib.request.Request(EVENTS_URL + "?" + urllib.parse.urlencode(params),
                                     headers={"Authorization": f"Bearer {access}"})
        with urllib.request.urlopen(req, timeout=30, context=_ssl_context()) as r:
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


def _get(url: str, access: str, params: dict | None = None, tries: int = 5) -> dict:
    """GET with retry: Google answers 403 rateLimitExceeded / 429 / 5xx when asked too fast."""
    import time
    full = url + ("?" + urllib.parse.urlencode(params) if params else "")
    req = urllib.request.Request(full, headers={"Authorization": f"Bearer {access}"})
    for attempt in range(tries):
        try:
            with urllib.request.urlopen(req, timeout=30, context=_ssl_context()) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            reason = _error_reason(e)
            retryable = e.code in (429, 500, 502, 503, 504) or (e.code == 403 and "ate" in reason and "imit" in reason)
            if retryable and attempt < tries - 1:
                time.sleep(2 ** attempt)           # 1, 2, 4, 8 seconds
                continue
            raise GoogleError(e.code, reason) from None
    raise AssertionError("unreachable")


class GoogleError(Exception):
    def __init__(self, code: int, reason: str):
        super().__init__(f"HTTP {code}: {reason}")
        self.code, self.reason = code, reason


def _error_reason(e: urllib.error.HTTPError) -> str:
    """Google's own explanation (error text only, never mail content)."""
    try:
        err = json.loads(e.read().decode() or "{}").get("error", {})
        return f"{err.get('message', '')} [{', '.join(x.get('reason', '') for x in err.get('errors', []))}]".strip()
    except Exception:
        return "no details"


def _header(headers: list[dict], name: str) -> str:
    for h in headers:
        if h.get("name", "").lower() == name.lower():
            return h.get("value", "")
    return ""


def _text_of(payload: dict) -> str:
    """Plain text of a message: text/plain if present, else tags stripped from text/html."""
    import re
    plain, html = [], []

    def walk(part):
        mt, data = part.get("mimeType", ""), part.get("body", {}).get("data")
        if data and mt in ("text/plain", "text/html"):
            raw = base64.urlsafe_b64decode(data + "=" * (-len(data) % 4)).decode("utf-8", "replace")
            (plain if mt == "text/plain" else html).append(raw)
        for sub in part.get("parts", []) or []:
            walk(sub)

    walk(payload)
    if plain:
        return "\n".join(plain)
    text = re.sub(r"(?is)<(script|style).*?</\1>", " ", "\n".join(html))
    text = re.sub(r"(?i)<br\s*/?>|</(p|div|li|tr|h[1-6])>", "\n", text)       # keep the line structure
    text = re.sub(r"(?s)<[^>]+>", " ", text)
    return "\n".join(re.sub(r"[ \t]+", " ", ln).strip() for ln in text.splitlines())


_QUOTE_START = re.compile(
    r"^\s*(on .{3,160}wrote:?|le .{3,160}a écrit\s*:?|am .{3,160}schrieb.{0,80}:?|-{2,}\s*(original message|forwarded message|message d.origine|ursprüngliche nachricht)"
    r"|(from|de|von|van)\s*:\s*\S|sent from my |envoyé de mon |gesendet von meinem )", re.I)


def strip_quoted(text: str) -> str:
    """Only what the author wrote: cut at the first quoted-reply marker and drop '>' quote lines."""
    lines = text.replace("\r", "").split("\n")
    out = []
    for i, ln in enumerate(lines):
        pair = ln.strip() + " " + (lines[i + 1].strip() if i + 1 < len(lines) else "")   # 'On ... wrote:' often wraps
        if _QUOTE_START.match(ln) or (ln.strip().lower().startswith(("on ", "le ", "am ")) and _QUOTE_START.match(pair)):
            break
        if ln.lstrip().startswith(">"):
            continue
        out.append(ln.rstrip())
    return "\n".join(out).strip()


def _parse_from(value: str) -> tuple[str, str]:
    from email.utils import parseaddr
    name, addr = parseaddr(value)
    return name.strip().strip('"'), addr.lower()


def _addresses(value: str) -> list[str]:
    from email.utils import getaddresses
    return [a.lower() for _, a in getaddresses([value]) if a]


def normalize_thread(thread: dict, me: str) -> dict | None:
    """One inbox thread -> the fields triage needs. Looks at the LAST message of the thread."""
    msgs = thread.get("messages") or []
    if not msgs:
        return None
    last = msgs[-1]
    h = last.get("payload", {}).get("headers", [])
    name, addr = _parse_from(_header(h, "From"))
    me = me.lower()
    body = " ".join(_text_of(last.get("payload", {})).split())[:BODY_CHARS]
    to_all = (_header(h, "To") + "," + _header(h, "Cc")).lower()
    return {
        "thread_id": thread["id"], "message_id": last["id"], "messages_in_thread": len(msgs),
        "received_ms": int(last.get("internalDate", 0)), "from_name": name, "from_email": addr,
        "to_me_directly": me in _header(h, "To").lower(), "cc_only": me in to_all and me not in _header(h, "To").lower(),
        "subject": _header(h, "Subject"), "snippet": last.get("snippet", ""), "body": body,
        "labels": last.get("labelIds", []), "last_from_me": addr == me,
        "rfc_message_id": _header(h, "Message-ID").strip(), "references": _header(h, "References").strip(),
        "to_addrs": _addresses(_header(h, "To")), "cc_addrs": _addresses(_header(h, "Cc")),
        "history": _history(msgs[:-1], me),
        "reply_to": _parse_from(_header(h, "Reply-To"))[1] if _header(h, "Reply-To") else "",
        "bulk": bool(_header(h, "List-Unsubscribe")) or _header(h, "Precedence").lower() in ("bulk", "list", "junk")
                or _header(h, "Auto-Submitted").lower().startswith("auto-"),
    }


def _history(earlier: list[dict], me: str) -> list[dict]:
    """The (up to 3) messages before the newest one, newest first: who wrote them and their new text only."""
    out = []
    for m in reversed(earlier[-3:]):
        h = m.get("payload", {}).get("headers", [])
        sender = _parse_from(_header(h, "From"))[1]
        out.append({"from_me": sender == me.lower(), "from_email": sender, "from_name": _parse_from(_header(h, "From"))[0],
                    "body": strip_quoted(_text_of(m.get("payload", {})))[:700]})
    return out


def sync_gmail() -> None:
    access = _access_token(GMAIL_TOKEN_ITEM, "login-gmail")
    me = _get(f"{GMAIL_API}/profile", access)["emailAddress"]
    ids = _get(f"{GMAIL_API}/threads", access, {"q": GMAIL_QUERY, "maxResults": str(GMAIL_MAX_THREADS)}).get("threads", [])
    threads, failed = [], {}
    import time
    for t in ids:
        try:
            n = normalize_thread(_get(f"{GMAIL_API}/threads/{t['id']}", access, {"format": "full"}), me)
        except GoogleError as e:               # one bad thread must not lose the rest
            failed[e.reason] = failed.get(e.reason, 0) + 1
            continue
        if n:
            threads.append(n)
        time.sleep(0.15)                       # stay well under Gmail's per-user rate limit
    for reason, n in failed.items():
        print(f"Skipped {n} thread(s): {reason}")
    DATA.mkdir(parents=True, exist_ok=True)
    tmp = GMAIL_OUT.with_suffix(".tmp")
    tmp.write_text(json.dumps({"fetched_at": datetime.now(timezone.utc).isoformat(), "me": me,
                               "query": GMAIL_QUERY, "threads": threads}, ensure_ascii=False))
    tmp.replace(GMAIL_OUT)
    GMAIL_OUT.chmod(0o600)
    print(f"Wrote {len(threads)} recent inbox threads to {GMAIL_OUT}")


def correspondents(me: str) -> list[str]:
    """Whose past correspondence to read: people in the People list (work) and senders of emails that need her."""
    import sqlite3
    path = DATA / "harness.db"
    if not path.exists():
        sys.exit("No harness database yet: start the harness (make up) and run make import first.")
    db = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    rows = db.execute("SELECT lower(email) FROM people WHERE email IS NOT NULL AND space='work' UNION "
                      "SELECT lower(from_email) FROM emails WHERE in_window=1 AND needs_reply=1 AND handled_at IS NULL AND space='work'").fetchall()
    db.close()
    return sorted({r[0] for r in rows if r[0] and r[0] != me.lower()})[:80]


def normalize_correspondence(thread: dict, me: str, addr: str) -> dict | None:
    """One thread -> the messages between her and `addr` (new text only), plus the thread's last-message headers."""
    import re as _re
    msgs, me, addr = [], me.lower(), addr.lower()
    for m in thread.get("messages") or []:
        h = m.get("payload", {}).get("headers", [])
        sender = _parse_from(_header(h, "From"))[1]
        people = (_header(h, "From") + "," + _header(h, "To") + "," + _header(h, "Cc")).lower()
        if addr not in people:
            continue                                                  # a third party's message in a shared thread
        text = strip_quoted(_text_of(m.get("payload", {})))
        msgs.append({"msg_id": m["id"], "ms": int(m.get("internalDate", 0)), "from_me": sender == me, "from_email": sender,
                     "subject": _header(h, "Subject"), "body": text[:BODY_CHARS_CORR], "rfc_id": _header(h, "Message-ID").strip(),
                     "references": _header(h, "References").strip()})
    if not msgs:
        return None
    last = msgs[-1]
    return {"thread_id": thread["id"], "subject": msgs[0]["subject"], "last_ms": last["ms"], "last_from_me": last["from_me"],
            "last_rfc_id": last["rfc_id"], "last_references": last["references"], "messages": msgs}


def sync_correspondence() -> None:
    access = _access_token(GMAIL_TOKEN_ITEM, "login-gmail")
    me = _get(f"{GMAIL_API}/profile", access)["emailAddress"]
    addrs = correspondents(me)
    cache: dict[str, dict] = {}
    import time
    out, failed = {}, 0
    for n, addr in enumerate(addrs, 1):
        try:
            ids = _get(f"{GMAIL_API}/threads", access, {"q": f"from:{addr} OR to:{addr}", "maxResults": str(CORR_THREADS)}).get("threads", [])
        except GoogleError:
            failed += 1
            continue
        threads = []
        for t in ids:
            if t["id"] not in cache:
                try:
                    cache[t["id"]] = _get(f"{GMAIL_API}/threads/{t['id']}", access, {"format": "full"})
                except GoogleError:
                    failed += 1
                    continue
                time.sleep(0.15)
            nt = normalize_correspondence(cache[t["id"]], me, addr)
            if nt:
                threads.append(nt)
        out[addr] = threads
        print(f"  {n}/{len(addrs)} people", end="\r", flush=True)
    DATA.mkdir(parents=True, exist_ok=True)
    tmp = CORR_OUT.with_suffix(".tmp")
    tmp.write_text(json.dumps({"fetched_at": datetime.now(timezone.utc).isoformat(), "me": me, "people": out}, ensure_ascii=False))
    tmp.replace(CORR_OUT)
    CORR_OUT.chmod(0o600)
    n_msgs = sum(len(t["messages"]) for ts in out.values() for t in ts)
    print(f"\nWrote {len(out)} people, {n_msgs} messages to {CORR_OUT}" + (f" ({failed} fetches skipped)" if failed else ""))


EVENT_QUERIES = [
    "from:clubdiplomatique.ch",
    "from:geneve-int.ch",
    "from:(luma-mail.com OR lu.ma)",
    'subject:("registration confirmed" OR "registration approved" OR "registration confirmation" OR "registration pending" OR "you\'re registered" OR "you are registered" OR "thank you for registering" '
    'OR "you\'re confirmed" OR "you are confirmed" OR "seat is confirmed" OR "your registration")',
    'subject:(invitation OR invited OR "save the date" OR "invitation to speak" OR "speaking invitation" OR webinar OR conference OR symposium OR workshop OR summit OR forum OR roundtable '
    'OR reception OR keynote OR panelist OR "open house" OR launch)',
]
EVENT_FIRST_DAYS, EVENT_LATER_DAYS = 400, 21


EVENT_BODY_CHARS = 2500
_KNOWN_PARSED = ("clubdiplomatique.ch", "geneve-int.ch", "luma-mail.com", "lu.ma")      # their emails are read by rules; no body needed


def normalize_event_mail(msg: dict, me: str, with_body: bool = False) -> dict | None:
    """One message -> the few fields the events importer needs. A trimmed plain-text body is kept only for senders the rules cannot read (the local model reads
    those, on this Mac); the Genève internationale tables are parsed here and only their rows are kept."""
    h = msg.get("payload", {}).get("headers", [])
    name, addr = _parse_from(_header(h, "From"))
    if not addr or addr == me.lower():
        return None
    body = " ".join(strip_quoted(_text_of(msg.get("payload", {}))).split())[:EVENT_BODY_CHARS] if with_body and not addr.endswith(_KNOWN_PARSED) else None
    return {**({"body": body} if body else {}), "id": msg["id"], "thread_id": msg.get("threadId", msg["id"]), "date_ms": int(msg.get("internalDate", 0)), "from_email": addr, "from_name": name,
            "subject": _header(h, "Subject"), "snippet": msg.get("snippet", ""), "direct": me.lower() in _header(h, "To").lower(), "labels": msg.get("labelIds", []),
            "bulk": bool(_header(h, "List-Unsubscribe")) or _header(h, "Precedence").lower() in ("bulk", "list", "junk") or _header(h, "Auto-Submitted").lower().startswith("auto-")}


def _html_of(payload: dict) -> str:
    out = []

    def walk(part):
        data = part.get("body", {}).get("data")
        if data and part.get("mimeType") == "text/html":
            out.append(base64.urlsafe_b64decode(data + "=" * (-len(data) % 4)).decode("utf-8", "replace"))
        for sub in part.get("parts", []) or []:
            walk(sub)
    walk(payload)
    return "\n".join(out)


def sync_event_mail() -> None:
    """Event-related mail from the past year (first run) or the last three weeks (later runs). Read-only Gmail. Written to ~/IG-Harness-data/event_mail.json."""
    import time
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from harness.event_parsers import parse_geneve_int                      # pure standard library
    access = _access_token(GMAIL_TOKEN_ITEM, "login-gmail")
    me = _get(f"{GMAIL_API}/profile", access)["emailAddress"]
    old = {}
    try:
        old = {m["id"]: m for m in json.loads(EVENT_OUT.read_text()).get("messages", [])}
    except (OSError, ValueError):
        pass
    days = EVENT_LATER_DAYS if old else EVENT_FIRST_DAYS
    ids: dict[str, None] = {}
    for q in EVENT_QUERIES:
        page = None
        while True:
            params = {"q": f"{q} newer_than:{days}d -in:spam -in:trash", "maxResults": "500"}
            if page:
                params["pageToken"] = page
            body = _get(f"{GMAIL_API}/messages", access, params)
            for m in body.get("messages", []):
                ids[m["id"]] = None
            page = body.get("nextPageToken")
            if not page:
                break
    new_ids = [i for i in ids if i not in old]
    print(f"{len(ids)} matching messages, {len(new_ids)} new")
    failed = 0
    for n, mid in enumerate(new_ids, 1):
        try:
            msg = _get(f"{GMAIL_API}/messages/{mid}", access, {"format": "full"})
            norm = normalize_event_mail(msg, me, with_body=True)
            if norm and norm["from_email"].endswith("geneve-int.ch"):                          # only this newsletter needs its body (HTML tables)
                norm["listing"] = parse_geneve_int(_html_of(msg.get("payload", {})))
        except GoogleError:
            failed += 1
            continue
        if norm:
            old[mid] = norm
        time.sleep(0.1)
        if n % 25 == 0:
            print(f"  {n}/{len(new_ids)}", end="\r", flush=True)
    DATA.mkdir(parents=True, exist_ok=True)
    tmp = EVENT_OUT.with_suffix(".tmp")
    tmp.write_text(json.dumps({"fetched_at": datetime.now(timezone.utc).isoformat(), "me": me, "messages": sorted(old.values(), key=lambda m: m["date_ms"])}, ensure_ascii=False))
    tmp.replace(EVENT_OUT)
    EVENT_OUT.chmod(0o600)
    print(f"\nWrote {len(old)} event-related messages to {EVENT_OUT}" + (f" ({failed} skipped)" if failed else ""))


def backfill_event_bodies() -> None:
    """One-off: add the trimmed body to messages already in event_mail.json (non-bulk first), for the local model to read. Read-only; saves as it goes."""
    import time
    access = _access_token(GMAIL_TOKEN_ITEM, "login-gmail")
    me = _get(f"{GMAIL_API}/profile", access)["emailAddress"]
    data = json.loads(EVENT_OUT.read_text())
    todo = [m for m in data["messages"] if "body" not in m and not m["from_email"].endswith(_KNOWN_PARSED) and "listing" not in m]
    todo.sort(key=lambda m: (m.get("bulk", False), -m["date_ms"]))
    print(f"{len(todo)} messages need a body")
    for n, m in enumerate(todo, 1):
        try:
            full = normalize_event_mail(_get(f"{GMAIL_API}/messages/{m['id']}", access, {"format": "full"}), me, with_body=True)
        except GoogleError:
            continue
        m["body"] = (full or {}).get("body") or ""
        if n % 50 == 0 or n == len(todo):
            tmp = EVENT_OUT.with_suffix(".tmp"); tmp.write_text(json.dumps(data, ensure_ascii=False)); tmp.replace(EVENT_OUT)
            print(f"  {n}/{len(todo)}", end="\r", flush=True)
        time.sleep(0.05)
    print("\nDone.")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "store-client" and len(sys.argv) == 3: store_client(sys.argv[2])
    elif cmd == "login": login()
    elif cmd == "sync": sync()
    elif cmd == "login-gmail": login(GMAIL_SCOPE, GMAIL_TOKEN_ITEM)
    elif cmd == "sync-gmail": sync_gmail()
    elif cmd == "sync-correspondence": sync_correspondence()
    elif cmd == "sync-events": sync_event_mail()
    elif cmd == "backfill-event-bodies": backfill_event_bodies()
    else: sys.exit(__doc__)

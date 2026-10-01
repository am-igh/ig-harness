#!/usr/bin/env python3
"""Mac-side Gmail DRAFT worker. Standard library only. It can create drafts and do nothing else.

It runs on the Mac, outside Docker, because the compose token lives in the macOS Keychain
(`ig-harness-google-gmail-drafts`). Google has no drafts-only permission: the permission that creates
drafts (gmail.compose) also technically allows sending. So the guarantee is ours, in layers:

  1. This file contains no send code. Its only network call is `_transmit`, reachable only through
     `GuardedGmail.request`, which accepts exactly ONE operation (create a draft) and refuses
     everything else by default (an allow-list, not a deny-list).
  2. A draft is created only for a request that Anne-Marie approved in the UI: the worker re-checks the
     approval and the exact text (hash) in the harness database before every call.
  3. tests/test_no_send.py proves all of this, including every send route and common URL tricks.

  python3 tools/draft_worker.py login     one time: approve the compose permission in the browser
  python3 tools/draft_worker.py once      process the outbox now
  python3 tools/draft_worker.py run       keep running (used by the background agent)
"""
import json
import os
import sqlite3
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))
from harness import draftspec                      # noqa: E402  (pure standard library, shared with the API)

DATA = Path(os.environ.get("IG_DATA_DIR", Path.home() / "IG-Harness-data"))
OUTBOX = DATA / "draft_outbox"
DRAFTS_TOKEN_ITEM = "ig-harness-google-gmail-drafts"
COMPOSE_SCOPE = "https://www.googleapis.com/auth/gmail.compose"

GMAIL_HOST = "gmail.googleapis.com"
ALLOWED_OPERATION = ("POST", "/gmail/v1/users/me/drafts")      # create a draft. Nothing else is allowed.
_BODY_KEYS = {"message"}
_MESSAGE_KEYS = {"raw", "threadId"}
_OVERRIDE_HEADERS = {"x-http-method", "x-http-method-override", "x-method-override"}


class ForbiddenOperation(Exception):
    """Raised for anything that is not 'create a draft'. There is no way to catch-and-continue into a send."""


class GuardedGmail:
    """The only door to Gmail in this file."""

    def __init__(self, transport):
        self._transport = transport

    @staticmethod
    def check(method: str, url: str, headers: dict | None, body) -> None:
        if method != ALLOWED_OPERATION[0]:
            raise ForbiddenOperation(f"method {method!r} is not allowed")
        u = urllib.parse.urlparse(url)          # urlparse (not urlsplit) so ';params' are seen too
        if u.scheme != "https" or u.hostname != GMAIL_HOST or u.port not in (None, 443) or u.username or u.password:
            raise ForbiddenOperation("only https://gmail.googleapis.com is allowed")
        if u.query or u.fragment or u.params:
            raise ForbiddenOperation("query strings and fragments are not allowed")
        if u.path != ALLOWED_OPERATION[1]:                         # exact match: no decoding games, no trailing slash
            raise ForbiddenOperation(f"path {u.path!r} is not allowed")
        if {k.lower() for k in (headers or {})} & _OVERRIDE_HEADERS:
            raise ForbiddenOperation("method-override headers are not allowed")
        if not isinstance(body, dict) or set(body) != _BODY_KEYS or not isinstance(body["message"], dict):
            raise ForbiddenOperation("the request body must be exactly {'message': {...}}")
        m = body["message"]
        if "raw" not in m or not set(m) <= _MESSAGE_KEYS or not all(isinstance(v, str) for v in m.values()):
            raise ForbiddenOperation("the message may only contain 'raw' and 'threadId'")

    def request(self, method: str, url: str, headers: dict | None = None, body=None):
        self.check(method, url, headers, body)
        return self._transport(method, url, headers or {}, body)

    def create_draft(self, token: str, raw: str, thread_id: str | None):
        message = {"raw": raw, **({"threadId": thread_id} if thread_id else {})}
        return self.request("POST", f"https://{GMAIL_HOST}{ALLOWED_OPERATION[1]}",
                            {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}, {"message": message})


def _transmit(method: str, url: str, headers: dict, body) -> dict:
    """The single network call in this file. Only GuardedGmail.request reaches it."""
    import google_helper as gh                                      # reuse the TLS context
    req = urllib.request.Request(url, json.dumps(body).encode(), headers, method=method)
    with urllib.request.urlopen(req, timeout=30, context=gh._ssl_context()) as r:
        return json.load(r)


# ---------- approval check (reads the harness database, read-only) ----------

def _db(path: Path | None = None) -> sqlite3.Connection:
    p = path or DATA / "harness.db"
    c = sqlite3.connect(f"file:{p}?mode=ro", uri=True, timeout=10)
    c.row_factory = sqlite3.Row
    return c


class NotApproved(Exception):
    pass


def verify_approval(req: dict, conn: sqlite3.Connection) -> dict:
    """The request file is only a carrier. It is honoured only if the database says Anne-Marie approved exactly
    this text: status 'approved', and the same hash in the file, the database and a fresh computation."""
    if not isinstance(req, dict) or not isinstance(req.get("request_id"), str) or not isinstance(req.get("fields"), dict):
        raise NotApproved("malformed request file")
    rid = req["request_id"]
    fields = draftspec.validate(req["fields"])                       # raises InvalidDraft on anything odd
    h = draftspec.content_hash(fields)
    row = conn.execute("SELECT status, body_hash FROM draft_requests WHERE id = ?", (rid,)).fetchone()
    if row is None or row["status"] != "approved":
        raise NotApproved("this draft was not approved")
    if not (req.get("hash") == h == row["body_hash"]):
        raise NotApproved("the text differs from what was approved")
    return fields


# ---------- processing ----------

def _result(path: Path, rid: str, ok: bool, draft_id: str | None = None, error: str | None = None) -> None:
    path.write_text(json.dumps({"request_id": rid, "ok": ok, "gmail_draft_id": draft_id, "error": error,
                                "at": datetime.now(timezone.utc).isoformat()}))


def process_outbox(outbox: Path, conn: sqlite3.Connection, gmail: GuardedGmail, token_provider) -> dict:
    """Create a Gmail draft for every approved request file. Never anything else."""
    stats = {"created": 0, "refused": 0, "skipped": 0}
    for f in sorted(outbox.glob("*.json")):
        if f.name.endswith(".result.json"):
            continue
        res = f.with_suffix(".result.json")
        if res.exists():                                              # already handled: never create a second draft
            stats["skipped"] += 1
            continue
        try:
            req = json.loads(f.read_text())
            fields = verify_approval(req, conn)
            out = gmail.create_draft(token_provider(), draftspec.to_raw(fields), fields["thread_id"])
            _result(res, req["request_id"], True, out.get("id"))
            stats["created"] += 1
        except (NotApproved, draftspec.InvalidDraft, ForbiddenOperation, json.JSONDecodeError) as e:
            _result(res, f.stem, False, error=f"refused: {e}")
            stats["refused"] += 1
        except Exception as e:                                        # network or Google error: leave it for a retry
            print(f"{f.name}: {type(e).__name__}: {e}", file=sys.stderr)
    return stats


def _token() -> str:
    import google_helper as gh
    return gh._access_token(DRAFTS_TOKEN_ITEM, "login")


def main(argv: list[str]) -> None:
    cmd = argv[1] if len(argv) > 1 else ""
    if cmd == "login":
        import google_helper as gh
        print("Google's screen will say this permission can 'manage drafts and send email'. That is Google's\n"
              "wording for the whole permission. This program only ever creates drafts (see the top of this file\n"
              "and tests/test_no_send.py).")
        gh.login(COMPOSE_SCOPE, DRAFTS_TOKEN_ITEM)
        return
    if cmd in ("once", "run"):
        OUTBOX.mkdir(parents=True, exist_ok=True)
        gmail = GuardedGmail(_transmit)
        while True:
            try:
                (OUTBOX / ".heartbeat").touch()                      # lets the app show "draft agent running"
                stats = process_outbox(OUTBOX, _db(), gmail, _token) if any(OUTBOX.glob("*.json")) else None
                if stats and (stats["created"] or stats["refused"]):
                    print(datetime.now().strftime("%H:%M:%S"), stats, flush=True)
            except Exception as e:
                print(f"worker error: {type(e).__name__}: {e}", file=sys.stderr, flush=True)
            if cmd == "once":
                return
            time.sleep(5)
    sys.exit(__doc__)


if __name__ == "__main__":
    main(sys.argv)

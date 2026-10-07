#!/usr/bin/env python3
"""Mac-side WEB RESEARCH helper. Standard library only. It searches and reads public web pages for the chat box's Research mode, and does nothing else.

It runs on the Mac, outside Docker, so the containers stay offline (like tools/events_helper.py and the draft worker). Layers:
  1. A request is honoured only if the harness database says it was approved (the screened query, her confirmation if the screen warned) and the query's hash matches; the
     hard-block screen (IBAN, AVS number, credentials) is applied again here.
  2. Its only network calls are `Door.search` (the self-hosted SearXNG on 127.0.0.1) and `Door.page` (a public https page). A page is fetched only if its host resolves to public
     addresses only, on the normal port, with every redirect re-checked, robots.txt respected, no cookies, size and time limits, text and html only. Nothing is saved or opened.
  3. tests/test_research.py proves these rules.

  python3 tools/research_helper.py once     process waiting requests now
  python3 tools/research_helper.py run      keep running (the background agent)
"""
import json
import os
import sqlite3
import socket
import ssl
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import urllib.robotparser
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from harness import researchspec as R                    # noqa: E402  (pure standard library, shared with the API)

DATA = Path(os.environ.get("IG_DATA_DIR", Path.home() / "IG-Harness-data"))
OUTBOX = DATA / "research_outbox"
SEARX_URL = os.environ.get("IG_SEARX_URL", "http://127.0.0.1:8888")
UA = "IG-Harness-research/1.0 (personal research assistant, ICT4Peace Foundation)"
MAX_PAGES, MAX_RESULTS, PER_HOST = 5, 10, 2
MAX_BYTES, PAGE_TIMEOUT, TOTAL_SECONDS = 1_500_000, 12, 70
TEXT_TYPES = ("text/html", "text/plain", "application/xhtml+xml")


class Refused(Exception):
    pass


def _ssl() -> ssl.SSLContext:
    ctx = ssl.create_default_context()
    if os.path.exists("/etc/ssl/cert.pem"):
        ctx.load_verify_locations("/etc/ssl/cert.pem")
    return ctx


class _Redirects(urllib.request.HTTPRedirectHandler):
    max_redirections = 3

    def __init__(self, check):
        self.check = check

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        self.check(newurl)                                   # a redirect may not lead anywhere a first request could not
        return super().redirect_request(req, fp, code, msg, headers, newurl)


class Door:
    """The only way this file reaches the network."""

    def __init__(self, opener=None, resolver=None):
        self.resolver = resolver or (lambda host, port: socket.getaddrinfo(host, port, type=socket.SOCK_STREAM))
        self.opener = opener or urllib.request.build_opener(urllib.request.HTTPSHandler(context=_ssl()), _Redirects(self._check), urllib.request.ProxyHandler({}))
        self._plain = urllib.request.build_opener(urllib.request.ProxyHandler({}))      # for the local search engine only
        self.robots: dict[str, urllib.robotparser.RobotFileParser] = {}

    def _check(self, url: str) -> None:
        try:
            R.public_https_url(url, self.resolver)
        except ValueError as e:
            raise Refused(str(e))

    def search(self, query: str) -> list[dict]:
        u = urllib.parse.urlparse(SEARX_URL)
        if u.hostname not in ("127.0.0.1", "localhost"):
            raise Refused("the search engine must be on this Mac")
        url = f"{SEARX_URL}/search?" + urllib.parse.urlencode({"q": query, "format": "json", "safesearch": "0"})
        try:
            with self._plain.open(urllib.request.Request(url, headers={"User-Agent": UA}), timeout=25) as r:
                data = json.load(r)
        except (urllib.error.URLError, OSError, ValueError) as e:
            raise Refused(f"the search engine is not answering ({type(e).__name__}). Is it running? (make searxng-up)")
        out, per = [], {}
        for it in data.get("results", []):
            link = it.get("url") or ""
            host = urllib.parse.urlparse(link).hostname or ""
            if not link.startswith("https://") or per.get(host, 0) >= PER_HOST:
                continue
            per[host] = per.get(host, 0) + 1
            out.append({"title": (it.get("title") or "")[:200], "url": link, "snippet": (it.get("content") or "")[:400]})
            if len(out) >= MAX_RESULTS:
                break
        return out

    def _allowed_by_robots(self, url: str) -> bool:
        u = urllib.parse.urlparse(url)
        host = u.netloc
        if host not in self.robots:
            rp = urllib.robotparser.RobotFileParser()
            try:
                req = urllib.request.Request(f"https://{host}/robots.txt", headers={"User-Agent": UA})
                rp.parse(self.opener.open(req, timeout=8).read(200_000).decode("utf-8", "replace").splitlines())
            except urllib.error.HTTPError as e:
                rp.parse(["User-agent: *", "Disallow: /"] if e.code in (401, 403) else [])
            except Exception:
                rp.parse([])                                  # an unreachable robots.txt on a public page: read it politely (one page, no crawling)
            self.robots[host] = rp
        return self.robots[host].can_fetch(UA, url)

    def page(self, url: str) -> tuple[str, str]:
        """(title, text) of one public page."""
        self._check(url)
        if not self._allowed_by_robots(url):
            raise Refused("robots.txt does not allow this page")
        req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "text/html,text/plain;q=0.9"})
        with self.opener.open(req, timeout=PAGE_TIMEOUT) as r:
            self._check(r.geturl())
            ctype = (r.headers.get("Content-Type") or "").split(";")[0].strip().lower()
            if ctype not in TEXT_TYPES:
                raise Refused(f"not a web page ({ctype or 'unknown type'})")
            raw = r.read(MAX_BYTES)
        return R.extract_text(raw.decode("utf-8", "replace"))


class NotApproved(Exception):
    pass


def verify_request(req: dict, conn: sqlite3.Connection) -> str:
    """The request file is only a carrier: it is honoured if the database holds this id as approved with the same query hash, and the hard-block screen passes."""
    if not isinstance(req, dict) or not isinstance(req.get("id"), str) or not isinstance(req.get("query"), str):
        raise NotApproved("malformed request")
    row = conn.execute("SELECT status, query_hash FROM research_requests WHERE id = ?", (req["id"],)).fetchone()
    if row is None or row["status"] != "approved" or row["query_hash"] != R.query_hash(req["query"]):
        raise NotApproved("this search was not approved")
    sc = R.screen(req["query"])
    if not sc["ok"]:
        raise NotApproved("; ".join(sc["blocked"]))
    return sc["query"]


def research(query: str, door: Door, now=time.monotonic) -> dict:
    t0 = now()
    results = door.search(query)
    pages, skipped = [], []
    for r in results:
        if len(pages) >= MAX_PAGES or now() - t0 > TOTAL_SECONDS:
            break
        try:
            title, text = door.page(r["url"])
        except (Refused, urllib.error.URLError, OSError, ValueError) as e:
            skipped.append({"url": r["url"], "why": str(e)[:100]})
            continue
        if len(text) >= 200:
            pages.append({"url": r["url"], "title": title or r["title"], "text": text, "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds")})
    return {"results": results, "pages": pages, "skipped": skipped}


def _db(path: Path | None = None) -> sqlite3.Connection:
    c = sqlite3.connect(f"file:{path or DATA / 'harness.db'}?mode=ro", uri=True, timeout=10)
    c.row_factory = sqlite3.Row
    return c


def process_outbox(outbox: Path, conn: sqlite3.Connection, door: Door) -> dict:
    stats = {"done": 0, "refused": 0}
    for f in sorted(outbox.glob("*.json")):
        if f.name.endswith(".result.json"):
            continue
        res = f.with_suffix(".result.json")
        if res.exists():
            continue
        try:
            req = json.loads(f.read_text())
            query = verify_request(req, conn)
            body = {"id": req["id"], "ok": True, **research(query, door)}
            stats["done"] += 1
        except (NotApproved, Refused, json.JSONDecodeError) as e:
            body = {"id": f.stem, "ok": False, "error": str(e)[:200]}
            stats["refused"] += 1
        res.write_text(json.dumps(body, ensure_ascii=False))
    return stats


def main(argv: list[str]) -> None:
    cmd = argv[1] if len(argv) > 1 else ""
    if cmd in ("once", "run"):
        OUTBOX.mkdir(parents=True, exist_ok=True)
        door = Door()
        while True:
            try:
                (OUTBOX / ".heartbeat").touch()
                if any(OUTBOX.glob("*.json")):
                    stats = process_outbox(OUTBOX, _db(), door)
                    if stats["done"] or stats["refused"]:
                        print(datetime.now().strftime("%H:%M:%S"), stats, flush=True)
            except Exception as e:
                print(f"research helper error: {type(e).__name__}: {e}", file=sys.stderr, flush=True)
            if cmd == "once":
                return
            time.sleep(2)
    sys.exit(__doc__)


if __name__ == "__main__":
    main(sys.argv)

#!/usr/bin/env python3
"""Mac-side public events fetcher: International Geneva listings. Standard library only. Public pages only (S0 data), no login, no personal data sent.

Politeness rules, enforced here: a short ALLOW-LIST of hosts (anything else is refused, including redirects); robots.txt is read and obeyed; the crawl delay a site asks for
is honoured (at least 3 s between requests to the same host); an honest User-Agent; a few pages once a day. Output: ~/IG-Harness-data/public_events.json, imported by the harness.

  python3 tools/events_helper.py pull       fetch the listings now (the refresh agent does this about once a day)
"""
import json
import os
import ssl
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import urllib.robotparser
from datetime import date, datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from harness import event_parsers as P  # noqa: E402  (pure standard library)

DATA = Path(os.environ.get("IG_DATA_DIR", Path.home() / "IG-Harness-data"))
OUT = DATA / "public_events.json"
UA = "IGHarness/1.0 (personal calendar helper; low frequency)"
ALLOWED_HOSTS = {"www.geneve-int.ch", "www.clubdiplomatique.ch", "www.ungeneva.org"}
MIN_DELAY = 3.0
MAX_BYTES = 5_000_000

SOURCES = [
    {"name": "geneve-int", "url": "https://www.geneve-int.ch/calendar", "pages": 5, "pager": "?page={n}"},
    {"name": "club", "url": "https://www.clubdiplomatique.ch/evenements/", "pages": 1},
    {"name": "unog", "url": "https://www.ungeneva.org/en/news-media/calendar-major-meetings", "pages": 1},
]


class Refused(Exception):
    pass


def _opener() -> urllib.request.OpenerDirector:
    """Verify HTTPS against the Mac's own certificate list (python.org builds ship none), like tools/google_helper.py."""
    ctx = ssl.create_default_context()
    if os.path.exists("/etc/ssl/cert.pem"):
        ctx.load_verify_locations("/etc/ssl/cert.pem")
    return urllib.request.build_opener(urllib.request.HTTPSHandler(context=ctx))


class Fetcher:
    def __init__(self, opener=None, sleep=time.sleep, now=time.monotonic):
        self.opener, self.sleep, self.now = opener or _opener(), sleep, now
        self.robots: dict[str, urllib.robotparser.RobotFileParser] = {}
        self.robots_error: dict[str, str] = {}
        self.last: dict[str, float] = {}

    def _check(self, url: str) -> str:
        host = urllib.parse.urlparse(url).netloc
        if urllib.parse.urlparse(url).scheme != "https" or host not in ALLOWED_HOSTS:
            raise Refused(f"{host or url} is not on the allow-list")
        return host

    def _wait(self, host: str, delay: float) -> None:
        gap = self.now() - self.last.get(host, -1e9)
        if gap < delay:
            self.sleep(delay - gap)
        self.last[host] = self.now()

    def _rp(self, host: str) -> urllib.robotparser.RobotFileParser:
        if host not in self.robots:
            rp = urllib.robotparser.RobotFileParser()
            try:
                self._wait(host, MIN_DELAY)
                req = urllib.request.Request(f"https://{host}/robots.txt", headers={"User-Agent": UA})
                rp.parse(self.opener.open(req, timeout=20).read().decode("utf-8", "replace").splitlines())
            except urllib.error.HTTPError as e:
                rp.parse(["User-agent: *", "Disallow: /"] if e.code in (401, 403) else [])         # 404 = no rules; 401/403 = keep out
            except Exception as e:
                self.robots_error[host] = f"{type(e).__name__}: {str(e)[:80]}"
                rp.parse(["User-agent: *", "Disallow: /"])                                          # cannot read the rules: do not fetch
            self.robots[host] = rp
        return self.robots[host]

    def get(self, url: str) -> str:
        host = self._check(url)
        rp = self._rp(host)
        if not rp.can_fetch(UA, url):
            raise Refused(f"could not read robots.txt ({self.robots_error[host]}), so nothing was fetched" if host in self.robots_error else "robots.txt does not allow this page")
        self._wait(host, max(MIN_DELAY, float(rp.crawl_delay(UA) or 0)))
        req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "text/html"})
        with self.opener.open(req, timeout=30) as r:
            self._check(r.geturl())                                                                  # a redirect must stay on the allow-list too
            return r.read(MAX_BYTES).decode("utf-8", "replace")


def _parse(name: str, html: str) -> list[dict]:
    if name == "geneve-int":
        return P.parse_geneve_int_web(html)
    if name == "club":
        return P.parse_club_events(html)
    return P.parse_unog(html, date.today().year)


def pull(out: Path = OUT, fetcher: Fetcher | None = None, sources=SOURCES) -> str:
    f = fetcher or Fetcher()
    doc = {"fetched_at": datetime.now(timezone.utc).isoformat(), "sources": {}}
    total = 0
    for s in sources:
        events, err, seen = [], None, set()
        try:
            for n in range(s["pages"]):
                url = s["url"] + (s["pager"].format(n=n) if n and s.get("pager") else "")
                page = _parse(s["name"], f.get(url))
                fresh = [e for e in page if (e["title"], e["start"]) not in seen]
                seen.update((e["title"], e["start"]) for e in fresh)
                events += fresh
                if not fresh:
                    break
        except Refused as e:
            err = f"refused: {e}"
        except Exception as e:
            err = f"{type(e).__name__}: {str(e)[:100]}"
        doc["sources"][s["name"]] = {"url": s["url"], "error": err, "events": events}
        total += len(events)
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix(".tmp")
    tmp.write_text(json.dumps(doc, ensure_ascii=False))
    tmp.replace(out)
    bad = [f"{k}: {v['error']}" for k, v in doc["sources"].items() if v["error"]]
    return f"{total} events from {len(doc['sources']) - len(bad)} of {len(doc['sources'])} sources" + (f" ({'; '.join(bad)})" if bad else "")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "pull":
        msg = pull()
        print(msg)
        sys.exit(0 if " 0 of " not in msg and not msg.startswith("0 events") else 1)
    sys.exit(__doc__)

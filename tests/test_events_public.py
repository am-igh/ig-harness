"""The polite public-pages fetcher and the importer. No real network: a fake opener serves canned pages."""
import io
import json
import sys
import urllib.error
from datetime import date
from pathlib import Path

import pytest

from harness import db, events as E
from harness.importers.public_events import import_public_events

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
import events_helper as H  # noqa: E402
from test_event_parsers import CLUB_WEB, GI_WEB, UNOG  # noqa: E402


class Resp(io.BytesIO):
    def __init__(self, body, url):
        super().__init__(body.encode()); self.url = url

    def geturl(self):
        return self.url

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class FakeOpener:
    def __init__(self, pages, robots=None, redirect=None):
        self.pages, self.robots, self.redirect, self.fetched = pages, robots or {}, redirect or {}, []

    def open(self, req, timeout=0):
        url = req.full_url
        self.fetched.append((url, req.headers.get("User-agent")))
        if url.endswith("/robots.txt"):
            host = url.split("/")[2]
            if host in self.robots and self.robots[host] is None:
                raise urllib.error.HTTPError(url, 404, "nf", {}, None)
            return Resp(self.robots.get(host, "User-agent: *\nAllow: /\n"), url)
        return Resp(self.pages[url], self.redirect.get(url, url))


def fetcher(pages, **kw):
    sleeps = []
    f = H.Fetcher(opener=FakeOpener(pages, **kw), sleep=sleeps.append, now=lambda: 0.0)
    f.sleeps = sleeps
    return f


PAGES = {"https://www.geneve-int.ch/calendar": GI_WEB, "https://www.clubdiplomatique.ch/evenements/": CLUB_WEB, "https://www.ungeneva.org/en/news-media/calendar-major-meetings": UNOG}


def test_pull_reads_the_three_sources_with_an_honest_user_agent_and_writes_a_private_file(tmp_path):
    f = fetcher(PAGES)
    out = tmp_path / "public_events.json"
    msg = H.pull(out, f, [s | {"pages": 1} for s in H.SOURCES])
    doc = json.loads(out.read_text())
    assert msg.startswith("7 events from 3 of 3 sources") and set(doc["sources"]) == {"geneve-int", "club", "unog"}
    assert all(ua == H.UA for _, ua in f.opener.fetched) and "personal calendar helper" in H.UA


def test_hosts_off_the_allow_list_are_refused_and_so_are_redirects_away(tmp_path):
    f = fetcher({})
    with pytest.raises(H.Refused):
        f.get("https://evil.example.com/x")
    with pytest.raises(H.Refused):
        f.get("http://www.geneve-int.ch/calendar")                                         # https only
    f2 = fetcher({"https://www.geneve-int.ch/calendar": "x"}, redirect={"https://www.geneve-int.ch/calendar": "https://elsewhere.com/y"})
    with pytest.raises(H.Refused):
        f2.get("https://www.geneve-int.ch/calendar")
    out = tmp_path / "o.json"
    msg = H.pull(out, f2, [{"name": "geneve-int", "url": "https://www.geneve-int.ch/calendar", "pages": 1}])
    assert "refused" in msg and json.loads(out.read_text())["sources"]["geneve-int"]["error"].startswith("refused")


def test_robots_txt_is_obeyed_and_a_crawl_delay_is_honoured():
    f = fetcher(PAGES, robots={"www.geneve-int.ch": "User-agent: *\nDisallow: /calendar\n", "www.clubdiplomatique.ch": "User-agent: *\nCrawl-delay: 10\n"})
    with pytest.raises(H.Refused, match="robots"):
        f.get("https://www.geneve-int.ch/calendar")
    f.get("https://www.clubdiplomatique.ch/evenements/")
    f2 = fetcher(PAGES, robots={"www.clubdiplomatique.ch": "User-agent: *\nCrawl-delay: 10\n"})
    f2.now = iter([0.0] * 40).__next__
    f2.get("https://www.clubdiplomatique.ch/evenements/")
    assert any(s >= 10 for s in f2.sleeps)


def test_an_unreadable_robots_file_means_do_not_fetch_and_one_failing_source_does_not_stop_the_others(tmp_path):
    class Broken(FakeOpener):
        def open(self, req, timeout=0):
            if "geneve-int" in req.full_url:
                raise OSError("network down")
            return super().open(req, timeout)
    f = H.Fetcher(opener=Broken(PAGES), sleep=lambda s: None, now=lambda: 0.0)
    out = tmp_path / "o.json"
    msg = H.pull(out, f, [s | {"pages": 1} for s in H.SOURCES])
    doc = json.loads(out.read_text())["sources"]
    assert doc["geneve-int"]["error"] and doc["club"]["events"] and doc["unog"]["events"] and "2 of 3" in msg


def test_pagination_stops_when_a_page_adds_nothing_new(tmp_path):
    pages = {"https://www.geneve-int.ch/calendar": GI_WEB, "https://www.geneve-int.ch/calendar?page=1": GI_WEB}
    f = fetcher(pages)
    out = tmp_path / "o.json"
    H.pull(out, f, [{"name": "geneve-int", "url": "https://www.geneve-int.ch/calendar", "pages": 5, "pager": "?page={n}"}])
    assert len([u for u, _ in f.opener.fetched if "page=" in u or u.endswith("/calendar")]) == 2          # page 0, then page 1 (all repeats), then it stops


def test_helper_source_never_posts_or_sends_anything():
    src = Path(H.__file__).read_text()
    assert "POST" not in src and "data=" not in src and "urlencode" not in src.replace("urllib.parse.urlparse", "")


# ------------------------------------------------------------------ the importer
@pytest.fixture
def c(tmp_path):
    c = db.connect(tmp_path / "t.db"); db.migrate(c)
    return c


def write(folder, sources):
    (folder / "public_events.json").write_text(json.dumps({"fetched_at": "2026-10-04T08:00:00+00:00", "sources": sources}))


def test_public_listings_become_s0_events_with_relevance_and_merge_with_emails(c, tmp_path):
    write(tmp_path, {
        "club": {"url": "u", "error": None, "events": [{"title": "Anticipatory Leadership Lab with GESDA", "start": "2026-09-17", "end": None, "organizer": "Club Diplomatique de Genève", "venue": "Campus Biotech", "url": "https://club/alab/"}]},
        "geneve-int": {"url": "u", "error": None, "events": [{"title": "AI Governance Day", "start": "2026-10-20", "end": "2026-10-21", "organizer": "ITU", "venue": "Online", "url": "https://itu/ai"},
                                                              {"title": "Meeting on DDT", "start": "2026-10-20", "end": "2026-10-20", "organizer": "Basel", "venue": "Geneva", "url": None}]},
        "unog": {"url": "u", "error": "refused: robots.txt does not allow this page", "events": []}})
    r = import_public_events(c, tmp_path)[0]
    assert r.added == 3 and "unog: refused" in r.notes[0]
    ev = {e["title"]: e for e in c.execute("SELECT * FROM events")}
    assert all(e["tier"] == "S0" and e["geneva"] == 1 for e in ev.values())
    assert (ev["Anticipatory Leadership Lab with GESDA"]["relevant"], ev["AI Governance Day"]["relevant"], ev["Meeting on DDT"]["relevant"]) == (1, 1, 0)
    assert (ev["AI Governance Day"]["start"], ev["AI Governance Day"]["end"], ev["AI Governance Day"]["online"]) == ("2026-10-20", "2026-10-22", 1)
    assert import_public_events(c, tmp_path)[0].added == 0 and c.execute("SELECT COUNT(*) FROM events").fetchone()[0] == 3        # idempotent
    # the invitation email arrives later: same event, now with a time, and the status becomes 'invited'
    from harness.importers.event_mail import import_event_mail
    (tmp_path / "event_mail.json").write_text(json.dumps({"me": "me@x.org", "messages": [{"id": "m1", "thread_id": "t1", "date_ms": 1789000000000, "from_email": "secretariat@clubdiplomatique.ch",
        "subject": "📨 Invitation | Anticipatory Leadership Lab with GESDA, 17 September 2026 at 16:30", "snippet": ""}]}))
    import_event_mail(c, tmp_path)
    row = c.execute("SELECT * FROM events WHERE title LIKE 'Anticipatory%'").fetchone()
    assert c.execute("SELECT COUNT(*) FROM events").fetchone()[0] == 3
    assert (row["derived_status"], row["start"], row["all_day"]) == ("invited", "2026-09-17T16:30:00+02:00", 0)
    assert sorted(x["kind"] for x in c.execute("SELECT kind FROM event_evidence WHERE event_id=?", (row["id"],))) == ["email-club", "listing-web-club"]


def test_a_missing_file_is_a_note(c, tmp_path):
    assert "events_helper" in import_public_events(c, tmp_path)[0].notes[0]

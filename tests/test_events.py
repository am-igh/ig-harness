"""Geneva and beyond, slice 5.1: events from the calendar, statuses, topics, clashes, archive, her overrides. Synthetic data only."""
from datetime import date

import pytest

from harness import db, events as E

TODAY = date(2026, 10, 2)


@pytest.fixture
def c(tmp_path):
    c = db.connect(tmp_path / "t.db"); db.migrate(c)
    return c


def cal(c, ref, title, start, end=None, all_day=0, resp=None, loc=None, link=None, self_org=0, att=0, status="confirmed", space="work"):
    c.execute("INSERT INTO calendar_events (title, start, end, all_day, status, space, source, source_ref, my_response, location, link, self_organizer, attendee_count) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
              (title, start, end, all_day, status, space, "google", ref, resp, loc, link, self_org, att))
    c.commit()


@pytest.mark.parametrize("title,loc,self_org,att,expected", [
    ("GESDA - The Anticipation Summit 2026", None, 0, 12, True),
    ("Digital International Geneva - Monthly Thematic Session", None, 0, 3, True),
    ("GPF panel (moderating): AI for Peace", None, 1, 0, True),
    ("Pall Mall Proces", "Paris", 0, 0, True),                                  # no keyword, but an invitation with a place
    ("Wilton Park WP3872: Human rights", "Wilton Park", 0, 2, True),
    ("Focus: Swiss taxes", None, 1, 0, False),
    ("Travel booking: Loire - choose option", None, 1, 0, False),
    ("D-3: IASEAI'27 workshop proposal due", None, 1, 0, False),                # a reminder to herself, even though it says workshop
    ("Coordination call | IG-CSC", None, 0, 6, False),
    ("Meeting with Michael Keating", "Geneva", 0, 2, False),
    ("Bi-weekly call founding members", None, 0, 5, False),
    ("Ann-Marie", None, 1, 0, False),
    ("Breakfast with Ines", "Geneva", 0, 2, False),
])
def test_what_counts_as_an_event(title, loc, self_org, att, expected):
    assert E.looks_like_event(title, loc, bool(self_org), att) is expected


def test_topics_geneva_and_roles_are_found_by_keywords():
    assert E.topics_of("AI for Good: disinformation and hate speech panel in Geneva") == "digital & AI,harmful information,tech for good"
    assert E.topics_of("Cyber peace dialogue") == "cyber,peacebuilding"
    assert E.topics_of("Lunch") is None
    assert E.role_of("GPF panel (moderating): AI") == "moderator" and E.role_of("Workshop (co-facilitating)") == "facilitator" and E.role_of("Judging Session") == "judge"
    assert E.role_of("Annual summit") is None


def test_status_comes_from_her_calendar_response():
    d = E.derive_status
    assert d("accepted", False, 3, None) == "confirmed" and d("tentative", False, 3, None) == "tentative" and d("needsAction", False, 3, None) == "invited"
    assert d("declined", False, 3, None) == "declined" and d(None, False, 0, None) == "none"
    assert d("accepted", True, 0, None) == "confirmed" and d(None, True, 0, "moderator") == "confirmed"      # something she put on her own calendar


def test_sync_creates_events_with_evidence_and_leaves_ordinary_meetings_out(c):
    cal(c, "a", "GESDA - The Anticipation Summit 2026", "2026-10-14", "2026-10-16", all_day=1, resp="accepted", loc="Palexpo, Geneva", att=9)
    cal(c, "b", "Coordination call | IG-CSC", "2026-10-14T10:00:00+02:00", "2026-10-14T11:00:00+02:00", resp="accepted", att=4)
    cal(c, "c", "Pall Mall Proces", "2026-11-10", "2026-11-12", all_day=1, resp="needsAction", loc="Paris", att=20)
    cal(c, "d", "Private event", "2026-10-20", all_day=1, resp="accepted", space="personal", loc="Home")
    r = E.sync_calendar(c)
    assert r == {"added": 2, "updated": 0}
    got = {x["title"]: x for x in c.execute("SELECT * FROM events")}
    assert set(got) == {"GESDA - The Anticipation Summit 2026", "Pall Mall Proces"}
    g = got["GESDA - The Anticipation Summit 2026"]
    assert (g["derived_status"], g["geneva"], g["topics"], g["source_kind"], g["tier"]) == ("confirmed", 1, "multilateral diplomacy", "calendar", "S2")
    assert got["Pall Mall Proces"]["derived_status"] == "invited"
    ev = c.execute("SELECT kind, signal FROM event_evidence WHERE event_id=?", (g["id"],)).fetchall()
    assert [tuple(x) for x in ev] == [("calendar", "accepted")]
    assert E.sync_calendar(c) == {"added": 0, "updated": 2}


def test_a_cancelled_or_vanished_calendar_entry_removes_the_event_and_her_override_survives_resync(c):
    cal(c, "a", "Open Government Forum", "2026-10-20T09:00:00+02:00", "2026-10-20T17:00:00+02:00", resp="needsAction", loc="Geneva", att=5)
    E.sync_calendar(c)
    eid = c.execute("SELECT id FROM events").fetchone()[0]
    assert E.set_status(c, eid, "confirmed")
    cal_changed = c.execute("UPDATE calendar_events SET my_response='declined'"); c.commit()
    E.sync_calendar(c)
    row = c.execute("SELECT derived_status, user_status FROM events").fetchone()
    assert (row["derived_status"], row["user_status"]) == ("declined", "confirmed")                       # her word beats the calendar
    assert E.list_events(c, TODAY)["items"][0]["status"] == "confirmed" and E.list_events(c, TODAY)["items"][0]["overridden"]
    c.execute("UPDATE calendar_events SET status='cancelled'"); c.commit()
    E.sync_calendar(c)
    assert c.execute("SELECT COUNT(*) FROM events").fetchone()[0] == 0


def test_upcoming_versus_archive_filters_and_search(c):
    cal(c, "p", "Old Forum", "2026-05-04", "2026-05-09", all_day=1, resp="accepted", loc="Geneva")
    cal(c, "u1", "Disinformation workshop", "2026-10-09T09:00:00+02:00", "2026-10-09T12:00:00+02:00", resp="accepted", loc="Geneva", att=3)
    cal(c, "u2", "Cyber Symposium", "2026-11-01", "2026-11-02", all_day=1, resp="needsAction", loc="Paris", att=3)
    cal(c, "run", "Long Summit", "2026-09-30", "2026-10-04", all_day=1, resp="accepted", loc="Berlin", att=3)       # still running today
    E.sync_calendar(c)
    up = E.list_events(c, TODAY)
    assert [i["title"] for i in up["items"]] == ["Long Summit", "Disinformation workshop", "Cyber Symposium"]
    assert [i["title"] for i in E.list_events(c, TODAY, "archive")["items"]] == ["Old Forum"]
    assert [i["title"] for i in E.list_events(c, TODAY, status="confirmed")["items"]] == ["Long Summit", "Disinformation workshop"]
    assert [i["title"] for i in E.list_events(c, TODAY, geneva=True)["items"]] == ["Disinformation workshop"]
    assert [i["title"] for i in E.list_events(c, TODAY, topic="harmful information")["items"]] == ["Disinformation workshop"]
    assert [i["title"] for i in E.list_events(c, TODAY, "archive", q="old")["items"]] == ["Old Forum"] and E.list_events(c, TODAY, q="paris")["total"] == 1
    assert up["counts"] == {"confirmed": 2, "tentative": 0, "invited": 1, "interested": 0}


def test_clashes_between_confirmed_events_only(c):
    cal(c, "a", "Panel one", "2026-10-09T09:00:00+02:00", "2026-10-09T11:00:00+02:00", resp="accepted", loc="X", att=2)
    cal(c, "b", "Panel two", "2026-10-09T10:30:00+02:00", "2026-10-09T12:00:00+02:00", resp="accepted", loc="Y", att=2)
    cal(c, "c", "Panel three", "2026-10-09T10:30:00+02:00", "2026-10-09T12:00:00+02:00", resp="needsAction", loc="Z", att=2)          # only invited: no clash
    cal(c, "d", "Panel four", "2026-10-09T11:00:00+02:00", "2026-10-09T12:00:00+02:00", resp="tentative", loc="W", att=2)
    E.sync_calendar(c)
    items = {i["title"]: i for i in E.list_events(c, TODAY)["items"]}
    a, b, d = (items[k]["id"] for k in ("Panel one", "Panel two", "Panel four"))
    assert set(items["Panel one"]["clashes"]) == {b} and set(items["Panel two"]["clashes"]) == {a, d} and items["Panel three"]["clashes"] == []


def test_hide_and_force_overrides(c):
    cal(c, "a", "Annual Summit", "2026-10-20", "2026-10-21", all_day=1, resp="accepted", loc="X", att=2)
    E.sync_calendar(c)
    eid = c.execute("SELECT id FROM events").fetchone()[0]
    assert E.hide(c, eid) and E.list_events(c, TODAY)["total"] == 0
    E.sync_calendar(c)
    assert c.execute("SELECT hidden FROM events").fetchone()[0] == 1                                       # stays hidden after a resync
    assert E.hide(c, eid, False) and E.list_events(c, TODAY)["total"] == 1
    with pytest.raises(ValueError):
        E.set_status(c, eid, "maybe")


def test_api(c):
    from fastapi.testclient import TestClient
    from harness.main import app
    with TestClient(app) as cl:
        r = cl.get("/api/events").json()
        assert {"items", "total", "counts", "topics"} <= set(r)
        assert cl.get("/api/events?scope=nope").status_code == 422 and cl.get("/api/events/999999").status_code == 404
        assert cl.post("/api/events/999999/status", json={"status": "confirmed"}).status_code == 404
        assert cl.post("/api/events/999999/status", json={"status": "maybe"}).status_code == 422

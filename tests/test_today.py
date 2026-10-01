from datetime import datetime

import pytest
from fastapi.testclient import TestClient

from harness import db
from harness.config import TZ
from harness.deadlines import done_this_week, mark_done, mark_undone
from harness.today import build_today, deadline_detail

NOW = datetime(2026, 10, 1, 9, 30, tzinfo=TZ)   # Thursday


@pytest.fixture
def conn(tmp_path):
    c = db.connect(tmp_path / "t.db")
    db.migrate(c)
    return c


def add_task(c, title, due, code=None, **kw):
    c.execute("INSERT INTO tasks (title, due_date, project_code) VALUES (?,?,?)", (title, due, code))


def test_today_list_has_overdue_today_and_excludes_future_and_undated(conn):
    add_task(conn, "overdue", "2026-09-25")
    add_task(conn, "due today", "2026-10-01")
    add_task(conn, "next week", "2026-10-06")
    add_task(conn, "far", "2026-12-01")
    add_task(conn, "undated", None)
    t = build_today(conn, NOW)
    assert [i["title"] for i in t["today_items"]] == ["overdue", "due today"]
    assert t["today_items"][0]["days_overdue"] == 6
    assert [i["title"] for i in t["upcoming_items"]] == ["next week"]
    assert t["undated_tasks"] == 1


def test_waiting_on_appears_when_chase_date_arrives(conn):
    conn.execute("INSERT INTO waiting_on (description, person, since_date, remind_on) VALUES ('draft','Partner','2026-09-01','2026-10-01')")
    conn.execute("INSERT INTO waiting_on (description, person, since_date, remind_on) VALUES ('later','P','2026-09-01','2026-10-20')")
    items = build_today(conn, NOW)["today_items"]
    assert [(i["title"], i["weight"], i["person"]) for i in items] == [("draft", "waiting", "Partner")]


def test_tick_persists_counts_for_jet_and_stays_visible_today(conn):
    add_task(conn, "A", "2026-10-01")
    assert mark_done(conn, "task", 1, NOW)
    t = build_today(conn, NOW)
    assert t["done_this_week"] == 1
    assert t["today_items"][0]["done"] is True       # stays in list, struck through
    assert mark_undone(conn, "task", 1)
    t = build_today(conn, NOW)
    assert t["done_this_week"] == 0 and t["today_items"][0]["done"] is False
    assert mark_undone(conn, "task", 1) is False


def test_done_earlier_in_the_week_counts_but_is_not_in_todays_list(conn):
    add_task(conn, "Monday job", "2026-09-28")
    mark_done(conn, "task", 1, datetime(2026, 9, 28, 10, 0, tzinfo=TZ))
    t = build_today(conn, NOW)
    assert t["done_this_week"] == 1 and t["today_items"] == []


def test_lake_marks_and_warning_ticks(conn):
    conn.execute("INSERT INTO deadlines (title, due_date, importance, project_code) VALUES ('Soon','2026-10-05','major','X')")
    conn.execute("INSERT INTO deadlines (title, due_date) VALUES ('Beyond lake','2026-12-31')")
    conn.execute("INSERT INTO deadlines (title, due_date) VALUES ('Overdue','2026-09-01')")
    t = build_today(conn, NOW)
    assert [m["title"] for m in t["lake"]] == ["Soon"]
    assert t["lake"][0]["warning"] == "D-14"
    assert t["ticks"] == ["2026-10-02"]                # D-3 is ahead; D-14 already passed


def test_calendar_today_and_next_event(conn):
    ins = "INSERT INTO calendar_events (title,start,end,all_day,source,source_ref) VALUES (?,?,?,?, 'gcal', ?)"
    conn.execute(ins, ("Morning", "2026-10-01T08:00:00+02:00", None, 0, "a"))
    conn.execute(ins, ("Afternoon", "2026-10-01T15:00:00+02:00", None, 0, "b"))
    conn.execute(ins, ("Tomorrow", "2026-10-02T09:00:00+02:00", None, 0, "c"))
    conn.execute(ins, ("Holiday", "2026-09-30", "2026-10-02", 1, "d"))
    t = build_today(conn, NOW)
    assert [e["title"] for e in t["events_today"]] == ["Holiday", "Morning", "Afternoon"]
    assert t["next_event"]["title"] == "Afternoon"


def test_deadline_detail_related_items(conn):
    conn.execute("INSERT INTO deadlines (title, due_date, project_code) VALUES ('Report','2026-10-15','GPF')")
    add_task(conn, "Run of show", "2026-10-01", "GPF")
    add_task(conn, "Other project", "2026-10-01", "ZZZ")
    d = deadline_detail(conn, 1, NOW.date())
    assert d["days_left"] == 14 and d["warn_d14"] == "2026-10-01" and d["warn_d3"] == "2026-10-12"
    assert [r["label"] for r in d["related"]] == ["Run of show"]
    assert deadline_detail(conn, 99, NOW.date()) is None


def test_api_endpoints_roundtrip():
    from harness.main import app
    with TestClient(app) as c:           # lifespan creates the throwaway test database
        conn = db.connect()
        conn.execute("INSERT INTO tasks (title, due_date) VALUES ('API task','2000-01-01')")
        conn.commit(); conn.close()
        today = c.get("/api/today").json()
        item = next(i for i in today["today_items"] if i["title"] == "API task")
        assert c.post(f"/api/items/{item['type']}/{item['id']}/done").json() == {"changed": True}
        assert c.get("/api/today").json()["done_this_week"] >= 1
        assert c.post(f"/api/items/{item['type']}/{item['id']}/undo").json() == {"changed": True}
        assert c.post("/api/items/bogus/1/done").status_code == 404
        assert c.get("/api/deadlines/9999").status_code == 404

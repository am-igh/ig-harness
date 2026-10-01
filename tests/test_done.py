"""Done record: timestamps, emails marked handled, task<->email sync, reopen, and what the lists show."""
import json
from datetime import datetime

import pytest

from harness import db
from harness.config import TZ
from harness.deadlines import done_this_week, mark_done, mark_undone
from harness.importers.gmail import import_gmail
from harness.today import build_today, done_list
from harness.triage import add_to_today, list_emails

NOW = datetime(2026, 10, 1, 14, 32, 5, tzinfo=TZ)
MS = lambda h: int((NOW.timestamp() - h * 3600) * 1000)


def thread(id, msg=None):
    return {"thread_id": id, "message_id": msg or f"m-{id}", "messages_in_thread": 1, "received_ms": MS(2), "from_name": "A",
            "from_email": f"{id}@x.org", "to_me_directly": True, "cc_only": False, "subject": f"Subject {id}", "snippet": "s",
            "body": "b", "labels": [], "last_from_me": False, "bulk": False}


@pytest.fixture
def conn(tmp_path):
    c = db.connect(tmp_path / "t.db"); db.migrate(c)
    (tmp_path / "gmail_recent.json").write_text(json.dumps({"fetched_at": "x", "me": "me@x.org", "query": "q", "threads": [thread("t1"), thread("t2")]}))
    import_gmail(c, tmp_path)
    c.execute("UPDATE emails SET triage_status='done', needs_reply=1, score=5, action='reply', why='asks'")
    c.commit()
    return c


@pytest.fixture
def folder(tmp_path):
    return tmp_path


def eid(c, t): return c.execute("SELECT id FROM emails WHERE thread_id=?", (t,)).fetchone()[0]


def test_done_records_date_and_time_and_is_listed_newest_first(conn):
    conn.execute("INSERT INTO tasks (title, due_date) VALUES ('Early', '2026-10-01')"); conn.execute("INSERT INTO tasks (title, due_date) VALUES ('Late', '2026-10-01')")
    mark_done(conn, "task", 1, datetime(2026, 10, 1, 9, 5, 0, tzinfo=TZ)); mark_done(conn, "task", 2, NOW)
    items = done_list(conn, NOW.date(), 7)
    assert [(i["title"], i["done_at"]) for i in items] == [("Late", "2026-10-01 14:32:05"), ("Early", "2026-10-01 09:05:00")]
    assert all(i["reopenable"] for i in items)


def test_search_and_period_filters(conn):
    conn.execute("INSERT INTO tasks (title) VALUES ('Budget note')"); conn.execute("INSERT INTO tasks (title) VALUES ('Old thing')")
    mark_done(conn, "task", 1, NOW); mark_done(conn, "task", 2, datetime(2026, 8, 1, 10, 0, tzinfo=TZ))
    assert [i["title"] for i in done_list(conn, NOW.date(), 7)] == ["Budget note"]
    assert len(done_list(conn, NOW.date(), None)) == 2
    assert [i["title"] for i in done_list(conn, NOW.date(), None, "old")] == ["Old thing"]


def test_marking_an_email_done_removes_it_from_the_list_and_logs_it_once(conn):
    e1 = eid(conn, "t1")
    assert {e["id"] for e in list_emails(conn, 72, now=NOW)["needs_reply"]} == {e1, eid(conn, "t2")}
    assert mark_done(conn, "email", e1, NOW) is True
    assert mark_done(conn, "email", e1, NOW) is False                       # no double counting
    assert [e["id"] for e in list_emails(conn, 72, now=NOW)["needs_reply"]] == [eid(conn, "t2")]
    full = list_emails(conn, 72, now=NOW, include_skipped=True)
    assert [e["id"] for e in full["handled"]] == [e1] and full["handled"][0]["handled_at"] == "2026-10-01 14:32:05"
    assert done_this_week(conn, NOW.date()) == 1
    assert [(i["type"], i["title"]) for i in done_list(conn, NOW.date(), 7)] == [("email", "Subject t1")]


def test_reopening_an_email_brings_it_back_and_clears_the_record(conn):
    e1 = eid(conn, "t1"); mark_done(conn, "email", e1, NOW)
    assert mark_undone(conn, "email", e1) is True and mark_undone(conn, "email", e1) is False
    assert e1 in {e["id"] for e in list_emails(conn, 72, now=NOW)["needs_reply"]}
    assert done_list(conn, NOW.date(), 7) == [] and done_this_week(conn, NOW.date()) == 0


def test_ticking_the_task_made_from_an_email_handles_the_email_with_one_record(conn):
    e1 = eid(conn, "t1"); tid = add_to_today(conn, e1, NOW)["task_id"]
    assert mark_done(conn, "task", tid, NOW)
    assert conn.execute("SELECT handled_at FROM emails WHERE id=?", (e1,)).fetchone()[0] is not None
    assert done_this_week(conn, NOW.date()) == 1
    assert [i["type"] for i in done_list(conn, NOW.date(), 7)] == ["task"]
    assert e1 not in {e["id"] for e in list_emails(conn, 72, now=NOW)["needs_reply"]}
    assert mark_undone(conn, "task", tid)                                       # untick: both come back
    assert e1 in {e["id"] for e in list_emails(conn, 72, now=NOW)["needs_reply"]}


def test_marking_the_email_done_closes_its_open_task_once(conn):
    e1 = eid(conn, "t1"); tid = add_to_today(conn, e1, NOW)["task_id"]
    assert mark_done(conn, "email", e1, NOW)
    assert conn.execute("SELECT status FROM tasks WHERE id=?", (tid,)).fetchone()[0] == "done"
    assert done_this_week(conn, NOW.date()) == 1                                # one record, not two
    assert mark_undone(conn, "email", e1)
    assert conn.execute("SELECT status FROM tasks WHERE id=?", (tid,)).fetchone()[0] == "open" and done_this_week(conn, NOW.date()) == 0


def test_a_new_message_in_a_handled_thread_brings_it_back(conn, folder):
    e1 = eid(conn, "t1"); mark_done(conn, "email", e1, NOW)
    (folder / "gmail_recent.json").write_text(json.dumps({"fetched_at": "x", "me": "me@x.org", "query": "q",
                                                            "threads": [thread("t1", msg="m-new"), thread("t2")]}))
    import_gmail(conn, folder)
    assert conn.execute("SELECT handled_at FROM emails WHERE id=?", (e1,)).fetchone()[0] is None


def test_done_today_items_carry_their_time_for_the_done_today_section(conn):
    conn.execute("INSERT INTO tasks (title, due_date) VALUES ('A', '2026-10-01')"); mark_done(conn, "task", 1, NOW)
    it = build_today(conn, NOW)["today_items"][0]
    assert it["done"] is True and it["done_at"] == "2026-10-01 14:32:05"


def test_items_closed_in_suivi_are_listed_but_not_reopenable(conn):
    conn.execute("INSERT INTO tasks (title, status, done_at, source, source_ref) VALUES ('Closed there', 'done', '2026-09-30', 'suivi', 'C-1')")
    items = done_list(conn, NOW.date(), 7)
    assert items[0]["title"] == "Closed there" and items[0]["reopenable"] is False and items[0]["via"] == "Suivi"


def test_migration_kept_old_done_log_rows(tmp_path):
    c = db.connect(tmp_path / "old.db")
    c.executescript("BEGIN;" + db.MIGRATIONS[0]); c.execute("PRAGMA user_version = 1"); c.commit()
    c.execute("INSERT INTO done_log (item_type,item_id,title,done_at) VALUES ('task',1,'kept','2026-09-28 10:00:00')"); c.commit()
    db.migrate(c)
    assert c.execute("SELECT title FROM done_log").fetchone()[0] == "kept"
    c.execute("INSERT INTO done_log (item_type,item_id,title) VALUES ('email',1,'ok')")      # new type now allowed


def test_api_endpoints():
    from fastapi.testclient import TestClient
    from harness.main import app
    with TestClient(app) as cl:
        assert "items" in cl.get("/api/done?days=30&q=x").json() and "items" in cl.get("/api/done?days=0").json()
        assert cl.post("/api/emails/999999/done").json() == {"changed": False}
        assert cl.post("/api/emails/999999/undo").json() == {"changed": False}
        assert cl.post("/api/items/email/999999/done").json() == {"changed": False}

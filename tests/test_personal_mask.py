"""Personal items are masked by the server: titles, project codes and names reach the page only via 'reveal'."""
import json
from datetime import datetime

import pytest

from harness import db
from harness.config import TZ
from harness.deadlines import mark_done
from harness.items import reveal
from harness.today import build_today, deadline_detail, done_list

NOW = datetime(2026, 10, 1, 9, 0, tzinfo=TZ)
SECRET_TASK, SECRET_DEADLINE, SECRET_WAIT, SECRET_PERSON, SECRET_CODE = "Dentist: root canal quote", "File personal tax return", "Landlord deposit refund", "landlord-bob", "TAXP"


@pytest.fixture
def conn(tmp_path):
    c = db.connect(tmp_path / "t.db"); db.migrate(c)
    c.execute("INSERT INTO tasks (title, due_date, project_code, space, sensitivity) VALUES (?,?,?, 'personal','S3')", (SECRET_TASK, "2026-09-30", SECRET_CODE))
    c.execute("INSERT INTO tasks (title, due_date, project_code) VALUES ('Work task', '2026-09-30', 'GPF')")
    c.execute("INSERT INTO deadlines (title, due_date, importance, project_code, space, sensitivity) VALUES (?,?,?,?, 'personal','S3')", (SECRET_DEADLINE, "2026-10-12", "major", SECRET_CODE))
    c.execute("INSERT INTO deadlines (title, due_date, project_code) VALUES ('Work report', '2026-10-14', 'GPF')")
    c.execute("INSERT INTO waiting_on (description, person, since_date, remind_on, space, sensitivity) VALUES (?,?,?,?, 'personal','S3')", (SECRET_WAIT, SECRET_PERSON, "2026-09-01", "2026-10-01"))
    c.commit()
    return c


def test_personal_items_show_a_generic_label_and_keep_their_date(conn):
    t = build_today(conn, NOW)
    by = {i["type"]: i for i in t["today_items"] if i["masked"]}
    assert by["task"]["title"] == "Personal task" and by["task"]["code"] is None and by["task"]["due"] == "2026-09-30"
    assert by["waiting_on"]["title"] == "Personal follow-up" and by["waiting_on"]["person"] is None
    work = next(i for i in t["today_items"] if i["title"] == "Work task")
    assert work["masked"] is False and work["code"] == "GPF"                      # work items are untouched
    marks = {m["id"]: m for m in t["lake"]}
    personal_mark = next(m for m in marks.values() if m["masked"])
    assert personal_mark["title"] == "Personal task" and personal_mark["code"] is None and personal_mark["due"] == "2026-10-12"
    assert next(m for m in marks.values() if not m["masked"])["title"] == "Work report"


def test_no_personal_detail_appears_anywhere_in_the_payload(conn):
    payload = json.dumps(build_today(conn, NOW))
    for secret in (SECRET_TASK, SECRET_DEADLINE, SECRET_WAIT, SECRET_PERSON, SECRET_CODE):
        assert secret not in payload, secret


def test_an_edited_personal_item_does_not_leak_the_original_title_either(conn):
    conn.execute("INSERT INTO item_overrides (table_name, item_id, field, source_value, edited_at) VALUES ('tasks', 1, 'title', ?, '2026-10-01')", (SECRET_TASK + " (source)",))
    conn.commit()
    payload = json.dumps(build_today(conn, NOW))
    assert "(source)" not in payload and SECRET_TASK not in payload


def test_done_list_masks_personal_titles_and_search_cannot_find_them(conn):
    mark_done(conn, "task", 1, NOW); mark_done(conn, "task", 2, NOW)
    items = {i["type"] + str(i["id"]): i for i in done_list(conn, NOW.date(), 7)}
    assert items["task1"]["title"] == "Personal task" and items["task1"]["masked"] and items["task2"]["title"] == "Work task"
    assert [i["title"] for i in done_list(conn, NOW.date(), 7, "dentist")] == []            # searching for it finds nothing
    assert [i["title"] for i in done_list(conn, NOW.date(), 7, "work")] == ["Work task"]
    assert SECRET_TASK not in json.dumps(done_list(conn, NOW.date(), 7))


def test_reveal_returns_the_details_only_on_request(conn):
    assert reveal(conn, "task", 1) == {"title": SECRET_TASK, "code": SECRET_CODE, "person": None}
    assert reveal(conn, "waiting_on", 1) == {"title": SECRET_WAIT, "code": None, "person": SECRET_PERSON}
    assert reveal(conn, "deadline", 1)["title"] == SECRET_DEADLINE
    assert reveal(conn, "task", 999) is None


def test_the_deadline_panel_is_the_reveal_for_lake_marks_but_hides_related_personal_items(conn):
    d = deadline_detail(conn, 1, NOW.date())                                        # she clicked the mark: details shown
    assert d["title"] == SECRET_DEADLINE and d["code"] == SECRET_CODE
    conn.execute("INSERT INTO deadlines (title, due_date, project_code, space) VALUES ('Other personal deadline', '2026-10-20', ?, 'personal')", (SECRET_CODE,)); conn.commit()
    d = deadline_detail(conn, 1, NOW.date())
    assert "Other personal deadline" not in json.dumps(d["related"]) and SECRET_TASK not in json.dumps(d["related"])
    assert any(r["label"] == "Personal task" for r in d["related"])


def test_reveal_endpoint():
    from fastapi.testclient import TestClient
    from harness.main import app
    with TestClient(app) as cl:
        c = db.connect()
        c.execute("INSERT INTO tasks (title, space, sensitivity) VALUES ('Secret API title', 'personal', 'S3')"); c.commit()
        tid = c.execute("SELECT id FROM tasks WHERE title='Secret API title'").fetchone()[0]; c.close()
        assert "Secret API title" not in json.dumps(cl.get("/api/today").json())
        assert cl.get(f"/api/items/task/{tid}/reveal").json()["title"] == "Secret API title"
        assert cl.get("/api/items/task/99999999/reveal").status_code == 404
        assert cl.get("/api/items/bogus/1/reveal").status_code == 404

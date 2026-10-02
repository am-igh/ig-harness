"""Notes and follow-ups: recorded in the harness, attached to items or free-standing, follow-ups become tasks."""
import json
from datetime import datetime

import pytest

from harness import db, drafting, notes
from harness.config import TZ
from harness.deadlines import mark_done
from harness.gateway import Gateway
from harness.gateway.providers import Completion
from harness.notes import NoteRefused
from harness.today import build_today
from harness.triage import list_emails

NOW = datetime(2026, 10, 2, 9, 0, tzinfo=TZ)


@pytest.fixture
def conn(tmp_path):
    c = db.connect(tmp_path / "t.db"); db.migrate(c)
    c.execute("INSERT INTO tasks (title, due_date, project_code) VALUES ('Prepare panel notes', '2026-10-02', 'GPF')")
    c.execute("INSERT INTO tasks (title, due_date, project_code, space, sensitivity) VALUES ('Dentist root canal quote', '2026-10-02', 'DENT', 'personal', 'S3')")
    c.execute("INSERT INTO emails (thread_id, message_id, from_name, from_email, subject, received_at, snippet, body, direct, rfc_message_id, triage_status, needs_reply, score) "
              "VALUES ('18c0ffee12345678','m1','Daniel','dan@org.ch','Reunion jeudi','2026-10-01T09:00:00+02:00','s','Can you confirm Thursday?',1,'<a@x>','done',1,5)")
    c.execute("INSERT INTO waiting_on (description, person, since_date, remind_on) VALUES ('the draft agreement','dan','2026-09-20','2026-09-27')")
    c.commit()
    return c


def rows(c, sql): return [dict(r) for r in c.execute(sql)]


# ---------------------------------------------------------------- notes on items
def test_a_note_on_an_item_is_recorded_listed_and_counted(conn):
    n = notes.add_note(conn, "  Spoke to Daniel: he prefers Thursday afternoon.  ", parent_type="task", parent_id=1, now=NOW)
    assert n["text"] == "Spoke to Daniel: he prefers Thursday afternoon." and n["kind"] == "note" and n["created_at"] == "2026-10-02 09:00:00"
    assert n["parent"] == {"type": "task", "id": 1, "title": "Prepare panel notes", "masked": False} and n["follow_up"] is None
    assert [x["id"] for x in notes.for_parent(conn, "task", 1)] == [n["id"]] and notes.for_parent(conn, "task", 99) == []
    item = next(i for i in build_today(conn, NOW)["today_items"] if i["title"] == "Prepare panel notes")
    assert item["note_count"] == 1
    assert conn.execute("SELECT COUNT(*) FROM tasks").fetchone()[0] == 2                      # a plain note creates no task


def test_notes_on_emails_and_waiting_items_are_counted_too(conn):
    notes.add_note(conn, "He called about this.", parent_type="email", parent_id=1)
    notes.add_note(conn, "Second thought.", parent_type="email", parent_id=1)
    notes.add_note(conn, "Chased by phone.", parent_type="waiting_on", parent_id=1)
    assert list_emails(conn, 72, now=NOW)["needs_reply"][0]["note_count"] == 2
    w = next(i for i in build_today(conn, NOW)["today_items"] if i["type"] == "waiting_on")
    assert w["note_count"] == 1


def test_free_standing_notes_have_no_parent(conn):
    n = notes.add_note(conn, "Idea: invite the cantonal office to the forum.")
    assert n["parent"] is None and n["personal"] is False


@pytest.mark.parametrize("kw,msg", [({"text": "   "}, "empty"), ({"text": "x" * 2001}, "too long"), ({"text": "ok", "kind": "memo"}, "note or a follow-up"),
                                    ({"text": "ok", "parent_type": "banana", "parent_id": 1}, "Unknown item"), ({"text": "ok", "parent_type": "task"}, "Unknown item"),
                                    ({"text": "ok", "parent_type": "task", "parent_id": 999}, "no longer exists"),
                                    ({"text": "ok", "kind": "followup", "due": "31/10/2026"}, "not valid")])
def test_bad_notes_are_refused_and_nothing_is_saved(conn, kw, msg):
    with pytest.raises(NoteRefused, match=msg):
        notes.add_note(conn, **kw)
    assert conn.execute("SELECT COUNT(*) FROM notes").fetchone()[0] == 0 and conn.execute("SELECT COUNT(*) FROM tasks").fetchone()[0] == 2


# ---------------------------------------------------------------- follow-ups become tasks in Today & overdue
def test_a_follow_up_creates_a_task_that_shows_in_today_on_its_date(conn):
    n = notes.add_note(conn, "Call Daniel about the agreement\nand ask for the signed copy", kind="followup", parent_type="waiting_on", parent_id=1, due="2026-10-02", now=NOW)
    t = dict(conn.execute("SELECT * FROM tasks WHERE id = ?", (n["follow_up"]["task_id"],)).fetchone())
    assert t["title"] == "Call Daniel about the agreement" and t["due_date"] == "2026-10-02" and t["source"] == "note" and t["source_ref"] == str(n["id"]) and t["sensitivity"] == "S2"
    item = next(i for i in build_today(conn, NOW)["today_items"] if i["title"] == "Call Daniel about the agreement")
    assert item["from_note"] is True and item["due"] == "2026-10-02"
    later = notes.add_note(conn, "Check the invoice", kind="followup", due="2026-10-20", now=NOW)
    assert "Check the invoice" in [i["title"] for i in build_today(conn, NOW)["later_items"]] and later["follow_up"]["due"] == "2026-10-20"


def test_a_follow_up_without_a_date_is_due_today_and_inherits_the_project(conn):
    n = notes.add_note(conn, "Send the run of show", kind="followup", parent_type="task", parent_id=1, now=NOW)
    t = conn.execute("SELECT due_date, project_code FROM tasks WHERE id = ?", (n["follow_up"]["task_id"],)).fetchone()
    assert (t["due_date"], t["project_code"]) == ("2026-10-02", "GPF")


def test_ticking_the_follow_up_is_reflected_on_the_note(conn):
    n = notes.add_note(conn, "Send the thing", kind="followup", now=NOW)
    mark_done(conn, "task", n["follow_up"]["task_id"], NOW)
    v = notes.view(conn, n["id"])
    assert v["follow_up"]["status"] == "done" and v["follow_up"]["done_at"] == "2026-10-02 09:00:00"


def test_deleting_a_note_removes_its_open_follow_up_from_today_but_keeps_a_finished_one(conn):
    a = notes.add_note(conn, "Open follow-up", kind="followup", now=NOW)
    b = notes.add_note(conn, "Finished follow-up", kind="followup", now=NOW); mark_done(conn, "task", b["follow_up"]["task_id"], NOW)
    assert notes.delete_note(conn, a["id"]) and notes.delete_note(conn, b["id"]) and not notes.delete_note(conn, a["id"])
    assert conn.execute("SELECT status FROM tasks WHERE id=?", (a["follow_up"]["task_id"],)).fetchone()[0] == "dropped"
    assert conn.execute("SELECT status FROM tasks WHERE id=?", (b["follow_up"]["task_id"],)).fetchone()[0] == "done"
    assert notes.log(conn, 30, "", NOW.date()) == [] and "Open follow-up" not in [i["title"] for i in build_today(conn, NOW)["today_items"]]
    assert conn.execute("SELECT COUNT(*) FROM notes").fetchone()[0] == 2                      # recorded, not erased


# ---------------------------------------------------------------- personal notes
def test_notes_on_personal_items_are_masked_everywhere_until_revealed(conn):
    n = notes.add_note(conn, "Dentist said the quote includes an implant: ask insurance.", parent_type="task", parent_id=2, now=NOW)
    assert n["personal"] and n["masked"] and n["text"] == "Personal note" and n["parent"]["title"] == "Personal task"
    f = notes.add_note(conn, "Pay the dentist deposit", kind="followup", parent_type="task", parent_id=2, now=NOW)
    payload = json.dumps([build_today(conn, NOW), notes.log(conn, 30, "", NOW.date()), notes.for_parent(conn, "task", 2), f])
    for secret in ("implant", "insurance", "dentist deposit", "Dentist root canal", "DENT"):
        assert secret.lower() not in payload.lower(), secret
    assert notes.reveal(conn, n["id"]) == {"text": "Dentist said the quote includes an implant: ask insurance."}
    task = next(i for i in build_today(conn, NOW)["today_items"] if i["from_note"] and i["masked"])
    assert task["title"] == "Personal task"                                                    # the follow-up task itself is masked


def test_a_free_standing_note_can_be_marked_personal(conn):
    n = notes.add_note(conn, "Book the flights for the holiday", personal=True)
    assert n["personal"] and n["masked"] and conn.execute("SELECT sensitivity FROM notes").fetchone()[0] == "S3"


def test_searching_the_log_never_matches_personal_notes(conn):
    notes.add_note(conn, "Work note about the forum agenda", now=NOW)
    notes.add_note(conn, "Private note about the forum of my family", personal=True, now=NOW)
    assert [n["text"] for n in notes.log(conn, 30, "forum", NOW.date())] == ["Work note about the forum agenda"]
    assert len(notes.log(conn, 30, "", NOW.date())) == 2


def test_personal_notes_are_never_context_for_drafts(conn):
    notes.add_note(conn, "Work context", parent_type="email", parent_id=1)
    conn.execute("INSERT INTO notes (created_at, text, parent_type, parent_id, space) VALUES ('2026-10-02 09:00:00', 'Private context', 'email', 1, 'personal')"); conn.commit()
    assert notes.context_for(conn, "email", 1) == ["Work context"]


# ---------------------------------------------------------------- the log
def test_the_log_is_newest_first_and_filters_by_period_and_words(conn):
    old = datetime(2026, 8, 1, 10, 0, tzinfo=TZ)
    notes.add_note(conn, "Old note about budget", now=old)
    notes.add_note(conn, "Recent note about budget", now=NOW)
    notes.add_note(conn, "Recent note about venue", now=datetime(2026, 10, 2, 11, 0, tzinfo=TZ))
    assert [n["text"] for n in notes.log(conn, 30, "", NOW.date())] == ["Recent note about venue", "Recent note about budget"]
    assert [n["text"] for n in notes.log(conn, None, "budget", NOW.date())] == ["Recent note about budget", "Old note about budget"]


# ---------------------------------------------------------------- notes inform drafts
class Model:
    external, name, model = False, "local", "fake"

    def __init__(self):
        self.prompts = []

    def complete(self, prompt, system=None, max_tokens=0, json_mode=False):
        self.prompts.append(prompt)
        return Completion(json.dumps({"body": "Hello,\n\nYes.\n\nBest,", "needs_input": []}))


def test_her_notes_on_an_email_and_on_a_waiting_item_are_given_to_the_model(conn, tmp_path):
    m = Model()
    gw = Gateway(connect=lambda: db.connect(tmp_path / "t.db"), providers={"local": m})
    notes.add_note(conn, "Daniel told me by phone that Thursday 15:00 is fixed.", parent_type="email", parent_id=1)
    drafting.generate_reply(conn, gw, 1)
    assert "Her own notes about this conversation" in m.prompts[0] and "Thursday 15:00 is fixed" in m.prompts[0]
    conn.execute("INSERT INTO people (slug, name, email) VALUES ('dan','Daniel','dan@org.ch')")
    conn.execute("INSERT INTO correspondence_threads (person_email, thread_id, subject, last_at, last_from_me, last_rfc_id) VALUES ('dan@org.ch','18c0ffee000000a1','Agreement','2026-09-20T10:00:00+02:00',1,'<z@x>')"); conn.commit()
    notes.add_note(conn, "He promised it by Friday.", parent_type="waiting_on", parent_id=1)
    drafting.generate_reminder(conn, gw, 1)
    assert "He promised it by Friday." in m.prompts[1]


# ---------------------------------------------------------------- API
def test_notes_api_roundtrip():
    from fastapi.testclient import TestClient
    from harness.main import app
    with TestClient(app) as cl:
        c = db.connect(); c.execute("INSERT INTO tasks (title, due_date) VALUES ('API task for notes', '2000-01-01')"); c.commit()
        tid = c.execute("SELECT id FROM tasks WHERE title='API task for notes'").fetchone()[0]; c.close()
        n = cl.post("/api/notes", json={"text": "An API note", "parent_type": "task", "parent_id": tid}).json()
        f = cl.post("/api/notes", json={"text": "An API follow-up", "kind": "followup", "due": "2000-01-05", "parent_type": "task", "parent_id": tid}).json()
        assert n["parent"]["title"] == "API task for notes" and f["follow_up"]["due"] == "2000-01-05"
        assert {x["id"] for x in cl.get(f"/api/notes?parent_type=task&parent_id={tid}").json()["items"]} == {n["id"], f["id"]}
        assert any(x["id"] == n["id"] for x in cl.get("/api/notes/log?days=0&q=API note").json()["items"])
        assert cl.get(f"/api/notes/{n['id']}/reveal").json()["text"] == "An API note"
        assert cl.post("/api/notes", json={"text": ""}).status_code == 422
        assert cl.post("/api/notes", json={"text": "x", "parent_type": "task", "parent_id": 99999999}).status_code == 422
        assert cl.get("/api/notes?parent_type=banana&parent_id=1").status_code == 404
        assert cl.get("/api/notes/99999999/reveal").status_code == 404
        assert cl.delete(f"/api/notes/{n['id']}").json() == {"changed": True} and cl.delete(f"/api/notes/{n['id']}").json() == {"changed": False}

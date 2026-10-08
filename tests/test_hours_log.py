"""Logging time when she ticks off a project to-do: asked only for finished work items in a project, entered by her, approved by her click, written by the existing hours writer path."""
import json
from datetime import date

import pytest

from harness import db, hours_log as HL

TODAY = date(2026, 10, 9)


@pytest.fixture
def c(tmp_path):
    c = db.connect(tmp_path / "t.db"); db.migrate(c)
    c.executemany("INSERT INTO project_codes (code, name, domain, kind) VALUES (?,?,?,?)", [("TK", "Toolkit", "W", "project"), ("IGCSC", "IG cyber", "W", "thread"), ("PERS", "Personal", "P", "project")])
    t = lambda title, code, space="work", status="done": c.execute("INSERT INTO tasks (title, project_code, space, status, done_at, source, source_ref) VALUES (?,?,?,?,?,?,?)", (title, code, space, status, "2026-10-09 10:30:00" if status == "done" else None, "t", title))
    t("Write the TK outline", "TK"); t("Reply about the thread", "IGCSC"); t("Dentist", "PERS", "personal"); t("Personal in a work code", "TK", "personal"); t("No project", None); t("Not done yet", "TK", status="open")
    c.execute("INSERT INTO deadlines (title, due_date, project_code, status, done_at, source, source_ref) VALUES ('Submit the TK report', '2026-10-09', 'TK', 'done', '2026-10-09 11:00:00', 't', 'd1')")
    c.commit()
    return c


def tid(c, title): return c.execute("SELECT id FROM tasks WHERE title = ?", (title,)).fetchone()[0]


def test_it_asks_only_for_finished_work_items_in_a_project(c):
    a = HL.ask(c, "task", tid(c, "Write the TK outline"), TODAY)
    assert a == {"ask": True, "project": "TK", "title": "Write the TK outline", "date": "2026-10-09", "already_logged": 0}
    assert HL.ask(c, "deadline", 1, TODAY)["ask"] is True
    for title in ("Reply about the thread", "Dentist", "Personal in a work code", "No project", "Not done yet"):
        assert HL.ask(c, "task", tid(c, title), TODAY)["ask"] is False, title
    assert HL.ask(c, "email", 1, TODAY)["ask"] is False and HL.ask(c, "task", 9999, TODAY)["ask"] is False
    HL.set_prompt(c, False)
    assert HL.ask(c, "task", tid(c, "Write the TK outline"), TODAY) == {"ask": False, "reason": "off"}
    HL.set_prompt(c, True)
    assert HL.ask(c, "task", tid(c, "Write the TK outline"), TODAY)["ask"] is True


def test_what_she_enters_becomes_approved_entries_for_the_hours_writer(c, tmp_path):
    out = HL.log(c, "task", tid(c, "Write the TK outline"), [{"date": "2026-10-08", "hours": "1,5"}, {"date": "2026-10-09", "hours": 2}], today=TODAY, data_dir=tmp_path)
    assert out["logged"] == 2 and out["hours"] == 3.5 and out["project"] == "TK" and out["queued"] is True
    rows = c.execute("SELECT date, hours, project, evidence, description, status, source FROM hour_proposals ORDER BY date").fetchall()
    assert [(r["date"], r["hours"], r["status"], r["source"]) for r in rows] == [("2026-10-08", 1.5, "approved", "todo"), ("2026-10-09", 2.0, "approved", "todo")]
    assert rows[0]["project"] == "TK" and rows[0]["description"] == "Write the TK outline" and rows[0]["evidence"] == f"Harness to-do #{tid(c, 'Write the TK outline')} (done 2026-10-09)"
    files = sorted((tmp_path / "hours/outbox").glob("*.json"))
    assert len(files) == 2 and all(json.loads(f.read_text())["approved_at"] for f in files)               # what tools/hours_writer.py picks up
    assert HL.ask(c, "task", tid(c, "Write the TK outline"), TODAY)["already_logged"] == 3.5


def test_wrong_input_is_refused_with_plain_words_and_nothing_is_half_logged(c, tmp_path):
    t = tid(c, "Write the TK outline")
    bad = [([], "between one and"), ([{"date": "2026-10-10", "hours": 1}], "not happened"), ([{"date": "2026-01-01", "hours": 1}], "too long ago"), ([{"date": "2026-10-09", "hours": 0}], "between 0 and 14"),
           ([{"date": "2026-10-09", "hours": 20}], "between 0 and 14"), ([{"date": "x", "hours": 1}], "date and a number"), ([{"date": "2026-10-09", "hours": "abc"}], "date and a number"),
           ([{"date": "2026-10-09", "hours": 1}, {"date": "2026-10-09", "hours": 1}], "once")]
    for entries, msg in bad:
        with pytest.raises(ValueError, match=msg):
            HL.log(c, "task", t, entries, today=TODAY, data_dir=tmp_path)
    assert c.execute("SELECT COUNT(*) FROM hour_proposals").fetchone()[0] == 0
    with pytest.raises(ValueError, match="finished work to-do"):
        HL.log(c, "task", tid(c, "Dentist"), [{"date": "2026-10-09", "hours": 1}], today=TODAY, data_dir=tmp_path)
    HL.log(c, "task", t, [{"date": "2026-10-09", "hours": 1}], today=TODAY, data_dir=tmp_path)
    with pytest.raises(ValueError, match="already logged"):
        HL.log(c, "task", t, [{"date": "2026-10-09", "hours": 1}], today=TODAY, data_dir=tmp_path)                    # the same day twice for the same to-do


def test_the_demo_shows_the_entry_in_the_hours_table_at_once(c, tmp_path, monkeypatch):
    monkeypatch.setenv("IG_DEMO", "1")
    out = HL.log(c, "task", tid(c, "Write the TK outline"), [{"date": "2026-10-09", "hours": 2}], description="Outline for the toolkit", today=TODAY, data_dir=tmp_path)
    assert out["queued"] is False
    h = c.execute("SELECT project, hours, description, source FROM hours").fetchone()
    assert (h["project"], h["hours"], h["description"], h["source"]) == ("TK", 2.0, "Outline for the toolkit", "harness")
    assert c.execute("SELECT status FROM hour_proposals").fetchone()[0] == "written"


def test_endpoints(c):
    from fastapi.testclient import TestClient
    from harness.main import app
    with TestClient(app) as cl:
        assert cl.get("/api/hours/ask?type=task&id=999999").json()["ask"] is False
        assert cl.post("/api/hours/log", json={"type": "task", "id": 999999, "entries": [{"date": "2026-10-09", "hours": 1}]}).status_code == 422
        assert cl.post("/api/hours/prompt", json={"on": True}).json() == {"on": True}

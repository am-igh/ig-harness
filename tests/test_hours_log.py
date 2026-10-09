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


def test_what_she_enters_becomes_journal_items_and_approved_hours_held_until_suivi_gives_the_id(c, tmp_path):
    t = tid(c, "Write the TK outline")
    out = HL.log(c, "task", t, [{"date": "2026-10-08", "hours": "1,5"}, {"date": "2026-10-09", "hours": 2}], today=TODAY, data_dir=tmp_path)
    assert out["logged"] == 2 and out["hours"] == 3.5 and out["project"] == "TK" and out["queued"] is True
    tj = c.execute("SELECT date, hours, project, description, evidence, status, journal_id FROM todo_journal ORDER BY date").fetchall()
    assert [(r["date"], r["hours"], r["status"], r["journal_id"]) for r in tj] == [("2026-10-08", 1.5, "pending", None), ("2026-10-09", 2.0, "pending", None)]
    assert tj[0]["project"] == "TK" and tj[0]["description"] == "Write the TK outline" and tj[0]["evidence"] == f"harness-to-do:{t} (done 2026-10-09)"
    props = c.execute("SELECT status, source, evidence FROM hour_proposals ORDER BY date").fetchall()
    assert [(p["status"], p["source"]) for p in props] == [("approved", "todo"), ("approved", "todo")] and all("pending" in p["evidence"] for p in props)
    assert not (tmp_path / "hours/outbox").exists() or not list((tmp_path / "hours/outbox").glob("*.json"))              # the hours writer has nothing yet
    assert HL.ask(c, "task", t, TODAY)["already_logged"] == 3.5
    assert HL.release(c, tmp_path) == 0                                                                                     # Suivi has not written the rows yet


def test_once_suivi_has_the_rows_the_journal_id_becomes_the_evidence_and_the_hours_writer_gets_the_entries(c, tmp_path):
    from harness import suivi_export as SE
    t = tid(c, "Write the TK outline")
    HL.log(c, "task", t, [{"date": "2026-10-08", "hours": 1.5}, {"date": "2026-10-09", "hours": 2}], today=TODAY, data_dir=tmp_path)
    ids = [r[0] for r in c.execute("SELECT id FROM todo_journal ORDER BY date")]
    state = SE.read_state(tmp_path)
    state["todo_hours"][str(ids[0])] = {"journal_id": "J-2026-041", "exported_at": "x", "row": 7}                          # only the first day is written so far
    SE.write_state(tmp_path, state)
    assert HL.release(c, tmp_path) == 1 and HL.release(c, tmp_path) == 0
    ev = [r[0] for r in c.execute("SELECT evidence FROM hour_proposals ORDER BY date")]
    assert ev[0] == "Suivi J-2026-041" and "pending" in ev[1]
    files = sorted((tmp_path / "hours/outbox").glob("*.json"))
    assert len(files) == 1 and json.loads(files[0].read_text())["approved_at"]
    state["todo_hours"][str(ids[1])] = {"journal_id": "J-2026-042", "exported_at": "x", "row": 8}
    SE.write_state(tmp_path, state)
    assert HL.release(c, tmp_path) == 1 and len(list((tmp_path / "hours/outbox").glob("*.json"))) == 2
    assert [r[0] for r in c.execute("SELECT journal_id FROM todo_journal ORDER BY date")] == ["J-2026-041", "J-2026-042"] and {r[0] for r in c.execute("SELECT status FROM todo_journal")} == {"released"}
    assert HL.ask(c, "task", t, TODAY)["already_logged"] == 3.5                                                             # still counted after release


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


def test_the_demo_shows_the_journal_row_and_the_hours_entry_at_once(c, tmp_path, monkeypatch):
    monkeypatch.setenv("IG_DEMO", "1")
    out = HL.log(c, "task", tid(c, "Write the TK outline"), [{"date": "2026-10-09", "hours": 2}], description="Outline for the toolkit", today=TODAY, data_dir=tmp_path)
    assert out["queued"] is False
    h = c.execute("SELECT project, hours, description, source, evidence FROM hours").fetchone()
    assert (h["project"], h["hours"], h["description"], h["source"]) == ("TK", 2.0, "Outline for the toolkit", "harness") and h["evidence"].startswith("Suivi J-2026-")
    j = c.execute("SELECT entry_date, project_code, hours, source_ref, entry_type FROM journal_entries WHERE source = 'demo-hours'").fetchone()
    assert (j["entry_date"], j["project_code"], j["hours"], j["entry_type"]) == ("2026-10-09", "TK", 2.0, "work") and h["evidence"] == f"Suivi {j['source_ref']}"
    assert c.execute("SELECT status FROM hour_proposals").fetchone()[0] == "written" and c.execute("SELECT status FROM todo_journal").fetchone()[0] == "released"


def test_endpoints(c):
    from fastapi.testclient import TestClient
    from harness.main import app
    with TestClient(app) as cl:
        assert cl.get("/api/hours/ask?type=task&id=999999").json()["ask"] is False
        assert cl.post("/api/hours/log", json={"type": "task", "id": 999999, "entries": [{"date": "2026-10-09", "hours": 1}]}).status_code == 422
        assert cl.post("/api/hours/prompt", json={"on": True}).json() == {"on": True}

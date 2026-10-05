"""Phone to-dos: the Reminders reader (mocked), the importer, and accepting into tasks. Synthetic data only."""
import json
import os
import stat
import subprocess
import sys
from datetime import date
from pathlib import Path
from types import SimpleNamespace

import pytest

from harness import db, phone
from harness.importers.phone_todos import import_phone_todos

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
import reminders_helper as RH  # noqa: E402

TODAY = date(2026, 10, 2)    # a Friday


@pytest.fixture
def c(tmp_path):
    c = db.connect(tmp_path / "t.db"); db.migrate(c)
    c.executemany("INSERT INTO project_codes (code, name, domain, kind) VALUES (?,?,?,?)", [("TK", "Toolkit", "W", "project"), ("GPF", "Forum", "W", "project"), ("TAX", "Tax", "P", "area")])
    c.commit()
    return c


def item(i, name, due=None, completed=False, body=""):
    return {"id": f"x-coredata://{i}", "name": name, "body": body, "due_date": due, "due_time": None, "created": "2026-10-02T08:00:00.000Z", "completed": completed}


def doc(items, error=None):
    return {"fetched_at": "2026-10-02T08:05:00+00:00", "list": "Harness", "error": error, "items": items}


# ---------------------------------------------------------------- the reader
def osa(*recs):
    """What the AppleScript prints: records separated by RS, fields by US."""
    return "\x1e".join("\x1f".join(r) for r in recs) + "\x1e"


def test_the_reader_writes_a_private_json_file_and_never_changes_reminders(tmp_path):
    seen = []
    def runner(cmd, **kw):
        seen.append((cmd, Path(cmd[1]).read_text()))                       # the script is a temporary file
        return SimpleNamespace(returncode=0, stdout=osa(("x-apple-reminder://A1", "Call Daniel", "", "2026-10-09 00:00", "2026-10-02T08:00", "false")), stderr="")
    out = tmp_path / "phone_todos.json"
    msg = RH.pull(out, "Harness", runner)
    assert msg == "read 1 reminder(s) from 'Harness'" and json.loads(out.read_text())["items"][0]["name"] == "Call Daniel"
    assert stat.S_IMODE(out.stat().st_mode) == 0o600 and seen[0][0][0] == "osascript" and seen[0][0][1].endswith(".applescript") and 'list "Harness"' in seen[0][1] and not Path(seen[0][0][1]).exists()
    it = json.loads(out.read_text())["items"][0]
    assert (it["id"], it["due_date"], it["due_time"], it["completed"]) == ("x-apple-reminder://A1", "2026-10-09", None, False)
    src = Path(RH.__file__).read_text()
    import re
    for banned in (r"\bdelete\b", r"\bset (completed|name|body|due date|priority|flagged) of\b", r"\bmake new\b", r"\bmove\b", r"\bset (completed|name|body|due date) to\b.*\bof (r|rem)"):
        assert not re.search(banned, src.split("SCRIPT = ")[1].split('"""')[1]), banned


def test_a_missing_list_or_missing_permission_is_reported_in_plain_words(tmp_path):
    out = tmp_path / "p.json"
    assert RH.pull(out, "Harness", lambda cmd, **kw: SimpleNamespace(returncode=1, stdout="", stderr="execution error: Reminders got an error: Can\'t get list \"Harness\". (-1728)")) == "no list named Harness"
    msg = RH.pull(out, "Harness", lambda cmd, **kw: SimpleNamespace(returncode=1, stdout="", stderr="execution error: Not authorized to send Apple events to Reminders. (-1743)"))
    assert "Automation" in msg and json.loads(out.read_text())["error"] == msg


# ---------------------------------------------------------------- reading the words
@pytest.mark.parametrize("text,personal,title", [("personal: renew passport", True, "renew passport"), ("Personal Send off pictures of the roof", True, "Send off pictures of the roof"),
                                                 ("personal, call the dentist", True, "call the dentist"), ("p: buy flowers", True, "buy flowers"), ("Perso - dentiste", True, "dentiste"),
                                                 ("pay the invoice", False, "pay the invoice"), ("personally thank Daniel", False, "personally thank Daniel"), ("p buy flowers", False, "p buy flowers")])
def test_the_personal_marker_works_with_or_without_punctuation_as_siri_dictates_it(text, personal, title):
    r = phone.clean(text, {"TK"})
    assert (r["space"] == "personal", r["text"]) == (personal, title)


@pytest.mark.parametrize("text,expected", [("call Daniel tomorrow", "2026-10-03"), ("send the note today", "2026-10-02"), ("finish report by Monday", "2026-10-05"), ("réunion vendredi", "2026-10-09"),
                                           ("do it next week", "2026-10-05"), ("call Daniel", None), ("Mondial plans", None)])
def test_due_dates_from_clear_words_only(text, expected):
    assert phone.parse_due_words(text, TODAY) == expected


def test_title_space_and_project_code(c):
    codes = {"TK", "GPF"}
    assert phone.clean("[TK] chase the server survey", codes) == {"text": "chase the server survey", "space": "work", "project_code": "TK"}
    assert phone.clean("GPF: confirm the panel room", codes)["project_code"] == "GPF"
    assert phone.clean("Ask Daniel about the TK budget", codes)["project_code"] == "TK"
    p = phone.clean("personal: renew passport", codes)
    assert (p["text"], p["space"], p["project_code"]) == ("renew passport", "personal", None) and phone.clean("p - dentist", codes)["space"] == "personal"
    assert phone.clean("ZZ nothing here", codes)["project_code"] is None


# ---------------------------------------------------------------- the list she confirms
def test_new_reminders_wait_for_her_and_are_not_added_twice(c):
    r = phone.import_phone(c, doc([item(1, "[TK] call Daniel", "2026-10-09"), item(2, "buy a gift tomorrow")]), TODAY)
    assert r == {"added": 2, "updated": 0, "error": None}
    assert phone.import_phone(c, doc([item(1, "[TK] call Daniel", "2026-10-09"), item(2, "buy a gift tomorrow")]), TODAY)["added"] == 0
    got = {i["text"]: i for i in phone.list_new(c)["items"]}
    assert got["call Daniel"]["project_code"] == "TK" and got["call Daniel"]["due_date"] == "2026-10-09" and got["buy a gift tomorrow"]["due_date"] == "2026-10-03"


def test_editing_on_the_phone_before_deciding_refreshes_the_waiting_item_and_a_deleted_or_completed_one_disappears(c):
    phone.import_phone(c, doc([item(1, "call Daniel"), item(2, "send slides"), item(3, "book room")]), TODAY)
    r = phone.import_phone(c, doc([item(1, "call Daniel Stauffacher on Friday"), item(2, "send slides", completed=True)]), TODAY)      # 3 was deleted on the phone
    assert r["updated"] == 1
    items = phone.list_new(c)["items"]
    assert [(i["text"], i["due_date"]) for i in items] == [("call Daniel Stauffacher on Friday", "2026-10-09")]


def test_accepting_creates_a_follow_up_task_with_project_and_due_date(c):
    phone.import_phone(c, doc([item(1, "[TK] call Daniel", "2026-10-09")]), TODAY)
    rid = phone.list_new(c)["items"][0]["id"]
    res = phone.accept(c, rid, None)
    t = c.execute("SELECT * FROM tasks WHERE id=?", (res["task_id"],)).fetchone()
    assert (t["title"], t["due_date"], t["project_code"], t["space"], t["source"]) == ("call Daniel", "2026-10-09", "TK", "work", "note")
    n = c.execute("SELECT * FROM notes WHERE id=?", (res["note_id"],)).fetchone()
    assert (n["kind"], n["project_code"], n["space"]) == ("followup", "TK", "work")
    assert phone.list_new(c)["items"] == []
    with pytest.raises(ValueError):
        phone.accept(c, rid, None)                                                                            # already decided
    assert phone.import_phone(c, doc([item(1, "[TK] call Daniel", "2026-10-09")]), TODAY)["added"] == 0      # an accepted one is never offered again


def test_edits_while_accepting_and_validation(c):
    phone.import_phone(c, doc([item(1, "call someone")]), TODAY)
    rid = phone.list_new(c)["items"][0]["id"]
    with pytest.raises(ValueError, match="project"):
        phone.accept(c, rid, {"project_code": "ZZZ"})
    res = phone.accept(c, rid, {"text": "call Daniel about the course", "due_date": "2026-10-20", "project_code": "gpf"})
    t = c.execute("SELECT title, due_date, project_code FROM tasks WHERE id=?", (res["task_id"],)).fetchone()
    assert tuple(t) == ("call Daniel about the course", "2026-10-20", "GPF")
    with pytest.raises(KeyError):
        phone.accept(c, "nope", None)


def test_personal_to_dos_are_masked_stay_personal_and_never_go_to_suivi(c):
    phone.import_phone(c, doc([item(1, "personal: renew passport", "2026-10-30")]), TODAY)
    item_ = phone.list_new(c)["items"][0]
    assert item_["masked"] and item_["text"] == "Personal to-do" and "passport" not in json.dumps(phone.list_new(c))
    assert phone.reveal(c, item_["id"])["text"] == "renew passport"
    res = phone.accept(c, item_["id"], None)
    assert c.execute("SELECT space, sensitivity FROM tasks WHERE id=?", (res["task_id"],)).fetchone()[:] == ("personal", "S3")
    from tools import suivi_writer as W
    from harness import suivi_export as SE
    assert not SE.eligible("personal", False)                                                                  # the Suivi writer only takes work notes


def test_dismiss_and_errors_are_shown_plainly(c):
    phone.import_phone(c, doc([item(1, "something")]), TODAY)
    rid = phone.list_new(c)["items"][0]["id"]
    assert phone.dismiss(c, rid) is True and phone.dismiss(c, rid) is False and phone.list_new(c)["items"] == []
    phone.import_phone(c, doc([], error="no list named Harness"), TODAY)
    s = phone.list_new(c)
    assert s["error"] == "no list named Harness" and s["items"] == []


def test_reminder_ids_with_slashes_work_through_the_api(c, tmp_path, monkeypatch):
    """Regression: Apple's ids look like x-apple-reminder://UUID, and used to break the address path (404)."""
    from fastapi.testclient import TestClient
    from harness import main as m
    rid = "x-apple-reminder://B9914A5-71C7-4A5B-ADD7-40F6AEE7EB24"
    phone.import_phone(c, doc([{**item(1, "[TK] Send off pictures", "2026-10-09"), "id": rid}, {**item(2, "personal: renew passport"), "id": "x-apple-reminder://OTHER"}]), TODAY)
    dbfile = c.execute("PRAGMA database_list").fetchone()[2]
    monkeypatch.setattr(m, "_with_conn", lambda fn: fn(db.connect(Path(dbfile))))
    with TestClient(m.app) as cl:
        listed = cl.get("/api/phone").json()["items"]
        assert {i["id"] for i in listed} == {rid, "x-apple-reminder://OTHER"}
        assert cl.get("/api/phone/reveal", params={"id": "x-apple-reminder://OTHER"}).json()["text"] == "renew passport"
        r = cl.post("/api/phone/accept", json={"id": rid, "text": "Send off the pictures", "due_date": "2026-10-12"})
        assert r.status_code == 200 and r.json()["due"] == "2026-10-12"
        assert cl.post("/api/phone/accept", json={"id": rid}).status_code == 422
        assert cl.post("/api/phone/dismiss", json={"id": "x-apple-reminder://OTHER"}).json() == {"ok": True}
        assert cl.post("/api/phone/dismiss", json={"id": "x-apple-reminder://OTHER"}).status_code == 404 and cl.post("/api/phone/accept", json={"id": "nope"}).status_code == 404
    assert tuple(db.connect(Path(dbfile)).execute("SELECT title, due_date, project_code FROM tasks ORDER BY id DESC LIMIT 1").fetchone()) == ("Send off the pictures", "2026-10-12", "TK")


def test_importer_and_api(c, tmp_path):
    assert "reminders_helper" in import_phone_todos(c, tmp_path)[0].notes[0]
    (tmp_path / "phone_todos.json").write_text(json.dumps(doc([item(1, "call Daniel")])))
    assert import_phone_todos(c, tmp_path)[0].added == 1
    from fastapi.testclient import TestClient
    from harness.main import app
    with TestClient(app) as cl:
        assert {"items", "fetched_at", "error", "list"} <= set(cl.get("/api/phone").json())
        assert cl.post("/api/phone/accept", json={"id": "nope"}).status_code == 404 and cl.post("/api/phone/dismiss", json={"id": "nope"}).status_code == 404 and cl.get("/api/phone/reveal", params={"id": "nope"}).status_code == 404


def test_the_applescript_output_is_parsed_with_times_completion_bodies_and_odd_characters():
    text = osa(("id1", "Call Daniel — tomorrow", "line one\nline two", "2026-10-09 14:30", "2026-10-02T08:00", "false"), ("id2", "Done thing", "", "", "2026-09-01T09:00", "true"), ("", "no id", "", "", "", "false"))
    items = RH.parse_output(text)
    assert [i["id"] for i in items] == ["id1", "id2"]
    assert (items[0]["due_date"], items[0]["due_time"], items[0]["body"]) == ("2026-10-09", "14:30", "line one\nline two") and items[1]["completed"] is True and items[1]["due_date"] is None
    assert RH.parse_output("") == []


def test_a_list_name_with_quotes_cannot_break_out_of_the_script():
    seen = []
    RH.run_reminders('Har"ness\\', lambda cmd, **kw: seen.append(Path(cmd[1]).read_text()) or SimpleNamespace(returncode=0, stdout="", stderr=""))
    assert 'list "Har\\"ness\\\\"' in seen[0]


def test_project_codes_ignore_hyphens_spaces_and_capitals_and_a_wrong_one_gets_a_helpful_message(c):
    c.execute("INSERT INTO project_codes (code, name, domain, kind) VALUES ('IGCSC', 'IG cyber centre', 'W', 'thread')"); c.commit()
    codes = {"TK", "IGCSC"}
    assert phone.resolve_code(codes, "IG-CSC") == "IGCSC" and phone.resolve_code(codes, "ig csc") == "IGCSC" and phone.resolve_code(codes, "tk") == "TK" and phone.resolve_code(codes, "ZZ") is None
    assert phone.clean("Reply to Regula about IG-CSC rules", codes)["project_code"] == "IGCSC" and phone.clean("[IG-CSC] reply to Regula", codes) == {"text": "reply to Regula", "space": "work", "project_code": "IGCSC"}
    phone.import_phone(c, doc([item(1, "Reply to Regula about the board")]), TODAY)
    rid = phone.list_new(c)["items"][0]["id"]
    with pytest.raises(ValueError, match="IGCS|IG"):
        phone.accept(c, rid, {"project_code": "IG-XYZ"})
    res = phone.accept(c, rid, {"project_code": "IG-CSC"})
    assert c.execute("SELECT project_code FROM tasks WHERE id=?", (res["task_id"],)).fetchone()[0] == "IGCSC"

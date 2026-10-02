"""Friday hours pass: suggestions, approval rules, and the Mac-side writer that appends to hours.csv. Synthetic data only."""
import csv
import io
import json
import os
import sys
import time
from datetime import date
from pathlib import Path

import pytest

from harness import db, hours_pass as HP

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
import hours_writer as W  # noqa: E402

HEADER = "date,project,budget_line,hours,rate,description,evidence,source,entered_on\n"
TODAY = date(2026, 10, 2)   # Friday; the week is 28 Sep - 4 Oct


@pytest.fixture
def env(tmp_path):
    data = tmp_path / "data"; data.mkdir()
    c = db.connect(data / "harness.db"); db.migrate(c)
    c.executemany("INSERT INTO project_codes (code, name, domain, kind) VALUES (?,?,?,?)", [("GPF", "Forum", "W", "project"), ("TK", "Toolkit", "W", "project"), ("FIN", "Finance", "W", "thread"), ("TAX", "Tax", "P", "area")])
    csvf = tmp_path / "hours.csv"
    csvf.write_text(HEADER + "2026-09-09,GPF,,1,,Older entry,old.docx,file,2026-09-09\n")
    old = time.time() - 600; os.utime(csvf, (old, old))
    return c, data, csvf


def jr(c, ref, day, text, code, hours=None, space="work"):
    c.execute("INSERT INTO journal_entries (entry_date, text, project_code, space, source, source_ref, hours) VALUES (?,?,?,?,?,?,?)", (day, text, code, space, "suivi", ref, hours))


# ------------------------------------------------------------------ suggestions
def test_suggestions_come_from_journal_rows_and_tagged_events_with_evidence_and_nothing_invented(env):
    c, data, csvf = env
    jr(c, "J-2026-021", "2026-09-29", "Drafted the panel brief", "GPF", 1.5)
    jr(c, "J-2026-022", "2026-09-30", "Toolkit server check", "TK")                              # no hours figure
    jr(c, "J-2026-023", "2026-09-30", "Finance thread work", "FIN", 2)                           # a thread, not a project
    jr(c, "J-2026-024", "2026-09-30", "Tax thing", "TAX", 1, space="personal")
    jr(c, "J-2026-025", "2026-09-10", "Last week", "GPF", 1)                                      # another week
    c.execute("INSERT INTO calendar_events (title, start, end, source, source_ref) VALUES ('[TK] Steering call', '2026-10-01T10:00:00+02:00', '2026-10-01T11:30:00+02:00', 'g', 'e1')")
    c.execute("INSERT INTO calendar_events (title, start, end, all_day, source, source_ref) VALUES ('[GPF] Conference', '2026-10-01', '2026-10-02', 1, 'g', 'e2')")      # all day: skipped
    c.execute("INSERT INTO calendar_events (title, start, end, source, source_ref) VALUES ('[GPF] Next week', '2026-10-06T10:00:00+02:00', '2026-10-06T11:00:00+02:00', 'g', 'e3')")
    c.commit()
    assert HP.find_week(c, TODAY) == 3
    items = {i["evidence"]: i for i in HP.week_items(c, TODAY)}
    assert set(items) == {"Suivi J-2026-021", "Suivi J-2026-022", "Calendar: [TK] Steering call 2026-10-01"}
    assert items["Suivi J-2026-021"]["hours"] == 1.5 and items["Suivi J-2026-022"]["hours"] is None and "enter your own estimate" in items["Suivi J-2026-022"]["basis"]
    ev = items["Calendar: [TK] Steering call 2026-10-01"]
    assert (ev["hours"], ev["project"], ev["description"]) == (1.5, "TK", "Steering call")
    assert HP.find_week(c, TODAY) == 0                                                         # asking again adds nothing


def test_what_is_already_in_hours_csv_is_not_suggested_and_skipped_ones_stay_skipped(env):
    c, data, csvf = env
    jr(c, "J-2026-021", "2026-09-29", "Drafted", "GPF", 1)
    jr(c, "J-2026-022", "2026-09-30", "Other", "GPF", 1)
    c.execute("INSERT INTO hours (row_key, date, project, hours, description, evidence, entered_on) VALUES ('k','2026-09-29','GPF',1,'Drafted','Suivi J-2026-021; doc.docx','2026-09-29')")
    c.commit()
    assert HP.find_week(c, TODAY) == 1
    pid = HP.week_items(c, TODAY)[0]["id"]
    HP.skip(c, pid)
    assert HP.find_week(c, TODAY) == 0 and HP.week_items(c, TODAY) == []


def test_approval_needs_hours_project_evidence_and_a_day_that_has_happened(env):
    c, data, csvf = env
    jr(c, "J-2026-022", "2026-09-30", "Toolkit work", "TK")
    HP.find_week(c, TODAY)
    pid = HP.week_items(c, TODAY)[0]["id"]
    with pytest.raises(ValueError, match="Enter the hours"):
        HP.approve(c, pid, TODAY, data)
    for bad in ({"hours": "abc"}, {"hours": 20}, {"hours": -1}, {"project": "ZZZ"}):
        with pytest.raises(ValueError):
            HP.edit(c, pid, bad, TODAY)
    HP.edit(c, pid, {"hours": "1,5", "description": " Server check ", "budget_line": "WP1"}, TODAY)
    r = HP.approve(c, pid, TODAY, data)
    assert r["status"] == "approved" and (data / "hours/outbox" / f"{pid}.json").is_file() and r["hours"] == 1.5 and r["description"] == "Server check"
    with pytest.raises(ValueError):
        HP.edit(c, pid, {"hours": 2}, TODAY)
    with pytest.raises(ValueError):
        HP.approve(c, pid, TODAY, data)
    c.execute("UPDATE hour_proposals SET evidence='' WHERE id=?", (pid,)); c.execute("UPDATE hour_proposals SET status='proposed' WHERE id=?", (pid,)); c.commit()
    with pytest.raises(ValueError, match="evidence"):
        HP.approve(c, pid, TODAY, data)


# ------------------------------------------------------------------ the writer
def approved(c, data, n=1, **kw):
    ids = []
    for k in range(n):
        jr(c, f"J-2026-1{k:02d}", "2026-09-30", f"Work item {k}", "TK", 1)
    HP.find_week(c, TODAY)
    for it in HP.week_items(c, TODAY):
        if kw:
            HP.edit(c, it["id"], kw, TODAY)
        HP.approve(c, it["id"], TODAY, data); ids.append(it["id"])
    c.commit()
    return ids


def test_rows_are_appended_to_the_end_and_everything_before_is_untouched(env):
    c, data, csvf = env
    before = csvf.read_bytes()
    ids = approved(c, data, 2)
    out = W.run_once(data, csvf, today="2026-10-02")
    assert out == "added 2 row(s); 0 refused"
    after = csvf.read_bytes()
    assert after.startswith(before) and len(after) > len(before)
    rows = list(csv.DictReader(io.StringIO(after.decode())))
    assert [r["description"] for r in rows] == ["Older entry", "Work item 0", "Work item 1"]
    new = rows[1]
    assert (new["date"], new["project"], new["hours"], new["evidence"], new["source"], new["entered_on"], new["rate"]) == ("2026-09-30", "TK", "1", "Suivi J-2026-100", "harness", "2026-10-02", "")
    assert list((data / "hours/backups").glob("hours.csv.*"))[0].read_bytes() == before                         # backup of the original
    assert HP.reconcile(c, data) == ids and all(HP.week_items(c, TODAY)[k]["status"] == "written" for k in range(2))


def test_the_same_entry_is_never_added_twice(env):
    c, data, csvf = env
    approved(c, data)
    W.run_once(data, csvf, today="2026-10-02")
    size = csvf.stat().st_size
    pid = c.execute("SELECT id FROM hour_proposals").fetchone()[0]
    (data / "hours/outbox").mkdir(parents=True, exist_ok=True); (data / "hours/outbox" / f"{pid}.json").write_text(json.dumps({"id": pid}))      # a repeated request
    old = time.time() - 600; os.utime(csvf, (old, old))
    c.execute("UPDATE hour_proposals SET status='approved'"); c.commit()
    W.run_once(data, csvf, today="2026-10-02")
    assert csvf.stat().st_size == size


def test_nothing_is_written_without_a_matching_approval_or_with_bad_content(env):
    c, data, csvf = env
    jr(c, "J-2026-300", "2026-09-30", "Not approved", "TK", 1); c.commit()
    HP.find_week(c, TODAY)
    pid = c.execute("SELECT id FROM hour_proposals").fetchone()[0]
    (data / "hours/outbox").mkdir(parents=True, exist_ok=True); (data / "hours/outbox" / f"{pid}.json").write_text(json.dumps({"id": pid}))      # a request file with no approval in the database
    before = csvf.read_bytes()
    assert W.run_once(data, csvf, today="2026-10-02") == "added 0 row(s); 1 refused" and csvf.read_bytes() == before
    r = json.loads((data / "hours/done" / f"{pid}.json").read_text())
    assert r["ok"] is False and "not approved" in r["message"]
    assert W.validate(dict(hours=15, status="approved", project="TK", description="d", evidence="e", date="2026-09-30"), "2026-10-02") == "hours must be between 0 and 14"
    assert "evidence" in W.validate(dict(hours=1, status="approved", project="TK", description="d", evidence=" ", date="2026-09-30"), "2026-10-02")
    assert "future" in W.validate(dict(hours=1, status="approved", project="TK", description="d", evidence="e", date="2026-10-09"), "2026-10-02")


def test_it_waits_while_the_file_is_in_use_and_while_paused(env):
    c, data, csvf = env
    approved(c, data)
    os.utime(csvf, None)                                                                          # just modified
    before = csvf.read_bytes()
    assert W.run_once(data, csvf, today="2026-10-02").startswith("waiting") and csvf.read_bytes() == before
    assert (data / "hours/outbox").glob("*.json")
    old = time.time() - 600; os.utime(csvf, (old, old))
    (data / "hours").mkdir(exist_ok=True); (data / "hours/DISABLED").touch()
    assert W.run_once(data, csvf, today="2026-10-02").startswith("paused") and csvf.read_bytes() == before
    (data / "hours/DISABLED").unlink()
    assert W.run_once(data, csvf, today="2026-10-02").startswith("added 1")


def test_if_the_write_cannot_be_verified_her_original_is_put_back_exactly(env, monkeypatch):
    c, data, csvf = env
    approved(c, data)
    before = csvf.read_bytes()
    monkeypatch.setattr(W.os, "fsync", lambda fd: (_ for _ in ()).throw(OSError("disk trouble")))
    out = W.run_once(data, csvf, today="2026-10-02")
    assert out.startswith("added 0 row(s); 1 refused") and csvf.read_bytes() == before


def test_a_file_without_the_expected_columns_is_never_touched(env):
    c, data, csvf = env
    csvf.write_text("a,b,c\n1,2,3\n"); old = time.time() - 600; os.utime(csvf, (old, old))
    approved(c, data)
    before = csvf.read_bytes()
    assert "unexpected columns" in W.run_once(data, csvf, today="2026-10-02") and csvf.read_bytes() == before


def test_formula_looking_text_and_commas_and_a_missing_final_newline_are_handled(env):
    c, data, csvf = env
    csvf.write_text(HEADER + "2026-09-09,GPF,,1,,Older entry,old.docx,file,2026-09-09")           # no newline at the end
    old = time.time() - 600; os.utime(csvf, (old, old))
    approved(c, data, description='=SUM(A1), "quoted" text\\nnew line')
    before = csvf.read_bytes()
    W.run_once(data, csvf, today="2026-10-02")
    assert csvf.read_bytes().startswith(before)
    rows = list(csv.DictReader(io.StringIO(csvf.read_text())))
    assert len(rows) == 2 and rows[1]["description"].startswith("'=SUM(A1), \"quoted\" text") and "\n" not in rows[1]["description"]


def test_dry_run_shows_rows_and_changes_nothing(env):
    c, data, csvf = env
    approved(c, data)
    before = csvf.read_bytes()
    assert W.run_once(data, csvf, today="2026-10-02", dry_run=True).startswith("would add:") and csvf.read_bytes() == before
    assert not (data / "hours/backups").exists()


def test_writer_source_has_no_delete_or_overwrite_of_her_file_except_the_revert():
    src = Path(W.__file__).read_text()
    for banned in ("os.remove", "shutil", "rmtree", ".rename(", "os.replace", ".replace("):
        assert banned not in src, banned
    assert src.count("csv_path.write_bytes(old)") == 1 and 'open(csv_path, "ab")' in src and "csv_path.unlink" not in src


def test_api_roundtrip(env, monkeypatch):
    from fastapi.testclient import TestClient
    from harness import main as m
    c, data, csvf = env
    monkeypatch.setattr(HP, "DATA_DIR", data)
    monkeypatch.setattr(m, "_with_conn", lambda fn: fn(db.connect(data / "harness.db")))
    jr(c, "J-2026-500", "2026-09-30", "API work", "TK", 1); c.commit()
    with TestClient(m.app) as cl:
        assert cl.post("/api/hours/pass/find?day=2026-09-30").json()["added"] == 1
        item = cl.get("/api/hours/pass?day=2026-09-30").json()["items"][0]
        assert cl.post(f"/api/hours/pass/{item['id']}/edit", json={"hours": 99}).status_code == 422
        assert cl.post(f"/api/hours/pass/{item['id']}/edit", json={"hours": 2}).json()["hours"] == 2
        assert cl.post(f"/api/hours/pass/{item['id']}/approve").json()["status"] == "approved"
        assert cl.post(f"/api/hours/pass/{item['id']}/skip").status_code == 422 and cl.post("/api/hours/pass/999/skip").status_code == 404

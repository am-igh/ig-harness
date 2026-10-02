"""hours.csv importer (read-only) and the Hours-this-week summary. Synthetic data only."""
from datetime import date

import pytest

from harness import db
from harness.hours import problems, week_bounds, week_summary
from harness.importers.hours import import_hours

HEADER = "date,project,budget_line,hours,rate,description,evidence,source,entered_on\n"
TODAY = date(2026, 10, 2)     # a Friday


@pytest.fixture
def world(tmp_path):
    c = db.connect(tmp_path / "t.db"); db.migrate(c)
    c.executemany("INSERT INTO project_codes (code, name, domain, kind) VALUES (?,?,?,?)", [("GPF", "Forum", "W", "project"), ("TK", "Toolkit", "W", "project")])
    c.commit()
    folder = tmp_path / "projets"; folder.mkdir()
    return c, folder


def write(folder, *lines):
    (folder / "hours.csv").write_text(HEADER + "\n".join(lines) + "\n", encoding="utf-8")


def test_import_reads_rows_idempotently_and_never_changes_the_file(world):
    c, folder = world
    write(folder, "2026-09-28,GPF,,1.5,,Concept note,doc.docx,file,2026-09-28", "2026-09-29,tk,,2,,Server survey,survey.txt,file,2026-09-29")
    before = (folder / "hours.csv").read_bytes()
    r = import_hours(c, folder)[0]
    assert (r.added, r.unchanged) == (2, 0)
    r = import_hours(c, folder)[0]
    assert (r.added, r.unchanged, r.retired) == (0, 2, 0)
    assert (folder / "hours.csv").read_bytes() == before
    assert [x["project"] for x in c.execute("SELECT project FROM hours ORDER BY date")] == ["GPF", "TK"]          # codes are upper-cased


def test_rows_removed_from_the_file_are_removed_here_and_bad_rows_are_counted_not_fatal(world):
    c, folder = world
    write(folder, "2026-09-28,GPF,,1,,a,e,file,2026-09-28", "not a date,GPF,,1,,b,e,file,2026-09-28", "2026-09-28,GPF,,1,,a,e,file,2026-09-28")
    r = import_hours(c, folder)[0]
    assert (r.added, r.skipped) == (1, 2)                                                                       # a bad date and an exact repeat
    write(folder, "2026-09-29,TK,,1,,c,e,file,2026-09-29")
    r = import_hours(c, folder)[0]
    assert (r.added, r.retired) == (1, 1) and c.execute("SELECT COUNT(*) FROM hours").fetchone()[0] == 1


def test_a_missing_file_is_a_note_not_an_error(world):
    c, folder = world
    assert "no hours.csv" in import_hours(c, folder)[0].notes[0]


def test_week_summary_totals_by_project_and_the_days_with_nothing_logged(world):
    c, folder = world
    write(folder, "2026-09-28,GPF,,1.5,,Mon work,e1,file,2026-09-28", "2026-09-30,GPF,,1,,Wed work,e2,file,2026-09-30", "2026-09-30,TK,,2,,Wed TK,e3,email,2026-10-01",
          "2026-09-21,GPF,,4,,last week,e4,file,2026-09-21")
    import_hours(c, folder)
    w = week_summary(c, TODAY)
    assert (w["week_start"], w["week_end"], w["is_current"]) == ("2026-09-28", "2026-10-04", True)
    assert w["total"] == 4.5 and w["by_project"] == [{"project": "GPF", "hours": 2.5}, {"project": "TK", "hours": 2.0}]
    assert w["days_without"] == ["2026-09-29", "2026-10-01", "2026-10-02"] and w["next"] is None and w["prev"] == "2026-09-21"
    last = week_summary(c, TODAY, date(2026, 9, 22))
    assert last["total"] == 4 and last["is_current"] is False and last["next"] == "2026-09-28"


def test_entries_without_evidence_dates_or_a_known_project_are_flagged():
    known = {"GPF"}
    ok = dict(date="2026-09-28", project="GPF", hours=1, evidence="doc", entered_on="2026-09-28")
    assert problems(ok, known) == []
    assert problems({**ok, "evidence": None}, known) == ["no evidence"]
    assert problems({**ok, "entered_on": None}, known) == ["no entered_on date"]
    assert problems({**ok, "entered_on": "2026-10-20"}, known) == ["entered 22 days later"]
    assert problems({**ok, "project": "ZZZ"}, known) == ["unknown project ZZZ"] and problems({**ok, "hours": 0}, known) == ["hours missing or not positive"]


def test_week_bounds_run_monday_to_sunday():
    assert week_bounds(date(2026, 10, 2)) == (date(2026, 9, 28), date(2026, 10, 4)) and week_bounds(date(2026, 9, 28))[0] == date(2026, 9, 28)


def test_api(world, tmp_path):
    from fastapi.testclient import TestClient
    from harness.main import app
    with TestClient(app) as cl:
        r = cl.get("/api/hours").json()
        assert {"week_start", "total", "by_project", "entries", "days_without"} <= set(r)
        assert cl.get("/api/hours?day=2026-09-30").json()["week_start"] == "2026-09-28" and cl.get("/api/hours?day=nope").status_code == 422

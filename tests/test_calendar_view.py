"""The calendar widget's data: events (timed, all-day, multi-day), layers, masking, and range limits."""
import json
from datetime import date

import pytest

from harness import db
from harness.calendar_view import BadRange, build_range


@pytest.fixture
def conn(tmp_path):
    c = db.connect(tmp_path / "t.db"); db.migrate(c)
    ev = "INSERT INTO calendar_events (title, start, end, all_day, status, source, source_ref) VALUES (?,?,?,?,?, 'gcal', ?)"
    for i, row in enumerate([
        ("Morning call", "2026-10-05T09:00:00+02:00", "2026-10-05T10:00:00+02:00", 0, "confirmed"),
        ("Conference (3 days)", "2026-10-07", "2026-10-10", 1, "confirmed"),              # all-day: ends on the 9th (end is exclusive)
        ("One-day holiday", "2026-10-12", "2026-10-13", 1, "confirmed"),
        ("Cancelled meeting", "2026-10-05T11:00:00+02:00", "2026-10-05T12:00:00+02:00", 0, "cancelled"),
        ("Tentative lunch", "2026-10-06T12:00:00+02:00", "2026-10-06T13:00:00+02:00", 0, "tentative"),
        ("Overnight train", "2026-10-03T22:00:00+02:00", "2026-10-04T06:00:00+02:00", 0, "confirmed"),
        ("Next month", "2026-11-20T10:00:00+01:00", "2026-11-20T11:00:00+01:00", 0, "confirmed")]):
        c.execute(ev, (*row, f"e{i}"))
    c.execute("INSERT INTO deadlines (title, due_date, importance) VALUES ('Funder report', '2026-10-08', 'major')")
    c.execute("INSERT INTO deadlines (title, due_date, space, sensitivity) VALUES ('File personal tax return', '2026-10-09', 'personal', 'S3')")
    c.execute("INSERT INTO deadlines (title, due_date, status) VALUES ('Finished deadline', '2026-10-08', 'done')")
    c.execute("INSERT INTO tasks (title, due_date) VALUES ('Send run of show', '2026-10-06')")
    c.execute("INSERT INTO tasks (title, due_date, space, sensitivity, project_code) VALUES ('Dentist root canal', '2026-10-06', 'personal', 'S3', 'DENT')")
    c.execute("INSERT INTO waiting_on (description, since_date, remind_on) VALUES ('Contract from Daniel', '2026-09-20', '2026-10-07')")
    c.commit()
    return c


def titles(r, key="events"): return [x["title"] for x in r[key]]


def test_events_in_a_week_include_timed_all_day_and_overlapping_ones_but_not_cancelled_or_outside(conn):
    r = build_range(conn, date(2026, 10, 5), date(2026, 10, 11))
    assert titles(r) == ["Morning call", "Tentative lunch", "Conference (3 days)"]
    assert next(e for e in r["events"] if e["title"] == "Tentative lunch")["tentative"] is True
    assert next(e for e in r["events"] if e["title"] == "Conference (3 days)")["all_day"] is True


def test_an_event_that_started_before_the_range_but_runs_into_it_is_included(conn):
    assert titles(build_range(conn, date(2026, 10, 4), date(2026, 10, 4))) == ["Overnight train"]             # started on the 3rd, ends on the 4th
    assert "Conference (3 days)" in titles(build_range(conn, date(2026, 10, 9), date(2026, 10, 9)))            # still on during its last day
    assert "Conference (3 days)" not in titles(build_range(conn, date(2026, 10, 10), date(2026, 10, 10)))      # all-day end date is exclusive


def test_a_one_day_all_day_event_covers_exactly_that_day(conn):
    assert titles(build_range(conn, date(2026, 10, 12), date(2026, 10, 12))) == ["One-day holiday"]
    assert titles(build_range(conn, date(2026, 10, 13), date(2026, 10, 13))) == []


def test_layers_show_open_deadlines_tasks_and_chase_dates_only(conn):
    r = build_range(conn, date(2026, 10, 5), date(2026, 10, 11))
    assert titles(r, "deadlines") == ["Funder report", "Personal task"] and titles(r, "tasks") == ["Send run of show", "Personal task"]
    assert titles(r, "waiting") == ["Contract from Daniel"]
    assert next(d for d in r["deadlines"] if d["title"] == "Funder report")["importance"] == "major"


def test_personal_items_are_masked_in_every_layer(conn):
    payload = json.dumps(build_range(conn, date(2026, 10, 5), date(2026, 10, 11)))
    for secret in ("personal tax", "Dentist", "DENT", "root canal"):
        assert secret.lower() not in payload.lower(), secret
    r = build_range(conn, date(2026, 10, 5), date(2026, 10, 11))
    assert [d["masked"] for d in r["deadlines"]] == [False, True]


def test_coverage_tells_the_screen_how_far_the_data_goes(conn):
    r = build_range(conn, date(2026, 10, 5), date(2026, 10, 11))
    assert r["coverage"] == {"from": "2026-10-03", "to": "2026-11-20"}


@pytest.mark.parametrize("a,b,msg", [(date(2026, 10, 5), date(2026, 10, 4), "before"), (date(2026, 10, 1), date(2026, 11, 30), "at most")])
def test_bad_ranges_are_refused(conn, a, b, msg):
    with pytest.raises(BadRange, match=msg):
        build_range(conn, a, b)


def test_a_month_view_sized_range_is_allowed(conn):
    assert len(build_range(conn, date(2026, 9, 28), date(2026, 11, 8))["events"]) == 5                         # 42 days (a six-week month grid): the cancelled and the November event are not in it


def test_api(conn):
    from fastapi.testclient import TestClient
    from harness.main import app
    with TestClient(app) as cl:
        r = cl.get("/api/calendar?start=2026-10-05&end=2026-10-11")
        assert r.status_code == 200 and set(r.json()) >= {"events", "deadlines", "tasks", "waiting", "coverage"}
        assert cl.get("/api/calendar?start=2026-10-05&end=2026-10-01").status_code == 422
        assert cl.get("/api/calendar?start=nope&end=2026-10-01").status_code == 422
        assert cl.get("/api/calendar?start=2026-01-01&end=2026-12-31").status_code == 422

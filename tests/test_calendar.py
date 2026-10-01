import json

import pytest

from harness import db
from harness.importers.calendar import import_calendar
from tools.gcal_helper import normalize_event


@pytest.fixture
def conn(tmp_path):
    c = db.connect(tmp_path / "t.db")
    db.migrate(c)
    return c


def write(folder, events):
    (folder / "calendar_events.json").write_text(json.dumps({
        "fetched_at": "2026-10-01T08:00:00+00:00", "window_start": "2026-09-24T00:00:00+00:00",
        "window_end": "2026-12-30T00:00:00+00:00", "events": events}))


EV = lambda id, title="Meeting", start="2026-10-05T10:00:00+02:00": {
    "id": id, "title": title, "start": start, "end": None, "all_day": False, "status": "confirmed"}


def test_import_idempotent_update_and_cancel(conn, tmp_path):
    write(tmp_path, [EV("a"), EV("b", start="2026-10-06")])
    r = import_calendar(conn, tmp_path)[0]
    assert r.added == 2
    assert import_calendar(conn, tmp_path)[0].unchanged == 2
    write(tmp_path, [EV("a", title="Renamed")])           # b vanished
    r = import_calendar(conn, tmp_path)[0]
    assert r.updated == 1 and r.retired == 1
    st = {x["source_ref"]: x["status"] for x in conn.execute("SELECT * FROM calendar_events")}
    assert st["b"] == "cancelled"
    assert conn.execute("SELECT sensitivity FROM calendar_events").fetchone()[0] == "S2"


def test_missing_file_is_a_note_not_an_error(conn, tmp_path):
    r = import_calendar(conn, tmp_path)[0]
    assert r.added == 0 and "make calendar" in r.notes[0]


def test_normalize_keeps_only_safe_fields():
    raw = {"id": "x", "status": "confirmed", "summary": "Call", "start": {"dateTime": "2026-10-05T10:00:00+02:00"},
           "end": {"dateTime": "2026-10-05T11:00:00+02:00"}, "attendees": [{"email": "a@b.c"}],
           "description": "secret", "hangoutLink": "https://meet"}
    n = normalize_event(raw)
    assert set(n) == {"id", "title", "start", "end", "all_day", "status"}
    assert normalize_event({**raw, "status": "cancelled"}) is None
    assert normalize_event({"id": "y", "start": {"date": "2026-10-09"}})["all_day"] is True

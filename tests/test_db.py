from datetime import date

import pytest

from harness import db
from harness.deadlines import done_this_week, mark_done, warning_level


@pytest.fixture
def conn(tmp_path):
    c = db.connect(tmp_path / "test.db")
    db.migrate(c)
    return c


def test_migrate_is_idempotent(tmp_path):
    c = db.connect(tmp_path / "t.db")
    assert db.migrate(c) == len(db.MIGRATIONS)
    assert db.migrate(c) == len(db.MIGRATIONS)


def test_all_tables_exist(conn):
    names = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"tasks", "deadlines", "done_log", "waiting_on", "journal_entries"} <= names


def test_source_ref_unique_but_manual_allows_many(conn):
    conn.execute("INSERT INTO tasks (title, source, source_ref) VALUES ('a','suivi','r1')")
    with pytest.raises(Exception):
        conn.execute("INSERT INTO tasks (title, source, source_ref) VALUES ('b','suivi','r1')")
    # NULL source_ref (manual tasks) may repeat
    conn.execute("INSERT INTO tasks (title) VALUES ('m1')")
    conn.execute("INSERT INTO tasks (title) VALUES ('m2')")


def test_rejects_bad_space_and_tier(conn):
    with pytest.raises(Exception):
        conn.execute("INSERT INTO tasks (title, space) VALUES ('x','shared')")
    with pytest.raises(Exception):
        conn.execute("INSERT INTO tasks (title, sensitivity) VALUES ('x','S9')")


@pytest.mark.parametrize(
    "due,expected",
    [
        ("2026-09-30", "overdue"),
        ("2026-10-01", "D-3"),
        ("2026-10-04", "D-3"),
        ("2026-10-05", "D-14"),
        ("2026-10-15", "D-14"),
        ("2026-10-16", None),
    ],
)
def test_warning_levels(due, expected):
    assert warning_level(date.fromisoformat(due), date(2026, 10, 1)) == expected


def test_mark_done_logs_once(conn):
    conn.execute("INSERT INTO tasks (title) VALUES ('Send report')")
    assert mark_done(conn, "task", 1) is True
    assert mark_done(conn, "task", 1) is False  # no double counting
    assert conn.execute("SELECT status FROM tasks WHERE id=1").fetchone()[0] == "done"
    assert conn.execute("SELECT COUNT(*) FROM done_log").fetchone()[0] == 1


def test_done_this_week_counts_from_monday(conn):
    conn.execute("INSERT INTO done_log (item_type,item_id,title,done_at) VALUES ('task',1,'a','2026-09-27 10:00:00')")  # Sunday before
    conn.execute("INSERT INTO done_log (item_type,item_id,title,done_at) VALUES ('task',2,'b','2026-09-28 08:00:00')")  # Monday
    conn.execute("INSERT INTO done_log (item_type,item_id,title,done_at) VALUES ('task',3,'c','2026-10-01 09:00:00')")
    assert done_this_week(conn, date(2026, 10, 1)) == 2

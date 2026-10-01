"""Deadline warning levels and the 'done' log. Pure logic, no AI."""
import sqlite3
from datetime import date, datetime, timedelta

from harness.config import now_local

# API item type -> (table, text column, done_log item_type)
ITEM_TYPES = {
    "task": ("tasks", "title", "task"),
    "deadline": ("deadlines", "title", "deadline"),
    "waiting_on": ("waiting_on", "description", "waiting_on"),
    "email": ("emails", "subject", "email"),
}


def warning_level(due: date, today: date) -> str | None:
    """'overdue' | 'D-3' | 'D-14' | None. Computed, never stored, so it can't go stale."""
    days = (due - today).days
    if days < 0:
        return "overdue"
    if days <= 3:
        return "D-3"
    if days <= 14:
        return "D-14"
    return None


def _stamp(now: datetime | None) -> str:
    return (now or now_local()).strftime("%Y-%m-%d %H:%M:%S")


def mark_done(conn: sqlite3.Connection, item_type: str, item_id: int, now: datetime | None = None) -> bool:
    """Tick an item off and record it in the done log, atomically.

    Returns False if the item doesn't exist or was already done (no double counting).
    Tasks made from an email also mark that email handled (and the other way round), always with ONE log entry.
    """
    when = _stamp(now)
    with conn:
        if item_type == "email":
            return _email_done(conn, item_id, when)
        table, text_col, log_type = ITEM_TYPES[item_type]
        row = conn.execute(
            f"SELECT {text_col} AS t, space{', source, source_ref' if table == 'tasks' else ''} FROM {table} WHERE id = ? AND status = 'open'",
            (item_id,),
        ).fetchone()
        if row is None:
            return False
        _close(conn, table, log_type, item_id, row["t"], row["space"], when)
        if table == "tasks" and row["source"] == "email":
            conn.execute("UPDATE emails SET handled_at = ? WHERE thread_id = ? AND handled_at IS NULL", (when, row["source_ref"]))
    return True


def _close(conn, table: str, log_type: str, item_id: int, title: str, space: str, when: str) -> None:
    conn.execute(f"UPDATE {table} SET status='done', done_at=?, updated_at=datetime('now') WHERE id = ?", (when, item_id))
    conn.execute("INSERT INTO done_log (item_type, item_id, title, done_at, space) VALUES (?,?,?,?,?)",
                 (log_type, item_id, title, when, space))


def _email_done(conn, email_id: int, when: str) -> bool:
    e = conn.execute("SELECT subject, space, task_id FROM emails WHERE id = ? AND handled_at IS NULL", (email_id,)).fetchone()
    if e is None:
        return False
    conn.execute("UPDATE emails SET handled_at = ?, updated_at = datetime('now') WHERE id = ?", (when, email_id))
    task = conn.execute("SELECT title, space FROM tasks WHERE id = ? AND status = 'open'", (e["task_id"],)).fetchone() if e["task_id"] else None
    if task:                                    # its task is the single 'done' record
        _close(conn, "tasks", "task", e["task_id"], task["title"], task["space"], when)
    else:
        conn.execute("INSERT INTO done_log (item_type, item_id, title, done_at, space) VALUES ('email',?,?,?,?)",
                     (email_id, e["subject"] or "(no subject)", when, e["space"]))
    return True


def mark_undone(conn: sqlite3.Connection, item_type: str, item_id: int) -> bool:
    """Undo a tick (the checkbox toggles, and 'Reopen' in the Done list). Removes the done-log entry."""
    with conn:
        if item_type == "email":
            e = conn.execute("SELECT task_id FROM emails WHERE id = ? AND handled_at IS NOT NULL", (item_id,)).fetchone()
            if e is None:
                return False
            conn.execute("UPDATE emails SET handled_at = NULL, updated_at = datetime('now') WHERE id = ?", (item_id,))
            if e["task_id"] and conn.execute("SELECT 1 FROM tasks WHERE id = ? AND status = 'done'", (e["task_id"],)).fetchone():
                _reopen(conn, "tasks", "task", e["task_id"])
            else:
                _drop_log(conn, "email", item_id)
            return True
        table, _, log_type = ITEM_TYPES[item_type]
        if not _reopen(conn, table, log_type, item_id):
            return False
        if table == "tasks":
            r = conn.execute("SELECT source, source_ref FROM tasks WHERE id = ?", (item_id,)).fetchone()
            if r["source"] == "email":
                conn.execute("UPDATE emails SET handled_at = NULL WHERE thread_id = ?", (r["source_ref"],))
    return True


def _reopen(conn, table: str, log_type: str, item_id: int) -> bool:
    cur = conn.execute(f"UPDATE {table} SET status='open', done_at=NULL, updated_at=datetime('now') WHERE id = ? AND status = 'done'", (item_id,))
    if cur.rowcount == 0:
        return False
    _drop_log(conn, log_type, item_id)
    return True


def _drop_log(conn, log_type: str, item_id: int) -> None:
    conn.execute("DELETE FROM done_log WHERE id = (SELECT MAX(id) FROM done_log WHERE item_type=? AND item_id=?)", (log_type, item_id))


def week_start(today: date) -> date:
    return today - timedelta(days=today.weekday())


def done_this_week(conn: sqlite3.Connection, today: date) -> int:
    """Items ticked off since Monday of the current week (drives the Jet d'eau height)."""
    return conn.execute(
        "SELECT COUNT(*) FROM done_log WHERE date(done_at) >= ?", (week_start(today).isoformat(),)
    ).fetchone()[0]

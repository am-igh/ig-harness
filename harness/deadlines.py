"""Deadline warning levels and the 'done' log. Pure logic, no AI."""
import sqlite3
from datetime import date, datetime, timedelta

from harness.config import now_local

# API item type -> (table, text column, done_log item_type)
ITEM_TYPES = {
    "task": ("tasks", "title", "task"),
    "deadline": ("deadlines", "title", "deadline"),
    "waiting_on": ("waiting_on", "description", "waiting_on"),
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
    """
    table, text_col, log_type = ITEM_TYPES[item_type]
    when = _stamp(now)
    with conn:
        row = conn.execute(
            f"SELECT {text_col} AS t, space FROM {table} WHERE id = ? AND status = 'open'", (item_id,)
        ).fetchone()
        if row is None:
            return False
        conn.execute(
            f"UPDATE {table} SET status='done', done_at=?, updated_at=datetime('now') WHERE id = ?",
            (when, item_id),
        )
        conn.execute(
            "INSERT INTO done_log (item_type, item_id, title, done_at, space) VALUES (?,?,?,?,?)",
            (log_type, item_id, row["t"], when, row["space"]),
        )
    return True


def mark_undone(conn: sqlite3.Connection, item_type: str, item_id: int) -> bool:
    """Undo a tick (the checkbox toggles). Reopens the item and removes its done-log entry."""
    table, _, log_type = ITEM_TYPES[item_type]
    with conn:
        cur = conn.execute(
            f"UPDATE {table} SET status='open', done_at=NULL, updated_at=datetime('now') "
            "WHERE id = ? AND status = 'done'", (item_id,),
        )
        if cur.rowcount == 0:
            return False
        conn.execute(
            "DELETE FROM done_log WHERE id = (SELECT MAX(id) FROM done_log WHERE item_type=? AND item_id=?)",
            (log_type, item_id),
        )
    return True


def week_start(today: date) -> date:
    return today - timedelta(days=today.weekday())


def done_this_week(conn: sqlite3.Connection, today: date) -> int:
    """Items ticked off since Monday of the current week (drives the Jet d'eau height)."""
    return conn.execute(
        "SELECT COUNT(*) FROM done_log WHERE date(done_at) >= ?", (week_start(today).isoformat(),)
    ).fetchone()[0]

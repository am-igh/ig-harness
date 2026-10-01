"""Deadline warning levels and the 'done' log. Pure logic, no AI."""
import sqlite3
from datetime import date, timedelta


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


def mark_done(conn: sqlite3.Connection, table: str, item_id: int) -> bool:
    """Tick an item off and record it in the done log, atomically.

    Returns False if the item doesn't exist or was already done (no double counting).
    """
    if table not in ("tasks", "deadlines"):
        raise ValueError(f"cannot mark {table} done")
    item_type = "task" if table == "tasks" else "deadline"
    with conn:
        row = conn.execute(
            f"SELECT title AS t, space FROM {table} WHERE id = ? AND status = 'open'",
            (item_id,),
        ).fetchone()
        if row is None:
            return False
        conn.execute(
            f"UPDATE {table} SET status='done', done_at=datetime('now'), "
            "updated_at=datetime('now') WHERE id = ?",
            (item_id,),
        )
        conn.execute(
            "INSERT INTO done_log (item_type, item_id, title, space) VALUES (?,?,?,?)",
            (item_type, item_id, row["t"], row["space"]),
        )
    return True


def done_this_week(conn: sqlite3.Connection, today: date) -> int:
    """Items ticked off since Monday of the current week (drives the Jet d'eau height)."""
    monday = today - timedelta(days=today.weekday())
    return conn.execute(
        "SELECT COUNT(*) FROM done_log WHERE date(done_at) >= ?", (monday.isoformat(),)
    ).fetchone()[0]

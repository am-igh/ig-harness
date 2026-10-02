"""What the calendar widget shows for a date range: her Google Calendar events, plus deadlines, tasks and
chase dates as optional layers. Read-only queries. Personal items are masked like everywhere else."""
import sqlite3
from datetime import date, timedelta

from harness import privacy

MAX_DAYS = 45


class BadRange(ValueError):
    pass


def _span(r: sqlite3.Row) -> tuple[str, str]:
    """First and last calendar day an event covers (all-day events end the day BEFORE their stored end date)."""
    first = r["start"][:10]
    if r["all_day"]:
        last = (date.fromisoformat(r["end"][:10]) - timedelta(days=1)).isoformat() if r["end"] else first
        return first, max(first, last)
    return first, max(first, (r["end"] or r["start"])[:10])


def build_range(conn: sqlite3.Connection, start: date, end: date) -> dict:
    if end < start:
        raise BadRange("The end is before the start")
    if (end - start).days + 1 > MAX_DAYS:
        raise BadRange(f"Ask for at most {MAX_DAYS} days at a time")
    s, e = start.isoformat(), end.isoformat()
    events = []
    for r in conn.execute("SELECT * FROM calendar_events WHERE status != 'cancelled' AND substr(start,1,10) <= ? ORDER BY start", (e,)):
        first, last = _span(r)
        if last >= s:
            events.append({"id": r["id"], "title": r["title"], "start": r["start"], "end": r["end"], "all_day": bool(r["all_day"]), "tentative": r["status"] == "tentative"})

    def item(type_: str, r: sqlite3.Row, due: str, **extra) -> dict:
        personal = privacy.is_personal(r["space"])
        return {"type": type_, "id": r["id"], "title": privacy.label(type_) if personal else r["title"], "due": due, "masked": personal, **extra}

    deadlines = [item("deadline", r, r["due_date"], importance=r["importance"]) for r in conn.execute(
        "SELECT id, title, due_date, importance, space FROM deadlines WHERE status='open' AND due_date BETWEEN ? AND ? ORDER BY due_date, id", (s, e))]
    tasks = [item("task", r, r["due_date"]) for r in conn.execute(
        "SELECT id, title, due_date, space FROM tasks WHERE status='open' AND due_date BETWEEN ? AND ? ORDER BY due_date, id", (s, e))]
    waiting = [item("waiting_on", r, r["remind_on"]) for r in conn.execute(
        "SELECT id, description AS title, remind_on, space FROM waiting_on WHERE status='open' AND remind_on BETWEEN ? AND ? ORDER BY remind_on, id", (s, e))]
    cov = conn.execute("SELECT MIN(substr(start,1,10)), MAX(substr(start,1,10)) FROM calendar_events WHERE status != 'cancelled'").fetchone()
    return {"start": s, "end": e, "events": events, "deadlines": deadlines, "tasks": tasks, "waiting": waiting,
            "coverage": {"from": cov[0], "to": cov[1]}}

"""Hours this week, from her hours.csv (read-only). Hours need an evidence pointer and an entered_on date: entries that lack them, that
name a project the Codes sheet does not know, or that were entered more than a week after the day they are for are flagged."""
import sqlite3
from datetime import date, timedelta

LATE_DAYS = 7


def week_bounds(day: date) -> tuple[date, date]:
    start = day - timedelta(days=day.weekday())
    return start, start + timedelta(days=6)


def problems(e: dict, known: set[str]) -> list[str]:
    out = []
    if not (e["evidence"] or "").strip():
        out.append("no evidence")
    if not e["entered_on"]:
        out.append("no entered_on date")
    elif (date.fromisoformat(e["entered_on"]) - date.fromisoformat(e["date"])).days > LATE_DAYS:
        out.append(f"entered {(date.fromisoformat(e['entered_on']) - date.fromisoformat(e['date'])).days} days later")
    if e["hours"] is None or e["hours"] <= 0:
        out.append("hours missing or not positive")
    if not e["project"]:
        out.append("no project")
    elif known and e["project"] not in known:
        out.append(f"unknown project {e['project']}")
    return out


def week_summary(conn: sqlite3.Connection, today: date, any_day: date | None = None) -> dict:
    start, end = week_bounds(any_day or today)
    known = {r[0] for r in conn.execute("SELECT code FROM project_codes")}
    entries = []
    for r in conn.execute("SELECT * FROM hours WHERE date BETWEEN ? AND ? ORDER BY date, project, rowid", (start.isoformat(), end.isoformat())):
        e = {k: r[k] for k in ("date", "project", "budget_line", "hours", "description", "evidence", "source", "entered_on")}
        e["problems"] = problems(e, known)
        entries.append(e)
    by: dict[str, float] = {}
    for e in entries:
        by[e["project"] or "?"] = by.get(e["project"] or "?", 0) + (e["hours"] or 0)
    working = [start + timedelta(days=i) for i in range(5) if start + timedelta(days=i) <= today]
    logged_days = {e["date"] for e in entries}
    return {"week_start": start.isoformat(), "week_end": end.isoformat(), "is_current": start <= today <= end,
            "total": round(sum(e["hours"] or 0 for e in entries), 2), "by_project": [{"project": p, "hours": round(h, 2)} for p, h in sorted(by.items(), key=lambda x: (-x[1], x[0]))],
            "entries": entries, "flagged": sum(1 for e in entries if e["problems"]),
            "days_without": [d.isoformat() for d in working if d.isoformat() not in logged_days] if start <= today else [],
            "prev": (start - timedelta(days=7)).isoformat(), "next": (start + timedelta(days=7)).isoformat() if start + timedelta(days=7) <= today else None,
            "has_any": conn.execute("SELECT COUNT(*) FROM hours").fetchone()[0] > 0}

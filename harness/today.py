"""Assembles what the Today tab shows. Read-only queries; no AI."""
import sqlite3
from datetime import date, datetime, timedelta

from harness.config import now_local
from harness.deadlines import done_this_week, warning_level, week_start

LAKE_DAYS = 47          # lake band runs from today to today + 47 days (30 Sep -> 15 Nov in the mockup)
UPCOMING_DAYS = 7


def _item(r: sqlite3.Row, type_: str, today: date) -> dict:
    due = r["due"]
    d = date.fromisoformat(due) if due else None
    if type_ == "deadline":
        weight = "major" if r["importance"] == "major" else "hard"
    elif type_ == "waiting_on":
        weight = "waiting"
    else:
        weight = "soft"
    return {
        "key": f"{type_}:{r['id']}", "type": type_, "id": r["id"], "title": r["title"],
        "code": r["code"], "weight": weight, "person": r["person"] if "person" in r.keys() else None,
        "personal": r["space"] == "personal", "due": due,
        "days_overdue": (today - d).days if d and d < today else 0,
        "done": r["status"] == "done",
    }


def _items(conn, today: date, lo: str | None, hi: str) -> list[dict]:
    """Open items with due in [lo, hi] (lo None = no lower bound), plus items ticked off today."""
    t, hi_ = today.isoformat(), hi
    lo_clause = "AND due >= :lo" if lo else ""
    params = {"t": t, "hi": hi_, "lo": lo}
    out = []
    sources = [
        ("task", "SELECT id, title, project_code AS code, due_date AS due, status, space, NULL AS person, NULL AS importance FROM tasks"),
        ("deadline", "SELECT id, title, project_code AS code, due_date AS due, status, space, NULL AS person, importance FROM deadlines"),
        ("waiting_on", "SELECT id, description AS title, NULL AS code, remind_on AS due, status, space, person, NULL AS importance FROM waiting_on"),
    ]
    for type_, base in sources:
        # done-today rows only when looking at today's list (lo is None)
        done_clause = "OR (status='done' AND substr(done_at,1,10) = :t)" if lo is None else ""
        rows = conn.execute(
            f"{base} WHERE (status='open' AND due IS NOT NULL AND due <= :hi {lo_clause}) {done_clause} "
            "ORDER BY due, id", params
        ).fetchall()
        out += [_item(r, type_, today) for r in rows]
    out.sort(key=lambda i: (i["due"] or "9999", i["id"]))
    return out


def _events_today(conn, today: date) -> list[dict]:
    t = today.isoformat()
    out = []
    for r in conn.execute("SELECT * FROM calendar_events WHERE status!='cancelled' AND substr(start,1,10) <= ? ORDER BY start", (t,)):
        if r["all_day"]:
            if not (r["start"] <= t < (r["end"] or r["start"])) and r["start"] != t:
                continue
        elif r["start"][:10] != t:
            continue
        out.append({"id": r["id"], "title": r["title"], "start": r["start"], "end": r["end"], "all_day": bool(r["all_day"])})
    return sorted(out, key=lambda e: (not e["all_day"], e["start"]))


def _next_event(conn, now: datetime) -> dict | None:
    rows = conn.execute("SELECT * FROM calendar_events WHERE status!='cancelled' AND all_day=0 AND start >= ? ORDER BY start LIMIT 40",
                        ((now - timedelta(days=1)).date().isoformat(),)).fetchall()
    for r in rows:
        if datetime.fromisoformat(r["start"]) > now:
            return {"title": r["title"], "start": r["start"]}
    return None


def build_today(conn: sqlite3.Connection, now: datetime | None = None) -> dict:
    now = now or now_local()
    today = now.date()
    t = today.isoformat()
    upcoming_hi = (today + timedelta(days=UPCOMING_DAYS)).isoformat()

    lake_hi = (today + timedelta(days=LAKE_DAYS)).isoformat()
    lake = []
    ticks = set()
    for r in conn.execute("SELECT * FROM deadlines WHERE status='open' AND due_date >= ? AND due_date <= ? ORDER BY due_date, id", (t, lake_hi)):
        due = date.fromisoformat(r["due_date"])
        lake.append({"id": r["id"], "title": r["title"], "due": r["due_date"], "importance": r["importance"],
                     "kind": r["kind"], "code": r["project_code"], "personal": r["space"] == "personal",
                     "warning": warning_level(due, today)})
        for n in (14, 3):  # D-14 / D-3 warning ticks
            w = due - timedelta(days=n)
            if today <= w <= today + timedelta(days=LAKE_DAYS):
                ticks.add(w.isoformat())

    undated = conn.execute("SELECT COUNT(*) FROM tasks WHERE status='open' AND due_date IS NULL").fetchone()[0]
    return {
        "now": now.isoformat(timespec="minutes"), "today": t, "week_start": week_start(today).isoformat(),
        "done_this_week": done_this_week(conn, today),
        "today_items": _items(conn, today, None, t),
        "upcoming_items": _items(conn, today, (today + timedelta(days=1)).isoformat(), upcoming_hi),
        "undated_tasks": undated,
        "lake": lake, "ticks": sorted(ticks),
        "events_today": _events_today(conn, today), "next_event": _next_event(conn, now),
    }


def done_list(conn: sqlite3.Connection, today: date) -> list[dict]:
    rows = conn.execute("SELECT title, done_at, space FROM done_log WHERE date(done_at) >= ? ORDER BY done_at DESC",
                        (week_start(today).isoformat(),)).fetchall()
    return [{"title": r["title"], "done_at": r["done_at"], "personal": r["space"] == "personal"} for r in rows]


def deadline_detail(conn: sqlite3.Connection, deadline_id: int, today: date) -> dict | None:
    r = conn.execute("SELECT * FROM deadlines WHERE id = ?", (deadline_id,)).fetchone()
    if r is None:
        return None
    due = date.fromisoformat(r["due_date"])
    code = r["project_code"]
    related = []
    if code:
        for tbl, label, col in (("tasks", "TASK", "title"), ("waiting_on", "WAITING", "description")):
            extra = "project_code" if tbl == "tasks" else None
            if extra is None:
                continue  # waiting_on has no project code
            for x in conn.execute(f"SELECT {col} AS t, due_date FROM {tbl} WHERE status='open' AND project_code=? ORDER BY due_date LIMIT 5", (code,)):
                related.append({"type": label, "label": x["t"], "meta": x["due_date"] or ""})
        for x in conn.execute("SELECT title, due_date FROM deadlines WHERE status='open' AND project_code=? AND id!=? ORDER BY due_date LIMIT 5", (code, deadline_id)):
            related.append({"type": "DEADLINE", "label": x["title"], "meta": x["due_date"]})
    return {
        "id": r["id"], "title": r["title"], "due": r["due_date"], "kind": r["kind"],
        "importance": r["importance"], "code": code, "status": r["status"], "personal": r["space"] == "personal",
        "source": r["source"], "days_left": (due - today).days,
        "warn_d14": (due - timedelta(days=14)).isoformat(), "warn_d3": (due - timedelta(days=3)).isoformat(),
        "related": related,
    }

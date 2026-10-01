"""Assembles what the Today tab shows. Read-only queries; no AI."""
import sqlite3
from datetime import date, datetime, timedelta

from harness.config import now_local
from harness.deadlines import done_this_week, warning_level, week_start
from harness.items import overrides_for

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
        "done": r["status"] == "done", "done_at": r["done_at"], "edited": None,
    }


def _items(conn, today: date, lo: str | None, hi: str) -> list[dict]:
    """Open items with due in [lo, hi] (lo None = no lower bound), plus items ticked off today."""
    t, hi_ = today.isoformat(), hi
    lo_clause = "AND due >= :lo" if lo else ""
    params = {"t": t, "hi": hi_, "lo": lo}
    out = []
    sources = [
        ("task", "SELECT id, title, project_code AS code, due_date AS due, status, done_at, space, NULL AS person, NULL AS importance FROM tasks"),
        ("deadline", "SELECT id, title, project_code AS code, due_date AS due, status, done_at, space, NULL AS person, importance FROM deadlines"),
        ("waiting_on", "SELECT id, description AS title, NULL AS code, remind_on AS due, status, done_at, space, person, NULL AS importance FROM waiting_on"),
    ]
    for type_, base in sources:
        # done-today rows only when looking at today's list (lo is None)
        done_clause = "OR (status='done' AND substr(done_at,1,10) = :t)" if lo is None else ""
        rows = conn.execute(
            f"{base} WHERE (status='open' AND due IS NOT NULL AND due <= :hi {lo_clause}) {done_clause} "
            "ORDER BY due, id", params
        ).fetchall()
        ov = overrides_for(conn, {"task": "tasks", "deadline": "deadlines", "waiting_on": "waiting_on"}[type_])
        for r in rows:
            it = _item(r, type_, today)
            if r["id"] in ov:                      # edited here: remember what the source still says
                it["edited"] = {"title": ov[r["id"]].get("title"), "due": ov[r["id"]].get("due"),
                                "title_changed": "title" in ov[r["id"]], "due_changed": "due" in ov[r["id"]]}
            out.append(it)
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
        "later_items": _items(conn, today, (today + timedelta(days=UPCOMING_DAYS + 1)).isoformat(), "9999-12-31")[:40],
        "undated_tasks": undated,
        "lake": lake, "ticks": sorted(ticks),
        "events_today": _events_today(conn, today), "next_event": _next_event(conn, now),
    }


def done_list(conn: sqlite3.Connection, today: date, days: int | None = 7, q: str = "") -> list[dict]:
    """Everything marked done, newest first, with date and time. days=None means all time.

    Items closed in Suivi (imported as done) are listed too, with a date only; they can't be reopened
    here because the next import would close them again."""
    like = f"%{q.strip()}%"
    cutoff = (today - timedelta(days=days)).isoformat() if days else "0000-00-00"
    out = []
    for r in conn.execute("SELECT item_type, item_id, title, done_at, space FROM done_log "
                          "WHERE substr(done_at,1,10) >= ? AND title LIKE ? ORDER BY done_at DESC, id DESC", (cutoff, like)):
        out.append({"key": f"{r['item_type']}:{r['item_id']}", "type": r["item_type"], "id": r["item_id"], "title": r["title"],
                    "done_at": r["done_at"], "personal": r["space"] == "personal", "reopenable": True, "via": None})
    for type_, table, col in (("task", "tasks", "title"), ("deadline", "deadlines", "title"), ("waiting_on", "waiting_on", "description")):
        for r in conn.execute(
            f"SELECT id, {col} AS t, done_at, space, source FROM {table} WHERE status='done' AND done_at IS NOT NULL "
            f"AND substr(done_at,1,10) >= ? AND {col} LIKE ? AND source != 'manual' "
            f"AND NOT EXISTS (SELECT 1 FROM done_log d WHERE d.item_type=? AND d.item_id={table}.id)", (cutoff, like, type_)):
            out.append({"key": f"{type_}:{r['id']}", "type": type_, "id": r["id"], "title": r["t"], "done_at": r["done_at"],
                        "personal": r["space"] == "personal", "reopenable": False, "via": "Suivi" if r["source"] == "suivi" else r["source"]})
    out.sort(key=lambda x: x["done_at"], reverse=True)
    return out


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

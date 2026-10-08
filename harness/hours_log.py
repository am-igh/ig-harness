"""Logging time when she ticks off a project to-do. Ticking a task or deadline that belongs to a work project can ask: how much time did this take, and on which day(s)? What she enters
becomes hours entries through the SAME approved path as the Friday hours pass (hour_proposals -> approval -> outbox -> tools/hours_writer.py appends to hours.csv with a backup).
Her clicking "Log hours" is the approval of those entries. Nothing is asked for personal items, emails or threads, and nothing is invented: no hours are guessed.
In the demo instance there is no writer, so the entry is shown in the hours table straight away."""
import hashlib
import os
import sqlite3
from datetime import date, datetime, timedelta

from harness import hours_pass as HP
from harness.config import DATA_DIR, now_local
from harness.hours import week_bounds

TABLES = {"task": ("tasks", "title"), "deadline": ("deadlines", "title")}
MAX_ENTRIES = 10
MAX_DAYS_BACK = 120


def prompt_enabled(conn) -> bool:
    r = conn.execute("SELECT value FROM draft_settings WHERE key='hours_prompt'").fetchone()
    return not r or r["value"] != "off"


def set_prompt(conn, on: bool) -> None:
    with conn:
        conn.execute("INSERT INTO draft_settings (key, value, source) VALUES ('hours_prompt', ?, 'edited') ON CONFLICT (key) DO UPDATE SET value=excluded.value, source='edited'", ("on" if on else "off",))


def _item(conn, item_type: str, item_id: int):
    if item_type not in TABLES:
        return None
    table, col = TABLES[item_type]
    return conn.execute(f"SELECT id, {col} AS title, project_code, space, status, done_at FROM {table} WHERE id = ?", (item_id,)).fetchone()


def ask(conn, item_type: str, item_id: int, today: date | None = None) -> dict:
    """Should the screen ask about time for this ticked item? Only for a finished work item that belongs to a project."""
    today = today or now_local().date()
    if not prompt_enabled(conn):
        return {"ask": False, "reason": "off"}
    r = _item(conn, item_type, item_id)
    if r is None or r["status"] != "done" or r["space"] != "work":
        return {"ask": False, "reason": "not a finished work item"}
    code = next((c for c in HP._codes(r["project_code"]) if c in HP._projects(conn)), None)
    if not code:
        return {"ask": False, "reason": "no project"}
    done = (r["done_at"] or today.isoformat())[:10]
    logged = conn.execute("SELECT COALESCE(SUM(hours), 0) FROM hour_proposals WHERE source = 'todo' AND status IN ('approved','written') AND evidence LIKE ?", (f"Harness to-do #{item_id} (%",)).fetchone()[0]
    return {"ask": True, "project": code, "title": r["title"], "date": done if done <= today.isoformat() else today.isoformat(), "already_logged": round(logged, 2)}


def log(conn, item_type: str, item_id: int, entries: list[dict], description: str | None = None, today: date | None = None, data_dir=None) -> dict:
    """entries: [{'date': 'YYYY-MM-DD', 'hours': 1.5}, ...]. Each becomes an approved hours entry. Raises ValueError with a plain message."""
    today = today or now_local().date()
    info = ask(conn, item_type, item_id, today)
    if not info["ask"] and info.get("reason") != "off":
        raise ValueError("Hours can only be logged for a finished work to-do that belongs to a project")
    r = _item(conn, item_type, item_id)
    code = next((c for c in HP._codes(r["project_code"]) if c in HP._projects(conn)), None)
    if r is None or not code:
        raise ValueError("This to-do does not belong to a project")
    if not entries or len(entries) > MAX_ENTRIES:
        raise ValueError(f"Enter between one and {MAX_ENTRIES} days")
    clean, seen = [], set()
    for e in entries:
        try:
            day = date.fromisoformat(str(e.get("date"))[:10])
            h = float(str(e.get("hours")).replace(",", "."))
        except (TypeError, ValueError):
            raise ValueError("Each line needs a date and a number of hours")
        if day > today:
            raise ValueError("That day has not happened yet")
        if day < today - timedelta(days=MAX_DAYS_BACK):
            raise ValueError("That is too long ago to log from here: use the Friday hours pass or your own file")
        if not 0 < h <= 14:
            raise ValueError("Hours must be between 0 and 14 for a day")
        if day in seen:
            raise ValueError("Each day can appear once: add the hours together")
        seen.add(day)
        clean.append((day, round(h, 2)))
    done = (r["done_at"] or today.isoformat())[:10]
    desc = (description or r["title"] or "").strip()[:300]
    evidence = f"Harness to-do #{item_id} (done {done})"
    pids = []
    for day, h in clean:
        pkey = hashlib.sha256(f"todo:{item_type}:{item_id}:{day.isoformat()}".encode()).hexdigest()[:24]
        if conn.execute("SELECT 1 FROM hour_proposals WHERE pkey = ?", (pkey,)).fetchone():
            raise ValueError(f"Time for {day.isoformat()} is already logged for this to-do")
        with conn:
            cur = conn.execute("INSERT INTO hour_proposals (pkey, week_start, date, project, hours, description, evidence, source, basis) VALUES (?,?,?,?,?,?,?,'todo',?)",
                               (pkey, week_bounds(day)[0].isoformat(), day.isoformat(), code, h, desc, evidence, "you entered it when you ticked the to-do off"))
        pids.append(cur.lastrowid)
    for pid in pids:
        HP.approve(conn, pid, today, data_dir)                                                         # her click on "Log hours" is the approval
        if os.environ.get("IG_DEMO") == "1":
            _demo_write(conn, pid, today)
    return {"logged": len(pids), "hours": round(sum(h for _, h in clean), 2), "project": code, "evidence": evidence, "queued": os.environ.get("IG_DEMO") != "1"}


def _demo_write(conn, pid: int, today: date) -> None:
    """The demo has no Mac-side writer: show the entry in the hours table at once."""
    r = conn.execute("SELECT * FROM hour_proposals WHERE id = ?", (pid,)).fetchone()
    key = hashlib.sha256(f"demo-hours:{pid}".encode()).hexdigest()[:32]
    with conn:
        conn.execute("INSERT OR IGNORE INTO hours (row_key, date, project, hours, description, evidence, source, entered_on) VALUES (?,?,?,?,?,?,'harness',?)",
                     (key, r["date"], r["project"], r["hours"], r["description"], r["evidence"], today.isoformat()))
        conn.execute("UPDATE hour_proposals SET status='written', written_at=datetime('now'), result='demo' WHERE id=?", (pid,))

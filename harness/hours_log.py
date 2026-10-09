"""Logging time when she ticks off a project to-do. Ticking a task or deadline that belongs to a work project can ask: how much time did this take, and on which day(s)?
Her clicking "Log hours" is the approval. Each day becomes (1) a row in the Suivi journal WITH the hours figure (tools/suivi_writer.py, the same safeguarded writer as her notes), and (2) an entry in
hours.csv (tools/hours_writer.py, the same path as the Friday hours pass, with its backup and checks) whose EVIDENCE is that journal row's id (for example "Suivi J-2026-041"). The hours entry is
held back until Suivi has given the row its id (`release`, run every few seconds by the API). Nothing is asked for personal items, emails or threads, and no hours are ever guessed.
In the demo instance there are no writers, so the journal row and the hours entry are shown at once."""
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
    logged = conn.execute("SELECT COALESCE(SUM(hours), 0) FROM todo_journal WHERE item_type = ? AND item_id = ?", (item_type, item_id)).fetchone()[0]
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
    evidence = f"harness-to-do:{item_id} (done {done})"                                  # what the Suivi journal row cites
    for day, h in clean:
        if conn.execute("SELECT 1 FROM todo_journal WHERE item_type = ? AND item_id = ? AND date = ?", (item_type, item_id, day.isoformat())).fetchone():
            raise ValueError(f"Time for {day.isoformat()} is already logged for this to-do")
    demo = os.environ.get("IG_DEMO") == "1"
    pids = []
    for day, h in clean:
        pkey = hashlib.sha256(f"todo:{item_type}:{item_id}:{day.isoformat()}".encode()).hexdigest()[:24]
        with conn:
            cur = conn.execute("INSERT INTO hour_proposals (pkey, week_start, date, project, hours, description, evidence, source, basis) VALUES (?,?,?,?,?,?,?,'todo',?)",
                               (pkey, week_bounds(day)[0].isoformat(), day.isoformat(), code, h, desc, f"Suivi (journal id pending): {evidence}", "you entered it when you ticked the to-do off"))
            pid = cur.lastrowid
            conn.execute("INSERT INTO todo_journal (item_type, item_id, date, project, hours, description, evidence, proposal_id) VALUES (?,?,?,?,?,?,?,?)", (item_type, item_id, day.isoformat(), code, h, desc, evidence, pid))
        HP.approve(conn, pid, today, data_dir, queue_now=False)                              # her click is the approval; the writer gets it once the journal id exists
        pids.append(pid)
        if demo:
            _demo_write(conn, pid, today)
    return {"logged": len(pids), "hours": round(sum(h for _, h in clean), 2), "project": code, "evidence": "Suivi journal row (id given when it is written)", "queued": not demo}


def release(conn, data_dir=None) -> int:
    """For every logged day whose Suivi journal row now has its id: make that id the evidence of the hours entry and hand the entry to the hours writer. Returns how many were released."""
    from harness import suivi_export as SE
    data_dir = data_dir or DATA_DIR
    pending = conn.execute("SELECT * FROM todo_journal WHERE status = 'pending'").fetchall()
    if not pending:
        return 0
    state = SE.read_state(data_dir).get("todo_hours", {})
    n = 0
    for r in pending:
        hit = state.get(str(r["id"]))
        if not hit:
            continue
        jid = hit["journal_id"]
        with conn:
            conn.execute("UPDATE todo_journal SET status='released', journal_id=? WHERE id=?", (jid, r["id"]))
            conn.execute("UPDATE hour_proposals SET evidence=? WHERE id=? AND status='approved'", (f"Suivi {jid}", r["proposal_id"]))
        row = conn.execute("SELECT decided_at FROM hour_proposals WHERE id = ?", (r["proposal_id"],)).fetchone()
        HP.queue(r["proposal_id"], row["decided_at"] or now_local().isoformat(timespec="seconds"), data_dir)
        n += 1
    return n


def _demo_write(conn, pid: int, today: date) -> None:
    """The demo has no Mac-side writers: show the Suivi journal row and the hours entry at once."""
    r = conn.execute("SELECT * FROM hour_proposals WHERE id = ?", (pid,)).fetchone()
    t = conn.execute("SELECT * FROM todo_journal WHERE proposal_id = ?", (pid,)).fetchone()
    n = conn.execute("SELECT COUNT(*) FROM journal_entries WHERE source = 'demo-hours'").fetchone()[0]
    jid = f"J-{today.year}-{101 + n:03d}"
    key = hashlib.sha256(f"demo-hours:{pid}".encode()).hexdigest()[:32]
    with conn:
        conn.execute("INSERT OR IGNORE INTO journal_entries (entry_date, text, project_code, source, source_ref, entry_type, evidence, hours) VALUES (?,?,?,'demo-hours',?, 'work',?,?)",
                     (r["date"], r["description"], r["project"], jid, t["evidence"], r["hours"]))
        conn.execute("INSERT OR IGNORE INTO hours (row_key, date, project, hours, description, evidence, source, entered_on) VALUES (?,?,?,?,?,?,'harness',?)",
                     (key, r["date"], r["project"], r["hours"], r["description"], f"Suivi {jid}", today.isoformat()))
        conn.execute("UPDATE hour_proposals SET status='written', evidence=?, written_at=datetime('now'), result='demo' WHERE id=?", (f"Suivi {jid}", pid))
        conn.execute("UPDATE todo_journal SET status='released', journal_id=? WHERE proposal_id=?", (jid, pid))

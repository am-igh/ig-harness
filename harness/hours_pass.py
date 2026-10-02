"""The Friday hours pass, API side: suggest hour entries for a week from what the harness already knows (Suivi journal rows, calendar events
tagged [CODE]), each with the evidence pointer her hours.csv requires; she edits and approves them one by one; the Mac-side writer
(tools/hours_writer.py) then APPENDS the approved rows to hours.csv. This module never writes to hours.csv (it is mounted read-only here).

Nothing is invented: a journal row without an hours figure is suggested with the hours left blank for her to fill in; a calendar event
is suggested with its length. Work only, projects only (not threads), and anything already in hours.csv (same evidence) is not suggested again."""
import hashlib
import json
import re
import sqlite3
from datetime import date, datetime, timedelta
from pathlib import Path

from harness.config import DATA_DIR, now_local
from harness.hours import week_bounds

OUTBOX, DONE = "hours/outbox", "hours/done"
_TAG = re.compile(r"\[([A-Za-z0-9]{2,10})\]")


def _codes(raw: str | None) -> list[str]:
    return [c.strip().upper() for c in (raw or "").split(";") if c.strip()]


def _projects(conn) -> set[str]:
    return {r[0] for r in conn.execute("SELECT code FROM project_codes WHERE kind = 'project' AND domain != 'P'")}


def _already_logged(conn, evidence: str, day: str, project: str) -> bool:
    e = evidence.lower()
    return any(e in (r[0] or "").lower() for r in conn.execute("SELECT evidence FROM hours WHERE date = ? AND project = ?", (day, project))) or \
        any(e in (r[0] or "").lower() for r in conn.execute("SELECT evidence FROM hours"))


def _event_hours(start: str, end: str | None) -> float | None:
    try:
        a, b = datetime.fromisoformat(start), datetime.fromisoformat(end or "")
        h = (b - a).total_seconds() / 3600
        return round(h * 4) / 4 if 0 < h <= 14 else None
    except ValueError:
        return None


def find_week(conn: sqlite3.Connection, today: date, any_day: date | None = None) -> int:
    """Create suggestions for the week containing `any_day` (default: this week). Returns how many new ones were added."""
    start, end = week_bounds(any_day or today)
    last = min(end, today)
    projects, added = _projects(conn), 0

    def add(pkey, day, project, hours, desc, evidence, source, basis):
        nonlocal added
        if _already_logged(conn, evidence, day, project):
            return
        with conn:
            cur = conn.execute("INSERT OR IGNORE INTO hour_proposals (pkey, week_start, date, project, hours, description, evidence, source, basis) VALUES (?,?,?,?,?,?,?,?,?)",
                               (hashlib.sha256(pkey.encode()).hexdigest()[:24], start.isoformat(), day, project, hours, desc[:300], evidence[:300], source, basis))
        added += cur.rowcount
    for r in conn.execute("SELECT * FROM journal_entries WHERE space='work' AND entry_date BETWEEN ? AND ? AND project_code IS NOT NULL ORDER BY entry_date, id", (start.isoformat(), last.isoformat())):
        for code in [c for c in _codes(r["project_code"]) if c in projects][:1]:
            ev = f"Suivi {r['source_ref']}" if r["source_ref"] else f"Suivi journal {r['entry_date']}"
            add(f"journal:{r['id']}:{code}", r["entry_date"], code, r["hours"], r["text"], ev, "journal",
                "the hours figure in your journal row" if r["hours"] else "your journal row has no hours figure: please enter your own estimate")
    for r in conn.execute("SELECT * FROM calendar_events WHERE space='work' AND all_day=0 AND status!='cancelled' AND substr(start,1,10) BETWEEN ? AND ? ORDER BY start", (start.isoformat(), last.isoformat())):
        for tag in _TAG.findall(r["title"]):
            if tag.upper() in projects:
                h = _event_hours(r["start"], r["end"])
                add(f"event:{r['id']}:{tag.upper()}", r["start"][:10], tag.upper(), h, re.sub(r"\[[A-Za-z0-9]+\]\s*", "", r["title"]).strip() or r["title"],
                    f"Calendar: {r['title']} {r['start'][:10]}", "calendar", "the length of the calendar event" if h else "the event's length could not be read: please enter your own estimate")
    return added


def week_items(conn: sqlite3.Connection, today: date, any_day: date | None = None) -> list[dict]:
    start, _ = week_bounds(any_day or today)
    cutoff = f"-{30} minutes"
    return [dict(r) for r in conn.execute(
        "SELECT * FROM hour_proposals WHERE week_start = ? AND status != 'skipped' AND NOT (status = 'written' AND written_at < datetime('now', ?)) ORDER BY date, id", (start.isoformat(), cutoff))]


def edit(conn: sqlite3.Connection, pid: int, fields: dict, today: date) -> dict:
    r = conn.execute("SELECT * FROM hour_proposals WHERE id = ?", (pid,)).fetchone()
    if r is None:
        raise KeyError(pid)
    if r["status"] != "proposed":
        raise ValueError("This suggestion has already been decided")
    clean = {}
    if "hours" in fields:
        try:
            h = float(str(fields["hours"]).replace(",", ".")) if fields["hours"] not in (None, "") else None
        except ValueError:
            raise ValueError("Hours must be a number")
        if h is not None and not 0 < h <= 14:
            raise ValueError("Hours must be between 0 and 14")
        clean["hours"] = h
    if "project" in fields:
        p = (fields["project"] or "").strip().upper()
        if p and p not in _projects(conn):
            raise ValueError("Unknown project code")
        clean["project"] = p or None
    for k in ("description", "budget_line"):
        if k in fields:
            clean[k] = (fields[k] or "").strip()[:300] or None
    if clean:
        with conn:
            conn.execute(f"UPDATE hour_proposals SET {', '.join(f'{k}=?' for k in clean)} WHERE id=?", [*clean.values(), pid])
    return dict(conn.execute("SELECT * FROM hour_proposals WHERE id = ?", (pid,)).fetchone())


def approve(conn: sqlite3.Connection, pid: int, today: date, data_dir: Path | None = None) -> dict:
    data_dir = data_dir or DATA_DIR
    r = conn.execute("SELECT * FROM hour_proposals WHERE id = ?", (pid,)).fetchone()
    if r is None:
        raise KeyError(pid)
    if r["status"] != "proposed":
        raise ValueError("This suggestion has already been decided")
    if not r["hours"] or not 0 < r["hours"] <= 14:
        raise ValueError("Enter the hours first")
    if not r["project"] or r["project"] not in _projects(conn):
        raise ValueError("Choose a project")
    if not (r["evidence"] or "").strip() or not (r["description"] or "").strip():
        raise ValueError("An hours entry needs a description and an evidence pointer")
    if date.fromisoformat(r["date"]) > today:
        raise ValueError("That day has not happened yet")
    (data_dir / OUTBOX).mkdir(parents=True, exist_ok=True)
    when = now_local().isoformat(timespec="seconds")
    with conn:
        conn.execute("UPDATE hour_proposals SET status='approved', decided_at=? WHERE id=?", (when, pid))
    (data_dir / OUTBOX / f"{pid}.json").write_text(json.dumps({"id": pid, "approved_at": when}))
    return dict(conn.execute("SELECT * FROM hour_proposals WHERE id = ?", (pid,)).fetchone())


def skip(conn: sqlite3.Connection, pid: int) -> dict:
    r = conn.execute("SELECT status FROM hour_proposals WHERE id = ?", (pid,)).fetchone()
    if r is None:
        raise KeyError(pid)
    if r["status"] in ("approved", "written"):
        raise ValueError("Already approved or written")
    with conn:
        conn.execute("UPDATE hour_proposals SET status='skipped', decided_at=datetime('now') WHERE id=?", (pid,))
    return dict(conn.execute("SELECT * FROM hour_proposals WHERE id = ?", (pid,)).fetchone())


def reconcile(conn: sqlite3.Connection, data_dir: Path | None = None) -> list[int]:
    """Read the writer's results; mark proposals written or failed. Returns ids newly written."""
    data_dir = data_dir or DATA_DIR
    done, newly = data_dir / DONE, []
    for f in sorted(done.glob("*.json")) if done.is_dir() else []:
        try:
            res = json.loads(f.read_text()); pid = int(res["id"])
        except (ValueError, KeyError, OSError):
            continue
        with conn:
            n = conn.execute("UPDATE hour_proposals SET status=?, result=?, written_at=datetime('now') WHERE id=? AND status='approved'",
                             ("written" if res.get("ok") else "failed", str(res.get("message", ""))[:300], pid)).rowcount
        if n and res.get("ok"):
            newly.append(pid)
        f.unlink(missing_ok=True)
    return newly

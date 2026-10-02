"""Notes: context and follow-ups she writes, on an item, on an email, or free-standing.

A *note* is context: it is recorded in the harness (and so in the backups), shown in the notes log, and used as
context when a draft is written. A *follow-up* is a note that also creates a task, which appears in Today &
overdue on its date. Notes on personal items are masked like the items themselves (details only on click)."""
import sqlite3
from datetime import date, datetime

from harness import privacy
from harness.config import now_local
from harness.items import TABLES
from harness.importers.common import TITLE_COL

PARENT_TYPES = (*TABLES, "email")
MAX_TEXT = 2000


class NoteRefused(ValueError):
    pass


def _stamp(now: datetime | None) -> str:
    return (now or now_local()).strftime("%Y-%m-%d %H:%M:%S")


def _parent(conn, ptype: str, pid: int):
    if ptype == "email":
        return conn.execute("SELECT subject AS title, space, NULL AS code FROM emails WHERE id = ?", (pid,)).fetchone()
    table = TABLES[ptype]
    code = "project_code" if table != "waiting_on" else "NULL"
    return conn.execute(f"SELECT {TITLE_COL[table]} AS title, space, {code} AS code FROM {table} WHERE id = ?", (pid,)).fetchone()


def add_note(conn: sqlite3.Connection, text: str, *, kind: str = "note", parent_type: str | None = None, parent_id: int | None = None,
             due: str | None = None, personal: bool = False, now: datetime | None = None) -> dict:
    text = (text or "").strip()
    if not text:
        raise NoteRefused("The note is empty")
    if len(text) > MAX_TEXT:
        raise NoteRefused(f"The note is too long (max {MAX_TEXT} characters)")
    if kind not in ("note", "followup"):
        raise NoteRefused("A note is either a note or a follow-up")
    parent = None
    if parent_type or parent_id is not None:
        if parent_type not in PARENT_TYPES or parent_id is None:
            raise NoteRefused("Unknown item to attach the note to")
        parent = _parent(conn, parent_type, parent_id)
        if parent is None:
            raise NoteRefused("That item no longer exists")
    is_personal = personal or bool(parent and privacy.is_personal(parent["space"]))
    due_date = None
    if kind == "followup":
        try:
            due_date = date.fromisoformat(due).isoformat() if due else (now or now_local()).date().isoformat()
        except ValueError:
            raise NoteRefused("The follow-up date is not valid")
    when = _stamp(now)
    with conn:
        nid = conn.execute("INSERT INTO notes (created_at, text, kind, parent_type, parent_id, due_date, project_code, space, sensitivity) VALUES (?,?,?,?,?,?,?,?,?)",
                           (when, text, kind, parent_type, parent_id, due_date, parent["code"] if parent else None,
                            "personal" if is_personal else "work", "S3" if is_personal else "S2")).lastrowid
        if kind == "followup":
            title = " ".join(text.splitlines()[0].split())[:160]
            tid = conn.execute("INSERT INTO tasks (title, due_date, project_code, space, sensitivity, source, source_ref) VALUES (?,?,?,?,?,'note',?)",
                               (title, due_date, parent["code"] if parent else None, "personal" if is_personal else "work",
                                "S3" if is_personal else "S2", str(nid))).lastrowid
            conn.execute("UPDATE notes SET follow_up_task_id = ? WHERE id = ?", (tid, nid))
    return view(conn, nid)


def _label(conn, r: sqlite3.Row) -> dict | None:
    """What the note is attached to (masked when it is personal)."""
    if not r["parent_type"]:
        return None
    p = _parent(conn, r["parent_type"], r["parent_id"])
    if p is None:
        return {"type": r["parent_type"], "id": r["parent_id"], "title": "(removed)"}
    personal = privacy.is_personal(p["space"])
    return {"type": r["parent_type"], "id": r["parent_id"], "title": privacy.label(r["parent_type"]) if personal else p["title"], "masked": personal}


def view(conn: sqlite3.Connection, note_id: int, reveal: bool = False) -> dict | None:
    r = conn.execute("SELECT * FROM notes WHERE id = ?", (note_id,)).fetchone()
    if r is None:
        return None
    masked = privacy.is_personal(r["space"]) and not reveal
    fu = None
    if r["follow_up_task_id"]:
        t = conn.execute("SELECT status, due_date, done_at FROM tasks WHERE id = ?", (r["follow_up_task_id"],)).fetchone()
        fu = {"task_id": r["follow_up_task_id"], "status": t["status"] if t else "gone", "due": t["due_date"] if t else r["due_date"], "done_at": t["done_at"] if t else None}
    return {"id": r["id"], "created_at": r["created_at"], "kind": r["kind"], "text": privacy.label("note") if masked else r["text"], "masked": masked,
            "personal": privacy.is_personal(r["space"]), "due_date": r["due_date"], "follow_up": fu, "parent": _label(conn, r)}


def for_parent(conn: sqlite3.Connection, ptype: str, pid: int) -> list[dict]:
    ids = [r[0] for r in conn.execute("SELECT id FROM notes WHERE parent_type = ? AND parent_id = ? AND deleted_at IS NULL ORDER BY created_at DESC, id DESC", (ptype, pid))]
    return [view(conn, i) for i in ids]


def log(conn: sqlite3.Connection, days: int | None = 30, q: str = "", today: date | None = None) -> list[dict]:
    """Every note, newest first. A search never matches personal notes."""
    from datetime import timedelta
    cutoff = ((today or now_local().date()) - timedelta(days=days)).isoformat() if days else "0000-00-00"
    like = f"%{q.strip()}%"
    rows = conn.execute("SELECT id FROM notes WHERE deleted_at IS NULL AND substr(created_at,1,10) >= ? AND (? = '%%' OR (text LIKE ? AND space != 'personal')) "
                        "ORDER BY created_at DESC, id DESC", (cutoff, like, like)).fetchall()
    return [view(conn, r[0]) for r in rows]


def reveal(conn: sqlite3.Connection, note_id: int) -> dict | None:
    r = conn.execute("SELECT text FROM notes WHERE id = ? AND deleted_at IS NULL", (note_id,)).fetchone()
    return None if r is None else {"text": r["text"]}


def delete_note(conn: sqlite3.Connection, note_id: int, now: datetime | None = None) -> bool:
    """Remove a note from view (kept in the database as deleted). Its follow-up task, if still open, is dropped from Today."""
    with conn:
        r = conn.execute("SELECT follow_up_task_id FROM notes WHERE id = ? AND deleted_at IS NULL", (note_id,)).fetchone()
        if r is None:
            return False
        conn.execute("UPDATE notes SET deleted_at = ? WHERE id = ?", (_stamp(now), note_id))
        if r["follow_up_task_id"]:
            conn.execute("UPDATE tasks SET status = 'dropped', updated_at = datetime('now') WHERE id = ? AND status = 'open'", (r["follow_up_task_id"],))
    return True


def counts(conn: sqlite3.Connection) -> dict[tuple[str, int], int]:
    return {(r[0], r[1]): r[2] for r in conn.execute("SELECT parent_type, parent_id, COUNT(*) FROM notes WHERE deleted_at IS NULL AND parent_type IS NOT NULL GROUP BY 1, 2")}


def context_for(conn: sqlite3.Connection, ptype: str, pid: int, limit: int = 5) -> list[str]:
    """Her notes on this item, for the model as context. Personal notes are never used."""
    return [r[0][:300] for r in conn.execute("SELECT text FROM notes WHERE parent_type = ? AND parent_id = ? AND deleted_at IS NULL AND space != 'personal' "
                                             "ORDER BY created_at DESC LIMIT ?", (ptype, pid, limit))]

"""Phone to-dos: what she dictated to Siri (Reminders list "Harness"), read on the Mac by tools/reminders_helper.py. They wait in a short "From your phone"
list on Today; she confirms (optionally editing) and each becomes a follow-up task through the existing notes feature (so a work to-do also reaches Suivi's
journal like any note). Personal to-dos ("personal ..." or "p: ...") stay personal: masked, never sent to Suivi. Nothing here changes her Reminders."""
import re
import sqlite3
from datetime import date, datetime, timedelta

from harness import notes as notes_mod
from harness.config import now_local

_PERSONAL = re.compile(r"^\s*(personal|perso|privat|p)\s*[:\-–]\s*", re.I)
_DAYS = {"monday": 0, "mon": 0, "lundi": 0, "tuesday": 1, "tue": 1, "mardi": 1, "wednesday": 2, "wed": 2, "mercredi": 2, "thursday": 3, "thu": 3, "jeudi": 3,
         "friday": 4, "fri": 4, "vendredi": 4, "saturday": 5, "sat": 5, "samedi": 5, "sunday": 6, "sun": 6, "dimanche": 6}


def parse_due_words(text: str, today: date) -> str | None:
    """'tomorrow', 'today', 'by Friday', 'next Monday', 'demain' -> a date. Only clear words; anything else is left for her to set."""
    t = text.lower()
    if re.search(r"\b(today|aujourd.hui|heute)\b", t):
        return today.isoformat()
    if re.search(r"\b(tomorrow|demain|morgen)\b", t):
        return (today + timedelta(days=1)).isoformat()
    m = re.search(r"\b(?:(next|prochain|nächsten?)\s+)?(" + "|".join(sorted(_DAYS, key=len, reverse=True)) + r")\b", t)
    if m:
        return (today + timedelta(days=(_DAYS[m.group(2)] - today.weekday()) % 7 or 7)).isoformat()      # the coming one (a day that is today means next week's)
    if re.search(r"\bnext week\b", t):
        return (today + timedelta(days=7 - today.weekday())).isoformat()
    return None


def clean(text: str, project_codes: set[str]) -> dict:
    """Title without the 'personal:' prefix, its space, and a project code if one is named ('[TK] ...', 'TK: ...' or a code written in capitals)."""
    t = (text or "").strip()
    personal = bool(_PERSONAL.match(t))
    t = _PERSONAL.sub("", t).strip()
    code = None
    m = re.match(r"^\[?([A-Z0-9]{2,8})\]?\s*[:\-–]?\s+(.*)$", t)
    if m and m.group(1) in project_codes:
        code, t = m.group(1), m.group(2).strip()
    else:
        for w in re.findall(r"\b[A-Z][A-Z0-9]{1,7}\b", t):
            if w in project_codes:
                code = w
                break
    return {"text": " ".join(t.split())[:300], "space": "personal" if personal else "work", "project_code": None if personal else code}


def import_phone(conn: sqlite3.Connection, doc: dict, today: date | None = None) -> dict:
    """Mirror the Harness list. New reminders wait for her; one she edits on the phone before deciding is refreshed; ones she completed or deleted there disappear."""
    today = today or now_local().date()
    codes = {r[0] for r in conn.execute("SELECT code FROM project_codes WHERE domain != 'P'")}
    added = updated = 0
    seen = set()
    with conn:
        conn.execute("INSERT INTO phone_state (k, v) VALUES ('fetched_at', ?) ON CONFLICT (k) DO UPDATE SET v=excluded.v", (doc.get("fetched_at") or "",))
        conn.execute("INSERT INTO phone_state (k, v) VALUES ('error', ?) ON CONFLICT (k) DO UPDATE SET v=excluded.v", (doc.get("error") or "",))
        conn.execute("INSERT INTO phone_state (k, v) VALUES ('list', ?) ON CONFLICT (k) DO UPDATE SET v=excluded.v", (doc.get("list") or "",))
        if doc.get("error"):
            return {"added": 0, "updated": 0, "error": doc["error"]}
        for it in doc.get("items", []):
            rid = str(it.get("id") or "")
            if not rid:
                continue
            seen.add(rid)
            c = clean(it.get("name") or "", codes)
            if not c["text"]:
                continue
            due = it.get("due_date") or parse_due_words(it.get("name") or "", today)
            row = conn.execute("SELECT * FROM phone_todos WHERE reminder_id = ?", (rid,)).fetchone()
            if it.get("completed"):
                if row and row["status"] == "new":
                    conn.execute("UPDATE phone_todos SET status='dismissed', decided_at=datetime('now'), gone=1 WHERE reminder_id=?", (rid,))
                continue
            if row is None:
                conn.execute("INSERT INTO phone_todos (reminder_id, text, notes, due_date, created_at, space, project_code) VALUES (?,?,?,?,?,?,?)",
                             (rid, c["text"], (it.get("body") or "")[:500] or None, due, (it.get("created") or "")[:19], c["space"], c["project_code"]))
                added += 1
            elif row["status"] == "new" and (row["text"], row["due_date"]) != (c["text"], due):
                conn.execute("UPDATE phone_todos SET text=?, due_date=?, space=?, project_code=?, gone=0 WHERE reminder_id=?", (c["text"], due, c["space"], c["project_code"], rid))
                updated += 1
        for r in conn.execute("SELECT reminder_id FROM phone_todos WHERE status='new' AND gone=0").fetchall():
            if r["reminder_id"] not in seen:
                conn.execute("UPDATE phone_todos SET gone=1 WHERE reminder_id=?", (r["reminder_id"],))
    return {"added": added, "updated": updated, "error": None}


def _view(r: sqlite3.Row, reveal: bool = False) -> dict:
    masked = r["space"] == "personal" and not reveal
    return {"id": r["reminder_id"], "text": "Personal to-do" if masked else r["text"], "due_date": r["due_date"], "project_code": None if masked else r["project_code"],
            "space": r["space"], "masked": masked, "created_at": r["created_at"], "notes": None if masked else r["notes"]}


def list_new(conn: sqlite3.Connection) -> dict:
    items = [_view(r) for r in conn.execute("SELECT * FROM phone_todos WHERE status='new' AND gone=0 ORDER BY first_seen, rowid")]
    st = {r["k"]: r["v"] for r in conn.execute("SELECT k, v FROM phone_state")}
    return {"items": items, "fetched_at": st.get("fetched_at") or None, "error": st.get("error") or None, "list": st.get("list") or None}


def reveal(conn: sqlite3.Connection, rid: str) -> dict | None:
    r = conn.execute("SELECT * FROM phone_todos WHERE reminder_id = ? AND status = 'new'", (rid,)).fetchone()
    return _view(r, reveal=True) if r else None


def accept(conn: sqlite3.Connection, rid: str, edits: dict | None = None, now: datetime | None = None) -> dict:
    r = conn.execute("SELECT * FROM phone_todos WHERE reminder_id = ?", (rid,)).fetchone()
    if r is None:
        raise KeyError(rid)
    if r["status"] != "new":
        raise ValueError("This to-do has already been decided")
    e = edits or {}
    text = (e.get("text") or r["text"]).strip()
    due = e.get("due_date") if "due_date" in e else r["due_date"]
    code = (e.get("project_code") if "project_code" in e else r["project_code"]) or None
    personal = (e["space"] == "personal") if "space" in e else r["space"] == "personal"
    if code and not personal and not conn.execute("SELECT 1 FROM project_codes WHERE code = ? AND domain != 'P'", (code.upper(),)).fetchone():
        raise ValueError("Unknown project code")
    note = notes_mod.add_note(conn, text, kind="followup", due=due or None, personal=personal, now=now)
    with conn:
        if code and not personal:
            conn.execute("UPDATE notes SET project_code = ? WHERE id = ?", (code.upper(), note["id"]))
            conn.execute("UPDATE tasks SET project_code = ? WHERE id = ?", (code.upper(), note["follow_up"]["task_id"]))
        conn.execute("UPDATE phone_todos SET status='accepted', text=?, due_date=?, project_code=?, space=?, note_id=?, task_id=?, decided_at=datetime('now') WHERE reminder_id=?",
                     (text, note["follow_up"]["due"], code.upper() if code and not personal else None, "personal" if personal else "work", note["id"], note["follow_up"]["task_id"], rid))
    return {"note_id": note["id"], "task_id": note["follow_up"]["task_id"], "due": note["follow_up"]["due"]}


def dismiss(conn: sqlite3.Connection, rid: str) -> bool:
    with conn:
        return conn.execute("UPDATE phone_todos SET status='dismissed', decided_at=datetime('now') WHERE reminder_id=? AND status='new'", (rid,)).rowcount > 0

"""Import gmail_recent.json (written on the Mac by tools/google_helper.py sync-gmail) into `emails`.

Read-only. A thread whose newest message changed goes back to 'pending' so it is triaged again.
Threads that left the fetched window are kept but marked in_window = 0."""
import json
import sqlite3
from datetime import datetime
from pathlib import Path

from harness.config import TZ
from harness.importers.common import Report

FILE = "gmail_recent.json"


def import_gmail(conn: sqlite3.Connection, folder: Path) -> list[Report]:
    rep = Report(source="gmail:threads")
    path = folder / FILE
    if not path.exists():
        rep.notes.append("no Gmail file yet: run `make gmail` on the Mac")
        return [rep]
    data = json.loads(path.read_text())
    people = {r["email"]: r["slug"] for r in conn.execute("SELECT email, slug FROM people WHERE email IS NOT NULL")}
    seen = set()
    with conn:
        for t in data["threads"]:
            seen.add(t["thread_id"])
            received = datetime.fromtimestamp(t["received_ms"] / 1000, TZ).isoformat(timespec="seconds")
            fields = {
                "message_id": t["message_id"], "from_name": t["from_name"], "from_email": t["from_email"],
                "subject": t["subject"], "received_at": received, "snippet": t["snippet"], "body": t["body"],
                "direct": int(t["to_me_directly"]), "cc_only": int(t["cc_only"]), "bulk": int(t["bulk"]),
                "last_from_me": int(t["last_from_me"]), "in_window": 1, "person_slug": people.get(t["from_email"]),
            }
            row = conn.execute("SELECT * FROM emails WHERE thread_id = ?", (t["thread_id"],)).fetchone()
            if row is None:
                cols = {"thread_id": t["thread_id"], **fields}
                conn.execute(f"INSERT INTO emails ({','.join(cols)}) VALUES ({','.join('?' * len(cols))})", list(cols.values()))
                rep.added += 1
                continue
            changes = {k: v for k, v in fields.items() if row[k] != v}
            if changes:
                if "message_id" in changes:                       # new message in the thread: triage again
                    changes.update(triage_status="pending", needs_reply=None, why=None, urgency=None, score=None)
                conn.execute("UPDATE emails SET " + ", ".join(f"{k}=?" for k in changes) + ", updated_at=datetime('now') WHERE id=?",
                             [*changes.values(), row["id"]])
                rep.updated += 1
            else:
                rep.unchanged += 1
        for r in conn.execute("SELECT id, thread_id FROM emails WHERE in_window = 1").fetchall():
            if r["thread_id"] not in seen:
                conn.execute("UPDATE emails SET in_window = 0 WHERE id = ?", (r["id"],))
                rep.retired += 1
    return [rep]

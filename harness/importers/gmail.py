"""Import gmail_recent.json (written on the Mac by tools/google_helper.py sync-gmail) into `emails`.

Read-only. A thread whose newest message changed goes back to 'pending' so it is triaged again.
Threads that left the fetched window are kept but marked in_window = 0."""
import json
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

from harness.config import TZ
from harness.importers.common import Report

FILE = "gmail_recent.json"
TRUNCATED_AT = 95            # the helper asks Gmail for 100 threads (tools/google_helper.py GMAIL_MAX_THREADS)


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
        if data.get("me"):                         # her own address: used so a draft is never addressed to herself
            conn.execute("INSERT INTO draft_settings (key, value, source) VALUES ('my_address', ?, 'learned') "
                         "ON CONFLICT (key) DO UPDATE SET value=excluded.value", (data["me"].lower(),))
        for t in data["threads"]:
            seen.add(t["thread_id"])
            received = datetime.fromtimestamp(t["received_ms"] / 1000, TZ).isoformat(timespec="seconds")
            fields = {
                "message_id": t["message_id"], "from_name": t["from_name"], "from_email": t["from_email"],
                "subject": t["subject"], "received_at": received, "snippet": t["snippet"], "body": t["body"],
                "direct": int(t["to_me_directly"]), "cc_only": int(t["cc_only"]), "bulk": int(t["bulk"]),
                "last_from_me": int(t["last_from_me"]), "in_window": 1, "person_slug": people.get(t["from_email"]),
                "to_addrs": json.dumps(t.get("to_addrs") or []), "cc_addrs": json.dumps(t.get("cc_addrs") or []),
                "history": json.dumps(t.get("history") or [], ensure_ascii=False),
                "rfc_message_id": t.get("rfc_message_id") or None, "references_hdr": t.get("references") or None, "reply_to": t.get("reply_to") or None,
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
                    changes.update(triage_status="pending", needs_reply=None, why=None, urgency=None, score=None, handled_at=None)
                conn.execute("UPDATE emails SET " + ", ".join(f"{k}=?" for k in changes) + ", updated_at=datetime('now') WHERE id=?",
                             [*changes.values(), row["id"]])
                rep.updated += 1
            else:
                rep.unchanged += 1
        # The helper fetches at most TRUNCATED_AT threads, newest first. When it hit that limit (a burst of automated mail can fill it), threads older than the oldest one
        # fetched were simply not looked at, so they stay as they were; only threads inside the fetched time range that are missing have really left the inbox.
        oldest = None
        if len(data["threads"]) >= TRUNCATED_AT:
            oldest = datetime.fromtimestamp(min(t["received_ms"] for t in data["threads"]) / 1000, TZ).isoformat(timespec="seconds")
        for r in conn.execute("SELECT id, thread_id, received_at FROM emails WHERE in_window = 1").fetchall():
            if r["thread_id"] not in seen and (oldest is None or r["received_at"] >= oldest):
                conn.execute("UPDATE emails SET in_window = 0 WHERE id = ?", (r["id"],))
                rep.retired += 1
        if oldest:                                                  # bring back what an earlier truncated run wrongly retired (last 3 days only, as the query)
            floor = (datetime.now(TZ) - timedelta(days=3)).isoformat(timespec="seconds")
            rep.notes.append(f"{conn.execute('UPDATE emails SET in_window = 1 WHERE in_window = 0 AND received_at < ? AND received_at >= ?', (oldest, floor)).rowcount} older threads kept in the window (the Gmail fetch hit its limit)")
    return [rep]

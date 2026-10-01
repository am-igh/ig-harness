"""Import correspondence.json (written on the Mac by `google_helper.py sync-correspondence`) into
correspondence_threads / correspondence_messages, then learn the style profiles. Read-only, local."""
import json
import sqlite3
from datetime import datetime
from pathlib import Path

from harness import style
from harness.config import TZ
from harness.importers.common import Report

FILE = "correspondence.json"


def import_correspondence(conn: sqlite3.Connection, folder: Path) -> list[Report]:
    rep = Report(source="correspondence")
    path = folder / FILE
    if not path.exists():
        rep.notes.append("no correspondence file yet: run `make correspondence` on the Mac")
        return [rep]
    data = json.loads(path.read_text())
    iso = lambda ms: datetime.fromtimestamp(ms / 1000, TZ).isoformat(timespec="seconds")
    with conn:
        for email, threads in data["people"].items():
            for t in threads:
                conn.execute("INSERT INTO correspondence_threads (person_email, thread_id, subject, last_at, last_from_me, last_rfc_id, last_references, n_messages) "
                             "VALUES (?,?,?,?,?,?,?,?) ON CONFLICT (person_email, thread_id) DO UPDATE SET subject=excluded.subject, last_at=excluded.last_at, "
                             "last_from_me=excluded.last_from_me, last_rfc_id=excluded.last_rfc_id, last_references=excluded.last_references, n_messages=excluded.n_messages",
                             (email, t["thread_id"], t["subject"], iso(t["last_ms"]), int(t["last_from_me"]), t["last_rfc_id"], t["last_references"], len(t["messages"])))
                for m in t["messages"]:
                    lang, _ = style.detect_language(m["body"])
                    cur = conn.execute("INSERT INTO correspondence_messages (person_email, thread_id, msg_id, sent_at, from_me, subject, body, language) VALUES (?,?,?,?,?,?,?,?) "
                                       "ON CONFLICT (person_email, msg_id) DO NOTHING",
                                       (email, t["thread_id"], m["msg_id"], iso(m["ms"]), int(m["from_me"]), m["subject"], m["body"], lang))
                    rep.added += cur.rowcount
                    rep.unchanged += 1 - cur.rowcount
    stats = style.rebuild_profiles(conn)
    rep.notes.append(f"profiles: {stats['learned']} learned, {stats['kept_edits']} kept as you edited them")
    return [rep]

"""Import calendar_events.json (written by tools/gcal_helper.py on the Mac) into
calendar_events. Read-only: the harness never writes to Google Calendar.

Events are tagged S2 (meeting titles can name partners). Events inside the fetched
window that are no longer in the file are marked 'cancelled', not deleted.
"""
import json
import sqlite3
from pathlib import Path

from harness.importers.common import Report

SOURCE, FILE = "gcal", "calendar_events.json"


def import_calendar(conn: sqlite3.Connection, folder: Path) -> list[Report]:
    rep = Report(source="calendar:events")
    path = folder / FILE
    if not path.exists():
        rep.notes.append("no calendar file yet: run `make calendar` on the Mac")
        return [rep]
    data = json.loads(path.read_text())
    w0, w1 = data["window_start"][:10], data["window_end"][:10]
    seen = set()
    with conn:
        for e in data["events"]:
            seen.add(e["id"])
            fields = {"title": e["title"], "start": e["start"], "end": e.get("end"),
                      "all_day": int(e.get("all_day", False)),
                      "status": e.get("status", "confirmed"), "sensitivity": "S2"}
            row = conn.execute("SELECT * FROM calendar_events WHERE source=? AND source_ref=?",
                               (SOURCE, e["id"])).fetchone()
            if row is None:
                cols = {**fields, "source": SOURCE, "source_ref": e["id"]}
                conn.execute(f"INSERT INTO calendar_events ({','.join(cols)}) "
                             f"VALUES ({','.join('?' * len(cols))})", list(cols.values()))
                rep.added += 1
                continue
            changes = {k: v for k, v in fields.items() if row[k] != v}
            if changes:
                sets = ", ".join(f"{k}=?" for k in changes) + ", updated_at=datetime('now')"
                conn.execute(f"UPDATE calendar_events SET {sets} WHERE id=?", [*changes.values(), row["id"]])
                rep.updated += 1
            else:
                rep.unchanged += 1
        for r in conn.execute("SELECT id, source_ref FROM calendar_events WHERE source=? AND status!='cancelled' "
                              "AND substr(start,1,10) BETWEEN ? AND ?", (SOURCE, w0, w1)).fetchall():
            if r["source_ref"] not in seen:
                conn.execute("UPDATE calendar_events SET status='cancelled', updated_at=datetime('now') WHERE id=?", (r["id"],))
                rep.retired += 1
    return [rep]

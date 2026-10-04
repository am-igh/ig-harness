"""phone_todos.json (written by tools/reminders_helper.py from the Reminders list "Harness") -> the short "From your phone" list."""
import json
import sqlite3
from pathlib import Path

from harness import phone
from harness.importers.common import Report

FILE = "phone_todos.json"


def import_phone_todos(conn: sqlite3.Connection, folder: Path) -> list[Report]:
    rep = Report(source="phone:todos")
    path = Path(folder) / FILE
    if not path.exists():
        rep.notes.append("no phone to-do file yet: run `python3 tools/reminders_helper.py pull` on the Mac")
        return [rep]
    r = phone.import_phone(conn, json.loads(path.read_text()))
    rep.added, rep.updated = r["added"], r["updated"]
    if r["error"]:
        rep.notes.append(r["error"])
    return [rep]

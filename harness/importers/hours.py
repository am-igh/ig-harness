"""hours.csv (her hours log) -> the `hours` table, read-only. Columns: date, project, budget_line, hours, rate, description, evidence,
source, entered_on. The file is never changed; rows that disappear from it disappear here at the next import."""
import csv
import hashlib
import io
import sqlite3
from datetime import date
from pathlib import Path

from harness.importers.common import Report

FILE = "hours.csv"
COLS = ["date", "project", "budget_line", "hours", "rate", "description", "evidence", "source", "entered_on"]


def _f(v):
    try:
        return float(str(v).replace(",", ".").strip())
    except (TypeError, ValueError):
        return None


def _d(v):
    try:
        return date.fromisoformat(str(v).strip()[:10]).isoformat()
    except (TypeError, ValueError):
        return None


def import_hours(conn: sqlite3.Connection, folder: Path) -> list[Report]:
    rep = Report(source="hours")
    path = Path(folder) / FILE
    if not path.exists():
        rep.notes.append(f"no {FILE} in the projects folder")
        return [rep]
    rows = list(csv.DictReader(io.StringIO(path.read_bytes().decode("utf-8-sig"))))   # read fully first, so a sync cannot change it mid-read
    seen = set()
    for r in rows:
        day = _d(r.get("date"))
        if day is None:
            rep.skipped += 1
            continue
        vals = {"date": day, "project": (r.get("project") or "").strip().upper() or None, "budget_line": (r.get("budget_line") or "").strip() or None,
                "hours": _f(r.get("hours")), "rate": _f(r.get("rate")), "description": (r.get("description") or "").strip() or None,
                "evidence": (r.get("evidence") or "").strip() or None, "source": (r.get("source") or "").strip() or None, "entered_on": _d(r.get("entered_on"))}
        key = hashlib.sha256("|".join(str(vals[c]) for c in COLS).encode()).hexdigest()[:32]
        if key in seen:                                    # two identical lines count once
            rep.skipped += 1
            continue
        seen.add(key)
        if conn.execute("SELECT 1 FROM hours WHERE row_key = ?", (key,)).fetchone():
            rep.unchanged += 1
            continue
        with conn:
            conn.execute("INSERT INTO hours (row_key, date, project, budget_line, hours, rate, description, evidence, source, entered_on) VALUES (?,?,?,?,?,?,?,?,?,?)",
                         (key, *(vals[c] for c in COLS)))
        rep.added += 1
    for (k,) in conn.execute("SELECT row_key FROM hours").fetchall():
        if k not in seen:
            with conn:
                conn.execute("DELETE FROM hours WHERE row_key = ?", (k,))
            rep.retired += 1
    return [rep]

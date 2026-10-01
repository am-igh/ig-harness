"""Read-only import of Registre_Projets.xlsx into deadlines.

Reads ONLY the columns needed for dates and titles. Money columns, IBAN, contract
numbers and notes are never loaded (they are S2/S3).

  Mandates     reporting deadline -> deadline (kind reporting, major)
               interim reports    -> one deadline per ISO date found in the cell
               activity end       -> deadline
  Instalments  expected date, if not yet received -> deadline
  Initiatives  next touchpoint (date at start of the text) -> fixed date
"""
import re
import sqlite3
from pathlib import Path

from harness.importers.common import Report, clean, iso, parse_date, read_sheet, retire_missing, upsert

SOURCE = "registre"
FILE = "Registre_Projets.xlsx"
CLOSED_MANDATE_STATES = {"closed", "archived", "done", "completed"}
_ISO_ALL = re.compile(r"\d{4}-\d{2}-\d{2}")


def import_registre(conn: sqlite3.Connection, folder: Path) -> list[Report]:
    path = folder / FILE
    rep = Report(source="registre:deadlines")
    seen: set[str] = set()

    def add(ref: str, title: str, due, kind: str, importance: str, code: str | None):
        seen.add(ref)
        fields = {"title": title, "due_date": iso(due), "kind": kind,
                  "importance": importance, "project_code": code,
                  "space": "work", "sensitivity": "S1"}
        upsert(conn, "deadlines", SOURCE, ref, fields, "open", None, rep)

    mandates = read_sheet(path, "Mandates", ["code", "name", "activity end", "reporting deadline",
                                             "interim reports", "status"])
    instalments = read_sheet(path, "Instalments", ["code", "instalment", "expected date", "received date"])
    initiatives = read_sheet(path, "Initiatives", ["code", "name", "status", "next touchpoint"])

    with conn:
        for m in mandates:
            code = clean(m["code"])
            if not code:
                continue
            if (clean(m["status"]) or "").lower() in CLOSED_MANDATE_STATES:
                rep.skipped += 1
                continue
            name = clean(m["name"]) or code
            if d := parse_date(m["reporting deadline"]):
                add(f"{code}|reporting", f"{name}: final report due", d, "reporting", "major", code)
            for s in _ISO_ALL.findall(str(m["interim reports"] or "")):
                add(f"{code}|interim|{s}", f"{name}: interim report due", parse_date(s), "reporting", "normal", code)
            if d := parse_date(m["activity end"]):
                add(f"{code}|activity-end", f"{name}: activity ends", d, "deadline", "normal", code)
        for i in instalments:
            code, label = clean(i["code"]), clean(i["instalment"])
            d = parse_date(i["expected date"])
            if code and d and not clean(i["received date"]):
                add(f"{code}|instalment|{label}", f"{code}: instalment {label} expected", d, "deadline", "normal", code)
        for n in initiatives:
            code, status = clean(n["code"]), (clean(n["status"]) or "").lower()
            raw = clean(n["next touchpoint"])
            if not (code and raw) or status in ("closed", "archived", "done"):
                continue
            d = parse_date(raw)
            if not d:
                rep.notes.append(f"{code}: next touchpoint not understood ({raw[:30]!r}), skipped")
                continue
            rest = raw[10:].strip(" ()") if len(raw) > 10 else ""
            title = f"{clean(n['name']) or code}" + (f": {rest}" if rest else "")
            add(f"{code}|touchpoint", title, d, "fixed", "normal", code)
        retire_missing(conn, "deadlines", SOURCE, seen, rep)
    return [rep]

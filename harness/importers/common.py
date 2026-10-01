"""Shared helpers for read-only importers.

Importers never write to the source files. They upsert into the harness database
keyed on (source, source_ref), so running them twice changes nothing.
"""
import io
import re
import sqlite3
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path

import openpyxl

_ISO = re.compile(r"(\d{4})-(\d{2})-(\d{2})")


@dataclass
class Report:
    source: str
    added: int = 0
    updated: int = 0
    unchanged: int = 0
    retired: int = 0
    skipped: int = 0
    notes: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return self.__dict__.copy()


def read_sheet(path: Path, sheet: str, columns: list[str]) -> list[dict]:
    """Read only the named columns of a sheet. Other columns (e.g. IBAN) are never kept.

    The file is read fully into memory first so a Drive sync can't change it mid-read.
    """
    wb = openpyxl.load_workbook(io.BytesIO(path.read_bytes()), read_only=True, data_only=True)
    try:
        rows = wb[sheet].iter_rows(values_only=True)
        header = [str(h).strip() if h is not None else "" for h in next(rows)]
        missing = [c for c in columns if c not in header]
        if missing:
            raise ValueError(f"{path.name} / {sheet}: missing columns {missing}")
        idx = {c: header.index(c) for c in columns}
        out = []
        for r in rows:
            rec = {c: (r[i] if i < len(r) else None) for c, i in idx.items()}
            if any(v is not None and str(v).strip() != "" for v in rec.values()):
                out.append(rec)
        return out
    finally:
        wb.close()


def parse_date(value) -> date | None:
    """ISO date from a date/datetime or the start of a string like '2026-10-14 (panel)'."""
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        m = _ISO.search(value.strip()[:10])
        if m:
            try:
                return date(*map(int, m.groups()))
            except ValueError:
                return None
    return None


def iso(d: date | None) -> str | None:
    return d.isoformat() if d else None


def clean(value) -> str | None:
    if value is None:
        return None
    s = str(value).strip()
    return s or None


def upsert(
    conn: sqlite3.Connection,
    table: str,
    source: str,
    ref: str,
    fields: dict,
    status: str,
    done_at: str | None,
    report: Report,
) -> None:
    """Insert or update one imported row. Never reopens something already ticked off here."""
    row = conn.execute(
        f"SELECT * FROM {table} WHERE source = ? AND source_ref = ?", (source, ref)
    ).fetchone()
    if row is None:
        cols = {**fields, "source": source, "source_ref": ref, "status": status}
        if status == "done":
            cols["done_at"] = done_at
        conn.execute(
            f"INSERT INTO {table} ({','.join(cols)}) VALUES ({','.join('?' * len(cols))})",
            list(cols.values()),
        )
        report.added += 1
        return
    changes = {k: v for k, v in fields.items() if row[k] != v}
    if row["status"] != "done" and status == "done":
        changes["status"] = "done"
        changes["done_at"] = done_at
    elif row["status"] == "dropped" and status == "open":
        changes["status"] = "open"  # reappeared in the source
    if not changes:
        report.unchanged += 1
        return
    sets = ", ".join(f"{k} = ?" for k in changes) + ", updated_at = datetime('now')"
    conn.execute(f"UPDATE {table} SET {sets} WHERE id = ?", [*changes.values(), row["id"]])
    report.updated += 1


def retire_missing(conn: sqlite3.Connection, table: str, source: str, seen: set[str], report: Report) -> None:
    """Open rows from this source that are no longer in it are marked 'dropped' (not deleted)."""
    rows = conn.execute(
        f"SELECT id, source_ref FROM {table} WHERE source = ? AND status = 'open'", (source,)
    ).fetchall()
    for r in rows:
        if r["source_ref"] not in seen:
            conn.execute(
                f"UPDATE {table} SET status='dropped', updated_at=datetime('now') WHERE id = ?",
                (r["id"],),
            )
            report.retired += 1

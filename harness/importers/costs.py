"""costs.csv (her project costs log) -> the `costs` table, read-only. Never changes the file. An IBAN in the account column is reduced to its
last four characters (rule: no IBAN is stored)."""
import csv
import hashlib
import io
import re
import sqlite3
from pathlib import Path

from harness.importers.common import Report
from harness.importers.hours import _d, _f

FILE = "costs.csv"
COLS = ["date", "project", "budget_line", "supplier", "amount", "currency", "amount_chf", "invoice_reference", "payment_date", "account", "justificatif", "entered_on"]
_IBAN = re.compile(r"\b[A-Z]{2}\d{2}(?:[ ]?[A-Z0-9]{3,5}){3,8}\b")


def _account(v: str) -> str | None:
    v = (v or "").strip()
    return ("…" + re.sub(r"\s", "", v)[-4:]) if _IBAN.search(v) else (v or None)


def import_costs(conn: sqlite3.Connection, folder: Path) -> list[Report]:
    rep = Report(source="costs")
    path = Path(folder) / FILE
    if not path.exists():
        rep.notes.append(f"no {FILE} in the projects folder")
        return [rep]
    seen = set()
    for r in csv.DictReader(io.StringIO(path.read_bytes().decode("utf-8-sig"))):
        if not any((v or "").strip() for v in r.values()):
            continue
        vals = {"date": _d(r.get("date")), "project": (r.get("project") or "").strip().upper() or None, "budget_line": (r.get("budget_line") or "").strip() or None,
                "supplier": (r.get("supplier") or "").strip() or None, "amount": _f(r.get("amount")), "currency": (r.get("currency") or "").strip().upper() or None,
                "amount_chf": _f(r.get("amount_chf")), "invoice_reference": (r.get("invoice_reference") or "").strip() or None, "payment_date": _d(r.get("payment_date")),
                "account": _account(r.get("account") or ""), "justificatif": (r.get("justificatif") or "").strip() or None, "entered_on": _d(r.get("entered_on"))}
        key = hashlib.sha256("|".join(str(vals[c]) for c in COLS).encode()).hexdigest()[:32]
        if key in seen:
            rep.skipped += 1
            continue
        seen.add(key)
        if conn.execute("SELECT 1 FROM costs WHERE row_key = ?", (key,)).fetchone():
            rep.unchanged += 1
            continue
        with conn:
            conn.execute(f"INSERT INTO costs (row_key, {','.join(COLS)}) VALUES (?,{','.join('?' * len(COLS))})", (key, *(vals[c] for c in COLS)))
        rep.added += 1
    for (k,) in conn.execute("SELECT row_key FROM costs").fetchall():
        if k not in seen:
            with conn:
                conn.execute("DELETE FROM costs WHERE row_key = ?", (k,))
            rep.retired += 1
    return [rep]

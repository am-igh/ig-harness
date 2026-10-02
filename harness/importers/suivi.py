"""Read-only import of Suivi.xlsx (Commitments, Journal) into tasks, deadlines,
waiting_on and journal_entries.

Mapping (decided with Anne-Marie's workbook structure, 1 Oct 2026):
  Commitments  direction 'owe'  + weight hard/major + due date -> deadlines
               direction 'owe'  otherwise                     -> tasks
               direction 'owed' (someone owes her)            -> waiting_on
               status open/done are imported; 'proposed' and 'someday' are skipped
  Journal      every entry                                    -> journal_entries
  domain 'P' (personal) -> space 'personal', always sensitivity S3 (rule 10)
"""
import sqlite3
from pathlib import Path

from harness.importers.common import (
    Report, clean, iso, parse_date, read_sheet, retire_missing, upsert,
)

SOURCE = "suivi"
FILE = "Suivi.xlsx"
IMPORT_STATUSES = {"open", "done"}


def _space(domain) -> tuple[str, str]:
    return ("personal", "S3") if clean(domain) == "P" else ("work", "S1")


def import_suivi(conn: sqlite3.Connection, folder: Path) -> list[Report]:
    path = folder / FILE
    return [_commitments(conn, path), _journal(conn, path), _people(conn, path), _codes(conn, path)]


def _commitments(conn, path) -> Report:
    rep = Report(source="suivi:commitments")
    rows = read_sheet(path, "Commitments",
                      ["id", "created", "domain", "code", "direction", "counterparty",
                       "what", "due", "weight", "status", "closed_on"])
    seen: dict[str, set[str]] = {"tasks": set(), "deadlines": set(), "waiting_on": set()}
    with conn:
        for r in rows:
            ref, what = clean(r["id"]), clean(r["what"])
            status = (clean(r["status"]) or "").lower()
            if not ref or not what:
                rep.skipped += 1
                rep.notes.append(f"row without id or text skipped ({ref or 'no id'})")
                continue
            if status not in IMPORT_STATUSES:
                rep.skipped += 1  # proposed / someday: not yet real commitments
                continue
            space, tier = _space(r["domain"])
            common = {"space": space, "sensitivity": tier}
            due, raw_due = parse_date(r["due"]), clean(r["due"])
            if raw_due and not due:
                rep.notes.append(f"{ref}: due date not understood ({raw_due[:30]!r}), left empty")
            done_at = iso(parse_date(r["closed_on"]))
            direction, weight = clean(r["direction"]), (clean(r["weight"]) or "soft").lower()

            if direction == "owed":
                table = "waiting_on"
                since = iso(parse_date(r["created"])) or iso(due) or "1970-01-01"
                fields = {"description": what, "person": clean(r["counterparty"]),
                          "since_date": since, "remind_on": iso(due), **common}
            elif weight in ("hard", "major") and due:
                table = "deadlines"
                fields = {"title": what, "due_date": iso(due), "kind": "deadline",
                          "importance": "major" if weight == "major" else "normal",
                          "project_code": clean(r["code"]), **common}
            else:
                table = "tasks"
                fields = {"title": what, "due_date": iso(due),
                          "project_code": clean(r["code"]), **common}
            seen[table].add(ref)
            upsert(conn, table, SOURCE, ref, fields, status, done_at, rep)
        for table, refs in seen.items():
            retire_missing(conn, table, SOURCE, refs, rep)
    return rep


def _journal(conn, path) -> Report:
    rep = Report(source="suivi:journal")
    rows = read_sheet(path, "Journal", ["id", "date", "domain", "code", "summary", "type", "evidence", "hours"], optional=("type", "evidence", "hours"))
    seen: set[str] = set()
    with conn:
        for r in rows:
            ref, text, d = clean(r["id"]), clean(r["summary"]), parse_date(r["date"])
            if not (ref and text and d):
                rep.skipped += 1
                rep.notes.append(f"journal row skipped ({ref or 'no id'}): missing id, date or summary")
                continue
            space, tier = _space(r["domain"])
            seen.add(ref)
            try:
                hrs = float(str(r["hours"]).replace(",", ".")) if clean(r["hours"]) else None
            except ValueError:
                hrs = None
            fields = {"entry_date": iso(d), "text": text, "project_code": clean(r["code"]),
                      "space": space, "sensitivity": tier, "entry_type": clean(r["type"]), "evidence": clean(r["evidence"]), "hours": hrs}
            row = conn.execute("SELECT * FROM journal_entries WHERE source=? AND source_ref=?",
                               (SOURCE, ref)).fetchone()
            if row is None:
                cols = {**fields, "source": SOURCE, "source_ref": ref}
                conn.execute(f"INSERT INTO journal_entries ({','.join(cols)}) "
                             f"VALUES ({','.join('?' * len(cols))})", list(cols.values()))
                rep.added += 1
            else:
                changes = {k: v for k, v in fields.items() if row[k] != v}
                if changes:
                    sets = ", ".join(f"{k}=?" for k in changes) + ", updated_at=datetime('now')"
                    conn.execute(f"UPDATE journal_entries SET {sets} WHERE id=?", [*changes.values(), row["id"]])
                    rep.updated += 1
                else:
                    rep.unchanged += 1
    return rep


def _people(conn, path) -> Report:
    """People sheet -> people table (used to recognise email senders). The free-text 'context'
    and 'groups' columns are deliberately not imported."""
    rep = Report(source="suivi:people")
    rows = read_sheet(path, "People", ["id", "name", "aliases", "org", "role", "email", "cadence", "domain"])
    with conn:
        for r in rows:
            slug, name = clean(r["id"]), clean(r["name"])
            if not (slug and name):
                rep.skipped += 1
                continue
            fields = {"name": name, "aliases": clean(r["aliases"]), "org": clean(r["org"]), "role": clean(r["role"]),
                      "email": (clean(r["email"]) or "").lower() or None, "cadence": clean(r["cadence"]),
                      "space": "personal" if clean(r["domain"]) == "P" else "work"}
            row = conn.execute("SELECT * FROM people WHERE slug = ?", (slug,)).fetchone()
            if row is None:
                cols = {"slug": slug, **fields}
                conn.execute(f"INSERT INTO people ({','.join(cols)}) VALUES ({','.join('?' * len(cols))})", list(cols.values()))
                rep.added += 1
            else:
                changes = {k: v for k, v in fields.items() if row[k] != v}
                if changes:
                    conn.execute("UPDATE people SET " + ", ".join(f"{k}=?" for k in changes) + ", updated_at=datetime('now') WHERE id=?",
                                 [*changes.values(), row["id"]])
                    rep.updated += 1
                else:
                    rep.unchanged += 1
    return rep


def _codes(conn, path) -> Report:
    """Codes sheet -> project_codes: which codes are projects, threads or personal areas, and where each is registered."""
    rep = Report(source="suivi:codes")
    try:
        rows = read_sheet(path, "Codes", ["code", "name", "domain", "kind", "registry_link"])
    except KeyError:
        rep.notes.append("no Codes sheet in Suivi.xlsx: project list not updated")
        return rep
    seen = set()
    with conn:
        for r in rows:
            code = clean(r["code"])
            if not code:
                rep.skipped += 1
                continue
            seen.add(code)
            fields = {"name": clean(r["name"]), "domain": clean(r["domain"]), "kind": clean(r["kind"]), "registry_link": clean(r["registry_link"])}
            row = conn.execute("SELECT * FROM project_codes WHERE code = ?", (code,)).fetchone()
            if row is None:
                conn.execute("INSERT INTO project_codes (code, name, domain, kind, registry_link) VALUES (?,?,?,?,?)", (code, *fields.values()))
                rep.added += 1
            else:
                changes = {k: v for k, v in fields.items() if row[k] != v}
                if changes:
                    conn.execute("UPDATE project_codes SET " + ", ".join(f"{k}=?" for k in changes) + ", updated_at=datetime('now') WHERE code=?", [*changes.values(), code])
                    rep.updated += 1
                else:
                    rep.unchanged += 1
        for r in conn.execute("SELECT code FROM project_codes").fetchall():          # a code removed from the sheet is removed here too (it is a mirror)
            if r["code"] not in seen:
                conn.execute("DELETE FROM project_codes WHERE code = ?", (r["code"],))
                rep.retired += 1
    return rep

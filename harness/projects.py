"""The Projects tab: each project and thread from Suivi's Codes sheet, with what is open, what is next, how recent the
activity is, and what the project register says. Read-only queries on data the importers mirrored; no AI.

Personal areas and personal items never appear here. A code can be several codes separated by ';' (Suivi allows that)."""
import re
import sqlite3
from datetime import date

KINDS = ("project", "thread")


def _split(codes: str | None) -> list[str]:
    return [c.strip() for c in (codes or "").split(";") if c.strip()]


def _open_items(conn: sqlite3.Connection) -> dict[str, list[dict]]:
    """Open work tasks and deadlines, grouped under every code they carry."""
    by: dict[str, list[dict]] = {}
    for table, type_ in (("tasks", "task"), ("deadlines", "deadline")):
        extra = ", importance" if table == "deadlines" else ""
        for r in conn.execute(f"SELECT id, title, due_date, project_code{extra} FROM {table} WHERE status='open' AND space='work' AND project_code IS NOT NULL"):
            item = {"type": type_, "id": r["id"], "title": r["title"], "due": r["due_date"], "importance": r["importance"] if table == "deadlines" else None}
            for c in _split(r["project_code"]):
                by.setdefault(c, []).append(item)
    return by


def _last_journal(conn: sqlite3.Connection) -> dict[str, str]:
    out: dict[str, str] = {}
    for r in conn.execute("SELECT project_code, entry_date FROM journal_entries WHERE space='work' AND project_code IS NOT NULL"):
        for c in _split(r["project_code"]):
            if r["entry_date"] > out.get(c, ""):
                out[c] = r["entry_date"]
    return out


def _tagged_events(conn: sqlite3.Connection, today: date) -> dict[str, list[dict]]:
    """Calendar events whose title carries a [CODE] tag, from today on."""
    out: dict[str, list[dict]] = {}
    for r in conn.execute("SELECT id, title, start FROM calendar_events WHERE status != 'cancelled' AND substr(start,1,10) >= ? ORDER BY start", (today.isoformat(),)):
        for tag in re.findall(r"\[([A-Za-z0-9]{2,10})\]", r["title"]):
            out.setdefault(tag.upper(), []).append({"id": r["id"], "title": r["title"], "start": r["start"]})
    return out


def _register(conn: sqlite3.Connection, code: str) -> dict | None:
    m = conn.execute("SELECT * FROM register_mandates WHERE code = ?", (code,)).fetchone()
    i = conn.execute("SELECT * FROM register_initiatives WHERE code = ?", (code,)).fetchone()
    if not (m or i):
        return None
    return {"mandate": dict(m) if m else None, "initiative": dict(i) if i else None}


def _gaps(link: str | None, reg: dict | None) -> list[str]:
    """Where Suivi says the project is registered, but the register has no such entry yet."""
    out, link = [], (link or "")
    if re.search(r"mandate", link, re.I) and not (reg and reg["mandate"]):
        out.append("Suivi says this is a mandate in the project register, but the register has no mandate row for it yet (funder, contract, budget, reporting dates).")
    if re.search(r"initiat", link, re.I) and not (reg and reg["initiative"]):
        out.append("Suivi says this is an initiative in the project register, but the register has no initiative row for it.")
    if re.search(r"registre", link, re.I) and not re.search(r"mandate|initiat", link, re.I) and not reg:
        out.append("Suivi points to the project register for this project, but the register has no entry for it yet.")
    return out


def build_projects(conn: sqlite3.Connection, today: date) -> dict:
    items, journal, events = _open_items(conn), _last_journal(conn), _tagged_events(conn, today)
    out = []
    for c in conn.execute("SELECT * FROM project_codes WHERE domain != 'P' AND kind IN ('project','thread') ORDER BY code"):
        code = c["code"]
        mine = items.get(code, [])
        dated = sorted((i for i in mine if i["due"] and i["due"] >= today.isoformat()), key=lambda i: i["due"])
        reg = _register(conn, code)
        ev = events.get(code, [])
        out.append({
            "code": code, "name": c["name"], "kind": c["kind"], "registry_link": c["registry_link"],
            "funder": (reg["mandate"] or {}).get("funder") if reg and reg["mandate"] else None, "register": reg,
            "open": len(mine), "overdue": sum(1 for i in mine if i["due"] and i["due"] < today.isoformat()),
            "next_due": ({"title": dated[0]["title"], "due": dated[0]["due"], "type": dated[0]["type"]} if dated else None),
            "last_activity": journal.get(code), "events_ahead": len(ev), "next_event": ev[0] if ev else None,
            "gaps": _gaps(c["registry_link"], reg),
        })
    order = {"project": 0, "thread": 1}
    out.sort(key=lambda p: (order[p["kind"]], -p["overdue"], -p["open"], p["code"]))
    return {"projects": [p for p in out if p["kind"] == "project"], "threads": [p for p in out if p["kind"] == "thread"],
            "gaps": [{"code": p["code"], "name": p["name"], "gap": g} for p in out for g in p["gaps"]]}


def project_detail(conn: sqlite3.Connection, code: str, today: date) -> dict | None:
    row = conn.execute("SELECT * FROM project_codes WHERE code = ? AND domain != 'P' AND kind IN ('project','thread')", (code,)).fetchone()
    if row is None:
        return None
    mine = sorted(_open_items(conn).get(code, []), key=lambda i: (i["due"] is None, i["due"] or ""))
    for i in mine:
        i["days_overdue"] = (today - date.fromisoformat(i["due"])).days if i["due"] and i["due"] < today.isoformat() else 0
    entries = []
    for r in conn.execute("SELECT entry_date, text, project_code FROM journal_entries WHERE space='work' AND project_code IS NOT NULL ORDER BY entry_date DESC, id DESC"):
        if code in _split(r["project_code"]):
            entries.append({"date": r["entry_date"], "text": r["text"]})
        if len(entries) >= 8:
            break
    reg = _register(conn, code)
    return {"code": code, "name": row["name"], "kind": row["kind"], "registry_link": row["registry_link"], "register": reg, "items": mine,
            "journal": entries, "events": _tagged_events(conn, today).get(code, [])[:8], "gaps": _gaps(row["registry_link"], reg)}

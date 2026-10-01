"""Editing an item's title and due date from Today & overdue.

Items imported from Suivi or the project register are mirrored read-only sources. A hand edit is kept in
`item_overrides` so re-imports never undo it; the override remembers what the source says now, so the
screen can show it and she can reset to it."""
import sqlite3
from datetime import date

from harness.importers.common import DUE_COL, TITLE_COL

TABLES = {"task": "tasks", "deadline": "deadlines", "waiting_on": "waiting_on"}   # ("email" is handled separately where needed)
IMPORTED = ("suivi", "registre")
MAX_TITLE = 300


class EditRefused(ValueError):
    pass


def _clean_due(value, table: str):
    if value in (None, ""):
        if table == "deadlines":
            raise EditRefused("A deadline needs a date")
        return None
    try:
        return date.fromisoformat(str(value)).isoformat()
    except ValueError:
        raise EditRefused("The date is not valid")


def edit_item(conn: sqlite3.Connection, item_type: str, item_id: int, *, title: str | None = None,
              due=None, set_due: bool = False, reset: bool = False) -> bool:
    """Change an open item's title and/or due date, or reset it to the source's version. False if not found."""
    table = TABLES[item_type]
    tcol, dcol = TITLE_COL[table], DUE_COL[table]
    row = conn.execute(f"SELECT {tcol} AS t, {dcol} AS d, source, status FROM {table} WHERE id = ?", (item_id,)).fetchone()
    if row is None:
        return False
    if row["status"] != "open":
        raise EditRefused("Reopen the item before editing it")
    imported = row["source"] in IMPORTED
    with conn:
        if reset:
            for o in conn.execute("SELECT field, source_value FROM item_overrides WHERE table_name=? AND item_id=?", (table, item_id)).fetchall():
                conn.execute(f"UPDATE {table} SET {tcol if o['field'] == 'title' else dcol} = ? WHERE id = ?", (o["source_value"], item_id))
            conn.execute("DELETE FROM item_overrides WHERE table_name=? AND item_id=?", (table, item_id))
            conn.execute(f"UPDATE {table} SET updated_at=datetime('now') WHERE id=?", (item_id,))
            return True
        sets = {}
        if title is not None:
            t = " ".join(title.split())
            if not t:
                raise EditRefused("The title can't be empty")
            if len(t) > MAX_TITLE:
                raise EditRefused(f"The title is too long (max {MAX_TITLE} characters)")
            if t != row["t"]:
                sets[tcol] = ("title", t, row["t"])
        if set_due:
            d = _clean_due(due, table)
            if d != row["d"]:
                sets[dcol] = ("due", d, row["d"])
        for col, (field, new, old) in sets.items():
            conn.execute(f"UPDATE {table} SET {col} = ?, updated_at=datetime('now') WHERE id = ?", (new, item_id))
            if not imported:
                continue
            ov = conn.execute("SELECT source_value FROM item_overrides WHERE table_name=? AND item_id=? AND field=?", (table, item_id, field)).fetchone()
            src = ov["source_value"] if ov else old                  # the source's value, before any edit of ours
            if new == src or (new is None and src is None):
                conn.execute("DELETE FROM item_overrides WHERE table_name=? AND item_id=? AND field=?", (table, item_id, field))
            else:
                conn.execute("INSERT INTO item_overrides (table_name, item_id, field, source_value, edited_at) VALUES (?,?,?,?,datetime('now')) "
                             "ON CONFLICT (table_name, item_id, field) DO UPDATE SET edited_at=datetime('now')", (table, item_id, field, src))
    return True


def overrides_for(conn: sqlite3.Connection, table: str) -> dict[int, dict]:
    """{item_id: {'title': source_title_or_None, 'due': source_due_or_None}} for edited items."""
    out: dict[int, dict] = {}
    for r in conn.execute("SELECT item_id, field, source_value FROM item_overrides WHERE table_name=?", (table,)):
        out.setdefault(r["item_id"], {})[r["field"]] = r["source_value"]
    return out


def reveal(conn: sqlite3.Connection, item_type: str, item_id: int) -> dict | None:
    """The details of one item, for when she clicks a masked (personal) one. Nothing else sends these."""
    if item_type == "email":
        r = conn.execute("SELECT subject AS title, NULL AS code, from_name AS person FROM emails WHERE id = ?", (item_id,)).fetchone()
    else:
        table = TABLES[item_type]
        tcol = TITLE_COL[table]
        extra = "project_code AS code, NULL AS person" if table != "waiting_on" else "NULL AS code, person"
        r = conn.execute(f"SELECT {tcol} AS title, {extra} FROM {table} WHERE id = ?", (item_id,)).fetchone()
    return None if r is None else {"title": r["title"], "code": r["code"], "person": r["person"]}

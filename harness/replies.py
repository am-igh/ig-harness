"""Replies on open items: new mail that answers something she is waiting for, even when it asks for nothing ("we will revert soonest").
A message qualifies (read or unread, whatever the triage said, and it does not use up the mail list's limit) when
  1. it lands in a thread where SHE wrote earlier (the other side has now replied), or
  2. its sender, or anyone on To/Cc, is named in an open waiting-on item: as the item's person (several people may be given, separated by ; , & or 'and'), or because their full name
     is written in the item's description (so "CI4G to confirm Dan Stein or Susan Wilding" catches a message from Susan even though the item is filed under someone else).
Plain rules, no model. Automated senders and newsletters never qualify; her own address never counts as a participant; handled emails are left out."""
import json
import re
import sqlite3
from datetime import datetime, timedelta

from harness import triage as T
from harness.config import TZ, now_local

_SPLIT = re.compile(r"\s*(?:;|,|&|/|\band\b|\bet\b)\s*", re.I)
MAX_SHOWN = 8            # a person who is copied on many threads must not flood the section
_ADDR = re.compile(r"[\w.+'-]+@[\w.-]+\.\w+")


def _participants(e: sqlite3.Row) -> list[tuple[str, str]]:
    """(name text, address) for the sender and everyone on To/Cc, without her own address."""
    out = [(e["from_name"] or "", (e["from_email"] or "").lower())]
    for col in ("to_addrs", "cc_addrs"):
        try:
            for a in json.loads(e[col] or "[]"):
                a = str(a)
                m = _ADDR.search(a)
                out.append((re.sub(r"[<>\"']", " ", a.replace(m.group(0), "")) if m else a, m.group(0).lower() if m else ""))
        except ValueError:
            pass
    return out


def _wrote_earlier(e: sqlite3.Row) -> bool:
    try:
        return any(h.get("from_me") for h in json.loads(e["history"] or "[]"))
    except ValueError:
        return False


def _open_items(conn: sqlite3.Connection) -> list[dict]:
    people = {r["slug"]: r for r in conn.execute("SELECT slug, name, email, aliases FROM people")}
    items = []
    for w in conn.execute("SELECT id, description, person FROM waiting_on WHERE status='open' AND space='work'"):
        names, emails = [], set()
        for tok in _SPLIT.split(w["person"] or ""):
            if not tok:
                continue
            p = people.get(tok) or next((x for x in people.values() if T._norm(x["name"]) == T._norm(tok)), None)
            if p:
                names.append(p["name"])
                if p["email"]:
                    emails.add(p["email"].lower())
            else:
                names.append(tok)
        items.append({"id": w["id"], "description": w["description"], "names": names, "emails": emails, "desc_norm": T._norm(w["description"])})
    return items


def _matches(item: dict, name_text: str, addr: str) -> bool:
    n = T._norm(name_text)
    words = n.split()
    if addr and addr in item["emails"]:
        return True
    if len(words) >= 2 and all(f" {w} " in item["desc_norm"] for w in words):          # a full name written out in the description
        return True
    return any(len(words) >= 2 and all(f" {w} " in T._norm(x) for w in words) for x in item["names"])


def find(conn: sqlite3.Connection, now: datetime | None = None, hours: int = 48) -> list[dict]:
    """The qualifying emails, newest first, each with the reasons and the open item it belongs to (if any)."""
    now = now or now_local()
    cutoff = datetime.fromtimestamp(now.timestamp() - hours * 3600, TZ).isoformat(timespec="seconds")
    me = (conn.execute("SELECT value FROM draft_settings WHERE key='my_address'").fetchone() or [""])[0].lower()
    items = _open_items(conn)
    out = []
    for e in conn.execute("SELECT * FROM emails WHERE in_window=1 AND handled_at IS NULL AND space='work' AND last_from_me=0 AND received_at >= ? ORDER BY received_at DESC", (cutoff,)):
        sender = e["from_email"] or ""
        if T.GOOGLE_ALERT.search(sender) or (not e["person_slug"] and (e["bulk"] or T.AUTOMATED.search(sender))):
            continue
        reasons, item = [], None
        if _wrote_earlier(e):
            reasons.append("you wrote earlier in this thread")
        for who, addr in _participants(e):
            if addr and addr == me:
                continue
            for it in items:
                if _matches(it, who, addr):
                    role = "sender" if addr == sender.lower() or who == (e["from_name"] or "") else "on the thread"
                    reasons.append(f"{(who.strip() or addr)} ({role}) is named in: {it['description'][:70]}")
                    item = item or it
                    break
        if reasons:
            out.append({"email": e, "reasons": reasons[:3], "item_id": item["id"] if item else None, "item": item["description"] if item else None})
    out.sort(key=lambda r: 0 if "(sender)" in r["reasons"][0] or "wrote earlier" in r["reasons"][0] else 1)       # stable: newest first within each group
    return out[:MAX_SHOWN]

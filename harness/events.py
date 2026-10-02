"""Geneva and beyond: conferences and events, from every source, with her status for each (slice 5.1: from her Google Calendar).

Each event has EVIDENCE (what we know and where it came from) and a status derived from the strongest evidence; her own override beats it.
A calendar entry counts as an event when its title looks like one (summit, forum, panel, webinar...) or it is an invitation with a place;
reminders she wrote for herself ("Travel booking", "Focus:", "D-3:") and ordinary calls and meetings are left out, and she can overrule
either way. Pure rules, no AI. Topics, Geneva and role are found by keywords so the same rules serve the email and web sources later."""
import re
import sqlite3
from datetime import date, datetime, timedelta

EVENT_WORDS = re.compile(r"\b(summit|forum|conference|congress|symposium|workshop|webinar|panel|dialogue|hack(athon)?|week|session|launch|reception|ceremony|award|open house|"
                         r"seminar|roundtable|round table|festival|expo|exhibition|keynote|masterclass|training|course launch|event|anticipation|pall mall|wilton park|gesda|iaseai|plenary|assembly)\b", re.I)
REMINDER = re.compile(r"^(focus:|travel booking|relancer|classement|cl[oô]ture|d-\d|deadline|cancel |followup|follow-up|trip to|ann-?marie$)", re.I)       # her own reminders: never events
NOT_EVENT = re.compile(r"\b(call|meeting|r[ée]union|rdv|catch.?up|1:1|bi-weekly|breakfast with|lunch|holiday|reminder|kick-?off call)\b", re.I)         # ordinary meetings, unless the title says event
GENEVA = re.compile(r"\b(gen[eè]ve|geneva|genf|palexpo|cicg|palais des nations|campus biotech|maison de la paix|graduate institute|gcsp|unog|itu\b|wmo|cern|"
                    r"portail des nations|villa barton|la pastorale|le grand-saconnex|meyrin|carouge|nations unies)\b", re.I)
ROLES = [("moderator", r"\bmoderat"), ("facilitator", r"\bfacilitat"), ("speaker", r"\b(speak|keynote|talk)"), ("panelist", r"\bpanel(l?ist)?\b.*\(|\bpanel(l?ist)\b"),
         ("judge", r"\b(judg|jury)"), ("mentor", r"\bmentor")]
TOPICS = {
    "digital & AI": r"\b(ai|a\.i\.|artificial intelligence|digital|internet|icann|data|algorithm|machine learning|llm|genai)\b",
    "cyber": r"\b(cyber|cybersecurity|ict|pall mall|cert\b|ransomware|information security)\b",
    "peacebuilding": r"\b(peace|peacebuilding|mediation|conflict|ceasefire|reconciliation|peacekeeping)\b",
    "humanitarian tech": r"\b(humanitarian|icrc|refugee|unhcr|ocha|displacement|aid)\b",
    "multilateral diplomacy": r"\b(diplomacy|diplomatic|multilateral|united nations|\bun\b|ambassador|permanent mission|negotiat|gesda|anticipation)\b",
    "harmful information": r"\b(mis-?information|dis-?information|harmful information|hate speech|information integrity|infodemic|propaganda|fake news|fimi|"
                           r"information manipulation|online harms?|information disorder|content moderation)\b",
    "tech for good": r"\b(for good|tech for good|technology for good|ai for good|social impact|humanitarian innovation|digital public good|civic tech)\b",
}
RANK = {"none": 0, "invited": 1, "interested": 2, "tentative": 3, "confirmed": 4, "declined": 9}


def looks_like_event(title: str, location: str | None, self_organizer: bool, attendees: int | None) -> bool:
    t = (title or "").strip()
    if REMINDER.search(t):
        return False
    if NOT_EVENT.search(t) and not EVENT_WORDS.search(re.sub(NOT_EVENT, "", t)):
        return False
    if EVENT_WORDS.search(t):
        return True
    return bool(location) and not self_organizer                      # an invitation to somewhere, from someone else


def topics_of(text: str) -> str | None:
    found = [name for name, pat in TOPICS.items() if re.search(pat, text or "", re.I)]
    return ",".join(found) or None


def role_of(title: str) -> str | None:
    for name, pat in ROLES:
        if re.search(pat, title or "", re.I):
            return name
    return None


def derive_status(my_response: str | None, self_organizer: bool, attendees: int | None, role: str | None) -> str:
    """accepted -> confirmed; tentative; needsAction -> invited; declined. Something she put on her own calendar counts as confirmed."""
    if my_response == "accepted" or (self_organizer and not attendees):
        return "confirmed"
    return {"tentative": "tentative", "needsAction": "invited", "declined": "declined"}.get(my_response or "", "none")


def _upsert(conn, key: str, fields: dict) -> int:
    row = conn.execute("SELECT id FROM events WHERE dedupe_key = ?", (key,)).fetchone()
    if row is None:
        cols = {"dedupe_key": key, **fields}
        return conn.execute(f"INSERT INTO events ({','.join(cols)}) VALUES ({','.join('?' * len(cols))})", list(cols.values())).lastrowid
    conn.execute(f"UPDATE events SET {', '.join(f'{k}=?' for k in fields)}, updated_at=datetime('now') WHERE id=?", [*fields.values(), row["id"]])
    return row["id"]


def sync_calendar(conn: sqlite3.Connection) -> dict:
    """Mirror event-like calendar entries into `events` (work calendar only; cancelled ones disappear). Her overrides are kept."""
    added = updated = 0
    live = set()
    with conn:
        for r in conn.execute("SELECT * FROM calendar_events WHERE status != 'cancelled' AND space = 'work'"):
            key = f"cal:{r['source_ref']}"
            existing = conn.execute("SELECT forced, hidden FROM events WHERE dedupe_key = ?", (key,)).fetchone()
            if not (looks_like_event(r["title"], r["location"], bool(r["self_organizer"]), r["attendee_count"]) or (existing and existing["forced"])):
                continue
            live.add(key)
            role = role_of(r["title"])
            text = f"{r['title']} {r['location'] or ''}"
            fields = {"title": r["title"], "start": r["start"], "end": r["end"], "all_day": r["all_day"], "venue": r["location"], "online": int(bool(r["link"]) and not r["location"]),
                      "url": r["link"], "topics": topics_of(text), "geneva": int(bool(GENEVA.search(text))), "role": role,
                      "derived_status": derive_status(r["my_response"], bool(r["self_organizer"]), r["attendee_count"], role), "source_kind": "calendar", "tier": "S2"}
            before = conn.execute("SELECT id FROM events WHERE dedupe_key = ?", (key,)).fetchone()
            eid = _upsert(conn, key, fields)
            added += before is None
            updated += before is not None
            conn.execute("INSERT INTO event_evidence (event_id, kind, ref, signal, detail) VALUES (?,?,?,?,?) ON CONFLICT (event_id, kind, ref) DO UPDATE SET signal=excluded.signal, observed_at=datetime('now')",
                         (eid, "calendar", r["source_ref"], r["my_response"] or ("own entry" if r["self_organizer"] else "no response"), f"{r['attendee_count'] or 0} attendee(s)"))
        for r in conn.execute("SELECT id, dedupe_key FROM events WHERE source_kind='calendar'").fetchall():
            if r["dedupe_key"] not in live:
                conn.execute("DELETE FROM events WHERE id = ?", (r["id"],))
    return {"added": added, "updated": updated}


def effective_status(row) -> str:
    return row["user_status"] or row["derived_status"]


def _end_of(r) -> datetime | None:
    try:
        if r["all_day"]:
            return datetime.fromisoformat((r["end"] or r["start"])[:10])
        return datetime.fromisoformat(r["end"] or r["start"]).replace(tzinfo=None)
    except ValueError:
        return None


def _start_of(r) -> datetime | None:
    try:
        return datetime.fromisoformat(r["start"][:10] if r["all_day"] else r["start"]).replace(tzinfo=None)
    except ValueError:
        return None


def clashes(rows: list) -> dict[int, list[int]]:
    """Confirmed or tentative events that overlap in time (all-day events overlap by day). Returns id -> ids it clashes with."""
    live = [r for r in rows if effective_status(r) in ("confirmed", "tentative")]
    spans = []
    for r in live:
        a, b = _start_of(r), _end_of(r)
        if a is None:
            continue
        if r["all_day"]:
            b = (b or a)                                  # Google's all-day end is exclusive
        else:
            b = b or a + timedelta(hours=1)
        spans.append((r["id"], a, b, bool(r["all_day"])))
    out: dict[int, list[int]] = {}
    for i, (ida, a1, b1, d1) in enumerate(spans):
        for idb, a2, b2, d2 in spans[i + 1:]:
            if d1 and d2 and not (a1 < b2 and a2 < b1):
                continue
            if (d1 != d2):                                # an all-day marker does not block a timed event
                continue
            if a1 < b2 and a2 < b1:
                out.setdefault(ida, []).append(idb); out.setdefault(idb, []).append(ida)
    return out


def _view(r, clash_ids: list[int]) -> dict:
    return {"id": r["id"], "title": r["title"], "start": r["start"], "end": r["end"], "all_day": bool(r["all_day"]), "venue": r["venue"], "online": bool(r["online"]), "url": r["url"],
            "organizer": r["organizer"], "topics": (r["topics"] or "").split(",") if r["topics"] else [], "geneva": bool(r["geneva"]), "role": r["role"],
            "status": effective_status(r), "derived_status": r["derived_status"], "overridden": r["user_status"] is not None, "source_kind": r["source_kind"],
            "hidden": bool(r["hidden"]), "clashes": clash_ids}


def list_events(conn: sqlite3.Connection, today: date, scope: str = "upcoming", q: str | None = None, status: str | None = None,
                geneva: bool | None = None, topic: str | None = None, limit: int = 300) -> dict:
    """upcoming: today and later (and anything still running). archive: before today, newest first, searchable."""
    rows = conn.execute("SELECT * FROM events WHERE hidden = 0").fetchall()
    day = today.isoformat()
    def ends_after(r):
        e = (r["end"] or r["start"])[:10]
        return e >= day if not r["all_day"] else (r["end"] or r["start"])[:10] > day or r["start"][:10] >= day
    sel = [r for r in rows if (ends_after(r) if scope == "upcoming" else not ends_after(r))]
    if q:
        needle = q.lower()
        sel = [r for r in sel if needle in " ".join(str(r[k] or "") for k in ("title", "venue", "organizer", "topics")).lower()]
    if status:
        sel = [r for r in sel if (effective_status(r) == "confirmed" if status == "confirmed" else effective_status(r) in status.split(","))]
    if geneva is not None:
        sel = [r for r in sel if bool(r["geneva"]) == geneva]
    if topic:
        sel = [r for r in sel if topic in (r["topics"] or "")]
    sel.sort(key=lambda r: r["start"], reverse=(scope == "archive"))
    cl = clashes([r for r in rows if ends_after(r)] if scope == "upcoming" else rows)
    items = [_view(r, cl.get(r["id"], [])) for r in sel[:limit]]
    counts = {s: sum(1 for r in rows if ends_after(r) and effective_status(r) == s) for s in ("confirmed", "tentative", "invited", "interested")}
    return {"scope": scope, "items": items, "total": len(sel), "counts": counts, "topics": list(TOPICS)}


def detail(conn: sqlite3.Connection, eid: int, today: date) -> dict | None:
    r = conn.execute("SELECT * FROM events WHERE id = ?", (eid,)).fetchone()
    if r is None:
        return None
    ev = [dict(e) for e in conn.execute("SELECT kind, signal, detail, observed_at FROM event_evidence WHERE event_id = ? ORDER BY id", (eid,))]
    rows = conn.execute("SELECT * FROM events WHERE hidden = 0").fetchall()
    return {**_view(r, clashes(rows).get(eid, [])), "evidence": ev, "forced": bool(r["forced"])}


def set_status(conn: sqlite3.Connection, eid: int, status: str | None) -> bool:
    if status not in ("interested", "confirmed", "declined", None):
        raise ValueError("status must be interested, confirmed, declined or null")
    with conn:
        return conn.execute("UPDATE events SET user_status=?, updated_at=datetime('now') WHERE id=?", (status, eid)).rowcount > 0


def hide(conn: sqlite3.Connection, eid: int, hidden: bool = True) -> bool:
    """'Not an event / not relevant'. A hidden calendar entry stays hidden across syncs (the row is kept; sync only refreshes its fields)."""
    with conn:
        return conn.execute("UPDATE events SET hidden=?, updated_at=datetime('now') WHERE id=?", (int(hidden), eid)).rowcount > 0

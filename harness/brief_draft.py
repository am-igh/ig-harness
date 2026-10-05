"""The morning brief as a Gmail DRAFT in her own work mailbox, so she can compare it with her Claude brief. Never sent: this goes through the same door as every
draft (a request file that the Mac-side draft agent re-checks against the database and turns into a draft, and nothing more).
Standing approval: Anne-Marie asked on 5 Oct 2026 for one draft each morning at 08:00. It is therefore recorded as approved by the harness for THIS purpose only:
kind `new`, addressed to her own address and nobody else, subject starting "[Harness] Morning brief", one per day. Switch off in the brief drawer (setting `brief_draft`)."""
import json
import sqlite3
import uuid
from datetime import datetime, time
from pathlib import Path

from harness import brief, brief_ai, draftspec
from harness.config import now_local

SUBJECT_PREFIX = "[Harness] Morning brief"
HOUR = time(8, 0)


class BriefDraftRefused(ValueError):
    pass


def _setting(conn, key: str) -> str:
    r = conn.execute("SELECT value FROM draft_settings WHERE key=?", (key,)).fetchone()
    return (r["value"] if r else "") or ""


def enabled(conn: sqlite3.Connection) -> bool:
    return _setting(conn, "brief_draft") != "off"          # on unless she switches it off


def set_enabled(conn: sqlite3.Connection, on: bool) -> None:
    with conn:
        conn.execute("INSERT INTO draft_settings (key, value, source) VALUES ('brief_draft', ?, 'edited') ON CONFLICT (key) DO UPDATE SET value=excluded.value, source='edited'", ("on" if on else "off",))


def queue(conn: sqlite3.Connection, day: str, outbox: Path) -> str:
    """Hand the day's saved brief to the draft agent. One draft per day: refused if one is already queued or saved."""
    r = conn.execute("SELECT * FROM briefs WHERE day = ?", (day,)).fetchone()
    if r is None:
        raise BriefDraftRefused("There is no brief for this day yet")
    if r["draft_status"] in ("queued", "saved"):
        raise BriefDraftRefused("This day's brief is already in Gmail or on its way")
    me = _setting(conn, "my_address").lower()
    if not me:
        raise BriefDraftRefused("The harness does not yet know your address (it learns it from the next Gmail refresh)")
    title = json.loads(r["data"])["title"]
    try:
        fields = draftspec.validate({"kind": "new", "to": [me], "cc": [], "subject": f"{SUBJECT_PREFIX} — {title}", "body": r["text"]})
    except draftspec.InvalidDraft as e:
        raise BriefDraftRefused(str(e))
    h, rid, stamp = draftspec.content_hash(fields), str(uuid.uuid4()), now_local().isoformat(timespec="seconds")
    with conn:
        conn.execute("INSERT INTO draft_requests (id, kind, to_json, cc_json, subject, body, status, body_hash, created_at, approved_at, model, sensitivity) "
                     "VALUES (?, 'new', ?, '[]', ?, ?, 'approved', ?, ?, ?, ?, 'S2')", (rid, json.dumps([me]), fields["subject"], fields["body"], h, stamp, stamp, r["model"]))
        conn.execute("UPDATE briefs SET draft_status='queued', draft_id=?, draft_note=NULL WHERE day=?", (rid, day))
    outbox.mkdir(parents=True, exist_ok=True)
    tmp = outbox / f"{rid}.tmp"
    tmp.write_text(json.dumps({"request_id": rid, "fields": fields, "hash": h}))
    tmp.replace(outbox / f"{rid}.json")
    return rid


def sync_status(conn: sqlite3.Connection) -> None:
    """Copy what the draft agent reported (via draft_requests) onto the brief."""
    for b in conn.execute("SELECT day, draft_id FROM briefs WHERE draft_status = 'queued' AND draft_id IS NOT NULL").fetchall():
        d = conn.execute("SELECT status, error FROM draft_requests WHERE id = ?", (b["draft_id"],)).fetchone()
        if d and d["status"] == "created":
            with conn:
                conn.execute("UPDATE briefs SET draft_status='saved' WHERE day=?", (b["day"],))
        elif d and d["status"] in ("failed", "cancelled"):
            with conn:
                conn.execute("UPDATE briefs SET draft_status='failed', draft_note=? WHERE day=?", ((d["error"] or d["status"])[:200], b["day"]))


def tick(conn: sqlite3.Connection, outbox: Path, now: datetime | None = None, gateway=None) -> str | None:
    """Called every minute: from 08:00 Geneva time, once a day, build the brief (section 5 by the local model if it is there) and queue its draft."""
    now = now or now_local()
    sync_status(conn)
    if not enabled(conn) or now.time() < HOUR:
        return None
    day = now.date().isoformat()
    r = conn.execute("SELECT draft_status FROM briefs WHERE day = ?", (day,)).fetchone()
    if r is not None and r["draft_status"] != "none":
        return None                                           # already queued, saved, or failed (a failed one is not retried by itself: no duplicate drafts)
    if not _setting(conn, "my_address"):
        return None
    b = brief_ai.write_attention(brief.build(conn, now), gateway)
    brief.save(conn, b, model=b.get("attention_model"))
    return queue(conn, day, outbox)

"""event_mail.json (written by the Mac-side helper from her inbox) -> events. Rules only:
  Club Diplomatique subjects, Luma registration emails, organiser registration confirmations, the Genève internationale newsletter tables.
  Anything that looks like an invitation but cannot be read by rules becomes a *candidate* for the local-model step.
The same event seen in several places is merged into one (similar title on overlapping days), keeping all the evidence."""
import json
import re
import sqlite3
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from harness import event_parsers as P
from harness import events as E
from harness.importers.common import Report

FILE = "event_mail.json"
INVITE = re.compile(r"\b(invit\w*|save[- ]the[- ]date|speaking|speaker|panel(l?ist)?|keynote|webinar|conference|symposium|workshop|summit|forum|roundtable|reception|launch|seminar|dialogue|briefing|ceremony)\b", re.I)


def _sent_iso(ms: int) -> str:
    return datetime.fromtimestamp(ms / 1000, timezone.utc).isoformat()


def _end_exclusive(end_iso: str | None) -> str | None:
    return (date.fromisoformat(end_iso) + timedelta(days=1)).isoformat() if end_iso else None


def import_event_mail(conn: sqlite3.Connection, folder: Path) -> list[Report]:
    rep = Report(source="events:mail")
    path = Path(folder) / FILE
    if not path.exists():
        rep.notes.append("no event mail file yet: run `python3 tools/google_helper.py sync-events` on the Mac")
        return [rep]
    data = json.loads(path.read_text())
    me = (data.get("me") or "").lower()
    before = conn.execute("SELECT COUNT(*) FROM events").fetchone()[0]
    with conn:
        for m in data.get("messages", []):
            sender = (m.get("from_email") or "").lower()
            dom = sender.split("@")[-1]
            subj, snip, sent = m.get("subject") or "", m.get("snippet") or "", _sent_iso(m.get("date_ms", 0))
            if not sender or sender == me:
                continue
            ref = m["id"]
            if dom.endswith("clubdiplomatique.ch"):
                c = P.parse_club_subject(subj)
                if not c:
                    rep.skipped += 1
                    continue
                E.upsert_external(conn, source_kind="email-club", tier="S2", title=c["title"], start=c["start"], end=None, all_day=c["all_day"], venue=c["venue"], online=False, url=None,
                                  organizer=c["organizer"], evidence=("email-club", ref, c["kind"], sent[:10]), extra_text="Geneva diplomacy")
            elif "luma-mail.com" in dom or dom == "lu.ma":
                l = P.parse_luma(subj, snip, sent)
                if not l:
                    rep.skipped += 1
                    continue
                E.upsert_external(conn, source_kind="email-luma", tier="S2", title=l["title"], start=l["start"], end=l["end"], all_day=False, venue=l["venue"], online=l["online"], url=None,
                                  organizer=None, evidence=("email-luma", ref, f"registration {l['what']}", sent[:10]))
            elif dom.endswith("geneve-int.ch"):
                for row in m.get("listing", []):
                    try:
                        start, end = row["start"], _end_exclusive(row["end"]) if row["end"] and row["end"] != row["start"] else None
                        loc = row.get("location") or ""
                        online = bool(re.match(r"(?i)^(online|virtual|hybrid)", loc))
                        rel = bool(E.topics_of(f"{row['title']} {row.get('theme') or ''}"))
                        E.upsert_external(conn, source_kind="listing-geneve-int", tier="S0", title=row["title"], start=start, end=end, all_day=True, venue=loc or None, online=online,
                                          url=row.get("url"), organizer=row.get("organizer"), evidence=("listing-geneve-int", ref, row.get("theme"), sent[:10]), relevant=rel,
                                          extra_text=f"Geneva {row.get('theme') or ''}")
                    except (KeyError, ValueError):
                        rep.skipped += 1
            else:
                r = P.parse_registration(subj, snip, sent)
                if r:
                    E.upsert_external(conn, source_kind="email-registration", tier="S2", title=r["title"], start=r["start"], end=r["end"], all_day=True, venue=r["venue"], online=False, url=None,
                                      organizer=dom, evidence=("email-registration", ref, "registration confirmed", sent[:10]))
                elif INVITE.search(subj) or P.is_registration_confirmation(subj):          # a confirmation without a readable date also goes to the model step
                    conn.execute("INSERT OR IGNORE INTO event_candidates (message_id, thread_id, received_at, sender, subject, snippet, bulk, direct, body) VALUES (?,?,?,?,?,?,?,?,?)",
                                       (ref, m.get("thread_id") or ref, sent[:10], sender, subj[:200], snip[:300], int(bool(m.get("bulk"))), int(bool(m.get("direct"))), m.get("body")))
                    if m.get("body") is not None:                                           # a later sync may bring the body of an earlier candidate ("" = the email has no text)
                        conn.execute("UPDATE event_candidates SET body = ? WHERE message_id = ? AND body IS NULL", (m["body"], ref))
    after = conn.execute("SELECT COUNT(*) FROM events").fetchone()[0]
    rep.added = max(0, after - before)
    rep.unchanged = max(0, len(data.get("messages", [])) - rep.added - rep.skipped)
    return [rep]

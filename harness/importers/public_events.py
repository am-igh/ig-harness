"""public_events.json (International Geneva listings fetched by tools/events_helper.py from public pages) -> events. S0 data. The same event also seen in an email or the
calendar becomes one card with all the evidence."""
import json
import sqlite3
from datetime import date, timedelta
from pathlib import Path

from harness import events as E
from harness.importers.common import Report

FILE = "public_events.json"
KINDS = {"geneve-int": ("web-geneve-int", "listing-web-geneve-int"), "club": ("web-club", "listing-web-club"), "unog": ("web-unog", "listing-web-unog")}


def import_public_events(conn: sqlite3.Connection, folder: Path) -> list[Report]:
    rep = Report(source="events:public")
    path = Path(folder) / FILE
    if not path.exists():
        rep.notes.append("no public listings yet: run `python3 tools/events_helper.py pull` on the Mac")
        return [rep]
    doc = json.loads(path.read_text())
    before = conn.execute("SELECT COUNT(*) FROM events").fetchone()[0]
    with conn:
        for name, src in doc.get("sources", {}).items():
            if src.get("error"):
                rep.notes.append(f"{name}: {src['error']}")
            kind, ev_kind = KINDS.get(name, ("web-other", "listing-web-other"))
            for e in src.get("events", []):
                try:
                    start, last = e["start"], e.get("end") or e["start"]
                    end = (date.fromisoformat(last) + timedelta(days=1)).isoformat() if last != start else None
                    # the Club's own events are the ones she belongs to; other listings only when they match her topics
                    relevant = name == "club" or bool(E.topics_of(f"{e['title']} {e.get('organizer') or ''}"))
                    venue = e.get("venue")
                    E.upsert_external(conn, source_kind=kind, tier="S0", title=e["title"], start=start, end=end, all_day=True, venue=venue,
                                      online=bool(venue and venue.lower().startswith(("online", "virtual", "hybrid"))), url=e.get("url"), organizer=e.get("organizer"),
                                      evidence=(ev_kind, e.get("url") or e["title"], "listed", e.get("organizer")), relevant=relevant, extra_text=f"Geneva {e.get('organizer') or ''}")
                except (KeyError, ValueError):
                    rep.skipped += 1
    rep.added = max(0, conn.execute("SELECT COUNT(*) FROM events").fetchone()[0] - before)
    return [rep]

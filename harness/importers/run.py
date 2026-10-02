"""Run all importers: `python -m harness.importers.run` (or POST /api/import)."""
import os
from pathlib import Path

from harness import db
from harness.config import DATA_DIR
from harness import events as _events
from harness.importers.calendar import import_calendar
from harness.importers.costs import import_costs
from harness.importers.event_mail import import_event_mail
from harness.importers.gmail import import_gmail
from harness.importers.hours import import_hours
from harness.importers.correspondence import import_correspondence
from harness.importers.registre import import_registre
from harness.importers.suivi import import_suivi

# Read-only mounts, see docker-compose.yml
SUIVI_DIR = Path(os.environ.get("IG_SUIVI_DIR", "/sources/suivi"))
PROJETS_DIR = Path(os.environ.get("IG_PROJETS_DIR", "/sources/projets"))


def import_events(conn, folder) -> list:
    """Event-like calendar entries -> the Geneva-and-beyond events table (after the calendar import)."""
    from harness.importers.common import Report
    d = _events.sync_calendar(conn)
    return [Report(source="events:calendar", added=d["added"], updated=d["updated"])]


def run_all(conn=None, suivi_dir: Path = None, projets_dir: Path = None, data_dir: Path = None) -> list[dict]:
    own = conn is None
    conn = conn or db.connect()
    try:
        reports = []
        for label, fn, folder in (
            ("suivi", import_suivi, suivi_dir or SUIVI_DIR),
            ("registre", import_registre, projets_dir or PROJETS_DIR),
            ("hours", import_hours, projets_dir or PROJETS_DIR),
            ("costs", import_costs, projets_dir or PROJETS_DIR),
            ("calendar", import_calendar, data_dir or DATA_DIR),
            ("events", import_events, data_dir or DATA_DIR),
            ("event-mail", import_event_mail, data_dir or DATA_DIR),
            ("gmail", import_gmail, data_dir or DATA_DIR),
            ("correspondence", import_correspondence, data_dir or DATA_DIR),
        ):
            try:
                reports += [r.as_dict() for r in fn(conn, folder)]
            except Exception as e:  # report, don't crash the other importer
                reports.append({"source": label, "error": f"{type(e).__name__}: {e}"})
        return reports
    finally:
        if own:
            conn.close()


if __name__ == "__main__":
    import json
    print(json.dumps(run_all(), indent=2, ensure_ascii=False))

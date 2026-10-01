"""Run all importers: `python -m harness.importers.run` (or POST /api/import)."""
import os
from pathlib import Path

from harness import db
from harness.importers.registre import import_registre
from harness.importers.suivi import import_suivi

# Read-only mounts, see docker-compose.yml
SUIVI_DIR = Path(os.environ.get("IG_SUIVI_DIR", "/sources/suivi"))
PROJETS_DIR = Path(os.environ.get("IG_PROJETS_DIR", "/sources/projets"))


def run_all(conn=None, suivi_dir: Path = None, projets_dir: Path = None) -> list[dict]:
    own = conn is None
    conn = conn or db.connect()
    try:
        reports = []
        for label, fn, folder in (
            ("suivi", import_suivi, suivi_dir or SUIVI_DIR),
            ("registre", import_registre, projets_dir or PROJETS_DIR),
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

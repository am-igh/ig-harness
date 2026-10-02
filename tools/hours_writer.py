#!/usr/bin/env python3
"""Mac-side hours writer: the ONLY thing that writes to her hours.csv. Standard library only.

It APPENDS rows that Anne-Marie approved in the app (the Friday hours pass) and does nothing else:
  - it never edits, reorders or deletes an existing line: the old file content must still be the exact start of the new file;
  - before each write it saves a backup copy (~/IG-Harness-data/hours/backups, the last 20 are kept);
  - it waits while the file changed in the last 90 seconds (Excel or a sync may be using it);
  - each row is re-checked here against the harness database (opened read-only): it must be 'approved', with hours between 0 and 14,
    a project, a description and an evidence pointer (her rule: no hours without evidence); entered_on is today's Geneva date;
  - a row already in the file (same date, project, description, evidence) is not added twice;
  - after writing it re-reads the file; if anything is off it puts the old content back and reports a failure;
  - pause with `touch ~/IG-Harness-data/hours/DISABLED` (make hours-pause / hours-resume).

  python3 tools/hours_writer.py once      write whatever is approved now (the refresh agent also runs this)
  python3 tools/hours_writer.py dry-run   show what would be added
"""
import csv
import io
import json
import os
import re
import sqlite3
import sys
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
DATA = Path(os.environ.get("IG_DATA_DIR", Path.home() / "IG-Harness-data"))
REQUIRED = ["date", "project", "hours", "description", "evidence", "entered_on"]
QUIET_SECONDS = 90
KEEP_BACKUPS = 20


def projets_dir(root: Path = ROOT) -> Path | None:
    v = os.environ.get("PROJETS_DIR")
    if not v and (root / ".env").is_file():
        for line in (root / ".env").read_text().splitlines():
            if line.startswith("PROJETS_DIR="):
                v = line.split("=", 1)[1].strip().strip('"\'')
    return Path(v).expanduser() if v else None


def today_geneva() -> str:
    return datetime.now(ZoneInfo("Europe/Zurich")).date().isoformat()


def _clean(text) -> str:
    t = re.sub(r"[\x00-\x1f\x7f]+", " ", str(text or "")).strip()
    return ("'" + t) if t[:1] in ("=", "+", "-", "@") else t               # never let a spreadsheet read a description as a formula


def validate(r: dict, today: str) -> str | None:
    """None when the approved row may be written, else why not."""
    if r["status"] != "approved":
        return "not approved in the app"
    if r["hours"] is None or not 0 < r["hours"] <= 14:
        return "hours must be between 0 and 14"
    if not re.fullmatch(r"[A-Z0-9]{2,10}", r["project"] or ""):
        return "no valid project code"
    if not (r["description"] or "").strip() or not (r["evidence"] or "").strip():
        return "an hours entry needs a description and an evidence pointer"
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", r["date"] or "") or r["date"] > today:
        return "the date is missing or in the future"
    return None


def build_cells(header: list[str], r: dict, today: str) -> list[str]:
    vals = {"date": r["date"], "project": r["project"], "budget_line": _clean(r["budget_line"]), "hours": f"{r['hours']:g}", "rate": "",
            "description": _clean(r["description"]), "evidence": _clean(r["evidence"]), "source": "harness", "entered_on": today}
    return [vals.get(h, "") for h in header]


def _result(data: Path, pid: int, ok: bool, message: str) -> None:
    d = data / "hours" / "done"
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{pid}.json").write_text(json.dumps({"id": pid, "ok": ok, "message": message}))


def _backup(data: Path, path: Path, content: bytes, stamp: str) -> None:
    b = data / "hours" / "backups"
    b.mkdir(parents=True, exist_ok=True)
    (b / f"hours.csv.{stamp}").write_bytes(content)
    for old in sorted(b.glob("hours.csv.*"))[:-KEEP_BACKUPS]:
        old.unlink(missing_ok=True)


def run_once(data: Path = DATA, csv_path: Path | None = None, today: str | None = None, now: float | None = None, dry_run: bool = False) -> str:
    box = data / "hours" / "outbox"
    reqs = sorted(box.glob("*.json")) if box.is_dir() else []
    if not reqs:
        return "nothing to write"
    if (data / "hours" / "DISABLED").exists():
        return "paused (make hours-resume to continue)"
    today = today or today_geneva()
    csv_path = csv_path or ((projets_dir() or Path("/nonexistent")) / "hours.csv")
    ids = []
    for f in reqs:
        try:
            ids.append((int(json.loads(f.read_text())["id"]), f))
        except (ValueError, KeyError, OSError):
            f.unlink(missing_ok=True)
    try:
        db = sqlite3.connect(f"file:{data / 'harness.db'}?mode=ro", uri=True, timeout=10)
        db.row_factory = sqlite3.Row
        rows = {i: db.execute("SELECT * FROM hour_proposals WHERE id = ?", (i,)).fetchone() for i, _ in ids}
        db.close()
    except sqlite3.Error:
        return "could not read the harness database; nothing written"
    if not csv_path.is_file():
        for i, f in ids:
            _result(data, i, False, "hours.csv was not found")
            f.unlink(missing_ok=True)
        return "hours.csv not found"
    now = now if now is not None else time.time()
    if now - csv_path.stat().st_mtime < QUIET_SECONDS:
        return f"waiting: hours.csv changed in the last {QUIET_SECONDS} s (it will be tried again)"
    old = csv_path.read_bytes()
    text = old.decode("utf-8-sig")
    reader = list(csv.reader(io.StringIO(text)))
    header = reader[0] if reader else []
    if any(c not in header for c in REQUIRED):
        for i, f in ids:
            _result(data, i, False, "hours.csv does not have the expected columns; nothing written")
            f.unlink(missing_ok=True)
        return "unexpected columns in hours.csv; nothing written"
    existing = {(r[header.index("date")], r[header.index("project")], r[header.index("description")], r[header.index("evidence")]) for r in reader[1:] if len(r) >= len(header)}
    to_write, verdict = [], {}
    for i, f in ids:
        r = rows.get(i)
        why = "no such approved suggestion" if r is None else validate(dict(r), today)
        if why:
            verdict[i] = (False, why)
            continue
        cells = build_cells(header, dict(r), today)
        key = (cells[header.index("date")], cells[header.index("project")], cells[header.index("description")], cells[header.index("evidence")])
        if key in existing:
            verdict[i] = (True, "already in hours.csv; nothing added")
        else:
            to_write.append((i, cells)); existing.add(key); verdict[i] = (True, "added to hours.csv")
    if dry_run:
        return "would add:\n" + "\n".join("  " + ", ".join(c[:40] for c in cells) for _, cells in to_write)
    if to_write:
        eol = "\r\n" if b"\r\n" in old else "\n"
        buf = io.StringIO()
        w = csv.writer(buf, lineterminator=eol)
        for _, cells in to_write:
            w.writerow(cells)
        add = ((eol if old and not old.endswith(b"\n") else "") + buf.getvalue()).encode("utf-8")
        _backup(data, csv_path, old, datetime.now().strftime("%Y%m%d-%H%M%S"))
        try:
            with open(csv_path, "ab") as fh:
                fh.write(add)
                fh.flush()
                os.fsync(fh.fileno())
            new = csv_path.read_bytes()
            got = list(csv.reader(io.StringIO(new.decode("utf-8-sig"))))[-len(to_write):]
            good = new.startswith(old) and got == [c for _, c in to_write]
        except Exception:
            good = False
        if not good:
            csv_path.write_bytes(old)                                        # put her file back exactly as it was
            for i, _ in to_write:
                verdict[i] = (False, "the file did not verify after writing; her original was put back")
    for i, f in ids:
        ok, msg = verdict.get(i, (False, "not processed"))
        _result(data, i, ok, msg)
        f.unlink(missing_ok=True)
    return f"added {sum(1 for i, _ in to_write if verdict[i][0])} row(s); {sum(1 for v in verdict.values() if not v[0])} refused"


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd in ("once", "dry-run"):
        print(run_once(dry_run=(cmd == "dry-run")))
    else:
        sys.exit(__doc__)

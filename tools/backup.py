#!/usr/bin/env python3
"""Backups of the harness database. Standard library only; runs on the Mac.

The database (~/IG-Harness-data/harness.db) holds everything that only exists inside the harness: what she has
ticked off and when, her edits, email verdicts and rules, style profiles, drafts. Everything else (calendar,
Gmail, Suivi) can be fetched again. Backups go to ~/IG-Harness-Backups, a folder of their own, and they stay on
this Mac: the database contains confidential (S2) and personal (S3) data, so it is never copied to a cloud
service by this tool. (Time Machine or an encrypted external drive can copy the folder.)

  backup.py backup               make a verified snapshot now
  backup.py daily                make one only if there is none yet today (used by the refresh agent)
  backup.py list                 show the snapshots
  backup.py verify [FILE]        check a snapshot (fingerprint, integrity, row counts); default: newest
  backup.py restore-check [FILE] restore into a throwaway folder and compare with the live database
  backup.py prune                apply the retention rules (14 daily, 12 monthly)
  backup.py restore FILE --yes   put a snapshot in place (the harness must be stopped; the old file is kept)
"""
import hashlib
import json
import os
import re
import shutil
import sqlite3
import sys
import tempfile
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = Path(os.environ.get("IG_DATA_DIR", Path.home() / "IG-Harness-data"))
BACKUPS = Path(os.environ.get("IG_BACKUP_DIR", Path.home() / "IG-Harness-Backups"))
DB_NAME = "harness.db"
NAME = re.compile(r"^harness-(\d{4})-(\d{2})-(\d{2})-(\d{4})\.db$")
KEEP_DAILY_DAYS = 14
KEEP_MONTHS = 12
REQUIRED_TABLES = {"tasks", "deadlines", "done_log", "waiting_on", "journal_entries", "emails", "draft_requests", "style_profiles", "privacy_log"}


class BackupError(Exception):
    pass


def _ro(path: Path) -> sqlite3.Connection:
    return sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=30)


def table_counts(conn: sqlite3.Connection) -> dict[str, int]:
    names = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")]
    return {n: conn.execute(f'SELECT COUNT(*) FROM "{n}"').fetchone()[0] for n in names}


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def manifest_path(db_file: Path) -> Path:
    return db_file.with_suffix(".json")


def create_backup(src: Path | None = None, dest: Path | None = None, now: datetime | None = None) -> Path:
    """A consistent copy made with SQLite's own backup API (safe while the app is writing), then verified."""
    src, dest, now = src or DATA / DB_NAME, dest or BACKUPS, now or datetime.now()
    if not src.exists():
        raise BackupError(f"no database at {src}")
    dest.mkdir(parents=True, exist_ok=True)
    dest.chmod(0o700)
    final = dest / f"harness-{now:%Y-%m-%d-%H%M}.db"
    tmp = dest / f".{final.name}.tmp"
    tmp.unlink(missing_ok=True)
    source = _ro(src)
    target = sqlite3.connect(tmp)
    try:
        source.backup(target)
    finally:
        source.close()
    check = target.execute("PRAGMA integrity_check").fetchone()[0]
    counts, version = table_counts(target), target.execute("PRAGMA user_version").fetchone()[0]
    target.close()
    if check != "ok":
        tmp.unlink(missing_ok=True)
        raise BackupError(f"the snapshot failed its integrity check: {check}")
    tmp.chmod(0o600)
    tmp.replace(final)
    manifest_path(final).write_text(json.dumps({"created_at": now.isoformat(timespec="seconds"), "schema_version": version, "tables": counts,
                                                "sha256": _sha256(final), "size_bytes": final.stat().st_size, "source": str(src)}, indent=1))
    manifest_path(final).chmod(0o600)
    return final


def snapshots(dest: Path | None = None) -> list[Path]:
    """Newest first."""
    dest = dest or BACKUPS
    return sorted((p for p in dest.glob("harness-*.db") if NAME.match(p.name)), reverse=True) if dest.is_dir() else []


def ensure_daily(src: Path | None = None, dest: Path | None = None, now: datetime | None = None) -> Path | None:
    now = now or datetime.now()
    today = f"harness-{now:%Y-%m-%d}-"
    if any(p.name.startswith(today) for p in snapshots(dest)):
        return None
    return create_backup(src, dest, now)


def verify(path: Path) -> list[str]:
    """Problems found in a snapshot; an empty list means it is sound."""
    problems = []
    mp = manifest_path(path)
    if not path.exists():
        return [f"{path.name} does not exist"]
    if not mp.exists():
        problems.append("no manifest next to the snapshot")
        manifest = {}
    else:
        manifest = json.loads(mp.read_text())
        if manifest.get("sha256") != _sha256(path):
            problems.append("the file's fingerprint differs from when it was made (it was changed or damaged)")
    try:
        conn = _ro(path)
        try:
            if (r := conn.execute("PRAGMA integrity_check").fetchone()[0]) != "ok":
                problems.append(f"integrity check: {r}")
            if conn.execute("PRAGMA foreign_key_check").fetchall():
                problems.append("foreign key violations")
            tables = table_counts(conn)
            missing = REQUIRED_TABLES - set(tables)
            if missing:
                problems.append(f"missing tables: {', '.join(sorted(missing))}")
            if manifest and tables != manifest.get("tables"):
                problems.append("row counts differ from the manifest")
            if manifest and conn.execute("PRAGMA user_version").fetchone()[0] != manifest.get("schema_version"):
                problems.append("schema version differs from the manifest")
        finally:
            conn.close()
    except sqlite3.DatabaseError as e:
        problems.append(f"cannot be opened as a database: {e}")
    return problems


def restore_check(path: Path, live: Path | None = None) -> tuple[bool, list[str]]:
    """Restore into a throwaway folder, open it the way the harness does, and compare with the live database."""
    live = live or DATA / DB_NAME
    lines, ok = [], True
    problems = verify(path)
    if problems:
        return False, [f"FAIL verify: {p}" for p in problems]
    lines.append("verify: fingerprint, integrity and row counts are fine")
    with tempfile.TemporaryDirectory(prefix="ig-restore-test-") as tmp:
        copy = Path(tmp) / DB_NAME
        shutil.copy2(path, copy)
        sys.path.insert(0, str(ROOT))
        try:
            from harness import db as hdb
            conn = hdb.connect(copy)
            version = hdb.migrate(conn)                     # the real harness code opens it; no upgrade should be needed
            lines.append(f"harness opens it: schema version {version} of {len(hdb.MIGRATIONS)}")
            if version != len(hdb.MIGRATIONS):
                ok = False
            probe = {t: conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in ("tasks", "done_log", "emails", "style_profiles")}
            conn.close()
            lines.append("reads: " + ", ".join(f"{k} {v}" for k, v in probe.items()))
        except Exception as e:
            return False, lines + [f"FAIL the harness could not open the restored copy: {type(e).__name__}: {e}"]
        finally:
            sys.path.pop(0)
    if live.exists():
        b, l = table_counts(_ro(path)), table_counts(_ro(live))
        shrank = [f"{t} ({b[t]} in backup, {l.get(t, 0)} now)" for t in b if t in l and b[t] > l[t]]
        grew = sum(max(0, l[t] - b.get(t, 0)) for t in l)
        lines.append(f"compared with the live database: {grew} newer rows exist now that the backup does not have")
        if shrank:
            ok = False
            lines.append("FAIL the backup has MORE rows than the live database in: " + "; ".join(shrank) + " (was data lost?)")
    return ok, lines


def prune(dest: Path | None = None, now: datetime | None = None) -> list[Path]:
    """Keep the newest snapshot of each of the last 14 days, plus the first of each of the last 12 months, plus the newest overall."""
    dest, now = dest or BACKUPS, now or datetime.now()
    files = snapshots(dest)
    keep, seen_days, first_of_month = set(), set(), {}
    for p in files:                                   # newest first
        y, m, d, _ = map(int, NAME.match(p.name).groups())
        day = datetime(y, m, d)
        if (now - day).days < KEEP_DAILY_DAYS and day not in seen_days:
            seen_days.add(day); keep.add(p)
    for p in reversed(files):                         # oldest first: the first snapshot of each month
        y, m, d, _ = map(int, NAME.match(p.name).groups())
        first_of_month.setdefault((y, m), p)
    cutoff = (now.year * 12 + now.month) - KEEP_MONTHS
    keep |= {p for (y, m), p in first_of_month.items() if y * 12 + m > cutoff}
    if files:
        keep.add(files[0])
    gone = [p for p in files if p not in keep]
    for p in gone:
        p.unlink(missing_ok=True)
        manifest_path(p).unlink(missing_ok=True)
    return gone


def _api_up() -> bool:
    try:
        with urllib.request.urlopen("http://127.0.0.1:5173/api/health", timeout=3) as r:
            return r.status == 200
    except Exception:
        return False


def restore(path: Path, live: Path | None = None, now: datetime | None = None, api_up=_api_up) -> Path:
    """Put a snapshot in place. The current database is kept next to it, never deleted."""
    live, now = live or DATA / DB_NAME, now or datetime.now()
    if api_up():
        raise BackupError("the harness is running. Stop it first with `make down`, then restore.")
    if (problems := verify(path)):
        raise BackupError("this snapshot is not sound: " + "; ".join(problems))
    kept = None
    if live.exists():
        kept = live.with_name(f"{live.name}.before-restore-{now:%Y%m%d-%H%M%S}")
        live.replace(kept)
    for ext in ("-journal", "-wal", "-shm"):
        live.with_name(live.name + ext).unlink(missing_ok=True)
    tmp = live.with_name(live.name + ".restoring")
    shutil.copy2(path, tmp)
    tmp.replace(live)
    live.chmod(0o600)
    return kept or live


def _pick(arg: str | None) -> Path:
    if arg:
        p = Path(arg).expanduser()
        return p if p.exists() else BACKUPS / arg
    s = snapshots()
    if not s:
        raise BackupError("there are no snapshots yet: run `make backup`")
    return s[0]


def main(argv: list[str]) -> int:
    cmd = argv[1] if len(argv) > 1 else ""
    try:
        if cmd == "backup":
            p = create_backup()
            gone = prune()
            print(f"Backup saved: {p}  ({p.stat().st_size // 1024} KB)" + (f"; pruned {len(gone)} old snapshot(s)" if gone else ""))
        elif cmd == "daily":
            p = ensure_daily()
            prune()
            print(f"Backup saved: {p}" if p else "A backup for today already exists.")
        elif cmd == "list":
            for p in snapshots():
                m = json.loads(manifest_path(p).read_text()) if manifest_path(p).exists() else {}
                print(f"{p.name}  {p.stat().st_size // 1024:>6} KB  schema v{m.get('schema_version', '?')}  rows {sum((m.get('tables') or {}).values())}")
            if not snapshots():
                print("No snapshots yet.")
        elif cmd == "verify":
            p = _pick(argv[2] if len(argv) > 2 else None)
            problems = verify(p)
            print(("OK: " if not problems else "PROBLEM: ") + p.name + ("" if not problems else "\n  " + "\n  ".join(problems)))
            return 1 if problems else 0
        elif cmd == "restore-check":
            p = _pick(argv[2] if len(argv) > 2 else None)
            ok, lines = restore_check(p)
            print(f"Restore test of {p.name}")
            print("\n".join("  " + ln for ln in lines))
            print("RESULT: " + ("PASS" if ok else "FAIL"))
            return 0 if ok else 1
        elif cmd == "prune":
            print(f"Pruned {len(prune())} old snapshot(s).")
        elif cmd == "restore":
            if "--yes" not in argv or len(argv) < 4:
                sys.exit("Usage: backup.py restore FILE --yes   (the harness must be stopped: make down)")
            kept = restore(_pick(argv[2]))
            print(f"Restored. The previous database was kept as {kept}\nNow start the harness again: make up")
        else:
            sys.exit(__doc__)
    except BackupError as e:
        print(f"Backup problem: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))

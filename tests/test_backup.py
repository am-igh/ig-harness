"""Backups of the harness database: consistent, verified, retained sensibly, restorable, never destructive."""
import json
import sqlite3
import stat
from datetime import datetime, timedelta

import pytest

from harness import db
from tools import backup as bk


@pytest.fixture
def live(tmp_path):
    path = tmp_path / "data" / "harness.db"
    path.parent.mkdir()
    c = db.connect(path); db.migrate(c)
    c.execute("INSERT INTO tasks (title, due_date) VALUES ('Keep me', '2026-10-05')")
    c.execute("INSERT INTO done_log (item_type, item_id, title, done_at) VALUES ('task', 1, 'Done thing', '2026-10-01 10:00:00')")
    c.execute("INSERT INTO triage_rules (text) VALUES ('A rule of hers that must survive.')")
    c.commit(); c.close()
    return path


@pytest.fixture
def dest(tmp_path):
    return tmp_path / "backups"


NOW = datetime(2026, 10, 1, 12, 0)


def rows(path, table):
    c = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        return c.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
    finally:
        c.close()


def test_a_backup_is_a_verified_private_copy_with_a_manifest(live, dest):
    p = bk.create_backup(live, dest, NOW)
    assert p.name == "harness-2026-10-01-1200.db" and rows(p, "tasks") == 1 and rows(p, "done_log") == 1
    m = json.loads(bk.manifest_path(p).read_text())
    assert m["schema_version"] == len(db.MIGRATIONS) and m["tables"]["tasks"] == 1 and len(m["sha256"]) == 64
    assert stat.S_IMODE(p.stat().st_mode) == 0o600 and stat.S_IMODE(dest.stat().st_mode) == 0o700
    assert bk.verify(p) == []


def test_a_backup_is_consistent_even_while_the_app_is_writing(live, dest):
    writer = sqlite3.connect(live)
    writer.execute("INSERT INTO tasks (title) VALUES ('half-written, never committed')")      # an open, uncommitted write
    p = bk.create_backup(live, dest, NOW)
    writer.rollback(); writer.close()
    assert rows(p, "tasks") == 1 and bk.verify(p) == []


def test_it_refuses_to_back_up_something_that_is_not_there(tmp_path, dest):
    with pytest.raises(bk.BackupError, match="no database"):
        bk.create_backup(tmp_path / "nope.db", dest, NOW)


def test_one_automatic_backup_per_day(live, dest):
    assert bk.ensure_daily(live, dest, NOW) is not None
    assert bk.ensure_daily(live, dest, NOW + timedelta(hours=5)) is None
    assert bk.ensure_daily(live, dest, NOW + timedelta(days=1)) is not None
    assert len(bk.snapshots(dest)) == 2 and bk.snapshots(dest)[0].name.startswith("harness-2026-10-02")


# ---------------------------------------------------------------- verification catches damage
def test_verify_catches_a_changed_file(live, dest):
    p = bk.create_backup(live, dest, NOW)
    data = bytearray(p.read_bytes()); data[-100] ^= 0xFF; p.write_bytes(bytes(data))
    assert any("fingerprint" in x or "integrity" in x or "cannot be opened" in x for x in bk.verify(p))


def test_verify_catches_a_missing_manifest_a_wrong_manifest_and_a_missing_table(live, dest):
    p = bk.create_backup(live, dest, NOW)
    m = json.loads(bk.manifest_path(p).read_text())
    m["tables"]["tasks"] = 99
    bk.manifest_path(p).write_text(json.dumps(m))
    assert any("row counts" in x for x in bk.verify(p))
    bk.manifest_path(p).unlink()
    assert any("no manifest" in x for x in bk.verify(p))
    other = dest / "harness-2026-10-02-0100.db"
    c = sqlite3.connect(other); c.execute("CREATE TABLE tasks (id INTEGER)"); c.commit(); c.close()
    assert any("missing tables" in x for x in bk.verify(other))
    assert any("does not exist" in x for x in bk.verify(dest / "ghost.db"))


def test_verify_catches_a_file_that_is_not_a_database(dest):
    dest.mkdir()
    junk = dest / "harness-2026-10-02-0100.db"
    junk.write_text("this is not sqlite")
    assert bk.verify(junk)


# ---------------------------------------------------------------- retention
def fake(dest, stamp):
    dest.mkdir(exist_ok=True)
    p = dest / f"harness-{stamp}.db"
    p.write_text("x"); bk.manifest_path(p).write_text("{}")
    return p


def test_retention_keeps_14_days_and_the_first_of_each_month_and_always_the_newest(dest):
    now = datetime(2026, 10, 20, 12, 0)
    for d in range(0, 30):                                              # 30 days of backups, two per day
        day = now - timedelta(days=d)
        fake(dest, f"{day:%Y-%m-%d}-0800"); fake(dest, f"{day:%Y-%m-%d}-2000")
    old_month = fake(dest, "2026-03-05-0800"); fake(dest, "2026-03-20-0800"); too_old = fake(dest, "2025-06-01-0800")
    gone = bk.prune(dest, now)
    names = {p.name for p in bk.snapshots(dest)}
    assert "harness-2026-10-20-2000.db" in names and "harness-2026-10-20-0800.db" not in names          # one per recent day: the newest
    assert len([n for n in names if n.startswith("harness-2026-10-")]) >= 14 - 0
    assert old_month.name in names and "harness-2026-03-20-0800.db" not in names                        # first of March kept, the rest dropped
    assert too_old.name not in names and not bk.manifest_path(too_old).exists()                         # older than 12 months: gone, with its sidecar
    assert gone and all(not p.exists() for p in gone)


def test_prune_never_removes_the_only_backup(dest):
    only = fake(dest, "2024-01-01-0800")
    assert bk.prune(dest, datetime(2026, 10, 1)) == [] and only.exists()


# ---------------------------------------------------------------- the restore test and real restores
def test_restore_check_passes_on_a_good_backup_and_reports_newer_rows(live, dest):
    p = bk.create_backup(live, dest, NOW)
    c = db.connect(live); c.execute("INSERT INTO tasks (title) VALUES ('added after the backup')"); c.commit(); c.close()
    ok, lines = bk.restore_check(p, live)
    assert ok and any("1 newer rows" in ln for ln in lines) and any("harness opens it" in ln for ln in lines)


def test_restore_check_fails_if_the_backup_has_more_than_the_live_database(live, dest):
    c = db.connect(live); c.execute("INSERT INTO tasks (title) VALUES ('second')"); c.commit(); c.close()
    p = bk.create_backup(live, dest, NOW)
    c = db.connect(live); c.execute("DELETE FROM tasks WHERE title='second'"); c.commit(); c.close()     # data "lost" since
    ok, lines = bk.restore_check(p, live)
    assert not ok and any("MORE rows" in ln for ln in lines)


def test_restore_check_fails_on_a_damaged_backup(live, dest):
    p = bk.create_backup(live, dest, NOW)
    p.write_bytes(p.read_bytes()[:2000])
    ok, lines = bk.restore_check(p, live)
    assert not ok and lines[0].startswith("FAIL")


def test_restore_puts_the_snapshot_back_and_keeps_the_old_database(live, dest):
    p = bk.create_backup(live, dest, NOW)
    c = db.connect(live); c.execute("DELETE FROM tasks"); c.execute("DELETE FROM triage_rules"); c.commit(); c.close()      # a bad day
    kept = bk.restore(p, live, NOW, api_up=lambda: False)
    assert rows(live, "tasks") == 1 and rows(live, "triage_rules") == 2                                  # (the seeded rule plus hers)
    assert kept.name.startswith("harness.db.before-restore-") and rows(kept, "tasks") == 0                 # the damaged one is kept, not deleted
    assert stat.S_IMODE(live.stat().st_mode) == 0o600


def test_restore_refuses_while_the_harness_is_running_or_the_snapshot_is_damaged(live, dest):
    p = bk.create_backup(live, dest, NOW)
    before = live.read_bytes()
    with pytest.raises(bk.BackupError, match="make down"):
        bk.restore(p, live, NOW, api_up=lambda: True)
    assert live.read_bytes() == before
    p.write_bytes(b"garbage")
    with pytest.raises(bk.BackupError, match="not sound"):
        bk.restore(p, live, NOW, api_up=lambda: False)
    assert live.read_bytes() == before


def test_command_line(live, dest, monkeypatch, capsys):
    monkeypatch.setattr(bk, "DATA", live.parent); monkeypatch.setattr(bk, "BACKUPS", dest)
    assert bk.main(["backup.py", "backup"]) == 0 and "Backup saved" in capsys.readouterr().out
    assert bk.main(["backup.py", "daily"]) == 0 and "already exists" in capsys.readouterr().out
    assert bk.main(["backup.py", "verify"]) == 0 and capsys.readouterr().out.startswith("OK")
    assert bk.main(["backup.py", "restore-check"]) == 0 and "RESULT: PASS" in capsys.readouterr().out
    assert bk.main(["backup.py", "list"]) == 0 and "schema v" in capsys.readouterr().out
    with pytest.raises(SystemExit):
        bk.main(["backup.py", "restore", "x"])                                                            # needs --yes


# ---------------------------------------------------------------- automatic snapshot before a database upgrade
def test_an_upgrade_of_a_database_with_data_first_keeps_a_copy(tmp_path):
    path = tmp_path / "harness.db"
    c = db.connect(path)
    c.executescript("BEGIN;" + db.MIGRATIONS[0]); c.execute("PRAGMA user_version = 1"); c.commit()
    c.execute("INSERT INTO tasks (title) VALUES ('before the upgrade')"); c.commit()
    db.migrate(c)
    snaps = list((tmp_path / "backups").glob("pre-migration-v1-*.db"))
    assert len(snaps) == 1 and rows(snaps[0], "tasks") == 1
    assert sqlite3.connect(snaps[0]).execute("PRAGMA user_version").fetchone()[0] == 1               # exactly how it was before


def test_a_new_empty_database_makes_no_snapshot_and_only_five_are_kept(tmp_path):
    fresh = db.connect(tmp_path / "a" / "harness.db") if (tmp_path / "a").mkdir() is None else None
    db.migrate(fresh)
    assert not (tmp_path / "a" / "backups").exists()
    folder = tmp_path / "b" / "backups"; folder.mkdir(parents=True)
    for i in range(8):
        (folder / f"pre-migration-v1-2026010{i + 1}-000000.db").write_text("x")
    c = db.connect(tmp_path / "b" / "harness.db")
    c.executescript("BEGIN;" + db.MIGRATIONS[0]); c.execute("PRAGMA user_version = 1"); c.commit()
    db.migrate(c)
    assert len(list(folder.glob("pre-migration-v*.db"))) == 5

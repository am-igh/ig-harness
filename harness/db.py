"""SQLite connection and schema migrations.

The database file lives in the data directory (~/IG-Harness-data), never in the repo.
Migrations are append-only: to change the schema, add a new entry to MIGRATIONS.
"""
import sqlite3
from pathlib import Path

from harness.config import DATA_DIR

DB_NAME = "harness.db"

# Columns shared by every table:
#   space       'work' | 'personal'  (personal items stay separable, rule 10)
#   sensitivity 'S0'..'S3'           (rule 3; personal items are always S3)
#   source / source_ref              where a row came from; (source, source_ref) is
#                                    unique so importers can re-run without duplicates
_COMMON = """
    space TEXT NOT NULL DEFAULT 'work' CHECK (space IN ('work','personal')),
    sensitivity TEXT NOT NULL DEFAULT 'S1' CHECK (sensitivity IN ('S0','S1','S2','S3')),
    source TEXT NOT NULL DEFAULT 'manual',
    source_ref TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
"""

MIGRATIONS: list[str] = [
    # 1: initial schema
    f"""
    CREATE TABLE tasks (
        id INTEGER PRIMARY KEY,
        title TEXT NOT NULL,
        notes TEXT,
        project_code TEXT,
        due_date TEXT,                      -- ISO date, optional
        status TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open','done','dropped')),
        done_at TEXT,
        {_COMMON},
        UNIQUE (source, source_ref)
    );
    CREATE TABLE deadlines (
        id INTEGER PRIMARY KEY,
        title TEXT NOT NULL,
        due_date TEXT NOT NULL,             -- ISO date
        kind TEXT NOT NULL DEFAULT 'deadline' CHECK (kind IN ('deadline','reporting','fixed')),
        importance TEXT NOT NULL DEFAULT 'normal' CHECK (importance IN ('major','normal')),
        project_code TEXT,
        status TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open','done','dropped')),
        done_at TEXT,
        {_COMMON},
        UNIQUE (source, source_ref)
    );
    CREATE TABLE done_log (
        id INTEGER PRIMARY KEY,
        item_type TEXT NOT NULL CHECK (item_type IN ('task','deadline','waiting_on')),
        item_id INTEGER NOT NULL,
        title TEXT NOT NULL,                -- snapshot, survives later edits
        done_at TEXT NOT NULL DEFAULT (datetime('now')),
        space TEXT NOT NULL DEFAULT 'work' CHECK (space IN ('work','personal'))
    );
    CREATE TABLE waiting_on (
        id INTEGER PRIMARY KEY,
        description TEXT NOT NULL,
        person TEXT,
        since_date TEXT NOT NULL,           -- ISO date
        remind_on TEXT,                     -- ISO date (7-day reminder in Phase 3)
        thread_ref TEXT,                    -- e.g. Gmail thread id, later phases
        status TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open','done','dropped')),
        done_at TEXT,
        {_COMMON},
        UNIQUE (source, source_ref)
    );
    CREATE TABLE journal_entries (
        id INTEGER PRIMARY KEY,
        entry_date TEXT NOT NULL,           -- ISO date
        text TEXT NOT NULL,
        project_code TEXT,
        {_COMMON},
        UNIQUE (source, source_ref)
    );
    CREATE INDEX idx_tasks_status_due ON tasks (status, due_date);
    CREATE INDEX idx_deadlines_status_due ON deadlines (status, due_date);
    CREATE INDEX idx_done_log_done_at ON done_log (done_at);
    CREATE INDEX idx_journal_date ON journal_entries (entry_date);
    """,
    # 2: Google Calendar events (title and times only; read-only mirror)
    f"""
    CREATE TABLE calendar_events (
        id INTEGER PRIMARY KEY,
        title TEXT NOT NULL,
        start TEXT NOT NULL,                -- ISO date or datetime as Google returns it
        end TEXT,
        all_day INTEGER NOT NULL DEFAULT 0,
        status TEXT NOT NULL DEFAULT 'confirmed' CHECK (status IN ('confirmed','tentative','cancelled')),
        {_COMMON},
        UNIQUE (source, source_ref)
    );
    CREATE INDEX idx_calendar_start ON calendar_events (start);
    """,
]


def connect(path: Path | None = None) -> sqlite3.Connection:
    path = path or DATA_DIR / DB_NAME
    # Default rollback journal (not WAL): safer on Docker bind mounts shared with macOS.
    conn = sqlite3.connect(path, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def schema_version(conn: sqlite3.Connection) -> int:
    return conn.execute("PRAGMA user_version").fetchone()[0]


def migrate(conn: sqlite3.Connection) -> int:
    """Apply any migrations not yet applied. Returns the resulting schema version."""
    version = schema_version(conn)
    for i, sql in enumerate(MIGRATIONS[version:], start=version + 1):
        with conn:  # one transaction per migration
            conn.executescript("BEGIN;" + sql)
            conn.execute(f"PRAGMA user_version = {i}")
    return schema_version(conn)

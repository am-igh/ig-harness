"""SQLite connection and schema migrations.

The database file lives in the data directory (~/IG-Harness-data), never in the repo.
Migrations are append-only: to change the schema, add a new entry to MIGRATIONS.
"""
import sqlite3
from datetime import datetime
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
    # 3: model gateway: privacy log (never stores prompt or answer text) and approvals
    """
    CREATE TABLE privacy_log (
        id INTEGER PRIMARY KEY,
        ts TEXT NOT NULL,                   -- Geneva time
        request_id TEXT NOT NULL,
        provider TEXT NOT NULL,             -- local | infomaniak | anthropic | openrouter
        model TEXT,
        tier TEXT NOT NULL CHECK (tier IN ('S0','S1','S2','S3')),
        redacted INTEGER NOT NULL DEFAULT 0,
        in_chars INTEGER NOT NULL DEFAULT 0,
        out_chars INTEGER NOT NULL DEFAULT 0,
        cost_chf REAL NOT NULL DEFAULT 0,
        purpose TEXT NOT NULL,
        outcome TEXT NOT NULL,              -- ok | blocked | needs_approval | error
        detail TEXT                         -- short reason, never content
    );
    CREATE INDEX idx_privacy_log_ts ON privacy_log (ts);
    CREATE TABLE approvals (
        id INTEGER PRIMARY KEY,
        created_at TEXT NOT NULL,
        tier TEXT NOT NULL,
        provider TEXT NOT NULL,
        purpose TEXT NOT NULL,
        content_hash TEXT NOT NULL,         -- hash of the redacted prompt that was previewed
        preview TEXT NOT NULL,              -- the redacted text she approves (placeholders only)
        status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','approved','rejected')),
        decided_at TEXT
    );
    """,
    # 4: people (from Suivi) and recent inbox threads with triage results. All S2, local only.
    """
    CREATE TABLE people (
        id INTEGER PRIMARY KEY,
        slug TEXT NOT NULL UNIQUE,          -- the id used in Suivi (matches waiting_on.person)
        name TEXT NOT NULL,
        aliases TEXT, org TEXT, role TEXT,
        email TEXT,                         -- lower-case
        cadence TEXT,
        space TEXT NOT NULL DEFAULT 'work' CHECK (space IN ('work','personal')),
        updated_at TEXT NOT NULL DEFAULT (datetime('now'))
    );
    CREATE INDEX idx_people_email ON people (email);
    CREATE TABLE emails (
        id INTEGER PRIMARY KEY,
        thread_id TEXT NOT NULL UNIQUE,
        message_id TEXT NOT NULL,           -- newest message; a new one resets triage
        from_name TEXT, from_email TEXT NOT NULL,
        subject TEXT,
        received_at TEXT NOT NULL,          -- ISO, Geneva time
        snippet TEXT, body TEXT,            -- trimmed text, stays on this Mac (S2)
        direct INTEGER NOT NULL DEFAULT 0,  -- she is in To (not just Cc)
        cc_only INTEGER NOT NULL DEFAULT 0,
        bulk INTEGER NOT NULL DEFAULT 0,    -- newsletter / automated
        last_from_me INTEGER NOT NULL DEFAULT 0,
        in_window INTEGER NOT NULL DEFAULT 1,
        person_slug TEXT,                   -- sender matched to People
        triage_status TEXT NOT NULL DEFAULT 'pending' CHECK (triage_status IN ('pending','skipped','done','error')),
        needs_reply INTEGER,
        why TEXT,
        urgency INTEGER,
        score REAL,
        triaged_model TEXT, triaged_at TEXT,
        sensitivity TEXT NOT NULL DEFAULT 'S2',
        space TEXT NOT NULL DEFAULT 'work',
        updated_at TEXT NOT NULL DEFAULT (datetime('now'))
    );
    CREATE INDEX idx_emails_received ON emails (received_at);
    """,
    # 5: triage v2: action + deadline from the model, her feedback labels, standing rules, model scoreboard
    """
    ALTER TABLE emails ADD COLUMN action TEXT;           -- e.g. 'reply', 'fill in the survey'
    ALTER TABLE emails ADD COLUMN deadline TEXT;         -- ISO date the sender asks for, if any
    ALTER TABLE emails ADD COLUMN user_label TEXT CHECK (user_label IN ('yes','no'));   -- her verdict: does this need me?
    ALTER TABLE emails ADD COLUMN labeled_at TEXT;
    ALTER TABLE emails ADD COLUMN task_id INTEGER;       -- task created from this email (Today & overdue)
    CREATE TABLE triage_rules (
        id INTEGER PRIMARY KEY,
        text TEXT NOT NULL,
        active INTEGER NOT NULL DEFAULT 1,
        created_at TEXT NOT NULL DEFAULT (datetime('now'))
    );
    INSERT INTO triage_rules (text) VALUES
        ('Unsolicited investment, venture-fund, fundraising or sales pitches never need a reply. ICT4Peace does not do that kind of thing.');
    CREATE TABLE model_evals (
        id INTEGER PRIMARY KEY,
        started_at TEXT NOT NULL,
        finished_at TEXT,
        status TEXT NOT NULL DEFAULT 'running' CHECK (status IN ('running','done','error')),
        n_labelled INTEGER NOT NULL DEFAULT 0,
        results TEXT,                        -- JSON
        error TEXT
    );
    """,
    # 6: emails can be marked handled (with date and time); done_log may now hold emails
    """
    ALTER TABLE emails ADD COLUMN handled_at TEXT;
    CREATE TABLE done_log_new (
        id INTEGER PRIMARY KEY,
        item_type TEXT NOT NULL CHECK (item_type IN ('task','deadline','waiting_on','email')),
        item_id INTEGER NOT NULL,
        title TEXT NOT NULL,                -- snapshot, survives later edits
        done_at TEXT NOT NULL DEFAULT (datetime('now')),
        space TEXT NOT NULL DEFAULT 'work' CHECK (space IN ('work','personal'))
    );
    INSERT INTO done_log_new (id, item_type, item_id, title, done_at, space)
        SELECT id, item_type, item_id, title, done_at, space FROM done_log;
    DROP TABLE done_log;
    ALTER TABLE done_log_new RENAME TO done_log;
    CREATE INDEX idx_done_log_done_at ON done_log (done_at);
    """,
    # 7: which model each job uses (set from the model picker; falls back to IG_LOCAL_MODEL)
    """
    CREATE TABLE model_settings (
        job TEXT PRIMARY KEY,
        provider TEXT NOT NULL,
        model TEXT,
        updated_at TEXT NOT NULL DEFAULT (datetime('now'))
    );
    """,
    # 8: her edits to imported items (title, due date) are kept across re-imports; source_value = what the source says now
    """
    CREATE TABLE item_overrides (
        table_name TEXT NOT NULL CHECK (table_name IN ('tasks','deadlines','waiting_on')),
        item_id INTEGER NOT NULL,
        field TEXT NOT NULL CHECK (field IN ('title','due')),
        source_value TEXT,
        edited_at TEXT NOT NULL,
        PRIMARY KEY (table_name, item_id, field)
    );
    """,
    # 9: draft replies. A draft only reaches Gmail after her explicit approval of this exact text (status + hash).
    """
    CREATE TABLE draft_requests (
        id TEXT PRIMARY KEY,                -- uuid
        kind TEXT NOT NULL DEFAULT 'reply' CHECK (kind IN ('reply','reminder','new')),
        email_id INTEGER,                   -- the email being answered, if any
        waiting_on_id INTEGER,              -- the waiting-on item, for reminders
        thread_id TEXT,
        to_json TEXT NOT NULL DEFAULT '[]',
        cc_json TEXT NOT NULL DEFAULT '[]',
        subject TEXT NOT NULL DEFAULT '',
        in_reply_to TEXT,
        references_hdr TEXT,
        body TEXT NOT NULL DEFAULT '',
        language TEXT,
        tone TEXT,
        model TEXT,
        status TEXT NOT NULL DEFAULT 'draft' CHECK (status IN ('draft','approved','created','failed','cancelled')),
        body_hash TEXT,                     -- hash of the approved fields; the Mac-side worker re-checks it
        created_at TEXT NOT NULL,
        approved_at TEXT,
        gmail_draft_id TEXT,
        error TEXT,
        space TEXT NOT NULL DEFAULT 'work',
        sensitivity TEXT NOT NULL DEFAULT 'S2'
    );
    CREATE INDEX idx_draft_requests_email ON draft_requests (email_id);
    """,
    # 10: threading headers for replies, past correspondence per person, learned style profiles, drafting settings
    """
    ALTER TABLE emails ADD COLUMN rfc_message_id TEXT;       -- Message-ID of the newest message (for In-Reply-To)
    ALTER TABLE emails ADD COLUMN references_hdr TEXT;
    ALTER TABLE emails ADD COLUMN reply_to TEXT;
    CREATE TABLE correspondence_threads (
        id INTEGER PRIMARY KEY,
        person_email TEXT NOT NULL,
        thread_id TEXT NOT NULL,
        subject TEXT,
        last_at TEXT,
        last_from_me INTEGER NOT NULL DEFAULT 0,
        last_rfc_id TEXT,
        last_references TEXT,
        n_messages INTEGER NOT NULL DEFAULT 0,
        UNIQUE (person_email, thread_id)
    );
    CREATE TABLE correspondence_messages (
        id INTEGER PRIMARY KEY,
        person_email TEXT NOT NULL,
        thread_id TEXT NOT NULL,
        msg_id TEXT NOT NULL,
        sent_at TEXT,
        from_me INTEGER NOT NULL,
        subject TEXT,
        body TEXT,                          -- new text only (quotes stripped), trimmed; stays on this Mac (S2)
        language TEXT,
        UNIQUE (person_email, msg_id)
    );
    CREATE INDEX idx_corr_msgs_person ON correspondence_messages (person_email, from_me);
    CREATE TABLE style_profiles (
        person_email TEXT PRIMARY KEY,
        language TEXT,                      -- 'en', 'fr', 'de', 'it', 'es'
        formality TEXT CHECK (formality IN ('formal','informal','neutral')),
        pronoun TEXT,                       -- vous / tu / Sie / du
        greeting TEXT,                      -- e.g. 'Dear {name},' or 'Bonjour {name},'
        closing TEXT,                       -- e.g. 'Kind regards,'
        avg_words INTEGER,
        n_mine INTEGER NOT NULL DEFAULT 0,
        n_theirs INTEGER NOT NULL DEFAULT 0,
        n_threads INTEGER NOT NULL DEFAULT 0,
        confidence TEXT NOT NULL DEFAULT 'none' CHECK (confidence IN ('none','low','medium','high')),
        notes TEXT,
        source TEXT NOT NULL DEFAULT 'learned' CHECK (source IN ('learned','edited')),
        updated_at TEXT NOT NULL DEFAULT (datetime('now'))
    );
    CREATE TABLE draft_settings (
        key TEXT PRIMARY KEY,
        value TEXT,
        source TEXT NOT NULL DEFAULT 'learned' CHECK (source IN ('learned','edited')),
        updated_at TEXT NOT NULL DEFAULT (datetime('now'))
    );
    """,
    # 11: what the draft was asked for and what it needs from her
    """
    ALTER TABLE draft_requests ADD COLUMN instruction TEXT;       -- her note when asking for the draft
    ALTER TABLE draft_requests ADD COLUMN needs_input TEXT;       -- JSON list of things only she can fill in
    ALTER TABLE draft_requests ADD COLUMN profile_summary TEXT;   -- JSON: which style information was used
    """,
    # 12: who the newest message went to, and the messages before it (for follow-ups and for context in drafts)
    """
    ALTER TABLE emails ADD COLUMN to_addrs TEXT;            -- JSON list: addresses in To of the newest message
    ALTER TABLE emails ADD COLUMN cc_addrs TEXT;            -- JSON list
    ALTER TABLE emails ADD COLUMN history TEXT;             -- JSON list: up to 3 earlier messages, newest first
    """,
    # 13: notes: context and follow-ups she writes, attached to an item or free-standing; follow-ups become tasks
    """
    CREATE TABLE notes (
        id INTEGER PRIMARY KEY,
        created_at TEXT NOT NULL,                       -- Geneva time
        text TEXT NOT NULL,
        kind TEXT NOT NULL DEFAULT 'note' CHECK (kind IN ('note','followup')),
        parent_type TEXT CHECK (parent_type IN ('task','deadline','waiting_on','email')),
        parent_id INTEGER,
        due_date TEXT,                                  -- for follow-ups
        follow_up_task_id INTEGER,                      -- the task a follow-up created (it shows in Today & overdue)
        project_code TEXT,
        space TEXT NOT NULL DEFAULT 'work' CHECK (space IN ('work','personal')),
        sensitivity TEXT NOT NULL DEFAULT 'S2',
        deleted_at TEXT
    );
    CREATE INDEX idx_notes_parent ON notes (parent_type, parent_id);
    CREATE INDEX idx_notes_created ON notes (created_at);
    """,
    # 14: audit readiness: runs of her checker (controle_justificatifs.py) and the lines it found. S2: stays on this Mac. No IBAN is kept.
    """
    CREATE TABLE audit_runs (
        id INTEGER PRIMARY KEY,
        year TEXT NOT NULL,
        started_at TEXT NOT NULL,
        finished_at TEXT,
        status TEXT NOT NULL DEFAULT 'running' CHECK (status IN ('running','done','error')),
        input_signature TEXT,              -- fingerprint of the statements, receipts and script used
        n_statements INTEGER, n_pieces INTEGER, n_lines INTEGER,
        summary TEXT,                      -- JSON
        error TEXT
    );
    CREATE TABLE audit_lines (
        id INTEGER PRIMARY KEY,
        run_id INTEGER NOT NULL REFERENCES audit_runs (id) ON DELETE CASCADE,
        compte TEXT, periode TEXT,
        date_raw TEXT,                     -- dd.mm.yyyy as in her report
        date_iso TEXT,
        beneficiaire TEXT, devise TEXT, montant REAL,
        statut TEXT, source TEXT, groupe TEXT
    );
    CREATE INDEX idx_audit_lines_run ON audit_lines (run_id, statut);
    """,
    # 15: project codes (Suivi's Codes sheet) and the project register's initiatives and mandates (no money, no IBAN)
    """
    CREATE TABLE project_codes (
        code TEXT PRIMARY KEY,
        name TEXT,
        domain TEXT,                            -- W / P
        kind TEXT,                              -- project | thread | area
        registry_link TEXT,                     -- where Suivi says the project's register entry lives
        updated_at TEXT NOT NULL DEFAULT (datetime('now'))
    );
    CREATE TABLE register_initiatives (
        code TEXT PRIMARY KEY, name TEXT, strand TEXT, counterpart TEXT, status TEXT, next_touchpoint TEXT,
        updated_at TEXT NOT NULL DEFAULT (datetime('now'))
    );
    CREATE TABLE register_mandates (
        code TEXT PRIMARY KEY, name TEXT, funder TEXT, signature TEXT, activity_start TEXT, activity_end TEXT,
        reporting_deadline TEXT, status TEXT, close_out_state TEXT,
        updated_at TEXT NOT NULL DEFAULT (datetime('now'))
    );
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


KEEP_PRE_MIGRATION_SNAPSHOTS = 5


def _snapshot_before_migration(conn: sqlite3.Connection, version: int) -> Path | None:
    """Before changing the structure of a database that holds data, keep a copy (in a `backups` folder next to it)."""
    file = conn.execute("PRAGMA database_list").fetchone()[2]
    if not file:
        return None
    folder = Path(file).parent / "backups"
    folder.mkdir(exist_ok=True)
    dest = folder / f"pre-migration-v{version}-{datetime.now():%Y%m%d-%H%M%S}.db"
    out = sqlite3.connect(dest)
    try:
        conn.backup(out)
    finally:
        out.close()
    for old in sorted(folder.glob("pre-migration-v*.db"))[:-KEEP_PRE_MIGRATION_SNAPSHOTS]:
        old.unlink(missing_ok=True)
    return dest


def migrate(conn: sqlite3.Connection) -> int:
    """Apply any migrations not yet applied. Returns the resulting schema version."""
    version = schema_version(conn)
    if 0 < version < len(MIGRATIONS):
        _snapshot_before_migration(conn, version)
    for i, sql in enumerate(MIGRATIONS[version:], start=version + 1):
        with conn:  # one transaction per migration
            conn.executescript("BEGIN;" + sql)
            conn.execute(f"PRAGMA user_version = {i}")
    return schema_version(conn)

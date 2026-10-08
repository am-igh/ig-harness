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
    # 16: always-show-me list: a name on a thread makes the email show up, no model involved
    """
    CREATE TABLE watch_names (
        id INTEGER PRIMARY KEY,
        name TEXT NOT NULL,
        active INTEGER NOT NULL DEFAULT 1,
        created_at TEXT NOT NULL DEFAULT (datetime('now'))
    );
    """,
    # 17: bank statements offered for filing into the audit folder (preview first; filed only after her approval)
    """
    CREATE TABLE filings (
        id INTEGER PRIMARY KEY,
        original_name TEXT NOT NULL,
        sha256 TEXT NOT NULL,
        size INTEGER NOT NULL,
        state TEXT NOT NULL,                -- new / duplicate / name_taken / same_period / wrong_year / not_statement / unreadable
        detail TEXT,                        -- plain-language explanation (existing file it clashes with, etc.)
        account TEXT, period_from TEXT, period_to TEXT, period_kind TEXT, year TEXT,
        status TEXT NOT NULL DEFAULT 'staged' CHECK (status IN ('staged','approved','filed','failed','skipped')),
        result TEXT,
        created_at TEXT NOT NULL DEFAULT (datetime('now')),
        decided_at TEXT, filed_at TEXT
    );
    """,
    # 18: scanned invoices and receipts (justificatifs): read locally, previewed, filed only after her approval
    """
    CREATE TABLE scans (
        id INTEGER PRIMARY KEY,
        source TEXT NOT NULL CHECK (source IN ('folder','upload')),
        original_name TEXT NOT NULL,
        sha256 TEXT NOT NULL UNIQUE,
        size INTEGER NOT NULL,
        found_at TEXT NOT NULL DEFAULT (datetime('now')),
        status TEXT NOT NULL DEFAULT 'found' CHECK (status IN ('found','reading','proposed','duplicate','approved','filed','failed','skipped','unreadable')),
        doc_type TEXT,                -- invoice_received / receipt / invoice_issued / contract / other
        supplier TEXT, number TEXT, amount REAL, currency TEXT, doc_date TEXT, paid_date TEXT,
        paid_manual INTEGER NOT NULL DEFAULT 0,
        folder TEXT,                  -- Expenses / Income / NULL (she chooses)
        proposed_name TEXT, year TEXT,
        note TEXT,                    -- plain-language line shown under the preview
        model TEXT, result TEXT,
        decided_at TEXT, filed_at TEXT
    );
    """,
    # 19: page count and parent (a PDF split into single pages)
    "ALTER TABLE scans ADD COLUMN pages INTEGER; ALTER TABLE scans ADD COLUMN parent_id INTEGER;",
    # 20: a fingerprint of a single page's picture, so a page that comes back unchanged is recognised
    "ALTER TABLE scans ADD COLUMN page_hash TEXT;",
    # 21: read-only mirror of her hours.csv (hours need an evidence pointer and an entered_on date)
    """
    CREATE TABLE hours (
        row_key TEXT PRIMARY KEY,           -- fingerprint of the whole CSV row: the same row is never added twice
        date TEXT NOT NULL, project TEXT, budget_line TEXT,
        hours REAL, rate REAL, description TEXT, evidence TEXT, source TEXT, entered_on TEXT,
        updated_at TEXT NOT NULL DEFAULT (datetime('now'))
    );
    CREATE INDEX idx_hours_date ON hours (date);
    """,
    # 22: the journal's own type, evidence and hours (the Friday pass uses them)
    "ALTER TABLE journal_entries ADD COLUMN entry_type TEXT; ALTER TABLE journal_entries ADD COLUMN evidence TEXT; ALTER TABLE journal_entries ADD COLUMN hours REAL;",
    # 23: the Friday hours pass: suggested hour entries, approved one by one, then appended to hours.csv by the Mac-side writer
    """
    CREATE TABLE hour_proposals (
        id INTEGER PRIMARY KEY,
        pkey TEXT NOT NULL UNIQUE,            -- fingerprint of where it came from: the same journal row or event is never proposed twice
        week_start TEXT NOT NULL,
        date TEXT NOT NULL, project TEXT, budget_line TEXT, hours REAL, description TEXT, evidence TEXT,
        source TEXT NOT NULL,                 -- journal / calendar
        basis TEXT,                           -- plain-language reason for the hours figure
        status TEXT NOT NULL DEFAULT 'proposed' CHECK (status IN ('proposed','approved','written','failed','skipped')),
        result TEXT, created_at TEXT NOT NULL DEFAULT (datetime('now')), decided_at TEXT, written_at TEXT
    );
    """,
    # 24: costs.csv mirror (read-only) and the register's budget line NAMES (no amounts) for the project checks
    """
    CREATE TABLE costs (
        row_key TEXT PRIMARY KEY,
        date TEXT, project TEXT, budget_line TEXT, supplier TEXT, amount REAL, currency TEXT, amount_chf REAL,
        invoice_reference TEXT, payment_date TEXT, account TEXT, justificatif TEXT, entered_on TEXT,
        updated_at TEXT NOT NULL DEFAULT (datetime('now'))
    );
    CREATE TABLE register_budget (
        bkey TEXT PRIMARY KEY, code TEXT NOT NULL, budget_line TEXT NOT NULL, phase TEXT,
        updated_at TEXT NOT NULL DEFAULT (datetime('now'))
    );
    """,
    # 25: what the calendar says about her own response, the place and the join link
    "ALTER TABLE calendar_events ADD COLUMN my_response TEXT; ALTER TABLE calendar_events ADD COLUMN location TEXT; ALTER TABLE calendar_events ADD COLUMN link TEXT; "
    "ALTER TABLE calendar_events ADD COLUMN self_organizer INTEGER NOT NULL DEFAULT 0; ALTER TABLE calendar_events ADD COLUMN attendee_count INTEGER;",
    # 26: Geneva and beyond: events from every source, with the evidence for each, her own status override and a hide switch
    """
    CREATE TABLE events (
        id INTEGER PRIMARY KEY,
        dedupe_key TEXT NOT NULL UNIQUE,         -- cal:<calendar id> for calendar events; other sources add their own keys
        title TEXT NOT NULL,
        start TEXT NOT NULL, end TEXT, all_day INTEGER NOT NULL DEFAULT 0,
        venue TEXT, city TEXT, online INTEGER NOT NULL DEFAULT 0, url TEXT, organizer TEXT,
        topics TEXT,                             -- comma-separated topic tags
        geneva INTEGER NOT NULL DEFAULT 0,
        role TEXT,                               -- attendee / speaker / moderator / panelist / judge / mentor / facilitator
        derived_status TEXT NOT NULL DEFAULT 'none' CHECK (derived_status IN ('none','invited','interested','tentative','confirmed','declined')),
        user_status TEXT CHECK (user_status IN ('interested','confirmed','declined')),     -- her override beats the derived status
        hidden INTEGER NOT NULL DEFAULT 0,       -- "not an event" / not relevant
        forced INTEGER NOT NULL DEFAULT 0,       -- "this is an event" for a calendar item the rules skipped
        source_kind TEXT NOT NULL, tier TEXT NOT NULL DEFAULT 'S2',
        created_at TEXT NOT NULL DEFAULT (datetime('now')), updated_at TEXT NOT NULL DEFAULT (datetime('now'))
    );
    CREATE INDEX idx_events_start ON events (start);
    CREATE TABLE event_evidence (
        id INTEGER PRIMARY KEY,
        event_id INTEGER NOT NULL REFERENCES events (id) ON DELETE CASCADE,
        kind TEXT NOT NULL, ref TEXT NOT NULL, signal TEXT, detail TEXT,
        observed_at TEXT NOT NULL DEFAULT (datetime('now')),
        UNIQUE (event_id, kind, ref)
    );
    """,
    # 27: events from emails and public listings: a relevance flag (listings outside her topics are kept but hidden by default) and the
    # emails that look like invitations but could not be read by rules (the local-model step reads them next)
    """
    ALTER TABLE events ADD COLUMN relevant INTEGER NOT NULL DEFAULT 1;
    CREATE TABLE event_candidates (
        id INTEGER PRIMARY KEY,
        message_id TEXT NOT NULL UNIQUE, thread_id TEXT NOT NULL,
        received_at TEXT NOT NULL, sender TEXT, subject TEXT, snippet TEXT,
        bulk INTEGER NOT NULL DEFAULT 0, direct INTEGER NOT NULL DEFAULT 0,
        status TEXT NOT NULL DEFAULT 'new' CHECK (status IN ('new','event','not_event')),
        event_id INTEGER REFERENCES events (id) ON DELETE SET NULL,
        created_at TEXT NOT NULL DEFAULT (datetime('now'))
    );
    """,
    # 28: reading candidate invitations with the local model: the email text, when and by which model it was read, retries, the reply-by date of an invitation,
    # and senders she told us to ignore
    """
    ALTER TABLE event_candidates ADD COLUMN body TEXT;
    ALTER TABLE event_candidates ADD COLUMN read_at TEXT;
    ALTER TABLE event_candidates ADD COLUMN model TEXT;
    ALTER TABLE event_candidates ADD COLUMN note TEXT;
    ALTER TABLE event_candidates ADD COLUMN attempts INTEGER NOT NULL DEFAULT 0;
    ALTER TABLE events ADD COLUMN rsvp_by TEXT;
    CREATE TABLE event_sender_rules (
        sender TEXT PRIMARY KEY,               -- an address or a whole domain
        rule TEXT NOT NULL DEFAULT 'ignore' CHECK (rule IN ('ignore')),
        created_at TEXT NOT NULL DEFAULT (datetime('now'))
    );
    """,
    # 29: to-dos she dictates on her phone (Reminders list "Harness"): a short list to confirm, then they become tasks
    """
    CREATE TABLE phone_todos (
        reminder_id TEXT PRIMARY KEY,
        text TEXT NOT NULL, notes TEXT, due_date TEXT, created_at TEXT,
        space TEXT NOT NULL DEFAULT 'work', project_code TEXT,
        status TEXT NOT NULL DEFAULT 'new' CHECK (status IN ('new','accepted','dismissed')),
        task_id INTEGER, note_id INTEGER, gone INTEGER NOT NULL DEFAULT 0,
        first_seen TEXT NOT NULL DEFAULT (datetime('now')), decided_at TEXT
    );
    CREATE TABLE phone_state (k TEXT PRIMARY KEY, v TEXT);
    """,
    # 30: the morning brief the harness writes each day (kept so it can be shown, compared with her Claude brief and saved as a Gmail draft)
    """
    CREATE TABLE briefs (
        day TEXT PRIMARY KEY,                    -- the Geneva date the brief is for
        created_at TEXT NOT NULL,
        data TEXT NOT NULL,                      -- the structured brief (JSON)
        text TEXT NOT NULL,                      -- the plain-text version (what the Gmail draft contains)
        attention_source TEXT NOT NULL DEFAULT 'rules',     -- rules / model
        model TEXT,
        draft_status TEXT NOT NULL DEFAULT 'none' CHECK (draft_status IN ('none','queued','saved','failed')),
        draft_note TEXT
    );
    """,
    # 31: which draft request carries the day's brief to Gmail
    """
    ALTER TABLE briefs ADD COLUMN draft_id TEXT;
    """,
    # 32: web research (chat "Research" mode). A log of every search query that left the Mac, and the approval the Mac-side helper re-checks. Answers are not stored.
    """
    CREATE TABLE research_requests (
        id TEXT PRIMARY KEY,
        query TEXT NOT NULL,
        query_hash TEXT NOT NULL,
        created_at TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'approved' CHECK (status IN ('approved','done','failed')),
        confirmed INTEGER NOT NULL DEFAULT 0,        -- she confirmed a screening warning
        warnings TEXT,                               -- JSON list of what the screen noticed
        n_results INTEGER, n_pages INTEGER,
        model TEXT, error TEXT
    );
    """,
    # 33: the research library: answers she chose to keep (summary, question, source links; never page text). Included in the daily backups.
    """
    CREATE TABLE research_saved (
        id INTEGER PRIMARY KEY,
        job_id TEXT UNIQUE,                          -- the research request it came from (a double click cannot save twice)
        saved_at TEXT NOT NULL,
        query TEXT NOT NULL,
        answer TEXT NOT NULL,
        sources TEXT NOT NULL DEFAULT '[]',          -- JSON: [{n, title, url, fetched_at}]
        model TEXT,
        project_code TEXT,
        sensitivity TEXT NOT NULL DEFAULT 'S1'
    );
    CREATE INDEX idx_research_saved_at ON research_saved (saved_at);
    """,
    # 34: project and contract management (funders, contracts, obligations and their deadlines, transfers with the bank's exchange rate). Contracts stay in her folders: only a path and a hash are kept.
    """
    CREATE TABLE pm_funders (
        id INTEGER PRIMARY KEY,
        name TEXT NOT NULL UNIQUE,
        short TEXT NOT NULL,
        role TEXT NOT NULL DEFAULT 'funder' CHECK (role IN ('funder','partner')),
        currency TEXT NOT NULL DEFAULT 'CHF',
        contact TEXT,
        notes TEXT
    );
    CREATE TABLE pm_projects (
        id INTEGER PRIMARY KEY,
        code TEXT NOT NULL UNIQUE,
        name TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('planned','active','closing','closed')),
        start_date TEXT, end_date TEXT,
        lead TEXT, summary TEXT,
        demo INTEGER NOT NULL DEFAULT 0,
        created_at TEXT NOT NULL DEFAULT (datetime('now'))
    );
    CREATE TABLE pm_contracts (
        id INTEGER PRIMARY KEY,
        project_id INTEGER NOT NULL REFERENCES pm_projects (id),
        funder_id INTEGER NOT NULL REFERENCES pm_funders (id),
        parent_id INTEGER REFERENCES pm_contracts (id),            -- an amendment points at its contract
        kind TEXT NOT NULL DEFAULT 'grant' CHECK (kind IN ('grant','amendment','subgrant')),   -- grant: money in; subgrant: money passed to a partner
        title TEXT NOT NULL,
        signed_date TEXT, start_date TEXT, end_date TEXT,
        amount REAL, currency TEXT NOT NULL DEFAULT 'CHF',
        budget_rate REAL NOT NULL DEFAULT 1.0,                     -- CHF per 1 unit of the contract currency assumed in the budget
        file_path TEXT, file_hash TEXT,
        status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('draft','active','amended','closed')),
        summary TEXT
    );
    CREATE TABLE pm_obligations (
        id INTEGER PRIMARY KEY,
        contract_id INTEGER NOT NULL REFERENCES pm_contracts (id),
        canon TEXT NOT NULL,                                       -- the common requirement type (see harness/pm.py CANON)
        title TEXT NOT NULL,
        clause TEXT,
        anchor TEXT NOT NULL DEFAULT 'period_end' CHECK (anchor IN ('period_end','start','end','fixed','none')),
        offset_days INTEGER NOT NULL DEFAULT 0,
        recurrence TEXT NOT NULL DEFAULT 'once' CHECK (recurrence IN ('none','once','quarterly','semiannual','annual')),
        fixed_date TEXT,
        format TEXT, language TEXT, detail TEXT, note TEXT,
        confirmed INTEGER NOT NULL DEFAULT 1,                      -- 0: a proposed mapping she has not confirmed
        source TEXT NOT NULL DEFAULT 'manual'                      -- manual / model
    );
    CREATE TABLE pm_deadlines (
        id INTEGER PRIMARY KEY,
        obligation_id INTEGER NOT NULL REFERENCES pm_obligations (id),
        period_label TEXT NOT NULL,
        due_date TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'todo' CHECK (status IN ('todo','drafting','submitted','accepted')),
        submitted_on TEXT, note TEXT,
        UNIQUE (obligation_id, period_label)
    );
    CREATE TABLE pm_transfers (
        id INTEGER PRIMARY KEY,
        contract_id INTEGER NOT NULL REFERENCES pm_contracts (id),
        label TEXT NOT NULL,
        expected_date TEXT, expected_amount REAL,
        received_date TEXT, received_amount REAL,
        chf_received REAL,                                         -- what the bank credited, in CHF
        bank_rate REAL,                                            -- CHF per 1 unit of the contract currency, as assigned by the bank on arrival
        bank_ref TEXT, note TEXT
    );
    CREATE INDEX idx_pm_deadlines_due ON pm_deadlines (due_date);
    """,
    # 35: a short summary of an email, written by the local model when she opens it and kept until a new message arrives in the thread
    """
    ALTER TABLE emails ADD COLUMN summary TEXT;
    ALTER TABLE emails ADD COLUMN summary_for TEXT;       -- the message id the summary was written for
    ALTER TABLE emails ADD COLUMN summary_model TEXT;
    """,
    # 36: the report workspace: documents behind a reporting deadline (funder forms by reference, templates made from the requirements, working drafts with versions, submitted copies)
    """
    ALTER TABLE pm_deadlines ADD COLUMN period_start TEXT;
    ALTER TABLE pm_deadlines ADD COLUMN period_end TEXT;
    CREATE TABLE pm_documents (
        id INTEGER PRIMARY KEY,
        deadline_id INTEGER NOT NULL REFERENCES pm_deadlines (id),
        kind TEXT NOT NULL CHECK (kind IN ('funder_form','template','draft','submitted','other')),
        title TEXT NOT NULL,
        version INTEGER NOT NULL DEFAULT 1,                 -- a new save is a new version: nothing is overwritten
        content TEXT,                                       -- text of templates and drafts (Markdown); forms and submitted copies stay in her folders and are only referenced
        file_path TEXT, note TEXT,
        author TEXT NOT NULL DEFAULT 'you' CHECK (author IN ('rules','you','model')),
        created_at TEXT NOT NULL
    );
    CREATE INDEX idx_pm_documents_deadline ON pm_documents (deadline_id, kind, title, version);
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

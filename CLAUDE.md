# IG Harness — project brief for Claude

Read this file fully before doing anything in this repository. It is the standing brief; the build plan and setup record (in Anne-Marie's documents folder, see "Reference documents") hold the detail.

## What this is

The IG Harness is the **ICT4Peace Foundation's "control center"**: a local web app that replaces Anne-Marie Buzatu's current scripts, `Suivi.xlsx` and the morning brief. It shows what is pressing (deadlines, today's tasks, emails needing a reply), drafts replies, tracks projects, hours and finance for the annual audit, and lists International Geneva events.

- **v1 is for one person:** Anne-Marie (Executive Director, ICT4Peace), on her MacBook Pro (Apple Silicon, 48 GB), opened in the browser.
- A later version may be packaged for other International Geneva organisations (possibly under the FAGI consortium grant). Keep components clean and replaceable with that in mind, but **do not build multi-user features in v1**.
- Anne-Marie is the product owner, not a developer. She reviews and tests at the end of each phase. Explain changes in plain language; give her exact commands to run when something must be done on her side.

## Non-negotiable rules

These apply to every change. If a task seems to require breaking one, stop and ask.

1. **Never send email.** The harness creates Gmail drafts only. There is no send function anywhere in the code. The outbound network rules block Gmail's `messages.send` and `drafts.send` endpoints, and an automated test (`tests/test_no_send.py`, to be written in Phase 3) must prove a send attempt fails. Never remove or weaken any of these three layers. Because Google's only permission that creates drafts (`gmail.compose`) also technically allows sending, these layers matter in practice. Decided 1 Oct 2026 with Anne-Marie: the Mac-side draft helper (which runs outside Docker, so container network rules cannot protect it) enforces layer 2 as a strict **allow-list** of Gmail operations in code (never a deny-list), holds its own Keychain token separate from the read-only one, and `tests/test_no_send.py` proves it. Drafts are created only after Anne-Marie's explicit approval of that specific draft.
2. **One exit door for AI.** Every model call (local or external) goes through the model gateway (`harness/gateway/`). No other module may call an AI provider directly.
3. **Sensitivity tiers decide where data may go:**

   | Tier | Examples | Allowed models |
   |---|---|---|
   | S0 Public | published reports, event listings, newsletters, public web | any |
   | S1 Internal | concept notes, project plans, task titles, non-personal admin | local, Infomaniak, Claude API |
   | S2 Confidential | bank statements, invoices, contracts, funder negotiations, partner email, personal tax | **local only for now**. External only after redaction AND explicit one-click approval, and only once data-processing agreements are confirmed (switch currently OFF) |
   | S3 Restricted | payroll/HR, AVS and IBAN numbers, health or other sensitive personal data, sensitive diplomatic exchanges, credentials, **all personal items** | local only, never leaves the Mac |

   When unsure, use the higher tier. Tier is assigned by source rules first, then pattern detectors (IBAN, AVS, salary…), then Anne-Marie's override in the UI.
4. **Redact before anything leaves.** For permitted external calls, names, emails, IBANs, amounts and other identifiers are replaced with placeholders; the mapping stays local.
5. **Log every external call** in the privacy log (time, provider, tier, redacted yes/no, size, cost).
6. **Budget cap:** external AI spend is capped at **CHF 40/month** in total. Warn at CHF 30, block external calls at CHF 40. Local models are unaffected.
7. **No secrets in the repo, ever.** API keys and tokens are read from the macOS Keychain:
   - `ig-harness-anthropic` (account `api`)
   - `ig-harness-infomaniak` (account `ai-tools`)
   - Google OAuth tokens: Keychain too, never files in the repo.
   Do not print secrets in logs or output. Do not ask Anne-Marie to paste them anywhere.
8. **No real data in the repo.** Real data lives in `~/IG-Harness-data` (database, privacy log) and in her existing folders. Tests use synthetic fixtures under `tests/fixtures/` only.
9. **Never overwrite or delete her files.** Filing creates new files or new versions; anything ambiguous is asked, not guessed. Her existing systems (below) are read-only for the harness until a phase explicitly says otherwise.
10. **Personal items** (personal tax, personal Gmail `ambuzatu@gmail.com`) are in v1 for Anne-Marie only: always S3, kept in a separate "personal" space so they can be excluded from any shared version.
11. **Claude app (MCP) bridge** — when built in Phase 7 — exposes S0–S1 tools only; S2 sharing through MCP stays disabled (she is on an individual Claude plan).

## Architecture

| Component | Purpose | Tech |
|---|---|---|
| UI (Control Center) | Four tabs: Today, Inbox, Projects & finance, Geneva | React + TypeScript (Vite), ported from `docs/design/mockup-v0.3/` |
| Harness API | Core logic; wraps her existing Python scripts | Python 3.12, FastAPI |
| Database | Tasks, journal, deadlines, hours, events, privacy log | SQLite in `~/IG-Harness-data` |
| Worker / scheduler | Morning prep, email sweep, scan-inbox watcher, Friday hours pass, 5th-of-month check | Python worker container |
| Connectors | Gmail (read-only triage now; drafts in Phase 3), Calendar, Drive, scan folder, bank statements, Geneva feeds | Mac-side helper `tools/google_helper.py` for Google (tokens in Keychain; it writes files into `~/IG-Harness-data` that importers read); file watchers, RSS |
| Model gateway | Tiers, redaction, routing, approvals, privacy log, budget cap | part of the API (`harness/gateway/`) |
| Local model | Default AI for everything | **Ollama run natively on macOS** (not in Docker — containers cannot use the Apple GPU), reached from containers at `host.docker.internal:11434` |

Everything except Ollama and the Google helper runs with `docker compose`. Containers get no general internet access. The API (gateway) reaches only the native Ollama, through a one-destination forwarder (`ollama.internal`, `docker/ollama-bridge.conf`); Google data never needs a container route, because the helper runs on the Mac, holds the tokens in the Keychain, and exchanges plain files with the harness. `make check-network` proves the isolation.

**Environment (as of 1 Oct 2026):** the Ollama port issue is resolved: her own Ollama (0.34.4) answers on 11434. Her Mac is an **M1 with 32 GB RAM** (not 48 GB). Models installed: `qwen3.8:27b-mlx` (in use, set via `IG_LOCAL_MODEL` in her git-ignored `.env`), `qwen3.5:9b`, `qwen3:8b`, `gemma3`, `llama3.2-vision:11b`, and `apertus1.5-8b-text:f16`, **our own unofficial text-only conversion** of the official Apertus 1.5 weights (see `docs/MODELS.md`; a transfer folder for her other MacBook was prepared). The model for each job is chosen in the UI's model picker (header); online providers are listed but locked until Phase 6, and the gateway still decides what data may use which model. Model comparison: the Inbox tab's scoreboard scores models against her own "this needs me / doesn't" labels.

## External model providers

- **Infomaniak AI Tools** (Swiss-hosted, OpenAI-compatible): base URL `https://api.infomaniak.com/2/ai/{PRODUCT_ID}/openai/v1`. The product ID is fetched with the token from `https://api.infomaniak.com/1/ai` during setup.
- **Anthropic Claude API** (Messages API, official Python SDK).
- OpenRouter: S0 only, for experiments. Proton Lumo: not yet (no public API as of mid-2026).

## Her existing systems (read-only sources)

Paths are on her Mac, under `~/Tresors/A-Ms_Tresor/Career/ICT4Peace/`:

- **Finance / audit:** `Admin/ICT4Peace Audit/` — `Outils/controle_justificatifs.py` (reconciliation checker), `<year>/` folders with quarterly UBS Relevés, receipts, contracts. Naming rule: `Fournisseur_Facture_<n>_CHF<montant>_paye_JJ.MM.AAAA.pdf`; one document justifies one payment.
- **Projects:** `Admin/ICT4Peace Projets/` — `Registre_Projets.xlsx` (Mandates / Instalments / Budget / Initiatives), `hours.csv`, `costs.csv`, `Outils/controle_projets.py`. Hours need an evidence pointer and an `entered_on` date.
- **Suivi:** `Suivi.xlsx` (Journal / Commitments / People / Codes) in the ICT4Peace Google Drive, synced locally via Google Drive for Desktop.
- **Google Workspace:** `anne-mariebuzatu@ict4peace.org` (Gmail, Calendar, Drive).

Wrap and call these; do not rewrite their logic. Ask Anne-Marie to connect a folder before reading from it.

**One exception to read-only, decided by Anne-Marie on 2 Oct 2026:** her harness *work* notes are appended to the Journal sheet of `Suivi.xlsx` by `tools/suivi_writer.py` (Mac-side only; the container still sees the Suivi folder read-only; personal notes are never sent; backup before each write; nothing is written while the file is open or changing; only the next empty journal rows change; verified before and after; revert on failure; pause with `make suivi-export-pause`). The project register, the audit folders and everything else stay read-only, **except for Phase 4 filing** (decided 2 Oct 2026): scan-inbox and bank-statement filing may add **new files only** to her audit/finance folders, **never overwrite or delete**, and each file is filed only after she approves a preview of its new name and destination. Anything ambiguous is asked.

## Design reference

- `docs/design/mockup-v0.3/` — the approved mockup (four `.dc.html` files: Main = Today, Inbox, Projects, Geneva). They use a small proprietary template syntax (`{{…}}`, `<sc-for>`, `<sc-if>`); treat them as the visual and behavioural spec, not as code to run.
- Key design decisions: lake band with the Jet d'eau at "today" and deadlines along the water; **the jet rises with each item done this week** (she likes this — keep it); detail opens in side panels/pop-ups; four widgets on Today (Audit readiness, Hours this week, Budget burn, Scan inbox), more selectable from a gallery.
- Palette from the ICT4Peace logo (`docs/design/assets/ict4peace_logo.png`): navy `#1F3864`, deep navy `#172B4D`, purple `#7D147D` (major), periwinkle `#6A7BC1` (Geneva / fixed dates), orange `#E8A300` (warnings), lime `#BAD403` (done, fills only), grey `#86858A`. Fonts: Source Serif 4 (headings), Public Sans (body), IBM Plex Mono (codes).

## Decisions since the first brief (1 Oct 2026)

- **Personal items** (Suivi domain P) are masked by the server: the board, lake and Done record show "Personal task" with the date; the title, project code and person are sent only when she clicks (`/api/items/{type}/{id}/reveal`). Searches never match personal titles. The mechanism is ready for personal emails.
- **Drafting.** A draft is written by a local model only (job `email_draft`, S2). Nothing reaches Gmail until she clicks "Save to Gmail" on that exact text; the Mac-side worker (`tools/draft_worker.py`, a LaunchAgent installed with `make agent-install`) re-checks her approval and the text's hash, and can only create a draft. Recipients always come from the email's headers, never from model output. When she wrote last in a conversation, the draft is a **follow-up** to the people her message went to; a draft addressed only to her own address is refused.
- **Style per person** is learned by plain rules from her past correspondence (`make correspondence`), shown on the Inbox tab and correctable; her corrections are never overwritten. New people default to a professional tone, overridable per draft.
- **Her edits to imported items** (title, due date) are kept across re-imports (`item_overrides`); Suivi.xlsx itself is never changed.
- **Ticking and the Done record:** ticked items move to "Done today" and the searchable Done record (with date and time); emails can be marked handled and reopen if the other person writes again.
- **Keeping current:** a Mac-side refresh agent (`tools/refresh_worker.py`, LaunchAgent via `make refresh-install`) refreshes calendar and Gmail (read-only), imports, triages and backs up every 30 minutes between 06:30 and 21:00 or on the header's ↻ button; status in `~/IG-Harness-data/refresh_status.json`. It holds only read-only Google permissions and has no draft capability (the draft agent is separate).
- **Backups:** daily verified snapshots of `harness.db` in `~/IG-Harness-Backups` (14 daily, 12 monthly) and an automatic copy before every database upgrade; they never leave the Mac (the database holds S2/S3 data). `make backup-test` is the restore test.
- **Notes** (`notes` table, `harness/notes.py`): context or follow-ups attached to a task, deadline, waiting-on item or email, or free-standing; a follow-up creates a task (source `note`) in Today & overdue. Recorded in the database (so in backups), listed in an All-notes log, masked when personal, and given to the drafting model as context (never personal notes).
- **Filed documents go to Suivi's journal too** (decided 2 Oct 2026): once a scanned document is really in the audit folder, `tools/suivi_writer.py` appends a `document` row (code FIN, evidence = its path under `Admin/ICT4Peace Audit/`), by the same safeguarded mechanism and pause switch as notes; each document once (state key `docs`).
- **Notes go to Suivi's journal too** (work notes only), as `capture` rows following her Suivi specification: `confirmed` because she wrote them, evidence on every row, ids continuing from the highest `J-YYYY-NNN`.
- **Calendar widget:** a Day/Week/Month view of the Google Calendar with deadline and task layers (`/api/calendar`); read-only, Geneva time; the helper reads 35 days back and 120 ahead.
- **Audit readiness (Phase 4, first slice):** `controle_justificatifs.py` runs unchanged inside the API container (`harness/audit.py`; poppler in the image; only the year folder and `Outils` mounted read-only); its `ecrire_xlsx` is replaced so its report is captured into `audit_runs`/`audit_lines` instead of being written; no IBAN stored; equivalence with her script was proved line by line on 2 Oct 2026.
- **Bank statement filing (Phase 4):** quarterly UBS statements are uploaded in the UI, previewed (new / duplicate / name taken / same period / wrong year), and added to the connected year folder as new files, under UBS's own name, only after her click. The API cannot write there (read-only mount); `tools/filer.py` (run by the refresh agent) alone creates the file, with O_EXCL, after re-checking her approval and the hash, and verifies it. Shared rules in `harness/filingspec.py`; `tests/test_filing.py` includes a source check that the filer has no delete/rename/overwrite calls.
- **Scan inbox (Phase 4):** Image Capture saves PDFs into `~/Scan-Inbox` (mounted read-only; never changed or deleted). The API container reads each scan (poppler/tesseract OCR) and a local model via the gateway (job `doc_read`, source `invoice`, S2) proposes type, supplier, number, amount, date; nothing read is stored except those fields. Name by her convention (`harness/filingspec.doc_name`), folder by simple rule (Expenses / Income; contracts and unclear wait for her), payment date matched against the latest audit check's unjustified payments, duplicates by content, name clashes become `_vN`. Filed only after her approval of that file's preview, by `tools/filer.py` (kind `document`: only `<year>/Expenses` or `<year>/Income`, new files only, O_EXCL, hash and approval re-checked). No auto-filing and no undo/delete (decided 2 Oct 2026).
- **Hours this week (Phase 4):** `hours.csv` is mirrored read-only into the `hours` table (`harness/importers/hours.py`); `harness/hours.py` builds the week view and flags entries lacking evidence or `entered_on`, with an unknown project code, or entered more than 7 days late. **Second exception to read-only, decided by Anne-Marie on 2 Oct 2026:** the Friday hours pass (`harness/hours_pass.py`) suggests entries from the Suivi journal and tagged calendar events, she approves each one, and `tools/hours_writer.py` (Mac-side, run by the refresh agent) APPENDS them to `hours.csv`: never edits an existing line, backup before each write (`~/IG-Harness-data/hours/backups`), waits while the file is in use, re-checks approval/evidence, verifies and reverts on failure, pause with `make hours-pause`. The container still sees the projects folder read-only.
- **Project checks (Phase 4):** `harness/projects_check.py` is the harness's own `controle_projets` (no script exists in her folder): read-only checks over the mirrored `hours`, `costs` (`costs.csv`, IBAN reduced to 4 characters) and register tables (mandates, budget line names only, never amounts). `GET /api/projects-check`.
- **Geneva and beyond (Phase 5, slice 5.1):** `events` and `event_evidence` tables (`harness/events.py`): event-like calendar entries (rules, no AI) with her own RSVP, status derived from the strongest evidence and overridable by her, topics (incl. harmful information and tech for good), Geneva flag, role, clash detection; the Google helper now also keeps location, join link, her response and an attendee COUNT (never addresses) and reads a year back. Plan and decisions: `docs/PHASE5_PLAN.md`.
- **Scenes (the bands):** `ui/src/scenes/Scene.tsx` is the shared band that echoes the Today lake (deep navy, layered water, time axis, clickable marks) with three landscapes: horizon (Geneva and beyond: Alps, contrail, jet; confirmed events glow purple, hollow ring = outside Geneva), Rhône (Projects & finance, one stream per project, fed by `GET /api/projects-timeline`), harbour (Inbox: the Jet d'eau and boats at anchor). Palette and fonts as above; motion respects `prefers-reduced-motion`.
- **Safety checks to keep green:** `make test` (red-team, one-door, no-send, fail-safe, masking), `make check-network`.

## Build phases

| Phase | Content | Done when |
|---|---|---|
| 0 | Accounts, keys, repo, environment | ✅ done 1 Oct 2026 |
| 1 ✅ built 1 Oct 2026 (she is checking it in daily use) | Docker skeleton (UI, API, worker), SQLite, port Today tab, read-only import from Suivi.xlsx, project register, Google Calendar. No AI. | Each morning Today matches Suivi and her calendar |
| 2 ✅ closed 1 Oct 2026 | Model gateway (tiers, redaction, approvals, privacy log, cap) + native Ollama; email triage (Gmail read-only), standing rules, feedback labels, model picker and scoreboard | Red-team samples cannot leave the Mac (tests + `make check-network`; privacy log: 0 external calls) |
| 3 ✅ done 1 Oct 2026 | Draft replies: **only on her click, reviewed before saving**; language and register learned per addressee from past correspondence (professional default for new people, overridable per draft); follow-ups when she wrote last; no-send guarantee + test; Waiting on reminders | Send attempt fails (proved by `tests/test_no_send.py`); drafts appear in Gmail (confirmed by her on 1 Oct 2026) |
| **4 (next after the refresh and backup work)** | Projects & finance: wrap the two checkers, scan inbox (rename, dedupe, never overwrite), bank upload, widgets, Friday hours pass | Q3 2026 rerun matches today's scripts |
| 5 | Geneva tab (calendar, invitations, newsletters via Gmail label, clashes), chat bar, local dictation | A week of newsletters gives a sensible view |
| 6 | Infomaniak + Claude API behind the gateway; S2 approval flow; cost display | S2 asks approval; S3 refused |
| 7 | MCP bridge to the Claude app (curated read-mostly tools) | Calls visible in privacy log |
| 8 | Four-week parallel run, backup/restore test, retire Suivi.xlsx and morning brief; review 5 Nov 2026 | She stops opening the old tools |

## Phase 1 — task list (done)

1. Repository skeleton: `harness/` (FastAPI app), `ui/` (Vite + React + TS), `worker/`, `tests/`, `docker-compose.yml`, `Makefile` with `make up`, `make down`, `make test`.
2. Data directory mounted from `~/IG-Harness-data`; SQLite schema for tasks, deadlines (with D-14 / D-3 warnings), done log, waiting-on, journal entries.
3. Read-only importers: `Suivi.xlsx` (Commitments, Journal), `Registre_Projets.xlsx` (deadlines, reporting dates), Google Calendar (events, read-only scope). Each import is idempotent and reports what changed.
4. Port the Today tab from the mockup with real data: header and tabs, lake band with Jet d'eau and deadline marks, Today & overdue with tick-off (persisted), done counter driving the jet height, deadline detail panel. Emails, widgets and chat bar may show "coming in Phase X" placeholders.
5. Other tabs as navigable placeholders.
6. Tests with synthetic fixtures; `make test` green.
7. Short `docs/RUNNING.md`: how Anne-Marie starts, stops and updates the harness.

## Working conventions

- Small, reviewable commits with clear messages; one topic per commit. Push only when Anne-Marie has agreed to the change set.
- English for code, comments and UI. Drafted emails follow the sender's language and tone; French professional correspondence uses the formal "vous".
- When something needs her action (a permission, a Terminal command, a setting), say exactly what, where and why, step by step.
- Update the setup record's change log (in her documents folder) when setup changes, and propose updates to this file when decisions change.

## Reference documents (in her documents folder, not in the repo)

`~/Tresors/A-Ms_Tresor/Career/ICT4Peace/Projects/IG_Harness/`:
- `IG_Harness_Concept_Note_v1.docx`
- `IG_Harness_Build_Plan_v1.1.docx` — architecture, data protection, model options, phases, decisions of 1 Oct 2026
- `IG_Harness_Setup_Record.docx` — accounts, Keychain item names, environment, two-GitHub-accounts procedure

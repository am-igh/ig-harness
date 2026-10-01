# IG Harness — project brief for Claude

Read this file fully before doing anything in this repository. It is the standing brief; the build plan and setup record (in Anne-Marie's documents folder, see "Reference documents") hold the detail.

## What this is

The IG Harness is the **ICT4Peace Foundation's "control center"**: a local web app that replaces Anne-Marie Buzatu's current scripts, `Suivi.xlsx` and the morning brief. It shows what is pressing (deadlines, today's tasks, emails needing a reply), drafts replies, tracks projects, hours and finance for the annual audit, and lists International Geneva events.

- **v1 is for one person:** Anne-Marie (Executive Director, ICT4Peace), on her MacBook Pro (Apple Silicon, 48 GB), opened in the browser.
- A later version may be packaged for other International Geneva organisations (possibly under the FAGI consortium grant). Keep components clean and replaceable with that in mind, but **do not build multi-user features in v1**.
- Anne-Marie is the product owner, not a developer. She reviews and tests at the end of each phase. Explain changes in plain language; give her exact commands to run when something must be done on her side.

## Non-negotiable rules

These apply to every change. If a task seems to require breaking one, stop and ask.

1. **Never send email.** The harness creates Gmail drafts only. There is no send function anywhere in the code. The outbound network rules block Gmail's `messages.send` and `drafts.send` endpoints, and an automated test (`tests/test_no_send.py`, to be written in Phase 3) must prove a send attempt fails. Never remove or weaken any of these three layers.
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
| Connectors | Gmail (read + drafts), Calendar, Drive, scan folder, bank statements, Geneva feeds | Google APIs, file watchers, RSS |
| Model gateway | Tiers, redaction, routing, approvals, privacy log, budget cap | part of the API (`harness/gateway/`) |
| Local model | Default AI for everything | **Ollama run natively on macOS** (not in Docker — containers cannot use the Apple GPU), reached from containers at `host.docker.internal:11434` |

Everything except Ollama runs with `docker compose`. Containers get no general internet access; only the gateway and the Google connectors have allow-listed outbound routes.

**Known environment issue:** as of 1 Oct 2026, port 11434 is held by an older Ollama (0.20.7) bundled inside AnythingLLM, not by her own Ollama (0.34.4). Before Phase 2, AnythingLLM is to be switched to use her Ollama and the native Ollama app started. Until then, do not rely on whatever answers on 11434.

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

## Design reference

- `docs/design/mockup-v0.3/` — the approved mockup (four `.dc.html` files: Main = Today, Inbox, Projects, Geneva). They use a small proprietary template syntax (`{{…}}`, `<sc-for>`, `<sc-if>`); treat them as the visual and behavioural spec, not as code to run.
- Key design decisions: lake band with the Jet d'eau at "today" and deadlines along the water; **the jet rises with each item done this week** (she likes this — keep it); detail opens in side panels/pop-ups; four widgets on Today (Audit readiness, Hours this week, Budget burn, Scan inbox), more selectable from a gallery.
- Palette from the ICT4Peace logo (`docs/design/assets/ict4peace_logo.png`): navy `#1F3864`, deep navy `#172B4D`, purple `#7D147D` (major), periwinkle `#6A7BC1` (Geneva / fixed dates), orange `#E8A300` (warnings), lime `#BAD403` (done, fills only), grey `#86858A`. Fonts: Source Serif 4 (headings), Public Sans (body), IBM Plex Mono (codes).

## Build phases

| Phase | Content | Done when |
|---|---|---|
| 0 | Accounts, keys, repo, environment | ✅ largely done 1 Oct 2026 |
| **1 (next)** | Docker skeleton (UI, API, worker), SQLite, port Today tab, read-only import from Suivi.xlsx, project register, Google Calendar. No AI. | Each morning Today matches Suivi and her calendar |
| 2 | Model gateway (tiers, redaction, approvals, privacy log, cap) + native Ollama; email triage (Gmail read-only) | Red-team samples cannot leave the Mac |
| 3 | Draft replies (sender's language and register), no-send guarantee + test, Waiting on and 7-day reminder drafts | Send attempt fails; drafts appear in Gmail |
| 4 | Projects & finance: wrap the two checkers, scan inbox (rename, dedupe, never overwrite), bank upload, widgets, Friday hours pass | Q3 2026 rerun matches today's scripts |
| 5 | Geneva tab (calendar, invitations, newsletters via Gmail label, clashes), chat bar, local dictation | A week of newsletters gives a sensible view |
| 6 | Infomaniak + Claude API behind the gateway; S2 approval flow; cost display | S2 asks approval; S3 refused |
| 7 | MCP bridge to the Claude app (curated read-mostly tools) | Calls visible in privacy log |
| 8 | Four-week parallel run, backup/restore test, retire Suivi.xlsx and morning brief; review 5 Nov 2026 | She stops opening the old tools |

## Phase 1 — task list

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

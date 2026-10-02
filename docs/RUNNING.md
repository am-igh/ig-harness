# Running the IG Harness

The harness runs on your Mac in Docker and opens in your browser. Nothing leaves your Mac in Phase 1: there is no AI yet, and your spreadsheets are only read, never changed.

## Every day

| I want to… | Do this |
|---|---|
| **Start it** | Open **Docker Desktop** (wait until it says "running"), then in Terminal: `cd ~/Developer/ig-harness && make up` |
| **Open it** | Go to <http://localhost:5173> in your browser |
| **Refresh now** | Press **↻ Updated hh:mm** in the header, or `make refresh-now` (shows each step). Normally you do nothing: the refresh agent does it every 30 minutes, 06:30–21:00. |
| **Refresh from Suivi and the project register only** | `make import` |
| **Refresh those and your Google Calendar** | `make calendar` |
| **Fetch and triage your recent emails** (read-only) | `make gmail`. The triage then runs in the background; the Emails panel fills in as it goes. |
| **Learn how you write to each person** | `make correspondence` (read-only; takes a few minutes). Then review the results on the Inbox tab under **How you write to people**. |
| **Install the draft agent** (once) | `make agent-install`. It starts at login and saves *approved* drafts to Gmail. It cannot send. Check it with `make agent-status`, remove it with `make agent-uninstall`. |
| **Stop it** | `make down` |

The Today page reloads its own data every minute. **Personal items** (Suivi domain P) are masked: the board shows **🔒 Personal task** (or Personal follow-up) with its date, and the page never receives the title or project code until you click "show details". The same on the lake and in the Done record. Click the **✎** on any open item to change its title or date (a waiting-on item's "chase on" date too). Edits are kept here even after the next import from Suivi, the row is marked *edited*, and the editor shows what Suivi still says, with **Reset to the original**. Suivi.xlsx itself is never changed. Items due more than a week away are under **Later**. Ticked items move into **Done today** (with the time). Click the green counter, or "See everything you have done", for the full record by day: search it, and **Reopen** anything. Emails have a **Mark as done** button in their pop-out; handled emails stay findable under **Handled** on the Inbox tab. Ticking something off is saved straight away in `~/IG-Harness-data/harness.db` and does not change Suivi.xlsx. Suivi stays your source of truth for now, and the harness only mirrors it.

## First time only (already done on this Mac)

1. Create the data folder: `mkdir -p ~/IG-Harness-data`
2. Copy `.env.example` to `.env` and set `SUIVI_DIR` and `PROJETS_DIR` to your two folders (they are mounted read-only).
3. Connect the calendar, once:
   - `python3 tools/google_helper.py store-client <the downloaded client_secret file>`
   - `python3 tools/google_helper.py login` (approve **read-only** calendar access in the browser)
   - `python3 tools/google_helper.py login-gmail` (approve **read-only** Gmail access; this cannot create drafts or send)

## Updating the harness

When Claude has made changes and you have agreed to them: `make down`, then `make up`. Docker rebuilds what changed.

## If something looks wrong

| Symptom | What to do |
|---|---|
| Page says "back end not reachable" | Is Docker Desktop running? Then `make up`. `make logs` shows the last messages. |
| "Not logged in" from `make calendar` | Run `python3 tools/google_helper.py login` again. |
| "Not logged in" from `make gmail` | Run `python3 tools/google_helper.py login-gmail`. |
| Emails panel says "waiting to be triaged" | Click **Triage now**. The local model must be running (header says "Local model"). A 27B model can take a minute or two per batch. |
| Calendar is empty or stale | Run `make calendar`. It is manual for now; automatic refresh comes later. |
| Numbers differ from Suivi | Run `make import`. Items you ticked off here stay ticked even if Suivi still shows them open. |

## Checking the code

`make test` runs the automated tests (synthetic data only, never your real files).

## Where things live

- Your data: `~/IG-Harness-data/` (database and calendar file). Never in the repo.
- Your Google tokens: macOS Keychain (`ig-harness-google-client`, `ig-harness-google-calendar`, `ig-harness-google-gmail`).
- Recent emails (trimmed text) are kept in `~/IG-Harness-data` only, and are only ever read by your local model.
- Never send email: the harness has no send function (Phase 3 adds drafts only, with a test that proves it).

## Proving the safety rules still hold

- `make test` includes the red-team tests (sensitive samples can't reach any external provider), the "one exit door" scan, and fail-safe tests for bad, huge and hostile email input.
- `make check-network` proves the containers have no internet, that only the gateway can reach your Ollama, and that Gmail's API is unreachable from the containers. Run it after any change to `docker-compose.yml`.


## Draft replies and reminders

1. Open an email (Today or Inbox) and click **Draft a reply**. The local model writes it on this Mac, in the language and tone it has learned for that person (professional for someone new). Use **Choose tone, language or what to say first** to steer it.
2. Edit the text, then **Save to Gmail as a draft**. Only that click lets the background agent create the Gmail draft, with exactly that text, inside the same conversation. You review and send it yourself from Gmail.
3. For something you are waiting on (a waiting-on item whose chase date has come), click **Remind**. The harness suggests the conversation where you asked for it; you can pick another or start a new message.

Needed once and refreshed now and then: `make gmail` (so replies can be threaded), `make correspondence` (your style per person, and the conversations used for reminders), and `make agent-install`.


## The background agents (set up once)

| Agent | What it does | Install / remove |
|---|---|---|
| **Refresh agent** | Every 30 min between 06:30 and 21:00, and when you press ↻: fetches your calendar and Gmail (read-only), reads your past correspondence about once a day, imports everything, triages new email, and makes the daily backup. | `make refresh-install` / `make refresh-uninstall` |
| **Draft agent** | Creates a Gmail *draft* only after you approve it in the app. Cannot send. | `make agent-install` / `make agent-uninstall` |

`make agent-status` shows both, the last refresh and the latest backup. The header chip turns orange if the last refresh failed or is stale, and its hover text lists each step. Logs (no email text) are in `~/IG-Harness-data/logs/`. Both agents start at login. They need the harness running (`make up`) for the import and triage steps; if it isn't, those steps are skipped and the fetching still happens.

## Backups and restoring

- **Automatic:** a verified snapshot of the harness database once a day (by the refresh agent), kept in `~/IG-Harness-Backups/` (14 daily, 12 monthly), plus an automatic copy before any database upgrade (`~/IG-Harness-data/backups/`). These stay on this Mac because the database holds confidential and personal data. Time Machine or an encrypted external drive can copy the folder.
- **`make backup`**: a snapshot now. **`make backup-list`**: what exists. **`make backup-test`**: restores the newest into a throwaway folder, opens it the way the harness does, and compares it with the live data. It should say `RESULT: PASS`.
- **If something goes wrong:** `make down`, then `python3 tools/backup.py restore <snapshot file> --yes`, then `make up`. Your current database is kept next to it as `harness.db.before-restore-…`, never deleted.
- What is *not* in the backup: your Google tokens (Keychain; you would log in again with `login`, `login-gmail` and `draft_worker.py login`), and your spreadsheets (they stay where they are).


## Notes and follow-ups

- **On an item:** click the **📝** on any open item in Today & overdue, or open an email, and write a **note** (context) or a **follow-up**. A follow-up also becomes a task in Today & overdue (due today, or the date you pick), tagged "from a note". Ticking it off shows on the note ("follow-up done"), and removing the note drops an open follow-up.
- **Free-standing:** **＋ Add a note or follow-up** at the top of the Today & overdue and the Emails needing you panels. Tick *personal* for a private one.
- **The record:** **All notes →** lists everything, newest first, with search and the follow-up status. Notes live in the harness database, so they are in your backups. Your notes on an email or a waiting-on item are also given to the model as context when it drafts a reply or reminder (never personal notes).
- **Into Suivi:** your **work** notes are also added to the Journal sheet of `Suivi.xlsx` (by the refresh agent, within 30 minutes), as `capture` rows with status `confirmed`, a type of `work` (or `email` for a note on an email), the project code, and an evidence pointer (the Gmail thread ID for email notes, otherwise `harness-note:N`). Each note shows `in Suivi J-2026-0NN` once added. **Personal notes are never sent to Suivi** (it lives in Google's cloud). Safeguards: a backup of Suivi.xlsx before every write (`~/IG-Harness-Backups/suivi/`, last 30), nothing is written while Excel has the file open or if it changed in the last 90 seconds, only the next empty journal rows change, everything is checked before and after, and your original is put back if a check fails. `make suivi-export-dry-run` shows what would be added; `make suivi-export-pause` / `-resume` switch it off and on.
- Notes on personal items are masked like the items themselves: "Personal note", details only on click, never matched by search.

## The calendar widget

The **Calendar** tile (top of the right-hand column) shows today's count and your next event. Click it for a full **Day / Week / Month** view of your Google Calendar. **Deadlines** and **Tasks & chase dates** can be switched on or off. Click a day to open it, an event for its details, and use the arrow keys or the ‹ › buttons to move. Times are Geneva time. It is read-only: the harness never changes your calendar. It shows from 35 days back to 120 days ahead, and it remembers your last view.


## Audit readiness (Projects & finance)

The **Audit readiness** tile shows what share of the bank debits in your year folder has its document, using your own `controle_justificatifs.py`, run **unchanged inside the harness**. Click it for the result (justified / covered / still to justify), the list of payments still missing a document, a **Check again now** button, and a comparison with your own `Controle_justificatifs_<year>.xlsx` report.

- Only the **2026 year folder** and the **Outils** folder are connected, read-only (set in `.env`: `AUDIT_YEAR_DIR`, `AUDIT_TOOLS_DIR`). Nothing is written to your folders and nothing is installed on your Mac. The PDF reader (poppler) lives inside the harness.
- The tile says when documents have changed since the last check; press **Check again now** (it takes seconds).
- Statements, receipts and amounts are confidential and stay on this Mac. No IBAN is stored, only the short account label your script prints.
- To use another year, point `AUDIT_YEAR_DIR` at that year's folder (and later we can mount more years).

## Projects & finance tab

The tab lists your four projects and your threads, taken from the Codes sheet of Suivi, with what is open and overdue, the next date,
the last journal entry, and tagged calendar events (a `[TK]` in an event title attaches it to TK). Click a card for the detail.
Personal areas never appear. Where Suivi says a project is in the project register but the register has no row yet (today: FAGI, MDH, TK),
a notice says so; the funders you named (TK: Swiss FDFA; MDH: Gablinger for the course, SmartPeace for the self-hosting build) are not
recorded anywhere yet, and the harness never writes to the register. Hours, Budget burn and Scan inbox are still "coming soon".

## Adding bank statements (quarterly UBS PDFs)

1. Download the statements from UBS as usual (they land in Downloads).
2. Projects & finance tab → **Bank statements → Add bank statements**, and select the PDFs (you can select several at once; extra
   "(1)" copies are fine).
3. Each file gets a preview: account, period, and one of: **new**, **already in the folder** (identical content, including browser
   "(1)" copies), **name taken by a different file**, **same account and period as an existing statement**, **wrong year**, or
   **not a statement**. Only "new" can be added; the others are explained and need nothing from you.
4. Click **Add to folder** (or **Add all N new statements**). The Mac-side filer (part of the refresh agent, `tools/filer.py`) creates the
   file as a **new file** in the 2026 audit folder under UBS's own name. It never overwrites, deletes or renames anything, re-checks your
   approval and the file's fingerprint, and verifies the copy afterwards. The audit check then re-runs by itself.

The agent must have been restarted once after this update: `make refresh-install`. To file by hand: `make filing-now`.

## Scans: invoices, receipts and other justificatifs

**Setup (once):** in Image Capture choose *Scan To: Scan-Inbox* (the `Scan-Inbox` folder in your home folder) and *Format: PDF*. The harness
looks at that folder read-only; it never changes, moves or deletes your scans.

**Each scan:** within a few seconds a new scan is read on this Mac (text recognition + the local model; nothing leaves the Mac) and appears under
**Scan inbox** (Today and Projects & finance) as *to confirm*. Click it to see, for each scan: type, supplier, number, amount, currency, payment
date, folder and the **exact file name it would get**. Correct any field (the name updates). Then **Add to folder**, or **Skip**.

- Name: `Fournisseur_Facture_<n>_CHF<montant>_paye_JJ.MM.AAAA.pdf` (income: `_recu_`). The payment date is filled in only when exactly one
  unjustified payment of that amount (matching the supplier) exists in your latest audit check; otherwise you are asked, or the name has no date yet.
- Folder: invoices and receipts → `Expenses`, invoices you issued → `Income`; contracts and unclear documents wait for your choice.
- Duplicates (identical content already in your folder) are set aside; a different file with the same name is saved as `_v2`, `_v3`… Nothing is ever overwritten or deleted.
- After filing, the audit check re-runs by itself. The original scan stays in Scan-Inbox; tidy it by hand when you like.
- No scanner at hand? **Add invoices and receipts** lets you choose PDFs directly.
- After updating: `docker compose build` is needed once (text recognition was added to the image); `make refresh-install` is already done.

**If Image Capture adds a new scan to the previous file** (the "Combine into single document" option reuses the name `Scan.pdf`): the harness notices that
`Scan.pdf` came back changed with more pages, and splits it into one scan per page by itself. The file in Scan-Inbox is never altered. A page that
repeats an earlier scan is flagged ("looks like the same document as scan #…"); skip one of them. For a multi-page PDF that is really one document,
nothing is split; use **Split into single pages** on a card only when its pages are different documents.
Tip: once a scan is filed, move its file from Scan-Inbox to the Trash yourself, so the next scan starts with a fresh `Scan.pdf`.

**Suivi journal rows for filed documents.** After a scanned document has really been added to your audit folder (not merely approved), the same safeguarded
writer that adds your work notes (every 30 minutes, or at once with ↻ / `make suivi-export-now`) adds one row to Suivi's Journal: type `document`, code
`FIN`, a one-line summary ("Filed invoice: Alber Rolle SA, no. 002131, CHF 2972.75, paid 29.01.2026 (in 2026/Expenses)"), and the evidence
`Admin/ICT4Peace Audit/2026/Expenses/<file name>`, status `confirmed` (you approved it). Each document is added once. The same pause switch stops it
(`make suivi-export-pause`). The filed card in the Scan inbox shows the journal id once it is in.

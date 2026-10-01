# Running the IG Harness

The harness runs on your Mac in Docker and opens in your browser. Nothing leaves your Mac in Phase 1: there is no AI yet, and your spreadsheets are only read, never changed.

## Every day

| I want to… | Do this |
|---|---|
| **Start it** | Open **Docker Desktop** (wait until it says "running"), then in Terminal: `cd ~/Developer/ig-harness && make up` |
| **Open it** | Go to <http://localhost:5173> in your browser |
| **Refresh from Suivi and the project register** | `make import` |
| **Refresh those and your Google Calendar** | `make calendar` |
| **Stop it** | `make down` |

The Today page reloads its own data every minute. Ticking something off is saved straight away in `~/IG-Harness-data/harness.db` and does not change Suivi.xlsx. Suivi stays your source of truth for now, and the harness only mirrors it.

## First time only (already done on this Mac)

1. Create the data folder: `mkdir -p ~/IG-Harness-data`
2. Copy `.env.example` to `.env` and set `SUIVI_DIR` and `PROJETS_DIR` to your two folders (they are mounted read-only).
3. Connect the calendar, once:
   - `python3 tools/gcal_helper.py store-client <the downloaded client_secret file>`
   - `python3 tools/gcal_helper.py login` (approve **read-only** access in the browser)

## Updating the harness

When Claude has made changes and you have agreed to them: `make down`, then `make up`. Docker rebuilds what changed.

## If something looks wrong

| Symptom | What to do |
|---|---|
| Page says "back end not reachable" | Is Docker Desktop running? Then `make up`. `make logs` shows the last messages. |
| "Not logged in" from `make calendar` | Run `python3 tools/gcal_helper.py login` again. |
| Calendar is empty or stale | Run `make calendar`. It is manual for now; automatic refresh comes later. |
| Numbers differ from Suivi | Run `make import`. Items you ticked off here stay ticked even if Suivi still shows them open. |

## Checking the code

`make test` runs the automated tests (synthetic data only, never your real files).

## Where things live

- Your data: `~/IG-Harness-data/` (database and calendar file). Never in the repo.
- Your Google token: macOS Keychain (`ig-harness-google-client`, `ig-harness-google-calendar`).
- Never send email: the harness has no send function (Phase 3 adds drafts only, with a test that proves it).

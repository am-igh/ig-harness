.PHONY: up down test logs import calendar gmail correspondence check-network agent-install agent-uninstall agent-status refresh-install refresh-uninstall refresh-now backup backup-list backup-test

up:      ## Start the harness (UI at http://localhost:5173)
	docker compose up -d --build
	@echo "IG Harness is starting: open http://localhost:5173"

down:    ## Stop the harness
	docker compose down

test:    ## Run the automated tests (synthetic data only)
	docker compose run --rm --no-deps api pytest -q

logs:    ## Show recent logs
	docker compose logs --tail=50

import:  ## Re-read Suivi.xlsx and the project register (read-only) and show what changed
	docker compose exec api python -m harness.importers.run

calendar: ## Fetch your Google Calendar (read-only, runs on the Mac) and import it
	python3 tools/google_helper.py sync
	docker compose exec api python -m harness.importers.run

gmail:   ## Fetch recent inbox threads (read-only, on the Mac), import them and run the triage
	python3 tools/google_helper.py sync-gmail
	docker compose exec api python -m harness.importers.run
	curl -s -X POST localhost:5173/api/triage/run; echo

check-network: ## Prove the containers are isolated (no internet; only the gateway reaches Ollama)
	sh scripts/check_network.sh

correspondence: ## Read your past emails with each person (read-only, on the Mac), then learn how you write to them
	python3 tools/google_helper.py sync-correspondence
	docker compose exec api python -m harness.importers.run

agent-install: ## Install the background agent that saves approved drafts to Gmail (never sends)
	sh scripts/install_draft_agent.sh

agent-uninstall: ## Remove the background agent
	sh scripts/uninstall_draft_agent.sh

agent-status: ## Are the background agents (drafts, refresh) installed and running? Last refresh and backup
	sh scripts/agents_status.sh

refresh-install: ## Install the background agent that keeps the harness current (calendar, Gmail, imports, triage, backup)
	sh scripts/install_refresh_agent.sh

refresh-uninstall: ## Remove the refresh agent
	sh scripts/uninstall_refresh_agent.sh

refresh-now: ## Refresh everything right now and print each step
	python3 tools/refresh_worker.py once

backup: ## Make a verified snapshot of the harness database now (kept in ~/IG-Harness-Backups)
	python3 tools/backup.py backup

backup-list: ## List the backups
	python3 tools/backup.py list

backup-test: ## Restore the newest backup into a throwaway folder and compare it with the live data
	python3 tools/backup.py restore-check

.PHONY: ui-test up down test logs import calendar gmail correspondence check-network agent-install agent-uninstall agent-status refresh-install refresh-uninstall refresh-now backup backup-list backup-test suivi-export-dry-run suivi-export-now suivi-export-pause suivi-export-resume events-mail events-public reminders-pull filing-now hours-now hours-pause hours-resume searxng-up searxng-down research-install research-uninstall research-now demo-up demo-seed demo-down demo-reset

up:      ## Start the harness (UI at http://localhost:5173)
	docker compose up -d --build
	@echo "IG Harness is starting: open http://localhost:5173"

down:    ## Stop the harness
	docker compose down

test:    ## Run the automated tests (synthetic data only): back end, then the screen's calendar logic
	docker compose run --rm --no-deps api pytest -q
	docker compose run --rm --no-deps ui node --test src/calendar/layout.test.ts

ui-test: ## Only the screen's own tests (calendar logic)
	docker compose run --rm --no-deps ui node --test src/calendar/layout.test.ts

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

suivi-export-dry-run: ## Show which notes would be added to Suivi's journal, without changing anything
	python3 tools/suivi_writer.py run --dry-run

suivi-export-now: ## Add pending work notes to Suivi's journal right now (the refresh agent does this every 30 min)
	python3 tools/suivi_writer.py run

suivi-export-pause: ## Stop sending notes to Suivi (nothing is uninstalled)
	mkdir -p $(HOME)/IG-Harness-data/suivi_export && touch $(HOME)/IG-Harness-data/suivi_export/DISABLED && echo "Paused."

suivi-export-resume: ## Resume sending notes to Suivi
	rm -f $(HOME)/IG-Harness-data/suivi_export/DISABLED && echo "Resumed."

filing-now: ## File any bank statements you approved (new files only; normally automatic)
	python3 tools/filer.py once

hours-now: ## Append the hour entries you approved to hours.csv (normally automatic)
	python3 tools/hours_writer.py once

hours-pause: ## Stop the harness appending to hours.csv
	mkdir -p ~/IG-Harness-data/hours && touch ~/IG-Harness-data/hours/DISABLED

hours-resume: ## Let the harness append to hours.csv again
	rm -f ~/IG-Harness-data/hours/DISABLED

events-mail: ## Read the past year of event emails (read-only Gmail) for the Geneva and beyond tab; later runs only read the last 3 weeks
	python3 tools/google_helper.py sync-events

reminders-pull: ## Read your phone to-dos now (Reminders list "Harness"); macOS asks once for permission
	python3 tools/reminders_helper.py pull

events-public: ## Fetch the public International Geneva listings (geneve-int.ch, Club Diplomatique, UN Geneva), politely
	python3 tools/events_helper.py pull

searxng-up: ## Start the self-hosted search engine for Research mode (first time: downloads its image)
	sh scripts/searxng_init.sh
	docker compose --profile research up -d searxng
	@echo "Search engine at http://127.0.0.1:8888 (only this Mac can reach it)."

searxng-down: ## Stop the search engine
	docker compose --profile research stop searxng

research-install: ## Install the background agent that reads public web pages for Research mode
	sh scripts/install_research_agent.sh

research-uninstall: ## Remove the research agent
	sh scripts/uninstall_research_agent.sh

research-now: ## Process waiting research requests once, now
	python3 tools/research_helper.py once

DEMO = docker compose -p igdemo -f docker-compose.yml -f docker-compose.demo.yml

demo-up: ## Start the AURORA demo (fictitious data, separate from your real harness): http://localhost:5174
	mkdir -p $(HOME)/IG-Harness-Demo-data
	$(DEMO) up -d --build api worker ui ollama-bridge
	@sleep 8
	$(DEMO) exec -T api python -m harness.demo_seed
	@echo "AURORA demo at http://localhost:5174 (banner says DEMO; nothing real is connected)."

demo-seed: ## Add the AURORA data to the demo instance (does nothing if it is already there)
	$(DEMO) exec -T api python -m harness.demo_seed

demo-down: ## Stop the demo
	$(DEMO) down

demo-reset: ## Throw the demo's data away and start it again from the story (use before each demo so the dates are fresh)
	$(DEMO) down
	rm -f $(HOME)/IG-Harness-Demo-data/harness.db $(HOME)/IG-Harness-Demo-data/harness.db-wal $(HOME)/IG-Harness-Demo-data/harness.db-shm
	$(MAKE) demo-up

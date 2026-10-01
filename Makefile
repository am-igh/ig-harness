.PHONY: up down test logs import calendar

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
	python3 tools/gcal_helper.py sync
	docker compose exec api python -m harness.importers.run

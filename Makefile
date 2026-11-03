.PHONY:  help setup notebook app model deck deck-pdf agent check format test db semantic-check export-html export-wasm export clean

NOTEBOOK    := notebooks/case_analysis.py
DECK        := notebooks/vip_presentation.py
STATIC_HTML := reports/case_analysis.html
SITE_DIR    := site

help: ## Show available commands
	@echo "Usage: make <target> from the repo root (targets are lowercase)"
	@echo ""
	@echo "setup        Sync the uv environment"
	@echo "notebook     Open the notebook in marimo edit"
	@echo "app          Run the notebook as a read-only app"
	@echo "model        Open the data model viewer"
	@echo "deck         Open the presentation deck"
	@echo "deck-pdf     Export the deck to vip_presentation.pdf"
	@echo "check        Run marimo checks and ruff lint/format checks"
	@echo "format       Format Python code with ruff"
	@echo "test         Run pytest if tests exist"
	@echo "db           Build local DuckDB views from the semantic model"
	@echo "semantic-check Validate semantic model and SQL examples"
	@echo "export-html  Build the static HTML backup"
	@echo "export-wasm  Build the interactive WASM site"
	@echo "export       Check, then build both exports"
	@echo "clean        Remove generated site and caches"

setup: ## Sync the uv environment
	uv sync

notebook: ## Open the notebook in marimo edit
	uv run marimo edit $(NOTEBOOK)

app: ## Run the notebook as a read-only app
	uv run marimo run $(NOTEBOOK)

model: ## Open the data model viewer
	uv run marimo edit notebooks/data_model.py

deck: ## Open the presentation deck
	uv run marimo edit $(DECK)

deck-pdf: ## Export the deck to vip_presentation.pdf
	uv run --with playwright --with pillow python scripts/export_deck_pdf.py

check: semantic-check ## Run marimo checks and ruff lint/format checks
	uv run marimo check $(NOTEBOOK) notebooks/data_model.py
	uv run ruff check .
	uv run ruff format --check .

format: ## Format Python code with ruff
	uv run ruff format .

test: ## Run pytest if tests exist
	@if find tests -type f -name 'test_*.py' | grep -q .; then \
		uv run pytest; \
	else \
		echo "No test files found; skipping pytest."; \
	fi

db: ## Build local DuckDB views from the semantic model
	uv run python notebooks/utils/semantic.py --build-db data/processed/vipps.duckdb

semantic-check: ## Validate semantic model and SQL examples
	uv run pytest tests/test_semantic.py

export-html: ## Build the static HTML backup
	mkdir -p reports
	uv run marimo export html $(NOTEBOOK) -o $(STATIC_HTML)

export-wasm: ## Build the interactive WASM site
	uv run marimo export html-wasm $(NOTEBOOK) -o $(SITE_DIR) \
		--mode run --no-show-code --execute

export: check export-html export-wasm ## Check, then build both exports

clean: ## Remove generated site and caches
	rm -rf $(SITE_DIR) .pytest_cache .ruff_cache

MARIMO_PORT ?= 2718
MARIMO_URL  ?= http://127.0.0.1:$(MARIMO_PORT)

agent: ## Open the notebook and pair it with the marimo agent
	@set -eu; \
	if uv run marimo pair notebook list --url $(MARIMO_URL) 2>/dev/null | grep -q 'case_analysis.py'; then \
		echo "Reusing the notebook already open at $(MARIMO_URL)"; \
	else \
		echo "Starting marimo at $(MARIMO_URL)"; \
		uv run marimo edit $(NOTEBOOK) --no-token --host 127.0.0.1 --port $(MARIMO_PORT) & \
		pid=$$!; \
		trap 'kill $$pid 2>/dev/null || true' EXIT INT TERM; \
		echo "Waiting for the notebook (open $(MARIMO_URL) if no browser opened)..."; \
		i=0; \
		while ! uv run marimo pair notebook list --url $(MARIMO_URL) 2>/dev/null | grep -q 'case_analysis.py'; do \
			i=$$((i + 1)); \
			[ "$$i" -ge 60 ] && { echo "Timed out waiting for the notebook." >&2; break; }; \
			sleep 1; \
		done; \
	fi; \
	opencode

.PHONY: install test generate clean help

PYTHON ?= python3
VENV   := .venv

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-15s\033[0m %s\n", $$1, $$2}'

install: ## Create venv, install deps, check ffmpeg
	$(PYTHON) -m venv $(VENV)
	$(VENV)/bin/pip install --upgrade pip
	$(VENV)/bin/pip install -r requirements.txt
	@command -v ffmpeg >/dev/null 2>&1 || \
		echo "\n⚠️  ffmpeg not found in PATH. Install it: https://ffmpeg.org/download.html"
	@echo "\n✅  Installation complete. Activate with: source $(VENV)/bin/activate"

test: ## Run smoke tests for each engine module
	$(VENV)/bin/python scripts/test_engines.py

generate: ## Run the full reel generation pipeline
	$(VENV)/bin/python scripts/generate_reel.py $(ARGS)

clean: ## Remove tmp/ working directory
	rm -rf tmp/*
	@echo "✅  Temp directory cleaned."

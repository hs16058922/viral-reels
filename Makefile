.PHONY: install test generate studio studio-test clean help

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

studio: ## 3D studio reel, e.g. make studio TOPIC="How does a jet engine work?" QUALITY=preview
	$(VENV)/bin/python -m engine.studio "$(TOPIC)" --quality $(or $(QUALITY),preview)

studio-test: ## Unit tests for SceneSpec v2 / studio pipeline
	$(VENV)/bin/python -m unittest tests.test_studio -v

clean: ## Remove tmp/ working directory
	rm -rf tmp/*
	@echo "✅  Temp directory cleaned."

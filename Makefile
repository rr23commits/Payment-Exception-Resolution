.DEFAULT_GOAL := help

PYTHON ?= python3
VENV ?= .venv
PY := $(VENV)/bin/python
DATA ?= data/raw/transactions.csv

.PHONY: help setup check test evaluate run

help:
	@printf '%s\n' 'Payment Exception Resolution Engine' '' 'make setup     Create .venv and install project dependencies.' 'make check     Verify the virtualenv, dependencies, and source CSV.' 'make test      Run the full regression suite (start PostgreSQL first).' 'make evaluate  Run the Phase 13 end-to-end proof and write reports.' 'make run       Start the local read-only API and UI demo at http://127.0.0.1:8000'

setup:
	$(PYTHON) -m venv $(VENV)
	$(PY) -m pip install --upgrade pip
	$(PY) -m pip install --editable .

check:
	@test -x "$(PY)" || { echo 'Missing virtual environment: run make setup'; exit 1; }
	@test -f "$(DATA)" || { echo 'Missing source CSV: place the unchanged dataset at $(DATA)'; exit 1; }
	@$(PY) -c "import psycopg, sklearn"

test: check
	$(PY) -m unittest discover -s tests -v

evaluate: check
	$(PY) -m src.evaluation $(DATA) --report evaluation/phase13_end_to_end_report.json --markdown-report evaluation/reports/phase13_end_to_end.md

run: check
	@echo 'Open http://127.0.0.1:8000 in your browser. Press Ctrl-C to stop.'
	$(PY) -m src.api $(DATA) --host 127.0.0.1 --port 8000

PYTHON ?= python3
VENV ?= .venv
VENV_PYTHON := $(VENV)/bin/python

.PHONY: setup lint typecheck test validate check run docker-build

setup:
	$(PYTHON) -m venv $(VENV)
	$(VENV_PYTHON) -m pip install --upgrade pip
	$(VENV_PYTHON) -m pip install -e "./src/hotel-servicing-agent[dev]"

lint:
	$(VENV_PYTHON) -m ruff check src scripts tests
	$(VENV_PYTHON) -m ruff format --check src scripts tests

typecheck:
	$(VENV_PYTHON) -m mypy src/hotel-servicing-agent/hotel_servicing_agent scripts

test:
	$(VENV_PYTHON) -m pytest

validate:
	$(VENV_PYTHON) scripts/validate_technical_naming.py
	$(VENV_PYTHON) scripts/validate_configuration.py

check: lint typecheck test validate

run:
	./run.sh

docker-build:
	docker build --tag hotel-servicing-agent:local .

PYTHON ?= python3
VENV ?= .venv
VENV_PYTHON := $(VENV)/bin/python

.PHONY: setup lint typecheck test web-check validate check run run-web docker-build web-docker-build

setup:
	$(PYTHON) -m venv $(VENV)
	$(VENV_PYTHON) -m pip install --upgrade pip
	$(VENV_PYTHON) -m pip install -e "./src/hotel-servicing-agent[dev]"
	$(VENV_PYTHON) -m pip install -e "./web/backend[dev]"
	npm --prefix web/frontend ci

lint:
	$(VENV_PYTHON) -m ruff check src web/backend scripts tests
	$(VENV_PYTHON) -m ruff format --check src web/backend scripts tests

typecheck:
	$(VENV_PYTHON) -m mypy \
		src/hotel-servicing-agent/hotel_servicing_agent \
		web/backend/hotel_voice_proxy \
		scripts

test:
	$(VENV_PYTHON) -m pytest

web-check:
	npm --prefix web/frontend test
	npm --prefix web/frontend run lint
	npm --prefix web/frontend run typecheck
	npm --prefix web/frontend run build

validate:
	$(VENV_PYTHON) scripts/validate_technical_naming.py
	$(VENV_PYTHON) scripts/validate_configuration.py

check: lint typecheck test web-check validate

run:
	./run.sh

run-web:
	$(VENV_PYTHON) -m hotel_voice_proxy.app

docker-build:
	docker build --tag hotel-servicing-agent:local .

web-docker-build:
	docker build --file web/backend/Dockerfile \
		--build-arg VITE_ENTRA_CLIENT_ID \
		--build-arg VITE_ENTRA_AUTHORITY \
		--build-arg VITE_ENTRA_REDIRECT_URI \
		--build-arg VITE_ENTRA_API_SCOPE \
		--build-arg VITE_BACKEND_BASE_URL \
		--tag hotel-voice-proxy:local .

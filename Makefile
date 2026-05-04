.PHONY: help preflight deps lint test test-web run-web \
	compose-config docker-build docker-up-web docker-down docker-logs-web \
	docker-cli docker-shell docker-hf-download docker-ps

SHELL := /bin/bash

help:
	@echo "Available targets:"
	@echo "  make preflight         - Create required storage/exports folders and set permissions"
	@echo "  make deps              - Install project dependencies with uv"
	@echo "  make lint              - Run Ruff checks"
	@echo "  make test              - Run full test suite"
	@echo "  make test-web          - Run web tests"
	@echo "  make run-web           - Run web app locally on :8000"
	@echo "  make compose-config    - Validate and render docker compose config"
	@echo "  make docker-build      - Build all compose services"
	@echo "  make docker-up-web     - Start web service on :8111"
	@echo "  make docker-down       - Stop all compose services"
	@echo "  make docker-logs-web   - Tail web service logs"
	@echo "  make docker-cli        - Open interactive hf-exporter container"
	@echo "  make docker-shell      - Open interactive hf-shell container"
	@echo "  make docker-hf-download REPO=owner/model - Run one-shot hf download"
	@echo "  make docker-ps         - Show compose service status"

preflight:
	bash scripts/preflight.sh

deps:
	uv sync

lint:
	uv run ruff check

test:
	uv run pytest

test-web:
	uv run pytest tests/test_web.py

run-web:
	uv run uvicorn hf_exporter.web:app --host 0.0.0.0 --port 8000 --reload

compose-config:
	docker compose config

docker-build:
	docker compose build

docker-up-web:
	docker compose up hf-exporter-web

docker-down:
	docker compose down

docker-logs-web:
	docker compose logs -f hf-exporter-web

docker-cli:
	docker compose run --rm hf-exporter

docker-shell:
	docker compose run --rm hf-shell

docker-hf-download:
	@if [[ -z "$(REPO)" ]]; then \
		echo "Usage: make docker-hf-download REPO=owner/model"; \
		exit 1; \
	fi
	docker compose run --rm hf-shell hf download "$(REPO)"

docker-ps:
	docker compose ps

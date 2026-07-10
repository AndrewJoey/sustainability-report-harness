.PHONY: install test lint format validate

install:
	UV_CACHE_DIR=.uv-cache uv sync --locked

test:
	UV_CACHE_DIR=.uv-cache uv run pytest

lint:
	UV_CACHE_DIR=.uv-cache uv run ruff check .

format:
	UV_CACHE_DIR=.uv-cache uv run ruff format .
	UV_CACHE_DIR=.uv-cache uv run python skills/sustainability-report-harness/scripts/update_manifest.py

validate:
	UV_CACHE_DIR=.uv-cache uv run python skills/sustainability-report-harness/scripts/validate_examples.py

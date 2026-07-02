.PHONY: install dev test lint

install:
	uv sync --all-packages

dev:
	uv run --package ensemble-backend python -c "from ensemble.config import get_settings; print(get_settings())"

test:
	uv run pytest

lint:
	uv run ruff check .

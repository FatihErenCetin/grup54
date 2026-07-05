.PHONY: install dev test lint openapi

install:
	uv sync --all-packages

dev:
	uv run uvicorn ensemble.app:create_app --factory --reload --port 8000

openapi:
	uv run python -c "import json; from pathlib import Path; from ensemble.app import create_app; Path('src/shared/openapi.json').write_text(json.dumps(create_app().openapi(), indent=2, ensure_ascii=False), encoding='utf-8')"

test:
	uv run pytest

lint:
	uv run ruff check .

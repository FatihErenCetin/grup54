.PHONY: install dev test lint openapi

install:
	uv sync --all-packages

dev:
	uv run uvicorn ensemble.app:create_app --factory --reload --port 8000

openapi:
	uv run python -c "import json; from ensemble.app import create_app; print(json.dumps(create_app().openapi(), indent=2, ensure_ascii=False))" > src/shared/openapi.json

test:
	uv run pytest

lint:
	uv run ruff check .

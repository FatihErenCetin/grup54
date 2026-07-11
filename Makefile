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

migrate:
	cd src/backend && uv run alembic upgrade head

rebuild:
	uv run python -c "from ensemble.store.engine import get_engine, get_session_factory; from ensemble.store.rebuild import rebuild_projection; from ensemble.config import get_settings; from ensemble_shared.harness import FileHarnessPort; settings=get_settings(); engine=get_engine(settings); session=get_session_factory(engine)(); harness=FileHarnessPort(); print('Rebuilding projection...'); res=rebuild_projection(session, harness); print(f'Rebuilt: {res}')"

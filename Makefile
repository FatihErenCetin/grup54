.PHONY: install dev test lint openapi eval-dataset eval-run eval-sweep eval eval-gate scope-eval harness-init frontend-build-guard

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

eval-dataset:
	uv run python eval/backtest/build_dataset.py

rebuild:
	uv run python -c "from ensemble.store.engine import get_engine, get_session_factory; from ensemble.store.rebuild import rebuild_projection; from ensemble.config import get_settings; from ensemble_shared.harness import FileHarnessPort; settings=get_settings(); engine=get_engine(settings); session=get_session_factory(engine)(); harness=FileHarnessPort(); print('Rebuilding projection...'); res=rebuild_projection(session, harness); print(f'Rebuilt: {res}')"

eval-run:
	uv run python -m eval.eval_runner

eval-sweep:
	uv run python -m eval.sweep

# #18 DONE kapısı: eşik+judge geçidi bir komutta + #30 precision-gate.
eval: eval-run eval-sweep eval-gate

# CI precision-gate (#30): eval kalibre operasyon noktasında koşar; precision
# veya F0.5 kalibre tabanın altına düşerse exit 1 (dedektör/judge regresyonu).
eval-gate:
	uv run python -m eval.gate

# #31 scope-drift DONE kapısı: 3-sınıf backtest + yanlış-alarm precision.
scope-eval:
	uv run python -m eval.scope_eval

# Onboarding sihirbazı (#57): ilk .harness/ iskeletini yazar (.harness/ zaten
# varsa DOKUNMAZ - fail-safe). Örnek: make harness-init MILESTONE="Sprint 3"
harness-init:
	uv run python -m ensemble.onboarding.wizard --milestone "$(MILESTONE)"

# #188 prod build hijyen guard: prod `vite build` (VITE_MOCK kapalı) + dist'te
# mock-bayrağı/fixture-handle/backend-sır taraması. CI: prod-build-guard.yml.
frontend-build-guard:
	cd src/frontend && VITE_MOCK= npm run build && node scripts/prod-build-guard.mjs dist

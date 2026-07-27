.PHONY: install dev test lint openapi contracts eval-dataset eval-run eval-sweep eval eval-gate eval-provider eval-model-secimi scope-eval harness-init frontend-build-guard deploy

install:
	uv sync --all-packages

dev:
	uv run uvicorn ensemble.app:create_app --factory --reload --port 8000

openapi:
	uv run python -c "import json; from pathlib import Path; from ensemble.app import create_app; Path('src/shared/openapi.json').write_text(json.dumps(create_app().openapi(), indent=2, ensure_ascii=False), encoding='utf-8')"

# #56 tek reçete: openapi.json + TS client'i BIRLIKTE regen eder (router/schema
# degisikliginden sonra bunu calistir). node_modules gerekir (bir kez `npm ci`
# ya da `cd src/frontend && npm ci`). CI'nin zorunlu yoluna sokulmaz (npm
# maliyeti — bkz. docs/kontrat-drift-guardrail.md); yalnizca yerel reçete +
# CI hata mesajinin isaret ettigi komut.
contracts: openapi
	cd src/frontend && npm run gen:api

test:
	uv run pytest

lint:
	uv run ruff check .

migrate:
	cd src/backend && uv run alembic upgrade head

eval-dataset:
	uv run python eval/backtest/build_dataset.py

rebuild:
	uv run python -m ensemble.store.rebuild

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

# #78 canli provider kalibrasyonu. Ornek:
#   make eval-provider                 # ikisi
#   make eval-provider PROVIDER=ollama # yalniz Ollama
PROVIDER ?= both
eval-provider:
	uv run python -m eval.provider_eval --provider "$(PROVIDER)"

# #31 scope-drift DONE kapısı: 3-sınıf backtest + yanlış-alarm precision.
scope-eval:
	uv run python -m eval.scope_eval

# #244 YZ model seçimi ölçümü — judge (GEMINI_MODEL) + embedding boyutu
# (GEMINI_EMBEDDING_DIMENSIONS) karşılaştırması. Varsayılan: yalnız tahmini
# çağrı sayısını yazdırır (ağsız) — GEMINI_API_KEY yoksa/`--run` verilmezse
# gerçek çağrı YAPILMAZ (maliyet kontrolü). Gerçek ölçüm:
#   uv run python -m eval.model_secimi_eval --run
# Rapor: eval/model-secimi-raporu.md.
eval-model-secimi:
	uv run python -m eval.model_secimi_eval

# Onboarding sihirbazı (#57): ilk .harness/ iskeletini yazar (.harness/ zaten
# varsa DOKUNMAZ - fail-safe). Örnek: make harness-init MILESTONE="Sprint 3"
harness-init:
	uv run python -m ensemble.onboarding.wizard --milestone "$(MILESTONE)"

# #188 prod build hijyen guard: prod `vite build` (VITE_MOCK kapalı) + dist'te
# mock-bayrağı/backend-sır taraması (takım handle'ları serbest, PO kararı #214).
# CI: prod-build-guard.yml.
frontend-build-guard:
	cd src/frontend && VITE_MOCK= npm run build && node scripts/prod-build-guard.mjs dist

# Self-host VDS'e deploy (#246, D-46 — Fly.io yerine "yan yana yaşama").
# fly.toml + flyctl KALDIRILDI (#181 devre dışı); bu hedef artık compose ile
# aynı işi self-host makinede görür: imaj build + migrate (fail-closed,
# `depends_on.migrate.condition: service_completed_successfully`) + api.
# Sunucuda repo/deploy/ dizininden, `.env.production` hazırlanmış olarak
# koşulur (bkz. deploy/.env.production.example + deploy/docker-compose.prod.yml
# başlığı). Hedef ADI bilerek `deploy` kaldı (diğer referanslar kırılmasın).
deploy:
	cd deploy && docker compose -f docker-compose.prod.yml --env-file .env.production up -d --build

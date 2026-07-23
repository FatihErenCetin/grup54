# syntax=docker/dockerfile:1
#
# Ensemble backend — çok-aşamalı imaj (Fly.io hedefi, #61).
#
# Aşamalar:
#   1) builder — uv ile bağımlılıkları + workspace paketlerini senkronla (cache-dostu layer sırası)
#   2) runtime — sadece çalışma-zamanı için gereken şeyleri taşı (non-root, slim)
#
# uv sürümü PIN'li (latest KULLANMA — reprodüktibilite). Yerel geliştirme
# makinesindeki uv (0.10.x) ile hizalı; uv.lock formatıyla uyumluluğu bunun
# için garanti eder.
FROM ghcr.io/astral-sh/uv:0.10.2 AS uv

FROM python:3.12-slim AS builder

# uv binary'lerini resmi imajdan al (ayrı kurulum adımı yok → hızlı + küçük).
COPY --from=uv /uv /uvx /bin/

# uv derleme sırasında .venv'i bytecode'a derlesin (soğuk başlatmayı hızlandırır)
# ve kopyalama yerine hardlink kullanmasın (farklı katmanlar arası taşınabilir olsun).
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never

WORKDIR /app

# --- Katman 1: yalnızca bağımlılık grafiği (kaynak kodu HENÜZ yok) ---
# Bu sayede kaynak kodu değiştiğinde (ama bağımlılıklar değişmediğinde) uv sync
# yeniden koşmaz — Docker layer cache'i korunur.
COPY pyproject.toml uv.lock ./
COPY src/backend/pyproject.toml src/backend/pyproject.toml
COPY src/shared/pyproject.toml src/shared/pyproject.toml
COPY src/mcp/pyproject.toml src/mcp/pyproject.toml

# Workspace üyelerinin kendi kaynak kodu olmadan "editable" kurulumu başarısız
# olur (hatchling paket dizinini arar) — bu yüzden --no-install-workspace ile
# yalnızca 3.parti bağımlılıkları senkronla; üye paketler katman 2'de kurulur.
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev --no-install-workspace

# --- Katman 2: kaynak kodu + workspace paketlerini kur ---
COPY src/backend/ src/backend/
COPY src/shared/ src/shared/
COPY src/mcp/ src/mcp/

RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev

# ---------------------------------------------------------------------------
FROM python:3.12-slim AS runtime

# Non-root kullanıcı — imaj içinde en az ayrıcalık.
RUN groupadd --system --gid 1000 ensemble \
    && useradd --system --uid 1000 --gid ensemble --home-dir /app --shell /usr/sbin/nologin ensemble

WORKDIR /app

# Sadece derlenmiş venv + kaynak kodu taşı (uv/derleme araçları runtime'a girmez).
COPY --from=builder --chown=ensemble:ensemble /app /app

# alembic.ini kökte (src/backend/) — migration'lar `make migrate` (cd src/backend
# && uv run alembic upgrade head) veya release-migrate (#187) için imajda kalır.
ENV PATH=/app/.venv/bin:$PATH \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

USER ensemble

EXPOSE 8000

# Basit healthcheck — /health local modda (SQLite) harici bağımlılık istemez.
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request,os; urllib.request.urlopen(f'http://127.0.0.1:{os.environ.get(\"PORT\",\"8000\")}/health', timeout=2)" || exit 1

# Prod CMD — reload YOK, host 0.0.0.0, port $PORT (Fly.io PORT enjekte eder,
# yoksa 8000'e düşer). exec-form + `exec`: sh kendini uvicorn ile değiştirir →
# PID 1 uvicorn olur, Fly'ın gönderdiği SIGTERM doğrudan ona ulaşır (graceful
# shutdown; sh'a takılıp grace-period sonunda sert kill riski yok). ${PORT:-8000}
# genişletmesi korunur, Docker'ın JSONArgsRecommended uyarısı da kalkar.
CMD ["sh", "-c", "exec uvicorn ensemble.app:create_app --factory --host 0.0.0.0 --port ${PORT:-8000}"]

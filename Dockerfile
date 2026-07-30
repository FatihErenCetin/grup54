# syntax=docker/dockerfile:1
#
# Ensemble backend — çok-aşamalı imaj (#61). Hedef: self-host VDS + Docker
# Compose (#246, D-46 — Fly.io yerine "yan yana yaşama"; fly.toml kaldırıldı).
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

# .harness/ KANONİK ortak bağlam (#242 — git'e alındı, artık gerçek içerik
# taşıyor). Kaynak katmanıyla BİRLİKTE gelir (katman 1 bağımlılık-only cache'i
# bozulmaz — .harness değişse de uv sync yeniden koşmaz). Runtime'da
# `read_scope`/`read_tasks` bunu okur (ensemble.app.lifespan fail-closed
# kontrolü aşağıda, RUNTIME aşamasında). `.dockerignore` bunu BİLEREK
# dışlamıyor (imaj lean tutma listesi .harness'e dokunmuyor — doğrulaması
# tests/unit/test_harness_git.py'de).
COPY .harness/ .harness/

# T-307 FAZ 1 — yerel tek-komut kurulumu için BOŞ, ÖNCEDEN var olan dizinler:
# SQLite DB (`data/`) + kullanıcı sağlayıcı ayarları (`.ensemble/`, bkz.
# store/provider_settings.py). Aşağıdaki RUNTIME aşamasındaki
# `COPY --from=builder --chown=ensemble:ensemble /app /app` bunları da
# ensemble kullanıcısına devreder; kök `docker-compose.yml` bunların ÜSTÜNE
# boş bir named volume mount edince Docker (yalnız İLK mount'ta) bu (zaten
# doğru sahipli) dizin içeriğini volume'a KOPYALAR — aksi halde taze bir
# named volume root:root 0755 ile yaratılır ve non-root `ensemble` kullanıcısı
# SQLite/ayar dosyasını YAZAMAZ (PermissionError, üretimde değil ama yerel
# `docker compose up`'ta ölçülür).
RUN mkdir -p data .ensemble

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
#
# `HOME=/app`: `store/provider_settings.py` (T-307 FAZ 2) `Path.home() /
# ".ensemble" / "ayarlar.json"` kullanır — `USER ensemble` (aşağıda) ile
# Docker'ın `HOME`'u `/etc/passwd`'den otomatik türetip türetmediği runtime'a
# göre DEĞİŞİR; bunu BURADA açıkça sabitlemek `useradd --home-dir /app`
# (yukarıda) ile TUTARLI, deterministik bir sonuç garantiler.
ENV PATH=/app/.venv/bin:$PATH \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    HOME=/app

USER ensemble

EXPOSE 8000

# Basit healthcheck — /health local modda (SQLite) harici bağımlılık istemez.
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request,os; urllib.request.urlopen(f'http://127.0.0.1:{os.environ.get(\"PORT\",\"8000\")}/health', timeout=2)" || exit 1

# Prod CMD — reload YOK, host 0.0.0.0, port $PORT (deploy/docker-compose.prod.yml
# `environment: PORT: "8000"` enjekte eder, yoksa 8000'e düşer). exec-form +
# `exec`: sh kendini uvicorn ile değiştirir → PID 1 uvicorn olur, Docker'ın
# (`docker compose stop`/restart sırasında) gönderdiği SIGTERM doğrudan ona
# ulaşır (graceful shutdown; sh'a takılıp grace-period sonunda sert kill riski
# yok). ${PORT:-8000} genişletmesi korunur, Docker'ın JSONArgsRecommended
# uyarısı da kalkar.
### #335 — `--forwarded-allow-ips`: OLMAYINCA GITHUB GIRISI CALISMIYORDU
#
# Olcum (29 Tem, canli): `/auth/login`'in GitHub'a yonlendirdigi URL
#   redirect_uri=http%3A%2F%2Fapi.recommend2me.com%2Fauth%2Fcallback
# yani HTTP. GitHub'da kayitli callback https:// oldugu icin eslesmiyor ve
# kullanici "The redirect_uri is not associated with this application" goruyor.
#
# Neden: `api/routers/auth.py` `redirect_uri`'yi `request.url_for()` ile
# uretir; bu da semayi ASGI scope'undan okur. Uvicorn'da `--proxy-headers`
# varsayilan ACIK ama `--forwarded-allow-ips` varsayilani `127.0.0.1` — Caddy
# bu container'a docker agindan (127.0.0.1 DEGIL) baglandigi icin
# `X-Forwarded-Proto: https` basligi SESSIZCE yok sayiliyordu. Bayragin "acik"
# olmasi yetmiyor; kimden geldigine GUVENMESI gerekiyor.
#
# `*` neden guvenli: `deploy/docker-compose.prod.yml`'de api servisi HICBIR
# port YAYINLAMIYOR — yalniz `ensemble-net` uzerinden erisilebiliyor, yani tek
# istemcisi kendi Caddy'miz. Caddy de `deploy/caddy/ensemble.caddy`'de gelen
# `Fly-Client-IP`'yi SILIYOR ve `X-Forwarded-For`'u {remote_host} ile KENDISI
# yaziyor — yani istemcinin gonderdigi basliklara guvenilmiyor.
# Port yayinlanmaya baslarsa bu deger DARALTILMALI (proxy'nin ag IP'si).
#
# Yan kazanc: `api/rate_limit.py::client_ip()` de ayni sebeple bozuktu (tum
# istekler proxy IP'sinden geliyor gorunup demo rate-limit'i herkesi tek kovaya
# koyuyordu); bu duzeltme onu da onarir.
CMD ["sh", "-c", "exec uvicorn ensemble.app:create_app --factory --host 0.0.0.0 --port ${PORT:-8000} --proxy-headers --forwarded-allow-ips='*'"]

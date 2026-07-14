import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from ensemble.api.routers import board, health, query, radar, scope
from ensemble.config import Settings, get_settings
from ensemble.engine.embeddings import HashEmbeddings
from ensemble.engine.radar import RadarService
from ensemble.integrations.gemini.fake import FakeJudgeAdapter
from ensemble.integrations.gemini.judge import GeminiJudgeAdapter
from ensemble.integrations.github.adapter import GitHubAdapter
from ensemble.integrations.github.errors import GitHubConfigError
from ensemble.integrations.github.fake import FakeGitHubAdapter
from ensemble.ports import EmbeddingsPort, GitHubPort, JudgePort

logger = logging.getLogger("ensemble.wiring")


def _build_github_port(settings: Settings) -> GitHubPort:
    # pem dosyası yoksa GitHubAdapter bunu hemen fark etmez (yalnız token
    # yenilenirken okunur) - istek-anı 500'e düşmeden acilis-anı degradasyona
    # ceviriyoruz (Fatih review notu, PR #159).
    if settings.GITHUB_APP_PRIVATE_KEY_PATH and not Path(settings.GITHUB_APP_PRIVATE_KEY_PATH).is_file():
        logger.warning(
            "GITHUB_APP_PRIVATE_KEY_PATH (%s) bulunamadı — FakeGitHubAdapter kullanılıyor.",
            settings.GITHUB_APP_PRIVATE_KEY_PATH,
        )
        return FakeGitHubAdapter()
    try:
        return GitHubAdapter(settings)
    except GitHubConfigError as exc:
        logger.warning("GitHub App yapılandırması eksik (%s) — FakeGitHubAdapter kullanılıyor.", exc)
        return FakeGitHubAdapter()


def _build_judge_port(settings: Settings) -> JudgePort:
    if settings.GEMINI_API_KEY:
        return GeminiJudgeAdapter(settings)
    logger.warning("GEMINI_API_KEY tanımlı değil — FakeJudgeAdapter (kural-tabanlı) kullanılıyor.")
    return FakeJudgeAdapter()


def _build_embeddings_port(settings: Settings) -> EmbeddingsPort:
    # Gerçek Gemini embeddings adapter'ı henüz yok (#15 açık, Semih) — bilinçli
    # ara-durum: her modda HashEmbeddings; #15 kapanınca tek satır değişir.
    logger.info("Gerçek embeddings adapter'ı henüz yok (#15 bekleniyor) — HashEmbeddings kullanılıyor.")
    return HashEmbeddings()


def _build_radar_service(settings: Settings) -> RadarService:
    return RadarService(
        github_port=_build_github_port(settings),
        judge_port=_build_judge_port(settings),
        embeddings_port=_build_embeddings_port(settings),
        window_days=settings.RADAR_WINDOW_DAYS,
        min_jaccard=settings.RADAR_MIN_JACCARD,
        min_similarity=settings.RADAR_MIN_SIMILARITY,
        default_base=settings.GITHUB_DEFAULT_BRANCH,
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.radar_service = _build_radar_service(app.state.settings)
    # TODO: ScopeService/BoardService gercek DI (Issue #15/#16 disinda, ayri kapsam)
    yield
    # TODO: Kapanışta kaynakları temizle


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    app = FastAPI(
        title="Ensemble",
        version="0.0.1",
        description="AI-çağı ekipleri için paylaşılan proje beyni",
        lifespan=lifespan,
    )
    app.state.settings = settings

    # CORS (#45): açık allowlist — asla "*". Kimlik bilgisi taşınmaz (D-23:
    # cookie/auth yok); kontrattaki tüm endpoint'ler GET.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_credentials=False,
        allow_methods=["GET"],
        allow_headers=["*"],
    )

    # Router'ları bağla
    app.include_router(health.router)
    app.include_router(radar.router)
    app.include_router(scope.router)
    app.include_router(board.router)
    app.include_router(query.router)

    return app

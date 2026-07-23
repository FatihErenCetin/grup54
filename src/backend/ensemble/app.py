import logging
from collections.abc import Callable
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session

from ensemble.api.errors import ERROR_RESPONSES, ErrorEnvelope, register_exception_handlers
from ensemble.api.routers import board, graph, health, query, radar, scope, webhook
from ensemble.config import Settings, get_settings
from ensemble.engine.embeddings import CachedEmbeddings, HashEmbeddings
from ensemble.engine.board import BoardService
from ensemble.engine.graph import GraphService
from ensemble.engine.query import QueryService
from ensemble.engine.radar import RadarService
from ensemble.engine.scope import ScopeService
from ensemble.integrations.gemini.embeddings import GeminiEmbeddingsAdapter
from ensemble.integrations.gemini.fake import FakeJudgeAdapter
from ensemble.integrations.gemini.judge import GeminiJudgeAdapter
from ensemble.integrations.gemini.query_judge import build_query_judge
from ensemble.integrations.gemini.scope_judge import build_scope_judge
from ensemble.integrations.github.adapter import GitHubAdapter
from ensemble.integrations.github.errors import GitHubConfigError
from ensemble.integrations.github.fake import FakeGitHubAdapter
from ensemble.integrations.ollama.adapter import OllamaAdapter
from ensemble.integrations.query_source import HarnessEventQuerySource
from ensemble.ports import EmbeddingsPort, GitHubPort, JudgePort, VectorIndexPort
from ensemble.store.engine import get_engine, get_session_factory
from ensemble.store.vector_store import LocalVectorIndex, build_vector_index
from ensemble_shared.harness import FileHarnessPort

logger = logging.getLogger("ensemble.wiring")


def _build_github_port(settings: Settings) -> GitHubPort:
    # pem dosyası yoksa GitHubAdapter bunu hemen fark etmez (yalnız token
    # yenilenirken okunur) - istek-anı 500'e düşmeden acilis-anı degradasyona
    # ceviriyoruz (Fatih review notu, PR #159).
    if (
        settings.GITHUB_APP_PRIVATE_KEY_PATH
        and not Path(settings.GITHUB_APP_PRIVATE_KEY_PATH).is_file()
    ):
        logger.warning(
            "GITHUB_APP_PRIVATE_KEY_PATH (%s) bulunamadı — FakeGitHubAdapter kullanılıyor.",
            settings.GITHUB_APP_PRIVATE_KEY_PATH,
        )
        return FakeGitHubAdapter()
    try:
        return GitHubAdapter(settings)
    except GitHubConfigError as exc:
        logger.warning(
            "GitHub App yapılandırması eksik (%s) — FakeGitHubAdapter kullanılıyor.", exc
        )
        return FakeGitHubAdapter()


def _build_judge_port(settings: Settings) -> JudgePort:
    if settings.LLM_PROVIDER == "ollama":
        return OllamaAdapter(settings)
    if settings.GEMINI_API_KEY:
        return GeminiJudgeAdapter(settings)
    logger.warning("GEMINI_API_KEY tanımlı değil — FakeJudgeAdapter (kural-tabanlı) kullanılıyor.")
    return FakeJudgeAdapter()


def _build_embeddings_port(settings: Settings) -> EmbeddingsPort:
    if settings.LLM_PROVIDER == "ollama":
        return CachedEmbeddings(OllamaAdapter(settings))
    if settings.GEMINI_API_KEY:
        return CachedEmbeddings(GeminiEmbeddingsAdapter(settings))
    logger.warning("GEMINI_API_KEY tanımlı değil — HashEmbeddings kullanılıyor.")
    return HashEmbeddings()


def _build_radar_service(settings: Settings) -> RadarService:
    return RadarService(
        github_port=_build_github_port(settings),
        judge_port=_build_judge_port(settings),
        embeddings_port=_build_embeddings_port(settings),
        window_days=settings.RADAR_WINDOW_DAYS,
        min_jaccard=settings.RADAR_MIN_JACCARD,
        min_similarity=settings.RADAR_MIN_SIMILARITY,
        backfill_limit=settings.GITHUB_BACKFILL_LIMIT,
        default_base=settings.GITHUB_DEFAULT_BRANCH,
    )


def _build_query_service(
    settings: Settings,
    radar_service: RadarService,
    *,
    session_factory: Callable[[], Session] | None = None,
    vector_index: VectorIndexPort | None = None,
) -> QueryService:
    if session_factory is None and settings.ENSEMBLE_MODE == "local":
        session_factory = get_session_factory(get_engine(settings))
    if vector_index is None:
        if settings.ENSEMBLE_MODE == "local":
            vector_index = build_vector_index(settings)
        else:
            logger.warning("Hosted vector index henüz bağlı değil — local index kullanılıyor.")
            vector_index = LocalVectorIndex()
    source = HarnessEventQuerySource(
        FileHarnessPort(),
        session_factory=session_factory,
        github_owner=settings.GITHUB_REPO_OWNER,
        github_repo=settings.GITHUB_REPO_NAME,
    )
    return QueryService(
        source_port=source,
        embeddings_port=radar_service.embeddings_port,
        vector_index=vector_index,
        judge_port=build_query_judge(settings),
    )


def _build_scope_service(settings: Settings, radar_service: RadarService) -> ScopeService:
    subject_port = (
        radar_service.github_port if isinstance(radar_service.github_port, GitHubAdapter) else None
    )
    return ScopeService(
        harness_port=FileHarnessPort(),
        judge_port=build_scope_judge(settings),
        embeddings_port=radar_service.embeddings_port,
        subject_port=subject_port,
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = app.state.settings
    app.state.radar_service = _build_radar_service(settings)
    # #104 review bulgusu (Semih, blocker): stub session_factory=lambda: None
    # override'sız istekte TypeError veriyordu - store/engine.py'deki gercek
    # engine'e baglandi (radar_service ile ayni desen). Tablolar Alembic'le
    # onceden kurulu varsayilir (make migrate) - burasi sema kurmaz.
    # #62 webhook receiver: Projector'un yazacagi gercek DB session factory,
    # graph_service ile aynisi paylasilir.
    app.state.session_factory = get_session_factory(get_engine(settings))
    app.state.graph_service = GraphService(app.state.session_factory)
    app.state.query_service = _build_query_service(
        settings,
        app.state.radar_service,
        session_factory=app.state.session_factory,
        vector_index=getattr(app.state, "vector_index", None),
    )
    app.state.scope_service = _build_scope_service(settings, app.state.radar_service)
    app.state.board_service = BoardService(session_factory=app.state.session_factory)
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

    # Global hata zarfı (#54): 500+stacktrace yerine tek tip JSON (Ek D)
    register_exception_handlers(app, settings)

    # Router'ları bağla — ERROR_RESPONSES tek kaynaktan yayılır (spec beyanı, #54)
    app.include_router(health.router, responses=ERROR_RESPONSES)
    app.include_router(radar.router, responses=ERROR_RESPONSES)
    app.include_router(scope.router, responses=ERROR_RESPONSES)
    app.include_router(board.router, responses=ERROR_RESPONSES)
    app.include_router(query.router, responses=ERROR_RESPONSES)
    app.include_router(graph.router, responses=ERROR_RESPONSES)
    # #62 hata sözleşmesi: framework HTTPException'ları da Ek D zarfını taşır
    # (errors.py::http_exception) ama bunu ERROR_RESPONSES'a genel eklemedik -
    # 400/401 diğer (GET) router'lara uymuyor. Webhook'a özel bildiriliyor ki
    # üretilen client (#20 zinciri) gerçek hata gövdesini tipleyebilsin
    # (Semih review, #62: openapi 401'i gövdesiz ilan ediyordu).
    _webhook_responses = {
        **ERROR_RESPONSES,
        400: {"model": ErrorEnvelope, "description": "Geçersiz JSON gövdesi"},
        401: {"model": ErrorEnvelope, "description": "Eksik/geçersiz webhook imzası"},
    }
    app.include_router(webhook.router, responses=_webhook_responses)

    return app

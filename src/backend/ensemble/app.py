import logging
from collections.abc import Callable
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session

from ensemble.api.errors import ERROR_RESPONSES, ErrorEnvelope, register_exception_handlers
from ensemble.api.rate_limit import DemoRateLimitMiddleware
from ensemble.api.routers import board, events, graph, health, query, radar, scope, webhook
from ensemble.config import Settings, get_settings
from ensemble.engine.cache import CachedConflictJudge, CachedQueryJudge, CachedScopeJudge
from ensemble.engine.embeddings import CachedEmbeddings, HashEmbeddings
from ensemble.engine.board import BoardService
from ensemble.engine.events import EventService
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
        judge: JudgePort = OllamaAdapter(settings)
    elif settings.GEMINI_API_KEY:
        judge = GeminiJudgeAdapter(settings)
    else:
        logger.warning(
            "GEMINI_API_KEY tanımlı değil — FakeJudgeAdapter (kural-tabanlı) kullanılıyor."
        )
        judge = FakeJudgeAdapter()
    if settings.DEMO_MODE:
        # #63: hosted public demo — Radar'ın 10 sn'lik poll'u aynı çifti
        # yeniden Gemini'ye sormasın (fatura kapağı). local/dev'de DEMO_MODE
        # kapalıyken bu sarmalayıcı hiç devreye girmez.
        judge = CachedConflictJudge(
            judge,
            ttl_s=settings.DEMO_CACHE_TTL_S,
            max_entries=settings.DEMO_CACHE_MAX_ENTRIES,
        )
    return judge


def _build_embeddings_port(settings: Settings) -> EmbeddingsPort:
    # #63: hosted demo modda cache boyutu sınırlanır (serbest metin `q` sınırsız
    # büyümesin — 512 MB Fly VM); local/dev'de max_entries=None (mevcut sınırsız
    # davranış, sıfır regresyon).
    max_entries = settings.DEMO_CACHE_MAX_ENTRIES if settings.DEMO_MODE else None
    if settings.LLM_PROVIDER == "ollama":
        return CachedEmbeddings(OllamaAdapter(settings), max_entries=max_entries)
    if settings.GEMINI_API_KEY:
        return CachedEmbeddings(GeminiEmbeddingsAdapter(settings), max_entries=max_entries)
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
    query_judge_port = build_query_judge(settings)
    if settings.DEMO_MODE:
        # #63: aynı soru+belge çiftini Gemini'ye yeniden sormaz.
        query_judge_port = CachedQueryJudge(
            query_judge_port,
            ttl_s=settings.DEMO_CACHE_TTL_S,
            max_entries=settings.DEMO_CACHE_MAX_ENTRIES,
        )
    return QueryService(
        source_port=source,
        embeddings_port=radar_service.embeddings_port,
        vector_index=vector_index,
        judge_port=query_judge_port,
    )


def _build_scope_service(settings: Settings, radar_service: RadarService) -> ScopeService:
    subject_port = (
        radar_service.github_port if isinstance(radar_service.github_port, GitHubAdapter) else None
    )
    scope_judge_port = build_scope_judge(settings)
    if settings.DEMO_MODE:
        # #63: aynı ref+subject+aday üçlüsünü yeniden yargılamaz.
        scope_judge_port = CachedScopeJudge(
            scope_judge_port,
            ttl_s=settings.DEMO_CACHE_TTL_S,
            max_entries=settings.DEMO_CACHE_MAX_ENTRIES,
        )
    return ScopeService(
        harness_port=FileHarnessPort(),
        judge_port=scope_judge_port,
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
    app.state.event_service = EventService(
        harness_port=FileHarnessPort(),
        github_port=_build_github_port(settings),
    )
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

    # Hosted demo IP/rate cap (#63) — CORS'TAN ÖNCE eklenmeli. Starlette
    # add_middleware'i başa ekler → SON eklenen middleware EN DIŞTA koşar.
    # Bu middleware CORS'tan SONRA eklenseydi, ürettiği 429 cevabı CORS
    # katmanının dışında kalır ve tarayıcı gerçek hatayı "CORS error" diye
    # gizlerdi (#45/#150 dersi — sıra test_demo_rate_limit.py ile kilitli).
    # Yalnız DEMO_MODE=true iken kurulur; local/dev'de hiç devreye girmez.
    if settings.DEMO_MODE:
        app.add_middleware(DemoRateLimitMiddleware, settings=settings)

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
    app.include_router(events.router, responses=ERROR_RESPONSES)
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

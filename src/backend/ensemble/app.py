from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from ensemble.api.errors import ERROR_RESPONSES, register_exception_handlers
from ensemble.api.routers import board, health, query, radar, scope
from ensemble.config import Settings, get_settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    # TODO: Engine servislerini başlat ve app.state'e ekle (Issue #15, #16 vb. geldiğinde)
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

    return app

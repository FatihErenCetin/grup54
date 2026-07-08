from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

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

    # Router'ları bağla
    app.include_router(health.router)
    app.include_router(radar.router)
    app.include_router(scope.router)
    app.include_router(board.router)
    app.include_router(query.router)

    return app

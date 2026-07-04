from contextlib import asynccontextmanager

from fastapi import FastAPI

from ensemble.api.routers import board, health, query, radar, scope


@asynccontextmanager
async def lifespan(app: FastAPI):
    # TODO: Engine servislerini başlat ve app.state'e ekle (Issue #15, #16 vb. geldiğinde)
    yield
    # TODO: Kapanışta kaynakları temizle


def create_app() -> FastAPI:
    app = FastAPI(
        title="Ensemble",
        version="0.0.1",
        description="AI-çağı ekipleri için paylaşılan proje beyni",
        lifespan=lifespan,
    )

    # Router'ları bağla
    app.include_router(health.router)
    app.include_router(radar.router)
    app.include_router(scope.router)
    app.include_router(board.router)
    app.include_router(query.router)

    return app

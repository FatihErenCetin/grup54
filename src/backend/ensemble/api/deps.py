from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.orm import Session, sessionmaker

from ensemble.config import Settings
from ensemble.engine import BoardService, EventService, GraphService, RadarService, ScopeService
from ensemble.engine.query import QueryService


from ensemble.ports import VectorIndexPort


def get_settings(request: Request) -> Settings:
    return request.app.state.settings


def get_session_factory(request: Request) -> sessionmaker[Session]:
    """`/auth/register` + `/auth/login` (T-294) `users` tablosuna yazmak için
    kullanır. `lifespan` (app.py) bunu HER zaman kurar (DEMO_MODE/ENSEMBLE_MODE
    fark etmez) — `get_board_service`'in aksine burada savunmacı bir kurulum-
    zamanı fallback'i YOK, çünkü bu dependency yalnızca gerçek uygulama
    yaşam-döngüsü (TestClient dahil, `with` bloğu) üzerinden çağrılır."""
    return request.app.state.session_factory


def get_radar_service(request: Request) -> RadarService:
    return request.app.state.radar_service


def get_scope_service(request: Request) -> ScopeService:
    return request.app.state.scope_service


def get_query_service(request: Request) -> QueryService:
    return request.app.state.query_service


def get_vector_index(request: Request) -> VectorIndexPort:
    return request.app.state.vector_index


def get_board_service(request: Request) -> BoardService:
    if hasattr(request.app.state, "board_service"):
        return request.app.state.board_service
    session_factory = getattr(request.app.state, "session_factory", None)
    if session_factory is None:
        from ensemble.store.engine import get_engine, get_session_factory
        session_factory = get_session_factory(get_engine(request.app.state.settings))
    return BoardService(session_factory=session_factory)


def get_graph_service(request: Request) -> GraphService:
    # #104 review bulgusu (Semih, blocker): eskiden Board/Scope ile ayni gecici
    # stub'du (session_factory=lambda: None) - override'siz istekte TypeError
    # veriyordu. Gercek DI app.py::lifespan'de kuruluyor (radar_service deseni).
    return request.app.state.graph_service


def get_event_service(request: Request) -> EventService:
    return request.app.state.event_service


# Annotated dependencies
SettingsDep = Annotated[Settings, Depends(get_settings)]
RadarServiceDep = Annotated[RadarService, Depends(get_radar_service)]
ScopeServiceDep = Annotated[ScopeService, Depends(get_scope_service)]
QueryServiceDep = Annotated[QueryService, Depends(get_query_service)]
VectorIndexDep = Annotated[VectorIndexPort, Depends(get_vector_index)]
BoardServiceDep = Annotated[BoardService, Depends(get_board_service)]
GraphServiceDep = Annotated[GraphService, Depends(get_graph_service)]
EventServiceDep = Annotated[EventService, Depends(get_event_service)]
SessionFactoryDep = Annotated[sessionmaker[Session], Depends(get_session_factory)]

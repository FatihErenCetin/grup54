from typing import Annotated

from fastapi import Depends, Request

from ensemble.config import Settings
from ensemble.engine import BoardService, GraphService, RadarService, ScopeService


def get_settings(request: Request) -> Settings:
    return request.app.state.settings


def get_radar_service(request: Request) -> RadarService:
    return request.app.state.radar_service


def get_scope_service(request: Request) -> ScopeService:
    # return request.app.state.scope_service
    return ScopeService(harness_port=None, judge_port=None)  # type: ignore


def get_board_service(request: Request) -> BoardService:
    # return request.app.state.board_service
    # Şimdilik stub, session_factory olarak dummy lambda döndürüyoruz
    return BoardService(session_factory=lambda: None)  # type: ignore


def get_graph_service(request: Request) -> GraphService:
    # #104 review bulgusu (Semih, blocker): eskiden Board/Scope ile ayni gecici
    # stub'du (session_factory=lambda: None) - override'siz istekte TypeError
    # veriyordu. Gercek DI app.py::lifespan'de kuruluyor (radar_service deseni).
    return request.app.state.graph_service


# Annotated dependencies
SettingsDep = Annotated[Settings, Depends(get_settings)]
RadarServiceDep = Annotated[RadarService, Depends(get_radar_service)]
ScopeServiceDep = Annotated[ScopeService, Depends(get_scope_service)]
BoardServiceDep = Annotated[BoardService, Depends(get_board_service)]
GraphServiceDep = Annotated[GraphService, Depends(get_graph_service)]

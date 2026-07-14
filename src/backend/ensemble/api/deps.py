from typing import Annotated

from fastapi import Depends, Request

from ensemble.config import Settings
from ensemble.engine import BoardService, RadarService, ScopeService


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


# Annotated dependencies
SettingsDep = Annotated[Settings, Depends(get_settings)]
RadarServiceDep = Annotated[RadarService, Depends(get_radar_service)]
ScopeServiceDep = Annotated[ScopeService, Depends(get_scope_service)]
BoardServiceDep = Annotated[BoardService, Depends(get_board_service)]

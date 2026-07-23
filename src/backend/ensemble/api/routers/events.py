"""Events/Presence endpoint'i — bayat filtreli (#60)."""

from datetime import datetime

from fastapi import APIRouter
from pydantic import BaseModel

from ensemble.api.deps import EventServiceDep
from ensemble.models import PresenceEntry


class PresenceResponse(BaseModel):
    """GET /presence yanıt modeli."""

    entries: list[PresenceEntry]
    latest_ts: datetime


router = APIRouter(tags=["events"])


@router.get("/presence", response_model=PresenceResponse)
def get_presence(service: EventServiceDep) -> PresenceResponse:
    """Aktif çalışan beyanlarını döndürür; bayat kayıtlar read-time'da elenir (#60)."""
    entries, latest_ts = service.get_presence()
    return PresenceResponse(entries=entries, latest_ts=latest_ts)

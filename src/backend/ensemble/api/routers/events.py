"""Events/Presence endpoint'i — bayat filtreli (#60) + artımlı feed cursor (#52)."""

from datetime import datetime

from fastapi import APIRouter, Header, Query, Response
from pydantic import BaseModel

from ensemble.api.deps import EventServiceDep
from ensemble.models import NormalizedEvent, PresenceEntry


class PresenceResponse(BaseModel):
    """GET /presence yanıt modeli."""

    entries: list[PresenceEntry]
    latest_ts: datetime


class EventsResponse(BaseModel):
    """GET /events yanıt modeli.

    latest_ts, bir sonraki poll'de `since` sorgu parametresi olarak geri
    gönderilecek cursor değeridir (#52).
    """

    events: list[NormalizedEvent]
    latest_ts: datetime


router = APIRouter(tags=["events"])



@router.get("/presence", response_model=PresenceResponse)
def get_presence(service: EventServiceDep) -> PresenceResponse:
    """Aktif çalışan beyanlarını döndürür; bayat kayıtlar read-time'da elenir (#60)."""
    entries, latest_ts = service.get_presence()
    return PresenceResponse(entries=entries, latest_ts=latest_ts)


@router.get("/events", response_model=EventsResponse)
def get_events(
    service: EventServiceDep,
    response: Response,
    since: datetime | None = Query(
        default=None,
        description="Artımlı polling cursor. Verilirse yalnız bu andan (dahil) sonraki eventler döner.",
    ),
    if_none_match: str | None = Header(default=None),
):
    """GitHub event akışını cursor'lı döndürür (#52).

    - `since`: bir önceki yanıtın `latest_ts`'i; payload'ı yeni eventlerle sınırlar.
    - `If-None-Match`: bir önceki ETag; içerik değişmediyse gövde yerine 304 döner.
    """
    events, latest_ts, etag = service.get_events(since=since)

    if if_none_match is not None and if_none_match == etag:
        return Response(status_code=304, headers={"ETag": etag})
        
    if if_none_match is not None and if_none_match != etag:
        # Cache is invalid (late event arrived). Force full feed to catch missed events.
        events, latest_ts, etag = service.get_events(since=None)

    response.headers["ETag"] = etag
    return EventsResponse(events=events, latest_ts=latest_ts)

"""HTTP response zarflari — kontrat §3'un (docs/sprint2-kontratlar.md) FastAPI beyani.

Cekirdek modeller (Detection, BoardCard, ...) ensemble.models'ta yasar; burasi
yalnizca endpoint-cikti zarflaridir. Beyanin amaci: openapi.json bu semalari
tasisin ki frontend'in uretilen TS client'i (#20) tip-guvenli olsun. Sekiller
§3 ile birebir — burada imza DEGISTIRILMEZ (kontrat degisikligi = §3'e PR +
daily duyurusu).
"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel

from ensemble.models import BoardCard, Detection


class HealthResponse(BaseModel):
    status: Literal["ok"]
    mode: Literal["local", "hosted"]


class RadarResponse(BaseModel):
    detections: list[Detection]
    updated_at: datetime


class BoardResponse(BaseModel):
    cards: list[BoardCard]


class QueryResponse(BaseModel):
    answer: str
    citations: list[str]

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
    # #53: gercekten kurulu mu (Fake* adaptere dusmemis mi) - Fly health-check
    # + local-first "token/key ayarli mi?" onboarding sinyali. Canli ag cagrisi
    # YOK (Fly health-check flaky olmasin) - yalniz acilis-anindaki wiring sonucu.
    github_auth: Literal["ok", "degraded"]
    gemini: Literal["ok", "degraded"]


class RadarResponse(BaseModel):
    detections: list[Detection]
    updated_at: datetime


class BoardResponse(BaseModel):
    cards: list[BoardCard]


class QueryResponse(BaseModel):
    answer: str
    citations: list[str]

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

from ensemble.models import BoardCard, Detection, QueryResult, ScopeVerdict


class HealthResponse(BaseModel):
    status: Literal["ok"]
    mode: Literal["local", "hosted"]
    # #53: acilis-anindaki WIRING sonucu — Fake* adaptere degil gercek
    # adapter sinifina mi dusuldu (Fly health-check + local-first "token/key
    # ayarli mi?" sinyali). Canli ag cagrisi YOK (Fly health-check flaky
    # olmasin). "configured" = gercek kimlik bilgisi SET EDILMIS ve adapter
    # kuruldu — GECERLI/DOGRULANMIS anlamina GELMEZ (review bulgusu, Semih:
    # gecersiz PEM/anahtarla da adapter kurulur, ilk gercek API cagrisinda
    # patlar). Canli dogrulama icin: #58/spot-check (kalibrasyon-raporu §4).
    github_auth: Literal["configured", "missing"]
    gemini: Literal["configured", "missing"]


class RadarResponse(BaseModel):
    detections: list[Detection]
    updated_at: datetime


class BoardResponse(BaseModel):
    cards: list[BoardCard]


class QueryResponse(QueryResult):
    pass


class ScopeVerdictCounts(BaseModel):
    in_scope: int
    drift: int
    non_goal_violation: int


class ScopeVerdictsResponse(BaseModel):
    verdicts: list[ScopeVerdict]
    counts: ScopeVerdictCounts
    judged_at: datetime | None

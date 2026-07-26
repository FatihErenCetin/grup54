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


class RadarDegraded(BaseModel):
    """Bu turda judge'ın DEĞERLENDİREMEDİĞİ çiftler (#252).

    Varlığı "sonuç eksik" demektir: `detections` listesi o turda gerçekten
    yargılanabilmiş çiftleri taşır, `judge_unavailable` kadarı ise hiç
    yargılanamamıştır — çakışma olmadığı için değil, judge'a ulaşılamadığı için.
    İstemci bunu tespit gibi göstermemeli, "sonuç eksik" uyarısı olarak
    göstermelidir.
    """

    judge_unavailable: int
    evaluated: int


class RadarResponse(BaseModel):
    detections: list[Detection]
    updated_at: datetime
    # Mutlu yolda `null` — istemci `if (data.degraded)` ile tek kontrolle ayırır.
    degraded: RadarDegraded | None = None


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

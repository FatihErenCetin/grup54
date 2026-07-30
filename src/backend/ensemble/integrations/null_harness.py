"""Dürüst-boş `HarnessPort` (T-79, çok-kiracılık).

`.harness/` yerel diskte yaşayan, TEK repoya ait bir dizindir (bkz.
`ensemble_shared.harness.FileHarnessPort`) — çok-kiracılı bir dağıtımda
kullanıcının izlediği ARBİTRER bir repo için bu dizin diskte YOKTUR (biz o
reponun git ağacını klonlamıyoruz). Brifingin kuralı: "scope ve presence
.harness/ dosyalarını yerel diskten okuyor... kiracı repoları için o
dosyalar bizde YOK. Dürüst boş/yapılandırılmamış durum dön — sahte veri ya
da demo reponun verisi DÖNDÜRME."

Bu sınıf tam olarak bunu yapar: `read_scope` `HarnessError` fırlatır
(`ScopeService`/`HarnessEventQuerySource` bunu zaten YAKALAYIP "unavailable"/
boş belge listesine çeviriyor — bkz. o sınıfların docstring'leri), `read_tasks`/
`read_active` BOŞ liste döner (çağıranların çoğu — Projector, GraphService,
HarnessEventQuerySource — bunları try/except OLMADAN doğrudan tüketiyor;
`[]` "hiç açık task/aktif beyan yok" ile ayırt edilemez MEŞRU bir durumdur,
tıpkı `FileHarnessPort._read_many`'nin "dizin yok" durumunda yaptığı gibi).

Yazma metodları (`write_*`) çağrılmamalı — bu port yalnız OKUMA yollarına
(radar/board/scope/query/graph/events) enjekte edilir; çağrılırsa
`HarnessError` fırlatır (sessiz no-op yerine gürültülü hata — bir yazma
denemesi buraya kadar gelirse bu, TenantRegistry'nin yanlış port'u yanlış
yere taktığının işaretidir, susturulmamalı).
"""

from __future__ import annotations

from typing import Any

from ensemble_shared.harness import HarnessError


class NullHarnessPort:
    """`HarnessPort` protokolüyle yapısal olarak uyumlu, hiçbir şey OKUMAYAN/
    YAZMAYAN adaptör — non-demo kiracılar için `.harness/`'in YOKLUĞUNU temsil
    eder."""

    def read_scope(self, sprint: str) -> dict[str, Any]:
        raise HarnessError(
            "bu kiracı için .harness/scope/ yapılandırılmamış (çok-kiracılı repo, T-79)"
        )

    def read_tasks(self) -> list[dict[str, Any]]:
        return []

    def read_active(self) -> list[dict[str, Any]]:
        return []

    def read_decisions(self) -> list[dict[str, Any]]:
        # `read_tasks`/`read_active` ile AYNI kural: non-demo kiracının
        # `.harness/`'i yok, ama bu bir HATA değil bir YOKLUK — dürüst-boş
        # döner. (Fırlatsaydı Ask o kiracıda tamamen çökerdi.)
        return []

    def verify_dir_readable(self, folder: str) -> None:
        raise HarnessError(
            f"bu kiracı için .harness/{folder}/ yapılandırılmamış (çok-kiracılı repo, T-79)"
        )

    def write_active(self, handle: str, decl: dict[str, Any]) -> None:
        raise HarnessError("NullHarnessPort yazma desteklemez (T-79 — yalnız okuma yollarına enjekte edilir)")

    def write_task(self, task_id: str, decl: dict[str, Any]) -> None:
        raise HarnessError("NullHarnessPort yazma desteklemez (T-79 — yalnız okuma yollarına enjekte edilir)")

    def write_scope(self, sprint: str, decl: dict[str, Any]) -> None:
        raise HarnessError("NullHarnessPort yazma desteklemez (T-79 — yalnız okuma yollarına enjekte edilir)")

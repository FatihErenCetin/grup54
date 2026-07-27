"""Kalıcı judge yargı deposu (#259, GÖREV 1/2) — `CachedConflictJudge`
(bellek, TTL'li) MISS verdiğinde bir sonraki katmanın (`PersistentJudge`,
GÖREV 2/2) baktığı ikinci katman. Konteyner yeniden yaratıldığında (CD,
#236) bellek katmanı sıfırlanır ama bu depo KALICIDIR — aynı çift için
Gemini/Groq'a ikinci kez ödenmez.

Bu modül YALNIZCA DB okuma/yazma sınırını taşır — ne judge sarmalama
sırasını (`CachedConflictJudge → PersistentJudge → FallbackJudge`) ne de
`cache_key`'in NASIL hesaplandığını bilir. `cache_key`, `engine/cache.py::
_digest` ile aynı içerik-adresli anahtardır ve `model`i de İÇERMELİDİR
(çağıranın sorumluluğu, bkz. `ensemble.store.models.JudgeVerdictRow`
docstring'i) — farklı bir model aynı çifti yargılarsa farklı bir
`cache_key` üretilmeli, eski satırın üzerine sessizce yazılmamalıdır.

MUTLAK KURAL (#252 sözleşmesi): `JudgeUnavailableError` bu modülden ASLA
geçmez. Hata bir sonuç DEĞİLDİR — bu modül yalnızca GERÇEK `Detection`
nesnelerini okur/yazar. Çağıran (`PersistentJudge`) alt portu çağırırken
`JudgeUnavailableError` alırsa bu modülü hiç ÇAĞIRMAMALIDIR (`put_verdict`
yalnızca GERÇEK bir yargı elde edildiğinde çağrılır).

DB yazımı judge yolunu BLOKLAMAZ/BOZMAZ ilkesi bu modülün DIŞINDA uygulanır
— `put_verdict` kendi hatasını YUTMAZ, olduğu gibi çağırana (`PersistentJudge`)
yayar; "DB'ye yazamadım ama yargı yine de dönsün, sessizce" kararını burada
DEĞİL, orada (görünür log/sayaç ile) vermek gerekir — aksi halde bu, repodaki
altıncı fail-open olurdu.
"""

from __future__ import annotations

import logging

from pydantic import ValidationError
from sqlalchemy.orm import Session

from ensemble.models import Detection
from ensemble.store.models import JudgeVerdictRow

logger = logging.getLogger("ensemble.store.verdict")


def get_verdict(session: Session, cache_key: str) -> Detection | None:
    """Kalıcı depoda `cache_key` için saklı bir yargı var mı bak.

    Satır yoksa `None` döner — gerçek MISS, üst katman (`PersistentJudge`)
    alt porta gitmelidir.

    Satır VAR ama `detection` JSON'ı artık `Detection` şemasına
    UYMUYORSA (örn. `Detection` modeli zamanla genişledi/daraldı, eski
    satır bayat şemalı kaldı) sessizce `None` DÖNER — bu MEŞRU bir geçiş
    yoludur (yargı yeniden hesaplanır; aynı `cache_key` ile `put_verdict`
    sonradan bu satırın üzerine güncel şemayla yazar). Ama TAMAMEN
    sessiz değildir: bayat şema log'lanır ki geçiş görünür kalsın (bu bir
    fail-open değil — dönen değer zaten dürüstçe `None`, sahte bir
    Detection değil).
    """
    row = session.get(JudgeVerdictRow, cache_key)
    if row is None:
        return None
    try:
        return Detection.model_validate(row.detection)
    except ValidationError:
        logger.warning(
            "judge_verdicts satırı bozuk/eski şemalı (cache_key=%s, model=%s) — "
            "None dönülüyor, yargı yeniden hesaplanacak.",
            cache_key,
            row.model,
        )
        return None


def put_verdict(session: Session, cache_key: str, model: str, detection: Detection) -> None:
    """`cache_key` için yargıyı kalıcı depoya yaz (idempotent upsert).

    Satır zaten varsa (aynı `cache_key` ikinci kez yazılırsa — örn. eş
    zamanlı iki istek aynı MISS'i alt porta gönderdi) satır ÇOĞALMAZ,
    `model`/`detection` üzerine yazılır (PK zaten `cache_key`).

    Bu fonksiyon `session.commit()` ÇAĞIRMAZ — session'ın sahibi
    (çağıran) commit eder. `session.flush()` ile satır anında görünür
    olur ama işlem yalnızca çağıranın commit'iyle kalıcılaşır.

    Bu fonksiyon patlarsa (örn. DB bağlantısı koptu) istisna olduğu gibi
    ÇAĞIRANA yayılır — burada yutulmaz, sessiz bir varsayılan
    döndürülmez (repodaki mevcut beş fail-open'a altıncısını eklememek
    için). Judge yolunun DB yazım hatasında da yargıyı döndürmeye devam
    etmesi (fail-open OLMADAN, çünkü döndürülen gerçek bir yargı) bu
    fonksiyonun DEĞİL, çağıranın (`PersistentJudge`) sorumluluğudur.
    """
    row = session.get(JudgeVerdictRow, cache_key)
    detection_json = detection.model_dump(mode="json")
    if row is None:
        session.add(
            JudgeVerdictRow(
                cache_key=cache_key,
                model=model,
                detection=detection_json,
            )
        )
    else:
        row.model = model
        row.detection = detection_json
    session.flush()

"""Kalıcı judge yargı katmanı (#259, GÖREV 2/2) — `CachedConflictJudge`
(bellek, TTL'li) ile `FallbackJudge` (Gemini→Groq) ARASINA giren ikinci
katman:

    CachedConflictJudge (bellek, hızlı, TTL'li)
        └─ PersistentJudge (DB, kalıcı)              <-- BU MODÜL
             └─ FallbackJudge (Gemini → Groq)

Ölçülen sorun: bir soğuk `/radar` ~91 aday × ~600 token ≈ 55.000 token —
Groq'un günlük 100.000 token bütçesinin yarısı. Bellek katmanı (`TtlLruCache`)
konteyner her yeniden yaratıldığında (CD, #236) SIFIRLANIR ve tüm yargılar
tekrar ödenir. Bu modülün arkasındaki `judge_verdicts` tablosu KALICIDIR —
aynı çift için ikinci kez Gemini/Groq'a gidilmez.

Neden `engine/` altında, `store/` altında değil: bu sınıf hiçbir DB şemasını
tanımaz, yalnızca `JudgePort` sözleşmesini + `ensemble.store.verdict_store`
arayüzünü (`get_verdict`/`put_verdict`) bilir — DB okuma/yazma sınırının
KENDİSİ o modülde yaşar (GÖREV 1/2, paralel yazıldı). Burası yalnızca
sarmalama/kompozisyon mantığını taşır — `engine/fallback.py::FallbackJudge`
ile AYNI "port'u saran, port döndüren dekoratör" desenidir (bkz. o modülün
docstring'i — üslup kaynağı).

`cache_key` üretimi: `engine/cache.py::_digest` KULLANILIR (yeniden
YAZILMAZ) — `CachedConflictJudge.judge_conflict`'in kullandığı AYNI
a/b/overlap/sim alanları + `model` (çağıranın kimlik etiketi, bkz.
`app.py::_build_judge_port::model_identity`). `model`in anahtara katılması
ŞART: farklı model farklı yargı üretir; model değişince (örn. GEMINI_MODEL
yükseltilince ya da Groq yedeği eklenip/çıkarılınca) eski satırlar yeni
sorgularla ASLA eşleşmez — silinmez, zararsızca (ve sessizce) terk edilirler.

MUTLAK KURAL 1 (#252 sözleşmesi): `JudgeUnavailableError` bu katmandan
HİÇBİR ŞEKİLDE kalıcılaştırılmaz. Hata bir sonuç DEĞİLDİR — yarın kota
dönünce taze yargı sorulmalı. `inner.judge_conflict()` bunu fırlatırsa
`put_verdict` hiç ÇAĞRILMAZ, istisna olduğu gibi çağırana yayılır (bu
fonksiyon onu try/except içine hiç ALMAZ — yalnızca DB YAZIMI etrafında bir
sınır vardır, judge çağrısının etrafında değil).

MUTLAK KURAL 2: DB yazımı judge yolunu BLOKLAMAZ/BOZMAZ. `put_verdict`/
`session.commit()` patlarsa (ör. bağlantı koptu) yalnız LOG'LANIR (+ görünür
sayaç) ve GERÇEK yargı (`inner`'ın ürettiği) yine de döndürülür. Bu bir
fail-open DEĞİLDİR — dönen değer sahte bir varsayılan değil, gerçekten
üretilmiş bir `Detection`; yalnızca onu kalıcılaştıramadık. Repodaki mevcut
beş fail-open'a (try/except içinde sessiz varsayılan · "yazamadım ama
başarılı raporladım" sayacı · eksik yapılandırmada sessiz atlama) altıncısını
EKLEMEMEK için sessiz DEĞİLDİR: `write_failures` sayacı + `logger.exception`.

MUTLAK KURAL 3: `session_factory` `None` ise sarmalayıcı HİÇ KURULMAMIŞ gibi
davranır — `inner`'a doğrudan delege eder, DB'ye hiç dokunmaz. Bu, `app.py`
wiring'inin zaten bu durumda katmanı hiç kurmaması gereken bir savunma
sınırıdır (ENSEMBLE_MODE=local'de bu katman devreye girmemeli) — ama
`PersistentJudge`'ın kendisi de bunu varsaymaz, kontrol eder.
"""

from __future__ import annotations

import logging
from collections.abc import Callable

from sqlalchemy.orm import Session

from ensemble.engine.cache import _digest
from ensemble.models import Detection, NormalizedEvent
from ensemble.ports import JudgePort
from ensemble.store.verdict_store import get_verdict, put_verdict

logger = logging.getLogger("ensemble.judge.persistence")


class PersistentJudge:
    """`JudgePort` sarmalayıcısı: bellek cache MISS verince kalıcı depoya
    (`judge_verdicts`) bakar; orada da yoksa `inner`'a gider ve dönen sonucu
    depoya yazar.

    `model`, çağıranın (bkz. `app.py::_build_judge_port`) bu judge zincirinin
    KONFİGÜRASYONUNA verdiği sabit bir kimlik etiketidir (örn.
    "gemini:gemini-2.5-flash+groq:llama-3.3-70b-versatile") — HANGİ alt
    sağlayıcının (birincil mi yedek mi) belirli bir çağrıyı yanıtladığını
    AYIRT ETMEZ; tıpkı `CachedConflictJudge(FallbackJudge(...))`'un bellek
    katmanının da bunu ayırt etmemesi gibi (bkz. o sarmanın gerekçesi,
    `app.py`). Zincirin konfigürasyonu değişince (model yükseltme, yedek
    ekleme/çıkarma) etiket değişir ve eski satırlar doğal olarak bayatlar.
    """

    def __init__(
        self,
        inner: JudgePort,
        *,
        session_factory: Callable[[], Session] | None,
        model: str,
    ) -> None:
        self.inner = inner
        self.session_factory = session_factory
        self.model = model
        # Gözlenebilirlik: DB yazımı sessizce başarısız olmasın diye (bkz.
        # modül docstring'i, MUTLAK KURAL 2). `TtlLruCache.hits`/`misses` ile
        # aynı disiplin — basit bir sayaç, ekstra bağımlılık yok.
        self.write_failures = 0

    def judge_conflict(
        self, a: NormalizedEvent, b: NormalizedEvent, overlap: list[str], sim: float | None
    ) -> Detection:
        if self.session_factory is None:
            # Kurulmamış gibi davran (MUTLAK KURAL 3) — normalde app.py
            # wiring'i bu durumda katmanı hiç kurmamalı; bu yalnız savunmacı
            # bir sınırdır.
            return self.inner.judge_conflict(a, b, overlap, sim)

        cache_key = _digest(
            {
                "a": a.model_dump(mode="json"),
                "b": b.model_dump(mode="json"),
                "overlap": sorted(overlap),
                "sim": sim,
                "model": self.model,
            }
        )

        with self.session_factory() as session:
            stored = get_verdict(session, cache_key)
        if stored is not None:
            return stored

        # DB MISS -> alt porta git. `inner.judge_conflict` burada try/except
        # DIŞINDA çağrılır: JudgeUnavailableError (ya da başka bir istisna)
        # olduğu gibi YUKARI YAYILIR (#252, MUTLAK KURAL 1) — hiçbir şey
        # yazılmaz, DB'ye HİÇ dokunulmaz.
        detection = self.inner.judge_conflict(a, b, overlap, sim)

        # Yalnızca DB YAZIMI etrafında bir sınır var — GERÇEK yargı elde
        # edildikten SONRA. Bu try/except judge çağrısını KAPSAMAZ.
        try:
            with self.session_factory() as session:
                put_verdict(session, cache_key, self.model, detection)
                session.commit()
        except Exception:
            # MUTLAK KURAL 2: DB yazımı judge yolunu bozmaz — gerçek yargı
            # yine de döner. Ama SESSİZ değil: log + sayaç görünür kalır.
            self.write_failures += 1
            logger.exception(
                "judge_verdicts yazımı başarısız (cache_key=%s, model=%s) — "
                "yargı yine de döndürülüyor, kalıcılaştırılamadı "
                "(write_failures=%d).",
                cache_key,
                self.model,
                self.write_failures,
            )

        return detection

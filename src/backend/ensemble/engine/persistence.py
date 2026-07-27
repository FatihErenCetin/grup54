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

MUTLAK KURAL 4 (#264, Semih blocker A — PR #264 review'da bulundu): DB
OKUMA hatası da YAZMA hatasıyla AYNI muameleyi görür. Eskiden yalnızca
`put_verdict`/`session.commit()` (yazma) try/except İÇİNDEYDİ; `get_verdict`
(okuma) YALIN çağrılıyordu — DB düşerse (bağlantı kopması, tablo yok,
kilitlenme) istisna YUKARI YAYILIR ve TÜM `/radar` isteği patlardı, oysa
`inner` (asıl judge) hâlâ ÇALIŞIYOR olabilirdi. Asimetri: yazma hatası
zararsızdı, okuma hatası ÖLÜMCÜLDÜ — ikisi de "cache yok" anlamına
gelmeliydi. Düzeltme: okuma da bir try/except'e alınır, hata halinde
`stored = None` ile devam edilir (yani MISS gibi davranılıp `inner`'a
düşülür).

Bu bir FAIL-SAFE'tir, fail-OPEN DEĞİLDİR — ayrım burada AÇIKÇA yazılı
olsun (repoda son iki günde ALTI fail-open bulundu, yedincisi bu OLMASIN):
dönen değer `inner`'ın GERÇEKTEN ürettiği bir `Detection`'dır, sahte/icat
edilmiş bir varsayılan DEĞİLDİR. Fail-open olsaydı, hatayı "cache boş" ile
AYIRT EDİLEMEZ bir değere (örn. sessizce sabit bir Detection uydurup HIT'miş
gibi davranmak, ya da hatayı yutup hiç loglamadan devam etmek) çökertirdik.
Burada tam tersi olur: DB'ye hiç ULAŞILAMADIĞI için MISS'e düşülür ve
GERÇEK bir hesaplama (`inner.judge_conflict`) tetiklenir — "yokluk" ile
"hata" birbirine karışmaz, çünkü ikisi de dürüstçe aynı sonuca (MISS →
gerçek yargı) götürür. Ayrıca SESSİZ değildir: `read_failures` sayacı +
`logger.exception` — repodaki mevcut altı fail-open'a yedincisini
EKLEMEMEK için.

MUTLAK KURAL 5 (#264, Semih blocker B): kalıcı katmanda TTL. `created_at`
sütunu VARDI ama hiçbir okuma yolu KULLANMIYORDU — DB'deki bir yargı
sonsuza kadar servis edilirdi. `cache_key` a/b/overlap/sim/model'den
üretilir ama PROMPT'un KENDİSİ (`gemini/judge.py::_build_prompt`) anahtara
KATILMAZ — rubrik değişince (örn. severity eşiği kalibre edilince) eski
satırlar farklı bir rubrikle üretilmiş olsa da aynı anahtarla SONSUZA dek
eşleşmeye devam ederdi. `ttl_days` (gerçek değer `app.py` wiring'inde
`Settings.VERDICT_TTL_DAYS`'ten geçirilir, varsayılan gerekçesi orada
yazılı) `get_verdict`'e geçirilir; süresi dolmuş satır MEŞRU bir MISS
sayılır (silinmez, `store/verdict_store.py::get_verdict` docstring'inde
gerekçesi var) ve `inner`'a yeniden gidilir; `put_verdict` satırı taze
`created_at` ile ÜZERİNE yazar (bkz. o fonksiyonun docstring'i — aksi
halde satır bir kez süresi dolunca sonsuza dek MISS kalırdı).
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

# Engine katmanı `ensemble.config`'e BAĞIMLI KALMAZ (bkz. `engine/cache.py`
# içindeki AYNI disiplin, `_SINGLE_FLIGHT_WAIT_S` yorumu) — bu yalnızca bir
# GÜVENLİK AĞI varsayılanıdır (constructor'a `ttl_days` hiç verilmeden
# doğrudan kullanıldığında, ör. testler). GERÇEK değer HER ZAMAN `app.py`
# wiring'inde `Settings.VERDICT_TTL_DAYS`'ten AÇIKÇA geçirilir (#264) —
# iki yerde AYNI sayı görünmesi bilinçli (config.py'deki gerekçe kanonik).
_DEFAULT_TTL_DAYS = 7.0


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

    `ttl_days` (#264, MUTLAK KURAL 5): satırın kaç gün "geçerli" sayılacağı;
    gerçek değer `app.py`'de `Settings.VERDICT_TTL_DAYS`'ten geçirilir.
    `read_failures`/`write_failures`: DB okuma/yazma hatalarının GÖRÜNÜR
    sayaçları (MUTLAK KURAL 2 ve 4) — ikisi de fail-SAFE'i belgeler, sessiz
    bir fail-open'ı DEĞİL.
    """

    def __init__(
        self,
        inner: JudgePort,
        *,
        session_factory: Callable[[], Session] | None,
        model: str,
        ttl_days: float = _DEFAULT_TTL_DAYS,
    ) -> None:
        self.inner = inner
        self.session_factory = session_factory
        self.model = model
        self.ttl_days = ttl_days
        # Gözlenebilirlik: DB yazımı sessizce başarısız olmasın diye (bkz.
        # modül docstring'i, MUTLAK KURAL 2). `TtlLruCache.hits`/`misses` ile
        # aynı disiplin — basit bir sayaç, ekstra bağımlılık yok.
        self.write_failures = 0
        # MUTLAK KURAL 4: okuma da aynı gözlenebilirlik disiplinini alır —
        # okuma hatası sessizce yutulmasın diye ayrı bir sayaç (yazma/okuma
        # hangi tarafın patladığını karıştırmadan ayırt edebilmek için
        # `write_failures` ile BİRLEŞTİRİLMEZ).
        self.read_failures = 0

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

        try:
            with self.session_factory() as session:
                stored = get_verdict(session, cache_key, ttl_days=self.ttl_days)
        except Exception:
            # MUTLAK KURAL 4: DB OKUMA hatası da yazma hatasıyla AYNI
            # muameleyi görür — MISS gibi davranılıp `inner`'a düşülür.
            #
            # FAIL-SAFE (bu), fail-OPEN (bu DEĞİL) ayrımı: `stored = None`
            # atandıktan sonra aşağıda `inner.judge_conflict()` GERÇEKTEN
            # çağrılacak ve dönen değer o çağrının ÜRETTİĞİ gerçek bir
            # `Detection` olacak — sahte/icat edilmiş bir varsayılan DEĞİL.
            # Sessiz de değil: `read_failures` sayacı + `logger.exception`
            # (repodaki mevcut altı fail-open'a yedincisini eklememek için).
            stored = None
            self.read_failures += 1
            logger.exception(
                "judge_verdicts okuması başarısız (cache_key=%s, model=%s) — "
                "MISS sayılıyor, inner'a gidiliyor (read_failures=%d).",
                cache_key,
                self.model,
                self.read_failures,
            )
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

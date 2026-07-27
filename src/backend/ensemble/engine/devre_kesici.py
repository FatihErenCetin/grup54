"""Devre kesici (#288) — tükenmiş bir sağlayıcıyı yüzlerce kez daha deneme.

Neden `engine/` altında: `FallbackJudge`/`CachedConflictJudge` ile aynı desen —
hiçbir sağlayıcıyı tanımaz, yalnızca `JudgePort` sözleşmesini bilir.

Ölçülen sorun (canlı, 2026-07-27)
---------------------------------
Gemini ücretsiz katmanı `generate_content` için **günde 20 istek** veriyor.
Tükendikten sonra `/radar` her adayı yine deniyordu:

    3 dakikada 392 kota hatası   (günde 20 veren uca dakikada ~130 istek)
    /radar                        35 saniye
    sonuç                         "iki sağlayıcı da değerlendiremedi"

Yani 35 saniye harcanıp EN BAŞTAN belli olan cevap veriliyordu. Kota günlük
olduğu için ilk birkaç hatadan sonra sonucun değişme ihtimali YOK.

Ne yapar
--------
Arka arkaya `esik` kadar `JudgeUnavailableError` görürse devreyi AÇAR ve
`soguma_s` boyunca sağlayıcıya HİÇ gitmeden aynı hatayı fırlatır. Süre
dolunca bir deneme yapar (yarı-açık): başarılıysa devre kapanır, değilse
soğuma yeniden başlar.

Ne YAPMAZ (bilinçli)
--------------------
Yargı UYDURMAZ. Devre açıkken de `JudgeUnavailableError` fırlatır — "çakışma
yok" demez. Bu ayrım bu repoda pahalıya öğrenildi: `JudgeUnavailableError`
docstring'i "bu çift çakışma DEĞİL" ile "bu çifti değerlendiremedik" farkını
anlatır. Devre kesici hızlandırır, susturmaz.

Ayrıca kalıcı DEĞİLDİR: süreç yeniden başlayınca devre kapalı başlar. Kota
penceresi süreçten bağımsız açılır; kalıcı bir "kapalı" durumu, kota geri
geldiğinde bizi gereksiz yere kör bırakırdı.
"""

import logging
import threading
import time

from ensemble.models import Detection, NormalizedEvent
from ensemble.ports import JudgePort, JudgeUnavailableError

logger = logging.getLogger("ensemble.judge.devre")

# Kaç ardışık başarısızlıktan sonra devre açılır. 3: tek bir geçici ağ
# hıçkırığı devreyi açmasın, ama gerçek bir kota duvarında da uzun
# sürmesin (radar 8 eşzamanlı judge koşturuyor).
VARSAYILAN_ESIK = 3
# Devre açık kalma süresi. Gemini'nin GÜNLÜK kotasında 60 sn kısa görünebilir
# ama amaç kotayı beklemek değil: her istekte bir kez yoklayıp gerisini
# ucuza kesmek. Kota geri geldiğinde en fazla 60 sn geç fark ederiz.
VARSAYILAN_SOGUMA_S = 60.0


class DevreKesiciJudge:
    """`JudgePort` sarmalayıcısı: tükenmiş sağlayıcıya gitmeyi keser."""

    def __init__(
        self,
        inner: JudgePort,
        *,
        esik: int = VARSAYILAN_ESIK,
        soguma_s: float = VARSAYILAN_SOGUMA_S,
        saat=time.monotonic,
    ) -> None:
        if esik < 1:
            raise ValueError("esik en az 1 olmali")
        self.inner = inner
        self._esik = esik
        self._soguma_s = soguma_s
        self._saat = saat
        # Radar judge'ları thread havuzunda koşuyor (RADAR_JUDGE_CONCURRENCY);
        # sayaç ve zaman damgası paylaşımlı durum -> kilit şart.
        self._kilit = threading.Lock()
        self._ardisik_hata = 0
        self._acilma_ani: float | None = None
        # Teşhis: kaç çağrı sağlayıcıya HİÇ gitmeden kesildi.
        self.kesilen = 0

    def _devre_acik_mi(self) -> bool:
        if self._acilma_ani is None:
            return False
        if self._saat() - self._acilma_ani >= self._soguma_s:
            # Yarı-açık: bir deneme hakkı ver. Sayaç sıfırlanmaz — deneme
            # başarısız olursa hemen yeniden açılsın istiyoruz.
            self._acilma_ani = None
            logger.info("judge devresi yarı-açık: bir deneme yapılacak")
            return False
        return True

    def judge_conflict(
        self, a: NormalizedEvent, b: NormalizedEvent, overlap: list[str], sim: float | None
    ) -> Detection:
        with self._kilit:
            if self._devre_acik_mi():
                self.kesilen += 1
                raise JudgeUnavailableError(
                    f"judge devresi AÇIK: son {self._esik} çağrı üst üste başarısız oldu, "
                    f"{self._soguma_s:.0f} sn boyunca sağlayıcıya gidilmiyor. "
                    "Yargı UYDURULMADI — bu çift değerlendirilemedi."
                )

        try:
            sonuc = self.inner.judge_conflict(a, b, overlap, sim)
        except JudgeUnavailableError:
            with self._kilit:
                self._ardisik_hata += 1
                if self._ardisik_hata >= self._esik and self._acilma_ani is None:
                    self._acilma_ani = self._saat()
                    logger.warning(
                        "judge devresi AÇILDI (%d ardışık hata) — %.0f sn kesiliyor",
                        self._ardisik_hata,
                        self._soguma_s,
                    )
            raise

        with self._kilit:
            # Başarı: sayaç sıfırlanır. "Ardışık" kelimesinin anlamı bu —
            # gün boyunca dağınık tekil hatalar devreyi açmamalı.
            self._ardisik_hata = 0
            self._acilma_ani = None
        return sonuc

"""Yedekli judge kompozisyonu (#255) — birincil düşerse ikincil devralır.

Neden `engine/` altında, `integrations/` altında değil: bu sınıf hiçbir
sağlayıcıyı tanımaz, yalnızca `JudgePort` sözleşmesini bilir. `CachedConflictJudge`
ile aynı desen — port'u saran, port döndüren bir dekoratör. Gemini↔Groq bugünkü
kullanım; yarın Ollama↔Groq da aynı sınıfla kurulur.

Neden yedek (fallback), yük paylaşımı (round-robin) değil
--------------------------------------------------------
Yük paylaşımı da kota tavanını yükseltirdi, ama AYNI board üzerinde iki farklı
model iki farklı çifti yargılardı. Modeller sistematik olarak farklı severity
dağılımlarına sahiptir; sonuç, kullanıcının aynı ekranda kıyasladığı kartların
farklı ölçütlerle puanlanması olurdu. `eval/kalibrasyon-raporu.md` tek bir judge
davranışına göre kalibre edilmiştir.

Yedekte ise ikincil sağlayıcı YALNIZCA birincil hiçbir yargı üretemediğinde
devreye girer. Tutarsızlık, aksi halde elde HİÇBİR yargı olmayacağı anlarla
sınırlı kalır — yani "biraz tutarsız" ile "hiç yok" arasında bir seçim, "tutarlı"
ile "tutarsız" arasında değil.
"""

import logging

from ensemble.models import Detection, NormalizedEvent
from ensemble.ports import JudgePort, JudgeUnavailableError

logger = logging.getLogger("ensemble.judge.fallback")


class FallbackJudge:
    """`JudgePort` sarmalayıcısı: `primary` düşerse `secondary`'yi dener."""

    def __init__(self, primary: JudgePort, secondary: JudgePort) -> None:
        self.primary = primary
        self.secondary = secondary

    def judge_conflict(
        self, a: NormalizedEvent, b: NormalizedEvent, overlap: list[str], sim: float | None
    ) -> Detection:
        try:
            return self.primary.judge_conflict(a, b, overlap, sim)
        except JudgeUnavailableError as birincil:
            # Yalnızca JudgeUnavailableError yakalanır. Diğer istisnalar (ağ
            # katmanı dışı programlama hataları) yayılır — hepsini yakalayıp
            # yedeğe düşmek, gerçek bir bug'ı "sağlayıcı arızası" gibi
            # gösterirdi.
            logger.info("birincil judge düştü, yedeğe geçiliyor: %s", birincil)
            try:
                return self.secondary.judge_conflict(a, b, overlap, sim)
            except JudgeUnavailableError as ikincil:
                # İKİSİ de düştü → çift gerçekten değerlendirilemedi. #252
                # sözleşmesi burada da geçerli: sahte tespit ÜRETİLMEZ.
                # `raise ... from birincil`: kök neden birincil sağlayıcıdır
                # (kota/kesinti); yedeğin hatası zincirin ucudur. Log'da her
                # ikisi de görünür ki "hangisi neden düştü" sorusu
                # yanıtlanabilsin.
                raise JudgeUnavailableError(
                    f"{a.id}-{b.id}: iki sağlayıcı da değerlendiremedi "
                    f"(birincil: {birincil} · yedek: {ikincil})"
                ) from birincil

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

from ensemble.models import (
    Detection,
    NormalizedEvent,
    QueryDocument,
    QueryJudgement,
    ScopeCandidate,
    ScopeJudgement,
)
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


class _YedekliJudge:
    """`FallbackJudge`'in query/scope icin ortak govdesi (#330).

    `FallbackJudge`'den TEK farki: hangi istisnanin "bu saglayici uretemedi"
    demek oldugunu KURULUMDA alir. Neden: `JudgePort`'un aksine
    `QueryJudgePort`/`ScopeJudgePort` sozlesmelerinde port-seviyesi bir
    "unavailable" istisnasi YOK; adapterler saglayiciya ozgu hatalarini
    (`GeminiError`/`GroqError`) yayiyor. Bu tipleri burada sabitlemek, bu
    dosyanin en ustte yazili kuralini ("hicbir saglayiciyi tanimaz") bozardi
    — o yuzden bilgi disaridan, saglayicinin zaten bilindigi yerden (app.py)
    enjekte edilir.

    IKISI DE DUSERSE BIRINCIL'IN HATASI YAYILIR (yedeginki degil). Bu bilincli:
    donmus hata sozlesmesi (`docs/sprint3-kontratlar.md` Ek D) `/scope/check`
    icin `503 gemini_unavailable` diyor; yedegin `GroqError`'unu yaymak, API
    hata haritasinda karsiligi olmayan bir istisnayi router'a kadar tasiyip
    500'e cevirirdi — yani yedek EKLEMEK hata sozlesmesini BOZARDI.
    """

    _METOT: str = ""

    def __init__(
        self,
        primary: object,
        secondary: object,
        *,
        unavailable: tuple[type[BaseException], ...],
    ) -> None:
        self.primary = primary
        self.secondary = secondary
        self.unavailable = unavailable

    def _cagir(self, *args: object, **kwargs: object) -> object:
        try:
            return getattr(self.primary, self._METOT)(*args, **kwargs)
        except self.unavailable as birincil:
            logger.info(
                "birincil %s dustu, yedege geciliyor: %s", self._METOT, birincil
            )
            try:
                return getattr(self.secondary, self._METOT)(*args, **kwargs)
            except self.unavailable as ikincil:
                logger.warning(
                    "%s: iki saglayici da uretemedi (birincil: %s · yedek: %s)",
                    self._METOT,
                    birincil,
                    ikincil,
                )
                raise birincil from ikincil


class FallbackQueryJudge(_YedekliJudge):
    """`QueryJudgePort` sarmalayicisi — Ask cevabi icin yedekli judge (#330)."""

    _METOT = "answer_query"

    def answer_query(self, question: str, documents: list[QueryDocument]) -> QueryJudgement:
        return self._cagir(question, documents)  # type: ignore[return-value]


class FallbackScopeJudge(_YedekliJudge):
    """`ScopeJudgePort` sarmalayicisi — kapsam karari icin yedekli judge (#330)."""

    _METOT = "judge_scope"

    def judge_scope(
        self, ref: str, subject: str, candidates: list[ScopeCandidate]
    ) -> ScopeJudgement:
        return self._cagir(ref, subject, candidates)  # type: ignore[return-value]

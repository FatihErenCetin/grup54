"""Agentic aksiyon (#339, D-61) — urunun dis dunyaya ILK YAZMA yolu.

29 Temmuz 2026'da olculdu: `integrations/github/adapter.py` icinde tek bir
POST/PATCH yoktu. Ensemble %100 SALT-OKUNURDU — gorur, siralar, gosterir; ama
hicbir seye dokunmazdi. Bu modul o esigi geciyor: radar `severity=high` bir
cakisma bulunca ilgili ACIK PR'a gerekcelendirilmis bir uyari yorumu birakir.

Guard'lar ozelligin KENDISI kadar onemli — bu yuzden hepsi engine'de (test
edilebilir yerde) durur, adapter'da degil:

| Guard | Nerede | Neden |
|---|---|---|
| `AGENTIC_ACTIONS_ENABLED` (varsayilan **false**) | `run()` ilk satir | Set edilmemis bir kurulum HICBIR sey yazmaz; tek bir GitHub cagrisi bile yapilmaz. |
| `AGENTIC_ACTIONS_DRY_RUN` (varsayilan **true**) | yazmadan hemen once | Ne yazacagini LOGLAR. Gercek yazma iki bayrak birden acikken. |
| yalniz `severity == "high"` | aday filtresi | `med`/`low` yorum uretmez — gurultu, uyariyi degersizlestirir. |
| idempotency (makine-okunur isaret) | yazmadan once | Ayni tespit icin IKINCI yorum ASLA. |
| kapali/merge edilmis PR | yazmadan once | Bitmis bir ise uyari yazmak zarardir. |
| `AGENTIC_ACTIONS_MAX_PER_RUN` | butce sayaci | Asilan kisim LOGLANIR + rapora girer; sessizce kesilmez. |
| yazma hatasi | `except` blogu | Hata bir DEGERE donusur ama **basari degil**: `sonuc="hata"`, sayilir, ERROR loglanir, rapor `degraded` olur. `yazilan` sayacina ASLA girmez. |

**Neden istisna firlatmiyoruz da hatayi bir sonuca cevirip sayiyoruz:** #252'nin
dersi "hatayi degere cevirme" DEGIL, "hatayi BASARI gibi gorunen bir degere
cevirme"dir. Ayni PR'daki cozum de tam olarak budur: `JudgeUnavailableError`
bir DEGER olarak toplanir, sayilir ve `RadarResult.judge_unavailable` ile
disari verilir. Burada da ayni desen: bir yazmanin patlamasi kalan tespitleri
dusurmez (bu, #252'nin cozdugu sorunun baska bir bicimi olurdu), ama hicbir
kosulda "yazildi" diye raporlanmaz ve `AgenticRunResult.degraded` True olur.

**Butce neden "gercek yazma"yi sayar, aday sayisini degil:** butce adaylari
sayarsaydi, ilk 3 aday "zaten yorum var" (yani hicbir sey yapilmayan) durumda
oldugunda 4. adaya SIRA HIC GELMEZDI — ve sonraki her turda ayni sey olurdu.
Yani gercek bir yuksek cakisma, ilk uc tespit dosyada durdugu surece SONSUZA
KADAR uyarisiz kalirdi (canli kilit / livelock). Butceyi yalnizca gercekten
yazilan (ya da kuru-calismada yazilacak olan) yorumlar tuketir.
"""

from __future__ import annotations

import hashlib
import logging
import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Literal

from ensemble.engine.radar import DetectionPair, RadarResult
from ensemble.models import NormalizedEvent
from ensemble.ports import GitHubPort

if TYPE_CHECKING:
    from ensemble.config import Settings

logger = logging.getLogger("ensemble.agentic")

# Aksiyonu TETIKLEYEN tek severity. `med`/`low` bilincli olarak disarida:
# otomatik yorum, ancak nadir oldugunda okunur.
TETIKLEYEN_SEVERITY = "high"

ISARET_ONEKI = "ensemble-detection-id"

Sonuc = Literal[
    "yazildi",  # gercek yorum GitHub'a yazildi
    "kuru_calisma",  # yazilacakti; DRY_RUN acik oldugu icin yalniz loglandi
    "zaten_var",  # ayni tespitin isareti PR'da zaten duruyor (idempotency)
    "pr_kapali",  # PR kapali/merge edilmis — yazilmaz
    "hedef_yok",  # cifte ait ACIK bir PR olayi yok (commit/issue cifti)
    "sinir_asildi",  # AGENTIC_ACTIONS_MAX_PER_RUN doldu — atlandi, loglandi
    "hata",  # yazma/okuma patladi — BASARI DEGIL, sayilir ve gorunur
]


@dataclass(frozen=True)
class AgenticOutcome:
    detection_id: str
    pr_number: int | None
    sonuc: Sonuc
    detay: str = ""


@dataclass(frozen=True)
class AgenticRunResult:
    """Bir agentic turunun TAM raporu — sessiz dusus yok (#339 / RadarResponse
    `degraded` deseni): atlanan, zaten-var olan ve patlayan her sey burada."""

    enabled: bool
    dry_run: bool
    yuksek_tespit: int
    outcomes: list[AgenticOutcome] = field(default_factory=list)

    def _sayim(self, sonuc: Sonuc) -> int:
        return sum(1 for outcome in self.outcomes if outcome.sonuc == sonuc)

    @property
    def yazilan(self) -> int:
        return self._sayim("yazildi")

    @property
    def kuru_calisma(self) -> int:
        return self._sayim("kuru_calisma")

    @property
    def hatalar(self) -> list[AgenticOutcome]:
        return [outcome for outcome in self.outcomes if outcome.sonuc == "hata"]

    @property
    def sinir_asilanlar(self) -> list[AgenticOutcome]:
        return [outcome for outcome in self.outcomes if outcome.sonuc == "sinir_asildi"]

    @property
    def degraded(self) -> bool:
        """Tur EKSIK tamamlandi mi (hata ya da sinir nedeniyle atlanan var mi)."""
        return bool(self.hatalar or self.sinir_asilanlar)


def tespit_isareti(detection_id: str) -> str:
    """Yorum govdesine gomulen MAKINE-OKUNUR isaret (idempotency anahtari).

    HTML yorumu secildi cunku GitHub onu render ETMEZ: insan temiz bir uyari
    gorur, urun kendi yazdigini tanir.

    Kimlik neden ham degil de `<temizlenmis>.<sha256[:8]>`: ham `Detection.id`
    icinde `-->` gecerse HTML yorumu ERKEN kapanir ve isaret bozulur (yani
    idempotency sessizce ölür → her turda yeni yorum). Yalniz temizleseydik
    farkli iki id ayni temiz metne cokebilirdi (`a-b` ve `a_b`) — o zaman
    B tespiti, A'nin isareti yuzunden SONSUZA KADAR uyarisiz kalirdi. Ozet
    ekleyerek ikisini de kapatiyoruz.
    """
    temiz = re.sub(r"[^A-Za-z0-9:_.]", "_", detection_id.strip())
    ozet = hashlib.sha256(detection_id.encode("utf-8")).hexdigest()[:8]
    return f"<!-- {ISARET_ONEKI}: {temiz}.{ozet} -->"


def _yorum_guvenli(metin: str) -> str:
    """LLM'den gelen SERBEST METNI (judge gerekcesi) yorum govdesine gomerken
    HTML-yorum sinirlarini notrlestirir.

    Gerekce: gerekce metni model uretimidir; icinde `<!--`/`-->` gecerse
    (kotu niyet gerekmez, diff alintisi yeter) govdeye gomdugumuz isaret
    erken kapanabilir ya da SAHTE bir isaret dogabilir — ikisi de
    idempotency'yi bozar.
    """
    return metin.replace("<!--", "< !--").replace("-->", "-- >")


def _pr_numaralari(pair: DetectionPair) -> list[int]:
    """Cifte ait PR numaralari (deterministik, artan).

    Cakismanin IKI tarafi da PR ise IKISINE de yazilir: uyari tek tarafa
    dusseydi, diger dalda calisan kisi kendi PR'inda hicbir sey gormezdi.
    """
    numaralar: set[int] = set()
    for event in (pair.a, pair.b):
        if event.type != "pr":
            continue
        ham = str(event.ref).strip()
        if not ham.isdigit():
            # Sessizce dusurmuyoruz: bu bir VERI sorunudur (normalize.py PR
            # ref'ini numara olarak yazar), gorunur olmali.
            logger.warning(
                "PR olayinin ref'i numara degil, hedef cozulemedi: id=%s ref=%r",
                event.id,
                event.ref,
            )
            continue
        numaralar.add(int(ham))
    return sorted(numaralar)


def _dal_etiketi(event: NormalizedEvent) -> str:
    return f"`{event.branch}`" if event.branch else "_(dal yok)_"


def yorum_govdesi(pair: DetectionPair) -> str:
    """PR'a yazilacak GEREKCELI uyari metni.

    Icerik sozlesmesi (#339): kim · hangi dal · kesisen dosyalar · judge
    gerekcesi · tespit kimligi. Bunlarin hepsi olmadan yorum "bir seyler
    ters" diyen ama ne yapilacagini soylemeyen bir bildirime doner.
    """
    detection = pair.detection
    kesisen = ", ".join(f"`{yol}`" for yol in pair.overlap) or "_(kesisim yok)_"
    taraflar = " · ".join(
        f"**{event.actor}** → {_dal_etiketi(event)} ({event.type} `{event.ref}`)"
        for event in (pair.a, pair.b)
    )
    return "\n".join(
        [
            tespit_isareti(detection.id),
            "### ⚠️ Ensemble — yuksek riskli calisma cakismasi",
            "",
            "Bu PR ile es zamanli ilerleyen baska bir calisma **ayni dosyalara** "
            "dokunuyor. Merge etmeden once konusmakta fayda var.",
            "",
            "| | |",
            "|---|---|",
            f"| Taraflar | {taraflar} |",
            f"| Kesisen dosyalar | {kesisen} |",
            f"| Judge gerekcesi | {_yorum_guvenli(detection.rationale)} |",
            f"| Siddet / guven | `{detection.severity}` / `{detection.confidence:.2f}` |",
            f"| Tespit kimligi | `{_yorum_guvenli(detection.id)}` |",
            "",
            "<sub>Bu yorumu Ensemble otomatik yazdi — yalnizca `severity=high` "
            "tespitlerde. Ayni tespit icin ikinci yorum yazilmaz. Kapatmak: "
            "`AGENTIC_ACTIONS_ENABLED=false`.</sub>",
        ]
    )


class AgenticActionService:
    """Radar sonucunu GitHub'a yazilan uyarilara cevirir (guard'lar burada)."""

    def __init__(
        self,
        github_port: GitHubPort,
        *,
        enabled: bool = False,
        dry_run: bool = True,
        max_per_run: int = 3,
    ) -> None:
        if max_per_run < 1:
            raise ValueError("max_per_run en az 1 olmali (#339)")
        self.github_port = github_port
        self.enabled = enabled
        self.dry_run = dry_run
        self.max_per_run = max_per_run

    @classmethod
    def from_settings(
        cls, settings: "Settings", github_port: GitHubPort, *, dry_run_zorla: bool = False
    ) -> "AgenticActionService":
        """`dry_run_zorla` yalnizca GUVENLI yonde etki eder: kuru calismayi
        acabilir, ASLA kapatamaz (CLI bayragiyla gercek yazma acilamaz)."""
        return cls(
            github_port,
            enabled=settings.AGENTIC_ACTIONS_ENABLED,
            dry_run=settings.AGENTIC_ACTIONS_DRY_RUN or dry_run_zorla,
            max_per_run=settings.AGENTIC_ACTIONS_MAX_PER_RUN,
        )

    def run(self, radar_result: RadarResult) -> AgenticRunResult:
        yuksek = [
            pair
            for pair in radar_result.pairs
            if pair.detection.severity == TETIKLEYEN_SEVERITY
        ]

        if not self.enabled:
            # FAIL-CLOSED: tek bir port cagrisi bile YOK. "Kapali" burada
            # "yazmayi dener ama son anda vazgecer" degil, "hic dokunmaz"
            # demek — bir yapilandirma hatasi ag trafigine bile donusemez.
            if yuksek:
                logger.info(
                    "agentic aksiyon KAPALI (AGENTIC_ACTIONS_ENABLED=false) — "
                    "%d yuksek tespit icin hicbir sey yazilmadi",
                    len(yuksek),
                )
            return AgenticRunResult(
                enabled=False, dry_run=self.dry_run, yuksek_tespit=len(yuksek)
            )

        outcomes: list[AgenticOutcome] = []
        butce = self.max_per_run

        for pair in yuksek:
            detection_id = pair.detection.id
            hedefler = _pr_numaralari(pair)
            if not hedefler:
                logger.info(
                    "agentic: tespit %s icin ACIK bir PR hedefi yok (taraflar: %s/%s) — atlandi",
                    detection_id,
                    pair.a.type,
                    pair.b.type,
                )
                outcomes.append(
                    AgenticOutcome(
                        detection_id=detection_id,
                        pr_number=None,
                        sonuc="hedef_yok",
                        detay="cifte ait PR olayi yok (commit/issue)",
                    )
                )
                continue

            for pr_number in hedefler:
                try:
                    outcome, tuketim = self._tek_hedef(pair, pr_number, butce)
                except Exception as exc:  # noqa: BLE001 — bilincli genis yakalama
                    # Genis yakalama, cunku hicbir saglayici hatasi (403 izin
                    # yok, 404, ag, 5xx) KALAN tespitleri dusurmemeli. Ama
                    # yutulmuyor: ERROR loglanir, `hata` olarak sayilir ve
                    # rapor `degraded` olur.
                    logger.error(
                        "agentic aksiyon BASARISIZ — PR #%s, tespit %s: %s",
                        pr_number,
                        detection_id,
                        exc,
                        exc_info=True,
                    )
                    outcomes.append(
                        AgenticOutcome(
                            detection_id=detection_id,
                            pr_number=pr_number,
                            sonuc="hata",
                            detay=f"{type(exc).__name__}: {exc}",
                        )
                    )
                    continue
                butce -= tuketim
                outcomes.append(outcome)

        return AgenticRunResult(
            enabled=True,
            dry_run=self.dry_run,
            yuksek_tespit=len(yuksek),
            outcomes=outcomes,
        )

    def _tek_hedef(
        self, pair: DetectionPair, pr_number: int, butce: int
    ) -> tuple[AgenticOutcome, int]:
        """Tek (tespit, PR) hedefini isler. Doner: (sonuc, butceden tuketilen).

        Kontrol SIRASI onemli:
          1. PR acik mi        → kapaliysa hicbir sey okumaya/yazmaya gerek yok
          2. isaret zaten var mi → varsa butce TUKETILMEZ (livelock guard)
          3. butce kaldi mi
          4. kuru calisma mi   → evetse LOGLA, yazma
          5. yaz
        """
        detection_id = pair.detection.id

        if not self.github_port.pull_request_open(pr_number):
            logger.info(
                "agentic: PR #%s acik degil (kapali/merge) — tespit %s icin yazilmadi",
                pr_number,
                detection_id,
            )
            return (
                AgenticOutcome(detection_id, pr_number, "pr_kapali", "PR kapali/merge edilmis"),
                0,
            )

        isaret = tespit_isareti(detection_id)
        mevcut = self.github_port.list_pull_request_comment_bodies(pr_number)
        if any(isaret in govde for govde in mevcut):
            logger.info(
                "agentic: tespit %s icin PR #%s'de zaten yorum var — ikinci yorum yazilmadi",
                detection_id,
                pr_number,
            )
            return (
                AgenticOutcome(detection_id, pr_number, "zaten_var", "isaret PR'da bulundu"),
                0,
            )

        if butce <= 0:
            logger.warning(
                "agentic: AGENTIC_ACTIONS_MAX_PER_RUN (%d) doldu — tespit %s / PR #%s "
                "BU TURDA atlandi (sonraki turda yeniden denenir)",
                self.max_per_run,
                detection_id,
                pr_number,
            )
            return (
                AgenticOutcome(
                    detection_id,
                    pr_number,
                    "sinir_asildi",
                    f"tur basina sinir {self.max_per_run} doldu",
                ),
                0,
            )

        govde = yorum_govdesi(pair)

        if self.dry_run:
            logger.info(
                "agentic KURU CALISMA (AGENTIC_ACTIONS_DRY_RUN=true) — PR #%s'e "
                "su yorum YAZILACAKTI:\n%s",
                pr_number,
                govde,
            )
            return (
                AgenticOutcome(detection_id, pr_number, "kuru_calisma", "yazilmadi (kuru calisma)"),
                1,
            )

        url = self.github_port.create_pull_request_comment(pr_number, govde)
        logger.info(
            "agentic: tespit %s icin PR #%s'e uyari yorumu YAZILDI (%s)",
            detection_id,
            pr_number,
            url,
        )
        return (AgenticOutcome(detection_id, pr_number, "yazildi", url), 1)

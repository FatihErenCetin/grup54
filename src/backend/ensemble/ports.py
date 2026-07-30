from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING, Protocol

from ensemble.models import (
    Detection,
    NormalizedEvent,
    QueryCorpus,
    QueryDocument,
    QueryJudgement,
    ScopeCandidate,
    ScopeJudgement,
    ScopeSubject,
)

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

# HarnessPort, shared paketinde (ensemble_shared.harness) yer alıyor ve
# oradan import edilecek. Buraya tekrar yazmıyoruz (GATE 1 kuralı).


@dataclass(frozen=True)
class BackfillResources:
    """HAM GitHub REST kaynakları (PR + issue listeleri) — `NormalizedEvent`'e
    İNDİRGENMEMİŞ hâlleri (#331).

    Neden ayrı bir port metodu gerekti: `fetch_backfill_events()` ham payload'ı
    `NormalizedEvent`'e daraltır ve durumun türediği alanları (`state`,
    `merged_at`, PR `body`, `head.ref`, issue `title`/`assignee`) ATAR. Board'ın
    GEÇMİŞİ tam olarak o alanlardan gelir; bu yüzden `engine/status_rules.py::
    transitions_from_resources` ile `TaskProjectionRow.from_github_issue`
    beslenecek ham sözlükler ikinci bir yoldan taşınır. `NormalizedEvent`'i
    bu alanlarla şişirmek radar/graph/activity'nin (üç ayrı tüketici)
    sözleşmesini durum-türetimi uğruna genişletirdi.

    `issues` LİSTESİ PR'LARDAN ARINDIRILMIŞTIR: GitHub'ın `/issues` ucu PR'ları
    da döndürür ve numaralar ortak havuzdan gelir — filtrelenmezse "PR #328
    kapandı" sinyali `T-328` diye SAHTE bir issue kartı üretirdi.
    """

    prs: list[dict] = field(default_factory=list)
    issues: list[dict] = field(default_factory=list)


class GitHubPort(Protocol):
    def fetch_events(self, since: datetime) -> list[NormalizedEvent]: ...
    def fetch_backfill_events(self, limit_per_type: int = 50) -> list[NormalizedEvent]: ...
    def fetch_backfill_resources(self, limit_per_type: int = 50) -> BackfillResources: ...
    def compare(self, base: str, head: str) -> list[str]: ...
    def get_diff(self, base: str, head: str) -> dict[str, str]: ...

    # --- YAZMA yuzeyi (#339) — urunun dis dunyaya ILK yazma yolu ------------
    # Bu satirlara kadar `GitHubPort` %100 SALT-OKUNURDU (olculdu 2026-07-29:
    # adapter'da tek bir POST/PATCH yoktu). Uc metodun ayri ayri durmasi
    # bilincli: "yazabilir miyim" (pull_request_open) ve "zaten yazdim mi"
    # (list_pull_request_comment_bodies) KARARLARI, yazmanin KENDISINDEN
    # (create_pull_request_comment) once ve ondan BAGIMSIZ olarak alinir —
    # tek bir "yorum at" metodu olsaydi guard'lar adapter'in icine gomulur
    # ve engine tarafindan test edilemezdi.
    #
    # HICBIRI "bilemedim"i bir degere COKERTMEZ: PR durumu okunamiyorsa
    # `False` (=kapali) DEGIL, istisna beklenir — "kapali" ile "bilmiyorum"
    # ayni sey degil (JudgeUnavailableError ile ayni ders, #252).
    def pull_request_open(self, number: int) -> bool: ...
    def list_pull_request_comment_bodies(self, number: int) -> list[str]: ...
    def create_pull_request_comment(self, number: int, body: str) -> str: ...


class EmbeddingsPort(Protocol):
    def embed(self, texts: list[str], task_type: str) -> list[list[float]]: ...


class VectorIndexPort(Protocol):
    def upsert(self, id: str, vec: list[float], meta: dict) -> None: ...
    def query(self, vec: list[float], k: int) -> list[tuple[str, float]]: ...

    def fingerprints(self) -> dict[str, str]:
        """`id -> meta["fingerprint"]` — hangi belgenin HANGİ HÂLİ gömülü.

        #355: `QueryService` bu haritayı bellekte tutuyordu, vektörler ise
        kalıcıydı. Sonuç: her süreç başlangıcında (her deploy) TÜM korpus
        "değişmiş" sayılıp yeniden gömülüyordu — 236 belge × her restart.
        Gemini'nin ücretsiz embed kotası günde 1000; birkaç deploy onu
        bitiriyor ve Ask o günün geri kalanında semantik aramasız kalıyor
        (canlıda 30 Tem'de tam olarak bu oldu).

        Kalıcı bir uygulama gerçek kayıtları döner; bellek-içi olanlar
        doğal olarak boş başlar — bu DOĞRU davranıştır, çünkü onların
        vektörleri de süreçle birlikte kaybolur. İkisi de aynı soruyu
        dürüstçe yanıtlar: "şu an elimde neyin hangi hâli gömülü?"
        """
        ...
    def clear(self) -> None:
        """Bağımsız operasyon için; rebuild akışı replace_all kullanır."""
    def replace_all(
        self,
        vectors: list[tuple[str, list[float], dict]],
        *,
        session: "Session | None" = None,
    ) -> None: ...


class JudgePort(Protocol):
    def judge_conflict(
        self, a: NormalizedEvent, b: NormalizedEvent, overlap: list[str], sim: float | None
    ) -> Detection: ...


class JudgeUnavailableError(RuntimeError):
    """Judge verilen çifti DEĞERLENDİREMEDİ (kota, ağ, bozuk yanıt).

    `JudgePort` sözleşmesinin parçası: adapter bu durumda `Detection`
    DÖNDÜRMEZ, bunu fırlatır (#252).

    Neden istisna, neden düşük-güvenli bir Detection değil: ikisi farklı
    olgudur ve tek nesneye sıkıştırılınca ayırt edilemez hale gelirler —
        "bu çift çakışma DEĞİL"        → gerçek bir yargı
        "bu çifti değerlendiremedik"   → yargının YOKLUĞU
    Sahte bir Detection döndürüldüğünde sistemin geri kalanı ona veri gibi
    davranır: cache saklar (900 sn), sıralama sıralar, UI render eder. Canlıda
    ölçülen sonuç 19 gerçek tespitin 131 sahte tespite dönüşmesiydi.

    İstisna olması, cache zehirlenmesini de kendiliğinden bitirir: istisna
    `CachedConflictJudge._cached_call`'daki `compute()`'tan yukarı yayılır ve
    `get_or_compute` hiçbir şey saklamaz. İstisnalar cache'lenmez; sahte
    başarılar cache'lenir.

    Çağıranın sorumluluğu: yakala, SAY ve görünür kıl — sessizce yutma
    (bkz. `RadarService.collect()` → `RadarResult.judge_unavailable`).
    """


class QuerySourcePort(Protocol):
    def load_query_corpus(self) -> QueryCorpus: ...


class QueryJudgePort(Protocol):
    def answer_query(self, question: str, documents: list[QueryDocument]) -> QueryJudgement: ...


class ScopeJudgePort(Protocol):
    def judge_scope(
        self, ref: str, subject: str, candidates: list[ScopeCandidate]
    ) -> ScopeJudgement: ...


class ScopeSubjectPort(Protocol):
    def resolve_scope_subject(self, ref: str) -> ScopeSubject: ...


class ScopeSubjectNotFoundError(LookupError):
    """ScopeSubjectPort verilen ref'i kendi kaynağında çözemedi."""

from datetime import datetime
from typing import Protocol

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

# HarnessPort, shared paketinde (ensemble_shared.harness) yer alıyor ve
# oradan import edilecek. Buraya tekrar yazmıyoruz (GATE 1 kuralı).


class GitHubPort(Protocol):
    def fetch_events(self, since: datetime) -> list[NormalizedEvent]: ...
    def fetch_backfill_events(self, limit_per_type: int = 50) -> list[NormalizedEvent]: ...
    def compare(self, base: str, head: str) -> list[str]: ...
    def get_diff(self, base: str, head: str) -> dict[str, str]: ...


class EmbeddingsPort(Protocol):
    def embed(self, texts: list[str], task_type: str) -> list[list[float]]: ...


class VectorIndexPort(Protocol):
    def upsert(self, id: str, vec: list[float], meta: dict) -> None: ...
    def query(self, vec: list[float], k: int) -> list[tuple[str, float]]: ...


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

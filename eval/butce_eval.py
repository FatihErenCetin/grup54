"""Cagri-sayisi butcesi (#256) - eval DOGRULUGU olcuyordu, MALIYETI olcmuyordu.

Boşluğun bedeli aynı gün üç kez ödendi: 131 çağrı/soğuk `/radar` (#255),
129 sn sıralı judge döngüsü (#254), kota tükenince 19 gerçek tespit yerine
131 sahte tespit (#252). Üçü de tek bir sorunun belirtisiydi: sistem ne kadar
DOĞRU olduğunu biliyordu, ne kadar PAHALI olduğunu bilmiyordu.

Bu modül `eval/gate.py`'nin (precision-gate, #30) maliyet ikizidir: sabit bir
fixture olay kümesi üzerinde `RadarService.collect()`'i GERÇEK yoluyla koştur,
sayaçlı sahte port'larla judge/embed/GitHub çağrı sayısını ölç, beyan edilen
bütçeyi aşarsa kırmızı ver.

NEDEN FIXTURE, CANLI REPO DEĞİL: sayı DETERMİNİSTİK olmalı - canlı GitHub'da
olay sayısı her gün değişir, test flaky olurdu. Aynı girdi -> aynı maliyet.

NEDEN `RadarService.collect()`, `file_overlap_candidates()` gibi alt-fonksiyonlar
DEĞİL: #162'nin dersi - eval üretimin GEÇTİĞİ kapılardan geçmeli, kestirme
yapmamalı. `eval/eval_runner.py` bu dersi precision tarafında zaten uyguluyor
(bkz. o dosyanın docstring'i); bu modül aynı disiplini maliyet tarafında
uygular. Sayaçlar `RadarService`'in KENDİSİNE değil, ona enjekte edilen
port'lara sarılır - servis kodu hiç değişmez, yalnız gözlenir.

ÖLÇEKLEME (kabul kriteri #5): aday sayısı olay sayısında KUADRATİKTİR
(`itertools.combinations(events, 2)` -> C(n,2)). `RADAR_WINDOW_DAYS` ve
`GITHUB_BACKFILL_LIMIT` ikisi de penceredeki olay sayısını (n) belirler -
pencereyi YARIYA indirmek, olay sayısını ~yarıya indirir ve aday sayısını
~DÖRTTE BİRE düşürür (C(n/2,2) ~= C(n,2)/4 büyük n için). Bu fixture'daki
5 çift/10 olay canlı `/radar`'ın küçük bir örneği - gerçek RADAR_WINDOW_DAYS=14
+ GITHUB_BACKFILL_LIMIT=50 penceresinde onlarca olay birikince aynı büyüme
kanunu 131 çağrıya kadar çıkarıyordu (#255).

Kullanım:
    python -m eval.butce_eval      # rapor satırı yazdırır, aşılırsa exit 1
    make eval-butce
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from ensemble.engine.embeddings import HashEmbeddings
from ensemble.engine.radar import RadarService
from ensemble.integrations.gemini.fake import FakeJudgeAdapter
from ensemble.models import Detection, NormalizedEvent
from ensemble.ports import EmbeddingsPort, GitHubPort, JudgePort

# ---------------------------------------------------------------------------
# Bütçe - KOD İÇİNDE SABİT (kabul kriteri #2). Gözlenen deger (asagidaki
# fixture, `judge_concurrency=1`, RADAR_MIN_JACCARD=RADAR_MIN_SIMILARITY=0.0
# kalibre operasyon noktasi) tam olarak judge=5 / embed=5 / github=11'dir;
# pay kucuk tutuldu ki sessiz bir regresyon (ornegin dosya-kesisimi filtresinin
# kaldirilmasi) hemen yakalansin - bkz. modul-alti "mutasyon dogrulamasi" notu.
MAX_JUDGE_CALLS = 6
MAX_EMBED_CALLS = 6
MAX_GITHUB_CALLS = 12


@dataclass(frozen=True)
class BudgetReport:
    """Bir `/radar` turunun olcumu - kabul kriteri #4'un kaynagi."""

    events: int
    judge_calls: int
    embed_calls: int
    github_calls: int

    def as_line(self) -> str:
        return (
            f"bu korpuste bir /radar = {self.judge_calls} judge · "
            f"{self.embed_calls} embed · {self.github_calls} GitHub çağrısı "
            f"({self.events} olay)"
        )


# ---------------------------------------------------------------------------
# Sayaçlı port sarmalayıcıları - RadarService'e HİÇ dokunmadan gözlem.
# ---------------------------------------------------------------------------


class _CountingGitHub:
    """`GitHubPort`'u sarar; her çağrıyı sayar (fetch/backfill + compare + get_diff)."""

    def __init__(self, inner: GitHubPort) -> None:
        self._inner = inner
        self.calls = 0

    def fetch_events(self, since: datetime) -> list[NormalizedEvent]:
        self.calls += 1
        return self._inner.fetch_events(since)

    def fetch_backfill_events(self, limit_per_type: int = 50) -> list[NormalizedEvent]:
        self.calls += 1
        return self._inner.fetch_backfill_events(limit_per_type)

    def compare(self, base: str, head: str) -> list[str]:
        self.calls += 1
        return self._inner.compare(base, head)

    def get_diff(self, base: str, head: str) -> dict[str, str]:
        self.calls += 1
        return self._inner.get_diff(base, head)


class _CountingEmbeddings:
    """`EmbeddingsPort`'u sarar; her `embed()` çağrısını sayar (metin sayısını DEĞİL)."""

    def __init__(self, inner: EmbeddingsPort) -> None:
        self._inner = inner
        self.calls = 0

    def embed(self, texts: list[str], task_type: str) -> list[list[float]]:
        self.calls += 1
        return self._inner.embed(texts, task_type)


class _CountingJudge:
    """`JudgePort`'u sarar; her `judge_conflict()` çağrısını sayar."""

    def __init__(self, inner: JudgePort) -> None:
        self._inner = inner
        self.calls = 0

    def judge_conflict(
        self, a: NormalizedEvent, b: NormalizedEvent, overlap: list[str], sim: float | None
    ) -> Detection:
        self.calls += 1
        return self._inner.judge_conflict(a, b, overlap, sim)


class _FixtureGitHub:
    """Ağa dokunmayan, sabit fixture GitHub kaynağı.

    `eval/backtest/*` gibi CANLI git tarihine değil, elle kurulmuş sabit bir
    olay kümesine dayanır - sayı, repo büyüdükçe/`gh` verisi değiştikçe
    KAYMASIN diye (fixture'ın var olma nedeni).
    """

    def __init__(self, events: list[NormalizedEvent], diffs: dict[tuple[str, str], dict[str, str]]):
        self._events = events
        self._diffs = diffs

    def fetch_events(self, since: datetime) -> list[NormalizedEvent]:
        return self._events

    def fetch_backfill_events(self, limit_per_type: int = 50) -> list[NormalizedEvent]:
        return self._events

    def compare(self, base: str, head: str) -> list[str]:
        return []

    def get_diff(self, base: str, head: str) -> dict[str, str]:
        return self._diffs.get((base, head), {})


# ---------------------------------------------------------------------------
# Sabit fixture - 10 olay, 5 dosya-kesişim çifti.
#
# Her küme (`radar`, `judge`, `scope`, `board`, `query`) iki olaydan oluşur;
# ikisi de kümeye özgü BİR dosyayı paylaşır + kümeye özgü ikinci bir dosyaya
# ayrı ayrı dokunur. Kümeler arası dosya kesişimi YOK - bu yüzden
# `file_overlap_candidates` tam olarak 5 aday üretir (C(10,2)=45 çiftin
# geri kalan 40'ı dosya-kesişimi filtresinde elenir). Aktörler hepsi farklı
# (aynı-aktör atlama mantığı devreye girmesin, sayı yalnız dosya-kesişimine
# bağlı kalsın).
# ---------------------------------------------------------------------------

_CLUSTERS = ["radar", "judge", "scope", "board", "query"]
_ACTORS = [
    "esma",
    "semih",
    "enes",
    "fatih",
    "zeynep",
    "kerem",
    "aylin",
    "burak",
    "ipek",
    "tarik",
]
_DEFAULT_BASE = "main"
# Her iki taraf da AYNI diff metnini içerir -> HashEmbeddings kendine karşı
# kosinüs benzerliği tam 1.0 verir (implementasyon detayına bağlı kırılganlık
# yok) -> `RADAR_MIN_SIMILARITY=0.0` eşiğini her zaman geçer, judge sayısı
# yalnız dosya-kesişim aday sayısına bağlı kalır.
_SHARED_DIFF = "@@ -1,2 +1,2 @@\n-eski davranis\n+ayni niyet: cakisma onarimi"


def _fixture_events() -> list[NormalizedEvent]:
    ts = datetime.now(timezone.utc) - timedelta(days=2)
    events: list[NormalizedEvent] = []
    actor_index = 0
    for cluster in _CLUSTERS:
        shared_file = f"src/backend/ensemble/engine/{cluster}.py"
        for side in ("a", "b"):
            actor = _ACTORS[actor_index]
            actor_index += 1
            branch = f"T-{cluster}-{side}"
            events.append(
                NormalizedEvent(
                    id=f"{cluster}-{side}",
                    type="commit",
                    actor=actor,
                    branch=branch,
                    files=[shared_file, f"docs/{cluster}-{side}-notlari.md"],
                    ts=ts,
                    ref=f"{cluster}{side}sha",
                )
            )
    return events


def _fixture_diffs() -> dict[tuple[str, str], dict[str, str]]:
    diffs: dict[tuple[str, str], dict[str, str]] = {}
    for cluster in _CLUSTERS:
        shared_file = f"src/backend/ensemble/engine/{cluster}.py"
        for side in ("a", "b"):
            branch = f"T-{cluster}-{side}"
            diffs[(_DEFAULT_BASE, branch)] = {shared_file: _SHARED_DIFF}
    return diffs


def measure_budget() -> BudgetReport:
    """Fixture üzerinde TEK bir `/radar` turu koştur, çağrı sayılarını döndür.

    `judge_concurrency=1`: bu bir eşzamanlılık testi değil (bkz. #254 testleri
    `tests/unit/test_radar.py`'de) - sayaçlar thread-safe artırma garantisi
    VERMEZ, sıralı koşu sayımı gürültüsüz tutar.
    """
    events = _fixture_events()
    github = _CountingGitHub(_FixtureGitHub(events, _fixture_diffs()))
    embeddings = _CountingEmbeddings(HashEmbeddings())
    judge = _CountingJudge(FakeJudgeAdapter())

    service = RadarService(
        github_port=github,
        judge_port=judge,
        embeddings_port=embeddings,
        window_days=14,
        min_jaccard=0.0,
        min_similarity=0.0,
        backfill_limit=50,
        default_base=_DEFAULT_BASE,
        judge_concurrency=1,
    )

    service.collect()

    return BudgetReport(
        events=len(events),
        judge_calls=judge.calls,
        embed_calls=embeddings.calls,
        github_calls=github.calls,
    )


def evaluate_budget_gate(
    report: BudgetReport,
    *,
    max_judge_calls: int = MAX_JUDGE_CALLS,
    max_embed_calls: int = MAX_EMBED_CALLS,
    max_github_calls: int = MAX_GITHUB_CALLS,
) -> list[str]:
    """Bütçeyi aşan ihlalleri döner (boş liste = geçti). Sınır dahil (`<=`)."""
    violations: list[str] = []
    if report.judge_calls > max_judge_calls:
        violations.append(
            f"judge çağrısı {report.judge_calls} > bütçe {max_judge_calls}"
        )
    if report.embed_calls > max_embed_calls:
        violations.append(
            f"embed çağrısı {report.embed_calls} > bütçe {max_embed_calls}"
        )
    if report.github_calls > max_github_calls:
        violations.append(
            f"GitHub çağrısı {report.github_calls} > bütçe {max_github_calls}"
        )
    return violations


def run_budget_gate() -> BudgetReport:
    return measure_budget()


def main() -> None:
    report = run_budget_gate()
    violations = evaluate_budget_gate(report)

    print("=" * 60)
    print("  Eval çağrı-sayısı bütçesi (#256)")
    print("=" * 60)
    print(f"  {report.as_line()}")
    print(
        f"  judge={report.judge_calls} (bütçe {MAX_JUDGE_CALLS})  "
        f"embed={report.embed_calls} (bütçe {MAX_EMBED_CALLS})  "
        f"github={report.github_calls} (bütçe {MAX_GITHUB_CALLS})"
    )

    if not violations:
        print("\n  GEÇTİ — çağrı sayıları bütçe içinde.")
        return

    print("\n  KIRILDI:")
    for violation in violations:
        print(f"    - {violation}")
    print(
        "\n  Aday sayısı beklenenden fazla artmış olabilir (ör. dosya-kesişimi "
        "filtresinde bir regresyon) - `ensemble.engine.radar.file_overlap_candidates` "
        "gözden geçirilmeli."
    )
    sys.exit(1)


if __name__ == "__main__":
    main()

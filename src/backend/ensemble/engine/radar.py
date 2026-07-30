import logging
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from collections.abc import Mapping
from datetime import datetime, timedelta, timezone
from itertools import combinations

from ensemble.models import Detection, NormalizedEvent
from ensemble.ports import (
    EmbeddingsPort,
    GitHubPort,
    JudgePort,
    JudgeUnavailableError,
    VectorIndexPort,
)
from ensemble.engine.chunking import chunk_diff
from ensemble.engine.embeddings import HashEmbeddings
from ensemble.engine.vectorstore import cosine_similarity


logger = logging.getLogger("ensemble.radar")

SEMANTIC_SIMILARITY_TASK = "SEMANTIC_SIMILARITY"
DEFAULT_RADAR_WINDOW_DAYS = 14
DEFAULT_BACKFILL_LIMIT = 50
# Judge asamasi I/O-bagimli (olcum: 131 aday/129 sn, CPU %0.7-6). Varsayilan
# 8, saglayici RPM tavani ile gecikme arasindaki dengeye gore ayarlanir (#254).
DEFAULT_JUDGE_CONCURRENCY = 8


@dataclass(frozen=True)
class DetectionPair:
    """Bir tespit + ONU URETEN iki olay (#339).

    `Detection` yalnizca `actors`/`branches`/`files` tasir — HANGI PR'a ait
    oldugunu tasimaz. Radar bunu okumak icin `Detection.id`'yi parcalamak
    (kirilgan) ya da olaylari ikinci kez uretmek (judge'i tekrar yakmak)
    gerekirdi; bunun yerine kaniti dogdugu yerde tasiyoruz.

    `RadarResult.detections` KAMUYA acik gorunumdur (API sozlesmesi,
    `RadarResponse`) ve DEGISMEDI; `pairs` yalnizca surec-ici tuketiciler
    icindir (bugun tek tuketici: `engine/agentic.py` — yorumun HANGI PR'a
    yazilacagini buradan cozer).
    """

    detection: Detection
    a: NormalizedEvent
    b: NormalizedEvent
    overlap: list[str]


@dataclass(frozen=True)
class RadarResult:
    """Bir `/radar` turunun sonucu — tespitler VE değerlendirilemeyenlerin sayısı.

    `judge_unavailable` neden yanıtın parçası (#252): judge kotası bittiğinde
    aday çiftler sessizce listeden düşerse board boş görünür ve kimse NEDEN
    boş olduğunu bilemez. Eksikliği gizlemek, onu sahte tespite çevirmekten
    daha az zararlı ama hâlâ yanıltıcı — bu yüzden sayı DIŞARI verilir.

    Sayaç neden burada, `RadarService` üzerinde bir alan olarak değil: FastAPI
    senkron endpoint'leri bir threadpool'da çalıştırır ve servis singleton'dır;
    paylaşılan sayaç eşzamanlı iki `/radar` isteği arasında yarışırdı. Sonucu
    çağrıya bağlı (frozen) bir nesnede taşımak bu yarışı yapısal olarak imkânsız
    kılar.
    """

    detections: list[Detection] = field(default_factory=list)
    evaluated: int = 0
    judge_unavailable: int = 0
    # `detections` ile AYNI sirada, AYNI elemanlar (bkz. DetectionPair).
    # Varsayilan bos: `RadarResult()`i elle kuran mevcut testler/cagiranlar
    # kirilmasin (additive alan, donuk `detections` sozlesmesine dokunulmadi).
    pairs: list[DetectionPair] = field(default_factory=list)


@dataclass(frozen=True)
class FileOverlapCandidate:
    a: NormalizedEvent
    b: NormalizedEvent
    overlap: list[str]
    jaccard: float


@dataclass(frozen=True)
class SemanticHunkCandidate:
    a: NormalizedEvent
    b: NormalizedEvent
    overlap: list[str]
    jaccard: float
    similarity: float | None
    path_scores: dict[str, float | None]


def jaccard_similarity(left: list[str], right: list[str]) -> float:
    left_set = set(left)
    right_set = set(right)
    union = left_set | right_set
    if not union:
        return 0.0
    return len(left_set & right_set) / len(union)


def file_overlap_candidates(
    events: list[NormalizedEvent],
    min_jaccard: float = 0.0,
    *,
    exclude_same_actor: bool = False,
) -> list[FileOverlapCandidate]:
    candidates: list[FileOverlapCandidate] = []

    for a, b in combinations(events, 2):
        if a.actor == b.actor:
            if exclude_same_actor:
                continue
            if not a.branch or not b.branch or a.branch == b.branch:
                continue

        overlap = sorted(set(a.files) & set(b.files))
        if not overlap:
            continue

        score = jaccard_similarity(a.files, b.files)
        if score < min_jaccard:
            continue

        a, b = _canonical_pair(a, b)
        candidates.append(FileOverlapCandidate(a=a, b=b, overlap=overlap, jaccard=score))

    return sorted(
        candidates,
        key=lambda candidate: (
            -candidate.jaccard,
            candidate.a.ts,
            candidate.b.ts,
            candidate.a.id,
            candidate.b.id,
        ),
    )


def semantic_hunk_candidates(
    candidates: list[FileOverlapCandidate],
    diffs_by_event: Mapping[str, Mapping[str, str]],
    embeddings: EmbeddingsPort,
    min_similarity: float = 0.0,
) -> list[SemanticHunkCandidate]:
    semantic_candidates: list[SemanticHunkCandidate] = []

    for candidate in candidates:
        path_scores: dict[str, float | None] = {}
        for path in candidate.overlap:
            left_diff = diffs_by_event.get(candidate.a.id, {}).get(path, "")
            right_diff = diffs_by_event.get(candidate.b.id, {}).get(path, "")
            path_scores[path] = semantic_hunk_similarity(
                left_diff,
                right_diff,
                path=path,
                embeddings=embeddings,
            )

        known_scores = [score for score in path_scores.values() if score is not None]
        similarity = max(known_scores, default=None)
        if not passes_similarity_threshold(similarity, min_similarity):
            continue

        semantic_candidates.append(
            SemanticHunkCandidate(
                a=candidate.a,
                b=candidate.b,
                overlap=candidate.overlap,
                jaccard=candidate.jaccard,
                similarity=similarity,
                path_scores=path_scores,
            )
        )

    return sorted(
        semantic_candidates,
        key=lambda candidate: (
            candidate.similarity is None,
            -(candidate.similarity if candidate.similarity is not None else 0.0),
            -candidate.jaccard,
            candidate.a.ts,
            candidate.b.ts,
            candidate.a.id,
            candidate.b.id,
        ),
    )


def passes_similarity_threshold(
    similarity: float | None,
    min_similarity: float,
) -> bool:
    """Bilinmeyen benzerligi elemeden kanonik similarity esigini uygular."""
    return similarity is None or similarity >= min_similarity


def semantic_hunk_similarity(
    left_diff: str,
    right_diff: str,
    path: str,
    embeddings: EmbeddingsPort,
) -> float | None:
    left_chunks = chunk_diff(left_diff, path=path)
    right_chunks = chunk_diff(right_diff, path=path)
    if not left_chunks or not right_chunks:
        return None

    left_texts = [chunk.text for chunk in left_chunks]
    right_texts = [chunk.text for chunk in right_chunks]
    vectors = embeddings.embed(left_texts + right_texts, SEMANTIC_SIMILARITY_TASK)
    if len(vectors) != len(left_texts) + len(right_texts):
        raise ValueError("embeddings must return one vector per hunk")

    left_vectors = vectors[: len(left_texts)]
    right_vectors = vectors[len(left_texts) :]
    return max(cosine_similarity(left, right) for left in left_vectors for right in right_vectors)


def _canonical_pair(
    a: NormalizedEvent, b: NormalizedEvent
) -> tuple[NormalizedEvent, NormalizedEvent]:
    if _event_order_key(a) <= _event_order_key(b):
        return a, b
    return b, a


def _event_order_key(event: NormalizedEvent) -> tuple[str, str, str, str]:
    return (
        event.id,
        event.actor,
        event.branch or "",
        event.ref,
    )


class RadarService:
    def __init__(
        self,
        github_port: GitHubPort,
        judge_port: JudgePort,
        embeddings_port: EmbeddingsPort | None = None,
        vector_index: VectorIndexPort | None = None,
        diffs_by_event: Mapping[str, Mapping[str, str]] | None = None,
        window_days: int = DEFAULT_RADAR_WINDOW_DAYS,
        min_jaccard: float = 0.0,
        min_similarity: float = 0.0,
        include_low_severity: bool = True,
        backfill_limit: int = DEFAULT_BACKFILL_LIMIT,
        default_base: str = "main",
        judge_concurrency: int = DEFAULT_JUDGE_CONCURRENCY,
    ):
        if window_days <= 0:
            raise ValueError("window_days must be positive")
        if backfill_limit < 0:
            raise ValueError("backfill_limit must be non-negative")
        if judge_concurrency < 1:
            raise ValueError("judge_concurrency must be at least 1")
        self.github_port = github_port
        self.judge_port = judge_port
        self.embeddings_port = embeddings_port or HashEmbeddings()
        self.vector_index = vector_index
        self.diffs_by_event = diffs_by_event or {}
        self.window_days = window_days
        self.min_jaccard = min_jaccard
        self.min_similarity = min_similarity
        self.include_low_severity = include_low_severity
        self.backfill_limit = backfill_limit
        self.judge_concurrency = judge_concurrency
        self.default_base = default_base
        self._compare_cache: dict[tuple[str, str], list[str]] = {}
        self._known_events: dict[str, NormalizedEvent] = {}
        self._backfill_done = False

    def get_detections(self) -> list[Detection]:
        """Geriye dönük uyumlu görünüm — yalnızca tespitler.

        Değerlendirilemeyen çiftlerin sayısına ihtiyaç duyan çağıranlar (API
        router) `collect()` kullanmalı; burası onun `.detections` alanıdır.
        """
        return self.collect().detections

    def collect(self) -> RadarResult:
        events = self._current_events()
        file_candidates = file_overlap_candidates(events, min_jaccard=self.min_jaccard)
        diffs = self._diffs_for_candidates(file_candidates)
        semantic_candidates = semantic_hunk_candidates(
            file_candidates,
            diffs,
            self.embeddings_port,
            min_similarity=self.min_similarity,
        )

        # (aday, tespit) ikilisi BIRLIKTE tasinir: tespitin hangi olaylardan
        # dogdugu bilgisi (#339, DetectionPair) burada kaybolursa bir daha
        # geri getirilemez. `detections` listesinin uretilme kurali —
        # filtre + siralama — AYNEN korundu.
        judged: list[tuple[SemanticHunkCandidate, Detection]] = []
        unavailable = 0
        # `strict=True`: `_judge_all` aday basina TEK sonuc dondurmeyi taahhut
        # eder (girdi sirasinda). Taahhut bir gun bozulursa `zip` sessizce
        # KIRPMASIN — tespitler ile onlari ureten olaylar birbirine kayardi.
        for candidate, verdict in zip(
            semantic_candidates, self._judge_all(semantic_candidates), strict=True
        ):
            if isinstance(verdict, JudgeUnavailableError):
                # #252: değerlendirilemeyen çift TESPİT DEĞİLDİR. Listeye
                # girmez ama sayılır — ham hata yalnızca log'da kalır;
                # kullanıcıya `RadarResult.judge_unavailable` sayısı gider.
                unavailable += 1
                logger.warning("judge değerlendiremedi: %s", verdict)
            else:
                judged.append((candidate, verdict))

        evaluated = len(judged)
        if not self.include_low_severity:
            judged = [item for item in judged if item[1].severity in {"med", "high"}]

        judged.sort(
            key=lambda item: (
                _severity_rank(item[1].severity),
                -item[1].confidence,
                item[1].id,
            )
        )

        return RadarResult(
            detections=[detection for _, detection in judged],
            evaluated=evaluated,
            judge_unavailable=unavailable,
            pairs=[
                DetectionPair(
                    detection=detection,
                    a=candidate.a,
                    b=candidate.b,
                    overlap=list(candidate.overlap),
                )
                for candidate, detection in judged
            ],
        )

    def _current_events(self) -> list[NormalizedEvent]:
        for event in self._events_with_compare_files(self._fetch_events()):
            self._known_events[event.id] = event

        since = self._since()
        self._known_events = {
            event_id: event
            for event_id, event in self._known_events.items()
            if _datetime_key(event.ts) >= _datetime_key(since)
        }
        return sorted(
            self._known_events.values(),
            key=lambda event: (_datetime_key(event.ts), event.id),
        )

    def _judge_all(
        self, candidates: list[SemanticHunkCandidate]
    ) -> list[Detection | JudgeUnavailableError]:
        """Adayları yargılar; sonuçları GİRDİ SIRASINDA döndürür (#254).

        Neden thread havuzu, neden asyncio değil: ölçüm bu aşamanın I/O-bağımlı
        olduğunu gösterdi — canlıda 131 aday 129 sn sürerken konteyner CPU'su
        %0.7-6 arasındaydı. Yani süre hesapta değil, sıra beklemede geçiyor.
        Adaptörler (Gemini SDK, httpx sync) senkron olduğu için thread havuzu
        doğal uyum; asyncio tüm adaptör zincirini async'e çevirmeyi gerektirirdi.

        Neden `.map()` değil de `submit()` + sıralı `result()`: `.map()` ilk
        istisnada yinelemeyi bozar; burada HER adayın sonucunu ayrı ayrı ele
        almamız gerekiyor (biri değerlendirilemedi diye diğer 130'u atmak
        #252'nin çözdüğü sorunun başka bir biçimi olurdu). Future listesi girdi
        sırasını koruduğu için sonuç, eşzamanlılıktan bağımsız olarak
        DETERMİNİSTİK kalır.

        `JudgeUnavailableError` bir DEĞER olarak döndürülür (fırlatılmaz):
        çağıran onu sayar. Diğer istisnalar (GitHub/ağ) yayılır — onlar tüm
        isteği düşürmeli, hata zarfı (api/errors.py) devralır.
        """
        if not candidates:
            return []

        def _judge(candidate: SemanticHunkCandidate) -> Detection | JudgeUnavailableError:
            try:
                return self.judge_port.judge_conflict(
                    candidate.a, candidate.b, candidate.overlap, candidate.similarity
                )
            except JudgeUnavailableError as exc:
                return exc

        # concurrency<=1 → havuz hiç kurulmaz. Testlerin ve tek-çekirdekli
        # ortamların sıralı, gözlenebilir bir yolu olsun diye kapatılabilir.
        if self.judge_concurrency <= 1 or len(candidates) == 1:
            return [_judge(candidate) for candidate in candidates]

        workers = min(self.judge_concurrency, len(candidates))
        with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="radar-judge") as pool:
            futures = [pool.submit(_judge, candidate) for candidate in candidates]
            return [future.result() for future in futures]

    def _diffs_for_candidates(
        self, candidates: list[FileOverlapCandidate]
    ) -> Mapping[str, Mapping[str, str]]:
        """Semantik hunk aşaması (#23/#152) için path->hunk metni sağlar.

        Constructor'da enjekte edilen `diffs_by_event` ÖNCELİKLİDİR (test-yolu
        korunur, #152 kabul kriteri) - yalnız orada olmayan ve `branch`'i olan
        event'ler için CANLI `github_port.get_diff()` çağrılır.

        Cache TEK BİR `get_detections()` çağrısıyla sınırlıdır (yerel değişken,
        `self`'te değil) - aksi halde bir branch'e yeni commit atıldığında
        RadarService süreç ömrü boyunca İLK gördüğü diff'e kilitlenip skorları
        bayatlatırdı (Semih review bulgusu, #152: aynı branch'e ikinci pollde
        değişen diff içeriği görmezden geliniyordu, repro'landı). `.compare()`/
        `_compare_cache`'teki AYNI sınıf bayatlık ayrı, önceden var olan bir
        desen — bu PR'ın kapsamı dışı, takip issue'ya taşındı.
        """
        diff_cache: dict[tuple[str, str], dict[str, str]] = {}
        diffs: dict[str, Mapping[str, str]] = dict(self.diffs_by_event)
        events = {event.id: event for pair in candidates for event in (pair.a, pair.b)}
        for candidate_event in events.values():
            if candidate_event.id in diffs or not candidate_event.branch:
                continue
            key = (self.default_base, candidate_event.branch)
            if key not in diff_cache:
                try:
                    diff_cache[key] = self.github_port.get_diff(*key)
                except Exception:
                    diff_cache[key] = {}
            diffs[candidate_event.id] = diff_cache[key]
        return diffs

    def _fetch_events(self) -> list[NormalizedEvent]:
        if not self._backfill_done:
            self._backfill_done = True
            if self.backfill_limit > 0:
                return self.github_port.fetch_backfill_events(self.backfill_limit)
        return self.github_port.fetch_events(self._since())

    def _since(self) -> datetime:
        return datetime.now(timezone.utc) - timedelta(days=self.window_days)

    def _events_with_compare_files(self, events: list[NormalizedEvent]) -> list[NormalizedEvent]:
        enriched: list[NormalizedEvent] = []
        for event in events:
            if event.files or not event.branch:
                enriched.append(event)
                continue

            key = (self.default_base, event.branch)
            if key not in self._compare_cache:
                try:
                    self._compare_cache[key] = self.github_port.compare(*key)
                except Exception:
                    self._compare_cache[key] = []
            files = self._compare_cache[key]
            enriched.append(event.model_copy(update={"files": files}))
        return enriched


def _severity_rank(severity: str) -> int:
    return {"high": 0, "med": 1, "low": 2}.get(severity, 3)


def _datetime_key(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        return value
    return value.astimezone(timezone.utc).replace(tzinfo=None)

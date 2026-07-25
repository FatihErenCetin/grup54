"""Hosted demo cached-verdict testleri (#63 — engine/cache.py).

Anti-tautoloji: her testte sarmalayıcının VARLIĞINI değil, iç (sayaçlı) fake
port'un GERÇEK çağrı sayısını ölçüyoruz. Aynı-içerik testleri BİLEREK iki
AYRI Python nesnesi kullanıyor (kimlik değil içerik keyed olduğunun kanıtı —
aksi halde test kırmızı olurdu). `sleep` YOK — TTL testlerinde saat enjekte
edilir.
"""

from __future__ import annotations

import sys
import threading
import time
from datetime import datetime, timezone

import pytest

from ensemble.engine import cache as cache_module
from ensemble.engine.cache import (
    CachedConflictJudge,
    CachedQueryJudge,
    CachedScopeJudge,
    TtlLruCache,
)
from ensemble.engine.embeddings import CachedEmbeddings
from ensemble.engine.radar import RadarService
from ensemble.integrations.github.fake import FakeGitHubAdapter
from ensemble.models import (
    NormalizedEvent,
    QueryDocument,
    QueryJudgement,
    ScopeCandidate,
    ScopeItemRef,
    ScopeJudgement,
)


# --- Fake sayaçlı port'lar (anti-tautoloji: gerçek çağrı sayısı ölçülür) ---


class _CountingJudge:
    def __init__(self) -> None:
        self.calls = 0

    def judge_conflict(self, a, b, overlap, sim):
        self.calls += 1
        from ensemble.models import Detection

        return Detection(
            id=f"{a.id}:{b.id}",
            actors=sorted({a.actor, b.actor}),
            branches=sorted({b for b in (a.branch, b.branch) if b}),
            files=list(overlap),
            severity="low",
            confidence=0.5,
            rationale="test",
        )


class _CountingQueryJudge:
    def __init__(self) -> None:
        self.calls = 0

    def answer_query(self, question, documents):
        self.calls += 1
        return QueryJudgement(
            answer=f"cevap [cite:{documents[0].ref}]",
            citation_refs=[documents[0].ref],
            confidence="high",
        )


class _CountingScopeJudge:
    def __init__(self) -> None:
        self.calls = 0

    def judge_scope(self, ref, subject, candidates):
        self.calls += 1
        return ScopeJudgement(verdict="in_scope", confidence=0.9, evidence_index=0)


def _event(id_: str, actor: str = "alice", branch: str = "feat", files=None, ref="1") -> NormalizedEvent:
    return NormalizedEvent(
        id=id_,
        type="pr",
        actor=actor,
        branch=branch,
        files=files or ["shared.py"],
        ts=datetime(2026, 7, 20, tzinfo=timezone.utc),
        ref=ref,
    )


def _doc(id_="d1", ref="ref-1", quote="alinti", text="metin") -> QueryDocument:
    return QueryDocument(id=id_, type="task", ref=ref, quote=quote, text=text)


def _candidate(similarity: float = 0.5) -> ScopeCandidate:
    return ScopeCandidate(
        evidence=ScopeItemRef(quote="madde", section="in_scope"), similarity=similarity
    )


# --- Es zamanlilik (single-flight) icin bloklanabilen fake port'lar ---
# `_Counting*` fake'lerinden AYRI tutulur: yukaridaki testler sarmalayicinin
# saf davranisini olcuyor, buradakiler `release_event`/`barrier` ile cagriyi
# BILEREK gecikip thread'lerin kilitte yigilip yigilmadigini kanitliyor.


class _BlockingCountingJudge:
    def __init__(self, release_event: threading.Event) -> None:
        self.calls = 0
        self._release_event = release_event

    def judge_conflict(self, a, b, overlap, sim):
        self.calls += 1
        self._release_event.wait(timeout=5)
        from ensemble.models import Detection

        return Detection(
            id=f"{a.id}:{b.id}",
            actors=sorted({a.actor, b.actor}),
            branches=sorted({x for x in (a.branch, b.branch) if x}),
            files=list(overlap),
            severity="low",
            confidence=0.5,
            rationale="test",
        )


class _BarrierJudge:
    def __init__(self, barrier: threading.Barrier) -> None:
        self.calls = 0
        self._barrier = barrier

    def judge_conflict(self, a, b, overlap, sim):
        self.calls += 1
        self._barrier.wait(timeout=5)  # global kilit olsa burada TIMEOUT olurdu
        from ensemble.models import Detection

        return Detection(
            id=f"{a.id}:{b.id}",
            actors=sorted({a.actor, b.actor}),
            branches=sorted({x for x in (a.branch, b.branch) if x}),
            files=list(overlap),
            severity="low",
            confidence=0.5,
            rationale="test",
        )


class _BlockingCountingQueryJudge:
    def __init__(self, release_event: threading.Event) -> None:
        self.calls = 0
        self._release_event = release_event

    def answer_query(self, question, documents):
        self.calls += 1
        self._release_event.wait(timeout=5)
        return QueryJudgement(
            answer=f"cevap [cite:{documents[0].ref}]",
            citation_refs=[documents[0].ref],
            confidence="high",
        )


class _BarrierQueryJudge:
    def __init__(self, barrier: threading.Barrier) -> None:
        self.calls = 0
        self._barrier = barrier

    def answer_query(self, question, documents):
        self.calls += 1
        self._barrier.wait(timeout=5)
        return QueryJudgement(
            answer=f"cevap [cite:{documents[0].ref}]",
            citation_refs=[documents[0].ref],
            confidence="high",
        )


class _BlockingCountingScopeJudge:
    def __init__(self, release_event: threading.Event) -> None:
        self.calls = 0
        self._release_event = release_event

    def judge_scope(self, ref, subject, candidates):
        self.calls += 1
        self._release_event.wait(timeout=5)
        return ScopeJudgement(verdict="in_scope", confidence=0.9, evidence_index=0)


class _BarrierScopeJudge:
    def __init__(self, barrier: threading.Barrier) -> None:
        self.calls = 0
        self._barrier = barrier

    def judge_scope(self, ref, subject, candidates):
        self.calls += 1
        self._barrier.wait(timeout=5)
        return ScopeJudgement(verdict="in_scope", confidence=0.9, evidence_index=0)


def _join_all(threads: list[threading.Thread]) -> None:
    for t in threads:
        t.join(timeout=5)
    for t in threads:
        assert not t.is_alive(), "thread zaman asiminda takildi kaldi"


def _run_all(threads: list[threading.Thread]) -> None:
    for t in threads:
        t.start()
    _join_all(threads)


# --- TtlLruCache (saf birim) ---


def test_ttl_dolunca_deger_dusuyor():
    now = [0.0]
    cache = TtlLruCache(ttl_s=5, max_entries=10, time_fn=lambda: now[0])
    cache.set("k", "v")
    assert cache.get("k") == "v"

    now[0] = 5.0001
    assert cache.get("k") is None


def test_lru_tahliyesi_en_eskiyi_atar():
    cache = TtlLruCache(ttl_s=100, max_entries=2, time_fn=lambda: 0.0)
    cache.set("a", 1)
    cache.set("b", 2)
    cache.set("c", 3)  # "a" en eski dokunulmamis anahtar - tahliye edilmeli

    assert cache.get("a") is None
    assert cache.get("b") == 2
    assert cache.get("c") == 3


def test_hit_miss_sayaclari():
    cache = TtlLruCache(ttl_s=100, max_entries=10, time_fn=lambda: 0.0)
    cache.get("yok")
    cache.set("k", "v")
    cache.get("k")
    cache.get("k")

    assert cache.misses == 1
    assert cache.hits == 2


def test_get_or_compute_hit_miss_sayaclari_ciftlenmez():
    """#63 ISTENEN 3: `get_or_compute` MISS yolunda `get()`'i iki kez
    cagiriyordu (hizli yol + kilit-alti double-check) - tek bir mantiksal
    MISS iki kez sayiliyordu. Double-check artik sayac ARTIRMAYAN `peek()`
    kullanir - bu testte 1 mantiksal miss (ilk cagri) + 1 mantiksal hit
    (ikinci cagri) TAM misses=1, hits=1 vermeli."""
    cache = TtlLruCache(ttl_s=100, max_entries=10, time_fn=lambda: 0.0)

    cache.get_or_compute("k", lambda: "deger")  # ilk cagri: MISS (hesaplar+yazar)
    cache.get_or_compute("k", lambda: "deger")  # ikinci cagri: HIT (hizli yoldan doner)

    assert cache.misses == 1
    assert cache.hits == 1


def test_get_or_compute_lock_acquire_istisnasinda_kayit_sizmiyor(monkeypatch):
    """#63 ISTENEN 3: `lock = self._locks.acquire(key)` ile
    `acquired = lock.acquire(timeout=...)` try BLOGUNUN DISINDAYDI - ikincisi
    istisna firlatirsa `finally` hic calismiyor, `self._locks.release(key)`
    cagrilmiyor, kayit defterinde KALICI sizinti oluyordu.

    `threading.Lock` C-tipi bir nesne oldugu icin tek bir ORNEGIN
    `.acquire`'ini monkeypatch'lemek mumkun degil (`attribute is read-only`) -
    onun yerine `KeyedLockRegistry.acquire`'i, GERCEK defter kaydini (refcount)
    aynen YAPAN ama gercek Lock yerine PATLAYAN sahte bir kilit donduren bir
    sarmalayicıyla degistiriyoruz."""
    cache = TtlLruCache(ttl_s=60, max_entries=10, time_fn=lambda: 0.0)

    class _ExplodingLock:
        def acquire(self, timeout=None):
            raise RuntimeError("lock patladi")

        def release(self):  # pragma: no cover - hicbir zaman cagrilmamali
            pass

    original_acquire = cache._locks.acquire

    def _acquire_with_exploding_lock(key: str):
        original_acquire(key)  # gercek refcount kaydi YINE artirilir
        return _ExplodingLock()

    monkeypatch.setattr(cache._locks, "acquire", _acquire_with_exploding_lock)

    with pytest.raises(RuntimeError, match="lock patladi"):
        cache.get_or_compute("k", lambda: "deger")

    assert len(cache._locks) == 0  # istisnaya ragmen kayit sizmadi


# --- CachedConflictJudge ---


def test_ayni_icerikli_farkli_nesnelerde_judge_bir_kez_cagrilir():
    inner = _CountingJudge()
    cached = CachedConflictJudge(inner, ttl_s=60, max_entries=10)

    a1, b1 = _event("a", "alice"), _event("b", "bob")
    a2, b2 = _event("a", "alice"), _event("b", "bob")  # AYNI icerik, FARKLI nesne

    r1 = cached.judge_conflict(a1, b1, ["shared.py"], 0.5)
    r2 = cached.judge_conflict(a2, b2, ["shared.py"], 0.5)

    assert inner.calls == 1
    assert r1 == r2


def test_farkli_overlap_ayri_anahtar_uretir():
    inner = _CountingJudge()
    cached = CachedConflictJudge(inner, ttl_s=60, max_entries=10)
    a, b = _event("a", "alice"), _event("b", "bob")

    cached.judge_conflict(a, b, ["shared.py"], 0.5)
    cached.judge_conflict(a, b, ["other.py"], 0.5)

    assert inner.calls == 2


def test_ttl_dolunca_judge_yeniden_sorulur():
    now = [0.0]
    inner = _CountingJudge()
    cached = CachedConflictJudge(inner, ttl_s=10, max_entries=10, time_fn=lambda: now[0])
    a, b = _event("a", "alice"), _event("b", "bob")

    cached.judge_conflict(a, b, ["shared.py"], 0.5)
    now[0] = 10.0001
    cached.judge_conflict(a, b, ["shared.py"], 0.5)

    assert inner.calls == 2


def test_hit_donen_nesne_mutasyona_kapali():
    inner = _CountingJudge()
    cached = CachedConflictJudge(inner, ttl_s=60, max_entries=10)
    a, b = _event("a", "alice"), _event("b", "bob")

    r1 = cached.judge_conflict(a, b, ["shared.py"], 0.5)
    r1.severity = "high"  # cagiranin kopyasini mutasyona ugrat

    r2 = cached.judge_conflict(a, b, ["shared.py"], 0.5)

    assert r2.severity == "low"  # cache'teki orijinal etkilenmedi
    assert inner.calls == 1  # hala HIT (yeniden sorulmadi)


# --- CachedQueryJudge ---


def test_query_judge_cache_soru_ve_belgeye_duyarli():
    inner = _CountingQueryJudge()
    cached = CachedQueryJudge(inner, ttl_s=60, max_entries=10)

    cached.answer_query("soru?", [_doc()])
    cached.answer_query("soru?", [_doc()])  # ayni icerik, FARKLI nesne
    assert inner.calls == 1

    cached.answer_query("soru?", [_doc(quote="degisti")])
    assert inner.calls == 2


# --- CachedScopeJudge ---


def test_scope_judge_cache_ref_subject_adaylara_duyarli():
    inner = _CountingScopeJudge()
    cached = CachedScopeJudge(inner, ttl_s=60, max_entries=10)

    cached.judge_scope("PR-1", "degisiklik metni", [_candidate()])
    cached.judge_scope("PR-1", "degisiklik metni", [_candidate()])  # ayni icerik
    assert inner.calls == 1

    cached.judge_scope("PR-1", "degisiklik metni", [_candidate(similarity=0.9)])
    assert inner.calls == 2


# --- Uctan uca fatura kaniti: Radar'in ikinci poll'unde judge cagirilmaz ---


def test_radar_ikinci_pollde_judge_cagirmaz():
    events = [
        _event("pr:1", actor="alice", branch="feat-a", files=["shared.py"], ref="1"),
        _event("pr:2", actor="bob", branch="feat-b", files=["shared.py"], ref="2"),
    ]
    github = FakeGitHubAdapter(events=events)
    inner_judge = _CountingJudge()
    cached_judge = CachedConflictJudge(inner_judge, ttl_s=60, max_entries=10)
    service = RadarService(github_port=github, judge_port=cached_judge, backfill_limit=50)

    first = service.get_detections()
    second = service.get_detections()  # frontend'in ~10 sn'lik poll'unun taklidi

    assert inner_judge.calls == 1
    assert [d.model_dump() for d in first] == [d.model_dump() for d in second]


# --- CachedEmbeddings boyut siniri (demo bellek korumasi) ---
#
# #63 takip (ikinci tur): el yazmasi OrderedDict (`._cache`) kaldirildi, yerine
# TtlLruCache (`.cache`) geldi - asagidaki testler `.cache` uzerinden okur
# (`__len__` TtlLruCache'in kendi metodu). Davranis (LRU sinir + sinirsiz
# varsayilan) AYNEN korunuyor, yalniz erisim yolu degisti.


def test_embeddings_cache_demo_modda_sinirli():
    class _CountingEmbeddings:
        def embed(self, texts, task_type):
            return [[float(len(text))] for text in texts]

    limited = CachedEmbeddings(_CountingEmbeddings(), max_entries=2)
    limited.embed(["a"], "T")
    limited.embed(["bb"], "T")
    limited.embed(["ccc"], "T")
    assert len(limited.cache) == 2

    # varsayilan (max_entries=None) = bugunku sinirsiz davranis, sifir regresyon
    unlimited = CachedEmbeddings(_CountingEmbeddings())
    unlimited.embed(["a"], "T")
    unlimited.embed(["bb"], "T")
    unlimited.embed(["ccc"], "T")
    assert len(unlimited.cache) == 3


def test_embeddings_cache_donen_vektor_mutasyona_kapali():
    """Kopya disiplini (#63 ISTENEN 1): deger list[float] yani MUTABLE -
    cagiran donen vektoru yerinde mutasyona ugratirsa cache'in kendi kopyasi
    KIRLENMEMELI (hit yolunda AYNI referans donseydi bu test kirilirdi)."""

    class _CountingEmbeddings:
        def __init__(self):
            self.calls = 0

        def embed(self, texts, task_type):
            self.calls += 1
            return [[1.0, 2.0] for _ in texts]

    inner = _CountingEmbeddings()
    cached = CachedEmbeddings(inner)

    first = cached.embed(["metin"], "T")[0]
    first[0] = 999.0  # cagiranin kendi kopyasini mutasyona ugrat

    second = cached.embed(["metin"], "T")[0]

    assert second == [1.0, 2.0]  # cache'teki orijinal etkilenmedi
    assert inner.calls == 1  # hala HIT (yeniden hesaplanmadi)


def test_embeddings_cache_ayni_metin_es_zamanli_inner_bir_kez_cagrilir():
    """Tekil-ucus (single-flight) - #63 ISTENEN 1 ZORUNLU testi: N thread AYNI
    metni es zamanli isterse `inner.embed` TAM 1 KEZ cagrilmali. Eski
    (kilitsiz) uygulamada hepsi miss gorup pahali cagriyi N KEZ tetiklerdi
    (BULGU 2)."""
    release_event = threading.Event()
    entered_event = threading.Event()
    call_count = [0]
    count_lock = threading.Lock()

    class _BlockingEmbeddings:
        def embed(self, texts, task_type):
            with count_lock:
                call_count[0] += 1
            entered_event.set()
            release_event.wait(timeout=5)
            return [[7.0] for _ in texts]

    cached = CachedEmbeddings(_BlockingEmbeddings())
    results: list[list[float]] = []
    results_lock = threading.Lock()

    def worker():
        vector = cached.embed(["ayni metin"], "T")[0]
        with results_lock:
            results.append(vector)

    threads = [threading.Thread(target=worker) for _ in range(6)]
    for t in threads:
        t.start()
    assert entered_event.wait(timeout=5)
    time.sleep(0.15)  # digerlerinin kilitte yigilmasi icin pay
    release_event.set()
    _join_all(threads)

    assert call_count[0] == 1
    assert len(results) == 6
    assert all(r == [7.0] for r in results)


def test_embeddings_cache_es_zamanlilikta_keyerror_vermez():
    """BULGU 1 (#63 takip) regresyon kilidi: el yazmasi OrderedDict
    `get()`/`move_to_end()` arasini kilitsiz birakiyordu - kucuk max_entries +
    yuksek thread sayisi + kucultulmus switch-interval ile ayni anahtarlarin
    surekli tahliye edilip yeniden yazilmasi zorlanir. Yeni (TtlLruCache
    tabanli) uygulamada KeyError HICBIR ZAMAN firlamamali. Deterministik ve
    hizli tutmak icin dar bir anahtar havuzu (yuksek carpisma/tahliye orani)
    + makul tur sayisi kullanilir."""
    old_interval = sys.getswitchinterval()
    sys.setswitchinterval(1e-6)
    try:
        class _FastEmbeddings:
            def embed(self, texts, task_type):
                return [[float(len(t))] for t in texts]

        cached = CachedEmbeddings(_FastEmbeddings(), max_entries=2)
        errors: list[BaseException] = []
        errors_lock = threading.Lock()

        def worker(rounds: int) -> None:
            try:
                for i in range(rounds):
                    text = f"metin-{i % 4}"
                    cached.embed([text], "T")
            except BaseException as exc:  # noqa: BLE001 - testte hatayi yakala
                with errors_lock:
                    errors.append(exc)

        threads = [threading.Thread(target=worker, args=(400,)) for _ in range(12)]
        _run_all(threads)

        assert errors == [], f"es zamanlilikta istisna(lar) firladi: {errors}"
    finally:
        sys.setswitchinterval(old_interval)


# --- TtlLruCache.get_or_compute (tekil-ucus / single-flight cekirdegi) ---
#
# DOGRULANMIS BLOCKER (#63 takip): get()->miss->inner->set() deseni get/set
# arasini korumuyordu - ayni anahtara es zamanli N istek hepsi miss goruyor,
# pahali cagriyi N KEZ tetikliyordu. Asagidaki testler bunu KAPATIYOR.


def test_get_or_compute_ayni_anahtar_es_zamanli_bir_kez_hesaplanir():
    cache = TtlLruCache(ttl_s=60, max_entries=10, time_fn=lambda: 0.0)
    call_count = [0]
    count_lock = threading.Lock()
    entered_event = threading.Event()
    release_event = threading.Event()

    def compute():
        with count_lock:
            call_count[0] += 1
        entered_event.set()
        release_event.wait(timeout=5)
        return "deger"

    results: list[str] = []
    results_lock = threading.Lock()

    def worker():
        value = cache.get_or_compute("k", compute)
        with results_lock:
            results.append(value)

    threads = [threading.Thread(target=worker) for _ in range(8)]
    for t in threads:
        t.start()

    assert entered_event.wait(timeout=5)  # tek bir thread compute'a girdi
    time.sleep(0.1)  # digerlerinin kilitte yigilmasi icin kisa pay
    release_event.set()  # tek hesaplayiciyi serbest birak

    _join_all(threads)

    assert call_count[0] == 1
    assert results == ["deger"] * 8


def test_get_or_compute_farkli_anahtarlar_paralel_calisir():
    cache = TtlLruCache(ttl_s=60, max_entries=10, time_fn=lambda: 0.0)
    barrier = threading.Barrier(2, timeout=5)
    errors: list[BaseException] = []
    errors_lock = threading.Lock()

    def compute(key: str) -> str:
        barrier.wait(timeout=5)  # ikisi de AYNI ANDA buraya ulasmali -
        # global kilit olsaydi ikincisi asla varamayip BrokenBarrierError'a duserdi
        return key

    results: dict[str, str] = {}
    results_lock = threading.Lock()

    def worker(key: str) -> None:
        try:
            value = cache.get_or_compute(key, lambda: compute(key))
            with results_lock:
                results[key] = value
        except BaseException as exc:  # noqa: BLE001 - testte hatayi yakala, raporla
            with errors_lock:
                errors.append(exc)

    threads = [
        threading.Thread(target=worker, args=("k1",)),
        threading.Thread(target=worker, args=("k2",)),
    ]
    _run_all(threads)

    assert errors == []
    assert results == {"k1": "k1", "k2": "k2"}


def test_get_or_compute_istisna_cachelenmez_ve_yayilir():
    cache = TtlLruCache(ttl_s=60, max_entries=10, time_fn=lambda: 0.0)
    calls: list[int] = []

    def failing_compute():
        calls.append(1)
        raise RuntimeError("gemini patladi")

    with pytest.raises(RuntimeError, match="gemini patladi"):
        cache.get_or_compute("k", failing_compute)

    assert cache.get("k") is None  # basarisiz sonuc HICBIR ZAMAN cachelenmedi
    assert len(cache._locks) == 0  # istisnadan sonra da kilit kaydi sizmadi

    def ok_compute():
        calls.append(1)
        return "deger"

    result = cache.get_or_compute("k", ok_compute)

    assert result == "deger"
    assert calls == [1, 1]  # ikinci cagri yeniden hesapladi (ilki basarisizdi)


def test_get_or_compute_kilit_sozlugu_sizinti_yapmiyor():
    cache = TtlLruCache(ttl_s=60, max_entries=10, time_fn=lambda: 0.0)

    def make_worker(key: str) -> threading.Thread:
        return threading.Thread(target=lambda: cache.get_or_compute(key, lambda: key))

    threads = [make_worker(f"k{i}") for i in range(10)]
    _run_all(threads)

    assert len(cache._locks) == 0
    assert len(cache) == 10  # ama DEGERLER cachelendi - yalniz kilit kaydi silindi


def test_get_or_compute_kilit_zaman_asiminda_kilitsiz_devam_eder(monkeypatch):
    monkeypatch.setattr(cache_module, "_SINGLE_FLIGHT_WAIT_S", 0.05)
    cache = TtlLruCache(ttl_s=60, max_entries=10, time_fn=lambda: 0.0)
    blocked_event = threading.Event()
    holder_entered = threading.Event()

    def blocker():
        holder_entered.set()
        # bu cagri kasten "asilir" - test suresince hic donmez; ikinci
        # cagrinin _SINGLE_FLIGHT_WAIT_S icinde zaman asimina dusmesini sinar
        blocked_event.wait(timeout=5)
        return "ilk"

    holder = threading.Thread(target=lambda: cache.get_or_compute("k", blocker))
    holder.start()
    assert holder_entered.wait(timeout=5)
    time.sleep(0.1)  # holder'in gercekten kilidi almis olmasini garantiye al

    fallback_calls: list[int] = []

    def fallback_compute():
        fallback_calls.append(1)
        return "ikinci"

    result = cache.get_or_compute("k", fallback_compute)  # kilit alinamaz -> zarif dusus

    assert result == "ikinci"
    assert fallback_calls == [1]

    blocked_event.set()
    holder.join(timeout=5)
    assert not holder.is_alive()


# --- Uc sarmalayicinin da tekil-ucus (single-flight) korumasi kullandigini
#     dogrudan (fake port'un GERCEK cagri sayisiyla) kanitlayan testler ---


def test_conflict_judge_ayni_anahtar_es_zamanli_inner_bir_kez_cagrilir():
    release_event = threading.Event()
    inner = _BlockingCountingJudge(release_event)
    cached = CachedConflictJudge(inner, ttl_s=60, max_entries=10)
    a, b = _event("a", "alice"), _event("b", "bob")

    results = []
    results_lock = threading.Lock()

    def worker():
        r = cached.judge_conflict(a, b, ["shared.py"], 0.5)
        with results_lock:
            results.append(r)

    threads = [threading.Thread(target=worker) for _ in range(6)]
    for t in threads:
        t.start()
    time.sleep(0.15)  # hepsinin get_or_compute'a girip kilitte yigilmasi icin pay
    release_event.set()
    _join_all(threads)

    assert inner.calls == 1
    assert len(results) == 6
    assert all(r == results[0] for r in results)


def test_conflict_judge_farkli_anahtarlar_paralel_calisir():
    barrier = threading.Barrier(2, timeout=5)
    inner = _BarrierJudge(barrier)
    cached = CachedConflictJudge(inner, ttl_s=60, max_entries=10)
    a, b = _event("a", "alice"), _event("b", "bob")
    errors: list[BaseException] = []
    errors_lock = threading.Lock()

    def worker(overlap: list[str]) -> None:
        try:
            cached.judge_conflict(a, b, overlap, 0.5)
        except BaseException as exc:  # noqa: BLE001
            with errors_lock:
                errors.append(exc)

    threads = [
        threading.Thread(target=worker, args=(["f1.py"],)),
        threading.Thread(target=worker, args=(["f2.py"],)),
    ]
    _run_all(threads)

    assert errors == []
    assert inner.calls == 2


def test_query_judge_ayni_anahtar_es_zamanli_inner_bir_kez_cagrilir():
    release_event = threading.Event()
    inner = _BlockingCountingQueryJudge(release_event)
    cached = CachedQueryJudge(inner, ttl_s=60, max_entries=10)

    def worker() -> None:
        cached.answer_query("soru?", [_doc()])

    threads = [threading.Thread(target=worker) for _ in range(6)]
    for t in threads:
        t.start()
    time.sleep(0.15)
    release_event.set()
    _join_all(threads)

    assert inner.calls == 1


def test_query_judge_farkli_anahtarlar_paralel_calisir():
    barrier = threading.Barrier(2, timeout=5)
    inner = _BarrierQueryJudge(barrier)
    cached = CachedQueryJudge(inner, ttl_s=60, max_entries=10)
    errors: list[BaseException] = []
    errors_lock = threading.Lock()

    def worker(question: str) -> None:
        try:
            cached.answer_query(question, [_doc()])
        except BaseException as exc:  # noqa: BLE001
            with errors_lock:
                errors.append(exc)

    threads = [
        threading.Thread(target=worker, args=("soru-1?",)),
        threading.Thread(target=worker, args=("soru-2?",)),
    ]
    _run_all(threads)

    assert errors == []
    assert inner.calls == 2


def test_scope_judge_ayni_anahtar_es_zamanli_inner_bir_kez_cagrilir():
    release_event = threading.Event()
    inner = _BlockingCountingScopeJudge(release_event)
    cached = CachedScopeJudge(inner, ttl_s=60, max_entries=10)

    def worker() -> None:
        cached.judge_scope("PR-1", "degisiklik metni", [_candidate()])

    threads = [threading.Thread(target=worker) for _ in range(6)]
    for t in threads:
        t.start()
    time.sleep(0.15)
    release_event.set()
    _join_all(threads)

    assert inner.calls == 1


def test_scope_judge_farkli_anahtarlar_paralel_calisir():
    barrier = threading.Barrier(2, timeout=5)
    inner = _BarrierScopeJudge(barrier)
    cached = CachedScopeJudge(inner, ttl_s=60, max_entries=10)
    errors: list[BaseException] = []
    errors_lock = threading.Lock()

    def worker(ref: str) -> None:
        try:
            cached.judge_scope(ref, "degisiklik metni", [_candidate()])
        except BaseException as exc:  # noqa: BLE001
            with errors_lock:
                errors.append(exc)

    threads = [
        threading.Thread(target=worker, args=("PR-1",)),
        threading.Thread(target=worker, args=("PR-2",)),
    ]
    _run_all(threads)

    assert errors == []
    assert inner.calls == 2

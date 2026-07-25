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
from ensemble.engine.embeddings import CachedEmbeddings, content_hash
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


# --- CachedEmbeddings sertlestirme turu (T-63 hosted-demo-hardening) ---
#
# Bagimsiz dogrulayicinin bulgulari: (1) `_fill_misses`in kilit-edinme
# dongusu yarida kesilirse eski `finally` TUM `unique_miss_keys` icin
# release() cagiriyordu - hic kaydedilmemis anahtarlar icin bu KeyError
# firlatip orijinal istisnayi maskeliyordu. (2) kopya disiplini testi
# yalniz MISS donusunu mutate ediyordu, HIT hizli-yolunu VE yazma-tarafi
# kopyasini AYRI AYRI kanitlamiyordu. Asagidaki testler bunlari kapatir.


def test_embeddings_cache_fill_misses_kilit_edinmede_istisna_orijinali_maskelemez():
    """HATA 1 (#63 sertlestirme turu): eski `finally` blogu, edinme dongusu
    YARIDA KESILSE BILE `unique_miss_keys`'in TAMAMI icin `self._locks.
    release()` cagiriyordu - ama dongu yarida kesilirse kalan anahtarlar
    kayit defterine HIC yazilmamis oluyordu, bu da `KeyError` firlatip
    orijinal istisnayi MASKELIYORDU. `cache.py`'nin kendi testindeki
    `_ExplodingLock` desenini burada 4 metinle, 2. anahtarda patlatarak
    tekrarliyoruz (bkz. `test_get_or_compute_lock_acquire_istisnasinda_kayit_sizmiyor`)."""

    class _CountingEmbeddings:
        def embed(self, texts, task_type):
            return [[float(len(t))] for t in texts]

    cached = CachedEmbeddings(_CountingEmbeddings())

    class _ExplodingLock:
        def acquire(self, timeout=None):
            raise RuntimeError("lock patladi")

        def release(self):  # pragma: no cover - hicbir zaman cagrilmamali
            pass

    original_acquire = cached._locks.acquire
    call_count = [0]

    def _acquire_explode_on_second(key: str):
        lock = original_acquire(key)  # gercek refcount kaydi YINE artirilir
        call_count[0] += 1
        if call_count[0] == 2:
            return _ExplodingLock()
        return lock

    cached._locks.acquire = _acquire_explode_on_second

    with pytest.raises(RuntimeError, match="lock patladi"):
        cached.embed(["bir", "iki", "uc", "dort"], "T")

    assert len(cached._locks) == 0  # kayit defterinde sizinti kalmadi (KeyError'a fena dusmedi)


def test_embeddings_cache_hit_yolundan_donen_vektor_mutasyona_kapali():
    """HATA 2a (#63 sertlestirme turu): mevcut
    `test_embeddings_cache_donen_vektor_mutasyona_kapali` yalniz ILK (MISS)
    cagrinin donusunu mutate ediyordu - `embed()` icindeki HIT hizli-yolunun
    (`result_by_position[index] = list(cached)`) KENDI kopyasini kanitlamiyordu.
    Bu test HIT donusunu mutate edip SONRAKI cagrinin temiz geldigini dogrular."""

    class _CountingEmbeddings:
        def __init__(self):
            self.calls = 0

        def embed(self, texts, task_type):
            self.calls += 1
            return [[1.0, 2.0] for _ in texts]

    inner = _CountingEmbeddings()
    cached = CachedEmbeddings(inner)

    cached.embed(["metin"], "T")  # ilk cagri: MISS, cache'e yazar
    second = cached.embed(["metin"], "T")[0]  # HIT hizli yolundan doner
    second[0] = 999.0  # HIT donusunu mutate et

    third = cached.embed(["metin"], "T")[0]  # yine HIT

    assert third == [1.0, 2.0]  # cache'teki orijinal etkilenmedi
    assert inner.calls == 1  # hala HIT (yeniden hesaplanmadi)


def test_embeddings_cache_yazma_tarafi_kopyasi_izole():
    """HATA 2b (#63 sertlestirme turu): yazma-tarafi kopyasini (`stored =
    list(vector)`) TEK BASINA kanitlayan test - caginin OKUMA kopyasina hic
    dokunmadan, `inner.embed()`'in DONDURDUGU orijinal vektor nesnesini
    sonradan mutate ediyoruz; cache'teki deger etkilenmemeli. (Bugune kadar
    okuma ve yazma kopyalari HEP BIRLIKTE mutate edilip kanitlanmisti.)"""
    produced_vectors: list[list[float]] = []

    class _CapturingEmbeddings:
        def embed(self, texts, task_type):
            vectors = [[1.0, 2.0] for _ in texts]
            produced_vectors.extend(vectors)
            return vectors

    cached = CachedEmbeddings(_CapturingEmbeddings())
    cached.embed(["metin"], "T")  # MISS - inner cagrilir, produced_vectors doldurulur

    produced_vectors[0][0] = 999.0  # inner'in orijinal donen nesnesini mutate et (caller DEGIL)

    result = cached.embed(["metin"], "T")[0]  # HIT

    assert result == [1.0, 2.0]  # cache'teki `stored` inner'in nesnesinden BAGIMSIZDI


def test_embeddings_cache_fill_misses_kendi_single_flight_alanini_kullanir():
    """KUCUK KAPANIS: `_fill_misses` `self._single_flight_wait_s`'i okur -
    mevcut wiring testi (`test_demo_acikken_judge_kilit_bekleme_suresi_gemini_ayarlarindan_turer`)
    yalniz `.cache.single_flight_wait_s` alanini dogruluyordu; constructor'daki
    `self._single_flight_wait_s = self.cache.single_flight_wait_s` satiri sabit
    `30.0` ile degistirilse bile o test yesil kalirdi. Enjekte edilen KUCUK bir
    deger (0.05sn) ile GERCEK kilit-timeout suresini olcerek `_fill_misses`in
    HANGI alani okudugunu dogrudan kanitliyoruz."""
    lock_holder_ready = threading.Event()
    release_holder = threading.Event()

    class _CountingEmbeddings:
        def __init__(self):
            self.calls = 0

        def embed(self, texts, task_type):
            self.calls += 1
            return [[1.0] for _ in texts]

    inner = _CountingEmbeddings()
    cached = CachedEmbeddings(inner, single_flight_wait_s=0.05)
    key = content_hash("metin", "T")

    # Anahtarin GERCEK kilidini disaridan tutarak `_fill_misses`i timeout
    # yoluna zorla.
    def holder():
        lock = cached._locks.acquire(key)
        lock.acquire()
        lock_holder_ready.set()
        release_holder.wait(timeout=10)
        lock.release()
        cached._locks.release(key)

    holder_thread = threading.Thread(target=holder)
    holder_thread.start()
    assert lock_holder_ready.wait(timeout=5)

    result_holder: dict[str, list] = {}

    def worker():
        result_holder["result"] = cached.embed(["metin"], "T")

    worker_thread = threading.Thread(target=worker)
    start = time.monotonic()
    worker_thread.start()
    worker_thread.join(timeout=1.0)
    elapsed = time.monotonic() - start
    still_alive = worker_thread.is_alive()

    release_holder.set()
    holder_thread.join(timeout=5)
    worker_thread.join(timeout=35)  # mutasyonlu (sabit 30sn) durumda dahi temiz bitsin

    assert not still_alive, "worker thread 1sn icinde bitmedi (30sn sabite dusmus olabilir)"
    assert elapsed < 1.0, f"enjekte edilen 0.05sn yerine cok daha uzun beklendi ({elapsed}s)"
    assert result_holder["result"] == [[1.0]]
    assert inner.calls == 1  # kilit timeout sonrasi kilitsiz hesaplandi


def test_embeddings_cache_fill_misses_kilitleri_sirali_alir():
    """KUCUK KAPANIS: `unique_miss_keys = sorted({...})` deterministik
    (alfabetik) kilit sirasi ile capraz-kilitlenmeyi (deadlock) onler (bkz.
    `_fill_misses` docstring'i) - ama bu SIRA test edilmiyordu; `sorted(...)`
    yerine `list(...)` yazilsa (set iterasyon sirasi ozel durumda
    sozde-rastgele) suite yesil kalirdi. Bu test kilit-edinme SIRASINI
    dogrudan gozlemleyip alfabetik sirayla eslestigini dogrular."""

    class _CountingEmbeddings:
        def embed(self, texts, task_type):
            return [[float(len(t))] for t in texts]

    cached = CachedEmbeddings(_CountingEmbeddings())
    acquired_order: list[str] = []
    original_acquire = cached._locks.acquire

    def _tracking_acquire(key: str):
        acquired_order.append(key)
        return original_acquire(key)

    cached._locks.acquire = _tracking_acquire

    texts = ["cok", "az", "orta", "bir", "iki"]
    cached.embed(texts, "T")

    expected_keys = sorted({content_hash(t, "T") for t in texts})
    assert acquired_order == expected_keys


def test_embeddings_cache_fill_misses_zaman_asiminda_disaridaki_kilidi_zorla_acmaz():
    """KUCUK KAPANIS: `_fill_misses`in ZAMAN ASIMI yolunun (bkz. `if lock.
    acquire(timeout=...): held_locks.append(...)`) hic testi yoktu. Kosul
    kaldirilip kosulsuz append yapilirsa: zaman asimina ugrayan (GERCEKTE
    TUTULMAYAN) kilit yine de finally'de release() edilir - sahiplik takibi
    olmayan `threading.Lock` icin bu, BASKA bir thread'in (dis tutucunun)
    HALA GECERLI kilidini FORCE-UNLOCK eder; o tutucu sonra KENDI
    release()'ini cagirdiginda `RuntimeError` alir (thread SESSIZCE olur -
    `not holder.is_alive()` bunu YAKALAMAZ, cunku olen thread de 'alive
    degil'dir). Bu test dis tutucu thread'in istisnasiz bittigini ACIKCA
    (paylasilan hata listesiyle) dogrular."""

    class _CountingEmbeddings:
        def embed(self, texts, task_type):
            return [[float(len(t))] for t in texts]

    cached = CachedEmbeddings(_CountingEmbeddings(), single_flight_wait_s=0.05)
    key = content_hash("metin", "T")

    holder_ready = threading.Event()
    release_holder = threading.Event()
    holder_errors: list[BaseException] = []

    def holder_target():
        try:
            lock = cached._locks.acquire(key)
            lock.acquire()
            holder_ready.set()
            release_holder.wait(timeout=5)
            lock.release()
            cached._locks.release(key)
        except BaseException as exc:  # noqa: BLE001 - testte hatayi yakala
            holder_errors.append(exc)

    holder_thread = threading.Thread(target=holder_target)
    holder_thread.start()
    assert holder_ready.wait(timeout=5)

    result = cached.embed(["metin"], "T")  # zaman asimina ugrar, kilitsiz devam eder

    release_holder.set()
    holder_thread.join(timeout=5)

    assert result == [[5.0]]
    assert not holder_thread.is_alive()
    assert holder_errors == [], f"dis tutucu thread istisnayla oldu: {holder_errors}"


# --- CachedEmbeddings son sertlestirme turu (T-63 son tur) ---
#
# Bagimsiz dogrulayicinin bulgulari: (MADDE 1) `_fill_misses`teki
# `lock = self._locks.acquire(key)` / `registered_keys.append(key)` SIRASI
# yuk tasiyan bir disiplindi - mevcut `_ExplodingLock` deseni SADECE donen
# kilidin KENDI `.acquire()`'ini patlatiyordu (yani KAYIT YAZILDIKTAN
# SONRASINI); `self._locks.acquire(key)`'in (registry seviyesi cagrinin)
# KENDISI (defter yazilmadan) patlarsa sira ters cevrilmis olsa bile hicbir
# test bunu yakalamiyordu. (MADDE 2) double-check adiminin `peek()` (sayac
# ARTIRMAYAN) kullandigi embeddings tarafinda hic kilitlenmemisti -
# cache.py'deki es (`test_get_or_compute_hit_miss_sayaclari_ciftlenmez`) VARDI,
# embeddings tarafinda YOKTU.


def test_embeddings_cache_fill_misses_defter_cagrisinin_kendisi_patlarsa_istisna_maskelenmez():
    """MADDE 1 (T-63 son tur): `lock = self._locks.acquire(key)` defter
    KAYDINI yazan cagridir; `registered_keys.append(key)` bunun SONRASINDA
    gelir - sira bu sekilde oldugu surece `self._locks.acquire(key)`'in
    KENDISI istisna firlatirsa (defter HIC yazilmadan) `registered_keys`e o
    anahtar asla girmez, `finally` onun icin `release()` cagirmaz -> orijinal
    istisna MASKELENMEZ. Mevcut `_ExplodingLock` deseni (bkz.
    `test_embeddings_cache_fill_misses_kilit_edinmede_istisna_orijinali_maskelemez`)
    bunu KACIRIYOR cunku donen kilidin KENDI `.acquire()`'ini (kayit
    YAZILDIKTAN SONRASINI) patlatiyor - burada ONUN YERINE registry-seviyesi
    `self._locks.acquire` metodunun KENDISI (gercek defter kaydi hic
    olusturulmadan) 2. anahtarda patlatilir. Sira `registered_keys.append(key)`
    ONCE / `self._locks.acquire(key)` SONRA olacak sekilde ters cevrilirse
    (`append once` mutasyonu) bu test KIRILIR: 2. anahtar defter kaydi
    olusmadan `registered_keys`e girer, `finally` onun icin `release()`
    cagirir, `KeyError` firlar ve orijinal `RuntimeError`'i MASKELER."""

    class _CountingEmbeddings:
        def embed(self, texts, task_type):
            return [[float(len(t))] for t in texts]

    cached = CachedEmbeddings(_CountingEmbeddings())

    original_acquire = cached._locks.acquire
    call_count = [0]

    def _acquire_explode_before_registering(key: str):
        call_count[0] += 1
        if call_count[0] == 2:
            # Gercek `original_acquire(key)` HIC cagrilmiyor - defter kaydi
            # bu anahtar icin ASLA olusmuyor (KAYIT YAZILMADAN patlama).
            raise RuntimeError("defter yazilmadan patladi")
        return original_acquire(key)

    cached._locks.acquire = _acquire_explode_before_registering

    with pytest.raises(RuntimeError, match="defter yazilmadan patladi"):
        cached.embed(["bir", "iki", "uc", "dort"], "T")

    assert len(cached._locks) == 0  # kayit defterinde sizinti kalmadi


def test_get_or_compute_defter_cagrisinin_kendisi_patlarsa_kayit_sizmaz_ve_maskelenmez(
    monkeypatch,
):
    """MADDE 1 (T-63 son tur) - kontrol: `cache.py::get_or_compute`de
    `lock = self._locks.acquire(key)` `try` BLOGUNUN TAMAMEN DISINDA - registry
    seviyesi `acquire()`'in KENDISI (defter yazilmadan) istisna firlatirsa
    `finally` hic calismaz, `self._locks.release()` cagrilmaz. Defter zaten
    yazilmadigi icin bu SIZINTI DEGIL, orijinal istisna da MASKELENMEZ.
    `embeddings.py::_fill_misses`teki (append/acquire SIRASINA bagli) risk
    BURADA yoktur - bu test o farki kilitler."""
    cache = TtlLruCache(ttl_s=60, max_entries=10, time_fn=lambda: 0.0)

    def _exploding_registry_acquire(key: str):
        raise RuntimeError("defter yazilmadan patladi")

    monkeypatch.setattr(cache._locks, "acquire", _exploding_registry_acquire)

    with pytest.raises(RuntimeError, match="defter yazilmadan patladi"):
        cache.get_or_compute("k", lambda: "deger")

    assert len(cache._locks) == 0  # hic kayit olusmadi, sizinti da yok


def test_embeddings_cache_hit_miss_sayaclari_ciftlenmez():
    """MADDE 2 (T-63 son tur): `_fill_misses`in double-check adimi SAYAC
    ARTIRMAYAN `self.cache.peek(key)` kullanir - `cache.py::get_or_compute`
    icindeki AYNI disiplinin (bkz. `test_get_or_compute_hit_miss_sayaclari_
    ciftlenmez`) embeddings tarafindaki esi. `peek` yerine `get` kullanilsa
    (mutasyon), ayni mantiksal MISS hem `embed()`in hizli-yol taramasinda hem
    de `_fill_misses`in double-check'inde SAYILIP misses=2 verirdi. Bu testte
    1 mantiksal MISS (ilk cagri) + 1 mantiksal HIT (ikinci cagri) TAM
    misses=1, hits=1 vermeli."""

    class _CountingEmbeddings:
        def embed(self, texts, task_type):
            return [[float(len(t))] for t in texts]

    cached = CachedEmbeddings(_CountingEmbeddings())

    cached.embed(["metin"], "T")  # ilk cagri: MISS (hesaplar+yazar)
    cached.embed(["metin"], "T")  # ikinci cagri: HIT (hizli yoldan doner)

    assert cached.cache.misses == 1
    assert cached.cache.hits == 1


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


def test_get_or_compute_kilit_zaman_asiminda_holder_istisnasiz_biter(monkeypatch):
    """KUCUK KAPANIS: yukaridaki test yalniz `not holder.is_alive()` diyordu -
    bu, ISTISNAYLA OLEN bir thread icin de DOGRU olur (dead=dead, sebebi
    onemsiz). `finally: if acquired: lock.release()` kosulu kaldirilip
    kosulsuz yapilirsa: zaman asimina ugrayan (acquired=False) fallback cagri
    AYNI PAYLASILAN Lock nesnesini holder HALA ICINDEYKEN FORCE-UNLOCK eder
    (sahiplik takibi olmayan `threading.Lock` icin `.release()` 'kim
    cagirdi' bakmaz, yalniz 'kilitli mi' bakar) - holder sonra KENDI
    finally'sinde ayni (zaten acilmis) kilidi tekrar release etmeye
    calisir -> `RuntimeError`, holder thread'i SESSIZCE oldurur. Bu test
    holder'in hata FIRLATMADAN bittigini ACIKCA (paylasilan hata listesiyle)
    dogrular."""
    monkeypatch.setattr(cache_module, "_SINGLE_FLIGHT_WAIT_S", 0.05)
    cache = TtlLruCache(ttl_s=60, max_entries=10, time_fn=lambda: 0.0)
    blocked_event = threading.Event()
    holder_entered = threading.Event()
    holder_errors: list[BaseException] = []

    def blocker():
        holder_entered.set()
        blocked_event.wait(timeout=5)
        return "ilk"

    def holder_target():
        try:
            cache.get_or_compute("k", blocker)
        except BaseException as exc:  # noqa: BLE001 - testte hatayi yakala
            holder_errors.append(exc)

    holder = threading.Thread(target=holder_target)
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
    assert holder_errors == [], f"holder thread istisnayla oldu: {holder_errors}"


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

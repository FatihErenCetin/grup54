"""Hosted demo cached-verdict testleri (#63 — engine/cache.py).

Anti-tautoloji: her testte sarmalayıcının VARLIĞINI değil, iç (sayaçlı) fake
port'un GERÇEK çağrı sayısını ölçüyoruz. Aynı-içerik testleri BİLEREK iki
AYRI Python nesnesi kullanıyor (kimlik değil içerik keyed olduğunun kanıtı —
aksi halde test kırmızı olurdu). `sleep` YOK — TTL testlerinde saat enjekte
edilir.
"""

from __future__ import annotations

from datetime import datetime, timezone

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


def test_embeddings_cache_demo_modda_sinirli():
    class _CountingEmbeddings:
        def embed(self, texts, task_type):
            return [[float(len(text))] for text in texts]

    limited = CachedEmbeddings(_CountingEmbeddings(), max_entries=2)
    limited.embed(["a"], "T")
    limited.embed(["bb"], "T")
    limited.embed(["ccc"], "T")
    assert len(limited._cache) == 2

    # varsayilan (max_entries=None) = bugunku sinirsiz davranis, sifir regresyon
    unlimited = CachedEmbeddings(_CountingEmbeddings())
    unlimited.embed(["a"], "T")
    unlimited.embed(["bb"], "T")
    unlimited.embed(["ccc"], "T")
    assert len(unlimited._cache) == 3

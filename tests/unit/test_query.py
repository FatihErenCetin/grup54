from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from ensemble.engine.query import QueryJudgeError, QueryRetrievalError, QueryService
from ensemble.engine.vectorstore import InMemoryVectorIndex
from ensemble.models import QueryCorpus, QueryDocument, QueryJudgement


class _Source:
    def __init__(self, documents: list[QueryDocument]) -> None:
        self.corpus = QueryCorpus(documents=documents, last_commit="abc1234")

    def load_query_corpus(self) -> QueryCorpus:
        return self.corpus


class _BrokenSource:
    def load_query_corpus(self) -> QueryCorpus:
        raise RuntimeError("bozuk projection")


class _TokenEmbeddings:
    vocabulary = ("scope", "drift", "postgres", "deploy", "mobil", "oyun")

    def __init__(self) -> None:
        self.calls: list[tuple[list[str], str]] = []

    def embed(self, texts: list[str], task_type: str) -> list[list[float]]:
        self.calls.append((texts, task_type))
        return [[float(token in text.casefold()) for token in self.vocabulary] for text in texts]


class _Judge:
    def __init__(self, judgement: QueryJudgement | None = None) -> None:
        self.judgement = judgement
        self.calls: list[tuple[str, list[QueryDocument]]] = []

    def answer_query(
        self,
        question: str,
        documents: list[QueryDocument],
    ) -> QueryJudgement:
        self.calls.append((question, documents))
        return self.judgement or QueryJudgement(
            answer=f"Scope-drift sprint kapsamındadır [cite:{documents[0].ref}]",
            citation_refs=[documents[0].ref],
            confidence="high",
        )


def _document(**overrides) -> QueryDocument:
    data = {
        "id": "scope:IS-1",
        "type": "scope",
        "ref": ".harness/scope/sprint-3.md#IS-1",
        "quote": "IS-1: Scope-drift bekçisini tamamla",
        "text": "IS-1: Scope-drift bekçisini tamamla",
    }
    data.update(overrides)
    return QueryDocument.model_validate(data)


def _service(
    documents: list[QueryDocument],
    *,
    judge: _Judge | None = None,
) -> tuple[QueryService, _Judge, _TokenEmbeddings]:
    actual_judge = judge or _Judge()
    embeddings = _TokenEmbeddings()
    return (
        QueryService(
            _Source(documents),
            embeddings,
            InMemoryVectorIndex(),
            actual_judge,
        ),
        actual_judge,
        embeddings,
    )


def test_ilgili_soru_kanonik_citation_ve_tazelik_fisi_doner():
    service, judge, _ = _service([_document()])

    result = service.ask("Scope drift sprintte var mı?")

    assert result.status == "answered"
    assert result.last_commit == "abc1234"
    assert result.confidence == "high"
    assert result.citations[0].ref == ".harness/scope/sprint-3.md#IS-1"
    assert result.citations[0].quote == "IS-1: Scope-drift bekçisini tamamla"
    assert result.citations[0].n == 1
    assert result.searched[0].model_dump() == {"type": "scope", "count": 1}
    assert len(judge.calls) == 1


def test_alakasiz_soru_judge_cagirmadan_durust_red_doner():
    service, judge, _ = _service(
        [
            _document(
                id="task:T-179",
                type="task",
                ref="T-179",
                quote="Postgres sürücüsünü ekle",
                text="Postgres migration ve pgvector sürücüsü",
            )
        ]
    )

    result = service.ask("Mobil oyun skorları nasıl?")

    assert result.status == "not_found"
    assert result.citations == []
    assert result.confidence == "low"
    assert result.nearest[0].ref == "T-179"
    assert judge.calls == []


def test_window_eski_eventi_retrievaldan_cikarir():
    now = datetime.now(timezone.utc)
    recent = _document(
        id="event:recent",
        type="event",
        ref="recent",
        quote="recent",
        text="deploy tamamlandı",
        occurred_at=now - timedelta(hours=2),
    )
    old = _document(
        id="event:old",
        type="event",
        ref="old",
        quote="old",
        text="deploy başladı",
        occurred_at=now - timedelta(days=2),
    )
    service, judge, _ = _service([old, recent])

    result = service.ask("son 24 saat deploy durumu")

    assert result.window == "son 24 saat"
    assert result.status == "answered"
    assert [document.ref for document in judge.calls[0][1]] == ["recent"]
    event_receipt = next(item for item in result.searched if item.type == "event")
    assert event_receipt.count == 1


def test_judge_retrieval_disinda_ref_uyduramaz():
    judge = _Judge(
        QueryJudgement(
            answer="Uydurma cevap [cite:T-999]",
            citation_refs=["T-999"],
            confidence="high",
        )
    )
    service, _, _ = _service([_document()], judge=judge)

    with pytest.raises(QueryJudgeError, match="retrieval dışında"):
        service.ask("Scope drift nedir?")


def test_judge_placeholder_olmadan_citation_veremez():
    ref = ".harness/scope/sprint-3.md#IS-1"
    judge = _Judge(
        QueryJudgement(
            answer="Kaynağı görünmeyen cevap",
            citation_refs=[ref],
            confidence="medium",
        )
    )
    service, _, _ = _service([_document()], judge=judge)

    with pytest.raises(QueryJudgeError, match="placeholder"):
        service.ask("Scope drift nedir?")


def test_judge_cevaba_bildirmedigi_ekstra_placeholder_sokamaz():
    ref = ".harness/scope/sprint-3.md#IS-1"
    judge = _Judge(
        QueryJudgement(
            answer=f"Doğru kaynak [cite:{ref}], gizli kaynak [cite:T-999]",
            citation_refs=[ref],
            confidence="medium",
        )
    )
    service, _, _ = _service([_document()], judge=judge)

    with pytest.raises(QueryJudgeError, match="placeholder"):
        service.ask("Scope drift nedir?")


def test_degisimeyen_corpus_ikinci_soruda_yeniden_indexlenmez():
    service, _, embeddings = _service([_document()])

    service.ask("Scope drift nedir?")
    service.ask("Scope drift var mı?")

    document_calls = [call for call in embeddings.calls if call[1] == "RETRIEVAL_DOCUMENT"]
    query_calls = [call for call in embeddings.calls if call[1] == "RETRIEVAL_QUERY"]
    assert len(document_calls) == 1
    assert len(query_calls) == 2


def test_corpus_okuma_hatasi_not_found_diye_gizlenmez():
    service = QueryService(
        _BrokenSource(),
        _TokenEmbeddings(),
        InMemoryVectorIndex(),
        _Judge(),
    )

    with pytest.raises(QueryRetrievalError, match="corpus'u okunamadı"):
        service.ask("Scope nedir?")


# ── #330: embeddings düşünce 503 değil, BEYANLI leksikal cevap ──────────────


class _DusenEmbeddings:
    """Kota/ağ arızasını taklit eder — `embed()` her çağrıda patlar."""

    def __init__(self) -> None:
        self.calls = 0

    def embed(self, texts: list[str], task_type: str) -> list[list[float]]:
        del texts, task_type
        self.calls += 1
        raise RuntimeError("429 kota doldu")


def test_embeddings_dustugunde_cevap_uretilir_ve_dusus_beyan_edilir():
    """MUTASYON KİLİDİ: `except Exception -> degraded` yerine eski
    `raise QueryRetrievalError` konursa bu test o istisnayla düşer — yani
    29 Tem'de canlıda ölçtüğümüz `503 query_retrieval_unavailable` geri gelir.
    `degraded` ataması düşürülürse ikinci assert düşer (sessiz düşüş = yasak).
    """
    embeddings = _DusenEmbeddings()
    judge = _Judge()
    service = QueryService(
        _Source([_document()]), embeddings, InMemoryVectorIndex(), judge
    )

    result = service.ask("Scope drift sprintte var mı?")

    assert embeddings.calls == 1
    # Leksikal yol cevabı TEK BAŞINA taşıdı — 503 yok, judge çağrıldı
    assert result.status == "answered"
    assert judge.calls != []
    assert result.degraded is not None
    assert "semantik retrieval kullanılamadı" in result.degraded
    assert "429 kota doldu" in result.degraded


def test_embeddings_saglamken_query_dusus_beyani_YOK():
    """MUTASYON KİLİDİ: `degraded` sabit metne bağlanırsa kırılır — sağlıklı
    turda kullanıcıya gereksiz "eksik sonuç" uyarısı basılmamalı."""
    service, _, _ = _service([_document()])

    result = service.ask("Scope drift sprintte var mı?")

    assert result.degraded is None

# ── #319 — QueryService.scan() (AskPage "Tarandı" şeridi, sıfır LLM) ────────


def test_scan_tum_tipleri_sifir_dahil_sayar():
    service, judge, embeddings = _service(
        [
            _document(),
            _document(id="task:T-1", type="task", ref="T-1", quote="t", text="t"),
            _document(id="task:T-2", type="task", ref="T-2", quote="t2", text="t2"),
        ]
    )

    result = service.scan()

    counts = {item.type: item.count for item in result.searched}
    assert counts == {"scope": 1, "task": 2, "decision": 0, "event": 0, "pr": 0}
    assert result.last_commit == "abc1234"
    # decision HER ZAMAN 0 çıkar (HarnessEventQuerySource decision okumuyor,
    # bkz. QueryScanResult docstring'i) — bu satır o olgunun regresyon kilidi:
    # biri corpus'a decision belgesi eklerse bu sayı artar ve test kırılır,
    # o zaman UI tarafındaki gate de gözden geçirilmeli.
    assert judge.calls == []
    assert embeddings.calls == []


def test_scan_embeddings_ve_judge_cagirmaz():
    # MUTASYON KİLİDİ: scan() içine yanlışlıkla self._retrieve(...)/judge_port
    # çağrısı eklenirse (örn. ask()'tan kopyala-yapıştır hatası) bu test kırılır
    # — scan LLM/embedding kotası YAKMAMALI (sayfa her açılışta çağrılabilir).
    service, judge, embeddings = _service([_document()])

    service.scan()

    assert judge.calls == []
    assert embeddings.calls == []


def test_scan_recent_events_yalniz_pencere_icindeki_event_pr_sayar():
    now = datetime.now(timezone.utc)
    recent_event = _document(
        id="event:recent",
        type="event",
        ref="recent",
        quote="recent",
        text="deploy tamamlandı",
        occurred_at=now - timedelta(hours=2),
    )
    old_event = _document(
        id="event:old",
        type="event",
        ref="old",
        quote="old",
        text="deploy başladı",
        occurred_at=now - timedelta(hours=72),
    )
    recent_pr = _document(
        id="pr:42",
        type="pr",
        ref="42",
        quote="PR",
        text="PR açıldı",
        occurred_at=now - timedelta(hours=10),
    )
    # MUTASYON KİLİDİ: tip filtresi (`document.type in ("event", "pr")`)
    # kaldırılırsa bu scope belgesi de (occurred_at YOK ama yine de) sayıma
    # girmeye ÇALIŞIR — occurred_at None olduğu için zaten elenir, ama tip
    # filtresi kaldırılıp occurred_at eklenseydi yanlış sayardı; bu yüzden
    # ayrı bir task belgesiyle de (occurred_at VERİLMİŞ) doğruluyoruz.
    scope_belgesi = _document()  # occurred_at yok → zaten elenir
    task_ile_occurred_at = _document(
        id="task:T-9",
        type="task",
        ref="T-9",
        quote="t",
        text="t",
        occurred_at=now - timedelta(hours=1),
    )
    service, judge, embeddings = _service(
        [recent_event, old_event, recent_pr, scope_belgesi, task_ile_occurred_at]
    )

    result = service.scan()

    assert result.recent_events == 2  # recent_event + recent_pr; old_event ve task DIŞARIDA
    assert result.recent_event_window_hours == 48
    assert judge.calls == []
    assert embeddings.calls == []


def test_scan_corpus_okuma_hatasi_gizlenmez():
    service = QueryService(
        _BrokenSource(),
        _TokenEmbeddings(),
        InMemoryVectorIndex(),
        _Judge(),
    )

    with pytest.raises(QueryRetrievalError, match="corpus'u okunamadı"):
        service.scan()


# ── #355: parmak izi kalıcılığı — "her restart tüm korpusu yeniden gömme" ────


def _belge(i: int) -> QueryDocument:
    return QueryDocument(
        id=f"scope:s{i}",
        type="scope",
        ref=f"sprint-3.md#IS-{i}",
        quote=f"scope drift maddesi {i}",
        text=f"scope drift maddesi {i}",
    )


def _servis(kaynak, gomme, indeks):
    return QueryService(
        source_port=kaynak,
        embeddings_port=gomme,
        vector_index=indeks,
        judge_port=_Judge(
            QueryJudgement(
                answer="cevap [cite:sprint-3.md#IS-0]",
                citation_refs=["sprint-3.md#IS-0"],
                confidence="low",
            )
        ),
    )


def _gomulen_belge_sayisi(gomme) -> int:
    """Yalnız BELGE gömmeleri (soru gömmesi her sorguda 1 tane, o hariç)."""
    return sum(len(texts) for texts, task in gomme.calls if task == "RETRIEVAL_DOCUMENT")


def test_yeniden_baslatmada_korpus_TEKRAR_gomulmez():
    """#355 — süreç yeniden başlayınca değişmemiş belgeler yeniden gömülMEZ.

    Canlıda ölçülen etki (30 Tem 2026): `_indexed_hashes` bellekte, vektörler
    kalıcıydı. Her deploy TÜM korpusu (~236 belge) yeniden gömüyordu; Gemini'nin
    ücretsiz günlük embed kotası 1000 olduğu için birkaç deploy onu bitiriyor ve
    Ask günün geri kalanında semantik aramasız kalıyordu — üç örnek sorunun
    ikisi `not_found` döndü.

    Burada "yeniden başlatma" = AYNI kalıcı indeksle YENİ bir QueryService.

    MUTASYON KİLİDİ: `_index_documents`'tan `self._parmak_izlerini_yukle()`
    çağrısını sil -> ikinci servis her şeyi yeniden gömer, bu test kırılır.
    """
    belgeler = [_belge(i) for i in range(4)]
    kaynak = _Source(belgeler)
    indeks = InMemoryVectorIndex()  # süreçler ARASI kalıcılığı temsil eder

    ilk_gomme = _TokenEmbeddings()
    _servis(kaynak, ilk_gomme, indeks).ask("scope drift")
    assert _gomulen_belge_sayisi(ilk_gomme) == 4

    # --- süreç yeniden başladı: yeni servis, AYNI indeks ---
    ikinci_gomme = _TokenEmbeddings()
    _servis(kaynak, ikinci_gomme, indeks).ask("scope drift")
    assert _gomulen_belge_sayisi(ikinci_gomme) == 0, (
        "değişmemiş belgeler yeniden gömüldü — kota boşa yanıyor"
    )


def test_DEGISEN_belge_yeniden_baslatmadan_sonra_da_gomulur():
    """Kalıcılık, değişikliği KAÇIRMA pahasına gelmemeli.

    MUTASYON KİLİDİ: `upsert`'teki `"fingerprint": fingerprint` alanını sil ->
    hiçbir parmak izi kaydedilmez, ilk test kırılır; parmak izini SABİT bir
    değere çevir -> bu test kırılır.
    """
    belgeler = [_belge(0), _belge(1)]
    kaynak = _Source(belgeler)
    indeks = InMemoryVectorIndex()
    _servis(kaynak, _TokenEmbeddings(), indeks).ask("scope drift")

    # Belgenin METNİ değişti (aynı id, yeni içerik)
    kaynak.corpus.documents[1] = QueryDocument(
        id="scope:s1",
        type="scope",
        ref="sprint-3.md#IS-1",
        quote="postgres deploy maddesi",
        text="postgres deploy maddesi",
    )
    gomme = _TokenEmbeddings()
    _servis(kaynak, gomme, indeks).ask("scope drift")
    assert _gomulen_belge_sayisi(gomme) == 1


class _ParmakIziPatlayanIndeks(InMemoryVectorIndex):
    def fingerprints(self) -> dict[str, str]:
        raise RuntimeError("indeks okunamadı")


def test_parmak_izi_okunamazsa_SEMANTIK_DUSMUS_gibi_raporlanmaz():
    """Parmak izi bir OPTİMİZASYONdur, doğruluk kaynağı değil.

    İnce ayrım ve testin ASIL konusu: parmak izi okunamadığında semantik
    retrieval HÂLÂ ÇALIŞIYOR (yalnız fazladan gömme yapılır). Bu hatayı
    yukarı kaçırırsak `_retrieve`'in genel `except`'ine düşer ve kullanıcıya
    "semantik retrieval kullanılamadı" diye YANLIŞ bir düşüş bildirilir —
    doğru çalışan bir yolu bozuk gösteren bir teşhis, hiç teşhis
    koymamaktan kötüdür.

    (İlk yazdığım hâli `status in (...)` kontrol ediyordu ve mutasyonla
    kırılmadı: hata zaten yakalanıp cevap üretiliyordu. Ayrım `degraded`de.)

    MUTASYON KİLİDİ: `_parmak_izlerini_yukle`'deki `except Exception`'ı
    daralt (ör. `except ZeroDivisionError`) -> RuntimeError yukarı kaçar,
    `degraded` dolar, bu test kırılır.
    """
    kaynak = _Source([_belge(0)])
    sonuc = _servis(kaynak, _TokenEmbeddings(), _ParmakIziPatlayanIndeks()).ask("scope drift")
    assert sonuc.degraded is None, (
        "parmak izi okuma hatası, çalışan semantik retrieval'ı düşmüş gösteriyor"
    )

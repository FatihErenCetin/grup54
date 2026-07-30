from __future__ import annotations

import pytest
from pathlib import Path
from datetime import datetime, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from ensemble.integrations.query_source import HarnessEventQuerySource
from ensemble.models import NormalizedEvent
from ensemble.store.models import Base, EventRow
from ensemble_shared.harness import FileHarnessPort, HarnessError


class _Harness:
    def read_scope(self, sprint: str) -> dict:
        assert sprint == "3"
        return {
            "path": ".harness/scope/sprint-3.md",
            "body": "G-1: Koordinasyonu görünür kıl",
            "goals": ["IS-1: Scope-drift bekçisini tamamla"],
            "non_goals": ["NG-1: OAuth yazma"],
        }

    def read_tasks(self) -> list[dict]:
        return [
            {
                "task_id": "T-58",
                "title": "Ask endpoint'ini yaz",
                "body": "RAG ve citations",
            }
        ]

    def read_active(self) -> list[dict]:
        return [
            {
                "task_id": "T-58",
                "intent": "QueryService geliştir",
                "module": "engine/query.py",
                "branch": "T-58-query-rag",
            }
        ]

    def read_decisions(self) -> list[dict]:
        return [
            {
                "id": "D-46",
                "title": "Fly.io terk edildi — backend VDS'e taşındı",
                "body": "## Karar\n\nFly.io bırakıldı; backend kendi VDS'imizde.",
                "path": ".harness/decisions/D-46-vds.md",
            },
            {
                # Başlıksız kayıt: alıntı gövdenin ilk anlamlı satırından
                # SEÇİLİR, uydurma özet ÜRETİLMEZ.
                "id": "D-47",
                "body": "# Başlık satırı\n\nİkinci satır.",
                "path": ".harness/decisions/D-47-x.md",
            },
        ]


def test_source_harness_ve_eventleri_citation_corpusuna_cevirir(tmp_path):
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine)
    with sessions() as session:
        session.add(
            EventRow.from_domain(
                NormalizedEvent(
                    id="commit:abc1234",
                    type="commit",
                    actor="semih",
                    branch="T-58-query-rag",
                    files=["src/backend/ensemble/engine/query.py"],
                    ts=datetime(2026, 7, 21, 12, 0, tzinfo=timezone.utc),
                    ref="abc1234",
                ),
                repo_full_name="FatihErenCetin/grup54",
            )
        )
        session.commit()

    source = HarnessEventQuerySource(
        _Harness(),
        session_factory=sessions,
        repo_root=tmp_path,
        github_owner="FatihErenCetin",
        github_repo="grup54",
        repo_full_name="FatihErenCetin/grup54",
    )

    corpus = source.load_query_corpus()

    assert corpus.last_commit == "abc1234"
    assert {document.type for document in corpus.documents} == {
        "scope",
        "task",
        "decision",
        "event",
    }
    task = next(document for document in corpus.documents if document.ref == "T-58")
    assert "QueryService geliştir" in task.text
    assert task.url.endswith("/issues/58")
    scope = next(document for document in corpus.documents if document.ref.endswith("#IS-1"))
    assert scope.quote == "IS-1: Scope-drift bekçisini tamamla"
    event = next(document for document in corpus.documents if document.id == "commit:abc1234")
    assert event.url.endswith("/commit/abc1234")

    # #354 — karar kaydı korpusa GİRER. Bu olmadığında ürün, kararla
    # çürütülmüş eski görev metnini hâlâ geçerliymiş gibi cevaplıyordu
    # (canlıda ölçüldü: "Hosted demo kararı neydi?" -> "Fly backend").
    karar = next(document for document in corpus.documents if document.ref == "D-46")
    assert karar.type == "decision"
    assert karar.quote == "Fly.io terk edildi — backend VDS'e taşındı"
    assert "VDS" in karar.text
    assert karar.url.endswith("/.harness/decisions/D-46-vds.md")
    # Başlıksız kayıtta alıntı gövdeden seçilir (markdown başlık işareti atılır)
    basliksiz = next(document for document in corpus.documents if document.ref == "D-47")
    assert basliksiz.quote == "Başlık satırı"


class _MissingHarness:
    def read_scope(self, sprint: str) -> dict:
        raise HarnessError(sprint)

    def read_tasks(self) -> list[dict]:
        raise HarnessError("tasks")

    def read_active(self) -> list[dict]:
        raise HarnessError("active")

    def read_decisions(self) -> list[dict]:
        raise HarnessError("decisions")


def test_source_veri_yokken_uydurma_dokuman_uretmez(tmp_path):
    source = HarnessEventQuerySource(_MissingHarness(), repo_root=tmp_path)

    corpus = source.load_query_corpus()

    assert corpus.documents == []
    assert corpus.last_commit == "unavailable"
    assert corpus.events_truncated is False


def _olay_dolu_sessions(adet: int):
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine)
    with sessions() as session:
        for index in range(adet):
            session.add(
                EventRow.from_domain(
                    NormalizedEvent(
                        id=f"commit:c{index:04d}",
                        type="commit",
                        actor="fatih",
                        branch="T-319-ask-activity-paritesi",
                        files=["src/backend/ensemble/engine/query.py"],
                        ts=datetime(2026, 7, 21, 12, 0, tzinfo=timezone.utc),
                        ref=f"c{index:04d}",
                    ),
                    repo_full_name="FatihErenCetin/grup54",
                )
            )
        session.commit()
    return sessions


def test_source_olay_cekimi_limite_dayandiysa_kesme_bildirilir(tmp_path):
    """#322 review (Semih): `.limit(event_limit)` tam dolduysa DB'de daha
    eski olaylar KALMIŞ olabilir — bunu yalnız kaynak bilir.

    MUTASYON KİLİDİ: `events_truncated` sabit `False` yapılırsa (ya da
    `len(rows) >= self.event_limit` karşılaştırması düşerse) bu test kırılır;
    `QueryService.scan()` de kesmeyi göremediği için "son 48 saatte N olay"
    yine eksik sayıyı KESİNMİŞ gibi basardı."""
    sessions = _olay_dolu_sessions(3)
    source = HarnessEventQuerySource(
        _MissingHarness(),
        session_factory=sessions,
        repo_root=tmp_path,
        repo_full_name="FatihErenCetin/grup54",
        event_limit=3,
    )

    corpus = source.load_query_corpus()

    assert len([d for d in corpus.documents if d.type == "event"]) == 3
    assert corpus.events_truncated is True


def test_source_olay_cekimi_limitin_altinda_kalirsa_kesme_yok(tmp_path):
    """Limitin altında kaldıysa DB tükendi demektir → kesme YOK.

    MUTASYON KİLİDİ: `events_truncated` sabit `True` yapılırsa kırılır —
    o durumda küçük/normal projelerde şerit sürekli gereksiz `N+` basardı."""
    sessions = _olay_dolu_sessions(2)
    source = HarnessEventQuerySource(
        _MissingHarness(),
        session_factory=sessions,
        repo_root=tmp_path,
        repo_full_name="FatihErenCetin/grup54",
        event_limit=5,
    )

    corpus = source.load_query_corpus()

    assert len([d for d in corpus.documents if d.type == "event"]) == 2
    assert corpus.events_truncated is False


class _KararsizHarness:
    """`read_decisions` TAŞIMAYAN port — protokolün #354 öncesi hâli."""

    def read_scope(self, sprint: str) -> dict:
        raise HarnessError(sprint)

    def read_tasks(self) -> list[dict]:
        return []

    def read_active(self) -> list[dict]:
        return []


def test_read_decisions_TASIMAYAN_port_sessizce_bos_donmez(tmp_path):
    """Eksik port metodu = BİZİM hatamız → gürültülü patlar.

    Neden bu testin kendisi #354'ün özeti: bug tam olarak "kaynak sessizce
    boş kalıyor, makbuz `decision: 0` basıyor, kimse fark etmiyor" idi. Eğer
    `_decision_documents` `AttributeError`'ı yakalayıp `[]` dönseydi, aynı
    sessizliği bu sefer BİLEREK inşa etmiş olurduk.

    Kural (D-63/#330 ile aynı): sağlayıcı arızasında yumuşa (`HarnessError`
    -> boş liste), KENDİ sözleşme ihlalimizde patla.

    MUTASYON KİLİDİ: `_decision_documents`'a `except AttributeError: return []`
    ekle -> bu test kırılır.
    """
    source = HarnessEventQuerySource(_KararsizHarness(), repo_root=tmp_path)
    with pytest.raises(AttributeError):
        source.load_query_corpus()


def test_gercek_harness_karar_kayitlarini_korpusa_verir():
    """Kurgu değil GERÇEK `.harness/decisions/` — canlıda kırılan yol buydu.

    Sahte port'la yazılmış bir test bu bug'ı yakalayamazdı: sahte zaten
    istediğini döndürür. Kırılan halka gerçek `FileHarnessPort`'un
    `decisions/` klasörünü hiç okumamasıydı.
    """
    kok = Path(__file__).resolve().parents[2]
    port = FileHarnessPort(kok)
    kararlar = port.read_decisions()
    assert kararlar, "depo .harness/decisions/ altında karar kaydı taşıyor"
    assert all(k.get("id", "").startswith("D-") for k in kararlar)

    source = HarnessEventQuerySource(port, sprint="3", repo_root=kok)
    belgeler = source.load_query_corpus().documents
    kararBelgeleri = [d for d in belgeler if d.type == "decision"]
    assert len(kararBelgeleri) == len(kararlar)
    # README.md veri DEĞİL — okuyucuya sızmamalı (NON_DATA_FILENAMES)
    assert all(d.ref.startswith("D-") for d in kararBelgeleri)

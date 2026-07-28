"""Projector testleri (#47) — D-55 (İş 3, GOREV 3/4) sonrası.

`project_events` artık durum TAHMİN ETMEZ (eski branch-tabanlı `commit ->
in_progress` / `pr -> in_review` çıkarımı kaldırıldı) — yalnız event audit log'u
(EventRow) + presence senkronu yapar. Durum geçişleri `apply_transitions`
(GERÇEK GitHub olayından türetilmiş `StatusTransition`, engine/status_rules.py
İş 1) ile uygulanır ve `task_status_events`'e (İş 2, store/rebuild.py)
yazılır — bkz. `test_ayni_gecis_tekrar_uygulaninca_unchanged_sayilir`
(redelivery güvenliği) ve `test_eslesmeyen_task_unmatched_sayilir`
(D-53 dersi: sessizce atlanan bir task artık DOĞRU sayılır, yalancı sayaç yok).
"""

from datetime import datetime
from unittest.mock import MagicMock

from ensemble.config import Settings
from ensemble.engine.projector import Projector
from ensemble.engine.status_rules import StatusTransition
from ensemble.models import NormalizedEvent
from ensemble.store.engine import get_engine, get_session_factory
from ensemble.store.models import (
    DEFAULT_REPO_FULL_NAME,
    Base,
    EventRow,
    PresenceRow,
    TaskProjectionRow,
    TaskStatusEventRow,
)
from ensemble_shared.harness import HarnessPort

_REPO = DEFAULT_REPO_FULL_NAME


def _make_session():
    settings = Settings(DATABASE_URL="sqlite:///:memory:")
    engine = get_engine(settings)
    Base.metadata.create_all(engine)
    session_factory = get_session_factory(engine)
    return session_factory()


def _seed_task(session, task_id: str, status: str = "todo", title: str = "Görev") -> TaskProjectionRow:
    # Projector varsayılan repo_full_name'i (DEFAULT_REPO_FULL_NAME) kullanır
    # (bu testler Projector(session, harness) — repo_full_name'siz — çağırıyor)
    # — tohum satır AYNI kiracıyla açılmalı, yoksa `session.get` eşleşmez.
    task = TaskProjectionRow(
        task_id=task_id, repo_full_name=_REPO, title=title, status=status, seed_status=status
    )
    session.add(task)
    session.commit()
    return task


def _transition(
    task_id: str,
    status: str,
    *,
    source_event_id: str,
    ts: datetime | None = None,
    reason: str = "test",
    resets: bool = False,
) -> StatusTransition:
    return StatusTransition(
        task_id=task_id,
        status=status,
        ts=ts or datetime(2026, 7, 25, 9, 0, 0),
        source_event_id=source_event_id,
        reason=reason,
        resets=resets,
    )


# --- project_events: yalnız audit + presence, durum TAHMİN ETMEZ ---


def test_project_events_durum_tahmin_etmez_yalniz_audit_ve_presence_yapar():
    session = _make_session()
    _seed_task(session, "T-47", status="todo")

    # Mock harness — active.schema.json alan adlari: task_id, updated_at
    # (task/since DEGIL; updated_at semada string zorunlu).
    mock_harness = MagicMock(spec=HarnessPort)
    mock_harness.read_active.return_value = [
        {"handle": "enes", "task_id": "T-47", "updated_at": "2026-07-11T10:00:00"}
    ]

    commit_event = NormalizedEvent(
        id="c1",
        type="commit",
        actor="enes",
        branch="T-47-yeni-ozellik",
        files=["test.py"],
        ts=datetime.now(),
        ref="sha123",
    )
    pr_event = NormalizedEvent(
        id="pr1", type="pr", actor="esma", branch="T-47-yeni-ozellik", files=[], ts=datetime.now(), ref="47"
    )

    projector = Projector(session, mock_harness)

    res1 = projector.project_events([commit_event])
    assert res1 == {"events_processed": 1, "presence_synced": 1}
    # D-55: branch-tabanlı tahmin KALDIRILDI — commit event'i durumu ETKİLEMEZ.
    t1 = session.query(TaskProjectionRow).filter_by(task_id="T-47").first()
    assert t1.status == "todo"

    res2 = projector.project_events([pr_event])
    assert res2 == {"events_processed": 1, "presence_synced": 1}
    # pr event'i de aynı şekilde durumu ETKİLEMEZ (o iş artık apply_transitions'ta).
    t2 = session.query(TaskProjectionRow).filter_by(task_id="T-47").first()
    assert t2.status == "todo"

    assert session.query(EventRow).count() == 2
    assert session.query(PresenceRow).count() == 1
    assert session.query(TaskStatusEventRow).count() == 0

    p = session.query(PresenceRow).first()
    assert p.handle == "enes"
    assert p.task == "T-47"

    session.close()


def test_project_events_bos_liste_sifir_sayar():
    session = _make_session()
    mock_harness = MagicMock(spec=HarnessPort)
    mock_harness.read_active.return_value = []

    result = Projector(session, mock_harness).project_events([])
    assert result == {"events_processed": 0, "presence_synced": 0}
    session.close()


# --- apply_transitions: gerçek durum uygulaması (D-55, İş 3) ---


def test_apply_transitions_gecerli_task_statusu_gunceller():
    session = _make_session()
    _seed_task(session, "T-158", status="todo")
    mock_harness = MagicMock(spec=HarnessPort)
    projector = Projector(session, mock_harness)

    transition = _transition(
        "T-158", "done", source_event_id="issue:158:2026-07-25T09:00:00Z", reason="issue_closed"
    )
    result = projector.apply_transitions([transition])

    assert result == {"applied": 1, "unchanged": 0, "unmatched": 0}
    task = session.query(TaskProjectionRow).filter_by(task_id="T-158").first()
    assert task.status == "done"
    assert task.last_event_id == "issue:158:2026-07-25T09:00:00Z"
    assert task.last_transition_at == transition.ts
    assert session.query(TaskStatusEventRow).count() == 1
    session.close()


def test_eslesmeyen_task_unmatched_sayilir(caplog):
    """.harness'te (task_projection'da) karşılığı olmayan bir task_id için
    `applied` SIFIR, `unmatched` BİR olmalı — eski kod bu satırı sessizce
    atlayıp yine de "tasks_updated" sayacını artırıyordu (D-53'ün sayaç
    hâlindeki tekrarı, #5 fail-open). Bu test bugünkü (düzeltilmiş) davranışta
    YEŞİL; MUTASYON KILIDI (apply_transitions dönüşünü {"applied": len(transitions)}
    yapan mutasyon) bu testi KIRMIZI yapmalı.
    """
    session = _make_session()
    mock_harness = MagicMock(spec=HarnessPort)
    projector = Projector(session, mock_harness)

    transition = _transition(
        "T-999", "done", source_event_id="issue:999:2026-07-25T09:00:00Z", reason="issue_closed"
    )
    with caplog.at_level("WARNING"):
        result = projector.apply_transitions([transition])

    assert result == {"applied": 0, "unchanged": 0, "unmatched": 1}
    # Eşleşmeyen task_id ADIYLA log'lanır (sessiz atlama YOK).
    assert any("T-999" in record.message for record in caplog.records)
    # Kalıcı günlük (task_status_events) orphan olsa bile satırı KAYBETMEZ —
    # .harness'e task sonradan eklenirse rebuild_projection bunu katlayabilir.
    assert session.query(TaskStatusEventRow).count() == 1
    session.close()


def test_apply_transitions_bos_liste_erken_doner():
    session = _make_session()
    mock_harness = MagicMock(spec=HarnessPort)
    result = Projector(session, mock_harness).apply_transitions([])
    assert result == {"applied": 0, "unchanged": 0, "unmatched": 0}
    session.close()


def test_ayni_gecis_tekrar_uygulaninca_unchanged_sayilir():
    """GitHub redelivery güvenliği: aynı (source_event_id, task_id) ikinci kez
    gelirse `task_status_events` ÇOĞALMAZ ve board (status) DEĞİŞMEZ — ikinci
    çağrı `applied=0, unchanged=1` döner."""
    session = _make_session()
    _seed_task(session, "T-158", status="todo")
    projector = Projector(session, MagicMock(spec=HarnessPort))

    transition = _transition(
        "T-158", "done", source_event_id="issue:158:2026-07-25T09:00:00Z", reason="issue_closed"
    )

    first = projector.apply_transitions([transition])
    assert first == {"applied": 1, "unchanged": 0, "unmatched": 0}

    second = projector.apply_transitions([transition])
    assert second == {"applied": 0, "unchanged": 1, "unmatched": 0}

    assert session.query(TaskStatusEventRow).count() == 1
    task = session.query(TaskProjectionRow).filter_by(task_id="T-158").first()
    assert task.status == "done"
    session.close()


def test_apply_transitions_birden_fazla_task_bagimsiz_sayilir():
    """Tek çağrıda hem eşleşen hem eşleşmeyen task_id birlikte gelebilir
    (örn. bir PR gövdesindeki birden fazla `Closes #N`) — her biri BAĞIMSIZ
    sayılır, biri diğerinin sayacını etkilemez."""
    session = _make_session()
    _seed_task(session, "T-200", status="in_progress")
    projector = Projector(session, MagicMock(spec=HarnessPort))

    matched = _transition("T-200", "done", source_event_id="pr:1:2026-07-25T11:00:00Z", reason="pr_merged")
    unmatched = _transition("T-201", "done", source_event_id="pr:1:2026-07-25T11:00:00Z", reason="pr_merged")

    result = projector.apply_transitions([matched, unmatched])
    assert result == {"applied": 1, "unchanged": 0, "unmatched": 1}
    assert session.query(TaskProjectionRow).filter_by(task_id="T-200").first().status == "done"
    assert session.query(TaskStatusEventRow).count() == 2
    session.close()


def test_apply_transitions_geriye_gecis_unchanged_sayilir_ve_statuyu_bozmaz():
    """`resets=False` bir geçiş mevcut ranktan GERİ ise (next_status/fold_status
    monotonluk kuralı) status DEĞİŞMEZ — bu `unchanged` sayılır, `applied` DEĞİL
    (yalancı sayaç bu ayrımı kaçırıyordu)."""
    session = _make_session()
    _seed_task(session, "T-99", status="in_review")
    projector = Projector(session, MagicMock(spec=HarnessPort))

    # in_review üzerine "eski" bir push (in_progress) geriye OYNAMAMALI.
    stale_push = _transition(
        "T-99", "in_progress", source_event_id="commit:abc123", reason="push",
        ts=datetime(2026, 7, 20, 8, 0, 0),
    )
    result = projector.apply_transitions([stale_push])

    assert result == {"applied": 0, "unchanged": 1, "unmatched": 0}
    task = session.query(TaskProjectionRow).filter_by(task_id="T-99").first()
    assert task.status == "in_review"
    session.close()

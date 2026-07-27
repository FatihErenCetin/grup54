"""Kalıcı durum günlüğü (task_status_events) + idempotent rebuild (D-55, İş 2).

Bulunan çelişki: rebuild_projection() task_projection'ı SİLİP yalnızca
.harness'ten yeniden kuruyordu — webhook'un yazdığı GERÇEK GitHub durumu ilk
rebuild'de KAYBOLUYORDU. Bu dosya o çelişkiyi test_rebuild_ingest_edilmis_durumu_korur
ile KİLİTLER: seed .harness'te "todo" ama GitHub'dan gelen bir "issue_closed"
geçişi "done" ise, rebuild sonrası satır "done" KALMALI.
"""

from datetime import datetime
from unittest.mock import MagicMock

from ensemble.store.engine import get_engine, get_session_factory
from ensemble.store.models import Base, TaskProjectionRow, TaskStatusEventRow
from ensemble.store.rebuild import append_status_events, fold_status, rebuild_projection
from ensemble.config import Settings
from ensemble_shared.harness import HarnessPort


def _fresh_session():
    """Her testte izole bir in-memory SQLite oturumu."""
    settings = Settings(DATABASE_URL="sqlite:///:memory:")
    engine = get_engine(settings)
    Base.metadata.create_all(engine)
    return get_session_factory(engine)()


def _mock_harness(tasks=None, actives=None) -> HarnessPort:
    harness = MagicMock(spec=HarnessPort)
    harness.read_tasks.return_value = tasks or []
    harness.read_active.return_value = actives or []
    return harness


# ---------------------------------------------------------------------------
# Ana kilit: rebuild ingest edilmiş (webhook'tan gelen) durumu KORUMALI.
# ---------------------------------------------------------------------------


def test_rebuild_ingest_edilmis_durumu_korur():
    """BUGÜNKÜ KOD (fold bloğu olmadan) bu testte KIRMIZI olur: T-158 tohumu
    'todo' ama issue #258 kapanınca üretilen 'issue_closed -> done' geçişi
    task_status_events'te varken, eski rebuild bu satırı sessizce yok sayıp
    kartı 'todo'da bırakıyordu. Yeni davranış: satır 'done' KALIR."""
    session = _fresh_session()
    harness = _mock_harness(tasks=[{"task_id": "T-158", "title": "Health zinciri", "status": "todo"}])

    event = TaskStatusEventRow(
        source_event_id="issue-258-closed",
        task_id="T-158",
        status="done",
        ts=datetime(2026, 7, 25, 12, 0),
        reason="issue_closed",
    )
    inserted = append_status_events(session, [event])
    session.commit()
    assert inserted == 1

    res = rebuild_projection(session, harness)

    row = session.query(TaskProjectionRow).filter_by(task_id="T-158").first()
    assert row is not None
    assert row.status == "done"
    assert row.seed_status == "todo"
    assert row.last_event_id == "issue-258-closed"
    assert row.last_transition_at == datetime(2026, 7, 25, 12, 0)
    assert res["transitions_applied"] == 1
    assert res["orphan_transitions"] == 0


def test_rebuild_projection_idempotent():
    """rebuild_projection art arda İKİ kez çağrıldığında task_projection
    içeriği bit-bit aynı olmalı (status + last_transition_at + last_event_id)
    — task_status_events rebuild tarafından SİLİNMEZ, her çağrı aynı biriken
    günlüğü yeniden katlar (fold)."""
    session = _fresh_session()
    harness = _mock_harness(tasks=[{"task_id": "T-1", "title": "A", "status": "backlog"}])

    event = TaskStatusEventRow(
        source_event_id="push-1",
        task_id="T-1",
        status="in_progress",
        ts=datetime(2026, 7, 20, 9, 0),
        reason="push",
    )
    append_status_events(session, [event])
    session.commit()

    res1 = rebuild_projection(session, harness)
    row1 = session.query(TaskProjectionRow).filter_by(task_id="T-1").first()
    snapshot = (row1.status, row1.last_transition_at, row1.last_event_id)

    res2 = rebuild_projection(session, harness)
    row2 = session.query(TaskProjectionRow).filter_by(task_id="T-1").first()

    assert (row2.status, row2.last_transition_at, row2.last_event_id) == snapshot
    assert res1 == res2
    assert set(res1.keys()) >= {"tasks", "presence", "transitions_applied"}


def test_yetim_gecis_kaybolmaz_ama_kart_uydurulmaz():
    """.harness'te karşılığı olmayan bir task_id için geçiş geldiğinde: satır
    task_status_events'e YAZILIR (kaybolmaz) ama task_projection'a yeni kart
    UYDURULMAZ; rebuild bunu orphan_transitions olarak sayar (sessiz yutma yok)."""
    session = _fresh_session()
    harness = _mock_harness(tasks=[])  # .harness'te HİÇ task yok

    event = TaskStatusEventRow(
        source_event_id="issue-999-closed",
        task_id="T-999",
        status="done",
        ts=datetime(2026, 7, 25, 12, 0),
        reason="issue_closed",
    )
    append_status_events(session, [event])
    session.commit()

    res = rebuild_projection(session, harness)

    assert res["orphan_transitions"] == 1
    assert res["transitions_applied"] == 1
    assert session.query(TaskProjectionRow).filter_by(task_id="T-999").count() == 0
    # Satır kendisi hâlâ orada — kaybolmadı.
    assert session.query(TaskStatusEventRow).filter_by(task_id="T-999").count() == 1


def test_seed_degisse_de_fold_sonucu_korunur():
    """.harness dosyası elle düzenlenip tohum değişirse (backlog -> todo)
    rebuild yeni tohum üzerinden AYNI geçişleri katlar; fold sonucu (done)
    değişmez."""
    session = _fresh_session()
    harness = _mock_harness(tasks=[{"task_id": "T-5", "title": "X", "status": "backlog"}])

    event = TaskStatusEventRow(
        source_event_id="issue-5-closed",
        task_id="T-5",
        status="done",
        ts=datetime(2026, 7, 22, 8, 0),
        reason="issue_closed",
    )
    append_status_events(session, [event])
    session.commit()

    rebuild_projection(session, harness)
    row = session.query(TaskProjectionRow).filter_by(task_id="T-5").first()
    assert row.status == "done"
    assert row.seed_status == "backlog"

    # Tohum elle değişti: backlog -> todo.
    harness.read_tasks.return_value = [{"task_id": "T-5", "title": "X", "status": "todo"}]
    rebuild_projection(session, harness)
    row = session.query(TaskProjectionRow).filter_by(task_id="T-5").first()
    assert row.seed_status == "todo"
    assert row.status == "done"  # fold sonucu hâlâ done


# ---------------------------------------------------------------------------
# Mutasyon kilidi #2: bileşik PK (source_event_id, task_id).
# ---------------------------------------------------------------------------


def test_ayni_olay_iki_kez_yazilinca_cogalmaz():
    """Retry-güvenliği: aynı PR hem branch'ten (T-10) hem gövdedeki
    'Closes #20' referansından (T-20) İKİ farklı task için geçiş üretir — TEK
    event (source_event_id='pr-99'), İKİ satır. GitHub aynı webhook'u YENİDEN
    teslim ederse (retry) satırlar ÇOĞALMAZ.

    PK yalnız source_event_id'ye indirgenirse (mutasyon): ikinci task'ın
    satırı session.get() tarafından "zaten var" sanılıp hiç eklenmez —
    inserted_first 2 yerine 1 olur ve bu test KIRMIZI olur.
    """
    session = _fresh_session()
    ts = datetime(2026, 7, 20, 10, 0)

    def _build_events():
        return [
            TaskStatusEventRow(
                source_event_id="pr-99", task_id="T-10", status="in_review", ts=ts, reason="pr_opened"
            ),
            TaskStatusEventRow(
                source_event_id="pr-99",
                task_id="T-20",
                status="in_review",
                ts=ts,
                reason="pr_opened_closes_ref",
            ),
        ]

    inserted_first = append_status_events(session, _build_events())
    session.commit()
    assert inserted_first == 2

    # Webhook retry: aynı payload'dan üretilen geçişler İKİNCİ kez yazılır.
    inserted_retry = append_status_events(session, _build_events())
    session.commit()
    assert inserted_retry == 0

    assert session.query(TaskStatusEventRow).filter_by(source_event_id="pr-99").count() == 2
    assert (
        session.query(TaskStatusEventRow)
        .filter_by(source_event_id="pr-99", task_id="T-10")
        .count()
        == 1
    )
    assert (
        session.query(TaskStatusEventRow)
        .filter_by(source_event_id="pr-99", task_id="T-20")
        .count()
        == 1
    )

    # Fold sonucu retry'den etkilenmez.
    rows = session.query(TaskStatusEventRow).filter_by(task_id="T-10").all()
    status, _, _ = fold_status("todo", rows)
    assert status == "in_review"


# ---------------------------------------------------------------------------
# Mutasyon kilidi #3: fold sıralaması (ts, source_event_id) — insertion sırası DEĞİL.
# ---------------------------------------------------------------------------


def test_gec_gelen_eski_olay_durumu_bozmaz():
    """Ağ gecikmesiyle GEÇ gelen ama ts'i ESKİ olan bir olay (ör. bir push
    webhook'u gecikip 5 Temmuz'daki merge'den SONRA DB'ye yazılır), fold
    sıralaması ts'e göre yapıldığı için sonucu BOZMAZ — kronolojik olarak
    SONRAKİ olay (merge -> done) kazanır.

    fold sıralaması ts yerine ekleme/liste sırasına alınırsa (mutasyon):
    aşağıdaki [later, early] sırası ile iterasyon early'i SON uygular ve
    sonuç 'in_progress' olur — bu test KIRMIZI olur.
    """
    seed = "todo"
    early_push = TaskStatusEventRow(
        source_event_id="push-1",
        task_id="T-1",
        status="in_progress",
        ts=datetime(2026, 7, 1, 9, 0),
        reason="push",
    )
    later_merge = TaskStatusEventRow(
        source_event_id="pr-merge-1",
        task_id="T-1",
        status="done",
        ts=datetime(2026, 7, 5, 9, 0),
        reason="pr_merged",
    )

    # DB'ye YAZILMA sırası: merge önce commit edilmiş, push (ağ sorunuyla)
    # SONRA/GEÇ ulaşmış — ama ts'i push'un daha ESKİ.
    rows_in_arrival_order = [later_merge, early_push]

    status, last_ts, last_event_id = fold_status(seed, rows_in_arrival_order)

    assert status == "done"
    assert last_ts == datetime(2026, 7, 5, 9, 0)
    assert last_event_id == "pr-merge-1"


def test_rebuild_RADARIN_degil_GECMISIN_limitini_kullanir():
    """#280 kilidi: `main()` `GITHUB_HISTORY_LIMIT` okumali, radarin
    `GITHUB_BACKFILL_LIMIT`'ini DEGIL.

    Neden ayrilar: radar adaylari CIFT olarak uretir (kare buyur, her cift
    bir judge cagrisi) -- 50'de tutulmasi kota icin sart. Projeksiyon ise
    duz liste yazar, maliyeti dogrusal. Ikisi ayni sayiyi paylastiginda
    guvenli-kucuk radar limiti akisin gecmisini kirpiyordu: repo 19
    Haziran'dan beri ~250 commit uretmisken Activity yalniz 21 Temmuz'a
    kadar geri gidiyordu (olculdu, 2026-07-27).

    MUTASYON: rebuild'de HISTORY -> BACKFILL yapilirsa bu test kirilir.
    """
    import inspect

    from ensemble.store import rebuild as rebuild_modulu

    kaynak = inspect.getsource(rebuild_modulu)
    assert "settings.GITHUB_HISTORY_LIMIT" in kaynak, (
        "rebuild `GITHUB_HISTORY_LIMIT` okumali -- radar limitini paylasirsa "
        "Activity/Graph gecmisi radar guvenligi ugruna kirpilir"
    )
    assert "backfill_limit=settings.GITHUB_BACKFILL_LIMIT" not in kaynak, (
        "rebuild radarin backfill limitine geri dondurulmus"
    )

    # Iki ayar GERCEKTEN ayri olmali (ayni degere sabitlenirse ayrim sozde kalir).
    s = Settings()
    assert s.GITHUB_HISTORY_LIMIT > s.GITHUB_BACKFILL_LIMIT, (
        f"gecmis limiti ({s.GITHUB_HISTORY_LIMIT}) radar limitinden "
        f"({s.GITHUB_BACKFILL_LIMIT}) buyuk olmali; degilse ayrim anlamsiz"
    )

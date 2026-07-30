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
from ensemble.store.models import DEFAULT_REPO_FULL_NAME, Base, TaskProjectionRow, TaskStatusEventRow
from ensemble.store.rebuild import append_status_events, fold_status, rebuild_projection
from ensemble.config import Settings
from ensemble_shared.harness import HarnessPort

# rebuild_projection() bu dosyada HEP repo_full_name'siz çağrılıyor (fonksiyon
# varsayılanı DEFAULT_REPO_FULL_NAME'e düşer) — elle kurulan TaskStatusEventRow
# satırları da AYNI kiracıyla etiketlenmeli, yoksa fold bunları görmez.
_REPO = DEFAULT_REPO_FULL_NAME


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
        repo_full_name=_REPO,
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
        repo_full_name=_REPO,
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
        repo_full_name=_REPO,
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
        repo_full_name=_REPO,
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
                source_event_id="pr-99",
                task_id="T-10",
                repo_full_name=_REPO,
                status="in_review",
                ts=ts,
                reason="pr_opened",
            ),
            TaskStatusEventRow(
                source_event_id="pr-99",
                task_id="T-20",
                repo_full_name=_REPO,
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


# ---------------------------------------------------------------------------
# #331 — GEÇMİŞ KURTARMA + KART KÜMESİ. Ölçülmüş üç kök neden:
#   (a) transitions_from_resources() yazılmış+test edilmiş ama prodüksiyonda
#       HİÇ çağrılmıyordu -> board yalnız webhook canlıya alındıktan SONRAKİ
#       olayları görebiliyordu (29 Tem ölçümü: 22 kartın 9'u yanlış).
#   (b) kart kümesi .harness/tasks/'ın 22 dosyasıyla donmuştu (repoda ~150 issue).
#   (c) fold "son satır kazanır" derken canlı yol monotonluk uyguluyordu.
# ---------------------------------------------------------------------------


def _github_with(prs=None, issues=None):
    """`GitHubPort`in GERÇEK ŞEKİLLİ ham kaynak döndüren fake'i.

    MagicMock KULLANILMAZ: `MagicMock(spec=GitHubPort).fetch_backfill_resources()`
    sessizce boş iterable gibi davranır — yani kablolama SİLİNSE BİLE testler
    yeşil kalırdı (bu issue'nun kök nedeninin ta kendisi: "kodda var" ile
    "çalışıyor" aynı şey değil).
    """
    from ensemble.integrations.github.fake import FakeGitHubAdapter
    from ensemble.ports import BackfillResources

    return FakeGitHubAdapter(
        events=[],
        backfill_resources=BackfillResources(prs=prs or [], issues=issues or []),
    )


def _bos_ai_portlari():
    from ensemble.ports import EmbeddingsPort
    from ensemble.store.vector_store import LocalVectorIndex

    embeddings = MagicMock(spec=EmbeddingsPort)
    embeddings.embed.return_value = []
    return LocalVectorIndex(), embeddings


def test_rebuild_GECMISI_github_kaynaklarindan_kurtarir():
    """(a) KİLİDİ: DB'de HİÇ task_status_events satırı yokken (webhook o gün
    henüz canlı değildi) rebuild, GitHub'ın anlık kaynaklarından geçmişi
    yeniden üretmeli.

    Senaryo canlıdan alınmıştır: T-190'ın issue'su 2026-07-27T13:57:58'de
    kapandı, webhook 14:06'da canlıya alındı — kart bugüne kadar `in_progress`
    kaldı.

    MUTASYON: rebuild.py'deki `transitions_from_resources(...)` +
    `append_status_events(...)` bloğunu sil -> kart `in_progress` kalır,
    `backfill_transitions` 0 olur, bu test kırmızı olur.
    """
    session = _fresh_session()
    harness = _mock_harness(
        tasks=[{"task_id": "T-190", "title": "Deploy runbook", "status": "in_progress"}]
    )
    github = _github_with(
        issues=[
            {
                "number": 190,
                "title": "Deploy runbook",
                "updated_at": "2026-07-27T13:57:58Z",
                "state": "closed",
            }
        ]
    )
    vector_index, embeddings = _bos_ai_portlari()

    res = rebuild_projection(
        session, harness, github=github, vector_index=vector_index, embeddings=embeddings
    )

    assert res["backfill_transitions"] == 1
    row = session.query(TaskProjectionRow).filter_by(task_id="T-190").one()
    assert row.status == "done"
    assert row.seed_status == "in_progress"  # tohum korunur, fold üstüne biner
    assert row.last_transition_at is not None
    assert res["orphan_transitions"] == 0


def test_rebuild_HARNESS_TE_OLMAYAN_github_issue_su_icin_kart_acar():
    """(b) KİLİDİ: kart kümesi `.harness/tasks/` ile sınırlı değil.

    MUTASYON: rebuild.py'deki `TaskProjectionRow.from_github_issue` döngüsünü
    sil -> T-324 kartı hiç oluşmaz, geçişi `orphan_transitions`e düşer ve bu
    test kırmızı olur.
    """
    session = _fresh_session()
    harness = _mock_harness(tasks=[])  # .harness'te HİÇ dosya yok
    github = _github_with(
        issues=[
            {
                "number": 324,
                "title": "Radar derinlik",
                "updated_at": "2026-07-29T10:00:00Z",
                "state": "closed",
                "assignee": {"login": "FatihErenCetin"},
            },
            {
                "number": 331,
                "title": "Board kendiliğinden dolmuyor",
                "updated_at": "2026-07-30T08:00:00Z",
                "state": "open",
            },
        ]
    )
    vector_index, embeddings = _bos_ai_portlari()

    res = rebuild_projection(
        session, harness, github=github, vector_index=vector_index, embeddings=embeddings
    )

    assert res["tasks_from_harness"] == 0
    assert res["tasks_from_github"] == 2
    assert res["orphan_transitions"] == 0

    kapali = session.query(TaskProjectionRow).filter_by(task_id="T-324").one()
    assert kapali.status == "done"
    assert kapali.title == "Radar derinlik"
    assert kapali.assignee == "FatihErenCetin"
    assert kapali.ref == "#324"

    acik = session.query(TaskProjectionRow).filter_by(task_id="T-331").one()
    # Açık issue: geçiş üretilmez, tohum `backlog`ta kalır (uydurma yok).
    assert acik.status == "backlog"
    assert acik.last_transition_at is None


def test_rebuild_HARNESS_KAZANIR_github_basligi_tohumu_ezmez():
    """`.harness` kanoniktir (dizin_yapisi §7): aynı task_id hem dosyada hem
    GitHub'da varsa başlık/assignee/tohum DOSYADAN gelir.

    MUTASYON: `if row.task_id in task_rows: continue` kontrolünü kaldır ->
    başlık "GitHub başlığı" olur ve bu test kırmızı olur.
    """
    session = _fresh_session()
    harness = _mock_harness(
        tasks=[{"task_id": "T-64", "title": "Harness başlığı", "status": "backlog"}]
    )
    github = _github_with(
        issues=[
            {
                "number": 64,
                "title": "GitHub başlığı",
                "updated_at": "2026-07-20T10:00:00Z",
                "state": "open",
            }
        ]
    )
    vector_index, embeddings = _bos_ai_portlari()

    res = rebuild_projection(
        session, harness, github=github, vector_index=vector_index, embeddings=embeddings
    )

    assert res["tasks_from_harness"] == 1
    assert res["tasks_from_github"] == 0
    row = session.query(TaskProjectionRow).filter_by(task_id="T-64").one()
    assert row.title == "Harness başlığı"
    assert row.ref is None


def test_rebuild_gecmis_backfilli_IDEMPOTENT():
    """Aynı GitHub anlık görüntüsüyle iki kez rebuild: ikinci çağrıda YENİ
    geçiş satırı EKLENMEZ (append-only günlük çoğalmaz) ve sonuç bit-bit aynı.

    MUTASYON: `append_status_events` yerine düz `session.add_all` kullanılırsa
    ikinci rebuild 1 yerine 2 satır yazar ve bu test kırmızı olur.
    """
    session = _fresh_session()
    harness = _mock_harness(tasks=[{"task_id": "T-190", "title": "X", "status": "todo"}])
    issues = [
        {"number": 190, "title": "X", "updated_at": "2026-07-27T13:57:58Z", "state": "closed"}
    ]
    vector_index, embeddings = _bos_ai_portlari()

    ilk = rebuild_projection(
        session,
        harness,
        github=_github_with(issues=issues),
        vector_index=vector_index,
        embeddings=embeddings,
    )
    ikinci = rebuild_projection(
        session,
        harness,
        github=_github_with(issues=issues),
        vector_index=vector_index,
        embeddings=embeddings,
    )

    assert ilk["backfill_transitions"] == 1
    assert ikinci["backfill_transitions"] == 0  # ikinci kez YAZILMAZ
    assert session.query(TaskStatusEventRow).filter_by(task_id="T-190").count() == 1
    assert ilk["tasks"] == ikinci["tasks"]
    assert session.query(TaskProjectionRow).filter_by(task_id="T-190").one().status == "done"


def test_fold_CANLI_YOLLA_ayni_monotonluk_kuralini_kullanir():
    """(c) KİLİDİ: fold artık `next_status`'ü çağırır — "son satır kazanır" DEĞİL.

    Canlıdan ölçülen senaryo (T-44): issue KAPANDI (done) ama aynı dalda hâlâ
    AÇIK bir PR var (in_review) ve PR'ın `updated_at`'i daha yeni. Eski
    "son satır kazanır" kuralı kartı done'dan in_review'a GERİ alıyordu;
    canlı yol (Projector.apply_transitions -> next_status) ise done'da
    tutuyordu. Aynı veriden iki farklı board = rebuild'in "canlı yolla aynı
    sonucu verir" iddiasının çürümesi.

    MUTASYON: fold_status içindeki `next_status(...)` çağrısını
    `current = row.status`a geri al -> sonuç `in_review` olur, bu test
    kırmızı olur.
    """
    kapanis = TaskStatusEventRow(
        source_event_id="issue:44:2026-07-27T13:00:00Z",
        task_id="T-44",
        repo_full_name=_REPO,
        status="done",
        ts=datetime(2026, 7, 27, 13, 0),
        reason="issue_closed",
    )
    acik_pr = TaskStatusEventRow(
        source_event_id="pr:300:2026-07-29T18:00:00Z",
        task_id="T-44",
        repo_full_name=_REPO,
        status="in_review",
        ts=datetime(2026, 7, 29, 18, 0),
        reason="pr_opened",
    )

    status, last_ts, last_event_id = fold_status("todo", [kapanis, acik_pr])

    assert status == "done"
    # "En son GÖRÜLEN olay" yine ilerler — durum değişmedi diye zaman donmaz.
    assert last_ts == datetime(2026, 7, 29, 18, 0)
    assert last_event_id == "pr:300:2026-07-29T18:00:00Z"


def test_fold_reopen_done_u_hala_geri_alir():
    """Monotonluğun TEK bilinçli istisnası (`resets=True`) fold'da da geçerli —
    aksi halde yeniden açılan bir issue sonsuza dek done kalırdı.

    MUTASYON: fold'da `resets` alanı okunmayıp `False` sabitlenirse sonuç
    `done` olur ve bu test kırmızı olur.
    """
    kapanis = TaskStatusEventRow(
        source_event_id="issue:44:closed",
        task_id="T-44",
        repo_full_name=_REPO,
        status="done",
        ts=datetime(2026, 7, 27, 13, 0),
        reason="issue_closed",
    )
    yeniden_acilis = TaskStatusEventRow(
        source_event_id="issue:44:reopened",
        task_id="T-44",
        repo_full_name=_REPO,
        status="todo",
        ts=datetime(2026, 7, 28, 9, 0),
        reason="issue_reopened",
        resets=True,
    )

    status, _, _ = fold_status("backlog", [kapanis, yeniden_acilis])
    assert status == "todo"


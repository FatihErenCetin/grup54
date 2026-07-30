"""Projeksiyon yeniden kurma — .harness/ kanonik kaynak → DB cache (#41).

İki bağımsız düzeltme burada BİRLEŞİR (D-55 + #218):

1) D-55 (İş 2) öncesi: rebuild_projection() `task_projection`'ı SİLİP yalnızca
   .harness'ten yeniden kuruyordu — webhook'un yazdığı GERÇEK GitHub durumu
   ilk rebuild'de KAYBOLUYORDU (bulunan çelişki: engine/projector.py'nin
   yazdığı `status`, store/rebuild.py'nin sildiği ilk şeydi). Şimdi: kimlik/
   içerik (.harness) TOHUM, durum GERÇEK GitHub olayı — ikisi
   `task_status_events` (append-only, kalıcı) üzerinden KATLANIR (fold).

2) #218 (T-191): rebuild artık yalnız tasks/presence değil, `events` +
   `vector_index`'i de GitHub'dan seed eder; DB satırları (tasks/presence/
   events) ve vektör indeksi TEK bir transaction'da güncellenir (atomik —
   "DB güncellenip index eski kalması" mümkün değildir). `__main__`
   girişinde FAIL-CLOSED bir kapı vardır: gerçek bir GitHub App yoksa
   (`FakeGitHubAdapter`) ve `ENSEMBLE_ALLOW_FAKE_SEED` açıkça verilmemişse
   rebuild REDDEDİLİR — eksik/hatalı `.pem` yüzünden gerçek DB verisinin
   üzerine sahte veri YAZILMASI böyle engellenir (D-51).

Sonuç: rebuild_projection() artık "sil + tohumdan kur" DEĞİL, sırayla
"sil + tohumdan kur (tasks/presence) + GitHub'dan seed et (events/vector) +
geçişleri yeniden oyna (fold)" — yani rebuild İDEMPOTENT'tir ve canlı yolla
AYNI sonucu verir (DB tamamen silinse bile `.harness` tohumu + GitHub
backfill'i + task_status_events günlüğü ile yeniden kurulabilir; "DB kanonik
değil" iddiası kanıtlı kalır).
"""

from datetime import datetime
from typing import Iterable

from sqlalchemy.orm import Session

from ensemble.engine.status_rules import (
    StatusTransition,
    next_status,
    transitions_from_resources,
)
from ensemble.ports import EmbeddingsPort, GitHubPort, VectorIndexPort
from ensemble.store.models import (
    DEFAULT_REPO_FULL_NAME,
    EventRow,
    PresenceRow,
    TaskProjectionRow,
    TaskStatusEventRow,
)
from ensemble_shared.harness import HarnessPort


# Toplu backfill 429'da ne kadar beklemeye RAZI (saniye). Gemini'nin dakikalik
# embed kotasi tukendiginde sunucu ~30 sn diyor; interaktif sinir (10 sn) burada
# isi yarim birakirdi.
_TOPLU_IS_BEKLEME_SINIRI_S = 120.0


def append_status_events(session: Session, events: Iterable[TaskStatusEventRow]) -> int:
    """`task_status_events`'e append-only ekleme.

    Aynı (`source_event_id`, `task_id`) çifti ikinci kez gelirse (GitHub'ın
    aynı webhook'u yeniden teslim etmesi — retry) satır ÇOĞALTILMAZ, sessizce
    atlanır. Fail-open ÜRETMEZ: atlanan satır sayılır (dönüş değeri yalnızca
    GERÇEKTEN eklenen satır sayısıdır), kaybolmaz — zaten DB'de var.

    Args:
        session: aktif SQLAlchemy oturumu (caller commit eder).
        events: eklenecek TaskStatusEventRow nesneleri (henüz session'a
            eklenmemiş / flush edilmemiş olabilir) — HER birinin
            `repo_full_name`'i ÇAĞIRAN tarafından ZATEN doldurulmuş olmalı
            (T-79: PK'nin parçası, bkz. store/models.py).

    Returns:
        Gerçekten eklenen (yeni) satır sayısı.
    """
    inserted = 0
    for event in events:
        existing = session.get(
            TaskStatusEventRow, (event.source_event_id, event.task_id, event.repo_full_name)
        )
        if existing is not None:
            continue
        session.add(event)
        session.flush()
        inserted += 1
    return inserted


def fold_status(
    seed: str, rows: Iterable[TaskStatusEventRow]
) -> tuple[str, datetime | None, str | None]:
    """Tohum + biriken geçişleri deterministik olarak katla (fold).

    `rows`, (`ts`, `source_event_id`) sırasına göre sıralanır — KRONOLOJİK
    sıra esastır, satırların DB'ye YAZILMA (insertion) sırası DEĞİL. Böylece
    ağ gecikmesiyle GEÇ gelen ama ts'i ESKİ olan bir olay, daha sonra gelmiş
    ts'i YENİ satırların sonucunu BOZMAZ (bkz.
    tests/unit/test_rebuild.py test_gec_gelen_eski_olay_durumu_bozmaz).

    Her satırın `status`'ü zaten ÇÖZÜLMÜŞ hedef durumdur (engine/status_rules.py
    sorumluluğu — İş 1); burada yalnızca sıralı katlama yapılır, ham GitHub
    event tipinden yeniden türetme YOKTUR.

    Katlama kuralı `status_rules.next_status`'tür — CANLI yolun (webhook →
    `Projector.apply_transitions`) kullandığı kuralın TA KENDİSİ (#331).
    Eskiden burada "son satır kazanır" vardı; `engine/projector.py`'nin
    docstring'i bu ayrışmayı açık bir entegrasyon notu olarak bırakmıştı
    (İş 2/3 mutabakatı). Geçmiş backfill'i devreye girince not teorik olmaktan
    çıktı: ÖLÇÜLDÜ (2026-07-30, repodaki 315 gerçek geçiş) — T-44'ün issue'su
    kapalı ama dalında hâlâ AÇIK bir PR var; "son satır kazanır" kartı
    done'dan in_review'a GERİ alıyordu, canlı yol ise done'da tutuyordu. Aynı
    veriden iki farklı board = rebuild'in "canlı yolla AYNI sonucu verir"
    iddiasının çürümesi. Tek kural: 143/144 → 144/144 doğru.

    Args:
        seed: `.harness/tasks/T-<id>.md` dosyasındaki tohum `status`.
        rows: bu task_id için birikmiş TaskStatusEventRow satırları.

    Returns:
        (folded_status, son_geçiş_ts'i veya None, son_geçiş_event_id'si veya None).
        Hiç satır yoksa (folded_status == seed, None, None) döner.
    """
    ordered = sorted(rows, key=lambda row: (row.ts, row.source_event_id))

    current = seed
    last_ts: datetime | None = None
    last_event_id: str | None = None
    for row in ordered:
        current = next_status(
            current,
            StatusTransition(
                task_id=row.task_id,
                status=row.status,
                ts=row.ts,
                source_event_id=row.source_event_id,
                reason=row.reason,
                resets=bool(row.resets),
            ),
        )
        # `last_transition_at` durum DEĞİŞMESE de ilerler: "bu kartla ilgili en
        # son GÖRÜLEN olay" bilgisidir, "en son DEĞİŞEN durum" değil — canlı
        # yol (projector) da aynı şeyi yapar (unchanged dalı).
        last_ts = row.ts
        last_event_id = row.source_event_id

    return current, last_ts, last_event_id


def rebuild_projection(
    session: Session,
    harness: HarnessPort,
    github: GitHubPort | None = None,
    backfill_limit: int = 50,
    vector_index: VectorIndexPort | None = None,
    embeddings: EmbeddingsPort | None = None,
    *,
    repo_full_name: str = DEFAULT_REPO_FULL_NAME,
) -> dict[str, int]:
    """Harness (tohum) + GitHub (events/vector) + task_status_events (fold)
    verisiyle projeksiyonu ve vektör indeksini yeniden kur.

    `repo_full_name` (T-79, çok-kiracılık): beş projeksiyon tablosu da artık
    bu kiracıya göre PK'nin parçası (bkz. store/models.py). Bu fonksiyon
    yalnızca KENDİ `repo_full_name`'ine ait satırları SİLİP yeniden kurar —
    global `.delete()` (eski davranış) çok-kiracılı bir DB'de diğer
    kiracıların projeksiyonunu da silerdi (izolasyon ihlali). Varsayılan
    (`DEFAULT_REPO_FULL_NAME`) tek-kiracılı/test çağrılarını (repo_full_name
    hiç verilmezse) geriye dönük ÇALIŞIR tutar — üretim DI'sı (tenancy.py)
    HER ZAMAN açıkça geçer.

    Sıra ÖNEMLİ ve SABİTTİR:
      a) tasks/presence — `.harness` tohumundan kurulur (silinip yeniden yazılır).
      a2) kart kümesi + geçmiş — `github` verilmişse HAM PR/issue kaynaklarından
         eksik kartlar açılır ve geçmiş geçişler `task_status_events`'e yazılır
         (#331). (a)'dan SONRA olmalı ki `.harness` kartları kazansın, (c)'den
         ÖNCE olmalı ki yazılan geçişler aynı rebuild'de katlansın.
      b) events/vector_index — `github` verilmişse GitHub'dan seed edilir (#218).
      c) transitions — `task_status_events` (`ts`, `source_event_id`) sırasıyla
         (a)'da kurulan tohumun ÜZERİNE katlanır (fold, D-55). Fold, tohum
         kurulduktan SONRA çalışır ki `task_row.seed_status` dolu olsun.

    Atomiklik (#218): DB satırları (tasks/presence/events) ve vektör indeksi
    TEK bir transaction'da güncellenir. Hosted PgVectorIndex, verilen
    `session`'a yazar ve commit tek `session.commit()` ile yapılır → ya hepsi
    kalır ya hepsi geri alınır; "DB güncellenip index eski kalması" mümkün
    değildir. Hata durumunda `session.rollback()` her ikisini de geri alır —
    bu, tasks/presence/fold içindeki bir hatayı da kapsar (tek try/except,
    tek transaction; bir tarafın hata yolu diğerinin içine GÖMÜLMEZ, ikisi de
    aynı üst-düzey rollback'e çıkar).

    `task_status_events` bu fonksiyon tarafından SİLİNMEZ (append-only kalıcı
    günlük) — yalnızca `task_projection`, `presence` ve `events` yeniden inşa
    edilir; bu yüzden art arda iki çağrı BİT-BİT AYNI sonucu üretir
    (idempotent).

    Ne `.harness`'te ne GitHub issue'ları arasında karşılığı olan bir task_id
    için geçiş bulunursa: satır `task_status_events`'te KALIR (kaybolmaz) ama
    `task_projection`'a yeni kart UYDURULMAZ — bu satırlar `orphan_transitions`
    olarak sayılır (fail-open üretmez, sessizce yutulmaz).

    GEÇMİŞ + KART KÜMESİ (#331, `github` verildiğinde):
      * `github.fetch_backfill_resources()` HAM PR/issue kaynaklarını getirir;
        `status_rules.transitions_from_resources` ile geçmişteki geçişler
        türetilip `task_status_events`'e (append-only, idempotent) yazılır.
        Bu kablolama yokken `transitions_from_resources` yazılmış+test edilmiş
        ama HİÇ ÇAĞRILMAMIŞTI: board webhook canlıya alınmadan önceki hiçbir
        kapanışı göremiyordu (ölçüldü 29 Tem: 22 kartın 9'u yanlış).
      * Kart kümesi artık `.harness/tasks/` ile SINIRLI DEĞİL: `.harness`'te
        karşılığı olmayan her GERÇEK GitHub issue'su için kart üretilir
        (`TaskProjectionRow.from_github_issue`). `.harness` KAZANIR — aynı
        task_id için dosya varsa GitHub'dan kart üretilmez, tohum/başlık/
        assignee `.harness`'ten gelir.

    Args:
        session: aktif SQLAlchemy oturumu (bu fonksiyon commit/rollback eder).
        harness: `.harness/` okuyucusu (tasks/active tohumu).
        github: verilirse `events` + `vector_index` GitHub backfill'inden
            seed edilir, GEÇMİŞ geçişleri türetilir ve issue kartları eklenir.
            `None` ise (varsayılan) yalnızca tasks/presence/fold çalışır —
            mevcut testlerle geriye dönük uyumlu.
        backfill_limit: `github.fetch_backfill_events(limit_per_type=...)` ve
            `github.fetch_backfill_resources(limit_per_type=...)`.
        vector_index: `github` verilmişse ZORUNLU (aksi halde ValueError).
            `github` verilmese BİLE geçilirse, birikmiş (stale) vektörler
            boş listeyle `replace_all` edilerek TEMİZLENİR.
        embeddings: `github` verilmişse ZORUNLU (aksi halde ValueError).

    Returns:
        {"tasks": N, "tasks_from_harness": H, "tasks_from_github": G,
         "presence": M, "events": E, "backfill_transitions": B,
         "transitions_applied": K, "orphan_transitions": O}
    """
    # Programlama-hatası kapısı EN BAŞTA: `github` verilip vector_index/
    # embeddings verilmemesi bir yapılandırma hatasıdır. Kontrol eskiden
    # (b) bloğunun içindeydi; (a2) geçmiş backfill'i (#331) araya girince
    # bu, hata fırlamadan ÖNCE iki GitHub isteği atılması demek olurdu
    # (rollback DB'yi kurtarır ama harcanan rate-limit geri gelmez).
    if github is not None and (vector_index is None or embeddings is None):
        raise ValueError("github port requires both vector_index and embeddings for rebuild")

    # Yeni vektörleri DB commit'ten önce hazırla (staging). Bu sayede hata
    # çıkarsa vector index hiç değiştirilmez (build-then-swap, #218).
    staged_vectors: list[tuple[str, list[float], dict]] = []

    try:
        # --- a) tasks: tohumdan kur ---
        # T-79: yalnız BU kiracının satırları silinir/kurulur — global
        # `.delete()` (eski davranış) çok-kiracılı bir DB'de diğer
        # kiracıların projeksiyonunu da silerdi (izolasyon ihlali).
        session.query(TaskProjectionRow).filter_by(repo_full_name=repo_full_name).delete()

        tasks = harness.read_tasks()
        task_rows: dict[str, TaskProjectionRow] = {}
        for task_data in tasks:
            row = TaskProjectionRow.from_harness(task_data, repo_full_name=repo_full_name)
            task_rows[row.task_id] = row
        harness_task_count = len(task_rows)

        # --- a2) GEÇMİŞ + kart kümesi: HAM GitHub kaynakları (#331) ---
        # Ham PR/issue sözlükleri; `fetch_backfill_events`'in ürettiği
        # NormalizedEvent bu iş için YETMEZ (state/merged_at/body/head.ref/
        # title/assignee alanlarını atar — bkz. ports.BackfillResources).
        backfill_transitions = 0
        if github is not None:
            resources = github.fetch_backfill_resources(limit_per_type=backfill_limit)

            # Kart kümesi: `.harness` KAZANIR (dizin_yapisi §7) — yalnız
            # `.harness`'te KARŞILIĞI OLMAYAN gerçek issue'lar için kart
            # üretilir. Böylece board 22 dosyayla sınırlı kalmaz ama
            # `.harness`'teki başlık/assignee GitHub tarafından EZİLMEZ.
            for issue in resources.issues:
                row = TaskProjectionRow.from_github_issue(issue, repo_full_name=repo_full_name)
                if row.task_id in task_rows:
                    continue
                task_rows[row.task_id] = row

            # Geçmiş geçişler: kalıcı günlüğe append-only yazılır. Aynı
            # (source_event_id, task_id) ikinci rebuild'de ÇOĞALMAZ →
            # rebuild idempotent kalır.
            transitions = transitions_from_resources(resources.prs, resources.issues)
            backfill_transitions = append_status_events(
                session,
                [
                    TaskStatusEventRow(
                        source_event_id=t.source_event_id,
                        task_id=t.task_id,
                        repo_full_name=repo_full_name,
                        status=t.status,
                        ts=t.ts,
                        reason=t.reason,
                        resets=t.resets,
                    )
                    for t in transitions
                ],
            )

        session.add_all(task_rows.values())
        session.flush()

        # --- presence (active/) ---
        session.query(PresenceRow).filter_by(repo_full_name=repo_full_name).delete()

        actives = harness.read_active()
        presence_rows = [PresenceRow.from_harness(a, repo_full_name=repo_full_name) for a in actives]
        session.add_all(presence_rows)

        # --- b) events + vector index (GitHub backfill, #218) ---
        session.query(EventRow).filter_by(repo_full_name=repo_full_name).delete()

        event_rows: list[EventRow] = []
        if github is not None:
            # `embeddings`/`vector_index` burada GARANTİLİ dolu — fonksiyonun
            # ilk satırındaki fail-closed kapı bunu zaten doğruladı.
            events = github.fetch_backfill_events(limit_per_type=backfill_limit)
            event_rows = [EventRow.from_domain(e, repo_full_name=repo_full_name) for e in events]
            session.add_all(event_rows)

            if events:
                texts = [
                    f"Event: {e.type} by {e.actor} on {e.branch or 'none'} at {e.ref}. Files: {', '.join(e.files)}"
                    for e in events
                ]
                vectors = embeddings.embed(texts, task_type="RETRIEVAL_DOCUMENT")
                for event, vec in zip(events, vectors, strict=True):
                    meta = {
                        "type": event.type,
                        "actor": event.actor,
                        "branch": event.branch,
                        "files": event.files,
                        "ts": event.ts.isoformat(),
                        "ref": event.ref,
                    }
                    staged_vectors.append((event.id, vec, meta))

        # --- vector index: AYNI transaction içinde (atomiklik #218) ---
        # PgVectorIndex verilen session'a TRUNCATE+INSERT yazar, commit'i
        # aşağıdaki tek session.commit() yapar → DB satırları + vektörler
        # birlikte commit/rollback olur. In-memory index session'ı yok sayar;
        # kendi içinde atomik (build-then-swap) olduğundan yarım-durum
        # bırakmaz. `github` verilmese bile `vector_index` verilmişse stale
        # vektörler boş listeyle temizlenir (replace_all([], ...)).
        # embeddings.embed hatası bu satıra gelmeden (yukarıda) fırlar → rollback.
        if vector_index is not None:
            vector_index.replace_all(staged_vectors, session=session)

        # --- c) transitions: kalıcı günlüğü (ts, source_event_id) sırasıyla
        # katla (fold, D-55). Tohum (task_rows) (a)'da kurulduğu için burada
        # her task_row.seed_status doludur; sıra bu yüzden ÖNEMLİ. T-79:
        # yalnız BU kiracının geçişleri katlanır — filtresiz sorgu diğer
        # kiracıların task_id'lerini (örn. "T-1" her repoda var olabilir)
        # bu kiracının fold'una karıştırırdı.
        by_task: dict[str, list[TaskStatusEventRow]] = {}
        for event_row in session.query(TaskStatusEventRow).filter_by(repo_full_name=repo_full_name).all():
            by_task.setdefault(event_row.task_id, []).append(event_row)

        transitions_applied = 0
        orphan_transitions = 0
        for task_id, rows in by_task.items():
            transitions_applied += len(rows)
            task_row = task_rows.get(task_id)
            if task_row is None:
                # Ne .harness'te ne GitHub issue'ları arasında olan task_id —
                # kaybolmaz (satır task_status_events'te kalır), ama
                # task_projection'a UYDURULMAZ. Tipik kaynak: bir PR'ın
                # `Closes #N`'i ya da `T-N-` dalı, artık var olmayan/silinmiş
                # bir issue'ya işaret ediyor.
                orphan_transitions += len(rows)
                continue
            folded_status, last_ts, last_event_id = fold_status(task_row.seed_status, rows)
            task_row.status = folded_status
            task_row.last_transition_at = last_ts
            task_row.last_event_id = last_event_id

        # Tek commit: tasks/presence/events/fold + (hosted'da) vektörler
        # atomik. Hata → except bloğu session.rollback() ile hepsini geri alır.
        session.commit()

    except Exception:
        session.rollback()
        raise

    return {
        "tasks": len(task_rows),
        # Kartın NEREDEN geldiği görünür kalır (#331): "kart kümesi donmuş mu"
        # sorusu tek bakışta cevaplanabilsin, sessizce şişmesin/erimesin.
        "tasks_from_harness": harness_task_count,
        "tasks_from_github": len(task_rows) - harness_task_count,
        "presence": len(presence_rows),
        "events": len(event_rows),
        # Bu rebuild'de günlüğe YENİ eklenen geçmiş geçiş sayısı (idempotent:
        # ikinci rebuild'de 0 olması BEKLENEN, hata değil).
        "backfill_transitions": backfill_transitions,
        "transitions_applied": transitions_applied,
        "orphan_transitions": orphan_transitions,
    }


if __name__ == "__main__":
    from ensemble.app import _build_embeddings_port, _build_github_port
    from ensemble.config import get_settings
    from ensemble.integrations.github.fake import FakeGitHubAdapter
    from ensemble.store.engine import get_engine, get_session_factory
    from ensemble.store.vector_store import build_vector_index
    from ensemble_shared.harness import FileHarnessPort

    settings = get_settings()

    # TOPLU IS: 429'da sunucunun dayattigi sureyi TAM bekle.
    # Interaktif yolda bu sure kirpiliyor (`GEMINI_RETRY_AFTER_CAP_S`, ~10 sn)
    # cunku insan bekliyor ve gunluk kota penceresi zaten bugun acilmayacak.
    # Burada tam tersi: kimse beklemiyor ve embed kotasi DAKIKALIK, yani
    # beklemek GERCEKTEN ise yariyor -- gecmis backfill'i 250'den 663 olaya
    # cikaran sey tam olarak buydu (#280/#283, olculdu 2026-07-27).
    if settings.GEMINI_RETRY_AFTER_CAP_S < _TOPLU_IS_BEKLEME_SINIRI_S:
        settings = settings.model_copy(
            update={"GEMINI_RETRY_AFTER_CAP_S": _TOPLU_IS_BEKLEME_SINIRI_S}
        )

    github = _build_github_port(settings)
    if isinstance(github, FakeGitHubAdapter) and not settings.ENSEMBLE_ALLOW_FAKE_SEED:
        raise SystemExit(
            "rebuild reddedildi: gercek GitHub App yok (FakeGitHubAdapter). "
            "events/vector_index sahte veriyle EZILMEZ. Bilerek demo seed'i "
            "istiyorsan ENSEMBLE_ALLOW_FAKE_SEED=1 ver."
        )

    # T-79: bu CLI script bilerek TEK repoyu (bugünkü demo/tek-kiracılı kurulum)
    # yeniden kurar — settings'ten türetilen repo_full_name olmadan
    # DEFAULT_REPO_FULL_NAME'e düşmek yanlış (boş) bir kiracıyı seed ederdi.
    repo_full_name = settings.demo_repo_full_name
    if not repo_full_name:
        raise SystemExit(
            "rebuild reddedildi: GITHUB_REPO_OWNER/GITHUB_REPO_NAME tanımlı değil "
            "— hangi kiracının yeniden kurulacağı belirsiz (T-79)."
        )

    engine = get_engine(settings)
    session_factory = get_session_factory(engine)
    with session_factory() as session:
        harness = FileHarnessPort()
        embeddings = _build_embeddings_port(settings)
        vector_index = build_vector_index(
            settings,
            session_factory=session_factory if settings.ENSEMBLE_MODE == "hosted" else None,
            repo_full_name=repo_full_name,
        )

        print("Rebuilding projection...")
        res = rebuild_projection(
            session,
            harness,
            github=github,
            # RADAR'in degil, GECMISIN limiti (#280): projeksiyon cift
            # uretmez, maliyeti dogrusal -- radar guvenligi icin kucuk
            # tutulan sayiyi paylasmasi akisin gecmisini kirpiyordu.
            backfill_limit=settings.GITHUB_HISTORY_LIMIT,
            vector_index=vector_index,
            embeddings=embeddings,
            repo_full_name=repo_full_name,
        )
        print(f"Rebuilt: {res}")

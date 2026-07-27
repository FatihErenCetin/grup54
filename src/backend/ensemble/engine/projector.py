"""Projeksiyon yazıcı (Projector) — eventler ve harness verisinden DB durumunu günceller (#47).

D-55 (İş 3, GOREV 3/4): branch-adından durum TAHMİNİ burada artık YOK — durumun
kanonik kaynağı GERÇEK GitHub PR/issue olayıdır, saf türetimi
`engine/status_rules.py`'nin (İş 1) sorumluluğu. `project_events()` yalnız
event audit log'u (EventRow) + presence senkronu yapar; durum geçişleri ayrı
bir metod olan `apply_transitions()` ile uygulanır: her geçiş önce
`store/rebuild.py`'nin (İş 2) `append_status_events`'i ile `task_status_events`'e
(append-only, idempotent) yazılır, sonra `task_projection.status`
`status_rules.next_status` (İş 1, monotonluk kararı TEK yerde) ile GÜNCEL
DB durumu üzerinden İLERİ oynatılır.

Not (entegrasyon notu, İş 2/3 arayüzü): `store/rebuild.py::fold_status` tam
tersine ham `(seed + tüm satırlar)`dan kronolojik SIRAYLA "son satırın statüsü"
kuralıyla yeniden kurar — `next_status`'u ÇAĞIRMAZ, yani rank/monotonluk
korumasını rebuild YOLUNDA uygulamaz (yalnız canlı yol, burada, uygular). Çok
nadir bir senaryoda (bir push'un ts'i, zaten `in_review`'a taşınmış bir PR
olayından SONRA ise) canlı yol ile rebuild farklı sonuç üretebilir — bu, İş 2
ile mutabakat gerektiren AYRI bir entegrasyon notu (bu görevin dosya kapsamı
`store/rebuild.py`'yi İÇERMİYOR, bkz. GOREV 3/4 dosya kilidi).
"""

import logging

from sqlalchemy.orm import Session

from ensemble.engine.status_rules import StatusTransition, next_status
from ensemble.models import NormalizedEvent
from ensemble.store.models import EventRow, PresenceRow, TaskProjectionRow, TaskStatusEventRow
from ensemble.store.rebuild import append_status_events
from ensemble_shared.harness import HarnessPort

logger = logging.getLogger("ensemble.projector")


class Projector:
    """GitHub eventleri ve .harness verisini okuyarak DB projeksiyonunu günceller."""

    def __init__(self, session: Session, harness: HarnessPort) -> None:
        self.session = session
        self.harness = harness

    def project_events(self, events: list[NormalizedEvent]) -> dict[str, int]:
        """Yeni gelen NormalizedEvent listesini audit log'a yazar + presence'ı senkronlar.

        - Tüm eventler EventRow olarak DB'ye yazılır (audit, idempotent merge).
        - .harness/active/ güncel durumu PresenceRow tablosuna yansıtılır.

        Durum TAHMİN ETMEZ (eski branch-tabanlı `commit->in_progress` /
        `pr->in_review` tahmini KALDIRILDI, D-55) — bu, `issue` event'lerini
        hiç görmediği ve merge edilmiş bir PR'ı sonsuza dek `in_review`'da
        bıraktığı için hatalıydı (bulunan çelişki). Durum geçişleri artık
        yalnız `apply_transitions()` ile, GERÇEK GitHub olayından türetilmiş
        `StatusTransition`'lar üzerinden uygulanır.
        """
        event_rows = []
        for event in events:
            # Idempotency: DB'de varsa üzerine yaz (merge) — aynı event'in
            # tekrar işlenmesi satırı çoğaltmaz.
            row = EventRow.from_domain(event)
            self.session.merge(row)
            event_rows.append(row)

        # Presence (active) tablosunu senkronize et
        self.session.query(PresenceRow).delete()
        actives = self.harness.read_active()
        presence_rows = [PresenceRow.from_harness(a) for a in actives]
        self.session.add_all(presence_rows)

        self.session.commit()

        return {
            "events_processed": len(events),
            "presence_synced": len(presence_rows),
        }

    def apply_transitions(self, transitions: list[StatusTransition]) -> dict[str, int]:
        """GERÇEK GitHub olayından türetilmiş `StatusTransition`'ları uygular.

        Her geçiş `task_status_events`'e `append_status_events` ile yazılır
        (append-only + idempotent — GitHub'ın aynı webhook'u yeniden teslim
        etmesi/redelivery satır ÇOĞALTMAZ). `.harness`'te karşılığı olmayan
        bir task_id için de bu satır KAYBOLMAZ (rebuild.py'nin orphan-tolerant
        felsefesiyle aynı: ileride task .harness'e eklenirse bir sonraki
        `rebuild_projection()` bu geçmiş geçişi doğru şekilde katlar) — ama
        `task_projection`'a hemen bir kart UYDURULMAZ; böyle bir task_id
        `unmatched` sayılır ve ADIYLA `logger.warning` edilir. (Eski kod bu
        satırı sessizce atlıyor ama yine de "tasks_updated" sayacını
        artırıyordu — D-53 dersinin sayaç hâlindeki tekrarıydı; bu metod onu
        düzeltir: `applied`/`unchanged`/`unmatched` DOĞRU, ayrık sayılır.)

        `task_projection.status`, her geçiş için AYRI AYRI (`next_status(mevcut
        status, geçiş)`) ileri oynatılır — böylece rank'ı geri alan bir geçiş
        (örn. PR açıldıktan/`in_review`'a geçtikten SONRA gelen eski bir push)
        kartı GERİYE oynatmaz (bulunan çelişki #5: eski kod yalnız `!= "done"`
        koruması yapıyordu). `resets=True` (yalnız issue reopen) TEK bilinçli
        istisnadır.

        Args:
            transitions: `status_rules.transitions_from_webhook` (veya ileride
                `transitions_from_resources`) çıktısı; işlenme sırası
                (`ts`, `source_event_id`) kronolojik olacak şekilde
                normalize edilir (geç gelen ama ts'i eski bir olay, halihazırda
                işlenmiş daha yeni bir sonucu bozmasın).

        Returns:
            {"applied": N, "unchanged": M, "unmatched": K} — HER geçiş TAM
            OLARAK bir kovaya sayılır (N+M+K == len(transitions)): N: status
            GERÇEKTEN değişti; M: task eşleşti ama `next_status` sonucu mevcut
            status'le aynı (redelivery ya da rank'ı ileri götürmeyen bir
            olay); K: `.harness`'te karşılığı olmayan (task_projection'da
            bulunamayan) task_id.
        """
        if not transitions:
            return {"applied": 0, "unchanged": 0, "unmatched": 0}

        event_rows = [
            TaskStatusEventRow(
                source_event_id=t.source_event_id,
                task_id=t.task_id,
                status=t.status,
                ts=t.ts,
                reason=t.reason,
                resets=t.resets,
            )
            for t in transitions
        ]
        # Append-only + idempotent: aynı (source_event_id, task_id) ikinci kez
        # gelirse (GitHub redelivery) satır ÇOĞALMAZ. Kalıcı günlük — task
        # henüz .harness'te olmasa bile (orphan) satır YAZILIR, kaybolmaz.
        append_status_events(self.session, event_rows)

        applied = 0
        unchanged = 0
        unmatched = 0

        # Kronolojik sıra (ts, source_event_id) — fold_status'un (store/rebuild.py,
        # İş 2) kullandığı SIRALAMA ilkesiyle tutarlı: geç gelen ama ts'i eski
        # bir olay, DB'ye yazılma sırasına göre değil gerçek zamana göre işlenir.
        ordered = sorted(transitions, key=lambda t: (t.ts, t.source_event_id))

        for t in ordered:
            task_row = self.session.get(TaskProjectionRow, t.task_id)
            if task_row is None:
                logger.warning(
                    "apply_transitions: eşleşmeyen task_id (.harness'te karşılığı yok): %s",
                    t.task_id,
                )
                unmatched += 1
                continue

            new_status = next_status(task_row.status, t)
            if new_status != task_row.status:
                task_row.status = new_status
                task_row.last_transition_at = t.ts
                task_row.last_event_id = t.source_event_id
                applied += 1
            else:
                unchanged += 1
                # Durum değişmese bile "en son görülen olay" işaretçisini,
                # yalnızca bu geçiş DAHA YENİ ise ilerlet — geç gelen eski bir
                # olay last_transition_at'i GERİYE almasın. SQLite round-trip'i
                # tz-aware bir datetime'ı naive olarak geri verebilir (GitHub
                # "Z" son ekli UTC damgaları gönderir, `_parse_ts` bunu
                # aware yapar) — ham `>` karşılaştırması bu yüzden ikisini de
                # naive'e indirger (ikisi de zaten UTC, yalnızca tzinfo düşer).
                stored = task_row.last_transition_at
                if stored is not None and stored.tzinfo is not None:
                    stored = stored.replace(tzinfo=None)
                incoming = t.ts.replace(tzinfo=None) if t.ts.tzinfo is not None else t.ts
                if stored is None or incoming > stored:
                    task_row.last_transition_at = t.ts
                    task_row.last_event_id = t.source_event_id

        self.session.commit()

        return {"applied": applied, "unchanged": unchanged, "unmatched": unmatched}

"""Events ve Presence servis katmanı (#52, #60).

.harness/active/ altındaki çalışan beyanlarını ve GitHub event'lerini okur.
Bayat (stale) varlık beyanlarını okuma anında (read-time) filtreler (#60).
"""

from datetime import datetime, timezone

from ensemble.models import ActorRef, NormalizedEvent, PresenceEntry
from ensemble.ports import GitHubPort
from ensemble_shared.harness import HarnessPort

DEFAULT_PRESENCE_TTL_SECONDS = 7200  # 2 saat


def _to_naive_utc(value: datetime) -> datetime:
    """Aware datetime'ı naive-UTC'ye indirger; naive olanı dokunmadan döndürür.

    Presence tarafıyla aynı konvansiyon (naive-UTC) — ts karşılaştırmaları
    aware/naive karışımında TypeError vermesin.
    """
    if value.tzinfo is not None:
        return value.astimezone(timezone.utc).replace(tzinfo=None)
    return value


def snapshot_boundary_ids(events: list[NormalizedEvent], latest_ts: datetime) -> list[str]:
    """`latest_ts` sınırındaki event id'lerini sıralı döndürür (#52).

    Feed'in "sürümü" = (latest_ts + o sınırdaki id kümesi). Payload penceresi
    cursor ilerledikçe değişir (tam feed vs artımlı feed), sınırdaki id kümesi
    değişmez; aynı sınıra sonradan event eklenirse küme büyür. ETag bunun
    üzerinden üretilir → iki poll aynı sunucu durumunu aynı sürüm olarak görür.
    """
    return sorted(e.id for e in events if _to_naive_utc(e.ts) == latest_ts)


class EventService:
    def __init__(
        self,
        harness_port: HarnessPort,
        github_port: GitHubPort,
    ):
        self.harness_port = harness_port
        self.github_port = github_port

    def get_presence(
        self,
        ttl_seconds: float = DEFAULT_PRESENCE_TTL_SECONDS,
        now: datetime | None = None,
    ) -> tuple[list[PresenceEntry], datetime]:
        """Aktif çalışan beyanlarını okur ve TTL aşan/bayat beyanları filtreler (#60).

        Returns:
            (filtrelemelerden geçen presence listesi, en son güncellenme zamanı)
        """
        actives = self.harness_port.read_active()
        entries: list[PresenceEntry] = []
        latest_ts = datetime.min
        current_time = now or datetime.now(timezone.utc).replace(tzinfo=None)
        if current_time.tzinfo is not None:
            current_time = current_time.astimezone(timezone.utc).replace(tzinfo=None)

        for a in actives:
            handle = a.get("handle", "")
            ts_str = a.get("updated_at")
            if ts_str:
                try:
                    ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
                    if ts.tzinfo is not None:
                        ts = ts.astimezone(timezone.utc).replace(tzinfo=None)
                except ValueError:
                    ts = datetime.min
            else:
                ts = datetime.min

            # Stale filtering (read-time, pure function logic #60)
            if (current_time - ts).total_seconds() > ttl_seconds:
                continue

            if ts > latest_ts:
                latest_ts = ts

            actor_type = "agent" if handle.endswith("-claude") or handle.endswith("-agent") else "human"
            actor = ActorRef(handle=handle, type=actor_type)

            entries.append(
                PresenceEntry(
                    actor=actor,
                    module=a.get("module"),
                    task=a.get("task_id"),
                    branch=a.get("branch"),
                    since=ts,
                )
            )

        # Hiç taze kayıt yoksa sabit epoch döndür — ETag/304 kontratı bozulmasın.
        # (current_time dönerse her çağrıda farklı ETag üretilir, Semih CR #221)

        return entries, latest_ts

    def get_events(
        self,
        since: datetime | None = None,
    ) -> tuple[list[NormalizedEvent], datetime]:
        """GitHub event akışını artımlı polling cursor (since) ile okur (#52).

        since verilmezse tüm feed döner (ilk poll). Sonraki poll'lerde istemci
        dönen latest_ts'i since olarak geri gönderir → payload küçülür.

        since ALT SINIR olarak DAHİL edilir (>=); sınırdaki event tekrar
        gelebilir. Tekrarları istemci stabil `id` alanıyla eler, "hiç yeni yok"
        durumunu ise router'daki ETag/304 kısa devre eder (kayıp riski yok).

        Returns:
            (ts,id'ye göre artan sıralı eventler, en son event ts'i = sonraki cursor)
        """
        # Fatih #241 blocker fix: GitHub adapter aware datetime bekler, naive gönderirsek
        # _fetch_pr_events içinde `datetime.fromisoformat(pr["updated_at"]) >= since`
        # karşılaştırması TypeError verir. since'i aware UTC'ye çevirip gönderiyoruz.
        if since is None:
            # Tüm feed (ilk poll): epoch'tan itibaren, aware UTC
            lower_bound = datetime.min.replace(tzinfo=timezone.utc)
        elif since.tzinfo is None:
            # Naive gelirse aware UTC'ye çevir
            lower_bound = since.replace(tzinfo=timezone.utc)
        else:
            # Zaten aware, olduğu gibi kullan
            lower_bound = since
        
        events = self.github_port.fetch_events(lower_bound)
        ordered = sorted(events, key=lambda e: (_to_naive_utc(e.ts), e.id))
        latest_ts = _to_naive_utc(ordered[-1].ts) if ordered else _to_naive_utc(lower_bound)
        return ordered, latest_ts

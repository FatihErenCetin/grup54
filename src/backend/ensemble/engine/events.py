"""Events ve Presence servis katmanı (#52, #60).

.harness/active/ altındaki çalışan beyanlarını ve GitHub event'lerini okur.
Bayat (stale) varlık beyanlarını okuma anında (read-time) filtreler (#60).
"""

import hashlib
from datetime import datetime, timezone
from collections.abc import Callable
from sqlalchemy.orm import Session
from sqlalchemy import select

from ensemble.models import ActorRef, NormalizedEvent, PresenceEntry
from ensemble.ports import GitHubPort
from ensemble_shared.harness import HarnessPort
from ensemble.store.models import DEFAULT_REPO_FULL_NAME, EventRow

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
    """`repo_full_name` (T-79, çok-kiracılık): her kiracı KENDİ `EventService`
    örneğine sahiptir (bkz. ensemble/tenancy.py) — `get_presence`'ın
    `harness_port` üzerinden okuduğu `.harness/active/` demo-repo'ya ÖZGÜDÜR
    (diğer kiracılar için dosya yok); non-demo kiracılara TenantRegistry
    dürüst-boş bir harness portu (`NullHarnessPort`) verir, bu sınıf
    KENDİSİ ayrım yapmaz (port'u sorgulamaz)."""

    def __init__(
        self,
        harness_port: HarnessPort,
        github_port: GitHubPort,
        session_factory: Callable[[], Session] | None = None,
        *,
        repo_full_name: str = DEFAULT_REPO_FULL_NAME,
    ):
        self.harness_port = harness_port
        self.github_port = github_port
        self.session_factory = session_factory
        self.repo_full_name = repo_full_name

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
    ) -> tuple[list[NormalizedEvent], datetime, str]:
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
        
        # #265 madde 1 — tek-tüketimlik port: `session_factory` verilmemiş
        # (DB'siz) kurulumlarda GEÇMİŞTEN kalan tek yol. app.py + tenancy.py
        # HER zaman bir session_factory geçtiği için üretimde bu dal HİÇ
        # çalışmaz — HTTP okuma yolu her koşulda DB projeksiyonundan (aşağıdaki
        # `else`) beslenir. `GitHubAdapter._seen_ids` (bkz. integrations/
        # github/adapter.py) "aynı process'te bir kez" filtreler; bu, İNGEST
        # için doğru ama HTTP okuma için yanlıştır (ikinci istemci boş feed
        # görür) — bu yüzden bu dal yalnızca geriye-dönük-uyum/test amaçlı
        # kalıyor, gerçek `/events` yanıtı buradan üretilmiyor
        # (bkz. tests/unit/test_events_db_okuma.py, HTTP-seviyesi kanıt).
        if self.session_factory is None:
            events = self.github_port.fetch_events(lower_bound)
            ordered = sorted(events, key=lambda e: (_to_naive_utc(e.ts), e.id))
            latest_ts = _to_naive_utc(ordered[-1].ts) if ordered else _to_naive_utc(lower_bound)
            payload = latest_ts.isoformat() + "|" + "|".join(snapshot_boundary_ids(ordered, latest_ts))
            etag = f'"{hashlib.sha1(payload.encode("utf-8")).hexdigest()}"'
        else:
            with self.session_factory() as session:
                # #265 madde 2 — ETag NEDEN "tüm DB'deki id kümesi"nden
                # hesaplanıyor (latest_ts + sınır-id'lerinden DEĞİL):
                #
                # Eski hesap `latest_ts + o sınırdaki id kümesi` idi. Bir event'in
                # `ts`'i `commit.author.date` — geliştiricinin makinesinde
                # damgalanır (integrations/github/normalize.py:34) — push anı
                # DEĞİL. Bu yüzden 09:00'da yazılıp 09:30'da push'lanan bir commit,
                # aradaki 09:10 damgalı bir olaydan SONRA gelirse `latest_ts`'in
                # GERİSİNE düşer: `latest_ts` ve sınır-id kümesi değişmez → ETag
                # aynı kalır → istemci 304 alır → geç gelen olay HİÇ görünmez
                # (bkz. tests/unit/test_events_db_okuma.py::
                # test_etag_tum_db_uzerinden_hesaplanir — mutasyon: bu hesaba
                # geri dönünce kırmızı olur).
                #
                # Tüm id kümesinin hash'i bu sınıfa duyarlı DEĞİL: geç gelen
                # olay `latest_ts`'in neresine düşerse düşsün id kümesine YENİ
                # bir üye ekler → hash her koşulda değişir.
                #
                # Maliyet ölçümü (2026-07-28, uv run python -m timeit ile,
                # üretimdeki ~763 olaya yakın 763 sentetik id ile): sort+join+
                # sha1 ~14.5 µs/çağrı — DB round-trip'inin yanında ölçülemeyecek
                # kadar ucuz (`/board` zaten aynı "tüm projeksiyonu oku" deseni,
                # bkz. BoardService). `since` yalnız DÖNEN GÖVDEYİ daraltır
                # (#273 perf), ETag'i DEĞİL — ikisi kasıtlı olarak ayrık.
                #
                # T-79: her iki sorgu da bu kiracıya (repo_full_name) filtrelenir
                # — filtresiz sorgu diğer kiracıların event'lerini sızdırırdı.
                all_ids = session.scalars(
                    select(EventRow.id)
                    .where(EventRow.repo_full_name == self.repo_full_name)
                    .order_by(EventRow.id)
                ).all()
                payload = "|".join(all_ids)
                etag = f'"{hashlib.sha1(payload.encode("utf-8")).hexdigest()}"'

                naive_lower_bound = _to_naive_utc(lower_bound)
                stmt = (
                    select(EventRow)
                    .where(
                        EventRow.repo_full_name == self.repo_full_name,
                        EventRow.ts >= naive_lower_bound,
                    )
                    .order_by(EventRow.ts.asc(), EventRow.id.asc())
                )
                rows = session.scalars(stmt).all()
                ordered = [row.to_domain() for row in rows]
                latest_ts = _to_naive_utc(ordered[-1].ts) if ordered else _to_naive_utc(lower_bound)

        return ordered, latest_ts, etag

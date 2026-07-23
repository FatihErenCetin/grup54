"""Events ve Presence servis katmanı (#52, #60).

.harness/active/ altındaki çalışan beyanlarını ve GitHub event'lerini okur.
Bayat (stale) varlık beyanlarını okuma anında (read-time) filtreler (#60).
"""

from datetime import datetime, timezone

from ensemble.models import ActorRef, PresenceEntry
from ensemble.ports import GitHubPort
from ensemble_shared.harness import HarnessPort

DEFAULT_PRESENCE_TTL_SECONDS = 7200  # 2 saat


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

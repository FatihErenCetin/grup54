"""Aga dokunmayan, deterministik JudgePort-benzeri GitHubPort fake'i.

Diger moduller (radar/board/frontend) gercek GitHub App/.pem olmadan buna
karsi yazar - docs/sprint2-kontratlar.md'nin "fake adapter" ilkesi.
"""

from datetime import datetime, timezone

from ensemble.models import NormalizedEvent

_DEFAULT_EVENTS: list[NormalizedEvent] = [
    NormalizedEvent(
        id="commit:aaa1111",
        type="commit",
        actor="esma",
        branch=None,
        files=["src/backend/ensemble/integrations/gemini/judge.py"],
        ts=datetime(2026, 7, 10, 9, 0, 0),
        ref="aaa1111",
    ),
    NormalizedEvent(
        id="pr:99:2026-07-10T10:00:00",
        type="pr",
        actor="fatih",
        branch="T-99-ornek-ozellik",
        files=[],
        ts=datetime(2026, 7, 10, 10, 0, 0),
        ref="99",
    ),
    NormalizedEvent(
        id="issue:50:2026-07-10T08:00:00",
        type="issue",
        actor="enes",
        branch=None,
        files=[],
        ts=datetime(2026, 7, 10, 8, 0, 0),
        ref="50",
    ),
]


class FakeGitHubAdapter:
    """`GitHubPort` kontratinin ag-cagrisi yapmayan, deterministik sahte implementasyonu."""

    def __init__(
        self,
        events: list[NormalizedEvent] | None = None,
        compare_files: dict[tuple[str, str], list[str]] | None = None,
    ) -> None:
        self._events = events if events is not None else _DEFAULT_EVENTS
        self._compare_files = compare_files or {}
        self._seen_backfill_ids: set[str] = set()

    def fetch_events(self, since: datetime) -> list[NormalizedEvent]:
        since_key = _datetime_key(since)
        return [e for e in self._events if _datetime_key(e.ts) >= since_key]

    def fetch_backfill_events(self, limit_per_type: int = 50) -> list[NormalizedEvent]:
        if limit_per_type <= 0:
            return []

        selected: list[NormalizedEvent] = []
        for event_type in ("commit", "pr", "issue"):
            candidates = [event for event in self._events if event.type == event_type]
            candidates = sorted(candidates, key=lambda event: (_datetime_key(event.ts), event.id), reverse=True)
            selected.extend(candidates[:limit_per_type])

        fresh = [event for event in selected if event.id not in self._seen_backfill_ids]
        self._seen_backfill_ids.update(event.id for event in fresh)
        return fresh

    def compare(self, base: str, head: str) -> list[str]:
        return self._compare_files.get((base, head), [])


def _datetime_key(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        return value
    return value.astimezone(timezone.utc).replace(tzinfo=None)

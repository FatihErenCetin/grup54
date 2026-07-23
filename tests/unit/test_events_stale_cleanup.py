from datetime import datetime, timezone
from unittest.mock import MagicMock

from ensemble.engine.events import EventService
from ensemble.ports import GitHubPort
from ensemble_shared.harness import HarnessPort


def test_stale_cleanup_filters_old_and_invalid_entries():
    mock_harness = MagicMock(spec=HarnessPort)
    mock_github = MagicMock(spec=GitHubPort)

    now = datetime(2026, 7, 21, 12, 0, 0)  # 12:00 UTC

    mock_harness.read_active.return_value = [
        # Fresh entry: 30 minutes ago (11:30 UTC) -> Keep
        {
            "handle": "enes",
            "task_id": "T-60",
            "module": "engine",
            "branch": "T-60-stale",
            "updated_at": "2026-07-21T11:30:00Z",
        },
        # Agent entry: 1 hour ago (11:00 UTC) -> Keep & agent type
        {
            "handle": "esma-claude",
            "task_id": "T-20",
            "module": "api",
            "branch": "T-20-agent",
            "updated_at": "2026-07-21T11:00:00Z",
        },
        # Stale entry: 3 hours ago (09:00 UTC) -> Filter out
        {
            "handle": "semih",
            "task_id": "T-10",
            "module": "store",
            "branch": "T-10-old",
            "updated_at": "2026-07-21T09:00:00Z",
        },
        # Timezone offset entry (+03:00): 12:00+03:00 = 09:00 UTC (3 hours ago) -> Filter out
        {
            "handle": "fatih",
            "task_id": "T-5",
            "module": "infra",
            "branch": "T-5-tz",
            "updated_at": "2026-07-21T12:00:00+03:00",
        },
        # Invalid timestamp -> Filter out
        {
            "handle": "corrupt-user",
            "task_id": "T-99",
            "module": "unknown",
            "branch": "broken",
            "updated_at": "invalid-iso-date",
        },
        # Missing timestamp -> Filter out
        {
            "handle": "missing-user",
            "task_id": "T-98",
            "module": "unknown",
            "branch": "missing",
        },
    ]

    service = EventService(mock_harness, mock_github)
    entries, latest_ts = service.get_presence(ttl_seconds=7200, now=now)

    assert len(entries) == 2
    handles = [e.actor.handle for e in entries]
    assert "enes" in handles
    assert "esma-claude" in handles
    assert "semih" not in handles
    assert "fatih" not in handles
    assert "corrupt-user" not in handles
    assert "missing-user" not in handles

    enes_entry = next(e for e in entries if e.actor.handle == "enes")
    assert enes_entry.actor.type == "human"

    esma_entry = next(e for e in entries if e.actor.handle == "esma-claude")
    assert esma_entry.actor.type == "agent"

    assert latest_ts == datetime(2026, 7, 21, 11, 30, 0)

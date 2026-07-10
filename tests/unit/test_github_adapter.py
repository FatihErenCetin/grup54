import json
from datetime import datetime, timezone
from pathlib import Path

import httpx

from ensemble.config import Settings
from ensemble.integrations.github.adapter import GitHubAdapter
from ensemble.integrations.github.client import GitHubRestClient
from ensemble.integrations.github.fake import FakeGitHubAdapter

_FIXTURES = Path(__file__).parent.parent / "fixtures" / "github_api"


def _load(name: str) -> dict:
    return json.loads((_FIXTURES / name).read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# FakeGitHubAdapter
# ---------------------------------------------------------------------------


def test_fake_adapter_fetch_events_filters_by_since():
    fake = FakeGitHubAdapter()
    events = fake.fetch_events(since=datetime(2026, 7, 10, 8, 30, 0))
    assert all(e.ts >= datetime(2026, 7, 10, 8, 30, 0) for e in events)
    assert len(events) < len(fake._events)


def test_fake_adapter_compare_returns_configured_files():
    fake = FakeGitHubAdapter(compare_files={("main", "feature"): ["a.py", "b.py"]})
    assert fake.compare("main", "feature") == ["a.py", "b.py"]
    assert fake.compare("main", "unknown") == []


# ---------------------------------------------------------------------------
# GitHubRestClient - ETag/304
# ---------------------------------------------------------------------------


def test_client_returns_none_on_304_with_matching_etag():
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        if request.headers.get("if-none-match") == '"v1"':
            return httpx.Response(304)
        return httpx.Response(200, json={"ok": True}, headers={"ETag": '"v1"'})

    client = GitHubRestClient(
        token_provider=lambda: "fake-token",
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    first = client.get("/x", cache_key="x")
    second = client.get("/x", cache_key="x")

    assert first == {"ok": True}
    assert second is None
    assert len(calls) == 2


# ---------------------------------------------------------------------------
# GitHubAdapter - gercek ag olmadan (httpx.MockTransport)
# ---------------------------------------------------------------------------


def _settings() -> Settings:
    return Settings(_env_file=None, GITHUB_REPO_OWNER="o", GITHUB_REPO_NAME="r")


def _fixture_handler(*, with_etag: bool):
    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if "/compare/" in path:
            key, body = "compare", _load("compare_response.json")
        elif "/commits/" in path:
            key, body = "commit_detail", _load("commit_detail.json")
        elif path.endswith("/commits"):
            key, body = "commits", _load("commits_list.json")
        elif path.endswith("/pulls"):
            key, body = "pulls", _load("pulls_list.json")
        elif path.endswith("/issues"):
            key, body = "issues", _load("issues_list.json")
        else:
            return httpx.Response(404)

        headers = {"ETag": f'"{key}-etag"'} if with_etag else {}
        return httpx.Response(200, json=body, headers=headers)

    return handler


def _adapter(*, with_etag: bool) -> GitHubAdapter:
    client = GitHubRestClient(
        token_provider=lambda: "fake-token",
        http_client=httpx.Client(transport=httpx.MockTransport(_fixture_handler(with_etag=with_etag))),
    )
    return GitHubAdapter(_settings(), client=client)


def test_adapter_compare_returns_files():
    adapter = _adapter(with_etag=False)
    files = adapter.compare("base", "head")
    assert files == ["src/backend/ensemble/engine/radar.py", "src/backend/ensemble/engine/board.py"]


def test_adapter_fetch_events_normalizes_and_filters_by_since():
    adapter = _adapter(with_etag=False)
    since = datetime(2026, 7, 10, 0, 0, 0, tzinfo=timezone.utc)

    events = adapter.fetch_events(since)
    by_type = {e.type: e for e in events}

    assert "commit" in by_type
    assert by_type["commit"].ref == "aaa1111"

    # yalnizca since'ten sonra guncellenen PR (99) gelmeli, eski PR (88) elenmeli
    pr_refs = [e.ref for e in events if e.type == "pr"]
    assert pr_refs == ["99"]

    # issue 99 aslinda bir PR (pull_request anahtari var) - issue listesinden elenmeli
    issue_refs = [e.ref for e in events if e.type == "issue"]
    assert issue_refs == ["50"]


def test_adapter_fetch_events_idempotent_replay():
    adapter = _adapter(with_etag=False)
    since = datetime(2026, 7, 10, 0, 0, 0, tzinfo=timezone.utc)

    first = adapter.fetch_events(since)
    second = adapter.fetch_events(since)

    assert len(first) > 0
    assert second == []

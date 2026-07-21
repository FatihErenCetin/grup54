import json
from datetime import datetime, timezone
from pathlib import Path

import httpx

from ensemble.config import Settings
from ensemble.integrations.github.adapter import GitHubAdapter
from ensemble.integrations.github.client import GitHubRestClient
from ensemble.integrations.github.fake import FakeGitHubAdapter
from ensemble.models import NormalizedEvent

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


def test_fake_adapter_get_diff_returns_configured_hunks():
    fake = FakeGitHubAdapter(diffs={("main", "feature"): {"a.py": "@@ -1 +1 @@\n-x\n+y"}})
    assert fake.get_diff("main", "feature") == {"a.py": "@@ -1 +1 @@\n-x\n+y"}
    assert fake.get_diff("main", "unknown") == {}


def test_fake_adapter_backfill_limits_per_type_and_is_idempotent():
    fake = FakeGitHubAdapter(
        events=[
            NormalizedEvent(
                id="commit:old",
                type="commit",
                actor="semih",
                branch=None,
                files=["old.py"],
                ts=datetime(2026, 7, 9, 8, 0, 0),
                ref="old",
            ),
            NormalizedEvent(
                id="commit:new",
                type="commit",
                actor="semih",
                branch=None,
                files=["new.py"],
                ts=datetime(2026, 7, 10, 8, 0, 0),
                ref="new",
            ),
            NormalizedEvent(
                id="pr:1:2026-07-10T09:00:00",
                type="pr",
                actor="enes",
                branch="T-1-x",
                files=[],
                ts=datetime(2026, 7, 10, 9, 0, 0),
                ref="1",
            ),
        ]
    )

    first = fake.fetch_backfill_events(limit_per_type=1)
    second = fake.fetch_backfill_events(limit_per_type=1)

    assert [event.id for event in first] == [
        "commit:new",
        "pr:1:2026-07-10T09:00:00",
    ]
    assert second == []


# ---------------------------------------------------------------------------
# GitHubRestClient - ETag/304
# ---------------------------------------------------------------------------


def test_client_replays_last_body_on_304_with_matching_etag():
    """304 = 'degisiklik yok', 'veri yok' degil - onceki govde replay edilmeli
    (Fatih'in #204 re-review'inda buldugu regresyon: eskiden None donuyordu,
    steady-state pollarda ust katman veriyi sessizce kaybediyordu)."""
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
    assert second == {"ok": True}
    assert len(calls) == 2


def test_client_304_without_prior_body_returns_none():
    """Hic 200 gormeden 304 gelirse (beklenmedik sunucu davranisi) - cache bos,
    replay edilecek bir sey yok, None guvenli deger."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(304)

    client = GitHubRestClient(
        token_provider=lambda: "fake-token",
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    assert client.get("/x", cache_key="x") is None


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


def test_adapter_get_diff_returns_patch_per_path():
    adapter = _adapter(with_etag=False)
    diffs = adapter.get_diff("base", "head")
    assert diffs["src/backend/ensemble/engine/radar.py"] == "@@ -1 +1 @@\n-old\n+new"
    # buyuk diff'lerde GitHub 'patch' alanini hic gondermez - sessizce ""
    assert diffs["src/backend/ensemble/engine/board.py"] == ""


def test_adapter_get_diff_uses_separate_cache_key_from_compare():
    """#152: compare() ve get_diff() AYNI cache_key'i paylasirsa, compare()
    once cagrilinca ETag kaydedilir ve get_diff() ayni istekte If-None-Match
    gonderip 304/None alir - patch verisi sessizce kaybolur. Bu test gercek
    ETag/If-None-Match davranisini simule eden bir handler'la bu regresyona
    karsi repro yapiyor (paylasilan _fixture_handler bunu simule etmiyordu)."""
    compare_body = _load("compare_response.json")
    seen_etags: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        key = request.url.path
        if_none_match = request.headers.get("if-none-match")
        if if_none_match and seen_etags.get(key) == if_none_match:
            return httpx.Response(304)
        etag = '"compare-etag"'
        seen_etags[key] = etag
        return httpx.Response(200, json=compare_body, headers={"ETag": etag})

    client = GitHubRestClient(
        token_provider=lambda: "fake-token",
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    adapter = GitHubAdapter(_settings(), client=client)

    adapter.compare("base", "head")
    diffs = adapter.get_diff("base", "head")

    assert diffs["src/backend/ensemble/engine/radar.py"] == "@@ -1 +1 @@\n-old\n+new"


def test_adapter_get_diff_steady_state_304_replays_previous_patch():
    """Fatih'in #204 re-review'i: ayni branch cifti art arda pollandiginda
    (yeni commit yok -> ETag esler -> 304) get_diff eskiden sessizce {} donup
    semantik sinyali coken - ilk poll'dan SONRAKI HER poll'da. Gercek adapter +
    MockTransport (200 sonra 304) ile reprodukte edip kilitliyoruz."""
    compare_body = _load("compare_response.json")
    etag = '"diff-etag"'
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if request.headers.get("if-none-match") == etag:
            return httpx.Response(304)
        return httpx.Response(200, json=compare_body, headers={"ETag": etag})

    client = GitHubRestClient(
        token_provider=lambda: "fake-token",
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    adapter = GitHubAdapter(_settings(), client=client)

    poll1 = adapter.get_diff("base", "head")
    poll2 = adapter.get_diff("base", "head")  # ayni ETag -> 304

    assert poll1 == poll2
    assert poll2["src/backend/ensemble/engine/radar.py"] == "@@ -1 +1 @@\n-old\n+new"
    assert calls["n"] == 2


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


def test_adapter_fetch_backfill_events_uses_recent_limit_without_since():
    seen_requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen_requests.append(request)
        return _fixture_handler(with_etag=False)(request)

    client = GitHubRestClient(
        token_provider=lambda: "fake-token",
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    adapter = GitHubAdapter(_settings(), client=client)

    events = adapter.fetch_backfill_events(limit_per_type=2)
    second = adapter.fetch_backfill_events(limit_per_type=2)

    assert [event.ref for event in events if event.type == "pr"] == ["99", "88"]
    assert [event.ref for event in events if event.type == "issue"] == ["50"]
    assert [event.ref for event in events if event.type == "commit"] == ["aaa1111"]
    assert second == []

    list_requests = [
        request
        for request in seen_requests
        if request.url.path.endswith(("/commits", "/pulls", "/issues"))
    ]
    assert all(request.url.params.get("per_page") == "2" for request in list_requests)
    assert all("since" not in request.url.params for request in list_requests)

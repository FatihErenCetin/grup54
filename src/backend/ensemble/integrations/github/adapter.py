from datetime import datetime

from ensemble.config import Settings
from ensemble.integrations.github.auth import InstallationTokenCache
from ensemble.integrations.github.client import GitHubRestClient
from ensemble.integrations.github.errors import GitHubConfigError
from ensemble.integrations.github.normalize import commit_to_event, issue_to_event, pr_to_event
from ensemble.models import NormalizedEvent


class GitHubAdapter:
    """`GitHubPort` kontratinin gercek GitHub REST implementasyonu.

    Idempotency: instance-level `_seen_ids` seti - ayni process'te ayni
    `since` ile tekrar cagrilirsa gorulmus event'ler filtrelenir. Cursor'i
    (bir sonraki `since`) ilerletmek caginanin isidir, adapter'in degil.
    """

    def __init__(self, settings: Settings, client: GitHubRestClient | None = None) -> None:
        if not (settings.GITHUB_REPO_OWNER and settings.GITHUB_REPO_NAME):
            raise GitHubConfigError("GITHUB_REPO_OWNER/GITHUB_REPO_NAME tanimli degil")
        self._owner = settings.GITHUB_REPO_OWNER
        self._repo = settings.GITHUB_REPO_NAME
        self._default_branch = settings.GITHUB_DEFAULT_BRANCH
        self._client = client or GitHubRestClient(
            token_provider=InstallationTokenCache(settings).get_token
        )
        self._seen_ids: set[str] = set()

    def compare(self, base: str, head: str) -> list[str]:
        data = self._client.get(
            f"/repos/{self._owner}/{self._repo}/compare/{base}...{head}",
            cache_key=f"compare:{base}:{head}",
        )
        if data is None:
            return []
        return [f["filename"] for f in data.get("files", [])]

    def fetch_events(self, since: datetime) -> list[NormalizedEvent]:
        events = [
            *self._fetch_commit_events(since),
            *self._fetch_pr_events(since),
            *self._fetch_issue_events(since),
        ]
        fresh = [e for e in events if e.id not in self._seen_ids]
        self._seen_ids.update(e.id for e in fresh)
        return fresh

    def _fetch_commit_events(self, since: datetime) -> list[NormalizedEvent]:
        since_iso = since.isoformat()
        commits = self._client.get(
            f"/repos/{self._owner}/{self._repo}/commits",
            params={"sha": self._default_branch, "since": since_iso},
            cache_key=f"commits:{since_iso}",
        )
        if not commits:
            return []
        events = []
        for summary in commits:
            sha = summary["sha"]
            detail = self._client.get(
                f"/repos/{self._owner}/{self._repo}/commits/{sha}",
                cache_key=f"commit_detail:{sha}",
            )
            if detail is None:
                continue
            events.append(commit_to_event(detail))
        return events

    def _fetch_pr_events(self, since: datetime) -> list[NormalizedEvent]:
        prs = self._client.get(
            f"/repos/{self._owner}/{self._repo}/pulls",
            params={"state": "all", "sort": "updated", "direction": "desc"},
            cache_key="pulls:all",
        )
        if not prs:
            return []
        return [
            pr_to_event(pr) for pr in prs if datetime.fromisoformat(pr["updated_at"]) >= since
        ]

    def _fetch_issue_events(self, since: datetime) -> list[NormalizedEvent]:
        since_iso = since.isoformat()
        issues = self._client.get(
            f"/repos/{self._owner}/{self._repo}/issues",
            params={"state": "all", "since": since_iso},
            cache_key=f"issues:{since_iso}",
        )
        if not issues:
            return []
        return [issue_to_event(i) for i in issues if "pull_request" not in i]

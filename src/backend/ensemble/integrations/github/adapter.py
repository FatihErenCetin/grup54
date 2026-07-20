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

    def get_diff(self, base: str, head: str) -> dict[str, str]:
        """Semantik hunk aşaması (#23/#152) için path->hunk metni.

        Aynı compare API'yi kullanır ama BİLEREK ayrı `cache_key` taşır
        (`compare()`'inkiyle aynı olsaydı, `compare()` önce çağrılınca ETag
        kaydedilir; hemen ardından aynı key ile gelen bu çağrı 304 alır ve
        `GitHubRestClient.get()` `None` döner — `patch` verisi sessizce
        kaybolurdu). Büyük diff'lerde GitHub `patch` alanını hiç göndermez
        (dosya bazlı, sessizce atlanır — chunk_diff boş metinle no-op döner).
        """
        data = self._client.get(
            f"/repos/{self._owner}/{self._repo}/compare/{base}...{head}",
            cache_key=f"diff:{base}:{head}",
        )
        if data is None:
            return {}
        return {f["filename"]: f.get("patch", "") for f in data.get("files", [])}

    def fetch_events(self, since: datetime) -> list[NormalizedEvent]:
        events = [
            *self._fetch_commit_events(since),
            *self._fetch_pr_events(since),
            *self._fetch_issue_events(since),
        ]
        return self._fresh(events)

    def fetch_backfill_events(self, limit_per_type: int = 50) -> list[NormalizedEvent]:
        """Ilk calistirmada radar/projeksiyon icin son N GitHub olayini cek.

        `fetch_events(since)` polling semantigini korur; backfill ise tarih
        penceresi yerine adet penceresi kullanir. Sonuc yine idempotenttir.
        """
        if limit_per_type <= 0:
            return []
        events = [
            *self._fetch_recent_commit_events(limit_per_type),
            *self._fetch_recent_pr_events(limit_per_type),
            *self._fetch_recent_issue_events(limit_per_type),
        ]
        return self._fresh(events)

    def _fresh(self, events: list[NormalizedEvent]) -> list[NormalizedEvent]:
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
        return self._commit_events_from_summaries(commits)

    def _fetch_recent_commit_events(self, limit: int) -> list[NormalizedEvent]:
        commits = self._client.get(
            f"/repos/{self._owner}/{self._repo}/commits",
            params={"sha": self._default_branch, "per_page": limit},
            cache_key=f"commits:recent:{limit}",
        )
        if not commits:
            return []
        return self._commit_events_from_summaries(commits)

    def _commit_events_from_summaries(self, commits: list[dict]) -> list[NormalizedEvent]:
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

    def _fetch_recent_pr_events(self, limit: int) -> list[NormalizedEvent]:
        prs = self._client.get(
            f"/repos/{self._owner}/{self._repo}/pulls",
            params={
                "state": "all",
                "sort": "updated",
                "direction": "desc",
                "per_page": limit,
            },
            cache_key=f"pulls:recent:{limit}",
        )
        if not prs:
            return []
        return [pr_to_event(pr) for pr in prs]

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

    def _fetch_recent_issue_events(self, limit: int) -> list[NormalizedEvent]:
        issues = self._client.get(
            f"/repos/{self._owner}/{self._repo}/issues",
            params={"state": "all", "sort": "updated", "direction": "desc", "per_page": limit},
            cache_key=f"issues:recent:{limit}",
        )
        if not issues:
            return []
        return [issue_to_event(i) for i in issues if "pull_request" not in i]

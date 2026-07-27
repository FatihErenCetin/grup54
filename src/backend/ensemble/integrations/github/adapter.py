import re
from datetime import datetime

from ensemble.config import Settings
from ensemble.integrations.github.auth import InstallationTokenCache
from ensemble.integrations.github.client import GitHubRestClient
from ensemble.integrations.github.errors import GitHubConfigError, GitHubNotFoundError
from ensemble.integrations.github.normalize import commit_to_event, issue_to_event, pr_to_event
from ensemble.models import NormalizedEvent, ScopeSubject
from ensemble.ports import ScopeSubjectNotFoundError

_PR_REF_RE = re.compile(r"(?:^PR[-# ]?|/pull/|^#)(\d+)$", re.IGNORECASE)


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
        self._scope_subject_cache: dict[int, ScopeSubject] = {}

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
        `GitHubRestClient.get()` — 304'te artık `None` değil, ilgili
        `cache_key`'in SON BİLİNEN gövdesini replay eder — bu durumda
        `compare()`'in gövdesini `get_diff()` adına replay ederdi. `compare()`
        yalnızca dosya adlarına bakar, `get_diff()` `patch` alanını okur; aynı
        gövde ikisi için de "doğru şekilde" parse olur ama farklı zamanlarda
        pollandıklarında birbirinin BAYAT verisini sessizce döndürebilirler).
        Büyük diff'lerde GitHub `patch` alanını hiç göndermez (dosya bazlı,
        sessizce atlanır — chunk_diff boş metinle no-op döner).
        """
        data = self._client.get(
            f"/repos/{self._owner}/{self._repo}/compare/{base}...{head}",
            cache_key=f"diff:{base}:{head}",
        )
        if data is None:
            return {}
        return {f["filename"]: f.get("patch", "") for f in data.get("files", [])}

    def resolve_scope_subject(self, ref: str) -> ScopeSubject:
        """Canlı PR başlık/gövde/dosya bilgisini scope motoruna taşır."""
        match = _PR_REF_RE.search(ref.strip())
        if match is None:
            raise ScopeSubjectNotFoundError(ref)

        number = int(match.group(1))
        cached = self._scope_subject_cache.get(number)
        try:
            pull = self._client.get(
                f"/repos/{self._owner}/{self._repo}/pulls/{number}",
                cache_key=f"scope:pull:{number}",
            )
            files = self._client.get(
                f"/repos/{self._owner}/{self._repo}/pulls/{number}/files",
                params={"per_page": 100},
                cache_key=f"scope:pull_files:{number}",
            )
        except GitHubNotFoundError as exc:
            raise ScopeSubjectNotFoundError(ref) from exc

        if pull is None and files is None and cached is not None:
            return cached
        if pull is not None and not isinstance(pull, dict):
            raise ScopeSubjectNotFoundError(ref)
        if files is not None and not isinstance(files, list):
            raise ScopeSubjectNotFoundError(ref)
        if cached is None and (pull is None or files is None):
            raise ScopeSubjectNotFoundError(ref)

        text_parts = (
            [str(pull.get("title") or "").strip(), str(pull.get("body") or "").strip()]
            if pull is not None
            else [cached.text]
        )
        subject = ScopeSubject(
            ref=ref.strip(),
            text="\n".join(part for part in text_parts if part),
            files=(
                sorted(
                    {
                        str(item.get("filename") or "").strip()
                        for item in files
                        if str(item.get("filename") or "").strip()
                    }
                )
                if files is not None
                else cached.files
            ),
        )
        self._scope_subject_cache[number] = subject
        return subject

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

    def _sayfali(
        self, path: str, *, params: dict, cache_key: str, limit: int
    ) -> list[dict]:
        """`limit` kayit toplanana kadar GitHub sayfalarini sirayla gezer.

        Neden gerekli (olculdu): `per_page` GitHub'da 100'de TAVANLI. Tek
        istekle `per_page=250` istemek sessizce 100 kayit dondurur -- hata
        YOK, yalniz eksik veri. grup54 19 Haziran'dan beri ~250 commit
        uretti; sayfalama olmadan Activity akisi yalniz son ~6 gunu
        gosteriyordu ve "kendiliginden daily" vaadi 5 haftalik gecmisi
        kaybediyordu.

        ETag TUZAGI: `cache_key` sayfa numarasini ICERMELI. Icermezse 2.
        sayfanin istegi 1. sayfanin ETag'ini gonderir, GitHub 304 doner ve
        client 1. SAYFANIN GOVDESINI replay eder -- ayni 100 kayit tekrar
        tekrar gelir, dongu erken biter ve bu HATASIZ gorunur. Anahtara
        `:p<N>` ekleyerek her sayfaya kendi ETag'ini veriyoruz.
        """
        # `per_page` TUM sayfalarda AYNI kalmali. GitHub offset'i
        # `(page-1) * per_page` ile hesaplar; son sayfada "yalniz kalani
        # iste" diye kucultursek offset de kayar ve sayfa ONCEKI sayfayla
        # CAKISAN bir araligi doner. Olculdu (250 kayit, 100/100/50 istenince):
        # 3. sayfa 200-249 yerine 100-149'u dondurdu -> 250 kayit geldi ama
        # yalniz 200'u tekildi; 50 kayit sessizce kayboldu. Sabit 100 isteyip
        # sonda kirpiyoruz -- fazladan gelen kayit ucuz, kayip kayit degil.
        # Boyutu limit'ten TUReTIYORUZ ama sonra DEGISTIRMIYORUZ: limit<=100
        # iken tek istek + eski `per_page=limit` davranisi aynen korunur.
        SAYFA_BOYU = min(100, limit)
        toplanan: list[dict] = []
        sayfa = 1
        while len(toplanan) < limit:
            govde = self._client.get(
                path,
                params={**params, "per_page": SAYFA_BOYU, "page": sayfa},
                cache_key=f"{cache_key}:p{sayfa}",
            )
            if not govde:
                break
            toplanan.extend(govde)
            # Kisa sayfa = son sayfa. Bu kontrol olmadan GitHub bos sayfa
            # dondurene kadar bir istek FAZLA atardik.
            if len(govde) < SAYFA_BOYU:
                break
            sayfa += 1
        return toplanan[:limit]

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
        commits = self._sayfali(
            f"/repos/{self._owner}/{self._repo}/commits",
            params={"sha": self._default_branch},
            cache_key="commits:recent",
            limit=limit,
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
        return [pr_to_event(pr) for pr in prs if datetime.fromisoformat(pr["updated_at"]) >= since]

    def _fetch_recent_pr_events(self, limit: int) -> list[NormalizedEvent]:
        prs = self._sayfali(
            f"/repos/{self._owner}/{self._repo}/pulls",
            params={"state": "all", "sort": "updated", "direction": "desc"},
            cache_key="pulls:recent",
            limit=limit,
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
        issues = self._sayfali(
            f"/repos/{self._owner}/{self._repo}/issues",
            params={"state": "all", "sort": "updated", "direction": "desc"},
            cache_key="issues:recent",
            limit=limit,
        )
        if not issues:
            return []
        return [issue_to_event(i) for i in issues if "pull_request" not in i]

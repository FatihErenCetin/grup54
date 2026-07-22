"""Ham GitHub REST payload'lari -> kanonik NormalizedEvent.

extract_task_id() saf bir yardimci fonksiyondur - NormalizedEvent'e YAZILMAZ
(model donuk, docs/sprint2-kontratlar.md). T-id branch adindan zaten turetilebilir
oldugu icin ihtiyac duyan tuketici extract_task_id(branch=event.branch) cagirir.
"""

import re
from datetime import datetime

from ensemble.models import NormalizedEvent

_BRANCH_TASK_RE = re.compile(r"^T-(\d+)-")
_CLOSES_RE = re.compile(r"[Cc]loses\s+#(\d+)")


def extract_task_id(*, branch: str | None = None, pr_body: str | None = None) -> str | None:
    if branch and (m := _BRANCH_TASK_RE.match(branch)):
        return m.group(1)
    if pr_body and (m := _CLOSES_RE.search(pr_body)):
        return m.group(1)
    return None


def commit_to_event(commit: dict) -> NormalizedEvent:
    sha = commit["sha"]
    files = [f["filename"] for f in commit.get("files", [])]
    return NormalizedEvent(
        id=f"commit:{sha}",
        type="commit",
        actor=(commit.get("author") or {}).get("login") or commit["commit"]["author"]["name"],
        branch=None,
        files=files,
        ts=datetime.fromisoformat(commit["commit"]["author"]["date"]),
        ref=sha,
    )


def pr_to_event(pr: dict) -> NormalizedEvent:
    number = pr["number"]
    updated_at = pr["updated_at"]
    return NormalizedEvent(
        id=f"pr:{number}:{updated_at}",
        type="pr",
        actor=pr["user"]["login"],
        branch=pr["head"]["ref"],
        files=[],
        ts=datetime.fromisoformat(updated_at),
        ref=str(number),
    )


def issue_to_event(issue: dict) -> NormalizedEvent:
    number = issue["number"]
    updated_at = issue["updated_at"]
    return NormalizedEvent(
        id=f"issue:{number}:{updated_at}",
        type="issue",
        actor=issue["user"]["login"],
        branch=None,
        files=[],
        ts=datetime.fromisoformat(updated_at),
        ref=str(number),
    )


def webhook_push_to_events(payload: dict) -> list[NormalizedEvent]:
    """Webhook `push` event payload'ı -> NormalizedEvent listesi (#62).

    REST commits API'den FARKLI şekil (webhook `commits[]` alanı): `sha` yerine
    `id`, `commit.author.date` yerine `timestamp`, ayrı `files` çağrısı yerine
    `added`/`removed`/`modified` dizileri gövdede zaten var — bu yüzden
    `commit_to_event` (REST şekli) yeniden kullanılamaz, ayrı bir mapper gerekir.
    """
    ref = payload.get("ref", "")
    branch = ref.removeprefix("refs/heads/") if ref.startswith("refs/heads/") else None
    events = []
    for commit in payload.get("commits", []):
        author = commit.get("author") or {}
        files = [
            *commit.get("added", []),
            *commit.get("removed", []),
            *commit.get("modified", []),
        ]
        events.append(
            NormalizedEvent(
                id=f"commit:{commit['id']}",
                type="commit",
                actor=author.get("username") or author.get("name", ""),
                branch=branch,
                files=files,
                ts=datetime.fromisoformat(commit["timestamp"]),
                ref=commit["id"],
            )
        )
    return events

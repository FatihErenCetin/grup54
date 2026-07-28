"""Ham GitHub REST payload'lari -> kanonik NormalizedEvent.

extract_task_id() saf bir yardimci fonksiyondur - NormalizedEvent'e YAZILMAZ
(model donuk, docs/sprint2-kontratlar.md). T-id branch adindan zaten turetilebilir
oldugu icin ihtiyac duyan tuketici extract_task_id(branch=event.branch) cagirir.

Aktör doğrulama (#296, T-296): hem REST commits (`commit_to_event`) hem webhook
`push` (`webhook_push_to_events`) yolu, GitHub'ın commit e-postasını bir hesapla
eşleştiremediği durumda ham git commit yazar adına (`commit.author.name` /
webhook `author.name`) DÜŞER — bu düşüş bugüne kadar görünmezdi (#296 teşhisi:
"Merge Simulation" adlı sahte bir aktör grafta gerçek bir takım üyesi gibi
göründü). Artık iki şey birlikte olur: (1) `NormalizedEvent.actor_verified=False`
işaretlenir, (2) düşüş `logger.warning` ile hangi commit/hangi ham ad olduğu
GÖRÜNÜR kılınır. Tercih sırası KİLİTLİ: `login`/`username` VARSA ham ad ASLA
kullanılmaz (bkz. tests/unit/test_github_normalize.py mutasyon kilitleri).
"""

import logging
import re
from datetime import datetime

from ensemble.models import NormalizedEvent

logger = logging.getLogger("ensemble.normalize")

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
    raw_name = commit["commit"]["author"]["name"]
    # `or None`: boş string login'i de "yok" say - tercih sırası (login VARSA
    # ham ad KULLANILMAZ) yalnızca gerçekten dolu bir login için geçerli.
    login = (commit.get("author") or {}).get("login") or None
    actor_verified = login is not None
    if not actor_verified:
        logger.warning(
            "commit_to_event: GitHub hesabıyla eşleşmeyen yazar (author.login yok) "
            "- sha=%s ham_ad=%r",
            sha,
            raw_name,
        )
    return NormalizedEvent(
        id=f"commit:{sha}",
        type="commit",
        actor=login or raw_name,
        branch=None,
        files=files,
        ts=datetime.fromisoformat(commit["commit"]["author"]["date"]),
        ref=sha,
        actor_verified=actor_verified,
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
        raw_name = author.get("name", "")
        # `or None`: boş string username'i de "yok" say (bkz. commit_to_event
        # ile aynı gerekçe) - tercih sırası KİLİTLİ, username VARSA ham ad
        # ASLA kullanılmaz.
        username = author.get("username") or None
        actor_verified = username is not None
        if not actor_verified:
            logger.warning(
                "webhook_push_to_events: GitHub hesabıyla eşleşmeyen yazar "
                "(author.username yok) - commit=%s ham_ad=%r",
                commit.get("id"),
                raw_name,
            )
        events.append(
            NormalizedEvent(
                id=f"commit:{commit['id']}",
                type="commit",
                actor=username or raw_name,
                branch=branch,
                files=files,
                ts=datetime.fromisoformat(commit["timestamp"]),
                ref=commit["id"],
                actor_verified=actor_verified,
            )
        )
    return events

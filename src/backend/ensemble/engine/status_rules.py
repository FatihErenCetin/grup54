"""Ham GitHub payload'larından (webhook veya REST kaynağı) saf durum geçişi türetimi.

Kanonik plan (D-55 taslağı): `.harness/tasks/T-<id>.md` içindeki `status` alanı
**tohum**dur; durumun kanonik kaynağı GERÇEK GitHub PR/issue olayıdır. Bu modül
o olayları/kaynakları `StatusTransition`'a çevirir — I/O YAPMAZ (sqlalchemy,
fastapi, httpx import ETMEZ; `tests/unit/test_arch_guard.py` felsefesine uygun
saf çekirdek). `next_status` monotonluk kararını TEK yerde tutar.

Task-id çıkarma regex'leri BURADA KOPYALANMAZ — `normalize.py`'deki
`_BRANCH_TASK_RE`/`_CLOSES_RE` yeniden kullanılır (tek kaynak, drift yok).

Kapsam (İş 1, GOREV 1/4): yalnız bu modül. `Projector`'ın bu fonksiyonları
çağırması ve `task_status_events` tablosuna yazması AYRI bir iştir (İş 2/3).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from ensemble.integrations.github.normalize import _BRANCH_TASK_RE, _CLOSES_RE

STATUS_RANK: dict[str, int] = {
    "backlog": 0,
    "todo": 1,
    "in_progress": 2,
    "in_review": 3,
    "done": 4,
}

_PR_REVIEW_ACTIONS = frozenset({"opened", "reopened", "ready_for_review"})


@dataclass(frozen=True)
class StatusTransition:
    task_id: str  # "T-158"
    status: str  # task.schema.json enum'u
    ts: datetime
    source_event_id: str  # "pr:{n}:{updated_at}" | "issue:{n}:{updated_at}" | "commit:{id}"
    reason: str  # push|pr_opened|pr_merged|pr_closed_unmerged|issue_closed|issue_reopened
    resets: bool = False  # True ise monotonluk kuralını BİLEREK kırar (yalnız reopen)


def _parse_ts(value: str) -> datetime:
    return datetime.fromisoformat(value)


def _task_id_from_branch(branch: str | None) -> str | None:
    if branch and (m := _BRANCH_TASK_RE.match(branch)):
        return m.group(1)
    return None


def _task_ids_from_body(body: str | None) -> list[str]:
    if not body:
        return []
    return [m.group(1) for m in _CLOSES_RE.finditer(body)]


def _pr_done_transitions(pr: dict, *, reason: str) -> list[StatusTransition]:
    """Merge edilmiş bir PR -> branch'indeki VE gövdesindeki HER Closes #N için done."""
    number = pr["number"]
    updated_at = pr["updated_at"]
    ts = _parse_ts(updated_at)
    source_event_id = f"pr:{number}:{updated_at}"

    ids: list[str] = []
    branch_id = _task_id_from_branch((pr.get("head") or {}).get("ref"))
    if branch_id:
        ids.append(branch_id)
    ids.extend(_task_ids_from_body(pr.get("body")))

    # Aynı task hem branch'te hem gövdede referanslanabilir; tekilleştir,
    # sırayı koru (dict.fromkeys idiomu - set() sırayı garanti etmez).
    unique_ids = list(dict.fromkeys(ids))

    return [
        StatusTransition(
            task_id=f"T-{tid}",
            status="done",
            ts=ts,
            source_event_id=source_event_id,
            reason=reason,
            resets=False,
        )
        for tid in unique_ids
    ]


def _pr_review_transition(pr: dict, *, reason: str) -> list[StatusTransition]:
    """Açık/yeniden-açılmış/hazır bir PR -> yalnız KENDİ branch'inin task'ı in_review."""
    branch_id = _task_id_from_branch((pr.get("head") or {}).get("ref"))
    if not branch_id:
        return []
    number = pr["number"]
    updated_at = pr["updated_at"]
    return [
        StatusTransition(
            task_id=f"T-{branch_id}",
            status="in_review",
            ts=_parse_ts(updated_at),
            source_event_id=f"pr:{number}:{updated_at}",
            reason=reason,
            resets=False,
        )
    ]


def _issue_transition(issue: dict, action: str | None) -> list[StatusTransition]:
    number = issue["number"]
    updated_at = issue["updated_at"]
    task_id = f"T-{number}"
    source_event_id = f"issue:{number}:{updated_at}"
    ts = _parse_ts(updated_at)

    if action == "closed":
        return [
            StatusTransition(
                task_id=task_id,
                status="done",
                ts=ts,
                source_event_id=source_event_id,
                reason="issue_closed",
                resets=False,
            )
        ]
    if action == "reopened":
        return [
            StatusTransition(
                task_id=task_id,
                status="todo",
                ts=ts,
                source_event_id=source_event_id,
                reason="issue_reopened",
                resets=True,
            )
        ]
    return []


def _merged(pr: dict) -> bool:
    """PR merge edildi mi — İKİ ayrı payload şeklini birlikte karşılar (#331).

    Webhook'un içindeki TAM PR nesnesi (`pull-request`) `merged: bool` taşır;
    REST LİSTE ucu (`GET /repos/{o}/{r}/pulls` → `pull-request-simple`) o alanı
    HİÇ TAŞIMAZ, yalnız `merged_at` verir. Yalnız `merged`'a bakmak backfill
    yolunda HER merge'i "merge edilmemiş kapanış" sayardı — yani geçmişten
    tek bir `done` bile üretilmezdi ve bu hatasız görünürdü (ölçüldü,
    2026-07-30: repodaki 130 kapalı PR'ın 130'unda `merged` anahtarı YOK).
    """
    return bool(pr.get("merged") or pr.get("merged_at"))


def _pr_transition_from_webhook(pr: dict, action: str | None) -> list[StatusTransition]:
    if action == "closed":
        if _merged(pr):
            return _pr_done_transitions(pr, reason="pr_merged")
        # Merge edilmemiş kapanış: kart PR'sız hâline kendiliğinden DÖNMEZ -
        # sessiz tahmin yok, geçiş üretilmez (kabul kriteri).
        return []
    if action in _PR_REVIEW_ACTIONS:
        return _pr_review_transition(pr, reason="pr_opened")
    return []


def _push_transitions(payload: dict) -> list[StatusTransition]:
    ref = payload.get("ref", "")
    if not ref.startswith("refs/heads/"):
        return []
    branch = ref.removeprefix("refs/heads/")
    task_id_num = _task_id_from_branch(branch)
    if not task_id_num:
        return []
    task_id = f"T-{task_id_num}"

    return [
        StatusTransition(
            task_id=task_id,
            status="in_progress",
            ts=_parse_ts(commit["timestamp"]),
            source_event_id=f"commit:{commit['id']}",
            reason="push",
            resets=False,
        )
        for commit in payload.get("commits", [])
    ]


def transitions_from_webhook(event_type: str, payload: dict) -> list[StatusTransition]:
    """Webhook payload -> StatusTransition listesi (saf, I/O yok).

    Desteklenen `event_type`: "issues" · "pull_request" · "push". Bilinmeyen
    event_type veya tanınmayan `action` için BOŞ liste döner — sessizce bir
    durum UYDURMAZ, yalnızca "bu olay durum üretmiyor" der.
    """
    if event_type == "issues":
        return _issue_transition(payload["issue"], payload.get("action"))
    if event_type == "pull_request":
        return _pr_transition_from_webhook(payload["pull_request"], payload.get("action"))
    if event_type == "push":
        return _push_transitions(payload)
    return []


def transitions_from_resources(prs: list[dict], issues: list[dict]) -> list[StatusTransition]:
    """Polling/backfill için REST kaynak listesinden AYNI kurallarla geçiş üretimi.

    REST kaynakları webhook'taki `action` alanını TAŞIMAZ; bunun yerine anlık
    durumu (`state`/`merged`) okuyarak aynı sonuca varılır — `pull_request`
    webhook payload'ının içindeki nesne zaten REST kaynağının AYNISI
    (`api/routers/webhook.py` docstring'i), yani `_pr_done_transitions`/
    `_pr_review_transition` burada da yeniden kullanılır (kopya yok).

    Açık bir issue'nun "yeni mi yoksa reopen mı" olduğu tek bir REST
    snapshot'ından ayırt edilemez → bilinçli no-op (sessiz tahmin yok).

    Kablolama (#331): `GitHubPort.fetch_backfill_resources()` →
    `store/rebuild.py::rebuild_projection`. Bu fonksiyon yazıldığı gün
    (D-55, İş 1) test edilmiş ama PRODÜKSİYONDA HİÇ ÇAĞRILMAMIŞTI; board
    bu yüzden yalnız webhook canlıya alındıktan SONRAKİ olayları görebiliyordu
    (ölçüldü, 29 Tem: 22 kartın 9'u yanlış, hepsi webhook öncesi kapanmış).
    """
    transitions: list[StatusTransition] = []
    for pr in prs:
        if _merged(pr):
            transitions.extend(_pr_done_transitions(pr, reason="pr_merged"))
        elif pr.get("state") == "open":
            transitions.extend(_pr_review_transition(pr, reason="pr_opened"))
        # kapalı + merge edilmemiş: webhook ile aynı kural — geçiş üretilmez.

    for issue in issues:
        if issue.get("state") == "closed":
            transitions.extend(_issue_transition(issue, action="closed"))
        # açık issue: reopen mi hiç kapanmamış mı ayırt edilemez — no-op.

    return transitions


def next_status(current: str, t: StatusTransition) -> str:
    """Monotonluk kararı TEK yerde. `resets=True` TEK bilinçli istisna (issue reopen)."""
    if t.resets:
        return t.status
    if STATUS_RANK.get(t.status, 0) >= STATUS_RANK.get(current, 0):
        return t.status
    return current

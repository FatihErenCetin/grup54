from __future__ import annotations

import re
from typing import Any

from ensemble.models import ScopeItemRef, ScopeSubject
from ensemble.ports import ScopeSubjectPort
from ensemble_shared.harness import HarnessPort

_TASK_ID_RE = re.compile(r"\bT-(\d+)\b", re.IGNORECASE)
_ITEM_ID_RE = re.compile(r"^\s*((?:G|IS|NG)-\d+)\s*:\s*(.+)$", re.IGNORECASE)


class ScopeError(RuntimeError):
    """Scope-drift motorunun açık ve verdict'e çevrilmeyen hata tabanı."""


class ScopeReferenceError(ScopeError):
    """İstenen ref `.harness` task/active kayıtlarından çözülemedi."""


class ScopeUnavailableError(ScopeError):
    """Scope belgesi judge için kullanılamıyor (taslak/boş)."""


def resolve_scope_subject(
    harness_port: HarnessPort,
    ref: str,
    *,
    subject_port: ScopeSubjectPort | None,
    default_sprint: str,
) -> ScopeSubject:
    clean_ref = ref.strip()
    if not clean_ref:
        raise ScopeReferenceError("scope ref boş olamaz")
    if subject_port is not None:
        subject = subject_port.resolve_scope_subject(clean_ref)
        if not subject.text.strip() and not subject.files:
            raise ScopeReferenceError(
                f"scope ref için değerlendirilebilir içerik yok: {clean_ref}"
            )
        return subject.model_copy(
            update={
                "ref": clean_ref,
                "text": subject.text.strip() or "\n".join(sorted(subject.files)),
                "files": sorted(set(subject.files)),
            }
        )

    tasks = harness_port.read_tasks()
    active = harness_port.read_active()
    task_id = _task_id_from_ref(clean_ref)
    matched_task = next(
        (task for task in tasks if _record_matches(task, clean_ref, task_id)),
        None,
    )
    matched_active = [
        decl for decl in active if _record_matches(decl, clean_ref, task_id)
    ]

    if matched_task is None and matched_active:
        active_task_id = str(matched_active[0].get("task_id") or "")
        matched_task = next(
            (task for task in tasks if task.get("task_id") == active_task_id),
            None,
        )
    if matched_task is None and not matched_active:
        raise ScopeReferenceError(
            f"scope ref `.harness/tasks` veya `.harness/active` içinde bulunamadı: {clean_ref}"
        )

    records = ([matched_task] if matched_task is not None else []) + matched_active
    text_parts: list[str] = []
    files: set[str] = set()
    for record in records:
        for key in ("title", "body", "intent", "module"):
            value = str(record.get(key) or "").strip()
            if value and value not in text_parts:
                text_parts.append(value)
        for path in record.get("paths") or []:
            path_text = str(path).strip()
            if path_text:
                files.add(path_text)

    if not text_parts and not files:
        raise ScopeReferenceError(f"scope ref için değerlendirilebilir içerik yok: {clean_ref}")
    sprint = next(
        (str(record["sprint"]) for record in records if record.get("sprint")),
        default_sprint,
    )
    return ScopeSubject(
        ref=clean_ref,
        text="\n".join(text_parts or sorted(files)),
        files=sorted(files),
        sprint=sprint,
    )


def scope_items(scope: dict[str, Any]) -> list[ScopeItemRef]:
    if str(scope.get("status") or "").casefold() == "draft":
        raise ScopeUnavailableError("scope belgesi taslak; PO dondurmadan judge çalıştırılmaz")

    items: list[ScopeItemRef] = []
    body = str(scope.get("body") or "").strip()
    if body:
        items.append(_scope_item(body, "goal"))
    items.extend(_scope_item(str(value), "in_scope") for value in scope.get("goals") or [])
    items.extend(
        _scope_item(str(value), "non_goals") for value in scope.get("non_goals") or []
    )
    if not any(item.section == "in_scope" for item in items):
        raise ScopeUnavailableError("scope belgesinde en az bir in_scope/goals maddesi gerekli")
    return items


def scope_quote_text(quote: str) -> str:
    match = _ITEM_ID_RE.match(quote)
    return match.group(2) if match else quote


def _task_id_from_ref(ref: str) -> str | None:
    match = _TASK_ID_RE.search(ref)
    return f"T-{match.group(1)}" if match else None


def _record_matches(record: dict[str, Any], ref: str, task_id: str | None) -> bool:
    wanted = ref.casefold()
    values = {
        str(record.get(key) or "").strip().casefold()
        for key in ("task_id", "branch", "ref")
    }
    if wanted in values:
        return True
    return task_id is not None and task_id.casefold() in values


def _scope_item(raw: str, section: str) -> ScopeItemRef:
    quote = raw.strip()
    match = _ITEM_ID_RE.match(quote)
    return ScopeItemRef(
        quote=quote,
        item_id=match.group(1).upper() if match else None,
        section=section,  # type: ignore[arg-type]
        line=None,
    )

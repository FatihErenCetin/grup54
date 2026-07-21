from __future__ import annotations

import re
import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import Any

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from ensemble.models import QueryCorpus, QueryDocument
from ensemble.store.models import EventRow
from ensemble_shared.harness import HarnessError, HarnessPort

_ITEM_ID_RE = re.compile(r"^\s*((?:G|IS|NG)-\d+)\s*:", re.IGNORECASE)
_TASK_ID_RE = re.compile(r"^T-(\d+)$", re.IGNORECASE)


class HarnessEventQuerySource:
    """Kanonik `.harness` ile event projeksiyonunu Ask corpus'una dönüştürür."""

    def __init__(
        self,
        harness_port: HarnessPort,
        *,
        session_factory: Callable[[], Session] | None = None,
        sprint: str = "3",
        event_limit: int = 200,
        repo_root: Path | str = ".",
        github_owner: str | None = None,
        github_repo: str | None = None,
    ) -> None:
        if not sprint:
            raise ValueError("sprint must not be empty")
        if event_limit < 0:
            raise ValueError("event_limit must be non-negative")
        self.harness_port = harness_port
        self.session_factory = session_factory
        self.sprint = sprint
        self.event_limit = event_limit
        self.repo_root = Path(repo_root)
        self.github_owner = github_owner
        self.github_repo = github_repo

    def load_query_corpus(self) -> QueryCorpus:
        documents = [*self._scope_documents(), *self._task_documents()]
        event_documents, event_last_commit = self._event_documents()
        documents.extend(event_documents)
        return QueryCorpus(
            documents=documents,
            last_commit=event_last_commit or self._git_commit() or "unavailable",
        )

    def _scope_documents(self) -> list[QueryDocument]:
        try:
            scope = self.harness_port.read_scope(self.sprint)
        except HarnessError:
            return []

        path = str(scope.get("path") or f".harness/scope/sprint-{self.sprint}.md")
        values = [
            str(scope.get("body") or "").strip(),
            *(str(value).strip() for value in scope.get("goals") or []),
            *(str(value).strip() for value in scope.get("non_goals") or []),
        ]
        documents: list[QueryDocument] = []
        for index, quote in enumerate(value for value in values if value):
            item_match = _ITEM_ID_RE.match(quote)
            anchor = item_match.group(1).upper() if item_match else f"item-{index + 1}"
            documents.append(
                QueryDocument(
                    id=f"scope:{path}:{anchor}",
                    type="scope",
                    ref=f"{path}#{anchor}",
                    quote=quote,
                    text=quote,
                )
            )
        return documents

    def _task_documents(self) -> list[QueryDocument]:
        try:
            tasks = self.harness_port.read_tasks()
            active = self.harness_port.read_active()
        except HarnessError:
            return []

        active_by_task: dict[str, list[dict[str, Any]]] = {}
        for declaration in active:
            ref = str(declaration.get("task_id") or declaration.get("branch") or "").strip()
            if ref:
                active_by_task.setdefault(ref, []).append(declaration)

        documents: list[QueryDocument] = []
        known_refs: set[str] = set()
        for task in tasks:
            ref = str(task.get("task_id") or task.get("ref") or "").strip()
            if not ref:
                continue
            title = str(task.get("title") or "").strip()
            body = str(task.get("body") or "").strip()
            extras = list(
                filter(None, (_active_text(item) for item in active_by_task.get(ref, [])))
            )
            text = "\n".join(part for part in [title, body, *extras] if part)
            if not text:
                continue
            known_refs.add(ref)
            documents.append(
                QueryDocument(
                    id=f"task:{ref}",
                    type="task",
                    ref=ref,
                    quote=title or body,
                    text=text,
                    url=self._issue_url(ref),
                )
            )

        for ref, declarations in active_by_task.items():
            if ref in known_refs:
                continue
            text = "\n".join(filter(None, (_active_text(item) for item in declarations)))
            if text:
                documents.append(
                    QueryDocument(
                        id=f"active:{ref}",
                        type="task",
                        ref=ref,
                        quote=text,
                        text=text,
                        url=self._issue_url(ref),
                    )
                )
        return documents

    def _event_documents(self) -> tuple[list[QueryDocument], str | None]:
        if self.session_factory is None or self.event_limit == 0:
            return [], None
        try:
            with self.session_factory() as session:
                rows = (
                    session.query(EventRow)
                    .order_by(EventRow.ts.desc(), EventRow.id.desc())
                    .limit(self.event_limit)
                    .all()
                )
        except SQLAlchemyError:
            return [], None

        documents: list[QueryDocument] = []
        last_commit: str | None = None
        for row in rows:
            event = row.to_domain()
            if event.type == "commit" and last_commit is None:
                last_commit = event.ref
            citation_type = "pr" if event.type == "pr" else "event"
            text = " ".join(
                part
                for part in (
                    f"{event.type} {event.ref}",
                    f"actor {event.actor}",
                    f"branch {event.branch}" if event.branch else "",
                    f"files {' '.join(event.files)}" if event.files else "",
                )
                if part
            )
            documents.append(
                QueryDocument(
                    id=event.id,
                    type=citation_type,
                    ref=event.ref,
                    quote=event.ref,
                    text=text,
                    url=self._event_url(event.type, event.ref),
                    occurred_at=event.ts,
                )
            )
        return documents, last_commit

    def _issue_url(self, ref: str) -> str | None:
        match = _TASK_ID_RE.match(ref)
        if match is None or not self.github_owner or not self.github_repo:
            return None
        return f"https://github.com/{self.github_owner}/{self.github_repo}/issues/{match.group(1)}"

    def _event_url(self, event_type: str, ref: str) -> str | None:
        if not self.github_owner or not self.github_repo:
            return None
        base = f"https://github.com/{self.github_owner}/{self.github_repo}"
        if event_type == "pr" and ref.isdigit():
            return f"{base}/pull/{ref}"
        if event_type == "issue" and ref.isdigit():
            return f"{base}/issues/{ref}"
        if event_type == "commit":
            return f"{base}/commit/{ref}"
        return None

    def _git_commit(self) -> str | None:
        try:
            result = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=self.repo_root,
                capture_output=True,
                text=True,
                check=False,
                encoding="utf-8",
                timeout=3,
            )
        except (OSError, subprocess.SubprocessError):
            return None
        commit = result.stdout.strip()
        return commit if result.returncode == 0 and commit else None


def _active_text(declaration: dict[str, Any]) -> str:
    return " ".join(
        part
        for part in (
            str(declaration.get("intent") or "").strip(),
            str(declaration.get("module") or "").strip(),
            str(declaration.get("branch") or "").strip(),
        )
        if part
    )

from __future__ import annotations

import re
import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import Any

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from ensemble.models import QueryCorpus, QueryDocument
from ensemble.store.models import DEFAULT_REPO_FULL_NAME, EventRow
from ensemble_shared.harness import HarnessError, HarnessPort

_ITEM_ID_RE = re.compile(r"^\s*((?:G|IS|NG)-\d+)\s*:", re.IGNORECASE)
_TASK_ID_RE = re.compile(r"^T-(\d+)$", re.IGNORECASE)


class HarnessEventQuerySource:
    """Kanonik `.harness` ile event projeksiyonunu Ask corpus'una dönüştürür.

    `repo_full_name` (T-79, çok-kiracılık): event sorgusu bu kiracıya filtrelenir.
    `.harness`-türevi belgeler (scope/task) yalnız demo kiracı için anlamlıdır —
    non-demo kiracılara TenantRegistry `HarnessError` fırlatan dürüst-boş bir
    port verir (`_scope_documents`/`_task_documents` bunu zaten YAKALAR ve boş
    liste döner, bu sınıf ayrım YAPMAZ)."""

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
        repo_full_name: str = DEFAULT_REPO_FULL_NAME,
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
        self.repo_full_name = repo_full_name

    def load_query_corpus(self) -> QueryCorpus:
        documents = [
            *self._scope_documents(),
            *self._task_documents(),
            *self._decision_documents(),
        ]
        event_documents, event_last_commit, events_truncated = self._event_documents()
        documents.extend(event_documents)
        return QueryCorpus(
            documents=documents,
            last_commit=event_last_commit or self._git_commit() or "unavailable",
            events_truncated=events_truncated,
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

    def _decision_documents(self) -> list[QueryDocument]:
        """`.harness/decisions/D-NN-*.md` → Ask korpusu.

        Bu kaynağın diğerlerinden FARKI ve neden en değerlisi: scope "ne
        yapılacak", task "kim yapıyor", event "ne oldu" der. Karar kaydı
        **NEDEN** der — ve bir kararı DEĞİŞTİREN tek şey başka bir karardır.
        Korpusta olmadığı sürece ürün, kararla çürütülmüş eski görev metnini
        hâlâ geçerliymiş gibi cevaplar (ölçüldü: "Fly backend", oysa D-46 ile
        VDS'e geçilmişti).

        Gövde `text`e girer (aranan), ama `quote` BAŞLIKtır: kullanıcıya
        gösterilen alıntı 3 sayfalık bir ADR gövdesi değil, kararın kendisi
        olmalı. Başlık yoksa gövdenin ilk anlamlı satırına düşer — uydurma
        bir özet ÜRETİLMEZ.
        """
        try:
            decisions = self.harness_port.read_decisions()
        except HarnessError:
            # `_scope_documents`/`_task_documents` ile aynı kural: `.harness`
            # yoksa (non-demo kiracı) Ask çökmez, o kaynak boş kalır.
            #
            # `AttributeError` BİLEREK yakalanmıyor: metodu taşımayan bir port
            # bizim hatamızdır, sağlayıcı arızası değil. Yakalasaydık tam da
            # bu bug'ın kendisini yeniden üretirdik — kaynak sessizce boş
            # kalır, makbuz `decision: 0` basar, kimse fark etmez. Kural
            # (D-63/#330 ile aynı): sağlayıcı arızasında yumuşa, KENDİ
            # sözleşmemizin ihlalinde patla.
            return []

        documents: list[QueryDocument] = []
        for decision in decisions:
            ref = str(decision.get("id") or "").strip()
            if not ref:
                continue
            title = str(decision.get("title") or "").strip()
            body = str(decision.get("body") or "").strip()
            text = "\n".join(part for part in [title, body] if part)
            if not text:
                continue
            documents.append(
                QueryDocument(
                    id=f"decision:{ref}",
                    type="decision",
                    ref=ref,
                    quote=title or _ilk_anlamli_satir(body),
                    text=text,
                    url=self._decision_url(decision),
                )
            )
        return documents

    def _decision_url(self, decision: dict[str, Any]) -> str | None:
        """Karar dosyasının GitHub'daki adresi — depo bilinmiyorsa `None`.

        Uydurma bir URL basmaktansa link vermemek doğru (ölü link, yanlış
        linkten iyidir ama ikisi de kötü; yokluk dürüst olan)."""
        path = str(decision.get("path") or "").strip()
        if not path or not self.github_owner or not self.github_repo:
            return None
        return f"https://github.com/{self.github_owner}/{self.github_repo}/blob/main/{path}"

    def _event_documents(self) -> tuple[list[QueryDocument], str | None, bool]:
        """(belgeler, son commit ref'i, `event_limit`'e DAYANILDI mı).

        Üçüncü değer (#322 review, Semih): `limit(event_limit)` tam dolduysa
        DB'de daha eski olaylar KALMIŞ olabilir — bunu yalnız burası bilir,
        çağıran (`QueryService.scan`) corpus'a bakarak ayırt EDEMEZ. "Tam 200
        olay vardı" ile "200'de kesildi" aynı listeyi üretir; fark yalnız
        buradan taşınabilir."""
        if self.session_factory is None or self.event_limit == 0:
            return [], None, False
        try:
            with self.session_factory() as session:
                rows = (
                    session.query(EventRow)
                    .filter_by(repo_full_name=self.repo_full_name)
                    .order_by(EventRow.ts.desc(), EventRow.id.desc())
                    .limit(self.event_limit)
                    .all()
                )
        except SQLAlchemyError:
            return [], None, False
        events_truncated = len(rows) >= self.event_limit

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
        return documents, last_commit, events_truncated

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
        root = Path(self.repo_root)
        if not (root / ".git").exists():
            return None
        try:
            result = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=root,
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


def _ilk_anlamli_satir(body: str) -> str:
    """Markdown gövdesinin ilk gerçek cümlesi — başlık işaretleri atılır.

    Alıntı olarak kullanılır (başlığı olmayan karar kaydı için). Uydurma bir
    özet ÜRETİLMEZ: metnin kendisinden bir satır seçilir, yeniden yazılmaz."""
    for satir in body.splitlines():
        temiz = satir.strip().lstrip("#").strip()
        if temiz:
            return temiz
    return ""


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

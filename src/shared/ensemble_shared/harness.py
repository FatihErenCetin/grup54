from __future__ import annotations

import json
import os
import re
import tempfile
from dataclasses import dataclass
from datetime import date, datetime
from importlib import resources
from pathlib import Path
from typing import Any, Protocol

import yaml
from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError as JsonSchemaValidationError


class HarnessPort(Protocol):
    """Contract for the single .harness/ read/write boundary."""

    def read_scope(self, sprint: str) -> dict[str, Any]: ...

    def read_tasks(self) -> list[dict[str, Any]]: ...

    def read_active(self) -> list[dict[str, Any]]: ...

    def write_active(self, handle: str, decl: dict[str, Any]) -> None: ...


class HarnessError(Exception):
    """Base error for .harness IO."""


class HarnessValidationError(HarnessError, ValueError):
    """Raised when front-matter is missing or does not match JSON schema."""


_SAFE_HANDLE = re.compile(r"^[A-Za-z0-9_.-]+$")


def _coerce_dates(value: Any) -> Any:
    """YAML'in tirnaksiz ISO tarihleri datetime'a cevirmesini geri al (semalar string bekler)."""
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, list):
        return [_coerce_dates(item) for item in value]
    if isinstance(value, dict):
        return {key: _coerce_dates(item) for key, item in value.items()}
    return value


@dataclass(frozen=True)
class HarnessMarkdown:
    path: Path
    frontmatter: dict[str, Any]
    body: str

    def as_dict(self, root: Path) -> dict[str, Any]:
        return {
            **self.frontmatter,
            "body": self.body,
            "path": self.path.relative_to(root).as_posix(),
        }


class FileHarnessPort:
    """Filesystem implementation of HarnessPort.

    All direct .harness/ reads and writes should go through this adapter so
    engine, MCP, and onboarding flows do not duplicate file-system logic.
    """

    def __init__(self, root: Path | str = ".", schema_dir: Path | str | None = None) -> None:
        self.root = Path(root)
        self.harness_dir = self.root / ".harness"
        # None = semalar PAKET verisinden yuklenir (ensemble_shared/schemas). Semalar URUNUN
        # parcasidir, izlenen reponun degil — Ensemble baska repolari izler (bkz. #83).
        self.schema_dir = Path(schema_dir) if schema_dir else None
        self._validators: dict[str, Draft202012Validator] = {}

    def read_scope(self, sprint: str) -> dict[str, Any]:
        """Read one scope document from .harness/scope/."""
        if not _SAFE_HANDLE.fullmatch(sprint):
            raise HarnessValidationError(f"Unsafe sprint id: {sprint!r}")
        path = self._scope_path(sprint)
        return self._read_markdown(path, "scope").as_dict(self.root)

    def read_tasks(self) -> list[dict[str, Any]]:
        """Read every task document from .harness/tasks/."""
        return [doc.as_dict(self.root) for doc in self._read_many("tasks", "task")]

    def read_active(self) -> list[dict[str, Any]]:
        """Read every active declaration from .harness/active/."""
        return [doc.as_dict(self.root) for doc in self._read_many("active", "active")]

    def write_active(self, handle: str, decl: dict[str, Any]) -> None:
        """Atomically write .harness/active/<handle>.md.

        The file name is derived only from handle, so each author has exactly
        one active declaration file. A second call with the same handle replaces
        that file instead of creating a sibling.
        """
        if not _SAFE_HANDLE.fullmatch(handle):
            raise HarnessValidationError(f"Unsafe active handle: {handle!r}")

        active_dir = self.harness_dir / "active"
        active_dir.mkdir(parents=True, exist_ok=True)

        frontmatter = dict(decl)
        body = str(frontmatter.pop("body", "")).rstrip() + "\n"
        frontmatter["type"] = "active"
        frontmatter["handle"] = handle

        self._validate_frontmatter(frontmatter, "active")
        self._atomic_write(active_dir / f"{handle}.md", self._to_markdown(frontmatter, body))

    def _scope_path(self, sprint: str) -> Path:
        scope_dir = self.harness_dir / "scope"
        candidates = [scope_dir / f"{sprint}.md"]
        if not sprint.startswith("sprint-"):
            candidates.append(scope_dir / f"sprint-{sprint}.md")

        for candidate in candidates:
            if candidate.exists():
                return candidate
        return candidates[-1]

    def _read_many(self, folder: str, expected_type: str) -> list[HarnessMarkdown]:
        directory = self.harness_dir / folder
        if not directory.exists():
            return []
        return [self._read_markdown(path, expected_type) for path in sorted(directory.glob("*.md"))]

    def _read_markdown(self, path: Path, expected_type: str) -> HarnessMarkdown:
        try:
            text = path.read_text(encoding="utf-8-sig")
        except FileNotFoundError as exc:
            raise HarnessError(f"Harness file not found: {path}") from exc

        frontmatter, body = self._parse_frontmatter(text, path)
        self._validate_frontmatter(frontmatter, expected_type)
        return HarnessMarkdown(path=path, frontmatter=frontmatter, body=body)

    def _parse_frontmatter(self, text: str, path: Path) -> tuple[dict[str, Any], str]:
        lines = text.splitlines()
        if not lines or lines[0] != "---":
            raise HarnessValidationError(f"Missing front-matter delimiter in {path}")

        end_index = None
        for index, line in enumerate(lines[1:], start=1):
            if line == "---":  # kolon-0 tam eslesme — block scalar icindeki girintili '---' kapanis sayilmaz
                end_index = index
                break

        if end_index is None:
            raise HarnessValidationError(f"Unclosed front-matter block in {path}")

        raw_frontmatter = "\n".join(lines[1:end_index])
        parsed = yaml.safe_load(raw_frontmatter) or {}
        if not isinstance(parsed, dict):
            raise HarnessValidationError(f"Front-matter must be an object in {path}")
        parsed = _coerce_dates(parsed)

        body = "\n".join(lines[end_index + 1 :]).lstrip("\n")
        return parsed, body

    def _validate_frontmatter(self, frontmatter: dict[str, Any], expected_type: str) -> None:
        actual_type = frontmatter.get("type")
        if actual_type != expected_type:
            raise HarnessValidationError(f"Expected type={expected_type!r}, got {actual_type!r}")

        validator = self._validator(expected_type)
        try:
            validator.validate(frontmatter)
        except JsonSchemaValidationError as exc:
            path = ".".join(str(part) for part in exc.path) or "<root>"
            message = f"Invalid {expected_type} front-matter at {path}: {exc.message}"
            raise HarnessValidationError(message) from exc

    def _validator(self, doc_type: str) -> Draft202012Validator:
        if doc_type not in self._validators:
            name = f"{doc_type}.schema.json"
            try:
                if self.schema_dir is not None:
                    raw = (self.schema_dir / name).read_text(encoding="utf-8")
                else:
                    schemas = resources.files("ensemble_shared").joinpath("schemas")
                    raw = schemas.joinpath(name).read_text(encoding="utf-8")
            except FileNotFoundError as exc:
                raise HarnessError(f"Harness schema not found: {name}") from exc
            self._validators[doc_type] = Draft202012Validator(json.loads(raw))
        return self._validators[doc_type]

    def _to_markdown(self, frontmatter: dict[str, Any], body: str) -> str:
        frontmatter_text = yaml.safe_dump(frontmatter, allow_unicode=True, sort_keys=False).strip()
        return f"---\n{frontmatter_text}\n---\n{body}"

    def _atomic_write(self, target: Path, text: str) -> None:
        fd, tmp_name = tempfile.mkstemp(prefix=f".{target.name}.", suffix=".tmp", dir=target.parent)
        tmp_path = Path(tmp_name)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as tmp_file:
                tmp_file.write(text)
                tmp_file.flush()
                os.fsync(tmp_file.fileno())
            os.replace(tmp_path, target)
        except Exception:
            tmp_path.unlink(missing_ok=True)
            raise

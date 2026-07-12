from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal


ChunkType = Literal["markdown", "diff", "text"]


@dataclass(frozen=True)
class Chunk:
    text: str
    meta: dict[str, str]


_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+)$")
_HUNK_RE = re.compile(r"^@@\s.*@@")
_TASK_RE = re.compile(r"\bT-(\d+)\b|#(\d+)")
_SPRINT_RE = re.compile(r"\bsprint[-\s]?(\d+)\b", re.IGNORECASE)


def chunk_text(
    text: str,
    path: str,
    chunk_type: ChunkType = "text",
    max_chars: int = 2000,
) -> list[Chunk]:
    if chunk_type == "markdown":
        return chunk_markdown(text, path=path, max_chars=max_chars)
    if chunk_type == "diff":
        return chunk_diff(text, path=path, max_chars=max_chars)
    return _split_plain(text, path=path, chunk_type=chunk_type, max_chars=max_chars)


def chunk_markdown(text: str, path: str, max_chars: int = 2000) -> list[Chunk]:
    chunks: list[Chunk] = []
    current_heading = ""
    current_lines: list[str] = []

    for line in text.splitlines():
        heading = _HEADING_RE.match(line)
        if heading and current_lines:
            chunks.extend(
                _split_with_meta(
                    "\n".join(current_lines).strip(),
                    path=path,
                    chunk_type="markdown",
                    heading=current_heading,
                    max_chars=max_chars,
                )
            )
            current_lines = []

        if heading:
            current_heading = heading.group(2).strip()

        current_lines.append(line)

    if current_lines:
        chunks.extend(
            _split_with_meta(
                "\n".join(current_lines).strip(),
                path=path,
                chunk_type="markdown",
                heading=current_heading,
                max_chars=max_chars,
            )
        )

    return chunks


def chunk_diff(text: str, path: str, max_chars: int = 2000) -> list[Chunk]:
    chunks: list[Chunk] = []
    current_hunk = ""
    current_lines: list[str] = []

    for line in text.splitlines():
        if _HUNK_RE.match(line) and current_lines:
            chunks.extend(
                _split_with_meta(
                    "\n".join(current_lines).strip(),
                    path=path,
                    chunk_type="diff",
                    heading=current_hunk,
                    max_chars=max_chars,
                )
            )
            current_lines = []

        if _HUNK_RE.match(line):
            current_hunk = line.strip()

        current_lines.append(line)

    if current_lines:
        chunks.extend(
            _split_with_meta(
                "\n".join(current_lines).strip(),
                path=path,
                chunk_type="diff",
                heading=current_hunk,
                max_chars=max_chars,
            )
        )

    return chunks


def _split_plain(
    text: str, path: str, chunk_type: ChunkType, max_chars: int
) -> list[Chunk]:
    return _split_with_meta(
        text.strip(), path=path, chunk_type=chunk_type, heading="", max_chars=max_chars
    )


def _split_with_meta(
    text: str,
    path: str,
    chunk_type: ChunkType,
    heading: str,
    max_chars: int,
) -> list[Chunk]:
    if not text:
        return []

    chunks: list[Chunk] = []
    for index, part in enumerate(_split_by_size(text, max_chars=max_chars)):
        meta = {
            "path": path,
            "type": chunk_type,
            "chunk_index": str(index),
        }
        if heading:
            meta["section"] = heading
        if task_id := _extract_task_id(part):
            meta["task_id"] = task_id
        if sprint := _extract_sprint(part):
            meta["sprint"] = sprint
        chunks.append(Chunk(text=part, meta=meta))
    return chunks


def _split_by_size(text: str, max_chars: int) -> list[str]:
    if max_chars <= 0:
        raise ValueError("max_chars must be positive")
    if len(text) <= max_chars:
        return [text]

    parts: list[str] = []
    current = ""
    for paragraph in text.split("\n\n"):
        if len(paragraph) > max_chars:
            if current:
                parts.append(current)
                current = ""
            parts.extend(_split_oversized(paragraph, max_chars=max_chars))
            continue

        candidate = f"{current}\n\n{paragraph}".strip() if current else paragraph
        if len(candidate) <= max_chars:
            current = candidate
            continue
        if current:
            parts.append(current)
        current = paragraph

    if current:
        parts.append(current)
    return parts


def _split_oversized(text: str, max_chars: int) -> list[str]:
    return [text[index : index + max_chars] for index in range(0, len(text), max_chars)]


def _extract_task_id(text: str) -> str | None:
    match = _TASK_RE.search(text)
    if not match:
        return None
    number = match.group(1) or match.group(2)
    return f"T-{number}"


def _extract_sprint(text: str) -> str | None:
    match = _SPRINT_RE.search(text)
    if not match:
        return None
    return f"sprint-{match.group(1)}"

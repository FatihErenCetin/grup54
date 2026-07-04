from pathlib import Path
from textwrap import dedent

import pytest

from ensemble_shared.harness import FileHarnessPort, HarnessError, HarnessValidationError


SCHEMA_DIR = Path(__file__).parents[2] / "shared" / "harness-schema"


def write_md(path: Path, frontmatter: str, body: str = "") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"---\n{dedent(frontmatter).strip()}\n---\n{body}", encoding="utf-8")


def test_read_scope_validates_frontmatter(tmp_path: Path):
    write_md(
        tmp_path / ".harness/scope/sprint-2.md",
        """
        type: scope
        sprint: "2"
        title: Sprint 2 scope
        """,
        "Only harness IO is in scope.\n",
    )

    port = FileHarnessPort(tmp_path, schema_dir=SCHEMA_DIR)

    scope = port.read_scope("2")
    assert scope["title"] == "Sprint 2 scope"
    assert scope["body"] == "Only harness IO is in scope."
    assert scope["path"] == ".harness/scope/sprint-2.md"


def test_read_tasks_validates_task_frontmatter(tmp_path: Path):
    write_md(
        tmp_path / ".harness/tasks/T-13.md",
        """
        type: task
        task_id: T-13
        title: Harness port
        status: in_progress
        assignee: asmarufoglu
        paths:
          - src/shared/ensemble_shared/harness.py
        """,
    )

    port = FileHarnessPort(tmp_path, schema_dir=SCHEMA_DIR)

    tasks = port.read_tasks()
    assert len(tasks) == 1
    assert tasks[0]["task_id"] == "T-13"
    assert tasks[0]["paths"] == ["src/shared/ensemble_shared/harness.py"]


def test_read_active_validates_active_frontmatter(tmp_path: Path):
    write_md(
        tmp_path / ".harness/active/asmarufoglu.md",
        """
        type: active
        handle: asmarufoglu
        task_id: T-13
        branch: T-13-harness-port
        paths:
          - src/shared/ensemble_shared/harness.py
        updated_at: "2026-07-03T12:00:00+03:00"
        """,
    )

    port = FileHarnessPort(tmp_path, schema_dir=SCHEMA_DIR)

    active = port.read_active()
    assert len(active) == 1
    assert active[0]["handle"] == "asmarufoglu"
    assert active[0]["task_id"] == "T-13"


def test_invalid_frontmatter_raises_validation_error(tmp_path: Path):
    write_md(
        tmp_path / ".harness/active/asmarufoglu.md",
        """
        type: active
        handle: asmarufoglu
        branch: T-13-harness-port
        paths: []
        updated_at: "2026-07-03T12:00:00+03:00"
        """,
    )

    port = FileHarnessPort(tmp_path, schema_dir=SCHEMA_DIR)

    with pytest.raises(HarnessValidationError, match="task_id"):
        port.read_active()


def test_write_active_creates_one_atomic_file_per_handle(tmp_path: Path):
    port = FileHarnessPort(tmp_path, schema_dir=SCHEMA_DIR)

    port.write_active(
        "asmarufoglu",
        {
            "task_id": "T-13",
            "branch": "T-13-harness-port",
            "paths": ["src/shared/ensemble_shared/harness.py"],
            "updated_at": "2026-07-03T12:00:00+03:00",
            "body": "Working on HarnessPort.",
        },
    )
    port.write_active(
        "asmarufoglu",
        {
            "task_id": "T-13",
            "branch": "T-13-harness-port-v2",
            "paths": [
                "src/shared/ensemble_shared/harness.py",
                "shared/harness-schema/active.schema.json",
            ],
            "updated_at": "2026-07-03T12:05:00+03:00",
        },
    )

    active_files = sorted((tmp_path / ".harness/active").glob("*.md"))
    assert active_files == [tmp_path / ".harness/active/asmarufoglu.md"]

    active = port.read_active()[0]
    assert active["branch"] == "T-13-harness-port-v2"
    assert active["handle"] == "asmarufoglu"


def test_rejects_unsafe_active_handle(tmp_path: Path):
    port = FileHarnessPort(tmp_path, schema_dir=SCHEMA_DIR)

    with pytest.raises(HarnessValidationError, match="Unsafe active handle"):
        port.write_active("../enes", {})


def test_read_scope_missing_file_raises_harness_error(tmp_path: Path):
    port = FileHarnessPort(tmp_path, schema_dir=SCHEMA_DIR)

    with pytest.raises(HarnessError, match="Harness file not found"):
        port.read_scope("2")
